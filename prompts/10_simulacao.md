# Prompt 10 — Simulação (nenhuma mudança)

## Contexto

A planilha `SIMULACAO` do Excel é apenas um painel de controle para validação:
- Contagem de respostas simuladas (42)
- GHEs simulados (4), liberados (3), suprimidos (1)
- Tabela cruzada domínio × GHE com escores médios
- Regras de leitura e instruções de uso

## Tarefa

**Nenhuma mudança necessária no sistema.** Esta planilha é uma ferramenta de validação do Excel, não um artefato que o sistema precise reproduzir. A tabela cruzada domínio × GHE já é produzida pelo Diagnóstico GHE (Prompt 06) e pelo Semáforo (Prompt 11).

Confirmar que, após os Prompts 02–06, o sistema é capaz de produzir os mesmos números que a planilha SIMULACAO mostra — isso serve como teste de integração de ponta a ponta.

## Resultado esperado

- Nenhum código novo.
- Validação manual: criar dados de teste equivalentes aos do Excel e confirmar que os escores do sistema batem com os da planilha.
