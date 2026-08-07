"""UI pública de aplicação do questionário (CLAUDE.md Etapa 7.2 / Seção 6.7).

Um único link por Aplicacao inteira (`Aplicacao.token`), compartilhado por todos os
respondentes — não existe mais um link individual por pessoa. Cada visita cria seu
próprio Respondente sob demanda (alias sequencial) e o identifica pela sessão do
navegador; reabrir o mesmo link no mesmo navegador retoma de onde parou, sem repetir
o que já foi respondido. Um navegador diferente que abra o mesmo link é tratado como
um respondente novo.

Fluxo: consentimento (duas declarações obrigatórias) -> perfil (tempo na organização,
modalidade de trabalho, nome se identificada) -> uma pergunta por página, cruzando
todos os domínios em sequência única (revisão de UX de 2026-07-29 — reduz distração
em relação a mostrar um domínio inteiro por página) -> perguntas abertas (opcionais)
-> conclusão. `_proximo_passo` decide sempre a próxima etapa a partir do estado do
Respondente, num único lugar."""

import random

from django import forms
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
from avaliacoes.services.calculo_risco import calcular_dominio
from avaliacoes.services.questionario import itens_em_ordem, posicao_item, proximo_item_pendente
from instrumentos.models import Dominio, Item


def _get_aplicacao_ou_404(aplicacao_token) -> Aplicacao:
    return get_object_or_404(Aplicacao, token=aplicacao_token)


def _chave_sessao(aplicacao: Aplicacao) -> str:
    return f"respondente_id__aplicacao_{aplicacao.pk}"


def _get_respondente_da_sessao(request, aplicacao: Aplicacao) -> Respondente | None:
    respondente_id = request.session.get(_chave_sessao(aplicacao))
    if not respondente_id:
        return None
    return Respondente.objects.filter(pk=respondente_id, aplicacao=aplicacao).first()


def _gerar_alias_anonimo(aplicacao: Aplicacao) -> str:
    """Sorteia um número não sequencial pro alias (2026-08-06) — antes era
    `count()+1`, ou seja, literalmente a ordem de chegada de quem começou a
    responder primeiro. Combinado com contexto de campo ("vi fulano pegando o
    celular assim que mandei o link"), isso permitia reidentificar quem respondeu o
    quê. Sorteando um número aleatório sem relação com a ordem de chegada, essa
    pista deixa de existir. Confere colisão dentro da mesma Aplicacao (baixa chance
    com 9000 valores possíveis, mas o link fica aberto indefinidamente)."""
    existentes = set(aplicacao.respondentes.values_list("alias_anonimo", flat=True))
    while True:
        candidato = f"Respondente {random.randint(1000, 9999)}"
        if candidato not in existentes:
            return candidato


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


def _recalcular_dominios_do_respondente(respondente: Respondente) -> None:
    """Chamado assim que `concluido_em` é gravado pela primeira vez (ver
    `_proximo_passo` abaixo). Os domínios que este respondente respondeu já tinham
    sido calculados um instante antes (`calcular_dominio` roda a cada resposta, em
    `responder_pergunta`) — nesse instante `concluido_em` ainda era `None`, e
    `calcular_dominio` só conta respondentes já concluídos (2026-08-06). Sem isso, a
    própria contribuição de quem acabou de terminar ficaria de fora do(s) domínio(s)
    que ele respondeu por último, até algo mais recalculá-los."""
    dominios = Dominio.objects.filter(itens__respostas__respondente=respondente).distinct()
    for dominio in dominios:
        calcular_dominio(respondente.aplicacao, dominio)


def _proximo_passo(respondente: Respondente):
    aplicacao = respondente.aplicacao
    atualizar_status_aplicacao(aplicacao.pk)

    if not _perfil_preenchido(respondente):
        return redirect("avaliacoes:responder_perfil", aplicacao_token=aplicacao.token)

    proximo_item = proximo_item_pendente(respondente)
    if proximo_item:
        return redirect("avaliacoes:responder_pergunta", aplicacao_token=aplicacao.token, item_pk=proximo_item.pk)

    # A partir daqui, todos os itens de todos os domínios já foram respondidos.
    # `concluido_em` passa a ser gravado aqui — não depende mais de visitar a etapa
    # de perguntas abertas (que continua opcional em conteúdo E agora também em
    # visita: quem termina os domínios e fecha a aba já conta como concluído, mesmo
    # sem ter passado por essa tela). Achado de 2026-08-06: um respondente que
    # respondeu 76 de 76 itens nunca aparecia como "concluído" no painel só porque
    # não tinha visitado a última tela — confundia contagem de N entre o painel e o
    # relatório (que já contava esse domínio de qualquer forma).
    if not respondente.concluido_em:
        respondente.concluido_em = timezone.now()
        respondente.save(update_fields=["concluido_em"])
        _recalcular_dominios_do_respondente(respondente)

    if not respondente.perguntas_abertas_respondidas_em:
        return redirect("avaliacoes:responder_perguntas_abertas", aplicacao_token=aplicacao.token)

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


def _construir_form_item(item: Item, respondente: Respondente, data=None) -> forms.Form:
    valor_existente = (
        Resposta.objects.filter(respondente=respondente, item=item).values_list("valor_bruto", flat=True).first()
    )
    choices = sorted(item.dominio.escala_labels.items(), key=lambda kv: int(kv[0]))
    opcoes = [(valor, rotulo) for valor, rotulo in choices]

    campo = forms.ChoiceField(
        label=item.texto,
        choices=opcoes,
        widget=forms.RadioSelect,
        initial=str(valor_existente) if valor_existente is not None else None,
    )
    formulario_item = type("FormularioItem", (forms.Form,), {"resposta": campo})
    return formulario_item(data)


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
            respondente = Respondente.objects.create(
                aplicacao=aplicacao,
                alias_anonimo=_gerar_alias_anonimo(aplicacao),
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
    # `concluido_em` sozinho não significa mais "terminou tudo" (2026-08-06) — agora é
    # gravado assim que os domínios acabam, antes até de perguntas abertas (opcional).
    # Só bloqueia esta tela quando as duas etapas já foram concluídas de verdade.
    if respondente.concluido_em and respondente.perguntas_abertas_respondidas_em:
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


def _cor_barra_progresso(percentual: float) -> str:
    """Interpola de âmbar (início) pra verde (perto do fim) conforme o progresso —
    pedido explícito do usuário pra dar uma pista visual contínua de avanço, além do
    número "Pergunta N de T"."""
    inicio = (245, 158, 11)  # âmbar
    fim = (34, 197, 94)  # verde
    fracao = max(0.0, min(1.0, percentual / 100))
    r = round(inicio[0] + (fim[0] - inicio[0]) * fracao)
    g = round(inicio[1] + (fim[1] - inicio[1]) * fracao)
    b = round(inicio[2] + (fim[2] - inicio[2]) * fracao)
    return f"rgb({r}, {g}, {b})"


def responder_pergunta(request, aplicacao_token, item_pk):
    aplicacao = _get_aplicacao_ou_404(aplicacao_token)
    respondente = _get_respondente_da_sessao(request, aplicacao)
    if not respondente:
        return redirect("avaliacoes:responder_consentimento", aplicacao_token=aplicacao_token)
    if _coleta_encerrada(aplicacao, respondente):
        return render(request, "avaliacoes/questionario_encerrado.html", {"aplicacao": aplicacao})
    if not _perfil_preenchido(respondente):
        return redirect("avaliacoes:responder_perfil", aplicacao_token=aplicacao_token)
    # `concluido_em` sozinho não significa mais "terminou tudo" (2026-08-06) — agora é
    # gravado assim que os domínios acabam, antes até de perguntas abertas (opcional).
    # Só bloqueia esta tela quando as duas etapas já foram concluídas de verdade.
    if respondente.concluido_em and respondente.perguntas_abertas_respondidas_em:
        return redirect("avaliacoes:responder_concluido", aplicacao_token=aplicacao_token)

    todos_itens = itens_em_ordem(aplicacao)
    item = get_object_or_404(Item, pk=item_pk)
    if item not in todos_itens:
        return redirect("avaliacoes:responder_consentimento", aplicacao_token=aplicacao_token)

    if request.method == "POST":
        form = _construir_form_item(item, respondente, data=request.POST)
        if form.is_valid():
            Resposta.objects.update_or_create(
                respondente=respondente,
                item=item,
                defaults={"valor_bruto": int(form.cleaned_data["resposta"])},
            )

            # Recalcula o agregado do domínio (todas as Respostas de todos os
            # Respondentes da Aplicacao até agora) a cada resposta — idempotente,
            # sem isso EscoreDominio/ClassificacaoRisco/PlanoDeAcao nunca nasceriam
            # a partir do fluxo real de resposta.
            calcular_dominio(aplicacao, item.dominio)

            return _proximo_passo(respondente)
    else:
        form = _construir_form_item(item, respondente)

    indice = todos_itens.index(item)
    progresso = posicao_item(aplicacao, item)
    percentual = progresso["atual"] / progresso["total"] * 100

    if indice == 0:
        url_anterior = reverse("avaliacoes:responder_perfil", args=[aplicacao_token])
    else:
        url_anterior = reverse(
            "avaliacoes:responder_pergunta", args=[aplicacao_token, todos_itens[indice - 1].pk]
        )

    return render(
        request,
        "avaliacoes/questionario_pergunta.html",
        {
            "respondente": respondente,
            "dominio": item.dominio,
            "item": item,
            "form": form,
            "progresso": progresso,
            "percentual_progresso": percentual,
            "cor_barra_progresso": _cor_barra_progresso(percentual),
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
    # `concluido_em` sozinho não significa mais "terminou tudo" (2026-08-06) — agora é
    # gravado assim que os domínios acabam, antes até de perguntas abertas (opcional).
    # Só bloqueia esta tela quando as duas etapas já foram concluídas de verdade.
    if respondente.concluido_em and respondente.perguntas_abertas_respondidas_em:
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

    todos_itens = itens_em_ordem(aplicacao)
    url_anterior = (
        reverse("avaliacoes:responder_pergunta", args=[aplicacao_token, todos_itens[-1].pk])
        if todos_itens
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
