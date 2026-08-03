"""
URL configuration for crarp project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, re_path
from django.views.static import serve as serve_static

urlpatterns = [
    path('admin/', admin.site.urls),
    # Painel do gestor (fora do Admin) — CLAUDE.md Seção 6.1.
    path(
        'painel/entrar/',
        auth_views.LoginView.as_view(template_name='painel/login.html', redirect_authenticated_user=True),
        name='painel_login',
    ),
    path('painel/sair/', auth_views.LogoutView.as_view(), name='painel_logout'),
    path('painel/', include('avaliacoes.painel_urls')),
    path('painel/', include('relatorios.painel_urls')),
    # Questionário público (respondentes, sem login).
    path('', include('avaliacoes.urls')),
]

# Servir /media/ direto pelo Django mesmo com DEBUG=False: os PDFs de relatório são
# gerados em runtime (WeasyPrint), então o WhiteNoise (que só serve STATIC_URL,
# coletado no build) não os enxerga. `django.conf.urls.static.static()` NÃO serve pra
# isso — ele só registra a rota quando DEBUG=True, então em produção (DEBUG=False,
# nosso caso real) ela nunca existia e todo PDF dava 404 (achado em 2026-08-03,
# testado no deploy do VPS). `re_path` com `django.views.static.serve` direto ignora
# esse comportamento e funciona independente de DEBUG. Para o volume baixo deste
# ambiente de teste isso é aceitável; se o tráfego crescer, mover para um storage
# externo (S3 etc.) em vez de servir arquivos direto do processo Django.
urlpatterns += [
    re_path(
        r'^%s(?P<path>.*)$' % settings.MEDIA_URL.lstrip('/'),
        serve_static,
        {'document_root': settings.MEDIA_ROOT},
    ),
]
