"""API de análise com Claude (CLAUDE.md Etapa 5 / Seção 8).

SÍNCRONO por decisão explícita (2026-07-17): o projeto está em SQLite, sem Celery/Redis
configurado, e é uso interno de uma empresa por vez — não precisa lidar com concorrência
alta ainda. Mas as três funções abaixo são puras: recebem IDs (nunca um `request`/
`response` do Django) e devolvem/persistem resultado. Se o projeto crescer pra
multi-empresa e a latência da chamada à IA incomodar, basta envolver
`gerar_e_salvar_parecer` numa task Celery (`@shared_task`) sem reescrever nada aqui.

A IA nunca decide classificação nem altera número calculado (Seção 8.1) — só recebe o
JSON já calculado pelo backend e devolve texto técnico estruturado via tool use forçado
(`tool_choice`), que é o mecanismo de saída estruturada da API da Anthropic hoje.
"""

import json

from avaliacoes.models import IndicadorIndireto, StatusCriterioVersao
from relatorios.models import Relatorio

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """Você é um assistente técnico que redige o parecer de um Inventário de \
Risco Psicossocial (NR-01/GRO-PGR) a partir de escores JÁ CALCULADOS por um motor \
determinístico. Regras obrigatórias:

1. Nunca invente números — use apenas os valores que vêm no JSON de entrada (escore, \
classificação, severidade, probabilidade, banda). Você não recalcula nem reclassifica nada.
2. Use linguagem técnica adequada a um documento de PGR: evite tom alarmista e evite \
linguagem clínica/diagnóstica sobre trabalhadores individuais — o foco é organizacional.
3. Sempre cite explicitamente de qual GHE e de qual domínio/subescala cada achado vem.
4. Para todo risco classificado como Elevado ou Crítico, sugira ao menos uma medida \
preventiva coerente com a NR-01 — mudança organizacional (processo, carga, escala, \
liderança, comunicação), nunca tratamento individual do trabalhador.
5. Termine sempre deixando claro, no campo "aviso_minuta", que este é um documento em \
minuta técnica, sujeito a revisão e assinatura do profissional legalmente habilitado \
responsável pelo PGR."""

PARECER_TOOL = {
    "name": "gerar_parecer_tecnico",
    "description": (
        "Registra o parecer técnico estruturado do Inventário de Risco Psicossocial, "
        "a partir dos escores e classificações já calculados pelo backend."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sintese_executiva": {
                "type": "string",
                "description": "Visão geral do ciclo de avaliação — GHEs cobertos, panorama geral de risco.",
            },
            "pareceres_por_dominio": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ghe": {"type": "string"},
                        "instrumento": {"type": "string"},
                        "dominio": {"type": "string"},
                        "classificacao": {"type": "string"},
                        "banda": {"type": "string"},
                        "parecer": {"type": "string"},
                    },
                    "required": ["ghe", "instrumento", "dominio", "classificacao", "banda", "parecer"],
                },
            },
            "riscos_prioritarios": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ghe": {"type": "string"},
                        "dominio": {"type": "string"},
                        "banda": {"type": "string"},
                        "justificativa": {"type": "string"},
                    },
                    "required": ["ghe", "dominio", "banda", "justificativa"],
                },
            },
            "recomendacoes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ghe": {"type": "string"},
                        "dominio": {"type": "string"},
                        "banda": {"type": "string"},
                        "medida_preventiva": {"type": "string"},
                    },
                    "required": ["ghe", "dominio", "banda", "medida_preventiva"],
                },
            },
            "aviso_minuta": {"type": "string"},
        },
        "required": [
            "sintese_executiva",
            "pareceres_por_dominio",
            "riscos_prioritarios",
            "recomendacoes",
            "aviso_minuta",
        ],
    },
}


def montar_payload_relatorio(relatorio_id: int) -> dict:
    """Monta o JSON de entrada da IA: só dados agregados por domínio/GHE, nunca
    resposta bruta individual identificável (Seção 8.1). Domínios suprimidos por
    confidencialidade (N < mínimo) entram só com a flag de supressão, sem o escore —
    a supressão vale ponta a ponta, não só na tela (Seção 3, princípio 3)."""

    relatorio = Relatorio.objects.select_related("unidade__empresa", "criterio_versao").get(pk=relatorio_id)

    payload = {
        "empresa": relatorio.unidade.empresa.nome,
        "unidade": relatorio.unidade.nome,
        "periodo_inicio": relatorio.periodo_inicio.isoformat(),
        "periodo_fim": relatorio.periodo_fim.isoformat(),
        "criterio_versao": relatorio.criterio_versao.codigo,
        "criterio_ratificado": relatorio.criterio_versao.status == StatusCriterioVersao.RATIFICADO,
        "ghes": [],
    }

    for aplicacao in relatorio.aplicacoes.select_related("ghe", "instrumento").all():
        indicadores = IndicadorIndireto.objects.filter(ghe=aplicacao.ghe, convergente=True).select_related(
            "dominio_relacionado"
        )
        ghe_payload = {
            "ghe": aplicacao.ghe.nome,
            "setor": aplicacao.ghe.setor,
            "instrumento": aplicacao.instrumento.codigo,
            "tipo_aplicacao": aplicacao.tipo,
            "dominios": [],
            "indicadores_indiretos": [
                {
                    "tipo": indicador.tipo,
                    "periodo_referencia": indicador.periodo_referencia.isoformat(),
                    "descricao": indicador.descricao,
                    "dominio_relacionado": (
                        indicador.dominio_relacionado.codigo if indicador.dominio_relacionado else None
                    ),
                }
                for indicador in indicadores
            ],
        }

        for escore in aplicacao.escores_dominio.select_related("dominio", "classificacao_risco").all():
            if escore.suprimido_por_confidencialidade:
                ghe_payload["dominios"].append(
                    {
                        "dominio": escore.dominio.codigo,
                        "nome": escore.dominio.nome,
                        "suprimido_por_confidencialidade": True,
                    }
                )
                continue

            dominio_payload = {
                "dominio": escore.dominio.codigo,
                "nome": escore.dominio.nome,
                "escore": float(escore.escore),
                "classificacao": escore.classificacao,
                "severidade": escore.severidade,
                "n_respondentes": escore.n_respondentes,
                "suprimido_por_confidencialidade": False,
            }
            classificacao_risco = getattr(escore, "classificacao_risco", None)
            if classificacao_risco is not None:
                dominio_payload.update(
                    {
                        "probabilidade": classificacao_risco.probabilidade,
                        "score": classificacao_risco.score,
                        "banda": classificacao_risco.banda,
                        "prazo_dias_plano_de_acao": classificacao_risco.prazo_dias_plano_de_acao,
                        "evento_grave_confirmado": classificacao_risco.evento_grave_confirmado,
                        "evidencias_convergentes": classificacao_risco.evidencias_convergentes,
                    }
                )
            ghe_payload["dominios"].append(dominio_payload)

        payload["ghes"].append(ghe_payload)

    return payload


def gerar_parecer(payload: dict, client=None) -> dict:
    """Chama a API da Anthropic com tool_choice forçado — a resposta É o JSON
    estruturado, sem parsing frágil de texto livre. `client` é injetável pra teste
    (ver relatorios/tests.py) sem precisar de rede nem de ANTHROPIC_API_KEY."""

    if client is None:
        import anthropic

        client = anthropic.Anthropic()  # lê ANTHROPIC_API_KEY do ambiente

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[PARECER_TOOL],
        tool_choice={"type": "tool", "name": "gerar_parecer_tecnico"},
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
    )

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "gerar_parecer_tecnico":
            return block.input

    raise RuntimeError("Resposta da IA não trouxe o tool_use esperado (gerar_parecer_tecnico).")


def gerar_e_salvar_parecer(relatorio_id: int, client=None) -> Relatorio:
    """Orquestra o fluxo completo e persiste o resultado. `Relatorio.status` continua
    "aguardando_revisão" (default do model) — gerar o parecer não aprova nem assina
    nada (Seção 8.1)."""

    payload = montar_payload_relatorio(relatorio_id)
    parecer = gerar_parecer(payload, client=client)

    relatorio = Relatorio.objects.get(pk=relatorio_id)
    relatorio.parecer_ia = parecer
    relatorio.save(update_fields=["parecer_ia"])
    return relatorio
