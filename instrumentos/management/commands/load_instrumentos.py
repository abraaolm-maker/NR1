import json
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from instrumentos.models import Dominio, Instrumento, Item


def _entradas_de_dominio(data: dict) -> list[dict]:
    """Lê os domínios/subescalas de um seed — sempre uma lista solta em "domains"
    (COPSOQ) ou "scales" (ITRA, sinônimo genérico), nunca aninhada por cargo/GHE
    (removido em 2026-07-18 — ver CLAUDE.md Seção 6.5: um instrumento nunca assume
    cargo fixo, o mesmo texto de item vale para qualquer GHE que o utilize).

    Não assume qual instrumento é qual: só reconhece as chaves documentadas nos
    seeds (CLAUDE.md Seção 5)."""

    for chave in ("domains", "scales"):
        if chave in data:
            return list(data[chave])

    raise CommandError('JSON não tem nenhuma das chaves de agrupamento esperadas: "domains" ou "scales".')


def _decimal(valor) -> Decimal:
    return Decimal(str(valor))


class Command(BaseCommand):
    help = (
        "Importa um instrumento de coleta (Instrumento/Dominio/Item) a partir de um JSON "
        "no formato dos seeds (CLAUDE.md Seção 5). Genérico: lê qualquer instrumento nesse "
        "formato, não é hardcoded para COPSOQ nem para ITRA. Idempotente — pode rodar de novo "
        "sem duplicar registros."
    )

    def add_arguments(self, parser):
        parser.add_argument("json_path", type=str, help="Caminho do arquivo JSON do instrumento.")

    def handle(self, *args, **options):
        path = Path(options["json_path"])
        if not path.exists():
            raise CommandError(f"Arquivo não encontrado: {path}")

        with path.open(encoding="utf-8") as f:
            data = json.load(f)

        instrumento, criado = Instrumento.objects.update_or_create(
            codigo=data["instrument_code"],
            defaults={
                "nome": data["instrument_name"],
                "descricao": data.get("instrument_description", ""),
                "fonte": data.get("source_note", ""),
            },
        )
        self.stdout.write(
            self.style.SUCCESS(f'Instrumento "{instrumento.codigo}" {"criado" if criado else "atualizado"}.')
        )

        total_dominios = 0
        total_itens = 0

        for ordem_dominio, dominio_entry in enumerate(_entradas_de_dominio(data)):
            codigo = dominio_entry.get("code") or dominio_entry["scale_code"]
            nome = dominio_entry.get("name") or dominio_entry["scale_name"]
            escala = dominio_entry.get("scale", data.get("scale"))
            thresholds = dominio_entry.get("thresholds", data.get("thresholds"))

            if escala is None or thresholds is None:
                raise CommandError(
                    f'Domínio "{codigo}" não tem "scale"/"thresholds" próprios nem herdados '
                    "do nível do instrumento."
                )

            referencia = dominio_entry.get("reference")

            dominio, dominio_criado = Dominio.objects.update_or_create(
                instrumento=instrumento,
                codigo=codigo,
                defaults={
                    "nome": nome,
                    "nota": dominio_entry.get("note", ""),
                    "escala_min": escala["min"],
                    "escala_max": escala["max"],
                    "escala_labels": escala.get("labels", {}),
                    "thresholds_referencia_baixo_max": _decimal(thresholds["baixo_max"]),
                    "thresholds_referencia_moderado_max": _decimal(thresholds["moderado_max"]),
                    "referencia_media_nacional": _decimal(referencia["media"]) if referencia else None,
                    "referencia_desvio_padrao": _decimal(referencia["dp"]) if referencia else None,
                    "ordem": ordem_dominio,
                },
            )
            total_dominios += 1

            for ordem, item_entry in enumerate(dominio_entry["items"]):
                Item.objects.update_or_create(
                    dominio=dominio,
                    item_id=item_entry["id"],
                    defaults={
                        "texto": item_entry["text"],
                        "polaridade": item_entry["polarity"],
                        "evento_grave": item_entry.get("evento_grave", False),
                        "profundidade": item_entry.get("profundidade", ""),
                        "ordem": ordem,
                    },
                )
                total_itens += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{total_dominios} domínio(s)/subescala(s) e {total_itens} item(ns) importados "
                f'para "{instrumento.codigo}".'
            )
        )
