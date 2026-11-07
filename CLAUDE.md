@AGENTS.md

## Específico do Claude Code

- Regras por área estão em `.claude/rules/` e carregam só quando você mexe nos arquivos correspondentes.
- Revisores ficam em `.claude/agents/` (`code-reviewer`, `pr-reviewer`), ambos somente leitura.
- Para tarefa com mais de um arquivo, comece em plan mode e espere aprovação.
