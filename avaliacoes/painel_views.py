"""Painel — admin (equipe do SaaS) e gestor de empresa (CLAUDE.md Seção 6.8).

CRUD de Empresa -> Unidade -> GHE -> Aplicacao. Empresa é sempre admin (onboarding de
cliente novo); Unidade/Função/GHE/Aplicação são compartilhados — tanto o admin quanto
o gestor da própria empresa podem criar/editar, mas cada um só enxerga o que
`avaliacoes.services.tenancy.empresas_visiveis` permite. O Django Admin continua
disponível pra tudo que não está aqui (Perigo, CriterioVersao). IndicadorIndireto
ganhou tela própria (achado no diagnóstico de UX de 2026-07-28: sem ela, ninguém
usando o painel sabia que precisava cadastrar evidências complementares no Admin pra
a probabilidade de risco sair de 1)."""

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models as django_models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .decorators import admin_required, gestor_required
from .forms import (
    AplicacaoForm,
    CatalogoAcaoForm,
    CriarGestorForm,
    CriterioVersaoForm,
    EditarGestorForm,
    EmpresaForm,
    FuncaoForm,
    GHEForm,
    IndicadorIndiretoForm,
    PlanoDeAcaoForm,
    UnidadeForm,
)
from .models import (
    GHE,
    Aplicacao,
    CatalogoAcao,
    ColetaChecklistTriangulacao,
    ConformidadeChecklist,
    CriterioVersao,
    Empresa,
    IndicadorIndireto,
    PlanoDeAcao,
    RespostaChecklistTriangulacao,
    StatusAplicacao,
    StatusColetaChecklist,
    StatusCriterioVersao,
    Unidade,
)
from .services.aplicacao_status import encerrar_coleta
from .services.calculo_risco import (
    BANDA_ORDEM,
    contar_alertas_d9,
    criterio_classificacao_linhas,
    diagnostico_ghe,
    dominios_da_aplicacao,
)
from .services.semaforo import calcular_semaforo, leitura_resumida
from .services.tenancy import empresa_do_usuario, empresas_visiveis

# Mapa de calor da tela de Pontuação Anônima (prompts/04_pontuacao_anonima.md):
# 0 -> verde, 50 -> amarelo, 100 -> vermelho, nas mesmas cores dos badges de risco já
# usados no resto do painel (--teal-500/--amber-500/--red-500 de painel/_base.html).
_HEATMAP_STOPS = [(0.0, (20, 184, 166)), (50.0, (245, 158, 11)), (100.0, (239, 68, 68))]
_HEATMAP_BRANCO_MIX = 0.55  # suaviza a cor (mistura com branco) pra não competir com o texto


def _cor_heatmap(escore: float) -> str:
    escore = max(0.0, min(100.0, escore))
    (x0, cor0), (x1, cor1) = (
        (_HEATMAP_STOPS[0], _HEATMAP_STOPS[1]) if escore <= 50 else (_HEATMAP_STOPS[1], _HEATMAP_STOPS[2])
    )
    t = (escore - x0) / (x1 - x0)
    rgb = tuple(cor0[i] + (cor1[i] - cor0[i]) * t for i in range(3))
    rgb = tuple(round(c * (1 - _HEATMAP_BRANCO_MIX) + 255 * _HEATMAP_BRANCO_MIX) for c in rgb)
    return f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]})"


def _empresa_ou_404(request, pk):
    return get_object_or_404(empresas_visiveis(request.user), pk=pk)


def _unidade_ou_404(request, pk):
    return get_object_or_404(
        Unidade.objects.select_related("empresa").filter(empresa__in=empresas_visiveis(request.user)), pk=pk
    )


def _ghe_ou_404(request, pk):
    return get_object_or_404(
        GHE.objects.select_related("unidade__empresa").filter(
            unidade__empresa__in=empresas_visiveis(request.user)
        ),
        pk=pk,
    )


def _aplicacao_ou_404(request, pk):
    return get_object_or_404(
        Aplicacao.objects.select_related("ghe__unidade__empresa").filter(
            ghe__unidade__empresa__in=empresas_visiveis(request.user)
        ),
        pk=pk,
    )


@admin_required
def empresa_list(request):
    empresas = Empresa.objects.order_by("nome")
    return render(request, "painel/empresa_list.html", {"empresas": empresas})


@admin_required
def empresa_create(request):
    if request.method == "POST":
        form = EmpresaForm(request.POST)
        if form.is_valid():
            empresa = form.save()
            messages.success(request, f'Empresa "{empresa.nome}" criada.')
            return redirect("painel_avaliacoes:empresa_detail", pk=empresa.pk)
    else:
        form = EmpresaForm()
    return render(request, "painel/empresa_form.html", {"form": form})


@admin_required
def empresa_update(request, pk):
    empresa = get_object_or_404(Empresa, pk=pk)
    if request.method == "POST":
        form = EmpresaForm(request.POST, instance=empresa)
        if form.is_valid():
            form.save()
            messages.success(request, f'Empresa "{empresa.nome}" atualizada.')
            return redirect("painel_avaliacoes:empresa_detail", pk=empresa.pk)
    else:
        form = EmpresaForm(instance=empresa)
    return render(request, "painel/empresa_form.html", {"form": form, "empresa": empresa})


@gestor_required
def empresa_detail(request, pk):
    empresa = _empresa_ou_404(request, pk)
    unidades = empresa.unidades.order_by("nome")
    return render(request, "painel/empresa_detail.html", {"empresa": empresa, "unidades": unidades})


@admin_required
def empresa_criar_gestor(request, pk):
    empresa = get_object_or_404(Empresa, pk=pk)
    if empresa.gestor_id:
        messages.error(request, "Esta empresa já tem um gestor.")
        return redirect("painel_avaliacoes:empresa_detail", pk=empresa.pk)

    if request.method == "POST":
        form = CriarGestorForm(request.POST)
        if form.is_valid():
            usuario = get_user_model().objects.create_user(
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
                is_staff=True,
            )
            empresa.gestor = usuario
            empresa.save(update_fields=["gestor"])
            messages.success(request, f'Acesso criado para "{usuario.username}".')
            return redirect("painel_avaliacoes:empresa_detail", pk=empresa.pk)
    else:
        form = CriarGestorForm()
    return render(request, "painel/empresa_criar_gestor.html", {"form": form, "empresa": empresa})


@admin_required
def empresa_editar_gestor(request, pk):
    empresa = get_object_or_404(Empresa, pk=pk)
    if not empresa.gestor_id:
        messages.error(request, "Esta empresa ainda não tem um gestor.")
        return redirect("painel_avaliacoes:empresa_detail", pk=empresa.pk)

    if request.method == "POST":
        form = EditarGestorForm(request.POST, usuario=empresa.gestor)
        if form.is_valid():
            usuario = empresa.gestor
            usuario.username = form.cleaned_data["username"]
            if form.cleaned_data["password"]:
                usuario.set_password(form.cleaned_data["password"])
            usuario.save()
            messages.success(request, f'Acesso de "{usuario.username}" atualizado.')
            return redirect("painel_avaliacoes:empresa_detail", pk=empresa.pk)
    else:
        form = EditarGestorForm(initial={"username": empresa.gestor.username}, usuario=empresa.gestor)
    return render(request, "painel/empresa_editar_gestor.html", {"form": form, "empresa": empresa})


@admin_required
def empresa_remover_gestor(request, pk):
    """Remove o acesso ao painel sem apagar o usuário do banco: `Aplicacao.responsavel_aplicador`
    é PROTECT, então excluir o User quebraria com ProtectedError se o gestor já tiver
    conduzido alguma Aplicacao. Desvincular + desativar (`is_active=False`) já resolve
    o objetivo real (barrar o login) sem esse risco."""
    empresa = get_object_or_404(Empresa, pk=pk)
    if request.method == "POST" and empresa.gestor_id:
        usuario = empresa.gestor
        empresa.gestor = None
        empresa.save(update_fields=["gestor"])
        usuario.is_active = False
        usuario.save(update_fields=["is_active"])
        messages.success(request, f'Acesso de "{usuario.username}" removido.')
    return redirect("painel_avaliacoes:empresa_detail", pk=empresa.pk)


@gestor_required
def unidade_create(request, empresa_id):
    empresa = _empresa_ou_404(request, empresa_id)
    if request.method == "POST":
        form = UnidadeForm(request.POST)
        if form.is_valid():
            unidade = form.save(commit=False)
            unidade.empresa = empresa
            unidade.save()
            messages.success(request, f'Unidade "{unidade.nome}" criada.')
            return redirect("painel_avaliacoes:unidade_detail", pk=unidade.pk)
    else:
        form = UnidadeForm()
    return render(request, "painel/unidade_form.html", {"form": form, "empresa": empresa})


@gestor_required
def unidade_update(request, pk):
    unidade = _unidade_ou_404(request, pk)
    if request.method == "POST":
        form = UnidadeForm(request.POST, instance=unidade)
        if form.is_valid():
            form.save()
            messages.success(request, f'Unidade "{unidade.nome}" atualizada.')
            return redirect("painel_avaliacoes:unidade_detail", pk=unidade.pk)
    else:
        form = UnidadeForm(instance=unidade)
    return render(request, "painel/unidade_form.html", {"form": form, "empresa": unidade.empresa, "unidade": unidade})


@gestor_required
def unidade_detail(request, pk):
    unidade = _unidade_ou_404(request, pk)
    ghes = unidade.ghes.order_by("nome")
    funcoes = unidade.funcoes.order_by("nome")
    tem_aplicacoes = Aplicacao.objects.filter(ghe__unidade=unidade).exists()
    return render(
        request,
        "painel/unidade_detail.html",
        {"unidade": unidade, "ghes": ghes, "funcoes": funcoes, "tem_aplicacoes": tem_aplicacoes},
    )


@gestor_required
def funcao_create(request, unidade_id):
    unidade = _unidade_ou_404(request, unidade_id)
    if request.method == "POST":
        form = FuncaoForm(request.POST)
        if form.is_valid():
            funcao = form.save(commit=False)
            funcao.unidade = unidade
            funcao.save()
            messages.success(request, f'Função "{funcao.nome}" criada.')
            return redirect("painel_avaliacoes:unidade_detail", pk=unidade.pk)
    else:
        form = FuncaoForm()
    return render(request, "painel/funcao_form.html", {"form": form, "unidade": unidade})


@gestor_required
def ghe_create(request, unidade_id):
    unidade = _unidade_ou_404(request, unidade_id)
    if request.method == "POST":
        form = GHEForm(request.POST, unidade=unidade)
        if form.is_valid():
            ghe = form.save(commit=False)
            ghe.unidade = unidade
            ghe.save()
            form.save_m2m()
            messages.success(request, f'GHE "{ghe.nome}" criado.')
            return redirect("painel_avaliacoes:ghe_detail", pk=ghe.pk)
    else:
        form = GHEForm(unidade=unidade)
    return render(request, "painel/ghe_form.html", {"form": form, "unidade": unidade})


@gestor_required
def ghe_update(request, pk):
    ghe = _ghe_ou_404(request, pk)
    if request.method == "POST":
        form = GHEForm(request.POST, instance=ghe, unidade=ghe.unidade)
        if form.is_valid():
            form.save()
            messages.success(request, f'GHE "{ghe.nome}" atualizado.')
            return redirect("painel_avaliacoes:ghe_detail", pk=ghe.pk)
    else:
        form = GHEForm(instance=ghe, unidade=ghe.unidade)
    return render(request, "painel/ghe_form.html", {"form": form, "unidade": ghe.unidade, "ghe": ghe})


@gestor_required
def ghe_detail(request, pk):
    ghe = _ghe_ou_404(request, pk)
    aplicacoes = ghe.aplicacoes.select_related("instrumento", "criterio_versao").order_by("-criado_em")
    return render(request, "painel/ghe_detail.html", {"ghe": ghe, "aplicacoes": aplicacoes})


@admin_required
def indicadores_indiretos(request, ghe_id):
    """Evidências complementares (Seção 7.5) — absenteísmo, turnover, CAT/CID-F,
    relato de entrevista. Antes só existia no Django Admin, invisível pra quem usa o
    painel (achado no diagnóstico de UX de 2026-07-28) — sem essas evidências, a
    probabilidade de qualquer risco fica travada em 1 e a Banda quase sempre sai
    "Aceitável", mesmo com domínios Elevados."""
    ghe = get_object_or_404(GHE.objects.select_related("unidade__empresa"), pk=ghe_id)
    if request.method == "POST":
        form = IndicadorIndiretoForm(request.POST, ghe=ghe)
        if form.is_valid():
            indicador = form.save(commit=False)
            indicador.ghe = ghe
            indicador.registrado_por = request.user
            indicador.save()
            messages.success(request, "Evidência registrada.")
            return redirect("painel_avaliacoes:indicadores_indiretos", ghe_id=ghe.pk)
    else:
        form = IndicadorIndiretoForm(ghe=ghe)

    indicadores = ghe.indicadores_indiretos.select_related("dominio_relacionado").order_by("-criado_em")
    return render(
        request,
        "painel/indicadores_indiretos.html",
        {"ghe": ghe, "form": form, "indicadores": indicadores},
    )


@gestor_required
def aplicacao_create(request, ghe_id):
    ghe = _ghe_ou_404(request, ghe_id)
    if request.method == "POST":
        form = AplicacaoForm(request.POST, usuario_logado=request.user)
        if form.is_valid():
            aplicacao = form.save(commit=False)
            aplicacao.ghe = ghe
            aplicacao.save()
            messages.success(request, "Aplicação criada.")
            return redirect("painel_avaliacoes:aplicacao_detail", pk=aplicacao.pk)
    else:
        form = AplicacaoForm(usuario_logado=request.user)
    return render(request, "painel/aplicacao_form.html", {"form": form, "ghe": ghe})


@gestor_required
def aplicacao_update(request, pk):
    aplicacao = _aplicacao_ou_404(request, pk)
    if request.method == "POST":
        form = AplicacaoForm(request.POST, instance=aplicacao, usuario_logado=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Aplicação atualizada.")
            return redirect("painel_avaliacoes:aplicacao_detail", pk=aplicacao.pk)
    else:
        form = AplicacaoForm(instance=aplicacao, usuario_logado=request.user)
    return render(request, "painel/aplicacao_form.html", {"form": form, "ghe": aplicacao.ghe, "aplicacao": aplicacao})


def _contexto_respondentes_resultados(aplicacao: Aplicacao) -> dict:
    """Dados dos cards "Respondentes" e "Resultados por domínio" — fatorado
    (2026-08-06) porque tanto `aplicacao_detail` (render completo) quanto
    `aplicacao_live` (endpoint de atualização em tempo real, chamado via polling
    JS) precisam montar exatamente os mesmos dados."""
    respondentes = aplicacao.respondentes.order_by("alias_anonimo")
    escores_lista = list(
        aplicacao.escores_dominio.select_related("dominio", "classificacao_risco").order_by("dominio__ordem")
    )
    n_minimo = aplicacao.criterio_versao.n_minimo_respondentes
    n_concluidos = sum(1 for r in respondentes if r.concluido_em)
    todos_suprimidos = bool(escores_lista) and all(
        e.suprimido_por_confidencialidade for e in escores_lista
    )
    dominios_em_risco = sum(
        1
        for e in escores_lista
        if not e.suprimido_por_confidencialidade and e.classificacao == "Elevado"
    )
    return {
        "respondentes": respondentes,
        "escores": escores_lista,
        "n_minimo": n_minimo,
        "n_concluidos": n_concluidos,
        "todos_suprimidos": todos_suprimidos,
        "dominios_em_risco": dominios_em_risco,
    }


@gestor_required
def aplicacao_detail(request, pk):
    aplicacao = _aplicacao_ou_404(request, pk)
    dados = _contexto_respondentes_resultados(aplicacao)
    link_respondente = request.build_absolute_uri(
        reverse("avaliacoes:responder_consentimento", args=[aplicacao.token])
    )
    alertas_d9 = contar_alertas_d9(aplicacao)
    # Ordenado do mais urgente pro menos urgente (Crítico > Alto > Moderado) — antes
    # vinha na ordem de cadastro do domínio, sem relação com prioridade de ação.
    planos_de_acao = sorted(
        PlanoDeAcao.objects.filter(
            classificacao_risco__escore_dominio__aplicacao=aplicacao
        ).select_related("classificacao_risco__escore_dominio__dominio"),
        key=lambda p: BANDA_ORDEM.get(p.classificacao_risco.banda, 0),
        reverse=True,
    )
    pronta_para_relatorio = (
        aplicacao.status == StatusAplicacao.CONCLUIDA and not aplicacao.relatorios.exists()
    )
    return render(
        request,
        "painel/aplicacao_detail.html",
        {
            "aplicacao": aplicacao,
            "link_respondente": link_respondente,
            "alertas_d9": alertas_d9,
            "planos_de_acao": planos_de_acao,
            "pronta_para_relatorio": pronta_para_relatorio,
            **dados,
        },
    )


@gestor_required
def aplicacao_live(request, pk):
    """Endpoint chamado por polling JS (`aplicacao_detail.html`, a cada 10s enquanto
    a coleta está em andamento e a aba está em foco) pra atualizar os cards
    "Respondentes" e "Resultados por domínio" sem recarregar a página inteira."""
    aplicacao = _aplicacao_ou_404(request, pk)
    dados = _contexto_respondentes_resultados(aplicacao)
    respondentes_html = render_to_string(
        "painel/_partials/respondentes_card.html",
        {"respondentes": dados["respondentes"]},
        request=request,
    )
    resultados_html = render_to_string(
        "painel/_partials/resultados_dominio_card.html",
        {"escores": dados["escores"], "n_minimo": dados["n_minimo"]},
        request=request,
    )
    return JsonResponse({"respondentes_html": respondentes_html, "resultados_html": resultados_html})


@admin_required
def pontuacao_anonima(request, pk):
    """Planilha `Pontuacao_anonima` do Excel de referência: uma linha por respondente,
    escore 0-100 por domínio + índice geral, com mapa de calor. Tela só do admin —
    mostra dado individual (embora anônimo), não dado agregado do GHE inteiro
    (CLAUDE.md Seção 6.8: parecer/relatório da IA é sempre admin; esta tela segue a
    mesma lógica por expor granularidade por respondente)."""
    aplicacao = _aplicacao_ou_404(request, pk)
    dominios = dominios_da_aplicacao(aplicacao)
    # `concluido_em__isnull=False` (2026-08-06): quem não terminou o questionário
    # inteiro não conta em nenhum cálculo (avaliacoes/services/calculo_risco.py) — essa
    # tela não deve mostrar a linha de alguém incompleto, mesmo que o EscoreRespondente
    # dele ainda não tenha sido limpo/recalculado. Ordenar por `alias_anonimo` (não por
    # `criado_em`/ordem de chegada) evita vazar a ordem cronológica de quem respondeu
    # primeiro ao lado dos escores individuais de cada um.
    respondentes = (
        aplicacao.respondentes.filter(concluido_em__isnull=False)
        .prefetch_related("escores")
        .order_by("alias_anonimo")
    )

    linhas = []
    for respondente in respondentes:
        escores_por_dominio_id = {e.dominio_id: e for e in respondente.escores.all()}
        celulas = []
        for dominio in dominios:
            escore_resp = escores_por_dominio_id.get(dominio.id)
            valor = float(escore_resp.escore) if escore_resp else None
            celulas.append({"valor": valor, "cor": _cor_heatmap(valor) if valor is not None else None})

        indice_geral = float(respondente.indice_geral) if respondente.indice_geral is not None else None
        linhas.append(
            {
                "respondente": respondente,
                "celulas": celulas,
                "indice_geral": indice_geral,
                "indice_geral_cor": _cor_heatmap(indice_geral) if indice_geral is not None else None,
            }
        )

    return render(
        request,
        "painel/pontuacao_anonima.html",
        {"aplicacao": aplicacao, "dominios": dominios, "linhas": linhas},
    )


@admin_required
def alertas_agregados(request, pk):
    """Planilha `Alertas_agregados` do Excel de referência: uma linha por GHE (Aplicacao)
    de uma Unidade, com nº de respondentes e alertas D9. Admin-only pela mesma lógica de
    `pontuacao_anonima` (CLAUDE.md Seção 6.8)."""
    unidade = _unidade_ou_404(request, pk)
    aplicacoes = (
        Aplicacao.objects.filter(ghe__unidade=unidade)
        .select_related("ghe", "instrumento")
        .order_by("ghe__nome")
    )
    linhas = [{"aplicacao": aplicacao, **contar_alertas_d9(aplicacao)} for aplicacao in aplicacoes]
    return render(
        request,
        "painel/alertas_agregados.html",
        {"unidade": unidade, "linhas": linhas},
    )


@admin_required
def diagnostico_ghe_view(request, pk):
    """Planilha `Diagnostico_GHE` do Excel de referência: uma linha por domínio desta
    Aplicacao, com N, escore, % elevados, classificação, prioridade (P1/P2/P3/AGRUPAR),
    alerta protegido e nota técnica. Admin-only (mesma lógica de escopo da Seção 6.8)."""
    aplicacao = _aplicacao_ou_404(request, pk)
    linhas = diagnostico_ghe(aplicacao)
    todos_agrupar = bool(linhas) and all(linha["prioridade"] == "AGRUPAR" for linha in linhas)
    return render(
        request,
        "painel/diagnostico_ghe.html",
        {
            "aplicacao": aplicacao,
            "linhas": linhas,
            "todos_agrupar": todos_agrupar,
            "n_minimo": aplicacao.criterio_versao.n_minimo_respondentes,
        },
    )


@admin_required
def catalogo_acoes_list(request):
    """Planilha `Catalogo_Acoes` do Excel de referência: 18 ações pré-definidas (9
    domínios x Moderado/Elevado), pré-carregadas pelo seed mas editáveis aqui — o
    profissional responsável pode personalizar pra realidade de cada empresa
    (CLAUDE.md prompts/07_catalogo_acoes.md)."""
    acoes = CatalogoAcao.objects.select_related("dominio", "dominio__instrumento").order_by(
        "dominio__instrumento", "dominio__ordem", "nivel"
    )
    return render(request, "painel/catalogo_acoes_list.html", {"acoes": acoes})


@admin_required
def catalogo_acoes_update(request, pk):
    acao = get_object_or_404(CatalogoAcao, pk=pk)
    if request.method == "POST":
        form = CatalogoAcaoForm(request.POST, instance=acao)
        if form.is_valid():
            form.save()
            messages.success(request, "Ação do catálogo atualizada.")
            return redirect("painel_avaliacoes:catalogo_acoes_list")
    else:
        form = CatalogoAcaoForm(instance=acao)
    return render(request, "painel/catalogo_acoes_form.html", {"form": form, "acao": acao})


@admin_required
def plano_de_acao_update(request, pk):
    """Edição dos 15 campos do Plano de Ação (prompts/08_plano_de_acao.md). Admin-only,
    mesma lógica de escopo do parecer da IA (CLAUDE.md Seção 6.8) — o profissional
    responsável do PGR é quem ajusta responsável/prazo/status/evidências."""
    plano = get_object_or_404(
        PlanoDeAcao.objects.select_related(
            "classificacao_risco__escore_dominio__dominio",
            "classificacao_risco__escore_dominio__aplicacao__ghe",
        ),
        pk=pk,
    )
    aplicacao = plano.classificacao_risco.escore_dominio.aplicacao
    if request.method == "POST":
        form = PlanoDeAcaoForm(request.POST, instance=plano)
        if form.is_valid():
            form.save()
            messages.success(request, "Plano de ação atualizado.")
            return redirect("painel_avaliacoes:aplicacao_detail", pk=aplicacao.pk)
    else:
        form = PlanoDeAcaoForm(instance=plano)
    return render(request, "painel/plano_de_acao_form.html", {"form": form, "plano": plano, "aplicacao": aplicacao})


@gestor_required
def checklist_triangulacao(request, pk):
    """Gestão da coleta do checklist de triangulação (entrevista + observação):
    abrir/encerrar uma rodada, ver o link e a lista de respondentes (gestores da
    empresa cliente, que respondem pelo link — CLAUDE.md Seção 6.11). Diferente das
    outras evidências agregadas, aberta tanto pro admin quanto pro gestor da empresa
    (decisão explícita do usuário, 2026-07-29) — quem responde já são pessoas da
    própria empresa, não há dado de outro cliente exposto aqui."""
    aplicacao = _aplicacao_ou_404(request, pk)
    coleta = aplicacao.coletas_checklist.order_by("-criado_em").first()

    # Itens de entrevista não têm conformidade válida (achado em 2026-07-29 — são
    # perguntas abertas), então aparecem sempre que houver texto de resposta; itens de
    # observação continuam exigindo uma conformidade avaliada (Conforme/Não conforme).
    respostas = (
        RespostaChecklistTriangulacao.objects.filter(respondente__coleta__aplicacao=aplicacao)
        .filter(
            django_models.Q(item__tipo="entrevista")
            | ~django_models.Q(conformidade=ConformidadeChecklist.NAO_AVALIADO)
        )
        .select_related("item", "respondente")
        .order_by("item__tipo", "item__ordem")
    )

    link_checklist = None
    if coleta:
        link_checklist = request.build_absolute_uri(
            reverse("avaliacoes:checklist_identificacao", args=[coleta.token])
        )

    return render(
        request,
        "painel/checklist_triangulacao.html",
        {
            "aplicacao": aplicacao,
            "coleta": coleta,
            "link_checklist": link_checklist,
            "respondentes": coleta.respondentes.all() if coleta else [],
            "respostas": respostas,
        },
    )


@gestor_required
def checklist_abrir_coleta(request, pk):
    aplicacao = _aplicacao_ou_404(request, pk)
    if request.method == "POST":
        ColetaChecklistTriangulacao.objects.create(aplicacao=aplicacao, criado_por=request.user)
        messages.success(request, "Nova coleta do checklist aberta — distribua o link abaixo.")
    return redirect("painel_avaliacoes:checklist_triangulacao", pk=aplicacao.pk)


@gestor_required
def checklist_encerrar_coleta(request, pk):
    aplicacao = _aplicacao_ou_404(request, pk)
    coleta = aplicacao.coletas_checklist.filter(status=StatusColetaChecklist.ABERTA).order_by("-criado_em").first()
    if request.method == "POST" and coleta:
        coleta.status = StatusColetaChecklist.ENCERRADA
        coleta.encerrada_em = timezone.now()
        coleta.save(update_fields=["status", "encerrada_em"])
        messages.success(request, "Coleta do checklist encerrada.")
    return redirect("painel_avaliacoes:checklist_triangulacao", pk=aplicacao.pk)


@admin_required
def semaforo_riscos(request, pk):
    """Planilha `Semaforo_Riscos` do Excel de referência: distribuição percentual de
    respondentes em 3 faixas (favorável/intermediário/risco) por domínio, agregando
    todas as Aplicacoes de uma Unidade ("TOTAL ORGANIZAÇÃO" no Excel) ou, via filtro
    `?ghe=<id>`, só de um GHE específico. Inclui GHEs suprimidos no agregado da unidade
    inteira — a supressão vale pra exibir o GHE isolado, não pra excluir seus dados do
    total (confirmado contra os 42 respondentes = 12+18+9+3 da planilha de referência).
    Admin-only, mesma lógica de escopo da Seção 6.8."""
    unidade = _unidade_ou_404(request, pk)
    ghes = unidade.ghes.order_by("nome")

    ghe_selecionado = None
    ghe_id = request.GET.get("ghe")
    aplicacoes = Aplicacao.objects.filter(ghe__unidade=unidade).select_related("criterio_versao")
    if ghe_id:
        ghe_selecionado = get_object_or_404(ghes, pk=ghe_id)
        aplicacoes = aplicacoes.filter(ghe=ghe_selecionado)

    aplicacoes = list(aplicacoes)
    linhas = calcular_semaforo(aplicacoes)
    resumo = leitura_resumida(linhas)
    n_total = max((linha["n_respondentes"] for linha in linhas), default=0)

    return render(
        request,
        "painel/semaforo_riscos.html",
        {
            "unidade": unidade,
            "ghes": ghes,
            "ghe_selecionado": ghe_selecionado,
            "linhas": linhas,
            "resumo": resumo,
            "n_total": n_total,
        },
    )


@gestor_required
def em_execucao(request, titulo):
    """Placeholder genérico pra módulos ainda não detalhados — CLAUDE.md Seção 6.8:
    evita construir/deduzir esses fluxos antes do usuário definir como devem ficar."""
    return render(request, "painel/em_execucao.html", {"titulo": titulo})


@admin_required
def configuracoes_risco_list(request):
    """CLAUDE.md Seção 7.8: toda versão de CriterioVersao é um snapshot IMUTÁVEL —
    esta tela só lista/inspeciona/ratifica versões existentes e permite criar uma
    versão NOVA a partir de uma base; nunca edita os números de uma versão já usada
    por algum Relatorio (isso quebraria a rastreabilidade exigida pela NR-01)."""
    criterios = CriterioVersao.objects.annotate(
        n_aplicacoes=django_models.Count("aplicacoes", distinct=True)
    ).order_by("-criado_em")
    return render(request, "painel/configuracoes_risco_list.html", {"criterios": criterios})


@admin_required
def configuracoes_risco_detail(request, pk):
    criterio = get_object_or_404(CriterioVersao, pk=pk)
    n_aplicacoes = criterio.aplicacoes.count()

    matriz_por_severidade: dict[int, list[dict]] = {}
    for entrada in criterio.matriz_risco:
        matriz_por_severidade.setdefault(entrada["severidade"], []).append(entrada)
    matriz_linhas = [
        {"severidade": s, "celulas": sorted(matriz_por_severidade.get(s, []), key=lambda e: e["probabilidade"])}
        for s in sorted(matriz_por_severidade)
    ]

    thresholds_por_instrumento = [
        {"instrumento": instrumento, "dominios": sorted(dominios.items())}
        for instrumento, dominios in criterio.thresholds_por_dominio.items()
    ]

    return render(
        request,
        "painel/configuracoes_risco_detail.html",
        {
            "criterio": criterio,
            "n_aplicacoes": n_aplicacoes,
            "criterio_classificacao_linhas": criterio_classificacao_linhas(criterio),
            "matriz_linhas": matriz_linhas,
            "thresholds_por_instrumento": thresholds_por_instrumento,
            "pode_ratificar": criterio.status == StatusCriterioVersao.AGUARDANDO_RATIFICACAO,
        },
    )


@admin_required
def configuracoes_risco_ratificar(request, pk):
    if request.method != "POST":
        return redirect("painel_avaliacoes:configuracoes_risco_detail", pk=pk)
    criterio = get_object_or_404(CriterioVersao, pk=pk)
    if criterio.status == StatusCriterioVersao.AGUARDANDO_RATIFICACAO:
        criterio.status = StatusCriterioVersao.RATIFICADO
        criterio.ratificado_por = request.user
        criterio.ratificado_em = timezone.now()
        criterio.save(update_fields=["status", "ratificado_por", "ratificado_em"])
        messages.success(request, f'Versão "{criterio.codigo}" ratificada.')
    return redirect("painel_avaliacoes:configuracoes_risco_detail", pk=pk)


@admin_required
def configuracoes_risco_create(request):
    """Cria uma nova CriterioVersao clonando os thresholds/severidade/matriz de risco
    (tecnicamente ancorados em risk_engine.py — nunca editáveis por aqui) da versão
    mais recente, deixando abertos só os parâmetros numéricos de negócio."""
    base = CriterioVersao.objects.order_by("-criado_em").first()

    if request.method == "POST":
        form = CriterioVersaoForm(request.POST)
        if form.is_valid():
            criterio = form.save(commit=False)
            criterio.thresholds_por_dominio = base.thresholds_por_dominio if base else {}
            criterio.severidade_por_classificacao = base.severidade_por_classificacao if base else {}
            criterio.matriz_risco = base.matriz_risco if base else []
            criterio.save()
            messages.success(
                request,
                f'Nova versão "{criterio.codigo}" criada — aguardando ratificação do '
                "profissional responsável antes de uso conclusivo.",
            )
            return redirect("painel_avaliacoes:configuracoes_risco_detail", pk=criterio.pk)
    else:
        initial = (
            {
                "n_minimo_respondentes": base.n_minimo_respondentes,
                "limiar_evento_grave": base.limiar_evento_grave,
                "limite_baixo": base.limite_baixo,
                "limite_elevado": base.limite_elevado,
                "prevalencia_p1": base.prevalencia_p1,
                "prevalencia_p2": base.prevalencia_p2,
                "periodo_referencia": base.periodo_referencia,
            }
            if base
            else {}
        )
        form = CriterioVersaoForm(initial=initial)

    return render(request, "painel/configuracoes_risco_form.html", {"form": form, "base": base})


@gestor_required
def relatorios_empresa(request):
    """Visão somente-leitura da empresa cliente: lista os relatórios da própria
    empresa e permite baixar o PDF quando existir. Parecer/edição/assinatura
    continuam admin-only (CLAUDE.md Seção 6.8) — aqui a empresa só acompanha."""
    from relatorios.models import Relatorio

    empresa = empresa_do_usuario(request.user)
    relatorios = (
        Relatorio.objects.filter(unidade__empresa=empresa)
        .select_related("unidade")
        .order_by("-gerado_em")
        if empresa
        else Relatorio.objects.none()
    )
    return render(request, "painel/relatorios_empresa.html", {"relatorios": relatorios})


@gestor_required
def analise_ia_empresa(request):
    """Resumo somente-leitura do parecer técnico (síntese + riscos prioritários) dos
    relatórios já assinados da própria empresa. Minutas não assinadas não aparecem —
    a empresa só vê análise já revisada e assinada pelo profissional responsável."""
    from relatorios.models import Relatorio, StatusRelatorio

    empresa = empresa_do_usuario(request.user)
    relatorios = (
        Relatorio.objects.filter(
            unidade__empresa=empresa, status=StatusRelatorio.ASSINADO, parecer_ia__isnull=False
        )
        .select_related("unidade")
        .order_by("-assinado_em")
        if empresa
        else Relatorio.objects.none()
    )
    return render(request, "painel/analise_ia_empresa.html", {"relatorios": relatorios})


@gestor_required
def aplicacao_encerrar_coleta(request, pk):
    aplicacao = _aplicacao_ou_404(request, pk)
    if request.method == "POST":
        try:
            encerrar_coleta(aplicacao.pk)
            messages.success(request, "Coleta encerrada — o link de resposta parou de aceitar novas respostas.")
        except ValidationError as exc:
            messages.error(request, str(exc.message))
    return redirect("painel_avaliacoes:aplicacao_detail", pk=aplicacao.pk)
