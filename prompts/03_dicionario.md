# Prompt 03 — Dicionário (padronizar escala 0–100)

## Contexto

A planilha `Dicionario` do Excel lista os 34 itens do COPSOQ com a fórmula de conversão para escala 0–100:
- Itens RISCO (direto): `(resposta - 1) × 25` → valores possíveis: 0, 25, 50, 75, 100
- Itens PROTETIVO (inverter): `(5 - resposta) × 25` → valores possíveis: 0, 25, 50, 75, 100

**Este prompt depende do Prompt 02 já ter sido implementado** (risk_engine.py já opera em escala 0–100).

## Tarefa

Verificar que, após a implementação do Prompt 02:

1. O `risk_engine.py::inverter_se_necessario()` já produz valores na escala 0–100 usando a fórmula genérica equivalente à do Excel.
2. Para a escala COPSOQ (min=1, max=5), a fórmula genérica `(valor_bruto - escala_min) * 100 / (escala_max - escala_min)` gera exatamente `(resposta - 1) * 25`, que é a fórmula do Dicionário.
3. Para PROTETIVO: `(escala_max - valor_bruto) * 100 / (escala_max - escala_min)` gera exatamente `(5 - resposta) * 25`.

Se o Prompt 02 foi implementado corretamente, este ponto já está coberto. Confirmar rodando `py -m pytest` e verificando que os testes de inversão de polaridade no `test_risk_engine.py` produzem valores 0–100.

## Resultado esperado

- Nenhuma mudança adicional de código se o Prompt 02 estiver completo.
- Confirmação via testes de que a escala está correta.

## Arquivos relevantes

- `avaliacoes/risk_engine_lib/risk_engine.py` — `inverter_se_necessario()`
- `avaliacoes/risk_engine_lib/test_risk_engine.py`
