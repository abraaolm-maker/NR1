import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from avaliacoes.models import GHE, Aplicacao, Empresa, Respondente, StatusAplicacao, Unidade
from instrumentos.models import Instrumento


@pytest.fixture
def gestor(db):
    return get_user_model().objects.create_user(
        username="gestor_teste", password="x", is_staff=True, is_superuser=True
    )


@pytest.mark.django_db
def test_painel_exige_login(client):
    resp = client.get(reverse("painel_avaliacoes:empresa_list"))
    assert resp.status_code == 302
    assert reverse("painel_login") in resp.url


@pytest.mark.django_db
def test_fluxo_completo_criacao_empresa_unidade_ghe_aplicacao(client, gestor, criterio_v1):
    client.force_login(gestor)

    resp = client.post(
        reverse("painel_avaliacoes:empresa_create"), {"nome": "Empresa X", "cnpj": "00.000.000/0001-00"}
    )
    empresa = Empresa.objects.get(nome="Empresa X")
    assert resp.status_code == 302

    resp = client.post(
        reverse("painel_avaliacoes:unidade_create", args=[empresa.pk]),
        {"nome": "Unidade Y", "cnpj": "", "endereco": ""},
    )
    unidade = Unidade.objects.get(nome="Unidade Y")
    assert unidade.empresa_id == empresa.pk

    resp = client.post(
        reverse("painel_avaliacoes:ghe_create", args=[unidade.pk]),
        {"nome": "GHE Z", "setor": "", "funcoes": []},
    )
    ghe = GHE.objects.get(nome="GHE Z")
    assert ghe.unidade_id == unidade.pk

    instrumento = Instrumento.objects.get(codigo="COPSOQ_RR_REVESTIR")
    resp = client.post(
        reverse("painel_avaliacoes:aplicacao_create", args=[ghe.pk]),
        {
            "instrumento": instrumento.pk,
            "criterio_versao": criterio_v1.pk,
            "tipo": "anonima",
            "responsavel_aplicador": gestor.pk,
            "justificativa_instrumento": "",
            "data_aplicacao": "",
        },
    )
    aplicacao = Aplicacao.objects.get(ghe=ghe)
    assert resp.status_code == 302
    assert aplicacao.criterio_versao_id == criterio_v1.pk


@pytest.mark.django_db
def test_aplicacao_detail_mostra_link_unico(client, gestor, aplicacao_copsoq):
    client.force_login(gestor)

    resp = client.get(reverse("painel_avaliacoes:aplicacao_detail", args=[aplicacao_copsoq.pk]))

    assert resp.status_code == 200
    assert f"/responder/{aplicacao_copsoq.token}/".encode() in resp.content


@pytest.mark.django_db
def test_alertas_agregados_lista_alertas_d9_por_ghe(client, gestor, aplicacao_copsoq):
    from django.utils import timezone

    from avaliacoes.models import Resposta
    from avaliacoes.services.calculo_risco import calcular_dominio
    from instrumentos.models import Dominio

    dominio_d9 = Dominio.objects.get(instrumento=aplicacao_copsoq.instrumento, codigo="D9")
    respondente = Respondente.objects.create(
        aplicacao=aplicacao_copsoq, alias_anonimo="Respondente 0", concluido_em=timezone.now()
    )
    valores = {"D9.1": 4, "D9.2": 1, "D9.3": 1, "D9.4": 1}
    for item in dominio_d9.itens.all():
        Resposta.objects.create(respondente=respondente, item=item, valor_bruto=valores[item.item_id])
    calcular_dominio(aplicacao_copsoq, dominio_d9)

    client.force_login(gestor)
    resp = client.get(reverse("painel_avaliacoes:alertas_agregados", args=[aplicacao_copsoq.ghe.unidade.pk]))

    assert resp.status_code == 200
    assert aplicacao_copsoq.ghe.nome.encode() in resp.content
    assert b"1 alerta" in resp.content


@pytest.mark.django_db
def test_catalogo_acoes_list_mostra_acoes_e_permite_editar(client, gestor, aplicacao_copsoq):
    from avaliacoes.models import CatalogoAcao

    client.force_login(gestor)

    resp = client.get(reverse("painel_avaliacoes:catalogo_acoes_list"))
    assert resp.status_code == 200
    assert b"Redimensionar capacidade" in resp.content

    acao = CatalogoAcao.objects.get(dominio__codigo="D1", nivel="Elevado")
    resp = client.post(
        reverse("painel_avaliacoes:catalogo_acoes_update", args=[acao.pk]),
        {
            "acao_sugerida": "Texto personalizado pela empresa.",
            "hierarquia": acao.hierarquia,
            "indicador": acao.indicador,
        },
        follow=True,
    )
    assert resp.status_code == 200
    acao.refresh_from_db()
    assert acao.acao_sugerida == "Texto personalizado pela empresa."


@pytest.mark.django_db
def test_checklist_triangulacao_get_sem_coleta_mostra_botao_abrir(client, gestor, aplicacao_copsoq):
    client.force_login(gestor)
    resp = client.get(reverse("painel_avaliacoes:checklist_triangulacao", args=[aplicacao_copsoq.pk]))

    assert resp.status_code == 200
    assert "nenhuma coleta aberta" in resp.content.decode().lower()
    assert reverse("painel_avaliacoes:checklist_abrir_coleta", args=[aplicacao_copsoq.pk]).encode() in resp.content


@pytest.mark.django_db
def test_checklist_abrir_coleta_cria_coleta_e_mostra_link(client, gestor, aplicacao_copsoq):
    from avaliacoes.models import ColetaChecklistTriangulacao

    client.force_login(gestor)
    resp = client.post(
        reverse("painel_avaliacoes:checklist_abrir_coleta", args=[aplicacao_copsoq.pk]), follow=True
    )

    assert resp.status_code == 200
    coleta = ColetaChecklistTriangulacao.objects.get(aplicacao=aplicacao_copsoq)
    assert coleta.status == "aberta"
    assert coleta.criado_por == gestor
    assert str(coleta.token).encode() in resp.content


@pytest.mark.django_db
def test_checklist_encerrar_coleta_muda_status(client, gestor, aplicacao_copsoq):
    from avaliacoes.models import ColetaChecklistTriangulacao

    client.force_login(gestor)
    client.post(reverse("painel_avaliacoes:checklist_abrir_coleta", args=[aplicacao_copsoq.pk]))
    coleta = ColetaChecklistTriangulacao.objects.get(aplicacao=aplicacao_copsoq)

    resp = client.post(
        reverse("painel_avaliacoes:checklist_encerrar_coleta", args=[aplicacao_copsoq.pk]), follow=True
    )

    assert resp.status_code == 200
    coleta.refresh_from_db()
    assert coleta.status == "encerrada"
    assert coleta.encerrada_em is not None


@pytest.mark.django_db
def test_semaforo_riscos_mostra_percentuais_e_leitura_resumida(
    client, gestor, aplicacao_copsoq, responder_dominio
):
    from avaliacoes.services.calculo_risco import calcular_dominio

    dominio = responder_dominio(
        aplicacao_copsoq, "D1", {"D1.1": 5, "D1.2": 5, "D1.3": 5, "D1.4": 5, "D1.5": 5}, n_respondentes=5
    )
    calcular_dominio(aplicacao_copsoq, dominio)

    client.force_login(gestor)
    resp = client.get(reverse("painel_avaliacoes:semaforo_riscos", args=[aplicacao_copsoq.ghe.unidade.pk]))

    assert resp.status_code == 200
    assert b"100%" in resp.content  # 5 de 5 respondentes na faixa de risco (valor bruto 5 -> escore 100)
    assert b"P1" in resp.content

    # filtro por GHE deve continuar funcionando
    resp_filtrado = client.get(
        reverse("painel_avaliacoes:semaforo_riscos", args=[aplicacao_copsoq.ghe.unidade.pk]),
        {"ghe": aplicacao_copsoq.ghe.pk},
    )
    assert resp_filtrado.status_code == 200
    assert aplicacao_copsoq.ghe.nome.encode() in resp_filtrado.content


@pytest.mark.django_db
def test_plano_de_acao_update_edita_todos_os_campos(client, gestor, aplicacao_copsoq, responder_dominio):
    from datetime import date

    from avaliacoes.services.calculo_risco import calcular_dominio

    dominio = responder_dominio(
        aplicacao_copsoq, "D1", {"D1.1": 4, "D1.2": 4, "D1.3": 5, "D1.4": 3, "D1.5": 4}, n_respondentes=5
    )
    escore_dominio = calcular_dominio(aplicacao_copsoq, dominio)
    plano = escore_dominio.classificacao_risco.planos_de_acao.get()

    client.force_login(gestor)
    resp = client.post(
        reverse("painel_avaliacoes:plano_de_acao_update", args=[plano.pk]),
        {
            "codigo": "A01",
            "medida": "Medida revisada pelo profissional.",
            "hierarquia": "organizacao",
            "evidencia_diagnostico": plano.evidencia_diagnostico,
            "indicador": "Novo indicador.",
            "meta": "Reduzir em 20% em 90 dias.",
            "responsavel": "Gerência Industrial + SESMT",
            "prazo": "2026-09-30",
            "status": "em_andamento",
            "evidencia_execucao": "Ata de reunião anexada.",
            "verificacao_eficacia": "Reaplicação do questionário em 6 meses.",
            "data_revisao": date.today().isoformat(),
            "observacoes": "Observação de teste.",
        },
        follow=True,
    )
    assert resp.status_code == 200
    plano.refresh_from_db()
    assert plano.medida == "Medida revisada pelo profissional."
    assert plano.responsavel == "Gerência Industrial + SESMT"
    assert plano.status == "em_andamento"
    assert plano.meta == "Reduzir em 20% em 90 dias."


@pytest.mark.django_db
def test_diagnostico_ghe_mostra_prioridade_e_nota_tecnica(client, gestor, aplicacao_copsoq, responder_dominio):
    from avaliacoes.services.calculo_risco import calcular_dominio

    dominio = responder_dominio(
        aplicacao_copsoq, "D1", {"D1.1": 5, "D1.2": 5, "D1.3": 5, "D1.4": 5, "D1.5": 5}, n_respondentes=5
    )
    calcular_dominio(aplicacao_copsoq, dominio)

    client.force_login(gestor)
    resp = client.get(reverse("painel_avaliacoes:diagnostico_ghe", args=[aplicacao_copsoq.pk]))

    assert resp.status_code == 200
    assert b"P1" in resp.content
    assert "triangular e controlar na fonte".encode() in resp.content


@pytest.mark.django_db
def test_diagnostico_ghe_mostra_aviso_quando_todos_suprimidos(client, gestor, aplicacao_copsoq, responder_dominio):
    """Achado no diagnóstico de UX de 2026-07-28: o gestor completava o fluxo inteiro
    e via 9 linhas idênticas de "SUPRIMIDO" sem nenhuma explicação central do porquê."""
    from avaliacoes.services.calculo_risco import calcular_dominio

    dominio = responder_dominio(
        aplicacao_copsoq, "D1", {"D1.1": 3, "D1.2": 3, "D1.3": 3, "D1.4": 3, "D1.5": 3}, n_respondentes=1
    )
    calcular_dominio(aplicacao_copsoq, dominio)

    client.force_login(gestor)
    resp = client.get(reverse("painel_avaliacoes:diagnostico_ghe", args=[aplicacao_copsoq.pk]))

    assert resp.status_code == 200
    assert "todos os domínios estão suprimidos".encode() in resp.content.lower()


@pytest.mark.django_db
def test_aplicacao_detail_mostra_aviso_quando_todos_suprimidos(client, gestor, aplicacao_copsoq, responder_dominio):
    from avaliacoes.services.calculo_risco import calcular_dominio

    dominio = responder_dominio(
        aplicacao_copsoq, "D1", {"D1.1": 3, "D1.2": 3, "D1.3": 3, "D1.4": 3, "D1.5": 3}, n_respondentes=1
    )
    calcular_dominio(aplicacao_copsoq, dominio)

    client.force_login(gestor)
    resp = client.get(reverse("painel_avaliacoes:aplicacao_detail", args=[aplicacao_copsoq.pk]))

    assert resp.status_code == 200
    assert "resultados suprimidos por confidencialidade".encode() in resp.content.lower()


@pytest.mark.django_db
def test_aplicacao_detail_avisa_antes_de_encerrar_com_n_baixo(client, gestor, aplicacao_copsoq, responder_dominio):
    """Achado no diagnóstico de UX de 2026-07-28: nada avisava, antes de encerrar a
    coleta, que o N era insuficiente e o resultado sairia todo suprimido."""
    dominio = responder_dominio(
        aplicacao_copsoq, "D1", {"D1.1": 3, "D1.2": 3, "D1.3": 3, "D1.4": 3, "D1.5": 3}, n_respondentes=1
    )

    client.force_login(gestor)
    resp = client.get(reverse("painel_avaliacoes:aplicacao_detail", args=[aplicacao_copsoq.pk]))

    assert resp.status_code == 200
    assert "mínimo para exibir resultados".encode() in resp.content.lower()


@pytest.mark.django_db
def test_indicadores_indiretos_get_e_post(client, gestor, aplicacao_copsoq):
    """Achado no diagnóstico de UX de 2026-07-28: IndicadorIndireto só existia no
    Django Admin — ninguém usando o painel sabia que precisava cadastrar evidências
    complementares pra a probabilidade de risco sair de 1."""
    from datetime import date

    from avaliacoes.models import IndicadorIndireto

    client.force_login(gestor)
    ghe = aplicacao_copsoq.ghe

    resp = client.get(reverse("painel_avaliacoes:indicadores_indiretos", args=[ghe.pk]))
    assert resp.status_code == 200

    resp = client.post(
        reverse("painel_avaliacoes:indicadores_indiretos", args=[ghe.pk]),
        {
            "tipo": "absenteismo",
            "periodo_referencia": date.today().isoformat(),
            "descricao": "Absenteísmo acima da média no trimestre.",
            "convergente": "on",
        },
        follow=True,
    )
    assert resp.status_code == 200
    assert IndicadorIndireto.objects.filter(ghe=ghe).count() == 1


@pytest.mark.django_db
def test_pontuacao_anonima_mostra_escore_por_respondente_e_indice_geral(
    client, gestor, aplicacao_copsoq, responder_dominio
):
    from avaliacoes.services.calculo_risco import calcular_dominio

    dominio = responder_dominio(
        aplicacao_copsoq, "D1", {"D1.1": 4, "D1.2": 4, "D1.3": 5, "D1.4": 3, "D1.5": 4}, n_respondentes=5
    )
    calcular_dominio(aplicacao_copsoq, dominio)

    client.force_login(gestor)
    resp = client.get(reverse("painel_avaliacoes:pontuacao_anonima", args=[aplicacao_copsoq.pk]))

    assert resp.status_code == 200
    assert b"75,0" in resp.content  # escore do domínio D1 e índice geral (só D1 respondido; pt-br usa vírgula)
    assert b"Respondente 0" in resp.content


@pytest.mark.django_db
def test_encerrar_coleta_muda_status_e_bloqueia_reencerrar(client, gestor, aplicacao_copsoq):
    client.force_login(gestor)

    resp = client.post(
        reverse("painel_avaliacoes:aplicacao_encerrar_coleta", args=[aplicacao_copsoq.pk]), follow=True
    )
    aplicacao_copsoq.refresh_from_db()

    assert resp.status_code == 200
    assert aplicacao_copsoq.status == StatusAplicacao.CONCLUIDA
    assert aplicacao_copsoq.concluida_em is not None

    resp = client.post(
        reverse("painel_avaliacoes:aplicacao_encerrar_coleta", args=[aplicacao_copsoq.pk]), follow=True
    )
    mensagens = [str(m) for m in resp.context["messages"]]
    assert any("não pode ser encerrada" in m.lower() for m in mensagens)


@pytest.mark.django_db
def test_empresa_create_exige_admin(client):
    """Só quem é `is_superuser` (equipe do SaaS) faz onboarding de empresa nova —
    um gestor de empresa comum recebe 403 (CLAUDE.md Seção 6.8)."""
    gestor_empresa = get_user_model().objects.create_user(
        username="gestor_de_uma_empresa", password="x", is_staff=True
    )
    client.force_login(gestor_empresa)

    resp = client.get(reverse("painel_avaliacoes:empresa_create"))

    assert resp.status_code == 403


@pytest.mark.django_db
def test_gestor_de_empresa_so_ve_a_propria_empresa(client):
    empresa_a = Empresa.objects.create(nome="Empresa A", cnpj="00.000.000/0001-00")
    empresa_b = Empresa.objects.create(nome="Empresa B", cnpj="00.000.000/0002-00")
    gestor_a = get_user_model().objects.create_user(username="gestor_a", password="x", is_staff=True)
    empresa_a.gestor = gestor_a
    empresa_a.save(update_fields=["gestor"])

    client.force_login(gestor_a)

    resp = client.get(reverse("painel_avaliacoes:empresa_detail", args=[empresa_a.pk]))
    assert resp.status_code == 200

    resp = client.get(reverse("painel_avaliacoes:empresa_detail", args=[empresa_b.pk]))
    assert resp.status_code == 404

    # nem a lista global de empresas (admin) nem a criação de outra empresa são
    # alcançáveis por um gestor de empresa comum
    assert client.get(reverse("painel_avaliacoes:empresa_list")).status_code == 403


@pytest.mark.django_db
def test_admin_cria_acesso_de_gestor(client, gestor):
    empresa = Empresa.objects.create(nome="Empresa Nova", cnpj="00.000.000/0003-00")
    client.force_login(gestor)

    resp = client.post(
        reverse("painel_avaliacoes:empresa_criar_gestor", args=[empresa.pk]),
        {"username": "novo_gestor", "password": "senha-forte-123"},
    )

    empresa.refresh_from_db()
    assert resp.status_code == 302
    assert empresa.gestor is not None
    assert empresa.gestor.username == "novo_gestor"
    assert empresa.gestor.check_password("senha-forte-123")
    assert empresa.gestor.is_staff is True
    assert empresa.gestor.is_superuser is False
