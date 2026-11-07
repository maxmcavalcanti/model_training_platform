# Limpeza de `docs/plans/` depois do ADR 0003

> Executa: agente (`task-implementer`). Depende de: ADR 0003 (`docs/adr/0003-tailscale-only-network.md`, já na `main`, commit `d4d1934`). Branch sugerida: `docs/plans-cleanup-after-adr-0003`.
> O PR altera só `docs/plans/**`, então dispensa `code-reviewer` e `pr-reviewer` (`AGENTS.md`, "Fluxo de trabalho").

## 1. Objetivo

Tirar dos planos numerados (`docs/plans/NN-*.md`) as sobras de antes do ADR 0003: a P15 tratada como aberta, as menções a Caddy, o "ADR de rede" tratado como algo ainda a escrever e a frase desatualizada sobre os comandos.
A mudança é só de texto. Nenhuma decisão, dependência ou escopo de PR muda além do que a P15 e o ADR 0003 já decidiram.

## 2. Fora do escopo

- `AGENTS.md`, `CLAUDE.md`, `.claude/**`, `docs/plataforma-ml.md`, `docs/adr/**`, `docs/guia-ciencia-de-dados.md`.
- Os planos datados `docs/plans/2026-11-07-*.md`. São registro histórico e não mudam.
- O plano `01-bootstrap-ambiente-dev.md`, que já foi executado (ver Q5).
- Passar a exigir só `127.0.0.1` nos testes do PR 03 (casos 4 e 5) e nos textos que ainda aceitam "IP do Tailscale / faixa `100.64.0.0/10`" (ver Q1).
- Escrever ADR, ou dar número aos ADRs futuros.
- Preencher a seção "Comandos" do `AGENTS.md` (ver Q3).

## 3. Fase do roadmap

Nenhuma fase própria. É uma tarefa transversal que fecha o ADR 0003 (pré-requisito da Fase 0, "Base da VPS", de `docs/plataforma-ml.md`) e não adianta itens de fases futuras: só corrige o texto dos planos que já existem.

## 4. Arquivos a alterar

Os números de linha valem para a `main` em `d4d1934`.

| Caminho | Motivo |
| --- | --- |
| `docs/plans/00-indice.md` | Linhas 5, 12, 17, 142, 147, 160 e 167–175: P15 resolvida, Caddy, ADR de rede, comandos, lista de ADRs |
| `docs/plans/02-provisionar-vps-manual.md` | Linha 30 ("ADR de rede") e linha 31 (passo condicional da P15) |
| `docs/plans/03-compose-rede-tailscale.md` | Linhas 5, 10, 21, 34–41, 45, 53, 113 e 122: Caddy, P15, ADR de rede, regras de infra citadas de antes do ADR 0003 |
| `docs/plans/10-postgres-no-compose.md` | Linhas 8, 30, 46, 76 e 81, mais as consequências diretas da P15 (linha no script, um caso de teste) |
| `docs/plans/12-subir-postgres-vps-manual.md` | Linhas 16 e 37 (P15 condicional), mais o passo que aplica o `tailscale serve --tcp` |
| `docs/plans/28-bancos-mlflow-prefect.md` | Linha 18 ("atrás do Caddy", "ADR de rede") |
| `docs/plans/29-mlflow-no-compose.md` | Linhas 20 e 83 |
| `docs/plans/30-prefect-server-no-compose.md` | Linhas 18 e 76 |
| `docs/plans/39-deploy-via-ssh.md` | Linha 76 ("(ADR de rede)") |
| `docs/plans/28b-upgrade-vps-condicional-manual.md` | Linha 32: "atualizar `POSTGRES_BIND_IP`" deixa de valer com o Postgres em loopback (ver Q2) |

Fatos de que o implementador precisa (copiados do repo):

- ADR 0003, "Postgres (P15)": "`127.0.0.1:5432` + `tailscale serve --tcp=5432`, sem sidecar do Tailscale no compose e sem depender da ordem de boot."
- ADR 0003, "Consequências": "O `After=tailscaled.service` do item 02 deixa de ser necessário, porque o Docker não precisa esperar o tailscaled no boot." E: "Ligar o Tailscale SSH no futuro exige revisar este ADR e replanejar os itens 38 e 39."
- `.claude/rules/infra.md` atual (depois do ADR 0003):
  > - Todo serviço no compose tem `restart: unless-stopped`.
  > - MLflow, Prefect e Grafana não têm autenticação adequada: só em `127.0.0.1`, expostos na tailnet por `tailscale serve`; a ACL do Tailscale é o controle de acesso (ADR 0003).
  > - Firewall: nenhuma porta pública (ADR 0003). A 22 pública só durante o provisionamento. Nenhuma porta do compose em `0.0.0.0` (o Docker passa por cima do ufw). Não ligar o Tailscale SSH. Não abrir porta para "testar".
  > - `.env` da VPS fica fora do git, permissão 600. Segredos do CI vão em GitHub Secrets.
- `docs/plataforma-ml.md` atual, roadmap: Fase 0, linha 187: "UIs na tailnet por `tailscale serve` (HTTPS `*.ts.net`), ACL do Tailscale como controle de acesso"; Fase 3, linha 205: "MLflow e Prefect no compose, só na tailnet (`tailscale serve`)". O doc não cita mais Caddy.
- Comandos que existem hoje (PR 01, `.github/workflows/ci.yml`): `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`. Não existem ainda: Postgres de teste (PR 05) e `uv run alembic ...` (PR 06). A seção "Comandos" do `AGENTS.md` ainda diz "Ainda não há código" (ver Q3).
- ADRs na `main`: `docs/adr/0001-english-naming-convention.md`, `docs/adr/0002-python-toolchain-and-package-layout.md`, `docs/adr/0003-tailscale-only-network.md`.
- Identificadores em inglês (ADR 0001): `platform`, `HEALTH_BIND_IP`, `POSTGRES_BIND_IP`, `infra/scripts/tailscale-serve.sh`, `tag:platform`, `/opt/platform`. Prosa em português.

## 5. Passos

1. Crie a branch `docs/plans-cleanup-after-adr-0003` a partir da `main`.
2. `docs/plans/00-indice.md`:
   1. Linha 5: troque "aplica as decisões P1 a P5 do usuário (...)" por "aplica as decisões P1 a P5 e a P15 do usuário (...)". O resto da linha não muda.
   2. Linha 12: substitua o item inteiro por:
      `- Comandos que já existem (PR 01, ver `.github/workflows/ci.yml`): `uv sync` (no CI, `uv sync --locked`), `uv run ruff check .`, `uv run ruff format --check .` e `uv run pytest`. O Postgres de teste vem do PR 05 e `uv run alembic ...` do PR 06. Cada PR registra os seus na seção "Comandos" do `AGENTS.md`. Nenhuma spec usa comando que não exista no ponto em que ela roda.`
   3. Linha 17: troque o trecho "num hostname `*.ts.net` com uma porta por UI (recomendado; a alternativa, acesso direto pelo IP/nome do tailnet, é a decisão fina do ADR de rede). O Postgres fica no IP do Tailscale ou em loopback + `tailscale serve --tcp` (P15)." por "num hostname `*.ts.net` com uma porta por UI (ADR 0003, `docs/adr/0003-tailscale-only-network.md`). O Postgres fica em `127.0.0.1:5432`, exposto na tailnet por `tailscale serve --tcp=5432` (P15)." O resto da linha não muda.
   4. Linha 142 (P4): troque "Sem domínio, sem Caddy, sem certificado público" por "Sem domínio, sem proxy com autenticação, sem certificado público", e "ou acesso direto pelo IP/nome do tailnet (decisão fina no ADR de rede)" por "(ADR 0003)". As specs afetadas não mudam.
   5. Na tabela "Decisões resolvidas", depois da linha da P5, acrescente:
      `| P15 | Postgres na tailnet | **Loopback + `tailscale serve --tcp=5432`**: `127.0.0.1:5432`, sem sidecar do Tailscale no compose e sem dependência da ordem de boot; o `After=tailscaled.service` deixa de ser necessário (ADR 0003) | 02, 03, 10, 12 |`
   6. Apague a linha 160 (P15 em "Pontos de decisão em aberto").
   7. Linha 147: troque "A numeração P6–P18 foi mantida" por "A numeração P6–P18 foi mantida (a P15 está em "Decisões resolvidas")".
   8. Substitua as linhas 167 a 175 (seção "ADRs a escrever") por:
      ```
      ## ADRs já escritos

      - `docs/adr/0001-english-naming-convention.md`: convenção de nomes em inglês.
      - `docs/adr/0002-python-toolchain-and-package-layout.md`: toolchain Python e layout de pacotes (P1).
      - `docs/adr/0003-tailscale-only-network.md`: rede só Tailscale (P4, P15).

      ## ADRs a escrever (o planner não escreve ADR)

      O número de cada ADR é dado quando ele for escrito.

      1. Operação interina antes do Prefect: deploy manual e supercronic (P6, P7) — antes do 11/16; marcado `superseded` nos PRs 36 e 39.
      2. Contrato de dados v1 de `raw` e `ref` (P8, P18) — antes do 09.
      3. Execução de modelos (P12, P13) — antes do 42; precisa da concordância da cientista.
      4. Fonte do real no monitoramento (P14) — antes do 53; precisa da concordância dela.
      5. Backup (P16) — antes do 57.
      ```
      Os textos dos itens 1 a 5 são os itens 3 a 7 atuais, sem mudança.
3. `docs/plans/02-provisionar-vps-manual.md`:
   1. Linha 30: troque "registre no ADR de rede e replaneje 38 e 39" por "revise o ADR 0003 (`docs/adr/0003-tailscale-only-network.md`) e replaneje 38 e 39".
   2. Apague a linha 31 inteira (o passo "Só se a P15 ficar com ...").
4. `docs/plans/03-compose-rede-tailscale.md`:
   1. Linha 5: troque "Isso é desvio de `docs/plataforma-ml.md` (que prevê Caddy na stack) e exige o ADR da seção 10 mergeado antes deste PR." por "Decisão registrada no ADR 0003 (`docs/adr/0003-tailscale-only-network.md`), já na `main`."
   2. Linha 10: troque "sempre em loopback (ou no IP do Tailscale, para o Postgres, conforme P15) e nunca na internet" por "sempre em loopback (o Postgres também, P15) e nunca na internet".
   3. Linha 21: substitua por `Fase 0 — Base da VPS: "UIs na tailnet por `tailscale serve` (HTTPS `*.ts.net`), ACL do Tailscale como controle de acesso" (`docs/plataforma-ml.md`, roadmap; ADR 0003).`
   4. Linhas 34 a 41: troque o bloco citado pelas quatro regras atuais de `.claude/rules/infra.md` (seção 4 deste plano), com a frase de introdução "Regras que os testes codificam (de `.claude/rules/infra.md`, copiadas aqui):". Apague a linha 41 ("Com a decisão de rede, vale o ramo ...").
   5. Linha 45: troque "Modelo de acesso (recomendado; a escolha fina é o ADR da seção 10):" por "Modelo de acesso (ADR 0003):".
   6. Linha 53: troque a célula "P15: `${POSTGRES_BIND_IP}` = IP do Tailscale, ou `127.0.0.1:5432` + `tailscale serve --tcp=5432`" por "`127.0.0.1:5432` + `tailscale serve --tcp=5432` (P15)".
   7. Apague a linha 113 (o item "ADR de rede (seção 10): ...").
   8. Linha 122 (seção 10): substitua por "Nenhuma nova. A rede só Tailscale está no ADR 0003 (`docs/adr/0003-tailscale-only-network.md`), já na `main`."
5. `docs/plans/10-postgres-no-compose.md`:
   1. Linha 8: troque "porta publicada só no IP do Tailscale ou em loopback (P15), nunca em `0.0.0.0`" por "porta publicada só em loopback (`127.0.0.1:5432`) e exposta na tailnet por `tailscale serve --tcp=5432` (P15, ADR 0003), nunca em `0.0.0.0`".
   2. Tabela da seção 4: acrescente `| `infra/scripts/tailscale-serve.sh` | Linha `tailscale serve --bg --tcp=5432 tcp://127.0.0.1:5432` (P15) |` e `| `tests/infra/test_tailscale_serve.py` | Caso novo para a linha do Postgres (test-writer) |`.
   3. Linha 30: troque "ADR do PR 03" por "ADR 0003".
   4. Passo 1: acrescente que o test-writer também escreve o caso 7 em `tests/infra/test_tailscale_serve.py`.
   5. Linha 46 (passo 3): troque o comentário por "o Postgres fica em 127.0.0.1 e é exposto na tailnet por `tailscale serve --tcp=5432` (ADR 0003); nunca 0.0.0.0".
   6. Depois do passo 3, insira o passo "Em `infra/scripts/tailscale-serve.sh`, acrescente `tailscale serve --bg --tcp=5432 tcp://127.0.0.1:5432` depois das linhas `--https`. Confira a sintaxe contra `tailscale serve --help` da versão instalada (mesma regra do PR 03); se divergir, ajuste e registre no PR." Renumere os passos seguintes.
   7. Seção 6: acrescente a linha `| `shellcheck infra/scripts/tailscale-serve.sh` | Sem saída |`.
   8. Seção 8: acrescente o caso "7. `infra/scripts/tailscale-serve.sh` tem uma linha `--tcp=5432 tcp://127.0.0.1:5432`, e `POSTGRES_BIND_IP` em `infra/.env.example` vale `127.0.0.1`."
   9. Linha 76: substitua o item por "Com `tailscale serve --tcp`, o Postgres vê as conexões da tailnet vindas de 127.0.0.1. Se o teste de reboot do item 12 falhar, devolva para o planejamento."
   10. Linha 81: troque por "Coberto pelo ADR 0003 (`docs/adr/0003-tailscale-only-network.md`)."
6. `docs/plans/12-subir-postgres-vps-manual.md`:
   1. Linha 16: troque "`POSTGRES_BIND_IP=<tailscale ip -4>` (ou `127.0.0.1`, se a P15 escolher `tailscale serve --tcp=5432`; nunca `0.0.0.0`)" por "`POSTGRES_BIND_IP=127.0.0.1` (nunca `0.0.0.0`)".
   2. Depois do passo `docker compose -f infra/docker-compose.yml up -d --wait postgres` (linha 17), insira: "- [ ] `infra/scripts/tailscale-serve.sh`; `tailscale serve status` lista a porta 5432 (P15, ADR 0003)."
   3. Linha 37: troque "Se o Postgres não subir por falta do IP do Tailscale, ver P15 no índice." por "Se o reboot exigir qualquer intervenção (inclusive rodar de novo o `tailscale-serve.sh`), devolva para o planejamento."
7. `docs/plans/28-bancos-mlflow-prefect.md`, linha 18: substitua por `Fase 3 — "MLflow e Prefect no compose" (pré-requisito). Pelo ADR 0003 (rede só Tailscale), o acesso é pela tailnet.`
8. `docs/plans/29-mlflow-no-compose.md`:
   1. Linha 20: substitua por `Fase 3 — "MLflow e Prefect no compose, só na tailnet (`tailscale serve`)". Pelo ADR 0003, o acesso é pela tailnet, sem proxy com autenticação.`
   2. Linha 83: troque por "Coberto pelo ADR 0003 (`docs/adr/0003-tailscale-only-network.md`)."
9. `docs/plans/30-prefect-server-no-compose.md`:
   1. Linha 18: substitua por `Fase 3 — "MLflow e Prefect no compose, só na tailnet (`tailscale serve`)". Pelo ADR 0003, o acesso é pela tailnet.`
   2. Linha 76: troque por "Nenhuma (coberto pelo ADR 0003, `docs/adr/0003-tailscale-only-network.md`)."
10. `docs/plans/39-deploy-via-ssh.md`, linha 76: troque "(ADR de rede)" por "(e revisão do ADR 0003)".
11. `docs/plans/28b-upgrade-vps-condicional-manual.md`, linha 32: troque "(se mudou, atualizar `POSTGRES_BIND_IP` no `.env` e o `VPS_KNOWN_HOSTS` do item 38, se já existir)" por "(se mudou, atualizar o `VPS_KNOWN_HOSTS` do item 38, se já existir)". Pule este passo se o usuário responder "não" à Q2.
12. Rode os critérios de pronto.
13. Commit em inglês: `docs: clean up plans after ADR 0003`. Título e corpo do PR em inglês. Abra o PR só se o usuário pedir.

## 6. Critérios de pronto

Rode a partir da raiz do repo, na branch. Os comandos funcionam em PowerShell e em bash. `$N` é a abreviação de `':(glob)docs/plans/[0-9][0-9]-*.md' ':(glob)docs/plans/[0-9][0-9][a-z]-*.md'` (planos numerados, sem os datados `2026-*`): escreva os dois pathspecs por extenso. Nas células abaixo, `\|` é o caractere `|` (escapado por causa da tabela).

| # | Comando | Saída esperada |
| --- | --- | --- |
| 1 | `git grep -n -i caddy -- $N` | Vazio (código 1) |
| 2 | `git grep -n -e 'ADR de rede' -e 'ADR da seção 10' -e 'ADR "Rede só Tailscale' -e 'ADR do PR 03' -- $N` | Vazio |
| 3 | `git grep -n -i -e 'se a P15' -e 'conforme P15' -e 'ver P15' -e 'P15:' -- $N` | Vazio |
| 4 | `git grep -n 'tailscaled.service' -- $N` | Uma linha só, em `docs/plans/00-indice.md` (a linha da P15 em "Decisões resolvidas") |
| 5 | `git grep -n 'IP do Tailscale' -- docs/plans/10-postgres-no-compose.md docs/plans/12-subir-postgres-vps-manual.md` | Vazio |
| 6 | `git grep -n -e '^## ' -e '^\| P15 \|' -- docs/plans/00-indice.md` | Uma linha que começa com `\| P15 \|`, com número entre o de `## Decisões resolvidas` e o de `## Pontos de decisão em aberto` |
| 7 | `git grep -n -e '0001-english-naming-convention' -e '0002-python-toolchain-and-package-layout' -e '0003-tailscale-only-network' -- docs/plans/00-indice.md` | As 3 linhas de "ADRs já escritos", mais a linha 17 (que cita o ADR 0003) |
| 8 | `git grep -n -E 'ADR 000[4-9]\|adr/000[4-9]' -- $N` | Vazio (nenhum número de ADR inventado; as migrações `0004`–`0009` não casam) |
| 9 | `git grep -n -e 'criados pelos PRs 01, 05 e 06' -e 'Toolchain Python e layout de pacotes (P1) — antes' -- docs/plans/00-indice.md` | Vazio |
| 10 | `git grep -n 'tcp://127.0.0.1:5432' -- docs/plans/10-postgres-no-compose.md` | Ao menos 3 linhas (tabela da seção 4, passo novo, caso 7) |
| 11 | `git diff --name-only main...HEAD` | Só os 10 arquivos da seção 4 (9, se a Q2 for "não"). Nenhum `docs/plans/2026-*`, `AGENTS.md`, `CLAUDE.md` ou `.claude/` |
| 12 | `uv run ruff check .` e `uv run pytest` | `All checks passed!` e `1 passed` (nada fora de `docs/` mudou) |

## 7. Testes necessários

`não`: só documentação (`docs/plans/**`), sem mudança de comportamento de código.

## 8. Casos de teste

n/a

## 9. Riscos e perguntas em aberto

- **Q1.** O ADR 0003 diz "Toda porta de serviço do compose fica em `127.0.0.1`", mas o caso 5 do PR 03 (linha 103) e os textos em `02:35`, `03:43`, `10:67`, `30:31` e `47:30` ainda aceitam o IP do Tailscale (`100.64.0.0/10`). Endurecer isso muda o que o PR 03 testa. Padrão: não mexer neste PR; vira tarefa própria se o usuário quiser.
- **Q2.** `28b:32` não está entre os arquivos citados na tarefa, mas é sobra da P15 (o `POSTGRES_BIND_IP` não depende mais do IP do Tailscale). Padrão: incluir (passo 11).
- **Q3.** O PR 01 previa preencher a seção "Comandos" do `AGENTS.md` (`01`, passo 9), mas o `AGENTS.md` da `main` ainda diz "Ainda não há código". Este PR não pode editar o `AGENTS.md`. Sugestão: tarefa própria, que passa por `code-reviewer` e `pr-reviewer`. Até lá, o índice aponta para `.github/workflows/ci.yml`.
- **Q4.** O passo 4.4 troca o bloco de regras que o PR 03 cita (linhas 34–41) pelo texto atual de `.claude/rules/infra.md`. É sobra do ADR 0003 (a regra antiga dizia "só 22 e 443"), mas não estava na lista da tarefa. Padrão: incluir.
- **Q5.** A seção 10 do `01-bootstrap-ambiente-dev.md` ainda fala do ADR de toolchain como algo a escrever. Como o 01 já foi executado, padrão: não mexer.
- Risco: os números de linha mudam conforme os passos avançam. Edite cada arquivo de baixo para cima, ou localize pelo texto citado.

## 10. Decisões que exigem ADR

Nenhuma. A tarefa só aplica o ADR 0003, que já está na `main`.
