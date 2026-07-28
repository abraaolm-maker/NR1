# Prompt 12 — Gráfico Semáforo (barras empilhadas no relatório PDF)

## Contexto

A planilha `Grafico_Semaforo` do Excel contém os dados formatados para gerar um gráfico de **barras empilhadas horizontais** (vermelho/amarelo/verde) por domínio. A referência visual é o gráfico do COPSOQ Manual Portugal 2013 (PDF p. 15, Gráfico 1).

O gráfico mostra:
- Eixo Y: 9 domínios (D1–D9)
- Eixo X: 0% a 100%
- Cada barra é composta por 3 segmentos empilhados:
  - **Vermelho** (risco para a saúde): % respondentes com escore ≥ 62.5
  - **Amarelo** (intermediário): % respondentes entre 37.5 e 62.5
  - **Verde** (favorável): % respondentes com escore ≤ 37.5

Cabeçalho: "DISTRIBUIÇÃO DOS FATORES PSICOSSOCIAIS POR FAIXA DE RISCO"
Subtítulo: "Grupo analisado: TOTAL ORGANIZAÇÃO" + "N válido: 42"

Rodapé: "Leitura: vermelho = risco para a saúde; amarelo = situação intermediária; verde = situação favorável."

## Tarefas

### 1. Gerar o gráfico no PDF via HTML/CSS puro (WeasyPrint)

WeasyPrint não suporta JavaScript (sem Chart.js, sem canvas). O gráfico deve ser feito em **HTML/CSS puro** — barras empilhadas horizontais via `div` com `display: flex` e `width` percentual.

Estrutura HTML para cada barra:
```html
<div class="barra-semaforo">
    <div class="label-dominio">D1 - Exigências do trabalho</div>
    <div class="barra-container">
        <div class="segmento vermelho" style="width: 64.3%;">64%</div>
        <div class="segmento amarelo" style="width: 35.7%;">36%</div>
        <div class="segmento verde" style="width: 0%;"></div>
    </div>
</div>
```

CSS:
```css
.barra-semaforo { display: flex; align-items: center; margin-bottom: 6px; }
.label-dominio { width: 200px; font-size: 9px; text-align: right; padding-right: 8px; }
.barra-container { flex: 1; display: flex; height: 22px; border: 1px solid #ddd; }
.segmento { display: flex; align-items: center; justify-content: center; font-size: 8px; color: #fff; font-weight: bold; }
.segmento.vermelho { background: #c0392b; }
.segmento.amarelo { background: #f1c40f; color: #333; }
.segmento.verde { background: #27ae60; }
```

Regras:
- Não mostrar texto dentro do segmento se a largura for < 5% (fica ilegível)
- Escala X (0%, 25%, 50%, 75%, 100%) como linhas de referência ou labels abaixo

### 2. Adicionar ao template `inventario.html`

Nova seção no PDF, **antes** do Diagnóstico por GHE (é o resumo visual geral):

```html
<div class="secao">
    <h2>Análise Semáforo — Distribuição dos Fatores Psicossociais</h2>
    <p class="subtitulo">Grupo analisado: {{ grupo_analisado }} — N válido: {{ n_total }}</p>

    {% for dominio in semaforo %}
    <div class="barra-semaforo">
        <div class="label-dominio">{{ dominio.dominio_nome }}</div>
        <div class="barra-container">
            {% if dominio.pct_risco > 0 %}
            <div class="segmento vermelho" style="width: {{ dominio.pct_risco_pct }}%;">
                {% if dominio.pct_risco >= 0.05 %}{{ dominio.pct_risco_pct|floatformat:0 }}%{% endif %}
            </div>
            {% endif %}
            {% if dominio.pct_intermediario > 0 %}
            <div class="segmento amarelo" style="width: {{ dominio.pct_intermediario_pct }}%;">
                {% if dominio.pct_intermediario >= 0.05 %}{{ dominio.pct_intermediario_pct|floatformat:0 }}%{% endif %}
            </div>
            {% endif %}
            {% if dominio.pct_favoravel > 0 %}
            <div class="segmento verde" style="width: {{ dominio.pct_favoravel_pct }}%;">
                {% if dominio.pct_favoravel >= 0.05 %}{{ dominio.pct_favoravel_pct|floatformat:0 }}%{% endif %}
            </div>
            {% endif %}
        </div>
    </div>
    {% endfor %}

    <p class="rodape-nota">
        Leitura: <span style="color: #c0392b;">■</span> risco para a saúde;
        <span style="color: #f1c40f;">■</span> situação intermediária;
        <span style="color: #27ae60;">■</span> situação favorável.
    </p>
</div>
```

### 3. Atualizar `_contexto_relatorio()` em `pdf.py`

Importar `calcular_semaforo()` do Prompt 11 e adicionar ao contexto:

```python
from avaliacoes.services.semaforo import calcular_semaforo

def _contexto_relatorio(relatorio, minuta):
    aplicacoes = list(relatorio.aplicacoes.all())
    semaforo = calcular_semaforo(aplicacoes)
    # Converter proporções para percentuais (template usa %)
    for item in semaforo:
        item["pct_risco_pct"] = item["pct_risco"] * 100
        item["pct_intermediario_pct"] = item["pct_intermediario"] * 100
        item["pct_favoravel_pct"] = item["pct_favoravel"] * 100

    return {
        ...,
        "semaforo": semaforo,
        "n_total": sum(item["n_respondentes"] for item in semaforo) // len(semaforo) if semaforo else 0,
        "grupo_analisado": relatorio.unidade.empresa.nome,
    }
```

### 4. Também mostrar no painel (tela web)

No painel (Prompt 11), além da tabela numérica, renderizar o mesmo gráfico de barras empilhadas. Na web, pode ser feito com o mesmo HTML/CSS (funciona em qualquer navegador).

### 5. Legenda e cabeçalho

O gráfico deve ter:
- Título: "DISTRIBUIÇÃO DOS FATORES PSICOSSOCIAIS POR FAIXA DE RISCO"
- Subtítulo: "Grupo analisado: [nome da empresa/unidade]" + "N válido: [total]"
- Legenda colorida abaixo
- Referência: "Referência visual: COPSOQ Manual Portugal 2013, Gráfico 1"

## Resultado esperado

- Gráfico de barras empilhadas horizontais renderizado no PDF via HTML/CSS puro.
- Mesmo gráfico visível no painel web.
- Dados vindos de `calcular_semaforo()` (Prompt 11).
- PDF final inclui o gráfico como peça visual central do relatório.
- Todos os testes passando.

## Arquivos a modificar

- `relatorios/templates/relatorios/inventario.html` — nova seção com gráfico
- `relatorios/services/pdf.py` — incluir semáforo no contexto
- Template do painel (se separado do Prompt 11) — mesmo gráfico
