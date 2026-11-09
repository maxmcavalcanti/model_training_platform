# S5 — Settings de segurança do GitHub e checks required (manual)

> Executa: **usuário** (dono do repositório; as Settings vivem fora do git e nenhum agente as altera). Depende de: S2 e S3 na `main` (S3 mergeado em 2026-11-08, `f8cca44`, #49). **Menor data para tornar os checks required: 2026-11-22** (2 semanas depois do merge do S3, ADR 0006, item 8). As Settings das seções 5.1 a 5.6 podem ser ligadas já. Precisa estar concluído antes dos PRs 37 e 39 e do item 38.
> Nome do arquivo: `S5-<slug>.md`, convenção do índice (`docs/plans/00-indice.md`, "Desvios"). O ADR 0006 previa `docs/plans/NNa-settings-seguranca-manual.md`; este é o mesmo item.
> Base: `docs/adr/0006-security-validation-in-ci.md`, itens 1, 8 e 9 da Decisão. Escrito em 2026-11-08 sobre a `main` em `05c32c9`.

## 1. Objetivo

Ligar e conferir, uma a uma por `gh api`, as Settings de segurança do repositório público `platform` que o ADR 0006 exige (secret scanning, push protection, CodeQL, alertas e atualizações do Dependabot, private vulnerability reporting, aprovação de contribuidores externos, workflow permissions read-only).
Depois de 2 semanas sem achado HIGH ou CRITICAL aberto sem exceção (a partir de 2026-11-22), tornar required os seis checks do CI e da segurança na branch protection da `main`, com "Do not allow bypassing".

## 2. Fora do escopo

- Qualquer mudança de código, workflow, `dependabot.yml` ou `SECURITY.md` (já entraram em S1 a S4).
- Environment `production` e segredos do deploy (item 38).
- Repositório `models` (item 40, M3).
- OSV-Scanner e Scorecard (futuros, ADR 0006, item 8).
- Exigir revisão aprovada em PR (`required_pull_request_reviews`): um único mantenedor; a revisão é dos agentes (`AGENTS.md`, "Fluxo de trabalho").

## 3. Fase do roadmap

"Segurança em CI" (fase própria do índice, em paralelo à Fase 2; ADR 0006). O item 8 do ADR: "Cumprido o critério, o usuário torna os checks required no item manual, antes de o deploy automático entrar (até o PR 39)".

## 4. Arquivos a criar ou alterar

**Nenhum arquivo do repositório.** Mudam só as Settings do GitHub. Um arquivo temporário no notebook (`protection.json`, seção 5.8) é apagado no fim.

Os comandos são de bash (no Windows, Git Bash ou WSL), porque usam `printf` com aspas simples e `head`. Defina o repositório uma vez por sessão:

```bash
R=<owner>/<repo>
gh auth status    # precisa de escopo "repo" e de ser admin do repositório
```

## 5. Passos

### 5.1. Secret scanning e push protection

- [ ] Ligar:

  ```bash
  printf '%s' '{"security_and_analysis":{"secret_scanning":{"status":"enabled"},"secret_scanning_push_protection":{"status":"enabled"}}}' | gh api -X PATCH "repos/$R" --input -
  ```

- [ ] Conferir: `gh api "repos/$R" --jq '[.security_and_analysis.secret_scanning.status, .security_and_analysis.secret_scanning_push_protection.status]'` → `["enabled","enabled"]`.

### 5.2. Alertas e atualizações de segurança do Dependabot

Hoje as duas consultas respondem `403`/`404` (desligadas).

- [ ] Ligar os alertas: `gh api -X PUT "repos/$R/vulnerability-alerts"` → sem saída, código 0.
- [ ] Conferir: `gh api -i "repos/$R/vulnerability-alerts" | head -1` → `HTTP/2.0 204 No Content` (`404` = desligado).
- [ ] Ligar as atualizações de segurança: `gh api -X PUT "repos/$R/automated-security-fixes"` → código 0.
- [ ] Conferir: `gh api "repos/$R/automated-security-fixes" --jq .enabled` → `true`.

### 5.3. CodeQL (default setup, também analisa `actions`)

- [ ] Ligar: `gh api -X PATCH "repos/$R/code-scanning/default-setup" -f state=configured -f query_suite=default`.
- [ ] Conferir: `gh api "repos/$R/code-scanning/default-setup" --jq '[.state, (.languages | sort | join(","))]'` → `["configured","actions,python"]` (a lista de linguagens pode demorar alguns minutos para aparecer).

### 5.4. Private vulnerability reporting

- [ ] Ligar: `gh api -X PUT "repos/$R/private-vulnerability-reporting"`.
- [ ] Conferir: `gh api "repos/$R/private-vulnerability-reporting" --jq .enabled` → `true`.

### 5.5. Workflow permissions read-only

- [ ] Aplicar: `gh api -X PUT "repos/$R/actions/permissions/workflow" -f default_workflow_permissions=read -F can_approve_pull_request_reviews=false`.
- [ ] Conferir: `gh api "repos/$R/actions/permissions/workflow" --jq '[.default_workflow_permissions, .can_approve_pull_request_reviews]'` → `["read",false]`.

### 5.6. "Require approval for all external contributors"

- [ ] Aplicar: `gh api -X PUT "repos/$R/actions/permissions/fork-pr-contributor-approval" -f approval_policy=all_external_contributors`.
- [ ] Conferir: `gh api "repos/$R/actions/permissions/fork-pr-contributor-approval" --jq .approval_policy` → `all_external_contributors`. Se o endpoint responder `404` (não disponível na sua conta), aplique pela UI (Settings → Actions → General → "Fork pull request workflows from outside collaborators" → "Require approval for all external contributors") e anote a conferência visual.

### 5.7. Critério de saída do modo "só avisa" (em 2026-11-22 ou depois)

Período: de 2026-11-08 (merge do S3) até o dia da checagem, no mínimo 2 semanas.

- [ ] `TZ=America/Sao_Paulo date +%F` → `2026-11-22` ou depois.
- [ ] Code scanning (CodeQL, zizmor, Trivy com SARIF), HIGH ou CRITICAL abertos:

  ```bash
  gh api "repos/$R/code-scanning/alerts?state=open&per_page=100" --paginate --jq '[.[] | select(.rule.security_severity_level == "high" or .rule.security_severity_level == "critical")] | length'
  ```

  → `0`.
- [ ] Dependabot, HIGH ou CRITICAL abertos:

  ```bash
  gh api "repos/$R/dependabot/alerts?state=open&per_page=100" --paginate --jq '[.[] | select(.security_advisory.severity == "high" or .security_advisory.severity == "critical")] | length'
  ```

  → `0`.
- [ ] Secret scanning abertos: `gh api "repos/$R/secret-scanning/alerts?state=open" --jq length` → `0`.
- [ ] Runs do `security.yml` no período sem falha:

  ```bash
  gh run list --workflow security.yml --created '>=2026-11-08' --limit 200 --json conclusion -q '[.[] | select(.conclusion == "failure")] | length'
  ```

  → `0`. Toda falha que houver precisa estar resolvida por correção no código ou por exceção versionada (ADR 0006, item 9: `.trivyignore`, `# zizmor: ignore[...]` ou `allow-ghsas`, com motivo, link e data de revisão). Alerta dispensado no GitHub leva o motivo no campo próprio. Se houver falha sem isso, não siga: a contagem de 2 semanas recomeça depois da correção.
- [ ] Nomes exatos dos checks: `gh api "repos/$R/commits/main/check-runs" --jq '[.check_runs[].name] | unique'` (e, num PR recente, `gh pr checks <número>`) → aparecem `lint-and-test`, `compose-smoke`, `zizmor`, `dependency-review`, `trivy-config` e `trivy-fs` (o `dependency-review` só aparece em PR). Se algum aparecer com outro nome, use no 5.8 o nome que a API mostrar.

### 5.8. Branch protection da `main` com checks required

- [ ] No notebook, crie `protection.json` (fora do repositório):

  ```json
  {
    "required_status_checks": {
      "strict": true,
      "checks": [
        {"context": "lint-and-test"},
        {"context": "compose-smoke"},
        {"context": "zizmor"},
        {"context": "dependency-review"},
        {"context": "trivy-config"},
        {"context": "trivy-fs"}
      ]
    },
    "enforce_admins": true,
    "required_pull_request_reviews": null,
    "restrictions": null,
    "allow_force_pushes": false,
    "allow_deletions": false
  }
  ```

  `enforce_admins: true` é o "Do not allow bypassing" (ADR 0006, item 9): nem o dono contorna os checks.
- [ ] Aplicar: `gh api -X PUT "repos/$R/branches/main/protection" --input protection.json`.
- [ ] Conferir:

  ```bash
  gh api "repos/$R/branches/main/protection" --jq '[(.required_status_checks.checks | map(.context) | sort | join(",")), .required_status_checks.strict, .enforce_admins.enabled, .allow_force_pushes.enabled]'
  ```

  → `["compose-smoke,dependency-review,lint-and-test,trivy-config,trivy-fs,zizmor",true,true,false]`.
- [ ] Apagar `protection.json`.
- [ ] Prova: o próximo PR mostra os seis checks como "Required" (`gh pr checks <número>` ou a página do PR).

### 5.9. Devolver para o planejamento

Data da checagem do 5.7, as saídas de conferência de 5.1 a 5.6, as quatro contagens do 5.7 e a saída do 5.8. Nada com segredo.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `gh api "repos/$R" --jq '[.security_and_analysis.secret_scanning.status, .security_and_analysis.secret_scanning_push_protection.status]'` | `["enabled","enabled"]` |
| `gh api -i "repos/$R/vulnerability-alerts" \| head -1` | `HTTP/2.0 204 No Content` |
| `gh api "repos/$R/automated-security-fixes" --jq .enabled` | `true` |
| `gh api "repos/$R/code-scanning/default-setup" --jq .state` | `configured` |
| `gh api "repos/$R/private-vulnerability-reporting" --jq .enabled` | `true` |
| `gh api "repos/$R/actions/permissions/workflow" --jq .default_workflow_permissions` | `read` |
| `gh api "repos/$R/actions/permissions/fork-pr-contributor-approval" --jq .approval_policy` | `all_external_contributors` (ou conferência visual anotada) |
| As quatro contagens do 5.7, em 2026-11-22 ou depois | `0`, `0`, `0`, `0` |
| Conferência do 5.8 | `["compose-smoke,dependency-review,lint-and-test,trivy-config,trivy-fs,zizmor",true,true,false]` |

## 7. Testes necessários

`não`: configuração manual de Settings do GitHub; nada muda no repositório.

## 8. Casos de teste

n/a

## 9. Riscos e perguntas em aberto

- **Não verificado nesta revisão** (sem acesso à API): os corpos exatos de resposta de `fork-pr-contributor-approval`, `private-vulnerability-reporting` e `code-scanning/default-setup`, e o nome exato dos checks do `security.yml` na API. O 5.6 e o 5.7 trazem a alternativa.
- **`dependency-review` só roda em PR:** como não há push direto na `main` (`enforce_admins`), ele sempre roda onde importa. Os workflows não têm `paths:` (ADR 0006, item 3), então nenhum check required fica pendente em PR só de docs.
- **`enforce_admins`** vale também para os merges do dono: um check vermelho bloqueia até a correção. A saída prevista é exceção versionada (ADR 0006, item 9), nunca desligar a proteção.
- **PRs do Dependabot** passam pelos mesmos checks; o do `postgres` precisa do commit manual na branch (regra do `AGENTS.md`) antes de ficar verde.
- **Contagem de 2 semanas:** se surgir achado HIGH/CRITICAL sem exceção, ela recomeça; os PRs 37 e 39 e o item 38 esperam.

## 10. Decisões que exigem ADR

**Nenhuma.** Executa os itens 1, 8 e 9 do ADR 0006.
