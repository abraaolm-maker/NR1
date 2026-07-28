from functools import wraps

from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied


def gestor_required(view_func):
    """staff_member_required() usa login_url='admin:login' por padrão — redireciona
    pro login do Django Admin, não pro /painel/entrar/ deste painel. Este wrapper
    corrige isso; usar em toda view do painel acessível tanto pro admin quanto pro
    gestor de uma empresa (CLAUDE.md Seção 6.8) — views que dependem do escopo de
    tenancy ainda precisam filtrar por `avaliacoes.services.tenancy.empresas_visiveis`."""
    return staff_member_required(view_func, login_url="painel_login")


def admin_required(view_func):
    """Só a equipe do SaaS (`is_superuser=True`) — onboarding de Empresa/Gestor,
    parecer da IA e assinatura do relatório (CLAUDE.md Seção 6.8, decisão do usuário:
    "só faz sentido o profissional do SaaS"). Um gestor de empresa autenticado que
    tentar acessar recebe 403 (PermissionDenied), não um redirect pra tela de login
    — ele já está logado, só não tem essa permissão."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied("Esta área é restrita à equipe responsável pelo sistema.")
        return view_func(request, *args, **kwargs)

    return gestor_required(_wrapped)
