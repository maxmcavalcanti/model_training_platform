# 16 — Agendador interino (supercronic) com o job `weather-forecast` às 06:30

> Executa: agente. Depende de: 15. Branch sugerida: `feat/interim-scheduler`.
> **Interino**: substituído pelos deployments do Prefect na Fase 3 (PRs 33 a 36). Decisão P7 no índice.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Rodar os jobs de ingestão em horário fixo na VPS antes de o Prefect existir, com um serviço `scheduler` no compose (supercronic) e um crontab versionado.
Neste PR o crontab tem só `weather-forecast` às 06:30 BRT; os PRs 22 e 26 acrescentam suas linhas.

## 2. Fora do escopo

- Prefect (Fase 3). Alertas (PR 55).
- Jobs do ONS e do clima observado (entram nos PRs 22 e 26, uma linha cada).

## 3. Fase do roadmap

Fase 2 — "`raw.weather_forecast` coletando todo dia (prioridade)". O agendamento definitivo é da Fase 3 ("Ingestões migradas para flows do Prefect").

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/cron/crontab` | Agenda dos jobs |
| `infra/jobs/Dockerfile` | Instalar `supercronic` (binário com checksum) e `tzdata`; copiar `infra/cron/` |
| `infra/docker-compose.yml` | Serviço `scheduler` |
| `tests/infra/test_crontab.py` | Testes do crontab (test-writer) |
| `tests/infra/test_compose.py` | Casos do serviço `scheduler` (test-writer) |
| `.github/workflows/ci.yml` | `supercronic -test` dentro da imagem |

Horários (`docs/plataforma-ml.md`, "Ingestão", BRT): 06:30 `ingest_weather_forecast`, 06:45 `ingest_weather_observed`, 07:00 `ingest_ons_load`.
Regra de infra: todo serviço com `restart: unless-stopped` (o `scheduler` é de longa duração, então cumpre).

## 5. Passos

1. (test-writer) Escreva `tests/infra/test_crontab.py` e os casos de compose (seção 8). Confirme falha porque `infra/cron/crontab` não existe. Commit `test: add crontab tests`.
2. (implementer) `infra/cron/crontab`:
   ```
   # Fuso: TZ=America/Sao_Paulo vem da imagem. Interino até a Fase 3 (Prefect).
   30 6 * * * python -m ingestion weather-forecast
   ```
3. `infra/jobs/Dockerfile`: `apt-get install -y --no-install-recommends tzdata ca-certificates curl`; baixe o `supercronic-linux-amd64` da release mais recente em github.com/aptible/supercronic/releases, confira com o SHA1 publicado na própria release (`echo "<sha1>  supercronic-linux-amd64" | sha1sum -c -`), instale em `/usr/local/bin/supercronic`. Copie `infra/cron/` para `/app/infra/cron/`. Fixe versão e checksum como `ARG`.
4. `infra/docker-compose.yml`, serviço `scheduler`: mesmo `build` do `jobs`, `command: ["supercronic", "/app/infra/cron/crontab"]`, `restart: unless-stopped`, `mem_limit: 512m` (o job roda dentro deste container; mesmo limite do `jobs`), mesmo `environment` do `jobs` (URL com `ingestor`), `depends_on: postgres` saudável, sem `ports`, sem profile.
5. `ci.yml`: depois do `docker build`, `docker run --rm platform-jobs:ci supercronic -test /app/infra/cron/crontab`.
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/` | Todos passam |
| `docker build -f infra/jobs/Dockerfile -t platform-jobs .` | Sem erro (checksum confere) |
| `docker run --rm platform-jobs supercronic -test /app/infra/cron/crontab` | Código 0, sem erro de parse |
| `docker run --rm platform-jobs date +%Z` | `-03` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: um erro de digitação no crontab ou um subcomando inexistente faz o job mais urgente deixar de rodar sem ninguém perceber.

## 8. Casos de teste

1. Toda linha não vazia e não comentário de `infra/cron/crontab` tem 5 campos de agenda seguidos de um comando.
2. Todo comando tem a forma `python -m ingestion <subcomando> ...` e `<subcomando>` existe em `ingestion.cli.SUBCOMMANDS`.
3. Existe exatamente uma linha para `weather-forecast`, com agenda `30 6 * * *`.
4. Nenhuma linha redireciona saída para arquivo (`>`): os logs vão para o stdout do container, visíveis com `docker compose logs scheduler`.
5. Compose: `scheduler` tem `restart: unless-stopped`, `mem_limit`, sem `ports`, `command` começa com `supercronic`, e `DATABASE_URL` usa `ingestor`.

## 9. Riscos e perguntas em aberto

- P7: alternativa ao supercronic é o crontab do host chamando `docker compose run --rm jobs ...`. O supercronic foi escolhido porque fica versionado no repo, sobe com o compose, volta após reboot pela política de restart e loga no stdout. Confirmar.
- Falha de job só aparece em `docker compose logs scheduler` até o PR 55. O item 17 inclui uma checagem diária manual até lá.
- Arquitetura da VPS: o item 02 registra a saída de `uname -m` (provedor "Regular Cloud Compute", provavelmente `x86_64`). Se for `aarch64`, baixar `supercronic-linux-arm64`.
- Memória: com 1 GB, dois jobs ao mesmo tempo (ex.: backfill manual durante o job agendado) podem passar do `mem_limit` ou usar swap. Evite sobrepor; a medição do checkpoint 28a confirma.

## 10. Decisões que exigem ADR

- ADR "Operação interina antes do Prefect: agendador supercronic e deploy manual" (P6 e P7), escrito antes deste PR ou junto com o do item 12.
