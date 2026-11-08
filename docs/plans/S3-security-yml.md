# S3 — Workflow `security.yml` (zizmor, dependency-review, Trivy) em modo só-avisa

> Executa: agente. Depende de: S1 (na `main` desde o commit `a722b74`). Não depende do S2 (o `.github/dependabot.yml` ainda não existe; ver riscos). Branch sugerida: `ci/security-workflow`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar. O índice marca "não (verificação por comandos)"; este plano muda para `sim` (seção 7), e a linha S3 do índice é corrigida no passo 2.
> Base: `docs/adr/0006-security-validation-in-ci.md` (Aceito, 2026-11-08), itens 3, 6, 7, 8, 9 e 10 da Decisão. Nome do arquivo: `S3-<slug>.md`, convenção do índice (`docs/plans/00-indice.md`, "Desvios"), não `<AAAA-MM-DD>-<slug>.md`.

## 1. Objetivo

Criar `.github/workflows/security.yml`, que roda em todo `pull_request` e em push na `main` quatro jobs de nome estável (`zizmor`, `dependency-review`, `trivy-config`, `trivy-fs`), com `permissions: {}` no topo, o mínimo por job e SARIF no code scanning.
Os jobs falham quando há achado, mas ainda não são required (modo só-avisa, ADR 0006, item 8). Testes estáticos em `tests/infra/` travam a forma do workflow e a política de exceções.

## 2. Fora do escopo

- OSV-Scanner, OpenSSF Scorecard (action ou `id-token: write`) e `harden-runner` (ADR 0006, item 8 e "fora de escopo").
- Tornar os checks required, mudar branch protection e qualquer Setting do GitHub (S5, manual, feito pelo usuário). Este PR **não** marca nada como required.
- `.github/dependabot.yml` e `SECURITY.md` (S2). Até o S2 entrar, ninguém atualiza SHAs, a versão do `zizmor` nem o digest do Trivy automaticamente.
- CodeQL (default setup é Setting, S5). Regra `S` do `ruff` (S4, já na `main`).
- Trivy da imagem construída (`trivy image`) com attestation: entra junto da publicação no GHCR (PR 37), com ADR próprio (ADR 0006, "fora de escopo").
- `trivy config` sobre o `docker-compose`: o ADR 0006, item 3, não afirma essa cobertura; as regras do compose seguem em `tests/infra/test_compose.py` e no job `compose-smoke`.
- Corrigir vulnerabilidades de dependência que o Trivy ou o dependency-review acharem (`uv lock --upgrade-package ...`): vai em PR próprio (`fix(deps): ...`), não neste. Exceção: achado no próprio `security.yml` ou no `ci.yml` que o zizmor apontar é corrigido aqui (passo 11).
- Dependency submission (envio do `uv.lock` ao dependency graph pela API): só entra se o critério do SBOM falhar, e em PR próprio (ver Q8).
- Gatilho `schedule` (varredura agendada): ver Q7.
- Mexer no `ci.yml` além do que um achado do zizmor exigir. `actionlint` (PR 37).
- Editar o ADR 0006 ou escrever ADR novo.

## 3. Fase do roadmap

"Segurança em CI (em paralelo à Fase 2)", item S3 de `docs/plans/00-indice.md`. Não é uma fase de `docs/plataforma-ml.md` (o doc não fala de segurança em CI); é a fase própria criada pelo ADR 0006, item 12 (terceiro dos quatro PRs), em paralelo à Fase 2 por decisão do usuário em 2026-11-08.

## 4. Arquivos a criar ou alterar

| Caminho | Quem | Motivo |
| --- | --- | --- |
| `docs/plans/00-indice.md` | task-planner (ou o usuário), passo 2 | Linha S3: coluna "Testes" de "não (verificação por comandos)" para "sim" |
| `tests/infra/test_security_workflow.py` (novo) | test-writer | Forma do `security.yml` (seção 8, casos 1 a 22) e política de exceções (casos 23 a 26), com exemplos negativos |
| `.github/workflows/security.yml` (novo) | implementer | O workflow |
| `pyproject.toml` e `uv.lock` | implementer (`uv add --dev zizmor`) | zizmor como dependência de dev travada por hash no `uv.lock` (Q2) |
| `AGENTS.md`, seção "Comandos" | implementer | Registrar `uv run zizmor .` e os comandos locais do Trivy (regra do índice: cada PR registra os seus comandos) |
| `.trivyignore` (novo, **só se** houver exceção aprovada pelo usuário) | implementer | Política de exceções (ADR 0006, item 9) |

`tests/infra/test_supply_chain_pins.py` **não muda**. Conferido em 2026-11-08: `workflow_files()` (linhas 190–191) faz glob de `.github/workflows/*.yml` e `*.yaml`, então o `security.yml` entra automaticamente nos testes parametrizados de pin por SHA com `# vX.Y.Z` (`test_every_action_is_pinned_by_sha_with_a_version_comment`), de `permissions` no topo (`test_every_workflow_declares_top_level_permissions`; `top_permissions_problems` aceita `{}`), de `persist-credentials: false` (`test_checkout_does_not_persist_credentials`), de gatilhos proibidos (`test_no_workflow_uses_dangerous_triggers`) e de imagens em `services`/`container`. Só valem para o `ci.yml`: `test_ci_workflow_does_not_reference_secrets` (linha 252), `minimal_permissions_problems` (exige topo `{contents: read}`, linha 80, por isso **não** se aplica ao `security.yml`) e as contagens de `uses:`/checkout. Esses três pontos e a imagem do Trivy dentro de `run:` (que nenhum teste atual lê) são cobertos pelo arquivo novo. O arquivo novo pode importar as funções do S1 (`from tests.infra.test_supply_chain_pins import image_reference_problems, uses_problems, USES_LINE`), porque `tests/__init__.py` e `tests/infra/__init__.py` existem.

### Contexto que o implementador precisa

Regras do ADR 0006 que este PR cumpre (citação resumida):

- Item 3: `security.yml` **sem filtro `paths:`** ("um check required com `paths:` fica pendente para sempre em PR só de docs") e **com nomes de job estáveis**. Três checagens: `zizmor`; `dependency-review-action` com `fail-on-severity: high`; Trivy `config` no(s) Dockerfile(s) e `fs` para vulnerabilidades e segredos, severidades HIGH e CRITICAL, com `ignore-unfixed`. "O Trivy roda por action pinada por SHA conferido ou por imagem fixada por digest."
- Item 6: `permissions: {}` no topo; cada job declara o mínimo (`contents: read`, e `security-events: write` só onde sobe SARIF). Nenhum `pull_request_target` nem `workflow_run`. Em PR de fork o upload de SARIF é pulado.
- Item 7: `security.yml` não usa segredos.
- Item 8: o job falha (fica vermelho) mas não é required. Critério de saída: zero achados HIGH ou CRITICAL abertos sem exceção registrada, por 2 semanas seguidas de PRs; cumprido, o usuário torna os checks required no S5.
- Item 9: rebaixar um check só por exceção versionada (`.trivyignore`, `# zizmor: ignore[...]`, `allow-ghsas`) com motivo, link do alerta e data de revisão, ou por `continue-on-error`.
- Item 10: não se afirma que o dependency graph cobre o `uv.lock`; o pronto deste PR confere o SBOM e abre um PR de teste com versão vulnerável.
- Contexto do ADR: em 2026-03-19, 76 das 77 tags do `aquasecurity/trivy-action` foram redirecionadas para commits maliciosos. Tags não são imutáveis; só SHA e digest são.

Estado atual: `.github/workflows/ci.yml` é o único workflow. Usa `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1` e `astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3`, topo `permissions: contents: read`, jobs `lint-and-test` e `compose-smoke`, nenhum `${{ }}` dentro de `run:`, nenhum `secrets.`. Único Dockerfile: `infra/jobs/Dockerfile` (base `ghcr.io/astral-sh/uv:0.9.30-python3.12-bookworm-slim@sha256:e5b6...`, `apt-get install --no-install-recommends`, `USER app`, sem `HEALTHCHECK`). `pyproject.toml`: grupo `dev` com `pytest`, `pyyaml`, `ruff`. Um Grep em 2026-11-08 por padrões de token (`BEGIN ... PRIVATE KEY`, `ghp_`, `github_pat_`, `AKIA...`, `xox[bp]-`, `sk-...`) não achou nada no repo.

### Forma-alvo do `security.yml` (ilustrativa: SHAs, versões e digest são resolvidos nos passos 4 a 6; flags conferidas no `--help` da versão fixada)

```yaml
name: security

on:
  pull_request:
  push:
    branches: [main]

permissions: {}

env:
  # Trivy runs from an image pinned by digest, not from aquasecurity/trivy-action (ADR 0006)
  TRIVY_IMAGE: ghcr.io/aquasecurity/trivy:<X.Y.Z>@sha256:<digest do índice>

jobs:
  zizmor:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3
      - run: uv sync --locked --only-dev
      - name: Run zizmor (SARIF)
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set +e
          uv run --no-sync zizmor --format sarif . > "$RUNNER_TEMP/zizmor.sarif"
          code=$?
          set -e
          # 0 = clean, >= 10 = findings; anything else is a tool error
          if [ "$code" -ne 0 ] && [ "$code" -lt 10 ]; then exit "$code"; fi
      - name: Upload zizmor SARIF
        if: ${{ !cancelled() && (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository) }}
        uses: github/codeql-action/upload-sarif@<40 hex> # vX.Y.Z
        with:
          sarif_file: ${{ runner.temp }}/zizmor.sarif
          category: zizmor
      - name: Fail on zizmor findings
        env:
          GH_TOKEN: ${{ github.token }}
        run: uv run --no-sync zizmor .

  dependency-review:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/dependency-review-action@<40 hex> # vX.Y.Z
        with:
          fail-on-severity: high
          fail-on-scopes: runtime, development

  trivy-config:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Run Trivy config on Dockerfiles (SARIF)
        run: |
          mkdir -p "$RUNNER_TEMP/trivy-out"
          docker run --rm --user "$(id -u):$(id -g)" \
            -v "$GITHUB_WORKSPACE:/src:ro" -v "$RUNNER_TEMP/trivy-out:/out" -w /src \
            "$TRIVY_IMAGE" config --misconfig-scanners dockerfile --skip-check-update \
            --severity HIGH,CRITICAL --exit-code 0 --format sarif --output /out/trivy-config.sarif .
      - name: Upload Trivy config SARIF
        if: ${{ !cancelled() && (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository) }}
        uses: github/codeql-action/upload-sarif@<40 hex> # vX.Y.Z
        with:
          sarif_file: ${{ runner.temp }}/trivy-out/trivy-config.sarif
          category: trivy-config
      - name: Fail on Trivy config findings
        run: |
          docker run --rm --user "$(id -u):$(id -g)" -v "$GITHUB_WORKSPACE:/src:ro" -w /src \
            "$TRIVY_IMAGE" config --misconfig-scanners dockerfile --skip-check-update \
            --severity HIGH,CRITICAL --exit-code 1 .

  trivy-fs:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Run Trivy fs for vulnerabilities and secrets (SARIF)
        run: |
          mkdir -p "$RUNNER_TEMP/trivy-out" "$RUNNER_TEMP/trivy-cache"
          docker run --rm --user "$(id -u):$(id -g)" \
            -v "$GITHUB_WORKSPACE:/src:ro" -v "$RUNNER_TEMP/trivy-out:/out" \
            -v "$RUNNER_TEMP/trivy-cache:/cache" -w /src \
            "$TRIVY_IMAGE" fs --cache-dir /cache --scanners vuln,secret --include-dev-deps \
            --severity HIGH,CRITICAL --ignore-unfixed \
            --exit-code 0 --format sarif --output /out/trivy-fs.sarif .
      - name: Upload Trivy fs SARIF
        if: ${{ !cancelled() && (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository) }}
        uses: github/codeql-action/upload-sarif@<40 hex> # vX.Y.Z
        with:
          sarif_file: ${{ runner.temp }}/trivy-out/trivy-fs.sarif
          category: trivy-fs
      - name: Fail on Trivy fs findings
        run: |
          docker run --rm --user "$(id -u):$(id -g)" \
            -v "$GITHUB_WORKSPACE:/src:ro" -v "$RUNNER_TEMP/trivy-cache:/cache" -w /src \
            "$TRIVY_IMAGE" fs --cache-dir /cache --skip-db-update --scanners vuln,secret \
            --include-dev-deps --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 .
```

Notas da forma-alvo:

- **Sem `name:` nos jobs**: o nome do check é o id do job (`zizmor`, `dependency-review`, `trivy-config`, `trivy-fs`). É o nome que o S5 vai marcar como required; renomear depois quebra a branch protection.
- **`dependency-review` em push na `main`** fica `skipped` pelo `if:`. Check `skipped` conta como sucesso para required, então o nome continua estável.
- **Por que SARIF primeiro e depois o passo que falha**: o passo de SARIF sai com 0 para o upload sempre acontecer; o passo final repete a varredura em formato tabela (legível no log) e é ele que deixa o job vermelho. No `trivy-fs` o segundo passo reusa o banco baixado (`--skip-db-update` com o mesmo `--cache-dir`).
- **Nenhum `${{ }}` dentro de `run:`** (evita injeção de template, auditoria `template-injection` do zizmor): o que o shell precisa entra por `env:` (`$TRIVY_IMAGE`, `$GH_TOKEN`) ou por variável padrão do runner (`$GITHUB_WORKSPACE`, `$RUNNER_TEMP`).
- **`if:` em uma linha só**: `if: |` com `${{ }}` em bloco vira string sempre verdadeira (auditoria `unsound-condition` do zizmor).
- **`GH_TOKEN: ${{ github.token }}`** é o token efêmero do job (somente leitura aqui), não um segredo do repositório; o texto do arquivo não contém `secrets.` (ADR 0006, item 7). Ele habilita as auditorias online do zizmor (`impostor-commit`, `ref-version-mismatch`, `known-vulnerable-actions`), que repetem a conferência do S1 a cada PR.
- **`setup-uv` sem `enable-cache`** neste workflow: evita qualquer superfície de cache poisoning num workflow de segurança.
- **`--user "$(id -u):$(id -g)"`**: o Trivy roda sem root e os arquivos de saída ficam do usuário do runner. O checkout é montado `:ro`.
- **`--skip-check-update`** no `config`: usa as checagens embutidas no binário fixado por digest, em vez de baixar um bundle de checagens não fixado (Q6). O banco de vulnerabilidades do `fs` continua sendo baixado a cada execução: é dado, não código, e precisa estar atual.
- **`.trivyignore`**: o Trivy lê `.trivyignore` do diretório de trabalho (`-w /src`, raiz do repo) por padrão; confirmar no `--help` (`--ignorefile`).
- **Fork**: em PR de fork o `GITHUB_TOKEN` é somente leitura, e o upload falharia; por isso o `if:` pula o upload e as varreduras rodam do mesmo jeito.

## 5. Passos

1. Criar a branch `ci/security-workflow` a partir da `main` atualizada (`git switch main && git pull && git switch -c ci/security-workflow`). Não há passo 0: os testes novos só usam `pyyaml` e `tomllib`, que já existem.
2. (task-planner, ou o usuário; commit `docs: S3 needs tests`) Em `docs/plans/00-indice.md`, linha S3, coluna "Testes": "não (verificação por comandos)" → "sim". Nada mais no índice.
3. (test-writer) Escrever `tests/infra/test_security_workflow.py` conforme a seção 8. Enquanto o `security.yml` não existe, o carregador devolve `{}` e o caso 1 falha com mensagem clara; os demais falham por asserção, não por exceção de import. Rodar `uv run pytest tests/infra/test_security_workflow.py` e mostrar que os casos de política falham pelo motivo certo e que os exemplos negativos (casos 27 a 33) passam. Rodar também `uv run ruff check tests/` e `uv run ruff format --check tests/`. Commit `test: expect a least-privilege security workflow`.
4. (implementer) Resolver o SHA de cada action nova, sem inventar, com o procedimento do plano S1, passo 4 (copiado aqui):
   1. Versão: a release mais recente estável de `github/codeql-action` no major atual (tag `vX.Y.Z`; **não** usar tags `codeql-bundle-*`) e de `actions/dependency-review-action`: `gh release list --repo <owner>/<repo> --limit 10` (ignorar pré-releases). Preferir uma release publicada há pelo menos 7 dias.
   2. SHA: `gh api repos/<owner>/<repo>/git/ref/tags/<tag> --jq '.object.type + " " + .object.sha'`. Se o tipo for `commit`, é o SHA. Se for `tag` (anotada), desreferenciar com `gh api repos/<owner>/<repo>/git/tags/<sha-do-objeto-tag> --jq '.object.type + " " + .object.sha'` → `commit <sha>`. Conferir com `git ls-remote --tags https://github.com/<owner>/<repo> "refs/tags/<tag>*"` (o commit é o da linha `^{}` quando houver).
   3. Validar: `gh api repos/<owner>/<repo>/commits/<sha> --jq .sha` → o mesmo SHA; `gh api "repos/<owner>/<repo>/compare/<tag>...<sha>" --jq .status` → `identical` (fecha o caso de commit de fork servido pelo repo pai).
   4. `actions/checkout` e `astral-sh/setup-uv`: **reusar os mesmos SHAs do `ci.yml`** (caso 21), sem upgrade.
   5. Registrar no PR a tabela `action | tag | sha | saída do compare`.
5. (implementer) zizmor como dependência de dev: `uv add --dev zizmor` (pega a última versão; o `uv.lock` fixa a versão exata com hash). Conferir `grep -A1 '^name = "zizmor"' uv.lock` e que a versão é a mesma da última release em `gh release list --repo zizmorcore/zizmor --limit 5`. Rodar `uv run zizmor --version` e `uv run zizmor --help` e confirmar as flags usadas (`--format sarif`, códigos de saída: 0 sem achado, 10 ou mais com achado; se a versão tiver `--no-exit-codes`, pode substituí-lo no passo de SARIF, mantendo a distinção entre erro e achado). Commitar `pyproject.toml` e `uv.lock` (`build: add zizmor as a dev dependency`).
6. (implementer) Imagem do Trivy, com cuidado redobrado pelo incidente de março de 2026:
   1. Ler os avisos de segurança publicados: `gh api repos/aquasecurity/trivy/security-advisories --jq '.[] | [.ghsa_id, .severity, .published_at, .summary] | @tsv'` e o mesmo para `aquasecurity/trivy-action` e `aquasecurity/setup-trivy`, mais a página da Aqua citada no ADR 0006. Anotar as versões do binário e das imagens afetadas. Este plano **não** afirma quais são; o implementador registra no PR o que leu.
   2. Escolher a versão: `gh release list --repo aquasecurity/trivy --limit 15`; a release estável mais recente que **não** esteja na lista de afetadas e tenha sido publicada há pelo menos 7 dias. Se houver dúvida sobre uma versão, escolher uma anterior sem dúvida e registrar.
   3. Digest do índice multi-arch: `docker buildx imagetools inspect ghcr.io/aquasecurity/trivy:<X.Y.Z>`. A linha `Digest:` do topo é o digest; `MediaType` deve ser `application/vnd.oci.image.index.v1+json` ou `application/vnd.docker.distribution.manifest.list.v2+json`; `Manifests` deve listar `Platform: linux/amd64`.
   4. Conferência cruzada: `docker buildx imagetools inspect aquasec/trivy:<X.Y.Z>` (Docker Hub) deve dar o mesmo `Digest:`. Se diferir, **parar e perguntar ao usuário** (não escolher sozinho).
   5. Assinatura (se o `cosign` estiver instalado; ele não é ferramenta do repo): `cosign verify ghcr.io/aquasecurity/trivy:<X.Y.Z>@sha256:<digest> --certificate-identity-regexp '^https://github.com/aquasecurity/trivy/' --certificate-oidc-issuer https://token.actions.githubusercontent.com`. Verificação que falha = parar e perguntar. Sem `cosign`, registrar "não verificado por assinatura" no PR.
   6. `docker run --rm ghcr.io/aquasecurity/trivy:<X.Y.Z>@sha256:<digest> --version` → `Version: <X.Y.Z>`. Rodar `... config --help` e `... fs --help` e confirmar as flags da forma-alvo (`--misconfig-scanners`, `--skip-check-update`, `--scanners`, `--include-dev-deps`, `--ignore-unfixed`, `--skip-db-update`, `--cache-dir`, `--exit-code`, `--format sarif`, `--output`). Flag que não existir na versão: ajustar e anotar no PR (não inventar substituto; se não houver equivalente, perguntar).
   7. Registrar no PR a tabela `imagem | tag | digest | MediaType | digest no Docker Hub | cosign`.
7. (implementer) Criar `.github/workflows/security.yml` na forma-alvo da seção 4, com os valores dos passos 4 a 6. Rodar `uv run pytest tests/infra/` até ficar verde.
8. (implementer) Rodar o zizmor localmente: `uv run zizmor .` (sem `GH_TOKEN`, as auditorias online são puladas; com `gh` logado, `GH_TOKEN="$(gh auth token)" uv run zizmor .` roda também as online; o token fica só no ambiente do comando, nunca em arquivo). Saída esperada: sem achados (ver "Achados prováveis" na seção 9).
9. (implementer, em bash: Linux, WSL ou Git Bash com `MSYS_NO_PATHCONV=1`) Rodar o Trivy localmente com a mesma imagem e as mesmas flags dos passos de falha: `docker run --rm -v "$PWD:/src:ro" -w /src "$TRIVY_IMAGE" config --misconfig-scanners dockerfile --skip-check-update --severity HIGH,CRITICAL --exit-code 1 .` e `docker run --rm -v "$PWD:/src:ro" -w /src "$TRIVY_IMAGE" fs --scanners vuln,secret --include-dev-deps --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 .`, com `TRIVY_IMAGE` igual ao do workflow. Rodar a partir de um checkout limpo ou de um worktree sem `.venv` (senão o `fs` varre o ambiente local e acha coisa que o CI não acha); se houver `.venv`, acrescentar `--skip-dirs .venv` só no comando local.
10. Tratar os achados dos passos 8 e 9 pela política do ADR 0006, item 9:
    - Achado verdadeiro no `security.yml` ou no `ci.yml` (zizmor): **corrigir** neste PR.
    - Vulnerabilidade com correção numa dependência (Trivy `fs` ou dependency-review): **não corrigir aqui**; listar no PR e abrir PR próprio `fix(deps): ...` com `uv lock --upgrade-package <pacote>`. O `trivy-fs` pode entrar vermelho (modo só-avisa).
    - Falso positivo ou risco aceito: **só com aprovação do usuário**, por exceção versionada no formato do caso 23: no `.trivyignore`, linha de comentário `# exception: <motivo>; <link do alerta>; review <AAAA-MM-DD>` seguida da linha `<ID> exp:<mesma data>`; no workflow, a mesma linha de comentário logo acima da linha com `# zizmor: ignore[<auditoria>]`. Data de revisão de no máximo 90 dias. O implementador não cria exceção sem o "sim" do usuário no PR.
11. (implementer) `AGENTS.md`, seção "Comandos", acrescentar (texto em português, comandos como estão):
    - `- Auditoria dos workflows: uv run zizmor . (auditorias online: GH_TOKEN="$(gh auth token)" uv run zizmor .)`
    - `- Trivy local (bash; mesma imagem do TRIVY_IMAGE em .github/workflows/security.yml): docker run --rm -v "$PWD:/src:ro" -w /src <TRIVY_IMAGE> config --misconfig-scanners dockerfile --skip-check-update --severity HIGH,CRITICAL --exit-code 1 . e o mesmo com fs --scanners vuln,secret --include-dev-deps --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 .`
    Ajustar as flags se o passo 6.6 mudou alguma.
12. Abrir o PR (o usuário, ou o implementer se instruído). Título sugerido: `ci: add security workflow with zizmor, dependency review and Trivy`. Corpo: tabelas dos passos 4 e 6, saídas dos passos 8 e 9, achados e tratamento (passo 10), e a frase "checks not required yet (ADR 0006, item 8); exit criterion tracked in S5".
13. Com o PR aberto, conferir o dependency graph e o `uv.lock` (ADR 0006, item 10):
    1. SBOM: `gh api 'repos/{owner}/{repo}/dependency-graph/sbom' --jq '.sbom.packages[] | select(.name | test("numpy|sqlalchemy|pyyaml"; "i")) | .name + " " + .versionInfo'`. Cobertura do `uv.lock` = aparecem `numpy` (transitiva do `pandas`) e `pyyaml` (dev) com as versões exatas do `uv.lock` (hoje `numpy 2.5.4`, `pyyaml 6.0.3`, `sqlalchemy 2.1.8`; conferir com `grep -A1 -E '^name = "(numpy|pyyaml|sqlalchemy)"' uv.lock`). Se só aparecerem as faixas do `pyproject.toml` (`>=`) ou não aparecer a transitiva, o grafo **não** cobre o `uv.lock`: registrar no PR e seguir a Q8.
    2. PR de teste com versão vulnerável (descartável, **nunca mergeado**): da branch do S3, `git switch -c test/vulnerable-dependency`, `uv add --dev "django==3.2"` (versão com advisories HIGH e CRITICAL conhecidos; conferir antes com `gh api /advisories -X GET -f ecosystem=pip -f affects=django@3.2 --jq '.[] | .ghsa_id + " " + .severity' | head`), commit, push e `gh pr create --draft --base ci/security-workflow --title "test: vulnerable dependency (do not merge)" --body "ADR 0006 item 10 check"`. Esperado: `dependency-review` e `trivy-fs` falham citando GHSAs do Django. Registrar `gh pr checks <n>` no PR do S3; depois `gh pr close <n> --delete-branch`. Se o `dependency-review` não rodar porque a base não é `main`, repetir com `--base main` (continua draft e é fechado sem merge).
14. Rodar os critérios de pronto (seção 6) e colar as saídas no PR. Revisão: `code-reviewer` e `pr-reviewer` (o PR toca `.github/`, ADR 0006, item 11).
15. Depois do merge (usuário): conferir a execução em push na `main` e as análises no code scanning (últimas linhas da seção 6). A data do merge é o início da contagem das 2 semanas do critério de saída; registrá-la no S5.

## 6. Critérios de pronto

Comandos em bash (Git Bash no Windows, ou o runner). Nenhum deles lê `.env`.

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/` | Todos passam (inclui os de `test_supply_chain_pins.py` parametrizados agora também com `security.yml`) |
| `uv run pytest` (com `docker compose -f infra/docker-compose.dev.yml up -d`) | Todos passam |
| `uv run ruff check .` e `uv run ruff format --check .` | Código 0 |
| `uv sync --locked` | Código 0 (lock coerente com o `pyproject.toml`) |
| `uv run zizmor .` | Código 0, sem achados |
| `uv run python -c "import yaml,sys; d=yaml.safe_load(open('.github/workflows/security.yml')); print(d['permissions'], sorted(d['jobs']))"` | `{} ['dependency-review', 'trivy-config', 'trivy-fs', 'zizmor']` |
| `grep -nE '^permissions: \{\}$' .github/workflows/security.yml` | Uma linha |
| `grep -nE 'paths(-ignore)?:' .github/workflows/security.yml` | Sem saída (código 1) |
| `grep -nE 'secrets\.\|pull_request_target\|workflow_run\|aquasecurity/(trivy-action\|setup-trivy)' .github/workflows/security.yml` | Sem saída (código 1) |
| `grep -c 'github.event.pull_request.head.repo.full_name == github.repository' .github/workflows/security.yml` | `3` (um por upload de SARIF) |
| `grep -cE 'uses: [A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40} # v[0-9]+\.[0-9]+\.[0-9]+$' .github/workflows/security.yml` igual a `grep -c 'uses:' .github/workflows/security.yml` | Os dois números iguais |
| Para cada action nova: `gh api "repos/<owner>/<repo>/compare/<tag>...<sha>" --jq .status` | `identical` |
| `docker buildx imagetools inspect "<TRIVY_IMAGE sem o @digest>"` | `Digest:` igual ao fixado; `MediaType` de índice; `Platform: linux/amd64` listado |
| `docker run --rm "<TRIVY_IMAGE>" --version` | `Version: <X.Y.Z>` fixada |
| `gh pr checks` | `zizmor`, `dependency-review`, `trivy-config`, `trivy-fs`, `lint-and-test` e `compose-smoke` presentes; os quatro de segurança em `pass`, ou em `fail` com cada achado listado no PR e tratado pelo passo 10 |
| Passo 13.1 (SBOM) | `numpy 2.5.4`, `pyyaml 6.0.3`, `sqlalchemy 2.1.8` (ou as versões do `uv.lock` na hora), ou o registro "não cobre" com a decisão da Q8 |
| Passo 13.2 (`gh pr checks <n>` do PR de teste) | `dependency-review` e `trivy-fs` em `fail`; PR fechado sem merge (`gh pr view <n> --json state,mergedAt` → `CLOSED`, `null`) |
| `gh api 'repos/{owner}/{repo}/branches/main/protection/required_status_checks' --jq '.contexts'` | Não contém nenhum dos quatro jobs de segurança (ou 404 se não houver checks required): o PR não os torna required |
| `git diff --name-only main...HEAD` | Só os arquivos da seção 4 |
| Após o merge: `gh run list --workflow security.yml --branch main --event push --limit 1 --json conclusion,status` | `status: completed`; no run, `dependency-review` aparece `skipped` |
| Após o merge: `gh api 'repos/{owner}/{repo}/code-scanning/analyses?ref=refs/heads/main' --jq '[.[].category] \| unique'` | Contém `zizmor`, `trivy-config` e `trivy-fs` |

## 7. Testes necessários

`sim`: o workflow é configuração, mas carrega regras de segurança do ADR 0006 (`permissions: {}`, mínimo por job, sem `paths:`, nomes estáveis, sem segredos, upload pulado em fork, imagem do Trivy por digest, política de exceções) que um PR futuro pode quebrar em silêncio; testes estáticos com `pyyaml`, sem rede, seguem o padrão de `tests/infra/test_supply_chain_pins.py` e custam pouco. A verificação de que SHA e digest pertencem à versão e de que as varreduras rodam fica nos comandos da seção 6.

## 8. Casos de teste

Arquivo novo `tests/infra/test_security_workflow.py`. Mesmo padrão do S1: cada regra é uma função de checagem que devolve uma lista de problemas, aplicada ao arquivo real e a exemplos embutidos que aceitam e que rejeitam. Notas para o test-writer: o PyYAML lê a chave `on:` como `True` (usar `data.get("on", data.get(True))`); o PyYAML perde comentários, então as regras de comentário (casos 23 a 26) leem o texto linha a linha; `pull_request:` vazio vira `None`. Reusar `uses_problems`, `image_reference_problems` e `USES_LINE` de `tests.infra.test_supply_chain_pins` em vez de duplicar. Não editar `tests/infra/test_supply_chain_pins.py`.

Políticas sobre o arquivo real `.github/workflows/security.yml`:

1. O arquivo existe e o YAML é um mapeamento não vazio.
2. O nome do workflow é `security`.
3. Os gatilhos são exatamente `pull_request` e `push`; `push` tem `branches: [main]`; nenhum gatilho tem `paths` nem `paths-ignore`; `pull_request` não tem filtro de `branches`.
4. O `permissions` do topo é exatamente o mapeamento vazio `{}`.
5. Os ids dos jobs são exatamente `zizmor`, `dependency-review`, `trivy-config`, `trivy-fs`; nenhum job tem `name:` diferente do próprio id.
6. Todo job declara `permissions` como mapeamento não vazio, com `contents: read`; as únicas chaves permitidas são `contents` (só `read`) e `security-events` (só `write`).
7. Um job tem `security-events: write` se e só se tem passo `github/codeql-action/upload-sarif@`.
8. Todo passo de upload de SARIF tem `if:` em uma linha que contém `!cancelled()` e `github.event.pull_request.head.repo.full_name == github.repository`; tem `with.sarif_file` e `with.category`; as categorias são distintas entre si (`zizmor`, `trivy-config`, `trivy-fs`).
9. O texto do arquivo não contém `secrets.`.
10. Nenhum valor de `run:` contém `${{`.
11. Nenhum `if:` de job ou passo é um bloco de várias linhas (string com quebra de linha).
12. O job `dependency-review` tem `if:` que restringe a `github.event_name == 'pull_request'`, usa `actions/dependency-review-action@` e tem `with.fail-on-severity` igual a `high`.
13. O `env.TRIVY_IMAGE` do topo existe e passa em `image_reference_problems` (forma `<nome>:<tag>@sha256:<64 hex>`, tag diferente de `latest`).
14. Todo `run:` que contém `docker run` referencia `"$TRIVY_IMAGE"` e nenhuma outra imagem literal; todo `run:` que chama o Trivy está nos jobs `trivy-config` ou `trivy-fs`.
15. Nenhum workflow do repo (`.github/workflows/*.yml` e `*.yaml`) usa `aquasecurity/trivy-action` nem `aquasecurity/setup-trivy` (Q1).
16. No job `trivy-config`, os `run:` que chamam o Trivy usam o subcomando `config`, `--misconfig-scanners dockerfile` e `--severity HIGH,CRITICAL`; pelo menos um tem `--exit-code 1`.
17. No job `trivy-fs`, os `run:` que chamam o Trivy usam `fs`, `--scanners vuln,secret`, `--severity HIGH,CRITICAL` e `--ignore-unfixed`; pelo menos um tem `--exit-code 1`.
18. Nos dois jobs do Trivy, a montagem do checkout é somente leitura (`:/src:ro`).
19. O job `zizmor` instala as dependências com `uv sync --locked` (alguma variante com `--locked`), chama `zizmor` por `uv run`, e o `GH_TOKEN`, quando presente, vem de `${{ github.token }}`.
20. O `pyproject.toml` (lido com `tomllib`) tem `zizmor` no grupo `dev` de `[dependency-groups]`, e o `uv.lock` tem um pacote `name = "zizmor"`.
21. A mesma action (`owner/repo[/caminho]`) usada em mais de um workflow aparece com o mesmo SHA e o mesmo comentário `# vX.Y.Z` em todos eles (hoje: `actions/checkout` e `astral-sh/setup-uv` em `ci.yml` e `security.yml`).
22. Nenhum passo do `security.yml` usa `astral-sh/setup-uv` com `enable-cache: true`.

Política de exceções (ADR 0006, item 9). Formato da linha de exceção: `# exception: <motivo não vazio>; <URL http(s)>; review <AAAA-MM-DD>`.

23. Se `.trivyignore` existir na raiz: toda linha que não é comentário nem vazia tem `exp:<AAAA-MM-DD>` e é precedida imediatamente por uma linha de exceção cuja data de revisão é igual à do `exp:`. Se não existir, o caso passa.
24. Em todo workflow, toda linha com `zizmor: ignore[` é precedida imediatamente por uma linha de exceção.
25. No `security.yml`, toda linha que contém um id `GHSA-xxxx-xxxx-xxxx` (por exemplo numa lista `allow-ghsas`) é precedida imediatamente por uma linha de exceção.
26. No `security.yml`, `continue-on-error` só aparece se precedido imediatamente por uma linha de exceção (hoje: não aparece; o modo só-avisa é "job vermelho e não required", não `continue-on-error`).

Exemplos para as funções de checagem (entrada → resultado):

27. Gatilhos: `{pull_request: None, push: {branches: [main]}}` → aceito; com `paths: [src/**]` em `push` → rejeitado; com `paths-ignore` em `pull_request` → rejeitado; `push` com `branches: [main, dev]` → rejeitado; acréscimo de `schedule` → rejeitado; `pull_request: {branches: [main]}` → rejeitado.
28. Permissões do topo: `{}` → aceito; `{contents: read}` → rejeitado; ausente → rejeitado; `read-all` → rejeitado.
29. Permissões de job: `{contents: read}` sem upload → aceito; `{contents: read, security-events: write}` com upload → aceito; `{contents: read, security-events: write}` sem upload → rejeitado; upload com `{contents: read}` → rejeitado; ausente ou `{}` → rejeitado; `{contents: write}` → rejeitado; `{contents: read, pull-requests: write}` → rejeitado; `{contents: read, id-token: write}` → rejeitado.
30. Upload de SARIF: `if` com `!cancelled()` e a guarda de fork → aceito; sem `if` → rejeitado; `if` só com `always()` → rejeitado; guarda de fork ausente → rejeitado; duas categorias iguais → rejeitado; sem `category` → rejeitado.
31. `run:` e `if:`: `run: echo "$TRIVY_IMAGE"` → aceito; `run: echo ${{ github.head_ref }}` → rejeitado; `if: github.event_name == 'pull_request'` → aceito; `if:` como bloco `|` de duas linhas → rejeitado; texto com `${{ secrets.X }}` → rejeitado; texto com `${{ github.token }}` → aceito pela regra 9.
32. Imagem do Trivy: `ghcr.io/aquasecurity/trivy:0.1.0@sha256:` + 64 hex → aceita; `aquasec/trivy:latest` → rejeitada; `aquasec/trivy:0.1.0` → rejeitada; `run: docker run --rm "$TRIVY_IMAGE" fs .` → aceito; `run: docker run --rm aquasec/trivy:0.1.0 fs .` → rejeitado; `uses: aquasecurity/trivy-action@` + 40 hex + ` # v0.1.0` → rejeitado pela regra 15. Flags: `fs` sem `--ignore-unfixed` → rejeitado; `config` sem `--misconfig-scanners dockerfile` → rejeitado; `--severity MEDIUM,HIGH,CRITICAL` → rejeitado; nenhum passo com `--exit-code 1` → rejeitado; montagem `-v "$GITHUB_WORKSPACE:/src"` sem `:ro` → rejeitada.
33. Exceções: `# exception: false positive on test fixture; https://github.com/o/r/security/code-scanning/1; review 2027-01-31` seguida de `CVE-2026-0001 exp:2027-01-31` → aceito; a mesma entrada sem a linha de exceção → rejeitado; sem `exp:` → rejeitado; `exp:` com data diferente da revisão → rejeitado; exceção sem URL → rejeitado; exceção com motivo vazio → rejeitado; linha `# zizmor: ignore[template-injection]` sem exceção acima → rejeitado; com exceção acima → aceito; `GHSA-abcd-efgh-ijkl` numa lista sem exceção acima → rejeitado; `continue-on-error: true` sem exceção → rejeitado. Mesma action com SHAs diferentes em dois textos de workflow → rejeitado (regra 21); com o mesmo SHA e comentários `# v7.0.1` × `# v7.0.2` → rejeitado.

Casos já existentes que devem continuar passando sem mudança: todo `tests/infra/test_supply_chain_pins.py` (agora parametrizado também com `security.yml`), `tests/infra/test_compose.py`, `tests/infra/test_jobs_image.py`, `tests/infra/test_crontab.py`, `tests/infra/test_tailscale_serve.py`, `tests/test_lint_config.py`.

## 9. Riscos e perguntas em aberto

### Achados prováveis (zizmor rodado "de cabeça" sobre o `ci.yml` e o `security.yml`-alvo, persona padrão)

- `ci.yml`: `unpinned-uses` (todas por SHA), `artipacked` (`persist-credentials: false` nos dois checkouts), `excessive-permissions` (topo e jobs com `contents: read`), `dangerous-triggers` (só `pull_request` e `push`), `template-injection` (nenhum `${{` em `run:`; `'{{.Ports}}'` é template do Docker, não expressão do Actions), `unpinned-images` (serviço `postgres` por digest), `github-env`, `insecure-commands`: **nada esperado**. `cache-poisoning`: o `setup-uv` com `enable-cache: true` só é apontado em workflow que publica artefato (release, tag, publicação); o `ci.yml` não publica, então **nada esperado hoje**. Atenção para o PR 37 se a publicação no GHCR entrar no mesmo workflow.
- Auditorias online (`impostor-commit`, `ref-version-mismatch`, `known-vulnerable-actions`): devem passar se o S1 resolveu os SHAs certo. Se `ref-version-mismatch` apontar, o comentário `# vX.Y.Z` não bate com o SHA: **corrigir** o comentário ou o SHA neste PR.
- Persona `pedantic`/`auditor` (não usada no CI) apontaria `undocumented-permissions`, `anonymous-definition`, `concurrency-limits`: fora do gate.
- `security.yml`: riscos de achado próprio são `template-injection` (por isso a regra do caso 10), `unsound-condition` (`if:` em bloco, caso 11) e `excessive-permissions` (só se alguém pôr `security-events: write` no topo; o caso 4 trava).
- Trivy `config` no `infra/jobs/Dockerfile`: `apt-get install` com `--no-install-recommends`, `apt-get update` combinado com install, `USER app`, nada de `ADD`, `:latest` nem `curl | sh`: **nada HIGH/CRITICAL esperado**. A falta de `HEALTHCHECK` é severidade baixa e fica fora do filtro.
- Trivy `fs` segredos: o Grep de 2026-11-08 não achou padrões de token. A URL `postgresql+psycopg://postgres:postgres@localhost` do `ci.yml` é credencial efêmera de CI; se alguma regra do Trivy a apontar, é falso positivo e vira exceção (passo 10, com o "sim" do usuário).
- Trivy `fs` vulnerabilidades e `dependency-review`: dependem do `uv.lock` e do banco do dia; não dá para prever. Tratamento no passo 10 (PR próprio de `fix(deps)`). Observação: o `dependency-review` só olha o que **muda** no PR, então num PR que não mexe em dependência ele passa mesmo com vulnerabilidade antiga; quem acusa o estoque é o `trivy-fs`.
- Regra geral: achado verdadeiro em workflow se corrige; vulnerabilidade de dependência se corrige em PR próprio; exceção só para falso positivo ou risco aceito, com motivo, link, data de revisão e aprovação do usuário.

### Riscos

- **Imagem do Trivy fora do Dependabot**: o `TRIVY_IMAGE` mora num `env:` do workflow, que nem o ecossistema `github-actions` nem o `docker` do S2 leem. Ele envelhece até alguém atualizar à mão com o passo 6. O banco de vulnerabilidades é baixado a cada execução, então a cobertura de CVEs fica atual; o que envelhece é o binário (parsers, checagens embutidas). Mitigação: anotar no S2 ou no S5 uma revisão trimestral; alternativa em Q1.
- **`uv.lock` fora do dependency graph** (ADR 0006, item 10): se o SBOM não cobrir, o `dependency-review` só vê o `pyproject.toml` e não pega transitivas. O `trivy-fs` lê o `uv.lock` direto e cobre o estoque nesse meio tempo. Q8.
- **Fork e Dependabot**: em PR de fork o upload de SARIF é pulado (os achados aparecem só no log do passo que falha). Em PR do Dependabot (S2), o token respeita o `permissions` declarado, mas convém conferir no primeiro PR dele que o upload funciona.
- **Checks novos do code scanning**: o upload de SARIF cria checks extras por ferramenta ("Code scanning results / ..."). Não são os jobs; o S5 deve marcar como required os quatro jobs, não esses.
- **Rede e limites**: o `trivy-fs` baixa o banco a cada execução (`mirror.gcr.io` por padrão). Falha de download deixa o job vermelho sem achado; o log diz o motivo. Se virar recorrente, Q9.
- **zizmor no grupo `dev`**: entra também no `uv sync --locked` do `lint-and-test` (alguns MB a mais). É o custo de ter versão travada por hash e o mesmo comando local e no CI.
- **zizmor e `.venv` local**: rodar `uv run zizmor .` na máquina do dev com `.venv` na raiz pode fazê-lo descer no ambiente procurando `action.yml`; se aparecer achado vindo de `.venv`, rodar `uv run zizmor .github/` localmente. No CI não há `.venv` no checkout antes do `uv sync`, e o `uv sync` cria o `.venv` na raiz: se o zizmor do CI apontar algo em `.venv`, trocar o alvo para `.github/` e registrar.
- **Flags do Trivy e do zizmor** mudam entre versões: a forma-alvo é ilustrativa e o passo 5/6.6 confere no `--help` da versão fixada.
- **Incidente de março de 2026**: a defesa é não usar `trivy-action`/`setup-trivy` (caso 15), fixar a imagem por digest de índice, conferir o digest em dois registries e, se possível, a assinatura. Digest fixado num artefato publicado durante uma janela de comprometimento continuaria malicioso: por isso o passo 6.1 lê os avisos antes de escolher a versão.

### Perguntas (cada uma com recomendação; o usuário aceita as recomendações)

- **Q1. Trivy por action ou por imagem.** Recomendação: **imagem `ghcr.io/aquasecurity/trivy:<X.Y.Z>@sha256:<digest>` via `docker run`**, sem `aquasecurity/trivy-action`. Motivo: o `trivy-action` é composite e chama o `setup-trivy`, que baixa o binário em tempo de execução; pinar o SHA da action não fixa o binário nem as actions internas, e foi exatamente o repositório cujas tags foram redirecionadas. A imagem por digest é um artefato só, endereçado por conteúdo, conferível em dois registries e por assinatura. Alternativa (rejeitada por ora): `trivy-action` por SHA conferido + `version:` explícita. Alternativa para o Dependabot atualizar o digest: um `Dockerfile` mínimo só com `FROM` do Trivy num diretório listado no S2; fica para depois, se a atualização manual incomodar.
- **Q2. zizmor por action ou por dependência de dev.** Recomendação: **dependência de dev no `uv.lock`** (`uv add --dev zizmor`), rodada por `uv run`. Motivo: versão exata com hash, o mesmo comando local e no CI, atualizada pelo ecossistema `uv` do S2. Alternativa: `zizmorcore/zizmor-action` por SHA + `version:` explícita (a action baixa a imagem do zizmor por tag, não por digest) com `advanced-security: true` fazendo o upload.
- **Q3. Trivy em um job ou dois.** Recomendação: **dois** (`trivy-config` e `trivy-fs`), para um achado num não esconder o outro (passos depois de um passo que falha não rodam) e para o S5 poder exigir cada um.
- **Q4. Escopo de dependências de dev.** Recomendação: **incluir dev** (`fail-on-scopes: runtime, development` no `dependency-review`; `--include-dev-deps` no Trivy, se a versão fixada o suportar para `uv`), porque `pytest`, `ruff`, `pyyaml` e `zizmor` rodam no CI. Se o escopo gerar ruído, rebaixar por exceção versionada.
- **Q5. Gate do zizmor.** Recomendação: **qualquer achado da persona padrão falha** (comportamento padrão da ferramenta), sem `--min-severity`: hoje o esperado é zero e os workflows são pequenos. O critério de saída do ADR (HIGH/CRITICAL) continua sendo o que o S5 mede.
- **Q6. Checagens do `trivy config`.** Recomendação: **`--skip-check-update`** (checagens embutidas no binário fixado), para não executar um bundle de regras baixado sem pin. Contra: as regras envelhecem junto com a imagem (mesmo risco do primeiro item de "Riscos").
- **Q7. Gatilho `schedule`.** Recomendação: **não agora**. Os alertas do Dependabot (S2/S5) já avisam CVE nova em código parado, e o ADR pede só `pull_request` e push na `main`. Rever junto do OSV-Scanner (futuro).
- **Q8. Se o SBOM não cobrir o `uv.lock`.** Recomendação: mergear o S3 assim mesmo (o `trivy-fs` cobre o estoque), registrar no PR e criar o item **S3b** "dependency submission do `uv.lock`" (precisa de `contents: write` num job próprio; planejar à parte). O ADR 0006, item 10, já prevê isso, sem ADR novo.
- **Q9. Registry da imagem do Trivy.** Recomendação: **`ghcr.io/aquasecurity/trivy`** (sem limite anônimo do Docker Hub), com conferência cruzada do digest no `aquasec/trivy` (passo 6.4). Se o download do banco falhar com frequência, acrescentar `--db-repository` com espelho alternativo num PR próprio.
- **Q10. Quem aprova exceções.** Recomendação: **só o usuário**, no PR, e o implementador nunca cria `.trivyignore`, `# zizmor: ignore[...]` ou `allow-ghsas` sem esse "sim"; data de revisão de no máximo 90 dias.
- **Q11. Regra em `.claude/rules/infra.md`.** Uma linha "workflows: `permissions: {}` no topo, mínimo por job, sem `${{ }}` em `run:`, sem `paths:` em workflow de check" ajudaria os planos 37 e 39. Recomendação: o usuário acrescenta no mesmo PR (o implementer não edita `.claude/`).

## 10. Decisões que exigem ADR

Nenhuma nova. O ADR 0006 (Aceito, 2026-11-08) cobre o workflow, as três checagens, as permissões, o upload pulado em fork, o modo só-avisa, a política de exceções e o critério do SBOM. Q1 está dentro do item 3 ("por action pinada por SHA conferido ou por imagem fixada por digest"); Q2 e Q3 são detalhe de implementação do item 3; Q8 está previsto no item 10. Ficariam fora do 0006 e exigiriam ADR próprio: Scorecard (`id-token: write`), `harden-runner`, agente de IA no CI com segredo, e Trivy da imagem com attestation (PR 37).
