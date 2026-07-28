import pytest
from django.urls import reverse

from avaliacoes.models import (
    ColetaChecklistTriangulacao,
    ItemChecklistTriangulacao,
    RespondenteChecklistTriangulacao,
    RespostaChecklistTriangulacao,
    StatusColetaChecklist,
)


@pytest.fixture
def coleta_checklist(aplicacao_copsoq):
    return ColetaChecklistTriangulacao.objects.create(aplicacao=aplicacao_copsoq)


def _identificar(client, coleta, nome="Fulano de Tal", cargo="Gerente de Produção"):
    return client.post(
        reverse("avaliacoes:checklist_identificacao", args=[coleta.token]),
        data={"nome": nome, "cargo": cargo},
        follow=True,
    )


def _responder_grupo(client, coleta, tipo, conformidade="conforme"):
    itens = ItemChecklistTriangulacao.objects.filter(tipo=tipo)
    dados = {}
    for item in itens:
        dados[f"conformidade_{item.id}"] = conformidade
        dados[f"evidencia_{item.id}"] = ""
    return client.post(
        reverse("avaliacoes:checklist_grupo", args=[coleta.token, tipo]), data=dados, follow=True
    )


@pytest.mark.django_db
def test_identificacao_cria_respondente(client, coleta_checklist):
    resp = _identificar(client, coleta_checklist)

    assert resp.status_code == 200
    respondente = RespondenteChecklistTriangulacao.objects.get(coleta=coleta_checklist)
    assert respondente.nome == "Fulano de Tal"
    assert respondente.cargo == "Gerente de Produção"
    # já entra direto no primeiro grupo pendente
    assert resp.redirect_chain[-1][0] == reverse(
        "avaliacoes:checklist_grupo", args=[coleta_checklist.token, "entrevista"]
    )


@pytest.mark.django_db
def test_fluxo_completo_ate_conclusao(client, coleta_checklist):
    _identificar(client, coleta_checklist)
    _responder_grupo(client, coleta_checklist, "entrevista", conformidade="conforme")
    resp = _responder_grupo(client, coleta_checklist, "observacao", conformidade="nao_conforme")

    assert resp.status_code == 200
    assert "obrigado pela sua participa" in resp.content.decode().lower()

    respondente = RespondenteChecklistTriangulacao.objects.get(coleta=coleta_checklist)
    assert respondente.concluido_em is not None
    assert RespostaChecklistTriangulacao.objects.filter(respondente=respondente).count() == 16
    assert RespostaChecklistTriangulacao.objects.filter(
        respondente=respondente, conformidade="nao_conforme"
    ).count() == 10


@pytest.mark.django_db
def test_botao_anterior_volta_para_grupo_anterior(client, coleta_checklist):
    _identificar(client, coleta_checklist)
    resp = client.get(reverse("avaliacoes:checklist_grupo", args=[coleta_checklist.token, "entrevista"]))
    assert resp.status_code == 200
    assert b"Anterior" not in resp.content  # primeiro grupo: sem botão de voltar

    _responder_grupo(client, coleta_checklist, "entrevista")
    resp = client.get(reverse("avaliacoes:checklist_grupo", args=[coleta_checklist.token, "observacao"]))
    assert resp.status_code == 200
    url_anterior = reverse("avaliacoes:checklist_grupo", args=[coleta_checklist.token, "entrevista"])
    assert url_anterior.encode() in resp.content


@pytest.mark.django_db
def test_coleta_encerrada_bloqueia_novo_respondente(client, coleta_checklist):
    coleta_checklist.status = StatusColetaChecklist.ENCERRADA
    coleta_checklist.save(update_fields=["status"])

    resp = client.get(reverse("avaliacoes:checklist_identificacao", args=[coleta_checklist.token]))

    assert resp.status_code == 200
    assert "encerrada" in resp.content.decode().lower()
    assert not RespondenteChecklistTriangulacao.objects.filter(coleta=coleta_checklist).exists()


@pytest.mark.django_db
def test_reabrir_link_no_mesmo_navegador_retoma_progresso(client, coleta_checklist):
    _identificar(client, coleta_checklist)
    _responder_grupo(client, coleta_checklist, "entrevista")

    # reabre o link de identificação (mesma sessão) — deve pular direto pro grupo pendente
    resp = client.get(reverse("avaliacoes:checklist_identificacao", args=[coleta_checklist.token]), follow=True)

    assert resp.status_code == 200
    assert RespondenteChecklistTriangulacao.objects.filter(coleta=coleta_checklist).count() == 1
