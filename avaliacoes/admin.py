from django.contrib import admin

from .models import (
    GHE,
    Aplicacao,
    CatalogoAcao,
    ClassificacaoRisco,
    ColetaChecklistTriangulacao,
    CriterioVersao,
    EscoreDominio,
    EscoreRespondente,
    Empresa,
    Funcao,
    IndicadorIndireto,
    ItemChecklistTriangulacao,
    Perigo,
    PerigoIdentificado,
    PlanoDeAcao,
    RegistroErgonomico,
    RespondenteChecklistTriangulacao,
    RespostaChecklistTriangulacao,
    Resposta,
    Respondente,
    Unidade,
)


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ("nome", "cnpj", "criado_em")
    search_fields = ("nome", "cnpj")


@admin.register(Unidade)
class UnidadeAdmin(admin.ModelAdmin):
    list_display = ("nome", "empresa", "cnpj")
    list_filter = ("empresa",)
    search_fields = ("nome", "cnpj")


@admin.register(Funcao)
class FuncaoAdmin(admin.ModelAdmin):
    list_display = ("nome", "unidade")
    list_filter = ("unidade",)


@admin.register(GHE)
class GHEAdmin(admin.ModelAdmin):
    list_display = ("nome", "unidade", "setor")
    list_filter = ("unidade",)
    filter_horizontal = ("funcoes",)


@admin.register(RegistroErgonomico)
class RegistroErgonomicoAdmin(admin.ModelAdmin):
    list_display = ("ghe", "tipo", "data_registro", "responsavel_tecnico")
    list_filter = ("tipo", "ghe")


@admin.register(Perigo)
class PerigoAdmin(admin.ModelAdmin):
    list_display = ("nome", "categoria")
    search_fields = ("nome", "categoria")


@admin.register(PerigoIdentificado)
class PerigoIdentificadoAdmin(admin.ModelAdmin):
    list_display = ("ghe", "perigo", "identificado_em", "identificado_por")
    list_filter = ("ghe",)


@admin.register(ItemChecklistTriangulacao)
class ItemChecklistTriangulacaoAdmin(admin.ModelAdmin):
    list_display = ("tipo", "ordem", "texto", "dominio_codigo_relacionado")
    list_filter = ("tipo",)


@admin.register(ColetaChecklistTriangulacao)
class ColetaChecklistTriangulacaoAdmin(admin.ModelAdmin):
    list_display = ("aplicacao", "status", "token", "criado_por", "criado_em", "encerrada_em")
    list_filter = ("status",)


@admin.register(RespondenteChecklistTriangulacao)
class RespondenteChecklistTriangulacaoAdmin(admin.ModelAdmin):
    list_display = ("nome", "cargo", "coleta", "criado_em", "concluido_em")
    list_filter = ("coleta__aplicacao",)


@admin.register(RespostaChecklistTriangulacao)
class RespostaChecklistTriangulacaoAdmin(admin.ModelAdmin):
    list_display = ("respondente", "item", "conformidade", "respondido_em")
    list_filter = ("conformidade", "item__tipo")


@admin.register(IndicadorIndireto)
class IndicadorIndiretoAdmin(admin.ModelAdmin):
    list_display = ("ghe", "tipo", "periodo_referencia", "dominio_relacionado", "convergente")
    list_filter = ("tipo", "convergente", "ghe")


@admin.register(CriterioVersao)
class CriterioVersaoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "ativo", "status", "criado_em")
    list_filter = ("ativo", "status")


class RespondenteInline(admin.TabularInline):
    """Somente leitura: Respondente nasce sob demanda quando alguém abre o link único
    da Aplicacao (CLAUDE.md Seção 6.7), não é mais pré-criado pelo gestor."""

    model = Respondente
    extra = 0
    can_delete = False
    fields = (
        "alias_anonimo",
        "funcao",
        "tempo_na_organizacao",
        "modalidade_trabalho",
        "consentimento_aceito_em",
        "concluido_em",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Aplicacao)
class AplicacaoAdmin(admin.ModelAdmin):
    list_display = ("ghe", "instrumento", "tipo", "status", "data_aplicacao", "criterio_versao", "alertas_d9")
    list_filter = ("instrumento", "tipo", "status")
    readonly_fields = ("token",)
    inlines = [RespondenteInline]


@admin.register(Respondente)
class RespondenteAdmin(admin.ModelAdmin):
    list_display = (
        "alias_anonimo",
        "aplicacao",
        "funcao",
        "tempo_na_organizacao",
        "modalidade_trabalho",
        "consentimento_aceito_em",
        "concluido_em",
    )
    list_filter = ("aplicacao__ghe", "tempo_na_organizacao", "modalidade_trabalho")


@admin.register(Resposta)
class RespostaAdmin(admin.ModelAdmin):
    list_display = ("respondente", "item", "valor_bruto", "respondido_em")
    list_filter = ("item__dominio",)


@admin.register(EscoreRespondente)
class EscoreRespondenteAdmin(admin.ModelAdmin):
    list_display = ("respondente", "dominio", "escore", "classificacao")
    list_filter = ("classificacao", "dominio")


@admin.register(EscoreDominio)
class EscoreDominioAdmin(admin.ModelAdmin):
    list_display = (
        "aplicacao",
        "dominio",
        "escore",
        "classificacao",
        "n_respondentes",
        "suprimido_por_confidencialidade",
    )
    list_filter = ("classificacao", "suprimido_por_confidencialidade")


@admin.register(ClassificacaoRisco)
class ClassificacaoRiscoAdmin(admin.ModelAdmin):
    list_display = ("escore_dominio", "banda", "probabilidade", "score", "prazo_dias_plano_de_acao")
    list_filter = ("banda",)


@admin.register(PlanoDeAcao)
class PlanoDeAcaoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "classificacao_risco", "hierarquia", "responsavel", "prazo", "status")
    list_filter = ("status", "hierarquia")
    search_fields = ("codigo", "medida", "responsavel")


@admin.register(CatalogoAcao)
class CatalogoAcaoAdmin(admin.ModelAdmin):
    list_display = ("dominio", "nivel", "hierarquia")
    list_filter = ("nivel", "hierarquia", "dominio__instrumento")
