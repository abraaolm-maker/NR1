# Prompt 05 — Alertas Agregados D9

## Contexto

A planilha `Alertas_agregados` do Excel mostra, por GHE:
- Quantidade de respostas (respondentes)
- **Alertas D9**: contagem de respondentes que marcaram D9.1 OU D9.2 com `valor_bruto >= 4`

No sistema, D9.1 e D9.2 já estão marcados como `evento_grave=true` no seed do COPSOQ. O `risk_engine.py` já verifica `verificar_evento_grave()` (se alguma resposta de item com `evento_grave=True` tem valor ≥ `LIMIAR_EVENTO_GRAVE`), mas isso é um booleano por domínio, não uma **contagem agregada por GHE**.

## Tarefas

### 1. Criar função de contagem de alertas D9

Em `avaliacoes/services/calculo_risco.py`, nova função:

```python
def contar_alertas_d9(aplicacao: Aplicacao) -> dict:
    """Conta respondentes com evento grave em D9 (D9.1 ou D9.2 com valor >= limiar).
    Retorna {'n_respondentes': int, 'alertas_d9': int}."""
    limiar = aplicacao.criterio_versao.limiar_evento_grave
    itens_graves = Item.objects.filter(
        dominio__instrumento=aplicacao.instrumento,
        evento_grave=True,
    ).values_list("pk", flat=True)

    respondentes_com_alerta = (
        Resposta.objects.filter(
            respondente__aplicacao=aplicacao,
            item_id__in=itens_graves,
            valor_bruto__gte=limiar,
        )
        .values("respondente_id")
        .distinct()
        .count()
    )

    n_respondentes = aplicacao.respondentes.filter(concluido_em__isnull=False).count()

    return {
        "n_respondentes": n_respondentes,
        "alertas_d9": respondentes_com_alerta,
    }
```

### 2. Persistir alertas no `EscoreDominio` ou em campo separado

Adicionar campo `alertas_evento_grave` (PositiveSmallIntegerField, default=0) ao `EscoreDominio` — preenchido em `calcular_dominio()` apenas para domínios que contêm itens `evento_grave=True` (no COPSOQ, só D9).

Ou, mais alinhado com o Excel: adicionar ao modelo `Aplicacao` um campo `alertas_d9` (PositiveSmallIntegerField, default=0), atualizado ao final de `calcular_aplicacao()`.

**Recomendação**: campo na `Aplicacao` (é um dado agregado da aplicação inteira, não de um domínio).

### 3. Exibir na tela de detalhe da Aplicacao

No template `aplicacao_detail.html`, adicionar uma seção "Alertas D9" mostrando:
- N respondentes concluídos
- Alertas D9: X respondente(s) com evento grave
- Se alertas_d9 > 0: banner de alerta vermelho com nota "Ativar fluxo protegido imediato"

### 4. Tela de Alertas Agregados (view separada, admin-only)

Criar view `alertas_agregados` que lista todas as Aplicacoes de uma Unidade/Relatório com a contagem de alertas D9 por GHE — reproduzindo a tabela do Excel.

## Resultado esperado

- Contagem de alertas D9 calculada e persistida por Aplicacao.
- Exibida no detalhe da Aplicacao e em view de alertas agregados.
- Teste unitário: simular respondente com D9.1=4 e verificar que alertas_d9=1.
- Todos os testes passando.

## Arquivos a modificar/criar

- `avaliacoes/models.py` — novo campo `Aplicacao.alertas_d9`
- `avaliacoes/services/calculo_risco.py` — `contar_alertas_d9()`, chamado em `calcular_aplicacao()`
- `avaliacoes/painel_views.py` — atualizar `aplicacao_detail`, nova view `alertas_agregados`
- Templates: `aplicacao_detail.html`, novo `alertas_agregados.html`
- Testes
