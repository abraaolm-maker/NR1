from django.contrib import admin, messages

from .models import PerfilProfissional, Relatorio
from .services.pdf import assinar_relatorio, gerar_pdf_relatorio


@admin.register(PerfilProfissional)
class PerfilProfissionalAdmin(admin.ModelAdmin):
    list_display = ("user", "titulo_profissional", "conselho", "numero_registro")
    search_fields = ("user__username", "user__first_name", "user__last_name", "numero_registro")


@admin.action(description="Gerar/atualizar PDF (minuta ou final conforme status)")
def gerar_pdf_selecionados(modeladmin, request, queryset):
    for relatorio in queryset:
        gerar_pdf_relatorio(relatorio.pk)
    modeladmin.message_user(request, f"PDF gerado para {queryset.count()} relatório(s).", messages.SUCCESS)


@admin.action(description="Assinar como usuário atual (registro interno — CLAUDE.md Seção 8.3)")
def assinar_selecionados(modeladmin, request, queryset):
    assinados, falhas = 0, []
    for relatorio in queryset:
        try:
            assinar_relatorio(relatorio.pk, request.user.pk)
            assinados += 1
        except ValueError as exc:
            falhas.append(str(exc))
    if assinados:
        modeladmin.message_user(request, f"{assinados} relatório(s) assinado(s).", messages.SUCCESS)
    for falha in falhas:
        modeladmin.message_user(request, falha, messages.ERROR)


@admin.register(Relatorio)
class RelatorioAdmin(admin.ModelAdmin):
    list_display = ("unidade", "periodo_inicio", "periodo_fim", "status", "gerado_em")
    list_filter = ("status", "unidade")
    filter_horizontal = ("aplicacoes",)
    actions = [gerar_pdf_selecionados, assinar_selecionados]
