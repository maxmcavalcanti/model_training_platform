# 03 — Compose de produção e rede só Tailscale (`tailscale serve`)

> Executa: agente. Depende de: 01. Branch sugerida: `feat/compose-tailscale-network`.
> Testes: test-writer primeiro (vermelho), depois implementação (verde), depois refatorar com a suíte verde.
> Decisão do usuário (2026-11-07, P4 resolvida): rede **só Tailscale**. Sem domínio público, sem proxy com autenticação, sem certificado público. Decisão registrada no ADR 0003 (`docs/adr/0003-tailscale-only-network.md`), já na `main`.

## 1. Objetivo

Criar `infra/docker-compose.yml` com um serviço mínimo de saúde (`health`) publicado só em loopback, o script versionado que expõe as UIs na tailnet com `tailscale serve`, e testes que travam as regras de infra (nenhuma porta em `0.0.0.0`, `restart`, `mem_limit`, segredos) em todo compose do repo.
É a base onde Postgres, MLflow, Prefect e Grafana entram nas Fases 1, 3 e 4, sempre em loopback (o Postgres também, P15) e nunca na internet.

## 2. Fora do escopo

- Postgres e qualquer outro serviço (PR 10 em diante).
- Subir na VPS, habilitar HTTPS no painel do Tailscale, ACL (item manual 04).
- Entradas de MLflow, Prefect e Grafana no script do `tailscale serve` (PRs 29, 30, 47).
- Tailscale Funnel (exposição à internet): proibido por este plano.

## 3. Fase do roadmap

Fase 0 — Base da VPS: "UIs na tailnet por `tailscale serve` (HTTPS `*.ts.net`), ACL do Tailscale como controle de acesso" (`docs/plataforma-ml.md`, roadmap; ADR 0003).

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/docker-compose.yml` | Compose de produção; neste PR só o serviço `health` |
| `infra/health/health` | Arquivo estático com o texto `ok`, servido em `/health` |
| `infra/scripts/tailscale-serve.sh` | Declara, em código, quais portas de loopback viram HTTPS na tailnet. Idempotente |
| `infra/.env.example` | Lista das variáveis, com valores fictícios. Sem segredo real |
| `tests/infra/__init__.py`, `tests/infra/test_compose.py`, `tests/infra/test_tailscale_serve.py` | Testes das regras de infra (test-writer) |
| `.github/workflows/ci.yml` | Novos passos: `docker compose config -q` e `shellcheck infra/scripts/*.sh` |

Regras que os testes codificam (de `.claude/rules/infra.md`, copiadas aqui):

> - Todo serviço no compose tem `restart: unless-stopped`.
> - MLflow, Prefect e Grafana não têm autenticação adequada: só em `127.0.0.1`, expostos na tailnet por `tailscale serve`; a ACL do Tailscale é o controle de acesso (ADR 0003).
> - Firewall: nenhuma porta pública (ADR 0003). A 22 pública só durante o provisionamento. Nenhuma porta do compose em `0.0.0.0` (o Docker passa por cima do ufw). Não ligar o Tailscale SSH. Não abrir porta para "testar".
> - `.env` da VPS fica fora do git, permissão 600. Segredos do CI vão em GitHub Secrets.

Fato que motiva o teste mais importante: porta publicada pelo Docker com `ports:` **passa por cima do ufw**. Uma porta em `0.0.0.0` fica na internet mesmo com o firewall fechado. Por isso nenhuma porta pode ser publicada em `0.0.0.0`: só em `127.0.0.1` (loopback, depois exposta pelo `tailscale serve`) ou no IP do Tailscale (faixa `100.64.0.0/10`).

Modelo de acesso (ADR 0003):

| UI | Publicação no host (compose) | URL na tailnet (`tailscale serve`) | PR |
| --- | --- | --- | --- |
| Saúde | `127.0.0.1:8080` | `https://<host>.ts.net:8080/health` | 03 |
| MLflow | `127.0.0.1:5000` | `https://<host>.ts.net:5000` | 29 |
| Prefect | `127.0.0.1:4200` | `https://<host>.ts.net:4200` | 30 |
| Grafana | `127.0.0.1:3000` | `https://<host>.ts.net:3000` | 47 |
| Postgres (não é HTTP) | `127.0.0.1:5432` + `tailscale serve --tcp=5432` (P15) | `<host>.ts.net:5432` | 10 |

`<host>.ts.net` é o nome MagicDNS da VPS (variável `TS_HOSTNAME`, não é segredo). Um hostname, uma porta por UI.

## 5. Passos

1. (test-writer) Escreva `tests/infra/test_compose.py`, que carrega com `yaml.safe_load` todo arquivo `infra/docker-compose*.yml` e verifica os casos 1 a 8 da seção 8, e `tests/infra/test_tailscale_serve.py` com os casos 9 a 11. As funções de checagem (ex.: "esta porta é aceitável?") são do próprio teste e também são exercitadas com exemplos negativos embutidos (`"0.0.0.0:8080:8080"`, `"8080:8080"`), para provar que a checagem não passa no vazio. Rode `uv run pytest tests/infra/` e confirme que falha porque `infra/docker-compose.yml` não existe. Commit `test: add compose and network policy tests`.
2. (implementer) Crie `infra/docker-compose.yml`:
   - `name: platform`.
   - Serviço `health`: imagem `busybox:1.<minor>` (fixe a versão atual conferida em hub.docker.com/_/busybox), `command: ["httpd", "-f", "-p", "8080", "-h", "/www"]`, `volumes: ["./health:/www:ro"]`, `restart: unless-stopped`, `mem_limit: 16m`, `ports: ["${HEALTH_BIND_IP}:8080:8080"]`, `healthcheck` com `wget -qO- http://localhost:8080/health`.
3. Crie `infra/health/health` contendo `ok` (uma linha).
4. Crie `infra/scripts/tailscale-serve.sh` (`#!/usr/bin/env bash`, `set -euo pipefail`):
   - `tailscale serve reset` e, em seguida, uma linha por UI: `tailscale serve --bg --https=8080 http://127.0.0.1:8080`. Neste PR só a saúde; os PRs 29, 30 e 47 acrescentam uma linha cada.
   - Reset + reaplicar deixa o script declarativo: o estado do `tailscale serve` na VPS é sempre o que está no git.
   - Confira a sintaxe exata contra `tailscale serve --help` da versão estável atual (documentação em tailscale.com/kb/1242/tailscale-serve). Se a sintaxe divergir, ajuste e registre no PR; não invente flags.
   - Nunca use `tailscale funnel` nem `--funnel`.
5. Crie `infra/.env.example` com `HEALTH_BIND_IP=127.0.0.1` e `TS_HOSTNAME=platform.example.ts.net`. Comentário no topo: "copie para infra/.env na VPS, chmod 600; nunca commite o .env; os repos são públicos, um segredo commitado uma vez fica público para sempre e precisa ser trocado. Nenhum *_BIND_IP pode ser 0.0.0.0".
6. No `ci.yml`, adicione ao job existente (o runner `ubuntu-latest` já tem Docker e `shellcheck`):
   - `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q`
   - `shellcheck infra/scripts/*.sh`
7. Rode os critérios de pronto. Refatore com a suíte verde se necessário.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/` | Todos passam |
| `uv run pytest` | Suíte toda verde |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem erro |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q` | Sem saída, código 0 |
| `shellcheck infra/scripts/tailscale-serve.sh` | Sem saída |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example up -d --wait health` | `Container platform-health-1  Healthy` |
| `curl -s http://127.0.0.1:8080/health` | `ok` |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example ps --format '{{.Ports}}'` | `127.0.0.1:8080->8080/tcp`, sem `0.0.0.0` |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example down` | Remove o container |
| `git ls-files infra/.env` | Vazio (o `.env` não está no git) |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: as regras de infra (nenhuma porta na internet, restart, limite de memória, segredos) são verificáveis lendo o YAML e o script, e vão proteger todos os PRs de compose seguintes.

## 8. Casos de teste

Os testes leem todos os arquivos `infra/docker-compose*.yml` que existirem.

1. Dado um compose, todo serviço sem `profiles` tem `restart: unless-stopped`.
2. Dado um compose, todo serviço (com ou sem `profiles`) tem `mem_limit` definido. Motivo: a VPS tem 1 GB de RAM (decisão de 2026-11-07); um serviço sem limite pode derrubar os outros por falta de memória.
3. Só serviços da lista permitida podem ter `ports`. Lista neste PR: `health`. (PR 05 acrescenta `postgres` no compose de dev; PR 10, `postgres` no de produção; PRs 29, 30 e 47, `mlflow`, `prefect-server` e `grafana`.)
4. Toda porta publicada tem IP de host explícito: `127.0.0.1` literal ou uma variável cujo nome termina em `_BIND_IP` (forma `"${X_BIND_IP}:host:container"`, ou `"${X_BIND_IP:-127.0.0.1}:..."` com padrão `127.0.0.1`). Reprovam: porta sem IP (`"8080:8080"`), `0.0.0.0`, `::`, qualquer outro IP literal, e a sintaxe longa com `host_ip` diferente de `127.0.0.1`.
5. Em `infra/.env.example`, todo `*_BIND_IP` vale `127.0.0.1` ou um endereço da faixa do Tailscale `100.64.0.0/10`. `0.0.0.0` reprova.
6. Nenhum valor de `environment` no compose parece segredo literal: chaves que contêm `PASSWORD`, `SENHA`, `TOKEN`, `SECRET` ou `HASH` só podem ter valor na forma `${...}`.
7. `infra/.env` não está versionado (`git ls-files` não o lista) e `infra/.env.example` existe.
8. Todo arquivo montado como volume com caminho relativo (`./...`) existe no repo.
9. Toda porta publicada em loopback por um serviço da lista de UIs (`health`, `mlflow`, `prefect-server`, `grafana`) tem uma linha `--https=<porta> http://127.0.0.1:<porta>` em `infra/scripts/tailscale-serve.sh`, e toda linha do script aponta para uma porta de loopback publicada no compose (sem entrada órfã nos dois sentidos).
10. `infra/scripts/tailscale-serve.sh` não contém `funnel` (Funnel exporia a UI à internet).
11. `infra/scripts/tailscale-serve.sh` começa com `set -euo pipefail` e chama `tailscale serve reset` antes das linhas de mapeamento.

## 9. Riscos e perguntas em aberto

- Porta igual no loopback e na tailnet (ex.: 5000 e 5000): o `tailscale serve` atende no IP do Tailscale, dentro do próprio tailscaled, e o Docker escuta em `127.0.0.1`; não deve haver conflito. Se a versão instalada acusar conflito, use portas de tailnet diferentes (ex.: 15000) e ajuste o caso 9.
- Se a versão do `tailscale serve` restringir as portas HTTPS aceitas, a alternativa é servir por caminho (`--set-path`) num só porto, o que exige configurar caminho base em MLflow, Prefect e Grafana. Pergunte antes de mudar.
- `tailscale serve` exige HTTPS e MagicDNS habilitados no painel do Tailscale, e que o usuário `deploy` seja operador (`sudo tailscale set --operator=deploy`, item 02). Itens 02 e 04.
- Sem proxy com autenticação, MLflow e Prefect ficam abertos para qualquer dispositivo da tailnet que a ACL deixar passar. A ACL do Tailscale é o controle de acesso; itens 04, 12 e 31 a configuram.
- `/health` responde só `ok` e não tem informação sensível; é o alvo do teste de reboot (item 04), da checagem final do deploy (PR 39) e do vigia (PR 56).

## 10. Decisões que exigem ADR

Nenhuma nova. A rede só Tailscale está no ADR 0003 (`docs/adr/0003-tailscale-only-network.md`), já na `main`.
