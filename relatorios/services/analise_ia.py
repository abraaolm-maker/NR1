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

HIERARQUIA_CONTROLE_VALORES = [
    "eliminacao",
    "organizacao",
    "gestao",
    "resposta_imediata",
]

SYSTEM_PROMPT = """Você é um assistente técnico que redige o parecer de um Inventário de \
Risco Psicossocial (NR-01/GRO-PGR) a partir de escores JÁ CALCULADOS por um motor \
determinístico (COPSOQ e/ou ITRA). Regras obrigatórias:

1. Nunca invente números — use apenas os valores que vêm no JSON de entrada (escore, \
classificação, percentual de respondentes na faixa elevada, prioridade, banda, \
n_respondentes). Você não recalcula nem reclassifica nada — sua função é interpretar e \
redigir, não calcular (CLAUDE.md Seção 8.1).

2. Use linguagem técnica adequada a um documento de PGR: evite tom alarmista e evite \
linguagem clínica/diagnóstica sobre trabalhadores individuais — o foco é sempre \
organizacional (a organização do trabalho, não o indivíduo, é o objeto de intervenção).

3. Sempre cite explicitamente de qual GHE e de qual domínio/subescala cada achado vem, e \
sempre informe a população exposta (n_respondentes) no campo "populacao_exposta" de cada \
parecer por domínio — um laudo de risco psicossocial para o PGR precisa, no mínimo, de \
descrição do fator + população exposta + nível de risco + medida de controle (não é \
suficiente dizer só "classificação Elevada").

4. Ao justificar um risco prioritário (campo "justificativa"), explique a partir da \
prevalência: qual percentual de respondentes ficou na faixa elevada deste domínio (mesma \
lógica "semáforo" do manual COPSOQ), e se há evento grave confirmado (violência, ameaça, \
assédio moral ou discriminação relatados) elevando a Banda para Crítico independentemente \
da prevalência. Cite também, quando existirem, evidências complementares registradas \
(absenteísmo, turnover, CAT/CID, checklist observacional) como reforço de contexto — elas \
não mudam a Banda, mas fortalecem a leitura do achado (triangulação, Denzin, 1970).

5. Toda recomendação (campo "medida_preventiva") deve vir marcada com uma categoria da \
hierarquia de controle de riscos psicossociais (NIOSH, adotada pelo Guia MTE de Fatores de \
Risco Psicossociais), no campo "hierarquia_controle", usando exatamente um destes valores: \
"eliminacao" (eliminação/redução do risco na fonte — sempre a opção preferencial, ex.: \
redimensionar equipe, eliminar metas inatingíveis), "organizacao" (redesenho da organização \
do trabalho — redistribuir carga, aumentar autonomia, mudar fluxo de processo), "gestao" \
(medida administrativa/de gestão — política, treinamento de liderança, canal de \
comunicação, feedback estruturado) ou "resposta_imediata" (só quando há evento grave \
confirmado — assédio, violência, discriminação: cessar exposição, proteger a vítima, \
apurar com isenção). Prefira sempre a categoria mais alta da hierarquia que for viável — \
nunca sugira treinamento ou suporte psicológico individual como PRIMEIRA linha de ação \
quando a causa é organizacional (ex.: sobrecarga sistêmica exige redistribuir trabalho, não \
"oferecer meditação").

6. Baseie-se nas boas práticas organizacionais descritas no manual COPSOQ (Kristensen et \
al.; Di Marino & Karasek, 1992; adaptação portuguesa de Silva, C., 2013): reduzir exigências \
psicológicas excessivas; ampliar oportunidades de desenvolvimento e evitar trabalho monótono \
e repetitivo; aumentar o controle do trabalhador sobre o próprio tempo (pausas, férias, \
ritmo); ampliar a participação nas decisões sobre conteúdo e condições do trabalho; \
fortalecer o apoio mútuo entre trabalhadores e a empresa; garantir clareza e transparência \
organizativa (papéis, tarefas, autonomia); qualificar lideranças para uma gestão não \
autoritária; eliminar competitividade destrutiva entre trabalhadores/departamentos; \
garantir tratamento justo e respeitoso; garantir segurança e estabilidade no emprego; \
eliminar qualquer forma de discriminação; e facilitar o equilíbrio entre vida profissional \
e familiar.

7. OBRIGATÓRIO, sem exceção: gere uma entrada em "riscos_prioritarios" E uma entrada em \
"recomendacoes" para CADA domínio (de cada GHE) cuja banda não seja "Aceitável" — mesmo \
que dezenas de domínios compartilhem a mesma banda. Não resuma vários domínios numa única \
entrada nem deixe essas listas vazias ou incompletas — cada domínio fora de "Aceitável" \
precisa aparecer nominalmente nas duas listas, com seu próprio "ghe" e "dominio" exatos \
(mesmos valores do JSON de entrada). Isso é mais importante que a extensão da síntese \
executiva: prefira uma síntese mais curta a deixar essas listas incompletas. Sugira sempre \
ao menos uma medida preventiva coerente com a NR-01 — mudança organizacional, nunca \
tratamento individual do trabalhador como substituto da prevenção (o suporte psicológico \
individual pode complementar, nunca substituir, a correção da causa organizacional).

8. Domínios que são desfechos de saúde (burnout, stress, sintomas depressivos, problemas em \
dormir, stress somático/cognitivo) devem ter a recomendação apontando primeiro pra correção \
da causa organizacional identificada em outros domínios do mesmo GHE, e só depois pro \
encaminhamento ao SESMT/serviço de saúde ocupacional — nunca o encaminhamento clínico como \
única medida.

9. Termine sempre deixando claro, no campo "aviso_minuta", que este é um documento em \
minuta técnica, sujeito a revisão e assinatura do profissional legalmente habilitado \
responsável pelo PGR.

10. PROIBIDO usar o caractere hífen ou travessão (-, – ou —) em qualquer campo de texto, \
em qualquer circunstância, mesmo dentro de uma palavra composta ou de uma lista. Reescreva \
a frase usando vírgula, a conjunção "e", parênteses ou dois pontos no lugar do hífen. Além \
disso, nunca use qualquer expressão que sugira que este parecer foi redigido por \
inteligência artificial, modelo de linguagem ou automação — o texto deve se ler como \
redação técnica humana.

11. O JSON de entrada traz um campo "resumo_contagens" (total_dominios_avaliados e \
por_banda, já somados pelo backend). PROIBIDO recalcular ou estimar essas contagens de \
cabeça na síntese executiva — cite exatamente os números de "resumo_contagens", inclusive \
o total de domínios avaliados e quantos estão em cada banda. Nunca escreva uma contagem no \
texto que não bata com esses valores; se precisar mencionar quais domínios estão em cada \
banda, liste os nomes, mas o NÚMERO sempre vem literal de "resumo_contagens".

12. Os campos "parecer" (em pareceres_por_dominio) e "justificativa" (em \
riscos_prioritarios) devem ter NO MÁXIMO 1 frase curta cada — linguagem simples, direta e \
conclusiva, sem repetir os números que já aparecem em outros campos do JSON (escore, \
percentual, banda já são exibidos separadamente no PDF; não os repita em texto). PROIBIDO \
incluir qualquer sugestão de ação, medida ou recomendação nesses dois campos especificamente \
— eles descrevem só o que foi encontrado e por que é prioritário, nunca o que fazer. A \
recomendação (medida a tomar) só pode aparecer no campo "medida_preventiva" (em \
recomendacoes), nunca vazada pra dentro de "parecer" ou "justificativa"."""

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
                        "populacao_exposta": {
                            "type": "string",
                            "description": 'Ex.: "12 de 15 trabalhadores do GHE" — sempre a partir de n_respondentes.',
                        },
                        "parecer": {"type": "string"},
                    },
                    "required": [
                        "ghe",
                        "instrumento",
                        "dominio",
                        "classificacao",
                        "banda",
                        "populacao_exposta",
                        "parecer",
                    ],
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
                        "justificativa": {
                            "type": "string",
                            "description": "Deve explicar a prevalência (percentual na faixa elevada) e evento grave confirmado, quando houver — não só repetir a banda.",
                        },
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
                        "hierarquia_controle": {
                            "type": "string",
                            "enum": HIERARQUIA_CONTROLE_VALORES,
                            "description": "Categoria da hierarquia de controle NIOSH desta medida.",
                        },
                        "medida_preventiva": {"type": "string"},
                    },
                    "required": ["ghe", "dominio", "banda", "hierarquia_controle", "medida_preventiva"],
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
                "percentual_elevados": float(escore.percentual_elevados),
                "prioridade": escore.prioridade,
                "n_respondentes": escore.n_respondentes,
                "suprimido_por_confidencialidade": False,
            }
            classificacao_risco = getattr(escore, "classificacao_risco", None)
            if classificacao_risco is not None:
                dominio_payload.update(
                    {
                        "banda": classificacao_risco.banda,
                        "prazo_dias_plano_de_acao": classificacao_risco.prazo_dias_plano_de_acao,
                        "evento_grave_confirmado": classificacao_risco.evento_grave_confirmado,
                        "evidencias_convergentes": classificacao_risco.evidencias_convergentes,
                    }
                )
            ghe_payload["dominios"].append(dominio_payload)

        payload["ghes"].append(ghe_payload)

    payload["resumo_contagens"] = _montar_resumo_contagens(payload["ghes"])
    return payload


def _montar_resumo_contagens(ghes_payload: list[dict]) -> dict:
    """Achado de 2026-08-05 (relatório real revisado pelo usuário): a síntese
    executiva gerada por IA errou a própria contagem de domínios ("Dos 25 domínios
    avaliados, 4 apresentaram banda Alto" quando na verdade eram 26 domínios e 3 em
    Alto) — a IA tentou somar/contar sozinha em texto livre e errou. Essas contagens
    são determinísticas e já estão disponíveis no payload; calculá-las aqui e exigir
    (regra 11 do SYSTEM_PROMPT) que a IA só as repita, nunca as recalcule, elimina
    essa classe de erro por completo."""
    total = 0
    por_banda = {"Aceitável": 0, "Moderado": 0, "Alto": 0, "Crítico": 0}
    for ghe_payload in ghes_payload:
        for dominio in ghe_payload["dominios"]:
            if dominio.get("suprimido_por_confidencialidade"):
                continue
            total += 1
            banda = dominio.get("banda")
            if banda in por_banda:
                por_banda[banda] += 1
    return {"total_dominios_avaliados": total, "por_banda": por_banda}


def _dominios_fora_de_aceitavel(payload: dict) -> set[tuple[str, str]]:
    """(ghe, dominio) de todo domínio não suprimido e com banda != "Aceitável" —
    é exatamente o conjunto que a regra 7 do SYSTEM_PROMPT exige cobrir em
    "riscos_prioritarios" e "recomendacoes"."""
    pendentes = set()
    for ghe_payload in payload.get("ghes", []):
        for dominio in ghe_payload["dominios"]:
            if dominio.get("suprimido_por_confidencialidade"):
                continue
            if dominio.get("banda") and dominio["banda"] != "Aceitável":
                pendentes.add((ghe_payload["ghe"], dominio["dominio"]))
    return pendentes


def _validar_cobertura_parecer(payload: dict, parecer: dict) -> None:
    """Garante que a IA não devolveu 'riscos_prioritarios'/'recomendacoes' vazios ou
    incompletos quando existe domínio fora de Aceitável — achado real de 2026-07-29:
    o schema aceitava listas vazias silenciosamente (nada em JSON Schema força
    minItems condicional ao conteúdo de outro campo), e o modelo devolveu uma boa
    síntese executiva mas as 3 listas totalmente vazias, mesmo havendo 29 domínios
    fora de Aceitável. Levanta erro em vez de aceitar um parecer incompleto — quem
    chama (`relatorio_gerar_parecer_ia`) já mostra exceções como mensagem, não 500."""
    pendentes = _dominios_fora_de_aceitavel(payload)
    if not pendentes:
        return

    cobertos_risco = {(r.get("ghe"), r.get("dominio")) for r in parecer.get("riscos_prioritarios", [])}
    cobertos_recom = {(r.get("ghe"), r.get("dominio")) for r in parecer.get("recomendacoes", [])}

    faltando_risco = pendentes - cobertos_risco
    faltando_recom = pendentes - cobertos_recom
    if faltando_risco or faltando_recom:
        partes = []
        if faltando_risco:
            partes.append(f"riscos_prioritarios sem {len(faltando_risco)} domínio(s) fora de Aceitável")
        if faltando_recom:
            partes.append(f"recomendacoes sem {len(faltando_recom)} domínio(s) fora de Aceitável")
        raise RuntimeError(
            "A IA devolveu um parecer incompleto (" + "; ".join(partes) + "). "
            "Tente gerar o parecer novamente."
        )


def gerar_parecer(payload: dict, client=None) -> dict:
    """Chama a API da Anthropic com tool_choice forçado — a resposta É o JSON
    estruturado, sem parsing frágil de texto livre. `client` é injetável pra teste
    (ver relatorios/tests.py) sem precisar de rede nem de ANTHROPIC_API_KEY."""

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
        system=SYSTEM_PROMPT,
        tools=[PARECER_TOOL],
        tool_choice={"type": "tool", "name": "gerar_parecer_tecnico"},
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
    )

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "gerar_parecer_tecnico":
            parecer = block.input
            _validar_cobertura_parecer(payload, parecer)
            return parecer

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
