from django.core.management.base import BaseCommand, CommandError

from avaliacoes.models import CriterioVersao
from avaliacoes.risk_engine_lib.risk_engine import (
    LIMIAR_EVENTO_GRAVE,
    LIMITE_BAIXO_DEFAULT,
    LIMITE_ELEVADO_DEFAULT,
    N_MINIMO_RESPONDENTES,
    PREVALENCIA_P1,
    PREVALENCIA_P2,
)
from avaliacoes.services.criterio_versao import matriz_risco_lista, severidade_por_classificacao_dict
from instrumentos.models import Dominio


def _thresholds_por_dominio_json() -> dict:
    """Origem: Seção 7.3 — os thresholds vêm do seed, já carregados em
    instrumentos.Dominio por `load_instrumentos`."""
    thresholds: dict[str, dict[str, dict[str, float]]] = {}
    for dominio in Dominio.objects.select_related("instrumento").all():
        thresholds.setdefault(dominio.instrumento.codigo, {})[dominio.codigo] = {
            "baixo_max": float(dominio.thresholds_referencia_baixo_max),
            "moderado_max": float(dominio.thresholds_referencia_moderado_max),
        }
    return thresholds


class Command(BaseCommand):
    help = (
        "Cria um snapshot CriterioVersao (CLAUDE.md Seção 7.8) a partir das constantes de "
        "risk_engine.py (7.4 severidade, 7.5 limiar de evento grave, 7.6 matriz de risco, "
        "7.7 N mínimo) e dos thresholds por domínio já carregados via load_instrumentos "
        "(7.3). Nunca redigita esses números — só lê e serializa. Recusa sobrescrever um "
        "código já existente: se risk_engine.py ou os thresholds mudarem, crie uma nova "
        "versão (ex. v1.1) em vez de editar uma existente."
    )

    def add_arguments(self, parser):
        parser.add_argument("--codigo", default="v1.0", help='Ex.: "v1.0" (default).')
        parser.add_argument(
            "--descricao",
            default=(
                "Snapshot inicial gerado a partir de risk_engine.py e dos thresholds importados "
                "via load_instrumentos. Aguardando ratificação formal do profissional responsável "
                "do PGR (CLAUDE.md Seção 7.3, princípio 9) antes de uso conclusivo."
            ),
        )

    def handle(self, *args, **options):
        codigo = options["codigo"]

        if CriterioVersao.objects.filter(codigo=codigo).exists():
            raise CommandError(
                f'Já existe um CriterioVersao "{codigo}". Uma versão existente nunca é '
                f"editada silenciosamente (CLAUDE.md Seção 7.8) — rode de novo com "
                f'--codigo apontando pra uma versão nova (ex.: "v1.1").'
            )

        thresholds_por_dominio = _thresholds_por_dominio_json()
        if not thresholds_por_dominio:
            raise CommandError(
                "Nenhum instrumentos.Dominio encontrado. Rode `load_instrumentos` para os "
                "seeds antes de criar um CriterioVersao."
            )

        criterio = CriterioVersao.objects.create(
            codigo=codigo,
            descricao=options["descricao"],
            thresholds_por_dominio=thresholds_por_dominio,
            severidade_por_classificacao=severidade_por_classificacao_dict(),
            matriz_risco=matriz_risco_lista(),
            n_minimo_respondentes=N_MINIMO_RESPONDENTES,
            limiar_evento_grave=LIMIAR_EVENTO_GRAVE,
            limite_baixo=LIMITE_BAIXO_DEFAULT,
            limite_elevado=LIMITE_ELEVADO_DEFAULT,
            prevalencia_p1=PREVALENCIA_P1,
            prevalencia_p2=PREVALENCIA_P2,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'CriterioVersao "{criterio.codigo}" criado (status={criterio.status}). '
                f"{len(thresholds_por_dominio)} instrumento(s), "
                f"{len(criterio.matriz_risco)} combinações na matriz de risco."
            )
        )
