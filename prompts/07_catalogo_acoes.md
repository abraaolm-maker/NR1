# Prompt 07 — Catálogo de Ações Pré-definidas

## Contexto

A planilha `Catalogo_Acoes` do Excel lista 18 ações sugeridas (2 por domínio × 9 domínios: uma para nível Moderado e uma para Elevado), cada uma com:

| Coluna | Descrição |
|---|---|
| Domínio | D1 a D9 |
| Nível | Moderado ou Elevado |
| Ação sugerida | Texto da medida preventiva |
| Hierarquia | Hierarquia de controle (Organização do trabalho, Eliminação/redução na fonte, Gestão/organização, Resposta imediata) |
| Indicador | Como medir se a ação funcionou |

Exemplos do Excel:
- D1 Moderado: "Revisar prioridades, prazos, interrupções e distribuição diária de tarefas." / Organização do trabalho / "Fila de demandas, horas extras, retrabalho e cumprimento de pausas."
- D1 Elevado: "Redimensionar capacidade/efetivo, reduzir picos evitáveis e redesenhar fluxo e metas." / Eliminação/redução na fonte / "Carga planejada x capacidade, horas extras, atrasos e retrabalho."

O sistema atual gera um `PlanoDeAcao` genérico ("Definir e executar medida corretiva para o domínio X (banda Y).") — sem sugestão concreta.

## Tarefas

### 1. Criar modelo `CatalogoAcao`

Em `avaliacoes/models.py`:

```python
class HierarquiaControle(models.TextChoices):
    ELIMINACAO = "eliminacao", "Eliminação/redução na fonte"
    ORGANIZACAO = "organizacao", "Organização do trabalho"
    GESTAO = "gestao", "Gestão/organização"
    CONTROLE_COLETIVO = "controle_coletivo", "Controle coletivo"
    REDESENHO = "redesenho", "Redesenho do trabalho"
    RESPOSTA_IMEDIATA = "resposta_imediata", "Resposta imediata e eliminação da exposição"

class CatalogoAcao(models.Model):
    dominio = models.ForeignKey(Dominio, on_delete=models.CASCADE, related_name="acoes_catalogo")
    nivel = models.CharField(max_length=10, choices=Classificacao.choices)  # Moderado ou Elevado
    acao_sugerida = models.TextField()
    hierarquia = models.CharField(max_length=30, choices=HierarquiaControle.choices)
    indicador = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["dominio", "nivel"], name="uniq_catalogo_por_dominio_nivel")
        ]
        ordering = ["dominio__ordem", "nivel"]
```

### 2. Criar seed `seeds/catalogo_acoes.json`

Conteúdo completo extraído do Excel, cobrindo os 9 domínios × 2 níveis = 18 ações. Formato:

```json
{
  "instrument_code": "COPSOQ_RR_REVESTIR",
  "acoes": [
    {
      "dominio_codigo": "D1",
      "nivel": "Moderado",
      "acao_sugerida": "Revisar prioridades, prazos, interrupções e distribuição diária de tarefas.",
      "hierarquia": "organizacao",
      "indicador": "Fila de demandas, horas extras, retrabalho e cumprimento de pausas."
    },
    {
      "dominio_codigo": "D1",
      "nivel": "Elevado",
      "acao_sugerida": "Redimensionar capacidade/efetivo, reduzir picos evitáveis e redesenhar fluxo e metas.",
      "hierarquia": "eliminacao",
      "indicador": "Carga planejada x capacidade, horas extras, atrasos e retrabalho."
    },
    ...
  ]
}
```

Incluir TODAS as 18 linhas do Excel (dados completos já extraídos na análise anterior).

### 3. Management command `load_catalogo_acoes`

Importa o seed para o banco. Padrão: `update_or_create` por (dominio, nivel).

### 4. Atualizar `_gerar_plano_de_acao_se_necessario()`

Em vez do texto genérico, buscar a ação do catálogo:

```python
def _gerar_plano_de_acao_se_necessario(classificacao_risco, suprimido):
    if suprimido or classificacao_risco.banda == "Aceitável":
        return
    if classificacao_risco.planos_de_acao.exists():
        return

    dominio = classificacao_risco.escore_dominio.dominio
    classificacao = classificacao_risco.escore_dominio.classificacao

    # Buscar ação do catálogo
    catalogo = CatalogoAcao.objects.filter(dominio=dominio, nivel=classificacao).first()

    PlanoDeAcao.objects.create(
        classificacao_risco=classificacao_risco,
        medida=catalogo.acao_sugerida if catalogo else f"Definir medida para {dominio.nome} ({classificacao}).",
        hierarquia=catalogo.hierarquia if catalogo else "",
        indicador=catalogo.indicador if catalogo else "",
        prazo=...,
        status=StatusPlanoDeAcao.PENDENTE,
    )
```

### 5. Tela de Catálogo de Ações no painel (admin-only)

View `catalogo_acoes` listando todas as ações do catálogo, com botão de edição por ação (para personalização futura). Formulário simples: editar `acao_sugerida`, `hierarquia`, `indicador`.

### 6. Garantir editabilidade

O catálogo é pré-definido pelo seed mas **deve ser editável** pelo admin via Django Admin e pelo painel. As ações vêm do seed como default, mas o profissional responsável pode personalizá-las para a realidade da empresa.

## Resultado esperado

- Modelo `CatalogoAcao` com 18 ações pré-definidas (9 domínios × 2 níveis).
- Seed JSON + management command de carga.
- `PlanoDeAcao` gerado automaticamente usa a ação do catálogo (se existir) em vez de texto genérico.
- Tela no painel para visualizar e editar o catálogo.
- Todos os testes passando.

## Arquivos a criar/modificar

- `avaliacoes/models.py` — novo `CatalogoAcao`, `HierarquiaControle`
- `seeds/catalogo_acoes.json` — novo seed
- `instrumentos/management/commands/load_catalogo_acoes.py` — novo command
- `avaliacoes/services/calculo_risco.py` — atualizar geração de plano de ação
- `avaliacoes/painel_views.py` + `painel_urls.py` — nova view de catálogo
- Template `avaliacoes/templates/painel/catalogo_acoes.html`
- Testes
