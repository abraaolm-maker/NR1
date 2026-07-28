# Prompt 01 — Form Responses 1 (Conformidade)

## Contexto

A planilha `Form Responses 1` do Excel de referência (`Relatorio_Semaforo_Dados_Simulados.xlsx`) contém 42 respostas simuladas com estas colunas:

- Col 1: Timestamp
- Col 2: `[META.CIENCIA]` Consentimento ("Li e compreendi...")
- Col 3: `[META.GHE]` GHE do respondente (texto: "GHE 01 - Administrativo / Auxiliar Administrativo", etc.)
- Col 4: `[META.TEMPO]` Tempo na organização (faixas: "Menos de 1 ano", "1 a 2 anos", "3 a 5 anos", "Mais de 5 anos")
- Col 5: `[META.MODALIDADE]` Modalidade (Presencial / Híbrido)
- Cols 6–39: 34 itens D1.1 a D9.4, escala 1–5
- Col 40: `[ABERTA.1]` Pergunta aberta 1
- Col 41: `[ABERTA.2]` Pergunta aberta 2

## Tarefa

Este ponto está **em conformidade** com o sistema atual. Verificar que:

1. O modelo `Respondente` já armazena: `tempo_na_organizacao`, `modalidade_trabalho`, `resposta_aberta_1`, `resposta_aberta_2`, `consentimento_aceito_em` — todos já implementados na Seção 6.7 do CLAUDE.md.
2. O modelo `Resposta` já armazena cada item individualmente (`respondente` + `item` + `valor_bruto`).
3. O GHE é resolvido pelo token da Aplicacao (que pertence a um GHE), não por texto livre do respondente — isso já funciona.
4. As faixas de tempo na organização do Excel ("Menos de 1 ano", "1 a 2 anos", "3 a 5 anos", "Mais de 5 anos") devem ser comparadas com as do `TempoNaOrganizacao` no sistema. Se houver divergência de faixas (o sistema tem 5 faixas: "Menos de 6 meses", "6 meses a 1 ano", "1 a 3 anos", "3 a 5 anos", "Mais de 5 anos" — e o Excel tem 4: "Menos de 1 ano", "1 a 2 anos", "3 a 5 anos", "Mais de 5 anos"), **alinhar as faixas do sistema com as do Excel**, pois o Excel é a referência do produto final.

## Resultado esperado

- Se as faixas de `TempoNaOrganizacao` divergirem do Excel, atualizar o `TextChoices` e criar migration.
- Nenhuma outra mudança de modelo — o mapeamento já existe.
- Rodar `py manage.py makemigrations --noinput; py manage.py migrate` se houve alteração.
- Rodar `py -m pytest` e confirmar que todos os testes passam.

## Arquivos relevantes

- `avaliacoes/models.py` — `TempoNaOrganizacao`, `Respondente`
- `avaliacoes/views.py` — `PerfilRespondenteForm` (faixas do formulário público)
