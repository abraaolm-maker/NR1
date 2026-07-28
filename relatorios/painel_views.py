"""Painel do gestor (fora do Django Admin) — CLAUDE.md Seção 6.1, decisão de 2026-07-17.

Criação de Relatorio, revisão/edição do parecer da IA, geração de PDF e assinatura.
"gerar parecer via IA" chama a API real da Anthropic (sem client injetado) — se
ANTHROPIC_API_KEY não estiver configurada, a falha é capturada e mostrada como
mensagem, não como erro 500."""

import json

from django.contrib import messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from avaliacoes.decorators import admin_required, gestor_required
from avaliacoes.models import Aplicacao, StatusAplicacao, Unidade
from avaliacoes.services.tenancy import empresas_visiveis

from .forms import ParecerJSONForm, PerfilProfissionalForm, RelatorioForm
from .models import PerfilProfissional, Relatorio, StatusRelatorio
from .services.analise_ia import gerar_e_salvar_parecer
from .services.parecer_form import contar_linhas_renderizadas, linhas_para_template, montar_parecer_do_post
from .services.pdf import assinar_relatorio, gerar_pdf_relatorio


@gestor_required
def painel_home(request):
    """Página inicial do painel — compartilhada entre admin e gestor de empresa,
    cada um só vê os dados da(s) empresa(s) que `empresas_visiveis` libera (CLAUDE.md
    Seção 6.8). Antes disso a landing page era a lista de empresas, sem nenhum
    indicador do que precisa de atenção (achado no teste de UX, 2026-07-17)."""
    empresas = empresas_visiveis(request.user)
    aplicacoes_em_andamento = (
        Aplicacao.objects.filter(status=StatusAplicacao.EM_ANDAMENTO, ghe__unidade__empresa__in=empresas)
        .select_related("ghe__unidade__empresa", "instrumento")
        .order_by("-criado_em")
    )
    aplicacoes_prontas_para_relatorio = (
        Aplicacao.objects.filter(
            status=StatusAplicacao.CONCLUIDA, ghe__unidade__empresa__in=empresas, relatorios__isnull=True
        )
        .select_related("ghe__unidade__empresa", "instrumento")
        .order_by("-concluida_em")
    )
    relatorios_pendentes = (
        Relatorio.objects.exclude(status=StatusRelatorio.ASSINADO)
        .filter(unidade__empresa__in=empresas)
        .select_related("unidade__empresa")
        .order_by("-gerado_em")
    )
    return render(
        request,
        "painel/home.html",
        {
            "total_empresas": empresas.count(),
            "aplicacoes_em_andamento": aplicacoes_em_andamento,
            "aplicacoes_prontas_para_relatorio": aplicacoes_prontas_para_relatorio,
            "relatorios_pendentes": relatorios_pendentes,
        },
    )


@admin_required
def relatorio_list(request):
    relatorios = Relatorio.objects.select_related("unidade__empresa").order_by("-gerado_em")
    aplicacoes_prontas = (
        Aplicacao.objects.filter(status=StatusAplicacao.CONCLUIDA, relatorios__isnull=True)
        .select_related("ghe__unidade__empresa")
        .order_by("-concluida_em")
    )
    return render(
        request,
        "painel/relatorio_list.html",
        {"relatorios": relatorios, "aplicacoes_prontas": aplicacoes_prontas},
    )


@admin_required
def relatorio_create(request, unidade_id):
    unidade = get_object_or_404(Unidade, pk=unidade_id)

    if not Aplicacao.objects.filter(ghe__unidade=unidade).exists():
        # Sem isso, o campo "Aplicações" nasce obrigatório mas sem nenhuma opção pra
        # marcar — beco sem saída com erro de validação mal posicionado (achado no
        # teste de UX, 2026-07-17). Corta o problema na raiz antes de chegar no form.
        return render(request, "painel/relatorio_sem_aplicacoes.html", {"unidade": unidade})

    relatorio_criado = None

    if request.method == "POST":
        form = RelatorioForm(request.POST, unidade=unidade)
        if form.is_valid():
            try:
                with transaction.atomic():
                    relatorio_criado = form.save(commit=False)
                    relatorio_criado.unidade = unidade
                    relatorio_criado.save()
                    form.save_m2m()
            except DjangoValidationError as exc:
                form.add_error(None, exc)
                relatorio_criado = None
            if relatorio_criado is not None:
                messages.success(request, "Relatório criado.")
                return redirect("painel_relatorios:relatorio_detail", pk=relatorio_criado.pk)
    else:
        form = RelatorioForm(unidade=unidade)

    return render(request, "painel/relatorio_form.html", {"form": form, "unidade": unidade})


@admin_required
def relatorio_detail(request, pk):
    relatorio = get_object_or_404(
        Relatorio.objects.select_related("unidade__empresa", "criterio_versao", "assinado_por"), pk=pk
    )
    aplicacoes = relatorio.aplicacoes.select_related("ghe").all()
    tem_perfil = hasattr(request.user, "perfil_profissional")

    # Stepper do fluxo (achado no diagnóstico de UX de 2026-07-28: nada no painel
    # mostrava em que etapa o relatório estava, nem impedia pular etapas).
    etapa_parecer = bool(relatorio.parecer_ia)
    etapa_pdf = bool(relatorio.pdf_path)
    etapa_assinatura = relatorio.status == StatusRelatorio.ASSINADO
    etapas = [
        {"nome": "Diagnósticos", "concluida": True, "atual": False},
        {"nome": "Parecer técnico", "concluida": etapa_parecer, "atual": not etapa_parecer},
        {"nome": "PDF", "concluida": etapa_pdf, "atual": etapa_parecer and not etapa_pdf},
        {
            "nome": "Assinatura",
            "concluida": etapa_assinatura,
            "atual": etapa_parecer and etapa_pdf and not etapa_assinatura,
        },
    ]

    return render(
        request,
        "painel/relatorio_detail.html",
        {
            "relatorio": relatorio,
            "aplicacoes": aplicacoes,
            "tem_perfil": tem_perfil,
            "etapas": etapas,
            "etapa_parecer": etapa_parecer,
            "etapa_pdf": etapa_pdf,
        },
    )


@admin_required
def relatorio_parecer_editar(request, pk):
    """Formulário estruturado por campo (achado no diagnóstico de UX de 2026-07-28:
    editar como JSON cru era inutilizável — um erro de vírgula quebrava tudo). Sem
    JavaScript: sempre mostra as linhas já existentes + 3 em branco por lista, pra
    dar espaço de adicionar itens novos. O modo "JSON avançado" continua disponível
    pra quem preferir colar a saída bruta da IA."""
    relatorio = get_object_or_404(Relatorio, pk=pk)
    parecer_atual = relatorio.parecer_ia or {}
    contagem = contar_linhas_renderizadas(parecer_atual)

    if request.method == "POST":
        if request.POST.get("modo") == "json":
            form_json = ParecerJSONForm(request.POST)
            if form_json.is_valid():
                relatorio.parecer_ia = form_json.cleaned_data["parecer_json"]
                relatorio.save(update_fields=["parecer_ia"])
                messages.success(request, "Parecer atualizado.")
                return redirect("painel_relatorios:relatorio_detail", pk=relatorio.pk)
            messages.error(request, "JSON inválido — corrija e envie novamente.")
        else:
            novo_parecer = montar_parecer_do_post(request.POST, contagem)
            novo_parecer["sintese_executiva"] = novo_parecer["sintese_executiva"] or ""
            relatorio.parecer_ia = novo_parecer
            relatorio.save(update_fields=["parecer_ia"])
            messages.success(request, "Parecer atualizado.")
            return redirect("painel_relatorios:relatorio_detail", pk=relatorio.pk)

    inicial_json = json.dumps(parecer_atual, ensure_ascii=False, indent=2)
    form_json = ParecerJSONForm(initial={"parecer_json": inicial_json})

    return render(
        request,
        "painel/relatorio_parecer_form.html",
        {
            "relatorio": relatorio,
            "parecer": parecer_atual,
            "linhas": linhas_para_template(parecer_atual),
            "form_json": form_json,
        },
    )


@admin_required
def relatorio_gerar_parecer_ia(request, pk):
    if request.method != "POST":
        return redirect("painel_relatorios:relatorio_detail", pk=pk)
    try:
        gerar_e_salvar_parecer(pk)
        messages.success(request, "Parecer gerado via IA.")
    except Exception as exc:  # SDK da Anthropic, chave ausente, rede, etc.
        messages.error(request, f"Não foi possível gerar o parecer via IA: {exc}")
    return redirect("painel_relatorios:relatorio_detail", pk=pk)


@admin_required
def relatorio_gerar_pdf(request, pk):
    if request.method != "POST":
        return redirect("painel_relatorios:relatorio_detail", pk=pk)
    gerar_pdf_relatorio(pk)
    messages.success(request, "PDF gerado/atualizado.")
    return redirect("painel_relatorios:relatorio_detail", pk=pk)


@admin_required
def relatorio_assinar(request, pk):
    if request.method != "POST":
        return redirect("painel_relatorios:relatorio_detail", pk=pk)
    try:
        assinar_relatorio(pk, request.user.pk)
        messages.success(request, "Relatório assinado.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("painel_relatorios:relatorio_detail", pk=pk)


@admin_required
def meu_perfil(request):
    perfil = PerfilProfissional.objects.filter(user=request.user).first()

    if request.method == "POST":
        form = PerfilProfissionalForm(request.POST, instance=perfil)
        if form.is_valid():
            perfil = form.save(commit=False)
            perfil.user = request.user
            perfil.save()
            messages.success(request, "Perfil profissional atualizado.")
            return redirect("painel_relatorios:meu_perfil")
    else:
        form = PerfilProfissionalForm(instance=perfil)

    return render(request, "painel/perfil_profissional_form.html", {"form": form, "perfil": perfil})
