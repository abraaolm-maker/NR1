from datetime import date

import pytest
from django.contrib.auth import get_user_model

from avaliacoes.services.calculo_risco import calcular_dominio
from relatorios.models import PerfilProfissional, Relatorio, StatusRelatorio
from relatorios.services.analise_ia import MODEL, gerar_e_salvar_parecer, gerar_parecer, montar_payload_relatorio
from relatorios.services.pdf import _contexto_relatorio, assinar_relatorio, gerar_pdf_relatorio


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
    # severidade 3 (Elevado) x probabilidade 1 (0 evidências convergentes) -> Moderado
    assert dominios["D1"]["banda"] == "Moderado"
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
    fake_response = _FakeResponse([_FakeToolUseBlock("gerar_parecer_tecnico", PARECER_DE_TESTE)])
    client = _FakeAnthropicClient(fake_response)

    relatorio = gerar_e_salvar_parecer(relatorio_com_dominio_calculado.pk, client=client)

    assert relatorio.parecer_ia == PARECER_DE_TESTE
    assert relatorio.status == StatusRelatorio.AGUARDANDO_REVISAO


@pytest.mark.django_db
def test_gerar_pdf_relatorio_minuta_tem_marca_dagua_e_nao_muda_status(
    relatorio_com_dominio_calculado, media_root_tmp
):
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
    relatorio_com_dominio_calculado.save(update_fields=["parecer_ia"])

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
