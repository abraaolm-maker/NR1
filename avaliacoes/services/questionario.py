"""Suporte ao fluxo público do questionário (CLAUDE.md Etapa 7.2).

Resolve "o que falta responder" pra permitir retomar de onde parou (mesmo link,
reaberto depois) sem repetir domínios já completos."""

from avaliacoes.models import Respondente, Resposta
from avaliacoes.services.calculo_risco import dominios_da_aplicacao
from instrumentos.models import Dominio


def dominios_pendentes(respondente: Respondente) -> list[Dominio]:
    """Domínios aplicáveis à Aplicacao deste Respondente que ainda têm pelo menos um
    item sem Resposta registrada por ele."""
    pendentes = []
    for dominio in dominios_da_aplicacao(respondente.aplicacao):
        item_ids = set(dominio.itens.values_list("item_id", flat=True))
        respondidos = set(
            Resposta.objects.filter(respondente=respondente, item__dominio=dominio).values_list(
                "item__item_id", flat=True
            )
        )
        if item_ids - respondidos:
            pendentes.append(dominio)
    return pendentes
