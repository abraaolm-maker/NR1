from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .models import ChaveApiClaude, PerfilProfissional, Relatorio
from .services.pdf import assinar_relatorio, gerar_pdf_relatorio

User = get_user_model()


@admin.register(ChaveApiClaude)
class ChaveApiClaudeAdmin(admin.ModelAdmin):
    """Só leitura/toggle de `ativa` — o cadastro (que grava o valor bruto no
    `.env.local`) só acontece pelo painel (`painel_relatorios:chaves_api_create`),
    nunca por aqui, pra não abrir um segundo caminho que exponha o valor completo."""

    list_display = ("nome", "prefixo", "sufixo", "ativa", "criada_por", "criada_em")
    list_filter = ("ativa",)
    readonly_fields = ("nome", "prefixo", "sufixo", "criada_por", "criada_em")

    def has_add_permission(self, request):
        return False


@admin.register(PerfilProfissional)
class PerfilProfissionalAdmin(admin.ModelAdmin):
    list_display = ("user", "titulo_profissional", "conselho", "numero_registro")
    search_fields = ("user__username", "user__first_name", "user__last_name", "numero_registro")
    fields = ("user", "titulo_profissional", "conselho", "numero_registro", "assinatura_imagem")


class PerfilProfissionalInline(admin.StackedInline):
    """Pedido do usuário em 2026-08-06: cadastrar a assinatura (PNG) direto na tela
    do usuário no Admin, sem precisar navegar até um cadastro separado de
    PerfilProfissional."""

    model = PerfilProfissional
    can_delete = False
    fk_name = "user"
    fields = ("titulo_profissional", "conselho", "numero_registro", "assinatura_imagem")


class CustomUserAdmin(UserAdmin):
    inlines = (PerfilProfissionalInline,)


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


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
