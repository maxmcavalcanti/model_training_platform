# 37 — Build, varredura Trivy, attestation e publicação das imagens no GHCR a cada merge na `main`

> Executa: agente. Depende de: 34 e 36 mergeados (imagem sem supercronic, serviço `scheduler` removido), S5 concluído (checks required, ADR 0006, item 8; `docs/plans/S5-settings-seguranca-manual.md`) e **ADR "Pipeline de entrega" mergeado** (seção 10). Branch sugerida: `ci/publish-images`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.
> Revisado em 2026-11-08 contra a `main` em `05c32c9` (depois de #46 pin por SHA, #48 Dependabot, #49 `security.yml`, #51 hardening, #52 regras de infra), com as correções da revisão independente (aceitas pelo usuário). Substitui o rascunho anterior, que fixava actions "por major" e publicava a tag mutável `main`. Alinhamento entre planos (mesmo dia): o `prefect-worker` usa a mesma referência por digest do `jobs` (plano 34, D5), explícito em todos os pontos que tocam a imagem `platform-jobs`. Revisão final (mesmo dia, aceita pelo usuário): nenhum comando lê o `infra/.env.example` (o `grep` de contagem saiu); a ausência das variáveis é provada pelo `config -q` falhando antes do append, e a presença pelos testes de `tests/infra`.

## 1. Objetivo

Criar `.github/workflows/deploy.yml` com um job `publish` que, a cada push na `main`, constrói as imagens próprias, varre cada uma com o Trivy (gate de publicação), publica no GHCR com a tag do commit, gera attestation de proveniência com `actions/attest` e expõe os digests como saída do job.
Fazer o compose de produção referenciar as imagens próprias **por digest**, sem `build:` (`jobs` e `prefect-worker` em `platform-jobs@${JOBS_IMAGE_DIGEST}`, `mlflow` em `platform-mlflow@${MLFLOW_IMAGE_DIGEST}`), para a VPS só fazer `pull` (primeira metade de "merge na `main` chega à VPS"; o SSH é o PR 39).

## 2. Fora do escopo

- SSH na VPS, `deploy.sh`, Tailscale no CI, environment `production` (PR 39; segredos no item 38). O `harden-runner` no `publish` também entra no PR 39, junto da decisão do ADR.
- Tornar os pacotes do GHCR públicos e trocar o fluxo da VPS para `pull` (item 38, usuário).
- Varredura `trivy image` em PR (só no merge; D6). Mudar os jobs de `security.yml` (os nomes são fixados por `tests/infra/test_security_workflow.py`, `EXPECTED_JOBS`).
- Tag mutável `main` ou `latest` nas imagens próprias.
- Multi-arquitetura (a VPS é `x86_64`; só `linux/amd64`).
- Editar ADR, `.claude/` ou `docs/plans/00-indice.md`.
- Qualquer item da Fase 4.

## 3. Fase do roadmap

Fase 3 de `docs/plataforma-ml.md` — "Pipelines do GitHub Actions nos dois repositórios" (lado `platform`, parte build → GHCR). Do doc, seção "CI/CD e operação": "No merge na `main`: Build da imagem → GHCR → SSH na VPS: `alembic upgrade head`, `docker compose pull && up -d`, registra deployments do Prefect". O doc lista `.github/workflows/` como `ci.yml, deploy.yml`.

## 4. Arquivos a criar ou alterar

| Caminho | Quem | Motivo |
| --- | --- | --- |
| `tests/infra/test_deploy_workflow.py` (novo) | test-writer | Forma do `deploy.yml` (casos 1 a 16), com exemplos negativos, no estilo de `tests/infra/test_security_workflow.py` |
| `tests/infra/test_compose.py` | test-writer | Imagens próprias por digest, sem `build:` em produção; `build:` no override (casos 17 a 21); ajustar os testes que hoje leem `build` do `jobs` e do `prefect-worker` no compose de produção |
| `tests/infra/test_supply_chain_pins.py` | test-writer | `OWN_IMAGE_PREFIXES` passa a aceitar a forma nova, e só com `@${..._IMAGE_DIGEST...}` (caso 22) |
| `.github/workflows/deploy.yml` (novo) | implementer | Workflow `deploy`, job `publish` |
| `infra/docker-compose.yml` | implementer | `image:` por digest nos serviços de imagem própria (`jobs`, `prefect-worker`, `mlflow`); remover `build:` |
| `infra/docker-compose.build.yml` (novo) | implementer | Override com `build:` e `image: platform-<nome>:local`, para CI e uso local |
| `.github/workflows/ci.yml` | implementer | `compose-smoke` sem `$COMPOSE` não citado (passo 0); `config -q` com o override; passo `actionlint` |
| `infra/.env.example` | implementer, **sem ler o arquivo** (passo 8) | `GHCR_OWNER`, `JOBS_IMAGE_DIGEST`, `MLFLOW_IMAGE_DIGEST` com valores fictícios |
| `AGENTS.md`, seção "Comandos" | implementer | Build local com o override; trocar o comando de build na VPS pela sequência interina de `pull` (passo 11); registrar `actionlint` |
| `.github/dependabot.yml` | implementer, **só se** `infra/mlflow` não estiver em `directories` do ecossistema `docker` | Manter o `FROM` do MLflow atualizado (ADR 0006, item 2) |

### Contexto que o implementador precisa (estado da `main` em `05c32c9`)

- `.github/workflows/ci.yml`: topo `permissions: contents: read`; jobs `lint-and-test` e `compose-smoke`; `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1` com `persist-credentials: false`; `astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3`. O `compose-smoke` tem `env: COMPOSE: docker compose -f infra/docker-compose.yml --env-file infra/.env.example` e passos como `run: $COMPOSE up -d --wait postgres`, `$COMPOSE build jobs`, `$COMPOSE run --rm jobs ...` (a expansão sem aspas é proposital, para separar as palavras, e é o que o shellcheck do actionlint aponta como SC2086). `lint-and-test` roda `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q` e `shellcheck infra/scripts/*.sh`. O teste `test_ci_workflow_has_uses_lines_to_check` exige **exatamente 3** linhas `uses:` no `ci.yml`: o `actionlint` entra por `run:` com `docker run`, não por `uses:`.
- `.github/workflows/security.yml`: `permissions: {}` no topo; `env.TRIVY_IMAGE: ghcr.io/aquasecurity/trivy:0.76.1@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c`; Trivy roda por `docker run --rm --user "$(id -u):$(id -g)" -v "$GITHUB_WORKSPACE:/src:ro" ... -v "$RUNNER_TEMP/trivy-cache:/cache" -w /src "$TRIVY_IMAGE" fs --cache-dir /cache ...`, nunca por `aquasecurity/trivy-action` nem `setup-trivy`. Com `-w /src`, o Trivy lê o `.trivyignore` da raiz do checkout, se existir.
- Regras de workflow (`.claude/rules/infra.md`, ADR 0006 itens 4 a 7): "toda action por SHA completo de commit com `# vX.Y.Z` na mesma linha, nunca por tag; `permissions` no topo (`{}` ou `contents: read`) e o mínimo declarado em cada job; `actions/checkout` com `persist-credentials: false`; nenhum gatilho `pull_request_target` nem `workflow_run`; nenhum `${{ }}` dentro de `run:` (o valor entra por `env:`); `if:` em uma linha só; [...] o Trivy roda pela imagem fixada por digest (`TRIVY_IMAGE` do `security.yml`) [...]. Antes de commitar mudança em workflow, rode `uv run zizmor .github/workflows/` e corrija os achados." ADR 0006, item 7: "Nenhum segredo no nível do repositório." Este job não usa `secrets.`: o login no GHCR usa o token do job (`github.token`).
- ADR 0006, item 9 (política de exceções): rebaixar um check só por exceção versionada "com motivo, link do alerta e data de revisão". Formato testado em `tests/infra/test_security_workflow.py` (`EXCEPTION_LINE`): linha `# exception: <motivo>; <url>; review AAAA-MM-DD` imediatamente acima da linha que rebaixa.
- Testes que já valem para **todo** workflow (`tests/infra/test_supply_chain_pins.py` e `test_security_workflow.py`, parametrizados por `workflow_files()`): pin por SHA com `# vX.Y.Z`; `permissions` no topo e nunca `write-all`/`read-all`; checkout com `persist-credentials: false`; sem `pull_request_target`/`workflow_run`; imagens de `services`/`container` por digest; sem `trivy-action`/`setup-trivy`; `# zizmor: ignore[...]` só com linha de exceção acima; a mesma action com o mesmo SHA e comentário em todos os workflows (`action_consistency_problems`).
- `infra/jobs/Dockerfile`: base `ghcr.io/astral-sh/uv:0.9.30-python3.12-bookworm-slim@sha256:e5b6...`, `USER app` (uid 10001). Depois do PR 36 já não tem supercronic nem `infra/cron/`.
- `infra/docker-compose.yml` depois do PR 34: `jobs` e `prefect-worker` têm o mesmo `build: {context: .., dockerfile: infra/jobs/Dockerfile}` (plano 34, D5: "No PR 37: `jobs` e `prefect-worker` passam a usar a mesma referência por digest [...] para que o código do worker e o do `jobs` (que registra os deployments) sejam sempre idênticos").
- `.dockerignore` (raiz) já exclui `**/.env`, `**/.env.*`, `.git`, `.claude`, `docs`, `tests`, `**/*.pem`, `**/*.key`. A imagem é pública: nenhum segredo em camada. O build do MLflow usa contexto `infra/mlflow`: confira se há `.dockerignore` lá ou se o contexto só tem o `Dockerfile` e os `requirements.*`.
- `tests/infra/test_supply_chain_pins.py`, linha 30: `OWN_IMAGE_PREFIXES = ("ghcr.io/${GHCR_OWNER}/platform-",)` com o comentário "Plan 37 extends this list".
- `.claude/rules/infra.md`: "`.env.example` com Docker: o agente pode rodar `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q` [...]; o agente continua sem abrir, copiar ou imprimir o arquivo, com qualquer ferramenta." Nunca `config` sem `-q`. Nenhum `grep`, `cat` ou outra leitura do `infra/.env.example`: a escrita é só por append (passo 8) e a conferência é pelo `config -q` e pelos testes.
- `actions/attest` (conferido pela revisão independente; reconfirmar na ref fixada): o README de `actions/attest-build-provenance` recomenda usar `actions/attest`. Inputs usados aqui: `subject-name`, `subject-digest`, `push-to-registry`, `create-storage-record`. Permissões: `id-token: write` e `attestations: write`; `packages: write` para gravar a attestation no registry; `artifact-metadata: write` só se `create-storage-record` ficar ligado (padrão).

### Suposições sobre o estado depois dos PRs 29 a 36 (conferir no passo 1; se alguma falhar, pare e avise)

- S-a. Imagens próprias = uma por `infra/**/Dockerfile`: `infra/jobs/Dockerfile` (contexto `.`) → `platform-jobs`, usada pelos serviços `jobs` e `prefect-worker` (PR 34: mesmo `build` do `jobs`; aqui, mesma referência `platform-jobs@${JOBS_IMAGE_DIGEST}`); `infra/mlflow/Dockerfile` (contexto `infra/mlflow`, PR 29) → `platform-mlflow`, usada pelo serviço `mlflow`.
- S-b. O `prefect-server` usa a imagem oficial fixada por `tag@sha256:` (PR 30, ADR 0006 item 5), não é imagem própria.
- S-c. Não existe mais serviço `scheduler` nem supercronic (PR 36). O `scheduler` nunca teve imagem própria: usava o mesmo Dockerfile do `jobs`.
- S-d. Se houver outro `infra/**/Dockerfile` além desses dois, ele entra como mais uma imagem `platform-<nome>` com o mesmo padrão (mais uma saída de digest, que o PR 39 também passa ao `deploy.sh`); registre no PR.

## 5. Passos

0. (implementer, leitura, antes de tudo) Resolver a imagem do `actionlint` como no plano S1, passo 6 (`docker buildx imagetools inspect rhysd/actionlint:<versão>` → digest do índice; validar `linux/amd64`) e rodá-lo na `main` atual: `docker run --rm -v "$PWD:/repo:ro" --workdir /repo rhysd/actionlint:<versão>@sha256:<digest> -color`. Registrar todos os achados no corpo do PR. Achado esperado: shellcheck SC2086 nos `run: $COMPOSE ...` do `compose-smoke`. Tratamento (recomendado, sem exceção): trocar o `env.COMPOSE` do job por `env.COMPOSE_FILE: infra/docker-compose.yml:infra/docker-compose.build.yml` (variável nativa do Docker Compose; separador `:` no Linux) e escrever cada passo como `docker compose --env-file infra/.env.example <subcomando> ...`, sem variável não citada. Só se isso não funcionar, a alternativa é `-ignore 'SC2086'` restrito no comando do actionlint, com linha `# exception: ...; <url>; review <data>` acima (ADR 0006, item 9). Outros achados: corrigir no código; se algum exigir exceção, mesmo formato.
1. (implementer, leitura) Conferir as suposições S-a a S-d: `git ls-files 'infra/**/Dockerfile'`, `grep -n "scheduler\|supercronic" infra/docker-compose.yml infra/jobs/Dockerfile` (vazio) e os serviços que hoje têm `build:` em `infra/docker-compose.yml` (esperado: `jobs`, `prefect-worker`, `mlflow`). Registrar no PR.
2. (implementer, leitura) Resolver e validar o SHA de cada action nova, como no plano S1, passo 4 (`docs/plans/S1-pin-sha-e-permissoes-ci.md`): `gh api repos/<owner>/<repo>/git/ref/tags/<tag> --jq '.object.type + " " + .object.sha'` (se `tag`, desreferenciar com `gh api repos/<owner>/<repo>/git/tags/<sha> --jq '.object.sha'`) e `gh api "repos/<owner>/<repo>/compare/<tag>...<sha>" --jq .status` → `identical`. Ler os inputs e permissões **na versão fixada**: `gh api "repos/<owner>/<repo>/contents/action.yml?ref=<sha>" --jq .content | base64 -d` e o README na mesma ref.
   - `actions/checkout`: o mesmo SHA do `ci.yml` (`3d3c42e5...` `# v7.0.1`), exigido pelo teste de consistência.
   - `actions/attest` (última release estável): confirmar `subject-name`, `subject-digest`, `push-to-registry` e `create-storage-record`. Se a versão fixada não tiver `create-storage-record`, acrescentar `artifact-metadata: write` às permissões (D10) e ajustar os casos 6 e 16.
   - Nenhuma action de terceiros para Docker (D2).
3. (test-writer) Escrever os casos da seção 8 em `tests/infra/test_deploy_workflow.py`, `tests/infra/test_compose.py` e `tests/infra/test_supply_chain_pins.py`, cada função de checagem com exemplos aceitos e rejeitados embutidos (padrão de `test_security_workflow.py`). Reaproveitar por import `REPO_ROOT`, `WORKFLOWS_DIR`, `SHA40`, `DIGEST`, `USES_LINE`, `load_yaml`, `image_reference_problems` de `tests.infra.test_supply_chain_pins` e `normalized`, `steps_of`, `jobs_of`, `run_expression_problems`, `multiline_if_problems` de `tests.infra.test_security_workflow`. Confirmar a falha (`deploy.yml` inexistente; compose ainda com `build:`). Commit `test: expect digest-pinned ghcr images and publish workflow`.
4. (implementer) Se o passo 0 adotou `COMPOSE_FILE`, reescrever o `compose-smoke` assim (os testes existentes de `ci.yml` continuam valendo).
5. (implementer) `infra/docker-compose.yml`:
   - `jobs` **e `prefect-worker`** (plano 34, D5): os dois com exatamente `image: ghcr.io/${GHCR_OWNER:?GHCR_OWNER is required}/platform-jobs@${JOBS_IMAGE_DIGEST:?JOBS_IMAGE_DIGEST is required}`; remover `build:` dos dois. Um único digest para os dois garante que o worker roda o mesmo código que o `jobs` registra.
   - `mlflow`: `image: ghcr.io/${GHCR_OWNER:?GHCR_OWNER is required}/platform-mlflow@${MLFLOW_IMAGE_DIGEST:?MLFLOW_IMAGE_DIGEST is required}`; remover `build:`.
   - Nenhuma outra mudança (portas, `mem_limit`, `restart`, `environment` intactos).
6. (implementer) `infra/docker-compose.build.yml` (override, nunca usado na VPS): para `jobs` e `prefect-worker`, `build: {context: .., dockerfile: infra/jobs/Dockerfile}` e `image: platform-jobs:local`; para `mlflow`, `build: {context: ./mlflow}` e `image: platform-mlflow:local`. O `image:` do override substitui o do base; a interpolação do base ainda exige as variáveis, daí os valores fictícios do passo 8. Comentário no topo (em inglês): local and CI builds only; production pulls by digest.
7. (implementer) Provar, **sem ler o `infra/.env.example`**, que as três variáveis ainda não estão declaradas: `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q; echo "exit=$?"` → código diferente de 0 e mensagem `required variable <NOME> is missing a value: <NOME> is required` com `<NOME>` em `GHCR_OWNER`, `JOBS_IMAGE_DIGEST` ou `MLFLOW_IMAGE_DIGEST` (o compose cita a primeira que faltar). Se der `exit=0` (as variáveis já existem) ou falhar citando outra variável, pare e pergunte ao usuário, sem abrir o arquivo.
8. (implementer) `infra/.env.example`: o agente **não lê** o arquivo (deny do `Read` e `AGENTS.md`). Acrescentar só por append: `printf '%s\n' '' '# Own images published by .github/workflows/deploy.yml (plan 37); example values, not real' 'GHCR_OWNER=example-owner' 'JOBS_IMAGE_DIGEST=sha256:0000000000000000000000000000000000000000000000000000000000000000' 'MLFLOW_IMAGE_DIGEST=sha256:0000000000000000000000000000000000000000000000000000000000000000' >> infra/.env.example`. Depois, conferir só por comandos que não imprimem o arquivo: o `config -q` do passo 7 agora sai com `exit=0`, e `uv run pytest tests/infra` passa (inclusive `test_every_required_compose_variable_is_declared_in_env_example`). (Q1: o usuário pode fazer o append à mão.)
9. (implementer) `.github/workflows/ci.yml`:
   - `compose-smoke`: usar o override (via `COMPOSE_FILE` do passo 0 ou `-f ... -f ...` explícito).
   - `lint-and-test`: além do `config -q` atual, `docker compose -f infra/docker-compose.yml -f infra/docker-compose.build.yml --env-file infra/.env.example config -q`.
   - Novo passo em `lint-and-test`: `docker run --rm -v "$GITHUB_WORKSPACE:/repo:ro" --workdir /repo rhysd/actionlint:<versão>@sha256:<digest> -color`.
10. (implementer) `.github/workflows/deploy.yml`, forma-alvo (ilustrativa; SHAs dos passos 0 e 2; conferir os inputs na versão fixada):

    ```yaml
    name: deploy

    on:
      push:
        branches: [main]

    permissions: {}

    concurrency:
      group: deploy-production
      cancel-in-progress: false

    env:
      # Same pinned image as security.yml (ADR 0006); tests keep both identical
      TRIVY_IMAGE: ghcr.io/aquasecurity/trivy:0.76.1@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c

    jobs:
      publish:
        if: github.ref == 'refs/heads/main'
        runs-on: ubuntu-latest
        permissions:
          contents: read
          packages: write
          id-token: write
          attestations: write
        outputs:
          jobs-digest: ${{ steps.push-jobs.outputs.digest }}
          mlflow-digest: ${{ steps.push-mlflow.outputs.digest }}
        steps:
          - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
            with:
              persist-credentials: false
          - name: Compute image names
            id: names
            run: |
              owner="${GITHUB_REPOSITORY_OWNER,,}"
              echo "jobs=ghcr.io/$owner/platform-jobs" >> "$GITHUB_OUTPUT"
              echo "mlflow=ghcr.io/$owner/platform-mlflow" >> "$GITHUB_OUTPUT"
          - name: Build platform-jobs
            env:
              IMAGE: ${{ steps.names.outputs.jobs }}
            run: |
              docker build -f infra/jobs/Dockerfile \
                --label "org.opencontainers.image.source=$GITHUB_SERVER_URL/$GITHUB_REPOSITORY" \
                --label "org.opencontainers.image.revision=$GITHUB_SHA" \
                -t "$IMAGE:$GITHUB_SHA" .
          - name: Scan platform-jobs with Trivy
            env:
              IMAGE: ${{ steps.names.outputs.jobs }}
            run: |
              mkdir -p "$RUNNER_TEMP/scan" "$RUNNER_TEMP/trivy-cache"
              docker save -o "$RUNNER_TEMP/scan/jobs.tar" "$IMAGE:$GITHUB_SHA"
              docker run --rm --user "$(id -u):$(id -g)" \
                -v "$GITHUB_WORKSPACE:/src:ro" -v "$RUNNER_TEMP/scan:/in:ro" \
                -v "$RUNNER_TEMP/trivy-cache:/cache" -w /src \
                "$TRIVY_IMAGE" image --cache-dir /cache --input /in/jobs.tar \
                --scanners vuln,secret --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1
          # ... mesmos dois passos para platform-mlflow (docker build -f infra/mlflow/Dockerfile ... infra/mlflow)
          - name: Log in to GHCR
            env:
              GHCR_TOKEN: ${{ github.token }}
            run: printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u "$GITHUB_ACTOR" --password-stdin
          - name: Push platform-jobs
            id: push-jobs
            env:
              IMAGE: ${{ steps.names.outputs.jobs }}
            run: |
              docker push "$IMAGE:$GITHUB_SHA"
              ref="$(docker image inspect --format '{{index .RepoDigests 0}}' "$IMAGE:$GITHUB_SHA")"
              digest="${ref##*@}"
              [[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]
              echo "digest=$digest" >> "$GITHUB_OUTPUT"
              echo "platform-jobs $digest"
              echo "platform-jobs $digest" >> "$GITHUB_STEP_SUMMARY"
          - uses: actions/attest@<sha> # vX.Y.Z
            with:
              subject-name: ${{ steps.names.outputs.jobs }}
              subject-digest: ${{ steps.push-jobs.outputs.digest }}
              push-to-registry: true
              create-storage-record: false
          # ... push e attestation de platform-mlflow
          - if: always()
            run: docker logout ghcr.io
    ```

    Pontos obrigatórios (os testes travam): topo `permissions: {}`; só gatilho `push` em `[main]`; job `publish` com `if:` de uma linha para `refs/heads/main` e exatamente as permissões acima; nenhum `secrets.`; nenhum `${{` em `run:`; login só por `--password-stdin`; Trivy só por `"$TRIVY_IMAGE"` com `image --input` sobre o `docker save`, checkout montado `:ro` e `-w /src` (para o `.trivyignore`), sem montar `/var/run/docker.sock`; nenhuma tag `latest`/`main`; o digest de cada imagem é impresso no log **e** no summary. O `[[ ... =~ ... ]]` depende do `bash -e` padrão dos passos `run:` do GitHub no `ubuntu-latest`.
11. (implementer) `AGENTS.md`, "Comandos":
    - "Imagem dos jobs": manter `docker build -f infra/jobs/Dockerfile -t platform-jobs .` e acrescentar o build local pelo override: `docker compose -f infra/docker-compose.yml -f infra/docker-compose.build.yml --env-file infra/.env.example build jobs prefect-worker mlflow`.
    - Trocar a linha "Na VPS (até o PR 37 a imagem é construída lá, ADR 0004): `docker compose -f infra/docker-compose.yml build jobs prefect-worker` e `... run --rm jobs <comando>`" por: "Na VPS, depois do PR 37 e até o primeiro deploy automático do PR 39 (último fluxo manual, ADR 0004; passo a passo em `docs/plans/38-segredos-ci-cd-manual.md`): `docker compose -f infra/docker-compose.yml --profile jobs pull`, `docker compose -f infra/docker-compose.yml run --rm jobs alembic upgrade head`, `docker compose -f infra/docker-compose.yml up -d --remove-orphans --wait`. Nunca `build` na VPS."
    - Trocar as linhas de build na VPS do worker (PR 34) e do MLflow (PR 29) pela mesma regra: na VPS, só `pull`.
    - Acrescentar "Validar workflows: `docker run --rm -v "$PWD:/repo:ro" --workdir /repo rhysd/actionlint:<versão>@sha256:<digest> -color`".
    - Não mexer na linha do Dependabot (o PR 39 trata) nem nas do agendador (o 36 já tratou).
12. (implementer) `.github/dependabot.yml`: se `/infra/mlflow` não estiver em `directories` do ecossistema `docker`, acrescentar (o PR 29 já deveria ter acrescentado, com o `ignore` de minor e major do MLflow, que fica intacto). Validar com `uvx --from check-jsonschema==0.39.0 check-jsonschema --builtin-schema vendor.dependabot .github/dependabot.yml`.
13. (implementer) `uv run zizmor .github/workflows/` e corrigir achados (nunca `# zizmor: ignore` sem linha de exceção, ADR 0006 item 9). Rodar os critérios de pronto.
14. Corpo do PR (inglês): achados do actionlint na `main` (passo 0) e o tratamento; a saída do `config -q` do passo 7 (a mensagem de variável ausente, sem valores); tabela `action | tag | sha`; tabela `imagem | tag | digest` do actionlint; as suposições S-a a S-d conferidas; e o aviso ao usuário:
    - depois do merge, os pacotes nascem privados e o item 38 os torna públicos; **tornar um pacote do GHCR público é irreversível** (não dá para voltar a privado; só apagar o pacote);
    - até o item 38, a VPS continua no fluxo manual do ADR 0004, mas **não pode mais fazer `build`** com o compose de produção (sem `build:`); o item 38 troca para `pull`.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/` | Todos passam (inclusive `test_every_required_compose_variable_is_declared_in_env_example`, que prova as três variáveis declaradas sem ninguém ler o arquivo) |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem achados |
| `uv run zizmor .github/workflows/` | Sem achados, código 0 |
| `docker run --rm -v "$PWD:/repo:ro" --workdir /repo rhysd/actionlint:<versão>@sha256:<digest> -color` | Sem saída, código 0 |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q` | Código 0 (antes do append do passo 8, falhava citando uma das três variáveis; registrado no PR) |
| `docker compose -f infra/docker-compose.yml -f infra/docker-compose.build.yml --env-file infra/.env.example config -q` | Código 0 |
| `docker compose -f infra/docker-compose.yml -f infra/docker-compose.build.yml --env-file infra/.env.example build jobs prefect-worker` | Termina sem erro |
| `grep -n "build:" infra/docker-compose.yml` | Nada |
| Para cada action nova: `gh api "repos/<owner>/<repo>/compare/<tag>...<sha>" --jq .status` | `identical` |
| `gh pr checks` | Verde (`ci`, `security`) |
| Depois do merge: `gh run list --workflow deploy.yml --branch main --limit 1 --json conclusion -q '.[0].conclusion'` | `success` |
| Depois do merge: `gh run view <id> --log \| grep -E "platform-(jobs\|mlflow) sha256:[0-9a-f]{64}"` | As duas linhas (também no summary) |
| Depois do merge: `gh attestation verify oci://ghcr.io/<dono>/platform-jobs@<digest> --repo <dono>/<repo>` | Verificação bem-sucedida (o pacote ainda privado só é visível ao dono autenticado) |
| Depois do merge: `docker buildx imagetools inspect ghcr.io/<dono>/platform-jobs@<digest>` (logado como dono enquanto privado) | Lista `linux/amd64` |
| Primeiro run do Dependabot depois do merge: aba Insights → Dependency graph → Dependabot, ecossistema `docker-compose` | Sem erro de parse em `infra/docker-compose.yml` (ver riscos) |

## 7. Testes necessários

`sim`: a forma do workflow (permissões, gatilho, gate do Trivy, ausência de segredo e de tag mutável) e a troca de `build:` por digest no compose são regras de segurança e de deploy verificáveis estaticamente; regressão nelas publicaria imagem sem varredura ou deixaria a VPS construir.

## 8. Casos de teste

`deploy.yml` (`tests/infra/test_deploy_workflow.py`; cada checagem também roda contra exemplos embutidos aceitos e rejeitados):

1. O arquivo existe, é um mapeamento não vazio e `name` é `deploy`.
2. Gatilho: só `push` com `branches: [main]`; sem `pull_request`, `workflow_dispatch`, `schedule`, `paths`. Rejeita `{push: {branches: [main, dev]}}` e a presença de `pull_request`.
3. Topo `permissions` é exatamente `{}`. Rejeita `{contents: read}` e ausência.
4. `concurrency.group` é `deploy-production` e `cancel-in-progress` é `false` (booleano). Rejeita `true` e ausência.
5. Job `publish` existe, com `if` de uma linha contendo `github.ref == 'refs/heads/main'`.
6. Permissões do `publish` são exatamente `{contents: read, packages: write, id-token: write, attestations: write}` (D10). Rejeita qualquer chave a mais (ex.: `security-events`, `actions`, `artifact-metadata`) ou a menos. Se o passo 2 obrigar `artifact-metadata: write`, o conjunto esperado passa a incluí-la e o caso 16 deixa de exigir `create-storage-record: false`.
7. O texto do workflow não contém `secrets.` (enquanto só existir o `publish`; o PR 39 muda este caso para "só no job `deploy`").
8. Nenhum `run:` contém `${{` e nenhum `if:` é multilinha (reuso das funções de `test_security_workflow.py`).
9. `env.TRIVY_IMAGE` do `deploy.yml` é idêntico ao do `security.yml` e passa em `image_reference_problems`. Rejeita digest diferente.
10. Para cada imagem própria, existe um `run` que chama `"$TRIVY_IMAGE" image` com `--input`, `--scanners vuln,secret`, `--severity HIGH,CRITICAL`, `--ignore-unfixed` e `--exit-code 1`, com o checkout montado `:/src:ro`. Rejeita a falta de qualquer flag, montagem gravável e `--exit-code 0` como única execução.
11. Nenhum `run` monta `/var/run/docker.sock` e nenhum `docker run` usa imagem literal além de `"$TRIVY_IMAGE"`.
12. Ordem dentro do `publish`: para cada imagem, a varredura vem antes do `docker push` da mesma imagem; o login vem depois de todas as varreduras. Rejeita push antes do scan.
13. Login: o único `docker login` do arquivo usa `--password-stdin` e o token entra por `env:` com valor `${{ github.token }}`. Rejeita `-p`/`--password` e valor vindo de `secrets.`.
14. Tags: todo `docker build -t`/`docker push` usa `:$GITHUB_SHA`; nenhuma ocorrência de `:latest` ou `:main` como tag de imagem. Rejeita `-t "$IMAGE:latest"`.
15. Saídas do job: `outputs` tem exatamente `jobs-digest` e `mlflow-digest` (um por imagem própria de S-a/S-d), cada uma vindo de `steps.<id>.outputs.digest`; o passo correspondente valida `sha256:[0-9a-f]{64}` antes de escrever em `GITHUB_OUTPUT` e imprime `platform-<nome> <digest>` no stdout e no `GITHUB_STEP_SUMMARY`.
16. Há um passo `actions/attest@<sha>` por imagem, com `push-to-registry: true`, `create-storage-record: false` (D10) e `subject-digest` vindo da saída do push da mesma imagem. Rejeita `actions/attest-build-provenance` e `push-to-registry` ausente.

Compose (`tests/infra/test_compose.py`):

17. Nenhum serviço de `infra/docker-compose.yml` tem `build:`.
18. `jobs` e `prefect-worker` têm `image` igual a `ghcr.io/${GHCR_OWNER:?GHCR_OWNER is required}/platform-jobs@${JOBS_IMAGE_DIGEST:?JOBS_IMAGE_DIGEST is required}`, e os dois valores são idênticos entre si; `mlflow` igual ao análogo com `platform-mlflow` e `MLFLOW_IMAGE_DIGEST`. Rejeita `:${IMAGE_TAG}`, `:latest`, digest sem `:?`, e `prefect-worker` com outra imagem ou outra variável de digest (ex.: `${WORKER_IMAGE_DIGEST}`).
19. `infra/docker-compose.build.yml` existe; os mesmos serviços têm `build:` (`jobs`/`prefect-worker`: `context: ..`, `dockerfile: infra/jobs/Dockerfile`; `mlflow`: `context: ./mlflow`) e `image: platform-<nome>:local` (`platform-jobs:local` para `jobs` e `prefect-worker`); nenhum outro serviço aparece no override; o override não declara `ports`, `environment` nem `volumes`.
20. Os testes de `build` existentes do `jobs` e do `prefect-worker` (`test_jobs_builds_from_repo_root_with_the_jobs_dockerfile`, `jobs_build_problems`, caso 2 do plano 34) passam a ler o serviço do override.
21. `infra/.env.example` declara `GHCR_OWNER`, `JOBS_IMAGE_DIGEST`, `MLFLOW_IMAGE_DIGEST` (coberto pelo caso geral `test_every_required_compose_variable_is_declared_in_env_example`, que deve continuar passando).

Supply chain (`tests/infra/test_supply_chain_pins.py`):

22. A exceção de imagem própria aceita só `ghcr.io/${GHCR_OWNER:?...}/platform-<nome>@${<NOME>_IMAGE_DIGEST:?...}`; imagem própria com tag (`...platform-jobs:${IMAGE_TAG}`) ou `latest` reprova. O teste existente `test_compose_check_allows_own_images_without_digest` é atualizado para a forma nova.

## 9. Riscos e perguntas em aberto

- **Não verificado nesta revisão** (o resto foi conferido pela revisão independente; reconfirmar na ref fixada no passo 2): a versão atual do `actionlint` e o conjunto exato de achados na `main` (passo 0 registra); o comportamento de `docker build` no `ubuntu-latest` atual (se o Docker do runner usar o image store do containerd, o push pode gerar um índice com attestation do BuildKit, e o digest de `RepoDigests` será o do índice, o que continua servindo para `pull` por digest; um critério de pronto confere `linux/amd64`); se `COMPOSE_FILE` com dois arquivos se comporta igual aos dois `-f` no `compose-smoke` (o próprio CI do PR confere).
- **Dependabot `docker-compose` e `image:` interpolada:** o ecossistema pode não conseguir interpretar `ghcr.io/${GHCR_OWNER:?...}/platform-jobs@${JOBS_IMAGE_DIGEST:?...}` e falhar o parse do arquivo inteiro (deixando de atualizar `postgres`, `busybox` e `prefecthq/prefect`). Checar no primeiro run do Dependabot depois do merge (último critério de pronto). Se falhar: registrar e propor, em PR próprio, `ignore` por `dependency-name` ou mover as imagens próprias para o override de produção.
- **`TRIVY_IMAGE` duplicado** em `security.yml` e `deploy.yml`: o Dependabot (`github-actions`) só atualiza `uses:`, não strings de `env:`. O caso 9 impede divergência; a atualização continua manual nos dois.
- **Imagem do MLflow com CVEs HIGH/CRITICAL corrigíveis** na base oficial pode bloquear toda publicação. Saída: exceção versionada em `.trivyignore` (ADR 0006 item 9, testado por `test_trivyignore_entries_follow_the_exception_format`) ou atualizar a base (patch pelo Dependabot; minor e major com o procedimento de upgrade do plano 29). Não usar `--exit-code 0`.
- Publicação falha = a VPS continua na versão anterior (seguro). Um achado novo do Trivy pode aparecer só no merge, porque o PR não roda `trivy image` (D6).
- `docker save` + `--input` evita dar o socket do Docker ao container do Trivy; custo: disco do runner (cabe).
- Até o item 38, o compose de produção sem `build:` impede o fluxo manual antigo (`build` na VPS). Ordem segura: merge do 37 → item 38 logo em seguida, fora da janela de deploy (06:00–08:00 BRT, a mesma que o `deploy.sh` do PR 39 recusa). Se a VPS não for atualizada, nada quebra: os containers em execução continuam.
- Tornar o pacote público (item 38) é irreversível; o aviso vai no corpo do PR (passo 14).
- Q1: o append no `infra/.env.example` (passo 8) é escrita sem leitura e respeita a regra; o usuário pode preferir acrescentar as três linhas ele mesmo.

### Decisões (aceitas pelo usuário)

- D1. Referência no compose **por digest** (`@${JOBS_IMAGE_DIGEST}` para `jobs` e `prefect-worker`, `@${MLFLOW_IMAGE_DIGEST}` para `mlflow`), sem tag.
- D2. Build/push pelo **`docker` CLI**, sem `docker/login-action`, `docker/setup-buildx-action`, `docker/build-push-action`, `docker/metadata-action` (quatro actions de terceiros a menos).
- D3. Tags publicadas: **só `:<sha do commit>`**.
- D4. Attestation: **GitHub artifact attestation por `actions/attest`** (recomendada pelo README do `attest-build-provenance`), verificável por `gh attestation verify`.
- D5. Gate do Trivy **bloqueante** no `publish`; escape só por exceção versionada.
- D6. `trivy image` em PR: **não neste PR**.
- D7. Sem SARIF da varredura da imagem (sem `security-events: write`).
- D8. Um job com passos por imagem em vez de `matrix` (as saídas de uma matrix se sobrescrevem).
- D9. Compose de produção **sem `build:`** e override `infra/docker-compose.build.yml` para CI e local.
- D10. **`create-storage-record: false`** em vez de conceder `artifact-metadata: write`. Justificativa: o storage record só alimenta a visão de artefatos ligados do GitHub, que este projeto não usa; desligá-lo tira uma permissão de escrita de um job que já publica. A attestation continua gravada no registry e no repositório (`attestations: write`) e verificável. Fallback: se a versão fixada não tiver o input, conceder `artifact-metadata: write`.
- D11. SC2086 do `compose-smoke`: **refatorar para `COMPOSE_FILE`** em vez de exceção.

## 10. Decisões que exigem ADR

**Sim.** O ADR 0006 diz, em "fora de escopo": "Trivy da imagem com attestation, junto da publicação no GHCR (PR 37)" e "exigem ADR próprio quando entrarem". Este PR também cria o primeiro workflow com permissões de escrita (`packages: write`, `id-token: write`, `attestations: write`). Decisão aceita: **um único ADR "Pipeline de entrega: publicação no GHCR e deploy automático"** cobrindo os PRs 37 a 39 (D1 a D11 deste plano; decisões do item 38 e do PR 39, inclusive o `harden-runner` só no `publish` como desvio do ADR 0006, a substituição do ADR 0004 no deploy e o fim da exceção do ADR 0004 no primeiro deploy automático bem-sucedido, com o checkout de bootstrap do plano 39, passo 9), escrito pelo usuário ou pela skill `generate-adr`, em PR próprio, **mergeado antes de começar este PR**. O planner não escreve o ADR.
