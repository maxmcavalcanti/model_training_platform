# 39 — Deploy automático: GitHub Actions → Tailscale → SSH → `deploy.sh`

> Executa: agente. Depende de: 37 e do item manual 38 concluído. Branch sugerida: `ci/deploy-ssh`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Depois de publicar as imagens, o workflow entra na tailnet, faz SSH na VPS e roda `infra/scripts/deploy.sh <sha>`, que atualiza o repo, migra, sobe os serviços, reaplica o `tailscale serve` e registra os deployments do Prefect.
Fecha "merge na `main` é a única forma de mudar produção".

## 2. Fora do escopo

- Rollback automático (o rollback é reverter o commit na `main`, que dispara um novo deploy).
- Deploy do repo `models` (item 40).

## 3. Fase do roadmap

Fase 3 — "Pipelines do GitHub Actions"; "Pronto quando: um merge na `main` chega à VPS sem eu entrar nela".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/scripts/deploy.sh` | Script chamado pela chave SSH restrita (forced command) |
| `.github/workflows/deploy.yml` | Job `deploy` depois de `images`, no environment `production` |
| `.github/workflows/ci.yml` | Confirmar que o `shellcheck infra/scripts/*.sh` do PR 03 cobre o script novo |
| `tests/infra/test_deploy_sh.py` | Testes do script com `git`, `docker` e `tailscale` falsos no `PATH` (test-writer) |

Do doc: "SSH na VPS: `alembic upgrade head`, `docker compose pull && up -d`, registra deployments do Prefect". Do item 38: a chave do CI está em `authorized_keys` com `restrict,command="/opt/platform/infra/scripts/deploy.sh"`; portanto o argumento chega em `SSH_ORIGINAL_COMMAND`, não em `$1`.

## 5. Passos

1. (test-writer) `tests/infra/test_deploy_sh.py`: cria num `tmp_path` executáveis falsos `git`, `docker` e `tailscale` que só gravam a linha de comando num arquivo de log (e saem com o código que o teste mandar), põe esse diretório no início do `PATH`, define `PLATFORM_DIR=<tmp>` e roda `bash infra/scripts/deploy.sh` com `SSH_ORIGINAL_COMMAND`. Pule no Windows (`skipif(sys.platform == "win32")`). Casos na seção 8. Confirme falha porque o script não existe. Commit `test: add deploy script tests`.
2. (implementer) `infra/scripts/deploy.sh`:
   - `set -euo pipefail`; `cd "${PLATFORM_DIR:-/opt/platform}"`.
   - `SHA="${SSH_ORIGINAL_COMMAND:-${1:-}}"`; aceita só `^[0-9a-f]{40}$`; senão sai com 2 e mensagem.
   - `git fetch --quiet origin main` e `git checkout --quiet --detach "$SHA"`.
   - `export IMAGE_TAG="$SHA"`; `C="docker compose -f infra/docker-compose.yml"`.
   - Na ordem: `$C pull`; `$C run --rm jobs alembic upgrade head`; `$C up -d --remove-orphans`; `infra/scripts/tailscale-serve.sh` (PR 03; roda sem sudo porque `deploy` é operador do Tailscale, item 02); `$C run --rm jobs python -m flows.deployments`.
   - Sem `docker login`: as imagens do GHCR são públicas (P2 resolvida).
   - Grava `IMAGE_TAG=$SHA` no `infra/.env` (substituindo a linha), para um reboot subir a mesma versão.
   - No fim, imprime `deploy ok <sha>`.
3. `deploy.yml`, job `deploy`: `needs: images`, `environment: production`, passos `tailscale/github-action` (major atual, com `oauth-client-id`, `oauth-secret`, `tags: tag:ci`), gravar `VPS_SSH_KEY` em arquivo `600` e `VPS_KNOWN_HOSTS` em `~/.ssh/known_hosts`, `ssh -i <arquivo> deploy@${{ secrets.VPS_HOST }} "${{ github.sha }}"`, e checagem final `curl -fsS https://${{ vars.TS_HOSTNAME }}:8080/health` (o runner está na tailnet pelo `tailscale/github-action`; a ACL do item 38 libera `tag:ci` só para as portas 22 e 8080; `TS_HOSTNAME` é variável do environment, não segredo).
4. `ci.yml`: o passo `shellcheck infra/scripts/*.sh` já existe desde o PR 03; confirme que pega o `deploy.sh`.
5. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/test_deploy_sh.py` (Linux/macOS/CI) | Todos passam |
| `shellcheck infra/scripts/deploy.sh` | Sem saída |
| `actionlint` (PR 37) | Sem saída |
| `gh pr checks` | Verde |
| Depois do merge: `gh run list --workflow deploy.yml --limit 1` | `completed success`, e o log do job `deploy` termina com `deploy ok <sha>` |

## 7. Testes necessários

`sim`: a ordem (migrar antes de subir), a validação do argumento e "parar na primeira falha" são testáveis com comandos falsos e são o que evita um deploy pela metade.

## 8. Casos de teste

1. `SSH_ORIGINAL_COMMAND` com SHA válido → o log tem, nesta ordem: `git fetch`, `git checkout --detach <sha>`, `docker compose ... pull`, `... run --rm jobs alembic upgrade head`, `... up -d --remove-orphans`, `tailscale serve reset` (chamado pelo `tailscale-serve.sh`), `... run --rm jobs python -m flows.deployments`; saída contém `deploy ok <sha>`; código 0.
2. `SSH_ORIGINAL_COMMAND="rm -rf /"` → código 2; nenhum comando `git`/`docker` foi chamado.
3. SHA curto (`abc123`) → código 2.
4. `docker` falso falhando no `alembic upgrade head` → código diferente de 0; `up -d` **não** foi chamado.
5. `IMAGE_TAG` exportado para os comandos `docker` é o SHA (o `docker` falso registra o ambiente).
6. `infra/.env` com `IMAGE_TAG=main` e outras linhas → depois do script, `IMAGE_TAG=<sha>` e as outras linhas intactas.
7. `tailscale` falso falhando → código diferente de 0; `flows.deployments` **não** foi chamado.
8. Nenhum comando registrado no log contém `docker login`.

## 9. Riscos e perguntas em aberto

- Migração que quebra a versão anterior: como o `up -d` vem depois do `alembic upgrade`, por alguns segundos a versão antiga roda com o schema novo. Migrações devem ser compatíveis para trás; vale como regra para os PRs com migração.
- `git checkout --detach` na VPS: o clone da VPS deixa de ter alterações locais (qualquer arquivo mexido à mão seria perdido; o `.env` está no `.gitignore` e fica).
- Coerência com a rede só Tailscale: o runner entra na tailnet (`tailscale/github-action`, `tag:ci`) e faz SSH pelo OpenSSH da VPS no IP do Tailscale; a porta 22 pública está fechada (item 02). A restrição `command=` do `authorized_keys` só vale porque o recurso "Tailscale SSH" (`tailscale up --ssh`) **não** está ligado: com ele, o tailscaled atende a 22 da tailnet e ignora o `authorized_keys`. Se o usuário quiser ligá-lo, este PR e o item 38 precisam de replanejamento (ADR de rede).
- `tailscale serve reset` no deploy derruba por um instante as conexões às UIs. Aceitável num deploy; se incomodar, o script pode comparar com `tailscale serve status --json` antes de resetar.
- Memória: `pull` + `up -d` recriam containers e, por alguns segundos, versões antiga e nova podem coexistir. Com 1 GB isso pode usar swap; a medição do item 35 diz se é problema.

## 10. Decisões que exigem ADR

- Atualizar o ADR "Operação interina" (P6) para `superseded`: o deploy manual acaba aqui.
