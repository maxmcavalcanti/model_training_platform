# ADR-0007: Pipeline de entrega

**Status:** Aceito **Data:** 2026-11-09

## Contexto

- Na Fase 3, um merge na `main` deve chegar à VPS sem que o mantenedor entre nela. O ADR 0004 permite deploy manual por SSH apenas como exceção, até o PR 39.
- O ADR 0006 exige ADR próprio para o Trivy da imagem com attestation (junto da publicação no GHCR) e para o primeiro workflow que usa segredos, e cita o `harden-runner` em modo `audit` quando o deploy por SSH entrar.
- O repositório é público: logs de workflow e a telemetria do `harden-runner` são visíveis a qualquer pessoa. Endereços e nomes do tailnet não são controle de segurança (o tailnet é inalcançável de fora), mas não devem ser publicados sem necessidade.
- A rede é Tailscale-only (ADR 0003): nenhuma porta pública, e o CI precisa entrar no tailnet para chegar à VPS.
- A VPS tem um único usuário de deploy (`deploy`, no grupo `docker`, equivalente a root no host). Quem controla o `deploy.sh` que roda na VPS tem root nela.
- Este ADR foi escrito pela skill `generate-adr` a pedido do usuário (2026-11-09), com revisão de segurança por agente (Opus) antes de gravar.

## Decisão

1. **Workflow `deploy.yml`** com dois jobs. `publish` constrói e publica no GHCR por digest (tag `:<sha>`), com build pela CLI do docker, varredura Trivy bloqueante antes do login e do push, usando a mesma imagem fixada por digest do `security.yml`, e attestation de proveniência com `actions/attest` (permissões mínimas). Os pacotes são públicos (a visibilidade pública é irreversível). `deploy` entra na VPS por SSH. Todas as actions ficam fixadas por SHA, `permissions: {}` no topo, `persist-credentials: false`, sem `pull_request_target`, sem `workflow_run` e sem `workflow_dispatch`. A tag `:<sha>` é mutável; só o digest é usado para implantar.
2. **Compose de produção por digest.** `JOBS_IMAGE_DIGEST`, `MLFLOW_IMAGE_DIGEST` e `GHCR_OWNER` vêm do ambiente. O `build:` sai do compose de produção e vive num override usado no CI e localmente. A VPS faz `pull`, não build.
3. **Acesso do CI à VPS** pelo Tailscale com federação de identidade (OIDC), sem segredo do Tailscale: o job pede `id-token: write`, e a identidade federada só aceita o subject `repo:<owner>/<repo>:environment:production` **e** a claim `job_workflow_ref` igual a `<owner>/<repo>/.github/workflows/deploy.yml@refs/heads/main`, para que outro workflow em `main` que declare o mesmo environment não receba a identidade. O nó entra com `tag:ci`. A ACL libera `tag:ci` só para a porta 22 da VPS, com bloco `tests` (incluindo negação para outro dispositivo), e as regras amplas com `src` `*` são removidas.
4. **SSH com chave restrita.** A entrada em `authorized_keys` usa `restrict`, `from=` com `100.64.0.0/10` e `fd7a:115c:a1e0::/48` (o `from=` só barra origem fora do tailnet; quem limita os nós é a ACL) e `command=` fixo para o `deploy.sh`. A host key é conferida fora de banda antes de virar segredo; o cliente usa `StrictHostKeyChecking=yes` e `-o AddressFamily=inet`. A action do Tailscale usa `use-cache: false`, `version` e `sha256sum` fixados e `log-mode: quiet`.
5. **`deploy.sh`** valida `SSH_ORIGINAL_COMMAND` inteiro por regex ancorada (`deploy <sha40> sha256:<64> sha256:<64>`); o lock (`flock`) é herdado entre as etapas e nunca reaberto; aceita só fast-forward da `main`; recusa deploy entre 06:00 e 08:00 BRT; nunca carrega o `infra/.env` com `source`.
   - **Verificação de proveniência antes do `pull`.** Para cada digest, o script verifica a attestation (`gh attestation verify` ou `cosign verify-attestation` equivalente, com binário fixado por versão e sha256 na VPS), exigindo o repositório, o workflow `deploy.yml`, `--source-ref refs/heads/main`, `--source-digest <sha>` e `--deny-self-hosted-runners`. Digest sem attestation válida do commit implantado falha a etapa 0. Isso impede que uma imagem publicada por outra branch, ou um digest antigo e vulnerável, seja implantado junto com um SHA novo.
   - **Ordem:** verificação, `pull` por digest, `pg_dump` do banco da plataforma quando `alembic current` difere de `heads`, `alembic upgrade head`, `up -d --wait` e verificação de saúde em loopback. Migrações precisam ser compatíveis com a versão anterior; não há downgrade, e reverter um commit com migração não desfaz a migração (corrige-se para a frente).
   - **Rollback.** Se algo falhar depois da migração, o script volta ao commit e aos digests anteriores. Exceções: quando o `mlflow db upgrade` rodou, ou quando não há digests anteriores registrados, o script para e exige intervenção manual pelo procedimento de emergência (item 12).
   - **Trilha de auditoria.** Cada execução acrescenta uma linha a `.deploy/history.log` (modo 600) com data UTC, SHA, digests, etapa final e código de saída.
6. **Segredos** existem só no environment `production`, restrito à `main`; não há segredo no nível do repositório e variáveis não guardam nada sensível, porque o log de um repositório público é público. `ci.yml` e `security.yml` continuam sem segredos. Runs do Dependabot recebem token somente leitura e não veem segredos de environment, então o deploy falha fechado.
7. **Desvio do ADR 0006:** o `harden-runner` roda em modo `audit` apenas no job `publish`. O job `deploy` não faz checkout nem executa código do repositório; seus únicos passos são a action do Tailscale fixada e o `ssh`. A telemetria do `harden-runner` em repositório público é pública para a camada comunitária e listaria domínios e IPs contactados; a exclusão é minimização de informação, não controle de segurança. O `harden-runner` é uma action de terceiros a mais no job com `packages: write` e `id-token: write`; o risco é aceito.
8. **Fim da exceção do ADR 0004.** Este ADR substitui o ADR 0004 na parte de deploy a partir do primeiro deploy automático bem-sucedido. Depois do merge do PR 39 há exatamente um passo manual de bootstrap, fora de 06:00–08:00: `git fetch origin main` e `git checkout --detach origin/main` na VPS, sem docker, seguido de "Re-run failed jobs"; o primeiro run do `deploy` falha de propósito porque o `deploy.sh` ainda não existe na VPS. Antes do re-run, o usuário confere que `git rev-parse HEAD` na VPS é o SHA do merge do PR 39 mostrado no GitHub (ou de um merge posterior já revisado) e reexecuta o run desse SHA; o fast-forward recusa a reexecução de um run antigo. A mudança de status do ADR 0004 vai num PR só de `docs/**` depois desse deploy, junto com o PR que remove a exceção de `.claude/rules/infra.md`.
9. **Upgrades de schema.** O MLflow não migra um banco existente ao subir: `mlflow db upgrade` é manual, depois de `pg_dump`, nunca dentro do comando do serviço; o Dependabot propõe apenas atualizações de patch do MLflow. Antes de trocar a imagem do Prefect, faz-se `pg_dump` do banco `prefect` (o Prefect migra ao subir). Os dumps ficam em diretório com modo 700 e arquivos 600, no máximo 3 por banco.
10. **Critério de saída da fase "só avisa" (S5).** Os checks do `security.yml` e do `ci.yml` só viram obrigatórios na branch protection depois de duas semanas sem achados HIGH ou CRITICAL, e ficam ativos **antes do PR 37**, que já publica imagens, e do primeiro deploy automático.
11. **Âncora de confiança.** Merge na `main` equivale a root na VPS. O environment `production` não tem required reviewers e a `main` não exige revisão aprovada (um único mantenedor). Os agentes de IA usam o `gh` autenticado do mantenedor e nada impede um `gh pr merge`; o risco só é aceito com estas condições, verificadas antes do primeiro deploy automático: (a) branch protection com os checks required e "Do not allow bypassing" ativa; (b) as credenciais do GitHub disponíveis aos agentes não podem fazer merge na `main` nem aprovar deployment (token fine-grained ou conta separada), **ou**, se isso não for viável, o environment `production` passa a ter o mantenedor como required reviewer. A escolha entre as duas opções é do usuário e fica registrada no plano S6 (a criar) ou no plano 38.
12. **Intervenção manual de emergência.** Intervir na VPS só em emergência (restore de dump, deploy travado), pelo usuário com a chave pessoal, registrando depois numa issue os comandos e o motivo; nunca por agente.
13. **Rotação e revogação.** A chave `VPS_SSH_KEY` é girada a cada 12 meses e imediatamente em caso de suspeita de vazamento; a revogação do CI é remover a linha do `authorized_keys` e desativar a credencial federada no Tailscale. Até o PR 55 (alertas), o aviso de deploy falho é o e-mail de falha do Actions.

## Consequências

**Positivo:**

- Merge na `main` volta a ser a única forma de mudar produção, com imagem imutável por digest, proveniência verificada na VPS antes do `pull` e rollback automático nos casos cobertos.
- Nenhum segredo de longa duração do Tailscale, nenhum segredo no nível do repositório e nenhuma porta pública.
- A chave SSH só executa o `deploy.sh`, e apenas com argumentos validados.
- Trilha de auditoria local e backup antes de migração.

**Negativo:**

- Um passo manual de bootstrap, e o primeiro run do `deploy` falha de propósito.
- A segurança de toda a cadeia depende de quem pode fazer merge na `main` (item 11); sem a restrição às credenciais dos agentes ou um required reviewer, o risco permanece.
- No `mlflow db upgrade` a senha fica no argv do processo do container enquanto ele roda (risco residual aceito: processo curto, VPS de um usuário).
- Tornar o pacote público é irreversível.
- O rollback depois de um `mlflow db upgrade` bem-sucedido, de uma mudança de imagem do Prefect ou sem digests anteriores é manual, a partir do `pg_dump`.
- A VPS precisa de um verificador de attestation instalado e fixado.
- Sem `harden-runner` no `deploy`, não há telemetria de rede nesse job.

## Alternativas consideradas

**`harden-runner` também no job `deploy`:** telemetria de rede no deploy. Rejeitado porque a telemetria de repositório público lista os destinos contactados e o job não executa código do repositório.

**OAuth client com segredo do Tailscale:** credencial de longa duração no environment. Rejeitado porque a federação OIDC elimina o segredo.

**Tags de imagem em vez de digest:** mais simples de ler. Rejeitado porque tags podem ser redirecionadas, como no incidente do `trivy-action` (ADR 0006).

**Build na VPS:** continua o modelo interino. Rejeitado porque a VPS tem 1 vCPU e pouca RAM, e a imagem não seria a mesma que o CI varreu e atestou.

**Attestation só para auditoria, sem verificação no deploy:** mais simples. Rejeitado porque um digest de outra branch ou antigo poderia ser implantado por quem controlasse o comando de deploy.

**`trivy-action`:** Rejeitado pelo mesmo motivo do ADR 0006 (tags redirecionadas em 2026-03-19); o Trivy roda por imagem fixada por digest.
