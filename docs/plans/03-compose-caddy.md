# 03 — Compose de produção com Caddy (HTTPS + autenticação)

> Executa: agente. Depende de: 01. Branch sugerida: `feat/compose-caddy`.
> Testes: test-writer primeiro (vermelho), depois implementação (verde), depois refatorar com a suíte verde.

## 1. Objetivo

Criar `infra/docker-compose.yml` com o serviço Caddy (HTTPS automático e `basic_auth`) servindo uma rota de saúde, e testes que garantem as regras de infra em todo compose do repo.
É a base onde MLflow, Prefect e Grafana entram atrás do proxy nas Fases 3 e 4.

## 2. Fora do escopo

- Postgres e qualquer outro serviço (PR 10 em diante).
- Subir na VPS, DNS, certificado real (item manual 04).
- Rotas para MLflow, Prefect, Grafana (PRs 29, 30, 47).

## 3. Fase do roadmap

Fase 0 — Base da VPS: "Caddy com HTTPS e autenticação".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/docker-compose.yml` | Compose de produção; neste PR só o serviço `caddy` |
| `infra/caddy/Caddyfile` | Site `{$DOMINIO}`, rota `/saude` sem auth, resto com `basic_auth` |
| `infra/.env.example` | Lista das variáveis, com valores fictícios. Sem segredo real |
| `tests/infra/__init__.py`, `tests/infra/test_compose.py` | Testes das regras de infra (test-writer) |
| `.github/workflows/ci.yml` | Novos passos: `docker compose config -q` e `caddy validate` |

Regras que os testes codificam (de `.claude/rules/infra.md`, copiadas aqui):

> - Todo serviço no compose tem `restart: unless-stopped`.
> - MLflow e Prefect não têm autenticação própria: nunca expor sem proxy com auth ou sem Tailscale.
> - Firewall: só 22 e 443 abertos, ou nenhuma porta pública. Não abrir porta para "testar".
> - `.env` da VPS fica fora do git, permissão 600. Segredos do CI vão em GitHub Secrets.

## 5. Passos

1. (test-writer) Escreva `tests/infra/test_compose.py`, que carrega com `yaml.safe_load` todo arquivo `infra/docker-compose*.yml` e verifica os casos da seção 8. Rode `uv run pytest tests/infra/test_compose.py` e confirme que falha porque `infra/docker-compose.yml` não existe. Commit `test: add compose policy tests`.
2. (implementer) Crie `infra/docker-compose.yml`:
   - `name: plataforma`.
   - Serviço `caddy`: imagem `caddy:2.<minor>` (fixe a minor atual conferida em hub.docker.com/_/caddy), `restart: unless-stopped`, `env_file: .env`, `ports: ["${CADDY_BIND_IP}:443:443"]`, volumes `./caddy/Caddyfile:/etc/caddy/Caddyfile:ro`, `caddy_data:/data`, `caddy_config:/config`.
   - Volumes nomeados `caddy_data`, `caddy_config`.
3. Crie `infra/caddy/Caddyfile`:
   ```
   {$DOMINIO} {
       handle /saude {
           respond "ok" 200
       }
       handle {
           basic_auth {
               {$CADDY_USUARIO} {$CADDY_SENHA_HASH}
           }
           respond "plataforma" 200
       }
   }
   ```
4. Crie `infra/.env.example` com `DOMINIO=plataforma.exemplo.com`, `CADDY_BIND_IP=0.0.0.0`, `CADDY_USUARIO=admin`, `CADDY_SENHA_HASH=<hash bcrypt de "exemplo">`. Gere o hash com `docker run --rm caddy:2 caddy hash-password --plaintext exemplo`. Comentário no topo: "copie para infra/.env na VPS, chmod 600; nunca commite o .env".
5. No `ci.yml`, adicione ao job existente (o runner `ubuntu-latest` já tem Docker):
   - `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q`
   - `docker run --rm --env-file infra/.env.example -v "$PWD/infra/caddy:/etc/caddy:ro" caddy:2 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile`
6. Rode os critérios de pronto. Refatore com a suíte verde se necessário.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/test_compose.py` | Todos passam |
| `uv run pytest` | Suíte toda verde |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem erro |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q` | Sem saída, código 0 |
| Comando `caddy validate` do passo 5 | Contém `Valid configuration` |
| `git ls-files infra/.env` | Vazio (o `.env` não está no git) |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: as regras de infra (restart, portas, segredos) são verificáveis lendo o YAML e vão proteger todos os PRs de compose seguintes.

## 8. Casos de teste

Os testes leem todos os arquivos `infra/docker-compose*.yml` que existirem.

1. Dado um compose, todo serviço sem `profiles` tem `restart: unless-stopped`.
2. Dado um compose, só serviços da lista permitida podem ter `ports`. Lista neste PR: `caddy`. (PR 05 acrescenta `postgres`.) `mlflow`, `prefect-server` e `grafana` nunca publicam porta.
3. Toda porta publicada tem IP de host explícito vindo de variável (forma `"${VAR}:host:container"`); porta sem IP ou com IP literal reprova.
4. O Caddy publica só a porta de container 443 (e 80 apenas se a variável `CADDY_HTTP_BIND_IP` existir; neste PR não existe, então só 443).
5. Nenhum valor de `environment` no compose parece segredo literal: chaves que contêm `PASSWORD`, `SENHA`, `TOKEN`, `SECRET` ou `HASH` só podem ter valor na forma `${...}`.
6. `infra/.env` não está versionado (`git ls-files` não o lista) e `infra/.env.example` existe.
7. Todo arquivo montado como volume com caminho relativo (`./...`) existe no repo.

## 9. Riscos e perguntas em aberto

- P4 (rede): na opção "só Tailscale", `CADDY_BIND_IP` recebe o IP do Tailscale e o HTTPS vem do certificado `*.ts.net` (Caddy obtém sozinho se o socket do tailscaled for montado em `/var/run/tailscale/tailscaled.sock`). Isso muda o compose; se o usuário escolher (b), o implementador acrescenta esse volume. Pergunte antes de supor.
- Desafio ACME: com só a 443 aberta, o Caddy usa TLS-ALPN-01, que funciona na 443. Não é preciso abrir a 80.
- `/saude` fica sem autenticação de propósito (o PR 56 vai checá-la); responde só `ok`.

## 10. Decisões que exigem ADR

- ADR "Exposição de rede: portas públicas e papel do Tailscale" (P4). Registrar antes do merge.
