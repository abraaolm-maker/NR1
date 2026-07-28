# Prompt 09 — Entrevista e Observação (checklist de triangulação)

## Contexto

A planilha `Entrevista_Observacao` do Excel contém 16 itens de triangulação, divididos em dois tipos:

**Entrevista com liderança (6 itens):**
1. Quais são os períodos de maior demanda e por quê?
2. Há acúmulo de função, substituição informal ou tarefas fora do papel definido?
3. Como são distribuídas tarefas, pausas, folgas, prioridades e cobranças?
4. Que registros existem sobre conflitos, retrabalho, erros, perdas ou reclamações?
5. Quais controles previnem assédio, violência, retaliação e discriminação?
6. Que evidências comprovam comunicação, reuniões, treinamentos e medidas preventivas?

**Observação em campo (10 itens):**
7. Dimensionamento de pessoal compatível com a demanda real.
8. Pausas e acesso a banheiro/hidratação são viáveis na rotina.
9. Prioridades, responsabilidades e mudanças são comunicadas com clareza.
10. Não há cobrança vexatória ou exposição pública.
11. Há canal de relato e fluxo de resposta sem retaliação.
12. O fluxo físico e informacional é adequado ao trabalho.
13. Tarefas simultâneas e interrupções têm controles definidos.
14. Integração e treinamento são adequados às rotinas reais.
15. O tratamento entre liderança, colegas, clientes e terceiros é respeitoso.
16. Há registros mínimos de acompanhamento e melhoria contínua.

Cada item tem: **Conforme / Não conforme / Evidência ou observação (texto)**.

O sistema atual tem `IndicadorIndireto` (5 tipos genéricos: absenteísmo, turnover, CAT, checklist, relato), que é bem diferente deste checklist estruturado.

## Tarefas

### 1. Criar modelo `ChecklistTriangulacao`

Em `avaliacoes/models.py`:

```python
class TipoChecklist(models.TextChoices):
    ENTREVISTA = "entrevista", "Entrevista com liderança"
    OBSERVACAO = "observacao", "Observação em campo"

class ConformidadeChecklist(models.TextChoices):
    CONFORME = "conforme", "Conforme"
    NAO_CONFORME = "nao_conforme", "Não conforme"
    NAO_AVALIADO = "nao_avaliado", "Não avaliado"

class ItemChecklistTriangulacao(models.Model):
    """Item pré-definido do checklist de triangulação (seed)."""
    tipo = models.CharField(max_length=15, choices=TipoChecklist.choices)
    texto = models.TextField()
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["tipo", "ordem"]

class RespostaChecklistTriangulacao(models.Model):
    """Resposta do profissional responsável ao checklist, vinculada a uma Aplicacao ou GHE."""
    aplicacao = models.ForeignKey(Aplicacao, on_delete=models.CASCADE, related_name="respostas_checklist")
    item = models.ForeignKey(ItemChecklistTriangulacao, on_delete=models.PROTECT)
    conformidade = models.CharField(max_length=15, choices=ConformidadeChecklist.choices,
        default=ConformidadeChecklist.NAO_AVALIADO)
    evidencia = models.TextField(blank=True, verbose_name="Evidência/observação")
    respondido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    respondido_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["aplicacao", "item"], name="uniq_checklist_por_aplicacao_item")
        ]
```

### 2. Criar seed `seeds/checklist_triangulacao.json`

```json
{
  "itens": [
    {"tipo": "entrevista", "ordem": 1, "texto": "Quais são os períodos de maior demanda e por quê?"},
    {"tipo": "entrevista", "ordem": 2, "texto": "Há acúmulo de função, substituição informal ou tarefas fora do papel definido?"},
    {"tipo": "entrevista", "ordem": 3, "texto": "Como são distribuídas tarefas, pausas, folgas, prioridades e cobranças?"},
    {"tipo": "entrevista", "ordem": 4, "texto": "Que registros existem sobre conflitos, retrabalho, erros, perdas ou reclamações?"},
    {"tipo": "entrevista", "ordem": 5, "texto": "Quais controles previnem assédio, violência, retaliação e discriminação?"},
    {"tipo": "entrevista", "ordem": 6, "texto": "Que evidências comprovam comunicação, reuniões, treinamentos e medidas preventivas?"},
    {"tipo": "observacao", "ordem": 1, "texto": "Dimensionamento de pessoal compatível com a demanda real."},
    {"tipo": "observacao", "ordem": 2, "texto": "Pausas e acesso a banheiro/hidratação são viáveis na rotina."},
    {"tipo": "observacao", "ordem": 3, "texto": "Prioridades, responsabilidades e mudanças são comunicadas com clareza."},
    {"tipo": "observacao", "ordem": 4, "texto": "Não há cobrança vexatória ou exposição pública."},
    {"tipo": "observacao", "ordem": 5, "texto": "Há canal de relato e fluxo de resposta sem retaliação."},
    {"tipo": "observacao", "ordem": 6, "texto": "O fluxo físico e informacional é adequado ao trabalho."},
    {"tipo": "observacao", "ordem": 7, "texto": "Tarefas simultâneas e interrupções têm controles definidos."},
    {"tipo": "observacao", "ordem": 8, "texto": "Integração e treinamento são adequados às rotinas reais."},
    {"tipo": "observacao", "ordem": 9, "texto": "O tratamento entre liderança, colegas, clientes e terceiros é respeitoso."},
    {"tipo": "observacao", "ordem": 10, "texto": "Há registros mínimos de acompanhamento e melhoria contínua."}
  ]
}
```

### 3. Management command `load_checklist_triangulacao`

Carrega os 16 itens pré-definidos. `update_or_create` por (tipo, ordem).

### 4. View de preenchimento do checklist (admin-only)

Criar view `checklist_triangulacao` em `avaliacoes/painel_views.py`:
- Lista os 16 itens pré-definidos
- Para cada item: radio (Conforme / Não conforme / Não avaliado) + textarea de evidência
- Formulário inline (todos os itens na mesma página)
- Salva `RespostaChecklistTriangulacao` para cada item

### 5. Integrar no relatório PDF

Adicionar seção "5. Entrevista e Observação" no template `inventario.html`, depois das evidências complementares:
- Tabela com: Tipo | Pergunta/item | Conforme/Não conforme | Evidência
- Apenas itens que foram avaliados (excluir "Não avaliado")

### 6. Relação com `IndicadorIndireto`

`IndicadorIndireto` **não é substituído** — continua existindo para absenteísmo, turnover, CAT, etc. O `ChecklistTriangulacao` é um complemento estruturado. Os dois coexistem na seção de evidências do relatório.

## Resultado esperado

- 16 itens pré-definidos carregados via seed.
- Tela de preenchimento do checklist no painel (admin-only).
- Seção no PDF com a tabela de entrevista/observação.
- `IndicadorIndireto` inalterado.
- Todos os testes passando.

## Arquivos a criar/modificar

- `avaliacoes/models.py` — novos models
- `seeds/checklist_triangulacao.json` — novo seed
- `instrumentos/management/commands/load_checklist_triangulacao.py` — novo command
- `avaliacoes/painel_views.py` + `painel_urls.py` — nova view
- Template `avaliacoes/templates/painel/checklist_triangulacao.html`
- `relatorios/templates/relatorios/inventario.html` — nova seção
- `relatorios/services/pdf.py` — incluir dados do checklist no contexto
- Testes + migrations
