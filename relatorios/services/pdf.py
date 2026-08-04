"""Geração do PDF final (WeasyPrint) — CLAUDE.md Etapa 6 / Seção 8.3.

Duas variantes do mesmo documento, controladas por `minuta` (decisão de 2026-07-17):
- minuta=True (relatorio.status != assinado): marca d'água "MINUTA", bloco de
  assinatura em branco — pro profissional responsável revisar o PDF formatado antes
  de assinar.
- minuta=False (relatorio.status == assinado): documento final, com nome, registro
  profissional (PerfilProfissional) e data de quem assinou.

`Relatorio.pdf_path` guarda sempre o PDF mais recente gerado — gerar de novo
sobrescreve, não há minuta e final coexistindo como dois arquivos.

"Assinar" (`assinar_relatorio`) é um registro interno simples — status + usuário +
data no banco, sem assinatura digital/criptográfica (decisão de 2026-07-17).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from avaliacoes.models import ConformidadeChecklist, RespostaChecklistTriangulacao
from avaliacoes.services.calculo_risco import BANDA_ORDEM, criterio_classificacao_linhas, media_nacional_comparavel
from avaliacoes.services.semaforo import calcular_semaforo, leitura_resumida
from relatorios.models import Relatorio, StatusRelatorio

BANDA_CSS = {
    "Aceitável": "aceitavel",
    "Moderado": "moderado",
    "Alto": "alto",
    "Crítico": "critico",
}

def _planos_ordenados(ghes: list[dict]) -> list[dict]:
    """Seção 8 (Plano de ação) lista as medidas do mais urgente pro menos urgente —
    Crítico primeiro, depois Alto, Moderado — em vez da ordem de cadastro por GHE/
    domínio, que não tinha relação nenhuma com prioridade de ação."""
    planos = []
    for item in ghes:
        for d in item["dominios"]:
            for plano in d["planos_de_acao"]:
                planos.append(
                    {
                        "plano": plano,
                        "ghe_nome": item["ghe"].nome,
                        "dominio_codigo": d["escore_dominio"].dominio.codigo,
                        "dominio_nome": d["escore_dominio"].dominio.nome,
                        "banda": d["classificacao_risco"].banda,
                        "banda_css": d["banda_css"],
                    }
                )
    planos.sort(key=lambda p: BANDA_ORDEM.get(p["banda"], 0), reverse=True)
    return planos


def _mapa_nomes_dominio(ghes: list[dict]) -> dict[str, str]:
    return {d["escore_dominio"].dominio.codigo: d["escore_dominio"].dominio.nome for item in ghes for d in item["dominios"]}


def _parecer_para_exibicao(parecer_ia: dict | None, ghes: list[dict]) -> dict | None:
    """Seção 3 (Parecer técnico): acha de 2026-08-03 (relatório real revisado pelo
    usuário) — mostrar só o código do domínio ("EE") obriga quem lê a decorar 29
    códigos diferentes; e as tabelas "Riscos prioritários" e "Recomendações" listavam
    os mesmos domínios em duas tabelas separadas, restatando a mesma banda duas
    vezes. Esta função prepara uma versão só pra exibição (nunca sobrescreve o JSON
    original salvo em `Relatorio.parecer_ia`): troca o código pelo nome completo e
    funde as duas tabelas numa só (Domínio, Banda, Justificativa, Medida preventiva).
    A coluna "GHE" e a coluna "Instrumento" só aparecem quando há mais de 1 GHE ou
    mais de 1 instrumento neste relatório — repetir "Escritório"/"COPSOQ_OFICIAL" em
    toda linha quando só existe um GHE/instrumento no ciclo não ajuda a leitura."""
    if not parecer_ia:
        return None

    nomes = _mapa_nomes_dominio(ghes)

    def _rotulo(codigo: str) -> str:
        nome = nomes.get(codigo)
        return f"{nome} ({codigo})" if nome else codigo

    ghes_distintos = {p.get("ghe") for p in parecer_ia.get("pareceres_por_dominio", [])}
    mostrar_ghe = len(ghes_distintos) > 1

    pareceres = []
    for p in parecer_ia.get("pareceres_por_dominio", []):
        pareceres.append({**p, "dominio_rotulo": _rotulo(p.get("dominio", ""))})

    riscos_por_chave = {(r.get("ghe"), r.get("dominio")): r for r in parecer_ia.get("riscos_prioritarios", [])}
    recomendacoes_por_chave = {
        (r.get("ghe"), r.get("dominio")): r for r in parecer_ia.get("recomendacoes", [])
    }
    chaves = list(dict.fromkeys([*riscos_por_chave, *recomendacoes_por_chave]))  # preserva ordem, sem duplicar

    riscos_e_recomendacoes = []
    for chave in chaves:
        risco = riscos_por_chave.get(chave, {})
        recomendacao = recomendacoes_por_chave.get(chave, {})
        riscos_e_recomendacoes.append(
            {
                "ghe": chave[0],
                "dominio_rotulo": _rotulo(chave[1] or ""),
                "banda": risco.get("banda") or recomendacao.get("banda", ""),
                "justificativa": risco.get("justificativa", ""),
                "medida_preventiva": recomendacao.get("medida_preventiva", ""),
            }
        )

    return {
        "sintese_executiva": parecer_ia.get("sintese_executiva", ""),
        "pareceres_por_dominio": pareceres,
        "riscos_e_recomendacoes": riscos_e_recomendacoes,
        "aviso_minuta": parecer_ia.get("aviso_minuta", ""),
        "mostrar_ghe": mostrar_ghe,
    }

VARIANTE_POR_PROFUNDIDADE = {
    "curta": "COPSOQ oficial, versão curta",
    "media": "COPSOQ oficial, versão média",
    "longa": "COPSOQ oficial, versão longa",
}


def _variante_instrumento(aplicacao) -> str:
    """Nome de negócio da variante do questionário aplicada neste GHE, pra exibir na
    Seção 3 (Metodologia) do relatório — nunca o código técnico do instrumento."""
    codigo = aplicacao.instrumento.codigo
    if codigo == "COPSOQ_OFICIAL":
        return VARIANTE_POR_PROFUNDIDADE.get(aplicacao.profundidade, "COPSOQ oficial")
    if codigo == "COPSOQ_RR_REVESTIR":
        return "COPSOQ adaptado"
    return aplicacao.instrumento.nome


def _dominios_criticos_por_evento_grave(ghes: list[dict]) -> list[dict]:
    """Domínios deste relatório especificamente elevados a Crítico por evento grave
    confirmado (não por prevalência) — usado pra tornar as caixas explicativas das
    Seções 4 e 5 concretas em vez de um texto genérico igual em todo relatório: cada
    documento cita, com nome, se isso realmente aconteceu neste ciclo ou não."""
    dominios = []
    for item in ghes:
        for d in item["dominios"]:
            cr = d["classificacao_risco"]
            if cr is not None and cr.evento_grave_confirmado:
                dominios.append(
                    {
                        "ghe_nome": item["ghe"].nome,
                        "dominio_codigo": d["escore_dominio"].dominio.codigo,
                        "dominio_nome": d["escore_dominio"].dominio.nome,
                    }
                )
    return dominios


def _criterio_classificacao_linhas(criterio_versao) -> list[dict]:
    """Wrapper fino sobre `calculo_risco.criterio_classificacao_linhas`, só adicionando
    a classe CSS do badge (usada apenas no template do PDF)."""
    linhas = criterio_classificacao_linhas(criterio_versao)
    for linha in linhas:
        linha["banda_css"] = BANDA_CSS.get(linha["banda"], "")
    return linhas


def _contexto_relatorio(relatorio: Relatorio, minuta: bool) -> dict:
    ghes = []
    for aplicacao in relatorio.aplicacoes.select_related("ghe", "instrumento").all():
        indicadores = aplicacao.ghe.indicadores_indiretos.filter(convergente=True).select_related(
            "dominio_relacionado"
        )

        dominios = []
        for escore in aplicacao.escores_dominio.select_related("dominio").all():
            classificacao_risco = getattr(escore, "classificacao_risco", None)
            dominios.append(
                {
                    "escore_dominio": escore,
                    "classificacao_risco": classificacao_risco,
                    "banda_css": BANDA_CSS.get(classificacao_risco.banda, "") if classificacao_risco else "",
                    "planos_de_acao": (
                        classificacao_risco.planos_de_acao.all() if classificacao_risco else []
                    ),
                    "media_nacional": media_nacional_comparavel(escore.dominio),
                }
            )

        checklist_triangulacao = RespostaChecklistTriangulacao.objects.filter(
            respondente__coleta__aplicacao=aplicacao
        ).exclude(conformidade=ConformidadeChecklist.NAO_AVALIADO).select_related("item").order_by(
            "item__tipo", "item__ordem"
        )

        ghes.append(
            {
                "aplicacao": aplicacao,
                "ghe": aplicacao.ghe,
                "indicadores": indicadores,
                "dominios": dominios,
                "checklist_triangulacao": checklist_triangulacao,
                "variante_instrumento": _variante_instrumento(aplicacao),
            }
        )

    perfil_assinante = None
    if relatorio.assinado_por is not None:
        perfil_assinante = getattr(relatorio.assinado_por, "perfil_profissional", None)

    linhas_semaforo = calcular_semaforo(list(relatorio.aplicacoes.select_related("criterio_versao").all()))
    resumo_semaforo = leitura_resumida(linhas_semaforo)
    n_total_semaforo = max((linha["n_respondentes"] for linha in linhas_semaforo), default=0)

    return {
        "relatorio": relatorio,
        "empresa": relatorio.unidade.empresa,
        "unidade": relatorio.unidade,
        "ghes": ghes,
        "minuta": minuta,
        "perfil_assinante": perfil_assinante,
        "criterio_classificacao_linhas": _criterio_classificacao_linhas(relatorio.criterio_versao),
        "planos_ordenados": _planos_ordenados(ghes),
        "dominios_criticos_evento_grave": _dominios_criticos_por_evento_grave(ghes),
        "parecer_exibicao": _parecer_para_exibicao(relatorio.parecer_ia, ghes),
        "linhas_semaforo": linhas_semaforo,
        "resumo_semaforo": resumo_semaforo,
        "n_total_semaforo": n_total_semaforo,
        "gerado_em": timezone.now(),
    }


def renderizar_html_relatorio(relatorio: Relatorio, minuta: bool) -> str:
    return render_to_string("relatorios/inventario.html", _contexto_relatorio(relatorio, minuta))


def gerar_pdf_relatorio(relatorio_id: int) -> Relatorio:
    """Gera o PDF (minuta se ainda não assinado, final se já assinado) e salva em
    Relatorio.pdf_path. Idempotente/re-executável — sempre reflete o estado atual."""
    relatorio = Relatorio.objects.select_related(
        "unidade__empresa", "assinado_por", "criterio_versao"
    ).get(pk=relatorio_id)
    minuta = relatorio.status != StatusRelatorio.ASSINADO

    html = renderizar_html_relatorio(relatorio, minuta=minuta)
    pdf_bytes = HTML(string=html).write_pdf()

    nome_arquivo = f"relatorio_{relatorio.pk}_{'minuta' if minuta else 'final'}.pdf"
    relatorio.pdf_path.save(nome_arquivo, ContentFile(pdf_bytes), save=False)
    relatorio.save(update_fields=["pdf_path"])
    return relatorio


def assinar_relatorio(relatorio_id: int, user_id: int) -> Relatorio:
    """Exige PerfilProfissional cadastrado no usuário — é o que preenche o registro
    profissional obrigatório no bloco de assinatura (Seção 8.3, item 8). Também exige
    parecer técnico gerado — assinar sem parecer produziria um documento "final" com a
    Seção 6 vazia (achado no diagnóstico de UX de 2026-07-28: nada impedia assinar um
    relatório sem nenhum conteúdo analítico). Regenera o PDF final automaticamente como
    parte do fluxo de assinatura."""
    user = get_user_model().objects.get(pk=user_id)

    if not hasattr(user, "perfil_profissional"):
        raise ValueError(
            f'Usuário "{user}" não tem PerfilProfissional cadastrado — obrigatório pra '
            "assinar um Relatorio (CLAUDE.md Seção 8.3, item 8)."
        )

    relatorio = Relatorio.objects.get(pk=relatorio_id)

    if not relatorio.parecer_ia:
        raise ValueError(
            "Este relatório ainda não tem parecer técnico gerado — gere o parecer "
            "antes de assinar (o documento final não pode sair sem análise)."
        )

    relatorio.status = StatusRelatorio.ASSINADO
    relatorio.assinado_por = user
    relatorio.assinado_em = timezone.now()
    relatorio.save(update_fields=["status", "assinado_por", "assinado_em"])

    return gerar_pdf_relatorio(relatorio_id)
