# 39 — Deploy automático: GitHub Actions → Tailscale → SSH (chave restrita) → `deploy.sh`

> Executa: agente (passos 1 a 8) e **usuário** (passo 9: verificador na VPS antes do merge e bootstrap logo depois). Depende de: 37 mergeado, item manual 38 concluído (environment `production`, credencial federada do Tailscale com subject **e** claim `job_workflow_ref`, chave restrita na VPS, VPS já em `pull`), S5 concluído (`docs/plans/S5-settings-seguranca-manual.md`), **S6 concluído** (`docs/plans/S6-ancora-de-confianca-manual.md`, âncora de confiança do ADR 0007, item 11; precisa estar feito antes do merge deste PR) e o ADR 0007 (`docs/adr/0007-delivery-pipeline.md`) mergeado antes do PR 37. Branch sugerida: `ci/deploy-ssh`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.
> Revisado em 2026-11-08 contra a `main` em `05c32c9`, com o retrabalho pedido pela revisão independente (aceito pelo usuário): `harden-runner` só no `publish`, validação do comando por regex ancorada, trava herdada na reexecução, rollback de git e de digests, `.env` nunca carregado com `source`, Tailscale com federação OIDC, `AddressFamily=inet`, saúde explícita em loopback, erro tratado passo a passo. Alinhamento entre planos (mesmo dia): troca de versão do MLflow com `pg_dump` + `mlflow db upgrade` (nota do plano 29), `pg_dump` do banco `prefect` antes de trocar a imagem do server (nota do plano 30), checagem de saúde do Prefect, `prefect-worker` com healthcheck (plano 34), VPS de 2 GB (28b padrão). Revisão final (mesmo dia, aceita pelo usuário): **bootstrap** do primeiro deploy (passo 9), URL do MLflow no argv do container como risco residual aceito, caso 45 antes de qualquer `docker`, `sha256sum` do binário do Tailscale obrigatório, `PLATFORM_DIR` padrão `/opt/platform`.
> **Alinhado em 2026-11-09 ao ADR 0007** (revisado por segurança; `main` em `7fc1923`): verificação da attestation de cada digest **antes do `pull`**, com verificador fixado por versão e sha256 na VPS (D16, casos 46 a 55, passo 9A); `pg_dump` do banco `ml` antes do `alembic upgrade` quando `alembic current` difere de `heads` (D17, casos 56 a 61); exceções do rollback com intervenção manual pelo procedimento de emergência do item 38 (D5); trilha `.deploy/history.log` (D18, casos 62 a 65); bootstrap com conferência do SHA antes do "Re-run" (D15, passo 9B).

## 1. Objetivo

Acrescentar ao `.github/workflows/deploy.yml` um job `deploy` que, depois do `publish`, entra na tailnet como nó efêmero `tag:ci` (federação OIDC) e faz SSH na VPS com uma chave cujo `authorized_keys` força `infra/scripts/deploy.sh`; o script atualiza o clone, **verifica a attestation de proveniência de cada digest**, puxa as imagens pelos digests, faz `pg_dump` antes de migrar o banco `ml` e antes de trocar a versão do Prefect server ou do MLflow (e roda o `mlflow db upgrade` quando o MLflow muda), migra, sobe, reaplica o `tailscale serve`, registra os deployments do Prefect, confere a saúde, reverte commit e containers se algo falhar depois da migração (salvo as exceções que exigem intervenção manual) e grava uma linha por execução em `.deploy/history.log`.
Fecha a exceção do ADR 0004: depois do primeiro deploy automático bem-sucedido (que exige um único checkout manual de bootstrap, passo 9B), merge na `main` volta a ser a única forma de mudar produção.

## 2. Fora do escopo

- Downgrade automático de migração (nunca; D5), inclusive do schema do MLflow e do Prefect. Rollback por `workflow_dispatch` (o rollback planejado é `git revert` na `main`, que gera um deploy novo).
- Restore automático dos dumps (D12, D13, D17): são rede de segurança; restore é intervenção manual de emergência (item 38, "Procedimento de emergência"), e o procedimento testado é do PR 57.
- Consultar a API do Prefect por flow runs em execução antes de recriar o worker (D8: fica para depois).
- Rotação do `.deploy/history.log` (cresce uma linha por deploy; ver riscos).
- Backup diário (Fase 5, PR 57). Alertas de deploy falho (Fase 5, PR 55; até lá, o aviso é o e-mail de falha do Actions, ADR 0007, item 13).
- CI e deploy do repo `models` e a prova do deploy (item 40).
- Editar ADRs (seção 10), `.claude/rules/infra.md` (PR próprio, seção 9), `CLAUDE.md` e `docs/plans/00-indice.md`.
- Configurar a âncora de confiança (S6) e os acessos do item 38: são itens do usuário.
- Tailscale SSH (proibido, ADR 0003). Abrir qualquer porta pública.

## 3. Fase do roadmap

Fase 3 de `docs/plataforma-ml.md` — "Pipelines do GitHub Actions nos dois repositórios"; "Pronto quando: um merge na `main` chega à VPS sem eu entrar nela". Do doc: "SSH na VPS: `alembic upgrade head`, `docker compose pull && up -d`, registra deployments do Prefect".

## 4. Arquivos a criar ou alterar

| Caminho | Quem | Motivo |
| --- | --- | --- |
| `tests/infra/test_deploy_sh.py` (novo) | test-writer | Comportamento do script com `git`, `docker`, `date`, `tailscale`, `curl` e `gh` falsos (casos 1 a 24, 39 a 45 e 46 a 65) |
| `tests/infra/test_deploy_workflow.py` | test-writer | Casos do job `deploy` (25 a 38); o caso 7 do PR 37 passa a "`secrets.` só no job `deploy`" |
| `infra/scripts/deploy.sh` (novo, executável) | implementer | Script chamado pelo forced command |
| `.github/workflows/deploy.yml` | implementer | Job `deploy`; `harden-runner` como primeiro passo do `publish` |
| `.gitignore` | implementer | `/.deploy.lock` e `/.deploy/` (estado local, dumps e trilha de auditoria do script na VPS) |
| `AGENTS.md` | implementer | Ver passo 7 |

`ci.yml` não muda: o passo `shellcheck infra/scripts/*.sh` já cobre o `deploy.sh`; o `actionlint` do PR 37 cobre o workflow.

### Contexto que o implementador precisa

- **ADR 0007, item 5** (`docs/adr/0007-delivery-pipeline.md`), texto que este PR implementa:
  - "**Verificação de proveniência antes do `pull`.** Para cada digest, o script verifica a attestation (`gh attestation verify` ou `cosign verify-attestation` equivalente, com binário fixado por versão e sha256 na VPS), exigindo o repositório, o workflow `deploy.yml`, `--source-ref refs/heads/main`, `--source-digest <sha>` e `--deny-self-hosted-runners`. Digest sem attestation válida do commit implantado falha a etapa 0."
  - "**Ordem:** verificação, `pull` por digest, `pg_dump` do banco da plataforma quando `alembic current` difere de `heads`, `alembic upgrade head`, `up -d --wait` e verificação de saúde em loopback. Migrações precisam ser compatíveis com a versão anterior; não há downgrade [...]."
  - "**Rollback.** Se algo falhar depois da migração, o script volta ao commit e aos digests anteriores. Exceções: quando o `mlflow db upgrade` rodou, ou quando não há digests anteriores registrados, o script para e exige intervenção manual pelo procedimento de emergência (item 12)."
  - "**Trilha de auditoria.** Cada execução acrescenta uma linha a `.deploy/history.log` (modo 600) com data UTC, SHA, digests, etapa final e código de saída."
  - Item 9: "Os dumps ficam em diretório com modo 700 e arquivos 600, no máximo 3 por banco."
  - Item 12: "Intervir na VPS só em emergência (restore de dump, deploy travado), pelo usuário com a chave pessoal, registrando depois numa issue os comandos e o motivo; nunca por agente." O passo a passo está no item 38 (`docs/plans/38-segredos-ci-cd-manual.md`, "Procedimento de emergência").
- Estado esperado de `.github/workflows/deploy.yml` (PR 37): `name: deploy`; `on: push: branches: [main]`; `permissions: {}`; `concurrency: {group: deploy-production, cancel-in-progress: false}`; `env.TRIVY_IMAGE` igual ao `security.yml`; job `publish` com `permissions` `{contents: read, packages: write, id-token: write, attestations: write}` e `outputs` `jobs-digest`, `mlflow-digest` (`sha256:<64 hex>`, tirados da saída do `docker push` e conferidos com `docker buildx imagetools inspect`). Cada imagem tem attestation de proveniência gravada por `actions/attest` com `subject-name: ghcr.io/<owner em minúsculas>/platform-<nome>`, `subject-digest` = digest publicado e `push-to-registry: true` (a attestation fica no GHCR, ao lado da imagem). A tag `:<sha>` é mutável; só o digest é implantado.
- Compose de produção (PR 37): `jobs` e `prefect-worker` com `image: ghcr.io/${GHCR_OWNER:?...}/platform-jobs@${JOBS_IMAGE_DIGEST:?...}`; `mlflow` com `...platform-mlflow@${MLFLOW_IMAGE_DIGEST:?...}`; `prefect-server` com `image: prefecthq/prefect:<X.Y.Z>-python3.12@sha256:<64 hex>` (PR 30); sem `build:`. `jobs` está em `profiles: ["jobs"]`, então o `pull` usa `--profile jobs`. Portas em loopback (ADR 0003): saúde `127.0.0.1:8080`, MLflow `127.0.0.1:5000`, Prefect `127.0.0.1:4200`, Postgres `127.0.0.1:5432`. Healthchecks no compose: `health`, `postgres` (já na `main`), `mlflow` (PR 29, `/health`), `prefect-server` (PR 30, `/api/ready`) e `prefect-worker` (PR 34, `--with-healthcheck`, `/health` em `127.0.0.1:8080` dentro do container).
- Banco da plataforma: `ml` (`infra/docker-compose.yml`, serviço `postgres`, `POSTGRES_DB: ml`). O serviço `jobs` roda o Alembic com `DATABASE_URL_ADMIN`. Saída do Alembic neste repo (planos 06 e 07): `alembic current` imprime `0002 (head)` quando o banco está no head e só o id (`0001`) quando está atrás; `alembic heads` imprime `<id> (head)`; com banco vazio, `current` não imprime revisão. Os logs `INFO` do Alembic vão para o stderr.
- `infra/mlflow/Dockerfile` (PR 29): uma linha `FROM ghcr.io/mlflow/mlflow:v<X.Y.Z>@sha256:<índice>`. O MLflow **não** migra banco existente na subida: com schema antigo, aborta com `Detected out-of-date database schema` e entra em laço de reinício. Procedimento do plano 29 (seção 5): `pg_dump` do banco `mlflow`, `stop mlflow`, `run --rm --no-deps mlflow sh -c 'exec mlflow db upgrade "$MLFLOW_BACKEND_STORE_URI"'`, `up`; **nunca** no `command` do serviço. O `mlflow db upgrade` só aceita a URL como argumento posicional: com esse `sh -c`, ela nunca aparece no argv nem no histórico do host, mas fica no argv do processo dentro do container enquanto o `db upgrade` roda (risco residual aceito, seção 9). O Dependabot só propõe patch do MLflow (`ignore` de minor e major no plano 29); minor e major chegam por PR manual, mas o deploy aplica o mesmo procedimento a qualquer mudança da linha `FROM`.
- Prefect server (plano 30): migra o próprio banco na subida; antes de trocar a imagem, `pg_dump` do banco `prefect`. API autenticada por `PREFECT_API_AUTH` (formato `admin:<senha>`) no `infra/.env`. Pelo código-fonte do Prefect (plano 30, risco "Endpoints fora da autenticação"), `GET /api/health` e `GET /api/ready` ficam fora da autenticação; o passo 0 do plano 30 confirma na versão fixada. O `deploy.sh` manda a credencial mesmo assim (D14): funciona nos dois casos.
- `infra/scripts/tailscale-serve.sh` (PR 03, já na `main`): `set -euo pipefail`; `tailscale serve reset`; uma linha `tailscale serve --bg --https=<porta> http://127.0.0.1:<porta>` por UI e `--tcp=5432`. Roda sem sudo porque `deploy` é operador do Tailscale (item 02).
- `python -m flows.deployments` (PR 33) registra os deployments de forma idempotente; o serviço `jobs` tem `PREFECT_API_URL: http://prefect-server:4200/api` e `PREFECT_API_AUTH_STRING: ${PREFECT_API_AUTH:?...}` (PR 34), então o registro usa a credencial do `infra/.env` da VPS, sem GitHub Secret.
- Item 38: `authorized_keys` com `restrict,from="100.64.0.0/10,fd7a:115c:a1e0::/48",command="/opt/platform/infra/scripts/deploy.sh"`; o argumento chega em `SSH_ORIGINAL_COMMAND`. O `from=` só barra origem fora da tailnet; quem limita os nós é a ACL. Segredos do environment `production`: `TS_OAUTH_CLIENT_ID`, `TS_AUDIENCE`, `VPS_HOST` (IPv4 da tailnet), `VPS_SSH_KEY`, `VPS_KNOWN_HOSTS`. Nenhum `TS_OAUTH_SECRET`, nenhuma variável. ACL: `tag:ci` → `tag:platform` só `tcp:22`. Credencial federada restrita ao subject `repo:<owner>/<repo>:environment:production` **e** à claim `job_workflow_ref` = `<owner>/<repo>/.github/workflows/deploy.yml@refs/heads/main` (ADR 0007, item 3). **O item 38 deixa a VPS num commit anterior a este PR**, com os digests de `jobs` e `mlflow` já no `infra/.env`: o `deploy.sh` ainda não existe lá quando o primeiro run do job `deploy` acontece (passo 9B, bootstrap).
- S6 (`docs/plans/S6-ancora-de-confianca-manual.md`): o usuário escolheu (b1) credenciais dos agentes sem poder de merge na `main` nem de aprovar deployment, **ou** (b2) o mantenedor como required reviewer do environment `production`. Com (b2), cada run do job `deploy` espera a aprovação na UI antes de rodar (inclusive o primeiro run e a reexecução do bootstrap); nada muda no workflow nem no script.
- `infra/.env` na VPS: linhas `CHAVE=valor` simples, com senhas. O script **nunca** faz `source`/`.` dele: lê só `GHCR_OWNER`, `JOBS_IMAGE_DIGEST`, `MLFLOW_IMAGE_DIGEST` e `PREFECT_API_AUTH` por `sed`, aceitando apenas `^[a-z0-9][a-z0-9-]*$` no dono, `sha256:[0-9a-f]{64}` nos digests e `^[A-Za-z0-9._~-]+:[A-Za-z0-9._~-]+$` na credencial.
- Horários atuais dos jobs (`America/Sao_Paulo`): 06:30 `ingest_weather_forecast`, 06:45 `ingest_weather_observed`, 07:00 `ingest_ons_load`. Recriar o `prefect-worker` durante um flow mata o flow.
- `sshd` do Ubuntu aceita do cliente só `LANG`/`LC_*` (`AcceptEnv`), então o CI não consegue injetar `DEPLOY_STAGE`, `PLATFORM_DIR`, `GH_BIN`, `GH_SHA256` nem outra variável.
- VPS: 1 vCPU, 2 GB de RAM (item 28b, padrão antes do item 31; 1 GB só se o usuário registrou dispensa), 2 GB de swap, 25 GB de disco. Nada de `build` na VPS.
- Regras de workflow (`.claude/rules/infra.md`): SHA + `# vX.Y.Z`; `permissions` mínimas por job; nenhum `${{ }}` em `run:` (valor por `env:`); `if:` em uma linha; `persist-credentials: false`; rodar `uv run zizmor .github/workflows/`.

## 5. Passos

1. (implementer, leitura) Resolver e validar SHAs como no plano S1, passo 4 (`gh api .../git/ref/tags/<tag>`, desreferenciar tag anotada, `compare/<tag>...<sha>` → `identical`) e **ler os inputs na ref fixada** (`gh api "repos/<owner>/<repo>/contents/action.yml?ref=<sha>" --jq .content | base64 -d` e o README na mesma ref):
   - `tailscale/github-action` (última release estável): confirmar os inputs de federação (esperado `oauth-client-id` e `audience`, com `id-token: write` no job), `tags`, `version` (fixar uma versão `X.Y.Z` do binário do Tailscale, nunca `latest`/`unstable`), `sha256sum` (**obrigatório**: o SHA-256 do pacote `tailscale_<X.Y.Z>_amd64.tgz`, conferido contra o arquivo `.sha256` publicado em `https://pkgs.tailscale.com/stable/`), `use-cache` (usar `false`) e `log-mode` (usar `quiet`; o input existe).
   - `step-security/harden-runner` (última release estável): input `egress-policy: audit`.
   - **Verificador de attestation (D16):** escolher a última release estável do `gh` (`cli/cli`) publicada há 7 dias ou mais. Num diretório novo e vazio do scratchpad, baixar `gh_<X.Y.Z>_linux_amd64.tar.gz` e `gh_<X.Y.Z>_checksums.txt` de `https://github.com/cli/cli/releases/download/v<X.Y.Z>/`, conferir o sha256 do tarball contra o `checksums.txt` (e, se a release tiver attestation, `gh attestation verify gh_<X.Y.Z>_linux_amd64.tar.gz --repo cli/cli`), extrair e calcular `sha256sum gh_<X.Y.Z>_linux_amd64/bin/gh`. Conferir no `--help` dessa versão (`gh_<X.Y.Z>_linux_amd64/bin/gh attestation verify --help`, rodado no CI ou em Linux) que existem `--bundle-from-oci`, `--repo`, `--signer-workflow`, `--source-ref`, `--source-digest` e `--deny-self-hosted-runners`. Se faltar algum, pare e avise (não troque por `cosign` sem o usuário: ver Q1).
   - `EXPECTED_REPO`: `gh repo view --json nameWithOwner -q .nameWithOwner`.
   Registrar no PR a tabela `action | tag | sha | inputs usados`, para o binário do Tailscale `versão | sha256 | URL conferida`, e para o `gh` `versão | sha256 do tarball | sha256 de bin/gh | URL conferida | flags conferidas`. Esses valores vão para o passo 9A.
2. (test-writer) `tests/infra/test_deploy_sh.py`: num `tmp_path`, executáveis falsos `git`, `docker`, `date`, `tailscale`, `curl` e `gh` que gravam a linha de comando, o estágio (`DEPLOY_STAGE`) e, para `docker`, uma cópia das linhas de digest do `infra/.env` no momento da chamada, e saem com o código que o teste mandar por subcomando. O `curl` falso grava também o que recebeu no stdin. O `git` falso responde `git show <rev>:<caminho>` com o conteúdo que o teste preparar (versão anterior do compose e do Dockerfile do MLflow). O `docker` falso também tenta `flock -n "$PLATFORM_DIR/.deploy.lock" true` e registra se conseguiu (caso 7); para `exec -T postgres ... pg_dump`, escreve bytes no stdout; para `run --rm jobs alembic current` e `run --rm jobs alembic heads`, imprime no stdout o texto que o teste preparar (padrão: `0008 (head)` nos dois). O `date` falso responde `+%H%M` com o horário do teste (padrão `1000`) e `-u +%Y-%m-%dT%H:%M:%SZ` com `2026-11-09T13:00:00Z`. O `gh` falso **emula a verificação**: lê uma tabela preparada pelo teste (digest → repositório, workflow, ref de origem, commit de origem, runner hospedado ou não), registra a linha de comando e se `GH_TOKEN`/`GITHUB_TOKEN` estavam no ambiente, e sai 0 só se `attestation verify oci://ghcr.io/<dono>/platform-<nome>@<digest>` tem `--bundle-from-oci` e cada flag (`--repo`, `--signer-workflow`, `--source-ref`, `--source-digest`, `--deny-self-hosted-runners`) bate com a linha da tabela; senão sai 1. O teste passa `GH_BIN=<tmp>/bin/gh` e `GH_SHA256=<sha256 do gh falso>`. `PATH=<tmp>/bin:/usr/bin:/bin` (o `flock`, o `sha256sum` e o `timeout` reais continuam disponíveis); `PLATFORM_DIR=<tmp>/platform` (sobrescreve o padrão `/opt/platform` do script) com `infra/.env` de exemplo (valores fictícios, nunca o `.env` real, incluindo `GHCR_OWNER=example-owner`), cópia de `infra/scripts/`, um `infra/docker-compose.yml` mínimo com a linha `image: prefecthq/prefect:...` e um `infra/mlflow/Dockerfile` com a linha `FROM`. Rodar `bash infra/scripts/deploy.sh` com `SSH_ORIGINAL_COMMAND`. `pytest.mark.skipif(sys.platform == "win32")`. Casos 1 a 24, 39 a 45 e 46 a 65. Em `tests/infra/test_deploy_workflow.py`, casos 25 a 38. Confirmar a falha (script inexistente; job `deploy` inexistente). Commit `test: add deploy script and deploy job tests`.
3. (implementer) `infra/scripts/deploy.sh` (mensagens e comentários em inglês):
   - **Estrutura:** corpo em funções, última linha `main "$@"; exit $?` (o script atualiza o próprio arquivo via `git checkout` enquanto roda). No topo: `PLATFORM_DIR="${PLATFORM_DIR:-/opt/platform}"`; `EXPECTED_REPO="<owner>/<repo>"` (passo 1); `GH_VERSION="<X.Y.Z>"`; `GH_BIN="${GH_BIN:-$HOME/.local/opt/gh-$GH_VERSION/bin/gh}"`; `GH_SHA256="${GH_SHA256:-<sha256 de bin/gh do passo 1>}"`. Os padrões são os de produção; os testes sobrescrevem `PLATFORM_DIR`, `GH_BIN` e `GH_SHA256`, e o `sshd` não deixa o cliente injetá-los. `set -uo pipefail` e **tratamento de erro explícito por passo**: cada comando que pode falhar é chamado como `if ! <cmd>; then fail <etapa>; fi` (ou por um helper `step <etapa> <cmd...>` que faz isso). Não depender de `set -e` dentro de funções: o bash ignora o `-e` em funções chamadas em contexto de condição. Nunca `set -x`, nunca `eval`, nunca `source`/`.` de arquivo de dados.
   - **Trilha de auditoria (D18):** toda execução termina por um único ponto que acrescenta a `"$PLATFORM_DIR/.deploy/history.log"` uma linha `<data UTC> sha=<S> jobs=<J> mlflow=<M> step=<etapa final> exit=<código> rollback=<none|done|refused>`, com a data de `date -u +%Y-%m-%dT%H:%M:%SZ`. Diretório `.deploy` criado com modo `700`, arquivo com modo `600` (`umask 077`), sempre por append. Quando o comando não passou na validação, `sha=- jobs=- mlflow=-` (o texto recebido nunca é gravado). A reexecução por `exec` não grava linha (o `exec` substitui o processo; um `trap ... EXIT` não roda no `exec`); só o processo que termina grava. Falha ao gravar vira aviso `history log write failed` no stderr e não muda o código de saída. Nomes de etapa: `validate`, `window`, `lock`, `git`, `credential`, `verify`, `dump`, `pull`, `db-backup`, `migrate`, `mlflow-upgrade`, `up`, `serve`, `deployments`, `health`, `done`.
   - **Validação:** `[[ "${SSH_ORIGINAL_COMMAND-}" =~ ^deploy\ [0-9a-f]{40}\ sha256:[0-9a-f]{64}\ sha256:[0-9a-f]{64}$ ]]` sobre a string inteira (rejeita quebra de linha, tab, espaço duplo, espaço no começo ou no fim). Falhou: stderr `invalid command` e saída 2, sem chamar `git` nem `docker`. Só depois de validar, separar as quatro palavras por expansão de parâmetro (`read -r` sobre a string já validada é aceitável).
   - **Janela:** `now="$(TZ=America/Sao_Paulo date +%H%M)"`; se `0600 <= now < 0800`, stderr `deploy window closed` e saída **75**, sem `git` nem `docker`.
   - **Trava (estágio inicial):** `exec 9>>"$PLATFORM_DIR/.deploy.lock"` e `flock -n 9`, senão saída 75 `another deploy is running`. O fd 9 fica aberto e é herdado pelo `exec` da reexecução.
   - **Git (estágio inicial):** `git fetch --quiet origin main`; `git merge-base --is-ancestor "$sha" origin/main` (senão 2); `git merge-base --is-ancestor HEAD "$sha"` (senão 2, `refusing to deploy an older commit`, D4; é isso que recusa a reexecução de um run antigo); guardar estado anterior em `$PLATFORM_DIR/.deploy/previous.env` (criado pelo script, modo `600`): `PREV_HEAD=<git rev-parse HEAD>`, `PREV_JOBS_IMAGE_DIGEST=<lido do infra/.env>`, `PREV_MLFLOW_IMAGE_DIGEST=<idem>` (vazio se ausente ou fora do formato); `git checkout --quiet --detach "$sha"`.
   - **Reexecução:** `exec env DEPLOY_STAGE=apply bash "$PLATFORM_DIR/infra/scripts/deploy.sh"` (o `SSH_ORIGINAL_COMMAND`, o `PLATFORM_DIR` e o fd 9 seguem), para que o resto rode com o `deploy.sh` do commit implantado (D6).
   - **Estágio `apply`:** revalidar o comando (mesma regex) e a janela; **não reabrir** o arquivo de trava: conferir que o fd 9 herdado está aberto e travado com `flock -n 9` (relock do mesmo fd sucede); se o fd não existir ou o `flock` falhar, saída 2 `apply stage without deploy lock`, sem `docker`. Ler `.deploy/previous.env` com `sed` (nunca `source`), aceitando só SHA de 40 hex e digests no formato. Ler e validar `PREFECT_API_AUTH` (D14) e `GHCR_OWNER` do `infra/.env` **antes de qualquer `docker`**: ausente ou fora do formato → como falha da etapa 0 (restaurar `git`, sem `docker`); etapa `credential`.
   - **Detectar troca de versão (estágio `apply`, antes de qualquer `docker`):** comparar a primeira linha que casa com `image: prefecthq/prefect:` em `git show "$PREV_HEAD:infra/docker-compose.yml"` com a do `infra/docker-compose.yml` implantado (`PREFECT_CHANGED`), e a linha `FROM` de `git show "$PREV_HEAD:infra/mlflow/Dockerfile"` com a do `infra/mlflow/Dockerfile` implantado (`MLFLOW_CHANGED`). Arquivo ausente em `PREV_HEAD` conta como mudança (D12, D13).
   - **Digests novos em `infra/.env`:** trocar só as duas linhas (acrescentar se faltarem) por arquivo temporário no mesmo diretório + `mv`, preservando modo `600`; demais linhas byte a byte iguais e na mesma ordem.
   - **Sequência**, com `C=(docker compose -f infra/docker-compose.yml)` e `dump <banco>` = `"${C[@]}" exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d <banco> -Fc' > "$PLATFORM_DIR/.deploy/backups/<banco>-<sha>.dump"` (diretório criado com modo `700`, arquivo `600`; arquivo vazio conta como falha; depois de cada dump bem-sucedido, o script mantém só os 3 mais recentes **daquele banco**, pela data de modificação):
     0. **Verificação de proveniência (D16), antes de qualquer `docker`.** Conferir que `"$GH_BIN"` existe, é executável e que `sha256sum "$GH_BIN"` bate com `GH_SHA256`; senão stderr `attestation verifier missing or checksum mismatch`. Depois, para `platform-jobs` com `J` e `platform-mlflow` com `M`, nesta ordem:

        ```bash
        timeout 180 env -u GH_TOKEN -u GITHUB_TOKEN GH_PROMPT_DISABLED=1 GH_NO_UPDATE_NOTIFIER=1 \
          "$GH_BIN" attestation verify "oci://ghcr.io/$GHCR_OWNER/platform-<nome>@<digest>" \
          --bundle-from-oci \
          --repo "$EXPECTED_REPO" \
          --signer-workflow "$EXPECTED_REPO/.github/workflows/deploy.yml" \
          --source-ref refs/heads/main \
          --source-digest "$sha" \
          --deny-self-hosted-runners >/dev/null
        ```

        Falhou → stderr `provenance verification failed for platform-<nome>` (sem a saída do `gh`, que pode trazer detalhes do ambiente), etapa `verify`, tratado como falha da etapa 0. Sucesso dos dois → stdout `provenance ok jobs=<J> mlflow=<M>`. Se o Q2 concluir que o `gh` exige token, este passo muda (replanejar; não improvisar token).
     0b. `dump prefect`, se `PREFECT_CHANGED`; `dump mlflow`, se `MLFLOW_CHANGED` (os dois antes do `pull`, com os containers ainda na versão anterior); etapa `dump`.
     1. `"${C[@]}" --profile jobs pull`
     1a. **Backup do banco da plataforma (D17):** `"${C[@]}" run --rm jobs alembic current` e `"${C[@]}" run --rm jobs alembic heads` (já com a imagem nova), capturando só o stdout; o conjunto de revisões de cada um é o primeiro campo de cada linha não vazia, ordenado. Qualquer dos dois falhando, ou `heads` vazio → falha na etapa `db-backup`. Se os conjuntos diferem (inclusive `current` vazio), `dump ml`.
     2. `"${C[@]}" run --rm jobs alembic upgrade head`
     2a. Só se `MLFLOW_CHANGED`: `"${C[@]}" stop mlflow` e `"${C[@]}" run --rm --no-deps mlflow sh -c 'exec mlflow db upgrade "$MLFLOW_BACKEND_STORE_URI"'`. A URL vem do ambiente do container: nunca aparece no argv nem no histórico do host; fica no argv do processo do container enquanto o `db upgrade` roda (risco residual aceito, seção 9)
     3. `"${C[@]}" up -d --remove-orphans --wait --wait-timeout 300` (espera `healthy` de todos os serviços com healthcheck, inclusive o `prefect-worker`)
     4. `infra/scripts/tailscale-serve.sh`
     5. `"${C[@]}" run --rm jobs python -m flows.deployments`
     6. saúde explícita em loopback, além do `--wait`: `curl -fsS --max-time 10 http://127.0.0.1:8080/health`, `http://127.0.0.1:5000/health` (MLflow) e, para o Prefect, `curl -fsS --max-time 10 -K - http://127.0.0.1:4200/api/health` com `user = "<PREFECT_API_AUTH>"` no stdin (D14); nunca `-u` nem a credencial em argumento
   - **Falha na validação da credencial ou nas etapas 0, 0b, 1, 1a ou 2** (containers ainda na versão anterior): restaurar as duas linhas do `infra/.env` a partir de `PREV_*` (se já trocadas), `git checkout --quiet --detach "$PREV_HEAD"`, sem `up`; stderr `deploy failed at <etapa>`; saída 1; `rollback=none`.
   - **Falha na etapa 2a** (`stop` ou `mlflow db upgrade`): o schema do `mlflow` pode ter mudado em parte. Restaurar `infra/.env` e `git checkout --quiet --detach "$PREV_HEAD"`, **sem `up`** (o MLflow antigo sobre schema novo entraria em laço de reinício); stderr `mlflow db upgrade failed; mlflow is stopped; restore from .deploy/backups/mlflow-<sha>.dump; manual intervention required (emergency procedure)`; saída 1; `rollback=refused`. Os outros serviços continuam na versão anterior, no ar.
   - **Falha nas etapas 3 a 6** (rollback). **Exceções, que param e exigem intervenção manual pelo procedimento de emergência** (item 38; ADR 0007, itens 5 e 12): se `PREV_JOBS_IMAGE_DIGEST` ou `PREV_MLFLOW_IMAGE_DIGEST` estiver vazio (sem digests anteriores registrados), **não** fazer `up`; stderr `no previous images recorded; manual intervention required (emergency procedure)`; saída 1; `rollback=refused`. Se `MLFLOW_CHANGED` (o `db upgrade` já rodou), também não fazer rollback dos containers: stderr `mlflow schema was upgraded; not rolling back; manual intervention required (emergency procedure)`; saída 1; `rollback=refused`. Caso contrário: `git checkout --quiet --detach "$PREV_HEAD"`, restaurar os digests anteriores no `infra/.env`, `"${C[@]}" up -d --remove-orphans --wait --wait-timeout 300`, reaplicar `infra/scripts/tailscale-serve.sh` em **best-effort** (falha vira aviso `tailscale serve reapply failed`, não muda o código de saída), imprimir `deploy failed <sha>, rolled back to <prev_head>` e sair 1; `rollback=done`. O rollback não verifica attestation de novo (os digests anteriores já estavam rodando). Nunca `alembic downgrade`. Se `PREFECT_CHANGED`, o rollback sobe a imagem anterior do Prefect sobre um banco que o server novo pode ter migrado: imprimir também o aviso `prefect image changed; check prefect-server logs; dump at .deploy/backups/prefect-<sha>.dump`.
   - **Sucesso:** `docker image prune -f --filter "until=168h"`; imprimir `deploy ok <sha> jobs=<digest> mlflow=<digest>`; saída 0; linha `step=done exit=0 rollback=none`. Nada de hostname, IP nem credencial na saída (vai para o log público).
   - Sem `docker login` (imagens públicas). Nenhuma senha, token nem credencial em argumento de comando no host.
4. (implementer) `.gitignore`: `/.deploy.lock` e `/.deploy/`.
5. (implementer) `deploy.yml`:
   - Primeiro passo do job `publish`: `step-security/harden-runner@<sha> # vX.Y.Z` com `egress-policy: audit`. **Não** pôr no job `deploy` (D9; ADR 0007, item 7).
   - Job `deploy`, forma-alvo (inputs conferidos no passo 1):

     ```yaml
       deploy:
         needs: publish
         if: github.ref == 'refs/heads/main'
         runs-on: ubuntu-latest
         timeout-minutes: 20
         environment: production
         permissions:
           id-token: write
         steps:
           - uses: tailscale/github-action@<sha> # vX.Y.Z
             with:
               oauth-client-id: ${{ secrets.TS_OAUTH_CLIENT_ID }}
               audience: ${{ secrets.TS_AUDIENCE }}
               tags: tag:ci
               version: <X.Y.Z>
               sha256sum: <sha256 do tailscale_X.Y.Z_amd64.tgz>
               use-cache: false
               log-mode: quiet
           - name: Prepare SSH
             env:
               VPS_SSH_KEY: ${{ secrets.VPS_SSH_KEY }}
               VPS_KNOWN_HOSTS: ${{ secrets.VPS_KNOWN_HOSTS }}
             run: |
               umask 077
               printf '%s\n' "$VPS_SSH_KEY" > "$RUNNER_TEMP/deploy_key"
               printf '%s\n' "$VPS_KNOWN_HOSTS" > "$RUNNER_TEMP/known_hosts"
           - name: Deploy
             env:
               VPS_HOST: ${{ secrets.VPS_HOST }}
               JOBS_DIGEST: ${{ needs.publish.outputs.jobs-digest }}
               MLFLOW_DIGEST: ${{ needs.publish.outputs.mlflow-digest }}
             run: |
               ssh -i "$RUNNER_TEMP/deploy_key" -o IdentitiesOnly=yes -o BatchMode=yes \
                 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$RUNNER_TEMP/known_hosts" \
                 -o AddressFamily=inet -o ConnectTimeout=30 "deploy@$VPS_HOST" \
                 deploy "$GITHUB_SHA" "$JOBS_DIGEST" "$MLFLOW_DIGEST"
           - if: always()
             run: rm -f "$RUNNER_TEMP/deploy_key" "$RUNNER_TEMP/known_hosts"
     ```

     Sem `actions/checkout` no `deploy` (o script vive na VPS). `timeout-minutes: 20` cobre a verificação de attestation, os `pg_dump` e o `mlflow db upgrade` com a base pequena da Fase 3; se crescer, subir até 30 (caso 38).
6. (implementer) `shellcheck infra/scripts/deploy.sh`, `uv run zizmor .github/workflows/`, actionlint; rodar os critérios de pronto.
7. (implementer) `AGENTS.md`:
   - Trocar a linha interina do PR 37 ("Na VPS, depois do PR 37 e até o PR 39 [...] `pull` [...]") por: "Deploy: automático a cada merge na `main` (`.github/workflows/deploy.yml` → `infra/scripts/deploy.sh`). Fora da janela 06:00–08:00 BRT; dentro dela o `deploy.sh` sai com 75 e o usuário usa 'Re-run failed jobs' depois das 08:00. O deploy verifica a attestation de cada digest antes do `pull`, faz `pg_dump` do `ml` antes de migrar e antes de trocar a versão do Prefect server ou do MLflow, roda o `mlflow db upgrade` quando o `FROM` de `infra/mlflow/Dockerfile` muda (nunca no `command` do serviço) e grava `.deploy/history.log` na VPS. Nenhum comando manual na VPS muda produção, salvo o procedimento de emergência do usuário (`docs/plans/38-segredos-ci-cd-manual.md`); nunca por agente."
   - Trocar "Merge de PR do Dependabot que muda `infra/` só chega à VPS pelo deploy manual do usuário (ADR 0004), fora da janela dos jobs" por "Merge de PR do Dependabot chega à VPS pelo deploy automático; faça o merge fora da janela 06:00–08:00 BRT. Do MLflow, o Dependabot só propõe patch; minor e major são PR manual (plano 29)".
   - Registrar `uv run pytest tests/infra/test_deploy_sh.py` (só Linux/CI).
8. Corpo do PR (inglês): tabela de actions, do binário do Tailscale e do `gh` (passo 1); o passo 9A em destaque (**instalar o verificador na VPS antes do merge**); o aviso de bootstrap do passo 9B (o primeiro run do job `deploy` **vai falhar** e isso é esperado); lembrete dos dois PRs que vêm logo depois (seção 10): status do ADR 0004 e remoção da exceção em `.claude/rules/infra.md`.
9. **(usuário) Verificador na VPS e bootstrap.**

   **9A. Antes do merge deste PR (com o PR aberto e os valores do passo 1 no corpo), fora de 06:00–08:00 BRT.** Na VPS, como `deploy`, instalar o `gh` fixado por versão e sha256 (sem `sudo`, sem `apt`; o caminho é o padrão `GH_BIN` do script). Troque `<X.Y.Z>`, `<TARBALL_SHA256>` e `<BIN_SHA256>` pelos valores do PR:

   ```bash
   V=<X.Y.Z>
   TARBALL_SHA256=<TARBALL_SHA256>
   BIN_SHA256=<BIN_SHA256>
   d="$(mktemp -d)"
   curl -fsSLo "$d/gh.tar.gz" "https://github.com/cli/cli/releases/download/v$V/gh_${V}_linux_amd64.tar.gz"
   curl -fsSLo "$d/checksums.txt" "https://github.com/cli/cli/releases/download/v$V/gh_${V}_checksums.txt"
   grep " gh_${V}_linux_amd64.tar.gz\$" "$d/checksums.txt"          # → a linha começa com <TARBALL_SHA256>
   echo "$TARBALL_SHA256  $d/gh.tar.gz" | sha256sum -c -             # → OK
   mkdir -p "$HOME/.local/opt/gh-$V"
   tar -xzf "$d/gh.tar.gz" -C "$HOME/.local/opt/gh-$V" --strip-components=1
   echo "$BIN_SHA256  $HOME/.local/opt/gh-$V/bin/gh" | sha256sum -c -   # → OK
   chmod -R go-w "$HOME/.local/opt/gh-$V"
   rm -rf "$d"
   "$HOME/.local/opt/gh-$V/bin/gh" --version                          # → gh version <X.Y.Z>
   ```

   Qualquer `FAILED` ou divergência: pare, apague `$HOME/.local/opt/gh-$V` e avise. Não faça `gh auth login` na VPS. Prova de que verifica **sem login** (Q2), com os digests que o item 38 gravou no `infra/.env` e o SHA do run do `deploy.yml` que os publicou (`<SHA38>`, do item 38), trocando `<owner>`/`<repo>`:

   ```bash
   cd /opt/platform
   J0="$(sed -n 's/^JOBS_IMAGE_DIGEST=\(sha256:[0-9a-f]\{64\}\)$/\1/p' infra/.env)"
   O="$(sed -n 's/^GHCR_OWNER=\([a-z0-9-]*\)$/\1/p' infra/.env)"
   env -u GH_TOKEN -u GITHUB_TOKEN "$HOME/.local/opt/gh-$V/bin/gh" attestation verify "oci://ghcr.io/$O/platform-jobs@$J0" \
     --bundle-from-oci --repo <owner>/<repo> \
     --signer-workflow <owner>/<repo>/.github/workflows/deploy.yml \
     --source-ref refs/heads/main --source-digest <SHA38> --deny-self-hosted-runners; echo "exit=$?"
   ```

   → verificação bem-sucedida e `exit=0`. Teste negativo, com outro SHA qualquer da `main` em `--source-digest` → `exit` diferente de 0. Se o comando pedir autenticação, **não** crie token: pare e devolva para o planejamento (Q2). Só faça o merge deste PR depois do `exit=0`.

   **9B. Logo depois do merge deste PR: bootstrap do primeiro deploy.** O item 38 deixou a VPS num commit anterior a este PR, e a forced command aponta para `/opt/platform/infra/scripts/deploy.sh`, que só existe a partir deste PR. Por isso o primeiro run do job `deploy` falha (o `ssh` sai com código diferente de 0, tipicamente `127`, sem tocar em nada). Com (b2) do S6, esse primeiro run espera aprovação antes; aprovar é o esperado. Fora de 06:00–08:00 BRT:
   1. No notebook, anotar o SHA do merge deste PR mostrado no GitHub: `gh pr view <número do PR> --json mergeCommit -q .mergeCommit.oid` → `S`.
   2. Na VPS, como `deploy`, só isto (sem `docker`, sem `build`, sem `up`):

      ```bash
      git -C /opt/platform fetch origin main && git -C /opt/platform checkout --detach origin/main
      git -C /opt/platform rev-parse HEAD
      ```

      → tem de ser `S`, ou o SHA de um merge **posterior já revisado** (que passou pelo fluxo normal de PR). Se for qualquer outro valor, pare: não reexecute nada e trate pelo procedimento de emergência (item 38). Os containers continuam na versão do item 38.
   3. No notebook, achar o run desse mesmo SHA (o `HEAD` conferido acima, `S` ou o merge posterior) e reexecutar **esse** run, não outro: `gh run list --workflow deploy.yml --branch main --json databaseId,headSha,conclusion -q '.[] | select(.headSha=="<HEAD conferido>")'` → `databaseId`; então `gh run rerun <databaseId> --failed` (ou "Re-run failed jobs" na UI desse run). Com (b2), aprovar de novo. O run reexecutado vê `HEAD` igual ao SHA dele, passa a checagem de fast-forward (`HEAD` é ancestral de si mesmo), registra `PREV_HEAD` igual a esse SHA e os digests do item 38 como anteriores (rollback possível), verifica a attestation e faz o deploy completo. A reexecução de um run **antigo** (SHA anterior ao `HEAD`) é recusada pelo fast-forward (`refusing to deploy an older commit`, código 2) sem mexer em nada.
   4. Conferir: `gh run view <databaseId> --log | grep -E "provenance ok jobs=sha256:[0-9a-f]{64} mlflow=sha256:[0-9a-f]{64}"` → uma linha; `gh run view <databaseId> --log | grep -E "deploy ok [0-9a-f]{40} jobs=sha256:"` → uma linha com o SHA conferido.

   Esse checkout é a **única** ação manual permitida entre o item 38 e o primeiro deploy automático bem-sucedido; ele não muda containers nem dados. A instalação do 9A não muda produção (só acrescenta um binário fora do clone). A exceção do ADR 0004 termina nesse deploy (seção 10; ADR 0007, item 8).

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/test_deploy_sh.py` (Linux/CI; no Windows os casos são pulados) | Todos passam |
| `uv run pytest tests/infra/` | Todos passam |
| `uv run pytest` | Suíte verde |
| `shellcheck infra/scripts/deploy.sh` | Sem saída |
| `uv run zizmor .github/workflows/` | Sem achados, código 0 |
| actionlint (comando do `AGENTS.md`, PR 37) | Sem saída |
| `git ls-files -s infra/scripts/deploy.sh` | Modo `100755` |
| `grep -nE '^\s*(source\|\.)\s' infra/scripts/deploy.sh` | Nada |
| `grep -nE 'curl[^\|]* -u ' infra/scripts/deploy.sh` | Nada |
| `grep -c -- '--deny-self-hosted-runners' infra/scripts/deploy.sh` | `1` ou mais |
| `gh pr checks` | Verde |
| Passo 9A, na VPS: `echo "$BIN_SHA256  $HOME/.local/opt/gh-$V/bin/gh" \| sha256sum -c -` | `OK` |
| Passo 9A, na VPS: verificação sem login do digest do item 38 | `exit=0` (e `exit` diferente de 0 com outro SHA em `--source-digest`) |
| Depois do merge e do bootstrap (passo 9B), fora da janela: `gh run view <databaseId> --json conclusion -q .conclusion` | `success` (no run reexecutado) |
| `gh run view <databaseId> --log \| grep -E "provenance ok jobs=sha256:[0-9a-f]{64} mlflow=sha256:[0-9a-f]{64}"` | Uma linha |
| `gh run view <databaseId> --log \| grep -E "deploy ok [0-9a-f]{40} jobs=sha256:"` | Uma linha, com o SHA conferido no 9B |
| `gh run view <databaseId> --log \| grep -Ei "ts\.net\|100\.[0-9]+\.[0-9]+\.[0-9]+"` e o mesmo no run que falhou antes do bootstrap | Nada nos dois (sem hostname nem IP da tailnet no log público, também em run com falha) |

## 7. Testes necessários

`sim`: validação do comando, janela, trava, fast-forward, verificação de proveniência antes do `pull`, ordem (dump antes de migrar e de trocar versão, migrar antes de subir), rollback de git e containers e suas exceções, trilha de auditoria, leitura segura do `.env`, credencial fora dos argumentos e "parar na primeira falha" são lógica testável com comandos falsos, e são o que evita deploy pela metade, imagem não atestada em produção, perda de schema ou comando arbitrário na VPS; a forma do job (`environment`, permissões, segredos só nele, opções do SSH, binário do Tailscale conferido) é testável estaticamente.

## 8. Casos de teste

`deploy.sh` (`tests/infra/test_deploy_sh.py`; `S` = 40 hex válido, `P` = SHA anterior, `J`/`M` = `sha256:` + 64 hex novos, `J0`/`M0` = anteriores; horário falso `1000` salvo indicação; salvo indicação, a imagem do Prefect e o `FROM` do MLflow em `P` são iguais aos do commit implantado, `alembic current` e `alembic heads` devolvem `0008 (head)`, e o `gh` falso tem `J` e `M` atestados por `EXPECTED_REPO`, workflow `deploy.yml`, ref `refs/heads/main`, commit `S`, runner hospedado):

1. `SSH_ORIGINAL_COMMAND="deploy S J M"`, tudo verde → código 0; o log tem, nesta ordem: `git fetch`, `git merge-base --is-ancestor S origin/main`, `git merge-base --is-ancestor HEAD S`, `git rev-parse HEAD`, `git checkout --quiet --detach S`, (estágio `apply`) `gh attestation verify ...platform-jobs@J...`, `gh attestation verify ...platform-mlflow@M...`, `docker compose ... --profile jobs pull`, `... run --rm jobs alembic current`, `... run --rm jobs alembic heads`, `... run --rm jobs alembic upgrade head`, `... up -d --remove-orphans --wait ...`, `tailscale serve reset`, `... run --rm jobs python -m flows.deployments`, `curl ... 127.0.0.1:8080/health`, `curl ... 127.0.0.1:5000/health`, `curl ... 127.0.0.1:4200/api/health`, `docker image prune -f --filter until=168h`; stdout contém `provenance ok jobs=J mlflow=M` e `deploy ok S jobs=J mlflow=M`; nenhum `pg_dump`, `stop mlflow` nem `db upgrade`.
2. Comandos inválidos → código 2, nenhum `git`/`docker`/`gh` no log (parametrizado): `rm -rf /`; SHA curto; SHA com maiúsculas; digest com 63 hex; `sha512:...`; palavras a mais (`deploy S J M x`); palavras a menos (`deploy S J`); verbo diferente (`deploi S J M`); vazio; ausente.
3. Separadores ilegais → código 2, nenhum `git`/`docker`: `"deploy S J M\nid"` (quebra de linha), tab no lugar de espaço, espaço duplo, espaço no começo, espaço no fim.
4. Horário falso `0600`, `0700` e `0759` → código 75, stderr com `deploy window closed`, nenhum `git`/`docker`. `0559` e `0800` → segue.
5. Trava já tomada por outro processo (o teste segura `flock` no mesmo arquivo) → código 75, nenhum `docker`.
6. Estágio `apply` sem fd 9 herdado (o teste roda com `DEPLOY_STAGE=apply` e sem o fd) → código 2, stderr `apply stage without deploy lock`, nenhum `docker`.
7. A trava fica retida durante o estágio `apply`: em todas as chamadas do `docker` falso, a tentativa `flock -n` dele no arquivo de trava falha (registrado como `locked`).
8. `git merge-base --is-ancestor S origin/main` falhando → código 2; nenhum `checkout` nem `docker`.
9. `git merge-base --is-ancestor HEAD S` falhando (reexecução de um run antigo) → código 2, stderr `refusing to deploy an older commit`; nenhum `checkout`, `gh` nem `docker`.
10. Reexecução: depois do `checkout`, o script roda de novo com `DEPLOY_STAGE=apply` (o log registra os dois estágios); no estágio `apply`, nenhum `git fetch`; um comando inválido injetado só no estágio `apply` (o teste chama o script direto com fd 9 travado e `DEPLOY_STAGE=apply`) → código 2.
11. Antes do `checkout`, `.deploy/previous.env` contém `PREV_HEAD=P`, `PREV_JOBS_IMAGE_DIGEST=J0`, `PREV_MLFLOW_IMAGE_DIGEST=M0`, modo `600`.
12. `infra/.env` com outras linhas e `J0`/`M0` → depois do sucesso, as duas linhas têm `J` e `M`, as outras linhas idênticas e na mesma ordem, modo `600`. Sem as linhas de digest → elas são acrescentadas e o resto fica intacto.
13. `infra/.env` contendo a linha `X=$(touch pwned)` (e `PWNED_DIR` apontando para o `tmp_path`) → nenhum arquivo `pwned` é criado em lugar nenhum do `tmp_path`; a linha continua no `infra/.env` byte a byte.
14. No momento de cada chamada `docker compose` do deploy, o `infra/.env` tem `JOBS_IMAGE_DIGEST=J` e `MLFLOW_IMAGE_DIGEST=M`.
15. `docker` falso falhando no `pull` → código 1; nenhum `alembic`; `infra/.env` volta a `J0`/`M0`; último `git checkout` registrado é `--detach P`; nenhum `up`.
16. `docker` falso falhando no `alembic upgrade head` → código 1; nenhum `up`; `infra/.env` volta a `J0`/`M0`; `git checkout --detach P`.
17. `docker` falso falhando no primeiro `up -d` → código 1; depois da falha, `git checkout --detach P` e um segundo `up -d`; no momento desse segundo `up`, `infra/.env` tem `J0`/`M0`; `tailscale serve reset` chamado de novo depois do segundo `up`; stdout contém `rolled back to P`; nenhum `alembic downgrade`; nenhuma nova chamada `gh` no rollback.
18. Cada um dos três `curl` falhando (parametrizado) → mesmo comportamento do caso 17.
19. `tailscale` falso falhando no deploy → rollback como no caso 17; `flows.deployments` não foi chamado. Com o `tailscale` falhando também no rollback → código continua 1, stderr com `tailscale serve reapply failed`, o segundo `up` aconteceu.
20. `flows.deployments` falhando → rollback como no caso 17.
21. Sem digests anteriores (`infra/.env` sem as linhas, ou com valor fora do formato) e falha no `up -d` → código 1, stderr com `no previous images recorded; manual intervention required`, **nenhum** segundo `up`; a linha da trilha tem `rollback=refused`.
22. Nenhum comando registrado contém `docker login`, `alembic downgrade`, `--password`, `-p `, `-u ` (exceto o `env -u GH_TOKEN -u GITHUB_TOKEN` do passo 0), `GH_TOKEN=` nem `--token`; o texto do script não contém `set -x`, `eval`, nem `source`/`.` de arquivo.
23. `docker image prune` só é chamado em sucesso, depois dos três `curl`; nunca em falha.
24. Com `PLATFORM_DIR` contendo espaço no caminho, o caso 1 continua verde (aspas em todas as expansões). Sem `PLATFORM_DIR` no ambiente, o script usa `/opt/platform` (o teste confere pela mensagem de erro de trava ou pelo caminho registrado, sem escrever em `/opt`).

Job `deploy` (`tests/infra/test_deploy_workflow.py`, com exemplos negativos embutidos):

25. Existe o job `deploy` com `needs: publish`, `if` de uma linha com `github.ref == 'refs/heads/main'` e `environment: production` (string ou `{name: production}`).
26. Permissões do `deploy` são exatamente `{id-token: write}`. Rejeita `{}` (sem federação), `contents: read` a mais, `packages`, `write-all`.
27. `secrets.` aparece **só** dentro do job `deploy`; o `publish` continua sem segredos; nenhum segredo no `env:` do topo.
28. Os únicos segredos referenciados são `TS_OAUTH_CLIENT_ID`, `TS_AUDIENCE`, `VPS_HOST`, `VPS_SSH_KEY`, `VPS_KNOWN_HOSTS`; nenhum `TS_OAUTH_SECRET`, nenhum `PREFECT_API_AUTH` (a credencial do Prefect fica só no `infra/.env` da VPS), nenhum `vars.`.
29. Nenhum `run:` contém `${{` (segredos e saídas do `publish` entram por `env:`).
30. Há um passo `tailscale/github-action@<sha>` com `tags: tag:ci`, `use-cache` falso, `version` no formato `X.Y.Z` (rejeita `latest`, `unstable`, ausência), `sha256sum` com 64 hex minúsculos (rejeita ausência, vazio e valor curto), `log-mode: quiet`, `oauth-client-id` e `audience`; sem `authkey`, sem `oauth-secret`, sem `--ssh` em `args`.
31. O comando `ssh` usa `-i`, `-o IdentitiesOnly=yes`, `-o BatchMode=yes`, `-o StrictHostKeyChecking=yes`, `-o UserKnownHostsFile=` e `-o AddressFamily=inet`. Rejeita `StrictHostKeyChecking=no`, `accept-new`, a falta de `AddressFamily=inet` e `ssh-keyscan` no workflow.
32. O `ssh` passa `deploy "$GITHUB_SHA" "$JOBS_DIGEST" "$MLFLOW_DIGEST"`, e `JOBS_DIGEST`/`MLFLOW_DIGEST` vêm de `needs.publish.outputs.jobs-digest`/`mlflow-digest`.
33. A chave é escrita com `umask 077` e existe passo `if: always()` que remove a chave e o `known_hosts`.
34. `harden-runner`: o primeiro passo do `publish` é `step-security/harden-runner@<sha>` com `egress-policy: audit`; o job `deploy` **não** tem nenhum passo `step-security/harden-runner`. Rejeita o `harden-runner` no `deploy`.
35. O job `deploy` não tem `actions/checkout`.
36. `concurrency` do workflow continua `deploy-production` sem cancelamento.
37. Nenhum passo do workflow imprime `tailscale status`, `tailscale ip`, `env` ou `printenv`.
38. `timeout-minutes` do `deploy` está definido e é ≤ 30.

`deploy.sh`, troca de versão e credencial (`tests/infra/test_deploy_sh.py`):

39. Imagem do Prefect diferente entre `P` e `S` (o `git show P:infra/docker-compose.yml` falso devolve `prefecthq/prefect:3.9.0-...`, o arquivo implantado tem `3.9.1-...`), tudo verde → código 0; um `exec -T postgres ... pg_dump ... -d prefect` depois das duas chamadas `gh` e antes do `pull`; o arquivo `.deploy/backups/prefect-S.dump` existe, não vazio, modo `600`; nenhum `pg_dump` do `mlflow`.
40. `FROM` do MLflow diferente entre `P` e `S`, tudo verde → código 0; nesta ordem: `pg_dump ... -d mlflow` (antes do `pull`), `pull`, `alembic upgrade head`, `stop mlflow`, `run --rm --no-deps mlflow sh -c 'exec mlflow db upgrade "$MLFLOW_BACKEND_STORE_URI"'`, `up -d`; nenhum argumento de comando registrado no host contém `postgresql` (a URL só é expandida dentro do container).
41. `pg_dump` falhando (ou devolvendo vazio) com o Prefect ou o MLflow mudando → código 1; nenhum `pull` nem `up`; `infra/.env` volta a `J0`/`M0`; `git checkout --detach P`.
42. `mlflow db upgrade` falhando → código 1; stderr contém `mlflow db upgrade failed` e `manual intervention required`; nenhum `up` depois da falha; `infra/.env` volta a `J0`/`M0`; `git checkout --detach P`.
43. `FROM` do MLflow mudando, `db upgrade` ok e falha no primeiro `up -d` → código 1; stderr contém `mlflow schema was upgraded; not rolling back` e `manual intervention required`; nenhum segundo `up`; a linha da trilha tem `rollback=refused`.
44. Imagem do Prefect mudando e falha num `curl` → rollback como no caso 17, e stderr contém `prefect image changed`.
45. Credencial do Prefect: o `curl` da 4200 recebe no stdin uma linha `user = "<valor de PREFECT_API_AUTH do infra/.env de exemplo>"`, e nenhum argumento registrado de nenhum comando contém esse valor nem a senha. `PREFECT_API_AUTH` ausente ou fora do formato `usuario:senha` URL-safe → código 1 **antes do passo 0** (nenhum `gh`, nenhum `pg_dump` e nenhuma chamada `docker` registrada), stderr `PREFECT_API_AUTH missing or invalid` (sem o valor), e último `git checkout` registrado `--detach P`.

Verificação de proveniência (D16; `gh` falso emulando a verificação):

46. Linha de comando exata, uma por digest, antes de qualquer `docker`: `attestation verify oci://ghcr.io/example-owner/platform-jobs@J --bundle-from-oci --repo <EXPECTED_REPO> --signer-workflow <EXPECTED_REPO>/.github/workflows/deploy.yml --source-ref refs/heads/main --source-digest S --deny-self-hosted-runners`, e a mesma com `platform-mlflow@M`; `provenance ok jobs=J mlflow=M` sai no stdout antes do `pull`.
47. Digest sem attestation (`J` fora da tabela do `gh` falso) → código 1; stderr `provenance verification failed for platform-jobs`; **nenhuma** chamada `docker`; `infra/.env` com `J0`/`M0`; último `git checkout` registrado `--detach P`; linha da trilha `step=verify exit=1 rollback=none`.
48. Digest de outra branch (`J` atestado com ref `refs/heads/feature`) → igual ao caso 47.
49. Digest antigo (`J` atestado para o commit `P`, não `S`) → igual ao caso 47.
50. Digest atestado por outro workflow (`.github/workflows/ci.yml`) ou outro repositório → igual ao caso 47.
51. Digest atestado num runner auto-hospedado → igual ao caso 47.
52. `J` válido e `M` sem attestation → código 1; stderr `provenance verification failed for platform-mlflow`; nenhum `docker`.
53. `GH_BIN` inexistente, ou com `GH_SHA256` diferente do sha256 do arquivo → código 1 **sem nenhuma chamada `gh`** nem `docker`; stderr `attestation verifier missing or checksum mismatch`; `git checkout --detach P`.
54. `GHCR_OWNER` ausente ou fora de `^[a-z0-9][a-z0-9-]*$` (ex.: `Example/x`) → código 1 antes de qualquer `gh` e `docker`; `git checkout --detach P`.
55. Com `GH_TOKEN=leak` e `GITHUB_TOKEN=leak` no ambiente do script, o `gh` falso registra os dois como ausentes; o texto `leak` não aparece em nenhum argumento registrado. (Depende do Q2: se o `gh` exigir token, este caso é replanejado.)

Backup do banco `ml` antes da migração (D17):

56. `alembic current` = `0008 (head)` e `heads` = `0008 (head)` → nenhum `pg_dump ... -d ml`; ordem `pull` → `alembic current` → `alembic heads` → `alembic upgrade head`.
57. `current` = `0007` e `heads` = `0008 (head)` → `exec -T postgres ... pg_dump ... -d ml` depois do `pull` e antes do `alembic upgrade head`; `.deploy/backups/ml-S.dump` existe, não vazio, modo `600`; `.deploy/backups` com modo `700`.
58. `current` sem nenhuma linha (banco sem revisão) e `heads` = `0008 (head)` → há o `pg_dump ... -d ml` antes do `upgrade`.
59. `pg_dump` do `ml` falhando ou devolvendo vazio → código 1; nenhum `alembic upgrade head` nem `up`; `infra/.env` volta a `J0`/`M0`; `git checkout --detach P`; linha da trilha `step=db-backup exit=1`.
60. `alembic current` (ou `alembic heads`) falhando, ou `heads` vazio → igual ao caso 59.
61. Retenção: com três dumps `ml-*.dump` mais antigos em `.deploy/backups` e um `prefect-*.dump`, depois do caso 57 há exatamente três `ml-*.dump`, entre eles `ml-S.dump`, o mais antigo foi removido e o `prefect-*.dump` continua.

Trilha de auditoria (D18):

62. Sucesso → `.deploy/history.log` ganha **exatamente uma** linha (apesar da reexecução), igual a `2026-11-09T13:00:00Z sha=S jobs=J mlflow=M step=done exit=0 rollback=none`; arquivo com modo `600` e `.deploy` com modo `700`.
63. Falhas (parametrizado), uma linha cada: `pull` falhando → `step=pull exit=1 rollback=none`; `up` falhando com rollback → `step=up exit=1 rollback=done`; janela fechada → `step=window exit=75`; trava ocupada → `step=lock exit=75`; caso 9 → `step=git exit=2`.
64. Comando inválido `rm -rf /` (e o com quebra de linha do caso 3) → uma linha `... sha=- jobs=- mlflow=- step=validate exit=2 rollback=none`; o texto recebido não aparece no arquivo; o arquivo continua com uma linha por execução (nenhuma quebra de linha injetada).
65. Duas execuções seguidas → duas linhas, a primeira intacta; nenhuma linha contém o valor de `PREFECT_API_AUTH`, `postgresql` nem `leak`. Com `.deploy/history.log` sem permissão de escrita, o deploy do caso 1 termina com código 0 e stderr `history log write failed`.

## 9. Riscos e perguntas em aberto

- **Q1. `gh` ou `cosign`:** o ADR 0007 aceita os dois. Recomendação deste plano: `gh attestation verify --bundle-from-oci`, porque a attestation de `actions/attest` com `push-to-registry: true` é gravada no GHCR pelo mecanismo de referrers do OCI, e o `cosign verify-attestation` procura por padrão o esquema de tags `.att`, o que pode não achar a attestation. Trocar para `cosign` exige replanejar o passo 0 e os casos 46 a 55.
- **Q2. O `gh` verifica sem login?** Não verificado. O `--bundle-from-oci` busca a attestation no registry público, mas o `gh` pode exigir autenticação para rodar o comando. O passo 9A prova isso antes do merge. Se exigir: não criar token na VPS por conta própria; devolver para o planejamento, porque um token na VPS é segredo novo fora do environment `production` (provável nota no ADR 0007).
- **Q3. Local do verificador:** `$HOME/.local/opt/gh-<X.Y.Z>/bin/gh` do usuário `deploy` (sem `sudo`). Alternativa: `/usr/local/lib/gh-<X.Y.Z>/` como root. Como `deploy` já é equivalente a root (grupo `docker`), a escolha não muda a segurança; a recomendação evita `sudo`. A conferência do sha256 a cada deploy pega troca acidental do binário.
- **Atualizar o `gh` da VPS** exige PR que muda `GH_VERSION`/`GH_SHA256` no `deploy.sh` **e** o usuário instalar a versão nova antes do merge (como no 9A); senão o deploy falha na etapa 0 (falha fechada). O Dependabot não acompanha esse binário.
- **Verificação depende de rede** (GHCR e a raiz de confiança do Sigstore/GitHub). Indisponibilidade = deploy falha na etapa 0, sem efeito na VPS; reexecutar depois. O `timeout 180` evita travar o job.
- **Não verificado nesta revisão:** se `docker compose up --wait --wait-timeout` existe na versão da VPS (o item 38 anota `docker compose version`); o valor do `sha256sum` do Tailscale (o passo 1 confere); a sintaxe exata de `--signer-workflow` na versão fixada do `gh` (o passo 1 confere no `--help`). A isenção de `/api/health` da autenticação vem do código-fonte do Prefect e é confirmada no passo 0 do plano 30; o script manda a credencial de qualquer forma.
- **Bootstrap (passo 9B):** o primeiro run do job `deploy` falha por desenho (o `deploy.sh` ainda não existe na VPS). Sem o checkout de bootstrap, nenhum deploy automático roda nunca. Se o usuário esquecer, o próximo merge falha do mesmo jeito; a correção é sempre o mesmo checkout, a conferência do SHA e o "Re-run" do run desse SHA.
- **URL do MLflow no argv do container (risco residual aceito, ADR 0007):** o `mlflow db upgrade` só aceita a URL como argumento posicional. Com `sh -c 'exec mlflow db upgrade "$MLFLOW_BACKEND_STORE_URI"'`, a senha nunca aparece no argv nem no histórico do host, mas fica visível no `/proc/<pid>/cmdline` do processo dentro do container enquanto o upgrade roda (segundos). Aceito porque o processo é curto, a VPS tem um único usuário e quem pode ler processos de container já está no grupo `docker` (equivalente a root).
- Rollback e migração: o rollback reverte commit e containers, nunca a migração. Uma migração que quebra a versão anterior deixa a versão antiga rodando sobre o schema novo. Regra (ADR 0007, item 5): migrações compatíveis com a versão anterior (expandir antes de contrair). Reverter na `main` um commit que trouxe migração **não** desfaz a migração e faz o `alembic upgrade head` falhar ("Can't locate revision"): corrija para frente, com migração nova. O dump do `ml` (D17) é para restore manual de emergência.
- **Schema do MLflow e do Prefect:** o `mlflow db upgrade` e a migração automática do Prefect não têm volta pelo script. Por isso o `pg_dump` vem antes e, quando o MLflow mudou, o script não sobe a versão antiga sobre o schema novo (D12). Restore de um dump é intervenção manual de emergência (item 38), registrada em issue; o procedimento testado de restore é do PR 57. Faça o merge de PR que troca a versão do MLflow ou do Prefect fora da janela e acompanhe o log.
- Depois de um rollback, a VPS fica inteira (commit e containers) em `P`. O próximo merge passa pela checagem fast-forward, porque `P` é ancestral de qualquer commit novo da `main`.
- `git checkout --detach` apaga mudanças locais em arquivos versionados na VPS (o `.env` está no `.gitignore` e fica). Depois deste PR, ninguém muda arquivo versionado na VPS.
- `tailscale serve reset` derruba por um instante as conexões às UIs; aceitável no deploy.
- Memória: `pull` + `up -d` recriam containers e, por alguns segundos, versões antiga e nova coexistem; com 2 GB e o swap do item 02 cabe, mas pode usar swap por instantes.
- Disco: os dumps ficam em `.deploy/backups/` (3 por banco: `ml`, `mlflow`, `prefect`). Os bancos são pequenos na Fase 3; o vigia de disco (PR 56) cobre crescimento. O `history.log` cresce uma linha por execução (bytes); rotação fica para depois.
- `docker image prune -f --filter "until=168h"` filtra pela **data de criação** da imagem (o `Created` do build no CI), não pela data do `pull`: uma imagem sem container, criada há mais de 7 dias, pode ser removida mesmo que tenha sido puxada hoje. Isso não quebra o rollback: o `up -d` puxa do GHCR (público) a imagem que faltar.
- A janela 06:00–08:00 é fixa no script. Os PRs 46 (07:30) e 54 (08:00) das Fases 4 e 5 vão exigir ampliá-la; não antecipe aqui.
- Exit 75 aparece como falha vermelha no Actions. É intencional: o usuário reexecuta depois das 08:00 ("Re-run failed jobs" reaproveita as saídas do `publish` já concluído). Alternativa rejeitada: `sleep` no runner até a janela abrir.
- Com (b2) do S6, todo deploy (inclusive de PR do Dependabot) espera aprovação; a janela é checada na hora em que o job roda, não na aprovação.
- Mascaramento no log público: o GitHub mascara o valor exato dos segredos, não variações (outro IP da tailnet, nome `*.ts.net`). O critério de pronto roda o `grep` também no run que falhou antes do bootstrap; o item 40 repete.
- Pendência fora deste PR: `.claude/rules/infra.md` diz "Exceção registrada até o PR 39 (ADR 0004): o usuário atualiza a VPS à mão [...]". Remover essa frase exige PR próprio com autorização do usuário (o implementer não edita `.claude/`), logo depois do primeiro deploy automático bem-sucedido (seção 10). O item 40 depende dele.

### Decisões (aceitas pelo usuário; D16 a D18 e a nova redação de D5 e D15 vêm do ADR 0007, revisado por segurança em 2026-11-09)

- D1. Saúde: `up --wait` (healthchecks do compose: `health`, `postgres`, `mlflow`, `prefect-server` e `prefect-worker`) **e** `curl` explícito em loopback para `:8080/health`, `:5000/health` (MLflow) e `:4200/api/health` (Prefect, D14), com resultado na saída do SSH. ACL do `tag:ci` só na 22.
- D2. Environment `production` sem required reviewers (item 38, D3), **salvo se o S6 escolher a opção (b2)**, que põe o mantenedor como required reviewer.
- D3. Janela: recusar entre 06:00 e 08:00 BRT com código 75 e reexecução manual.
- D4. Só avança (fast-forward): recusar SHA mais antigo que o `HEAD` implantado. Rollback planejado = `git revert` na `main`.
- D5. Rollback automático de **commit e containers** (HEAD e digests anteriores), nunca de migração. **Exceções que param e exigem intervenção manual pelo procedimento de emergência** (item 38): sem digests anteriores registrados, ou depois de um `mlflow db upgrade` (bem-sucedido ou não).
- D6. Reexecutar o `deploy.sh` do commit implantado depois do checkout, herdando a trava (fd 9).
- D7. Concorrência: `concurrency` do workflow (o GitHub mantém um run pendente e cancela o pendente mais antigo; o mais novo contém o mais antigo) **e** `flock` na VPS.
- D8. Consulta de flow runs em execução na API do Prefect antes de recriar o worker: **não neste PR**; a janela cobre os horários agendados. Reavaliar quando houver flows longos fora da janela.
- D9. `harden-runner` **só no `publish`** (ADR 0007, item 7: desvio do ADR 0006 por minimização de informação em repositório público).
- D10. Tailscale no CI por **federação OIDC** (item 38, D2), com `version` fixada, `sha256sum` obrigatório, `use-cache: false` e `log-mode: quiet`.
- D11. `-o AddressFamily=inet` no SSH, casando com `VPS_HOST` em IPv4 (item 38, D6).
- D12. **Troca de versão do MLflow** (linha `FROM` de `infra/mlflow/Dockerfile` diferente de `PREV_HEAD`): `pg_dump` do `mlflow` antes do `pull`, `stop mlflow` e `mlflow db upgrade` por `run --rm --no-deps` depois do `alembic`, então `up`. Nunca no `command` do serviço. Sem rollback de containers depois do `db upgrade` (D5).
- D13. **Troca de imagem do Prefect server** (linha `image: prefecthq/prefect:` diferente de `PREV_HEAD`): `pg_dump` do `prefect` antes do `pull`; a migração continua sendo a do próprio server na subida.
- D14. **Saúde do Prefect com credencial:** `PREFECT_API_AUTH` lida do `infra/.env` por `sed`, validada antes de qualquer `docker` e passada ao `curl` pelo stdin (`-K -`), nunca em argumento nem no log.
- D15. **Bootstrap do primeiro deploy** (passo 9B): um único `git fetch` + `git checkout --detach origin/main` manual na VPS, sem `docker`; antes do "Re-run", o usuário confere que `git rev-parse HEAD` é o SHA do merge deste PR mostrado no GitHub (ou de um merge posterior já revisado) e reexecuta o run **desse** SHA; o fast-forward recusa a reexecução de um run antigo. Alternativas rejeitadas: o CI copiar o `deploy.sh` pelo SSH (a chave só executa a forced command) e o item 38 fazer checkout de um commit que ainda não existe.
- D16. **Verificação de proveniência antes do `pull`**, por `gh attestation verify --bundle-from-oci` com repositório, workflow `deploy.yml`, `--source-ref refs/heads/main`, `--source-digest <sha>` e `--deny-self-hosted-runners`; `gh` fixado por versão e sha256 (conferido a cada deploy), instalado pelo usuário no passo 9A; falha = falha da etapa 0. Fecha o caminho de implantar, junto com um SHA novo, uma imagem de outra branch ou um digest antigo e vulnerável.
- D17. **`pg_dump` do banco `ml`** depois do `pull` e antes do `alembic upgrade head`, só quando `alembic current` difere de `heads`; modo 700/600, 3 por banco.
- D18. **Trilha `.deploy/history.log`** (modo 600): uma linha por execução com data UTC, SHA, digests, etapa final, código de saída e resultado do rollback; nada com segredo, host ou texto não validado.

## 10. Decisões que exigem ADR

**Nenhuma nova.** D1 a D18 estão cobertas pelo ADR 0007 (`docs/adr/0007-delivery-pipeline.md`, "Pipeline de entrega", escrito em 2026-11-09 com status Aceito), que precisa estar **mergeado na `main` antes do PR 37**. Ele já registra o desvio do ADR 0006 sobre o `harden-runner`, a regra de migrações compatíveis, o tratamento do schema do MLflow e do Prefect, a verificação de proveniência, a trilha de auditoria e que ele **substitui o ADR 0004 no que toca ao deploy** a partir do primeiro deploy automático bem-sucedido, com o checkout de bootstrap como única ação manual entre o item 38 e esse deploy.

Sinalizar ao usuário (não é ADR novo, mas pode pedir nota no ADR 0007): se o Q2 concluir que o `gh` exige token na VPS, ou se o Q1 levar a `cosign`, a forma do item 5 do ADR muda.

A mudança de status do ADR 0004 (agendador → `superseded` pelo ADR 0008, "Agendamento e execução pelo Prefect"; deploy → `superseded` pelo ADR 0007) vai num **único PR só de `docs/**` logo depois do primeiro deploy automático bem-sucedido**, aberto junto do PR que remove a exceção de `.claude/rules/infra.md`. Este último não é só `docs/**`: passa pelo `code-reviewer` e pelo `pr-reviewer`. Nenhum agente edita ADR.
