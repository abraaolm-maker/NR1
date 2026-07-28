"""Formulário estruturado do parecer técnico (Prompt de UX 2026-07-28: editar o
parecer como JSON cru num textarea era inutilizável pro profissional de SST — um
erro de vírgula quebrava tudo). Sem depender de JavaScript: a tela sempre renderiza
as linhas existentes + 3 linhas em branco por lista, e o parse na volta usa a mesma
contagem pra saber quantos índices ler.

`parecer_ia` tem 3 campos-lista com formatos fixos (ver `analise_ia.py::PARECER_TOOL`):
  pareceres_por_dominio: [{ghe, instrumento, dominio, classificacao, banda, parecer}]
  riscos_prioritarios:   [{ghe, dominio, banda, justificativa}]
  recomendacoes:         [{ghe, dominio, banda, medida_preventiva}]
"""

LINHAS_EM_BRANCO = 3

CAMPOS_POR_LISTA = {
    "dominio": ["ghe", "instrumento", "dominio", "classificacao", "banda", "parecer"],
    "risco": ["ghe", "dominio", "banda", "justificativa"],
    "recom": ["ghe", "dominio", "banda", "medida_preventiva"],
}

CHAVE_POR_PREFIXO = {
    "dominio": "pareceres_por_dominio",
    "risco": "riscos_prioritarios",
    "recom": "recomendacoes",
}


def contar_linhas_renderizadas(parecer: dict) -> dict:
    """Quantas linhas cada lista deve renderizar (existentes + linhas em branco pra
    adicionar novos itens sem JavaScript). A mesma contagem é usada no GET (pra
    desenhar o form) e no POST (pra saber até que índice ler)."""
    return {
        prefixo: len(parecer.get(chave) or []) + LINHAS_EM_BRANCO
        for prefixo, chave in CHAVE_POR_PREFIXO.items()
    }


def linhas_para_template(parecer: dict) -> dict:
    """Uma lista de dicts por prefixo, já com índice, pronta pra {% for %} no
    template — linhas existentes primeiro, depois as em branco."""
    resultado = {}
    for prefixo, chave in CHAVE_POR_PREFIXO.items():
        campos = CAMPOS_POR_LISTA[prefixo]
        existentes = parecer.get(chave) or []
        linhas = []
        for i, linha in enumerate(existentes):
            linhas.append({"indice": i, "prefixo": prefixo, **{c: linha.get(c, "") for c in campos}})
        for i in range(len(existentes), len(existentes) + LINHAS_EM_BRANCO):
            linhas.append({"indice": i, "prefixo": prefixo, **{c: "" for c in campos}})
        resultado[prefixo] = linhas
    return resultado


def montar_parecer_do_post(post, contagem: dict) -> dict:
    """Reconstrói o dict `parecer_ia` a partir do POST. Linhas com todos os campos
    vazios são descartadas (são as linhas em branco não preenchidas)."""
    resultado = {
        "sintese_executiva": post.get("sintese_executiva", "").strip(),
        "aviso_minuta": post.get("aviso_minuta", "").strip(),
    }
    for prefixo, chave in CHAVE_POR_PREFIXO.items():
        campos = CAMPOS_POR_LISTA[prefixo]
        total = contagem[prefixo]
        linhas = []
        for i in range(total):
            if post.get(f"{prefixo}_{i}_remover"):
                continue
            linha = {c: post.get(f"{prefixo}_{i}_{c}", "").strip() for c in campos}
            if any(linha.values()):
                linhas.append(linha)
        resultado[chave] = linhas
    return resultado
