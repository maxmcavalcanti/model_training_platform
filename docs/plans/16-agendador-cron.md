# 16 — Agendador interino (supercronic) com o job `clima-previsao` às 06:30

> Executa: agente. Depende de: 15. Branch sugerida: `feat/agendador-interino`.
> **Interino**: substituído pelos deployments do Prefect na Fase 3 (PRs 33 a 36). Decisão P7 no índice.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Rodar os jobs de ingestão em horário fixo na VPS antes de o Prefect existir, com um serviço `agendador` no compose (supercronic) e um crontab versionado.
Neste PR o crontab tem só `clima-previsao` às 06:30 BRT; os PRs 22 e 26 acrescentam suas linhas.

## 2. Fora do escopo

- Prefect (Fase 3). Alertas (PR 55).
- Jobs do ONS e do clima observado (entram nos PRs 22 e 26, uma linha cada).

## 3. Fase do roadmap

Fase 2 — "`raw.clima_previsao` coletando todo dia (prioridade)". O agendamento definitivo é da Fase 3 ("Ingestões migradas para flows do Prefect").

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/cron/crontab` | Agenda dos jobs |
| `infra/jobs/Dockerfile` | Instalar `supercronic` (binário com checksum) e `tzdata`; copiar `infra/cron/` |
| `infra/docker-compose.yml` | Serviço `agendador` |
| `tests/infra/test_crontab.py` | Testes do crontab (test-writer) |
| `tests/infra/test_compose.py` | Casos do serviço `agendador` (test-writer) |
| `.github/workflows/ci.yml` | `supercronic -test` dentro da imagem |

Horários (`docs/plataforma-ml.md`, "Ingestão", BRT): 06:30 `ingest_clima_previsao`, 06:45 `ingest_clima_observado`, 07:00 `ingest_ons_carga`.
Regra de infra: todo serviço com `restart: unless-stopped` (o `agendador` é de longa duração, então cumpre).

## 5. Passos

1. (test-writer) Escreva `tests/infra/test_crontab.py` e os casos de compose (seção 8). Confirme falha porque `infra/cron/crontab` não existe. Commit `test: add crontab tests`.
2. (implementer) `infra/cron/crontab`:
   ```
   # Fuso: TZ=America/Sao_Paulo vem da imagem. Interino até a Fase 3 (Prefect).
   30 6 * * * python -m ingestion clima-previsao
   ```
3. `infra/jobs/Dockerfile`: `apt-get install -y --no-install-recommends tzdata ca-certificates curl`; baixe o `supercronic-linux-amd64` da release mais recente em github.com/aptible/supercronic/releases, confira com o SHA1 publicado na própria release (`echo "<sha1>  supercronic-linux-amd64" | sha1sum -c -`), instale em `/usr/local/bin/supercronic`. Copie `infra/cron/` para `/app/infra/cron/`. Fixe versão e checksum como `ARG`.
4. `infra/docker-compose.yml`, serviço `agendador`: mesmo `build` do `jobs`, `command: ["supercronic", "/app/infra/cron/crontab"]`, `restart: unless-stopped`, mesmo `environment` do `jobs` (URL com `ingestor`), `depends_on: postgres` saudável, sem `ports`, sem profile.
5. `ci.yml`: depois do `docker build`, `docker run --rm plataforma-jobs:ci supercronic -test /app/infra/cron/crontab`.
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/` | Todos passam |
| `docker build -f infra/jobs/Dockerfile -t plataforma-jobs .` | Sem erro (checksum confere) |
| `docker run --rm plataforma-jobs supercronic -test /app/infra/cron/crontab` | Código 0, sem erro de parse |
| `docker run --rm plataforma-jobs date +%Z` | `-03` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: um erro de digitação no crontab ou um subcomando inexistente faz o job mais urgente deixar de rodar sem ninguém perceber.

## 8. Casos de teste

1. Toda linha não vazia e não comentário de `infra/cron/crontab` tem 5 campos de agenda seguidos de um comando.
2. Todo comando tem a forma `python -m ingestion <subcomando> ...` e `<subcomando>` existe em `ingestion.cli.SUBCOMANDOS`.
3. Existe exatamente uma linha para `clima-previsao`, com agenda `30 6 * * *`.
4. Nenhuma linha redireciona saída para arquivo (`>`): os logs vão para o stdout do container, visíveis com `docker compose logs agendador`.
5. Compose: `agendador` tem `restart: unless-stopped`, sem `ports`, `command` começa com `supercronic`, e `DATABASE_URL` usa `ingestor`.

## 9. Riscos e perguntas em aberto

- P7: alternativa ao supercronic é o crontab do host chamando `docker compose run --rm jobs ...`. O supercronic foi escolhido porque fica versionado no repo, sobe com o compose, volta após reboot pela política de restart e loga no stdout. Confirmar.
- Falha de job só aparece em `docker compose logs agendador` até o PR 55. O item 17 inclui uma checagem diária manual até lá.
- Arquitetura da VPS: se for ARM, baixar `supercronic-linux-arm64`. Confirmar no item 02.

## 10. Decisões que exigem ADR

- ADR "Operação interina antes do Prefect: agendador supercronic e deploy manual" (P6 e P7), escrito antes deste PR ou junto com o do item 12.
