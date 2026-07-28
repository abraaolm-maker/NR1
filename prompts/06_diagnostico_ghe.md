# Prompt 06 — Diagnóstico GHE (prevalência como critério de prioridade)

## Contexto

A planilha `Diagnostico_GHE` do Excel é a tabela central de resultados. Cada linha = 1 GHE × 1 domínio, com estas colunas:

| Coluna | Descrição |
|---|---|
| GHE/grupo | Nome do GHE |
| Domínio | "D1 - Exigências do trabalho" etc. |
| N | Número de respondentes |
| Índice de risco (0–100) | Média do domínio no GHE (escala 0–100) |
| % de respondentes elevados | Proporção que ficou ≥ 62.5 |
| Classificação | Baixo (≤37.5) / Moderado (37.5–62.5) / Elevado (≥62.5) / SUPRIMIDO (N<5) |
| Prioridade | P1 (≥50% elevados) / P2 (≥25%) / P3 (<25%) / AGRUPAR (suprimido) |
| Alerta protegido | Para D9: "SEM ALERTA AGREGADO" se alertas_d9=0, ou texto de alerta |
| Nota técnica | Texto padrão por classificação/prioridade |

GHE 04 (N=3) está todo SUPRIMIDO — N < mínimo (5).

## O que o Excel faz diferente do sistema atual

O sistema atual usa: Classificação (do escore médio) → Severidade → Probabilidade (evidências convergentes) → Matriz S×P → Banda. O Excel **não usa** a matriz S×P para priorizar. Ele usa:

1. **Classificação** do escore médio (mesma lógica: Baixo/Moderado/Elevado)
2. **Prevalência** (% respondentes na faixa elevada) como critério de **Prioridade** (P1/P2/P3)
3. **Nota técnica** fixa por prioridade:
   - P1: "Prioridade coletiva elevada; triangular e controlar na fonte."
   - P2: "Resultado moderado; investigar causas e prevenir agravamento."
   - P3: "Manter controles e monitorar."
   - AGRUPAR (suprimido): "Microgrupo com N < 5. Não divulgar resultado; ampliar coleta ou agregar somente exposições equivalentes."

## Tarefas

### 1. O `EscoreDominio` deve armazenar os dados do Diagnóstico GHE

Após o Prompt 02 e 04, `EscoreDominio` já deve ter:
- `escore` (0–100)
- `classificacao` (Baixo/Moderado/Elevado)
- `percentual_elevados` (float 0–1)
- `prioridade` (P1/P2/P3/AGRUPAR)
- `n_respondentes`
- `suprimido_por_confidencialidade`

Adicionar campo `nota_tecnica` (TextField, blank=True) — preenchido automaticamente pelo `calculo_risco.py` com o texto padrão correspondente à prioridade.

Ou, **recomendação**: não persistir a nota técnica — derivar do template a partir da prioridade, usando um dicionário de notas fixas. Menos campos no banco, mesma funcionalidade.

### 2. Adaptar `calculo_risco.py` para produzir o diagnóstico no formato do Excel

Em `calcular_dominio()`, após calcular escores individuais (Prompt 04):
- `percentual_elevados` = count(escores ≥ limite_elevado) / N
- Se N < n_minimo: `prioridade = "AGRUPAR"`, `suprimido = True`, não exibir escore nem percentual
- Senão: `prioridade` = P1 se ≥ prevalencia_p1, P2 se ≥ prevalencia_p2, P3 caso contrário

Para D9 especificamente:
- Verificar alertas D9 (Prompt 05) e anotar como "alerta protegido"
- Se sem alertas: "SEM ALERTA AGREGADO"

### 3. Simplificar `ClassificacaoRisco`

O modelo `ClassificacaoRisco` (Severidade × Probabilidade → Banda) perde relevância com a mudança para o modelo de prevalência. **Decisão**: manter `ClassificacaoRisco` no banco (não apagar dados existentes), mas o **diagnóstico primário** passa a ser `EscoreDominio.prioridade` (P1/P2/P3).

A `ClassificacaoRisco` continua calculada internamente (para rastreabilidade com o CLAUDE.md original), mas a Prioridade do relatório vem da prevalência, não da matriz S×P.

### 4. View de Diagnóstico GHE no painel

Criar view `diagnostico_ghe` em `avaliacoes/painel_views.py`, acessível a partir do detalhe da Aplicacao ou da Unidade. Mostra a tabela idêntica ao Excel:

| GHE | Domínio | N | Índice de risco (0–100) | % elevados | Classificação | Prioridade | Alerta protegido | Nota técnica |

Com cores:
- P1: badge vermelho
- P2: badge amarelo
- P3: badge verde
- AGRUPAR: badge cinza
- SUPRIMIDO: sem valores, texto "SUPRIMIDO"

### 5. Template com notas técnicas

Dicionário de notas no template (ou em constantes do Python):
```python
NOTAS_TECNICAS = {
    "P1": "Prioridade coletiva elevada; triangular e controlar na fonte.",
    "P2": "Resultado moderado; investigar causas e prevenir agravamento.",
    "P3": "Manter controles e monitorar.",
    "AGRUPAR": "Microgrupo com N < {n_minimo}. Não divulgar resultado; ampliar coleta ou agregar somente exposições equivalentes.",
}
```

## Resultado esperado

- Diagnóstico GHE calculado com prevalência (P1/P2/P3) em vez de matriz S×P para priorização.
- Supressão funciona com N_minimo=5 (configurável).
- Alertas D9 integrados na coluna "Alerta protegido".
- Tela no painel reproduzindo a tabela do Excel.
- Testes cobrindo: P1 (≥50% elevados), P2 (≥25%), P3 (<25%), AGRUPAR (N<5), D9 com e sem alerta.

## Arquivos a modificar/criar

- `avaliacoes/models.py` — atualizar `EscoreDominio` se campos ainda faltarem
- `avaliacoes/services/calculo_risco.py` — lógica de prevalência e prioridade
- `avaliacoes/painel_views.py` — nova view `diagnostico_ghe`
- `avaliacoes/painel_urls.py` — nova rota
- Template `avaliacoes/templates/painel/diagnostico_ghe.html`
- Testes
