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
from avaliacoes.models import Aplicacao, PlanoDeAcao, StatusAplicacao, Unidade
from avaliacoes.services.calculo_risco import BANDA_ORDEM
from avaliacoes.services.tenancy import empresas_visiveis

from .forms import ChaveApiClaudeForm, ParecerJSONForm, PerfilProfissionalForm, RelatorioForm
from .models import ChaveApiClaude, PerfilProfissional, Relatorio, StatusRelatorio, TipoRelatorio
from .services.analise_ia import gerar_e_salvar_parecer
from .services.plano_acao_ia import gerar_e_salvar_planos_refinados
from .services.chaves_api import (
    chave_precisa_reverificacao,
    definir_chave_ativa,
    remover_chave,
    salvar_chave,
    verificar_chave,
)
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
    #
    # Bug corrigido em 2026-07-29 (achado pelo usuário, print do card com ícones
    # verdes): `etapa_pdf` marcava a etapa 3 como concluída só por existir um
    # `pdf_path`, mesmo sem nenhum parecer gerado — um PDF gerado antes do parecer
    # existir aparecia com ✓ verde igual a um PDF de verdade completo, confundindo
    # a hierarquia visual do fluxo. Agora só conta como concluída quando o PDF
    # existe E reflete um parecer já gerado; um PDF "órfão" (sem parecer) aparece
    # como pendente/desatualizado (`pdf_desatualizado`), não como concluído.
    etapa_parecer = bool(relatorio.parecer_ia)
    pdf_existe = bool(relatorio.pdf_path)
    etapa_pdf = etapa_parecer and pdf_existe
    pdf_desatualizado = pdf_existe and not etapa_parecer
    etapa_assinatura = relatorio.status == StatusRelatorio.ASSINADO

    # Pedido do usuário em 2026-08-04: só liberar "Gerar PDF" pro tipo Diagnóstico +
    # Plano de Ação depois de rodar OBRIGATORIAMENTE os dois botões de IA — sem isso o
    # documento sairia com parecer vazio e/ou medida genérica do catálogo sem avisar.
    etapa_planos_refinados = bool(relatorio.planos_refinados_em)
    exige_planos_refinados = relatorio.tipo == TipoRelatorio.DIAGNOSTICO_PLANO_ACAO
    pode_gerar_pdf = etapa_parecer and (etapa_planos_refinados or not exige_planos_refinados)

    etapas = [
        {"nome": "Diagnósticos", "concluida": True, "atual": False, "ancora": "#secao-tipo"},
        {
            "nome": "Parecer técnico",
            "concluida": etapa_parecer,
            "atual": not etapa_parecer,
            "ancora": "#secao-parecer",
        },
    ]
    if exige_planos_refinados:
        etapas.append(
            {
                "nome": "Refinar planos de ação",
                "concluida": etapa_planos_refinados,
                "atual": etapa_parecer and not etapa_planos_refinados,
                "ancora": "#secao-planos",
            }
        )
    etapas.append(
        {"nome": "PDF", "concluida": etapa_pdf, "atual": pode_gerar_pdf and not etapa_pdf, "ancora": "#secao-pdf"}
    )
    etapas.append(
        {
            "nome": "Assinatura",
            "concluida": etapa_assinatura,
            "atual": etapa_pdf and not etapa_assinatura,
            "ancora": "#secao-pdf",
        }
    )

    # Planos de ação de todas as Aplicações deste relatório, do mais urgente pro
    # menos urgente — mesma ordenação usada no PDF (relatorios/services/pdf.py::
    # _planos_ordenados) e na tela da Aplicação (achado de 2026-07-29).
    planos_de_acao = sorted(
        PlanoDeAcao.objects.filter(
            classificacao_risco__escore_dominio__aplicacao__in=aplicacoes
        ).select_related("classificacao_risco__escore_dominio__dominio", "classificacao_risco__escore_dominio__aplicacao__ghe"),
        key=lambda p: BANDA_ORDEM.get(p.classificacao_risco.banda, 0),
        reverse=True,
    )

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
            "etapa_planos_refinados": etapa_planos_refinados,
            "exige_planos_refinados": exige_planos_refinados,
            "pode_gerar_pdf": pode_gerar_pdf,
            "pdf_desatualizado": pdf_desatualizado,
            "planos_de_acao": planos_de_acao,
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
def relatorio_refinar_planos_ia(request, pk):
    if request.method != "POST":
        return redirect("painel_relatorios:relatorio_detail", pk=pk)
    try:
        atualizados = gerar_e_salvar_planos_refinados(pk)
        messages.success(request, f"{atualizados} plano(s) de ação refinado(s) via IA.")
    except Exception as exc:  # SDK da Anthropic, chave ausente, rede, etc.
        messages.error(request, f"Não foi possível refinar os planos de ação via IA: {exc}")
    return redirect("painel_relatorios:relatorio_detail", pk=pk)


@admin_required
def relatorio_gerar_pdf(request, pk):
    if request.method != "POST":
        return redirect("painel_relatorios:relatorio_detail", pk=pk)
    try:
        gerar_pdf_relatorio(pk)
        messages.success(request, "PDF gerado/atualizado.")
    except ValueError as exc:
        messages.error(request, str(exc))
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
def chaves_api_list(request):
    """Reverifica automaticamente (contra `client.models.list()`, sem custo de
    tokens) qualquer chave nunca checada ou checada há mais de 1 dia — assim a
    coluna "Válida" nunca fica desatualizada por muito tempo, sem precisar de uma
    tarefa agendada separada."""
    chaves = list(ChaveApiClaude.objects.select_related("criada_por").all())
    for chave in chaves:
        if chave_precisa_reverificacao(chave):
            verificar_chave(chave)
    return render(request, "painel/chaves_api_list.html", {"chaves": chaves})


@admin_required
def chaves_api_create(request):
    if request.method == "POST":
        form = ChaveApiClaudeForm(request.POST)
        if form.is_valid():
            try:
                chave = salvar_chave(
                    form.cleaned_data["nome"], form.cleaned_data["valor"], request.user
                )
            except ValueError as exc:
                form.add_error("valor", str(exc))
            else:
                if not ChaveApiClaude.objects.exclude(pk=chave.pk).filter(ativa=True).exists():
                    definir_chave_ativa(chave.pk)
                verificar_chave(chave)
                if chave.valida:
                    messages.success(request, f'Chave "{chave.nome}" salva e válida ({chave.prefixo}…{chave.sufixo}).')
                else:
                    messages.warning(
                        request,
                        f'Chave "{chave.nome}" salva ({chave.prefixo}…{chave.sufixo}), mas a Anthropic '
                        "não aceitou esse valor — confira se copiou a chave corretamente.",
                    )
                return redirect("painel_relatorios:chaves_api_list")
    else:
        form = ChaveApiClaudeForm()
    return render(request, "painel/chaves_api_form.html", {"form": form})


@admin_required
def chaves_api_ativar(request, pk):
    if request.method == "POST":
        chave = get_object_or_404(ChaveApiClaude, pk=pk)
        definir_chave_ativa(chave.pk)
        messages.success(request, f'Chave "{chave.nome}" agora é a usada para gerar pareceres via IA.')
    return redirect("painel_relatorios:chaves_api_list")


@admin_required
def chaves_api_remover(request, pk):
    if request.method == "POST":
        chave = get_object_or_404(ChaveApiClaude, pk=pk)
        remover_chave(chave)
        messages.success(request, "Chave removida.")
    return redirect("painel_relatorios:chaves_api_list")


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
