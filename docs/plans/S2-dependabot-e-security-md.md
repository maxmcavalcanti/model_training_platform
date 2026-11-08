# S2: `dependabot.yml` e `SECURITY.md`

> Executa: agente. Depende de: S1 (mergeado em `a722b74`, "pin actions and base images by digest, least-privilege CI permissions (#46)"). Branch sugerida: `ci/dependabot-security-policy`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar. O índice marcava "não (verificação por comandos)"; este plano muda para `sim` (seção 7), e a linha S2 de `docs/plans/00-indice.md` já foi corrigida junto com este plano.
> Base: `docs/adr/0006-security-validation-in-ci.md` (Aceito, 2026-11-08), itens 1 (o `SECURITY.md` "entra no PR do `dependabot.yml`"), 2, 4, 5 e 12 (segundo dos quatro PRs).

## 1. Objetivo

Criar `.github/dependabot.yml` com os ecossistemas `github-actions`, `docker`, `docker-compose` e `uv`, semanal, com `directories`, `cooldown` e um grupo por ecossistema, para manter os SHAs e digests fixados no S1.
Criar `SECURITY.md` na raiz, que manda reportar pelo "Report a vulnerability" (private vulnerability reporting) do GitHub, com prazo realista para mantenedor único e escopo, sem e-mail, IP ou host; e travar as duas coisas com testes estáticos.

## 2. Fora do escopo

- Workflow `security.yml` (zizmor, dependency-review, Trivy): S3.
- Settings do GitHub (ligar Dependabot alerts e security updates, private vulnerability reporting, secret scanning, CodeQL, branch protection, checks required): S5 e o item manual do ADR 0006, item 1. Este PR só **confere** por `gh api` se o private vulnerability reporting está ligado (ver Q1).
- Auto-merge de PRs do Dependabot, `@dependabot` commands, `CODEOWNERS`, labels customizadas.
- `multi-ecosystem-groups` (um PR só para vários ecossistemas): o ADR pede grupos por ecossistema.
- Atualizar qualquer versão agora: este PR não toca `ci.yml`, `Dockerfile`, compose, `pyproject.toml` nem `uv.lock`. Os primeiros bumps chegam pelos PRs do próprio Dependabot depois do merge.
- Binário do supercronic (`ARG SUPERCRONIC_VERSION`/`SUPERCRONIC_SHA256` em `infra/jobs/Dockerfile`, linhas 13 e 14): o Dependabot não acompanha `ARG` com URL; segue manual até o PR 36 o remover.
- Pacotes `apt` do Dockerfile, versão do Python (`.python-version`, `requires-python`), `hatchling` do `[build-system]`.
- Imagens próprias no GHCR (PR 37), OSV-Scanner, Scorecard, `harden-runner` (ADR 0006: futuros).
- Mudar os testes do S1 (`tests/infra/test_supply_chain_pins.py`, `tests/infra/test_compose.py`).
- Mudar a regra de revisão de PRs do `AGENTS.md` para PRs do Dependabot (ver Q5).
- Escrever ou editar ADR.

## 3. Fase do roadmap

"Segurança em CI (em paralelo à Fase 2)", item S2 de `docs/plans/00-indice.md` (fase própria criada pelo ADR 0006, item 12; não existe em `docs/plataforma-ml.md`). Roda em paralelo à Fase 2 por decisão do usuário em 2026-11-08. É dependência do S5.

## 4. Arquivos a criar ou alterar

| Caminho | Quem | Motivo |
| --- | --- | --- |
| `tests/infra/test_dependabot.py` (novo) | test-writer | Política do `dependabot.yml` (seção 8, casos 1 a 14), com exemplos negativos, no padrão de `tests/infra/test_supply_chain_pins.py` |
| `tests/test_security_policy.py` (novo) | test-writer | Política do `SECURITY.md` (seção 8, casos 15 a 22). Fica fora de `tests/infra/` porque não é infra |
| `.github/dependabot.yml` (novo) | implementer | Configuração (forma-alvo abaixo) |
| `SECURITY.md` (novo, na raiz) | implementer | Política de segurança (rascunho abaixo). Raiz porque o GitHub reconhece `SECURITY.md` na raiz, em `docs/` ou em `.github/`, e na raiz é o mais visível |
| `AGENTS.md` | implementer | Seção "Comandos": comando de validação do `dependabot.yml`. Seção "Fluxo de trabalho": uma linha sobre PRs do Dependabot que trocam o `postgres` (ver passo 9 e risco R1) |
| `docs/plans/00-indice.md` | task-planner (já feito com este plano) | Linha S2, coluna "Testes": `não (verificação por comandos)` → `sim` |

### Estado atual (para o implementador)

Nenhum `.github/dependabot.yml` nem `SECURITY.md` existe hoje (conferido por Glob em 2026-11-08). O que o Dependabot vai manter:

| Ecossistema | Diretório | Arquivo | Referência fixada hoje |
| --- | --- | --- | --- |
| `github-actions` | `/` (lê `.github/workflows/`) | `.github/workflows/ci.yml`, linhas 30, 33 e 53 | `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1` (2x), `astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3` |
| `docker` | `/infra/jobs` | `infra/jobs/Dockerfile`, linha 1 | `ghcr.io/astral-sh/uv:0.9.30-python3.12-bookworm-slim@sha256:e5b6...8e58` |
| `docker-compose` | `/infra` | `infra/docker-compose.yml`, linhas 5 e 20; `infra/docker-compose.dev.yml`, linha 5 | `busybox:1.38.0@sha256:a462...5fa4`; `postgres:16.15@sha256:f9a7...9657` (prod e dev) |
| `uv` | `/` | `pyproject.toml` (dependências com `>=`, grupo `dev` com `pytest`, `pyyaml`, `ruff`) e `uv.lock` | versões travadas no `uv.lock` |

Fora de qualquer ecossistema: o serviço `postgres` do job `lint-and-test` em `.github/workflows/ci.yml`, linha 21 (`image: postgres:16.15@sha256:f9a7...9657`). O `github-actions` do Dependabot atualiza `uses:`, não `services.*.image` (conferir no passo 2). O teste do S1 `test_postgres_reference_is_identical_in_prod_dev_and_ci` (`tests/infra/test_supply_chain_pins.py`, linhas 275 a 282) exige a mesma referência `tag@digest` em prod, dev e CI; ver risco R1.

O formato `uses: <owner>/<repo>@<40 hex> # vX.Y.Z` (um espaço antes de `#`) já é o que o Dependabot reconhece para atualizar SHA e comentário juntos (ADR 0006, item 4). O S1 trava esse formato (`VERSION_COMMENT = re.compile(r"^\s+# v\d+\.\d+\.\d+\s*$")`); um PR do Dependabot que quebre o comentário fica vermelho no CI.

### Forma-alvo do `.github/dependabot.yml`

Valores sujeitos à conferência do passo 2 (chaves e nomes de ecossistema). Comentários em inglês.

```yaml
# Keeps the SHA and digest pins from plan S1 up to date (ADR 0006, items 2, 4 and 5).
version: 2

updates:
  - package-ecosystem: github-actions
    directories:
      - "/"
    schedule:
      interval: weekly
      day: monday
      time: "06:00"
      timezone: America/Sao_Paulo
    cooldown:
      default-days: 7
      semver-major-days: 30
    groups:
      github-actions:
        patterns: ["*"]
    commit-message:
      prefix: chore
      include: scope

  - package-ecosystem: docker
    directories:
      - "/infra/jobs"
    schedule: { mesmo bloco acima }
    cooldown: { mesmo bloco acima }
    groups:
      docker:
        patterns: ["*"]
    commit-message: { mesmo bloco acima }

  - package-ecosystem: docker-compose
    directories:
      - "/infra"
    schedule: { mesmo bloco acima }
    cooldown: { mesmo bloco acima }
    groups:
      docker-compose:
        patterns: ["*"]
    ignore:
      # A Postgres major upgrade needs pg_upgrade or dump/restore, never a tag bump
      - dependency-name: postgres
        update-types: ["version-update:semver-major"]
    commit-message: { mesmo bloco acima }

  - package-ecosystem: uv
    directories:
      - "/"
    schedule: { mesmo bloco acima }
    cooldown: { mesmo bloco acima }
    groups:
      uv:
        patterns: ["*"]
    commit-message: { mesmo bloco acima }
```

`{ mesmo bloco acima }` é notação deste plano: no arquivo, repetir o bloco por extenso (sem âncoras YAML, para o validador e o Dependabot lerem sem surpresa). Resultado esperado dos PRs: um PR por ecossistema por semana, título `chore(deps): bump the <grupo> group ...`.

### Rascunho do `SECURITY.md` (em inglês, ver Q2)

O implementador ajusta a redação, mas mantém as seções e as regras: sem e-mail, sem IP, sem hostname (`*.ts.net` ou outro), sem nome de tailnet, sem dizer quais serviços não têm autenticação, sem detalhe de porta. O link usa o repositório real (`.git/config` tem `https://github.com/maxmcavalcanti/model_training_platform.git`; confirmar com `gh repo view --json url --jq .url`). Link absoluto, porque relativo quebra na aba Security (`/security/policy`).

```markdown
# Security policy

## Supported versions

Only the `main` branch is supported. There are no releases: production runs what is on `main`.

## Reporting a vulnerability

Please do not open a public issue, discussion or pull request for a suspected vulnerability.

Report it privately through GitHub's private vulnerability reporting: open the
**Security** tab of this repository and click **Report a vulnerability**, or go straight to
https://github.com/maxmcavalcanti/model_training_platform/security/advisories/new.

Include the affected file or commit, the steps to reproduce and the impact you expect.
Do not paste working credentials in the report; if you found a leaked secret, say where it is.

## What to expect

This project has a single maintainer, so responses are best effort:

- acknowledgement within 7 days;
- first assessment (accepted, needs more information, or out of scope) within 14 days;
- a fix or mitigation for accepted reports within 90 days, sooner for critical ones.

Disclosure is coordinated through the GitHub security advisory. There is no bug bounty.

## Scope

In scope:

- code in this repository: ingestion jobs, database migrations and role grants, the jobs
  image (`infra/jobs/Dockerfile`), the compose files, scripts and the GitHub Actions workflows;
- secrets committed to the repository or its history;
- supply-chain issues, such as an action or image not pinned by SHA or digest, or a workflow
  that could leak a token or run untrusted code;
- a database role defined here being able to do more than its documented grants.

Out of scope:

- the services are not exposed to the internet; they are reachable only from a private
  network. Do not try to find or reach the production host. Issues that require existing
  access to that private network or to the host are out of scope, unless they let a role
  do more than it is granted;
- vulnerabilities in upstream projects (PostgreSQL, MLflow, Prefect, Grafana, Tailscale,
  Python packages, base images) without a misconfiguration in this repository; report those
  upstream;
- the separate `models` repository;
- the public data sources (Open-Meteo, ONS) and the data they publish;
- denial of service, rate limiting, social engineering;
- scanner output or missing hardening without a demonstrated impact.
```

## 5. Passos

1. Criar a branch `ci/dependabot-security-policy` a partir da `main`. Não há passo 0: `pyyaml` já é dependência de dev (`pyproject.toml`, `[dependency-groups].dev`).
2. (implementer, antes de escrever o YAML; pode rodar antes do test-writer, porque o resultado pode mudar a forma-alvo) Conferir na documentação oficial do Dependabot, que é a fonte de verdade (a forma-alvo acima vem de memória do planner e não foi conferida na rede):
   1. Baixar as páginas em Markdown para o scratchpad (pasta temporária fora do repo):
      - `curl -fsSL "https://docs.github.com/api/article/body?pathname=/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference" -o <scratch>/options.md`
      - `curl -fsSL "https://docs.github.com/api/article/body?pathname=/en/code-security/dependabot/ecosystems-supported-by-dependabot/supported-ecosystems-and-repositories" -o <scratch>/ecosystems.md`
      - Se a API de artigo responder 404, abrir as mesmas páginas em `https://docs.github.com/en/...` no navegador, ou ler o fonte com `gh api repos/github/docs/contents/content/code-security/dependabot/working-with-dependabot/dependabot-options-reference.md --jq .content | base64 -d`. Se o caminho tiver mudado, achar o atual com `gh search code --repo github/docs "semver-major-days"`.
   2. Confirmar, com `grep -n` nos arquivos baixados (ex.: `grep -nE 'docker-compose|uv' <scratch>/ecosystems.md`), e registrar no corpo do PR uma tabela `pergunta | resposta | trecho da doc`:
      - a. Os valores literais de `package-ecosystem` são `github-actions`, `docker`, `docker-compose` e `uv`.
      - b. `directories` é aceito em todos os quatro, é lista, e não pode coexistir com `directory` no mesmo bloco.
      - c. `cooldown` existe, com que chaves (`default-days`, `semver-major-days`, `semver-minor-days`, `semver-patch-days`, `include`, `exclude`), e se vale para os quatro ecossistemas. Se `semver-*-days` não valer para `docker`, `docker-compose` ou `github-actions`, manter só `default-days: 7` nesses blocos. Conferir também que cooldown não atrasa security updates.
      - d. `groups` com `patterns: ["*"]` agrupa todas as atualizações de versão do ecossistema; e se atualizações só de digest (mesma tag, digest novo) entram no grupo.
      - e. `schedule.interval: weekly` com `day`, `time` (string `"HH:MM"`) e `timezone` (nome IANA).
      - f. `ignore` com `dependency-name` e `update-types: ["version-update:semver-major"]` vale para `docker-compose`.
      - g. Quais nomes de arquivo o `docker-compose` lê. Em especial: `docker-compose.dev.yml` é lido? Se não for, registrar e seguir (risco R1 cobre).
      - h. `docker` e `docker-compose` atualizam referência `tag@sha256:<digest>` (tag e digest juntos) e `github-actions` atualiza `@<sha> # vX.Y.Z` (SHA e comentário juntos).
      - i. Se o `github-actions` atualiza `jobs.*.services.*.image` dos workflows (esperado: não).
   3. Se alguma resposta contrariar a forma-alvo, ajustar o YAML para o que a doc diz e anotar no PR. Se contrariar um caso de teste da seção 8 (por exemplo, `cooldown` não suportado num ecossistema), parar e avisar o usuário antes de seguir: o implementer não edita testes.
3. (test-writer) Escrever `tests/infra/test_dependabot.py` e `tests/test_security_policy.py` conforme a seção 8. Rodar `uv run pytest tests/infra/test_dependabot.py tests/test_security_policy.py` e mostrar que as políticas sobre os arquivos reais falham pelo motivo certo (arquivos ausentes) e que os exemplos positivos e negativos das funções de checagem passam. Rodar `uv run ruff check .` e `uv run ruff format --check .` (a regra `S` está ligada; em `pyproject.toml`, `[tool.ruff.lint.per-file-ignores]`, `tests/**` já ignora `S101` e `S608`; não usar o literal `"0.0.0.0"` nos exemplos, para não disparar `S104`). Commit `test: expect dependabot config and security policy`.
4. (implementer) Criar `.github/dependabot.yml` na forma-alvo da seção 4, já ajustada pelo passo 2.
5. (implementer) Validar o schema com o JSON Schema do SchemaStore, sem adicionar dependência ao projeto: `uvx --from check-jsonschema==<X.Y.Z> check-jsonschema --builtin-schema vendor.dependabot .github/dependabot.yml`, com `<X.Y.Z>` = versão mais recente publicada (`curl -fsSL https://pypi.org/pypi/check-jsonschema/json | python -c "import json,sys; print(json.load(sys.stdin)['info']['version'])"`), registrada no PR. Esperado: `ok -- validation done`. O schema do SchemaStore pode estar atrasado em relação à doc (`cooldown`, `uv`, `docker-compose`); se o único erro for uma chave ou ecossistema que a doc do passo 2 confirma, registrar no PR com o trecho da doc e seguir.
6. (implementer) Conferir o private vulnerability reporting (só leitura): `gh api repos/maxmcavalcanti/model_training_platform/private-vulnerability-reporting --jq .enabled`. Se der `false`, avisar o usuário no PR: ele liga em Settings → Code security → "Private vulnerability reporting" antes do merge (Q1). Nenhum agente muda Settings.
7. (implementer) Criar `SECURITY.md` na raiz a partir do rascunho da seção 4.
8. (implementer) `AGENTS.md`, seção "Comandos": acrescentar `- Validar o dependabot.yml: uvx --from check-jsonschema==<X.Y.Z> check-jsonschema --builtin-schema vendor.dependabot .github/dependabot.yml` (com a versão do passo 5).
9. (implementer) `AGENTS.md`, seção "Fluxo de trabalho": acrescentar uma linha: "PR do Dependabot que troca o `postgres` de `infra/docker-compose.yml`: levar o mesmo `tag@sha256:` ao serviço `postgres` do `.github/workflows/ci.yml` (e ao `infra/docker-compose.dev.yml`, se o Dependabot não o atualizar), por commit na própria branch do Dependabot; o teste `test_postgres_reference_is_identical_in_prod_dev_and_ci` fica vermelho até isso. Merge de PR do Dependabot que muda `infra/` só chega à VPS pelo deploy manual do usuário (ADR 0004), fora da janela dos jobs." Ajustar o parêntese conforme a resposta do passo 2g.
10. Rodar os critérios de pronto (seção 6) e colar as saídas no PR.
11. (usuário, depois do merge) Rodar os critérios marcados "pós-merge".

## 6. Critérios de pronto

Comandos em bash (Git Bash no Windows, ou o runner). Nenhum deles lê `.env`.

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/test_dependabot.py tests/test_security_policy.py` | Todos passam |
| `uv run pytest` (com `docker compose -f infra/docker-compose.dev.yml up -d`) | Todos passam (inclusive os do S1, sem mudança) |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem erro, código 0 |
| `uvx --from check-jsonschema==<X.Y.Z> check-jsonschema --builtin-schema vendor.dependabot .github/dependabot.yml` | `ok -- validation done`, ou erro só em chave/ecossistema confirmado pela doc no passo 2 (trecho colado no PR) |
| `grep -c 'package-ecosystem:' .github/dependabot.yml` | `4` |
| `grep -c 'interval: weekly' .github/dependabot.yml` | `4` |
| `grep -c 'cooldown:' .github/dependabot.yml` | `4` |
| `grep -nE '^\s+directory:' .github/dependabot.yml` | Sem saída (código 1) |
| `grep -nEi '[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}' SECURITY.md` | Sem saída (código 1) |
| `grep -nE '([0-9]{1,3}\.){3}[0-9]{1,3}' SECURITY.md` | Sem saída (código 1) |
| `grep -niF 'ts.net' SECURITY.md` | Sem saída (código 1) |
| `grep -c 'https://github.com/maxmcavalcanti/model_training_platform/security/advisories/new' SECURITY.md` | `1` ou mais |
| `gh api repos/maxmcavalcanti/model_training_platform/private-vulnerability-reporting --jq .enabled` | `true` (se `false`, o usuário liga antes do merge, Q1) |
| Tabela do passo 2 no corpo do PR | As 9 perguntas respondidas, com trecho da doc |
| `gh pr checks` | `lint-and-test` e `compose-smoke` em `pass` |
| `git diff --name-only main...HEAD` | Só os arquivos da seção 4 (mais `docs/plans/00-indice.md` e este plano, se commitados na branch) |
| Pós-merge (usuário): `gh api graphql -f query='{repository(owner:"maxmcavalcanti",name:"model_training_platform"){isSecurityPolicyEnabled securityPolicyUrl}}'` | `isSecurityPolicyEnabled: true` e `securityPolicyUrl` apontando para o `SECURITY.md` |
| Pós-merge (usuário): Insights → Dependency graph → Dependabot | Os 4 ecossistemas listados, sem erro de configuração; "Check for updates" roda sem erro |
| Pós-merge (usuário), na semana seguinte: `gh pr list --author app/dependabot --json title,headRefName` | PRs com título `chore(deps): ...`, no máximo um por grupo; num PR de `github-actions`, as linhas `uses:` continuam `@<40 hex> # vX.Y.Z` (o teste do S1 passa no CI do PR) |

## 7. Testes necessários

`sim`: um teste estático é barato (só `pyyaml` e regex, sem rede, roda no Windows), segue o padrão de `tests/infra/` e impede regressões que nenhum comando pega sozinho depois do merge: um PR futuro (29, 30, 37) que crie um Dockerfile ou compose num diretório que o Dependabot não lê, um diretório que deixe de existir, ou um e-mail/IP/host colado no `SECURITY.md` de um repositório público. O que depende de rede (schema oficial, private vulnerability reporting, Dependabot lendo o arquivo) fica nos comandos da seção 6.

## 8. Casos de teste

Notas para o test-writer: carregar o YAML com `yaml.safe_load`; cada regra tem função de checagem que recebe a estrutura (ou o texto) e devolve a lista de problemas, com exemplos que aceitam e que rejeitam, como em `tests/infra/test_supply_chain_pins.py`. Os caminhos do Dependabot começam com `/` e são relativos à raiz do repo; as funções que olham o disco recebem a raiz como parâmetro, para os exemplos usarem `tmp_path`.

`tests/infra/test_dependabot.py`, políticas sobre o arquivo real `.github/dependabot.yml`:

1. O arquivo existe e é um mapa com `version` igual ao inteiro `2`.
2. Os valores de `package-ecosystem` em `updates` são exatamente `{github-actions, docker, docker-compose, uv}`, cada um uma vez.
3. Todo bloco usa `directories` (lista não vazia de strings que começam com `/`) e nenhum usa `directory`.
4. Diretórios esperados: `github-actions` → `["/"]`; `uv` → `["/"]`; `docker` contém `/infra/jobs`; `docker-compose` contém `/infra`.
5. Todo diretório listado existe no repositório.
6. Todo diretório tem o manifesto do seu ecossistema: `github-actions` → existe pelo menos um `.github/workflows/*.yml` ou `*.yaml` abaixo dele; `uv` → `pyproject.toml` e `uv.lock`; `docker` → `Dockerfile`; `docker-compose` → pelo menos um `docker-compose*.yml`, `docker-compose*.yaml`, `compose*.yml` ou `compose*.yaml`.
7. Cobertura inversa: todo `Dockerfile` encontrado sob `infra/` está num diretório listado no `docker`; todo diretório sob `infra/` que tenha `docker-compose*.yml` está listado no `docker-compose`.
8. Todo bloco tem `schedule.interval` igual a `weekly`.
9. Todo bloco tem `cooldown` como mapa com `default-days` inteiro maior ou igual a 1.
10. Todo bloco tem `groups` com exatamente um grupo, e os `patterns` desse grupo contêm `"*"`.
11. O bloco `docker-compose` tem em `ignore` uma entrada com `dependency-name: postgres` cujo `update-types` contém `version-update:semver-major`.
12. Todo bloco tem `commit-message.prefix` igual a `chore`.

Exemplos para as funções de checagem (entrada → resultado):

13. Rejeitados: `version: 1`; `version: "2"` (string); faltando o ecossistema `uv`; `docker` duas vezes; ecossistema extra `pip`; bloco com `directory: "/"` em vez de `directories`; `directories: []`; `directories: ["infra"]` (sem `/`); diretório `/infra/nope` inexistente; diretório do `docker` sem `Dockerfile`; `Dockerfile` em `infra/mlflow/` sem `/infra/mlflow` listado; `interval: daily`; bloco sem `cooldown`; `cooldown: {default-days: 0}`; `cooldown: {}`; bloco sem `groups`; grupo com `patterns: ["actions/*"]`; dois grupos no mesmo bloco; `docker-compose` sem o `ignore` do `postgres` major; `ignore` do `postgres` só com `version-update:semver-minor`; `commit-message` ausente.
14. Aceito: um config mínimo montado no teste com os quatro blocos corretos sobre uma árvore em `tmp_path` com `.github/workflows/ci.yml`, `pyproject.toml`, `uv.lock`, `infra/jobs/Dockerfile` e `infra/docker-compose.yml`.

`tests/test_security_policy.py`, políticas sobre o arquivo real `SECURITY.md` (na raiz):

15. O arquivo existe na raiz do repositório.
16. Contém pelo menos um link `https://github.com/<owner>/<repo>/security/advisories/new` e o texto `Report a vulnerability`.
17. Contém as seções `Reporting a vulnerability`, `What to expect` e `Scope`, e o texto `Out of scope`.
18. Não contém endereço de e-mail.
19. Não contém IPv4 literal.
20. Não contém hostname `*.ts.net` (sem diferenciar maiúsculas).

Exemplos para as funções de checagem (entrada → resultado):

21. E-mail: `contact me at a@b.co` → detectado; `user.name+x@example.com.br` → detectado; `git@github.com:owner/repo` → detectado; `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` → não detectado; `@dependabot rebase` → não detectado.
22. IPv4: `100.64.0.1` → detectado; `192.0.2.10:5432` → detectado; `v7.0.1` → não detectado; `16.15` → não detectado. Host: `vps.tail1234.ts.net` → detectado; `VPS.TAIL1234.TS.NET` → detectado; `Tailscale` → não detectado.

Casos existentes que devem continuar passando sem mudança: todo `tests/infra/` (em especial `test_supply_chain_pins.py` e `test_compose.py`).

## 9. Riscos e perguntas em aberto

Riscos:

- **R1. Paridade do `postgres` em três arquivos.** O `docker-compose` do Dependabot atualiza `infra/docker-compose.yml` (e talvez o `.dev.yml`, passo 2g), mas não o `services.postgres.image` do `ci.yml` (passo 2i). Como o `postgres:16.15` oficial é reconstruído com frequência, PRs de digest vão aparecer e ficar vermelhos em `test_postgres_reference_is_identical_in_prod_dev_and_ci`. É o comportamento desejado (paridade do S1); a correção é um commit na branch do Dependabot (passo 9). Depois desse commit o Dependabot para de fazer rebase automático da branch; aceitável para um PR por semana.
- **R2. Major de Postgres.** Sem o `ignore` do caso 11, o Dependabot proporia `postgres:17` ou `18`, que não sobe sobre um volume da 16. O `ignore` trava; upgrade de major é tarefa própria.
- **R3. Grupo com major junto.** `patterns: ["*"]` põe majors no mesmo PR semanal (por exemplo, um major de `pandas` ou do `ruff`), e o PR inteiro fica vermelho. Mitigação: `semver-major-days: 30` atrasa majors; um major problemático sai do grupo com `@dependabot ignore <dependência> major version` no PR, ou vira PR próprio. Um bump do `ruff` pode trazer achados novos da regra `S` (plano S4, seção 9).
- **R4. `uv.lock` escrito por outro `uv`.** O Dependabot regera o `uv.lock` com a versão do `uv` dele; a imagem dos jobs usa `uv 0.9.30` com `uv sync --locked`. Se o formato do lock mudar, o `compose-smoke` (build do `jobs`) fica vermelho no PR do Dependabot, que é onde deve falhar. O primeiro PR de `docker` (imagem `uv`) tende a resolver.
- **R5. Imagem `uv` com sufixo.** A tag `0.9.30-python3.12-bookworm-slim` tem sufixo; o esperado é o Dependabot só propor tags com o mesmo sufixo, mantendo Python 3.12 e Debian bookworm. Conferir no primeiro PR de `docker`.
- **R6. Supercronic fora do Dependabot.** Continua fixado por versão e SHA-256 à mão até o PR 36.
- **R7. Schema do SchemaStore atrasado.** O passo 5 pode acusar `cooldown` ou um ecossistema novo como inválido; a doc oficial (passo 2) prevalece, com o trecho no PR. O GitHub só mostra erro de configuração depois do merge (critério pós-merge).
- **R8. Deploy na VPS.** Merge de PR do Dependabot que muda `infra/` muda a referência de imagem em produção no próximo deploy manual (ADR 0004), feito só pelo usuário, fora das 06:30, 06:45 e 07:00 (`America/Sao_Paulo`).
- **R9. Dado sensível no `SECURITY.md`.** Repo público: qualquer e-mail, IP, hostname ou nome de tailnet fica no histórico para sempre. Os casos 18 a 20 e os greps da seção 6 travam; o rascunho não descreve quais serviços não têm autenticação.

Perguntas (com recomendação; o usuário aceita recomendações):

- **Q1. Private vulnerability reporting desligado.** O link do `SECURITY.md` só funciona com a Setting ligada, e as Settings são do S5, que depende deste PR. Recomendação: o usuário liga só essa Setting antes do merge do S2 (o passo 6 confere); o S5 confere de novo com as outras. Alternativa rejeitada: mergear com o link morto até o S5, porque um relato acabaria em issue pública.
- **Q2. Idioma do `SECURITY.md`.** Não fica em `docs/` e é lido por quem reporta de fora, como título e corpo de PR (inglês pelo ADR 0001). Recomendação: inglês. Alternativa: bilíngue (mais texto para manter).
- **Q3. Majors no mesmo grupo.** Recomendação: um grupo por ecossistema com `patterns: ["*"]`, sem filtro `update-types`, mais `semver-major-days: 30` (R3). Motivo: o ADR pede "agrupado", e um filtro `update-types: [minor, patch]` pode deixar atualizações só de digest fora do grupo (passo 2d). Alternativa: majors em PRs separados.
- **Q4. Valores de `cooldown` e horário.** Recomendação: `default-days: 7`, `semver-major-days: 30`, segunda-feira às 06:00 `America/Sao_Paulo`.
- **Q5. Revisão dos PRs do Dependabot.** Pelo `AGENTS.md`, todo PR fora de `docs/**` passa por `code-reviewer` e `pr-reviewer`, o que dá até quatro PRs por semana com duas revisões cada. Recomendação: manter a regra neste PR (não mudar o `AGENTS.md` nesse ponto); se pesar, o usuário decide uma regra própria para PRs do Dependabot num PR separado.
- **Q6. Comando de validação no `AGENTS.md`.** `uvx` baixa o `check-jsonschema` do PyPI na hora, fora do `uv.lock`. Recomendação: registrar com versão exata (`==X.Y.Z`, passo 8) e não adicionar como dependência de dev.

## 10. Decisões que exigem ADR

Nenhuma nova. O ADR 0006 (Aceito, 2026-11-08) já decide os quatro ecossistemas, os `directories`, `cooldown`, `groups`, a frequência semanal e que o `SECURITY.md` entra neste PR. Se o passo 2 mostrar que `docker-compose` ou `uv` não existem como ecossistema do Dependabot, ou que `cooldown` não vale para algum deles, o item 2 do ADR 0006 estaria descrevendo algo impossível: parar e avisar o usuário, que decide se emenda o ADR (tarefa separada) antes da implementação.
