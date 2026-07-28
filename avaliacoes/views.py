"""UI pública de aplicação do questionário (CLAUDE.md Etapa 7.2 / Seção 6.7).

Um único link por Aplicacao inteira (`Aplicacao.token`), compartilhado por todos os
respondentes — não existe mais um link individual por pessoa. Cada visita cria seu
próprio Respondente sob demanda (alias sequencial) e o identifica pela sessão do
navegador; reabrir o mesmo link no mesmo navegador retoma de onde parou, sem repetir
o que já foi respondido. Um navegador diferente que abra o mesmo link é tratado como
um respondente novo.

Fluxo: consentimento (duas declarações obrigatórias) -> perfil (tempo na organização,
modalidade de trabalho, nome se identificada) -> um domínio/subescala por página ->
perguntas abertas (opcionais) -> conclusão. `_proximo_passo` decide sempre a próxima
etapa a partir do estado do Respondente, num único lugar."""

from django import forms
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from avaliacoes.models import (
    Aplicacao,
    ModalidadeTrabalho,
    Respondente,
    Resposta,
    StatusAplicacao,
    TempoNaOrganizacao,
    TipoAplicacao,
)
from avaliacoes.services.aplicacao_status import atualizar_status_aplicacao
from avaliacoes.services.calculo_risco import calcular_dominio, dominios_da_aplicacao
from avaliacoes.services.questionario import dominios_pendentes
from instrumentos.models import Dominio


def _get_aplicacao_ou_404(aplicacao_token) -> Aplicacao:
    return get_object_or_404(Aplicacao, token=aplicacao_token)


def _chave_sessao(aplicacao: Aplicacao) -> str:
    return f"respondente_id__aplicacao_{aplicacao.pk}"


def _get_respondente_da_sessao(request, aplicacao: Aplicacao) -> Respondente | None:
    respondente_id = request.session.get(_chave_sessao(aplicacao))
    if not respondente_id:
        return None
    return Respondente.objects.filter(pk=respondente_id, aplicacao=aplicacao).first()


def _coleta_encerrada(aplicacao: Aplicacao, respondente: Respondente | None) -> bool:
    if respondente and respondente.concluido_em:
        return False
    return aplicacao.status in (StatusAplicacao.CONCLUIDA, StatusAplicacao.CANCELADA)


def _perfil_preenchido(respondente: Respondente) -> bool:
    if not respondente.tempo_na_organizacao or not respondente.modalidade_trabalho:
        return False
    if respondente.aplicacao.tipo == TipoAplicacao.IDENTIFICADA and not respondente.nome:
        return False
    return True


def _proximo_passo(respondente: Respondente):
    aplicacao = respondente.aplicacao
    atualizar_status_aplicacao(aplicacao.pk)

    if respondente.concluido_em:
        return redirect("avaliacoes:responder_concluido", aplicacao_token=aplicacao.token)
    if not _perfil_preenchido(respondente):
        return redirect("avaliacoes:responder_perfil", aplicacao_token=aplicacao.token)

    pendentes = dominios_pendentes(respondente)
    if pendentes:
        return redirect(
            "avaliacoes:responder_dominio", aplicacao_token=aplicacao.token, dominio_codigo=pendentes[0].codigo
        )
    if not respondente.perguntas_abertas_respondidas_em:
        return redirect("avaliacoes:responder_perguntas_abertas", aplicacao_token=aplicacao.token)

    respondente.concluido_em = timezone.now()
    respondente.save(update_fields=["concluido_em"])
    return redirect("avaliacoes:responder_concluido", aplicacao_token=aplicacao.token)


class ConsentimentoForm(forms.Form):
    participacao_voluntaria = forms.BooleanField(
        required=True,
        label=(
            "Concordo em responder ao questionário de forma voluntária e consciente, ciente de "
            "que os dados serão usados exclusivamente para fins de identificação e gestão de "
            "riscos psicossociais no ambiente de trabalho."
        ),
        error_messages={"required": "É necessário concordar com esta declaração para continuar."},
    )
    li_e_compreendi = forms.BooleanField(
        required=True,
        label="Li e compreendi a finalidade, a forma de uso e os limites deste formulário.",
        error_messages={"required": "É necessário confirmar esta declaração para continuar."},
    )


class PerfilRespondenteForm(forms.Form):
    tempo_na_organizacao = forms.ChoiceField(
        choices=[("", "---------")] + list(TempoNaOrganizacao.choices), label="Tempo na organização"
    )
    modalidade_trabalho = forms.ChoiceField(
        choices=[("", "---------")] + list(ModalidadeTrabalho.choices),
        label="Modalidade predominante de trabalho",
    )

    def __init__(self, *args, pedir_nome: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        if pedir_nome:
            self.fields["nome"] = forms.CharField(label="Nome", max_length=200)
            self.order_fields(["nome", "tempo_na_organizacao", "modalidade_trabalho"])


class PerguntasAbertasForm(forms.Form):
    resposta_aberta_1 = forms.CharField(
        label="Qual mudança na organização do trabalho mais ajudaria a reduzir riscos?",
        widget=forms.Textarea,
        required=False,
    )
    resposta_aberta_2 = forms.CharField(
        label="Há algum fator importante que não foi abordado?", widget=forms.Textarea, required=False
    )


def _construir_form_dominio(dominio: Dominio, respondente: Respondente, data=None) -> forms.Form:
    respostas_existentes = dict(
        Resposta.objects.filter(respondente=respondente, item__dominio=dominio).values_list(
            "item__item_id", "valor_bruto"
        )
    )
    choices = sorted(dominio.escala_labels.items(), key=lambda kv: int(kv[0]))
    opcoes = [(valor, f"{valor} — {rotulo}") for valor, rotulo in choices]

    campos = {}
    for item in dominio.itens.all():
        valor_existente = respostas_existentes.get(item.item_id)
        campos[item.item_id] = forms.ChoiceField(
            label=item.texto,
            choices=opcoes,
            widget=forms.RadioSelect,
            initial=str(valor_existente) if valor_existente is not None else None,
        )

    formulario_dominio = type("FormularioDominio", (forms.Form,), campos)
    return formulario_dominio(data)


def responder_consentimento(request, aplicacao_token):
    aplicacao = _get_aplicacao_ou_404(aplicacao_token)
    respondente = _get_respondente_da_sessao(request, aplicacao)

    if _coleta_encerrada(aplicacao, respondente):
        return render(request, "avaliacoes/questionario_encerrado.html", {"aplicacao": aplicacao})
    if respondente:
        return _proximo_passo(respondente)

    if request.method == "POST":
        form = ConsentimentoForm(request.POST)
        if form.is_valid():
            numero = aplicacao.respondentes.count() + 1
            respondente = Respondente.objects.create(
                aplicacao=aplicacao,
                alias_anonimo=f"Respondente {numero}",
                consentimento_aceito_em=timezone.now(),
            )
            request.session[_chave_sessao(aplicacao)] = respondente.pk
            return _proximo_passo(respondente)
    else:
        form = ConsentimentoForm()

    return render(request, "avaliacoes/questionario_consentimento.html", {"aplicacao": aplicacao, "form": form})


def responder_perfil(request, aplicacao_token):
    aplicacao = _get_aplicacao_ou_404(aplicacao_token)
    respondente = _get_respondente_da_sessao(request, aplicacao)
    if not respondente:
        return redirect("avaliacoes:responder_consentimento", aplicacao_token=aplicacao_token)
    if _coleta_encerrada(aplicacao, respondente):
        return render(request, "avaliacoes/questionario_encerrado.html", {"aplicacao": aplicacao})
    if respondente.concluido_em:
        return redirect("avaliacoes:responder_concluido", aplicacao_token=aplicacao_token)

    pedir_nome = aplicacao.tipo == TipoAplicacao.IDENTIFICADA

    if request.method == "POST":
        form = PerfilRespondenteForm(request.POST, pedir_nome=pedir_nome)
        if form.is_valid():
            respondente.tempo_na_organizacao = form.cleaned_data["tempo_na_organizacao"]
            respondente.modalidade_trabalho = form.cleaned_data["modalidade_trabalho"]
            if pedir_nome:
                respondente.nome = form.cleaned_data["nome"]
            respondente.save()
            return _proximo_passo(respondente)
    else:
        form = PerfilRespondenteForm(
            pedir_nome=pedir_nome,
            initial={
                "tempo_na_organizacao": respondente.tempo_na_organizacao,
                "modalidade_trabalho": respondente.modalidade_trabalho,
                "nome": respondente.nome,
            },
        )

    return render(request, "avaliacoes/questionario_perfil.html", {"respondente": respondente, "form": form})


def responder_dominio(request, aplicacao_token, dominio_codigo):
    aplicacao = _get_aplicacao_ou_404(aplicacao_token)
    respondente = _get_respondente_da_sessao(request, aplicacao)
    if not respondente:
        return redirect("avaliacoes:responder_consentimento", aplicacao_token=aplicacao_token)
    if _coleta_encerrada(aplicacao, respondente):
        return render(request, "avaliacoes/questionario_encerrado.html", {"aplicacao": aplicacao})
    if not _perfil_preenchido(respondente):
        return redirect("avaliacoes:responder_perfil", aplicacao_token=aplicacao_token)
    if respondente.concluido_em:
        return redirect("avaliacoes:responder_concluido", aplicacao_token=aplicacao_token)

    todos_dominios = dominios_da_aplicacao(aplicacao)
    dominios_por_codigo = {d.codigo: d for d in todos_dominios}
    dominio = dominios_por_codigo.get(dominio_codigo)
    if dominio is None:
        raise Http404("Este domínio não pertence à aplicação.")

    if request.method == "POST":
        form = _construir_form_dominio(dominio, respondente, data=request.POST)
        if form.is_valid():
            for item in dominio.itens.all():
                Resposta.objects.update_or_create(
                    respondente=respondente,
                    item=item,
                    defaults={"valor_bruto": int(form.cleaned_data[item.item_id])},
                )

            # Recalcula o agregado do domínio (todas as Respostas de todos os
            # Respondentes da Aplicacao até agora) assim que alguém termina de
            # respondê-lo — sem isso, EscoreDominio/ClassificacaoRisco/PlanoDeAcao
            # nunca nasceriam a partir do fluxo real de resposta.
            calcular_dominio(aplicacao, dominio)

            return _proximo_passo(respondente)
    else:
        form = _construir_form_dominio(dominio, respondente)

    indice = todos_dominios.index(dominio)
    progresso = {"atual": indice + 1, "total": len(todos_dominios)}

    if indice == 0:
        url_anterior = reverse("avaliacoes:responder_perfil", args=[aplicacao_token])
    else:
        url_anterior = reverse(
            "avaliacoes:responder_dominio",
            args=[aplicacao_token, todos_dominios[indice - 1].codigo],
        )

    return render(
        request,
        "avaliacoes/questionario_dominio.html",
        {
            "respondente": respondente,
            "dominio": dominio,
            "form": form,
            "progresso": progresso,
            "url_anterior": url_anterior,
        },
    )


def responder_perguntas_abertas(request, aplicacao_token):
    aplicacao = _get_aplicacao_ou_404(aplicacao_token)
    respondente = _get_respondente_da_sessao(request, aplicacao)
    if not respondente:
        return redirect("avaliacoes:responder_consentimento", aplicacao_token=aplicacao_token)
    if _coleta_encerrada(aplicacao, respondente):
        return render(request, "avaliacoes/questionario_encerrado.html", {"aplicacao": aplicacao})
    if respondente.concluido_em:
        return redirect("avaliacoes:responder_concluido", aplicacao_token=aplicacao_token)

    if request.method == "POST":
        form = PerguntasAbertasForm(request.POST)
        if form.is_valid():
            respondente.resposta_aberta_1 = form.cleaned_data["resposta_aberta_1"]
            respondente.resposta_aberta_2 = form.cleaned_data["resposta_aberta_2"]
            respondente.perguntas_abertas_respondidas_em = timezone.now()
            respondente.save()
            return _proximo_passo(respondente)
    else:
        form = PerguntasAbertasForm(
            initial={
                "resposta_aberta_1": respondente.resposta_aberta_1,
                "resposta_aberta_2": respondente.resposta_aberta_2,
            }
        )

    todos_dominios = dominios_da_aplicacao(aplicacao)
    url_anterior = (
        reverse("avaliacoes:responder_dominio", args=[aplicacao_token, todos_dominios[-1].codigo])
        if todos_dominios
        else reverse("avaliacoes:responder_perfil", args=[aplicacao_token])
    )

    return render(
        request,
        "avaliacoes/questionario_perguntas_abertas.html",
        {"respondente": respondente, "form": form, "url_anterior": url_anterior},
    )


def responder_concluido(request, aplicacao_token):
    aplicacao = _get_aplicacao_ou_404(aplicacao_token)
    respondente = _get_respondente_da_sessao(request, aplicacao)
    return render(request, "avaliacoes/questionario_concluido.html", {"respondente": respondente})
