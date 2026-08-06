"""Geração do PDF final (Chromium via Playwright + Paged.js) — CLAUDE.md Etapa 6 /
Seção 8.3, migração de motor registrada em PLANO_ACAO_RELATORIO.md Seção 3.7.

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

Motor de renderização (2026-08-05): trocado de WeasyPrint pra Chromium headless
(Playwright) + Paged.js. WeasyPrint não é motor de navegador — suporte parcial a
sombra/gradiente/CSS moderno e a `@page` margin boxes (bug real de font-family
corrigido antes da migração, CLAUDE.md Seção 6.23). Chromium sozinho resolve
fidelidade visual, mas a API nativa `page.pdf()` só aceita header/footer
ESTÁTICOS — sem equivalente a `string-set`/`content: string()` pro masthead mudar
de texto por seção. Paged.js é um polyfill de CSS Paged Media que roda dentro do
Chromium (via `page.add_script_tag`) e implementa esse recurso corretamente,
resolvendo os dois problemas com o mesmo HTML/CSS que já existia — nenhuma
reescrita de template foi necessária pra migrar."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.utils import timezone
from playwright.sync_api import sync_playwright

from avaliacoes.models import ConformidadeChecklist, RespostaChecklistTriangulacao
from avaliacoes.services.calculo_risco import BANDA_ORDEM, criterio_classificacao_linhas, media_nacional_comparavel
from avaliacoes.services.semaforo import calcular_semaforo, leitura_resumida
from relatorios.models import Relatorio, StatusRelatorio, TipoRelatorio

PAGEDJS_PATH = Path(__file__).resolve().parent.parent / "vendor" / "paged.polyfill.js"


def _renderizar_pdf_via_chromium(html: str) -> bytes:
    """Abre uma página Chromium headless, injeta o Paged.js (vendorizado em
    `relatorios/vendor/paged.polyfill.js` — nunca buscado de CDN em runtime, pra
    não depender de internet em produção), espera a paginação terminar de
    assentar, e imprime o resultado já paginado em PDF. As margens do `@page`
    já ficam "assadas" no HTML paginado pelo Paged.js, então `page.pdf()` roda
    sem margem adicional do Chrome (senão a margem seria somada duas vezes)."""
    pagedjs_source = PAGEDJS_PATH.read_text(encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="networkidle")
        page.add_script_tag(content=pagedjs_source)
        page.wait_for_selector(".pagedjs_pages", timeout=30000)
        page.wait_for_timeout(500)
        pdf_bytes = page.pdf(
            print_background=True,
            prefer_css_page_size=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        browser.close()

    return pdf_bytes

BANDA_CSS = {
    "Aceitável": "aceitavel",
    "Moderado": "moderado",
    "Alto": "alto",
    "Crítico": "critico",
}

def _medida_em_bullets(medida: str) -> list[str]:
    """Fase 4 da 3ª rodada + item 6 da 4ª auditoria (PLANO_ACAO_RELATORIO.md Seção
    3.6): a medida gerada pelo catálogo/IA vira lista de bullets curtos em vez de
    parágrafo corrido denso, casando com o padrão de escaneabilidade já usado no
    Parecer técnico. Tenta primeiro separar por ponto e vírgula (sub-ações
    explícitas); a maioria das medidas reais, porém, não usa ";" — é uma sequência
    de frases separadas por ponto final (achado da 4ª auditoria: o split por ";"
    sozinho deixava praticamente todo item como um único bloco de texto). Nesse
    caso, cada frase completa (terminada em "." e seguida de maiúscula) vira um
    bullet próprio."""
    partes = [p.strip() for p in medida.split(";") if p.strip()]
    if len(partes) > 1:
        return partes

    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ú])", medida.strip()) if f.strip()]
    return frases if len(frases) > 1 else [medida]


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
                        "medida_bullets": _medida_em_bullets(plano.medida),
                    }
                )
    planos.sort(key=lambda p: BANDA_ORDEM.get(p["banda"], 0), reverse=True)
    return planos


def _mapa_nomes_dominio(ghes: list[dict]) -> dict[str, str]:
    return {d["escore_dominio"].dominio.codigo: d["escore_dominio"].dominio.nome for item in ghes for d in item["dominios"]}


def _parecer_para_exibicao(parecer_ia: dict | None, ghes: list[dict]) -> dict | None:
    """Seção 4 (Parecer técnico): acha de 2026-08-03 (relatório real revisado pelo
    usuário) — mostrar só o código do domínio ("EE") obriga quem lê a decorar 29
    códigos diferentes. Achado de 2026-08-05 (Fase 5, PLANO_ACAO_RELATORIO.md Seção
    3.6): "Pareceres por domínio" e "Riscos prioritários e recomendações" diziam
    quase a mesma coisa sobre os mesmos domínios em duas listas separadas — fundidas
    aqui numa única lista "achados" por domínio (Domínio/Banda, o que foi encontrado,
    por que é prioritário, o que fazer), nunca sobrescrevendo o JSON original salvo em
    `Relatorio.parecer_ia`. A coluna "GHE" só aparece quando há mais de 1 GHE neste
    relatório — repetir "Escritório" em toda linha quando só existe um GHE no ciclo
    não ajuda a leitura."""
    if not parecer_ia:
        return None

    nomes = _mapa_nomes_dominio(ghes)

    def _rotulo(codigo: str) -> str:
        nome = nomes.get(codigo)
        return f"{nome} ({codigo})" if nome else codigo

    ghes_distintos = {p.get("ghe") for p in parecer_ia.get("pareceres_por_dominio", [])}
    mostrar_ghe = len(ghes_distintos) > 1

    pareceres_por_chave = {(p.get("ghe"), p.get("dominio")): p for p in parecer_ia.get("pareceres_por_dominio", [])}
    riscos_por_chave = {(r.get("ghe"), r.get("dominio")): r for r in parecer_ia.get("riscos_prioritarios", [])}
    recomendacoes_por_chave = {
        (r.get("ghe"), r.get("dominio")): r for r in parecer_ia.get("recomendacoes", [])
    }
    chaves = list(dict.fromkeys([*pareceres_por_chave, *riscos_por_chave, *recomendacoes_por_chave]))

    achados = []
    for chave in chaves:
        parecer = pareceres_por_chave.get(chave, {})
        banda = parecer.get("banda", "")
        if banda == "Aceitável":
            continue
        risco = riscos_por_chave.get(chave, {})
        recomendacao = recomendacoes_por_chave.get(chave, {})
        achados.append(
            {
                "ghe": chave[0],
                "dominio_rotulo": _rotulo(chave[1] or ""),
                "banda": banda or risco.get("banda") or recomendacao.get("banda", ""),
                "o_que_foi_encontrado": parecer.get("parecer", ""),
                "por_que_e_prioritario": risco.get("justificativa", ""),
                "o_que_fazer": recomendacao.get("medida_preventiva", ""),
            }
        )

    return {
        "sintese_executiva": parecer_ia.get("sintese_executiva", ""),
        "achados": achados,
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


NIVEL_GERAL_POR_BANDA = {"Aceitável": "Baixo", "Moderado": "Moderado", "Alto": "Alto", "Crítico": "Alto"}
ORDEM_BANDA_GERAL = {"Baixo": 0, "Moderado": 1, "Alto": 2}
NIVEL_GERAL_CSS = {"Baixo": "aceitavel", "Moderado": "moderado", "Alto": "alto"}


def _montar_panorama(ghes: list[dict]) -> dict:
    """Seção 1 (Panorama), inspirada no relatório de referência Solute RH (CLAUDE.md
    Seção 6.18 / PLANO_ACAO_RELATORIO.md Seção 3): um resumo executivo com índice
    consolidado, N de participantes, nível geral de risco e as "frentes de atenção" —
    nunca substitui o semáforo por domínio (decisão inegociável do usuário), só
    resume o que ele já mostra em números fáceis de captar de relance.

    Índice consolidado = média simples dos escores (0-100) de todos os domínios não
    suprimidos deste relatório (decisão de engenharia registrada em
    PLANO_ACAO_RELATORIO.md Seção 5, item 3 — não há fórmula oficial publicada, mas
    a média simples é a mesma lógica agregadora já usada por domínio, só um nível
    acima). Nível geral de risco deriva da pior banda entre "Baixo" (Aceitável),
    "Moderado" e "Alto" (Alto ou Crítico) predominante — usa a banda mais frequente,
    não a pior isolada, pra não deixar 1 domínio Crítico (que já tem destaque próprio
    na Seção 4) dominar sozinho a leitura executiva."""
    escores = []
    frentes_atencao = []
    protegendo = []
    pede_acao = []
    n_respondentes_total = 0
    dominios_ja_contados_n = set()

    for item in ghes:
        for d in item["dominios"]:
            escore_dominio = d["escore_dominio"]
            chave_n = (item["aplicacao"].pk,)
            if chave_n not in dominios_ja_contados_n:
                # N de participantes = maior N entre os domínios da Aplicacao (mesmo
                # critério já usado em n_total_semaforo) — soma só uma vez por Aplicacao.
                dominios_ja_contados_n.add(chave_n)

            if escore_dominio.suprimido_por_confidencialidade:
                continue

            escores.append(float(escore_dominio.escore))
            cr = d["classificacao_risco"]
            banda = cr.banda if cr else "Aceitável"
            entrada = {
                "ghe_nome": item["ghe"].nome,
                "dominio_codigo": escore_dominio.dominio.codigo,
                "dominio_nome": escore_dominio.dominio.nome,
                "banda": banda,
                "banda_css": d["banda_css"],
            }
            if banda == "Aceitável":
                protegendo.append(entrada)
            else:
                frentes_atencao.append(entrada)
                pede_acao.append(entrada)

    for item in ghes:
        maior_n = max(
            (d["escore_dominio"].n_respondentes for d in item["dominios"]), default=0
        )
        n_respondentes_total += maior_n

    indice_consolidado = round(sum(escores) / len(escores), 1) if escores else None

    if indice_consolidado is None:
        nivel_geral_risco = None
    else:
        contagem_bandas = {"Baixo": 0, "Moderado": 0, "Alto": 0}
        for entrada in [*protegendo, *frentes_atencao]:
            contagem_bandas[NIVEL_GERAL_POR_BANDA.get(entrada["banda"], "Baixo")] += 1
        nivel_geral_risco = max(contagem_bandas, key=lambda k: (contagem_bandas[k], ORDEM_BANDA_GERAL[k]))

    return {
        "indice_consolidado": indice_consolidado,
        "nivel_geral_risco": nivel_geral_risco,
        "nivel_geral_risco_css": NIVEL_GERAL_CSS.get(nivel_geral_risco, ""),
        "n_participantes": n_respondentes_total,
        "frentes_atencao": frentes_atencao,
        "protegendo": protegendo,
        "pede_acao": pede_acao,
    }


def _contador_supressao(ghes: list[dict]) -> dict:
    """Pedido do usuário em 2026-08-05, a partir do Relatório 2 de referência
    (Hospital São Lucas): mostrar explicitamente quantos domínios foram suprimidos
    por confidencialidade no documento inteiro, em vez de só marcar "Suprimido" na
    linha, sem nunca somar o total (PLANO_ACAO_RELATORIO.md Seção 4.1, item 2)."""
    total = 0
    suprimidos = 0
    for item in ghes:
        for d in item["dominios"]:
            total += 1
            if d["escore_dominio"].suprimido_por_confidencialidade:
                suprimidos += 1
    return {"total": total, "suprimidos": suprimidos}


def _hash_integridade(relatorio: Relatorio, ghes: list[dict]) -> str:
    """Apêndice de integridade (PLANO_ACAO_RELATORIO.md Seção 4.1, item 3): um hash
    determinístico dos dados que fundamentam este documento (não do PDF em si, que
    ainda não existe no momento em que este contexto é montado) — serve pra
    conferir, depois, que o conteúdo numérico do relatório não foi alterado por
    fora do fluxo do sistema. Baseado só em dado determinístico já persistido
    (escores, classificações, N), nunca em timestamp de geração do PDF."""
    partes = {
        "relatorio_id": relatorio.pk,
        "criterio_versao": relatorio.criterio_versao.codigo,
        "dominios": sorted(
            [
                {
                    "aplicacao_id": item["aplicacao"].pk,
                    "dominio": d["escore_dominio"].dominio.codigo,
                    "escore": str(d["escore_dominio"].escore),
                    "n": d["escore_dominio"].n_respondentes,
                    "suprimido": d["escore_dominio"].suprimido_por_confidencialidade,
                }
                for item in ghes
                for d in item["dominios"]
            ],
            key=lambda x: (x["aplicacao_id"], x["dominio"]),
        ),
    }
    canonico = json.dumps(partes, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


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
        "panorama": _montar_panorama(ghes),
        "contador_supressao": _contador_supressao(ghes),
        "hash_integridade": _hash_integridade(relatorio, ghes),
        "gerado_em": timezone.now(),
    }


def renderizar_html_relatorio(relatorio: Relatorio, minuta: bool) -> str:
    return render_to_string("relatorios/inventario.html", _contexto_relatorio(relatorio, minuta))


def validar_pre_requisitos_pdf(relatorio: Relatorio) -> None:
    """Pedido do usuário em 2026-08-04: o PDF com Plano de Ação só pode ser gerado
    depois de rodar obrigatoriamente "Gerar parecer via IA" e "Refinar planos de ação
    com IA" — sem isso, o documento entregue como "Diagnóstico + Plano de Ação" teria
    o parecer vazio e/ou as medidas genéricas do catálogo, sem nenhuma indicação de
    que isso não é o que o tipo do relatório promete. O tipo "Diagnóstico" (sem plano)
    só exige o parecer técnico — não depende do refinamento do plano, que nem aparece
    nesse documento."""
    if not relatorio.parecer_ia:
        raise ValueError(
            "Gere o parecer técnico via IA antes de gerar o PDF — o documento "
            "(mesmo em minuta) não pode sair sem a análise técnica."
        )
    if relatorio.tipo == TipoRelatorio.DIAGNOSTICO_PLANO_ACAO and not relatorio.planos_refinados_em:
        raise ValueError(
            "Este relatório é do tipo \"Diagnóstico + Plano de Ação\" — refine os "
            "planos de ação via IA antes de gerar o PDF."
        )


def gerar_pdf_relatorio(relatorio_id: int) -> Relatorio:
    """Gera o PDF (minuta se ainda não assinado, final se já assinado) e salva em
    Relatorio.pdf_path. Idempotente/re-executável — sempre reflete o estado atual."""
    relatorio = Relatorio.objects.select_related(
        "unidade__empresa", "assinado_por", "criterio_versao"
    ).get(pk=relatorio_id)
    validar_pre_requisitos_pdf(relatorio)
    minuta = relatorio.status != StatusRelatorio.ASSINADO

    html = renderizar_html_relatorio(relatorio, minuta=minuta)
    pdf_bytes = _renderizar_pdf_via_chromium(html)

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
