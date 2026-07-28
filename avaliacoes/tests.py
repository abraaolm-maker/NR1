from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from avaliacoes.models import EscoreRespondente, IndicadorIndireto, Respondente, Resposta, TipoIndicadorIndireto
from avaliacoes.services.calculo_risco import calcular_dominio, contar_alertas_d9, diagnostico_ghe
from avaliacoes.services.semaforo import calcular_semaforo, leitura_resumida
from instrumentos.models import Dominio


@pytest.mark.django_db
def test_calcula_dominio_risco_puro_elevado_gera_plano_de_acao(aplicacao_copsoq, responder_dominio):
    valores = {"D1.1": 4, "D1.2": 4, "D1.3": 5, "D1.4": 3, "D1.5": 4}  # média bruta 4.0 -> 75.0 na escala 0-100 -> Elevado
    dominio = responder_dominio(aplicacao_copsoq, "D1", valores, n_respondentes=5)
    IndicadorIndireto.objects.create(
        ghe=aplicacao_copsoq.ghe,
        tipo=TipoIndicadorIndireto.ABSENTEISMO,
        periodo_referencia=timezone.now().date(),
        descricao="Absenteísmo do GHE acima da média histórica no trimestre.",
        dominio_relacionado=dominio,
    )

    escore_dominio = calcular_dominio(aplicacao_copsoq, dominio)

    assert escore_dominio.escore == Decimal("75.0")
    assert escore_dominio.classificacao == "Elevado"
    assert escore_dominio.severidade == 3
    assert escore_dominio.n_respondentes == 5
    assert escore_dominio.suprimido_por_confidencialidade is False

    classificacao_risco = escore_dominio.classificacao_risco
    assert classificacao_risco.evidencias_convergentes == 1  # 1 IndicadorIndireto convergente
    assert classificacao_risco.probabilidade == 2  # 1 evidência complementar
    assert classificacao_risco.banda == "Alto"
    assert classificacao_risco.prazo_dias_plano_de_acao == 30

    planos = list(classificacao_risco.planos_de_acao.all())
    assert len(planos) == 1
    assert planos[0].prazo == timezone.now().date() + timedelta(days=30)

    # recalcular não deve duplicar o plano de ação nem o escore
    calcular_dominio(aplicacao_copsoq, dominio)
    assert classificacao_risco.planos_de_acao.count() == 1


@pytest.mark.django_db
def test_calcula_dominio_d9_evento_grave_forca_critico(aplicacao_copsoq, responder_dominio):
    valores = {"D9.1": 5, "D9.2": 5, "D9.3": 1, "D9.4": 1}
    dominio = responder_dominio(aplicacao_copsoq, "D9", valores, n_respondentes=5)

    escore_dominio = calcular_dominio(aplicacao_copsoq, dominio)

    assert escore_dominio.escore == Decimal("100.0")
    assert escore_dominio.classificacao == "Elevado"

    classificacao_risco = escore_dominio.classificacao_risco
    assert classificacao_risco.evento_grave_confirmado is True
    assert classificacao_risco.evidencias_convergentes == 0
    assert classificacao_risco.probabilidade == 3
    assert classificacao_risco.banda == "Crítico"
    assert classificacao_risco.prazo_dias_plano_de_acao == 15

    plano = classificacao_risco.planos_de_acao.get()
    assert plano.prazo == timezone.now().date() + timedelta(days=15)


@pytest.mark.django_db
def test_supressao_por_confidencialidade_nao_bloqueia_calculo(aplicacao_copsoq, responder_dominio):
    valores = {"D1.1": 4, "D1.2": 4, "D1.3": 5, "D1.4": 3, "D1.5": 4}
    dominio = responder_dominio(aplicacao_copsoq, "D1", valores, n_respondentes=2)

    escore_dominio = calcular_dominio(aplicacao_copsoq, dominio)

    assert escore_dominio.n_respondentes == 2
    assert escore_dominio.suprimido_por_confidencialidade is True
    # o cálculo em si continua acontecendo normalmente (CLAUDE.md Seção 3, princípio 3)...
    assert escore_dominio.classificacao == "Elevado"
    # ...mas nenhum artefato derivado pode vazar o resultado suprimido: mesmo com banda
    # não-Aceitável (Elevado/Moderado aqui), não deve gerar Plano de Ação.
    assert escore_dominio.classificacao_risco.planos_de_acao.count() == 0


@pytest.mark.django_db
def test_dominio_aceitavel_nao_gera_plano_de_acao(aplicacao_copsoq, responder_dominio):
    valores = {"D1.1": 1, "D1.2": 1, "D1.3": 1, "D1.4": 1, "D1.5": 1}  # média 1.0 -> Baixo
    dominio = responder_dominio(aplicacao_copsoq, "D1", valores, n_respondentes=3)

    escore_dominio = calcular_dominio(aplicacao_copsoq, dominio)

    assert escore_dominio.classificacao == "Baixo"
    classificacao_risco = escore_dominio.classificacao_risco
    assert classificacao_risco.banda == "Aceitável"
    assert classificacao_risco.planos_de_acao.count() == 0


@pytest.mark.django_db
def test_calcular_dominio_cria_escore_por_respondente(aplicacao_copsoq, responder_dominio):
    # todos os 5 respondentes têm os mesmos valores (fixture responder_dominio aplica o
    # mesmo valores_por_item pra todos) -> mesmo escore individual pra cada um
    valores = {"D1.1": 4, "D1.2": 4, "D1.3": 5, "D1.4": 3, "D1.5": 4}  # média bruta 4.0 -> 75.0
    dominio = responder_dominio(aplicacao_copsoq, "D1", valores, n_respondentes=5)

    calcular_dominio(aplicacao_copsoq, dominio)

    escores_respondente = EscoreRespondente.objects.filter(dominio=dominio)
    assert escores_respondente.count() == 5
    for escore in escores_respondente:
        assert escore.escore == Decimal("75.0")
        assert escore.classificacao == "Elevado"


@pytest.mark.django_db
def test_indice_geral_e_media_dos_dominios_ja_respondidos(aplicacao_copsoq):
    from instrumentos.models import Dominio

    from avaliacoes.models import Resposta

    respondente = Respondente.objects.create(aplicacao=aplicacao_copsoq, alias_anonimo="Respondente 0")

    dominio_d1 = Dominio.objects.get(instrumento=aplicacao_copsoq.instrumento, codigo="D1")
    for item in dominio_d1.itens.all():
        Resposta.objects.create(respondente=respondente, item=item, valor_bruto=5)  # RISCO -> 100.0
    calcular_dominio(aplicacao_copsoq, dominio_d1)

    respondente.refresh_from_db()
    assert respondente.indice_geral == Decimal("100.00")

    dominio_d3 = Dominio.objects.get(instrumento=aplicacao_copsoq.instrumento, codigo="D3")
    for item in dominio_d3.itens.all():
        Resposta.objects.create(respondente=respondente, item=item, valor_bruto=5)  # PROTETIVO -> 0.0
    calcular_dominio(aplicacao_copsoq, dominio_d3)

    respondente.refresh_from_db()
    # média de D1 (100.0) e D3 (0.0) -> 50.0 (D2, D4-D9 ainda não respondidos, não entram)
    assert respondente.indice_geral == Decimal("50.00")


@pytest.mark.django_db
def test_contar_alertas_d9_conta_respondentes_com_evento_grave(aplicacao_copsoq):
    from instrumentos.models import Dominio

    from avaliacoes.models import Resposta

    dominio_d9 = Dominio.objects.get(instrumento=aplicacao_copsoq.instrumento, codigo="D9")

    respondente_com_alerta = Respondente.objects.create(
        aplicacao=aplicacao_copsoq, alias_anonimo="Respondente 0", concluido_em=timezone.now()
    )
    valores_alerta = {"D9.1": 4, "D9.2": 1, "D9.3": 1, "D9.4": 1}  # D9.1 >= limiar (4) -> evento grave
    for item in dominio_d9.itens.all():
        Resposta.objects.create(respondente=respondente_com_alerta, item=item, valor_bruto=valores_alerta[item.item_id])

    respondente_sem_alerta = Respondente.objects.create(
        aplicacao=aplicacao_copsoq, alias_anonimo="Respondente 1", concluido_em=timezone.now()
    )
    valores_sem_alerta = {"D9.1": 2, "D9.2": 1, "D9.3": 1, "D9.4": 1}
    for item in dominio_d9.itens.all():
        Resposta.objects.create(respondente=respondente_sem_alerta, item=item, valor_bruto=valores_sem_alerta[item.item_id])

    resultado = contar_alertas_d9(aplicacao_copsoq)
    assert resultado == {"n_respondentes": 2, "alertas_d9": 1}

    # calcular_dominio() persiste o mesmo resultado em Aplicacao.alertas_d9
    calcular_dominio(aplicacao_copsoq, dominio_d9)
    aplicacao_copsoq.refresh_from_db()
    assert aplicacao_copsoq.alertas_d9 == 1


def _criar_respondentes_com_escores(aplicacao, dominio_codigo, valores_por_respondente):
    """valores_por_respondente: lista de dicts {item_id: valor_bruto}, um por respondente."""
    dominio = Dominio.objects.get(instrumento=aplicacao.instrumento, codigo=dominio_codigo)
    for i, valores in enumerate(valores_por_respondente):
        respondente = Respondente.objects.create(
            aplicacao=aplicacao, alias_anonimo=f"Respondente {i}", concluido_em=timezone.now()
        )
        for item in dominio.itens.all():
            Resposta.objects.create(respondente=respondente, item=item, valor_bruto=valores[item.item_id])
    return dominio


@pytest.mark.django_db
def test_diagnostico_ghe_prioridade_p1_maioria_elevada(aplicacao_copsoq):
    # 3 de 5 respondentes (60%) com D1 elevado (valor bruto 5 -> escore 100 >= 62.5)
    elevado = {"D1.1": 5, "D1.2": 5, "D1.3": 5, "D1.4": 5, "D1.5": 5}
    baixo = {"D1.1": 1, "D1.2": 1, "D1.3": 1, "D1.4": 1, "D1.5": 1}
    dominio = _criar_respondentes_com_escores(aplicacao_copsoq, "D1", [elevado, elevado, elevado, baixo, baixo])

    calcular_dominio(aplicacao_copsoq, dominio)
    linhas = diagnostico_ghe(aplicacao_copsoq)

    linha_d1 = next(l for l in linhas if l["dominio"].startswith("D1"))
    assert linha_d1["prioridade"] == "P1"
    assert linha_d1["classificacao"] != "SUPRIMIDO"
    assert "triangular e controlar na fonte" in linha_d1["nota_tecnica"]


@pytest.mark.django_db
def test_diagnostico_ghe_prioridade_p2_minoria_significativa(aplicacao_copsoq):
    # 1 de 5 respondentes (20%)... precisa >= 25% pra P2, então usar 2 de 6 (33%) -> ainda P2? 2/6=33%>=25%
    elevado = {"D1.1": 5, "D1.2": 5, "D1.3": 5, "D1.4": 5, "D1.5": 5}
    baixo = {"D1.1": 1, "D1.2": 1, "D1.3": 1, "D1.4": 1, "D1.5": 1}
    dominio = _criar_respondentes_com_escores(
        aplicacao_copsoq, "D1", [elevado, elevado, baixo, baixo, baixo, baixo]
    )

    calcular_dominio(aplicacao_copsoq, dominio)
    linhas = diagnostico_ghe(aplicacao_copsoq)

    linha_d1 = next(l for l in linhas if l["dominio"].startswith("D1"))
    assert linha_d1["prioridade"] == "P2"
    assert "investigar causas" in linha_d1["nota_tecnica"]


@pytest.mark.django_db
def test_diagnostico_ghe_prioridade_p3_poucos_elevados(aplicacao_copsoq):
    # 1 de 6 respondentes (16.7%) elevado -> abaixo de 25% -> P3
    elevado = {"D1.1": 5, "D1.2": 5, "D1.3": 5, "D1.4": 5, "D1.5": 5}
    baixo = {"D1.1": 1, "D1.2": 1, "D1.3": 1, "D1.4": 1, "D1.5": 1}
    dominio = _criar_respondentes_com_escores(
        aplicacao_copsoq, "D1", [elevado, baixo, baixo, baixo, baixo, baixo]
    )

    calcular_dominio(aplicacao_copsoq, dominio)
    linhas = diagnostico_ghe(aplicacao_copsoq)

    linha_d1 = next(l for l in linhas if l["dominio"].startswith("D1"))
    assert linha_d1["prioridade"] == "P3"
    assert "Manter controles" in linha_d1["nota_tecnica"]


@pytest.mark.django_db
def test_diagnostico_ghe_agrupar_quando_n_abaixo_do_minimo(aplicacao_copsoq):
    baixo = {"D1.1": 1, "D1.2": 1, "D1.3": 1, "D1.4": 1, "D1.5": 1}
    dominio = _criar_respondentes_com_escores(aplicacao_copsoq, "D1", [baixo, baixo, baixo])  # N=3 < 5

    calcular_dominio(aplicacao_copsoq, dominio)
    linhas = diagnostico_ghe(aplicacao_copsoq)

    linha_d1 = next(l for l in linhas if l["dominio"].startswith("D1"))
    assert linha_d1["prioridade"] == "AGRUPAR"
    assert linha_d1["classificacao"] == "SUPRIMIDO"
    assert linha_d1["escore"] is None
    assert linha_d1["percentual_elevados"] is None
    assert "N < 5" in linha_d1["nota_tecnica"]


@pytest.mark.django_db
def test_diagnostico_ghe_alerta_protegido_d9(aplicacao_copsoq):
    dominio = _criar_respondentes_com_escores(
        aplicacao_copsoq,
        "D9",
        [
            {"D9.1": 4, "D9.2": 1, "D9.3": 1, "D9.4": 1},
            {"D9.1": 1, "D9.2": 1, "D9.3": 1, "D9.4": 1},
            {"D9.1": 1, "D9.2": 1, "D9.3": 1, "D9.4": 1},
            {"D9.1": 1, "D9.2": 1, "D9.3": 1, "D9.4": 1},
            {"D9.1": 1, "D9.2": 1, "D9.3": 1, "D9.4": 1},
        ],
    )
    calcular_dominio(aplicacao_copsoq, dominio)
    linha_d9 = next(l for l in diagnostico_ghe(aplicacao_copsoq) if l["dominio"].startswith("D9"))
    assert "evento grave confirmado" in linha_d9["alerta_protegido"]

    dominio_d1 = Dominio.objects.get(instrumento=aplicacao_copsoq.instrumento, codigo="D1")
    linha_d1 = next(
        (l for l in diagnostico_ghe(aplicacao_copsoq) if l["dominio"].startswith("D1")), None
    )
    assert linha_d1 is None  # D1 não foi calculado ainda, então não aparece no diagnóstico


@pytest.mark.django_db
def test_diagnostico_ghe_sem_alerta_protegido_d9(aplicacao_copsoq):
    baixo = {"D9.1": 1, "D9.2": 1, "D9.3": 1, "D9.4": 1}
    dominio = _criar_respondentes_com_escores(aplicacao_copsoq, "D9", [baixo] * 5)
    calcular_dominio(aplicacao_copsoq, dominio)

    linha_d9 = next(l for l in diagnostico_ghe(aplicacao_copsoq) if l["dominio"].startswith("D9"))
    assert linha_d9["alerta_protegido"] == "SEM ALERTA AGREGADO"


@pytest.mark.django_db
def test_plano_de_acao_usa_medida_do_catalogo_quando_existe(aplicacao_copsoq, responder_dominio):
    from avaliacoes.models import CatalogoAcao

    valores = {"D1.1": 4, "D1.2": 4, "D1.3": 5, "D1.4": 3, "D1.5": 4}  # média 4.0 -> 75.0 -> Elevado
    dominio = responder_dominio(aplicacao_copsoq, "D1", valores, n_respondentes=5)

    escore_dominio = calcular_dominio(aplicacao_copsoq, dominio)
    plano = escore_dominio.classificacao_risco.planos_de_acao.get()

    catalogo = CatalogoAcao.objects.get(dominio=dominio, nivel="Elevado")
    assert plano.medida == catalogo.acao_sugerida
    assert plano.hierarquia == catalogo.hierarquia
    assert plano.indicador == catalogo.indicador


@pytest.mark.django_db
def test_plano_de_acao_usa_texto_generico_quando_nao_ha_catalogo(aplicacao_copsoq, responder_dominio):
    from avaliacoes.models import CatalogoAcao

    valores = {"D1.1": 4, "D1.2": 4, "D1.3": 5, "D1.4": 3, "D1.5": 4}
    dominio = responder_dominio(aplicacao_copsoq, "D1", valores, n_respondentes=5)
    CatalogoAcao.objects.filter(dominio=dominio, nivel="Elevado").delete()

    escore_dominio = calcular_dominio(aplicacao_copsoq, dominio)
    plano = escore_dominio.classificacao_risco.planos_de_acao.get()

    assert "Definir e executar medida corretiva" in plano.medida
    assert plano.hierarquia == ""


@pytest.mark.django_db
def test_plano_de_acao_gera_codigo_e_evidencia_diagnostico_automaticamente(
    aplicacao_copsoq, responder_dominio
):
    valores = {"D1.1": 4, "D1.2": 4, "D1.3": 5, "D1.4": 3, "D1.5": 4}
    dominio = responder_dominio(aplicacao_copsoq, "D1", valores, n_respondentes=5)

    escore_dominio = calcular_dominio(aplicacao_copsoq, dominio)
    plano = escore_dominio.classificacao_risco.planos_de_acao.get()

    assert plano.codigo == "A01"
    assert plano.status == "planejada"
    assert dominio.nome in plano.evidencia_diagnostico
    assert "Elevado" in plano.evidencia_diagnostico
    assert aplicacao_copsoq.ghe.nome in plano.evidencia_diagnostico
    assert plano.responsavel == ""


@pytest.mark.django_db
def test_calcular_semaforo_classifica_percentuais_por_faixa(aplicacao_copsoq):
    # valores brutos 1,3,4,5 -> escores 0, 50, 75, 100 (RISCO: (v-1)*25); 8 respondentes
    # (>= N mínimo de 5) pra faixa não ser suprimida
    valores = [
        {"D1.1": 1, "D1.2": 1, "D1.3": 1, "D1.4": 1, "D1.5": 1},  # 0 -> favorável
        {"D1.1": 1, "D1.2": 1, "D1.3": 1, "D1.4": 1, "D1.5": 1},  # 0 -> favorável
        {"D1.1": 3, "D1.2": 3, "D1.3": 3, "D1.4": 3, "D1.5": 3},  # 50 -> intermediário
        {"D1.1": 3, "D1.2": 3, "D1.3": 3, "D1.4": 3, "D1.5": 3},  # 50 -> intermediário
        {"D1.1": 4, "D1.2": 4, "D1.3": 4, "D1.4": 4, "D1.5": 4},  # 75 -> risco
        {"D1.1": 4, "D1.2": 4, "D1.3": 4, "D1.4": 4, "D1.5": 4},  # 75 -> risco
        {"D1.1": 5, "D1.2": 5, "D1.3": 5, "D1.4": 5, "D1.5": 5},  # 100 -> risco
        {"D1.1": 5, "D1.2": 5, "D1.3": 5, "D1.4": 5, "D1.5": 5},  # 100 -> risco
    ]
    dominio = _criar_respondentes_com_escores(aplicacao_copsoq, "D1", valores)
    calcular_dominio(aplicacao_copsoq, dominio)

    linhas = calcular_semaforo([aplicacao_copsoq])
    linha_d1 = next(l for l in linhas if l["dominio_codigo"] == "D1")

    assert linha_d1["suprimido"] is False
    assert linha_d1["n_respondentes"] == 8
    assert linha_d1["pct_favoravel"] == 0.25
    assert linha_d1["pct_intermediario"] == 0.25
    assert linha_d1["pct_risco"] == 0.5
    assert linha_d1["prioridade"] == "P1"
    assert linha_d1["media_risco"] == 56.25


@pytest.mark.django_db
def test_calcular_semaforo_suprime_agregado_com_n_abaixo_do_minimo(aplicacao_copsoq):
    """O N mínimo de confidencialidade vale também no agregado: com N total < mínimo,
    o Semáforo não pode exibir o que as outras telas suprimem (vazamento encontrado no
    diagnóstico de UX de 2026-07-28 — unidade com 1 respondente mostrava escore aberto)."""
    baixo = {"D1.1": 1, "D1.2": 1, "D1.3": 1, "D1.4": 1, "D1.5": 1}
    dominio = _criar_respondentes_com_escores(aplicacao_copsoq, "D1", [baixo, baixo, baixo])  # N=3 < 5
    calcular_dominio(aplicacao_copsoq, dominio)

    linhas = calcular_semaforo([aplicacao_copsoq])
    linha_d1 = next(l for l in linhas if l["dominio_codigo"] == "D1")

    assert linha_d1["suprimido"] is True
    assert linha_d1["n_respondentes"] == 3
    assert linha_d1["pct_risco"] is None
    assert linha_d1["media_risco"] is None
    assert linha_d1["prioridade"] is None

    # e a leitura resumida ignora linhas suprimidas
    resumo = leitura_resumida(linhas)
    assert resumo["maior_risco"] is None


@pytest.mark.django_db
def test_leitura_resumida_conta_prioridades_e_aponta_maior_risco():
    linhas = [
        {"dominio_codigo": "D1", "dominio_nome": "Exigências", "pct_risco": 0.7, "prioridade": "P1"},
        {"dominio_codigo": "D2", "dominio_nome": "Emocionais", "pct_risco": 0.3, "prioridade": "P2"},
        {"dominio_codigo": "D3", "dominio_nome": "Autonomia", "pct_risco": 0.1, "prioridade": "P3"},
    ]
    resumo = leitura_resumida(linhas)

    assert resumo["maior_risco"]["dominio_codigo"] == "D1"
    assert resumo["contagem_prioridade"] == {"P1": 1, "P2": 1, "P3": 1}


@pytest.mark.django_db
def test_checklist_nao_conforme_conta_como_evidencia_convergente(aplicacao_copsoq, responder_dominio):
    """Achado no diagnóstico de UX de 2026-07-28: o checklist de entrevista/observação
    (Prompt 09) existia mas não alimentava o cálculo — um item "Não conforme" deveria
    contar como evidência complementar (Seção 7.5), igual a um IndicadorIndireto."""
    from avaliacoes.models import (
        ColetaChecklistTriangulacao,
        ItemChecklistTriangulacao,
        RespondenteChecklistTriangulacao,
        RespostaChecklistTriangulacao,
    )

    valores = {"D1.1": 4, "D1.2": 4, "D1.3": 5, "D1.4": 3, "D1.5": 4}  # média 4.0 -> 75.0 -> Elevado
    dominio = responder_dominio(aplicacao_copsoq, "D1", valores, n_respondentes=5)

    # sem nenhuma evidência: probabilidade 1 -> banda Moderado (severidade 3 x prob 1)
    escore_dominio = calcular_dominio(aplicacao_copsoq, dominio)
    assert escore_dominio.classificacao_risco.probabilidade == 1
    assert escore_dominio.classificacao_risco.banda == "Moderado"

    coleta = ColetaChecklistTriangulacao.objects.create(aplicacao=aplicacao_copsoq)
    respondente = RespondenteChecklistTriangulacao.objects.create(coleta=coleta, nome="Gestor de Teste")
    item = ItemChecklistTriangulacao.objects.filter(tipo="observacao").first()
    RespostaChecklistTriangulacao.objects.create(
        respondente=respondente, item=item, conformidade="nao_conforme", evidencia="Observado in loco."
    )

    escore_dominio = calcular_dominio(aplicacao_copsoq, dominio)
    assert escore_dominio.classificacao_risco.probabilidade == 2  # 1 evidência agora
    assert escore_dominio.classificacao_risco.banda == "Alto"


@pytest.mark.django_db
def test_checklist_conforme_nao_conta_como_evidencia(aplicacao_copsoq, responder_dominio):
    from avaliacoes.models import (
        ColetaChecklistTriangulacao,
        ItemChecklistTriangulacao,
        RespondenteChecklistTriangulacao,
        RespostaChecklistTriangulacao,
    )

    valores = {"D1.1": 4, "D1.2": 4, "D1.3": 5, "D1.4": 3, "D1.5": 4}
    dominio = responder_dominio(aplicacao_copsoq, "D1", valores, n_respondentes=5)

    coleta = ColetaChecklistTriangulacao.objects.create(aplicacao=aplicacao_copsoq)
    respondente = RespondenteChecklistTriangulacao.objects.create(coleta=coleta, nome="Gestor de Teste")
    item = ItemChecklistTriangulacao.objects.filter(tipo="observacao").first()
    RespostaChecklistTriangulacao.objects.create(
        respondente=respondente, item=item, conformidade="conforme", evidencia=""
    )

    escore_dominio = calcular_dominio(aplicacao_copsoq, dominio)
    assert escore_dominio.classificacao_risco.probabilidade == 1
    assert escore_dominio.classificacao_risco.banda == "Moderado"
