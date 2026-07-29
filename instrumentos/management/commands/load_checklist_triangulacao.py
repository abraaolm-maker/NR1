import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from avaliacoes.models import ItemChecklistTriangulacao


class Command(BaseCommand):
    help = (
        "Importa os itens pré-definidos do checklist de triangulação (entrevista com "
        "liderança + observação em campo) a partir de um JSON no formato de "
        "seeds/checklist_triangulacao.json. Idempotente (update_or_create por tipo+ordem)."
    )

    def add_arguments(self, parser):
        parser.add_argument("json_path", type=str, help="Caminho do arquivo JSON do checklist.")

    def handle(self, *args, **options):
        path = Path(options["json_path"])
        if not path.exists():
            raise CommandError(f"Arquivo não encontrado: {path}")

        with path.open(encoding="utf-8") as f:
            data = json.load(f)

        total = 0
        for entrada in data["itens"]:
            ItemChecklistTriangulacao.objects.update_or_create(
                tipo=entrada["tipo"],
                ordem=entrada["ordem"],
                defaults={
                    "texto": entrada["texto"],
                    "dominio_codigo_relacionado": entrada.get("dominio_relacionado", ""),
                },
            )
            total += 1

        self.stdout.write(self.style.SUCCESS(f"{total} item(ns) do checklist de triangulação importados."))
