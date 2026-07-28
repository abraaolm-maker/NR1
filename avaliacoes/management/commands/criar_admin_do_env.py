"""Cria (ou atualiza a senha de) um superusuário a partir de variáveis de ambiente,
pra automatizar o primeiro deploy em nuvem sem precisar de um shell interativo. Nunca
grava a senha em código — ela só existe como env var configurada no painel do Render.
Idempotente: rodar de novo com as mesmas variáveis não duplica nem falha."""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Cria/atualiza o superusuário admin a partir de DJANGO_ADMIN_USER/DJANGO_ADMIN_PASSWORD."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_ADMIN_USER")
        password = os.environ.get("DJANGO_ADMIN_PASSWORD")

        if not username or not password:
            self.stdout.write(
                self.style.WARNING(
                    "DJANGO_ADMIN_USER/DJANGO_ADMIN_PASSWORD não definidos — nenhum admin criado."
                )
            )
            return

        User = get_user_model()
        user, criado = User.objects.get_or_create(
            username=username, defaults={"is_staff": True, "is_superuser": True}
        )
        user.set_password(password)
        user.is_staff = True
        user.is_superuser = True
        user.save()

        acao = "criado" if criado else "atualizado"
        self.stdout.write(self.style.SUCCESS(f"Superusuário '{username}' {acao}."))
