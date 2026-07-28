"""Ponte entre risk_engine.py e avaliacoes.CriterioVersao (CLAUDE.md Seção 7.8).

Fonte única: estas funções só LEEM as constantes de risk_engine.py e as traduzem pra
JSON — nunca redigitam os números. Usadas tanto pelo management command
`criar_criterio_versao` (pra montar o snapshot) quanto por
`avaliacoes.services.calculo_risco` (pra conferir, antes de calcular, que o snapshot
de uma Aplicacao ainda bate com o código atual do risk_engine.py)."""

from avaliacoes.risk_engine_lib.risk_engine import MATRIZ_RISCO, PRAZO_DIAS_POR_BANDA, SEVERIDADE_POR_CLASSIFICACAO


def severidade_por_classificacao_dict() -> dict:
    return {classificacao.value: severidade for classificacao, severidade in SEVERIDADE_POR_CLASSIFICACAO.items()}


def matriz_risco_lista() -> list[dict]:
    return [
        {
            "severidade": severidade,
            "probabilidade": probabilidade,
            "banda": banda.value,
            "prazo_dias": PRAZO_DIAS_POR_BANDA[banda],
        }
        for (severidade, probabilidade), banda in MATRIZ_RISCO.items()
    ]


class CriterioVersaoDesatualizadoError(Exception):
    """risk_engine.py mudou suas constantes desde que este CriterioVersao foi criado.

    CLAUDE.md Seção 7.8: uma versão nunca é editada silenciosamente. Se isso disparar,
    a ação correta é rodar `criar_criterio_versao --codigo <nova-versão>` e apontar
    novas Aplicacoes pra ela — não "consertar" a versão existente."""


def verificar_criterio_versao_atualizado(criterio) -> None:
    from avaliacoes.risk_engine_lib.risk_engine import LIMIAR_EVENTO_GRAVE, N_MINIMO_RESPONDENTES

    if criterio.severidade_por_classificacao != severidade_por_classificacao_dict():
        raise CriterioVersaoDesatualizadoError(
            f'CriterioVersao "{criterio.codigo}": severidade_por_classificacao não bate mais '
            "com risk_engine.SEVERIDADE_POR_CLASSIFICACAO."
        )
    if criterio.matriz_risco != matriz_risco_lista():
        raise CriterioVersaoDesatualizadoError(
            f'CriterioVersao "{criterio.codigo}": matriz_risco não bate mais com '
            "risk_engine.MATRIZ_RISCO/PRAZO_DIAS_POR_BANDA."
        )
    if criterio.n_minimo_respondentes != N_MINIMO_RESPONDENTES:
        raise CriterioVersaoDesatualizadoError(
            f'CriterioVersao "{criterio.codigo}": n_minimo_respondentes não bate mais com '
            "risk_engine.N_MINIMO_RESPONDENTES."
        )
    if criterio.limiar_evento_grave != LIMIAR_EVENTO_GRAVE:
        raise CriterioVersaoDesatualizadoError(
            f'CriterioVersao "{criterio.codigo}": limiar_evento_grave não bate mais com '
            "risk_engine.LIMIAR_EVENTO_GRAVE."
        )
