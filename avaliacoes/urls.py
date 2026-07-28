from django.urls import path

from . import checklist_views, views

app_name = "avaliacoes"

urlpatterns = [
    path("responder/<uuid:aplicacao_token>/", views.responder_consentimento, name="responder_consentimento"),
    path("responder/<uuid:aplicacao_token>/perfil/", views.responder_perfil, name="responder_perfil"),
    path(
        "responder/<uuid:aplicacao_token>/perguntas-abertas/",
        views.responder_perguntas_abertas,
        name="responder_perguntas_abertas",
    ),
    path("responder/<uuid:aplicacao_token>/concluido/", views.responder_concluido, name="responder_concluido"),
    path(
        "responder/<uuid:aplicacao_token>/dominio/<str:dominio_codigo>/",
        views.responder_dominio,
        name="responder_dominio",
    ),
    # Checklist de triangulação (entrevista + observação) — gestores/liderança da
    # empresa cliente, via link próprio (CLAUDE.md Seção 6.11).
    path("checklist/<uuid:token>/", checklist_views.checklist_identificacao, name="checklist_identificacao"),
    path(
        "checklist/<uuid:token>/concluido/",
        checklist_views.checklist_concluido,
        name="checklist_concluido",
    ),
    path(
        "checklist/<uuid:token>/<str:tipo>/",
        checklist_views.checklist_grupo,
        name="checklist_grupo",
    ),
]
