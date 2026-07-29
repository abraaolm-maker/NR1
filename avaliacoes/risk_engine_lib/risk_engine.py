"""
risk_engine.py

Motor de cálculo determinístico da matriz de risco psicossocial.
Implementação de referência da Seção 7 do CLAUDE.md deste projeto.

Não depende de Django nem de banco de dados — é Python puro, testável isoladamente
com pytest (ver test_risk_engine.py) e importável por qualquer app/service do backend.

Se este arquivo divergir do texto do CLAUDE.md no futuro, ESTE ARQUIVO é a fonte de verdade
e o CLAUDE.md deve ser atualizado para refletir a mudança (mantê-los sincronizados).

Escala de escores: 0–100 (normalizado a partir das respostas brutas 1–5 ou outra).
Fórmula de conversão: RISCO → (valor - min) * 100 / (max - min);
                       PROTETIVO → (max - valor) * 100 / (max - min).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from statistics import mean


class Polaridade(str, Enum):
    RISCO = "RISCO"
    PROTETIVO = "PROTETIVO"


class Classificacao(str, Enum):
    BAIXO = "Baixo"
    MODERADO = "Moderado"
    ELEVADO = "Elevado"


class BandaRisco(str, Enum):
    ACEITAVEL = "Aceitável"
    MODERADO = "Moderado"
    ALTO = "Alto"
    CRITICO = "Crítico"


class Prioridade(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    AGRUPAR = "AGRUPAR"  # N < n_minimo (Seção 7.7) — planilha Diagnostico_GHE do Excel de referência


# ---------------------------------------------------------------------------
# Constantes definitivas do projeto (Seção 7 do CLAUDE.md)
# ---------------------------------------------------------------------------

N_MINIMO_RESPONDENTES = 5

SEVERIDADE_POR_CLASSIFICACAO: dict[Classificacao, int] = {
    Classificacao.BAIXO: 1,
    Classificacao.MODERADO: 2,
    Classificacao.ELEVADO: 3,
}

# Todas as 9 combinações possíveis de Severidade (1-3) x Probabilidade (1-3).
# Chave: (severidade, probabilidade) -> banda de risco
MATRIZ_RISCO: dict[tuple[int, int], BandaRisco] = {
    (1, 1): BandaRisco.ACEITAVEL,
    (1, 2): BandaRisco.ACEITAVEL,
    (2, 1): BandaRisco.ACEITAVEL,
    (1, 3): BandaRisco.MODERADO,
    (3, 1): BandaRisco.MODERADO,
    (2, 2): BandaRisco.MODERADO,
    (2, 3): BandaRisco.ALTO,
    (3, 2): BandaRisco.ALTO,
    (3, 3): BandaRisco.CRITICO,
}

PRAZO_DIAS_POR_BANDA: dict[BandaRisco, int | None] = {
    BandaRisco.ACEITAVEL: None,  # sem prazo de ação corretiva, só monitoramento no próximo ciclo
    BandaRisco.MODERADO: 90,
    BandaRisco.ALTO: 30,
    BandaRisco.CRITICO: 15,
}

# Limiar de valor bruto (escala original, ex. 1–5) acima do qual um item marcado como
# `evento_grave` força Probabilidade = 3 (Seção 7.5 do CLAUDE.md).
# Checado contra o valor bruto, não o convertido 0–100.
LIMIAR_EVENTO_GRAVE = 4

# Defaults de prevalência (planilha Configuracao do Excel)
PREVALENCIA_P1 = 0.50
PREVALENCIA_P2 = 0.25

# Defaults de limites na escala 0–100
LIMITE_BAIXO_DEFAULT = 37.5
LIMITE_ELEVADO_DEFAULT = 62.5

# Banda de risco a partir da Prioridade por prevalência (P1/P2/P3), não mais da matriz
# Severidade × Probabilidade acima (achado de 2026-07-29: a regra de "evidências
# convergentes -> probabilidade 1/2/3" não tinha nenhuma fonte científica ou normativa
# citável, era uma convenção de engenharia deste projeto sem lastro, e gerava um
# resultado divergente do semáforo do próprio manual COPSOQ e da planilha de
# referência do projeto — um domínio podia sair 100% "Risco" no semáforo/prevalência e
# ainda assim "Moderado" na Banda, sem nenhuma explicação que não fosse "falta
# evidência cadastrada"). A partir de agora a Banda é diretamente a mesma classificação
# tripartida do manual COPSOQ (Portugal 2013, p. 15: "interpretação semáforo"),
# reaproveitando a Prioridade que já é calculada a partir da prevalência de
# respondentes na faixa elevada (Seção 6.9 do CLAUDE.md).
BANDA_POR_PRIORIDADE: dict[Prioridade, BandaRisco] = {
    Prioridade.P3: BandaRisco.ACEITAVEL,
    Prioridade.P2: BandaRisco.MODERADO,
    Prioridade.P1: BandaRisco.ALTO,
}


# ---------------------------------------------------------------------------
# Estruturas de dados de entrada/saída
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ItemInstrumento:
    id: str
    polaridade: Polaridade
    evento_grave: bool = False


@dataclass(frozen=True)
class Thresholds:
    baixo_max: float
    moderado_max: float


@dataclass(frozen=True)
class RespostaItem:
    item_id: str
    valor_bruto: float


@dataclass
class ResultadoDominio:
    codigo: str
    escore: float
    classificacao: Classificacao
    severidade: int


@dataclass
class ResultadoRisco:
    severidade: int
    probabilidade: int
    score: int
    banda: BandaRisco
    prazo_dias_plano_de_acao: int | None
    evento_grave_confirmado: bool


@dataclass
class ResultadoPrevalencia:
    percentual_elevados: float
    prioridade: Prioridade


# ---------------------------------------------------------------------------
# 7.1 — Conversão para escala 0–100 + inversão de polaridade
# ---------------------------------------------------------------------------

def inverter_se_necessario(
    valor_bruto: float,
    polaridade: Polaridade,
    escala_min: int,
    escala_max: int,
) -> float:
    """Converte o valor bruto para escala 0–100, invertendo itens PROTETIVO.
    RISCO: (valor - min) * 100 / (max - min)
    PROTETIVO: (max - valor) * 100 / (max - min)"""
    amplitude = escala_max - escala_min
    if amplitude == 0:
        return 0.0
    if polaridade == Polaridade.PROTETIVO:
        return (escala_max - valor_bruto) * 100 / amplitude
    return (valor_bruto - escala_min) * 100 / amplitude


# ---------------------------------------------------------------------------
# 7.2 — Escore por domínio/subescala
# ---------------------------------------------------------------------------

def calcular_escore_dominio(
    respostas: list[RespostaItem],
    itens_por_id: dict[str, ItemInstrumento],
    escala_min: int,
    escala_max: int,
) -> float:
    """Calcula o escore médio de um domínio na escala 0–100."""
    if not respostas:
        raise ValueError("Não é possível calcular escore de domínio sem respostas.")

    valores_ajustados = []
    for resposta in respostas:
        item = itens_por_id[resposta.item_id]
        valores_ajustados.append(
            inverter_se_necessario(resposta.valor_bruto, item.polaridade, escala_min, escala_max)
        )
    return mean(valores_ajustados)


def calcular_escore_respondente(
    respostas_respondente: list[RespostaItem],
    itens_por_id: dict[str, ItemInstrumento],
    escala_min: int,
    escala_max: int,
) -> float:
    """Calcula o escore de UM respondente para um domínio, na escala 0–100."""
    return calcular_escore_dominio(respostas_respondente, itens_por_id, escala_min, escala_max)


# ---------------------------------------------------------------------------
# 7.3 — Classificação por domínio
# ---------------------------------------------------------------------------

def classificar_escore(escore: float, thresholds: Thresholds) -> Classificacao:
    if escore <= thresholds.baixo_max:
        return Classificacao.BAIXO
    if escore <= thresholds.moderado_max:
        return Classificacao.MODERADO
    return Classificacao.ELEVADO


# ---------------------------------------------------------------------------
# Prevalência (P1/P2/P3)
# ---------------------------------------------------------------------------

def calcular_prevalencia(
    escores_por_respondente: list[float],
    limite_elevado: float = LIMITE_ELEVADO_DEFAULT,
    p1_threshold: float = PREVALENCIA_P1,
    p2_threshold: float = PREVALENCIA_P2,
) -> ResultadoPrevalencia:
    """Calcula a prevalência de respondentes na faixa elevada e a prioridade."""
    if not escores_por_respondente:
        return ResultadoPrevalencia(percentual_elevados=0.0, prioridade=Prioridade.P3)
    n_elevados = sum(1 for e in escores_por_respondente if e >= limite_elevado)
    pct = n_elevados / len(escores_por_respondente)
    if pct >= p1_threshold:
        prioridade = Prioridade.P1
    elif pct >= p2_threshold:
        prioridade = Prioridade.P2
    else:
        prioridade = Prioridade.P3
    return ResultadoPrevalencia(percentual_elevados=round(pct, 4), prioridade=prioridade)


# ---------------------------------------------------------------------------
# 7.4 — Severidade
# ---------------------------------------------------------------------------

def calcular_severidade(classificacao: Classificacao) -> int:
    return SEVERIDADE_POR_CLASSIFICACAO[classificacao]


# ---------------------------------------------------------------------------
# 7.5 — Probabilidade
# ---------------------------------------------------------------------------

def calcular_probabilidade(
    evidencias_convergentes: int,
    evento_grave_confirmado: bool,
) -> int:
    """
    Regra definitiva (Seção 7.5 do CLAUDE.md):
    - evento_grave_confirmado=True força P=3, sempre.
    - Caso contrário, conta-se o número de evidências complementares convergentes
      (absenteísmo acima da média, turnover acima da média, CAT/CID-F relacionado,
      item "Não conforme" no checklist observacional, relato coerente na entrevista
      com a liderança):
        0 evidências -> P=1
        1 evidência  -> P=2
        2+ evidências -> P=3
    """
    if evento_grave_confirmado:
        return 3
    if evidencias_convergentes >= 2:
        return 3
    if evidencias_convergentes == 1:
        return 2
    return 1


def verificar_evento_grave(
    respostas: list[RespostaItem],
    itens_por_id: dict[str, ItemInstrumento],
) -> bool:
    """Retorna True se algum item marcado como evento_grave=True no seed teve
    valor_bruto >= LIMIAR_EVENTO_GRAVE em qualquer resposta.
    Nota: checado contra o valor bruto (escala original), não o convertido 0–100."""
    for resposta in respostas:
        item = itens_por_id[resposta.item_id]
        if item.evento_grave and resposta.valor_bruto >= LIMIAR_EVENTO_GRAVE:
            return True
    return False


# ---------------------------------------------------------------------------
# 7.6 — Matriz de risco
# ---------------------------------------------------------------------------

def calcular_risco(
    severidade: int,
    evidencias_convergentes: int,
    evento_grave_confirmado: bool,
) -> ResultadoRisco:
    if severidade not in (1, 2, 3):
        raise ValueError("Severidade deve ser 1, 2 ou 3.")

    probabilidade = calcular_probabilidade(evidencias_convergentes, evento_grave_confirmado)
    score = severidade * probabilidade
    banda = MATRIZ_RISCO[(severidade, probabilidade)]
    prazo = PRAZO_DIAS_POR_BANDA[banda]

    return ResultadoRisco(
        severidade=severidade,
        probabilidade=probabilidade,
        score=score,
        banda=banda,
        prazo_dias_plano_de_acao=prazo,
        evento_grave_confirmado=evento_grave_confirmado,
    )


# ---------------------------------------------------------------------------
# Banda de risco a partir da prevalência (substitui a matriz Severidade × Probabilidade
# como critério principal, achado de 2026-07-29 — ver comentário de BANDA_POR_PRIORIDADE)
# ---------------------------------------------------------------------------

def calcular_risco_por_prevalencia(
    prioridade: Prioridade,
    severidade: int,
    evento_grave_confirmado: bool,
) -> ResultadoRisco:
    """Banda = diretamente a Prioridade por prevalência (P1/P2/P3), igual à
    interpretação "semáforo" do próprio manual COPSOQ (verde/amarelo/vermelho por
    tercil) e à planilha de referência do projeto. Único escalonamento automático:
    evento_grave_confirmado (violência/assédio/discriminação relatado, Seção 7.5) força
    Banda = Crítico sempre, independente da prevalência — um relato grave confirmado
    nunca pode ficar mascarado por uma prevalência baixa. `probabilidade`/`score` são
    mantidos no resultado só como número informativo (proxy da prioridade: P1=3,
    P2=2, P3=1) — não são mais o critério que decide a banda."""
    if prioridade == Prioridade.AGRUPAR:
        raise ValueError("Prioridade AGRUPAR (suprimido) não gera Banda — trate a supressão antes de chamar.")

    if evento_grave_confirmado:
        banda = BandaRisco.CRITICO
    else:
        banda = BANDA_POR_PRIORIDADE[prioridade]

    probabilidade_proxy = {Prioridade.P1: 3, Prioridade.P2: 2, Prioridade.P3: 1}[prioridade]
    prazo = PRAZO_DIAS_POR_BANDA[banda]

    return ResultadoRisco(
        severidade=severidade,
        probabilidade=probabilidade_proxy,
        score=severidade * probabilidade_proxy,
        banda=banda,
        prazo_dias_plano_de_acao=prazo,
        evento_grave_confirmado=evento_grave_confirmado,
    )


# ---------------------------------------------------------------------------
# 7.7 — Confidencialidade
# ---------------------------------------------------------------------------

def deve_suprimir_por_confidencialidade(n_respondentes: int) -> bool:
    return n_respondentes < N_MINIMO_RESPONDENTES


# ---------------------------------------------------------------------------
# Pipeline de conveniência: do domínio bruto ao risco final
# ---------------------------------------------------------------------------

def avaliar_dominio(
    codigo_dominio: str,
    respostas: list[RespostaItem],
    itens_por_id: dict[str, ItemInstrumento],
    thresholds: Thresholds,
    escala_min: int,
    escala_max: int,
    n_respondentes: int,
    evidencias_convergentes: int = 0,
) -> tuple[ResultadoDominio, ResultadoRisco, bool]:
    """Executa o pipeline completo (7.1 a 7.7) para um domínio/subescala de um GHE.
    Retorna (resultado_dominio, resultado_risco, suprimir_por_confidencialidade).
    Escores são na escala 0–100."""

    escore = calcular_escore_dominio(respostas, itens_por_id, escala_min, escala_max)
    classificacao = classificar_escore(escore, thresholds)
    severidade = calcular_severidade(classificacao)
    evento_grave = verificar_evento_grave(respostas, itens_por_id)

    resultado_dominio = ResultadoDominio(
        codigo=codigo_dominio,
        escore=round(escore, 2),
        classificacao=classificacao,
        severidade=severidade,
    )
    resultado_risco = calcular_risco(severidade, evidencias_convergentes, evento_grave)
    suprimir = deve_suprimir_por_confidencialidade(n_respondentes)

    return resultado_dominio, resultado_risco, suprimir
