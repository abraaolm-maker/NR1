from django.urls import path

from . import painel_views

app_name = "painel_relatorios"

urlpatterns = [
    path("", painel_views.painel_home, name="home"),
    path("relatorios/", painel_views.relatorio_list, name="relatorio_list"),
    path(
        "unidades/<int:unidade_id>/relatorios/novo/",
        painel_views.relatorio_create,
        name="relatorio_create",
    ),
    path("relatorios/<int:pk>/", painel_views.relatorio_detail, name="relatorio_detail"),
    path(
        "relatorios/<int:pk>/parecer/",
        painel_views.relatorio_parecer_editar,
        name="relatorio_parecer_editar",
    ),
    path(
        "relatorios/<int:pk>/gerar-parecer-ia/",
        painel_views.relatorio_gerar_parecer_ia,
        name="relatorio_gerar_parecer_ia",
    ),
    path(
        "relatorios/<int:pk>/refinar-planos-ia/",
        painel_views.relatorio_refinar_planos_ia,
        name="relatorio_refinar_planos_ia",
    ),
    path("relatorios/<int:pk>/gerar-pdf/", painel_views.relatorio_gerar_pdf, name="relatorio_gerar_pdf"),
    path("relatorios/<int:pk>/assinar/", painel_views.relatorio_assinar, name="relatorio_assinar"),
    path("chaves-api/", painel_views.chaves_api_list, name="chaves_api_list"),
    path("chaves-api/nova/", painel_views.chaves_api_create, name="chaves_api_create"),
    path("chaves-api/<int:pk>/ativar/", painel_views.chaves_api_ativar, name="chaves_api_ativar"),
    path("chaves-api/<int:pk>/remover/", painel_views.chaves_api_remover, name="chaves_api_remover"),
    path("meu-perfil/", painel_views.meu_perfil, name="meu_perfil"),
]
