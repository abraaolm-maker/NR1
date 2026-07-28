# Prompt 08 — Plano de Ação (expandir para 15 campos do Excel)

## Contexto

A planilha `Plano_de_Acao` do Excel tem 15 colunas por ação:

| # | Coluna | Tipo | No sistema atual? |
|---|---|---|---|
| 1 | ID | Texto (A01, A02...) | Não (usa pk numérico) |
| 2 | GHE/grupo | Texto | Sim (via classificacao_risco → escore_dominio → aplicacao → ghe) |
| 3 | Domínio/perigo | Texto | Sim (via classificacao_risco → escore_dominio → dominio) |
| 4 | Evidência do diagnóstico | Texto livre | **NÃO** |
| 5 | Medida escolhida | Texto | Sim (`medida`) |
| 6 | Hierarquia | Texto | **NÃO** |
| 7 | Responsável | FK User | Sim (`responsavel`) — mas no Excel é texto livre |
| 8 | Prazo | Data ou texto | Sim (`prazo`, DateField) — Excel usa "30 dias", "60 dias", "Imediato" |
| 9 | Indicador | Texto | **NÃO** |
| 10 | Meta | Texto | **NÃO** |
| 11 | Evidência de execução | Texto | Sim (`evidencia_execucao`) |
| 12 | Status | Texto | Sim (`status`) — mas o Excel tem mais opções: "Planejada", "Contínua" |
| 13 | Verificação de eficácia | Texto | **NÃO** |
| 14 | Data da revisão | Date | **NÃO** |
| 15 | Observações | Texto | **NÃO** |

O `PlanoDeAcao` atual tem apenas: `classificacao_risco`, `medida`, `responsavel`, `prazo`, `status`, `evidencia_execucao`.

## Tarefas

### 1. Expandir modelo `PlanoDeAcao`

Adicionar os campos faltantes em `avaliacoes/models.py`:

```python
class StatusPlanoDeAcao(models.TextChoices):
    PENDENTE = "pendente", "Pendente"
    PLANEJADA = "planejada", "Planejada"
    EM_ANDAMENTO = "em_andamento", "Em andamento"
    CONCLUIDO = "concluido", "Concluído"
    CONTINUA = "continua", "Contínua"
    ATRASADO = "atrasado", "Atrasado"

class PlanoDeAcao(models.Model):
    classificacao_risco = models.ForeignKey(...)
    # --- campos existentes ---
    medida = models.TextField(verbose_name="Medida escolhida")
    responsavel = models.CharField(max_length=200, blank=True, verbose_name="Responsável")
    # MUDAR: responsavel de FK User para CharField (texto livre, como no Excel)
    prazo = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=StatusPlanoDeAcao.choices, default=StatusPlanoDeAcao.PLANEJADA)
    evidencia_execucao = models.TextField(blank=True, verbose_name="Evidência de execução")

    # --- campos novos ---
    codigo = models.CharField(max_length=10, blank=True, verbose_name="ID da ação",
        help_text="Identificador manual (ex.: A01, A02). Gerado automaticamente se vazio.")
    evidencia_diagnostico = models.TextField(blank=True, verbose_name="Evidência do diagnóstico",
        help_text="O que o diagnóstico mostrou para justificar esta ação.")
    hierarquia = models.CharField(max_length=100, blank=True, verbose_name="Hierarquia de controle",
        help_text="Ex.: Organização do trabalho, Eliminação/redução na fonte.")
    indicador = models.TextField(blank=True, verbose_name="Indicador de acompanhamento")
    meta = models.TextField(blank=True, verbose_name="Meta")
    verificacao_eficacia = models.TextField(blank=True, verbose_name="Verificação de eficácia")
    data_revisao = models.DateField(null=True, blank=True, verbose_name="Data da revisão")
    observacoes = models.TextField(blank=True, verbose_name="Observações")
```

### 2. Mudar `responsavel` de FK para CharField

O Excel usa texto livre ("Direção de Operações", "Gerência Industrial + SESMT", etc.), não um FK para User. O sistema deve acompanhar. A migration precisa:
- Criar campo `responsavel_texto` (CharField)
- Copiar `responsavel.get_full_name()` para `responsavel_texto` nos registros existentes
- Remover o FK `responsavel`
- Renomear `responsavel_texto` para `responsavel`

Ou, mais simples se o banco for resetado (o usuário já confirmou que é teste): fazer direto.

### 3. Atualizar `_gerar_plano_de_acao_se_necessario()`

Preencher os novos campos automaticamente a partir do catálogo (Prompt 07) e do diagnóstico:

```python
PlanoDeAcao.objects.create(
    classificacao_risco=classificacao_risco,
    codigo=f"A{str(PlanoDeAcao.objects.count() + 1).zfill(2)}",
    medida=catalogo.acao_sugerida if catalogo else ...,
    hierarquia=catalogo.hierarquia if catalogo else "",
    indicador=catalogo.indicador if catalogo else "",
    evidencia_diagnostico=f"{dominio.nome} {classificacao} no GHE {ghe.nome}; índice de risco {escore}.",
    prazo=prazo_calculado,
    status=StatusPlanoDeAcao.PLANEJADA,
)
```

### 4. Atualizar o formulário de Plano de Ação no painel

Se existir tela de edição de PlanoDeAcao no painel, incluir todos os 15 campos. Se não existir, criar `plano_de_acao_update` com form completo.

### 5. Atualizar o template do relatório PDF

O Plano de Ação (Seção 7 do PDF) deve mostrar todos os 15 campos em uma tabela expandida.

### 6. Migration

Novos campos + mudança do `responsavel` de FK para CharField.

## Resultado esperado

- `PlanoDeAcao` com os 15 campos do Excel.
- Geração automática preenchendo código, evidência, hierarquia, indicador a partir do catálogo e diagnóstico.
- Status expandido com "Planejada" e "Contínua".
- PDF atualizado com tabela de plano de ação completa.
- Todos os testes passando (ajustar fixtures que usam `responsavel` como FK).

## Arquivos a modificar

- `avaliacoes/models.py` — expandir `PlanoDeAcao`, `StatusPlanoDeAcao`
- `avaliacoes/services/calculo_risco.py` — atualizar geração automática
- `avaliacoes/painel_views.py` — form de edição do plano
- `relatorios/templates/relatorios/inventario.html` — Seção 7 do PDF
- Migrations
- Testes (ajustar fixtures)
