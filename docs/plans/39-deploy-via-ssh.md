# 39 — Deploy automático: GitHub Actions → Tailscale → SSH (chave restrita) → `deploy.sh`

> Executa: agente. Depende de: 37 mergeado, item manual 38 concluído (environment `production`, credencial federada do Tailscale, chave restrita na VPS, VPS já em `pull`), S5 concluído (`docs/plans/S5-settings-seguranca-manual.md`), e o ADR "Pipeline de entrega" mergeado antes do PR 37 (plano 37, seção 10). Branch sugerida: `ci/deploy-ssh`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.
> Revisado em 2026-11-08 contra a `main` em `05c32c9`, com o retrabalho pedido pela revisão independente (aceito pelo usuário): `harden-runner` só no `publish`, validação do comando por regex ancorada, trava herdada na reexecução, rollback de git e de digests, `.env` nunca carregado com `source`, Tailscale com federação OIDC, `AddressFamily=inet`, saúde explícita em loopback, erro tratado passo a passo. Alinhamento entre planos (mesmo dia): troca de versão do MLflow com `pg_dump` + `mlflow db upgrade` (nota do plano 29), `pg_dump` do banco `prefect` antes de trocar a imagem do server (nota do plano 30), checagem de saúde do Prefect, `prefect-worker` com healthcheck (plano 34), VPS de 2 GB (28b padrão). Revisão final (mesmo dia, aceita pelo usuário): **bootstrap** do primeiro deploy (passo 9), URL do MLflow no argv do container como risco residual aceito, caso 45 antes de qualquer `docker`, `sha256sum` do binário do Tailscale obrigatório, `PLATFORM_DIR` padrão `/opt/platform`.

## 1. Objetivo

Acrescentar ao `.github/workflows/deploy.yml` um job `deploy` que, depois do `publish`, entra na tailnet como nó efêmero `tag:ci` (federação OIDC) e faz SSH na VPS com uma chave cujo `authorized_keys` força `infra/scripts/deploy.sh`; o script atualiza o clone, puxa as imagens pelos digests publicados, faz `pg_dump` antes de trocar a versão do Prefect server ou do MLflow (e roda o `mlflow db upgrade` quando o MLflow muda), migra, sobe, reaplica o `tailscale serve`, registra os deployments do Prefect e confere a saúde, revertendo commit e containers se algo falhar depois da migração.
Fecha a exceção do ADR 0004: depois do primeiro deploy automático bem-sucedido (que exige um único checkout manual de bootstrap, passo 9), merge na `main` volta a ser a única forma de mudar produção.

## 2. Fora do escopo

- Downgrade automático de migração (nunca; D5), inclusive do schema do MLflow e do Prefect. Rollback por `workflow_dispatch` (o rollback planejado é `git revert` na `main`, que gera um deploy novo).
- Restore automático dos dumps do D12 e do D13 (são rede de segurança; restore manual de emergência, e o procedimento testado é do PR 57).
- Consultar a API do Prefect por flow runs em execução antes de recriar o worker (D8: fica para depois).
- Backup diário (Fase 5, PR 57). Alertas de deploy falho (Fase 5, PR 55).
- CI e deploy do repo `models` e a prova do deploy (item 40).
- Editar ADRs (seção 10), `.claude/rules/infra.md` (PR próprio, seção 9) e `docs/plans/00-indice.md`.
- Tailscale SSH (proibido, ADR 0003). Abrir qualquer porta pública.

## 3. Fase do roadmap

Fase 3 de `docs/plataforma-ml.md` — "Pipelines do GitHub Actions nos dois repositórios"; "Pronto quando: um merge na `main` chega à VPS sem eu entrar nela". Do doc: "SSH na VPS: `alembic upgrade head`, `docker compose pull && up -d`, registra deployments do Prefect".

## 4. Arquivos a criar ou alterar

| Caminho | Quem | Motivo |
| --- | --- | --- |
| `tests/infra/test_deploy_sh.py` (novo) | test-writer | Comportamento do script com `git`, `docker`, `date`, `tailscale`, `curl` falsos no `PATH` (casos 1 a 24 e 39 a 45) |
| `tests/infra/test_deploy_workflow.py` | test-writer | Casos do job `deploy` (25 a 38); o caso 7 do PR 37 passa a "`secrets.` só no job `deploy`" |
| `infra/scripts/deploy.sh` (novo, executável) | implementer | Script chamado pelo forced command |
| `.github/workflows/deploy.yml` | implementer | Job `deploy`; `harden-runner` como primeiro passo do `publish` |
| `.gitignore` | implementer | `/.deploy.lock` e `/.deploy/` (estado local e dumps do script na VPS) |
| `AGENTS.md` | implementer | Ver passo 7 |

`ci.yml` não muda: o passo `shellcheck infra/scripts/*.sh` já cobre o `deploy.sh`; o `actionlint` do PR 37 cobre o workflow.

### Contexto que o implementador precisa

- Estado esperado de `.github/workflows/deploy.yml` (PR 37): `name: deploy`; `on: push: branches: [main]`; `permissions: {}`; `concurrency: {group: deploy-production, cancel-in-progress: false}`; `env.TRIVY_IMAGE` igual ao `security.yml`; job `publish` com `permissions` `{contents: read, packages: write, id-token: write, attestations: write}` e `outputs` `jobs-digest`, `mlflow-digest` (`sha256:<64 hex>`).
- Compose de produção (PR 37): `jobs` e `prefect-worker` com `image: ghcr.io/${GHCR_OWNER:?...}/platform-jobs@${JOBS_IMAGE_DIGEST:?...}`; `mlflow` com `...platform-mlflow@${MLFLOW_IMAGE_DIGEST:?...}`; `prefect-server` com `image: prefecthq/prefect:<X.Y.Z>-python3.12@sha256:<64 hex>` (PR 30); sem `build:`. `jobs` está em `profiles: ["jobs"]`, então o `pull` usa `--profile jobs`. Portas em loopback (ADR 0003): saúde `127.0.0.1:8080`, MLflow `127.0.0.1:5000`, Prefect `127.0.0.1:4200`, Postgres `127.0.0.1:5432`. Healthchecks no compose: `health`, `postgres` (já na `main`), `mlflow` (PR 29, `/health`), `prefect-server` (PR 30, `/api/ready`) e `prefect-worker` (PR 34, `--with-healthcheck`, `/health` em `127.0.0.1:8080` dentro do container).
- `infra/mlflow/Dockerfile` (PR 29): uma linha `FROM ghcr.io/mlflow/mlflow:v<X.Y.Z>@sha256:<índice>`. O MLflow **não** migra banco existente na subida: com schema antigo, aborta com `Detected out-of-date database schema` e entra em laço de reinício. Procedimento do plano 29 (seção 5): `pg_dump` do banco `mlflow`, `stop mlflow`, `run --rm --no-deps mlflow sh -c 'exec mlflow db upgrade "$MLFLOW_BACKEND_STORE_URI"'`, `up`; **nunca** no `command` do serviço. O `mlflow db upgrade` só aceita a URL como argumento posicional: com esse `sh -c`, ela nunca aparece no argv nem no histórico do host, mas fica no argv do processo dentro do container enquanto o `db upgrade` roda (risco residual aceito, seção 9). O Dependabot só propõe patch do MLflow (`ignore` de minor e major no plano 29); minor e major chegam por PR manual, mas o deploy aplica o mesmo procedimento a qualquer mudança da linha `FROM`.
- Prefect server (plano 30): migra o próprio banco na subida; antes de trocar a imagem, `pg_dump` do banco `prefect`. API autenticada por `PREFECT_API_AUTH` (formato `admin:<senha>`) no `infra/.env`. Pelo código-fonte do Prefect (plano 30, risco "Endpoints fora da autenticação"), `GET /api/health` e `GET /api/ready` ficam fora da autenticação; o passo 0 do plano 30 confirma na versão fixada. O `deploy.sh` manda a credencial mesmo assim (D14): funciona nos dois casos.
- `infra/scripts/tailscale-serve.sh` (PR 03, já na `main`): `set -euo pipefail`; `tailscale serve reset`; uma linha `tailscale serve --bg --https=<porta> http://127.0.0.1:<porta>` por UI e `--tcp=5432`. Roda sem sudo porque `deploy` é operador do Tailscale (item 02).
- `python -m flows.deployments` (PR 33) registra os deployments de forma idempotente; o serviço `jobs` tem `PREFECT_API_URL: http://prefect-server:4200/api` e `PREFECT_API_AUTH_STRING: ${PREFECT_API_AUTH:?...}` (PR 34), então o registro usa a credencial do `infra/.env` da VPS, sem GitHub Secret.
- Item 38: `authorized_keys` com `restrict,from="100.64.0.0/10,fd7a:115c:a1e0::/48",command="/opt/platform/infra/scripts/deploy.sh"`; o argumento chega em `SSH_ORIGINAL_COMMAND`. Segredos do environment `production`: `TS_OAUTH_CLIENT_ID`, `TS_AUDIENCE`, `VPS_HOST` (IPv4 da tailnet), `VPS_SSH_KEY`, `VPS_KNOWN_HOSTS`. Nenhum `TS_OAUTH_SECRET`, nenhuma variável. ACL: `tag:ci` → `tag:platform` só `tcp:22`. Credencial federada restrita ao subject `repo:<owner>/<repo>:environment:production`. **O item 38 deixa a VPS num commit anterior a este PR**, com os digests de `jobs` e `mlflow` já no `infra/.env`: o `deploy.sh` ainda não existe lá quando o primeiro run do job `deploy` acontece (passo 9, bootstrap).
- `infra/.env` na VPS: linhas `CHAVE=valor` simples, com senhas. O script **nunca** faz `source`/`.` dele: lê só `JOBS_IMAGE_DIGEST`, `MLFLOW_IMAGE_DIGEST` e `PREFECT_API_AUTH` por `sed`, aceitando apenas `sha256:[0-9a-f]{64}` nos digests e `^[A-Za-z0-9._~-]+:[A-Za-z0-9._~-]+$` na credencial.
- Horários atuais dos jobs (`America/Sao_Paulo`): 06:30 `ingest_weather_forecast`, 06:45 `ingest_weather_observed`, 07:00 `ingest_ons_load`. Recriar o `prefect-worker` durante um flow mata o flow.
- `sshd` do Ubuntu aceita do cliente só `LANG`/`LC_*` (`AcceptEnv`), então o CI não consegue injetar `DEPLOY_STAGE`, `PLATFORM_DIR` nem outra variável.
- VPS: 1 vCPU, 2 GB de RAM (item 28b, padrão antes do item 31; 1 GB só se o usuário registrou dispensa), 2 GB de swap, 25 GB de disco. Nada de `build` na VPS.
- Regras de workflow (`.claude/rules/infra.md`): SHA + `# vX.Y.Z`; `permissions` mínimas por job; nenhum `${{ }}` em `run:` (valor por `env:`); `if:` em uma linha; `persist-credentials: false`; rodar `uv run zizmor .github/workflows/`.

## 5. Passos

1. (implementer, leitura) Resolver e validar SHAs como no plano S1, passo 4 (`gh api .../git/ref/tags/<tag>`, desreferenciar tag anotada, `compare/<tag>...<sha>` → `identical`) e **ler os inputs na ref fixada** (`gh api "repos/<owner>/<repo>/contents/action.yml?ref=<sha>" --jq .content | base64 -d` e o README na mesma ref):
   - `tailscale/github-action` (última release estável): confirmar os inputs de federação (esperado `oauth-client-id` e `audience`, com `id-token: write` no job), `tags`, `version` (fixar uma versão `X.Y.Z` do binário do Tailscale, nunca `latest`/`unstable`), `sha256sum` (**obrigatório**: o SHA-256 do pacote `tailscale_<X.Y.Z>_amd64.tgz`, conferido contra o arquivo `.sha256` publicado em `https://pkgs.tailscale.com/stable/`), `use-cache` (usar `false`) e `log-mode` (usar `quiet`; o input existe).
   - `step-security/harden-runner` (última release estável): input `egress-policy: audit`.
   Registrar no PR a tabela `action | tag | sha | inputs usados` e, para o binário do Tailscale, `versão | sha256 | URL conferida`.
2. (test-writer) `tests/infra/test_deploy_sh.py`: num `tmp_path`, executáveis falsos `git`, `docker`, `date`, `tailscale`, `curl` que gravam a linha de comando, o estágio (`DEPLOY_STAGE`) e, para `docker`, uma cópia das linhas de digest do `infra/.env` no momento da chamada, e saem com o código que o teste mandar por subcomando. O `curl` falso grava também o que recebeu no stdin. O `git` falso responde `git show <rev>:<caminho>` com o conteúdo que o teste preparar (versão anterior do compose e do Dockerfile do MLflow). O `docker` falso também tenta `flock -n "$PLATFORM_DIR/.deploy.lock" true` e registra se conseguiu (caso 7), e, para `exec -T postgres ... pg_dump`, escreve bytes no stdout. `PATH=<tmp>/bin:/usr/bin:/bin` (o `flock` real do util-linux continua disponível); `PLATFORM_DIR=<tmp>/platform` (sobrescreve o padrão `/opt/platform` do script) com `infra/.env` de exemplo (valores fictícios, nunca o `.env` real), cópia de `infra/scripts/`, um `infra/docker-compose.yml` mínimo com a linha `image: prefecthq/prefect:...` e um `infra/mlflow/Dockerfile` com a linha `FROM`. Rodar `bash infra/scripts/deploy.sh` com `SSH_ORIGINAL_COMMAND`. `pytest.mark.skipif(sys.platform == "win32")`. Casos 1 a 24 e 39 a 45. Em `tests/infra/test_deploy_workflow.py`, casos 25 a 38. Confirmar a falha (script inexistente; job `deploy` inexistente). Commit `test: add deploy script and deploy job tests`.
3. (implementer) `infra/scripts/deploy.sh` (mensagens e comentários em inglês):
   - **Estrutura:** corpo em funções, última linha `main "$@"; exit $?` (o script atualiza o próprio arquivo via `git checkout` enquanto roda). `PLATFORM_DIR="${PLATFORM_DIR:-/opt/platform}"` no topo (padrão de produção; os testes sobrescrevem; o `sshd` não deixa o cliente injetá-lo). `set -uo pipefail` e **tratamento de erro explícito por passo**: cada comando que pode falhar é chamado como `if ! <cmd>; then fail <etapa>; fi` (ou por um helper `step <etapa> <cmd...>` que faz isso). Não depender de `set -e` dentro de funções: o bash ignora o `-e` em funções chamadas em contexto de condição. Nunca `set -x`, nunca `eval`, nunca `source`/`.` de arquivo de dados.
   - **Validação:** `[[ "${SSH_ORIGINAL_COMMAND-}" =~ ^deploy\ [0-9a-f]{40}\ sha256:[0-9a-f]{64}\ sha256:[0-9a-f]{64}$ ]]` sobre a string inteira (rejeita quebra de linha, tab, espaço duplo, espaço no começo ou no fim). Falhou: stderr `invalid command` e saída 2, sem chamar `git` nem `docker`. Só depois de validar, separar as quatro palavras por expansão de parâmetro (`read -r` sobre a string já validada é aceitável).
   - **Janela:** `now="$(TZ=America/Sao_Paulo date +%H%M)"`; se `0600 <= now < 0800`, stderr `deploy window closed` e saída **75**, sem `git` nem `docker`.
   - **Trava (estágio inicial):** `exec 9>>"$PLATFORM_DIR/.deploy.lock"` e `flock -n 9`, senão saída 75 `another deploy is running`. O fd 9 fica aberto e é herdado pelo `exec` da reexecução.
   - **Git (estágio inicial):** `git fetch --quiet origin main`; `git merge-base --is-ancestor "$sha" origin/main` (senão 2); `git merge-base --is-ancestor HEAD "$sha"` (senão 2, `refusing to deploy an older commit`, D4); guardar estado anterior em `$PLATFORM_DIR/.deploy/previous.env` (criado pelo script, modo `600`): `PREV_HEAD=<git rev-parse HEAD>`, `PREV_JOBS_IMAGE_DIGEST=<lido do infra/.env>`, `PREV_MLFLOW_IMAGE_DIGEST=<idem>` (vazio se ausente ou fora do formato); `git checkout --quiet --detach "$sha"`.
   - **Reexecução:** `exec env DEPLOY_STAGE=apply bash "$PLATFORM_DIR/infra/scripts/deploy.sh"` (o `SSH_ORIGINAL_COMMAND`, o `PLATFORM_DIR` e o fd 9 seguem), para que o resto rode com o `deploy.sh` do commit implantado (D6).
   - **Estágio `apply`:** revalidar o comando (mesma regex) e a janela; **não reabrir** o arquivo de trava: conferir que o fd 9 herdado está aberto e travado com `flock -n 9` (relock do mesmo fd sucede); se o fd não existir ou o `flock` falhar, saída 2 `apply stage without deploy lock`, sem `docker`. Ler `.deploy/previous.env` com `sed` (nunca `source`), aceitando só SHA de 40 hex e digests no formato. Ler e validar `PREFECT_API_AUTH` do `infra/.env` (D14) **antes de qualquer `docker`**: ausente ou fora do formato → como falha da etapa 0 (restaurar `git`, sem `docker`).
   - **Detectar troca de versão (estágio `apply`, antes de qualquer `docker`):** comparar a primeira linha que casa com `image: prefecthq/prefect:` em `git show "$PREV_HEAD:infra/docker-compose.yml"` com a do `infra/docker-compose.yml` implantado (`PREFECT_CHANGED`), e a linha `FROM` de `git show "$PREV_HEAD:infra/mlflow/Dockerfile"` com a do `infra/mlflow/Dockerfile` implantado (`MLFLOW_CHANGED`). Arquivo ausente em `PREV_HEAD` conta como mudança (D12, D13).
   - **Digests novos em `infra/.env`:** trocar só as duas linhas (acrescentar se faltarem) por arquivo temporário no mesmo diretório + `mv`, preservando modo `600`; demais linhas byte a byte iguais e na mesma ordem.
   - **Sequência**, com `C=(docker compose -f infra/docker-compose.yml)` e `dump <banco>` = `"${C[@]}" exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d <banco> -Fc' > "$PLATFORM_DIR/.deploy/backups/<banco>-<sha>.dump"` (diretório criado com modo `700`, arquivo `600`; arquivo vazio conta como falha; o script mantém só os 3 dumps mais recentes de cada banco):
     0. `dump prefect`, se `PREFECT_CHANGED`; `dump mlflow`, se `MLFLOW_CHANGED` (os dois antes do `pull`, com os containers ainda na versão anterior)
     1. `"${C[@]}" --profile jobs pull`
     2. `"${C[@]}" run --rm jobs alembic upgrade head`
     2a. Só se `MLFLOW_CHANGED`: `"${C[@]}" stop mlflow` e `"${C[@]}" run --rm --no-deps mlflow sh -c 'exec mlflow db upgrade "$MLFLOW_BACKEND_STORE_URI"'`. A URL vem do ambiente do container: nunca aparece no argv nem no histórico do host; fica no argv do processo do container enquanto o `db upgrade` roda (risco residual aceito, seção 9)
     3. `"${C[@]}" up -d --remove-orphans --wait --wait-timeout 300` (espera `healthy` de todos os serviços com healthcheck, inclusive o `prefect-worker`)
     4. `infra/scripts/tailscale-serve.sh`
     5. `"${C[@]}" run --rm jobs python -m flows.deployments`
     6. saúde explícita em loopback, além do `--wait`: `curl -fsS --max-time 10 http://127.0.0.1:8080/health`, `http://127.0.0.1:5000/health` (MLflow) e, para o Prefect, `curl -fsS --max-time 10 -K - http://127.0.0.1:4200/api/health` com `user = "<PREFECT_API_AUTH>"` no stdin (D14); nunca `-u` nem a credencial em argumento
   - **Falha na validação da credencial ou nas etapas 0, 1 ou 2** (containers ainda na versão anterior): restaurar as duas linhas do `infra/.env` a partir de `PREV_*` (se já trocadas), `git checkout --quiet --detach "$PREV_HEAD"`, sem `up`; stderr `deploy failed at <etapa>`; saída 1.
   - **Falha na etapa 2a** (`stop` ou `mlflow db upgrade`): o schema do `mlflow` pode ter mudado em parte. Restaurar `infra/.env` e `git checkout --quiet --detach "$PREV_HEAD"`, **sem `up`** (o MLflow antigo sobre schema novo entraria em laço de reinício); stderr `mlflow db upgrade failed; mlflow is stopped; restore from .deploy/backups/mlflow-<sha>.dump`; saída 1. Os outros serviços continuam na versão anterior, no ar.
   - **Falha nas etapas 3 a 6** (rollback): se `PREV_JOBS_IMAGE_DIGEST` ou `PREV_MLFLOW_IMAGE_DIGEST` estiver vazio (sem digests anteriores registrados), **não** fazer `up`; stderr `no previous images recorded; manual intervention required`; saída 1. Se `MLFLOW_CHANGED` (o `db upgrade` já rodou), também não fazer rollback dos containers: stderr `mlflow schema was upgraded; not rolling back; manual intervention required`; saída 1. Caso contrário: `git checkout --quiet --detach "$PREV_HEAD"`, restaurar os digests anteriores no `infra/.env`, `"${C[@]}" up -d --remove-orphans --wait --wait-timeout 300`, reaplicar `infra/scripts/tailscale-serve.sh` em **best-effort** (falha vira aviso `tailscale serve reapply failed`, não muda o código de saída), imprimir `deploy failed <sha>, rolled back to <prev_head>` e sair 1. Nunca `alembic downgrade`. Se `PREFECT_CHANGED`, o rollback sobe a imagem anterior do Prefect sobre um banco que o server novo pode ter migrado: imprimir também o aviso `prefect image changed; check prefect-server logs; dump at .deploy/backups/prefect-<sha>.dump`.
   - **Sucesso:** `docker image prune -f --filter "until=168h"`; imprimir `deploy ok <sha> jobs=<digest> mlflow=<digest>`; saída 0. Nada de hostname, IP nem credencial na saída (vai para o log público).
   - Sem `docker login` (imagens públicas). Nenhuma senha nem credencial em argumento de comando no host.
4. (implementer) `.gitignore`: `/.deploy.lock` e `/.deploy/`.
5. (implementer) `deploy.yml`:
   - Primeiro passo do job `publish`: `step-security/harden-runner@<sha> # vX.Y.Z` com `egress-policy: audit`. **Não** pôr no job `deploy` (D9).
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

     Sem `actions/checkout` no `deploy` (o script vive na VPS). `timeout-minutes: 20` cobre o `pg_dump` e o `mlflow db upgrade` com a base pequena da Fase 3; se crescer, subir até 30 (caso 38).
6. (implementer) `shellcheck infra/scripts/deploy.sh`, `uv run zizmor .github/workflows/`, actionlint; rodar os critérios de pronto.
7. (implementer) `AGENTS.md`:
   - Trocar a linha interina do PR 37 ("Na VPS, depois do PR 37 e até o PR 39 [...] `pull` [...]") por: "Deploy: automático a cada merge na `main` (`.github/workflows/deploy.yml` → `infra/scripts/deploy.sh`). Fora da janela 06:00–08:00 BRT; dentro dela o `deploy.sh` sai com 75 e o usuário usa 'Re-run failed jobs' depois das 08:00. O deploy faz `pg_dump` antes de trocar a versão do Prefect server ou do MLflow e roda o `mlflow db upgrade` quando o `FROM` de `infra/mlflow/Dockerfile` muda (nunca no `command` do serviço). Nenhum comando manual na VPS muda produção."
   - Trocar "Merge de PR do Dependabot que muda `infra/` só chega à VPS pelo deploy manual do usuário (ADR 0004), fora da janela dos jobs" por "Merge de PR do Dependabot chega à VPS pelo deploy automático; faça o merge fora da janela 06:00–08:00 BRT. Do MLflow, o Dependabot só propõe patch; minor e major são PR manual (plano 29)".
   - Registrar `uv run pytest tests/infra/test_deploy_sh.py` (só Linux/CI).
8. Corpo do PR (inglês): tabela de actions e do binário do Tailscale; o aviso de bootstrap do passo 9 em destaque (o primeiro run do job `deploy` **vai falhar** e isso é esperado); lembrete dos dois PRs que vêm logo depois (seção 10): status do ADR 0004 e remoção da exceção em `.claude/rules/infra.md`.
9. **(usuário, logo depois do merge deste PR) Bootstrap do primeiro deploy.** O item 38 deixou a VPS num commit anterior a este PR, e a forced command aponta para `/opt/platform/infra/scripts/deploy.sh`, que só existe a partir deste PR. Por isso o primeiro run do job `deploy` falha (o `ssh` sai com código diferente de 0, tipicamente `127`, sem tocar em nada). Fora de 06:00–08:00 BRT:
   1. Na VPS, como `deploy`, só isto (sem `docker`, sem `build`, sem `up`):

      ```bash
      git -C /opt/platform fetch origin main && git -C /opt/platform checkout --detach origin/main
      git -C /opt/platform rev-parse HEAD
      ```

      → o SHA do merge deste PR (`S`). Os containers continuam na versão do item 38.
   2. No Actions, no run que falhou: "Re-run failed jobs" (reaproveita as saídas do `publish`). O segundo run vê `HEAD = S`, passa a checagem de fast-forward (`HEAD` é ancestral de `S`, porque é igual), registra `PREV_HEAD = S` e os digests do item 38 como anteriores (rollback possível), e faz o deploy completo.
   3. Conferir: `gh run view <id> --log | grep -E "deploy ok [0-9a-f]{40} jobs=sha256:"` → uma linha com `S`.

   Esse checkout é a **única** ação manual permitida entre o item 38 e o primeiro deploy automático bem-sucedido; ele não muda containers nem dados. A exceção do ADR 0004 termina nesse deploy (seção 10).

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
| `grep -nE '^\s*(source|\.)\s' infra/scripts/deploy.sh` | Nada |
| `grep -nE 'curl[^|]* -u ' infra/scripts/deploy.sh` | Nada |
| `gh pr checks` | Verde |
| Depois do merge e do bootstrap (passo 9), fora da janela: `gh run list --workflow deploy.yml --branch main --limit 1 --json conclusion -q '.[0].conclusion'` | `success` (no run reexecutado) |
| `gh run view <id> --log \| grep -E "deploy ok [0-9a-f]{40} jobs=sha256:"` | Uma linha, com o SHA do merge |
| `gh run view <id> --log \| grep -Ei "ts\.net\|100\.[0-9]+\.[0-9]+\.[0-9]+"` | Nada (sem hostname nem IP da tailnet no log público) |

## 7. Testes necessários

`sim`: validação do comando, janela, trava, fast-forward, ordem (dump antes de trocar versão, migrar antes de subir), rollback de git e containers, leitura segura do `.env`, credencial fora dos argumentos e "parar na primeira falha" são lógica testável com comandos falsos, e são o que evita deploy pela metade, perda de schema ou comando arbitrário na VPS; a forma do job (`environment`, permissões, segredos só nele, opções do SSH, binário do Tailscale conferido) é testável estaticamente.

## 8. Casos de teste

`deploy.sh` (`tests/infra/test_deploy_sh.py`; `S` = 40 hex válido, `P` = SHA anterior, `J`/`M` = `sha256:` + 64 hex novos, `J0`/`M0` = anteriores; horário falso `1000` salvo indicação; salvo indicação, a imagem do Prefect e o `FROM` do MLflow em `P` são iguais aos do commit implantado):

1. `SSH_ORIGINAL_COMMAND="deploy S J M"`, tudo verde → código 0; o log tem, nesta ordem: `git fetch`, `git merge-base --is-ancestor S origin/main`, `git merge-base --is-ancestor HEAD S`, `git rev-parse HEAD`, `git checkout --quiet --detach S`, (estágio `apply`) `docker compose ... --profile jobs pull`, `... run --rm jobs alembic upgrade head`, `... up -d --remove-orphans --wait ...`, `tailscale serve reset`, `... run --rm jobs python -m flows.deployments`, `curl ... 127.0.0.1:8080/health`, `curl ... 127.0.0.1:5000/health`, `curl ... 127.0.0.1:4200/api/health`, `docker image prune -f --filter until=168h`; stdout contém `deploy ok S jobs=J mlflow=M`; nenhum `pg_dump`, `stop mlflow` nem `db upgrade`.
2. Comandos inválidos → código 2, nenhum `git`/`docker` no log (parametrizado): `rm -rf /`; SHA curto; SHA com maiúsculas; digest com 63 hex; `sha512:...`; palavras a mais (`deploy S J M x`); palavras a menos (`deploy S J`); verbo diferente (`deploi S J M`); vazio; ausente.
3. Separadores ilegais → código 2, nenhum `git`/`docker`: `"deploy S J M\nid"` (quebra de linha), tab no lugar de espaço, espaço duplo, espaço no começo, espaço no fim.
4. Horário falso `0600`, `0700` e `0759` → código 75, stderr com `deploy window closed`, nenhum `git`/`docker`. `0559` e `0800` → segue.
5. Trava já tomada por outro processo (o teste segura `flock` no mesmo arquivo) → código 75, nenhum `docker`.
6. Estágio `apply` sem fd 9 herdado (o teste roda com `DEPLOY_STAGE=apply` e sem o fd) → código 2, stderr `apply stage without deploy lock`, nenhum `docker`.
7. A trava fica retida durante o estágio `apply`: em todas as chamadas do `docker` falso, a tentativa `flock -n` dele no arquivo de trava falha (registrado como `locked`).
8. `git merge-base --is-ancestor S origin/main` falhando → código 2; nenhum `checkout` nem `docker`.
9. `git merge-base --is-ancestor HEAD S` falhando → código 2; nenhum `checkout` nem `docker`.
10. Reexecução: depois do `checkout`, o script roda de novo com `DEPLOY_STAGE=apply` (o log registra os dois estágios); no estágio `apply`, nenhum `git fetch`; um comando inválido injetado só no estágio `apply` (o teste chama o script direto com fd 9 travado e `DEPLOY_STAGE=apply`) → código 2.
11. Antes do `checkout`, `.deploy/previous.env` contém `PREV_HEAD=P`, `PREV_JOBS_IMAGE_DIGEST=J0`, `PREV_MLFLOW_IMAGE_DIGEST=M0`, modo `600`.
12. `infra/.env` com outras linhas e `J0`/`M0` → depois do sucesso, as duas linhas têm `J` e `M`, as outras linhas idênticas e na mesma ordem, modo `600`. Sem as linhas de digest → elas são acrescentadas e o resto fica intacto.
13. `infra/.env` contendo a linha `X=$(touch pwned)` (e `PWNED_DIR` apontando para o `tmp_path`) → nenhum arquivo `pwned` é criado em lugar nenhum do `tmp_path`; a linha continua no `infra/.env` byte a byte.
14. No momento de cada chamada `docker compose` do deploy, o `infra/.env` tem `JOBS_IMAGE_DIGEST=J` e `MLFLOW_IMAGE_DIGEST=M`.
15. `docker` falso falhando no `pull` → código 1; nenhum `alembic`; `infra/.env` volta a `J0`/`M0`; último `git checkout` registrado é `--detach P`; nenhum `up`.
16. `docker` falso falhando no `alembic upgrade head` → código 1; nenhum `up`; `infra/.env` volta a `J0`/`M0`; `git checkout --detach P`.
17. `docker` falso falhando no primeiro `up -d` → código 1; depois da falha, `git checkout --detach P` e um segundo `up -d`; no momento desse segundo `up`, `infra/.env` tem `J0`/`M0`; `tailscale serve reset` chamado de novo depois do segundo `up`; stdout contém `rolled back to P`; nenhum `alembic downgrade`.
18. Cada um dos três `curl` falhando (parametrizado) → mesmo comportamento do caso 17.
19. `tailscale` falso falhando no deploy → rollback como no caso 17; `flows.deployments` não foi chamado. Com o `tailscale` falhando também no rollback → código continua 1, stderr com `tailscale serve reapply failed`, o segundo `up` aconteceu.
20. `flows.deployments` falhando → rollback como no caso 17.
21. Sem digests anteriores (`infra/.env` sem as linhas, ou com valor fora do formato) e falha no `up -d` → código 1, stderr `no previous images recorded; manual intervention required`, **nenhum** segundo `up`.
22. Nenhum comando registrado contém `docker login`, `alembic downgrade`, `--password`, `-p ` ou `-u `; o texto do script não contém `set -x`, `eval`, nem `source`/`.` de arquivo.
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

39. Imagem do Prefect diferente entre `P` e `S` (o `git show P:infra/docker-compose.yml` falso devolve `prefecthq/prefect:3.9.0-...`, o arquivo implantado tem `3.9.1-...`), tudo verde → código 0; um `exec -T postgres ... pg_dump ... -d prefect` antes do `pull`; o arquivo `.deploy/backups/prefect-S.dump` existe, não vazio, modo `600`; nenhum `pg_dump` do `mlflow`.
40. `FROM` do MLflow diferente entre `P` e `S`, tudo verde → código 0; nesta ordem: `pg_dump ... -d mlflow` (antes do `pull`), `pull`, `alembic upgrade head`, `stop mlflow`, `run --rm --no-deps mlflow sh -c 'exec mlflow db upgrade "$MLFLOW_BACKEND_STORE_URI"'`, `up -d`; nenhum argumento de comando registrado no host contém `postgresql` (a URL só é expandida dentro do container).
41. `pg_dump` falhando (ou devolvendo vazio) com o Prefect ou o MLflow mudando → código 1; nenhum `pull` nem `up`; `infra/.env` volta a `J0`/`M0`; `git checkout --detach P`.
42. `mlflow db upgrade` falhando → código 1; stderr contém `mlflow db upgrade failed`; nenhum `up` depois da falha; `infra/.env` volta a `J0`/`M0`; `git checkout --detach P`.
43. `FROM` do MLflow mudando, `db upgrade` ok e falha no primeiro `up -d` → código 1; stderr contém `mlflow schema was upgraded; not rolling back`; nenhum segundo `up`.
44. Imagem do Prefect mudando e falha num `curl` → rollback como no caso 17, e stderr contém `prefect image changed`.
45. Credencial do Prefect: o `curl` da 4200 recebe no stdin uma linha `user = "<valor de PREFECT_API_AUTH do infra/.env de exemplo>"`, e nenhum argumento registrado de nenhum comando contém esse valor nem a senha. `PREFECT_API_AUTH` ausente ou fora do formato `usuario:senha` URL-safe → código 1 **antes do passo 0** (nenhum `pg_dump` e nenhuma chamada `docker` registrada), stderr `PREFECT_API_AUTH missing or invalid` (sem o valor), e último `git checkout` registrado `--detach P`.

## 9. Riscos e perguntas em aberto

- **Não verificado nesta revisão:** se `docker compose up --wait --wait-timeout` existe na versão da VPS (o item 38 anota `docker compose version`); o valor do `sha256sum` (o passo 1 confere no site de pacotes do Tailscale). A isenção de `/api/health` da autenticação vem do código-fonte do Prefect e é confirmada no passo 0 do plano 30; o script manda a credencial de qualquer forma.
- **Bootstrap (passo 9):** o primeiro run do job `deploy` falha por desenho (o `deploy.sh` ainda não existe na VPS). Sem o checkout de bootstrap, nenhum deploy automático roda nunca. Se o usuário esquecer, o próximo merge falha do mesmo jeito; a correção é sempre o mesmo checkout seguido de "Re-run failed jobs".
- **URL do MLflow no argv do container (risco residual aceito):** o `mlflow db upgrade` só aceita a URL como argumento posicional. Com `sh -c 'exec mlflow db upgrade "$MLFLOW_BACKEND_STORE_URI"'`, a senha nunca aparece no argv nem no histórico do host, mas fica visível no `/proc/<pid>/cmdline` do processo dentro do container enquanto o upgrade roda (segundos). Aceito porque o processo é curto, a VPS tem um único usuário e quem pode ler processos de container já está no grupo `docker` (equivalente a root).
- Rollback e migração: o rollback reverte commit e containers, nunca a migração. Uma migração que quebra a versão anterior deixa a versão antiga rodando sobre o schema novo. Regra para PRs com migração (a registrar no ADR): migrações compatíveis com a versão anterior (expandir antes de contrair). Reverter na `main` um commit que trouxe migração **não** desfaz a migração e faz o `alembic upgrade head` falhar ("Can't locate revision"): corrija para frente, com migração nova.
- **Schema do MLflow e do Prefect:** o `mlflow db upgrade` e a migração automática do Prefect não têm volta pelo script. Por isso o `pg_dump` vem antes e, quando o MLflow mudou, o script não sobe a versão antiga sobre o schema novo (D12). Restore de um dump é intervenção manual de emergência, registrada; o procedimento testado de restore é do PR 57. Faça o merge de PR que troca a versão do MLflow ou do Prefect fora da janela e acompanhe o log.
- Depois de um rollback, a VPS fica inteira (commit e containers) em `P`. O próximo merge passa pela checagem fast-forward, porque `P` é ancestral de qualquer commit novo da `main`.
- `git checkout --detach` apaga mudanças locais em arquivos versionados na VPS (o `.env` está no `.gitignore` e fica). Depois deste PR, ninguém muda arquivo versionado na VPS.
- `tailscale serve reset` derruba por um instante as conexões às UIs; aceitável no deploy.
- Memória: `pull` + `up -d` recriam containers e, por alguns segundos, versões antiga e nova coexistem; com 2 GB e o swap do item 02 cabe, mas pode usar swap por instantes.
- Disco: os dumps ficam em `.deploy/backups/` (3 por banco). Os bancos `mlflow` e `prefect` são pequenos na Fase 3; o vigia de disco (PR 56) cobre crescimento.
- `docker image prune -f --filter "until=168h"` filtra pela **data de criação** da imagem (o `Created` do build no CI), não pela data do `pull`: uma imagem sem container, criada há mais de 7 dias, pode ser removida mesmo que tenha sido puxada hoje. Isso não quebra o rollback: o `up -d` puxa do GHCR (público) a imagem que faltar.
- A janela 06:00–08:00 é fixa no script. Os PRs 46 (07:30) e 54 (08:00) das Fases 4 e 5 vão exigir ampliá-la; não antecipe aqui.
- Exit 75 aparece como falha vermelha no Actions. É intencional: o usuário reexecuta depois das 08:00 ("Re-run failed jobs" reaproveita as saídas do `publish` já concluído). Alternativa rejeitada: `sleep` no runner até a janela abrir.
- Pendência fora deste PR: `.claude/rules/infra.md` diz "Exceção registrada até o PR 39 (ADR 0004): o usuário atualiza a VPS à mão [...]". Remover essa frase exige PR próprio com autorização do usuário (o implementer não edita `.claude/`), logo depois do primeiro deploy automático bem-sucedido (seção 10). O item 40 depende dele.

### Decisões (aceitas pelo usuário)

- D1. Saúde: `up --wait` (healthchecks do compose: `health`, `postgres`, `mlflow`, `prefect-server` e `prefect-worker`) **e** `curl` explícito em loopback para `:8080/health`, `:5000/health` (MLflow) e `:4200/api/health` (Prefect, D14), com resultado na saída do SSH. ACL do `tag:ci` só na 22.
- D2. Environment `production` sem required reviewers (item 38, D3).
- D3. Janela: recusar entre 06:00 e 08:00 BRT com código 75 e reexecução manual.
- D4. Só avança (fast-forward): recusar SHA mais antigo que o `HEAD` implantado. Rollback planejado = `git revert` na `main`.
- D5. Rollback automático de **commit e containers** (HEAD e digests anteriores), nunca de migração; sem rollback se não houver digests anteriores.
- D6. Reexecutar o `deploy.sh` do commit implantado depois do checkout, herdando a trava (fd 9).
- D7. Concorrência: `concurrency` do workflow (o GitHub mantém um run pendente e cancela o pendente mais antigo; o mais novo contém o mais antigo) **e** `flock` na VPS.
- D8. Consulta de flow runs em execução na API do Prefect antes de recriar o worker: **não neste PR**; a janela cobre os horários agendados. Reavaliar quando houver flows longos fora da janela.
- D9. `harden-runner` **só no `publish`**. Motivo: a telemetria de rede do job vai para a StepSecurity e, em repo público, poderia expor o destino do SSH (IP da tailnet). É um desvio do texto do ADR 0006 ("`harden-runner` em modo `audit`, quando o deploy por SSH entrar"), a registrar no ADR "Pipeline de entrega".
- D10. Tailscale no CI por **federação OIDC** (item 38, D2), com `version` fixada, `sha256sum` obrigatório, `use-cache: false` e `log-mode: quiet`.
- D11. `-o AddressFamily=inet` no SSH, casando com `VPS_HOST` em IPv4 (item 38, D6).
- D12. **Troca de versão do MLflow** (linha `FROM` de `infra/mlflow/Dockerfile` diferente de `PREV_HEAD`): o procedimento do plano 29 dentro do deploy: `pg_dump` do `mlflow` antes do `pull`, `stop mlflow` e `mlflow db upgrade` por `run --rm --no-deps` depois do `alembic`, então `up`. Nunca no `command` do serviço. A URL nunca no argv nem no histórico do host; presente no argv do processo do container durante o upgrade (risco residual aceito). Sem rollback de containers depois de um `db upgrade` bem-sucedido. O Dependabot só propõe patch do MLflow (plano 29, D10); minor e major são PR manual, mergeado fora da janela.
- D13. **Troca de imagem do Prefect server** (linha `image: prefecthq/prefect:` diferente de `PREV_HEAD`): `pg_dump` do `prefect` antes do `pull` (plano 30, "Troca de imagem do Prefect"); a migração continua sendo a do próprio server na subida.
- D14. **Saúde do Prefect com credencial:** `PREFECT_API_AUTH` lida do `infra/.env` por `sed`, validada antes de qualquer `docker` e passada ao `curl` pelo stdin (`-K -`), nunca em argumento nem no log. Funciona com ou sem isenção de `/api/health`.
- D15. **Bootstrap do primeiro deploy** (passo 9): um único `git fetch` + `git checkout --detach origin/main` manual na VPS, sem `docker`, seguido de "Re-run failed jobs". Alternativas rejeitadas: o CI copiar o `deploy.sh` pelo SSH (a chave só executa a forced command) e o item 38 fazer checkout de um commit que ainda não existe.

## 10. Decisões que exigem ADR

**Sim.** O ADR "Pipeline de entrega" (plano 37, seção 10), mergeado antes do PR 37, precisa cobrir D1 a D15 daqui, inclusive:

- o desvio do ADR 0006 sobre o `harden-runner` (D9);
- a regra de migrações compatíveis com a versão anterior, e o tratamento do schema do MLflow e do Prefect no deploy (D12, D13);
- que ele **substitui o ADR 0004 no que toca ao deploy**, e que a exceção do ADR 0004 **termina no primeiro deploy automático bem-sucedido** depois do merge deste PR 39, com um único checkout manual de bootstrap permitido entre o item 38 e esse deploy (D15).

A mudança de status do ADR 0004 (agendador → `superseded` pelo ADR "Agendamento e execução pelo Prefect"; deploy → `superseded` pelo ADR "Pipeline de entrega") vai num **único PR só de `docs/**` logo depois do primeiro deploy automático bem-sucedido**, aberto junto do PR que remove a exceção de `.claude/rules/infra.md`. Este último não é só `docs/**`: passa pelo `code-reviewer` e pelo `pr-reviewer`. Nenhum agente edita ADR.
