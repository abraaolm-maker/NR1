from django.urls import path

from . import painel_views

app_name = "painel_avaliacoes"

urlpatterns = [
    path("empresas/", painel_views.empresa_list, name="empresa_list"),
    path("empresas/nova/", painel_views.empresa_create, name="empresa_create"),
    path("empresas/<int:pk>/", painel_views.empresa_detail, name="empresa_detail"),
    path("empresas/<int:pk>/editar/", painel_views.empresa_update, name="empresa_update"),
    path("empresas/<int:pk>/criar-gestor/", painel_views.empresa_criar_gestor, name="empresa_criar_gestor"),
    path("empresas/<int:pk>/editar-gestor/", painel_views.empresa_editar_gestor, name="empresa_editar_gestor"),
    path("empresas/<int:pk>/remover-gestor/", painel_views.empresa_remover_gestor, name="empresa_remover_gestor"),
    path("empresas/<int:empresa_id>/unidades/nova/", painel_views.unidade_create, name="unidade_create"),
    path("unidades/<int:pk>/", painel_views.unidade_detail, name="unidade_detail"),
    path("unidades/<int:pk>/editar/", painel_views.unidade_update, name="unidade_update"),
    path("unidades/<int:pk>/alertas-agregados/", painel_views.alertas_agregados, name="alertas_agregados"),
    path("unidades/<int:pk>/semaforo-riscos/", painel_views.semaforo_riscos, name="semaforo_riscos"),
    path("unidades/<int:unidade_id>/funcoes/nova/", painel_views.funcao_create, name="funcao_create"),
    path("unidades/<int:unidade_id>/ghes/novo/", painel_views.ghe_create, name="ghe_create"),
    path("ghes/<int:pk>/", painel_views.ghe_detail, name="ghe_detail"),
    path("ghes/<int:pk>/editar/", painel_views.ghe_update, name="ghe_update"),
    path(
        "ghes/<int:ghe_id>/indicadores-indiretos/",
        painel_views.indicadores_indiretos,
        name="indicadores_indiretos",
    ),
    path("ghes/<int:ghe_id>/aplicacoes/nova/", painel_views.aplicacao_create, name="aplicacao_create"),
    path("aplicacoes/<int:pk>/", painel_views.aplicacao_detail, name="aplicacao_detail"),
    path("aplicacoes/<int:pk>/editar/", painel_views.aplicacao_update, name="aplicacao_update"),
    path(
        "aplicacoes/<int:pk>/encerrar-coleta/",
        painel_views.aplicacao_encerrar_coleta,
        name="aplicacao_encerrar_coleta",
    ),
    path(
        "aplicacoes/<int:pk>/pontuacao-anonima/",
        painel_views.pontuacao_anonima,
        name="pontuacao_anonima",
    ),
    path(
        "aplicacoes/<int:pk>/diagnostico-ghe/",
        painel_views.diagnostico_ghe_view,
        name="diagnostico_ghe",
    ),
    path("catalogo-acoes/", painel_views.catalogo_acoes_list, name="catalogo_acoes_list"),
    path("catalogo-acoes/<int:pk>/editar/", painel_views.catalogo_acoes_update, name="catalogo_acoes_update"),
    path("planos-de-acao/<int:pk>/editar/", painel_views.plano_de_acao_update, name="plano_de_acao_update"),
    path(
        "aplicacoes/<int:pk>/checklist-triangulacao/",
        painel_views.checklist_triangulacao,
        name="checklist_triangulacao",
    ),
    path(
        "aplicacoes/<int:pk>/checklist-triangulacao/abrir/",
        painel_views.checklist_abrir_coleta,
        name="checklist_abrir_coleta",
    ),
    path(
        "aplicacoes/<int:pk>/checklist-triangulacao/encerrar/",
        painel_views.checklist_encerrar_coleta,
        name="checklist_encerrar_coleta",
    ),
    path("minha-empresa/relatorios/", painel_views.relatorios_empresa, name="relatorios_empresa"),
    path("minha-empresa/analise-ia/", painel_views.analise_ia_empresa, name="analise_ia_empresa"),
    path("configuracoes-risco/", painel_views.configuracoes_risco_list, name="configuracoes_risco"),
    path("configuracoes-risco/nova/", painel_views.configuracoes_risco_create, name="configuracoes_risco_create"),
    path(
        "configuracoes-risco/<int:pk>/",
        painel_views.configuracoes_risco_detail,
        name="configuracoes_risco_detail",
    ),
    path(
        "configuracoes-risco/<int:pk>/ratificar/",
        painel_views.configuracoes_risco_ratificar,
        name="configuracoes_risco_ratificar",
    ),
]
