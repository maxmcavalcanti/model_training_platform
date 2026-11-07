# Alinhar `.claude/` ao ADR 0001 (nomes em inglês)

Branch sugerida: `chore/align-claude-naming`

## 1. Objetivo

Trocar os identificadores antigos em português que ainda aparecem em `.claude/rules/` e `.claude/agents/` pelos nomes novos da tabela do ADR 0001 (`docs/adr/0001-english-naming-convention.md`).
Acrescentar aos agentes que escrevem commits, testes e código uma referência curta à convenção em inglês, que hoje só está em `AGENTS.md:26`.

## 2. Fora do escopo

- Renomear arquivos: `.claude/rules/migrations-e-dados.md` continua com esse nome. Pela decisão Q19 e pela seção M do ADR 0001, os nomes de arquivo de docs e regras ficam em português.
- Traduzir a prosa de regras e agentes, incluindo o nome do produto "plataforma ML" (`code-reviewer.md:8`, `pr-reviewer.md:10`, `task-implementer.md:9`, `test-writer.md:8`, `task-planner.md:8`), os rótulos `Testes necessários: sim/não` e expressões como "como emitida" (`migrations-e-dados.md:15`).
- O caminho `docs/plataforma-ml.md` citado em `task-planner.md:21`, que é nome de arquivo de docs e fica como está (seção M do ADR).
- `AGENTS.md`: já está alinhado (linhas 3, 7 e 20 usam `platform`, `models` e `ingested_at`; a linha 26 traz a convenção). Não alterar.
- `CLAUDE.md` e `.claude/settings.json`: nenhum identificador antigo. Não alterar.
- `.claude/rules/infra.md`: nenhum identificador antigo. A menção ao firewall com 443 é assunto do ADR de rede (índice, item 2), não desta tarefa.
- Mudar o comportamento dos revisores (`code-reviewer`, `pr-reviewer`) para cobrar a convenção (ver Q2).
- Avisar a ciência de dados: o ADR 0001 já cobre a mudança de nomes. Esta tarefa só alinha o texto dos agentes.

## 3. Fase do roadmap

Nenhuma fase específica de `docs/plataforma-ml.md`. É uma tarefa transversal, que acompanha o ADR 0001 (Consequências, segundo item: "`.claude/` ... ainda cita nomes antigos ... até uma tarefa própria de alinhamento") e vem antes do item 01 (Fase 0). Não adianta nada de fases futuras.

## 4. Arquivos a criar ou alterar

| Arquivo | Motivo |
| --- | --- |
| `.claude/rules/migrations-e-dados.md` | Linhas 12, 13 e 15 usam `cientista`, `leitura`, `ingerido_em`, `raw.clima_previsao` e `emitida_em` |
| `.claude/agents/code-reviewer.md` | A linha 16 usa `ingerido_em` |
| `.claude/agents/task-implementer.md` | A linha 20 fala de conventional commits mas não diz que são em inglês. Acrescentar a convenção |
| `.claude/agents/test-writer.md` | A linha 21 fala da mensagem `test:` mas não diz que é em inglês. Acrescentar a convenção |

### 4.1 Inventário de identificadores antigos (busca feita em todo `.claude/`, `AGENTS.md` e `CLAUDE.md`)

| Arquivo:linha | Atual | Novo (tabela do ADR 0001) |
| --- | --- | --- |
| `.claude/rules/migrations-e-dados.md:12` | `cientista` | `scientist` (seção D) |
| `.claude/rules/migrations-e-dados.md:12` | `leitura` | `reader` (seção D) |
| `.claude/rules/migrations-e-dados.md:13` | `ingerido_em` | `ingested_at` (seção C) |
| `.claude/rules/migrations-e-dados.md:15` | `raw.clima_previsao` | `raw.weather_forecast` (seção B) |
| `.claude/rules/migrations-e-dados.md:15` | `emitida_em` | `issued_at` (seção C) |
| `.claude/agents/code-reviewer.md:16` | `ingerido_em` | `ingested_at` (seção C) |

Sem ocorrências: `.claude/settings.json`, `.claude/rules/infra.md`, `.claude/agents/pr-reviewer.md`, `.claude/agents/task-planner.md`, `.claude/agents/task-implementer.md`, `.claude/agents/test-writer.md`, `CLAUDE.md`, `AGENTS.md`. `plataforma` aparece só como prosa ("plataforma ML") ou dentro do caminho `docs/plataforma-ml.md`, e `modelos` não aparece como nome de repo ou pacote em `.claude/`.

### 4.2 Convenção em inglês para commits, PR e comentários

- `AGENTS.md:26` já diz: "Identificadores e artefatos de implementação em inglês: ... comentários, mensagens de log e de erro do código, mensagens de commit e títulos e corpos de PR. ... Tabela de nomes e regras de formação: `docs/adr/0001-english-naming-convention.md`." Todos os agentes leem `AGENTS.md`.
- Nenhum arquivo de `.claude/` menciona a convenção. Os dois agentes que escrevem commits e código não a citam:
  - `.claude/agents/task-implementer.md:20`: "Trabalhe em branch própria. Faça commits pequenos e atômicos, com mensagens no estilo conventional commits."
  - `.claude/agents/test-writer.md:21`: "... um commit atômico só dos testes, na branch indicada, com mensagem iniciando com `test:`. ..."
- Onde acrescentar: uma linha nova em cada um desses dois agentes, logo depois das linhas citadas (texto exato no passo 4 e no passo 5).
- `code-reviewer`, `pr-reviewer` e `task-planner`: não acrescentar nada (ver Q2 e Q3).

## 5. Passos

Quem executa: ver Q1. O `task-implementer` está proibido de alterar `.claude/` (`.claude/agents/task-implementer.md:16`: "Não altere `docs/plans/` nem `.claude/`."). Por padrão, quem aplica as edições é o usuário ou a sessão principal, não o subagente.

1. Crie a branch `chore/align-claude-naming` a partir da `main` atualizada.
2. Em `.claude/rules/migrations-e-dados.md`, troque só os identificadores entre crases, sem mexer na prosa nem no nome do arquivo:
   - Linha 12, de: ``- Permissões por usuário do Postgres: `ingestor` escreve `raw` e `ref`; `cientista` escreve `features`; `scorer` escreve `predictions` e `monitoring`; `leitura` só lê. Toda tabela nova declara quem escreve e quem lê.``
     para: ``- Permissões por usuário do Postgres: `ingestor` escreve `raw` e `ref`; `scientist` escreve `features`; `scorer` escreve `predictions` e `monitoring`; `reader` só lê. Toda tabela nova declara quem escreve e quem lê.``
   - Linha 13, de: ``... upsert por chave, `ingerido_em`, checagem pandera ...`` para: ``... upsert por chave, `ingested_at`, checagem pandera ...`` (o resto da linha não muda).
   - Linha 15, de: ``- `raw.clima_previsao` guarda a previsão como emitida (`emitida_em`). Nunca sobrescrever uma previsão antiga com uma nova.``
     para: ``- `raw.weather_forecast` guarda a previsão como emitida (`issued_at`). Nunca sobrescrever uma previsão antiga com uma nova.``
3. Em `.claude/agents/code-reviewer.md`, linha 16, troque `` `ingerido_em` ausente`` por `` `ingested_at` ausente``. O resto da linha não muda.
4. Em `.claude/agents/task-implementer.md`, insira logo depois da linha 20 (antes de "- Nunca faça force push."):
   ``- Identificadores, comentários de código, mensagens de log e de erro, mensagens de commit e título e corpo de PR em inglês, com os nomes de `docs/adr/0001-english-naming-convention.md`.``
5. Em `.claude/agents/test-writer.md`, insira logo depois da linha 21 (antes da linha em branco que precede "Devolva:"):
   ``- Nomes de teste, fixtures, comentários e mensagem de commit em inglês, com os nomes de `docs/adr/0001-english-naming-convention.md`.``
6. Rode os critérios de pronto da seção 6 e guarde as saídas.
7. Faça um commit com mensagem em inglês, por exemplo `chore: align .claude rules and agents with ADR 0001 naming`.
8. Abra o PR com título e corpo em inglês e cole no corpo as saídas da seção 6. O PR toca `.claude/`, então **exige `code-reviewer` antes do PR e `pr-reviewer` depois** (`AGENTS.md`, Fluxo de trabalho).

## 6. Critérios de pronto

Não existe comando de lint ou teste no repo (`AGENTS.md`, "Comandos"). Os critérios usam só `git`.

```sh
# 1. Nenhum identificador antigo em .claude/
git grep -n -E 'ingerido_em|emitida_em|clima_previsao|`cientista`|`leitura`' -- .claude
# esperado: nenhuma saída (código de saída 1)

# 2. Nomes novos nos lugares certos
git grep -n -E 'ingested_at|issued_at|raw\.weather_forecast|`scientist`|`reader`' -- .claude
# esperado: exatamente 4 linhas:
#   .claude/agents/code-reviewer.md:16:...
#   .claude/rules/migrations-e-dados.md:12:...
#   .claude/rules/migrations-e-dados.md:13:...
#   .claude/rules/migrations-e-dados.md:15:...

# 3. Convenção citada nos dois agentes
git grep -n 'docs/adr/0001-english-naming-convention.md' -- .claude
# esperado: 2 linhas, .claude/agents/task-implementer.md:21 e .claude/agents/test-writer.md:22

# 4. Prosa e nome de arquivo preservados
git grep -n 'como emitida' -- .claude/rules/migrations-e-dados.md
# esperado: 1 linha, :15
git diff --name-status -M main...HEAD
# esperado: só linhas "M" para os 4 arquivos da seção 4 (e "A" para este plano, se ele for no mesmo PR); nenhuma linha "R"

# 5. Arquivos que não podem mudar
git diff --stat main...HEAD -- AGENTS.md CLAUDE.md .claude/settings.json .claude/rules/infra.md .claude/agents/pr-reviewer.md .claude/agents/task-planner.md
# esperado: nenhuma saída
```

## 7. Testes necessários

não. É documentação e configuração de agentes (Markdown em `.claude/`), sem código nem mudança de lógica.

## 8. Casos de teste

n/a

## 9. Riscos e perguntas em aberto

- **Risco: efeito no comportamento dos agentes.** Regras e agentes mudam o comportamento dos subagentes. Depois do merge, `migrations-e-dados.md` passa a orientar `ingested_at`, `issued_at`, `scientist` e `reader`. É o desejado e está alinhado com os planos já renomeados.
- **Risco: o critério 3 depende da posição.** Se a linha nova for inserida em outro lugar, os números de linha do critério 3 mudam. O que vale é a linha existir logo depois da linha citada no passo.
- **Q1. Quem aplica as edições?** O `task-implementer` não pode alterar `.claude/` (`task-implementer.md:16`). Padrão sugerido: o usuário ou a sessão principal aplica os passos 1 a 8 à mão, sem worktree. O `code-reviewer` e o `pr-reviewer` continuam obrigatórios.
- **Q2. Os revisores devem cobrar a convenção?** O `code-reviewer` diz "Ignore estilo e formatação", e nome em português poderia ser lido como estilo. Padrão sugerido: não mexer agora. Os dois revisores já revisam contra `AGENTS.md`, que traz a regra na linha 26. Se aparecer código com nome em português que passe pela revisão, abrir uma tarefa para acrescentar um item "Convenção" ao `code-reviewer`.
- **Q3. O `task-planner` deve exigir slug em inglês?** Q19 mantém em português os nomes de arquivo de docs, mas os planos recentes usam slug em inglês (`2026-11-07-english-naming-convention.md`, `2026-11-07-python-toolchain-adr.md`). Padrão sugerido: não alterar `task-planner.md`. O slug fica a critério de quem pede o plano, e a seção 5.5 do planner não muda.
- **Q4. O plano vai no mesmo PR?** Padrão sugerido: sim, este arquivo vai junto no PR da branch `chore/align-claude-naming`. O PR já passa pelos dois revisores por tocar `.claude/`.

## 10. Decisões que exigem ADR

Nenhuma. A tarefa só aplica o ADR 0001, que já foi aceito e mergeado (commit `13bc8ad`), e não muda `raw`, `ref`, contrato nem exposição de serviço.
