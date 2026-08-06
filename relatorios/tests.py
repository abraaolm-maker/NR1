from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from avaliacoes.models import PlanoDeAcao
from avaliacoes.services.calculo_risco import calcular_dominio
from relatorios.models import PerfilProfissional, Relatorio, StatusRelatorio, TipoRelatorio
from relatorios.services.analise_ia import MODEL, gerar_e_salvar_parecer, gerar_parecer, montar_payload_relatorio
from relatorios.services.pdf import _contexto_relatorio, assinar_relatorio, gerar_pdf_relatorio
from relatorios.services.plano_acao_ia import gerar_e_salvar_planos_refinados, montar_payload_planos


class _FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, name: str, input_data: dict):
        self.name = name
        self.input = input_data


class _FakeResponse:
    def __init__(self, content):
        self.content = content


class _FakeMessages:
    def __init__(self, resposta):
        self._resposta = resposta
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return self._resposta


class _FakeAnthropicClient:
    def __init__(self, resposta):
        self.messages = _FakeMessages(resposta)


PARECER_DE_TESTE = {
    "sintese_executiva": "Panorama geral de teste.",
    "pareceres_por_dominio": [],
    "riscos_prioritarios": [],
    "recomendacoes": [],
    "aviso_minuta": "Minuta técnica sujeita a revisão e assinatura do profissional habilitado.",
}


@pytest.fixture
def relatorio_com_dominio_calculado(aplicacao_copsoq, responder_dominio):
    dominio_elevado = responder_dominio(
        aplicacao_copsoq,
        "D1",
        {"D1.1": 4, "D1.2": 4, "D1.3": 5, "D1.4": 3, "D1.5": 4},
        n_respondentes=5,
    )
    calcular_dominio(aplicacao_copsoq, dominio_elevado)

    dominio_suprimido = responder_dominio(
        aplicacao_copsoq,
        "D2",
        {"D2.1": 4, "D2.2": 4, "D2.3": 4, "D2.4": 4},
        n_respondentes=2,  # abaixo do N mínimo -> suprimido
    )
    calcular_dominio(aplicacao_copsoq, dominio_suprimido)

    relatorio = Relatorio.objects.create(
        unidade=aplicacao_copsoq.ghe.unidade,
        criterio_versao=aplicacao_copsoq.criterio_versao,
        periodo_inicio=date.today(),
        periodo_fim=date.today(),
    )
    relatorio.aplicacoes.add(aplicacao_copsoq)
    return relatorio


@pytest.fixture
def media_root_tmp(settings, tmp_path):
    """Evita que os PDFs gerados em teste sujem o media/ real do projeto."""
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


@pytest.mark.django_db
def test_montar_payload_relatorio_estrutura_e_supressao(relatorio_com_dominio_calculado):
    payload = montar_payload_relatorio(relatorio_com_dominio_calculado.pk)

    assert payload["unidade"] == "Unidade Teste"
    assert len(payload["ghes"]) == 1
    dominios = {d["dominio"]: d for d in payload["ghes"][0]["dominios"]}

    assert dominios["D1"]["escore"] == 75.0
    # 5 respondentes uniformes, todos elevados -> prevalência 100% -> Prioridade P1 -> Banda Alto
    assert dominios["D1"]["banda"] == "Alto"
    assert dominios["D1"]["suprimido_por_confidencialidade"] is False

    # domínio com N < mínimo nunca deve vazar escore pra IA, só a flag de supressão
    assert dominios["D2"]["suprimido_por_confidencialidade"] is True
    assert "escore" not in dominios["D2"]
    assert "banda" not in dominios["D2"]


def test_gerar_parecer_usa_tool_use_forcado():
    fake_response = _FakeResponse([_FakeToolUseBlock("gerar_parecer_tecnico", PARECER_DE_TESTE)])
    client = _FakeAnthropicClient(fake_response)

    resultado = gerar_parecer({"empresa": "Empresa Teste"}, client=client)

    assert resultado == PARECER_DE_TESTE
    assert client.messages.last_kwargs["model"] == MODEL
    assert client.messages.last_kwargs["tool_choice"] == {"type": "tool", "name": "gerar_parecer_tecnico"}


def test_gerar_parecer_sem_tool_use_levanta_erro():
    client = _FakeAnthropicClient(_FakeResponse([]))

    with pytest.raises(RuntimeError):
        gerar_parecer({"empresa": "Empresa Teste"}, client=client)


@pytest.mark.django_db
def test_gerar_e_salvar_parecer_persiste_sem_mudar_status(relatorio_com_dominio_calculado):
    # D1 sai como banda "Moderado" (não suprimido) — a validação de cobertura
    # (achado de 2026-07-29: IA devolvia riscos_prioritarios/recomendacoes vazios
    # mesmo com domínios fora de Aceitável) exige uma entrada por domínio nessas
    # duas listas pra todo domínio não-Aceitável e não suprimido.
    parecer_cobrindo_d1 = {
        **PARECER_DE_TESTE,
        "riscos_prioritarios": [
            {"ghe": "Equipe Teste", "dominio": "D1", "banda": "Moderado", "justificativa": "Teste."}
        ],
        "recomendacoes": [
            {
                "ghe": "Equipe Teste",
                "dominio": "D1",
                "banda": "Moderado",
                "hierarquia_controle": "organizacao",
                "medida_preventiva": "Teste.",
            }
        ],
    }
    fake_response = _FakeResponse([_FakeToolUseBlock("gerar_parecer_tecnico", parecer_cobrindo_d1)])
    client = _FakeAnthropicClient(fake_response)

    relatorio = gerar_e_salvar_parecer(relatorio_com_dominio_calculado.pk, client=client)

    assert relatorio.parecer_ia == parecer_cobrindo_d1
    assert relatorio.status == StatusRelatorio.AGUARDANDO_REVISAO


@pytest.mark.django_db
def test_gerar_e_salvar_parecer_incompleto_levanta_erro(relatorio_com_dominio_calculado):
    """D1 está fora de Aceitável (banda Moderado) — um parecer com listas vazias
    deve ser rejeitado, não persistido silenciosamente (achado de 2026-07-29)."""
    fake_response = _FakeResponse([_FakeToolUseBlock("gerar_parecer_tecnico", PARECER_DE_TESTE)])
    client = _FakeAnthropicClient(fake_response)

    with pytest.raises(RuntimeError, match="incompleto"):
        gerar_e_salvar_parecer(relatorio_com_dominio_calculado.pk, client=client)


@pytest.mark.django_db
def test_gerar_pdf_relatorio_minuta_tem_marca_dagua_e_nao_muda_status(
    relatorio_com_dominio_calculado, media_root_tmp
):
    relatorio_com_dominio_calculado.parecer_ia = PARECER_DE_TESTE
    relatorio_com_dominio_calculado.planos_refinados_em = timezone.now()
    relatorio_com_dominio_calculado.save(update_fields=["parecer_ia", "planos_refinados_em"])

    relatorio = gerar_pdf_relatorio(relatorio_com_dominio_calculado.pk)

    assert relatorio.status == StatusRelatorio.AGUARDANDO_REVISAO
    assert "minuta" in relatorio.pdf_path.name
    conteudo = relatorio.pdf_path.read()
    assert conteudo.startswith(b"%PDF")


@pytest.mark.django_db
def test_contexto_relatorio_inclui_checklist_triangulacao_avaliado(
    relatorio_com_dominio_calculado, aplicacao_copsoq
):
    from avaliacoes.models import (
        ColetaChecklistTriangulacao,
        ItemChecklistTriangulacao,
        RespondenteChecklistTriangulacao,
        RespostaChecklistTriangulacao,
    )

    coleta = ColetaChecklistTriangulacao.objects.create(aplicacao=aplicacao_copsoq)
    respondente = RespondenteChecklistTriangulacao.objects.create(coleta=coleta, nome="Gestor de Teste")
    item = ItemChecklistTriangulacao.objects.filter(tipo="entrevista").order_by("ordem").first()
    RespostaChecklistTriangulacao.objects.create(
        respondente=respondente, item=item, conformidade="conforme", evidencia="Evidência de teste."
    )

    contexto = _contexto_relatorio(relatorio_com_dominio_calculado, minuta=True)

    checklist = contexto["ghes"][0]["checklist_triangulacao"]
    assert list(checklist)[0].item == item
    assert list(checklist)[0].evidencia == "Evidência de teste."


@pytest.mark.django_db
def test_contexto_relatorio_inclui_grafico_semaforo_com_n_total(relatorio_com_dominio_calculado):
    contexto = _contexto_relatorio(relatorio_com_dominio_calculado, minuta=True)

    assert contexto["linhas_semaforo"]
    assert contexto["n_total_semaforo"] == max(
        linha["n_respondentes"] for linha in contexto["linhas_semaforo"]
    )
    linha_d1 = next(l for l in contexto["linhas_semaforo"] if l["dominio_codigo"] == "D1")
    # D1: 5 respondentes com valores {4,4,5,3,4} -> escore 75.0 -> risco (>= 62.5)
    assert linha_d1["pct_risco"] == 1.0


@pytest.mark.django_db
def test_gerar_pdf_relatorio_inclui_grafico_semaforo(relatorio_com_dominio_calculado, media_root_tmp):
    relatorio_com_dominio_calculado.parecer_ia = PARECER_DE_TESTE
    relatorio_com_dominio_calculado.planos_refinados_em = timezone.now()
    relatorio_com_dominio_calculado.save(update_fields=["parecer_ia", "planos_refinados_em"])

    relatorio = gerar_pdf_relatorio(relatorio_com_dominio_calculado.pk)

    conteudo = relatorio.pdf_path.read()
    assert conteudo.startswith(b"%PDF")  # confirma que a Seção 5 (gráfico) não quebra o WeasyPrint


@pytest.mark.django_db
def test_assinar_relatorio_sem_perfil_profissional_levanta_erro(relatorio_com_dominio_calculado):
    user = get_user_model().objects.create_user(username="sem_perfil", password="x")

    with pytest.raises(ValueError):
        assinar_relatorio(relatorio_com_dominio_calculado.pk, user.pk)


@pytest.mark.django_db
def test_assinar_relatorio_com_perfil_gera_pdf_final(relatorio_com_dominio_calculado, media_root_tmp):
    user = get_user_model().objects.create_user(username="resp_tecnico", password="x", first_name="Maria")
    PerfilProfissional.objects.create(
        user=user, titulo_profissional="Psicóloga do Trabalho", conselho="CRP", numero_registro="06/123456"
    )
    relatorio_com_dominio_calculado.parecer_ia = PARECER_DE_TESTE
    relatorio_com_dominio_calculado.planos_refinados_em = timezone.now()
    relatorio_com_dominio_calculado.save(update_fields=["parecer_ia", "planos_refinados_em"])

    relatorio = assinar_relatorio(relatorio_com_dominio_calculado.pk, user.pk)

    assert relatorio.status == StatusRelatorio.ASSINADO
    assert relatorio.assinado_por == user
    assert relatorio.assinado_em is not None
    assert "final" in relatorio.pdf_path.name
    conteudo = relatorio.pdf_path.read()
    assert conteudo.startswith(b"%PDF")


@pytest.mark.django_db
def test_assinar_relatorio_sem_parecer_levanta_erro(relatorio_com_dominio_calculado, media_root_tmp):
    """Achado no diagnóstico de UX de 2026-07-28: nada impedia assinar um relatório
    sem nenhum parecer técnico gerado — o documento "final" saía com a Seção 6 vazia."""
    user = get_user_model().objects.create_user(username="sem_parecer", password="x")
    PerfilProfissional.objects.create(
        user=user, titulo_profissional="Psicólogo do Trabalho", conselho="CRP", numero_registro="06/1"
    )

    with pytest.raises(ValueError, match="parecer"):
        assinar_relatorio(relatorio_com_dominio_calculado.pk, user.pk)


@pytest.mark.django_db
def test_montar_payload_planos_so_inclui_dominios_com_plano_gerado(relatorio_com_dominio_calculado):
    """D1 é Alto (tem PlanoDeAcao); D2 está suprimido por confidencialidade (nunca
    gera PlanoDeAcao, Seção 3 princípio 3) — não deve aparecer no payload."""
    payload = montar_payload_planos(relatorio_com_dominio_calculado.pk)

    dominios = {p["dominio"] for p in payload["planos"]}
    assert dominios == {"D1"}
    assert payload["planos"][0]["banda"] == "Alto"
    assert payload["planos"][0]["medida_catalogo"]


@pytest.mark.django_db
def test_gerar_e_salvar_planos_refinados_atualiza_plano_existente(relatorio_com_dominio_calculado):
    resultado_ia = {
        "planos_refinados": [
            {
                "ghe": "Equipe Teste",
                "dominio": "D1",
                "medida": "Medida refinada de teste para D1.",
                "hierarquia_controle": "organizacao",
                "indicador": "Indicador refinado de teste.",
            }
        ]
    }
    fake_response = _FakeResponse([_FakeToolUseBlock("refinar_plano_de_acao", resultado_ia)])
    client = _FakeAnthropicClient(fake_response)

    atualizados = gerar_e_salvar_planos_refinados(relatorio_com_dominio_calculado.pk, client=client)

    assert atualizados == 1
    plano = PlanoDeAcao.objects.get(classificacao_risco__escore_dominio__dominio__codigo="D1")
    assert plano.medida == "Medida refinada de teste para D1."
    assert plano.hierarquia == "organizacao"
    assert plano.indicador == "Indicador refinado de teste."


@pytest.mark.django_db
def test_gerar_pdf_sem_parecer_levanta_erro(relatorio_com_dominio_calculado, media_root_tmp):
    """Pedido do usuário em 2026-08-04: o PDF (mesmo em minuta) não pode ser gerado
    sem o parecer técnico, seja qual for o tipo do relatório."""
    with pytest.raises(ValueError, match="parecer"):
        gerar_pdf_relatorio(relatorio_com_dominio_calculado.pk)


@pytest.mark.django_db
def test_gerar_pdf_diagnostico_plano_acao_sem_refinar_levanta_erro(
    relatorio_com_dominio_calculado, media_root_tmp
):
    """Relatório do tipo Diagnóstico + Plano de Ação (default) só pode gerar PDF
    depois de "Gerar parecer via IA" E "Refinar planos de ação com IA"."""
    relatorio_com_dominio_calculado.parecer_ia = PARECER_DE_TESTE
    relatorio_com_dominio_calculado.save(update_fields=["parecer_ia"])

    with pytest.raises(ValueError, match="Plano de Ação"):
        gerar_pdf_relatorio(relatorio_com_dominio_calculado.pk)


@pytest.mark.django_db
def test_gerar_pdf_diagnostico_nao_exige_planos_refinados(relatorio_com_dominio_calculado, media_root_tmp):
    """Relatório do tipo Diagnóstico (sem Plano de Ação) só exige o parecer técnico —
    o refinamento do plano nem aparece nesse documento."""
    relatorio_com_dominio_calculado.tipo = TipoRelatorio.DIAGNOSTICO
    relatorio_com_dominio_calculado.parecer_ia = PARECER_DE_TESTE
    relatorio_com_dominio_calculado.save(update_fields=["tipo", "parecer_ia"])

    relatorio = gerar_pdf_relatorio(relatorio_com_dominio_calculado.pk)

    conteudo = relatorio.pdf_path.read()
    assert conteudo.startswith(b"%PDF")


@pytest.mark.django_db
def test_pdf_diagnostico_nao_inclui_secao_plano_de_acao(relatorio_com_dominio_calculado):
    relatorio_com_dominio_calculado.tipo = TipoRelatorio.DIAGNOSTICO
    relatorio_com_dominio_calculado.save(update_fields=["tipo"])

    from relatorios.services.pdf import renderizar_html_relatorio

    html = renderizar_html_relatorio(relatorio_com_dominio_calculado, minuta=True)

    assert "Do diagnóstico à" not in html
    assert "9 · Encerramento" in html


@pytest.mark.django_db
def test_pdf_diagnostico_plano_acao_inclui_secao_plano_de_acao(relatorio_com_dominio_calculado):
    from relatorios.services.pdf import renderizar_html_relatorio

    html = renderizar_html_relatorio(relatorio_com_dominio_calculado, minuta=True)

    assert "09 · O que fazer" in html
    assert "10 · Encerramento" in html


@pytest.mark.django_db
def test_gerar_e_salvar_planos_refinados_marca_planos_refinados_em(relatorio_com_dominio_calculado):
    resultado_ia = {
        "planos_refinados": [
            {
                "ghe": "Equipe Teste",
                "dominio": "D1",
                "medida": "Medida refinada.",
                "hierarquia_controle": "organizacao",
                "indicador": "Indicador.",
            }
        ]
    }
    fake_response = _FakeResponse([_FakeToolUseBlock("refinar_plano_de_acao", resultado_ia)])
    client = _FakeAnthropicClient(fake_response)

    assert relatorio_com_dominio_calculado.planos_refinados_em is None
    gerar_e_salvar_planos_refinados(relatorio_com_dominio_calculado.pk, client=client)

    relatorio_com_dominio_calculado.refresh_from_db()
    assert relatorio_com_dominio_calculado.planos_refinados_em is not None


@pytest.mark.django_db
def test_gerar_e_salvar_planos_refinados_incompleto_levanta_erro(relatorio_com_dominio_calculado):
    """Mesmo achado do parecer técnico: uma lista incompleta não pode ser aceita
    silenciosamente — precisa cobrir todo domínio com PlanoDeAcao já existente."""
    fake_response = _FakeResponse([_FakeToolUseBlock("refinar_plano_de_acao", {"planos_refinados": []})])
    client = _FakeAnthropicClient(fake_response)

    with pytest.raises(RuntimeError, match="incompleto"):
        gerar_e_salvar_planos_refinados(relatorio_com_dominio_calculado.pk, client=client)
