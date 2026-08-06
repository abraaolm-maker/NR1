# Plano de Ação — Reformulação do Relatório (Diagnóstico / Diagnóstico + Plano de Ação)

> Documento de trabalho criado em 2026-08-04. Registra o que foi decidido até aqui
> sobre a reformulação do relatório PDF do sistema, pra não perder nada entre
> sessões.
>
> **Atualização de 2026-08-05**: a Seção 2 (separação de tipos de relatório,
> Diagnóstico vs. Diagnóstico + Plano de Ação) foi **implementada** — ver
> CLAUDE.md Seção 6.18 para o detalhamento final de como ficou.
>
> **Atualização de 2026-08-05 (mesmo dia)**: as Seções 3 e 4 também foram
> **implementadas**, na parte que dava pra decidir sem abrir novas pendências —
> ver CLAUDE.md Seção 6.19. Ficaram de fora (Seção 5 abaixo continua valendo
> como pendência real): "Recortes" por setor/cargo, comparação de tendência
> entre ciclos, e a decisão definitiva de paleta (o laranja foi usado como
> acento pontual no Panorama, não substituiu o azul-marinho como cor
> principal).

---

## 1. Contexto e motivação

A proposta comercial do sistema vende **3 serviços separados**, com preços
diferentes (ver print analisado em 2026-08-04):

| Serviço | O que inclui | Preço |
|---|---|---|
| Aplicação | Questionário estruturado por grupos, aplicação online/presencial, consolidação dos dados | R$ 110,00 por colaborador |
| Diagnóstico | Análise dos 9 domínios, semáforo de risco, triangulação e relatório técnico assinado | incluído no valor por colaborador |
| Plano de Ação | Medidas priorizadas com responsáveis, prazos e metas, prontas pra compor o PGR | R$ 4.000,00 valor único |

**Problema atual**: o sistema só gera **um único PDF**, sempre com tudo junto
(diagnóstico + parecer técnico + plano de ação). Isso não reflete o que é vendido —
uma empresa que contratou só o Diagnóstico não deveria receber (nem pagar por) um
Plano de Ação despejado no mesmo documento.

**Pedido do usuário**: dois tipos de relatório devem poder ser gerados a partir do
mesmo ciclo de coleta:
1. **Só Diagnóstico** — sem Plano de Ação.
2. **Diagnóstico + Plano de Ação** — documento completo.

---

## 2. Ajustes técnicos necessários (arquitetura)

### 2.1 Modelo de dados
- `relatorios.models.Relatorio` ganha um campo `tipo` (`TextChoices`):
  - `DIAGNOSTICO = "diagnostico"`
  - `DIAGNOSTICO_PLANO_ACAO = "diagnostico_plano_acao"`
- Definido **na criação** do relatório, imutável depois (mesmo princípio já usado
  pro `CriterioVersao` — rastreabilidade, NR-01 exige que o documento não mude de
  natureza depois de gerado).
- Relatórios já existentes no banco recebem `tipo = diagnostico_plano_acao` por
  padrão (migration de dados) — preserva o comportamento atual pra quem já tem
  relatório gerado.
- Novo campo `planos_refinados_em` (DateTimeField, null=True) — registra quando
  `gerar_e_salvar_planos_refinados` rodou com sucesso pela última vez pra este
  relatório. Hoje esse registro não existe (só existe pro parecer, via
  `relatorio.parecer_ia` não-nulo); é necessário pra poder bloquear a geração do PDF
  sem essa etapa ter rodado.

### 2.2 Formulário de criação (`RelatorioForm`, `relatorio_create`)
- Novo campo obrigatório **"Tipo de relatório"**, com as duas opções acima,
  explicando em `help_text` a diferença (reflete o que foi vendido na proposta).

### 2.3 Template do PDF (`relatorios/templates/relatorios/inventario.html`)
- A seção de **Plano de Ação só entra quando `relatorio.tipo ==
  diagnostico_plano_acao`**.
- Numeração de seção deixa de ser fixa no HTML e passa a ser calculada
  dinamicamente (hoje é "1., 2., 3." escritos direto no template) — quando não há
  Plano de Ação, a Assinatura vira a seção anterior numericamente (ex.: 8 em vez de
  9), sem buraco na numeração.
- Estrutura de seções revista pra incorporar o padrão do relatório de referência
  (ver Seção 3 abaixo) — isso vale pros dois tipos de relatório, não só a divisão
  Diagnóstico/Plano.

### 2.4 Bloqueio no botão "Gerar PDF" (`relatorio_gerar_pdf`, `pdf.py::gerar_pdf_relatorio`)
Validação **no servidor** (nunca só escondendo o botão na tela — senão dá pra
contornar acessando a URL direto):
- Tipo `diagnostico`: exige que `relatorio.parecer_ia` já exista (parecer via IA
  gerado pelo menos uma vez).
- Tipo `diagnostico_plano_acao`: exige **os dois** — parecer via IA gerado **e**
  `planos_refinados_em` preenchido (plano de ação refinado via IA já rodou pelo
  menos uma vez).
- Se a validação falhar, a view devolve mensagem de erro clara (mesmo padrão já
  usado nas outras validações do painel), nunca um 500.

### 2.5 Tela do relatório (`relatorio_detail.html`)
- O botão "Gerar PDF"/"Baixar PDF" fica **desabilitado** com texto explicando o que
  falta ("Gere o parecer técnico antes de gerar o PDF" / "Gere o parecer e refine o
  plano de ação antes de gerar o PDF final, conforme o tipo deste relatório"),
  seguindo o mesmo padrão visual do stepper que já existe pra etapa de assinatura.

---

## 3. Referência visual e de conteúdo — Relatório 1 (Solute RH)

> Analisado em 2026-08-04 (arquivos `Diagnostico_Psicossocial_Modelo_Solute.pdf` e
> `.md`, fornecidos pelo usuário). **Aguardando o Relatório 2** antes de fechar a
> versão definitiva desta seção — o que segue é o que já foi validado como "quero
> isso" a partir do primeiro exemplo.

### 3.1 O que o usuário disse explicitamente que gostou
- A forma como o relatório **"fala com o leitor"**: títulos e textos diretos,
  quase conversacionais ("O que os dados dizem.", "Base técnica e protocolo de
  leitura.", "Onde está concentrada a carga.", "O que fazer com isso.").
- O uso de **cor de destaque** (laranja, no caso deles) em palavras-chave dentro
  da manchete de cada seção.
- Os **quadros/cards** de indicador (número grande + rótulo pequeno).
- Os **recortes** (cortes de leitura: por unidade, por setor, por cargo).
- A estrutura de 6 blocos: Panorama → Como foi feito → Resultados → Recortes →
  Recomendações → Considerações finais.

### 3.2 Ressalva explícita e inegociável do usuário
> "O relatório da Solute usa em 'Oito dimensões, uma leitura' a apresentação
> própria deles [uma lista ranqueada dos fatores, do mais ao menos intenso]. Quero
> manter minha apresentação usando **semáforo**, ela é imutável e inegociável."

Ou seja: a estrutura de conteúdo e o estilo de escrita/visual da Solute servem de
inspiração, mas a **forma de apresentar os resultados por domínio continua sendo o
semáforo** (gráfico de barras empilhadas verde/amarelo/vermelho por domínio, Seção
6.9 Prompt 11 do CLAUDE.md), nunca uma lista ranqueada de "N dimensões, uma
leitura" no estilo deles.

### 3.3 Mapeamento de seções (Solute → nosso sistema)

| Solute | Nosso sistema (proposto) | Presente em |
|---|---|---|
| 01 · Panorama — "O que os dados dizem." | **Panorama** — resumo executivo: índice consolidado, N participantes, nível geral de risco, frentes de atenção | Diagnóstico e Diagnóstico+Plano |
| 02 · Como foi feito — "Base técnica e protocolo de leitura." | **Base técnica e metodologia** — funde as atuais Seções "Base técnica" e "Metodologia" num único bloco com esse tom | Diagnóstico e Diagnóstico+Plano |
| 03 · Resultados — "Oito dimensões, uma leitura." | **Resultados por domínio** — mantém o **semáforo** (não a lista ranqueada deles) | Diagnóstico e Diagnóstico+Plano |
| 04 · Recortes — "Onde está concentrada a carga." | **Recortes** (por GHE/setor/cargo) — feature nova, ver pendência 4.3 | Diagnóstico e Diagnóstico+Plano |
| 05 · Recomendações — "O que fazer com isso." | **Plano de ação** | **Só** Diagnóstico+Plano |
| 06 · Considerações finais — "Próximo ciclo." | **Considerações finais** — reaplicação, conformidade NR-01, sigilo | Diagnóstico e Diagnóstico+Plano |

### 3.4 Elementos visuais específicos a incorporar

> **Atualização de 2026-08-05 (auditoria pós-implementação)**: a primeira rodada
> (CLAUDE.md Seção 6.19) implementou só os 2 primeiros itens abaixo (eyebrow +
> manchete, e os cards/colunas — mas só dentro da Seção 1 Panorama). O usuário
> comparou o PDF real gerado com o PDF da Solute lado a lado e apontou,
> corretamente: **da Seção 2 em diante o documento continua com a cara antiga**
> — tabelas com grade cinza cheia de bordas, sem o respiro/whitespace da
> Solute, sem cor de destaque em lugar nenhum fora do Panorama, capa sem
> nenhum elemento visual (barra lateral, marca), rodapé sem selo de
> confidencialidade. Isso é uma lacuna real de execução, não uma limitação
> técnica — fica detalhado no plano faseado abaixo (Seção 3.5), que é o que
> falta pra realmente fechar o que este documento pede desde o início.

- Rótulo pequeno maiúsculo com letter-spacing antes da manchete de cada seção
  (ex.: "01 · PANORAMA"), seguido de manchete grande em negrito com 1-2 palavras
  destacadas na cor de acento. **[Feito em todas as seções, 2026-08-05]**
- Cards de indicador: número grande + rótulo pequeno abaixo + selo/legenda de
  leitura (ex.: "Faixa favorável", "Alta confiabilidade"). **[Feito só na Seção 1]**
- Cartão de destaque (fundo escuro no exemplo da Solute) para o número de
  "frentes de atenção". **[Feito só na Seção 1]**
- Duas colunas "O que está protegendo" / "O que pede ação". **[Feito só na
  Seção 1 — o resto do documento nunca teve essa leitura]**
- Badges coloridos de faixa. **[Já existiam antes deste ciclo, sem mudança]**
- Cabeçalho/rodapé com nome do sistema, empresa, número de página e selo de
  confidencialidade. **[NÃO feito — rodapé continua só "Página N de M"]**
- Capa com barra de acento lateral e marca quadrada tipo "S" da Solute. **[NÃO
  feito — capa continua só texto centralizado, sem nenhum elemento gráfico]**
- Tabelas densas convertidas em listas/cards sem grade completa (a Solute não
  usa NENHUMA tabela com borda visível em lugar nenhum do documento — tudo é
  card, lista com marcador, ou texto corrido). **[NÃO feito — todas as tabelas
  do sistema (Metodologia, Parecer por domínio, Resultados por GHE, Riscos
  prioritários) continuam com grade cinza completa, exatamente como antes]**

### 3.5 Plano faseado para fechar a lacuna (não implementado — aguardando aprovação)

> Only a genuine redesign closes this gap — trocar só os cabeçalhos (o que já
> foi feito) não é suficiente porque a Solute nunca usa tabela com grade em
> nenhuma página; o "peso visual" do documento inteiro vem de whitespace,
> cards e listas, não de texto+régua. Um clone pixel a pixel não é viável (o
> exemplo da Solute tem 8 dimensões; nosso COPSOQ Oficial tem até 26) — mas o
> *sistema visual* (cor, espaçamento, tipografia, componentes) dá pra replicar
> em qualquer densidade de dado, inclusive nas tabelas de 26 linhas.

**Fase A — Fundação do sistema visual (CSS, sem mudar conteúdo/estrutura)**
- Paleta definitiva: `#2b3a55` (azul-marinho, cor primária — títulos, bordas,
  ícones) + `#c76b1f` (laranja, SÓ para destaque pontual — palavra-chave em
  manchete, barra lateral de card, nunca fundo nem texto corrido).
- Escala tipográfica única (eyebrow 9.5px caps letter-spaced / manchete 19-22px
  bold / corpo 10.5-11px / rótulo de card 9px) aplicada em todo o documento,
  não só no Panorama.
- Componente "card" reutilizável (fundo levemente cinza, borda 1px suave,
  cantos arredondados, sem sombra pesada — WeasyPrint suporta `border-radius`)
  para substituir tabela onde fizer sentido.
- Selo "CONFIDENCIAL" + nome do documento no rodapé de toda página (hoje só
  tem número de página).

**Fase B — Capa**
- Barra de acento lateral (navy, largura ~8px, borda esquerda da página) e uma
  marca quadrada simples com iniciais do sistema (equivalente ao "S" da
  Solute) — não precisa ser um logo desenhado, só um quadrado com iniciais em
  fonte bold, mesmo espírito.

**Fase C — Conversão de tabelas densas em cards/listas onde o dado permite**
- "Parecer por domínio" (Seção 4): de tabela de 5 colunas × 26 linhas para uma
  lista de mini-cards (1 por domínio fora de Aceitável — os Aceitáveis ficam
  só na lista "protegendo" do Panorama, sem repetir parecer individual deles,
  reduzindo de 26 blocos pra só os ~9 que importam).
- "Riscos prioritários e recomendações": já é conceitualmente um card por
  domínio (Domínio/Banda/Por quê/Medida) — só precisa perder a borda de
  tabela e virar cards empilhados, como o Plano de Ação já faz.
- "Instrumentos por GHE" e "Variante do questionário" (Metodologia): tabelas
  de 1-2 linhas viram texto corrido ("Este ciclo usou o COPSOQ oficial, versão
  curta, aplicado de forma anônima ao GHE Escritório") — tabela é desperdício
  de espaço pra 1 linha de dado.
- "Resultados por GHE e por domínio" (Seção 5) e a tabela "N respondentes por
  domínio" (Metodologia): são genuinamente tabulares (26 linhas × várias
  colunas numéricas) — aqui a Solute não tem equivalente direto (só 8
  dimensões). Decisão proposta: manter como tabela, mas remover a grade cinza
  completa (`border: 1px solid #ccc` em toda célula) e usar só linha divisória
  horizontal fina + fundo alternado sutil (zebra), no mesmo espírito "sem
  grade pesada" da Solute.

**Fase D — Correção de um bug real encontrado nesta auditoria**
- A síntese executiva gerada por IA (Seção 4, Parecer técnico) **erra a
  contagem dos próprios dados**: no relatório revisado, ela diz "Dos 25
  domínios avaliados, 4 apresentaram banda Alto" — mas a Aplicação tem **26**
  domínios (confirmado na tabela da Metodologia) e só **3** estão em banda
  Alto (EC, CLT, IL — confirmado na Seção 5 e no Panorama, que mostra 9
  frentes de atenção = 3 Alto + 6 Moderado, batendo com a tabela real). A IA
  não tem acesso a "achar" esses números — ela SÓ deveria repetir o que já
  veio pronto no payload (`montar_payload_relatorio`), mas erra a soma/
  contagem em texto livre. Isso é uma falha de confiabilidade factual num
  documento que promete "a IA nunca decide, só interpreta números já prontos"
  (CLAUDE.md Seção 8.1) — se ela erra a contagem na síntese, quebra essa
  promessa na prática, mesmo sem alterar a Banda/classificação em si (que
  continuam corretas, calculadas pelo backend). Correção proposta: computar as
  contagens (nº de domínios avaliados, nº por banda) no backend e **injetar
  esses números prontos no payload enviado à IA**, com instrução explícita de
  reusar os valores literalmente na síntese em vez de tentar somar sozinha.

**Fase E — O que continua fora de escopo** (inalterado desde a Seção 5 abaixo):
Recortes por setor/cargo, tendência entre ciclos, fórmula alternativa de
índice consolidado.

> **Atualização de 2026-08-05 (mesmo dia)**: Fases A, B, C e D **implementadas**
> — ver CLAUDE.md Seção 6.20 para o detalhamento final. Fase E permanece
> pendente (inalterada).

---

## 3.6 Terceira auditoria: por que ainda parece distante da Solute (2026-08-05)

> O usuário comparou de novo o PDF gerado (`relatorio teste.pdf`, 19 páginas)
> com o `Diagnostico_Psicossocial_Modelo_Solute.pdf` (6 páginas) e disse que
> ainda sente "uma distância muito grande". Também apontou um bug concreto:
> tópicos duplicados no cabeçalho de seção. Esta auditoria identifica **por
> que** a distância persiste mesmo depois das Fases A a D.

**A conclusão central**: as Fases A a D consertaram o *estilo* (cor, borda,
tipografia, componentes). O que ainda separa os dois documentos não é estilo,
é **densidade, ritmo de página e voz**. A Solute é um documento que se lê em
6 fôlegos; o nosso é um anexo técnico contínuo de 19 páginas. Nenhum ajuste
de CSS resolve isso sozinho, porque o problema está em como o conteúdo é
distribuído e quanto dele existe.

### 3.6.1 Bug confirmado: cabeçalho duplicado

Na Solute, o eyebrow é o **nome curto da seção** e a manchete é uma **frase
conversacional diferente**, sempre terminada em ponto. Nunca as mesmas
palavras. No nosso, 4 das 10 seções repetem o mesmo texto duas vezes:

| Seção | Eyebrow atual | Manchete atual | Problema |
|---|---|---|---|
| 02 | BASE TÉCNICA | Base técnica e legal utilizada | duplicado |
| 05 | RESULTADOS | Resultados por GHE e por domínio | duplicado |
| 07 | EVIDÊNCIAS COMPLEMENTARES | Evidências complementares | duplicado |
| 08 | ENTREVISTA E OBSERVAÇÃO | Entrevista e observação | duplicado |
| 10 | PRÓXIMO CICLO | Assinatura do responsável técnico | incoerente (eyebrow não descreve o conteúdo) |

### 3.6.2 As sete diferenças estruturais restantes

1. **Ritmo de página.** A Solute quebra página a cada seção: 6 seções, 6
   páginas. O nosso é fluxo contínuo, então uma seção começa no meio da
   página, logo abaixo do fim da anterior, e parágrafos são cortados na
   virada (a frase "sobre os resultados encontrados" termina na página 3
   começando com a palavra "encontrados", órfã). Isso é o que mais faz o
   documento parecer denso e desorganizado.
2. **Densidade de texto.** A Solute usa cerca de metade da página em branco.
   O nosso preenche de margem a margem. Mesmo com o mesmo CSS, um bloco de
   texto de 8 linhas corridas lê diferente de 3 linhas com respiro.
3. **Escala tipográfica.** A manchete da Solute é aproximadamente o dobro do
   tamanho da nossa, e o contraste entre título e corpo é muito maior. Nossa
   manchete de 19px compete com o corpo de 11px; a deles domina a página.
4. **Plano de Ação como despejo de banco de dados.** Cada ficha tem 12 linhas
   rótulo/valor, e 9 fichas ocupam 9 das 19 páginas. Metade do documento é
   uma tabela vertical repetida. A Solute agrupa recomendações em 3 blocos
   por horizonte de execução (curto, médio, longo), com 3 bullets cada,
   cabendo tudo em 1 página.
5. **Caixas explicativas gigantes.** "COMO LER A COLUNA BANDA" tem 12 linhas
   de texto corrido dentro de uma caixa. Os callouts da Solute têm 2 a 3
   linhas. Uma caixa que ocupa um terço da página deixa de ser um destaque e
   vira mais um bloco de leitura obrigatória.
6. **Voz dos títulos.** Nossos títulos ainda são rótulos técnicos
   ("Metodologia", "Evidências complementares", "Análise semáforo"). Os da
   Solute falam com o leitor ("Base técnica e protocolo de leitura.", "Onde
   está concentrada a carga.", "O que fazer com isso."). Já fizemos isso em
   2 seções (Panorama e Parecer), falta nas outras 8.
7. **Capa.** A Solute tem manchete grande com ponto final, um parágrafo
   descrevendo o que é o documento, e os metadados numa linha horizontal com
   rótulo pequeno acima do valor ("Emissão · maio de 2026 | Ciclo · 2026.1 |
   Participação · 142 colaboradores"). A nossa é uma pilha vertical de 5
   linhas do mesmo tamanho, sem hierarquia.

### 3.6.3 Redundância de conteúdo (fora do visual)

"Pareceres por domínio" e "Riscos prioritários e recomendações" dizem
praticamente a mesma coisa para os mesmos 9 domínios, em sequência, com
textos parecidos. São 2 páginas do documento repetindo informação. A Solute
nunca repete: cada dado aparece uma vez, no lugar onde é mais útil.

### 3.6.4 Plano de execução (6 fases)

**Fase 1 — Cabeçalhos: eliminar duplicação e ajustar a voz**
Tabela definitiva de eyebrow/manchete, no padrão Solute (eyebrow = categoria
curta, manchete = frase com ponto final, nunca repetindo as mesmas palavras):

| Nº | Eyebrow | Manchete |
|---|---|---|
| 01 | PANORAMA | O que os **dados** dizem. |
| 02 | COMO FOI FEITO | Base técnica e protocolo de **leitura**. |
| 03 | COMO FOI FEITO | A **coleta**, passo a passo. |
| 04 | PARECER TÉCNICO | O que a análise técnica **aponta**. |
| 05 | RESULTADOS | Cada fator, uma **leitura**. |
| 06 | DISTRIBUIÇÃO | Onde está concentrada a **carga**. |
| 07 | TRIANGULAÇÃO | O que as outras **fontes** mostram. |
| 08 | O QUE FAZER | Do diagnóstico à **ação**. |
| 09 | ENCERRAMENTO | **Próximo** ciclo. |

**Fase 2 — Ritmo de página (maior impacto isolado)**
`page-break-before: always` em cada `.secao`, para que toda seção comece numa
página limpa, exatamente como a Solute. Margem superior maior (3cm) para dar
o respiro característico do topo da página deles. Nenhum parágrafo órfão na
virada.

**Fase 3 — Escala tipográfica e respiro**
Manchete sobe de 19px para 30px. Corpo ganha `line-height: 1.65` e
`max-width` de coluna (nunca texto de margem a margem em bloco corrido).
Espaço entre blocos aumenta de 10px para 18px. Caixas explicativas reduzidas
a no máximo 4 linhas, com o texto longo virando nota de rodapé pequena.

**Fase 4 — Plano de Ação reformatado por horizonte**
Substituir as 9 fichas de 12 linhas por 3 blocos agrupados por prazo (30
dias, 90 dias, sem prazo), cada bloco com uma lista compacta de medidas
(código, domínio, banda, medida em 2 a 3 linhas). Os campos operacionais
(responsável, status, evidência de execução, verificação de eficácia, data
de revisão, observações) viram **uma tabela única de acompanhamento** no fim
da seção, com uma linha por ação, em vez de 12 linhas repetidas por ficha.
Estimativa: de 9 páginas para 2.

**Fase 5 — Eliminar a redundância parecer/riscos**
Fundir "Pareceres por domínio" e "Riscos prioritários e recomendações" numa
única lista por domínio, com 3 campos (o que foi encontrado, por que é
prioritário, o que fazer). Elimina cerca de 2 páginas de repetição.

**Fase 6 — Capa no padrão Solute**
Manchete grande com ponto final, parágrafo curto explicando o que é o
documento, e metadados numa linha horizontal com rótulo pequeno em maiúsculas
acima do valor. Selo CONFIDENCIAL destacado no rodapé da capa.

**Resultado esperado**: de 19 páginas densas e contínuas para algo entre 10 e
12 páginas com ritmo de leitura, seção por página, sem repetição — mantendo
todo o conteúdo técnico exigido pela NR-01 e o semáforo como forma única de
apresentar resultado por domínio (ressalva inegociável, Seção 3.2).

> **Atualização de 2026-08-05 (mesmo dia)**: as 6 fases foram **implementadas**
> — ver CLAUDE.md Seção 6.21 para o detalhamento final de como ficou cada uma.

---

## 3.7 Plano de migração do motor de renderização: WeasyPrint → Chromium (2026-08-05)

> Depois de 5 rodadas de auditoria visual (Seções 3.5, 3.6 e as 2 seguintes,
> "4ª" e "5ª auditoria" registradas no CLAUDE.md 6.20-6.23), o usuário
> perguntou diretamente qual biblioteca gera o PDF hoje e se ela é o teto do
> problema. Resposta: sim. **Este documento é o plano de migração + a
> especificação visual completa extraída página a página do PDF de
> referência (Solute RH), pronta pra implementar — nada disto foi
> implementado ainda.**

### 3.7.1 Por que o WeasyPrint é o teto

O WeasyPrint converte HTML/CSS pra PDF **sem motor de navegador** — ele
implementa um subconjunto próprio de CSS2.1/CSS3. Isso explica, com precisão
técnica, cada rodada de ajuste que não fechou de vez:

- `@page` margin boxes (o masthead) têm suporte incompleto: não herdam
  `font-family` do body (bug real corrigido na Seção 6.23), e `string-set`/
  `content: string()` funcionam mas de forma frágil.
- Sombras, gradientes, `border-radius` combinados com `overflow` e efeitos
  de profundidade têm suporte parcial — a "textura" premium da referência
  (blob de gradiente na capa, sombras suaves nos cards) não é replicável com
  confiança.
- Tipografia sem os recursos completos de OpenType (kerning fino,
  hinting) — mesmo corrigindo o tamanho em pt (Seção 6.23), a "qualidade de
  type" nunca fica idêntica à de um navegador real.
- Sem JavaScript, sem reflow computado — qualquer coisa que dependa de medir
  texto dinamicamente não existe.

O PDF de referência tem características (gradiente decorativo na capa,
kerning fino, sombras/cards com acabamento consistente, cabeçalho que muda
de texto por página com precisão) típicas de renderização por **motor de
navegador real** (Chromium), não por um conversor HTML→PDF simplificado.

### 3.7.2 Duas opções de migração

**Opção A — Playwright + Chromium `page.pdf()` puro.**
Renderiza o HTML/CSS com o motor completo do Chrome (CSS moderno, fontes com
kerning real, sombras, gradientes). Limitação real: a API `page.pdf()` do
Chrome só aceita `headerTemplate`/`footerTemplate` **estáticos** (mesmo HTML
em toda página) — não existe equivalente ao `string-set` do CSS Paged Media
pra mostrar "em que seção estou" mudando por página automaticamente. Pra
replicar o masthead dinâmico da referência (que muda de "PANORAMA GERAL" pra
"METODOLOGIA" pra "RESULTADOS POR DIMENSÃO" em cada página), seria preciso
renderizar cada seção como um PDF separado (1 chamada de `page.pdf()` por
seção, cada uma com seu próprio `headerTemplate`) e depois juntar os PDFs
com `pypdf`/`pikepdf` — funciona, mas é mais complexo de manter.

**Opção B — Playwright/Puppeteer + Paged.js (recomendada).**
[Paged.js](https://pagedjs.org/) é um polyfill JavaScript de CSS Paged Media
que roda **dentro de um navegador real** (Chromium via Puppeteer/Playwright)
e implementa `string-set`, `content: string()`, contadores de página,
`@page` completo — exatamente os recursos que o WeasyPrint tenta oferecer,
só que com o motor de renderização certo por trás. Isso resolve os dois
problemas ao mesmo tempo: (1) qualidade visual de motor de navegador real
(fontes, sombras, gradientes, CSS moderno) e (2) masthead dinâmico por
seção, exatamente como a referência faz, sem precisar quebrar o documento em
PDFs separados. É o padrão de facto pra ferramentas de "book/relatório de
qualidade editorial gerado a partir de HTML" — mesma categoria de problema
que este projeto tem.

**Decisão proposta**: Opção B (Paged.js sobre Chromium). Opção A fica como
plano B se a integração do Paged.js se mostrar complexa demais no ambiente
Docker do projeto.

### 3.7.3 Impacto técnico da migração

- **Dependência nova**: `playwright` (Python) + binário do Chromium
  (`playwright install chromium --with-deps`) — ou `pyppeteer` como
  alternativa mais leve. Paged.js entra como um script JS servido/injetado
  na página antes de imprimir (via CDN local ou `staticfiles`).
- **Dockerfile**: imagem cresce ~300-500MB pelo Chromium; precisa garantir
  as dependências de sistema do Chromium headless (`--with-deps` cobre isso
  em base Debian/Ubuntu, que já é o caso deste projeto).
- **`relatorios/services/pdf.py`**: a função que hoje faz
  `HTML(string=html).write_pdf()` (WeasyPrint) é substituída por uma função
  que abre uma página Chromium, injeta o HTML + Paged.js, espera a
  paginação terminar (`window.PagedPolyfill` expõe um evento de conclusão),
  e chama `page.pdf()`. Mantém a mesma assinatura (`renderizar_html_relatorio`
  continua devolvendo o HTML; só `gerar_pdf_relatorio` muda o motor por
  baixo) — nenhuma mudança na Django view nem no fluxo de geração síncrona
  já decidido (CLAUDE.md, sem Celery).
- **CSS do template**: a sintaxe de `@page`/`string-set` já escrita
  continua válida (é justamente o que o Paged.js interpreta) — não precisa
  reescrever do zero, só validar contra o polyfill e ajustar onde ele
  diverge do WeasyPrint.
- **Latência**: abrir um Chromium headless por PDF gerado é mais lento que
  o WeasyPrint (alguns segundos a mais). Aceitável dado que a geração já é
  síncrona e o usuário já espera pela chamada de IA no mesmo fluxo.
- **Testes**: os testes que hoje checam `conteudo.startswith(b"%PDF")`
  continuam funcionando sem alteração — só o motor por trás muda.

### 3.7.4 Especificação visual extraída da referência (página a página)

> Leitura minuciosa do PDF da Solute, com posição, cor, estrutura e padrão
> de cada elemento — pronta pra guiar a implementação quando a migração
> acontecer.

**Capa**
- Barra vertical laranja sólida (`#F47B20`) ocupando toda a lateral esquerda
  da página (~1,2cm de largura) — elemento que a versão atual não tem (só
  uma barra horizontal curta abaixo do título).
- Marca quadrada "S" (laranja, canto arredondado ~4px, letra branca bold)
  no canto superior esquerdo do conteúdo, ao lado do nome da consultoria em
  caps + subtítulo cinza pequeno abaixo.
- Blob decorativo de gradiente laranja suave no canto superior direito —
  puramente decorativo, prioridade baixa.
- Eyebrow laranja caps com letter-spacing, linha fina abaixo.
- Título grande preto bold em 3 linhas, altamente compacto (~40pt).
- Parágrafo de descrição cinza.
- "Preparado para [Cliente]" em negrito.
- Bloco de metadados (Emissão/Ciclo/Participação) como pares rótulo/valor
  pequenos, canto inferior esquerdo.
- Selo "CONFIDENCIAL" como **contorno** laranja (borda laranja, texto
  laranja, sem preenchimento) — a versão atual não tem esse selo na capa.

**Masthead (todas as páginas internas)**
- Esquerda: bullet laranja + "SOLUTE CONSULTORIA" (nome da consultoria, não
  o nome do documento) em caps pequeno.
- Direita: **nome da seção atual**, mudando por página ("PANORAMA GERAL",
  "METODOLOGIA", "RESULTADOS POR DIMENSÃO", "LEITURA POR ÁREA", "PLANO DE
  AÇÃO", "ENCERRAMENTO") — já implementado via `string-set` no sistema
  atual, só precisa sobreviver à migração de motor.
- Linha fina horizontal abaixo dos dois.
- Rodapé: "Solute RH · Diagnóstico Psicossocial · Modelo" à esquerda + nº de
  página à direita, linha fina acima.

**Padrão de cabeçalho de seção** (confirma o padrão já adotado): eyebrow
"0N · NOME CURTO" em laranja caps, manchete grande preta com 1 trecho em
laranja, parágrafo de contexto logo abaixo. Já implementado — manter.

**Panorama**
- 4 cards de métrica em linha, **sem caixa/borda ao redor** — só uma linha
  de acento laranja curta (~30px) logo abaixo do número grande, depois
  rótulo cinza caps, depois uma legenda **em laranja** (não um badge/chip —
  é texto colorido simples: "Faixa favorável", "Alta confiabilidade",
  "Modelo Karasek + Siegrist", "Manter monitoramento"). A versão atual usa
  cards com borda/fundo cinza claro — a referência é mais limpa/plana.
- Cartão de destaque ("3 Frentes de atenção"): fundo **quase preto**
  (não azul-marinho como o sistema atual usa) — `#1a1a1a` ou muito próximo,
  número grande, texto branco com trechos em negrito branco (não laranja)
  dentro do parágrafo.
- Duas colunas "O que está protegendo" / "O que pede ação": marcador é um
  **traço/en-dash laranja** ("−"), não bullet redondo — cada item é
  "**Frase-chave em negrito** — descrição em texto normal".

**Metodologia (Base técnica)**
- 3 cards de processo em linha ("01 · Coleta", "02 · Mensuração",
  "03 · Classificação"), cada um com uma linha fina laranja no topo do
  card, subtítulo em negrito, descrição pequena.
- Lista "Referências teóricas" com marcador traço laranja, "**Termo em
  negrito** — explicação".
- Tabela "Faixas de interpretação": cabeçalho caps cinza pequeno, linha
  fina inferior, a coluna "Faixa" mostra **texto colorido sem chip**
  (verde "Favorável", laranja "Atenção", vermelho "Crítico") — mesma
  filosofia "pálida"/sem preenchimento sólido já adotada pro `.badge-suave`
  do sistema atual, mas aqui é até mais minimalista (nem tem fundo tint,
  só o texto colorido).
- Caixa "Sobre confidencialidade": fundo laranja bem pálido, borda esquerda
  laranja — já é exatamente o padrão de `.caixa-explicativa` do sistema
  atual.

**Resultados por dimensão**
- **Lista, não tabela em grade** — cada domínio é uma linha com: título em
  negrito + escore alinhado à direita na mesma linha; linha fina laranja
  curta (decorativa, não proporcional ao escore) abaixo do título;
  descrição pequena cinza à esquerda e badge de faixa (chip verde pálido)
  à direita, na mesma linha; linha divisória fina horizontal separando
  cada domínio. É um padrão mais "lista de leitura" que "tabela de dados" —
  mais aplicável quando há poucos domínios (8, no caso da Solute); pra
  este sistema, com até 26-35 domínios (COPSOQ Oficial), continua fazendo
  sentido manter a tabela genuinamente tabular pros domínios completos
  (decisão já registrada na Seção 3.5) — mas os poucos domínios fora de
  Aceitável no Parecer técnico (que já viraram cards) podem adotar esse
  estilo de "linha com escore alinhado à direita" em vez do formato atual
  de card com sub-tabela interna.

**Recortes** — feature ainda não implementada neste sistema (pendência já
registrada na Seção 5, item 2) — tabelas simples por corte, texto colorido
sem chip pra faixa, caixa de síntese no mesmo padrão de `.caixa-explicativa`.

**Plano de ação**
- Layout de **2 colunas por horizonte**: coluna esquerda estreita com o
  rótulo do horizonte + prazo ("CURTO" / "0–90 dias"), coluna direita com
  subtítulo em negrito + lista de bullets (traço laranja). O sistema atual
  já agrupa por horizonte (Fase 4, Seção 3.6) mas empilha tudo numa coluna
  só com `<h3>` — ajuste de layout, não de conteúdo.
- Caixa "Recomendação central": mesmo padrão pálido/borda esquerda, com
  trecho em negrito embutido no meio do parágrafo.

**Encerramento**
- "O que esperar da reaplicação" e "Conformidade" em sequência (já
  implementado, Seção 6.22 item 2).
- Bloco de assinatura em **2 colunas lado a lado** ("Responsável técnico" /
  "Aprovação interna") quando há duas partes assinando — o sistema atual
  tem só 1 assinante (o profissional responsável do SaaS, CLAUDE.md Seção
  6.8) então o layout de 1 coluna alinhada à esquerda (já corrigido na
  Seção 6.22 item 4) continua correto pro nosso caso de uso; a referência
  usa 2 colunas porque o fluxo deles inclui aprovação do cliente também —
  não é uma incompatibilidade, é um fluxo de assinatura diferente.

### 3.7.5 Cores e tipografia — valores finais a adotar

| Token | Valor atual do sistema | Valor da referência | Ação |
|---|---|---|---|
| Acento laranja | `#F47B20` | `#F47B20` | Já corrigido (Seção 6.23) — manter |
| Texto de título (manchete) | `#1a1a1a` | preto quase puro | Já corrigido (Seção 6.23) — manter |
| Fundo do cartão de destaque | `#2b3a55` (navy) | quase preto (`~#1a1a1a`) | **Trocar** — é a divergência de cor mais visível ainda pendente |
| Badge de faixa (informativo) | `.badge-suave` (tint leve + texto colorido) | texto colorido, praticamente sem tint de fundo | Já próximo (Seção 6.23) — ajuste fino opcional |
| Fonte | DejaVu Sans (via WeasyPrint) | Liberation Sans (via Chromium) | Resolvido automaticamente pela migração de motor |

### 3.7.6 Ordem de execução recomendada

1. Configurar Playwright + Chromium no ambiente de desenvolvimento local e
   confirmar que `manage.py` consegue chamar `page.pdf()` num template de
   teste simples.
2. Integrar Paged.js (script servido localmente, sem dependência de CDN
   externo em produção) e confirmar que `string-set`/`content: string()`
   funcionam no polyfill com o template atual, sem reescrever o HTML.
3. Trocar o motor dentro de `relatorios/services/pdf.py`
   (`gerar_pdf_relatorio`), mantendo a mesma assinatura de função.
4. Atualizar o `Dockerfile` (instalar Chromium + dependências) e testar a
   geração dentro do container antes de subir ao VPS.
5. Só depois de confirmada a migração funcionando, aplicar os ajustes
   visuais da Seção 3.7.4 (barra lateral da capa, cartão de destaque em
   preto, layout de 2 colunas no Plano de Ação, listas com traço laranja
   em vez de bullet redondo) — pra não misturar "trocar o motor" com
   "ajustar o CSS" no mesmo commit e dificultar isolar qualquer regressão.

> **Atualização de 2026-08-05 (mesmo dia)**: a migração de motor (Seções
> 3.7.1 a 3.7.3, Etapas 1 a 4 da ordem de execução) foi **implementada e
> validada com um relatório real** — ver CLAUDE.md Seção 6.24. A
> especificação visual da Seção 3.7.4/3.7.5 (Etapa 5 — capa com barra
> lateral, cartão de destaque em preto, marcadores em traço, layout de
> 2 colunas no Plano de Ação) continua pendente, de propósito: a migração
> de motor foi isolada num commit próprio pra não misturar com ajuste de
> CSS, exatamente como o plano recomendava.

> **Atualização de 2026-08-05 (rodada seguinte, mesmo dia)**: um relatório
> real de 13 páginas revelou uma regressão crítica na migração (Seção de
> Encerramento sumindo + contador "Página X de 0") — causa raiz e correção
> documentadas em CLAUDE.md Seção 6.25. Corrigida a regressão, a Etapa 5
> (ajustes visuais listados acima) foi **implementada e validada** no mesmo
> lote, junto com o redesenho da Seção 5 (Resultados) pedido pelo usuário
> (tabela por GHE removida, substituída por lista de leitura no formato da
> referência) e a correção do acento de título em "Cada fator, uma leitura."
> — ver CLAUDE.md Seção 6.25 para o detalhamento completo.

---

## 4. Referência visual e de conteúdo — Relatório 2 (Hospital São Lucas, "COPSOQ-inspired")

> Analisado em 2026-08-04 (`RelatriodeAvaliaodeRiscosPsicossociais.md`, 42 páginas,
> só a versão `.md` foi enviada — o usuário disse explicitamente "não sei muito o
> que usar dele, é seu trabalho ver coisas boas". Relatório de um framework
> autoral (não é o nosso sistema), muito mais denso e estatístico que o da Solute:
> além do resumo executivo, tem múltiplos recortes cruzados, heatmap completo,
> mapa de hotspots, análise de equidade/gap, matriz de risco 5×5 e um apêndice de
> integridade.

### 4.1 O que vale a pena aproveitar

1. **Múltiplos recortes organizacionais, não só um**: o relatório segmenta os
   mesmos 8 domínios por Unidade, Setor, Cargo, Diretoria, Ambiente, GHE **e**
   GES — cada um com sua própria tabelinha (score médio, distribuição por banda,
   N) **e** uma lista "Top Problemas" (top 3 fatores daquele recorte). Isso é uma
   versão mais completa da ideia de "Recortes" que já tínhamos puxado do
   relatório da Solute (que só fazia unidade/setor/cargo) — confirma que vale a
   pena generalizar "Recortes" pra qualquer dimensão de corte que a empresa tiver
   cadastrado, não fixar em 3 categorias.
2. **Contagem explícita de supressão por confidencialidade**: o relatório mostra
   literalmente "0 recorte(s) suprimido(s) por k-anonimato" — transparência sobre
   quantos cortes foram escondidos por N mínimo, em vez de simplesmente omitir
   sem dizer nada. Vale adotar: hoje nosso sistema só mostra "Suprimido" na linha
   que foi escondida, nunca um contador total de quantos recortes sumiram no
   documento inteiro.
3. **Apêndice de integridade/rastreabilidade**: versão do relatório (`v45`),
   versão do algoritmo de scoring, timestamp exato de geração, e um **hash
   SHA-256** do conteúdo pra provar que o PDF não foi alterado depois de gerado.
   Isso é uma ideia genuinamente boa pra credibilidade jurídica (valor probatório
   documental) e é barata de implementar (já temos todo o dado determinístico —
   só falta calcular e exibir um hash do conteúdo do relatório). Vale incorporar
   como uma pequena seção/rodapé técnico no final do documento.
4. **"Tendência" comparando com ciclo anterior**: quando existe uma aplicação
   anterior da mesma Unidade/GHE, mostrar se cada domínio subiu, desceu ou ficou
   estável desde o último ciclo. Isso é novo pra nós (hoje cada relatório é uma
   fotografia isolada) — fica registrado como ideia de melhoria futura, não
   necessariamente neste ciclo de reformulação (depende de ter 2+ ciclos de dados
   reais pra fazer sentido, o que ainda não é o caso de nenhum cliente).

### 4.2 O que **não** vale a pena aproveitar (e por quê)

1. **Matriz de risco P×S 5×5 (Probabilidade × Severidade)** — é exatamente o
   modelo que já abandonamos deliberadamente em 2026-07-29 (Seção 6.14 do
   CLAUDE.md: banda por prevalência substituiu Severidade×Probabilidade por
   falta de base científica citável na conversão de evidências em
   probabilidade). Este relatório do Hospital São Lucas usa esse mesmo modelo —
   reforça que a decisão que já tomamos (abandonar P×S) estava certa, mas não é
   um motivo pra voltar atrás.
2. **Heatmap completo cruzando as 8 dimensões × N recortes numa grade só** —
   visualmente denso, e vai na direção contrária do que você já pediu
   explicitamente antes ("relatório fácil de compreender", preferir semáforo a
   uma tabela de 25 domínios). Um heatmap gigante de dimensões × recortes é
   ainda mais difícil de ler que a tabela que já reduzimos. Não recomendo.
3. **Mapa de Hotspots (ranking de combinações fator×recorte)** — tecnicamente
   interessante, mas é built em cima da matriz P×S (item 1) e adiciona mais uma
   camada de tabela/ranking a um relatório que estamos justamente tentando
   enxugar. Fica de fora por ora.
4. **Análise de Distribuição e Equidade (Gap Top25%/Bottom25%, quartis)** —
   estatisticamente sofisticado, mas exige N grande por recorte pra fazer
   sentido (quartis de 8 pessoas por recorte, como no exemplo, são pouco
   confiáveis) e adiciona complexidade estatística que foge do "fácil de
   compreender". Fica de fora por ora.
5. **Ruído visual do cabeçalho/rodapé repetido** — o `.md` deste relatório
   mostra o texto "Framework COPSOQ-inspired — Padrão (autoral) v1.0.0" e a
   identificação do ciclo repetidos dezenas de vezes, inclusive misturados de
   forma ilegível pelo processo de extração. Isso é uma lição do que **evitar**:
   nosso cabeçalho/rodapé já é enxuto (nome do documento + página), não
   precisamos adicionar mais informação repetida em toda página.

### 4.3 Conclusão da comparação (Solute vs. Hospital São Lucas)

O relatório da Solute (Relatório 1) continua sendo a referência principal de
**tom, estrutura e visual** (é o que o usuário validou explicitamente). O
Hospital São Lucas (Relatório 2) contribui com 3 ideias pontuais boas — recortes
organizacionais mais ricos (múltiplas dimensões de corte, não só 3), contador de
supressões, e apêndice de integridade/hash — sem alterar a decisão de manter o
semáforo nem de evitar tabelas/heatmaps densos.

---

## 5. Pendências em aberto (não decidir/implementar ainda)

1. **Paleta de cor de destaque**: manter o azul-marinho (`#2b3a55`) já usado no
   sistema, ou adotar um acento tipo o laranja da Solute? Decidir só na hora de
   implementar.
2. **"Recortes"**: o sistema hoje não segmenta respondentes por setor/cargo
   dentro de um GHE — precisa avaliar se isso é viável com o dado que já é
   coletado (`Respondente.tempo_na_organizacao`, `modalidade_trabalho`) ou se
   exige campo novo (ex.: cadastro de setor/cargo do respondente), e quantas
   dimensões de corte vale a pena suportar já neste ciclo (o Hospital São Lucas
   sugere que "quanto mais dimensões, melhor", mas isso é trabalho de coleta
   novo, não só de relatório).
3. **"Índice consolidado" (0-100) e "Nível geral de risco" (Baixo/Moderado/Alto)**
   pro Panorama: hoje o sistema calcula escore por domínio, não um índice único
   agregando todos os domínios de um relatório — precisa definir a fórmula (média
   simples dos escores? média ponderada pela prevalência?) quando for implementar.
4. **Hash de integridade (SHA-256) e apêndice técnico**: decidir se entra já
   nesta reformulação ou fica pra depois — é barato de implementar e
   independente do resto do plano, pode ser feito a qualquer momento.
5. **Contador de recortes suprimidos por confidencialidade**: idem — mudança
   pequena e isolada, pode entrar já ou depois, não depende de nenhuma outra
   pendência.

---

## 6. O que NÃO muda

- O **semáforo** continua sendo a forma de apresentar resultados por domínio —
  decisão inegociável do usuário, não é substituído pela lista ranqueada da Solute.
- A regra de que a IA (Claude) nunca decide classificação, só interpreta números
  já calculados (CLAUDE.md Seção 8.1) — continua valendo pro parecer técnico e
  pro plano de ação refinado.
- Confidencialidade por N mínimo de respondentes (hoje 5) — mesmo princípio já
  usado, só reforçado pelo padrão "k-anonimato mínimo de 5" citado no relatório da
  Solute (confirma que o valor já adotado está alinhado com prática de mercado).
