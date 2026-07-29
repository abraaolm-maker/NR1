"""Suporte ao fluxo público do questionário (CLAUDE.md Etapa 7.2 / revisão de UX de
2026-07-29 — uma pergunta por página em vez de um domínio inteiro por página, pra
aumentar a concentração de quem responde).

A ordem é uma lista única e plana de itens, cruzando todos os domínios da Aplicacao
(na ordem de `dominios_da_aplicacao` e depois `itens_da_aplicacao` dentro de cada
domínio) — não existe mais "domínio atual"; existe "item atual dentro da sequência
inteira". O título do domínio mostrado na tela muda sozinho quando o item muda de
domínio, sem precisar de nenhum estado extra: cada página só olha pro domínio do
item que está mostrando."""

from avaliacoes.models import Respondente, Resposta
from avaliacoes.services.calculo_risco import dominios_da_aplicacao, itens_da_aplicacao
from instrumentos.models import Item


def itens_em_ordem(aplicacao) -> list[Item]:
    """Lista plana e ordenada de todos os itens aplicáveis à Aplicacao (já filtrados
    por profundidade quando o instrumento usa esse conceito — CLAUDE.md Seção 5.1.1)."""
    itens = []
    for dominio in dominios_da_aplicacao(aplicacao):
        itens.extend(itens_da_aplicacao(aplicacao, dominio))
    return itens


def proximo_item_pendente(respondente: Respondente) -> Item | None:
    """Primeiro item da sequência que este respondente ainda não respondeu, ou None
    se todos já foram respondidos (nesse caso o fluxo segue pras perguntas abertas)."""
    respondidos = set(Resposta.objects.filter(respondente=respondente).values_list("item_id", flat=True))
    for item in itens_em_ordem(respondente.aplicacao):
        if item.pk not in respondidos:
            return item
    return None


def posicao_item(aplicacao, item: Item) -> dict:
    """1-based: {'atual': N, 'total': T} — usado pra 'Pergunta N de T' e pra barra
    de progresso. Item que não pertence à Aplicacao não aparece na lista (index()
    levantaria ValueError de propósito, é bug de chamada, não deveria acontecer)."""
    todos = itens_em_ordem(aplicacao)
    return {"atual": todos.index(item) + 1, "total": len(todos)}
