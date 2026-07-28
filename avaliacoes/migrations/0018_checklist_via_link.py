# Checklist de triangulação vira questionário via link (CLAUDE.md Seção 6.11) —
# escrita manualmente (não via makemigrations) porque remover o FK direto `aplicacao`
# de RespostaChecklistTriangulacao para trocar por `respondente` exigiria um default
# interativo; a tabela está vazia em desenvolvimento (só dados de teste, Seção 0).

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("avaliacoes", "0017_itemchecklisttriangulacao_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ColetaChecklistTriangulacao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("aberta", "Aberta"), ("encerrada", "Encerrada")],
                        default="aberta",
                        max_length=15,
                    ),
                ),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("encerrada_em", models.DateTimeField(blank=True, null=True)),
                (
                    "aplicacao",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="coletas_checklist",
                        to="avaliacoes.aplicacao",
                    ),
                ),
                (
                    "criado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="RespondenteChecklistTriangulacao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=200)),
                ("cargo", models.CharField(blank=True, max_length=200)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("concluido_em", models.DateTimeField(blank=True, null=True)),
                (
                    "coleta",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="respondentes",
                        to="avaliacoes.coletachecklisttriangulacao",
                    ),
                ),
            ],
        ),
        migrations.RemoveConstraint(
            model_name="respostachecklisttriangulacao",
            name="uniq_checklist_por_aplicacao_item",
        ),
        migrations.RemoveField(
            model_name="respostachecklisttriangulacao",
            name="aplicacao",
        ),
        migrations.RemoveField(
            model_name="respostachecklisttriangulacao",
            name="respondido_por",
        ),
        migrations.AddField(
            model_name="respostachecklisttriangulacao",
            name="respondente",
            field=models.ForeignKey(
                default=None,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="respostas",
                to="avaliacoes.respondentechecklisttriangulacao",
            ),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="respostachecklisttriangulacao",
            constraint=models.UniqueConstraint(
                fields=("respondente", "item"), name="uniq_checklist_por_respondente_item"
            ),
        ),
    ]
