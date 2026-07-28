"""Separação admin (equipe do SaaS) x empresa cliente (CLAUDE.md Seção 6.8).

Admin = `is_superuser=True`, enxerga todas as empresas — é quem faz o onboarding
(cria Empresa, cria o acesso do gestor) e quem opera os módulos que ainda pertencem
só à equipe técnica (parecer da IA, assinatura do relatório). Gestor de empresa =
usuário comum (`is_staff=True`, não superuser) ligado a exatamente uma Empresa via
`Empresa.gestor` — só enxerga a própria empresa."""

from avaliacoes.models import Empresa


def eh_admin(user) -> bool:
    return bool(user.is_authenticated and user.is_superuser)


def empresa_do_usuario(user) -> Empresa | None:
    return getattr(user, "empresa_gerenciada", None)


def empresas_visiveis(user):
    """Queryset de Empresa que este usuário pode enxergar: todas (admin) ou só a
    própria (gestor de empresa, ou nenhuma se ainda não tiver empresa vinculada)."""
    if eh_admin(user):
        return Empresa.objects.all()
    empresa = empresa_do_usuario(user)
    if empresa is None:
        return Empresa.objects.none()
    return Empresa.objects.filter(pk=empresa.pk)
