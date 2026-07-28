"""UI pública do checklist de triangulação (entrevista + observação), respondido
via link pelos gestores/liderança da empresa cliente — mesmo padrão de link único +
sessão do navegador do questionário do colaborador (`avaliacoes/views.py`), mas aqui
o respondente se identifica (nome/cargo), pois é uma entrevista com a liderança, não
uma coleta anônima (CLAUDE.md Seção 6.11).

Fluxo: identificação (nome/cargo) -> grupo "Entrevista com liderança" (6 itens) ->
grupo "Observação em campo" (10 itens) -> conclusão. `_proximo_passo` decide sempre a
próxima etapa a partir do estado do respondente, mesmo padrão de
`avaliacoes/views.py::_proximo_passo`."""

from django import forms
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from avaliacoes.models import (
    ColetaChecklistTriangulacao,
    ConformidadeChecklist,
    ItemChecklistTriangulacao,
    RespondenteChecklistTriangulacao,
    RespostaChecklistTriangulacao,
    StatusColetaChecklist,
)

GRUPOS = ["entrevista", "observacao"]


def _get_coleta_ou_404(token) -> ColetaChecklistTriangulacao:
    return get_object_or_404(ColetaChecklistTriangulacao, token=token)


def _chave_sessao(coleta: ColetaChecklistTriangulacao) -> str:
    return f"checklist_respondente_id__coleta_{coleta.pk}"


def _get_respondente_da_sessao(request, coleta: ColetaChecklistTriangulacao) -> RespondenteChecklistTriangulacao | None:
    respondente_id = request.session.get(_chave_sessao(coleta))
    if not respondente_id:
        return None
    return RespondenteChecklistTriangulacao.objects.filter(pk=respondente_id, coleta=coleta).first()


def _proximo_grupo_pendente(respondente: RespondenteChecklistTriangulacao) -> str | None:
    for tipo in GRUPOS:
        total = ItemChecklistTriangulacao.objects.filter(tipo=tipo).count()
        respondidos = respondente.respostas.filter(item__tipo=tipo).count()
        if respondidos < total:
            return tipo
    return None


def _proximo_passo(respondente: RespondenteChecklistTriangulacao):
    coleta = respondente.coleta
    if respondente.concluido_em:
        return redirect("avaliacoes:checklist_concluido", token=coleta.token)

    grupo_pendente = _proximo_grupo_pendente(respondente)
    if grupo_pendente:
        return redirect("avaliacoes:checklist_grupo", token=coleta.token, tipo=grupo_pendente)

    respondente.concluido_em = timezone.now()
    respondente.save(update_fields=["concluido_em"])
    return redirect("avaliacoes:checklist_concluido", token=coleta.token)


class IdentificacaoForm(forms.Form):
    nome = forms.CharField(label="Nome", max_length=200)
    cargo = forms.CharField(label="Cargo", max_length=200, required=False)


def _construir_form_grupo(tipo: str, respondente: RespondenteChecklistTriangulacao, data=None) -> forms.Form:
    itens = ItemChecklistTriangulacao.objects.filter(tipo=tipo).order_by("ordem")
    respostas_existentes = {
        r.item_id: r for r in respondente.respostas.filter(item__tipo=tipo)
    }

    campos = {}
    for item in itens:
        existente = respostas_existentes.get(item.id)
        campos[f"conformidade_{item.id}"] = forms.ChoiceField(
            label=item.texto,
            choices=ConformidadeChecklist.choices,
            widget=forms.RadioSelect,
            initial=existente.conformidade if existente else ConformidadeChecklist.NAO_AVALIADO,
        )
        campos[f"evidencia_{item.id}"] = forms.CharField(
            label="Evidência/observação",
            widget=forms.Textarea(attrs={"rows": 2}),
            required=False,
            initial=existente.evidencia if existente else "",
        )

    FormularioGrupo = type("FormularioGrupo", (forms.Form,), campos)
    return FormularioGrupo(data)


def checklist_identificacao(request, token):
    coleta = _get_coleta_ou_404(token)
    respondente = _get_respondente_da_sessao(request, coleta)

    if coleta.status == StatusColetaChecklist.ENCERRADA and not (respondente and respondente.concluido_em):
        return render(request, "avaliacoes/checklist_encerrado.html", {"coleta": coleta})
    if respondente:
        return _proximo_passo(respondente)

    if request.method == "POST":
        form = IdentificacaoForm(request.POST)
        if form.is_valid():
            respondente = RespondenteChecklistTriangulacao.objects.create(
                coleta=coleta,
                nome=form.cleaned_data["nome"],
                cargo=form.cleaned_data["cargo"],
            )
            request.session[_chave_sessao(coleta)] = respondente.pk
            return _proximo_passo(respondente)
    else:
        form = IdentificacaoForm()

    return render(request, "avaliacoes/checklist_identificacao.html", {"coleta": coleta, "form": form})


def checklist_grupo(request, token, tipo):
    if tipo not in GRUPOS:
        raise Http404("Grupo inválido.")

    coleta = _get_coleta_ou_404(token)
    respondente = _get_respondente_da_sessao(request, coleta)
    if not respondente:
        return redirect("avaliacoes:checklist_identificacao", token=token)
    if coleta.status == StatusColetaChecklist.ENCERRADA and not respondente.concluido_em:
        return render(request, "avaliacoes/checklist_encerrado.html", {"coleta": coleta})
    if respondente.concluido_em:
        return redirect("avaliacoes:checklist_concluido", token=token)

    itens = list(ItemChecklistTriangulacao.objects.filter(tipo=tipo).order_by("ordem"))

    if request.method == "POST":
        form = _construir_form_grupo(tipo, respondente, data=request.POST)
        if form.is_valid():
            for item in itens:
                RespostaChecklistTriangulacao.objects.update_or_create(
                    respondente=respondente,
                    item=item,
                    defaults={
                        "conformidade": form.cleaned_data[f"conformidade_{item.id}"],
                        "evidencia": form.cleaned_data[f"evidencia_{item.id}"],
                    },
                )
            return _proximo_passo(respondente)
    else:
        form = _construir_form_grupo(tipo, respondente)

    itens_com_campos = [
        {
            "item": item,
            "campo_conformidade": form[f"conformidade_{item.id}"],
            "campo_evidencia": form[f"evidencia_{item.id}"],
        }
        for item in itens
    ]

    indice = GRUPOS.index(tipo)
    url_anterior = (
        None if indice == 0 else reverse("avaliacoes:checklist_grupo", args=[token, GRUPOS[indice - 1]])
    )
    e_ultimo_grupo = indice == len(GRUPOS) - 1

    return render(
        request,
        "avaliacoes/checklist_grupo.html",
        {
            "coleta": coleta,
            "tipo": tipo,
            "titulo_grupo": dict(ItemChecklistTriangulacao._meta.get_field("tipo").choices)[tipo],
            "itens_com_campos": itens_com_campos,
            "progresso": {"atual": indice + 1, "total": len(GRUPOS)},
            "url_anterior": url_anterior,
            "e_ultimo_grupo": e_ultimo_grupo,
        },
    )


def checklist_concluido(request, token):
    coleta = _get_coleta_ou_404(token)
    respondente = _get_respondente_da_sessao(request, coleta)
    return render(request, "avaliacoes/checklist_concluido.html", {"coleta": coleta, "respondente": respondente})
