"""
test_risk_engine.py

Testes do motor de cálculo (risk_engine.py). Rodar com: pytest test_risk_engine.py -v

Cobre exatamente os casos que a Seção 7.9 do CLAUDE.md exige:
- conversão para escala 0–100 + inversão de polaridade
- domínio de polaridade mista (D9 do COPSOQ)
- as 9 combinações da matriz de risco
- regra de evento grave forçando P=3
- supressão por N mínimo de respondentes
- prevalência (P1/P2/P3)
"""

import pytest

from risk_engine import (
    ItemInstrumento,
    Polaridade,
    Classificacao,
    BandaRisco,
    Prioridade,
    RespostaItem,
    Thresholds,
    inverter_se_necessario,
    calcular_escore_dominio,
    classificar_escore,
    calcular_severidade,
    calcular_probabilidade,
    calcular_prevalencia,
    verificar_evento_grave,
    calcular_risco,
    deve_suprimir_por_confidencialidade,
    avaliar_dominio,
    MATRIZ_RISCO,
)


# ---------------------------------------------------------------------------
# Conversão para escala 0–100 + inversão de polaridade
# ---------------------------------------------------------------------------

def test_conversao_item_risco_para_escala_0_100():
    # escala 1-5: valor 4 RISCO → (4-1)*100/4 = 75
    assert inverter_se_necessario(4, Polaridade.RISCO, 1, 5) == 75.0
    assert inverter_se_necessario(1, Polaridade.RISCO, 1, 5) == 0.0
    assert inverter_se_necessario(5, Polaridade.RISCO, 1, 5) == 100.0
    assert inverter_se_necessario(3, Polaridade.RISCO, 1, 5) == 50.0


def test_conversao_item_protetivo_para_escala_0_100():
    # escala 1-5: valor 5 (muito bom) PROTETIVO → (5-5)*100/4 = 0 (risco zero)
    assert inverter_se_necessario(5, Polaridade.PROTETIVO, 1, 5) == 0.0
    # valor 1 (muito ruim) PROTETIVO → (5-1)*100/4 = 100 (risco máximo)
    assert inverter_se_necessario(1, Polaridade.PROTETIVO, 1, 5) == 100.0
    # ponto médio continua no meio
    assert inverter_se_necessario(3, Polaridade.PROTETIVO, 1, 5) == 50.0


# ---------------------------------------------------------------------------
# Domínio de polaridade mista — caso real do D9 do COPSOQ
# ---------------------------------------------------------------------------

def test_dominio_d9_polaridade_mista_calcula_risco_alto_corretamente():
    itens = {
        "D9.1": ItemInstrumento("D9.1", Polaridade.RISCO, evento_grave=True),
        "D9.2": ItemInstrumento("D9.2", Polaridade.RISCO, evento_grave=True),
        "D9.3": ItemInstrumento("D9.3", Polaridade.PROTETIVO),
        "D9.4": ItemInstrumento("D9.4", Polaridade.PROTETIVO),
    }
    # Cenário: respondente relata alta exposição a violência (D9.1=5, D9.2=5)
    # e baixa confiança nos canais de proteção (D9.3=1, D9.4=1)
    # RISCO 5 → 100; PROTETIVO 1 → 100; todos viram 100 → média 100
    respostas = [
        RespostaItem("D9.1", 5),
        RespostaItem("D9.2", 5),
        RespostaItem("D9.3", 1),
        RespostaItem("D9.4", 1),
    ]
    escore = calcular_escore_dominio(respostas, itens, escala_min=1, escala_max=5)
    assert escore == 100.0

    thresholds = Thresholds(baixo_max=37.5, moderado_max=62.5)
    classificacao = classificar_escore(escore, thresholds)
    assert classificacao == Classificacao.ELEVADO

    evento_grave = verificar_evento_grave(respostas, itens)
    assert evento_grave is True

    severidade = calcular_severidade(classificacao)
    resultado = calcular_risco(severidade, evidencias_convergentes=0, evento_grave_confirmado=evento_grave)
    assert resultado.probabilidade == 3
    assert resultado.banda == BandaRisco.CRITICO
    assert resultado.prazo_dias_plano_de_acao == 15


def test_dominio_d9_sem_relatos_graves_mas_baixa_confianca_nos_canais():
    itens = {
        "D9.1": ItemInstrumento("D9.1", Polaridade.RISCO, evento_grave=True),
        "D9.2": ItemInstrumento("D9.2", Polaridade.RISCO, evento_grave=True),
        "D9.3": ItemInstrumento("D9.3", Polaridade.PROTETIVO),
        "D9.4": ItemInstrumento("D9.4", Polaridade.PROTETIVO),
    }
    respostas = [
        RespostaItem("D9.1", 1),
        RespostaItem("D9.2", 1),
        RespostaItem("D9.3", 2),
        RespostaItem("D9.4", 2),
    ]
    evento_grave = verificar_evento_grave(respostas, itens)
    assert evento_grave is False


# ---------------------------------------------------------------------------
# Todas as 9 combinações da matriz de risco
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "severidade,probabilidade,banda_esperada,score_esperado",
    [
        (1, 1, BandaRisco.ACEITAVEL, 1),
        (1, 2, BandaRisco.ACEITAVEL, 2),
        (2, 1, BandaRisco.ACEITAVEL, 2),
        (1, 3, BandaRisco.MODERADO, 3),
        (3, 1, BandaRisco.MODERADO, 3),
        (2, 2, BandaRisco.MODERADO, 4),
        (2, 3, BandaRisco.ALTO, 6),
        (3, 2, BandaRisco.ALTO, 6),
        (3, 3, BandaRisco.CRITICO, 9),
    ],
)
def test_todas_as_9_combinacoes_da_matriz(severidade, probabilidade, banda_esperada, score_esperado):
    assert MATRIZ_RISCO[(severidade, probabilidade)] == banda_esperada
    assert severidade * probabilidade == score_esperado


# ---------------------------------------------------------------------------
# Regra de probabilidade por evidências convergentes
# ---------------------------------------------------------------------------

def test_probabilidade_sem_evidencias_complementares():
    assert calcular_probabilidade(evidencias_convergentes=0, evento_grave_confirmado=False) == 1


def test_probabilidade_uma_evidencia_complementar():
    assert calcular_probabilidade(evidencias_convergentes=1, evento_grave_confirmado=False) == 2


def test_probabilidade_duas_ou_mais_evidencias():
    assert calcular_probabilidade(evidencias_convergentes=2, evento_grave_confirmado=False) == 3
    assert calcular_probabilidade(evidencias_convergentes=5, evento_grave_confirmado=False) == 3


def test_evento_grave_forca_probabilidade_3_mesmo_sem_evidencias():
    assert calcular_probabilidade(evidencias_convergentes=0, evento_grave_confirmado=True) == 3


# ---------------------------------------------------------------------------
# Supressão por N mínimo de respondentes (confidencialidade)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n,esperado", [(0, True), (1, True), (2, True), (3, True), (4, True), (5, False), (10, False)])
def test_supressao_por_confidencialidade(n, esperado):
    assert deve_suprimir_por_confidencialidade(n) == esperado


# ---------------------------------------------------------------------------
# Prevalência (P1/P2/P3)
# ---------------------------------------------------------------------------

def test_prevalencia_p1_maioria_elevada():
    # 6 de 10 respondentes >= 62.5 → 60% → P1
    escores = [80, 70, 65, 90, 75, 63, 30, 20, 10, 40]
    resultado = calcular_prevalencia(escores)
    assert resultado.prioridade == Prioridade.P1
    assert resultado.percentual_elevados == 0.6


def test_prevalencia_p2_minoria_significativa():
    # 3 de 10 → 30% → P2
    escores = [80, 70, 65, 30, 20, 10, 40, 35, 25, 15]
    resultado = calcular_prevalencia(escores)
    assert resultado.prioridade == Prioridade.P2
    assert resultado.percentual_elevados == 0.3


def test_prevalencia_p3_poucos_elevados():
    # 1 de 10 → 10% → P3
    escores = [80, 30, 20, 10, 40, 35, 25, 15, 5, 0]
    resultado = calcular_prevalencia(escores)
    assert resultado.prioridade == Prioridade.P3
    assert resultado.percentual_elevados == 0.1


def test_prevalencia_lista_vazia():
    resultado = calcular_prevalencia([])
    assert resultado.prioridade == Prioridade.P3
    assert resultado.percentual_elevados == 0.0


# ---------------------------------------------------------------------------
# Pipeline completo (smoke test) — instrumento COPSOQ, domínio D1
# ---------------------------------------------------------------------------

def test_pipeline_completo_dominio_de_risco_puro():
    itens = {
        "D1.1": ItemInstrumento("D1.1", Polaridade.RISCO),
        "D1.2": ItemInstrumento("D1.2", Polaridade.RISCO),
        "D1.3": ItemInstrumento("D1.3", Polaridade.RISCO),
        "D1.4": ItemInstrumento("D1.4", Polaridade.RISCO),
        "D1.5": ItemInstrumento("D1.5", Polaridade.RISCO),
    }
    # Respostas brutas: 4,4,5,3,4 → convertidas 0-100: 75,75,100,50,75 → média = 75.0
    respostas = [
        RespostaItem("D1.1", 4), RespostaItem("D1.2", 4), RespostaItem("D1.3", 5),
        RespostaItem("D1.4", 3), RespostaItem("D1.5", 4),
    ]
    thresholds = Thresholds(baixo_max=37.5, moderado_max=62.5)

    resultado_dominio, resultado_risco, suprimir = avaliar_dominio(
        codigo_dominio="D1",
        respostas=respostas,
        itens_por_id=itens,
        thresholds=thresholds,
        escala_min=1,
        escala_max=5,
        n_respondentes=5,
        evidencias_convergentes=1,
    )

    assert resultado_dominio.escore == 75.0
    assert resultado_dominio.classificacao == Classificacao.ELEVADO
    assert resultado_risco.severidade == 3
    assert resultado_risco.probabilidade == 2
    assert resultado_risco.banda == BandaRisco.ALTO
    assert suprimir is False
