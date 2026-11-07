@AGENTS.md

## Específico do Claude Code

- Regras por área estão em `.claude/rules/` e carregam só quando você mexe nos arquivos correspondentes.
- Agentes ficam em `.claude/agents/`: `task-planner` (só grava em `docs/plans/`), `test-writer` (só escreve em `tests/`), `task-implementer` (roda em worktree) e os revisores `code-reviewer` e `pr-reviewer`, ambos somente leitura.
- Para tarefa com mais de um arquivo, comece em plan mode e espere aprovação.
