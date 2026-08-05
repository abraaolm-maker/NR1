from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from avaliacoes.models import Empresa, Unidade
from avaliacoes.services.aplicacao_status import encerrar_coleta
from avaliacoes.services.calculo_risco import calcular_dominio
from relatorios.models import PerfilProfissional, Relatorio, StatusRelatorio, TipoRelatorio


@pytest.fixture
def gestor(db):
    return get_user_model().objects.create_user(
        username="gestor_relatorio", password="x", is_staff=True, is_superuser=True
    )


@pytest.mark.django_db
def test_criar_relatorio_scoped_a_unidade(client, gestor, aplicacao_copsoq, responder_dominio):
    client.force_login(gestor)
    dominio = responder_dominio(
        aplicacao_copsoq, "D1", {"D1.1": 3, "D1.2": 3, "D1.3": 3, "D1.4": 3, "D1.5": 3}, 3
    )
    calcular_dominio(aplicacao_copsoq, dominio)
    unidade = aplicacao_copsoq.ghe.unidade

    resp = client.post(
        reverse("painel_relatorios:relatorio_create", args=[unidade.pk]),
        {
            "tipo": TipoRelatorio.DIAGNOSTICO_PLANO_ACAO,
            "criterio_versao": aplicacao_copsoq.criterio_versao_id,
            "aplicacoes": [aplicacao_copsoq.pk],
            "periodo_inicio": date.today().isoformat(),
            "periodo_fim": date.today().isoformat(),
        },
    )

    assert resp.status_code == 302
    relatorio = Relatorio.objects.get(unidade=unidade)
    assert list(relatorio.aplicacoes.all()) == [aplicacao_copsoq]
    assert relatorio.status == StatusRelatorio.AGUARDANDO_REVISAO


@pytest.mark.django_db
def test_relatorio_create_sem_aplicacoes_mostra_mensagem_amigavel(client, gestor):
    """Achado do teste de UX (2026-07-17): sem essa página, o campo "Aplicações" nascia
    obrigatório mas sem nenhuma opção pra marcar — beco sem saída com erro mal posicionado."""
    client.force_login(gestor)
    unidade = Unidade.objects.create(
        empresa=Empresa.objects.create(nome="Empresa Vazia", cnpj="00.000.000/0009-00"), nome="Unidade Vazia"
    )

    resp = client.get(reverse("painel_relatorios:relatorio_create", args=[unidade.pk]))

    assert resp.status_code == 200
    assert "ainda não é possível criar um relatório" in resp.content.decode().lower()
    assert b"criterio_versao" not in resp.content  # não é o formulário de fato, é a página de aviso


@pytest.mark.django_db
def test_relatorio_list_mostra_aplicacao_pronta_para_relatorio(client, gestor, aplicacao_copsoq):
    encerrar_coleta(aplicacao_copsoq.pk)
    client.force_login(gestor)

    resp = client.get(reverse("painel_relatorios:relatorio_list"))

    assert resp.status_code == 200
    assert aplicacao_copsoq.ghe.nome.encode() in resp.content
    assert reverse("painel_relatorios:relatorio_create", args=[aplicacao_copsoq.ghe.unidade.pk]).encode() in resp.content


@pytest.mark.django_db
def test_relatorio_list_nao_mostra_aplicacao_ja_incluida_em_relatorio(client, gestor, aplicacao_copsoq):
    encerrar_coleta(aplicacao_copsoq.pk)
    relatorio = Relatorio.objects.create(
        unidade=aplicacao_copsoq.ghe.unidade,
        criterio_versao=aplicacao_copsoq.criterio_versao,
        periodo_inicio=date.today(),
        periodo_fim=date.today(),
    )
    relatorio.aplicacoes.add(aplicacao_copsoq)
    client.force_login(gestor)

    resp = client.get(reverse("painel_relatorios:relatorio_list"))

    assert resp.status_code == 200
    assert b"Prontas para relat\xc3\xb3rio (0)" in resp.content


@pytest.mark.django_db
def test_painel_home_mostra_aplicacoes_prontas_para_relatorio(client, gestor, aplicacao_copsoq):
    encerrar_coleta(aplicacao_copsoq.pk)
    client.force_login(gestor)

    resp = client.get(reverse("painel_relatorios:home"))

    assert resp.status_code == 200
    assert aplicacao_copsoq.ghe.nome.encode() in resp.content


@pytest.mark.django_db
def test_aplicacao_detail_mostra_banner_pronta_para_relatorio_apos_encerrar(client, gestor, aplicacao_copsoq):
    encerrar_coleta(aplicacao_copsoq.pk)
    client.force_login(gestor)

    resp = client.get(reverse("painel_avaliacoes:aplicacao_detail", args=[aplicacao_copsoq.pk]))

    assert resp.status_code == 200
    assert "pronta para relatório" in resp.content.decode().lower()
    assert reverse("painel_relatorios:relatorio_create", args=[aplicacao_copsoq.ghe.unidade.pk]).encode() in resp.content


@pytest.mark.django_db
def test_assinar_sem_perfil_mostra_mensagem_de_erro(client, gestor, aplicacao_copsoq):
    client.force_login(gestor)
    relatorio = Relatorio.objects.create(
        unidade=aplicacao_copsoq.ghe.unidade,
        criterio_versao=aplicacao_copsoq.criterio_versao,
        periodo_inicio=date.today(),
        periodo_fim=date.today(),
    )

    resp = client.post(reverse("painel_relatorios:relatorio_assinar", args=[relatorio.pk]), follow=True)

    relatorio.refresh_from_db()
    assert relatorio.status == StatusRelatorio.AGUARDANDO_REVISAO
    mensagens = [str(m) for m in resp.context["messages"]]
    assert any("perfil profissional" in m.lower() or "perfilprofissional" in m.lower() for m in mensagens)


@pytest.mark.django_db
def test_assinar_sem_parecer_mostra_mensagem_de_erro(client, gestor, aplicacao_copsoq):
    PerfilProfissional.objects.create(
        user=gestor, titulo_profissional="Psicólogo do Trabalho", conselho="CRP", numero_registro="06/1"
    )
    client.force_login(gestor)
    relatorio = Relatorio.objects.create(
        unidade=aplicacao_copsoq.ghe.unidade,
        criterio_versao=aplicacao_copsoq.criterio_versao,
        periodo_inicio=date.today(),
        periodo_fim=date.today(),
    )

    resp = client.post(reverse("painel_relatorios:relatorio_assinar", args=[relatorio.pk]), follow=True)

    relatorio.refresh_from_db()
    assert relatorio.status == StatusRelatorio.AGUARDANDO_REVISAO
    mensagens = [str(m) for m in resp.context["messages"]]
    assert any("parecer" in m.lower() for m in mensagens)


@pytest.mark.django_db
def test_assinar_com_perfil_muda_status_e_gera_pdf(client, gestor, aplicacao_copsoq, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    PerfilProfissional.objects.create(
        user=gestor, titulo_profissional="Psicólogo do Trabalho", conselho="CRP", numero_registro="06/1"
    )
    client.force_login(gestor)
    relatorio = Relatorio.objects.create(
        unidade=aplicacao_copsoq.ghe.unidade,
        criterio_versao=aplicacao_copsoq.criterio_versao,
        periodo_inicio=date.today(),
        periodo_fim=date.today(),
    )
    relatorio.aplicacoes.add(aplicacao_copsoq)
    relatorio.tipo = TipoRelatorio.DIAGNOSTICO
    relatorio.parecer_ia = {
        "sintese_executiva": "Panorama de teste.",
        "pareceres_por_dominio": [],
        "riscos_prioritarios": [],
        "recomendacoes": [],
        "aviso_minuta": "Minuta sujeita a revisão.",
    }
    relatorio.save(update_fields=["tipo", "parecer_ia"])

    client.post(reverse("painel_relatorios:relatorio_assinar", args=[relatorio.pk]))

    relatorio.refresh_from_db()
    assert relatorio.status == StatusRelatorio.ASSINADO
    assert relatorio.assinado_por == gestor
    assert "final" in relatorio.pdf_path.name


@pytest.mark.django_db
def test_relatorios_empresa_mostra_so_relatorios_assinados_para_download(aplicacao_copsoq, tmp_path, settings):
    """Achado no diagnóstico de UX de 2026-07-28: a empresa cliente não tinha acesso a
    nenhum resultado da própria coleta (era um stub "em execução"). Agora a empresa
    enxerga o status de todos os relatórios, mas só baixa o PDF quando assinado."""
    settings.MEDIA_ROOT = str(tmp_path)
    from django.test import Client

    empresa = aplicacao_copsoq.ghe.unidade.empresa
    gestor_empresa = get_user_model().objects.create_user(username="gestor_empresa", password="x", is_staff=True)
    empresa.gestor = gestor_empresa
    empresa.save(update_fields=["gestor"])

    relatorio = Relatorio.objects.create(
        unidade=aplicacao_copsoq.ghe.unidade,
        criterio_versao=aplicacao_copsoq.criterio_versao,
        periodo_inicio=date.today(),
        periodo_fim=date.today(),
    )
    relatorio.aplicacoes.add(aplicacao_copsoq)

    client = Client()
    client.force_login(gestor_empresa)
    resp = client.get(reverse("painel_avaliacoes:relatorios_empresa"))

    assert resp.status_code == 200
    assert aplicacao_copsoq.ghe.unidade.nome.encode() in resp.content
    assert b"Ainda n\xc3\xa3o dispon\xc3\xadvel" in resp.content  # ainda não assinado -> sem link de download


@pytest.mark.django_db
def test_analise_ia_empresa_so_mostra_relatorios_assinados(aplicacao_copsoq, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    from django.test import Client

    empresa = aplicacao_copsoq.ghe.unidade.empresa
    gestor_empresa = get_user_model().objects.create_user(username="gestor_empresa2", password="x", is_staff=True)
    empresa.gestor = gestor_empresa
    empresa.save(update_fields=["gestor"])

    relatorio = Relatorio.objects.create(
        unidade=aplicacao_copsoq.ghe.unidade,
        criterio_versao=aplicacao_copsoq.criterio_versao,
        periodo_inicio=date.today(),
        periodo_fim=date.today(),
    )
    relatorio.aplicacoes.add(aplicacao_copsoq)
    relatorio.tipo = TipoRelatorio.DIAGNOSTICO
    relatorio.parecer_ia = {
        "sintese_executiva": "Panorama de teste da empresa.",
        "pareceres_por_dominio": [],
        "riscos_prioritarios": [],
        "recomendacoes": [],
        "aviso_minuta": "Minuta.",
    }
    relatorio.save(update_fields=["tipo", "parecer_ia"])

    client = Client()
    client.force_login(gestor_empresa)

    # ainda não assinado -> não aparece
    resp = client.get(reverse("painel_avaliacoes:analise_ia_empresa"))
    assert b"Panorama de teste da empresa." not in resp.content

    # depois de assinado -> aparece
    PerfilProfissional.objects.create(
        user=gestor_empresa, titulo_profissional="Psicólogo", conselho="CRP", numero_registro="06/1"
    )
    from relatorios.services.pdf import assinar_relatorio

    assinar_relatorio(relatorio.pk, gestor_empresa.pk)

    resp = client.get(reverse("painel_avaliacoes:analise_ia_empresa"))
    assert b"Panorama de teste da empresa." in resp.content
