# Prompt 11 — Semáforo de Riscos (distribuição por faixas)

## Contexto

A planilha `Semaforo_Riscos` do Excel mostra, para TODA a organização (ou por GHE), a **distribuição percentual** dos respondentes em 3 faixas para cada domínio:

| Domínio | Risco (vermelho) | Intermediário (amarelo) | Favorável (verde) | Prioridade | Média de risco |
|---|---|---|---|---|---|
| D1 | 64.3% | 35.7% | 0% | P1 | 68.8 |
| D2 | 35.7% | 47.6% | 16.7% | P2 | 54.8 |
| ... | ... | ... | ... | ... | ... |
| D9 | 0% | 9.5% | 90.5% | P3 | 23.8 |

Faixas:
- **Risco para a saúde** (vermelho): escore do respondente ≥ 62.5
- **Intermediário** (amarelo): entre 37.5 e 62.5
- **Situação favorável** (verde): escore ≤ 37.5

A leitura resumida mostra:
- Qual domínio tem maior proporção em vermelho
- Contagem de domínios por prioridade (P1, P2, P3)

O critério final na planilha: "verde = escore de risco até o limite baixo; amarelo = entre os limites; vermelho = escore igual ou superior ao limite elevado."

## Tarefas

### 1. Criar função de cálculo do semáforo

Em `avaliacoes/services/calculo_risco.py` ou novo arquivo `avaliacoes/services/semaforo.py`:

```python
def calcular_semaforo(
    aplicacoes: list[Aplicacao],
    limite_baixo: float = 37.5,
    limite_elevado: float = 62.5,
) -> list[dict]:
    """Calcula a distribuição semáforo para um conjunto de Aplicacoes (ex.: todas de uma Unidade).

    Retorna lista de dicts, um por domínio:
    {
        "dominio_codigo": "D1",
        "dominio_nome": "Exigências do trabalho",
        "n_respondentes": 42,
        "pct_risco": 0.643,       # vermelho (≥ limite_elevado)
        "pct_intermediario": 0.357, # amarelo (entre limites)
        "pct_favoravel": 0.0,      # verde (≤ limite_baixo)
        "prioridade": "P1",
        "media_risco": 68.8,
    }
    """
```

A função precisa dos escores **por respondente por domínio** (`EscoreRespondente` do Prompt 04). Para cada domínio:
1. Coletar todos os `EscoreRespondente` das Aplicacoes fornecidas
2. Classificar cada escore em verde/amarelo/vermelho
3. Calcular percentuais
4. Calcular média
5. Determinar prioridade (P1/P2/P3) pela prevalência (% em vermelho)

### 2. View de Semáforo no painel

Criar view `semaforo_riscos` em `avaliacoes/painel_views.py` (ou `relatorios/painel_views.py`):
- Acessível a partir do detalhe da Unidade ou do Relatório
- Parâmetro: Unidade (agrega todas as Aplicacoes daquela Unidade) ou Aplicacao específica
- Tabela com as colunas do Excel:

| Domínio | Risco (%) | Intermediário (%) | Favorável (%) | Prioridade | Média |

Com cores:
- Coluna "Risco": fundo vermelho suave
- Coluna "Intermediário": fundo amarelo suave
- Coluna "Favorável": fundo verde suave
- Prioridade: badge (P1=vermelho, P2=amarelo, P3=verde)

### 3. Leitura técnica resumida

Abaixo da tabela, calcular e exibir:
- "Maior proporção em vermelho: D1 - Exigências do trabalho (64.3%)"
- "Domínios P1: 1 | Domínios P2: 7 | Domínios P3: 1"

### 4. Opção de filtro por GHE

O Excel mostra "TOTAL ORGANIZAÇÃO" (agregado). O sistema deve permitir:
- Visualizar por Unidade inteira (soma todos os GHEs)
- Filtrar por GHE específico
- Respeitar supressão (GHE com N < mínimo não aparece individualmente, mas seus dados SÃO incluídos no total da organização — confirmar se o Excel faz isso ou exclui; pela planilha, os 42 respondentes = 12+18+9+3, portanto inclui o GHE suprimido no total)

### 5. Integrar no relatório PDF

Adicionar seção "Análise Semáforo" no template `inventario.html`, com a tabela de distribuição por faixas. Esta é uma das peças visuais mais importantes do relatório.

## Resultado esperado

- Função `calcular_semaforo()` operacional.
- Tela no painel com tabela + leitura resumida.
- Filtro por GHE.
- Seção no PDF.
- Todos os testes passando + teste para semáforo com dados simulados.

## Arquivos a criar/modificar

- `avaliacoes/services/semaforo.py` — novo (ou adicionar a `calculo_risco.py`)
- `avaliacoes/painel_views.py` + `painel_urls.py` — nova view
- Template `avaliacoes/templates/painel/semaforo_riscos.html`
- `relatorios/templates/relatorios/inventario.html` — nova seção
- `relatorios/services/pdf.py` — incluir dados do semáforo no contexto
- Testes
