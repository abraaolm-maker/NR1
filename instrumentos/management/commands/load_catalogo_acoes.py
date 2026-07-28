import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from avaliacoes.models import CatalogoAcao
from instrumentos.models import Dominio, Instrumento


class Command(BaseCommand):
    help = (
        "Importa o catálogo de ações preventivas pré-definidas (CatalogoAcao) a partir de um "
        "JSON no formato de seeds/catalogo_acoes.json — uma linha por (domínio, nível). "
        "Idempotente (update_or_create) — rodar de novo atualiza em vez de duplicar."
    )

    def add_arguments(self, parser):
        parser.add_argument("json_path", type=str, help="Caminho do arquivo JSON do catálogo.")

    def handle(self, *args, **options):
        path = Path(options["json_path"])
        if not path.exists():
            raise CommandError(f"Arquivo não encontrado: {path}")

        with path.open(encoding="utf-8") as f:
            data = json.load(f)

        try:
            instrumento = Instrumento.objects.get(codigo=data["instrument_code"])
        except Instrumento.DoesNotExist as exc:
            raise CommandError(
                f'Instrumento "{data["instrument_code"]}" não encontrado — rode '
                "load_instrumentos antes de load_catalogo_acoes."
            ) from exc

        total = 0
        for entrada in data["acoes"]:
            try:
                dominio = Dominio.objects.get(instrumento=instrumento, codigo=entrada["dominio_codigo"])
            except Dominio.DoesNotExist as exc:
                raise CommandError(
                    f'Domínio "{entrada["dominio_codigo"]}" não encontrado em "{instrumento.codigo}".'
                ) from exc

            CatalogoAcao.objects.update_or_create(
                dominio=dominio,
                nivel=entrada["nivel"],
                defaults={
                    "acao_sugerida": entrada["acao_sugerida"],
                    "hierarquia": entrada["hierarquia"],
                    "indicador": entrada.get("indicador", ""),
                },
            )
            total += 1

        self.stdout.write(self.style.SUCCESS(f'{total} ação(ões) do catálogo importadas para "{instrumento.codigo}".'))
