"""Transição de status da Aplicacao. rascunho -> em_andamento na primeira Resposta
recebida (automático). em_andamento -> concluida é sempre uma ação manual do gestor
(`encerrar_coleta`) — desde que o link de resposta passou a ser único e universal por
Aplicacao (CLAUDE.md Seção 6.7), não existe mais um conjunto fixo de Respondentes pra
detectar "todos terminaram": sempre pode chegar mais um respondente pelo mesmo link.

Nunca sai de `cancelada`, nem regride uma `concluida` de volta.
"""

from django.core.exceptions import ValidationError
from django.utils import timezone

from avaliacoes.models import Aplicacao, Resposta, StatusAplicacao


def atualizar_status_aplicacao(aplicacao_id: int) -> Aplicacao:
    aplicacao = Aplicacao.objects.get(pk=aplicacao_id)

    if aplicacao.status == StatusAplicacao.RASCUNHO and Resposta.objects.filter(
        respondente__aplicacao=aplicacao
    ).exists():
        aplicacao.status = StatusAplicacao.EM_ANDAMENTO
        aplicacao.save(update_fields=["status"])

    return aplicacao


def encerrar_coleta(aplicacao_id: int) -> Aplicacao:
    """Ação manual do gestor pra fechar a coleta e travar o link de resposta."""
    aplicacao = Aplicacao.objects.get(pk=aplicacao_id)
    if aplicacao.status not in (StatusAplicacao.RASCUNHO, StatusAplicacao.EM_ANDAMENTO):
        raise ValidationError(f'Aplicacao com status "{aplicacao.get_status_display()}" não pode ser encerrada.')

    aplicacao.status = StatusAplicacao.CONCLUIDA
    aplicacao.concluida_em = timezone.now()
    aplicacao.save(update_fields=["status", "concluida_em"])
    return aplicacao
