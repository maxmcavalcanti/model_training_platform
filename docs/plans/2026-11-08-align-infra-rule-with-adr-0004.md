# Alinhar `.claude/rules/infra.md` aos ADRs 0004 e 0003

Branch sugerida: `chore/align-infra-rule-with-adr-0004`

> **Exceção autorizada pelo usuário (2026-11-08), válida só para este PR:** o `task-implementer` pode editar `.claude/rules/infra.md`, ao contrário de "implementer não edita ... `.claude/`" (`CLAUDE.md`). Só esse arquivo. Continua proibido editar qualquer outro arquivo de `.claude/`, testes, `docs/plans/`, ADRs, `AGENTS.md`, `CLAUDE.md` e `docs/plataforma-ml.md`.

## 1. Objetivo

Fazer o texto de `.claude/rules/infra.md` dizer a política que vale hoje: `restart: unless-stopped` só em serviço sem `profiles`, `mem_limit` em todos, e o deploy manual por SSH como exceção registrada até o PR 39.
É só redação: a política já está no ADR 0004 e nos testes de `tests/infra/test_compose.py`; a regra é que está atrasada.

## 2. Fora do escopo

- Alterar `docs/plataforma-ml.md:178` ("`restart: unless-stopped` em todos os serviços"), que tem o mesmo desvio. Não está autorizado nesta tarefa (ver Q1).
- Alterar `AGENTS.md` ("Merge na `main` é a única forma de mudar produção"). O ADR 0004 diz que a exceção não muda essa regra; ela volta a valer sozinha no PR 39.
- Alterar ADRs (0003, 0004), testes, `infra/docker-compose.yml` ou outros arquivos de `.claude/`.
- Alterar planos antigos que citam o texto antigo da regra (`docs/plans/03-*.md`, `10-*.md`, `11-*.md`, `16-*.md`, `37-*.md`). São registros históricos ou specs futuras; o PR 37 e o PR 39 tratam o seu próprio texto.
- Marcar o ADR 0004 como `superseded` (é dos PRs 36 e 39).
- Codificar na regra o allow-list de portas (`PORT_PUBLISHING_SERVICES` em `tests/infra/test_compose.py:24`). É detalhe dos testes, que crescem a cada PR; a regra de exposição (linhas 10 e 11) já cobre o princípio.
- Acrescentar linha no `docs/plans/00-indice.md`: o índice só lista os PRs do roadmap, não tarefas avulsas (os planos `2026-11-07-*` também não estão lá).

## 3. Fase do roadmap

Nenhuma fase nova. É tarefa transversal que fecha a pendência registrada no ADR 0004 (Consequências, primeiro item: "A redação de `.claude/rules/infra.md` ... deve ser alinhada a esta exceção; isso não é feito por este ADR e fica para o PR que tocar a regra"). Acompanha a fase corrente (Fase 2 antecipada, depois do PR 16, commit `58667da`). Não adianta nada de fases futuras.

## 4. Arquivos a criar ou alterar

| Arquivo | Motivo |
| --- | --- |
| `.claude/rules/infra.md` | Linhas 9 e 13 contradizem o ADR 0004 e os testes de compose (exceção autorizada) |
| `docs/plans/2026-11-08-align-infra-rule-with-adr-0004.md` | Este plano, se for no mesmo PR (ver Q2) |

### 4.1 Texto atual de `.claude/rules/infra.md` (15 linhas)

```markdown
---
paths:
  - "infra/**"
  - ".github/**"
---

# Infra e CI/CD

- Todo serviço no compose tem `restart: unless-stopped`.
- MLflow, Prefect e Grafana não têm autenticação adequada: só em `127.0.0.1`, expostos na tailnet por `tailscale serve`; a ACL do Tailscale é o controle de acesso (ADR 0003).
- Firewall: nenhuma porta pública (ADR 0003). A 22 pública só durante o provisionamento. Nenhuma porta do compose em `0.0.0.0` (o Docker passa por cima do ufw). Não ligar o Tailscale SSH. Não abrir porta para "testar".
- `.env` da VPS fica fora do git, permissão 600. Segredos do CI vão em GitHub Secrets.
- Deploy só sai de merge na `main`. Nada de SSH manual para mudar produção.
- Backup sem restore testado não conta como backup.
```

### 4.2 Fontes da política (citações exatas)

ADR 0004 (`docs/adr/0004-interim-operation-before-prefect.md`):

- Linha 22: "Até o PR 39, atualizar a VPS é manual: o usuário entra por SSH (pela tailnet, ADR 0003), faz `git pull` e roda `docker compose up`. A imagem dos jobs é construída na própria VPS até o PR 37 (GHCR)."
- Linha 24: "É uma exceção registrada à regra "Nada de SSH manual para mudar produção", não uma mudança dela. A partir do PR 39, o merge na `main` volta a ser a única forma de mudar produção, como diz o `AGENTS.md`."
- Linha 34: "Serviço de execução única, declarado em `profiles` (o `jobs` do PR 11, rodado com `docker compose run --rm jobs <comando>`), fica com `restart: "no"`. A regra "todo serviço tem `restart: unless-stopped`" continua valendo para todo serviço sem `profiles`. `mem_limit` continua obrigatório em todos, com ou sem profile (PR 03)."
- Linha 39: "Enquanto a exceção durar, quem aplica o deploy é uma pessoa, sem trilha automática além do histórico do git."

ADR 0003 (`docs/adr/0003-tailscale-only-network.md`), linha 47: "OpenSSH dentro da tailnet. O recurso Tailscale SSH (`tailscale up --ssh`) não é ligado". As linhas 10 e 11 da regra já estão alinhadas ao ADR 0003 e não mudam.

Testes que codificam a política (`tests/infra/test_compose.py`), nenhum lê o texto da regra:

- `services_missing_restart` (linhas 52 a 58): serviço sem `profiles` precisa de `restart == "unless-stopped"`; serviço com `profiles` é ignorado.
- `services_missing_mem_limit` (linhas 61 a 63): todo serviço, com ou sem `profiles`, precisa de `mem_limit`.
- `jobs_service_problems` (linhas 705 a 716): `jobs` tem `profiles == ["jobs"]`, `restart == "no"` (string; `test_yaml_unquoted_no_is_false`, linha 837, mostra que `restart: no` sem aspas vira `False`), `mem_limit` e nenhuma porta.
- `scheduler_service_problems` (linhas 910 a 921): `scheduler` sem `profiles`, `restart: unless-stopped`, `mem_limit`, sem portas.

Estado real de `infra/docker-compose.yml`: `health`, `postgres` e `scheduler` sem `profiles` e com `restart: unless-stopped`; `jobs` com `profiles: ["jobs"]` e `restart: "no"`; os quatro com `mem_limit`.

## 5. Passos

1. Crie a branch `chore/align-infra-rule-with-adr-0004` a partir da `main` atualizada.
2. Em `.claude/rules/infra.md`, troque a linha 9 inteira:
   - de: ``- Todo serviço no compose tem `restart: unless-stopped`.``
   - para: ``- Todo serviço do compose sem `profiles` tem `restart: unless-stopped`. Serviço de execução única, declarado em `profiles` e rodado com `docker compose run --rm` (ex.: `jobs`), tem `restart: "no"`, com aspas, porque sem aspas o YAML lê `false` (ADR 0004). Todo serviço, com ou sem `profiles`, tem `mem_limit`.``
3. No mesmo arquivo, troque a linha 13 inteira:
   - de: ``- Deploy só sai de merge na `main`. Nada de SSH manual para mudar produção.``
   - para: ``- Deploy só sai de merge na `main`. Nada de SSH manual para mudar produção. Exceção registrada até o PR 39 (ADR 0004): o usuário atualiza a VPS à mão, por SSH pela tailnet (ADR 0003), com `git pull` e `docker compose up`, e a imagem dos jobs é construída na própria VPS até o PR 37. Quem aplica esse deploy é o usuário, nunca um agente.``
4. Não mexa no frontmatter nem nas linhas 7, 10, 11, 12 e 14. O arquivo continua com 15 linhas.
5. Rode os critérios da seção 6 e guarde as saídas.
6. Commit em inglês, por exemplo `chore: align infra rule with ADR 0004 restart and deploy exceptions`.
7. Rode o `code-reviewer`. Abra o PR (título e corpo em inglês, com as saídas da seção 6 e a menção à exceção autorizada) e rode o `pr-reviewer`. O PR toca `.claude/`, então **os dois revisores são obrigatórios** (`AGENTS.md`, Fluxo de trabalho).

## 6. Critérios de pronto

```sh
# 1. Texto antigo da linha 9 saiu
git grep -n -F 'Todo serviço no compose tem `restart: unless-stopped`.' -- .claude/rules/infra.md
# esperado: nenhuma saída (código de saída 1)

# 2. Linha 9 nova, com profiles, "no" e mem_limit
git grep -n -F 'Todo serviço do compose sem `profiles` tem `restart: unless-stopped`.' -- .claude/rules/infra.md
# esperado: 1 linha, .claude/rules/infra.md:9:...
git grep -n -F 'tem `restart: "no"`' -- .claude/rules/infra.md
# esperado: 1 linha, :9
git grep -n -F 'com ou sem `profiles`, tem `mem_limit`' -- .claude/rules/infra.md
# esperado: 1 linha, :9

# 3. Linha 13 mantém a regra e registra a exceção
git grep -n -F 'Exceção registrada até o PR 39 (ADR 0004)' -- .claude/rules/infra.md
# esperado: 1 linha, :13
git grep -n -F 'Nada de SSH manual para mudar produção.' -- .claude/rules/infra.md
# esperado: 1 linha, :13

# 4. Resto do arquivo intacto
git diff --numstat main...HEAD -- .claude/rules/infra.md
# esperado: "2	2	.claude/rules/infra.md"

# 5. Só os arquivos permitidos mudaram
git diff --name-only main...HEAD
# esperado: .claude/rules/infra.md (e docs/plans/2026-11-08-align-infra-rule-with-adr-0004.md, se o plano for no PR)

# 6. A política codificada continua verde (nada de código mudou; é rede de segurança)
uv run pytest tests/infra -m "not db"
# esperado: todos passam, 0 failed

# 7. Lint e formatação sem regressão
uv run ruff check .
# esperado: "All checks passed!"
uv run ruff format --check .
# esperado: nenhum arquivo "Would reformat"
```

## 7. Testes necessários

não. Só Markdown de regra de agente (`.claude/rules/infra.md`), sem código nem mudança de comportamento; nenhum teste lê o texto da regra (busca por `infra.md` e `rules` em `tests/` sem ocorrência), e a política já é verificada por `tests/infra/test_compose.py`.

## 8. Casos de teste

n/a

## 9. Riscos e perguntas em aberto

- **Risco: a regra muda o comportamento dos agentes** em `infra/**` e `.github/**`. É o desejado: hoje um revisor que lê a regra ao pé da letra acusaria o `jobs` (`restart: "no"`) e o deploy manual dos itens 04, 12 e 17. Mitigação: `code-reviewer` e `pr-reviewer` obrigatórios.
- **Risco: a exceção de deploy virar permanente na regra.** O texto prende a exceção ao PR 39. O PR 39 precisa apagar a frase "Exceção registrada até o PR 39 ..." junto com o `superseded` do ADR 0004; vale registrar isso na spec `docs/plans/39-deploy-via-ssh.md` numa tarefa separada (ver Q3).
- **Risco: o plano não chega ao worktree.** Este arquivo foi gravado sem commit no checkout principal. O `task-implementer` roda em worktree a partir da branch; se o plano não estiver commitado na branch, passe a ele o caminho absoluto no checkout principal ou commite o plano antes (ver Q2).
- **Q1. `docs/plataforma-ml.md:178` também diz "`restart: unless-stopped` em todos os serviços".** Fica fora por não estar autorizado. Padrão sugerido: tarefa só de `docs/**` depois, que dispensa revisores.
- **Q2. O plano vai no mesmo PR?** Padrão sugerido: sim, commitado na branch antes do implementador começar.
- **Q3. Lembrete no plano 39?** Padrão sugerido: sim, numa tarefa só de docs, acrescentar à spec 39 o passo "remover a exceção de `.claude/rules/infra.md` linha 13" (exige de novo autorização para editar `.claude/` naquele PR).
- **Q4. Incluir `mem_limit` na regra?** Não estava na lista de conflitos da tarefa, mas o ADR 0004 (linha 34) e o teste `services_missing_mem_limit` o tornam obrigatório, e a regra não o menciona. Padrão sugerido: incluir, como no passo 2. Se o usuário preferir o escopo mínimo, retire a última frase do passo 2 e o terceiro `git grep` do critério 2.

## 10. Decisões que exigem ADR

Nenhuma. A tarefa só transcreve para a regra decisões já aceitas e mergeadas nos ADRs 0003 e 0004; não muda `raw`, `ref`, o contrato, nem expõe porta ou serviço.
