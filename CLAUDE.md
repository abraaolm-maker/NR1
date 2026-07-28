# CLAUDE.md — Sistema de Avaliação de Fatores de Risco Psicossocial (NR-01/GRO-PGR)

> Este arquivo é a fonte de verdade do projeto. Qualquer trabalho feito pelo Claude Code neste
> repositório deve primeiro ler este documento inteiro antes de gerar código. Ele define:
> o que o produto precisa fazer, por que (base legal), os dois instrumentos de coleta completos
> com suas escalas corretas, a ordem correta do processo, a arquitetura de cálculo da matriz de
> risco, e o contrato da API de análise com Claude que gera o Inventário de Risco Psicossocial em PDF.

---

## 0. Stack técnica (definitivo)

- **Backend/API:** Django + Django REST Framework (DRF).
- **Banco de dados:** SQLite3. **Decisão definitiva** (não temporária) do usuário em 2026-07-17 —
  substitui a escolha original de PostgreSQL descrita nas versões anteriores deste documento. Não
  planejar migração para Postgres neste projeto a menos que o usuário reabra essa decisão
  explicitamente. Ver detalhamento e motivo em [4.1 Decisões de Modelagem Registradas](#41-decisões-de-modelagem-registradas).
- **Geração de PDF:** WeasyPrint (HTML/CSS → PDF), a partir de template Django.
- **Motor de cálculo de risco:** módulo Python puro, sem dependência de Django (`risk_engine.py`,
  entregue junto com este documento), importado pelos models/services da app. Isso permite testar
  o cálculo isoladamente com `pytest`, sem subir banco nem servidor.
- **Fila assíncrona (opcional, recomendada para geração de PDF/chamada à IA):** Celery + Redis.
- **Seeds dos instrumentos:** arquivos JSON entregues junto com este documento
  (`seeds/copsoq_rr_revestir.json` e `seeds/itra.json`) — carregar via fixture/management command
  do Django, nunca reescrever os itens manualmente no código.

---

## 1. O que este sistema é (e o que ele não é)

Este é um sistema de **digitalização e gestão do ciclo completo de avaliação de fatores de risco
psicossociais relacionados ao trabalho (FRPRT)**, para uso interno de empresas que precisam se
adequar ao Capítulo 1.5 da NR-01 (GRO/PGR).

Ele **não é** apenas um formulário digital. Um formulário sozinho não atende à NR-01. O que a
fiscalização do MTE cobra é **processo rastreável**: identificação → coleta com instrumento
validado → cálculo técnico de risco → registro no Inventário de Riscos → plano de ação com dono e
prazo → acompanhamento contínuo. O sistema precisa cobrir esse ciclo inteiro, não só a etapa de
coleta.

**Papel da IA (Claude) neste produto:** gerar a interpretação técnica em linguagem natural
(parecer, contextualização dos números, sugestões de ação) a partir de escores **já calculados
deterministicamente pelo backend**. A IA nunca calcula a matriz de risco nem decide a
classificação final sozinha — isso é cálculo determinístico auditável. Todo relatório gerado pela
IA sai marcado como minuta sujeita à revisão e assinatura do profissional legalmente habilitado
responsável pelo PGR.

---

## 2. Base legal (resumo para o time de desenvolvimento)

- **Portaria MTE nº 1.419/2024** alterou o item 1.5.4.4 da NR-01, incluindo expressamente os
  fatores de risco psicossocial entre os elementos que toda organização deve identificar e avaliar
  dentro do GRO.
- **Portaria MTE nº 765/2025** prorrogou a vigência plena (fiscalização punitiva) para
  **26/05/2026**. Antes disso, o período é educativo/orientativo.
- A NR-01 **não impõe uma ferramenta de coleta específica**. O que ela exige é: metodologia
  técnica de avaliação com questionário validado, evidências de coleta, registro de respostas,
  cálculo de nível de risco por fator, critérios de probabilidade/severidade documentados por
  escrito, e plano de ação com responsáveis e prazos.
- A gestão dos FRPRT deve começar pela **Avaliação Ergonômica Preliminar (NR-17)** e, se
  necessário, pela Análise Ergonômica do Trabalho (AET) — os fatores psicossociais e ergonômicos
  se sobrepõem (ex.: ritmo de trabalho, pressão por metas).
- O resultado da avaliação **alimenta o Inventário de Riscos Ocupacionais**, que é parte do PGR —
  não é um documento separado e solto.
- **Não existe portal de envio do PGR ao MTE.** O documento fica arquivado na empresa (físico ou
  digital, assinado por profissional habilitado) e é apresentado quando o auditor fiscal solicita.
- **O eSocial não recebe o inventário psicossocial completo.** Só recebe efeitos em saúde: evento
  S-2220 (ASOs) e S-2240 (condições ambientais). O sistema deve manter os dados internos
  estruturados de forma compatível para checagem cruzada futura, mas não precisa (nem deve) tentar
  enviar o inventário inteiro para o eSocial.

---

## 3. Princípios de design (não negociáveis)

1. **Metodologia plugável.** Nenhuma lógica do backend deve assumir "é sempre COPSOQ" ou "é sempre
   ITRA". Todo instrumento é modelado como `{instrumento, escala, domínio/subescala, item,
   polaridade}` — exatamente o formato dos arquivos `seeds/copsoq_rr_revestir.json` e
   `seeds/itra.json` entregues junto com este documento. **O escopo inicial do projeto cobre os
   dois instrumentos desde o primeiro sprint** (COPSOQ = formulário da RR Revestir; ITRA = escalas
   EACT/ECHT/EADRT/EIPSTP/EIPSTN da planilha CRARP) — não é um "depois adicionamos o outro", os
   dois entram juntos no modelo de dados e no motor de cálculo desde o início.
2. **Polaridade por item, não por domínio.** Um domínio pode conter itens de risco (quanto maior,
   pior) e itens protetivos (quanto maior, melhor) ao mesmo tempo — é o caso real do Domínio 9 do
   COPSOQ adaptado deste projeto (ver seção 5.1). O cálculo deve inverter a escala item a item
   *antes* de agregar por domínio, nunca depois.
3. **Consentimento e confidencialidade por padrão.** Aplicação anônima como padrão; termo de
   consentimento obrigatório antes de responder; supressão automática de resultado agregado quando
   o número de respondentes de um GHE for menor que um mínimo configurável (padrão sugerido: 3).
4. **Critérios de risco documentados, não implícitos.** Os critérios de severidade, probabilidade,
   níveis e classificação usados pelo sistema devem ser armazenados como dados versionados e
   exportados junto com cada relatório — nunca "hardcoded silenciosamente" sem aparecer no
   documento final.
5. **Identificação do perigo antes da coleta.** Cada GHE deve ter, antes da aplicação do
   questionário, um cadastro dos perigos psicossociais identificados (a partir da lista oficial do
   Guia MTE), para que o inventário nasça completo e não dependa só do resultado do questionário.
6. **Plano de ação estruturado, não texto livre.** Cada risco classificado acima do limiar de
   atenção deve gerar automaticamente um item de plano de ação com: descrição da medida,
   responsável, prazo, status, e campo de evidência de execução.
7. **Trilha de auditoria completa.** Toda aplicação, todo cálculo e toda geração de relatório
   devem ser registrados com timestamp, responsável técnico e versão do critério de cálculo usado.
8. **IA não decide, interpreta.** Ver seção 7.
9. **Pontos de corte do ITRA como parâmetro, não como verdade fixa no código.** Os pontos de corte
   oficiais completos de ECHT, EADRT, EIPSTP e EIPSTN pertencem ao manual original de Mendes &
   Ferreira (2007, "Psicodinâmica do Trabalho", Capítulo 5) e não puderam ser confirmados em fonte
   aberta com precisão suficiente para uso em produção. O sistema deve tratá-los como parâmetros
   configuráveis por instrumento/escala, com um aviso explícito na interface para que o psicólogo
   ou profissional responsável valide os cortes contra o manual oficial antes de usar os resultados
   de forma conclusiva. **Não hardcode pontos de corte do ITRA além da EACT (única confirmada
   abaixo em fonte acadêmica aberta).**

---

## 4. Modelo de dados (visão lógica)

```
Empresa
 └─ Unidade (endereço, CNPJ)
     └─ GHE (Grupo Homogêneo de Exposição)
         ├─ RegistroErgonomico (AEP | AET — referência mínima ao vínculo NR-17, sem workflow completo)
         ├─ Perigos identificados (cadastro prévio, lista MTE — sem seed ainda, cadastro via Admin)
         ├─ Função(ões) vinculada(s)
         └─ Aplicação
             ├─ instrumento_usado (COPSOQ_ADAPTADO | ITRA | outro)
             ├─ criterio_versao (FK — qual CriterioVersao calculou esta Aplicação)
             ├─ tipo (anônima | identificada)
             ├─ data, responsável_aplicador
             ├─ Respondente (opcional se identificada; nunca exposto em relatório agregado)
             │    └─ Resposta (item_id, valor_bruto 1..5 ou 0..6 conforme escala)
             ├─ EscoreDominio (calculado: média ajustada por polaridade)
             └─ ClassificacaoRisco (severidade × probabilidade → nível)
Criterios (versionado): severidade[], probabilidade[], niveis[], classificacao[]
PlanoDeAcao (risco_id, medida, responsavel, prazo, status, evidencia)
Relatorio (unidade, aplicacoes[] — M2M, mesma Unidade e mesmo CriterioVersao entre elas,
           periodo, gerado_em, criterio_versao, pdf_path, assinado_por,
           status: aguardando_revisão|aprovado|assinado)
```

---

## 4.1 Decisões de Modelagem Registradas

> Decisões tomadas em conversa com o usuário em 2026-07-17, durante a implementação da Etapa 2
> (modelagem). Ficam aqui porque este arquivo é a fonte de verdade — o que foi decidido no chat
> precisa estar escrito aqui, não só na conversa.

1. ~~`Dominio.ghe_variante`~~ **[REMOVIDO em 2026-07-18, ver Seção 6.5]**. Resolvia a variação real
   dos seeds da época: no COPSOQ da RR Revestir o texto dos itens de D1–D4 mudava por GHE (GHE01
   "Auxiliar Administrativo" vs GHE02 "Almoxarife"), então cada variante tinha sua própria linha
   de `Dominio`. Removido porque essa customização de UMA empresa piloto tinha virado, na prática,
   a única opção do sistema pra qualquer empresa — o COPSOQ agora é genérico (9 domínios, sem
   variante), igual ao ITRA sempre foi.

2. **`Relatorio` é M2M com `Aplicacao`** (não um-para-um): um Inventário de Risco Psicossocial em
   PDF pode cobrir várias Aplicações/GHEs do mesmo ciclo (Seção 8.3, item 4 fala em "Resultados
   por GHE" no plural). **Trava obrigatória**: todas as `Aplicacao` ligadas a um mesmo `Relatorio`
   devem pertencer à mesma `Unidade` do `Relatorio` e ter sido calculadas sob o mesmo
   `CriterioVersao` do `Relatorio` — validado via sinal `m2m_changed` em
   `relatorios/models.py`, que recusa o `add()` (levanta `ValidationError`) se a Aplicação não
   bater unidade ou critério. Isso existe porque um relatório que misture unidades ou versões de
   critério diferentes sem sinalizar quebraria a rastreabilidade que a NR-01 exige (Seção 7.8).
   `Relatorio.status` usa exatamente a semântica minuta (`"aguardando_revisão"`, default) →
   `aprovado` → `assinado` descrita na Seção 8.1.

3. **NR-17 (AEP/AET)**: não ficou de fora do modelo. `RegistroErgonomico` (app `avaliacoes`) é uma
   referência mínima — `ghe` (FK), `tipo` (AEP/AET), `data_registro`, `responsavel_tecnico`,
   `referencia`, `observacao` — sem implementar o workflow completo de avaliação ergonômica agora.
   Existe só para não exigir uma migration dolorosa depois, quando já houver `Aplicacao` reais
   ligadas a `GHE` sem essa referência.

4. **Catálogo `Perigo`** (lista oficial de perigos psicossociais do Guia MTE) não veio com seed
   JSON como COPSOQ/ITRA. Por ora é cadastrado manualmente via Django Admin. Quando o usuário
   organizar a lista oficial, ela chega como `seeds/perigos_mte.json` (mesmo padrão dos outros
   dois) e ganha um management command análogo ao `load_instrumentos` (ex.: `load_perigos`) — não
   inventar essa lista antes disso.

5. **Banco de dados: SQLite3 é definitivo, não temporário.** Ver Seção 0. PostgreSQL foi a escolha
   original deste documento; o usuário decidiu manter SQLite3 permanentemente neste projeto em
   2026-07-17. Não sugerir nem preparar migração para Postgres a menos que o usuário reabra essa
   decisão.

---

## 4.2 Indicadores Indiretos (Evidências Complementares)

> Decisão tomada em 2026-07-17, durante a implementação da Etapa 5 (API de análise com Claude).

A Seção 7.5 depende de "evidências complementares convergentes" (absenteísmo acima da média,
turnover acima da média, CAT/CID-F relacionado, item "Não conforme" no checklist observacional,
relato coerente na entrevista com a liderança) para calcular a Probabilidade de um risco. O
diagrama original da Seção 4 não previa onde guardar esses dados — gap real, não intencional.

Modelo criado (app `avaliacoes`): **`IndicadorIndireto`**

- `ghe` (FK → GHE)
- `tipo` (choices: `ABSENTEISMO`, `TURNOVER`, `CAT_CID_F`, `CHECKLIST_NAO_CONFORME`,
  `RELATO_ENTREVISTA`)
- `periodo_referencia` (data de referência do período observado)
- `descricao` (texto livre — o que foi observado/registrado)
- `dominio_relacionado` (FK → `Dominio`, nullable — vazio quando o indicador vale pro GHE inteiro,
  sem apontar um domínio específico)
- `convergente` (boolean, default `True`) — permite ao profissional responsável registrar um
  indicador sem contá-lo como evidência convergente num cálculo específico
- `registrado_por`, `criado_em`

**Regra de cálculo** (`avaliacoes/services/calculo_risco.py::contar_evidencias_convergentes`):
`evidencias_convergentes` de um domínio = contagem de `IndicadorIndireto` do mesmo GHE com
`convergente=True` e (`dominio_relacionado` nulo OU igual ao domínio calculado). Isso substitui o
parâmetro manual que existia antes — `calcular_dominio()` não aceita mais `evidencias_convergentes`
como argumento externo, ele é sempre derivado do banco.

---

## 5. Instrumentos de coleta (extraídos e organizados)

### 5.1 COPSOQ (genérico — 9 domínios)

> **Realinhamento de 2026-07-18** (ver Seção 6.5): até esta data, os domínios D1–D4 tinham texto
> específico para dois cargos de uma empresa piloto usada como referência (RR Revestir —
> "Auxiliar Administrativo"/"Almoxarife"), exigindo que toda `Aplicacao` escolhesse uma "Variante
> do instrumento (GHE)" entre essas duas opções fixas. Isso confundia o gestor (só existiam
> aquelas duas opções, sem relação com o GHE real da empresa dele) e divergia do objetivo original
> do usuário (converter o Excel/PDF fornecidos num sistema **genérico**, plugável em qualquer
> empresa). Generalizado: agora os 9 domínios têm texto único, válido para qualquer cargo/GHE —
> não existe mais conceito de variante, nem campo `instrumento_ghe_variante`/`ghe_variante` no
> banco.

**Escala (todos os itens, 1 a 5):**

| Valor | Rótulo |
|---|---|
| 1 | Muito baixo / nunca / discordo totalmente |
| 2 | Baixo / raramente |
| 3 | Moderado / às vezes |
| 4 | Alto / frequentemente |
| 5 | Muito alto / sempre / concordo totalmente |

**Classificação por domínio (após inversão de polaridade item a item):**
Baixo ≤ 2,5 · Moderado 2,6–3,4 · Elevado ≥ 3,5

**Polaridade:** `RISCO` = quanto maior o valor, maior o risco (usar direto). `PROTETIVO` = quanto
maior o valor, menor o risco (inverter antes de agregar: `valor_invertido = 6 - valor_bruto`).

---

**D1 — Exigências do trabalho** (todos `RISCO`)
- D1.1 Ritmo de trabalho elevado em relação ao tempo disponível para realizar as tarefas.
- D1.2 Pressão por prazos para concluir as atividades do dia a dia.
- D1.3 Volume de trabalho superior ao efetivo disponível em períodos de maior demanda.
- D1.4 Interrupções frequentes que dificultam concluir as tarefas em andamento.
- D1.5 Baixa previsibilidade da demanda, com solicitações urgentes, ajustes de última hora e retrabalho.

**D2 — Exigências emocionais** (todos `RISCO`)
- D2.1 Necessidade de lidar com clientes, fornecedores ou colegas em situação de tensão, cobrança ou conflito.
- D2.2 Necessidade de controlar emoções para manter o atendimento/relacionamento adequado mesmo sob pressão.
- D2.3 Exposição a reclamações, cobranças ríspidas ou hostilidade verbal durante a rotina.
- D2.4 Carga emocional decorrente da responsabilidade por evitar erros, perdas ou retrabalho na execução das tarefas.

**D3 — Autonomia e controle** (todos `PROTETIVO`)
- D3.1 Possui autonomia para organizar a sequência das próprias atividades e priorizar demandas.
- D3.2 Consegue realizar pausas técnicas básicas sem prejuízo operacional ou constrangimento.
- D3.3 Tem influência sobre rotinas/procedimentos quando identifica falhas de segurança, qualidade ou organização.
- D3.4 A carga de trabalho permite executar as tarefas com atenção, sem necessidade de atalhos inseguros ou esforço excessivo.

**D4 — Sentido e significado do trabalho** (todos `PROTETIVO`)
- D4.1 Percebe que o próprio trabalho contribui para o funcionamento seguro e organizado da empresa.
- D4.2 As atividades realizadas são coerentes com as responsabilidades da função.
- D4.3 Há clareza do papel, das responsabilidades e dos limites da função, evitando conflito e retrabalho.

**D5 — Reconhecimento e recompensa** (todos `PROTETIVO`)
- D5.1 Recebe reconhecimento proporcional às responsabilidades assumidas na rotina.
- D5.2 O feedback sobre desempenho é claro, respeitoso e voltado à melhoria do trabalho.
- D5.3 Critérios de metas, cobranças e prioridades são compatíveis com qualidade, segurança e capacidade operacional.
- D5.4 Percebe equilíbrio entre exigências e recursos disponíveis, incluindo estrutura, ferramentas, apoio e tempo.

**D6 — Relações sociais e liderança** (todos `PROTETIVO`)
- D6.1 A liderança fornece suporte quando há sobrecarga, conflito de prioridade ou dificuldade operacional.
- D6.2 A comunicação com a liderança é acessível e resolve problemas de rotina.
- D6.3 As relações no trabalho são cooperativas, com ajuda mútua e respeito.
- D6.4 Conflitos são tratados de forma técnica, imparcial e sem exposição indevida.

**D7 — Segurança psicológica** (todos `PROTETIVO`)
- D7.1 Pode relatar erros, quase-erros, desvios ou dificuldades sem medo de punição injusta.
- D7.2 Pode discordar tecnicamente de uma orientação quando percebe risco de erro, perda, acidente ou não conformidade.
- D7.3 Sente que sua opinião prática é considerada nas decisões que afetam a rotina de trabalho.

**D8 — Justiça organizacional** (todos `PROTETIVO`)
- D8.1 Escalas, folgas e distribuição de tarefas são feitas com critérios claros e equilibrados.
- D8.2 Regras e cobranças são aplicadas de forma consistente, sem favorecimento ou tratamento desigual.
- D8.3 Mudanças de rotina, metas, sistema ou procedimento são comunicadas com antecedência suficiente.

**D9 — Violência, assédio e discriminação** (⚠️ **polaridade mista** — cuidado especial no backend)
- D9.1 Já sofreu agressão verbal, ameaça ou intimidação de cliente, fornecedor, terceiro ou colega durante o trabalho. → `RISCO`
- D9.2 Já presenciou ou sofreu assédio moral, humilhação, exposição pública ou cobrança vexatória. → `RISCO`
- D9.3 Há canais confiáveis e resposta efetiva para relato de conflito, assédio ou violência, sem retaliação. → `PROTETIVO`
- D9.4 Há tratamento respeitoso e sem discriminação por gênero, raça, idade, deficiência, aparência, religião ou outra condição. → `PROTETIVO`

---

### 5.2 ITRA — Inventário de Trabalho e Risco de Adoecimento (Mendes & Ferreira)

⚠️ **Este instrumento é uma metodologia acadêmica validada e de terceiros.** Os itens abaixo foram
extraídos do arquivo enviado (planilha CRARP). As escalas de resposta indicadas seguem a
literatura acadêmica aberta consultada (ver observações). **Antes de usar em produção, o
profissional responsável deve validar contra a fonte primária**: MENDES, A. M.; FERREIRA, M. C.
*Inventário sobre Trabalho e Riscos de Adoecimento – ITRA*. In: Mendes, A.M. (Org.).
*Psicodinâmica do Trabalho: teoria, método e pesquisas*. São Paulo: Casa do Psicólogo, 2007, cap. 5.

#### 5.2.1 EACT — Escala de Avaliação do Contexto do Trabalho (27 itens, todos `RISCO`)

**Escala confirmada em fonte acadêmica aberta:** 1 = Nunca · 2 = Raramente · 3 = Às vezes ·
4 = Frequentemente · 5 = Sempre.

**Classificação (fonte acadêmica aberta):** Satisfatório < 2,29 · Crítico 2,3–3,69 · Grave ≥ 3,7.
(Nota: alguns estudos usam variações finas desses limites — confirmar versão oficial com o
profissional responsável.)

1. O ritmo de trabalho é excessivo
2. As tarefas são cumpridas com pressão de prazos
3. Existe forte cobrança por resultados
4. As normas para execução das tarefas são rígidas
5. Existe fiscalização do desempenho
6. O número de pessoas é insuficiente para se realizar as tarefas
7. Os resultados esperados estão fora da realidade
8. Existe divisão entre quem planeja e quem executa
9. As tarefas são repetitivas
10. Falta tempo para realizar pausas de descanso no trabalho
11. As tarefas executadas sofrem descontinuidade
12. As condições de trabalho são precárias
13. O ambiente físico é desconfortável
14. Existe muito barulho no ambiente de trabalho
15. O mobiliário existente no ambiente de trabalho é inadequado
16. Os instrumentos de trabalho são insuficientes para a realização das tarefas
17. O material de consumo é insuficiente
18. As tarefas não estão claramente definidas
19. Os funcionários são excluídos das decisões
20. Existem dificuldades na comunicação entre chefia e subordinados
21. Existem disputas profissionais no local de trabalho
22. Falta integração no ambiente de trabalho
23. A comunicação entre funcionários é insatisfatória
24. Falta apoio das chefias para o meu desenvolvimento profissional
25. As informações que preciso para executar minhas tarefas são de difícil acesso
26. As condições de trabalho oferecem risco à segurança das pessoas
27. O espaço físico para realizar o trabalho é inadequado

*(Cálculo original da planilha: soma de todos os itens ÷ 27 = escore geral. Recomenda-se também
calcular por subfator — Organização do Trabalho, Condições de Trabalho, Relações Socioprofissionais
— conforme literatura, em vez de só o escore único; ver seção 6.)*

#### 5.2.2 ECHT — Escala de Custo Humano do Trabalho (todos `RISCO`)

**Escala:** mesmo formato Likert de 1 a 5 usado na EACT (1 Nunca … 5 Sempre) — confirmar com o
profissional responsável se a versão adotada pela empresa usa a mesma escala.

1. Usar força física
2. Usar os braços de forma contínua
3. Ficar em posição curvada
4. Caminhar
5. Ser obrigado a ficar em pé
6. Ter que manusear objetos pesados
7. Fazer esforço físico
8. Usar as pernas de forma contínua
9. Usar as mãos de forma repetida
10. Subir e descer escada
11. Desenvolver macetes
12. Ter que resolver problemas
13. Ser obrigado a lidar com imprevistos
14. Fazer previsão de acontecimentos
15. Usar a visão de forma contínua
16. Usar a memória
17. Ter desafios intelectuais
18. Fazer esforço mental
19. Ter concentração mental
20. Usar a criatividade
21. Ter controle das emoções
22. Ter que lidar com ordens contraditórias
23. Ter custo emocional
24. Ser obrigado a lidar com a agressividade dos outros
25. Disfarçar sentimentos
26. Ser obrigado a elogiar as pessoas
27. Ser submetido a constrangimentos
28. Transgredir valores éticos
29. Ser obrigado a sorrir

*(Cálculo original: soma ÷ 29. Recomenda-se também segmentar em custo físico, cognitivo e
afetivo/emocional, conforme a literatura do ITRA.)*

#### 5.2.3 EADRT — Escala de Avaliação de Danos Relacionados ao Trabalho (todos `RISCO`)

**Escala:** frequência nos últimos 6 meses, 1 a 5 (1 Nunca … 5 Sempre), conforme instrução original
da planilha ("Marque o número que melhor corresponde à frequência...").
⚠️ Esta escala tem leitura mais sensível: mesmo pontuação moderada já pode indicar necessidade de
ação, pois os itens descrevem sintomas de adoecimento. Não tratar com os mesmos limiares da EACT
sem validação do profissional responsável.

1. Dores no corpo
2. Dores nos braços
3. Dor de cabeça
4. Distúrbios respiratórios
5. Distúrbios digestivos
6. Dores nas costas
7. Distúrbios auditivos
8. Alterações do apetite
9. Distúrbios na visão
10. Alterações do sono
11. Dores nas pernas
12. Distúrbios circulatórios
13. Amargura
14. Sensação de vazio
15. Sentimento de desamparo
16. Mau humor
17. Vontade de desistir de tudo
18. Tristeza
19. Irritação com tudo
20. Sensação de abandono
21. Dúvida sobre a capacidade de fazer as tarefas
22. Solidão
23. Insensibilidade em relação aos colegas
24. Dificuldades nas relações fora do trabalho
25. Vontade de ficar sozinho
26. Conflitos nas relações familiares
27. Agressividade com os outros
28. Dificuldade com os amigos
29. Impaciência com as pessoas em geral

*(Cálculo original: soma ÷ 29. Recomenda-se segmentar em danos físicos, psicológicos e sociais.)*

#### 5.2.4 EIPSTP — Escala de Indicadores de Prazer no Trabalho (todos `PROTETIVO`)

**Escala (decisão definitiva do projeto):** Likert de 1 a 5 (1 Nunca · 2 Raramente · 3 Às vezes ·
4 Frequentemente · 5 Sempre) — mesma escala usada em EACT, ECHT e EADRT dentro da mesma planilha
CRARP, que segue o mesmo padrão de instrução em todas as seções ("marque a alternativa que melhor
corresponde..."). A literatura acadêmica registra uma variação histórica de 7 pontos (0–6) usada em
versões do EIPST de 2003, mas como o arquivo-fonte deste projeto (planilha CRARP) não define rótulo
próprio e segue a mesma estrutura das demais escalas, adotamos 1–5 para manter consistência interna
do sistema e simplicidade de UI. **Esta é a escala oficial deste projeto — não implementar range
alternativo.**

1. Satisfação
2. Motivação
3. Orgulho pelo que faço
4. Bem-estar
5. Realização profissional
6. Valorização
7. Reconhecimento
8. Identificação com as minhas atividades
9. Liberdade com a chefia para negociar o que precisa
10. Liberdade para falar do meu trabalho com meus colegas
11. Solidariedade entre os colegas
12. Confiança entre os colegas
13. Liberdade para expressar minhas opiniões no local de trabalho
14. Liberdade para utilizar minha criatividade
15. Liberdade para falar sobre o meu trabalho com as chefias
16. Cooperação entre os colegas

*(Cálculo original: soma ÷ 16.)*

#### 5.2.5 EIPSTN — Escala de Indicadores de Sofrimento no Trabalho (todos `RISCO`)

**Escala (decisão definitiva do projeto):** mesma escala 1–5 da seção 5.2.4, pelo mesmo motivo
(consistência com o restante da planilha CRARP).

1. Esgotamento emocional
2. Estresse
3. Insatisfação
4. Sobrecarga
5. Frustração
6. Insegurança
7. Medo
8. Falta de reconhecimento do meu esforço
9. Falta de reconhecimento do meu desempenho
10. Desvalorização
11. Indignação
12. Inutilidade
13. Discriminação

*(Cálculo original: soma ÷ 13.)*

---

## 6. Ordem correta do processo (fluxo que o sistema deve implementar)

Baseado na orientação oficial do MTE (Guia de Informações sobre os Fatores de Riscos Psicossociais
Relacionados ao Trabalho + Nota Técnica SEI nº 4655/2024/MTE):

1. **Preparação** — cadastro de empresa, unidade, GHEs e funções.
2. **Articulação com NR-17** — registro de AEP (e AET, se aplicável) vinculada a cada GHE.
3. **Identificação dos perigos psicossociais** — cadastro dos fatores presentes por GHE, com base
   na lista oficial do Guia MTE, *antes* de aplicar qualquer questionário.
4. **Escolha e configuração do instrumento de coleta por GHE** — o sistema deve permitir COPSOQ
   adaptado e ITRA simultaneamente desde o primeiro ciclo (não é sequencial: um GHE pode usar
   COPSOQ e outro pode usar ITRA, ou o mesmo GHE pode ter os dois em ciclos diferentes). A escolha
   por GHE/ciclo fica registrada com justificativa técnica.
5. **Consentimento e aplicação** — coleta anônima (padrão) por GHE, com termo de consentimento.
6. **Tabulação e cálculo de escores** — ver seção 7.
7. **Classificação de risco** — matriz probabilidade × severidade.
8. **Registro no Inventário de Riscos Ocupacionais (dentro do PGR)**.
9. **Plano de ação** — gerado a partir de cada risco classificado, com responsável e prazo.
10. **Geração do relatório (Inventário de Risco Psicossocial em PDF)** — minuta via IA, revisão e
    assinatura do profissional habilitado.
11. **Acompanhamento contínuo** — reaplicação periódica, atualização de status do plano de ação,
    nova versão do relatório.

---

## 6.1 Decisões de Implementação Registradas (Etapa 7 — UI de aplicação do questionário)

> Decisões tomadas em conversa com o usuário em 2026-07-17. Implementa o passo 5 ("Consentimento e
> aplicação") desta seção — sem WhatsApp neste projeto (diferente do Elo), a coleta é via link web.

1. **Acesso por token, não por login**: `Respondente.token` (UUID, único, não editável) é a
   credencial de acesso — URL `/responder/<token>/`. Sem autenticação de usuário; o token em si é
   o que autoriza. Evita enumerar/adivinhar outros respondentes por pk sequencial.

2. **Criação de slots**: as duas formas coexistem. (a) Criação manual via `RespondenteInline` no
   Admin da `Aplicacao` (um por um, com alias explícito) — já existia. (b) Geração em massa: botão
   "Gerar links de respondente" no `AplicacaoAdmin` (view custom em `get_urls()`) que cria N
   `Respondente` de uma vez (alias sequencial "Respondente N") e lista os N links prontos — pensado
   pra empresas com centenas de funcionários.

3. **Navegação**: um domínio/subescala por página (`/responder/<token>/<dominio_codigo>/`), com
   resume automático — reabrir o link salta direto pro primeiro domínio ainda pendente
   (`avaliacoes/services/questionario.py::dominios_pendentes`), nunca repete o que já foi
   respondido. Formulário dinâmico (`RadioSelect`) construído a partir de
   `Dominio.escala_labels`.

4. **Status automático da Aplicacao** (`avaliacoes/services/aplicacao_status.py`):
   `rascunho` → `em_andamento` na primeira `Resposta` recebida; → `concluida` só quando **todos**
   os `Respondente` da Aplicacao têm `concluido_em` preenchido. Nunca sai de `cancelada`, nunca
   regride uma `concluida`. **Limitação conhecida**: um slot gerado em massa que ninguém nunca
   responde bloqueia a Aplicacao de virar `concluida` para sempre — o gestor precisa apagar slots
   não usados no Admin se quiser fechar o ciclo sem 100% de resposta.

5. **Confidencialidade também no Plano de Ação, extendida aqui**: `Respondente.concluido_em`
   marca conclusão individual; o dado bruto de quem respondeu o quê nunca aparece fora do Admin
   (telas restritas) — o público só vê o formulário do próprio respondente, nunca resultado
   agregado de terceiros.

---

## 6.2 Painel do Gestor (fora do Django Admin)

> Decisão tomada em 2026-07-17: o usuário havia validado anteriormente que o Django Admin bastava
> como interface do gestor, mas reverteu essa decisão e pediu um painel próprio cobrindo cadastro
> de Empresa/GHE/Aplicacao, geração de links, revisão do parecer da IA e assinatura do relatório.
> O Django Admin continua disponível e funcional em paralelo para tudo que não está neste painel.

- **Login próprio, não o do Admin**: `/painel/entrar/` (template custom), autenticação via
  `django.contrib.auth`. Toda view do painel usa o decorator `avaliacoes.decorators.gestor_required`
  (não `staff_member_required` puro — esse por padrão redireciona pro login do Admin
  `admin:login`, não pro login deste painel; isso só foi pego pelo teste automatizado
  `test_painel_exige_login`, não na verificação manual).
- **Estrutura**: `avaliacoes/painel_views.py` + `avaliacoes/painel_urls.py` (namespace
  `painel_avaliacoes`) cobrem Empresa → Unidade → GHE → Aplicacao → gerar links.
  `relatorios/painel_views.py` + `relatorios/painel_urls.py` (namespace `painel_relatorios`)
  cobrem Relatorio, parecer, PDF, assinatura e "meu perfil profissional".
- **Revisão do parecer da IA**: textarea de JSON bruto (não um formulário estruturado por campo)
  — troca simplicidade de implementação por uma UI menos rica; validado no servidor
  (`ParecerJSONForm`) conferindo que os 5 campos obrigatórios existem.
- **"Gerar parecer via IA" chama a API real** (sem client injetado, ao contrário dos testes).
  Falha (ex.: `ANTHROPIC_API_KEY` ausente) é capturada e mostrada como mensagem ao usuário, nunca
  como erro 500.
- **Bug real encontrado e corrigido durante o teste no navegador**: o fluxo público do
  questionário (`avaliacoes/views.py::responder_dominio`) salvava as `Resposta` mas nunca chamava
  `calcular_dominio()` — `EscoreDominio`/`ClassificacaoRisco`/`PlanoDeAcao` nunca nasciam a partir
  de uma resposta real, só de chamadas manuais nos testes. Corrigido: toda submissão de domínio
  recalcula o agregado daquele domínio pra Aplicacao inteira. Coberto por teste de regressão em
  `avaliacoes/test_views.py`.

---

## 6.3 Correções de UX do Painel do Gestor (revisão 2026-07-17)

> O usuário pediu uma revisão de UX/UI do painel (Seção 6.2) navegando como um gestor de primeira
> viagem — não uma revisão de código, uma revisão de experiência. Foram levantados 13 pontos;
> o usuário pediu para corrigir todos. Ficam registrados aqui porque mudam comportamento validado
> do sistema, não só aparência.

1. **`instrumento_ghe_variante` passa a ser validado (antes: texto livre sem checagem).** Era
   possível criar uma `Aplicacao` de COPSOQ sem variante — `dominios_da_aplicacao()` retornava zero
   domínios e o respondente ia direto do consentimento para "Obrigado pela participação!" sem
   responder nada, com a Aplicacao marcada como "Concluída" (sugerindo sucesso, não falha).
   Corrigido com `Aplicacao.clean()` (bloqueia no model, portanto também no Admin) + `ChoiceField`
   dinâmico em `AplicacaoForm` (dropdown com as variantes realmente cadastradas nos `Dominio` do
   instrumento escolhido, em vez de campo de texto). Instrumentos sem variante (ITRA) devem deixar
   o campo vazio; instrumentos com variante (COPSOQ) exigem uma das existentes.
2. **Aviso de escopo do COPSOQ na tela de criação de Aplicacao**: os itens atuais de D1–D4 foram
   adaptados para os cargos de uma empresa piloto (RR Revestir — "Auxiliar Administrativo" e
   "Almoxarife"). O formulário agora avisa isso no `help_text` do campo instrumento, para o gestor
   considerar o ITRA (genérico, sem variante) se o cargo do GHE for muito diferente.
3. **Criar Relatorio para uma Unidade sem nenhuma Aplicacao não é mais um formulário quebrado**:
   antes, o campo obrigatório "Aplicações" nascia sem nenhuma opção pra marcar. Agora
   `relatorio_create` detecta essa condição antes de renderizar o form e mostra uma página
   explicando o que falta (criar GHE → Aplicacao → coletar respostas primeiro), com link direto.
4. **Links de respondente ficaram copiáveis**: botão "Copiar" por link individual e "Copiar todos"
   (um por linha) na tela de geração de links, via `navigator.clipboard`. Também é possível
   reabrir a lista de links já gerados a partir do detalhe da Aplicacao (antes só existiam no
   instante da geração).
5. **CRUD de `Funcao` movido para dentro do painel**: antes, o campo "Funções" do formulário de GHE
   aparecia vazio sem explicação caso a Unidade não tivesse nenhuma cadastrada, e não havia como
   cadastrar uma sem ir ao Admin. Criada `funcao_create` (view + form + template), com link direto
   a partir do formulário de GHE quando a lista está vazia.
6. **Vazamento de referências a "CLAUDE.md" removido de todo texto visível ao usuário final**
   (`help_text` de `Aplicacao.justificativa_instrumento`, `Respondente.token`,
   `RelatorioForm.aplicacoes`) — esses textos citavam literalmente "(CLAUDE.md Seção X)", que não
   faz sentido para quem usa o sistema, só para quem desenvolve.
7. **`verbose_name` amigável em todos os campos expostos no painel**: CNPJ, Endereço, Funções,
   Critério de cálculo, Data da aplicação, Variante do instrumento (GHE), Justificativa da escolha
   do instrumento, Aplicações, Início/Fim do período — antes apareciam com o nome técnico do campo
   (`cnpj`, `endereco`, `criterio_versao` etc.) nos formulários.
8. **Explicação do status "Aguardando ratificação" do `CriterioVersao`** adicionada tanto no
   detalhe da Aplicacao quanto no detalhe do Relatorio: deixa claro que os números do relatório já
   valem normalmente (Seção 7.3 — "o sistema não deve ficar bloqueado esperando" a ratificação),
   só a revisão formal do critério em si por um profissional habilitado é que está pendente.
9. **Validação e formatação de CNPJ** em `Empresa` e `Unidade`: `clean_cnpj()` em
   `EmpresaForm`/`UnidadeForm` exige exatamente 14 dígitos (aceita com ou sem pontuação na
   digitação) e sempre normaliza para o formato `00.000.000/0000-00` antes de salvar. CNPJ da
   `Unidade` continua opcional (pode repetir o da `Empresa` ou ficar em branco); da `Empresa` é
   obrigatório.
10. **Confirmação de navegador (`confirm()`) antes de assinar um relatório**: assinatura é
    irreversível pelo painel (Seção 8.4, item 2 — "registro interno simples", sem certificado)
    e antes não tinha nenhuma barreira contra clique acidental.
11. **Dashboard (`painel_relatorios:home`) criado como página inicial do painel** (antes, entrar no
    painel caía direto na lista de Empresas, sem visão geral). Mostra contagem de empresas,
    Aplicações em andamento e Relatórios ainda não assinados — feito para responder "o que precisa
    da minha atenção agora" no primeiro clique.
12. **Edição adicionada para Empresa, Unidade, GHE e Aplicacao** (`*_update`, ao lado dos `*_create`
    já existentes) — antes só era possível criar; qualquer correção de nome/CNPJ/etc. exigia ir ao
    Admin.
13. **Polimento da tela de login**: parágrafo de contexto explicando o que é o sistema (para quem
    chega no link sem saber o que é o CRARP) e nota "esqueceu sua senha? fale com o administrador"
    (não há fluxo de recuperação de senha neste projeto — é preciso deixar isso explícito em vez de
    simplesmente omitir o link).

**Cobertura de teste**: os pontos 1 e 3 (os dois que causavam estado inconsistente/silencioso, não
só incômodo visual) ganharam testes automatizados dedicados
(`avaliacoes/test_painel_views.py::test_aplicacao_*`,
`relatorios/test_painel_views.py::test_relatorio_create_sem_aplicacoes_mostra_mensagem_amigavel`).
Os demais foram verificados manualmente navegando o painel no navegador. Suíte completa: 52 testes
passando.

---

## 6.4 Segunda Rodada de UX do Painel do Gestor (revisão 2026-07-18)

> Segunda revisão de UX, também navegando como gestor de primeira viagem. Diferente da
> primeira rodada (Seção 6.3), o usuário já trouxe achados próprios (links sem estilo,
> nomenclatura de instrumento confusa) e pediu correção imediata desses + uma nova
> varredura livre. Rodada dividida em duas sessões no mesmo dia: a primeira entregou os
> itens 1–6 e levantou os itens 7–9 como propostas em aberto (exigiam escolha de
> produto); o usuário revisou o item 1 (rejeitou a correção inicial, queria formato de
> botão de verdade) e decidiu os itens 7–9 na sequência — todos entram abaixo já como
> implementados, com a decisão do usuário registrada em cada um onde houve escolha.

**Implementado:**

1. **Links de texto (breadcrumb `.voltar` e "Ver" em tabelas) sem estilo próprio.** Primeira
   tentativa (só cor de link + remover sublinhado) foi rejeitada pelo usuário: "esperava um
   botão, com formato de botão, similar ao 'salvar'". Corrigido de verdade em
   `templates/painel/_base.html`: `.voltar` agora é um botão completo (fundo `#eef1f6`,
   padding, `border-radius`, mesmo padrão visual do `.botao.secundario`) e as 7 ocorrências
   de link "Ver" em tabela (`empresa_list`, `empresa_detail`, `unidade_detail`,
   `ghe_detail`, `relatorio_list`, `home` ×2) ganharam `class="botao secundario pequeno"`
   (nova classe `.botao.pequeno`, padding reduzido pra caber em linha de tabela). Link
   inline dentro de frase (ex. "Ver todas »" no dashboard) foi mantido como texto/não virou
   botão — é prosa, não uma ação de linha de tabela.

2. **Nome dos instrumentos simplificado.** `Instrumento.nome` mostrava o texto bruto do
   seed ("COPSOQ adaptado - RR Revestir Ltda", "Inventário de Trabalho e Risco de
   Adoecimento (Mendes & Ferreira, 2007)") em todo lugar — dropdown de Aplicação, tabela
   de Aplicações do GHE, checkbox de Relatório. Agora `instrument_name` nos seeds
   (`seeds/copsoq_rr_revestir.json`, `seeds/itra.json`) é só "COPSOQ"/"ITRA"; a origem
   ("empresa piloto RR Revestir", citação Mendes & Ferreira) foi realocada pro campo
   `fonte` (já existia no model `Instrumento`, só não era populado). Novo campo JSON
   opcional `instrument_description` nos dois seeds alimenta `Instrumento.descricao`
   (também já existia no model) com uma explicação em linguagem de negócio de quando
   usar cada instrumento — `load_instrumentos.py` foi atualizado pra mapear essa chave;
   os seeds continuam sendo a fonte de verdade, carregados via comando, nunca
   redigitados nos models (CLAUDE.md Seção 0).

3. **Formulário de Nova Aplicação ficou dinâmico/guiado.** `AplicacaoForm`
   (`avaliacoes/forms.py`) e `aplicacao_form.html` agora mostram, logo abaixo do campo
   Instrumento, uma legenda que troca conforme a seleção (lida de
   `Instrumento.descricao` via um `<script type="application/json">` + JS puro, sem
   framework) — resolve o pedido de "instruções de como saber qual selecionar, guiar o
   usuário".

4. **Variante do instrumento (GHE) parou de mostrar só o código.** Antes o dropdown
   listava "GHE01"/"GHE02" sem dizer o que significavam. Novo campo
   `Dominio.ghe_variante_nome` (migração `instrumentos/migrations/0002_...`) é
   preenchido a partir do `ghe_name` que já existia no seed do COPSOQ (não foi
   inventado — já estava no JSON, só não era lido); `load_instrumentos.py` agora grava
   esse valor. O dropdown mostra "GHE01 — Auxiliar Administrativo" e uma legenda
   dinâmica abaixo confirma a seleção ("Você selecionou: GHE01 — Auxiliar
   Administrativo"), no mesmo padrão do item 3.

5. **Critério de cálculo parou de mostrar só "v1.0".** `AplicacaoForm` e `RelatorioForm`
   agora sobrescrevem `label_from_instance` do campo `criterio_versao` pra mostrar
   `"v1.0 (Aguardando ratificação do profissional responsável)"` — usa
   `get_status_display()`, já existente em `CriterioVersao.status`, só não estava
   sendo mostrado na hora de escolher a versão.

6. **`RelatorioForm.aplicacoes` parou de mostrar o `__str__` técnico de `Aplicacao`**
   (ex. `"COPSOQ_RR_REVESTIR @ Auxiliar Administrativo — Unidade Matriz (Construtora
   Boa Vista Ltda) (Concluída)"`, que usa `instrumento.codigo`) — `label_from_instance`
   agora monta `"{instrumento.nome} — {ghe.nome} ({status})"`, consistente com o nome
   simplificado do item 2.

7. **Tabela "Resultados por domínio" do detalhe da Aplicação mostrava "Classificação" e
   "Banda" lado a lado sem explicar a diferença** (ex.: D1 aparecia com Classificação
   "Moderado" e Banda "Aceitável"; D9 com Classificação "Moderado" e Banda "Alto" — os
   dois valores existem e são coerentes com a Seção 7.3 vs 7.6, mas nada na tela
   explicava a diferença). Corrigido com um parágrafo explicativo acima da tabela em
   `aplicacao_detail.html`: Classificação = nível bruto do domínio (só respostas,
   Seção 7.3); Banda = resultado final depois de cruzar com a probabilidade (Seção
   7.6) — é a Banda que define ação/prazo.

8. **Seção "GHEs" aparecia antes de "Funções" no detalhe da Unidade com o mesmo peso
   visual**, sem explicar a relação entre as duas. O usuário decidiu explicitamente
   **não reordenar as seções** — só aproximar o texto ("por que usar um e não outro?
   por que os dois?"). Resolvido em `unidade_detail.html`: cartão de GHEs ganhou um
   parágrafo "Comece aqui" explicando que GHE é obrigatório (é quem responde o
   questionário) e Funções é opcional (só marca cargos dentro de um GHE); cartão de
   Funções ganhou o rótulo "(opcional)" no `<h2>`, texto explicando que não é um
   cadastro paralelo ("é um detalhe que você anexa a um GHE"), e o botão "+ Nova
   função" foi rebaixado de `.botao` (navy, ação primária) pra `.botao.secundario`
   (cinza claro) — reforça visualmente a mesma mensagem sem mudar a ordem das seções.

9. **Criar um GHE sem nenhuma Função cadastrada perdia o que já tinha sido digitado**
   ao clicar em "criar uma função". Corrigido com a solução mais simples que não muda
   comportamento de navegação sem avisar: o link em `ghe_form.html` ganhou
   `target="_blank" rel="noopener"` ("criar uma numa aba nova") — o formulário de GHE
   em andamento fica intacto na aba original.

10. **Bônus encontrado durante a verificação manual**: `Aplicacao.instrumento_ghe_variante`
    mostrava só o código ("GHE01") no detalhe da Aplicação, mesmo depois do dropdown do
    formulário já mostrar o nome amigável (item 4). Nova property
    `Aplicacao.variante_nome` (`avaliacoes/models.py`) busca o `Dominio.ghe_variante_nome`
    correspondente; `aplicacao_detail.html` agora mostra "Variante: GHE01 — Auxiliar
    Administrativo". `relatorios/painel_views.py`/`home.html` também trocaram
    `aplicacao.instrumento.codigo` (técnico) por `.nome` (amigável) na listagem do
    dashboard, pelo mesmo motivo do item 6.

**Cobertura de teste**: suíte completa (52 testes) segue passando sem alteração em nenhuma
das duas sessões desta rodada — todos os itens são de estilo (CSS), texto/label
(`label_from_instance`, `help_text`, seeds) ou uma property de leitura
(`Aplicacao.variante_nome`), sem mudança de regra de negócio ou de validação. Verificado
manualmente no navegador em cada item das duas sessões.

---

## 6.5 Realinhamento: remoção do conceito de variante-por-GHE (2026-07-18)

> O usuário reportou confusão persistente no formulário de Nova Aplicação ("instrumento, variante
> do instrumento, critério de cálculo... por que só tem opção de Auxiliar Administrativo e
> Almoxarife? isso não tem sentido pra mim") e pediu uma análise de divergência: reler o Excel
> (`CRARP - CHECKLIST...xlsx`) e o PDF (`Formulario_Aplicacao_COPSOQ_RR_Revestir.pdf`) originais e
> entender onde o sistema construído tinha se afastado do que ele pediu.

**Diagnóstico.** O Excel original (fonte de verdade do ITRA) é **100% genérico**: uma única aba
"AMOSTRA 01", com as 5 escalas do ITRA e dois campos de texto livre no topo ("SETOR:"/"CARGO:")
vazios, pensados para serem preenchidos por qualquer empresa/GHE — sem nenhum cargo fixo, sem
nenhuma menção a "Auxiliar Administrativo" ou "Almoxarife". O PDF, por outro lado, é o formulário
**já preenchido para uma empresa específica** (RR Revestir), com os domínios D1–D4 do COPSOQ
escritos sob medida para dois cargos exatos daquela empresa. Numa sessão anterior, o texto desses
itens foi copiado literalmente do PDF pro seed do COPSOQ, e a customização por cargo virou um
campo de modelo (`Dominio.ghe_variante`, `Aplicacao.instrumento_ghe_variante`) — o que fez sentido
tecnicamente (plugabilidade, Seção 3 princípio 1), mas na prática deixou **apenas duas opções
possíveis** no dropdown de variante, ambas de uma empresa-piloto usada só como referência, sem
nenhuma forma de o gestor cadastrar os cargos da própria empresa dele. Esse era o ponto real de
divergência: o objetivo do usuário era um sistema genérico (como o Excel já era para o ITRA), e o
COPSOQ tinha ficado hardcoded numa única empresa de exemplo.

**Decisão** (usuário escolheu entre 3 opções apresentadas): **generalizar o COPSOQ** — reescrever
D1–D4 em linguagem genérica (sem cargo específico), na mesma linha de D5–D9 (que já eram
genéricos) e do ITRA inteiro (que já era genérico desde o Excel). Eliminar por completo o conceito
de variante por GHE — não é mais necessário nenhum cadastro de "variante" por empresa; o mesmo
COPSOQ (9 domínios) e o mesmo ITRA (5 escalas) servem pra qualquer GHE de qualquer empresa, do
jeito que o Excel já demonstrava ser o padrão esperado. Dados de teste existentes foram descartados
(usuário confirmou que eram só teste) e o banco foi recriado do zero.

**O que mudou:**

1. **`seeds/copsoq_rr_revestir.json` generalizado**: estrutura achatada em `"domains"` (mesmo
   formato do ITRA, sem mais `"ghes"` aninhado por cargo); os 5 itens de D1 e os itens variáveis
   de D2.4/D3.4/D4.1 foram reescritos em linguagem genérica (ver texto completo na Seção 5.1). A
   origem/adaptação da RR Revestir continua documentada em `source_note` (→ `Instrumento.fonte`),
   só não determina mais o texto dos itens.
2. **Campos removidos do banco** (migrations `instrumentos/migrations/0003_...` e
   `avaliacoes/migrations/0007_...`): `Dominio.ghe_variante`, `Dominio.ghe_variante_nome`,
   `Aplicacao.instrumento_ghe_variante`. A property `Aplicacao.variante_nome` também foi removida.
   `Dominio` agora tem unicidade só por `(instrumento, codigo)`.
3. **`load_instrumentos.py` simplificado**: `_entradas_de_dominio()` só reconhece `"domains"` ou
   `"scales"` — não existe mais a variante de seed aninhada por cargo (`"ghes"`).
4. **`avaliacoes/services/calculo_risco.py`**: `dominios_da_aplicacao()` volta a ser um filtro
   simples por instrumento (sem `Q(ghe_variante...)`); a chave de threshold no `CriterioVersao`
   é só `dominio.codigo` (era `codigo:variante`).
5. **`AplicacaoForm`/`aplicacao_form.html`**: campo "Variante do instrumento (GHE)" removido do
   formulário e da tela de detalhe da Aplicação. Sobra só "Instrumento" (com a legenda dinâmica
   já existente, Seção 6.4 item 3) — nenhum cargo fixo aparece em lugar nenhum do fluxo.
6. **Testes**: os 4 testes de validação de variante (`test_aplicacao_*_variante_*`) foram removidos
   por não terem mais objeto; a fixture compartilhada `aplicacao_copsoq_ghe01` virou
   `aplicacao_copsoq` (sem `instrumento_ghe_variante`) e `responder_dominio()` perdeu o parâmetro
   `ghe_variante`. Suíte: 48 testes passando (52 → 48, após remover os 4 testes obsoletos).
7. **Verificado manualmente**: criada uma Empresa/Unidade/GHE nova do zero com um cargo qualquer
   ("Operador de Máquina Injetora", sem nenhuma relação com RR Revestir), aplicação COPSOQ criada
   sem exigir variante nenhuma, questionário público mostrando os 9 domínios com texto genérico
   ("Ritmo de trabalho elevado em relação ao tempo disponível para realizar as tarefas.") — confirma
   que qualquer empresa consegue usar o sistema sem ficar presa aos dois cargos da RR Revestir.

**Nota sobre a Seção 6.3/6.4**: os itens 1 (crítico: validar `instrumento_ghe_variante`) da Seção
6.3 e os itens 2 (parcial), 4 e 10 da Seção 6.4 descrevem uma funcionalidade (variante por GHE)
que foi removida nesta sessão — o texto original foi mantido como registro histórico de por que
aquelas decisões foram tomadas na época, não porque a funcionalidade ainda existe.

---

## 6.6 Redução de fricção na tela de Nova Aplicação (2026-07-18)

> Pedido do usuário, analisando a tela como o gestor que abre uma rodada de coleta: dos 6 campos
> do formulário, só "Instrumento" e "Tipo" são decisões reais na maioria dos casos — os outros 4
> têm resposta óbvia quase sempre (uma única versão de critério, um único usuário no sistema,
> "hoje" como data, justificativa em geral vazia), mas apareciam todos com o mesmo peso visual.

**O que mudou** (`avaliacoes/forms.py::AplicacaoForm`, `aplicacao_form.html`,
`avaliacoes/painel_views.py::aplicacao_create/aplicacao_update`):

1. **Critério de cálculo**: deixa de ser dropdown por padrão. `AplicacaoForm` pré-seleciona
   automaticamente o `CriterioVersao` ratificado mais recente (sem nenhum ratificado, o mais
   recente mesmo assim — `criado_em` decrescente) e a tela mostra só uma linha "Critério: v1.0
   (Aguardando ratificação...)". O dropdown (com o link "usar outra versão") só aparece quando
   `CriterioVersao.objects.count() > 1` — hoje é sempre 1, então nunca aparece na prática. Quando
   colapsado, o valor segue pro backend via `{{ form.criterio_versao.as_hidden }}`.
2. **Responsável aplicador**: pré-selecionado com `request.user` (passado como `usuario_logado=`
   pro form). A tela mostra "Responsável aplicador: Você (username)" em vez de dropdown; o
   dropdown só aparece se houver mais de um usuário `is_staff=True` no banco (hoje só existe um).
3. **Data da aplicação**: pré-preenchida com a data de hoje (`timezone.now().date()`), continua
   sendo um campo de data normal e editável — só o valor inicial mudou. **Achado durante a
   implementação**: o widget `forms.DateInput(attrs={"type": "date"})` não formatava o valor
   inicial como ISO (`YYYY-MM-DD`), que é o único formato que o `<input type="date">` do HTML5
   aceita — o navegador descartava o valor silenciosamente e o campo aparecia vazio. Corrigido
   adicionando `format="%Y-%m-%d"` ao widget.
4. **Justificativa da escolha do instrumento**: continua opcional, mas nasce recolhida atrás de um
   link "+ Adicionar justificativa" — só aparece expandida por padrão se a Aplicacao (em edição)
   já tiver esse campo preenchido.
5. **Tipo**: pré-selecionado "Anônima" (coerente com a Seção 3, princípio 3 — anônima é o padrão
   do produto), mas continua sempre visível como dropdown — é uma decisão real, só já vem
   respondida do jeito mais comum.

**Resultado**: a tela passa a ter 2 decisões em destaque (Instrumento vazio pra escolher; Tipo
pré-marcado "Anônima") e o resto em segundo plano (informação ou campo recolhido), sem perder a
possibilidade de ajustar manualmente os casos atípicos (reabrir aplicação com critério antigo,
mais de um gestor no sistema, data retroativa, justificativa registrada).

**Cobertura de teste**: suíte completa (48 testes) segue passando sem alteração — a mudança é de
UI/inicialização de formulário, não de validação; os testes que fazem POST direto continuam
enviando todos os campos explicitamente. Verificado manualmente no navegador: criação de
Aplicacao com os campos colapsados, expansão de "usar outra versão"/"+ Adicionar justificativa",
e submissão completa confirmando que os valores ocultos (`criterio_versao`,
`responsavel_aplicador`) chegam corretos no servidor.

---

## 6.7 Link único de resposta + perfil + perguntas abertas (2026-07-19)

> Pedido do usuário após testar o MVP: (1) o painel gerava um link por respondente —
> acordado que um único link universal por Aplicacao basta; (2) o consentimento não
> tinha a declaração "Li e compreendi..."; (3) faltavam perguntas de perfil (tempo na
> organização, modalidade de trabalho) antes do questionário; (4) faltavam perguntas
> abertas ao final.

**O que mudou:**

1. **Link único por Aplicacao**: novo `Aplicacao.token` (UUID) é o único link público
   (`/responder/<token>/`), o mesmo para todos os participantes de um GHE. Removido
   `Respondente.token` — cada visitante agora é identificado pela **sessão do
   navegador** (`request.session`, chave por Aplicacao), e um novo `Respondente` é
   criado sob demanda no primeiro consentimento daquela sessão (alias sequencial
   automático). Reabrir o link no mesmo navegador retoma de onde parou; um navegador
   diferente é tratado como uma pessoa nova. Removidos: `GerarLinksForm`,
   `services/links.py::gerar_respondentes`, a tela de geração em lote no painel e no
   Django Admin, e o `RespondenteInline` editável (agora só leitura — os respondentes
   nascem pelo link, não são mais pré-criados).
2. **Status "Concluída" virou ação manual do gestor**: sem um conjunto fixo de
   respondentes esperados, não há como detectar automaticamente "todo mundo
   terminou" — sempre pode chegar mais alguém pelo mesmo link. `atualizar_status_aplicacao`
   só faz mais a transição `rascunho -> em_andamento`; a transição para `concluída`
   agora é `services/aplicacao_status.py::encerrar_coleta`, disparada pelo botão
   "Encerrar coleta" na tela da Aplicacao (com `confirm()`, mesmo padrão da
   assinatura de relatório). Uma vez encerrada (ou cancelada), o link mostra uma
   página "esta coleta já foi encerrada" e não aceita respondentes novos — quem já
   tinha terminado continua vendo sua própria tela de agradecimento normalmente.
3. **Consentimento com duas declarações obrigatórias**: além de "concordo em responder
   de forma voluntária...", nova checkbox "Li e compreendi a finalidade, a forma de
   uso e os limites deste formulário." — as duas são `forms.BooleanField(required=True)`,
   validadas no servidor (`avaliacoes/views.py::ConsentimentoForm`).
4. **Perfil do respondente** (`avaliacoes/views.py::PerfilRespondenteForm`), etapa nova
   entre o consentimento e o primeiro domínio: "Tempo na organização" (5 faixas, de
   "menos de 6 meses" a "mais de 5 anos") e "Modalidade predominante de trabalho"
   (Presencial/Remoto/Híbrido), ambos obrigatórios. Quando `Aplicacao.tipo ==
   identificada`, o formulário ganha também um campo "Nome" obrigatório (a
   identificação nesse caso acontece aqui, não mais por pré-cadastro no Admin).
   Campos novos em `Respondente`: `tempo_na_organizacao`, `modalidade_trabalho`.
5. **Perguntas abertas ao final** (`avaliacoes/views.py::PerguntasAbertasForm`), depois
   do último domínio e antes da tela de conclusão: "Qual mudança na organização do
   trabalho mais ajudaria a reduzir riscos?" e "Há algum fator importante que não foi
   abordado?" — ambas opcionais (texto livre, não entram no cálculo de risco).
   Campos novos em `Respondente`: `resposta_aberta_1`, `resposta_aberta_2`,
   `perguntas_abertas_respondidas_em` (marca que a etapa foi vista, mesmo em branco).
6. **`_proximo_passo(respondente)`** centraliza toda a lógica de "qual a próxima etapa"
   num único lugar em `avaliacoes/views.py` (perfil pendente → domínio pendente →
   perguntas abertas pendentes → concluído), chamado depois de cada ação do fluxo —
   evita duplicar essa cadeia de decisão em cada view.

**Cobertura de teste**: suíte completa (53 testes). Novos testes cobrem: as duas
declarações de consentimento obrigatórias, criação de Respondente sob demanda,
redirecionamento pra perfil quando incompleto, fluxo completo até perguntas
abertas/conclusão, retomada no mesmo navegador, dois navegadores diferentes gerando
dois respondentes distintos, bloqueio de novo respondente após "encerrar coleta", e
exigência do campo "Nome" quando a aplicação é identificada.

---

## 6.8 Separação admin (SaaS) x empresa cliente (2026-07-27)

> O usuário percebeu que `/painel/` era um painel só — sem nenhuma separação entre "quem
> opera o SaaS" e "a empresa cliente que comprou o serviço". Pediu uma análise de todas
> as páginas existentes, classificando cada uma como função do admin ou da empresa, e a
> separação real do painel a partir disso.

**Diagnóstico**: não existia NENHUM vínculo entre `User` e `Empresa` — qualquer gestor
logado via `gestor_required` (`is_staff=True`) enxergava e editava os dados de **todas**
as empresas cadastradas (confirmado ao vivo: dashboard somava relatórios/aplicações de
todas as empresas juntas). O painel era, na prática, 100% admin — só que sem controle de
acesso nenhum.

**Decisões do usuário** (perguntas feitas via AskUserQuestion):
1. Parecer da IA e assinatura do relatório: **sempre admin** — "o SaaS é parte de um
   serviço que vai oferecer... o segundo serviço é com base no questionário fazer um
   plano de ação, então só faz sentido o profissional do SaaS".
2. Unidade/Função/GHE: **tanto admin quanto empresa podem criar** — não é exclusivo de
   um lado.
3. Vínculo usuário↔empresa: **1 gestor por empresa no MVP** (evolui pra N:N depois se
   for preciso).
4. **`PerfilProfissional` é só do admin** — a empresa só vê quem é o profissional
   responsável e a assinatura dele (quando esse módulo for detalhado).
5. Módulos ainda não especificados pelo usuário (Relatório, Parecer da IA do lado da
   empresa, Configurações de Classificação de Risco) **não devem ser construídos/
   deduzidos agora** — viram uma página genérica "em execução" até serem detalhados.

**O que foi implementado:**

1. **`Empresa.gestor`** (`OneToOneField` pra `User`, nullable) — o único usuário que
   acessa o painel em nome daquela empresa.
2. **`avaliacoes/services/tenancy.py`**: `eh_admin(user)` (`is_superuser`),
   `empresa_do_usuario(user)` (via `user.empresa_gerenciada`), `empresas_visiveis(user)`
   (queryset: todas se admin, só a própria se gestor de empresa, vazio se nenhuma).
3. **`avaliacoes/decorators.py::admin_required`**: encadeia com `gestor_required` e
   levanta `PermissionDenied` (403) se `not user.is_superuser` — nunca redireciona pro
   login (o usuário já está autenticado, só não tem essa permissão).
4. **Escopo aplicado em todas as views compartilhadas** (`avaliacoes/painel_views.py`):
   `empresa_detail`, `unidade_*`, `funcao_create`, `ghe_*`, `aplicacao_*` resolvem o
   objeto pelo pai filtrado por `empresas_visiveis(request.user)` (`_empresa_ou_404`,
   `_unidade_ou_404`, `_ghe_ou_404`, `_aplicacao_ou_404`) — um gestor de empresa que
   tentar acessar um pk de outra empresa recebe **404**, não 403 (não revela nem que o
   recurso existe).
5. **`empresa_list`/`empresa_create`/`empresa_update` viram `admin_required`** — onboarding
   de empresa nova é sempre admin.
6. **`empresa_criar_gestor`** (view + form `CriarGestorForm` + template): admin cria o
   usuário-gestor de uma empresa a partir do detalhe dela (`empresa_detail.html` ganha
   um card "Acesso do gestor" visível só pro admin).
7. **`relatorios/painel_views.py` inteiro virou `admin_required`** (exceto `painel_home`,
   que é compartilhada e escopada por `empresas_visiveis`) — `relatorio_list`,
   `relatorio_create`, `relatorio_detail`, `relatorio_parecer_editar`,
   `relatorio_gerar_parecer_ia`, `relatorio_gerar_pdf`, `relatorio_assinar`,
   `meu_perfil`.
8. **Página genérica "em execução"** (`templates/painel/em_execucao.html` +
   `avaliacoes/painel_views.py::em_execucao`) usada em 3 rotas novas: "Relatórios" e
   "Análise da IA" do lado da empresa (`painel_avaliacoes:relatorios_empresa`,
   `:analise_ia_empresa`), e "Configurações de Classificação de Risco" do lado do admin
   (`:configuracoes_risco`) — nenhum desses módulos foi desenhado/deduzido, só reservado
   o lugar.
9. **Navegação lateral (`_base.html`) por papel**, via `avaliacoes.context_processors.tenancy`
   (novo context processor, injeta `eh_admin`/`empresa_do_usuario` em todo template):
   admin vê Início/Empresas/Relatórios/Configurações de risco/Meu perfil; gestor de
   empresa vê Início/Minha empresa/Relatórios (stub)/Análise da IA (stub).
10. **`unidade_detail.html`**: botão "Novo relatório desta unidade" e o aviso associado
    só aparecem pro admin (a view real de criação de Relatorio agora é admin-only).
11. **`relatorios/templates/painel/home.html`**: seção "Relatórios aguardando
    revisão/assinatura" e o link "Ver todas" (lista global de empresas) só aparecem pro
    admin; "Aplicações em andamento" continua visível pros dois, já escopada.

**Cobertura de teste**: suíte completa (56 testes, 3 novos): `test_empresa_create_exige_admin`
(gestor de empresa comum recebe 403 ao tentar criar empresa),
`test_gestor_de_empresa_so_ve_a_propria_empresa` (404 ao tentar acessar outra empresa,
403 na lista global), `test_admin_cria_acesso_de_gestor` (fluxo completo de criação de
acesso). Fixtures `gestor` de `avaliacoes/test_painel_views.py` e
`relatorios/test_painel_views.py` passaram a ser `is_superuser=True` — representam o
admin nos testes que exercitam fluxos cross-empresa que só ele pode fazer.

---

## 6.9 Alinhamento com o Excel de referência (`Relatorio_Semaforo_Dados_Simulados.xlsx`) (2026-07-27)

> O usuário forneceu uma planilha de referência com dados simulados (13 abas) e pediu o
> alinhamento do sistema com ela, ponto a ponto, via 12 prompts autocontidos entregues em
> `prompts/`. Execução sequencial (um prompt por vez, revisado antes do próximo): 02 → 01 → ...

**Prompt 02 — Configuração** (escala e prevalência): motor de cálculo migrado de escala
1–5 para **escala 0–100** (`valor_ajustado * 100 / amplitude`, RISCO/PROTETIVO invertidos
item a item antes de agregar — mesma regra da Seção 7.1, só a normalização final muda).
Thresholds de baixo/elevado recalculados proporcionalmente em `risk_engine.py`
(`LIMITE_BAIXO_DEFAULT=37.5`, `LIMITE_ELEVADO_DEFAULT=62.5`) e nos seeds (COPSOQ e ITRA).
N mínimo de confidencialidade subiu de 3 para 5 (`N_MINIMO_RESPONDENTES`). Nova métrica de
**prevalência por domínio** (`calcular_prevalencia()`): percentual de respondentes com
escore ≥ limite_elevado define uma prioridade P1 (≥50%) / P2 (≥25%) / P3 (<25%), persistida
em `EscoreDominio.percentual_elevados`/`.prioridade`. `CriterioVersao` ganhou os 4 novos
parâmetros versionados (`limite_baixo`, `limite_elevado`, `prevalencia_p1`,
`prevalencia_p2`) — nunca hardcoded fora do critério versionado (Seção 7.8).

**Prompt 01 — Form Responses 1**: confirmado que `Respondente`/`Resposta` já cobrem todos
os campos da aba (`tempo_na_organizacao`, `modalidade_trabalho`, `resposta_aberta_1/2`,
resolução de GHE via token da Aplicacao). Único ponto de divergência real: as faixas de
`TempoNaOrganizacao` tinham 5 opções (`"Menos de 6 meses"` → `"Mais de 5 anos"`) enquanto o
Excel usa 4 (`"Menos de 1 ano"`, `"1 a 2 anos"`, `"3 a 5 anos"`, `"Mais de 5 anos"`) —
**o Excel é a referência do produto final**, então o `TextChoices` foi reduzido pras 4
faixas do Excel (`avaliacoes/models.py::TempoNaOrganizacao`). Nenhuma outra mudança de
modelo foi necessária.

**Cobertura de teste**: suíte completa (62 testes) passando após os dois prompts.

**Prompt 04 — Pontuação Anônima** (escore por respondente + mapa de calor): a planilha
`Pontuacao_anonima` mostra uma linha por respondente (não a média agregada do domínio) —
gap real do modelo anterior, que só guardava `EscoreDominio` (média de todos). Novo model
`EscoreRespondente` (`avaliacoes/models.py`): escore 0-100 e classificação de UM
respondente em UM domínio, único por `(respondente, dominio)`. `calcular_dominio()`
(`avaliacoes/services/calculo_risco.py`) agora persiste um `EscoreRespondente` por
respondente ANTES de agregar — `EscoreDominio.escore` continua sendo a média desses
escores individuais, nunca calculado ao contrário. Novo campo `Respondente.indice_geral`
(nullable, recalculado por `_recalcular_indice_geral()` a cada domínio novo respondido) =
média dos `EscoreRespondente` já existentes daquele respondente — corresponde à coluna
"Índice geral" do Excel; domínios ainda não respondidos simplesmente não entram na média
(índice parcial até a aplicação terminar).

Nova tela **admin-only** `painel_avaliacoes:pontuacao_anonima`
(`avaliacoes/painel_views.py::pontuacao_anonima`, acessível a partir do detalhe da
Aplicacao) mostra a tabela completa com mapa de calor: verde (0) → amarelo (50) → vermelho
(100), interpolado a partir das mesmas cores dos badges de risco já usados no resto do
painel (`--teal-500`/`--amber-500`/`--red-500` de `templates/painel/_base.html`,
suavizadas com 55% de branco pra não competir com o texto) — `_cor_heatmap()` calcula a
cor em Python e passa `style="background-color: ..."` pronto pro template, sem filtro de
template nem CSS externo. Mesma decisão de escopo do parecer da IA (Seção 6.8): esta tela
expõe granularidade por respondente (embora sem nome, só alias), então fica restrita ao
admin — o gestor da empresa não vê.

**Cobertura de teste**: suíte completa (65 testes, 3 novos):
`test_calcular_dominio_cria_escore_por_respondente`,
`test_indice_geral_e_media_dos_dominios_ja_respondidos` (em `avaliacoes/tests.py`) e
`test_pontuacao_anonima_mostra_escore_por_respondente_e_indice_geral` (em
`avaliacoes/test_painel_views.py`).

**Prompt 05 — Alertas Agregados D9**: a planilha `Alertas_agregados` mostra, por GHE, quantos
respondentes marcaram um item de evento grave (D9.1/D9.2 no COPSOQ) com valor ≥ limiar —
diferente de `ClassificacaoRisco.evento_grave_confirmado` (booleano por domínio calculado,
usado na matriz de risco da Seção 7.5/7.6), que não conta PESSOAS. Nova função
`avaliacoes/services/calculo_risco.py::contar_alertas_d9()` conta respondentes distintos com
`Resposta.valor_bruto >= criterio_versao.limiar_evento_grave` em qualquer `Item.evento_grave=True`
do instrumento (agnóstico de instrumento — não hardcoda "D9"), e novo campo
`Aplicacao.alertas_d9` persiste o resultado. Recalculado dentro do próprio `calcular_dominio()`
(não só em `calcular_aplicacao()`) porque o fluxo real do questionário
(`avaliacoes/views.py::responder_dominio`) chama `calcular_dominio()` por domínio, nunca
`calcular_aplicacao()` inteiro — sem isso o alerta só apareceria depois de uma chamada manual.

Duas telas novas, ambas **admin-only** (mesma lógica de escopo da Seção 6.8 — dado agregado
mas sensível): (1) seção "Alertas D9" no detalhe da Aplicação
(`avaliacoes/templates/painel/aplicacao_detail.html`), com banner vermelho e texto "Ativar
fluxo protegido imediato" quando `alertas_d9 > 0`; (2) nova view
`painel_avaliacoes:alertas_agregados` (por Unidade, uma linha por GHE/Aplicacao — reproduz a
tabela do Excel), linkada a partir do detalhe da Unidade.

**Cobertura de teste**: suíte completa (67 testes, 2 novos):
`test_contar_alertas_d9_conta_respondentes_com_evento_grave` (`avaliacoes/tests.py`) e
`test_alertas_agregados_lista_alertas_d9_por_ghe` (`avaliacoes/test_painel_views.py`).

**Prompt 06 — Diagnóstico GHE** (prevalência como critério de prioridade): a planilha
`Diagnostico_GHE` prioriza por **prevalência** (P1/P2/P3, já calculada no Prompt 02), não
pela matriz Severidade × Probabilidade da Seção 7.6 — que continua calculada e persistida
em `ClassificacaoRisco` (rastreabilidade com a base legal original), mas deixou de ser o
diagnóstico primário exibido ao gestor. Nova entrada `AGRUPAR` em `risk_engine.Prioridade`
e em `avaliacoes.models.PrioridadeChoices` (campo `EscoreDominio.prioridade` ampliado de
`max_length=2` pra `10`): sobrescreve P1/P2/P3 sempre que o domínio está suprimido por
confidencialidade — do contrário a prioridade sozinha vazaria uma leitura do resultado que a
supressão deveria esconder (mesmo princípio da Seção 3.3 aplicado a mais um campo).

`avaliacoes/services/calculo_risco.py::diagnostico_ghe(aplicacao)` monta a linha completa
por domínio (N, escore, % elevados, classificação, prioridade, alerta protegido, nota
técnica) a partir dos `EscoreDominio` já calculados — nunca recalcula nada, só lê e formata.
"Alerta protegido" só aparece pra domínios com pelo menos um `Item.evento_grave=True`
(verificado de forma agnóstica de instrumento, não hardcoda "D9"), reaproveitando
`contar_alertas_d9()` do Prompt 05. `NOTAS_TECNICAS` é um dicionário fixo por
`Prioridade` (P1/P2/P3/AGRUPAR), com `{n_minimo}` preenchido a partir de
`CriterioVersao.n_minimo_respondentes` — nunca hardcoded no template.

Nova tela **admin-only** `painel_avaliacoes:diagnostico_ghe`, linkada a partir do detalhe da
Aplicação, reproduzindo a tabela do Excel com badges coloridos por prioridade (P1
vermelho/crítico, P2 amarelo/moderado, P3 verde/aceitável, AGRUPAR cinza).

**Cobertura de teste**: suíte completa (74 testes, 7 novos, todos em
`avaliacoes/tests.py` exceto o último): `test_diagnostico_ghe_prioridade_p1_maioria_elevada`,
`test_diagnostico_ghe_prioridade_p2_minoria_significativa`,
`test_diagnostico_ghe_prioridade_p3_poucos_elevados`,
`test_diagnostico_ghe_agrupar_quando_n_abaixo_do_minimo`,
`test_diagnostico_ghe_alerta_protegido_d9`, `test_diagnostico_ghe_sem_alerta_protegido_d9`,
`test_diagnostico_ghe_mostra_prioridade_e_nota_tecnica` (`avaliacoes/test_painel_views.py`).

**Prompt 07 — Catálogo de Ações Pré-definidas**: a planilha `Catalogo_Acoes` do Excel de
referência tem 18 linhas (9 domínios × Moderado/Elevado — D9 "Elevado" corresponde ao
rótulo "Elevado/alerta" da planilha original, o nível que aciona o fluxo protegido).
Extraída diretamente do arquivo `Relatorio_Semaforo_Dados_Simulados.xlsx` (aba
`Catalogo_Acoes`) — nenhuma linha foi inventada. Novo modelo `CatalogoAcao`
(`avaliacoes/models.py`), único por `(dominio, nivel)`; novo `HierarquiaControle`
(6 categorias — só 3 usadas nos dados atuais: eliminação/redução na fonte, organização do
trabalho, gestão/organização, mais resposta imediata pro D9 elevado). Seed em
`seeds/catalogo_acoes.json`, carregado por `instrumentos/management/commands/load_catalogo_acoes.py`
(idempotente, `update_or_create` por domínio+nível — precisa do instrumento já carregado
via `load_instrumentos`).

`PlanoDeAcao` ganhou os campos `hierarquia` e `indicador`.
`_gerar_plano_de_acao_se_necessario()` (`avaliacoes/services/calculo_risco.py`) agora busca
`CatalogoAcao.objects.filter(dominio=dominio, nivel=escore_dominio.classificacao).first()` —
se existir, usa `acao_sugerida`/`hierarquia`/`indicador` do catálogo; senão, cai de volta no
texto genérico anterior ("Definir e executar medida corretiva..."), preservando
compatibilidade com domínios sem entrada no catálogo (ex. instrumentos futuros sem seed
próprio de ações). **Pré-definido pelo seed, mas editável**: nova tela admin-only
`painel_avaliacoes:catalogo_acoes_list`/`catalogo_acoes_update` (link na navegação lateral,
"Catálogo de ações") e Django Admin (`CatalogoAcaoAdmin`) — o profissional responsável pode
personalizar `acao_sugerida`/`hierarquia`/`indicador` pra realidade de cada empresa sem
tocar no seed original.

Fixture compartilhada `instrumentos_carregados` (`conftest.py`) passou a carregar também
`load_catalogo_acoes` — os testes que já geravam `PlanoDeAcao` automaticamente (Prompt 02)
passam a receber a medida do catálogo em vez do texto genérico, sem que nenhum teste
existente dependesse do texto antigo (verificado antes da mudança).

**Cobertura de teste**: suíte completa (77 testes, 3 novos):
`test_plano_de_acao_usa_medida_do_catalogo_quando_existe`,
`test_plano_de_acao_usa_texto_generico_quando_nao_ha_catalogo` (`avaliacoes/tests.py`) e
`test_catalogo_acoes_list_mostra_acoes_e_permite_editar` (`avaliacoes/test_painel_views.py`).

**Prompt 08 — Plano de Ação (15 campos do Excel)**: `PlanoDeAcao` expandido de 6 pra 15
campos, cobrindo a planilha `Plano_de_Acao` do Excel de referência. Novos:
`codigo` (ID manual tipo "A01", gerado automaticamente na criação —
`f"A{str(PlanoDeAcao.objects.count() + 1).zfill(2)}"`), `evidencia_diagnostico` (texto
montado a partir do domínio/classificação/GHE/escore/N no momento do cálculo — nunca
editado depois pelo usuário fora do form), `meta`, `verificacao_eficacia`,
`data_revisao`, `observacoes`. `StatusPlanoDeAcao` ganhou `PLANEJADA` (novo default,
antes era `PENDENTE`) e `CONTINUA` — vocabulário do Excel pra ação formalmente definida
mas não iniciada vs. ação recorrente sem data de término.

**`responsavel` mudou de FK(User) pra CharField livre** — decisão do usuário confirmada
no prompt: o Excel usa nomes de área/cargo ("Direção de Operações", "Gerência
Industrial + SESMT"), não necessariamente um usuário cadastrado no sistema. Migration
gerada como `AlterField` direto (SQLite reconstrói a tabela na migration; sem
`RunPython` de cópia de dados porque o banco de desenvolvimento é só dados de teste,
conforme já registrado na Seção 0). `relatorios/services/pdf.py` perdeu o
`select_related("responsavel")` (não é mais FK, quebraria a query).

O PDF (Seção 7 do Inventário) deixou de ser uma tabela de 6 colunas e virou uma
"ficha" por ação (`.ficha-acao` em `relatorios/templates/relatorios/inventario.html`)
com os 15 campos em pares rótulo/valor — uma tabela de 15 colunas não caberia numa
página A4 impressa. Nova tela admin-only `painel_avaliacoes:plano_de_acao_update`
(`PlanoDeAcaoForm`, todos os 15 campos exceto `classificacao_risco`), acessível a
partir de uma nova seção "Planos de ação" no detalhe da Aplicação
(`aplicacao_detail.html`, admin-only mesma lógica da Seção 6.8).

**Cobertura de teste**: suíte completa (79 testes, 2 novos):
`test_plano_de_acao_gera_codigo_e_evidencia_diagnostico_automaticamente`
(`avaliacoes/tests.py`) e `test_plano_de_acao_update_edita_todos_os_campos`
(`avaliacoes/test_painel_views.py`) — os testes de PDF já existentes
(`test_gerar_pdf_relatorio_minuta_tem_marca_dagua_e_nao_muda_status`,
`test_assinar_relatorio_com_perfil_gera_pdf_final`) seguiram passando sem alteração,
confirmando que o novo template da Seção 7 renderiza corretamente via WeasyPrint.

**Prompt 09 — Entrevista e Observação (checklist de triangulação)**: a planilha
`Entrevista_Observacao` tem 16 itens fixos (6 de entrevista com liderança + 10 de
observação em campo), cada um com conformidade (Conforme/Não conforme/Não avaliado) +
evidência em texto — um complemento **estruturado** a `IndicadorIndireto` (que
continua existindo inalterado, cobrindo absenteísmo/turnover/CAT/etc., mais livres em
tipo). Dois modelos novos: `ItemChecklistTriangulacao` (os 16 itens pré-definidos, via
seed `seeds/checklist_triangulacao.json` + comando `load_checklist_triangulacao`,
idempotente por `(tipo, ordem)`) e `RespostaChecklistTriangulacao` (a resposta do
profissional responsável, única por `(aplicacao, item)` — o checklist é preenchido por
ciclo de coleta, não uma vez só pra sempre).

Nova tela **admin-only** `painel_avaliacoes:checklist_triangulacao`
(`avaliacoes/painel_views.py::_construir_form_checklist` monta um form dinâmico com 2
campos por item — conformidade + evidência —, mesmo padrão de
`avaliacoes/views.py::_construir_form_dominio` do questionário público), linkada do
detalhe da Aplicação. Uma única página com os 16 itens (6 + 10), salva tudo de uma vez.

PDF: nova **Seção 6 "Entrevista e observação"** em
`relatorios/templates/relatorios/inventario.html`, inserida logo depois de "Evidências
complementares" — as seções seguintes foram renumeradas (Parecer técnico 6→7, Plano de
ação 7→8, Assinatura 8→9). Mostra só os itens **avaliados** (exclui
`ConformidadeChecklist.NAO_AVALIADO`) — `relatorios/services/pdf.py::_contexto_relatorio`
ganhou a chave `checklist_triangulacao` por GHE.

**Cobertura de teste**: suíte completa (82 testes, 3 novos):
`test_checklist_triangulacao_get_lista_16_itens`,
`test_checklist_triangulacao_post_salva_respostas` (`avaliacoes/test_painel_views.py`) e
`test_contexto_relatorio_inclui_checklist_triangulacao_avaliado` (`relatorios/tests.py`).

**Prompt 10 — Simulação**: nenhuma mudança de código (planilha SIMULACAO é só painel de
controle de validação do próprio Excel). Rodada uma validação de ponta a ponta com os
dados reais da aba `Pontuacao_anonima` (42 respostas, 4 GHEs) contra `risk_engine.py`:
média por domínio do GHE Administrativo (N=12) bateu exatamente (diff 0,000000) com a
coluna correspondente da aba `SIMULACAO`; supressão por confidencialidade do GHE
Manutenção (N=3) reproduzida corretamente; prevalência/prioridade e classificação por
threshold também conferidas. Nenhuma divergência encontrada.

**Prompt 11 — Semáforo de Riscos**: novo módulo `avaliacoes/services/semaforo.py`
(`calcular_semaforo()` + `leitura_resumida()`) — distribuição percentual de
respondentes em 3 faixas (favorável/intermediário/risco) por domínio, agregando os
`EscoreRespondente` (Prompt 04) de um conjunto de Aplicacoes. Diferente do Diagnóstico
GHE (Prompt 06, uma linha por GHE×domínio), o Semáforo agrega **todas** as Aplicacoes
recebidas num só cálculo — normalmente todas as de uma Unidade ("TOTAL ORGANIZAÇÃO" no
Excel). **Decisão confirmada contra os dados reais do Excel** (42 = 12+18+9+3): GHEs
suprimidos individualmente por N < mínimo entram no agregado da unidade inteira — a
supressão vale só pra exibição isolada do GHE (Diagnóstico GHE, Alertas Agregados),
nunca pra excluir esses respondentes do total. Os limites (`limite_baixo`,
`limite_elevado`) e a prevalência (`prevalencia_p1/p2`) vêm do `CriterioVersao` da
primeira Aplicacao da lista, nunca hardcoded (Seção 7.8).

Nova tela **admin-only** `painel_avaliacoes:semaforo_riscos` (por Unidade, com filtro
`?ghe=<id>` opcional pra ver só um GHE), linkada do detalhe da Unidade. Nova **Seção 5
"Análise semáforo"** no PDF (`relatorios/templates/relatorios/inventario.html`),
inserida logo após "Resultados por GHE e por domínio" — as seções seguintes foram
renumeradas (Evidências complementares 5→6, Entrevista/observação 6→7, Parecer 7→8,
Plano de ação 8→9, Assinatura 9→10). `relatorios/services/pdf.py::_contexto_relatorio`
ganhou `linhas_semaforo`/`resumo_semaforo`, calculados sobre `relatorio.aplicacoes.all()`.

**Cobertura de teste**: suíte completa (86 testes, 4 novos):
`test_calcular_semaforo_classifica_percentuais_por_faixa`,
`test_calcular_semaforo_inclui_ghe_com_n_abaixo_do_minimo_no_agregado`,
`test_leitura_resumida_conta_prioridades_e_aponta_maior_risco` (`avaliacoes/tests.py`) e
`test_semaforo_riscos_mostra_percentuais_e_leitura_resumida` (`avaliacoes/test_painel_views.py`)
— os testes de PDF existentes seguiram passando, confirmando que a nova Seção 5 renderiza
corretamente.

**Prompt 12 — Gráfico Semáforo (barras empilhadas)**: WeasyPrint não roda JS/Chart.js/
canvas, então o gráfico de barras empilhadas horizontais (referência visual: COPSOQ
Manual Portugal 2013, Gráfico 1) foi feito em **HTML/CSS puro** — `div`s com
`display: flex` e `width` percentual por segmento (vermelho/amarelo/verde), texto do
segmento omitido quando < 5% da barra (ilegível nesse tamanho). Em vez de criar uma
seção nova e duplicada, o gráfico foi **inserido dentro da Seção 5 "Análise semáforo"**
já existente (Prompt 11), acima da tabela numérica — mesmos dados
(`calcular_semaforo()`), duas representações. Título "DISTRIBUIÇÃO DOS FATORES
PSICOSSOCIAIS POR FAIXA DE RISCO", subtítulo com grupo analisado + N válido, legenda
colorida e nota de referência ao manual COPSOQ no rodapé — tanto no PDF
(`relatorios/templates/relatorios/inventario.html`) quanto na tela do painel
(`avaliacoes/templates/painel/semaforo_riscos.html`, cores reaproveitadas de
`--red-500`/`--amber-500`/`--teal-500` do design system, em vez dos hex literais do
PDF). `pdf.py::_contexto_relatorio` ganhou `n_total_semaforo` (maior `n_respondentes`
entre os domínios calculados — nem todo domínio necessariamente tem o mesmo N se a
coleta ainda está em andamento).

**Cobertura de teste**: suíte completa (88 testes, 2 novos, ambos em
`relatorios/tests.py`): `test_contexto_relatorio_inclui_grafico_semaforo_com_n_total` e
`test_gerar_pdf_relatorio_inclui_grafico_semaforo` (confirma que o HTML do gráfico não
quebra a geração via WeasyPrint).

Com o Prompt 12, os 12 pontos de alinhamento com `Relatorio_Semaforo_Dados_Simulados.xlsx`
levantados na Seção 6.9 estão implementados.

---

## 6.10 Diagnóstico de UX/UI e correções do fluxo de relatório (2026-07-28)

> O usuário (que também é quem construiu o sistema) testou o ciclo completo como
> usuário de primeira viagem — criar Aplicação, distribuir link, responder com 1
> pessoa, encerrar coleta, criar relatório — e achou o resultado "horrível", sem
> conseguir apontar exatamente o quê. Pediu um diagnóstico completo de UX/UI (não só
> aparência, também funcionalidade e fluxo) e depois pediu para corrigir tudo, na
> ordem de gravidade levantada.

**Achados, em ordem de gravidade, e o que foi corrigido:**

1. **Vazamento de confidencialidade no Semáforo** (crítico): com N=1 respondente na
   unidade, o Diagnóstico GHE e a tela da Aplicação mostravam "SUPRIMIDO" em todos os
   9 domínios, mas o Semáforo de Riscos da mesma unidade mostrava os escores abertos
   — o "agregado da unidade" era, na prática, a resposta de uma única pessoa.
   Corrigido em `avaliacoes/services/semaforo.py::calcular_semaforo()`: agora aplica
   o N mínimo do `CriterioVersao` também no agregado (chave `"suprimido"` por linha);
   `leitura_resumida()` ignora linhas suprimidas. Refletido nos templates do painel
   (`semaforo_riscos.html`) e do PDF (`inventario.html`, Seção 5).

2. **Fluxo terminava em resultado vazio sem nenhum aviso** (crítico): o gestor
   completava coleta → encerramento → relatório inteiro sem nenhum sinal de que N < 5
   suprimiria tudo. Corrigido em `avaliacoes/painel_views.py::aplicacao_detail` e
   `diagnostico_ghe_view`: banners de aviso (`todos_suprimidos`, `todos_agrupar`)
   quando todos os domínios calculados estão suprimidos; aviso explícito no botão
   "Encerrar coleta" quando `n_concluidos < n_minimo`, com confirmação reforçada;
   cards-resumo no topo da Aplicação (N respondentes, domínios calculados, domínios
   em risco, alertas D9) — antes só existiam tabelas cinzas empilhadas.

3. **Relatório podia ser assinado sem parecer técnico** (alto): nada impedia gerar um
   documento "final" com a Seção de parecer vazia. Corrigido em
   `relatorios/services/pdf.py::assinar_relatorio()` — agora levanta `ValueError` se
   `relatorio.parecer_ia` estiver vazio. Novo **stepper visual** em
   `relatorio_detail.html` (Diagnósticos ✓ → Parecer → PDF → Assinatura, com bolinhas
   numeradas/check e trilho colorido) mostrando em que etapa o relatório está; botão
   "Assinar" só aparece quando parecer + PDF + perfil profissional existem, com texto
   explicando o que falta nos outros casos. Botões primário/secundário trocam de
   destaque conforme a etapa atual (antes todos gritavam igual).

4. **Parecer só editável como JSON cru** (alto): a tela de revisão pedia pra editar
   `{"sintese_executiva": ...}` num textarea — inutilizável pro profissional de SST,
   um erro de vírgula quebrava tudo. Novo módulo
   `relatorios/services/parecer_form.py`: sem depender de JavaScript, sempre
   renderiza as linhas já existentes de cada lista (`pareceres_por_dominio`,
   `riscos_prioritarios`, `recomendacoes`) + 3 linhas em branco pra adicionar itens
   novos; o parse no POST usa a mesma contagem calculada no GET. `relatorio_parecer_editar`
   aceita os dois modos (`modo=estruturado` por campo, `modo=json` avançado dentro de
   um `<details>` recolhido) — o JSON cru continua disponível pra quem preferir.

5. **Empresa cliente sem acesso a nenhum resultado** (alto): "Relatórios" e "Análise
   da IA" do lado da empresa eram stubs "em execução" — quem paga pelo serviço não via
   nada da própria coleta. Decisão de escopo mínimo (mantendo Seção 6.8: parecer/
   assinatura continuam admin-only): `avaliacoes/painel_views.py::relatorios_empresa`
   lista os relatórios da própria empresa com status e link de download do PDF **só
   quando assinado**; `analise_ia_empresa` mostra síntese executiva + riscos
   prioritários dos relatórios **já assinados** (minutas não aparecem — a empresa só
   vê análise revisada e assinada pelo profissional responsável).

6. **`IndicadorIndireto` sem tela no painel + checklist sem efeito no cálculo**
   (alto): evidências complementares (Seção 7.5) só existiam no Django Admin —
   inacessíveis pra quem usa o painel; sem elas, a probabilidade de qualquer risco
   ficava travada em 1 e a Banda quase sempre saía "Aceitável" mesmo com domínios
   Elevados. Nova tela admin-only `avaliacoes/painel_views.py::indicadores_indiretos`
   (form + lista, por GHE), linkada do detalhe do GHE e da Aplicação. Além disso,
   `contar_evidencias_convergentes()` (`calculo_risco.py`) passou a receber a
   `Aplicacao` (não só o GHE) e agora também conta uma resposta "Não conforme" no
   checklist de entrevista/observação (Prompt 09) como evidência — antes esse
   checklist existia mas não alimentava o cálculo em nada.

7. **Jargão, parágrafos longos, sem mapa do processo** (médio): textos explicativos
   de 4–8 linhas apareciam como parágrafo corrido em quase toda tela. Convertidos em
   `<details>`/`<summary>` ("saiba mais") em `aplicacao_detail.html`,
   `semaforo_riscos.html` e `diagnostico_ghe.html` — a explicação continua disponível,
   só não ocupa espaço por padrão. Novo acordeão "Como funciona o ciclo completo" no
   dashboard (`relatorios/templates/painel/home.html`) com o mapa de 8 passos do
   processo inteiro. Vazamento de código técnico do instrumento
   (`COPSOQ_RR_REVESTIR`) na tabela "Aplicações incluídas" do relatório trocado pelo
   nome amigável.

8. **Hierarquia visual fraca** (médio): telas de resultado eram só tabelas cinzas
   empilhadas, sem indicar o que precisa de atenção primeiro. Além dos cards-resumo
   do item 2 e do stepper do item 3, os botões de ação do relatório (Gerar parecer /
   Gerar PDF) agora usam `.botao` (destaque) só quando são a próxima etapa pendente e
   `.botao.secundario` quando já foram concluídos e a ação é só "refazer".

**Cobertura de teste**: suíte completa (94+ testes) — novos testes cobrem: supressão
do Semáforo no agregado (`test_calcular_semaforo_suprime_agregado_com_n_abaixo_do_minimo`),
checklist "Não conforme" alterando a probabilidade
(`test_checklist_nao_conforme_conta_como_evidencia_convergente`), assinatura bloqueada
sem parecer (`test_assinar_relatorio_sem_parecer_levanta_erro`), banners de supressão
na Aplicação e no Diagnóstico GHE, CRUD de `IndicadorIndireto` no painel
(`test_indicadores_indiretos_get_e_post`), e as telas da empresa cliente escopando
por status assinado/não assinado (`test_relatorios_empresa_mostra_so_relatorios_assinados_para_download`,
`test_analise_ia_empresa_so_mostra_relatorios_assinados`).

---

## 6.11 Checklist de triangulação vira questionário via link (2026-07-29)

> O usuário percebeu que "Entrevista e observação" (`/painel/aplicacoes/<pk>/checklist-triangulacao/`)
> era um formulário único digitado direto pelo profissional responsável — mas o conteúdo
> real (entrevista com a liderança + observação em campo) deveria ser respondido pelos
> próprios gestores da empresa cliente, não digitado por quem opera o SaaS. Pediu a
> transformação num "questionário" completo, no mesmo espírito do fluxo do colaborador
> (Seção 6.7): link público, abrir/fechar coleta, vários respondentes.

**O que mudou:**

1. **Dois modelos novos** (`avaliacoes/models.py`): `ColetaChecklistTriangulacao` — uma
   rodada de coleta ligada a uma `Aplicacao`, com `token` (UUID, link público) e `status`
   (aberta/encerrada) — e `RespondenteChecklistTriangulacao` — quem responde pelo link,
   identificado por `nome`/`cargo` (diferente do `Respondente` anônimo do colaborador:
   aqui é uma entrevista com a liderança, não uma coleta anônima). `RespostaChecklistTriangulacao`
   passou a ter FK pra `respondente` em vez de `aplicacao` direto, permitindo vários
   respondentes por rodada; unicidade agora é `(respondente, item)`.
2. **Fluxo público** (`avaliacoes/checklist_views.py`, novo módulo, urls em
   `avaliacoes/urls.py` sob `/checklist/<token>/`): identificação (nome/cargo) → grupo
   "Entrevista com liderança" (6 itens) → grupo "Observação em campo" (10 itens) →
   conclusão. Mesmo padrão de sessão do navegador do questionário do colaborador
   (`_get_respondente_da_sessao`), e os mesmos botões Anterior/Próximo/Finalizar da
   Seção anterior. Coleta encerrada mostra `checklist_encerrado.html`.
3. **Painel — acesso compartilhado, decisão explícita do usuário**: diferente de
   `IndicadorIndireto` e das outras evidências agregadas (admin-only, Seção 6.8), abrir
   uma coleta, ver o link e a lista de respondentes é liberado **tanto pro admin quanto
   pro gestor da empresa** — `@gestor_required` em vez de `@admin_required`
   (`avaliacoes/painel_views.py::checklist_triangulacao/checklist_abrir_coleta/checklist_encerrar_coleta`).
   A tela antiga de "digitar respostas direto" foi substituída por uma tela de gestão:
   status da coleta, botão copiar link, lista de respondentes, e uma tabela somente
   leitura das respostas já avaliadas (substitui o formulário editável).
4. **`calculo_risco.py::contar_evidencias_convergentes`** e
   `relatorios/services/pdf.py::_contexto_relatorio` tiveram a query ajustada de
   `RespostaChecklistTriangulacao.objects.filter(aplicacao=...)` para
   `filter(respondente__coleta__aplicacao=...)` — mesma regra de negócio (uma resposta
   "Não conforme" conta como evidência complementar), só muda o caminho do join.
5. **Migração de dados**: `avaliacoes/migrations/0018_checklist_via_link.py` foi escrita
   à mão (não via `makemigrations` interativo) porque trocar o FK direto `aplicacao` por
   `respondente` exigiria um default interativo; a tabela estava vazia em desenvolvimento
   (só dados de teste, Seção 0), então não houve necessidade de migração de dados real.

**Cobertura de teste**: novo arquivo `avaliacoes/test_checklist_views.py` (fluxo público
completo: identificação, os dois grupos, conclusão, botão Anterior, coleta encerrada
bloqueando novo respondente, reabrir o link no mesmo navegador retomando o progresso);
testes antigos de POST direto no painel (`test_checklist_triangulacao_post_salva_respostas`)
substituídos por `test_checklist_abrir_coleta_cria_coleta_e_mostra_link` e
`test_checklist_encerrar_coleta_muda_status`; `test_checklist_nao_conforme_conta_como_evidencia_convergente`
e `test_checklist_conforme_nao_conta_como_evidencia` (`avaliacoes/tests.py`) e
`test_contexto_relatorio_inclui_checklist_triangulacao_avaliado` (`relatorios/tests.py`)
ajustados pra criar `ColetaChecklistTriangulacao`/`RespondenteChecklistTriangulacao` em
vez de gravar `RespostaChecklistTriangulacao` direto na `Aplicacao`.

---

## 7. Backend — cálculo da matriz de risco (valores definitivos, sem exemplos ilustrativos)

A implementação de referência completa está no arquivo **`risk_engine.py`** entregue junto com
este documento. É código Python puro, testado, sem dependência de Django — importar direto, não
reescrever a lógica manualmente. O que segue aqui é a especificação que o `risk_engine.py`
implementa; se algum dia houver divergência entre este texto e o código, **o código é a fonte de
verdade** (deve ser mantido sincronizado).

### 7.1 Inversão de polaridade (item a item, antes de qualquer agregação)

```
valor_ajustado = polaridade == "PROTETIVO"
    ? (escala_max + escala_min) - valor_bruto
    : valor_bruto
```

### 7.2 Escore por domínio/subescala

```
escore_dominio = média(valor_ajustado de todos os itens do domínio, de todos os respondentes do GHE)
```

### 7.3 Classificação por domínio (3 bandas, valores fixos por instrumento — tabela definitiva)

| Instrumento / subescala | Baixo | Moderado | Elevado |
|---|---|---|---|
| COPSOQ adaptado (todos os domínios D1–D9) | ≤ 2,5 | 2,6 – 3,4 | ≥ 3,5 |
| ITRA — EACT | < 2,3 | 2,3 – 3,69 | ≥ 3,7 |
| ITRA — ECHT | < 2,3 | 2,3 – 3,69 | ≥ 3,7 |
| ITRA — EIPSTN | < 2,3 | 2,3 – 3,69 | ≥ 3,7 |
| ITRA — EIPSTP (após inversão de polaridade) | < 2,3 | 2,3 – 3,69 | ≥ 3,7 |
| ITRA — EADRT (banda mais rígida — itens descrevem sintomas de adoecimento) | < 2,0 | 2,0 – 2,9 | ≥ 3,0 |

**Origem dos números (documentado para não ser tratado como arbitrário):** os cortes do COPSOQ vêm
do próprio formulário de aplicação da RR Revestir (fonte primária do projeto). Os cortes da EACT
(<2,29 / 2,3–3,69 / ≥3,7) vêm de fonte acadêmica aberta que cita a metodologia original de Mendes &
Ferreira. Como não há corte publicado em fonte aberta específico para ECHT/EIPSTN/EIPSTP, este
projeto padroniza essas três subescalas com o mesmo corte da EACT — todas usam a mesma escala 1–5
de frequência, então isso é uma decisão de engenharia consistente, não um número inventado sem
critério. A EADRT recebe banda própria, mais conservadora, ancorada no único dado empírico
encontrado em fonte aberta (escore médio 2,14 nessa escala foi classificado como "moderado" em
estudo acadêmico — por isso o teto do "Baixo" fica abaixo de 2,14, em 2,0, e não em 2,3).
**Este critério deve ser revisado e formalmente ratificado por escrito pelo profissional
responsável do PGR antes do primeiro relatório oficial** — mas o sistema não deve ficar bloqueado
esperando isso: os valores acima são o padrão operacional até serem substituídos por uma nova
versão registrada (ver "versionamento de critérios" abaixo).

### 7.4 Severidade (S) — mapeamento fixo e universal (não varia por instrumento)

```
Baixo    -> S = 1
Moderado -> S = 2
Elevado  -> S = 3
```

### 7.5 Probabilidade (P) — regra definitiva

```
SE houver evento grave confirmado
   (ex.: item de risco tipo "já sofreu/presenciou violência, ameaça, assédio moral ou
    discriminação" com valor_bruto >= 4, em qualquer instrumento)
   ENTÃO P = 3   (sempre, independente de qualquer outra evidência)

SENÃO, contar evidências complementares convergentes com o domínio em risco:
   - absenteísmo do GHE acima da média histórica da empresa
   - turnover do GHE acima da média histórica da empresa
   - CAT/CID-F relacionado registrado no período
   - item "Não conforme" no checklist observacional relacionado ao mesmo domínio
   - relato coerente na entrevista com a liderança

   0 evidências complementares -> P = 1
   1 evidência complementar    -> P = 2
   2 ou mais evidências        -> P = 3
```

### 7.6 Matriz de risco — todas as 9 combinações definidas (nenhuma omitida)

| Severidade (S) | Probabilidade (P) | Score (S×P) | Banda | Prazo do plano de ação |
|---|---|---|---|---|
| 1 | 1 | 1 | Aceitável | Sem prazo — monitoramento no próximo ciclo |
| 1 | 2 | 2 | Aceitável | Sem prazo — monitoramento no próximo ciclo |
| 2 | 1 | 2 | Aceitável | Sem prazo — monitoramento no próximo ciclo |
| 1 | 3 | 3 | Moderado | 90 dias |
| 3 | 1 | 3 | Moderado | 90 dias |
| 2 | 2 | 4 | Moderado | 90 dias |
| 2 | 3 | 6 | Alto | 30 dias |
| 3 | 2 | 6 | Alto | 30 dias |
| 3 | 3 | 9 | Crítico | 15 dias, com comunicação imediata à liderança/CIPA |

### 7.7 Confidencialidade

```
SE número de respondentes do GHE < 3
   ENTÃO suprimir resultado individual do GHE nos relatórios e telas,
         agregar apenas em nível de setor/unidade antes de exibir.
```

### 7.8 Versionamento de critérios (obrigatório)

A tabela da seção 7.3 (classificação por domínio), o mapeamento da 7.4 (severidade) e a regra da
7.5/7.6 (probabilidade/matriz) devem ser armazenados no banco como uma entidade `CriterioVersao`,
nunca como constante solta espalhada pelo código. Toda `Aplicacao`/`Relatorio` referencia o
`CriterioVersao` usado. Se o profissional responsável decidir ajustar um número no futuro, isso
cria uma nova versão — relatórios antigos continuam citando a versão com que foram calculados
(rastreabilidade exigida pela NR-01).

### 7.9 Requisitos de implementação

- Testes unitários obrigatórios (já entregues em `test_risk_engine.py`) cobrindo: inversão de
  polaridade, domínio de polaridade mista (D9 do COPSOQ), as 9 combinações da matriz de risco,
  a regra de evento grave forçando P=3, e a supressão por N mínimo.
- O cálculo deve ser 100% reproduzível a partir dos dados brutos armazenados — nunca guardar só o
  resultado agregado sem manter as respostas item a item que o originaram.

---

## 8. API de análise com Claude — geração do parecer e do PDF

### 8.1 Contrato

- **Entrada:** JSON já calculado pelo backend (escores por domínio, classificação, matriz de risco,
  indicadores indiretos, dados de identificação do GHE/empresa) — nunca respostas brutas
  individuais identificáveis.
- **Saída esperada:** texto técnico estruturado (parecer por domínio, síntese executiva, riscos
  prioritários, sugestões de medida preventiva por risco) em JSON, para popular o template do PDF.
- **A IA não recebe autoridade para alterar classificação ou nível de risco** — ela só redige a
  interpretação dos números que já vieram prontos.
- Todo output deve ser tratado no sistema como **minuta**, com campo `status: "aguardando_revisão"`
  até que o profissional responsável edite/aprove e assine.

### 8.2 Prompt (diretrizes, não literal)

- Instruir o modelo a: (1) nunca inventar números, apenas os do JSON de entrada; (2) usar
  linguagem técnica adequada a documento de PGR (evitar tom alarmista ou clínico/diagnóstico
  individual); (3) sempre citar de qual domínio/GHE cada achado vem; (4) para cada risco Elevado
  ou Crítico, sugerir ao menos uma medida de prevenção coerente com a NR-01 (mudança organizacional,
  não tratamento individual do trabalhador); (5) terminar com aviso de que o documento é uma minuta
  técnica e depende de revisão e assinatura do profissional habilitado.
- Chamar via `/v1/messages`, `model: claude-sonnet-5`, com `max_tokens` suficiente para o
  relatório completo (testar; relatórios longos podem exigir chamadas por seção/domínio).
  Correção de 2026-07-17: a versão anterior deste documento citava `claude-sonnet-4-6` —
  copiado de um boilerplate genérico sem atualizar pro modelo atual, não uma decisão válida.
  `claude-sonnet-5` é o modelo de equilíbrio custo/qualidade adequado pra redação técnica
  estruturada deste parecer; não precisa do Opus aqui, e o Haiku é arriscado demais pra um
  parecer que vira documento de PGR.
- Usar **structured output em JSON** (ver seção de "Structured Outputs" do produto) para garantir
  que cada seção do parecer caia no campo certo do template do PDF, evitando parsing frágil de
  texto livre.

### 8.3 Geração do PDF final (Inventário de Risco Psicossocial)

Estrutura mínima do documento:

1. Capa — empresa, CNPJ, unidade, período de aplicação, versão do relatório.
2. Base técnica e legal utilizada (instrumento, critérios, versão).
3. Metodologia — como foi coletado, N de respondentes por GHE, tipo de aplicação.
4. Resultados por GHE e por domínio — escores, classificação, matriz de risco (visual).
5. Evidências complementares — indicadores indiretos, entrevista com liderança, checklist
   observacional.
6. Parecer técnico (gerado por IA, revisado por humano).
7. Plano de ação — tabela com risco, medida, responsável, prazo, status.
8. Campo de assinatura do responsável técnico habilitado (nome, registro profissional, data).

---

## 8.4 Decisões de Implementação Registradas (Etapa 6 — PDF)

> Decisões tomadas em conversa com o usuário em 2026-07-17, durante a implementação da Etapa 6.

1. **Registro profissional (item 8 da Seção 8.3)**: criado `PerfilProfissional` (app
   `relatorios`) — `OneToOneField` para `User` com `titulo_profissional`, `conselho` (ex.: "CRP",
   "CREA") e `numero_registro` (ex.: "06/123456"). Ligado ao usuário (não campos soltos em
   `Relatorio`) pra não redigitar o registro a cada relatório assinado pela mesma pessoa.

2. **Semântica da assinatura**: "assinar" é um **registro interno simples** — `status=assinado` +
   `assinado_por` + `assinado_em` no banco, sem assinatura digital/criptográfica (sem certificado,
   sem ICP-Brasil). `assinar_relatorio()` (`relatorios/services/pdf.py`) exige que o usuário tenha
   `PerfilProfissional` cadastrado; sem isso, levanta erro em vez de assinar sem registro
   profissional.

3. **Revisão do parecer da IA**: sem tela dedicada por enquanto — o profissional responsável edita
   `Relatorio.parecer_ia` (JSON bruto) direto no Django Admin antes de aprovar/assinar, mesmo
   padrão já usado pros outros cadastros deste projeto (Seção 11: "Django Admin resolve por
   enquanto").

4. **Duas variantes do PDF, um único arquivo**: `Relatorio.pdf_path` guarda sempre o PDF mais
   recente gerado — **minuta** (marca d'água "MINUTA", bloco de assinatura em branco) enquanto
   `status != assinado`; **final** (sem marca d'água, bloco de assinatura preenchido com
   `PerfilProfissional`) quando `status == assinado`. Gerar de novo sobrescreve; não há minuta e
   final coexistindo como dois arquivos separados. `assinar_relatorio()` já regenera o PDF final
   automaticamente como parte do fluxo de assinatura.

5. **Confidencialidade também no Plano de Ação**: durante a implementação, `EscoreDominio`
   suprimidos por confidencialidade (N < mínimo) ainda geravam `PlanoDeAcao` citando o domínio e a
   banda de risco — isso vazava exatamente o dado que a Seção 3 (princípio 3) manda suprimir,
   através da Seção 7 do PDF em vez da Seção 4. Corrigido em
   `avaliacoes/services/calculo_risco.py::_gerar_plano_de_acao_se_necessario`: nenhum Plano de
   Ação é criado para um domínio suprimido, mesmo que a banda calculada não seja Aceitável.

---

## 9. Segurança e conformidade

- Dados de resposta individual são dado sensível (LGPD, art. 5º, II) — criptografar em repouso,
  restringir acesso por papel (RH/SST/admin), nunca expor em relatório agregado quando N < mínimo.
- Manter log de acesso a dados individuais.
- Retenção de dados: definir política com o jurídico da empresa (documentos de PGR normalmente
  precisam ficar disponíveis por vários anos para fiscalização).

---

## 10. Artefatos já entregues junto com este documento (usar, não recriar)

- `risk_engine.py` — motor de cálculo completo (Python puro), implementando as seções 7.1 a 7.7.
- `test_risk_engine.py` — testes cobrindo os casos críticos (D9 misto, 9 combinações da matriz,
  evento grave, supressão por N mínimo).
- `seeds/copsoq_rr_revestir.json` — os 2 GHEs, 9 domínios, todos os itens e polaridades do COPSOQ.
- `seeds/itra.json` — as 5 subescalas do ITRA (EACT, ECHT, EADRT, EIPSTP, EIPSTN), todos os itens,
  escalas e cortes de classificação.

## 11. Próximos passos sugeridos para o Claude Code (projeto Django)

1. Criar o projeto Django + DRF + PostgreSQL; configurar `settings` para múltiplos apps
   (`instrumentos`, `avaliacoes`, `relatorios`).
2. Modelar o schema de banco de dados a partir da seção 4, incluindo a entidade `CriterioVersao`
   (seção 7.8).
3. Escrever um management command (`load_instrumentos`) que importa `seeds/copsoq_rr_revestir.json`
   e `seeds/itra.json` para o banco — nunca digitar os itens manualmente nos models/migrations.
4. Importar `risk_engine.py` como dependência interna do app `avaliacoes`; rodar
   `test_risk_engine.py` no CI antes de qualquer deploy.
5. Implementar a API de análise com Claude (seção 8) como serviço isolado do cálculo (o cálculo
   nunca depende da IA estar disponível).
6. Implementar o gerador de PDF (WeasyPrint) a partir do JSON de saída da IA + dados calculados
   pelo `risk_engine.py`.
7. Só depois disso, construir a UI de aplicação do questionário (pode reaproveitar o Django Admin
   no início para cadastro de empresa/GHE/plano de ação, antes de investir em frontend dedicado).
