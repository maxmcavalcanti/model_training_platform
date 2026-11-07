@AGENTS.md

## Específico do Claude Code

- Regras por área estão em `.claude/rules/` e carregam só quando você mexe nos arquivos correspondentes.
- Agentes ficam em `.claude/agents/`: `task-planner`, `test-writer`, `task-implementer` (roda em worktree), `code-reviewer` e `pr-reviewer`.
  - Imposto pelo harness: o conjunto de tools de cada agente (`tools:` no frontmatter). O `isolation: worktree` do implementer. Não há `disallowedTools` no `pr-reviewer`: a entrada com especificador (`Bash(gh pr merge:*)`) remove o Bash inteiro, não só o comando.
  - Só por instrução do prompt (não imposto): planner só grava em `docs/plans/`; test-writer só em `tests/`; implementer não edita testes, `docs/plans/` nem `.claude/`; `code-reviewer` e `pr-reviewer` usam Bash só para leitura e o `pr-reviewer` não comenta no PR.
  - Para impor restrições de pasta no futuro, o caminho é um hook `PreToolUse` por caminho.
- Para tarefa com mais de um arquivo, comece em plan mode e espere aprovação.
