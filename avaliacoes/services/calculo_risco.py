"""Motor de cálculo integrado (CLAUDE.md Etapa 4 / Seção 7).

Busca as Respostas de uma Aplicacao, monta as estruturas que risk_engine.py espera e
persiste o resultado em EscoreDominio/ClassificacaoRisco, gerando PlanoDeAcao
automaticamente quando a banda não é Aceitável (Seção 4.3). O cálculo em si nunca é
reimplementado aqui — só chama `risk_engine.avaliar_dominio()`.

Os parâmetros (thresholds, severidade, matriz, N mínimo, limiar de evento grave) vêm
sempre do `CriterioVersao` da Aplicacao, nunca de instrumentos.Dominio diretamente nem
de uma constante solta — é o que garante que o cálculo de uma Aplicacao antiga
continue reproduzível mesmo que os seeds ou o risk_engine.py mudem depois (Seção 7.8).
"""

from datetime import timedelta
from decimal import Decimal

from django.db import models as django_models
from django.db import transaction
from django.utils import timezone

from avaliacoes.models import (
    Aplicacao,
    CatalogoAcao,
    ClassificacaoRisco,
    ConformidadeChecklist,
    EscoreDominio,
    EscoreRespondente,
    GHE,
    IndicadorIndireto,
    PlanoDeAcao,
    Respondente,
    Resposta,
    RespostaChecklistTriangulacao,
    StatusPlanoDeAcao,
)
from avaliacoes.risk_engine_lib import risk_engine
from avaliacoes.services.criterio_versao import verificar_criterio_versao_atualizado
from instrumentos.models import Dominio, Item


BANDA_ORDEM = {
    "Crítico": 4,
    "Alto": 3,
    "Moderado": 2,
    "Aceitável": 1,
}


def media_nacional_comparavel(dominio: Dominio) -> float | None:
    """Normaliza a média nacional publicada (bruta, 1-5, manual COPSOQ Portugal 2013)
    pra escala 0-100 já invertida por polaridade — mesma direção do EscoreDominio.escore
    (maior = mais risco), pra comparar direto "sua empresa X | média nacional Y". Usada
    tanto no PDF (`relatorios/services/pdf.py`) quanto na tela do painel
    (`avaliacoes/painel_views.py::aplicacao_detail`) — CLAUDE.md Seção 6.13.

    Retorna None quando não há valor publicado ou quando o domínio tem polaridade mista
    (Confiança horizontal/vertical) — inverter a média agregada do manual exigiria o
    dado item a item que o manual não publica, então não arriscamos uma conta enganosa."""
    if dominio.referencia_media_nacional is None:
        return None
    polaridades = set(dominio.itens.values_list("polaridade", flat=True))
    if len(polaridades) != 1:
        return None
    valor = float(dominio.referencia_media_nacional)
    if polaridades.pop() == "PROTETIVO":
        valor = (dominio.escala_max + dominio.escala_min) - valor
    amplitude = dominio.escala_max - dominio.escala_min
    return round((valor - dominio.escala_min) / amplitude * 100, 1)


def _thresholds_do_criterio(aplicacao: Aplicacao, dominio: Dominio) -> "risk_engine.Thresholds":
    criterio = aplicacao.criterio_versao
    try:
        dados = criterio.thresholds_por_dominio[dominio.instrumento.codigo][dominio.codigo]
    except KeyError as exc:
        raise ValueError(
            f'CriterioVersao "{criterio.codigo}" não tem thresholds para '
            f'"{dominio.instrumento.codigo}" / "{dominio.codigo}".'
        ) from exc
    return risk_engine.Thresholds(baixo_max=float(dados["baixo_max"]), moderado_max=float(dados["moderado_max"]))


def contar_evidencias_convergentes(aplicacao: Aplicacao, dominio: Dominio) -> int:
    """CLAUDE.md Seção 7.5: conta as evidências complementares convergentes com o
    domínio. Duas fontes:
    1. IndicadorIndireto do GHE (absenteísmo, turnover, CAT/CID-F, relato de
       entrevista, ou "checklist não conforme" cadastrado manualmente).
    2. RespostaChecklistTriangulacao "Não conforme" desta Aplicacao (Prompt 09), só de
       itens `tipo=observacao` (achado em 2026-07-29: itens `tipo=entrevista` são
       perguntas abertas, sem conformidade válida — nunca devem contar aqui) e só
       quando o item não tem `dominio_codigo_relacionado` (evidência geral) ou tem o
       mesmo código do domínio calculado (mesma semântica do `dominio_relacionado`
       nulo/preenchido do IndicadorIndireto, ver Seção 4.2). Conta no máximo 1, como um
       único tipo de evidência — o mesmo peso que os outros 4 tipos têm na regra
       0/1/2+ do risk_engine."""
    indicadores = IndicadorIndireto.objects.filter(ghe=aplicacao.ghe, convergente=True).filter(
        django_models.Q(dominio_relacionado__isnull=True) | django_models.Q(dominio_relacionado=dominio)
    ).count()

    tem_checklist_nao_conforme = RespostaChecklistTriangulacao.objects.filter(
        respondente__coleta__aplicacao=aplicacao,
        conformidade=ConformidadeChecklist.NAO_CONFORME,
        item__tipo="observacao",
    ).filter(
        django_models.Q(item__dominio_codigo_relacionado="") | django_models.Q(item__dominio_codigo_relacionado=dominio.codigo)
    ).exists()

    return indicadores + (1 if tem_checklist_nao_conforme else 0)


def _recalcular_indice_geral(respondente_id: int) -> None:
    """Índice geral = média dos EscoreRespondente (D1-D9) já calculados para este
    respondente até agora — mesma definição da coluna "Índice geral" da planilha
    Pontuacao_anonima. Recalculado a cada domínio novo respondido; domínios ainda não
    respondidos simplesmente não entram na média (parcial até a aplicação terminar)."""
    escores = list(
        EscoreRespondente.objects.filter(respondente_id=respondente_id).values_list("escore", flat=True)
    )
    if not escores:
        return
    media = sum(escores) / len(escores)
    Respondente.objects.filter(pk=respondente_id).update(indice_geral=Decimal(str(round(float(media), 2))))


_ORDEM_PROFUNDIDADE = {"curta": 1, "media": 2, "longa": 3}


def itens_da_aplicacao(aplicacao: Aplicacao, dominio: Dominio):
    """Itens de um domínio que valem pra esta Aplicacao — normalmente todos, mas no
    COPSOQ Oficial (CLAUDE.md — 3 profundidades curta/média/longa) só entram os itens
    com `profundidade` em branco (sempre incluído) ou cujo nível é <= o nível escolhido
    na Aplicacao (curta ⊆ média ⊆ longa, por conteúdo do item — Seção sobre o COPSOQ
    Oficial)."""
    qs = dominio.itens.all()
    if not aplicacao.profundidade:
        return qs
    nivel_aplicacao = _ORDEM_PROFUNDIDADE[aplicacao.profundidade]
    ids_validos = [
        item.id
        for item in qs
        if not item.profundidade or _ORDEM_PROFUNDIDADE[item.profundidade] <= nivel_aplicacao
    ]
    return qs.filter(id__in=ids_validos)


def dominios_da_aplicacao(aplicacao: Aplicacao) -> list[Dominio]:
    """Todos os Dominio do instrumento da Aplicacao que têm pelo menos um item válido
    pra esta profundidade — sempre genéricos, o mesmo conjunto vale para qualquer GHE
    (CLAUDE.md Seção 6.5). No COPSOQ Oficial, um domínio exclusivo da versão longa (ex.
    "Variação no trabalho") não aparece numa Aplicacao com profundidade=curta/média."""
    dominios = Dominio.objects.filter(instrumento=aplicacao.instrumento).select_related("instrumento")
    if not aplicacao.profundidade:
        return list(dominios)
    return [d for d in dominios if itens_da_aplicacao(aplicacao, d).exists()]


@transaction.atomic
def calcular_dominio(aplicacao: Aplicacao, dominio: Dominio) -> EscoreDominio:
    verificar_criterio_versao_atualizado(aplicacao.criterio_versao)

    evidencias_convergentes = contar_evidencias_convergentes(aplicacao, dominio)

    respostas_qs = Resposta.objects.filter(
        respondente__aplicacao=aplicacao, item__dominio=dominio
    ).select_related("item", "respondente")

    respostas = [
        risk_engine.RespostaItem(item_id=r.item.item_id, valor_bruto=r.valor_bruto) for r in respostas_qs
    ]
    if not respostas:
        raise ValueError(f'Nenhuma Resposta encontrada para "{dominio}" na Aplicacao #{aplicacao.pk}.')

    n_respondentes = respostas_qs.values("respondente_id").distinct().count()

    itens_por_id = {
        item.item_id: risk_engine.ItemInstrumento(
            id=item.item_id,
            polaridade=risk_engine.Polaridade(item.polaridade),
            evento_grave=item.evento_grave,
        )
        for item in dominio.itens.all()
    }

    # `avaliar_dominio` ainda calcula a Banda antiga (Severidade × Probabilidade por
    # evidências convergentes) internamente, mas esse resultado NÃO é mais usado pra
    # decidir a Banda persistida (achado de 2026-07-29, ver risk_engine.py::
    # calcular_risco_por_prevalencia) — só aproveitamos `resultado_dominio` (escore/
    # classificação/severidade), `suprimir` e `evento_grave_confirmado` daqui.
    resultado_dominio, resultado_risco_legado, suprimir = risk_engine.avaliar_dominio(
        codigo_dominio=dominio.codigo,
        respostas=respostas,
        itens_por_id=itens_por_id,
        thresholds=_thresholds_do_criterio(aplicacao, dominio),
        escala_min=dominio.escala_min,
        escala_max=dominio.escala_max,
        n_respondentes=n_respondentes,
        evidencias_convergentes=evidencias_convergentes,
    )

    # Calcular escore por respondente (planilha "Pontuacao_anonima" do Excel de
    # referência — prompts/04_pontuacao_anonima.md) e, a partir dele, a prevalência.
    thresholds = _thresholds_do_criterio(aplicacao, dominio)
    respondentes_ids = respostas_qs.values_list("respondente_id", flat=True).distinct()
    escores_por_respondente: list[float] = []
    for resp_id in respondentes_ids:
        respostas_resp = [
            risk_engine.RespostaItem(item_id=r.item.item_id, valor_bruto=r.valor_bruto)
            for r in respostas_qs if r.respondente_id == resp_id
        ]
        if respostas_resp:
            escore_resp = risk_engine.calcular_escore_respondente(
                respostas_resp, itens_por_id, dominio.escala_min, dominio.escala_max,
            )
            escores_por_respondente.append(escore_resp)
            EscoreRespondente.objects.update_or_create(
                respondente_id=resp_id,
                dominio=dominio,
                defaults={
                    "escore": Decimal(str(escore_resp)),
                    "classificacao": risk_engine.classificar_escore(escore_resp, thresholds).value,
                },
            )
            _recalcular_indice_geral(resp_id)

    criterio = aplicacao.criterio_versao
    prevalencia = risk_engine.calcular_prevalencia(
        escores_por_respondente,
        limite_elevado=float(criterio.limite_elevado),
        p1_threshold=float(criterio.prevalencia_p1),
        p2_threshold=float(criterio.prevalencia_p2),
    )

    # Diagnóstico GHE (prompts/06_diagnostico_ghe.md): a Prioridade que vale pro
    # diagnóstico primário é a prevalência (P1/P2/P3), OU "AGRUPAR" se o domínio está
    # suprimido por confidencialidade — nesse caso nem escore nem percentual são
    # exibidos (Seção 3 princípio 3), então a prioridade também não pode ser P1/P2/P3
    # (isso vazaria uma leitura do resultado através da prioridade sozinha).
    prioridade = risk_engine.Prioridade.AGRUPAR if suprimir else prevalencia.prioridade

    escore_dominio, _ = EscoreDominio.objects.update_or_create(
        aplicacao=aplicacao,
        dominio=dominio,
        defaults={
            "escore": Decimal(str(resultado_dominio.escore)),
            "classificacao": resultado_dominio.classificacao.value,
            "severidade": resultado_dominio.severidade,
            "n_respondentes": n_respondentes,
            "suprimido_por_confidencialidade": suprimir,
            "percentual_elevados": Decimal(str(prevalencia.percentual_elevados)),
            "prioridade": prioridade.value,
        },
    )

    # Banda/prazo vêm da Prioridade por prevalência (mesma lógica do semáforo COPSOQ),
    # não mais da matriz Severidade × Probabilidade (achado de 2026-07-29). Usa
    # `prevalencia.prioridade` (nunca a variável `prioridade` acima, que vira AGRUPAR
    # quando suprimido) — a supressão continua protegida da mesma forma que sempre
    # foi: os templates checam `suprimido_por_confidencialidade` antes de mostrar
    # Banda/escore, não porque o dado deixa de existir internamente.
    resultado_risco = risk_engine.calcular_risco_por_prevalencia(
        prioridade=prevalencia.prioridade,
        severidade=resultado_dominio.severidade,
        evento_grave_confirmado=resultado_risco_legado.evento_grave_confirmado,
    )

    classificacao_risco, _ = ClassificacaoRisco.objects.update_or_create(
        escore_dominio=escore_dominio,
        defaults={
            "evidencias_convergentes": evidencias_convergentes,
            "evento_grave_confirmado": resultado_risco.evento_grave_confirmado,
            "probabilidade": resultado_risco.probabilidade,
            "score": resultado_risco.score,
            "banda": resultado_risco.banda.value,
            "prazo_dias_plano_de_acao": resultado_risco.prazo_dias_plano_de_acao,
        },
    )

    _gerar_plano_de_acao_se_necessario(classificacao_risco, suprimido_por_confidencialidade=suprimir)

    alertas = contar_alertas_d9(aplicacao)
    Aplicacao.objects.filter(pk=aplicacao.pk).update(alertas_d9=alertas["alertas_d9"])
    aplicacao.alertas_d9 = alertas["alertas_d9"]

    return escore_dominio


def calcular_aplicacao(aplicacao: Aplicacao) -> list[EscoreDominio]:
    """Calcula todos os domínios/subescalas aplicáveis desta Aplicacao. Domínios sem
    nenhuma Resposta ainda são pulados (aplicação parcialmente respondida)."""
    resultados = []
    for dominio in dominios_da_aplicacao(aplicacao):
        tem_resposta = Resposta.objects.filter(
            respondente__aplicacao=aplicacao, item__dominio=dominio
        ).exists()
        if not tem_resposta:
            continue
        resultados.append(calcular_dominio(aplicacao, dominio))
    return resultados


def contar_alertas_d9(aplicacao: Aplicacao) -> dict:
    """Planilha `Alertas_agregados` do Excel de referência (prompts/05_alertas_agregados.md):
    por GHE, quantos respondentes marcaram um item de evento grave (D9.1/D9.2 no COPSOQ,
    `Item.evento_grave=True` de forma agnóstica de instrumento) com valor >= limiar do
    CriterioVersao. Diferente de `ClassificacaoRisco.evento_grave_confirmado` (booleano por
    domínio calculado) — esta é uma contagem de PESSOAS, agregada na Aplicacao inteira."""
    limiar = aplicacao.criterio_versao.limiar_evento_grave
    itens_graves = Item.objects.filter(
        dominio__instrumento=aplicacao.instrumento,
        evento_grave=True,
    ).values_list("pk", flat=True)

    alertas_d9 = (
        Resposta.objects.filter(
            respondente__aplicacao=aplicacao,
            item_id__in=itens_graves,
            valor_bruto__gte=limiar,
        )
        .values("respondente_id")
        .distinct()
        .count()
    )

    n_respondentes = aplicacao.respondentes.filter(concluido_em__isnull=False).count()

    return {"n_respondentes": n_respondentes, "alertas_d9": alertas_d9}


# Notas técnicas fixas por prioridade — planilha `Diagnostico_GHE` do Excel de
# referência (prompts/06_diagnostico_ghe.md). "{n_minimo}" é preenchido com
# `CriterioVersao.n_minimo_respondentes` no momento de montar o diagnóstico.
NOTAS_TECNICAS = {
    risk_engine.Prioridade.P1: "Prioridade coletiva elevada; triangular e controlar na fonte.",
    risk_engine.Prioridade.P2: "Resultado moderado; investigar causas e prevenir agravamento.",
    risk_engine.Prioridade.P3: "Manter controles e monitorar.",
    risk_engine.Prioridade.AGRUPAR: (
        "Microgrupo com N < {n_minimo}. Não divulgar resultado; ampliar coleta ou "
        "agregar somente exposições equivalentes."
    ),
}


def diagnostico_ghe(aplicacao: Aplicacao) -> list[dict]:
    """Uma linha por domínio já calculado desta Aplicacao, no formato da planilha
    `Diagnostico_GHE` do Excel de referência: N, escore, % elevados, classificação,
    prioridade, alerta protegido (só pra domínios com item `evento_grave=True`, ex.
    D9 no COPSOQ — verificado de forma agnóstica de instrumento) e nota técnica fixa."""
    n_minimo = aplicacao.criterio_versao.n_minimo_respondentes
    linhas = []
    for escore in aplicacao.escores_dominio.select_related("dominio").order_by("dominio__ordem"):
        dominio = escore.dominio
        tem_item_evento_grave = dominio.itens.filter(evento_grave=True).exists()
        alerta_protegido = None
        if tem_item_evento_grave:
            alertas = contar_alertas_d9(aplicacao)
            alerta_protegido = (
                "SEM ALERTA AGREGADO"
                if alertas["alertas_d9"] == 0
                else f"{alertas['alertas_d9']} respondente(s) com evento grave confirmado — ativar fluxo protegido."
            )

        prioridade = risk_engine.Prioridade(escore.prioridade)
        linhas.append(
            {
                "ghe": aplicacao.ghe.nome,
                "dominio": f"{dominio.codigo} - {dominio.nome}",
                "n": escore.n_respondentes,
                "escore": None if escore.suprimido_por_confidencialidade else escore.escore,
                "percentual_elevados": (
                    None if escore.suprimido_por_confidencialidade else escore.percentual_elevados
                ),
                "classificacao": "SUPRIMIDO" if escore.suprimido_por_confidencialidade else escore.classificacao,
                "prioridade": prioridade.value,
                "alerta_protegido": alerta_protegido,
                "nota_tecnica": NOTAS_TECNICAS[prioridade].format(n_minimo=n_minimo),
            }
        )
    return linhas


def criterio_classificacao_linhas(criterio_versao) -> list[dict]:
    """Critério que efetivamente decide a Banda hoje (achado de 2026-07-29): a
    Prioridade por prevalência, mesma lógica "semáforo" do manual COPSOQ Portugal 2013
    (p. 15) e da planilha de referência do projeto — substitui a antiga matriz
    Severidade × Probabilidade (`CriterioVersao.matriz_risco`, mantida no banco só
    como registro histórico de como as Aplicacoes antigas foram calculadas, nunca mais
    usada pra decidir Banda de cálculos novos). Usada tanto no PDF do relatório
    (`relatorios/services/pdf.py`) quanto na tela de Configurações de risco do painel."""
    p1 = criterio_versao.prevalencia_p1
    p2 = criterio_versao.prevalencia_p2
    return [
        {
            "prioridade": "P1",
            "condicao": f"≥ {int(float(p1) * 100)}% dos respondentes na faixa elevada",
            "banda": "Alto",
            "prazo_dias": 30,
        },
        {
            "prioridade": "P2",
            "condicao": f"≥ {int(float(p2) * 100)}% e < {int(float(p1) * 100)}% dos respondentes na faixa elevada",
            "banda": "Moderado",
            "prazo_dias": 90,
        },
        {
            "prioridade": "P3",
            "condicao": f"< {int(float(p2) * 100)}% dos respondentes na faixa elevada",
            "banda": "Aceitável",
            "prazo_dias": None,
        },
        {
            "prioridade": "—",
            "condicao": "Evento grave confirmado (violência, ameaça, assédio moral ou discriminação relatados)",
            "banda": "Crítico",
            "prazo_dias": 15,
        },
    ]


def _gerar_plano_de_acao_se_necessario(
    classificacao_risco: ClassificacaoRisco, suprimido_por_confidencialidade: bool
) -> None:
    if suprimido_por_confidencialidade:
        # CLAUDE.md Seção 3, princípio 3: N < mínimo suprime todo resultado agregado do
        # GHE, não só o escore na tela — um Plano de Ação citando domínio+banda vazaria
        # exatamente o que a supressão deveria esconder.
        return
    if classificacao_risco.banda == risk_engine.BandaRisco.ACEITAVEL.value:
        return
    if classificacao_risco.planos_de_acao.exists():
        return  # recalcular não deve duplicar plano já existente

    escore_dominio = classificacao_risco.escore_dominio
    dominio = escore_dominio.dominio
    ghe = escore_dominio.aplicacao.ghe
    prazo = None
    if classificacao_risco.prazo_dias_plano_de_acao is not None:
        prazo = timezone.now().date() + timedelta(days=classificacao_risco.prazo_dias_plano_de_acao)

    # Planilha `Catalogo_Acoes` do Excel de referência (prompts/07_catalogo_acoes.md):
    # a medida sugerida vem do catálogo pré-definido por (domínio, nível), pré-definido
    # pelo seed mas editável pelo admin — nunca reescrito aqui, só lido.
    catalogo = CatalogoAcao.objects.filter(dominio=dominio, nivel=escore_dominio.classificacao).first()

    PlanoDeAcao.objects.create(
        classificacao_risco=classificacao_risco,
        codigo=f"A{str(PlanoDeAcao.objects.count() + 1).zfill(2)}",
        medida=(
            catalogo.acao_sugerida
            if catalogo
            else (
                f'Definir e executar medida corretiva para o domínio "{dominio.nome}" '
                f"(banda {classificacao_risco.banda})."
            )
        ),
        hierarquia=catalogo.hierarquia if catalogo else "",
        evidencia_diagnostico=(
            f"{dominio.nome} classificado como {escore_dominio.classificacao} no GHE "
            f'"{ghe.nome}"; índice de risco {escore_dominio.escore} (escala 0-100), '
            f"N={escore_dominio.n_respondentes}."
        ),
        indicador=catalogo.indicador if catalogo else "",
        prazo=prazo,
        status=StatusPlanoDeAcao.PLANEJADA,
    )
