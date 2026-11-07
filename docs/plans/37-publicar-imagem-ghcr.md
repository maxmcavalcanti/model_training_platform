# 37 — Build e publicação das imagens no GHCR a cada merge na `main`

> Executa: agente. Depende de: 34 (e 36, para a imagem já sem supercronic). Branch sugerida: `ci/publish-images`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar `.github/workflows/deploy.yml` que, a cada push na `main`, constrói as imagens `platform-jobs` e `platform-mlflow` e publica no GHCR com a tag do commit e `main`.
Fazer o compose de produção usar essas imagens, para a VPS só precisar de `pull` (primeira metade de "merge na `main` chega à VPS").

## 2. Fora do escopo

- SSH na VPS e `up -d` (PR 39). Segredos (item 38).

## 3. Fase do roadmap

Fase 3 — "Pipelines do GitHub Actions nos dois repositórios" (lado `plataforma`, parte build → GHCR).

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `.github/workflows/deploy.yml` | Job `imagens`: login no GHCR com `GITHUB_TOKEN`, build e push |
| `infra/docker-compose.yml` | `image: ghcr.io/${GHCR_OWNER}/platform-jobs:${IMAGE_TAG}` em `jobs`, `prefect-worker`; idem `platform-mlflow` em `mlflow`. Mantém `build:` para uso local |
| `infra/.env.example` | `GHCR_OWNER`, `IMAGE_TAG=main` |
| `.github/workflows/ci.yml` | Passo `actionlint` para validar os workflows |
| `tests/infra/test_compose.py` | Casos de imagem (test-writer) |

Do doc ("CI/CD e operação"): "No merge na `main`: Build da imagem → GHCR → SSH na VPS: `alembic upgrade head`, `docker compose pull && up -d`, registra deployments do Prefect".
Regra (`.claude/rules/infra.md`): "Deploy só sai de merge na `main`. Nada de SSH manual para mudar produção."

## 5. Passos

1. (test-writer) Casos da seção 8. Confirme falha. Commit `test: expect ghcr images in compose`.
2. (implementer) `deploy.yml`:
   - `on: push: branches: [main]` e `workflow_dispatch`.
   - `permissions: contents: read, packages: write`.
   - `concurrency: {group: deploy, cancel-in-progress: false}` (dois merges seguidos não rodam deploys em paralelo).
   - Job `imagens`: `actions/checkout`, `docker/login-action` (registry `ghcr.io`, usuário `${{ github.actor }}`, senha `${{ secrets.GITHUB_TOKEN }}`), `docker/build-push-action` para `infra/jobs/Dockerfile` (contexto `.`) e `infra/mlflow/Dockerfile` (contexto `infra/mlflow`), tags `ghcr.io/${{ github.repository_owner }}/platform-jobs:${{ github.sha }}` e `:main` (idem `platform-mlflow`). Nome do dono em minúsculas (o GHCR exige).
   - Fixe cada action por major atual, conferida no Marketplace.
3. Compose: `image:` nos três serviços, como na tabela.
4. `ci.yml`: passo `docker run --rm -v "$PWD:/repo" --workdir /repo rhysd/actionlint:<versão> -color` (fixe a versão).
5. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/` | Todos passam |
| `docker run --rm -v "$PWD:/repo" --workdir /repo rhysd/actionlint:<versão>` | Sem saída, código 0 |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q` | Código 0 |
| `gh pr checks` | Verde |
| Depois do merge: `gh run list --workflow deploy.yml --limit 1` | `completed success` |
| Depois do merge: `docker pull ghcr.io/<dono>/platform-jobs:main` | Baixa a imagem |

## 7. Testes necessários

`sim` para o compose (imagens e tags); o workflow em si não tem teste automatizado além do `actionlint` e da primeira execução real, que substituem.

## 8. Casos de teste

1. `jobs` e `prefect-worker` usam `image: ghcr.io/${GHCR_OWNER}/platform-jobs:${IMAGE_TAG}`.
2. `mlflow` usa `ghcr.io/${GHCR_OWNER}/platform-mlflow:${IMAGE_TAG}`.
3. Nenhuma imagem própria usa a tag `latest`.
4. `infra/.env.example` declara `GHCR_OWNER` e `IMAGE_TAG` (já coberto pelo caso geral de variáveis do PR 10).

## 9. Riscos e perguntas em aberto

- P2 resolvida (2026-11-07): repositórios públicos; a VPS puxa as imagens do GHCR sem `docker login` e sem token. Atenção: o pacote do GHCR pode nascer privado mesmo com o repo público; o item 38 confere a visibilidade e a torna pública. O `GITHUB_TOKEN` do workflow só escreve no GHCR e nunca sai do Actions.
- Imagem pública: nada de segredo em camada da imagem (sem `.env`, sem `ARG` com senha). O `.dockerignore` deve excluir `.env` e `infra/.env`; confira.
- A partir daqui, `build` na VPS não deve mais ser usado; o item 38 troca o fluxo manual por `pull`.

## 10. Decisões que exigem ADR

Nenhuma (o fluxo está no doc).
