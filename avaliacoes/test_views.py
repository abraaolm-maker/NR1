import uuid

import pytest
from django.test import Client
from django.urls import reverse

from avaliacoes.models import EscoreDominio, Respondente, StatusAplicacao, TipoAplicacao
from avaliacoes.services.aplicacao_status import encerrar_coleta
from avaliacoes.services.calculo_risco import dominios_da_aplicacao


def _consentir(client, aplicacao):
    return client.post(
        reverse("avaliacoes:responder_consentimento", args=[aplicacao.token]),
        data={"participacao_voluntaria": "on", "li_e_compreendi": "on"},
        follow=True,
    )


def _preencher_perfil(client, aplicacao, nome=None):
    dados = {"tempo_na_organizacao": "3_a_5_anos", "modalidade_trabalho": "presencial"}
    if nome is not None:
        dados["nome"] = nome
    return client.post(reverse("avaliacoes:responder_perfil", args=[aplicacao.token]), data=dados, follow=True)


def _responder_todos_os_dominios(client, aplicacao, valor="3"):
    resp = None
    for dominio in dominios_da_aplicacao(aplicacao):
        url = reverse("avaliacoes:responder_dominio", args=[aplicacao.token, dominio.codigo])
        data = {item.item_id: valor for item in dominio.itens.all()}
        resp = client.post(url, data=data, follow=True)
    return resp


def _responder_perguntas_abertas(client, aplicacao, r1="", r2=""):
    return client.post(
        reverse("avaliacoes:responder_perguntas_abertas", args=[aplicacao.token]),
        data={"resposta_aberta_1": r1, "resposta_aberta_2": r2},
        follow=True,
    )


@pytest.mark.django_db
def test_token_invalido_retorna_404(client):
    resp = client.get(reverse("avaliacoes:responder_consentimento", args=[uuid.uuid4()]))
    assert resp.status_code == 404


@pytest.mark.django_db
def test_consentimento_exige_as_duas_declaracoes(client, aplicacao_copsoq):
    resp = client.post(
        reverse("avaliacoes:responder_consentimento", args=[aplicacao_copsoq.token]),
        data={"participacao_voluntaria": "on"},  # falta "li_e_compreendi"
    )
    assert resp.status_code == 200
    assert not Respondente.objects.filter(aplicacao=aplicacao_copsoq).exists()
    assert "necessário confirmar" in resp.content.decode().lower()


@pytest.mark.django_db
def test_consentir_cria_respondente_e_vai_para_perfil(client, aplicacao_copsoq):
    resp = _consentir(client, aplicacao_copsoq)
    assert resp.redirect_chain[-1][0] == reverse("avaliacoes:responder_perfil", args=[aplicacao_copsoq.token])
    assert Respondente.objects.filter(aplicacao=aplicacao_copsoq).count() == 1


@pytest.mark.django_db
def test_dominio_direto_sem_perfil_redireciona_para_perfil(client, aplicacao_copsoq):
    _consentir(client, aplicacao_copsoq)
    dominio = dominios_da_aplicacao(aplicacao_copsoq)[0]
    resp = client.get(
        reverse("avaliacoes:responder_dominio", args=[aplicacao_copsoq.token, dominio.codigo]), follow=True
    )
    assert resp.redirect_chain[-1][0] == reverse("avaliacoes:responder_perfil", args=[aplicacao_copsoq.token])


@pytest.mark.django_db
def test_perfil_completo_segue_para_primeiro_dominio(client, aplicacao_copsoq):
    _consentir(client, aplicacao_copsoq)
    resp = _preencher_perfil(client, aplicacao_copsoq)

    primeiro = dominios_da_aplicacao(aplicacao_copsoq)[0]
    assert resp.redirect_chain[-1][0] == reverse(
        "avaliacoes:responder_dominio", args=[aplicacao_copsoq.token, primeiro.codigo]
    )
    respondente = Respondente.objects.get(aplicacao=aplicacao_copsoq)
    assert respondente.tempo_na_organizacao == "3_a_5_anos"
    assert respondente.modalidade_trabalho == "presencial"


@pytest.mark.django_db
def test_resume_pula_dominios_ja_respondidos(client, aplicacao_copsoq):
    _consentir(client, aplicacao_copsoq)
    _preencher_perfil(client, aplicacao_copsoq)
    todos_dominios = dominios_da_aplicacao(aplicacao_copsoq)

    primeiro = todos_dominios[0]
    client.post(
        reverse("avaliacoes:responder_dominio", args=[aplicacao_copsoq.token, primeiro.codigo]),
        data={item.item_id: "3" for item in primeiro.itens.all()},
    )

    # reabrir o link (consentimento) deve pular direto pro segundo domínio
    resp = client.get(
        reverse("avaliacoes:responder_consentimento", args=[aplicacao_copsoq.token]), follow=True
    )
    segundo = todos_dominios[1]
    assert resp.redirect_chain[-1][0] == reverse(
        "avaliacoes:responder_dominio", args=[aplicacao_copsoq.token, segundo.codigo]
    )


@pytest.mark.django_db
def test_fluxo_completo_ate_perguntas_abertas_e_concluido(client, aplicacao_copsoq):
    _consentir(client, aplicacao_copsoq)
    _preencher_perfil(client, aplicacao_copsoq)
    resp = _responder_todos_os_dominios(client, aplicacao_copsoq)

    assert resp.redirect_chain[-1][0] == reverse(
        "avaliacoes:responder_perguntas_abertas", args=[aplicacao_copsoq.token]
    )

    resp = _responder_perguntas_abertas(client, aplicacao_copsoq, r1="Mais autonomia na rotina.")
    assert resp.redirect_chain[-1][0] == reverse("avaliacoes:responder_concluido", args=[aplicacao_copsoq.token])

    respondente = Respondente.objects.get(aplicacao=aplicacao_copsoq)
    assert respondente.concluido_em is not None
    assert respondente.resposta_aberta_1 == "Mais autonomia na rotina."
    assert respondente.perguntas_abertas_respondidas_em is not None

    # o fluxo real de resposta precisa disparar o cálculo — sem isso, EscoreDominio
    # nunca nasceria fora de uma chamada manual a calcular_dominio()
    assert EscoreDominio.objects.filter(aplicacao=aplicacao_copsoq).count() == len(
        dominios_da_aplicacao(aplicacao_copsoq)
    )

    # sem conjunto fixo de respondentes, ninguém "termina por todo mundo" — só o
    # gestor encerra a coleta manualmente (CLAUDE.md Seção 6.7)
    aplicacao_copsoq.refresh_from_db()
    assert aplicacao_copsoq.status == StatusAplicacao.EM_ANDAMENTO


@pytest.mark.django_db
def test_reabrir_link_apos_concluido_vai_direto_pra_tela_de_conclusao(client, aplicacao_copsoq):
    _consentir(client, aplicacao_copsoq)
    _preencher_perfil(client, aplicacao_copsoq)
    _responder_todos_os_dominios(client, aplicacao_copsoq)
    _responder_perguntas_abertas(client, aplicacao_copsoq)

    resp = client.get(
        reverse("avaliacoes:responder_consentimento", args=[aplicacao_copsoq.token]), follow=True
    )
    assert resp.redirect_chain[-1][0] == reverse("avaliacoes:responder_concluido", args=[aplicacao_copsoq.token])


@pytest.mark.django_db
def test_navegadores_diferentes_criam_respondentes_diferentes(client, aplicacao_copsoq):
    """O link é o mesmo pra todo mundo — quem diferencia uma pessoa da outra é a
    sessão do navegador, não mais um token individual (CLAUDE.md Seção 6.7)."""
    outro_client = Client()

    _consentir(client, aplicacao_copsoq)
    _consentir(outro_client, aplicacao_copsoq)

    assert Respondente.objects.filter(aplicacao=aplicacao_copsoq).count() == 2


@pytest.mark.django_db
def test_coleta_encerrada_bloqueia_novo_respondente(client, aplicacao_copsoq):
    encerrar_coleta(aplicacao_copsoq.pk)

    resp = client.get(reverse("avaliacoes:responder_consentimento", args=[aplicacao_copsoq.token]))

    assert resp.status_code == 200
    assert not Respondente.objects.filter(aplicacao=aplicacao_copsoq).exists()
    assert "encerrada" in resp.content.decode().lower()


@pytest.mark.django_db
def test_aplicacao_identificada_exige_nome_no_perfil(client, aplicacao_copsoq):
    aplicacao_copsoq.tipo = TipoAplicacao.IDENTIFICADA
    aplicacao_copsoq.save(update_fields=["tipo"])

    _consentir(client, aplicacao_copsoq)
    resp = client.post(
        reverse("avaliacoes:responder_perfil", args=[aplicacao_copsoq.token]),
        data={"tempo_na_organizacao": "3_a_5_anos", "modalidade_trabalho": "presencial"},  # sem nome
    )
    assert resp.status_code == 200
    respondente = Respondente.objects.get(aplicacao=aplicacao_copsoq)
    assert not respondente.nome

    _preencher_perfil(client, aplicacao_copsoq, nome="Maria")
    respondente.refresh_from_db()
    assert respondente.nome == "Maria"
