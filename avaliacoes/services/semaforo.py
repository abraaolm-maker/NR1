"""Semáforo de Riscos — distribuição percentual de respondentes por faixa (planilha
`Semaforo_Riscos` do Excel de referência, prompts/11_semaforo_riscos.md).

Diferente do Diagnóstico GHE (Prompt 06, uma linha por GHE x domínio), o Semáforo agrega
por domínio um conjunto de Aplicacoes — tipicamente todas as de uma Unidade ("TOTAL
ORGANIZAÇÃO" no Excel) ou um GHE específico — a partir dos `EscoreRespondente` (Prompt 04)
já calculados. Nunca recalcula escore, só lê e agrega.

Faixas (mesmos limites do CriterioVersao — Seção 7.8, nunca hardcoded fora dele):
  verde/favorável:      escore <= limite_baixo
  amarelo/intermediário: limite_baixo < escore < limite_elevado
  vermelho/risco:       escore >= limite_elevado

Confidencialidade: o N mínimo (Seção 7.7) vale TAMBÉM no agregado. Incluir GHEs
suprimidos no total da unidade só é legítimo quando o total agregado atinge o mínimo —
do contrário o "agregado" é, na prática, a resposta individual de poucas pessoas, e o
Semáforo estaria exibindo exatamente o que o Diagnóstico GHE suprime (vazamento real
encontrado no diagnóstico de UX de 2026-07-28: unidade com 1 respondente mostrava os
escores abertos aqui e "SUPRIMIDO" em todas as outras telas).
"""

from avaliacoes.models import Aplicacao, EscoreRespondente
from avaliacoes.risk_engine_lib import risk_engine


def calcular_semaforo(aplicacoes: list[Aplicacao]) -> list[dict]:
    """Uma linha por domínio, agregando os EscoreRespondente de todas as `aplicacoes`
    informadas. Os limites (baixo/elevado) e a prevalência (P1/P2/P3) vêm do
    CriterioVersao da primeira Aplicacao da lista — na prática todas as Aplicacoes de
    uma mesma Unidade/Relatorio compartilham o mesmo critério (CLAUDE.md Seção 4.1,
    decisão #2). Domínios são agrupados por pk — instrumentos diferentes com domínios
    de mesmo código nunca se misturam."""
    if not aplicacoes:
        return []

    criterio = aplicacoes[0].criterio_versao
    limite_baixo = float(criterio.limite_baixo)
    limite_elevado = float(criterio.limite_elevado)
    p1_threshold = float(criterio.prevalencia_p1)
    p2_threshold = float(criterio.prevalencia_p2)
    n_minimo = criterio.n_minimo_respondentes

    escores_qs = EscoreRespondente.objects.filter(
        respondente__aplicacao__in=aplicacoes
    ).select_related("dominio")

    escores_por_dominio: dict[int, dict] = {}
    for escore_resp in escores_qs:
        dominio = escore_resp.dominio
        grupo = escores_por_dominio.setdefault(
            dominio.pk, {"dominio": dominio, "escores": []}
        )
        grupo["escores"].append(float(escore_resp.escore))

    linhas = []
    for grupo in sorted(escores_por_dominio.values(), key=lambda g: g["dominio"].ordem):
        dominio = grupo["dominio"]
        escores = grupo["escores"]
        n = len(escores)

        if n < n_minimo:
            # Supressão por confidencialidade no agregado (Seção 7.7): nenhum
            # percentual, média ou prioridade vaza pra fora quando o total ainda
            # está abaixo do mínimo — mesma regra das outras telas.
            linhas.append(
                {
                    "dominio_codigo": dominio.codigo,
                    "dominio_nome": dominio.nome,
                    "n_respondentes": n,
                    "suprimido": True,
                    "n_minimo": n_minimo,
                    "pct_favoravel": None,
                    "pct_intermediario": None,
                    "pct_risco": None,
                    "prioridade": None,
                    "media_risco": None,
                }
            )
            continue

        n_favoravel = sum(1 for e in escores if e <= limite_baixo)
        n_risco = sum(1 for e in escores if e >= limite_elevado)
        n_intermediario = n - n_favoravel - n_risco

        prevalencia = risk_engine.calcular_prevalencia(
            escores, limite_elevado=limite_elevado, p1_threshold=p1_threshold, p2_threshold=p2_threshold
        )

        linhas.append(
            {
                "dominio_codigo": dominio.codigo,
                "dominio_nome": dominio.nome,
                "n_respondentes": n,
                "suprimido": False,
                "n_minimo": n_minimo,
                "pct_favoravel": n_favoravel / n,
                "pct_intermediario": n_intermediario / n,
                "pct_risco": n_risco / n,
                "prioridade": prevalencia.prioridade.value,
                "media_risco": round(sum(escores) / n, 2),
            }
        )

    return linhas


def leitura_resumida(linhas: list[dict]) -> dict:
    """Texto de apoio abaixo da tabela: domínio com maior % em vermelho + contagem por
    prioridade (P1/P2/P3) — mesma leitura da aba Semaforo_Riscos do Excel. Linhas
    suprimidas por confidencialidade ficam de fora da leitura."""
    linhas_visiveis = [linha for linha in linhas if not linha.get("suprimido")]
    if not linhas_visiveis:
        return {"maior_risco": None, "contagem_prioridade": {"P1": 0, "P2": 0, "P3": 0}}

    maior_risco = max(linhas_visiveis, key=lambda linha: linha["pct_risco"])
    contagem_prioridade = {"P1": 0, "P2": 0, "P3": 0}
    for linha in linhas_visiveis:
        if linha["prioridade"] in contagem_prioridade:
            contagem_prioridade[linha["prioridade"]] += 1

    return {"maior_risco": maior_risco, "contagem_prioridade": contagem_prioridade}
