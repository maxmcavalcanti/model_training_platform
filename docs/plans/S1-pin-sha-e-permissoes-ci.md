# S1 — Pin por SHA das actions, `permissions` mínimas no `ci.yml` e imagens de terceiros por digest

> Executa: agente. Depende de: nenhuma (roda em paralelo à Fase 2, sem esperar o item 27, por decisão do usuário em 2026-11-08; ver Q1, resolvida). Branch sugerida: `ci/pin-sha-permissions`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar. O índice marcava "não (verificação por comandos)"; este plano muda para `sim` (ver seção 7) e a linha S1 do índice é corrigida no commit de docs do passo 2.
> Base: `docs/adr/0006-security-validation-in-ci.md`, itens 4, 5, 6, 7 e 9 (Aceito, 2026-11-08).

## 1. Objetivo

Fixar toda action do `.github/workflows/ci.yml` por SHA completo de commit com comentário `# vX.Y.Z`, declarar `permissions: contents: read` no topo e por job, e usar `persist-credentials: false` no checkout.
Fixar toda imagem de terceiros (Dockerfile dos jobs, os dois compose e o serviço do CI) por `tag@sha256:<digest>`, com testes em `tests/infra/` que travam essas regras.

## 2. Fora do escopo

- `.github/dependabot.yml` e `SECURITY.md` (S2). Até o S2, ninguém atualiza SHAs e digests automaticamente.
- Workflow `security.yml`, `zizmor`, `dependency-review-action`, Trivy (S3). `actionlint` (PR 37). Nenhum deles existe no repo hoje; não invente o comando.
- Regra `S` do `ruff` (S4). Settings do GitHub e checks required (S5).
- Subir versão de action ou de imagem. Este PR fixa **as versões que já estão em uso** (mesmo comportamento); upgrade é do Dependabot (S2).
- Fixar versão dos pacotes `apt` do Dockerfile (`tzdata`, `ca-certificates`, `curl`). Dependências Python já têm hash no `uv.lock`.
- Trocar o binário do supercronic: ele já é fixado por versão e SHA-256 (`infra/jobs/Dockerfile`, linhas 13–19, e testes do plano 16 em `tests/infra/test_jobs_image.py`). Aqui só se confirma o checksum (passo 9).
- Editar ADR 0002 (linha 91, "As actions são fixadas por major"): o ADR 0006 prevalece; ver Q3.
- Editar o plano 01 (histórico, já executado).
- `harden-runner`, OSV-Scanner, Scorecard (ADR 0006: futuros).
- Imagens próprias no GHCR (`ghcr.io/${GHCR_OWNER}/platform-*`): nascem no PR 37, que estende os testes deste plano (ver texto de alinhamento no passo 2).

## 3. Fase do roadmap

"Segurança em CI (em paralelo à Fase 2)", item S1 de `docs/plans/00-indice.md` (decidida no ADR 0006, item 12: primeiro dos quatro PRs). Não é uma fase de `docs/plataforma-ml.md`; é a fase própria criada pelo ADR 0006. O item 12 do ADR ainda diz "depois da Fase 2"; por decisão do usuário em 2026-11-08 a fase roda em paralelo à Fase 2, sem esperar o item 27, e o texto do ADR é ajustado neste PR (passo 2).

## 4. Arquivos a criar ou alterar

| Caminho | Quem | Motivo |
| --- | --- | --- |
| `tests/infra/test_supply_chain_pins.py` (novo) | test-writer | Regras de pin de actions, `permissions`, `persist-credentials`, gatilhos e segredos nos workflows; digest em todo `image:` e `FROM` de terceiros. Com exemplos negativos, no padrão dos arquivos vizinhos |
| `tests/infra/test_compose.py` | test-writer | O helper `image_tag` (linhas 463–467) quebra com digest (ver "Trecho que quebra" abaixo); o caso do plano 10 passa a comparar referência completa `tag@digest` entre prod, dev e o serviço do CI |
| `.github/workflows/ci.yml` | implementer | SHAs, `permissions`, `persist-credentials: false`, remover o comentário velho do `setup-uv`, `postgres` do serviço por `16.15@sha256:` |
| `infra/jobs/Dockerfile` | implementer | `FROM ghcr.io/astral-sh/uv:0.9.30-python3.12-bookworm-slim@sha256:<digest>` |
| `infra/docker-compose.yml` | implementer | `busybox:1.38.0@sha256:<digest>`, `postgres:16.15@sha256:<digest>` |
| `infra/docker-compose.dev.yml` | implementer | `postgres:16.15@sha256:<mesmo digest do prod>` |
| `docs/plans/37-publicar-imagem-ghcr.md` | task-planner (não o implementer) | Alinhar "por major" → SHA com comentário (ADR 0006, item 4) |
| `docs/plans/39-deploy-via-ssh.md` | task-planner | Idem para `tailscale/github-action` |
| `docs/plans/00-indice.md` | task-planner | Linha S1: coluna "Testes" passa a `sim` |
| `docs/adr/0006-security-validation-in-ci.md` | usuário (nenhum agente escreve ADR, `AGENTS.md`) | Item 12 da Decisão: "depois da Fase 2" → "em paralelo à Fase 2, por decisão do usuário em 2026-11-08". É a única menção à ordem no ADR (conferido por Grep em 2026-11-08: linha 35) |

### Estado atual (para o implementador)

`.github/workflows/ci.yml` hoje: sem `permissions`; `uses: actions/checkout@v7` (linhas 25 e 45); `uses: astral-sh/setup-uv@v10.3.3` (linha 27) precedido do comentário `# setup-uv publishes no floating major tag, so pin the exact release` (linha 26); serviço `postgres` com `image: postgres:16` (linha 16). Jobs: `lint-and-test` e `compose-smoke`. Nenhum usa `secrets.`.

Imagens de terceiros hoje: `infra/jobs/Dockerfile` linha 1 `FROM ghcr.io/astral-sh/uv:0.9.30-python3.12-bookworm-slim`; `infra/docker-compose.yml` linha 5 `image: busybox:1.38.0`, linha 20 `image: postgres:16.15`; `infra/docker-compose.dev.yml` linha 5 `image: postgres:16.15`. Os serviços `scheduler` e `jobs` usam `build:` (sem `image:`).

### Trecho que quebra (motivo da mudança em `test_compose.py`)

```python
# tests/infra/test_compose.py, linhas 463-467
def image_tag(service: dict) -> str | None:
    image = service.get("image")
    if not isinstance(image, str) or ":" not in image:
        return None
    return image.rsplit(":", 1)[1]
```

Com `postgres:16.15@sha256:abc...`, isso devolve `abc...`, e `test_postgres_image_tag_matches_dev_and_is_fixed` falha (`FIXED_MINOR_TAG`). Como o implementer não edita testes, o test-writer ajusta o helper neste PR. O teste de base do Dockerfile já aceita digest opcional (`tests/infra/test_jobs_image.py`, `BASE_IMAGE`, linhas 18–20) e não precisa mudar.

### Forma-alvo do `ci.yml` (SHAs ilustrativos: o implementador resolve os reais no passo 4)

```yaml
name: ci

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    # ...
    services:
      postgres:
        image: postgres:16.15@sha256:<digest do passo 6>
    steps:
      - uses: actions/checkout@<40 hex> # vX.Y.Z
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@<40 hex> # v10.3.3
        with:
          enable-cache: true
      # ... resto igual
  compose-smoke:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@<40 hex> # vX.Y.Z
        with:
          persist-credentials: false
      # ... resto igual
```

Regras do ADR 0006 que o PR cumpre: item 4 (SHA + `# vX.Y.Z`, `persist-credentials: false`, comentário do `setup-uv` removido); item 5 (imagens de terceiros por `tag@sha256:digest`); item 6 (`ci.yml` com `permissions: contents: read` no topo; sem `pull_request_target` nem `workflow_run`); item 7 (`ci.yml` sem segredos).

## 5. Passos

1. Criar a branch `ci/pin-sha-permissions` a partir da `main`. Não há passo 0: `pyyaml` já é dependência de dev (`pyproject.toml`).
2. (task-planner, antes do implementer; o usuário commita na branch como `docs: align plans 37 and 39 with SHA pinning`) Aplicar o alinhamento dos planos (ADR 0006, item 4: "o alinhamento dos planos entra no PR do pin"). Texto a aplicar:
   - `docs/plans/37-publicar-imagem-ghcr.md`, passo 2, linha "Fixe cada action por major atual, conferida no Marketplace." → "Fixe cada action por SHA completo de commit com comentário `# vX.Y.Z` (ADR 0006, item 4), resolvido e validado como no plano S1, passo 4; `actions/checkout` com `persist-credentials: false`."
   - Mesmo plano, passo 4 e critério de pronto do `actionlint`: `rhysd/actionlint:<versão>` → `rhysd/actionlint:<versão>@sha256:<digest>` (ADR 0006, item 5), resolvido como no plano S1, passo 6.
   - Mesmo plano, seção 9: acrescentar "O teste de digest do S1 (`tests/infra/test_supply_chain_pins.py`) exige `@sha256:` em todo `image:`; as imagens próprias `ghcr.io/${GHCR_OWNER}/platform-*:${IMAGE_TAG}` entram numa lista explícita de exceção, escrita pelo test-writer deste PR."
   - `docs/plans/39-deploy-via-ssh.md`, passo 3: "`tailscale/github-action` (major atual, ..." → "`tailscale/github-action` (por SHA completo com comentário `# vX.Y.Z`, ADR 0006, item 4, resolvido como no plano S1, passo 4, ...".
   - `docs/plans/00-indice.md`, linha S1: coluna "Testes" de "não (verificação por comandos)" para "sim".
   - (usuário, não o task-planner nem o implementer: nenhum agente escreve ADR) `docs/adr/0006-security-validation-in-ci.md`, item 12 da Decisão (linha 35): "**Ordem de implementação:** depois da Fase 2, em quatro PRs pequenos: ..." → "**Ordem de implementação:** em paralelo à Fase 2, por decisão do usuário em 2026-11-08, em quatro PRs pequenos: ...", sem mudar o resto do item. Não há outra menção à ordem no ADR (Grep por "Fase", "pós", "depois", "após" e "item 27" em 2026-11-08 só achou a linha 35); se o usuário achar outra, ajustar do mesmo jeito. Commit sugerido: `docs: run CI security in parallel with Phase 2 (ADR 0006)`.
3. (test-writer) Escrever `tests/infra/test_supply_chain_pins.py` e ajustar `tests/infra/test_compose.py` conforme a seção 8. Rodar `uv run pytest tests/infra/` e mostrar que falham pelo motivo certo (actions por tag, sem `permissions`, sem `persist-credentials`, imagens sem digest, postgres do CI diferente do compose), e que os exemplos negativos passam. Commit `test: expect pinned actions, images and minimal ci permissions`.
4. (implementer) Resolver o SHA de cada action, sem inventar:
   1. Versão exata. `setup-uv`: manter `v10.3.3`. `checkout`: descobrir para qual release `v7.Y.Z` a tag flutuante `v7` aponta hoje:
      `git ls-remote --tags https://github.com/actions/checkout "refs/tags/v7*"`
      Cada tag aparece numa linha `<sha>\trefs/tags/<tag>`; tag anotada aparece também como `refs/tags/<tag>^{}`, e **o commit é o SHA da linha `^{}`**. Escolher o `v7.Y.Z` cujo commit é igual ao commit de `v7`. Se nenhum `v7.Y.Z` coincidir, usar o maior `v7.Y.Z` publicado (`gh release list --repo actions/checkout --limit 10`) e registrar isso no PR.
   2. SHA pela API (alternativa e conferência):
      `gh api repos/<owner>/<repo>/git/ref/tags/<tag> --jq '.object.type + " " + .object.sha'`
      Se o tipo for `commit`, esse é o SHA. Se for `tag` (anotada), desreferenciar:
      `gh api repos/<owner>/<repo>/git/tags/<sha-do-objeto-tag> --jq '.object.type + " " + .object.sha'` → deve dar `commit <sha>`.
   3. Validar que o SHA é do repo e da tag (fecha o caso de commit de fork servido pelo repo pai):
      `gh api repos/<owner>/<repo>/commits/<sha> --jq .sha` → o mesmo SHA;
      `gh api "repos/<owner>/<repo>/compare/<tag>...<sha>" --jq .status` → `identical`.
   4. Registrar no corpo do PR uma tabela `action | tag | sha | saída do compare`.
5. (implementer) Editar `.github/workflows/ci.yml` para a forma-alvo da seção 4: `permissions: contents: read` no topo e em cada job; os dois checkouts e o `setup-uv` como `uses: <owner>/<repo>@<sha> # vX.Y.Z` (um espaço antes de `#`, formato que o Dependabot reconhece); `with: persist-credentials: false` nos dois checkouts; apagar a linha 26 (comentário "setup-uv publishes no floating major tag..."), sem substituto além do `# vX.Y.Z`. Nada mais muda nos passos.
6. (implementer) Resolver o digest de cada imagem, sempre o **digest do índice multi-arch** (manifest list / OCI index), nunca o de uma plataforma:
   `docker buildx imagetools inspect <imagem>:<tag>`
   A linha `Digest:` do topo é o digest do índice; `MediaType` deve ser `application/vnd.oci.image.index.v1+json` ou `application/vnd.docker.distribution.manifest.list.v2+json`, e a lista `Manifests` deve conter `Platform: linux/amd64`. Imagens: `ghcr.io/astral-sh/uv:0.9.30-python3.12-bookworm-slim`, `postgres:16.15`, `busybox:1.38.0`. Alternativa se o `buildx` faltar: `docker pull <imagem>:<tag>` e `docker image inspect --format '{{index .RepoDigests 0}}' <imagem>:<tag>` (dá o digest com que a tag foi puxada); conferir com o `imagetools` assim que possível.
7. (implementer) Validar cada digest: `docker buildx imagetools inspect <imagem>:<tag>@sha256:<digest>` lista `linux/amd64`, e `docker pull --platform linux/amd64 <imagem>:<tag>@sha256:<digest>` termina sem erro. Atenção: com `tag@digest` o Docker usa só o digest e ignora a tag; quem garante que o digest é da tag é o passo 6, feito na hora do PR. Registrar no PR a tabela `imagem | tag | digest | MediaType`.
8. (implementer) Aplicar: `infra/jobs/Dockerfile` linha 1; `infra/docker-compose.yml` (`busybox`, `postgres`); `infra/docker-compose.dev.yml` (`postgres`, mesmo digest do prod); `ci.yml`, serviço `postgres` → `postgres:16.15@sha256:<mesmo digest>` (hoje é `postgres:16`, flutuante; passa a ser a mesma imagem do compose).
9. (implementer) Confirmar o supercronic sem mudar o arquivo: `gh api repos/aptible/supercronic/releases/tags/v0.2.51 --jq '.assets[] | select(.name=="supercronic-linux-amd64") | .digest'` deve dar `sha256:cc232108374e8e2b537045f2d5eaa1229f619db314c3ba6a14d38b35dc0aa123`. Se o campo `digest` vier vazio, usar `curl -fsSL https://github.com/aptible/supercronic/releases/download/v0.2.51/supercronic-linux-amd64 | sha256sum` e comparar com o `ARG SUPERCRONIC_SHA256` do Dockerfile. O `sha256sum -c` do build já impõe isso; registrar a saída no PR.
10. Rodar os critérios de pronto (seção 6) e colar as saídas no PR.

## 6. Critérios de pronto

Comandos em bash (Git Bash no Windows, ou o runner). Nenhum deles lê `.env`.

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/` | Todos passam |
| `uv run pytest` (com `docker compose -f infra/docker-compose.dev.yml up -d`) | Todos passam |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem erro, código 0 |
| `grep -c 'uses:' .github/workflows/ci.yml` | `3` |
| `grep -cE 'uses: [A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40} # v[0-9]+\.[0-9]+\.[0-9]+$' .github/workflows/ci.yml` | `3` |
| `grep -c 'persist-credentials: false' .github/workflows/ci.yml` | `2` |
| `grep -n 'floating major' .github/workflows/ci.yml` | Sem saída (código 1) |
| `grep -nE '^permissions:' .github/workflows/ci.yml` | Uma linha |
| Para cada action: `gh api "repos/<owner>/<repo>/compare/<tag>...<sha>" --jq .status` | `identical` |
| `grep -nE '^FROM ' infra/jobs/Dockerfile` | `FROM ghcr.io/astral-sh/uv:0.9.30-python3.12-bookworm-slim@sha256:<64 hex>` |
| `grep -nE 'image: ' infra/docker-compose.yml infra/docker-compose.dev.yml .github/workflows/ci.yml` | Toda linha termina em `@sha256:<64 hex>`; os três `postgres` com o mesmo digest |
| Para cada imagem: `docker buildx imagetools inspect <imagem>:<tag>` | `Digest:` igual ao fixado; `MediaType` de índice; `Platform: linux/amd64` listado |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q` | Código 0, sem saída |
| `docker build -f infra/jobs/Dockerfile -t platform-jobs .` | Build termina, com o passo `sha256sum -c` em `OK` |
| `docker run --rm platform-jobs supercronic -test /app/infra/cron/crontab` | Código 0 |
| Passo 9 (`gh api .../releases/tags/v0.2.51 ...`) | `sha256:cc232108374e8e2b537045f2d5eaa1229f619db314c3ba6a14d38b35dc0aa123` |
| `grep -n 'depois da Fase 2' docs/adr/0006-security-validation-in-ci.md` | Sem saída (código 1) |
| `grep -n 'em paralelo à Fase 2' docs/adr/0006-security-validation-in-ci.md` | Uma linha (item 12) |
| `gh pr checks` | `lint-and-test` e `compose-smoke` em `pass` |
| `git diff --name-only main...HEAD` | Só os arquivos da seção 4 |

## 7. Testes necessários

`sim`: um teste estático em `tests/infra/` é barato (só `pyyaml` e regex, sem rede nem Docker), segue o padrão dos testes de compose e Dockerfile já existentes e impede que um PR futuro (37, 39, S3) volte a usar tag; além disso, o digest quebra o helper `image_tag` de `tests/infra/test_compose.py`, que precisa de ajuste do test-writer de qualquer forma. A verificação de que SHA e digest pertencem à tag fica nos comandos da seção 6 (precisa de rede e vale só na hora do PR).

## 8. Casos de teste

Arquivo novo `tests/infra/test_supply_chain_pins.py`, varrendo `.github/workflows/*.yml` e `*.yaml`, `infra/docker-compose*.yml` e `infra/**/Dockerfile`. Cada regra tem função de checagem com exemplos que aceitam e que rejeitam, como em `tests/infra/test_compose.py`. Notas para o test-writer: o PyYAML perde comentários, então a regra do `# vX.Y.Z` lê o texto linha a linha; e o PyYAML lê a chave `on:` como `True`, então os gatilhos ficam em `data.get("on", data.get(True))`.

Políticas sobre os arquivos reais:

1. Todo `uses:` de todos os workflows (passo ou job reutilizável) tem a forma `<owner>/<repo>[/<caminho>]@<40 hex minúsculos>`, seguida de ` # vX.Y.Z` na mesma linha. Hoje: 3 ocorrências no `ci.yml`, todas válidas.
2. Todo workflow declara `permissions` no topo, e o valor não é `write-all` nem `read-all`.
3. No `ci.yml`, o `permissions` do topo é exatamente `{contents: read}` e todo job declara `permissions` em que nenhum valor é `write`.
4. Todo passo que usa `actions/checkout` tem `with.persist-credentials` igual ao booleano `false`.
5. Nenhum workflow tem gatilho `pull_request_target` nem `workflow_run`.
6. O texto do `ci.yml` não contém `secrets.`.
7. Todo `image:` dos compose (`infra/docker-compose*.yml`) e dos workflows (`jobs.*.services.*.image` e `jobs.*.container.image`, string ou mapa com `image`) tem a forma `<nome>:<tag>@sha256:<64 hex minúsculos>`, com tag presente e diferente de `latest`. Serviço só com `build:` e sem `image:` não é checado.
8. Todo `FROM` de `infra/**/Dockerfile` tem `@sha256:<64 hex>`, exceto `FROM scratch` e `FROM <nome de estágio>` declarado antes com `AS <nome>`.
9. O `postgres` de `infra/docker-compose.yml`, o de `infra/docker-compose.dev.yml` e o serviço `postgres` do job `lint-and-test` do `ci.yml` usam a mesma referência completa `tag@digest`.

Exemplos para as funções de checagem (entrada → resultado):

10. `uses: actions/checkout@` + 40 hex + ` # v7.0.1` → aceito; `uses: org/repo/.github/workflows/x.yml@` + 40 hex + ` # v1.2.3` → aceito.
11. Rejeitados: `uses: actions/checkout@v7`; `@v10.3.3`; `@main`; SHA com 39 ou 41 caracteres; SHA com maiúsculas; SHA de 40 hex sem comentário; comentário `# v7` (sem `X.Y.Z`); comentário `# latest`.
12. `uses: ./.github/actions/local` → fora da regra 1 (ação local, sem ref); `uses: docker://alpine:3.20` → rejeitado; `uses: docker://alpine:3.20@sha256:` + 64 hex → aceito.
13. Permissões do topo: ausente → rejeitado; `write-all` → rejeitado; `read-all` → rejeitado; `{}` → aceito pela regra 2; `{contents: read}` → aceito.
14. Job do `ci.yml` sem `permissions` → rejeitado; job com `{contents: write}` → rejeitado; `{contents: read}` → aceito.
15. Checkout sem `with` → rejeitado; `persist-credentials: true` → rejeitado; a string `"false"` → rejeitado; o booleano `false` → aceito; passo que não é checkout → ignorado.
16. Gatilhos `{pull_request: null, push: {branches: [main]}}` → aceito; com `pull_request_target` → rejeitado; com `workflow_run` → rejeitado; lista `[push, pull_request_target]` → rejeitado.
17. Imagem `postgres:16.15@sha256:` + 64 hex → aceita; `ghcr.io/astral-sh/uv:0.9.30-python3.12-bookworm-slim@sha256:` + 64 hex → aceita (o `:` do registry com porta, ex. `localhost:5000/x:1.0@sha256:...`, também é aceito). Rejeitadas: `postgres:16.15`; `postgres@sha256:` + 64 hex (sem tag); `postgres:latest@sha256:` + 64 hex; `postgres:16.15@sha256:` + 63 hex; `postgres:16.15@sha512:...`; `postgres:16.15@sha256:` + 64 hex maiúsculos.
18. Dockerfile: `FROM python:3.12@sha256:` + 64 hex → aceito; `FROM python:3.12` → rejeitado; `FROM --platform=linux/amd64 python:3.12@sha256:...` → aceito; `FROM x@sha256:... AS build` seguido de `FROM build` → aceito; `FROM scratch` → aceito; `FROM build` sem estágio `build` declarado → rejeitado.

Ajuste em `tests/infra/test_compose.py` (plano 10, caso 5):

19. `image_tag` separa o digest: `postgres:16.15@sha256:` + 64 hex → tag `16.15`. A checagem do caso 5 continua exigindo tag fixa `major.minor` igual em prod e dev, e passa a exigir também o mesmo digest. Os negativos atuais (`postgres:16`, `postgres:latest`, `postgres`, `16.15` × `16.14`, `16.15` × `16`) continuam rejeitados; novos: mesma tag com digests diferentes → rejeitado; mesma tag e mesmo digest → aceito.

Casos já existentes que devem continuar passando sem mudança: `tests/infra/test_jobs_image.py` (base com digest opcional, supercronic com versão e SHA-256), `tests/infra/test_crontab.py`, `tests/infra/test_tailscale_serve.py`.

## 9. Riscos e perguntas em aberto

Riscos:

- **Multi-arch da imagem `uv`** (e das outras): fixar o digest de uma plataforma em vez do índice funciona no runner e na VPS (ambos `linux/amd64`; o supercronic baixado já é `amd64`), mas quebra em máquina `arm64` e confunde o Dependabot (S2). Mitigação: passos 6 e 7 exigem digest de índice com `linux/amd64` listado; o `compose-smoke` constrói a imagem no runner e prova o caminho `amd64`.
- **`compose-smoke` precisa continuar verde**: ele sobe `postgres` pelo digest, constrói `jobs` e `scheduler` a partir do `FROM` com digest e roda `alembic`, `whoami`, `supercronic -test` e `date +%Z`. Nenhum passo do job muda além do checkout. Se falhar, o problema é digest errado ou de plataforma errada.
- **Tag oficial reconstruída**: `postgres:16.15` e `busybox:1.38.0` são reconstruídas no Docker Hub com a mesma tag (patches do Debian). O digest fixado fica certo na hora do PR e envelhece depois; até o S2 entrar, ninguém o atualiza. Não pôr "digest = tag atual" no CI, porque passaria a falhar sozinho.
- **Deploy manual na VPS** (ADR 0004, feito pelo usuário, nunca por agente): depois do merge, `docker compose up -d` pode recriar `postgres` e `health` se o digest fixado diferir da imagem local, com alguns segundos de banco fora. Fazer fora da janela dos jobs (06:30, 06:45 e 07:00, `America/Sao_Paulo`) e reconstruir `scheduler` (`docker compose -f infra/docker-compose.yml build scheduler`) depois.
- **`postgres:16` → `postgres:16.15@...` no CI**: muda a imagem do banco de teste para a mesma do compose. É o desejado (paridade), mas pode revelar diferença de versão nos testes `db`.
- **Commit de fork**: a API do GitHub serve commits de forks pelo repo pai. O `compare ... → identical` do passo 4 é a defesa; o `zizmor` (S3, auditoria `impostor-commit`) vai repetir a checagem.
- Nada de rede nos testes novos: são estáticos e rodam também no Windows.

Perguntas (todas resolvidas em 2026-11-08; registro da recomendação adotada):

- **Q1. Dependência do item 27. RESOLVIDA (decisão do usuário em 2026-11-08, recomendação adotada): S1 não espera o 27.** A fase "Segurança em CI" roda em paralelo à Fase 2; o índice já registra isso e o ADR 0006, item 12, é ajustado neste PR (passo 2). O PR não toca ingestão nem banco.
- **Q2. Quem alinha os planos 37 e 39.** Decidido pela recomendação em 2026-11-08. O implementer não edita `docs/plans/`. Recomendação: tarefa do task-planner (passo 2), com o texto já definido acima, commitada pelo usuário na branch do S1 antes do implementer, para cumprir "o alinhamento dos planos entra no PR do pin" (ADR 0006, item 4). Alternativa rejeitada: PR só de docs separado, que deixa o S1 entrar sem o alinhamento.
- **Q3. ADR 0002, linha 91** ("As actions são fixadas por major"). Decidido pela recomendação em 2026-11-08. Recomendação: não editar; o ADR 0006 (posterior, Aceito) prevalece. Se o usuário quiser rastreabilidade, uma nota "alterado pelo ADR 0006" é um PR só de docs dele.
- **Q4. `permissions` por job além do topo.** Decidido pela recomendação em 2026-11-08. O ADR pede o topo; a tarefa pede também o mínimo por job. Recomendação: declarar nos dois (topo `contents: read` e cada job `contents: read`), porque um job novo que precise de mais tem de dizer isso explicitamente; o teste da regra 3 trava.
- **Q5. Versão do `checkout`.** Decidido pela recomendação em 2026-11-08. Recomendação: o `v7.Y.Z` para o qual `v7` aponta hoje (mesmo código que roda agora), não a última release de outro major.
- **Q6. Regra em `.claude/rules/infra.md`.** Decidido pela recomendação em 2026-11-08. Uma linha "actions por SHA com `# vX.Y.Z`; imagens de terceiros por `tag@sha256:`; `permissions` mínimas" ajudaria os planos 37 e 39 e o S3. Recomendação: o usuário acrescenta no mesmo PR (o implementer não edita `.claude/`); o PR já passa por `code-reviewer` e `pr-reviewer`.

## 10. Decisões que exigem ADR

Nenhuma nova. O ADR 0006 (Aceito, 2026-11-08) cobre pin por SHA, imagens por digest, `permissions` e `persist-credentials`. O conflito com a linha 91 do ADR 0002 é resolvido pelo 0006 (Q3). A troca da ordem no item 12 do ADR 0006 ("depois da Fase 2" → "em paralelo à Fase 2") já é decisão do usuário (2026-11-08); entra como ajuste de texto feito pelo usuário neste PR (passo 2), sem ADR novo.
