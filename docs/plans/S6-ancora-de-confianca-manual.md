# S6 — Âncora de confiança do deploy: quem pode fazer merge na `main` (manual)

> Executa: **usuário** (dono do repositório; Settings, contas e credenciais vivem fora do git e nenhum agente as altera). Depende de: S5 concluído (`docs/plans/S5-settings-seguranca-manual.md`, branch protection com os seis checks required e "Do not allow bypassing"). **Bloqueia o merge do PR 39** (`docs/plans/39-deploy-via-ssh.md`): tem de estar concluído e verificado antes do primeiro deploy automático. Se a escolha for a opção (b2), o passo (b2) roda **depois** do item 38 (`docs/plans/38-segredos-ci-cd-manual.md`), que cria o environment `production`.
> Nome do arquivo: `S6-<slug>.md`, convenção do índice (`docs/plans/00-indice.md`, "Desvios").
> Base: `docs/adr/0007-delivery-pipeline.md`, item 11 da Decisão. Escrito em 2026-11-09 sobre a `main` em `7fc1923`.

## 1. Objetivo

Cumprir as condições do ADR 0007, item 11, antes do primeiro deploy automático: confirmar a branch protection da `main` com checks required e "Do not allow bypassing" (S5) e aplicar **uma** de duas opções, à escolha do usuário: (b1) as credenciais do GitHub disponíveis aos agentes não podem fazer merge na `main` nem aprovar deployment, **ou** (b2) o environment `production` passa a ter o mantenedor como required reviewer.
Registrar a escolha e as saídas de verificação neste plano.

## 2. Fora do escopo

- Mudar código, workflows, `deploy.sh` ou o ADR 0007.
- Editar `CLAUDE.md`, `AGENTS.md` ou `.claude/` para refletir a nova forma de autenticação dos agentes: PR próprio depois deste item (toca fora de `docs/**`, passa pelo `code-reviewer` e pelo `pr-reviewer`); ver seção 9.
- Hook `PreToolUse` que bloqueie `gh pr merge` ou a aprovação de deployment nos agentes: mitigação complementar possível, tarefa separada (o `CLAUDE.md` já aponta hooks como o caminho para impor restrições).
- Exigir revisão aprovada em PR (`required_pull_request_reviews`): um único mantenedor (S5, "Fora do escopo").
- Repositório `models`.

## 3. Fase do roadmap

"Segurança em CI" (fase própria do índice, ADR 0006), como pré-requisito do PR 39 da Fase 3 de `docs/plataforma-ml.md` ("Pipelines do GitHub Actions nos dois repositórios"). O ADR 0007, item 11, exige estas condições "verificadas antes do primeiro deploy automático".

## 4. Arquivos a criar ou alterar

**Nenhum arquivo do repositório**, além de preencher a seção "Registro da escolha" (5.5) deste plano num PR só de `docs/**`. Mudam só Settings do GitHub, contas e as credenciais do ambiente onde os agentes rodam.

### Contexto (por que isto existe)

- ADR 0007, item 11: "Merge na `main` equivale a root na VPS. O environment `production` não tem required reviewers e a `main` não exige revisão aprovada (um único mantenedor). Os agentes de IA usam o `gh` autenticado do mantenedor e nada impede um `gh pr merge`; o risco só é aceito com estas condições, verificadas antes do primeiro deploy automático: (a) branch protection com os checks required e 'Do not allow bypassing' ativa; (b) as credenciais do GitHub disponíveis aos agentes não podem fazer merge na `main` nem aprovar deployment (token fine-grained ou conta separada), **ou**, se isso não for viável, o environment `production` passa a ter o mantenedor como required reviewer."
- Estado atual: o `CLAUDE.md` registra que as restrições de uso do Bash pelos agentes (só leitura, não comentar no PR etc.) são "só por instrução do prompt (não imposto)". Os agentes rodam no mesmo usuário do Windows do mantenedor e herdam o `gh` autenticado dele (token com escopo `repo` e papel de admin) e as credenciais do Git Credential Manager. Nada técnico impede um `gh pr merge`, um `git push origin HEAD:main` (bloqueado só pelos checks do S5) ou um `gh api` que aprove um deployment.
- Depois do PR 39, um merge na `main` chega à VPS e executa o `deploy.sh` do commit mergeado como o usuário `deploy`, que está no grupo `docker` (equivalente a root).

Os comandos são de bash (Git Bash ou WSL) salvo onde indicado PowerShell. Defina o repositório uma vez por sessão:

```bash
R=<owner>/<repo>
```

## 5. Passos

### 5.1. Diagnóstico do estado atual (no terminal onde os agentes rodam)

- [ ] `gh auth status` → mostra a conta do mantenedor (é o risco que este item fecha).
- [ ] `gh api user --jq .login` → `<login do mantenedor>`.
- [ ] `gh api "repos/$R" --jq '.permissions | [.admin, .push]'` → `[true,true]`.
- [ ] (PowerShell) `cmdkey /list | Select-String github` → anote se há entrada `git:https://github.com` (credencial do Git Credential Manager, usada por `git push`).

### 5.2. Pré-condição (a): branch protection do S5 ativa

- [ ] Conferir:

  ```bash
  gh api "repos/$R/branches/main/protection" --jq '[(.required_status_checks.checks | map(.context) | sort | join(",")), .required_status_checks.strict, .enforce_admins.enabled, .allow_force_pushes.enabled]'
  ```

  → `["compose-smoke,dependency-review,lint-and-test,trivy-config,trivy-fs,zizmor",true,true,false]`. `enforce_admins: true` é o "Do not allow bypassing". Se a saída for outra, pare e conclua o S5 (seção 5.8 de `docs/plans/S5-settings-seguranca-manual.md`) antes de seguir.

### 5.3. Escolher a opção

| | (b1) Agentes sem poder de merge (conta separada) | (b2) Mantenedor como required reviewer de `production` |
| --- | --- | --- |
| O que impede | Merge na `main` e qualquer ação de admin pela credencial dos agentes, por regra do GitHub | Deploy sem um clique de aprovação |
| Protege contra um agente que usa a credencial que tem | **Sim**: a conta dos agentes não tem como fazer merge nem aprovar | **Não totalmente**: se o agente ainda tiver o token do mantenedor, ele pode aprovar o deployment pela API (`POST repos/$R/actions/runs/<id>/pending_deployments`) e fazer o merge; a barreira passa a ser só a instrução do prompt e a visibilidade |
| Custo | Segunda conta do GitHub (machine account, com 2FA), convite de colaborador, um ruleset, e os agentes passam a rodar num contexto (usuário do Windows ou distro WSL) onde só essa conta está autenticada; o mantenedor faz todo merge pela própria conta | Um comando; cada deploy (inclusive de PR do Dependabot, a reexecução do bootstrap e a prova da rotação de chave) espera o clique do mantenedor |
| Efeito no fluxo atual | `task-implementer` abre PR com a conta dos agentes; quem faz merge é sempre o mantenedor | Nenhum para os agentes; o deploy fica pendente até a aprovação |

**Recomendação: (b1), na variante com contexto separado (5.4.b1, item 5, variante I).** Motivo: é a única opção que muda o que a credencial dos agentes **consegue** fazer; a (b2) só acrescenta um passo que a mesma credencial do mantenedor também consegue cumprir. Se a (b1) não for viável agora, aplique a (b2) e registre em 5.5 que o risco residual do agente com o token do mantenedor continua aceito (ADR 0007, item 11, "se isso não for viável"). Nada impede aplicar as duas.

Por que não "token fine-grained do mantenedor" para os agentes: um token fine-grained que consegue empurrar branches precisa de `Contents: write`, que também permite fazer merge de PR; e ele age como o mantenedor (admin), que é justamente quem pode passar pela regra de merge do 5.4.b1. A separação só funciona com uma conta que **não** é admin.

### 5.4. Aplicar a opção escolhida

#### (b1) Conta separada para os agentes

1. [ ] Criar a conta (web, deslogado da sua): uma machine account, por exemplo `<owner>-agent`, com e-mail próprio e **2FA ligado**. Os termos do GitHub permitem uma conta de máquina por pessoa.
2. [ ] Convidar como colaboradora com escrita (como mantenedor, no seu contexto normal):

   ```bash
   gh api -X PUT "repos/$R/collaborators/<agent-login>" -f permission=push
   ```

   Em repositório de conta pessoal, colaborador sempre tem escrita; o `permission` é ignorado.
3. [ ] Ruleset que deixa só admin atualizar a `main`, e só por PR (como mantenedor). O papel "Repository admin" tem `actor_id` 5:

   ```bash
   printf '%s' '{"name":"main-merge-by-admin-only","target":"branch","enforcement":"active","conditions":{"ref_name":{"include":["refs/heads/main"],"exclude":[]}},"rules":[{"type":"update"},{"type":"deletion"},{"type":"non_fast_forward"}],"bypass_actors":[{"actor_id":5,"actor_type":"RepositoryRole","bypass_mode":"pull_request"}]}' | gh api -X POST "repos/$R/rulesets" --input -
   ```

   O `bypass` deste ruleset vale só para as regras **dele** (atualizar, apagar, force push). Os checks required continuam na branch protection do S5, com `enforce_admins: true`, e valem também para o mantenedor.
4. [ ] Conferir o ruleset (como mantenedor):

   ```bash
   gh api "repos/$R/rulesets" --jq '.[] | select(.name=="main-merge-by-admin-only") | [.id, .enforcement]'
   gh api "repos/$R/rulesets/<id>" --jq '[.bypass_actors, ([.rules[].type] | sort)]'
   ```

   → `[<id>,"active"]` e `[[{"actor_id":5,"actor_type":"RepositoryRole","bypass_mode":"pull_request"}],["deletion","non_fast_forward","update"]]`.
5. [ ] Ambiente dos agentes. Escolha uma variante:
   - **Variante I (recomendada): contexto separado.** Um usuário do Windows ou uma distro WSL só para os agentes, onde o mantenedor **nunca** faz login no GitHub. Lá: instalar `gh` e `git`, `gh auth login` com a conta `<agent-login>`, `gh auth setup-git`, `git config --global user.name "<agent-login>"`, `git config --global user.email "<id>+<agent-login>@users.noreply.github.com"`, clonar o repositório e rodar o Claude Code a partir desse clone. O seu contexto normal continua com a sua conta para merges, Settings e os itens manuais (S5, 38, este).
   - **Variante II: mesmo usuário do Windows.** Tirar as suas credenciais desse usuário e deixar só a da conta dos agentes: `gh auth logout --hostname github.com --user <login do mantenedor>`; (PowerShell) `cmdkey /delete:git:https://github.com` (se a entrada existir no 5.1); `gh auth login` com `<agent-login>`; `gh auth setup-git`. A partir daí, você faz merge, aprovações e Settings **pelo navegador**; para comandos `gh api` de admin, use um token fine-grained de curta duração só no seu terminal (`GH_TOKEN`), revogado em seguida. Risco residual: processos do mesmo usuário do Windows conseguem, em tese, ler a sessão do navegador e o ambiente do seu terminal.
6. [ ] Aceitar o convite **no contexto dos agentes**:

   ```bash
   gh api user/repository_invitations --jq '.[] | [.id, .repository.full_name]'
   gh api -X PATCH "user/repository_invitations/<id>"
   ```

7. [ ] Verificar **no contexto dos agentes** (todas as saídas abaixo vão para o 5.5):
   - `gh api user --jq .login` → `<agent-login>`.
   - `gh auth status` → só `<agent-login>`.
   - `gh api "repos/$R" --jq '.permissions | [.admin, .maintain, .push]'` → `[false,false,true]`.
   - `git config --get credential.https://github.com.helper` → contém `gh auth git-credential` (o `git push` usa a conta dos agentes).
   - Push direto recusado: `git switch -c chore/s6-merge-probe && git commit --allow-empty -m "chore: s6 merge probe" && git push origin HEAD:main` → `rejected` (regra do repositório).
   - Merge recusado: `git push -u origin chore/s6-merge-probe`, `gh pr create --base main --title "chore: s6 merge probe" --body "Probe for plan S6; do not merge."`, esperar os checks e `gh pr merge <n> --squash` → falha citando regra do repositório. Depois `gh pr close <n> --delete-branch`.
   - Autoria do push: `gh api "repos/$R/events" --jq '[.[] | select(.type=="CreateEvent")][0].actor.login'` → `<agent-login>`.
8. [ ] Verificar **no seu contexto** que você continua fazendo merge: o próximo PR real é mergeado pela sua conta normalmente (os checks required continuam valendo).
9. [ ] Aprovação de deployment: com (b1) sozinho, o environment `production` não tem reviewers, então não há o que aprovar; a conta dos agentes não é admin e não consegue mudar o environment (`.permissions.admin` falso no item 7).

#### (b2) Mantenedor como required reviewer de `production`

Rode **depois** do item 38 (o `PUT` do item 38 substitui a configuração do environment).

1. [ ] Aplicar (no seu contexto):

   ```bash
   ME_ID="$(gh api user --jq .id)"
   printf '{"wait_timer":0,"prevent_self_review":false,"reviewers":[{"type":"User","id":%s}],"deployment_branch_policy":{"protected_branches":false,"custom_branch_policies":true}}' "$ME_ID" | gh api -X PUT "repos/$R/environments/production" --input -
   ```

   `prevent_self_review: false` é necessário: com um único mantenedor, quem faz o merge (e portanto dispara o deploy) é o mesmo que aprova.
2. [ ] Conferir:

   ```bash
   gh api "repos/$R/environments/production" --jq '[.protection_rules[] | {type, prevent_self_review, reviewers: [.reviewers[]?.reviewer.login]}]'
   gh api "repos/$R/environments/production/deployment-branch-policies" --jq '[.branch_policies[].name]'
   ```

   → uma regra `required_reviewers` com `reviewers: ["<login do mantenedor>"]` e `prevent_self_review: false`, a regra `branch_policy`, e `["main"]`.
3. [ ] Prova no primeiro deploy (PR 39): o job `deploy` fica em "Waiting" até você aprovar na página do run (Review deployments → Approve). Aprove só depois de conferir o SHA e o PR de origem.

### 5.5. Registro da escolha (preencher)

| Campo | Valor |
| --- | --- |
| Data (`TZ=America/Sao_Paulo date +%F`) | |
| Opção aplicada | (b1) variante I / (b1) variante II / (b2) / (b1) + (b2) |
| Saída do 5.2 | |
| Saídas da verificação (b1, item 7) ou (b2, item 2) | |
| Risco residual aceito (se (b2) sem (b1)) | "Um agente com o token do mantenedor consegue aprovar deployment e fazer merge pela API; aceito até a (b1)." |

Sem segredo, token, IP ou nome da tailnet nas saídas coladas.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| Conferência do 5.2 | `["compose-smoke,dependency-review,lint-and-test,trivy-config,trivy-fs,zizmor",true,true,false]` |
| (b1) contexto dos agentes: `gh api user --jq .login` | `<agent-login>` |
| (b1) contexto dos agentes: `gh api "repos/$R" --jq '.permissions \| [.admin, .maintain, .push]'` | `[false,false,true]` |
| (b1) contexto dos agentes: `gh pr merge <n> --squash` no PR de prova | Falha citando regra do repositório |
| (b1) contexto dos agentes: `git push origin HEAD:main` | `rejected` |
| (b1) `gh api "repos/$R/rulesets/<id>" --jq '[.bypass_actors, ([.rules[].type] \| sort)]'` | `[[{"actor_id":5,"actor_type":"RepositoryRole","bypass_mode":"pull_request"}],["deletion","non_fast_forward","update"]]` |
| (b2) `gh api "repos/$R/environments/production" --jq '[.protection_rules[].type] \| sort'` | `["branch_policy","required_reviewers"]` |
| (b2) reviewers da regra `required_reviewers` | `["<login do mantenedor>"]`, `prevent_self_review` `false` |
| Seção 5.5 preenchida e mergeada (PR só de `docs/**`) | Antes do merge do PR 39 |

## 7. Testes necessários

`não`: configuração manual de Settings, contas e credenciais; nada muda no código do repositório.

## 8. Casos de teste

n/a

## 9. Riscos e perguntas em aberto

- **Não verificado nesta revisão** (sem acesso à API): que o `actor_id` 5 do `RepositoryRole` é "Repository admin" e que repositório de conta pessoal aceita esse bypass no ruleset; que a regra `update` impede o merge de PR por colaborador com escrita (o item 7 do (b1) prova na prática); os valores exatos de `protection_rules[].type`. Se o ruleset recusar o bypass por papel, **não** aplique um ruleset `update` sem bypass (ele bloquearia também os seus merges): pare e devolva para o planejamento; a (b2) continua disponível enquanto isso.
- **(b2) não protege contra o agente com o token do mantenedor** (seção 5.3). Fica registrado em 5.5 se for a escolha.
- **(b1), variante II:** processos do mesmo usuário do Windows podem, em tese, ler cookies do navegador e o ambiente de outros processos; a variante I evita isso.
- **(b1) e o fluxo do `AGENTS.md`:** o `task-implementer` passa a abrir PR com a conta dos agentes; o `pr-reviewer` e o `code-reviewer` só leem. O Dependabot não muda. Commits dos agentes aparecem com a conta deles.
- **(b1) e reexecução de runs:** colaborador com escrita consegue reexecutar runs do `deploy.yml`. Reexecutar o run mais recente reimplanta o mesmo SHA e os mesmos digests (sem efeito); um run antigo é recusado pelo fast-forward do `deploy.sh`. Aceitável.
- **Pós-item:** atualizar o `CLAUDE.md` ("Específico do Claude Code") e, se preciso, o `AGENTS.md` para registrar com que credencial os agentes rodam, em PR próprio que passa pelo `code-reviewer` e pelo `pr-reviewer`.
- **Revogação da conta dos agentes:** a sessão do `gh` dos agentes é uma credencial de longa duração com escrita no repositório; se houver suspeita, `gh auth logout` no contexto dos agentes, revogar a sessão em Settings → Applications da conta dos agentes e, se preciso, remover a colaboradora: `gh api -X DELETE "repos/$R/collaborators/<agent-login>"`.

## 10. Decisões que exigem ADR

**Nenhuma.** Executa o item 11 do ADR 0007 (`docs/adr/0007-delivery-pipeline.md`), que prevê as duas opções e deixa a escolha ao usuário, registrada neste plano.
