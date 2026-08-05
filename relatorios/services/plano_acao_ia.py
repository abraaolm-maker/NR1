"""Refinamento do Plano de Ação por IA (pedido do usuário, 2026-07-29).

Diferente do parecer técnico (Seção 8 do CLAUDE.md), o Plano de Ação SEMPRE nasce
automaticamente, de forma síncrona e sem IA, dentro de `calculo_risco.py::
_gerar_plano_de_acao_se_necessario` — com o texto padrão do catálogo (`CatalogoAcao`).
Isso continua acontecendo, sem mudança: o questionário público não pode depender de
uma chamada de rede à Anthropic no meio do fluxo do respondente.

Este módulo é uma etapa OPCIONAL, disparada sob demanda pelo profissional responsável
(botão "Refinar planos de ação com IA" na tela do Relatório, mesmo padrão do parecer
técnico) — nunca automática. Ela pega os `PlanoDeAcao` já existentes (gerados a partir
do catálogo) e pede à IA uma versão mais específica e contextualizada da medida,
usando o texto do catálogo como ponto de partida, não como substituto.

A IA nunca decide banda, nunca cria ou remove um PlanoDeAcao — só reescreve os campos
`medida`, `hierarquia` e `indicador` de planos já existentes (Seção 8.1 do CLAUDE.md:
a IA interpreta, não calcula nem decide classificação).
"""

import json

from django.utils import timezone

from relatorios.models import Relatorio
from relatorios.services.analise_ia import MODEL

SYSTEM_PROMPT_PLANO = """Você é um assistente técnico que refina o Plano de Ação de um \
Inventário de Risco Psicossocial (NR-01/GRO-PGR). Cada item de entrada já tem uma medida \
padrão vinda de um catálogo pré-definido, associada a um domínio com Banda Moderado, Alto \
ou Crítico. Regras obrigatórias:

1. Use a medida padrão do catálogo (campo "medida_catalogo") como ponto de partida, nunca \
como substituto — sua função é tornar a medida mais específica e acionável pra este GHE em \
particular, considerando o escore, a prevalência (percentual de respondentes na faixa \
elevada) e as evidências complementares informadas, nunca inventar dados que não vieram no \
JSON de entrada.

2. Nunca rebaixe a hierarquia de controle informada em "hierarquia_catalogo" — pode manter \
a mesma categoria ou subir pra uma categoria mais preventiva (eliminação é sempre a mais \
preventiva, seguida de organização do trabalho, gestão/administrativo, e resposta imediata \
somente para evento grave confirmado). Nunca sugira treinamento ou suporte psicológico \
individual como PRIMEIRA linha de ação quando a causa for organizacional.

3. Se o domínio tiver "evento_grave_confirmado": true, a medida deve obrigatoriamente \
tratar como prioridade máxima cessar a exposição da pessoa envolvida e proteger contra \
retaliação, mantendo hierarquia_controle "resposta_imediata".

4. A medida final deve ser concreta o suficiente pra um responsável real conseguir executar \
e verificar (quem faz o quê, com que critério de conclusão) — evite recomendações vagas do \
tipo "melhorar a comunicação" sem dizer como.

5. Gere uma entrada em "planos_refinados" para CADA domínio recebido no JSON de entrada, \
sem pular nenhum e sem juntar dois domínios numa única entrada.

6. PROIBIDO usar o caractere hífen ou travessão (-, – ou —) em qualquer campo de texto, sob \
qualquer circunstância, mesmo dentro de palavra composta ou lista. Reescreva com vírgula, a \
conjunção "e", parênteses ou dois pontos. Nunca use qualquer expressão que sugira que este \
texto foi redigido por inteligência artificial, modelo de linguagem ou automação."""

PLANO_TOOL = {
    "name": "refinar_plano_de_acao",
    "description": (
        "Registra a versão refinada da medida de cada item do Plano de Ação, a partir da "
        "medida padrão do catálogo e do contexto específico do domínio/GHE."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "planos_refinados": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ghe": {"type": "string"},
                        "dominio": {"type": "string"},
                        "medida": {
                            "type": "string",
                            "description": "Medida específica e acionável para este GHE, a partir da medida do catálogo.",
                        },
                        "hierarquia_controle": {
                            "type": "string",
                            "enum": ["eliminacao", "organizacao", "gestao", "resposta_imediata"],
                        },
                        "indicador": {
                            "type": "string",
                            "description": "Indicador de acompanhamento concreto para verificar se a medida funcionou.",
                        },
                    },
                    "required": ["ghe", "dominio", "medida", "hierarquia_controle", "indicador"],
                },
            },
        },
        "required": ["planos_refinados"],
    },
}


def montar_payload_planos(relatorio_id: int) -> dict:
    """Monta o JSON de entrada: um item por PlanoDeAcao já existente e ligado a este
    relatório (nunca inclui domínio suprimido por confidencialidade — esses nunca
    geram PlanoDeAcao, ver calculo_risco.py::_gerar_plano_de_acao_se_necessario)."""
    relatorio = Relatorio.objects.select_related("unidade__empresa").get(pk=relatorio_id)

    planos_payload = []
    for aplicacao in relatorio.aplicacoes.select_related("ghe").all():
        for escore in aplicacao.escores_dominio.select_related("dominio", "classificacao_risco").all():
            classificacao_risco = getattr(escore, "classificacao_risco", None)
            if classificacao_risco is None:
                continue
            plano = classificacao_risco.planos_de_acao.first()
            if plano is None:
                continue
            planos_payload.append(
                {
                    "ghe": aplicacao.ghe.nome,
                    "dominio": escore.dominio.codigo,
                    "nome_dominio": escore.dominio.nome,
                    "banda": classificacao_risco.banda,
                    "escore": float(escore.escore),
                    "percentual_elevados": float(escore.percentual_elevados),
                    "evidencias_convergentes": classificacao_risco.evidencias_convergentes,
                    "evento_grave_confirmado": classificacao_risco.evento_grave_confirmado,
                    "medida_catalogo": plano.medida,
                    "hierarquia_catalogo": plano.hierarquia or None,
                }
            )

    return {
        "empresa": relatorio.unidade.empresa.nome,
        "unidade": relatorio.unidade.nome,
        "planos": planos_payload,
    }


def _validar_cobertura_planos(payload: dict, resultado: dict) -> None:
    """Garante que a IA devolveu uma entrada refinada pra cada plano enviado — mesmo
    achado do parecer técnico (2026-07-29): sem essa checagem, o modelo pode devolver
    uma lista parcial silenciosamente."""
    esperados = {(p["ghe"], p["dominio"]) for p in payload["planos"]}
    recebidos = {(p.get("ghe"), p.get("dominio")) for p in resultado.get("planos_refinados", [])}
    faltando = esperados - recebidos
    if faltando:
        raise RuntimeError(
            f"A IA devolveu um plano de ação incompleto (faltam {len(faltando)} domínio(s) "
            "de um total esperado). Tente refinar novamente."
        )


def gerar_planos_refinados(payload: dict, client=None) -> dict:
    """Chama a API da Anthropic com tool_choice forçado — mesmo padrão de
    `analise_ia.py::gerar_parecer`. `client` é injetável pra teste sem rede."""
    if client is None:
        import anthropic

        from relatorios.services.chaves_api import obter_valor_chave_ativa

        api_key = obter_valor_chave_ativa()
        if not api_key:
            raise RuntimeError(
                "Nenhuma chave de API do Claude ativa. Cadastre e selecione uma em "
                "Relatórios > Chaves de API do Claude."
            )
        client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        system=SYSTEM_PROMPT_PLANO,
        tools=[PLANO_TOOL],
        tool_choice={"type": "tool", "name": "refinar_plano_de_acao"},
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
    )

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "refinar_plano_de_acao":
            resultado = block.input
            _validar_cobertura_planos(payload, resultado)
            return resultado

    raise RuntimeError("Resposta da IA não trouxe o tool_use esperado (refinar_plano_de_acao).")


def gerar_e_salvar_planos_refinados(relatorio_id: int, client=None) -> int:
    """Orquestra o fluxo completo: monta o payload, chama a IA, e sobrescreve
    medida/hierarquia/indicador dos PlanoDeAcao já existentes (nunca cria nem remove
    um plano). Retorna quantos planos foram atualizados."""
    from avaliacoes.models import ClassificacaoRisco, PlanoDeAcao

    payload = montar_payload_planos(relatorio_id)
    if not payload["planos"]:
        raise RuntimeError("Este relatório não tem nenhum Plano de Ação gerado para refinar.")

    resultado = gerar_planos_refinados(payload, client=client)

    relatorio = Relatorio.objects.select_related("unidade").get(pk=relatorio_id)
    planos_por_chave = {}
    for aplicacao in relatorio.aplicacoes.select_related("ghe").all():
        for cr in ClassificacaoRisco.objects.filter(escore_dominio__aplicacao=aplicacao).select_related(
            "escore_dominio__dominio"
        ):
            plano = cr.planos_de_acao.first()
            if plano is not None:
                planos_por_chave[(aplicacao.ghe.nome, cr.escore_dominio.dominio.codigo)] = plano

    atualizados = 0
    for item in resultado["planos_refinados"]:
        plano = planos_por_chave.get((item["ghe"], item["dominio"]))
        if plano is None:
            continue
        plano.medida = item["medida"]
        plano.hierarquia = item["hierarquia_controle"]
        plano.indicador = item["indicador"]
        plano.save(update_fields=["medida", "hierarquia", "indicador"])
        atualizados += 1

    relatorio.planos_refinados_em = timezone.now()
    relatorio.save(update_fields=["planos_refinados_em"])

    return atualizados
