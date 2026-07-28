from django.contrib import admin

from .models import Dominio, Instrumento, Item


class ItemInline(admin.TabularInline):
    model = Item
    extra = 0


@admin.register(Instrumento)
class InstrumentoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nome", "criado_em")
    search_fields = ("codigo", "nome")


@admin.register(Dominio)
class DominioAdmin(admin.ModelAdmin):
    list_display = ("instrumento", "codigo", "nome", "escala_min", "escala_max")
    list_filter = ("instrumento",)
    search_fields = ("codigo", "nome")
    inlines = [ItemInline]


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("item_id", "dominio", "polaridade", "evento_grave")
    list_filter = ("dominio__instrumento", "polaridade", "evento_grave")
    search_fields = ("item_id", "texto")
