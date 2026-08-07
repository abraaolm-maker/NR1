# Solicitações pendentes — fila de trabalho

> Arquivo de trabalho vivo. Toda vez que você pedir uma mudança na conversa, eu:
> 1. Registro o pedido aqui, na sua própria seção.
> 2. Avalio se ele tem relação/conflito com algo já decidido no `CLAUDE.md` ou com outra
>    solicitação já registrada neste arquivo (e anoto isso na seção "Relação com o que já existe").
> 3. Traduzo o pedido numa especificação executável — arquivos, funções e comportamento
>    esperado, no mesmo padrão de precisão do `CLAUDE.md` — pronta pra ser implementada
>    quando você mandar (aqui ou numa sessão nova, sem precisar reexplicar o contexto).
> 4. Reenvio o `.md` inteiro atualizado.
>
> Nada aqui é executado sozinho — cada item só vira código quando você confirmar. Itens já
> implementados são movidos pra "Concluído" (com a data e o commit), não apagados — assim o
> histórico de por que uma decisão foi tomada não se perde.

---

> **Atualização de 2026-08-06**: os 12 itens abaixo (1 a 12) foram implementados na Etapa 2 do
> plano de execução pedido pelo usuário ("1 priorize a ordem... 2 execute os ajustes, 3 deixa pra
> rodar qualquer teste"). Código e migrations aplicados localmente, `manage.py check` sem erros.
> Ordem de execução usada (respeitando as duas dependências reais: item 5 antes do 8, item 9
> antes do 10): 2 → 1 → 9 → 10 → 5 → 8 → 7 → 6 → 3 → 4 → 11 → 12. Decisões tomadas sem confirmação
> explícita, por já terem sido sinalizadas antes e o usuário ter pedido pra seguir: item 4
> implementado com a opção (a) (aceitar buraco na numeração da fita, não renumerar
> dinamicamente); item 5 implementado com os 3 achados juntos (causa raiz + os 2 achados
> adicionais de timestamp exato).
>
> **Pendências pós-deploy** (não são bugs, são passos que só fazem sentido rodar no ambiente real):
> - Item 1: a Aplicacao #3 real (e qualquer outra já calculada sob o `CriterioVersao` v1.0)
>   continua com os thresholds antigos do COPSOQ Oficial — é o comportamento correto por design
>   (rastreabilidade, CLAUDE.md Seção 7.8), só Aplicações NOVAS usam a v1.1 automaticamente.
> - Item 9: a Aplicacao #3 real tem `EscoreDominio` desatualizado pela contribuição do Respondente
>   9 (parcial) — precisa de um recálculo manual pós-deploy (comando fornecido na resposta da
>   conversa) se ela já estiver encerrada.
> - Item 5: respondentes já existentes mantêm o alias sequencial antigo — a correção só vale pra
>   quem responder a partir do deploy.
>
> **Atualização de 2026-08-07 — Etapa 3 (testes) e itens 13-20**: os itens 13 a 20 (segundo lote,
> reprodução visual da referência Solute RH — capa, base técnica, resultados, achados, panorama)
> foram implementados na ordem 13 → 17 → 18 → 20 → 19 → 14 → 15 → 16 (itens que reestruturam
> seções primeiro). Detalhamento completo em CLAUDE.md Seção 6.27. Em seguida, a suíte completa de
> testes (143 testes, todos os apps) foi executada — 3 correções necessárias (fixture
> `responder_dominio` sem `concluido_em`, um teste que validava o comportamento antigo de índice
> geral, duas asserções de número de seção desatualizadas), todas por mudança de comportamento já
> esperada, nenhum bug novo encontrado. **Suíte 100% verde (143 passed)** — código commitado e
> enviado (push) em seguida.

## Pendentes

### 1. Bug: Classificação do COPSOQ Oficial sempre "Elevado" (limiares em escala errada)

**Pedido original**: você testou uma nova Aplicação e viu a coluna "Classificação" marcando
"Elevado" em todos os domínios, mesmo em escores baixos (ex.: 8,33). Perguntou o motivo.

**Diagnóstico já feito** (2026-08-06, mesma conversa): confirmado bug real, não comportamento
esperado. `calcular_escore_dominio()` (`avaliacoes/risk_engine_lib/risk_engine.py:186`) sempre
produz o escore na escala 0–100. Mas os limiares `baixo_max`/`moderado_max` do COPSOQ Oficial em
`seeds/copsoq_oficial.json` foram gravados na escala antiga de 1–5 (os tercis do manual: `2.33` e
`3.66`) e nunca convertidos pra 0–100 — `criar_criterio_versao.py` copia esses valores
literalmente pro `CriterioVersao.thresholds_por_dominio`, sem reescalar. Resultado:
`classificar_escore()` compara um escore 0–100 contra um limiar pensado pra 1–5, então qualquer
escore acima de ~3,66 (ou seja, quase todos) cai em "Elevado".

**Relação com o que já existe**: não afeta a Banda de risco (essa já usa a prevalência,
CLAUDE.md Seção 6.14, e está correta na sua tela) — só a coluna "Classificação", que ainda é
citada no PDF (Seção 5, Seção "Como ler o selo de Banda") e na tela de Diagnóstico GHE. É
consistente com o princípio da Seção 3, item 9 do CLAUDE.md (pontos de corte do ITRA/COPSOQ como
parâmetro configurável, nunca hardcoded) — a correção é só recalibrar o parâmetro, não mudar a
lógica.

**Especificação de execução**:
1. Recalcular `baixo_max`/`moderado_max` de cada domínio COPSOQ Oficial em
   `seeds/copsoq_oficial.json`, convertendo os tercis do manual (2,33 e 3,66, escala 1–5) pra
   escala 0–100: `baixo_max ≈ 33.25`, `moderado_max ≈ 66.5` (fórmula: `(valor - 1) / 4 * 100`,
   mesma direção de `inverter_se_necessario`).
2. Recarregar o seed (`load_instrumentos`) e gerar um novo `CriterioVersao` (mesmo comando/fluxo
   já usado em `criar_criterio_versao.py`) — não editar `CriterioVersao` existentes diretamente
   (são snapshots imutáveis citados por Relatórios já gerados, CLAUDE.md Seção 7.8).
3. Confirmar com um teste (ou verificação manual) que um escore baixo (~8) classifica "Baixo" e
   não "Elevado" depois da correção.

**Status**: aguardando sua confirmação pra executar.

---

### 2. Bug: fuso horário do Django está em UTC, não em Brasília

**Pedido original**: "a hora está errada, o fuso horário do django provavelmente está errado,
veja o porque está errado e coloque o correto fuso horario de brasilia."

**Diagnóstico já feito** (2026-08-06, mesma conversa): confirmado. `crarp/settings.py:150` tem
`TIME_ZONE = 'UTC'` (com `USE_TZ = True` em `settings.py:154`, o que está correto — o banco deve
continuar guardando tudo em UTC internamente). O problema é só o fuso de **exibição**: qualquer
timestamp mostrado em tela ou no PDF (`gerado_em`, `assinado_em`, `criado_em` de qualquer model,
data de emissão na capa do relatório) sai convertido pra UTC em vez de horário de Brasília
(UTC-3), então aparece sempre 3h (ou 2h, no horário de verão, que o Brasil não usa mais desde
2019) adiantada.

**Relação com o que já existe**: mudança de configuração isolada, não tem relação/conflito com
nenhuma outra decisão registrada no CLAUDE.md ou neste arquivo. `USE_TZ = True` não muda — é
justamente o que garante que trocar só o `TIME_ZONE` já resolve a exibição em todo o sistema
(Admin, painel, PDF) sem precisar tocar em `timezone.now()` nenhum, porque esses timestamps já
são gravados como "aware" (com fuso) e o Django converte pra exibição automaticamente a partir do
`TIME_ZONE` configurado.

**Especificação de execução**:
1. Em `crarp/settings.py:150`, trocar `TIME_ZONE = 'UTC'` por `TIME_ZONE = 'America/Sao_Paulo'`.
2. Verificar que nenhum lugar do código usa `datetime.utcnow()`/`datetime.now()` "nu" (sem
   timezone) esperando UTC explicitamente — `grep` rápido por `utcnow` e `datetime.now(` fora de
   `django.utils.timezone` antes de considerar concluído, já que `timezone.now()` (usado em
   `relatorios/services/pdf.py:432` e `:503`) não precisa de nenhuma mudança, ele já retorna
   UTC "aware" e é convertido na exibição.
3. Reiniciar o container/processo do Django após o deploy (mudança de `settings.py` só é lida no
   boot).
4. Verificar manualmente: gerar uma ação que grava timestamp agora (ex.: criar uma Aplicacao) e
   conferir que a hora exibida bate com o horário local de Brasília.

**Status**: aguardando sua confirmação pra executar.

---

### 3. PDF: justificar todo o texto do relatório

**Pedido original**: "o texto do relatório, deixar todo texto justificado"

**Diagnóstico já feito** (2026-08-06, mesma conversa): hoje `relatorios/templates/relatorios/inventario.html`
não define nenhum `text-align: justify` — o corpo do texto (regra `body` em torno da linha 64,
`line-height: 1.55`) usa o alinhamento padrão do navegador (esquerda). Alguns elementos pontuais
já têm `text-align` próprio (`.capa .meta-item` e `.escala-x span` = center, `.label-dominio` =
right, `.assinatura` = left) — esses são intencionais (Seção 6.22/6.25 do CLAUDE.md) e não devem
virar "justify" junto com o corpo, senão a assinatura e os rótulos de tabela ficam esquisitos.

**Relação com o que já existe**: puramente visual, não conflita com nenhuma decisão de conteúdo
já registrada. Só um cuidado: `text-align: justify` em parágrafos curtos (1–2 linhas, como os que
aparecem nos cards do Panorama e nos textos de "achados" da Seção 4) pode criar espaçamento
irregular entre palavras de forma mais visível que em parágrafos longos — vale conferir no PDF
real depois de aplicado, não só confirmar que o CSS foi escrito.

**Especificação de execução**:
1. Adicionar `text-align: justify;` na regra `body` do `<style>` de
   `relatorios/templates/relatorios/inventario.html` (ou, se preferir escopo mais seguro, aplicar
   em `p` genérico em vez de `body`, pra não herdar em blocos que já têm alinhamento próprio
   definido — os `text-align` mais específicos citados acima continuam válidos por especificidade
   de CSS de qualquer forma, então aplicar em `body` é seguro, só reforça a intenção).
2. Adicionar `text-align-last: left;` (evita que a última linha de cada parágrafo justificado
   fique esticada/com espaçamento estranho — comportamento padrão indesejado de `justify`).
3. Regenerar um PDF real e conferir visualmente parágrafos curtos e longos (Panorama, achados da
   Seção 4, Metodologia) antes de considerar concluído.

**Status**: aguardando sua confirmação pra executar.

---

### 4. PDF: ocultar Seções 07/08 "Triangulação" quando não houver dado pra mostrar

**Pedido original**: "no relatorio, a parte '07 · TRIANGULAÇÃO' onde diz 'O que outras fontes
confirmam.' e 'A leitura de quem está no campo.' só deve ser plotada se for preenchido e tiver
oque mostrar, se não tiver nada pra dizer, apenas oculte na hora de plotar o pdf"

**Diagnóstico já feito** (2026-08-06, mesma conversa): são duas seções distintas, ambas com
`eyebrow` "Triangulação":
- **Seção 07** (`inventario.html:808-832`) — "O que outras fontes confirmam.", evidências
  complementares (`IndicadorIndireto`, Seção 4.2 do CLAUDE.md).
- **Seção 08** (`inventario.html:834-858`) — "A leitura de quem está no campo.", checklist de
  entrevista/observação (`RespostaChecklistTriangulacao`, Seção 6.11/6.12 do CLAUDE.md).

Hoje as duas sempre renderizam (título + um bloco por GHE), e cada GHE sem dado mostra a frase
"Nenhuma evidência complementar registrada para este GHE." / "Nenhum item do checklist de
entrevista/observação avaliado para este GHE." — é exatamente esse texto de "nada aqui" que você
quer que suma, ocultando a seção inteira (título incluso) quando NENHUM GHE do relatório tiver
dado nessa categoria.

**Relação com o que já existe** — ponto de atenção real, não é só filtro de exibição: o eyebrow de
cada seção do PDF é um número literal fixo no template ("07 ·", "08 ·", "09 ·" no Plano de Ação,
"09/10 ·" no Encerramento, calculado condicionalmente pelo tipo de relatório — Seção 6.18/6.19 do
CLAUDE.md). Se a Seção 07 for ocultada num relatório que não tem evidência complementar mas TEM
checklist de entrevista, a Seção 08 continuaria rotulada "08" mesmo sendo a 7ª seção realmente
impressa — um "buraco" na numeração. Duas formas de resolver, preciso que você escolha antes de eu
implementar:
  - (a) aceitar o buraco na numeração (mais simples, a rastreabilidade de conteúdo não é afetada,
    só o número da fita de eyebrow não bate mais com a ordem física impressa em relatórios onde
    uma das duas seções some);
  - (b) calcular o número do eyebrow dinamicamente a partir de quais seções realmente entram
    naquele relatório específico (mais correto visualmente, mas exige tocar na lógica de
    numeração de todas as seções do documento — hoje espalhada como texto fixo em cada
    `<div class="eyebrow">`, teria que virar uma sequência calculada no contexto do relatório em
    `relatorios/services/pdf.py`, similar ao que já é feito pra decidir se a Seção 9 do Plano de
    Ação existe).

**Especificação de execução** (parte comum às duas opções):
1. Em `relatorios/services/pdf.py::_contexto_relatorio`, calcular duas flags booleanas:
   `tem_evidencias_complementares` (True se algum `item.indicadores` da lista `ghes` for
   não-vazio) e `tem_checklist_triangulacao` (True se algum `item.checklist_triangulacao` for
   não-vazio).
2. Em `inventario.html`, envolver o bloco inteiro da Seção 07 (`<div class="secao">` de
   `evidências complementares`, linhas 808-832) num `{% if tem_evidencias_complementares %}...{% endif %}`,
   e o bloco inteiro da Seção 08 (linhas 834-858) num
   `{% if tem_checklist_triangulacao %}...{% endif %}` — removendo, dentro de cada bloco, o
   `{% else %}Nenhuma... registrada{% endif %}` por GHE (não faz mais sentido per-GHE se a seção
   só aparece quando existe pelo menos um GHE com dado — mas um GHE individual sem dado dentro de
   uma seção que aparece por causa de outro GHE ainda deve mostrar algo curto, tipo "Sem
   evidências complementares registradas para este GHE", só não a seção inteira).
3. Decidir com você a questão do número da fita (opção a ou b acima) antes de mexer no template.

**Status**: aguardando sua confirmação pra executar — **e sua decisão sobre a numeração da fita
(opção a ou b) antes de eu implementar o item 4.**

---

### 5. Privacidade: alias sequencial + timestamps exatos permitem reidentificar respondente

**Pedido original**: "percebi um erro que pode identificar quem responde, você a forma de ler
'respondente 1, respondente 2' ainda é possível saber quem respondeu por ordem de quem termina,
precisa ser ainda mais sigiloso a apresentação de quem responde em 'Respondentes (11)' em
`/painel/aplicacoes/3/` e em `/painel/aplicacoes/3/pontuacao-anonima/`."

**Diagnóstico já feito** (2026-08-06, mesma conversa) — **achei o vazamento que você descreveu, e
mais dois adicionais, mais graves, na mesma investigação**:

1. **A causa raiz do que você notou**: `avaliacoes/views.py:159-162`
   (`responder_consentimento`) gera o alias como `f"Respondente {numero}"` onde
   `numero = aplicacao.respondentes.count() + 1` — ou seja, o número do alias é literalmente a
   ordem de quem **começou** a responder primeiro (não de quem termina, mas o efeito prático que
   você descreveu é o mesmo: um número sequencial correlacionado com tempo real é uma pista de
   reidentificação pra quem tem contexto de campo, tipo "eu vi fulano pegando o celular assim que
   mandei o link").
2. **Achado adicional #1 (mais grave)**: a tabela "Respondentes (N)" em
   `/painel/aplicacoes/<pk>/` (`avaliacoes/templates/painel/aplicacao_detail.html:149-158`) mostra
   duas colunas com **timestamp exato** — "Consentiu" e "Concluiu" — ao lado de "Tempo na
   organização" e "Modalidade". Isso é uma reidentificação muito mais direta que a ordem do
   alias: quem sabe que um trabalhador específico respondeu às 14h32 no intervalo consegue casar
   a linha certa na tabela e ler o resto (incluindo, indiretamente, o alias que aparece nas outras
   telas).
3. **Achado adicional #2 (o mais grave dos três)**: a tela `/painel/aplicacoes/<pk>/pontuacao-anonima/`
   (`avaliacoes/templates/painel/pontuacao_anonima.html:32`) mostra a data de cadastro
   (`respondente.criado_em`, sem hora, mas ainda assim uma data específica) **na mesma linha do
   mapa de calor com o escore individual de cada domínio daquela pessoa** — ou seja, esse dado
   não está só ao lado do alias, está ao lado das respostas individuais de fato. Além disso, a
   view (`avaliacoes/painel_views.py:431`, `pontuacao_anonima`) ordena essa tabela por
   `order_by("criado_em")` — literalmente por ordem cronológica de início, reforçando de novo o
   mesmo problema que você apontou, agora bem ao lado dos escores em vez de só do alias.

**Relação com o que já existe**: dado de resposta individual já é tratado como dado sensível no
CLAUDE.md (Seção 9 — LGPD art. 5º II, "nunca expor em relatório agregado quando N < mínimo"), e a
Seção 3 (princípios 3 e 4) exige confidencialidade por padrão — os três pontos acima são falhas
reais desse princípio já declarado, não uma mudança de política nova.

**Especificação de execução**:
1. **Alias deixa de ser sequencial/correlacionado com hora de início.** Em
   `avaliacoes/views.py::responder_consentimento`, trocar `numero = aplicacao.respondentes.count() + 1`
   por um número aleatório único dentro da Aplicacao (ex.: sortear um inteiro entre 1000–9999,
   checar colisão contra `aplicacao.respondentes.values_list("alias_anonimo", flat=True)`, repetir
   se colidir) — o alias vira algo como "Respondente 4821", sem nenhuma relação com ordem de
   chegada.
2. **`pontuacao_anonima` (`avaliacoes/painel_views.py:431`) para de ordenar por `criado_em`** —
   trocar pra `order_by("alias_anonimo")` (já seguro depois do item 1, porque o alias deixa de
   correlacionar com tempo).
3. **Remover a coluna de data em `pontuacao_anonima.html:32`** (`respondente.criado_em`) — não
   generalizar pra "mês/ano", remover de vez, já que fica ao lado do escore individual.
4. **Em `aplicacao_detail.html:149-158`, trocar as colunas "Consentiu"/"Concluiu" (timestamp
   exato) por um indicador sem hora** — ex.: só "Status" com "Respondeu"/"Pendente" (booleano, sem
   nenhum timestamp) — preserva a utilidade operacional (saber quem falta responder) sem expor o
   momento exato. Ajustar a query em `avaliacoes/painel_views.py` (por volta da linha 391,
   `n_concluidos = sum(...)`) se necessário pra continuar contando concluídos sem depender do
   template mostrar a data.
5. Conferir se `_recalcular_indice_geral`/outras telas não dependem de ordenação por `criado_em`
   pra nenhum outro fim que não seja exibição (a ordenação interna de cálculo pode continuar
   usando `criado_em`/pk sem problema — o risco é só na exibição pro usuário do painel).
6. Teste de regressão: confirmar que o alias gerado é único dentro da Aplicacao mesmo com
   respondentes concorrentes (retry em caso de colisão).

**Status**: aguardando sua confirmação pra executar. Os itens 2 e 3 do diagnóstico (timestamps
exatos e ordenação por `criado_em`) são achados meus, além do que você descreveu — avise se quer
tratar os três juntos ou só confirmar a causa raiz (item 1) primeiro.

---

### 6. PDF: remover todas as siglas de domínio, sempre usar o nome completo

**Pedido original**: "no relatorio se usa muito siglas dos dominios, mas se a intenção é dar o
relatorio ao gestor pouco importa, retire todas as siglas do dominio, sempre chame ele pelo nome
completo."

**Diagnóstico já feito** (2026-08-06, mesma conversa): mapeei todos os pontos de
`relatorios/templates/relatorios/inventario.html` que imprimem a sigla (`.codigo`/`dominio_codigo`)
do domínio junto ou no lugar do nome:
- Linha 527/539 — listas "protegendo"/"pede ação" do Panorama: `{{ p.dominio_nome }} ({{ p.dominio_codigo }})`.
- Linha 606 — tabela de Metodologia (N respondentes por domínio): `{{ ...codigo }} — {{ ...nome }}`.
- Linha 673/742 — nota de domínios com evento grave confirmado: `{{ dc.dominio_codigo }} ({{ dc.dominio_nome }})`.
- Linha 703 — Seção 5 (linha de leitura por domínio, redesenhada na Seção 6.25 do CLAUDE.md):
  `{{ ...codigo }} — {{ ...nome }}`.
- Linha 761 — rótulo de cada barra do gráfico semáforo (`.label-dominio`): `{{ dominio_codigo }} - {{ dominio_nome }}`.
- Linha 795 — "maior proporção em vermelho" no resumo do semáforo: `{{ ...maior_risco.dominio_codigo }}`.
- Linha 822 — tabela de evidências complementares: coluna "Domínio relacionado" mostra `ind.dominio_relacionado.codigo`.
- Linha 883/913 — fichas e tabela do Plano de Ação: `{{ entrada.dominio_codigo }}`.

**Não confundir com**: `plano.codigo` (linhas 883/912) é o código do **próprio Plano de Ação**
(ex. "A01", Seção 6.9 Prompt 08 do CLAUDE.md) — isso não é sigla de domínio, é o identificador de
rastreio da ação e deve continuar aparecendo.

**Relação com o que já existe**: a Seção 6.16 do CLAUDE.md já tinha removido sigla "sozinha" (sem
nome) em duas tabelas do Parecer técnico, exatamente pelo mesmo motivo de credibilidade/leitura
pro cliente final — este pedido estende esse mesmo princípio pro resto do documento, de forma
completa. Único ponto de atenção técnico: o rótulo do gráfico semáforo (linha 761,
`.label-dominio { width: 212px; }`) foi dimensionado pensando em siglas curtas — no COPSOQ
Oficial existem nomes de domínio longos (ex. "Possibilidades de desenvolvimento",
"Comprometimento com o local de trabalho"); pode ser necessário aumentar a largura da coluna de
rótulo ou reduzir a fonte pra caber sem quebrar o layout do gráfico de barras.

**Especificação de execução**:
1. Em cada um dos 8 pontos listados acima, remover o `{{ ...codigo }}` (e o traço/parênteses que
   o cercam) e deixar só `{{ ...nome }}`.
2. Ajustar `.label-dominio` (CSS) se necessário pra acomodar nomes completos sem quebrar a barra
   do gráfico semáforo — testar especificamente com os nomes mais longos do COPSOQ Oficial.
3. Regenerar um PDF real (COPSOQ Oficial, pelo menos 1 domínio com evento grave e 1 no Panorama)
   e conferir visualmente que nenhuma sigla isolada restou.

**Status**: aguardando sua confirmação pra executar.

---

### 7. Remover coluna de comparação com média nacional (Portugal) — painel e relatório

**Pedido original**: "notei que não é prudente comparar a média nacional de portugal com a
realidade brasileira, retire toda coluna que compara a media nacional tanto em
`/painel/aplicacoes/3/` em 'domínio' quando no relatório gerado."

**Diagnóstico já feito** (2026-08-06, mesma conversa): **no PDF já não existe mais essa coluna** —
foi removida na rodada de redesenho da Seção 5 (CLAUDE.md Seção 6.25, "a coluna 'Média nacional'
foi descartada dessa visão... dado comparativo secundário, não exigido pela NR-01"), e conferido
agora que `inventario.html` não tem mais nenhuma referência a `media_nacional`. Falta só o lado do
**painel**: a tela `/painel/aplicacoes/<pk>/` (`avaliacoes/templates/painel/aplicacao_detail.html:186-207`)
ainda mostra a coluna "Média nacional*" na tabela "Resultados por domínio", com nota de rodapé
citando o manual COPSOQ Portugal 2013 — exatamente a comparação que você quer retirar, e o motivo
que você deu (Portugal ≠ Brasil) é válido e consistente com o princípio de não comparar
populações não equivalentes sem ressalva.

**Relação com o que já existe**: a função `media_nacional_comparavel()`
(`avaliacoes/services/calculo_risco.py:49`) e os dados `Dominio.referencia_media_nacional`/`referencia_desvio_padrao`
importados do manual (usados só por essa função) não precisam ser apagados — ficam como
infraestrutura não usada, sem custo, caso um dia essa comparação volte a fazer sentido com dado
nacional brasileiro real. Só a **exibição** sai, nos dois lugares.

**Especificação de execução**:
1. Em `avaliacoes/templates/painel/aplicacao_detail.html:186`, remover a coluna `<th>Média
   nacional*</th>` do cabeçalho e `<td>{{ escore.media_nacional|default:"—" }}</td>` do corpo da
   tabela (linha ~195), e remover o parágrafo de nota de rodapé sobre a fonte da média nacional
   (linhas ~204-207+).
2. Em `avaliacoes/painel_views.py` (view `aplicacao_detail`, por volta da linha 391-394), remover
   o loop `for escore in escores_lista: escore.media_nacional = media_nacional_comparavel(escore.dominio)`
   e o import de `media_nacional_comparavel` no topo do arquivo, já que deixa de ser usado ali.
3. **Não tocar** em `relatorios/services/pdf.py:386` (`"media_nacional": media_nacional_comparavel(...)`
   no contexto do PDF) nem nos 4 testes dedicados de `media_nacional_comparavel` em
   `avaliacoes/test_copsoq_oficial.py` — o valor no contexto do PDF já está sem uso no template
   (dado morto inofensivo) e os testes validam a função em si, que continua existindo.

**Status**: aguardando sua confirmação pra executar.

---

### 8. Atualização em tempo real de "Respondentes" e "Resultados por domínio" na tela da Aplicação

**Pedido original**: "quando iniciar uma nova aplicação de um questionário, quero que a aba em
`/painel/aplicacoes/3/` em 'Respondentes' e 'Resultados por domínio' atualize em tempo real para
mostrar quem responde e a evolução da resposta em Resultados por domínio."

**Diagnóstico já feito** (2026-08-06, mesma conversa): hoje a tela `/painel/aplicacoes/<pk>/`
(`avaliacoes/painel_views.py::aplicacao_detail`, `avaliacoes/templates/painel/aplicacao_detail.html`)
é 100% renderizada no servidor — só atualiza se o gestor der F5 manualmente. O projeto não tem
nenhuma infraestrutura de tempo real hoje (sem Django Channels/WebSocket, sem Celery/Redis rodando
em produção — `entrypoint.sh` sobe só `gunicorn crarp.wsgi:application`, WSGI síncrono). Adicionar
WebSocket exigiria trocar o servidor de aplicação inteiro (WSGI → ASGI, novo processo Daphne/
Uvicorn, Redis como channel layer) — desproporcional pro que foi pedido. A abordagem que resolve
sem mudar a arquitetura de deploy é **polling via JavaScript puro** (mesmo padrão "sem framework"
já usado em todo o painel, ex. Seção 6.17 do CLAUDE.md): a página busca periodicamente um
fragmento HTML atualizado dos dois cards e substitui o conteúdo, sem recarregar a página inteira.

**Relação com o que já existe**: não conflita com nada registrado — é aditivo. Tem uma
dependência direta com o **item 5** (privacidade dos respondentes) desta mesma fila: os dois cards
que vão virar "ao vivo" são exatamente os que o item 5 está corrigindo (timestamps exatos,
alias sequencial). **Recomendo implementar o item 5 antes deste**, pra não construir o polling em
cima da versão com vazamento e ter que mexer duas vezes no mesmo template.

**Especificação de execução**:
1. Extrair os dois blocos hoje inline em `aplicacao_detail.html` — a tabela "Respondentes" e a
   tabela "Resultados por domínio" (com os banners que dependem dela: supressão por
   confidencialidade, alertas D9) — pra dois templates parciais reutilizáveis, ex.
   `avaliacoes/templates/painel/_partials/respondentes_card.html` e
   `_partials/resultados_dominio_card.html`, cada um envolto num `<div id="card-respondentes">`/
   `<div id="card-resultados-dominio">` fixo (o `id` é o alvo do JS).
2. Fatorar a lógica que monta o contexto desses dois cards (`respondentes`, `n_concluidos`,
   `escores_lista`, `todos_suprimidos`, `dominios_em_risco`, `alertas_d9`) numa função auxiliar
   em `avaliacoes/painel_views.py`, reaproveitada tanto pela view `aplicacao_detail` (render
   completo) quanto pela nova view abaixo.
3. Nova view `aplicacao_live` (`avaliacoes/painel_views.py`, `@gestor_required`, mesma proteção de
   tenancy via `_aplicacao_ou_404` que todas as outras views desta Aplicacao), rota
   `painel_avaliacoes:aplicacao_live` em `/painel/aplicacoes/<pk>/live/` (GET só) — renderiza os
   dois parciais com `render_to_string` e devolve `JsonResponse({"respondentes_html": ..., "resultados_html": ...})`.
4. JS puro em `aplicacao_detail.html`: `setInterval` (10s) chamando `fetch()` na rota acima e
   substituindo `innerHTML` dos dois `<div id="...">` pelo HTML recebido — só ativa o polling se
   `aplicacao.status == "em_andamento"` (não tem por que continuar batendo no servidor quando a
   coleta já foi encerrada/cancelada ou ainda nem começou); pausar o polling quando
   `document.visibilityState !== "visible"` (aba em segundo plano) e retomar ao voltar o foco, pra
   não gastar requisição à toa.
5. Teste automatizado: `aplicacao_live` retorna 200 com o alias novo depois de um respondente
   responder um domínio (fluxo: criar respondente via `avaliacoes:responder_*`, chamar
   `aplicacao_live`, conferir que o alias aparece no HTML devolvido).

**Status**: aguardando sua confirmação pra executar — recomendo depois do item 5 (mesma tela).

---

### 9. `concluido_em` não deve exigir a etapa de perguntas abertas + excluir respostas parciais do cálculo

**Contexto/diagnóstico** (2026-08-06, mesma conversa, confirmado com dado real da Aplicacao #3
via `manage.py shell` na VPS — comandos e saída completa no histórico desta conversa): você
reportou "Respondentes (11)" mas só 9 marcados como concluídos, achando que era erro de contagem.
Não é bug de contagem — são duas definições diferentes de "terminou" coexistindo:
- **Respondente 9** (id 21): 34 de 76 itens respondidos — parou de verdade no meio, é o caso
  legítimo de resposta parcial.
- **Respondente 11** (id 23): **76 de 76** itens respondidos (todos os domínios completos), mas
  nunca visitou a telinha final de "Perguntas abertas" (2 perguntas opcionais de texto livre) —
  por isso `concluido_em` nunca foi gravado, mesmo tendo terminado tudo que importa pro cálculo.

Confirmado também, na mesma investigação, que **não houve nenhuma duplicata/respondente órfão**
causada pelo erro que você viu em campo — o mecanismo de retomada por cookie funcionou
corretamente pras 11 pessoas (a suspeita inicial de "duplicata por erro 505" foi descartada com
dado real).

**Pedido**: você escolheu a opção 1 (marcar `concluido_em` assim que todos os domínios forem
respondidos, sem depender de visitar a etapa de perguntas abertas) e pediu um mecanismo adicional:
quem parar no meio (resposta parcial, tipo Respondente 9) **não deve contar no cálculo/relatório
final** — nada de "meia resposta" contaminando escore, N ou prevalência de nenhum domínio.

**Relação com o que já existe** — dois pontos de atenção reais, não só "implementar":
1. **Item 8 desta fila** (atualização em tempo real dos cards de Respondentes/Resultados por
   domínio): com essa mudança, um domínio só passa a ter dado calculado depois que **pelo menos
   uma pessoa terminar o questionário inteiro** (não só aquele domínio) — durante a coleta, antes
   da primeira conclusão total, "Resultados por domínio" ficará vazio mesmo que várias pessoas já
   tenham respondido esse domínio especificamente. Isso é o comportamento correto de acordo com o
   que você pediu, mas o card "ao vivo" do item 8 precisa saber mostrar esse estado ("aguardando o
   primeiro respondente completar o questionário") em vez de parecer quebrado.
2. **Dado histórico já persistido**: a Aplicacao #3 real já tem `EscoreDominio`/`EscoreRespondente`
   calculados incluindo a contribuição parcial do Respondente 9 nos domínios que ele alcançou —
   esses valores ficam desatualizados (e continuariam errados pelo novo critério) até alguma coisa
   disparar um recálculo. A especificação abaixo cobre isso.

**Especificação de execução**:

1. **`avaliacoes/views.py::_proximo_passo`** — remover o atalho antigo do topo da função
   (`if respondente.concluido_em: return redirect responder_concluido`, hoje nas primeiras linhas)
   e mover a gravação de `concluido_em` pra acontecer assim que `proximo_item_pendente(respondente)`
   voltar `None` (ou seja, todos os itens de todos os domínios respondidos) — **antes** de checar
   `perguntas_abertas_respondidas_em`, não depois. A função passa a reconstruir o destino certo a
   cada chamada (idempotente, sem atalho no topo): perfil pendente → domínio pendente → grava
   `concluido_em` (se ainda não gravado) → perguntas abertas pendente → tela de agradecimento.
   Assim quem termina os domínios já conta como concluído mesmo que abandone antes da tela de
   perguntas abertas, mas ainda é convidado a respondê-la se voltar ao link depois.
2. **`avaliacoes/services/calculo_risco.py::calcular_dominio`** — adicionar
   `.filter(respondente__concluido_em__isnull=False)` na query-base `respostas_qs` (linha ~163).
   Isso propaga automaticamente pra tudo que deriva dela na mesma função: `respostas`,
   `n_respondentes`, o loop de `EscoreRespondente`/`_recalcular_indice_geral`, e a prevalência —
   uma resposta de alguém que não terminou o questionário inteiro deixa de entrar em qualquer
   cálculo (escore de domínio, N, prevalência, plano de ação).
3. **Fechar a lacuna do próprio momento da conclusão**: quando `_proximo_passo` grava
   `concluido_em` pela primeira vez (item 1 acima), disparar `calcular_dominio(aplicacao, dominio)`
   de novo pra **cada** domínio que esse respondente respondeu (`Dominio.objects.filter(itens__respostas__respondente=respondente).distinct()`)
   — sem isso, a última pessoa a terminar ficaria de fora do cálculo do último domínio que
   respondeu, porque `calcular_dominio` daquele domínio já tinha rodado (chamado de
   `responder_pergunta`) um instante antes de `concluido_em` existir.
4. **Fechar a lacuna do dado já coletado antes desta mudança**: em
   `avaliacoes/services/aplicacao_status.py::encerrar_coleta`, depois de marcar
   `status = CONCLUIDA`, disparar um recálculo completo — `calcular_dominio(aplicacao, dominio)`
   pra cada domínio de `dominios_da_aplicacao(aplicacao)` que tenha pelo menos uma `Resposta` —
   garantindo que os números usados no relatório final estejam sempre 100% recalculados só com
   respondentes completos no momento em que a coleta é oficialmente fechada, independente de
   qualquer sequência de eventos anterior.
5. **`pontuacao_anonima`** (mapa de calor por respondente, `avaliacoes/painel_views.py`/
   `pontuacao_anonima.html`): depois do item 2 acima, um `EscoreRespondente` de alguém incompleto
   (como o Respondente 9 hoje) fica **desatualizado, não removido** — ele só é sobrescrito na
   próxima vez que `calcular_dominio` rodar pra aquele domínio específico. Adicionar
   `respondentes = respondentes.filter(concluido_em__isnull=False)` (ou equivalente) na query da
   view `pontuacao_anonima`, pra essa tela nunca mostrar linha de gente que não terminou, mesmo
   antes do recálculo do passo 4 acontecer.
6. **Dado já existente na Aplicacao #3 real**: depois do deploy, rodar `encerrar_coleta`/o
   recálculo do item 4 manualmente pra essa Aplicacao específica (se ela já estiver com coleta
   encerrada, ou vai ficar quando você encerrar) — só recarregar a tela não corrige os `EscoreDominio`
   já persistidos, é preciso o recálculo passar por eles pelo menos uma vez.
7. Testes: cobrir (a) resposta parcial não aparece em `EscoreDominio.n_respondentes`/escore; (b) o
   último domínio do último respondente a terminar entra no cálculo mesmo tendo sido respondido
   um instante antes de `concluido_em` existir; (c) `encerrar_coleta` recalcula e corrige um
   domínio que só tinha contribuição de um respondente incompleto.

**Status**: aguardando sua confirmação pra executar.

---

### 10. Bug: coluna "% elevados" do Diagnóstico GHE sempre mostra 0% ou 1%

**Pedido original**: você notou em `/painel/aplicacoes/3/diagnostico-ghe/` que a coluna "%
elevados" só mostra 0% ou 1%, nunca um percentual real (ex.: escore 59,1 com "1%"). Pediu pra
investigar a causa, ver se afeta o relatório, e registrar se for erro.

**Diagnóstico já feito** (2026-08-06, mesma conversa): confirmado bug real, isolado numa única
linha. `percentual_elevados` é sempre armazenado como fração 0–1 (ex.: 1 de 11 respondentes
elevados = `0.0909`) — é assim em todo o sistema (`risk_engine.py::calcular_prevalencia`,
`EscoreDominio.percentual_elevados`). Em
`avaliacoes/templates/painel/diagnostico_ghe.html:58`, o template faz
`{{ linha.percentual_elevados|floatformat:0 }}%` — aplica o arredondamento pra inteiro **direto
na fração**, sem multiplicar por 100 antes. `0.0909` arredondado pra 0 casas dá `"0"` → mostra
"0%"; qualquer fração ≥ 0,5 arredonda pra `"1"` → mostra "1%". Nunca aparece nada entre isso.

**Impacto no relatório (PDF)**: **nenhum.** Conferi todos os pontos de
`relatorios/templates/relatorios/inventario.html` que mostram esse mesmo percentual (Seção 5 —
linha 714 — e Seção 6/gráfico semáforo — linhas 769-797) e todos usam
`{% widthratio valor 1 100 %}%`, que já faz a conversão corretamente — é inclusive o padrão certo
que devia ter sido usado também no painel.

**Relação com o que já existe**: acoplado ao item 9 desta fila — depois daquela mudança
(`percentual_elevados` só considera respondentes completos), o valor que essa coluna vai exibir
muda de qualquer forma; faz sentido corrigir a exibição depois de garantir que o dado por trás
também está certo, senão fica difícil validar visualmente se a correção do item 9 funcionou.

**Especificação de execução**:
1. Em `avaliacoes/templates/painel/diagnostico_ghe.html:58`, trocar
   `{{ linha.percentual_elevados|floatformat:0 }}%` por
   `{% widthratio linha.percentual_elevados 1 100 %}%` (mesmo padrão já usado no PDF) — mantendo o
   `{% if linha.percentual_elevados is not None %}...{% else %}—{% endif %}` em volta.
2. Regenerar/recarregar a tela com dados reais (ex.: Aplicacao #3) e conferir visualmente que os
   percentuais batem com `escore.percentual_elevados` visto no shell (ex.: IT deveria mostrar algo
   condizente com o escore 59,1, não "1%").

**Status**: aguardando sua confirmação pra executar — recomendo implementar junto/depois do item 9.

---

### 11. Mover a escolha "Diagnóstico" vs. "Diagnóstico + Plano de Ação" da criação pra tela do Relatório

**Pedido original**: "quando encerro o questionario, e tenho a opção de fazer o relatorio, o
sistema me pergunta uma unica vez se quero um relatório com plano de ação ou sem, mas isso não
devia ser perguntado agora, era pra aparecer essa opção em `/painel/relatorios/2/` onde eu
consigo gerar o relatorio com plano de ação, e só o diagnostico, veja tudo que precisa mudar com
isso."

**Diagnóstico já feito** (2026-08-06, mesma conversa) — mapeei o fluxo atual completo:

- `Relatorio.tipo` (`relatorios/models.py:92-100`) é um campo fixado **na criação**, com
  `help_text` dizendo literalmente "Escolhido na criação e não muda depois". Essa é uma decisão
  documentada explicitamente no CLAUDE.md (Seção 6.18, 2026-08-05): "**não é editável depois** (não
  há tela de 'mudar o tipo' — se o gestor quiser o outro tipo, cria um novo Relatorio)." **Este
  pedido reverte essa decisão** — vale registrar que está sendo revertida por uso real (você, o
  usuário, testando o próprio fluxo), não uma mudança de ideia arbitrária.
- `RelatorioForm` (`relatorios/forms.py:33`) inclui `tipo` no `fields` — é o campo que pergunta na
  hora de criar.
- `relatorio_detail.html` tem uma seção "Planos de ação" que **só aparece** (com o botão "Refinar
  planos de ação com IA") quando `exige_planos_refinados` é `True` — e isso vem direto de
  `relatorio.tipo == DIAGNOSTICO_PLANO_ACAO` (`relatorios/painel_views.py:148`). Se o tipo for
  "Diagnóstico", a seção mostra só um aviso dizendo pra criar outro relatório.
- O botão "Gerar PDF" é **um único botão** (`relatorio_detail.html:264-269`), bloqueado
  (`pode_gerar_pdf`) até `etapa_parecer` estar pronta e, se o tipo exigir, até
  `etapa_planos_refinados` também.
- `avaliacoes/services/... ` **não precisa mudar** — o motor que decide se um `PlanoDeAcao` nasce
  automaticamente por domínio (`_gerar_plano_de_acao_se_necessario`) é independente do
  `Relatorio.tipo`; ele sempre gera o plano, seja qual for o tipo do relatório que depois vai
  incluir ou não essa seção no PDF. Isso facilita a mudança: os dados do plano de ação **já
  existem** pra qualquer Relatorio, o `tipo` só decide se o PDF os imprime.
- `relatorios/services/pdf.py::validar_pre_requisitos_pdf` (linha 440) já checa
  `relatorio.tipo == DIAGNOSTICO_PLANO_ACAO` pra exigir `planos_refinados_em` — essa função **não
  precisa mudar**, ela já está certa pra qualquer valor de `tipo` no momento em que é chamada.
- `gerar_pdf_relatorio`/`assinar_relatorio` (`pdf.py:460-506`) sempre releem `relatorio.tipo` do
  banco na hora de gerar — também **não precisam mudar**.

**A ideia central da mudança**: `Relatorio.tipo` deixa de ser "a promessa fixa deste relatório,
escolhida uma vez" e passa a ser "qual foi o último formato de PDF gerado" — atualizado a cada
clique em "Gerar PDF", não mais na criação. Isso é consistente com o que você quer: o mesmo
Relatorio pode virar um PDF só de diagnóstico hoje, e amanhã (sem criar outro registro) virar um
PDF com plano de ação, sem perder nada — os dois PDFs simplesmente se sobrescrevem no mesmo
`Relatorio.pdf_path` (já é assim hoje pra minuta/final, Seção 8.4 do CLAUDE.md).

**Relação com o que já existe**: além de reverter a Seção 6.18 (documentado acima), interage com:
- O botão "Assinar" (`relatorio_assinar`) finaliza **o que estiver em `relatorio.pdf_path` no
  momento** — ou seja, assina o último tipo gerado. Preciso deixar isso visível na tela (ex.:
  "Assinar vai finalizar a versão atual: Diagnóstico + Plano de Ação"), pra você não assinar sem
  perceber qual formato está indo pro documento final.
- O stepper visual (Seção 6.19 do CLAUDE.md) tinha uma etapa "Refinar planos de ação" que só
  aparecia se o tipo exigisse — ela vira sempre visível/opcional (você pode refinar os planos a
  qualquer momento, é só recomendado antes de gerar a variante "+ Plano de Ação").

**Especificação de execução**:
1. **`relatorios/forms.py::RelatorioForm`** — remover `"tipo"` da lista `fields` (linha 33). A
   criação do Relatorio passa a pedir só critério, aplicações e período, como já era o resto.
2. **`relatorios/models.py::Relatorio.tipo`** — manter o campo (ainda é usado pra decidir o que o
   PDF inclui), só atualizar o `help_text` pra refletir a nova semântica: reflete o último formato
   de PDF gerado, pode ser regenerado no outro formato a qualquer momento a partir da tela do
   Relatório. Sem migration nova (o campo em si não muda de tipo/choices/default).
3. **`relatorios/templates/painel/relatorio_detail.html`**:
   - Seção "Tipo deste relatório" (`#secao-tipo`, linhas 35-47): reescrever pra explicar que os
     dois formatos estão disponíveis a partir desta tela, apontando pra seção PDF — remover o link
     "crie um novo relatório".
   - Seção "Planos de ação" (`#secao-planos`, linhas 194-238): remover o `{% if
     exige_planos_refinados %}...{% else %}...{% endif %}` — a seção (tabela + botão "Refinar
     planos de ação com IA") passa a aparecer sempre, já que os planos existem independente do
     tipo escolhido depois.
   - Seção PDF (`#secao-pdf`, linhas 240-269): trocar o botão único por **dois botões**, cada um
     com `<input type="hidden" name="tipo" value="...">` apontando pro
     `TipoRelatorio.DIAGNOSTICO`/`DIAGNOSTICO_PLANO_ACAO` correspondente:
     - "Gerar PDF — Diagnóstico" — habilitado assim que `etapa_parecer` estiver pronta.
     - "Gerar PDF — Diagnóstico + Plano de Ação" — habilitado só quando `etapa_parecer` **e**
       `etapa_planos_refinados` estiverem prontos; desabilitado com texto explicativo até lá (mesmo
       padrão visual já usado hoje pro botão único).
   - Perto do botão "Assinar", mostrar qual tipo será finalizado (`relatorio.get_tipo_display`,
     que a essa altura já reflete o último PDF gerado).
4. **`relatorios/painel_views.py::relatorio_detail`** — trocar a flag única `pode_gerar_pdf` por
   duas: `pode_gerar_pdf_diagnostico = etapa_parecer` e
   `pode_gerar_pdf_com_plano = etapa_parecer and etapa_planos_refinados`. Remover
   `exige_planos_refinados` como flag de bloqueio (a seção de planos deixa de ser condicional) —
   pode continuar existindo só como informação ("este relatório já tem plano de ação refinado?").
   Ajustar o stepper (`etapas`) pra sempre incluir "Refinar planos de ação" como etapa visível
   (concluída se `etapa_planos_refinados`, mas nunca bloqueando a etapa de PDF sozinha — só bloqueia
   o botão específico "+ Plano de Ação"). Ajustar também o banner "Próximo passo" (linhas 15-25 do
   template) pra não forçar "Refinar planos de ação" como obrigatório antes do PDF.
5. **`relatorios/painel_views.py::relatorio_gerar_pdf`** — ler `tipo = request.POST.get("tipo")`,
   validar que é um dos dois valores de `TipoRelatorio.values` (senão, mensagem de erro e redirect,
   sem chamar nada), gravar `relatorio.tipo = tipo; relatorio.save(update_fields=["tipo"])` **antes**
   de chamar `gerar_pdf_relatorio(pk)` — como essa função já releem o `Relatorio` fresco do banco,
   nenhuma mudança é necessária em `relatorios/services/pdf.py`.
6. Testes: cobrir (a) criar Relatorio sem escolher tipo; (b) gerar PDF "Diagnóstico" sem ter
   refinado planos — permitido; (c) gerar PDF "+ Plano de Ação" sem ter refinado planos — bloqueado
   com a mesma mensagem de erro já existente; (d) gerar os dois formatos em sequência no mesmo
   Relatorio e conferir que `relatorio.tipo` e o conteúdo do PDF (presença/ausência da Seção de
   Plano de Ação) refletem sempre o último clicado; (e) assinar finaliza o último tipo gerado.

**Status**: aguardando sua confirmação pra executar.

---

### 12. Django Admin: upload de imagem de assinatura (PNG) no usuário, aparece no PDF já no tamanho certo

**Pedido original**: "adicione no django admin de ir no usuario e adicionar foto da assinatura em
png pra quando assinar, a assinatura aparecer lá no relatorio já no tamanho correto."

**Diagnóstico já feito** (2026-08-06, mesma conversa): hoje o bloco de assinatura do PDF
(`relatorios/templates/relatorios/inventario.html:970-982`) é **só texto** — nome (`{{
relatorio.assinado_por.get_full_name }}`), título profissional, conselho/registro e data,
alimentados por `PerfilProfissional` (`relatorios/models.py:10-28`), que já é o model ligado
1-pra-1 ao `User` (decisão de 2026-07-17, Seção 8.4 item 1/2 do CLAUDE.md: "registro interno
simples... sem assinatura digital/criptográfica"). Adicionar uma imagem de assinatura manuscrita
é aditivo a essa decisão, não conflita — continua sendo um registro interno, só ganha um elemento
visual a mais.

**Ponto técnico que precisa de cuidado** (por isso "no tamanho correto" não é trivial): o PDF é
gerado pelo Chromium headless via `page.set_content(html, ...)`
(`relatorios/services/pdf.py:72`) — **sem URL base nenhuma**. Isso significa que um `<img
src="/media/assinaturas/xyz.png">" comum não teria como ser resolvido pelo navegador headless (não
existe uma página "de onde" ele possa completar esse caminho relativo, diferente de uma navegação
normal). Confirmei que o projeto já tem exatamente esse cuidado em outros lugares — todo elemento
visual do PDF hoje é CSS puro (a marca "IRP" da capa, os gráficos de barra do semáforo) e o
Paged.js é vendorizado em vez de buscado por URL, propositalmente pra nunca depender de rede/URL
na hora de renderizar. A forma correta de incluir uma imagem de verdade é embutir o PNG como
**data URI base64 direto no HTML** gerado (calculado em Python, em
`relatorios/services/pdf.py::_contexto_relatorio`, não no template) — mesmo arquivo, sem
depender do Django servir `/media/` pro próprio processo do Chromium.

**Especificação de execução**:
1. **`relatorios/models.py::PerfilProfissional`** — novo campo:
   ```python
   assinatura_imagem = models.ImageField(
       upload_to="assinaturas/",
       null=True,
       blank=True,
       validators=[FileExtensionValidator(["png"])],
       help_text="PNG da assinatura manuscrita (fundo transparente recomendado). "
       "Aparece no bloco de assinatura do PDF, redimensionada automaticamente — "
       "não precisa se preocupar com o tamanho do arquivo original.",
   )
   ```
   Gerar a migration correspondente.
2. **`relatorios/admin.py`** — dois pontos:
   - Adicionar `"assinatura_imagem"` aos campos de `PerfilProfissionalAdmin` (mantém o cadastro
     direto por `/admin/relatorios/perfilprofissional/` funcionando).
   - **Novo**: registrar um `PerfilProfissionalInline` (`admin.StackedInline`, `fk_name="user"`,
     `can_delete=False`) e reabrir o admin do `User` (`admin.site.unregister(User)` +
     `admin.site.register(User, CustomUserAdmin)` com `inlines=(PerfilProfissionalInline,)`) —
     é isso que faz "ir no usuário" no Admin (`/admin/auth/user/<id>/change/`) já mostrar o campo
     de upload da assinatura, sem precisar navegar até um cadastro separado.
3. **`relatorios/services/pdf.py::_contexto_relatorio`** — onde `perfil_assinante` já é resolvido
   (linha ~407-409), calcular também `assinatura_imagem_data_uri`: se
   `perfil_assinante.assinatura_imagem` existir, ler os bytes do arquivo e montar
   `f"data:image/png;base64,{base64.b64encode(dados).decode()}"`; senão, `None`. Adicionar ao
   dicionário de contexto retornado.
4. **`relatorios/templates/relatorios/inventario.html`** — dentro do bloco `.assinatura` (linha
   970-982), antes do nome, adicionar (só quando não for minuta e a imagem existir):
   ```html
   {% if assinatura_imagem_data_uri %}
   <img src="{{ assinatura_imagem_data_uri }}" alt="Assinatura" class="assinatura-imagem">
   {% endif %}
   ```
   CSS novo: `.assinatura-imagem { display: block; max-width: 220px; max-height: 70px;
   object-fit: contain; margin-bottom: 4px; }` — é isso que garante o "tamanho correto": a imagem
   sempre encaixa numa caixa fixa (220×70px), não importa a resolução/proporção do PNG original
   que o profissional subiu no Admin.
5. Teste: gerar um PDF final com um `PerfilProfissional` que tem `assinatura_imagem` preenchida e
   confirmar (a) o data URI aparece no HTML renderizado, (b) sem imagem cadastrada, o bloco
   continua funcionando só com texto (comportamento atual, sem regressão).

**Status**: aguardando sua confirmação pra executar.

---

### 13. Engenharia reversa completa da capa do PDF (identica à referência Solute RH)

**Pedido original**: "quero que você faça uma engenharia reversa e faça a capa do meu relatório
ter o exato template do relatorio referencia, no sentido de cores, fonte, tamanho da fonte,
cards, tudo, quero ter uma capa idêntica." (arquivo de referência:
`Diagnostico_Psicossocial_Modelo_Solute.pdf`, capa/página 1).

**Diagnóstico já feito** (2026-08-06, mesma conversa): extraído com `pdfplumber` (instalado
temporariamente no venv só pra essa análise, não é dependência do projeto) — cada caractere, cor,
fonte, tamanho e posição exatos da capa de referência, não estimados visualmente. Comparado com a
capa atual (`relatorios/templates/relatorios/inventario.html`, bloco `.capa`, Seções 6.20/6.24/6.25
do CLAUDE.md). **Achado central**: a estrutura é fundamentalmente diferente, não só um ajuste de
cor — a referência é **alinhada à esquerda o tempo todo** (masthead no topo, título, parágrafo,
metadados no rodapé, tudo `text-align: left`), enquanto a atual é **centralizada** (`.capa {
text-align: center }`, `.marca`/`.meta-linha` centralizados). Reproduzir "idêntica" exige trocar
o layout inteiro de centralizado pra alinhado à esquerda, não só cores/fontes.

**Dados extraídos (fonte de verdade, não estimativa)** — página 594.96×841.92pt (A4):

| Elemento | Posição (pt, do topo/esquerda) | Fonte | Tamanho | Cor |
|---|---|---|---|---|
| Barra lateral | x 0→51pt (full height) | — | **51pt = 1,8cm de largura** | `#F47B20` (igual ao nosso laranja atual) |
| Quadrado da marca | x 102→126, y 87.7→111.7 (24×24pt) | — | 24×24pt (~32px) | fundo `#F47B20` |
| Letra "S" na marca | x 109.4, y 93.2 | LiberationSans-Bold | 14pt (~18.7px) | branco |
| "SOLUTE RH" | x 134.3, y 88.1 | LiberationSans-Bold | 11pt (~14.7px) | `#1A1A1A` |
| "CONSULTORIA EM GESTÃO DE PESSOAS" | x 134.3, y 105.8 | LiberationSans regular | 7.5pt (~10px) | `#6B6B6B` |
| Eyebrow (2 linhas) | x 102, y 344.3/357.8 | LiberationSans-Bold | 8.5pt (~11.3px) | `#F47B20` |
| Linha divisória fina | x 102→459 (357pt ≈ 12,6cm), y 382.5 | — | 0.7pt (~1px) altura | `#E8E8E8` |
| Manchete (3 linhas) | x 102, y 414.1/451.6/489.9 (~37,9pt entrelinha) | LiberationSans-Bold | **36pt (~48px)** | `#1A1A1A` — **sem nenhum acento laranja**, as 3 linhas são todas pretas |
| Parágrafo (4 linhas) | x 102, y 547.8→597.3 (~16,5pt entrelinha) | LiberationSans regular | 11pt (~14.7px) | `#6B6B6B` |
| "Preparado para [Cliente]" | x 102, y 630.3 | LiberationSans-Bold | 11pt (~14.7px) | `#1A1A1A` |
| Metadados (3 linhas, "Rótulo · valor" numa linha bold só) | x 102, y 733.9/747.4/760.9 (~13,5pt entrelinha) | LiberationSans-Bold | 8pt (~10.7px) | `#1A1A1A` |
| Selo "CONFIDENCIAL" (moldura sem preenchimento) | x 431.6→532.9, y 751.1→770.6 (101×19.5pt / 135×26px) | LiberationSans-Bold | 7.5pt (~10px) | texto e borda `#F47B20`, sem fundo |
| Painel decorativo topo-direita | x 255→595.5, y 0→340.5 | — | gradiente/pattern (não deu pra extrair a cor exata via `pdfplumber` — é um "shading pattern" do PDF) | tom claro, provavelmente laranja bem diluído |

**Relação com o que já existe**: a barra lateral (`#F47B20`, full-height, bleed até a borda —
CLAUDE.md Seção 6.25) e o laranja em si já batem exatamente com a referência — não precisa
recriar esses dois. O que muda: largura da barra (1cm atual → 1,8cm), todo o alinhamento
(centralizado → esquerda), o masthead (hoje é `.marca`/`.selo` centralizados sem subtítulo — vira
um bloco no canto superior esquerdo com subtítulo), a manchete perde o acento laranja só na capa
(as manchetes das Seções internas continuam com acento, isso não muda), o parágrafo de resumo
some do centro e vai pra esquerda, os metadados deixam de ser uma linha horizontal com
rótulo-em-cima-valor-embaixo e viram 3 linhas empilhadas "Rótulo · valor", e ganha o selo
"CONFIDENCIAL" com moldura (hoje só existe o selo "CONFIDENCIAL" preenchido no rodapé de
página — Seção 6.22 — este é um elemento novo, exclusivo da capa).

**Decisões (2026-08-06, resolvidas — usuário confirmou "quero a exata cópia" do design; texto de
identidade é adaptado ao produto real, no mesmo formato/posição/peso/cor da referência, nunca
copiando o nome de uma empresa terceira real. Atualização no mesmo dia: o nome "CRARP" é
provisório — o usuário disse explicitamente que o nome da empresa prestadora do serviço vai
mudar pro nome correto depois. Por isso o nome NÃO pode ficar hardcoded espalhado no template —
vira uma configuração central, trocar depois é uma linha só)**:
1. **Nome/serviços da empresa prestadora viram configuração, não texto fixo no template.** Novas
   settings em `crarp/settings.py` (mesmo padrão de variável de ambiente com default já usado no
   projeto, ex. `WHATSAPP_INSTANCE_NAME`/`DJANGO_ALLOWED_HOSTS` do projeto irmão Elo — aqui local,
   `os.environ.get(..., default)`):
   ```python
   NOME_EMPRESA_PRESTADORA = os.environ.get("NOME_EMPRESA_PRESTADORA", "CRARP")
   SERVICOS_EMPRESA_PRESTADORA = os.environ.get(
       "SERVICOS_EMPRESA_PRESTADORA", "GESTÃO DE RISCOS PSICOSSOCIAIS"
   )
   ```
   `relatorios/services/pdf.py::_contexto_relatorio` passa os dois pro contexto do template
   (`nome_empresa_prestadora`, `servicos_empresa_prestadora`) lendo de
   `django.conf.settings`. O template usa `{{ nome_empresa_prestadora }}` e
   `{{ servicos_empresa_prestadora }}` — nunca "CRARP" escrito direto no HTML.
2. **Letra na marca**: **primeira letra de `nome_empresa_prestadora`, calculada automaticamente**
   (`{{ nome_empresa_prestadora|first|upper }}`) — não fixa em "C", pra continuar correta sozinha
   quando o nome mudar (hoje "C" de CRARP, depois vira a letra do nome real, sem precisar tocar
   no template de novo). Reproduz a mesma proporção do quadrado 32×32px a 14pt da referência
   (1 letra só, igual ao "S" da Solute).
3. **Conteúdo do `<h1>`**: mantém a mesma função estrutural da referência — o `<h1>` vira o
   **assunto do relatório** ("Fatores Psicossociais no Trabalho." — frase que já descreve
   exatamente o que este produto mede, não precisou adaptar), e o nome da empresa **cliente**
   (`{{ empresa.nome }}`, não a prestadora) desce pra linha "Preparado para {{ empresa.nome }}",
   igual à referência. Eyebrow adaptado pro nosso escopo real (NR-01/fatores psicossociais, não
   "saúde mental" especificamente): "DIAGNÓSTICO TÉCNICO · RISCOS PSICOSSOCIAIS".

**Especificação de execução** (`relatorios/templates/relatorios/inventario.html`, bloco `.capa`
e CSS associado — reescrita completa, não ajuste pontual):
1. `.capa`: remover `text-align: center`; `margin-top` deixa de ser fixo em 5cm — o masthead
   passa a começar logo no topo da área imprimível (a referência tem o masthead a ~3,09cm do
   topo, que já é quase exatamente a nossa margem de página atual de 3,2cm — não precisa de
   margem extra antes dele).
2. `.capa .barra-lateral`: `width: 1cm` → `width: 1.8cm` (51pt exato).
3. **Novo bloco de masthead** (substitui `.marca`/`.selo` centralizados atuais): `<div
   class="capa-masthead">` com o quadrado de 32×32px (`background:#F47B20`, letra branca bold
   ~19px, `{{ nome_empresa_prestadora|first|upper }}`) à esquerda e, ao lado (gap ~11px), duas
   linhas de texto — `{{ nome_empresa_prestadora }}` em bold 15px `#1A1A1A` e
   `{{ servicos_empresa_prestadora }}` em 10px `#6B6B6B` com letter-spacing. Todo o bloco
   alinhado à esquerda (`display:flex; align-items:flex-start`), sem centralizar. Nenhum dos dois
   textos hardcoded no template — vêm de `settings.NOME_EMPRESA_PRESTADORA`/
   `SERVICOS_EMPRESA_PRESTADORA` (item 1 da especificação de execução, acima).
4. Espaço entre o masthead e o eyebrow: a referência tem um vão grande (masthead termina ~y=113pt,
   eyebrow começa em y=344pt → ~231pt ≈ 8,15cm de distância) — cerca de 41% da altura da página.
   Implementar como `margin-top` grande no bloco do eyebrow (ex. `margin-top: 8cm`, ajustar
   depois de gerar um PDF de teste pra bater visualmente).
5. Eyebrow: nova `<div class="capa-eyebrow">DIAGNÓSTICO TÉCNICO · [algo equivalente]</div>`
   (texto a definir com você — o nosso "assunto" não é exatamente "Saúde mental no trabalho", é
   psicossocial/NR-01; sugestão: "DIAGNÓSTICO TÉCNICO · RISCOS PSICOSSOCIAIS"), 11.3px bold,
   `#F47B20`, uppercase, letter-spacing, alinhado à esquerda. Linha divisória logo abaixo:
   `height:1px; background:#E8E8E8; width: 12.6cm` (ou 100% da coluna de conteúdo).
6. Manchete: `.capa h1` continua reaproveitando `{{ empresa.nome }}` OU muda pra um texto fixo
   tipo "Fatores Psicossociais no Trabalho." com o nome da empresa indo pro "Preparado para"
   (mais fiel à referência, que separa "assunto do documento" de "cliente") — **isso também
   precisa da sua confirmação**, porque hoje `<h1>{{ empresa.nome }}</h1>` é o nome do cliente em
   destaque, e a referência usa esse espaço pro ASSUNTO do relatório, não pro nome do cliente.
   Tamanho 48px bold, `#1A1A1A`, `line-height` ~1.05, `text-align:left`, **sem `.acento`** (a
   manchete da capa não usa a cor laranja, diferente das manchetes de Seção internas).
7. Parágrafo de resumo: mover pra esquerda, `text-align:left`, `max-width: 12.6cm`, 14.7px
   regular `#6B6B6B`.
8. Nova linha "Preparado para {{ empresa.nome }}" (bold, 14.7px, `#1A1A1A`) — só existe se a
   decisão do item 6 for mover o nome da empresa pra cá.
9. Metadados: trocar `.meta-linha` (flex horizontal, rótulo em cima) por 3 `<div>` empilhados,
   cada um bold 10.7px `#1A1A1A`, texto único "**Rótulo** · valor" (ex.: "Emissão · 06 de agosto
   de 2026"). Campos: Emissão (`gerado_em`), Ciclo (não temos um conceito de "ciclo" no modelo —
   usar `relatorio.periodo_inicio.year` + algum contador, ou substituir por "Período" que já
   temos), Participação (somar `n_respondentes` de todas as Aplicações do relatório).
10. Novo selo "CONFIDENCIAL" com moldura (não preenchido): `<div class="capa-selo-confidencial">`,
    posicionado `position:absolute` no canto inferior direito da capa, borda 1px `#F47B20`,
    texto 10px bold uppercase `#F47B20`, sem fundo, padding ~6px 14px, `border-radius` pequeno.
11. (Opcional, prioridade baixa — não deu pra extrair a cor exata do PDF de referência) painel
    decorativo no canto superior direito — pode ser aproximado com um `radial-gradient` sutil em
    tom de laranja bem diluído, ou deixado de fora se você preferir simplicidade.
12. Gerar um PDF real depois de implementado e comparar lado a lado com a referência (mesmo
    método rigoroso das rodadas anteriores — nunca só confirmar visualmente sem gerar o
    documento de verdade).

**Status**: decisões resolvidas — pronto pra execução quando você mandar.

---

### 14. Panorama "O que está protegendo" precisa de leitura qualitativa por domínio (não só nome+GHE)

**Pedido original**: você comparou o que seu relatório mostra em "O que está protegendo" — "Exigências
quantitativas (EQ) — Escritório 2 / Ritmo de trabalho (RT) — Escritório 2 / ..." — com o que a
referência mostra — "Reconhecimento percebido — colaboradores relatam sentir que o esforço é
notado pelas chefias diretas. / Clareza de papel — atribuições e expectativas estão razoavelmente
bem comunicadas. / ..." — e pediu pra reproduzir o modelo da referência: nome do domínio (sem
sigla) + uma breve explicação, cobrindo os 3 instrumentos (COPSOQ adaptado, COPSOQ Oficial nas 3
profundidades, ITRA), com um banco de dados de "o que dizer quando esse domínio está favorável".

**Diagnóstico já feito** (2026-08-06, mesma conversa): a sigla "(EQ)" que ainda aparece no seu
relatório é porque a correção do item 6 (remover siglas) não foi implantada na VPS ainda —
Etapa 2 desta fila foi implementada mas não commitada/enviada (ver conversa anterior). Isso já
está resolvido no código local, só falta o deploy — não é um item novo. **O problema novo, real,
é a falta de explicação qualitativa**: `_montar_panorama()` (`relatorios/services/pdf.py:248-303`)
monta a lista "protegendo" só com `dominio_nome`, `ghe_nome` e a banda — nunca existiu um campo de
texto explicativo por domínio pra esse caso. Confirmei em `instrumentos/models.py` que
`Dominio.nota` existe, mas é reservado pra avisos de polaridade mista (Seção 5.1, D9) — usar esse
campo pra outra coisa quebraria sua semântica atual. É necessário um campo novo.

**Por que só "protegendo" e não "pede ação" também**: os domínios que pedem ação já ganham texto
qualitativo em outro lugar do documento — a Seção "Achados" (`_parecer_para_exibicao`, Seção 6.21
do CLAUDE.md) já funde parecer + risco + recomendação por domínio fora de Aceitável, gerado pela
IA a partir do parecer técnico. Só os domínios **Aceitável** (protegendo) nunca recebem nenhuma
análise textual em lugar nenhum do PDF hoje — daí a lista pobre que você viu. Se você quiser o
mesmo tratamento de "leitura fixa por banco de dados" também pro lado "pede ação" (em vez do texto
gerado por IA que já existe), me avisa que registro como item separado.

**Relação com o que já existe**: mesmo padrão já usado pro catálogo de ações
(`seeds/catalogo_acoes.json`/`catalogo_acoes_copsoq_oficial.json`, CLAUDE.md Seção 6.9 Prompt 07 e
Seção 6.13) — texto elaborado por domínio, carregado via seed, nunca gerado em tempo real por IA
(isso mantém o Panorama determinístico e sem custo de API, diferente do parecer). Reaproveita o
mesmo mecanismo de carga (`load_instrumentos`), só adiciona um campo novo no `Dominio`.

**Especificação de execução**:
**Atualização de 2026-08-06 (mesma conversa) — feedback em 2 níveis dentro de "protegendo"**: o
usuário pediu que a frase varie por intensidade — **"muito positivo"** quando a maioria das
respostas está muito baixa (bem dentro da faixa aceitável) e **"favorável"** quando está aceitável
mas mais perto do limite. E confirmou explicitamente que "Moderado" nunca deve aparecer em
"protegendo" — perguntei se isso deveria ser reforçado como trava adicional (já que Banda e
Classificação são cálculos independentes e podem divergir em casos raros — é literalmente o que os
itens 9/10 desta fila corrigiram) e o usuário pediu pra eu decidir; decidi que sim, adicionar a
trava, porque é mais seguro num documento com peso legal nunca mostrar mensagem "favorável"/"muito
positivo" ao lado de um resultado que tecnicamente é Moderado.

1. **`instrumentos/models.py::Dominio`** — dois novos campos:
   ```python
   leitura_favoravel = models.TextField(blank=True, help_text="Frase curta pra quando o domínio "
       "está na faixa Aceitável mas mais perto do limite (Panorama, 'O que está protegendo').")
   leitura_muito_favoravel = models.TextField(blank=True, help_text="Frase curta pra quando o "
       "domínio está bem dentro da faixa Aceitável (a maioria das respostas muito baixa/muito "
       "protetiva) — mesma seção, tom mais forte que leitura_favoravel.")
   ```
   Migration.
2. **`instrumentos/management/commands/load_instrumentos.py`** — ler as chaves opcionais
   `"leitura_favoravel"`/`"leitura_muito_favoravel"` de cada item de domínio/escala no seed JSON e
   gravar nos dois campos (mesmo padrão já usado pra `note`/`ghe_variante_nome`).
3. **Critério de corte entre os dois níveis** — usa o mesmo `CriterioVersao.limite_baixo` que já
   existe (hoje 37,5 na escala 0-100, Seção 6.9 Prompt 02 do CLAUDE.md) dividido ao meio, decisão
   de engenharia documentada (mesmo padrão já usado em outros cortes derivados deste projeto, ex.
   EADRT Seção 7.3): `escore <= limite_baixo / 2` → muito positivo; `limite_baixo / 2 < escore <=
   limite_baixo` → favorável. Como o escore já vem sempre normalizado pra "maior = mais risco"
   independente da polaridade original do item (`inverter_se_necessario`, Seção 7.1), esse corte
   funciona igual pra domínios `RISCO` e `PROTETIVO` sem tratamento especial.
4. **Trava adicional de Classificação** — `_montar_panorama` só classifica um domínio como
   "protegendo" se `banda == "Aceitável"` **E** `escore_dominio.classificacao == "Baixo"`; se a
   Classificação for "Moderado" (mesmo com Banda Aceitável, caso raro de divergência), o domínio
   vai pra `pede_acao`/`frentes_atencao` em vez de "protegendo".
5. **Autoria do conteúdo** (o "banco de dados" pedido) — **2 frases por domínio** (muito
   positivo/favorável), nos 3 seeds:
   - `seeds/copsoq_rr_revestir.json` — 9 domínios (D1–D9, COPSOQ adaptado).
   - `seeds/copsoq_oficial.json` — 35 subescalas (EQ, RT, EC, EE, IT, PD, PREV, TPL, REC, CONFL,
     ASC, ASS, CO, IL, SG, e as demais de compromisso/confiança/conflito família-trabalho/saúde —
     Seção 5.1.1 do CLAUDE.md).
   - `seeds/itra.json` — 5 escalas (EACT, ECHT, EADRT, EIPSTP, EIPSTN).
   Total: ~98 frases. Critério de voz (mesmo espírito do `SYSTEM_PROMPT` do parecer,
   `analise_ia.py`, reforçado pelo usuário em 2026-08-06: **simples, objetivo, fácil de ler e
   compreender** — sem jargão técnico desnecessário, sem frase longa/composta, uma ideia por
   frase): uma frase só por nível, linguagem simples, descreve o que se observa/relata na equipe
   — nunca tom clínico/diagnóstico, nunca promete algo que o dado não mede. Exemplos de
   referência (âncora pras outras ~94 frases a escrever na implementação):
   - COPSOQ adaptado D3 (Autonomia e controle, PROTETIVO):
     - muito positivo: "colaboradores relatam autonomia consistente para organizar tarefas,
       prioridades e pausas, sem qualquer sinal de restrição."
     - favorável: "colaboradores relatam ter liberdade para organizar suas tarefas e fazer pausas
       básicas sem prejuízo ao trabalho."
   - ITRA EIPSTN (Indicadores de sofrimento no trabalho, RISCO):
     - muito positivo: "a equipe praticamente não relata esgotamento, frustração ou insegurança
       no dia a dia de trabalho."
     - favorável: "a equipe relata níveis baixos de esgotamento, frustração ou insegurança no dia
       a dia de trabalho."
   - COPSOQ Oficial IL (Insegurança laboral, RISCO):
     - muito positivo: "praticamente ninguém relata preocupação com perda do emprego ou mudanças
       abruptas na função."
     - favorável: "a equipe não relata preocupação relevante com perda do emprego ou mudanças
       abruptas na função."
6. **`relatorios/services/pdf.py::_montar_panorama`** — na `entrada` do ramo `protegendo` (linha
   ~285-293), calcular o nível (`muito_favoravel` se `escore <= limite_baixo/2`, senão
   `favoravel`) e resolver o texto certo:
   `"leitura": (dominio.leitura_muito_favoravel or dominio.leitura_favoravel) if nivel == "muito_favoravel" else dominio.leitura_favoravel`
   — com fallback pra `leitura_favoravel` se a frase "muito positivo" ainda não tiver sido
   escrita pra aquele domínio.
7. **`relatorios/templates/relatorios/inventario.html`** (lista "O que está protegendo", linha
   ~527) — trocar `<li>{{ p.dominio_nome }}{% if ... %} — {{ p.ghe_nome }}{% endif %}</li>` por:
   ```html
   <li><strong>{{ p.dominio_nome }}</strong> — {{ p.leitura|default:"resultado dentro da faixa aceitável." }}{% if panorama.protegendo|length > 1 %} ({{ p.ghe_nome }}){% endif %}</li>
   ```
   O `|default` cobre qualquer domínio cujo texto eu não tenha escrito ainda (nunca deixa a linha
   em branco).
8. Gerar um PDF real (idealmente um GHE com domínios cobrindo os dois níveis, de instrumentos
   diferentes) e conferir visualmente contra a referência.

**Status**: aguardando sua confirmação pra executar. As ~98 frases completas (2 por domínio)
serão escritas no momento da implementação, seguindo o tom dos exemplos acima.

---

### 15. Panorama "O que pede ação" precisa da mesma leitura qualitativa do "O que está protegendo"

**Pedido original**: hoje "O que pede ação" mostra só nome do domínio (ainda com sigla — mesma
correção do item 6, só falta o deploy) e a banda ("Moderado"/"Alto") em cores. O usuário mandou o
exemplo da referência ("Condução de mudanças — comunicação tardia e ausência de espaço para
dúvidas.") e pediu o mesmo nível de detalhe do item 14 ("O que está protegendo"), **mas mantendo
o badge colorido de Moderado/Alto**, porque isso já tem alto impacto visual no relatório atual.

**Diagnóstico e decisão** (2026-08-06, mesma conversa): pra manter a mesma confiabilidade do item
14 (determinístico, sem custo de IA, nunca incompleto — evitando o problema documentado na Seção
6.17 do CLAUDE.md de a IA devolver listas incompletas quando cobre muitos domínios de uma vez),
"pede ação" também vira **fixo/banco de dados**, no mesmo mecanismo do item 14 — não reaproveita o
texto já gerado pela IA na Seção "Achados" (Seção 4), que fica como está, é conteúdo mais extenso
e already existe pra esse fim.

**Diferença de escopo pro "Crítico"**: Banda Crítico não vem de prevalência (Moderado/Alto vêm),
vem só de evento grave confirmado (violência, ameaça, assédio moral ou discriminação relatados —
Seção 7.5/6.14 do CLAUDE.md) — não faz sentido escrever uma frase fixa "quando o domínio X está
crítico", porque o motivo é sempre o mesmo tipo de evento, não uma variação da prevalência daquele
domínio específico. Pra Crítico, reaproveita a mesma framing que `dominios_criticos_evento_grave`
já usa em outros pontos do PDF (Seção 6.16) — uma frase fixa genérica citando o tipo de evento,
não uma frase por domínio.

**Especificação de execução**:
1. **`instrumentos/models.py::Dominio`** — mais dois campos (somando aos 2 do item 14, total 4
   novos campos no model):
   ```python
   leitura_pede_acao_moderado = models.TextField(blank=True, help_text="Frase curta pra quando "
       "este domínio está em Banda Moderado (Panorama, 'O que pede ação').")
   leitura_pede_acao_alto = models.TextField(blank=True, help_text="Frase curta pra quando este "
       "domínio está em Banda Alto (Panorama, 'O que pede ação').")
   ```
   Uma migration só cobre os 4 campos dos itens 14+15 (não precisa gerar migrations separadas).
2. **`instrumentos/management/commands/load_instrumentos.py`** — ler as chaves opcionais
   `"leitura_pede_acao_moderado"`/`"leitura_pede_acao_alto"` dos seeds, mesmo padrão dos outros
   campos de leitura.
3. **Autoria do conteúdo** — 2 frases por domínio (Moderado/Alto), nos mesmos 3 seeds do item 14
   (~98 frases adicionais, total 196 somando com o item 14). Mesmo critério de voz do item 14
   (reforçado pelo usuário em 2026-08-06: **simples, objetivo, fácil de ler e compreender**, sem
   jargão, uma ideia por frase): uma frase só, linguagem simples, descreve o que se
   observa/relata na equipe quando o domínio está nessa banda — nunca tom clínico, nunca promete
   uma causa que o dado não prova (isso é papel do parecer técnico, não do Panorama). Exemplos de
   referência:
   - COPSOQ Oficial EC (Exigências cognitivas, RISCO) Moderado: "a equipe relata exigência de
     atenção simultânea e resolução de problemas em ritmo mais intenso que o desejável."
   - COPSOQ Oficial IT (Influência no trabalho, PROTETIVO) Alto: "colaboradores relatam pouca
     influência sobre como e quando o próprio trabalho é realizado."
   - COPSOQ Oficial ASS (Apoio social de superiores, PROTETIVO) Alto: "a equipe relata pouco
     suporte percebido da liderança direta nas dificuldades do dia a dia."
   - COPSOQ Oficial IL (Insegurança laboral, RISCO) Alto: "parte relevante da equipe relata
     preocupação recorrente com perda do emprego ou mudança abrupta de função."
4. **`relatorios/services/pdf.py::_montar_panorama`** — na `entrada` do ramo `pede_acao`/
   `frentes_atencao` (linha ~294-296), resolver `"leitura"`:
   - `banda == "Moderado"` → `dominio.leitura_pede_acao_moderado`
   - `banda == "Alto"` → `dominio.leitura_pede_acao_alto`
   - `banda == "Crítico"` → frase fixa reaproveitando a mesma citação de evento grave já usada em
     `_dominios_criticos_por_evento_grave` (ex.: "relato confirmado de evento grave — violência,
     ameaça, assédio moral ou discriminação — exige resposta imediata, independente da
     prevalência.").
5. **`relatorios/templates/relatorios/inventario.html`** (lista "O que pede ação", linha ~539) —
   trocar `<li>{{ p.dominio_nome }} — <span class="badge ...">{{ p.banda }}</span></li>` por:
   ```html
   <li><strong>{{ p.dominio_nome }}</strong> — {{ p.leitura|default:"resultado fora da faixa aceitável." }} <span class="badge {{ p.banda_css }}">{{ p.banda }}</span>{% if panorama.pede_acao|length > 1 %} ({{ p.ghe_nome }}){% endif %}</li>
   ```
   Mantém o badge colorido exatamente como já é hoje — só adiciona a explicação antes dele.
6. Gerar um PDF real (idealmente cobrindo Moderado, Alto e Crítico) e conferir visualmente.

**Status**: aguardando sua confirmação pra executar.

---

### 16. Card "Frentes de atenção" do Panorama precisa citar os domínios de verdade (não texto genérico)

**Pedido original**: o usuário mandou um print do card escuro "N Frentes de atenção" da referência
— número grande laranja + rótulo vertical "FRENTES / DE / ATENÇÃO" à esquerda, e à direita um
parágrafo que CITA os domínios específicos em negrito ("mudanças organizacionais conduzidas sem
preparo, volume de demandas no ritmo cotidiano e autonomia restrita em decisões operacionais") e
termina com um prazo concreto ("nos próximos 90 a 180 dias") — e pediu que o nosso ficasse mais
parecido, no lugar do texto genérico atual: "**Frente(s) de atenção** — domínio(s) fora da faixa
Aceitável neste ciclo. Nenhuma delas está necessariamente em nível crítico isolado, mas todas se
beneficiam de intervenção preventiva conforme o prazo indicado na Seção 5."

**Diagnóstico já feito** (2026-08-06, mesma conversa): `.card-destaque`
(`relatorios/templates/relatorios/inventario.html:418-429` CSS, `:529-537` HTML) hoje é: número
grande + "**Frente(s) de atenção**" como parte do próprio parágrafo (não um rótulo separado à
esquerda), e o texto nunca nomeia os domínios nem dá um prazo real — só remete genericamente "à
Seção 5". `_montar_panorama()` (`relatorios/services/pdf.py:248-322`) já calcula tudo que falta
pra resolver isso: `frentes_atencao` é a lista completa dos domínios fora de Aceitável (cada um já
com `dominio_nome` e `banda`), só falta ordenar por gravidade, escolher quais citar por extenso, e
calcular o prazo. `nivel_geral_risco` (Baixo/Moderado/Alto) já existe pra abrir a frase ("Embora o
índice geral esteja em faixa X...").

**Relação com o que já existe**: reaproveita `BANDA_ORDEM` (já importado em `pdf.py`, usado pra
ordenar planos de ação por urgência) e `ClassificacaoRisco.prazo_dias_plano_de_acao` (já calculado
por domínio, Seção 7.6 do CLAUDE.md) — nenhum cálculo novo de risco, só reorganização de dado que
já existe. **Não** cria mais nenhum campo de texto novo no `Dominio` (diferente dos itens 14/15) —
o card cita o **nome real do domínio** em negrito, sem parafrasear, mesma decisão já tomada no
item 15 pra manter a fonte de verdade sempre o nome oficial do domínio.

**Especificação de execução**:
1. **`relatorios/services/pdf.py::_montar_panorama`** — antes do `return`, com `frentes_atencao`
   já calculada:
   - Ordenar `frentes_atencao` por `BANDA_ORDEM` decrescente (pior primeiro — Crítico > Alto >
     Moderado).
   - `frentes_destaque = frentes_atencao[:3]` (as 3 mais graves, pra citar por extenso — número
     escolhido pra manter a frase curta e legível, "simples e objetivo" como já pedido nos itens
     14/15; ajustável depois se você achar 3 pouco ou demais).
   - `frentes_resto = max(0, len(frentes_atencao) - 3)` (quantas ficam de fora da citação).
   - `tem_frente_critica = any(f["banda"] == "Crítico" for f in frentes_atencao)`.
   - Prazos: coletar `prazo_dias_plano_de_acao` de cada `classificacao_risco` das frentes (já
     calculado por domínio); `prazo_min`/`prazo_max` = mínimo/máximo entre os valores presentes
     (`None` tratado fora, não deveria acontecer já que toda frente fora de Aceitável sempre tem
     prazo).
   - Adicionar ao dict de retorno: `frentes_destaque`, `frentes_resto`, `tem_frente_critica`,
     `prazo_min`, `prazo_max`.
2. **CSS** (`inventario.html`) — `.card-destaque` ganha um bloco à esquerda dedicado ao
   número+rótulo (`display:flex` já existe, só precisa envolver número+rótulo num `<div>` próprio
   em vez do número solto):
   ```css
   .card-destaque .numero-bloco { text-align: center; flex-shrink: 0; }
   .card-destaque .rotulo-vertical {
       font-size: 9px; letter-spacing: .08em; text-transform: uppercase;
       color: #bbb; line-height: 1.4; margin-top: 4px;
   }
   ```
3. **HTML** — trocar o conteúdo de `.card-destaque` (linhas 529-537) por:
   ```html
   <div class="card-destaque">
       <div class="numero-bloco">
           <div class="numero">{{ panorama.frentes_atencao|length }}</div>
           <div class="rotulo-vertical">Frente{{ panorama.frentes_atencao|pluralize }}<br>de<br>atenção</div>
       </div>
       <div class="texto">
           {% if panorama.frentes_atencao %}
           Embora o índice geral esteja em faixa {{ panorama.nivel_geral_risco|lower }},
           {{ panorama.frentes_atencao|length }} frente{{ panorama.frentes_atencao|pluralize }}
           concentra{{ panorama.frentes_atencao|pluralize:"m" }} a maior parte da carga psicossocial relatada —
           {% for f in panorama.frentes_destaque %}<strong>{{ f.dominio_nome }}</strong>{% if not forloop.last %}, {% endif %}{% endfor %}{% if panorama.frentes_resto %}, entre outras{% endif %}.
           {% if panorama.tem_frente_critica %}
           Uma ou mais frentes estão em nível crítico e exigem resposta imediata, independente do prazo abaixo.
           {% else %}
           Nenhuma dessas frentes está em nível crítico,
           {% endif %}
           todas se beneficiam de intervenção preventiva
           {% if panorama.prazo_min == panorama.prazo_max %}em até {{ panorama.prazo_min }} dias{% else %}entre {{ panorama.prazo_min }} e {{ panorama.prazo_max }} dias{% endif %}.
           {% else %}
           Nenhum domínio saiu da faixa Aceitável neste ciclo — não há frentes de atenção a destacar.
           {% endif %}
       </div>
   </div>
   ```
4. Gerar um PDF real com pelo menos 3-4 frentes de bandas diferentes (Moderado + Alto, e
   idealmente um caso com Crítico) e conferir visualmente contra a referência — inclusive o caso
   de 0 frentes (relatório todo Aceitável), que a referência não mostra mas o nosso sistema
   precisa continuar cobrindo sem quebrar o card.

**Status**: aguardando sua confirmação pra executar.

---

### 17. Reformular Seção "02 · Como foi feito" (Base técnica) no exato modelo da referência

**Pedido original**: reproduzir exatamente o design da Seção "Base técnica e protocolo de leitura"
da referência: passo a passo em 3 cards (Coleta/Mensuração/Classificação) com subtítulo e legenda
minimalista dentro dos cards, "Referências teóricas" citando as referências completas e permitindo
adicionar outras com o tempo, "Faixas de interpretação" no mesmo estilo visual mas com os
números/lógica do nosso sistema (não os números da referência), e uma nota de confidencialidade no
mesmo estilo — tudo no design/cores minimalistas da referência. Consultei o PDF de referência
(`Diagnostico_Psicossocial_Modelo_Solute.pdf`, página 3) com `pdfplumber` pra extrair posição,
cor, fonte e tamanho exatos de cada elemento — igual ao rigor já usado no item 13 (capa).

**Achado importante durante a extração**: a manchete da referência tem só "protocolo de leitura"
em laranja (3 palavras — confirmado caractere a caractere, não só visualmente), e a nossa manchete
atual (`inventario.html:570`) só destaca "leitura" (1 palavra) — a mesma inconsistência de acento
já corrigida em outros títulos nas rodadas anteriores (CLAUDE.md Seção 6.23, item 4) passou
despercebida nesta seção. Corrigido nesta especificação também.

**Dados extraídos da referência (página 3, 594.96×841.92pt)**:

| Elemento | Posição/tamanho | Fonte/cor |
|---|---|---|
| Manchete | x 62.4, y 136.4, 22pt bold | "Base técnica e " preto `#1A1A1A` + "protocolo de leitura" **laranja** `#F47B20` + "." preto |
| Parágrafo intro (3 linhas) | x 62.4, y 172.8→207.3, 11pt regular | `#2E2E2E` |
| 3 cards do passo a passo | x0 62.2/222.0/381.0, top 234.7, ~152×125pt cada | borda 1px `#E8E8E8`, fundo branco, gap ~8pt entre eles |
| — eyebrow do card ("01 · COLETA") | 8pt bold, laranja | dentro do card, ~12pt do topo |
| — subtítulo do card ("Aplicação anônima") | 10pt bold, preto | logo abaixo do eyebrow |
| — corpo do card (4 linhas) | 9pt regular, `#6B6B6B` | linha 13.5pt |
| "Referências teóricas" (h3) | x 62.4, y 391.8, 13pt bold preto | barra de acento laranja 1.5pt logo abaixo (127.5pt de largura) |
| Lista de referências (3 itens, "–" laranja) | x 84.2, 10.5pt — título em bold + descrição em regular, ambos pretos `#1A1A1A` (não cinza) | dash laranja como marcador, mesmo padrão já usado em `.coluna-leitura li::before` |
| "Faixas de interpretação" (h3) | x 62.4, y 562.0, 13pt bold preto | mesma barra de acento laranja abaixo (145.5pt) |
| Tabela de faixas (3 linhas) | colunas "FAIXA/ESCORE/LEITURA TÉCNICA", cabeçalho 7.5pt bold cinza uppercase; linhas 9pt regular; badge-pill por linha (não coluna de badge separada) | Favorável: texto `#3F7D3F` / pill `#EAF3EA`. Atenção: texto `#B5760F` / pill `#FBF1DC` (**já é exatamente a cor do nosso `.badge-suave.moderado` hoje**). Crítico: texto `#A93226` / pill `#F8E4E1` (muito próximo do nosso `.badge-suave.alto` `#FBE6E2`) |
| Divisórias entre linhas | 0.7pt, `#E8E8E8` (mais forte, `#1A1A1A`, só embaixo do cabeçalho) | — |
| Caixa de confidencialidade | 471×39pt, fundo `#FAFAF7`, borda esquerda 2.2pt `#A8A8A8` (cinza, **não laranja/navy** — diferente da nossa `.caixa-explicativa` atual) | "**Sobre confidencialidade.**" bold 8.5pt preto + resto 8.5pt cinza `#6B6B6B` |

**Relação com o que já existe**: nosso documento divide esse conteúdo em **duas seções**
(`inventario.html:567-601` Seção 02 "Base técnica e legal" — NR-01, COPSOQ, instrumentos por GHE;
`inventario.html:603-...` Seção 03 "Metodologia" — passo a passo + tabela de N por domínio),
enquanto a referência junta tudo numa página só. **Decisão de estrutura**: manter as duas seções
(nosso conteúdo legal/tabela de N por domínio é mais denso que o da referência e não cabe numa
página só sem virar bagunça), mas:
- Seção 02 ganha, no final (depois do parágrafo "propósito do instrumento"), os 4 blocos novos:
  3 cards de passo a passo, Referências teóricas, Faixas de interpretação, Caixa de
  confidencialidade — nessa ordem, no exato estilo extraído acima.
- Seção 03 perde o parágrafo introdutório genérico (o conceito de "passo a passo" já foi coberto
  pelos 3 cards da Seção 02) e passa direto pra tabela de instrumentos por GHE + N por domínio,
  que é dado técnico específico, não descrição de processo.
- A tabela "Critério de classificação da Banda" que já existe em outro lugar do documento (Seção
  6.14 do CLAUDE.md, `criterio_classificacao_linhas`) **não é duplicada** — "Faixas de
  interpretação" aqui é uma versão resumida/executiva (3 linhas, Baixo/Moderado/Alto — nosso real
  critério de Banda por prevalência, não os números "até 25/26 a 50/acima de 50" da referência,
  que são de outro instrumento/outra metodologia).

**Especificação de execução**:
1. **Manchete** (linha 570): trocar `<span class="acento">leitura</span>` por envolver "protocolo
   de leitura" inteiro: `Base técnica e <span class="acento">protocolo de leitura</span>.`
2. **3 cards do passo a passo** — novo HTML/CSS em `inventario.html`, inserido no fim da Seção 02:
   ```html
   <div class="cards-processo">
       <div class="card-processo">
           <div class="eyebrow-card">01 · Coleta</div>
           <h4>Aplicação {% if ... %}anônima{% else %}identificada{% endif %}</h4>
           <p>Questionário estruturado, aplicado por link único por GHE, com N mínimo de
              {{ criterio.n_minimo_respondentes }} respondentes por recorte para proteção de identidade.</p>
       </div>
       <div class="card-processo">
           <div class="eyebrow-card">02 · Mensuração</div>
           <h4>Escores normalizados</h4>
           <p>Respostas em escala Likert convertidas em índices padronizados 0–100. Valores mais
              altos indicam maior exposição psicossocial.</p>
       </div>
       <div class="card-processo">
           <div class="eyebrow-card">03 · Classificação</div>
           <h4>Banda por prevalência</h4>
           <p>Cada domínio recebe uma Banda (Aceitável a Crítico) a partir do percentual de
              respondentes na faixa elevada, alinhada às exigências da NR-01 para integração ao
              Programa de Gerenciamento de Riscos.</p>
       </div>
   </div>
   ```
   **Importante**: o card 03 usa a descrição da NOSSA lógica real (Banda por prevalência, Seção
   6.14 do CLAUDE.md) — a referência descreve "Probabilidade × Severidade, grade 5×5", que é a
   matriz antiga que o nosso sistema abandonou; copiar isso literalmente descreveria uma lógica
   que não é mais a nossa.
   CSS: `.cards-processo { display:flex; gap: 8pt; margin: 16px 0; }`, `.card-processo { flex:1;
   border:1px solid #E8E8E8; border-radius:4px; padding: 12px 14px; }`, `.eyebrow-card { font-size:
   11px; font-weight:bold; color:#F47B20; text-transform:uppercase; letter-spacing:.04em; }`,
   `.card-processo h4 { font-size:13px; margin: 4px 0 8px; }`, `.card-processo p { font-size:12px;
   color:#6B6B6B; line-height:1.4; margin:0; }`.
3. **Referências teóricas — extensível, não hardcoded**: novo model
   `instrumentos.ReferenciaTeorica` (`titulo`, `descricao`, `ordem`), cadastrável via Django
   Admin (é o "permitir adicionar outras com o tempo" pedido) — seed inicial com as 3 já citadas
   noutro ponto do sistema (Seção 6.13 do CLAUDE.md, catálogo de ações): "Modelo
   Demanda-Controle-Suporte (Karasek & Theorell)", "Modelo Esforço-Recompensa (Siegrist)",
   "Justiça organizacional e qualidade da liderança". `_contexto_relatorio` passa
   `ReferenciaTeorica.objects.order_by("ordem")` pro template. HTML/CSS reaproveita o padrão de
   lista com traço já existente (`.coluna-leitura li::before`) — só precisa de uma nova classe
   com o texto em preto em vez de cinza (`color:#1A1A1A` em vez do cinza padrão dessas listas).
4. **Faixas de interpretação** — nova tabela compacta com pill-badge por linha (não reaproveita o
   componente de tabela genérico `.zebra` atual, que é grade/zebra, estilo diferente do pedido):
   ```html
   <h3>Faixas de interpretação<div class="acento-linha"></div></h3>
   <table class="tabela-faixas">
       <thead><tr><th>Faixa</th><th>Prevalência</th><th>Leitura técnica</th></tr></thead>
       <tbody>
           <tr><td><span class="badge-suave aceitavel">Baixo</span></td><td>até {{ criterio.prevalencia_p2|floatformat:0 }}%</td><td>Condições adequadas ou fatores protetivos presentes. Manter práticas atuais.</td></tr>
           <tr><td><span class="badge-suave moderado">Moderado</span></td><td>{{ criterio.prevalencia_p2|floatformat:0 }}% a {{ criterio.prevalencia_p1|floatformat:0 }}%</td><td>Sinais relevantes que pedem monitoramento e ação preventiva planejada.</td></tr>
           <tr><td><span class="badge-suave alto">Alto</span></td><td>acima de {{ criterio.prevalencia_p1|floatformat:0 }}%</td><td>Exposição significativa com potencial de impacto em saúde e desempenho.</td></tr>
       </tbody>
   </table>
   ```
   Usa `criterio.prevalencia_p1`/`prevalencia_p2` (já existem em `CriterioVersao`, Seção 6.9
   Prompt 02 do CLAUDE.md) em vez dos números fixos da referência ("até 25/26 a 50/acima de 50",
   que são de outro instrumento) — nossos percentuais reais de corte de prevalência.
   CSS: linhas com `border-bottom:1px solid #E8E8E8` (já é o padrão global de tabela do
   documento), badge-pill reaproveitando `.badge-suave` já existente (cores já batem quase exato
   com a referência, confirmado na extração acima).
5. **Caixa de confidencialidade** — nova classe (não reaproveita `.caixa-explicativa`, que tem
   borda navy grossa — a da referência é mais discreta, cinza, fundo quase branco):
   ```css
   .caixa-confidencialidade {
       background: #FAFAF7; border-left: 3px solid #A8A8A8;
       padding: 10px 14px; font-size: 11px; color: #6B6B6B; margin-top: 16px;
   }
   .caixa-confidencialidade strong { color: #1A1A1A; }
   ```
   ```html
   <div class="caixa-confidencialidade">
       <strong>Sobre confidencialidade.</strong> Resultados são apresentados de forma agregada.
       Recortes com menos de {{ criterio.n_minimo_respondentes }} respondentes são automaticamente
       omitidos, em conformidade com a LGPD e com a política interna de proteção de dados.
   </div>
   ```
6. **Seção 03 (Metodologia)** — remover o parágrafo introdutório genérico
   (`inventario.html:607-611`, "Coleta realizada por GHE... atualizado a cada novo ciclo de
   coleta.") já que os 3 cards da Seção 02 cobrem esse conceito; a seção passa a abrir direto na
   lista de instrumentos por GHE + tabela de N por domínio, que continuam como estão.
7. Gerar um PDF real e comparar lado a lado com a página 3 da referência.

**Status**: aguardando sua confirmação pra executar.

---

### 18. Remover a Seção "A coleta, passo a passo" + glossário de domínios na Base técnica

> **Reescrito em 2026-08-06** — versão original pedia reformular a Seção 5 em cards; o item 20
> decidiu remover a Seção 5 inteira em vez de reformular (fundindo com o Semáforo), o que
> esvaziou a maior parte da especificação original. O que sobrou de valor real (a frase "o que
> este domínio busca medir") virou um **glossário único**, decisão do usuário: mostrado uma vez
> na Seção 02 (Base técnica), logo depois de "Referências teóricas" (item 17) — não repetido em
> cada seção onde o domínio aparece (Panorama, Achados, tabela do Semáforo), pra não inflar o
> documento com a mesma frase reaparecendo várias vezes.

**Pedido original**: o usuário achou a Seção 03 ("A coleta, passo a passo.") redundante — depois
do item 17, a Seção 02 já cobre a metodologia de verdade, e a Seção 03 sobrava só como tabela
técnica sem leitura nenhuma. Junto com isso, queria uma frase por domínio explicando "o que esse
domínio busca medir" (ex.: pra "Reconhecimento e recompensas" → o que quer dizer isso, o que
busca medir). Como a Seção 5 (onde essa frase apareceria por card) foi removida pelo item 20,
virou glossário — pergunté "o que sugere que fica melhor" e o usuário confirmou a recomendação.

**Especificação de execução**:
1. **Remover a Seção 03** ("A coleta, passo a passo.", `inventario.html:603-...`) por completo —
   o parágrafo introdutório e a lista de "instrumento por GHE" já ficam cobertos pela Seção 02
   (parágrafo "O instrumento de coleta..." + lista "Instrumentos utilizados por GHE" que já
   existe lá). A tabela de N por domínio que existia na Seção 03 não precisa de substituto
   próprio — o N por domínio passa a aparecer na tabela compacta que o item 20 adiciona ao
   Semáforo.
2. **`instrumentos/models.py::Dominio`** — novo campo:
   ```python
   descricao_medicao = models.TextField(blank=True, help_text="Frase curta e neutra explicando "
       "o que este domínio mede — sempre a mesma, independente do resultado do ciclo. Usada no "
       "glossário de domínios, Seção 02 (Base técnica).")
   ```
   Mesma migration dos campos dos itens 14/15/17, se implementados juntos.
3. **`instrumentos/management/commands/load_instrumentos.py`** — ler a chave opcional
   `"descricao_medicao"` dos seeds, mesmo padrão dos outros campos de leitura.
4. **Autoria do conteúdo** — 1 frase neutra por domínio, nos 3 seeds (~49 frases). Critério de
   voz: neutro, não diz se é bom ou ruim, só define o que está sendo perguntado/medido — mesmo
   padrão "simples, objetivo, fácil de ler" pedido nos itens anteriores. Exemplos (domínios reais
   do nosso sistema):
   - COPSOQ adaptado D3 (Autonomia e controle): "Quanto a pessoa pode decidir como organizar,
     executar e ajustar o próprio trabalho."
   - COPSOQ adaptado D5 (Reconhecimento e recompensa): "Se o esforço da pessoa é percebido,
     valorizado e tem retorno proporcional."
   - ITRA EACT (Avaliação do contexto do trabalho): "Como estão organizadas as condições, o ritmo
     e as normas de trabalho no dia a dia."
5. **`relatorios/templates/relatorios/inventario.html`** — novo bloco "Glossário de domínios" na
   Seção 02, logo após a lista de "Referências teóricas" (item 17):
   ```html
   <h3>Glossário de domínios<div class="acento-linha"></div></h3>
   <dl class="glossario-dominios">
   {% for dominio in dominios_avaliados %}
       {% if dominio.descricao_medicao %}
       <dt>{{ dominio.nome }}</dt>
       <dd>{{ dominio.descricao_medicao }}</dd>
       {% endif %}
   {% endfor %}
   </dl>
   ```
   Precisa de `dominios_avaliados` no contexto (`_contexto_relatorio`) — lista única de domínios
   (sem repetir entre GHEs) realmente usados neste relatório, ordenada por `dominio__ordem`.
   CSS: `.glossario-dominios dt { font-weight: bold; font-size: 12.5px; margin-top: 8px; }`,
   `.glossario-dominios dd { margin: 2px 0 0; font-size: 11.5px; color: #666; }`.
6. Seções seguintes renumeradas (a lista de eyebrows "0X ·" desce um número cada) — mesma
   renumeração que o item 20 já vai mexer, fazer as duas remoções (Seção 03 e Seção 5) juntas
   evita renumerar duas vezes.
7. Gerar um PDF real e conferir o glossário (nomes batendo com os domínios do relatório, sem
   sigla — já corrigido pelo item 6) contra o que se espera.

**Status**: aguardando sua confirmação pra executar.

---

### 19. Redesenhar "O que a análise técnica aponta" (Achados) — cards enxutos, sem plano de ação

**Pedido original**: o usuário achou a Seção "O que a análise técnica aponta" (hoje uma tabela
`.ficha-acao` densa, texto pesado) ruim de ler, confirmou o problema já levantado antes (mistura
diagnóstico com plano de ação — tem uma linha "O que fazer" que é conteúdo de Plano de Ação) e
propôs reformular no mesmo estilo de card do item 18 (nome do domínio + achado em uma frase +
número + badge), com um rascunho de texto de exemplo. Pedi pra melhorar o rascunho antes de
travar — ele ainda misturava jargão interno ("prioridade P2") e uma recomendação disfarçada
("Recomenda-se atenção à distribuição do ritmo..."), os dois problemas que o usuário queria
eliminar. O usuário pediu pra eu escolher a origem do texto do achado (fixo como os itens 14/15,
ou IA mais curta) — decidi por **IA, mais curta e com escopo restrito** (ver justificativa
abaixo).

**Por que IA e não texto fixo aqui (diferente da decisão dos itens 14/15)**: os itens 14/15 usam
texto fixo porque não existia nenhuma proteção contra o problema de incompletude da IA documentado
na Seção 6.17 do CLAUDE.md (a IA já devolveu listas vazias quando cobre muitos domínios de uma
vez). A Seção de Achados **já tem essa proteção** — `_validar_cobertura_parecer`
(`relatorios/services/analise_ia.py`) já rejeita um parecer que não cobre todos os domínios fora
de Aceitável, então o risco que me fez recomendar texto fixo nos itens 14/15 já está mitigado
aqui. Além disso, o propósito desta seção (CLAUDE.md Seção 8.1: "IA gera a interpretação técnica
em linguagem natural... a partir de escores já calculados") é justamente trazer uma leitura
específica desta empresa/deste ciclo — se eu trocar por texto fixo igual ao do item 15, esta seção
vira uma repetição do Panorama sem nenhum valor a mais, o que não faz sentido ter as duas.

**Achado adicional durante a investigação** (2026-08-06, mesma conversa): `_rotulo()`
(`relatorios/services/pdf.py:156-158`, usada por `_parecer_para_exibicao` pra montar
`dominio_rotulo`) ainda monta `"{nome} ({codigo})"` — ou seja, **o título de cada card de Achados
ainda mostraria a sigla entre parênteses**, mesmo depois do item 6 (remover siglas) já
implementado. O item 6 cobriu 10 pontos do `inventario.html`, mas essa função em `pdf.py` não
estava na lista — é um gap real da varredura anterior, corrigido aqui já que estou mexendo no
mesmo trecho de código.

**Segundo achado, a partir do lembrete do usuário** ("não esqueça que deve mostrar do mais alto
pro moderado"): o template atual (`inventario.html:652`) ordena os achados com
`|dictsortreversed:"banda"` — esse filtro ordena **alfabeticamente**, não por gravidade. Entre os
valores possíveis aqui (Alto/Crítico/Moderado, nunca Aceitável), ordem alfabética decrescente dá
"Moderado, Crítico, Alto" — nem bate com o que o usuário pediu, nem com a gravidade real. Bug
pré-existente, corrigido nesta mesma especificação usando `BANDA_ORDEM` (já usado em outros
pontos do sistema pra essa exata finalidade — ex. ordenação do Plano de Ação — Crítico=4, Alto=3,
Moderado=2), ordenado em Python, não mais no template.

**Especificação de execução**:
1. **`relatorios/services/pdf.py::_rotulo`** (linha ~156-158) — remover o `"({codigo})"`, deixar só
   `nome` (mesmo padrão do resto do documento desde o item 6).
2. **`relatorios/services/pdf.py::_parecer_para_exibicao`** — cada achado ganha os números reais
   (determinísticos, não vêm da IA) além do que já tem: `"escore"`, `"percentual_elevados"`,
   `"prazo_dias"` — buscados do `EscoreDominio`/`ClassificacaoRisco` já carregados em `ghes`
   (mesmo dado que a Seção de Resultados usa, só precisa ser cruzado por `(ghe, dominio)` igual
   já é feito com `pareceres_por_chave`/`riscos_por_chave`). O campo `"o_que_fazer"` deixa de ser
   lido/incluído no dict de cada achado — não é mais usado por esta seção (a IA continua
   preenchendo `recomendacoes` no JSON bruto de `parecer_ia`, usado pelo Plano de Ação e por
   `plano_acao_ia.py`; só paramos de PUXAR esse campo pra dentro do achado exibido aqui).
   **Antes de retornar**, ordenar a lista `achados` por `BANDA_ORDEM.get(banda, 0)` decrescente
   (já importado em `pdf.py` — `from avaliacoes.services.calculo_risco import BANDA_ORDEM`) —
   Crítico primeiro, depois Alto, depois Moderado. Isso substitui o `dictsortreversed:"banda"` do
   template (ponto 4), que ordenava errado (alfabético, não por gravidade).
3. **`relatorios/services/analise_ia.py::SYSTEM_PROMPT`** — nova regra: os campos `parecer`
   (pareceres_por_dominio) e `justificativa` (riscos_prioritarios) devem ter **no máximo 1 frase
   curta cada**, linguagem simples e conclusiva (mesmo padrão "objetivo e fácil de ler" já pedido
   nos itens 14/15/17/18) — e nunca incluir sugestão de ação/medida nesses dois campos
   especificamente (a IA continua podendo detalhar a ação em `recomendacoes`, só não pode
   vazar isso pra dentro de `parecer`/`justificativa`).
4. **`relatorios/templates/relatorios/inventario.html`** (bloco de Achados, linhas 652-666) —
   trocar o `.ficha-acao` (tabela de 3 linhas) por um card no mesmo estilo `.linha-dominio` do
   item 18. A lista `parecer_exibicao.achados` já chega ordenada por gravidade do Python (ponto
   2 acima) — o template só itera, **sem** `dictsortreversed` nenhum:
   ```html
   {% for a in parecer_exibicao.achados %}
       <div class="linha-dominio">
           <div class="cabecalho-linha">
               <span class="nome">{% if parecer_exibicao.mostrar_ghe %}{{ a.ghe }} — {% endif %}{{ a.dominio_rotulo }}</span>
               <span class="escore">{{ a.escore }}<span class="unidade"> / 100</span></span>
           </div>
           <div class="acento-linha"></div>
           <p class="descricao-dominio">{{ a.o_que_foi_encontrado }}</p>
           <div class="rodape-linha">
               <span>{% widthratio a.percentual_elevados 1 100 %}% na faixa elevada{% if a.prazo_dias %} · prazo de {{ a.prazo_dias }} dias{% endif %}</span>
               <span class="badge {{ a.banda|slugify }}">{{ a.banda }}</span>
           </div>
       </div>
   {% endfor %}
   ```
   Sem "Por que é prioritário" nem "O que fazer" como linhas separadas — só o achado em si, o
   número, e o badge. Reaproveita 100% o CSS que o item 18 já cria (`.linha-dominio`,
   `.descricao-dominio`), nenhuma classe nova.
5. Gerar um parecer real via IA depois da mudança de prompt e conferir se os achados saem curtos
   e sem menção a ação/medida — se a IA ainda vazar recomendação pro campo errado, reforçar a
   regra do prompt (ponto 3) antes de considerar concluído.

**Status**: aguardando sua confirmação pra executar.

---

### 20. Eliminar "Cada fator, uma leitura" (Seção 5) — fundir com o Semáforo

**Pedido original**: depois dos itens 14/15/19, o usuário notou que "Cada fator, uma leitura"
(Seção 5 — lista com todo domínio, favorável e não-favorável) ficou redundante: o favorável já
aparece detalhado no Panorama (item 14) e o não-favorável já aparece detalhado nos Achados (item
19). O usuário confirmou que o Semáforo (Seção 6, "Onde está concentrada a carga") tem
prioridade — é a forma obrigatória de mostrar resultado por domínio neste projeto (decisão já
registrada antes) — e sugeriu fundir a Seção 5 nela em vez de manter as duas.

**Decisão tomada via pergunta ao usuário (2026-08-06)**: o número exato por domínio (escore, N,
%) continua aparecendo no documento — uma tabela compacta logo abaixo das barras do Semáforo,
não uma seção separada. Não vira só "barra visual sem número", pra manter rastreabilidade técnica
(auditoria NR-01 costuma pedir o número, não só a cor da barra).

**Diagnóstico de uma diferença de granularidade que precisa de tratamento explícito**: o Semáforo
(`avaliacoes/services/semaforo.py::calcular_semaforo`) agrega **por Unidade inteira** (todas as
Aplicações/GHEs somadas num cálculo só — decisão deliberada, CLAUDE.md Seção 6.9 Prompt 11), com
`linhas_semaforo` guardando só `n_respondentes`/percentuais/prioridade, **sem o escore 0-100 nem
a Banda por GHE**. Já a Seção 5 mostrava dado **por GHE** (um bloco por Aplicacao, com escore e
Banda daquele GHE especificamente — o mesmo padrão que Achados/Panorama usam quando há mais de 1
GHE no relatório). Fundir direto nos dados do Semáforo perderia a granularidade por GHE em
relatórios com mais de um GHE. A tabela compacta (decisão acima) usa a **mesma fonte de dado que
a Seção 5 já usava** (`ghes` → `item.dominios`, por GHE), não os agregados do Semáforo — as barras
continuam agregadas por Unidade (sem mudança), a tabela nova é por GHE, logo abaixo.

**Relação com o que já existe**: interage com os itens 16 e 18 desta fila:
- O card "Frentes de atenção" do Panorama (item 16) já tinha "conforme o prazo indicado na Seção
  5" — o item 16 já reescreve esse texto com um prazo real calculado, então essa referência já
  desaparece sozinha, sem precisar de ajuste extra aqui.
- O item 18 (redesenho da própria Seção 5) tinha um passo "adicionar N respondentes ao rodapé da
  `.linha-dominio`" — **isso fica sem efeito**, já que a Seção 5 deixa de existir. O N por domínio
  passa a aparecer na tabela compacta desta especificação, não mais na Seção 5. Atualizando o item
  18 abaixo pra remover essa instrução obsoleta.
- A caixa "Como ler o selo de Banda" + tabela "Critério de classificação da Banda" (que o item 18
  mantinha dentro da Seção 5, por decisão anterior do usuário) migram junto pra dentro do
  Semáforo — não desaparecem, só mudam de seção.

**Especificação de execução**:
1. **Remover a Seção 5 inteira** (`inventario.html`, bloco `<!-- 5. RESULTADOS POR GHE E POR
   DOMÍNIO -->`) — a caixa explicativa "Como ler o selo de Banda" e a tabela "Critério de
   classificação da Banda" **migram** (não são apagadas) pro início da Seção 6 (Semáforo), logo
   após a manchete/parágrafo introdutório, antes das barras.
2. **Seção 6 (Semáforo)** ganha, logo depois das barras/legenda que já existem, uma tabela
   compacta por GHE:
   ```html
   {% for item in ghes %}
   {% if ghes|length > 1 %}<h4>{{ item.ghe.nome }}</h4>{% endif %}
   <table class="zebra">
       <thead><tr><th>Domínio</th><th>Escore</th><th>N</th><th>% na faixa elevada</th><th>Banda</th><th>Prazo</th></tr></thead>
       <tbody>
       {% for d in item.dominios %}
           <tr>
               <td>{{ d.escore_dominio.dominio.nome }}</td>
               {% if d.escore_dominio.suprimido_por_confidencialidade %}
                   <td colspan="5">Suprimido por confidencialidade</td>
               {% else %}
                   <td>{{ d.escore_dominio.escore }}</td>
                   <td>{{ d.escore_dominio.n_respondentes }}</td>
                   <td>{% widthratio d.escore_dominio.percentual_elevados 1 100 %}%</td>
                   <td><span class="badge {{ d.banda_css }}">{{ d.classificacao_risco.banda }}</span></td>
                   <td>{{ d.classificacao_risco.prazo_dias_plano_de_acao|default:"—" }}{% if d.classificacao_risco.prazo_dias_plano_de_acao %} dias{% endif %}</td>
               {% endif %}
           </tr>
       {% endfor %}
       </tbody>
   </table>
   {% endfor %}
   ```
   Reaproveita a mesma fonte de dado (`ghes`) que a Seção 5 já usava — nenhum cálculo novo, só
   reposicionamento.
3. **Atualizar as auto-referências textuais** que ficam quebradas com a fusão
   (`inventario.html`, texto livre, não é cálculo):
   - Linha 505 (Panorama): "resultados detalhados por domínio, sempre no formato semáforo, estão
     na Seção 5" → atualizar pro número da seção do Semáforo depois da renumeração (ponto 5).
   - Linhas 754-755 (caixa explicativa do próprio Semáforo): "a mesma informação da Banda 'Alto'
     da Seção 5" / "sair como Crítico na Seção 5" → como a tabela de critério passa a estar na
     mesma seção agora, viram algo como "mostrada na tabela abaixo" em vez de apontar pra outra
     seção.
4. **Item 18 já foi reescrito** pra refletir essa fusão (glossário de domínios em vez de reformular
   a Seção 5 em cards) — nenhuma ação extra necessária aqui.
5. **Renumerar as seções seguintes** (Seção 4 Parecer, 6 Semáforo → 5, 7 Evidências → 6, e assim
   por diante) — os eyebrows `"0X ·"` de cada `.secao` precisam refletir a nova sequência.
6. Gerar um PDF real com mais de 1 GHE (pra conferir que a tabela compacta mantém a granularidade
   por GHE corretamente, diferente das barras que continuam agregadas por Unidade) e comparar.

**Status**: aguardando sua confirmação pra executar.

---

## Concluído

_(vazio por enquanto)_
