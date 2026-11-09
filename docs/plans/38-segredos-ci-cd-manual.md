# 38 — Acessos e segredos do deploy automático; VPS passa a puxar imagens (manual)

> Executa: **usuário**. Depende de: 37 mergeado (primeiro run do `deploy.yml` com `success` e os dois digests no log e no summary), S5 concluído (`docs/plans/S5-settings-seguranca-manual.md`) e o ADR "Pipeline de entrega" mergeado (plano 37, seção 10). Precisa estar pronto antes do merge do PR 39.
> Fase do roadmap: Fase 3 de `docs/plataforma-ml.md` — "Pipelines do GitHub Actions nos dois repositórios" (parte que exige contas, chaves e segredos).
> Revisado em 2026-11-08 contra a `main` em `05c32c9`, com as correções da revisão independente (aceitas pelo usuário): federação de identidade (OIDC) no lugar do segredo do OAuth, ACL sem regra `*` alcançando a VPS, `from=` com IPv4 e IPv6 da tailnet, `VPS_HOST` exato no `known_hosts`, aviso de irreversibilidade do pacote público. Revisão final (mesmo dia): este é o último deploy manual **completo**; depois dele, a única ação manual permitida até o primeiro deploy automático bem-sucedido é o checkout de bootstrap do plano 39, passo 9.

## Por que é manual

Envolve criar credenciais em três lugares (Tailscale, VPS, GitHub) que nenhum agente pode ver, e é o **último deploy manual completo** sob a exceção do ADR 0004 (`docs/adr/0004-interim-operation-before-prefect.md`: "Até o PR 39, atualizar a VPS é manual"). A exceção termina no primeiro deploy automático bem-sucedido, depois do merge do PR 39; entre este item e esse deploy, só o checkout de bootstrap (plano 39, passo 9: `git fetch` + `git checkout --detach origin/main`, sem `docker`) é permitido. Regras aplicáveis:

- `.claude/rules/infra.md`: "Segredos de CI e deploy vão em GitHub Secrets do environment `production`, nunca no nível do repositório; `ci.yml` e `security.yml` não usam segredos (ADR 0006, item 7)." "Não ligar o Tailscale SSH."
- ADR 0006, item 7: "Nenhum segredo no nível do repositório. Os segredos do deploy ficam só no environment `production`, restrito à `main`."
- Repositório público (P2): nenhum destes valores entra em arquivo do repo, commit, issue, PR ou **log do Actions** (os logs de repo público são públicos). Nome da tailnet, hostname e IP da VPS também ficam fora do repo e dos logs: vão como segredo (mascarado), não como variável. Um segredo que vaze precisa ser trocado.
- A VPS não precisa de credencial de leitura: repo e imagens são públicos.

Marcadores usados aqui: `<owner>`, `<repo>`, `<vps-host>` (nome MagicDNS curto), `<tailnet>`, `<vps-tailscale-ipv4>` (o `100.x.y.z` da VPS) e `tag:platform` (a tag da VPS na ACL; ADR 0003: "A ACL do Tailscale, por tag da VPS e por porta"). Troque pelos seus valores só no terminal e nos painéis, nunca aqui.

## Decisões (aceitas pelo usuário)

| Id | Decisão |
| --- | --- |
| D1 | `tag:ci` alcança **só `tcp:22`** da VPS. A saúde é conferida dentro do `deploy.sh`, em loopback, e volta pela saída do SSH (PR 39). |
| D2 | **Workload identity federation (OIDC)** do Tailscale para o GitHub Actions, no lugar do OAuth client com segredo: sem `TS_OAUTH_SECRET`, sem credencial de longa duração. A credencial federada aceita só o subject `repo:<owner>/<repo>:environment:production` e cria nós efêmeros com `tag:ci`. O job `deploy` do PR 39 pede `id-token: write`. Fallback, só se a federação não estiver disponível no seu plano do Tailscale: OAuth client com segredo (`TS_OAUTH_SECRET`) e replanejar os casos 28 e 30 do PR 39. |
| D3 | Environment `production` **sem required reviewers** (um único mantenedor; o merge na `main` com checks required e revisão dos agentes é a aprovação). Restrição de branch `main`. |
| D4 | Hostname/IP e host key da VPS são **segredos** (`VPS_HOST`, `VPS_KNOWN_HOSTS`), não variáveis. |
| D5 | Chave do deploy **sem passphrase**; a proteção é `restrict,from=...,command=...` no `authorized_keys` e o segredo de environment. |
| D6 | `VPS_HOST` = **IPv4 da tailnet** (`<vps-tailscale-ipv4>`), sem depender de MagicDNS no runner; o PR 39 usa `-o AddressFamily=inet`. Alternativa: FQDN `<vps-host>.<tailnet>.ts.net`. Seja qual for, o `ssh-keyscan` usa **a mesma string**. |

## Checklist

### Tailscale (o runner entra na tailnet só durante o deploy)

Confira os nomes de menu na documentação atual do Tailscale (`tailscale.com/kb`: "GitHub Action", "Workload identity federation", "Tags", "Grants", "Tailnet Lock", "Device approval").

- [ ] Em `tagOwners`, declarar o dono da tag: `"tag:ci": ["autogroup:admin"]`.
- [ ] **Remover ou estreitar qualquer regra com `src` `*`** (a política padrão do Tailscale vem com uma regra "todos para todos"). Nenhuma regra com `"src": ["*"]` pode ter a VPS (ou `*`) como destino; troque por regras explícitas para você, a cientista (já existentes nos itens 04, 12 e 31) e `tag:ci`.
- [ ] Liberar `tag:ci` só para SSH na VPS. Em *grants*:

  ```json
  {"src": ["tag:ci"], "dst": ["tag:platform"], "ip": ["tcp:22"]}
  ```

  ou, se o policy file ainda usa `acls`: `{"action": "accept", "src": ["tag:ci"], "dst": ["tag:platform:22"]}`. Se a VPS não tiver tag, use um alias em `hosts` (Q1).
- [ ] Confirmar que nenhuma outra regra dá algo a `tag:ci` e que `tag:ci` não é destino de nada.
- [ ] Testes no próprio policy file (o Tailscale recusa salvar se falharem). Declare em `hosts` um alias para outro dispositivo seu (ex.: `"notebook": "<ip-100.x-do-notebook>"`) para o teste de negação:

  ```json
  "tests": [
    {"src": "tag:ci", "proto": "tcp",
     "accept": ["tag:platform:22"],
     "deny": ["tag:platform:5432", "tag:platform:8080", "tag:platform:5000", "tag:platform:4200", "notebook:22"]}
  ]
  ```

- [ ] Criar a credencial federada (D2) para o GitHub Actions: issuer do GitHub, subject exatamente `repo:<owner>/<repo>:environment:production`, escopo para criar auth keys e tag `tag:ci`. Anotar o client ID e a audiência que o painel mostrar; vão para o GitHub abaixo. Não há segredo a copiar.
- [ ] **Tailnet Lock:** se estiver ligado na sua tailnet, nós novos precisam ser assinados; um nó efêmero do CI não entra sem chave pré-assinada. Confira o estado em Settings; se estiver ligado, siga a documentação de "pre-signed/pre-approved keys" para CI ou avise antes do PR 39.
- [ ] **Device approval:** se "Device approval" estiver ligado, confirme que nós criados pela credencial com tag entram pré-aprovados (a documentação da action diz como); senão o job do PR 39 trava esperando aprovação.
- [ ] Lembrete: taguear um nó desliga a expiração de chave dele por padrão. Para os nós efêmeros do CI isso não importa (somem ao sair); para a VPS, se você taguear agora (Q1), ela passa a não expirar, o que é o desejado para servidor.
- [ ] Não ligar o Tailscale SSH na VPS (`tailscale up --ssh`): ele ignora o `authorized_keys` e anula a restrição `command=` (ADR 0003).

### VPS — chave restrita do deploy

No **notebook** (nunca no repo):

- [ ] `ssh-keygen -t ed25519 -f ~/deploy_ci -C github-actions-deploy -N ""` (D5).

Na **VPS**, como `deploy`:

- [ ] Acrescentar a chave pública (`~/deploy_ci.pub`) em `~/.ssh/authorized_keys` **numa linha só**:

  ```
  restrict,from="100.64.0.0/10,fd7a:115c:a1e0::/48",command="/opt/platform/infra/scripts/deploy.sh" ssh-ed25519 AAAA... github-actions-deploy
  ```

  `restrict` desliga PTY, port forwarding, agent e X11; `from=` aceita só origem da tailnet (IPv4 CGNAT e IPv6 do Tailscale; o PR 39 ainda força IPv4 com `-o AddressFamily=inet`); `command=` força o script, e o que o CI mandar chega em `SSH_ORIGINAL_COMMAND`. O script só existe na VPS depois do checkout de bootstrap do plano 39 (passo 9): até lá a chave não faz nada útil, e o primeiro run do job `deploy` falha por isso, o que é esperado.
- [ ] A sua chave pessoal continua sem restrição, só para emergência e leitura: a partir do primeiro deploy automático bem-sucedido, mudar produção por SSH à mão volta a ser proibido (o checkout de bootstrap do plano 39 é a única exceção, antes disso).
- [ ] Anotar a impressão digital da host key, para conferir fora de banda: `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`.
- [ ] Anotar `docker compose version` (o PR 39 usa `up --wait --wait-timeout`) e `flock --version`.

### VPS — último deploy manual completo: passar de `build` para `pull` (ADR 0004)

Fora da janela de deploy (não entre 06:00 e 08:00 BRT). Pegue os digests no log ou no summary do último run do `deploy.yml`: `platform-jobs sha256:...` e `platform-mlflow sha256:...`.

- [ ] GitHub (perfil → Packages → `platform-jobs` e `platform-mlflow` → Package settings → Change visibility): **Public**. **Atenção: é irreversível** — um pacote público do GHCR não volta a privado (só pode ser apagado). Antes, confira que nenhuma camada tem segredo (o Trivy do PR 37 roda `--scanners vuln,secret` e passou). Confira também que cada pacote aparece ligado a `<owner>/<repo>`: o push feito pelo `GITHUB_TOKEN` de um workflow do repositório já faz esse vínculo; a label `org.opencontainers.image.source` do PR 37 é só redundância. Não crie token de leitura nem faça `docker login` na VPS.
- [ ] Em `/opt/platform/infra/.env` (continua `chmod 600`), acrescentar ou trocar: `GHCR_OWNER=<owner em minúsculas>`, `JOBS_IMAGE_DIGEST=sha256:<...>` (usado por `jobs` e `prefect-worker`), `MLFLOW_IMAGE_DIGEST=sha256:<...>`. Se houver uma linha `IMAGE_TAG=` do rascunho antigo, apague. Use só linhas `CHAVE=valor` simples (o `deploy.sh` do PR 39 lê essas chaves com `grep`/`sed`, sem `source`). Esses digests viram os "anteriores" do primeiro deploy automático (rollback possível).
- [ ] Atualizar o clone e subir pelo registry (sem `build`):

  ```sh
  cd /opt/platform
  git fetch origin main && git checkout --detach origin/main
  docker compose -f infra/docker-compose.yml --profile jobs pull
  docker compose -f infra/docker-compose.yml run --rm jobs alembic upgrade head
  docker compose -f infra/docker-compose.yml up -d --remove-orphans --wait
  infra/scripts/tailscale-serve.sh
  docker compose -f infra/docker-compose.yml run --rm jobs python -m flows.deployments
  ```

  `--profile jobs` faz o `pull` incluir o serviço `jobs`, que está em `profiles`. O `checkout --detach` deixa o clone no mesmo estado que o `deploy.sh` vai manter (HEAD destacado num commit da `main`). Esse commit é anterior ao PR 39; por isso o plano 39 tem o passo de bootstrap.

### GitHub — environment `production` e segredos

Nenhum valor abaixo vai na linha de comando: `gh secret set` lê do stdin ou pergunta.

- [ ] Criar o environment só para a `main`:

  ```sh
  gh api -X PUT repos/<owner>/<repo>/environments/production \
    -F 'deployment_branch_policy[protected_branches]=false' \
    -F 'deployment_branch_policy[custom_branch_policies]=true'
  gh api -X POST repos/<owner>/<repo>/environments/production/deployment-branch-policies \
    -f name=main -f type=branch
  ```

  Required reviewers: nenhum (D3).
- [ ] Segredos do environment:

  ```sh
  gh secret set TS_OAUTH_CLIENT_ID --env production    # client ID da credencial federada
  gh secret set TS_AUDIENCE --env production           # audiência mostrada pelo painel
  gh secret set VPS_HOST --env production              # <vps-tailscale-ipv4> (D6)
  gh secret set VPS_SSH_KEY --env production < ~/deploy_ci
  ```

  Os nomes `TS_OAUTH_CLIENT_ID` e `TS_AUDIENCE` acompanham os inputs da action conferidos no PR 39, passo 1; se lá os nomes forem outros, o PR 39 ajusta o mapeamento, não os segredos.
- [ ] `VPS_KNOWN_HOSTS`, gerado de dentro da tailnet **com a mesma string de `VPS_HOST`** e conferido com a impressão digital anotada na VPS:

  ```sh
  ssh-keyscan -4 -t ed25519 <vps-tailscale-ipv4> > ~/vps_known_hosts
  ssh-keygen -lf ~/vps_known_hosts      # tem de bater com a impressão digital anotada na VPS
  gh secret set VPS_KNOWN_HOSTS --env production < ~/vps_known_hosts
  ```

- [ ] Nenhum segredo no nível do repositório (ADR 0006, item 7). Se o rascunho antigo criou algum, apague: `gh secret delete <NOME>`. Não crie `TS_OAUTH_SECRET` (D2).
- [ ] Apagar do notebook `~/deploy_ci`, `~/deploy_ci.pub` e `~/vps_known_hosts`.

## Verificação de pronto

| Comando | Saída esperada |
| --- | --- |
| `gh api repos/<owner>/<repo>/environments/production --jq '.deployment_branch_policy'` | `{"custom_branch_policies":true,"protected_branches":false}` |
| `gh api repos/<owner>/<repo>/environments/production/deployment-branch-policies --jq '.branch_policies[].name'` | `main` (só) |
| `gh api repos/<owner>/<repo>/environments/production --jq '[.protection_rules[].type]'` | Sem `required_reviewers` (D3) |
| `gh secret list --env production --json name -q '.[].name' \| sort` | `TS_AUDIENCE`, `TS_OAUTH_CLIENT_ID`, `VPS_HOST`, `VPS_KNOWN_HOSTS`, `VPS_SSH_KEY` |
| `gh secret list --json name -q 'length'` | `0` (nenhum segredo no repositório) |
| `gh variable list --env production` | Vazio (D4) |
| `docker logout ghcr.io; docker pull ghcr.io/<owner>/platform-jobs@<digest>` (do notebook, sem login) | Baixa sem erro de autenticação |
| Na VPS: `grep -qs ghcr.io ~/.docker/config.json && echo found \|\| echo 0` | `0` |
| Na VPS: `docker compose -f /opt/platform/infra/docker-compose.yml ps --format '{{.Service}} {{.Image}} {{.Status}}'` | Serviços longos `Up`/`healthy`; `prefect-worker`/`mlflow` com imagem `ghcr.io/<owner>/platform-...@sha256:...` |
| Na VPS: `git -C /opt/platform rev-parse HEAD` | SHA do último merge na `main` |
| Na VPS: `stat -c '%a' /opt/platform/infra/.env` | `600` |
| Na VPS: `grep -c 'command="/opt/platform/infra/scripts/deploy.sh"' ~/.ssh/authorized_keys` | `1` |
| Painel do Tailscale: salvar o policy file com o bloco `tests` | Salva sem erro |
| Painel do Tailscale: procurar regras com `"src": ["*"]` | Nenhuma alcança a VPS |
| Do notebook: `curl -s https://<vps-host>.<tailnet>.ts.net:8080/health` | `ok` |

## Riscos e perguntas em aberto

- **Não verificado:** os valores exatos que `GET /repos/{o}/{r}/environments/{name}` devolve em `protection_rules[].type` (esperado `branch_policy` e, se houvesse, `required_reviewers`). Conferir rodando o comando e comparando com a UI.
- Q1: a VPS já tem tag (o ADR 0003 fala em "tag da VPS")? Se já existe `tag:platform`, use. Se não, um alias em `hosts` evita mudar o dono do nó; taguear também é aceitável (desliga a expiração de chave, o que é bom para servidor).
- Tirar a regra `*` pode cortar acessos que hoje dependem dela (seu notebook, a cientista). Antes de salvar, liste as regras explícitas que substituem a `*` e acrescente-as aos `tests` como `accept`.
- O `deploy` está no grupo `docker`, o que equivale a root na VPS. A chave do CI só executa o `deploy.sh` e só a partir da tailnet; a superfície é o próprio script (validação estrita no PR 39) e quem consegue fazer merge na `main`.
- Com a federação, não há segredo do Tailscale para vazar; a credencial só vale para jobs no environment `production` deste repositório. Revogue a credencial no painel se precisar cortar o acesso do CI.
- Se este deploy manual falhar no `alembic upgrade head`, não suba os serviços novos: os antigos continuam rodando. Investigue antes de seguir.
- A exceção do ADR 0004 acaba no primeiro deploy automático bem-sucedido (depois do merge do PR 39 e do checkout de bootstrap do passo 9 de lá); a partir dele, atualizar a VPS à mão deixa de ser permitido.

## Decisões que exigem ADR

Nenhuma própria. D1 a D6 pertencem ao ADR "Pipeline de entrega" (plano 37, seção 10), que precisa estar mergeado antes deste item. Esse ADR também registra que a exceção do ADR 0004 termina no primeiro deploy automático bem-sucedido, com o checkout de bootstrap como única ação manual permitida entre este item e esse deploy.
