# Prompt 04 — Pontuação Anônima (escore por respondente + mapa de calor)

## Contexto

A planilha `Pontuacao_anonima` do Excel mostra uma linha por respondente com:
- Data, GHE/grupo, Tempo na organização, Modalidade
- D1 a D9: escore de risco 0–100 do respondente naquele domínio
- Índice geral: média dos 9 escores de domínio

Cada célula de D1–D9 e Índice geral tem um **mapa de calor**: verde (próximo de 0) → amarelo (próximo de 50) → vermelho (próximo de 100).

## O que o sistema precisa

### 1. Calcular e armazenar escore por respondente por domínio

Atualmente, `calcular_dominio()` em `calculo_risco.py` calcula a média agregada de TODOS os respondentes. O Excel calcula o escore **por respondente** (média dos itens daquele domínio para aquele respondente, já em escala 0–100).

Criar modelo `EscoreRespondente` em `avaliacoes/models.py`:

```python
class EscoreRespondente(models.Model):
    respondente = models.ForeignKey(Respondente, on_delete=models.CASCADE, related_name="escores")
    dominio = models.ForeignKey(Dominio, on_delete=models.PROTECT, related_name="escores_respondentes")
    escore = models.DecimalField(max_digits=5, decimal_places=2)  # escala 0-100
    classificacao = models.CharField(max_length=10, choices=Classificacao.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["respondente", "dominio"], name="uniq_escore_respondente_dominio")
        ]
```

### 2. Atualizar `calculo_risco.py`

Em `calcular_dominio()`, antes de calcular a média agregada:

1. Para cada respondente da Aplicacao que respondeu aquele domínio:
   - Pegar todas as `Resposta` daquele respondente para itens daquele domínio
   - Calcular o escore individual (média dos valores ajustados, escala 0–100)
   - Classificar (Baixo/Moderado/Elevado) usando os thresholds
   - Salvar em `EscoreRespondente`
2. A média agregada do domínio = média dos escores individuais dos respondentes
3. O percentual de elevados = nº de respondentes com classificação "Elevado" / total de respondentes
4. A prioridade (P1/P2/P3) = resultado de `calcular_prevalencia(escores_individuais)`

### 3. Calcular Índice Geral por respondente

O "Índice geral" do Excel é a média dos escores de D1 a D9 de cada respondente. Armazenar no `EscoreRespondente` com um domínio virtual "GERAL" OU como campo calculado no `Respondente` (campo `indice_geral`, DecimalField nullable).

**Decisão recomendada**: campo `indice_geral` no `Respondente` (mais simples, não polui o modelo de Dominio com um domínio falso).

### 4. View/tela de Pontuação Anônima no painel

Criar view `pontuacao_anonima` em `avaliacoes/painel_views.py` acessível a partir do detalhe da Aplicacao. Mostra tabela com:
- Data | GHE/grupo | Tempo na organização | Modalidade | D1 | D2 | ... | D9 | Índice geral
- Cada célula D1–D9 e Índice com classe CSS de mapa de calor

CSS do mapa de calor (inline style calculado no template ou via classes):
```css
/* Verde (0) → Amarelo (50) → Vermelho (100) */
/* Usar interpolação no template com style="background-color: ..." */
```

No template, calcular a cor via um template tag ou inline:
- 0–37.5: tons de verde (situação favorável)
- 37.5–62.5: tons de amarelo (intermediário)
- 62.5–100: tons de vermelho (risco para a saúde)

**Nota**: esta tela é do admin (exibe dados anônimos agregados, mas por respondente individual). O gestor da empresa NÃO vê esta tela.

### 5. Migration

- Novo modelo `EscoreRespondente`
- Novo campo `Respondente.indice_geral` (DecimalField, null=True, blank=True, max_digits=5, decimal_places=2)

## Resultado esperado

- `EscoreRespondente` criado com escore 0–100 por respondente por domínio.
- `calculo_risco.py` calcula escores individuais antes de agregar.
- `Respondente.indice_geral` calculado automaticamente.
- Tela de Pontuação Anônima com mapa de calor funcional.
- Todos os testes passando + novos testes para escore por respondente.

## Arquivos a modificar/criar

- `avaliacoes/models.py` — novo `EscoreRespondente`, novo campo `Respondente.indice_geral`
- `avaliacoes/services/calculo_risco.py` — calcular escores individuais
- `avaliacoes/painel_views.py` — nova view `pontuacao_anonima`
- `avaliacoes/painel_urls.py` — nova rota
- Template `avaliacoes/templates/painel/pontuacao_anonima.html`
- `conftest.py` / testes — novos testes
