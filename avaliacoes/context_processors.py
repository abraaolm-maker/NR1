"""Injeta o papel do usuário logado (admin x gestor de empresa) em todo template do
painel — evita repetir `eh_admin(request.user)` em cada view só pra decidir o que
mostrar na navegação (CLAUDE.md Seção 6.8)."""

from .services.tenancy import eh_admin, empresa_do_usuario


def tenancy(request):
    if not request.user.is_authenticated:
        return {}
    return {
        "eh_admin": eh_admin(request.user),
        "empresa_do_usuario": empresa_do_usuario(request.user),
    }
