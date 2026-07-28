# Prompt 02 — Configuração (escala 0–100 + prevalência P1/P2/P3)

## Contexto

A planilha `Configuracao` do Excel define os parâmetros do método:

```
Parâmetro                         | Valor
Mínimo para divulgação por grupo  | 5
Limite máximo - Baixo             | 37.5
Limite mínimo - Elevado           | 62.5
Prevalência para P1               | 0.5   (50% dos respondentes na faixa elevada)
Prevalência para P2               | 0.25  (25% dos respondentes na faixa elevada)
Período de referência             | Últimos 3 meses
```

O sistema atual trabalha com escala 1–5 e cortes em 2.5/3.5. O Excel normaliza para escala **0–100** com a fórmula `(resposta - 1) × 25` para itens RISCO e `(5 - resposta) × 25` para PROTETIVO. Os cortes: Baixo ≤ 37.5, Elevado ≥ 62.5.

**Matematicamente é equivalente** (2.5 na escala 1–5 = 37.5 na escala 0–100), mas o Excel e o relatório usam e exibem a escala 0–100 em toda parte.

Além disso, o Excel introduz o conceito de **Prevalência** para determinar Prioridade:
- **P1**: ≥50% dos respondentes do GHE têm escore de domínio ≥ 62.5 (faixa elevada)
- **P2**: ≥25% dos respondentes na faixa elevada
- **P3**: <25% na faixa elevada

Isso **substitui** o modelo atual de Severidade × Probabilidade (com evidências convergentes) para fins de priorização. A Prioridade do Excel (P1/P2/P3) é o que define urgência/ação, não mais a matriz S×P.

## Tarefas

### 1. Migrar `risk_engine.py` para escala 0–100

- A função `inverter_se_necessario()` deve retornar na escala 0–100: `(valor_bruto - escala_min) * 100 / (escala_max - escala_min)` para RISCO, e `(escala_max - valor_bruto) * 100 / (escala_max - escala_min)` para PROTETIVO.
- `calcular_escore_dominio()` agora retorna a média em escala 0–100.
- Os `Thresholds` (atualmente `baixo_max=2.5, moderado_max=3.4` para COPSOQ) passam a ser `baixo_max=37.5, moderado_max=62.5` (valores default configuráveis).
- **IMPORTANTE**: para ITRA, os thresholds da Seção 7.3 do CLAUDE.md (EACT: <2.3/≥3.7, EADRT: <2.0/≥3.0 etc.) também devem ser convertidos para escala 0–100. A fórmula genérica é: `threshold_0_100 = (threshold_1_5 - 1) * 25`. Ex.: EACT baixo_max=2.29 → `(2.29-1)*25 = 32.25`, moderado_max=3.69 → `(3.69-1)*25 = 67.25`.

### 2. Adicionar cálculo de Prevalência ao `risk_engine.py`

Nova função:
```python
def calcular_prevalencia(
    escores_por_respondente: list[float],  # escore 0-100 de cada respondente no domínio
    limite_elevado: float = 62.5,
) -> tuple[float, str]:
    """Retorna (percentual_elevados, prioridade)."""
    if not escores_por_respondente:
        return 0.0, "P3"
    n_elevados = sum(1 for e in escores_por_respondente if e >= limite_elevado)
    pct = n_elevados / len(escores_por_respondente)
    if pct >= 0.50:
        prioridade = "P1"
    elif pct >= 0.25:
        prioridade = "P2"
    else:
        prioridade = "P3"
    return pct, prioridade
```

### 3. Atualizar `CriterioVersao`

- `n_minimo_respondentes`: mudar default de 3 para **5** (pode ser alterado pelo admin).
- Adicionar campos:
  - `limite_baixo` (DecimalField, default=37.5) — "Limite máximo - Baixo" do Excel
  - `limite_elevado` (DecimalField, default=62.5) — "Limite mínimo - Elevado" do Excel
  - `prevalencia_p1` (DecimalField, default=0.50) — percentual mínimo de respondentes elevados para P1
  - `prevalencia_p2` (DecimalField, default=0.25) — percentual mínimo para P2
  - `periodo_referencia` (CharField, default="Últimos 3 meses")
- Os thresholds existentes (`thresholds_por_dominio`) devem ser atualizados para escala 0–100.

### 4. Atualizar `seeds/copsoq_rr_revestir.json` e `seeds/itra.json`

- Os thresholds nos seeds devem mudar para escala 0–100:
  - COPSOQ: `"baixo_max": 37.5, "moderado_max": 62.5` (antes era 2.5 e 3.4)
  - ITRA EACT: `"baixo_max": 32.25, "moderado_max": 67.25`
  - ITRA EADRT: `"baixo_max": 25.0, "moderado_max": 47.5`
  - ITRA ECHT/EIPSTN/EIPSTP: `"baixo_max": 32.25, "moderado_max": 67.25`
- Os `Dominio.thresholds_referencia_baixo_max` e `moderado_max` devem acompanhar.

### 5. Atualizar `calculo_risco.py`

- `calcular_dominio()` deve calcular o escore de cada respondente individualmente (não só a média), para poder computar a prevalência.
- Persistir no `EscoreDominio`:
  - `escore` agora em escala 0–100 (era 1–5)
  - Novo campo `percentual_elevados` (DecimalField) — proporção de respondentes na faixa elevada
  - Novo campo `prioridade` (CharField: P1/P2/P3/AGRUPAR)
- O campo `EscoreDominio.escore` muda de `max_digits=4, decimal_places=2` para `max_digits=5, decimal_places=2` (agora vai de 0.00 a 100.00).

### 6. Atualizar `test_risk_engine.py`

- Todos os testes que usam thresholds na escala 1–5 devem ser convertidos para escala 0–100.
- Adicionar testes para `calcular_prevalencia()`.

### 7. Atualizar management command `criar_criterio_versao`

- O comando deve usar os novos thresholds em escala 0–100 ao montar o `CriterioVersao`.

## Resultado esperado

- `risk_engine.py` opera inteiramente em escala 0–100.
- `CriterioVersao` tem os novos campos de configuração (limites, prevalência).
- `EscoreDominio` armazena escore 0–100, percentual de elevados e prioridade.
- Seeds e thresholds atualizados.
- Todos os testes passando com os valores convertidos.

## Arquivos a modificar

- `avaliacoes/risk_engine_lib/risk_engine.py`
- `avaliacoes/risk_engine_lib/test_risk_engine.py`
- `avaliacoes/models.py` — `CriterioVersao`, `EscoreDominio`
- `avaliacoes/services/calculo_risco.py`
- `avaliacoes/services/criterio_versao.py`
- `seeds/copsoq_rr_revestir.json`
- `seeds/itra.json`
- `instrumentos/models.py` — `Dominio.thresholds_referencia_*`
- `instrumentos/management/commands/load_instrumentos.py`
- `instrumentos/management/commands/criar_criterio_versao.py`
