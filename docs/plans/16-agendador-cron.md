# 16 — Agendador interino (supercronic) com o job `weather-forecast` às 06:30

> Executa: agente. Depende de: 15 (na `main` em `13c2ae0`). Branch sugerida: `feat/interim-scheduler`.
> **Antecipado** (Fase 2 antes do fim da Fase 1; desvio de "uma fase por vez" aprovado pelo usuário em 2026-11-07, P5).
> **Interino**: substituído pelos deployments do Prefect na Fase 3 (PRs 33 a 36). Decisão P7, registrada no ADR 0004 (já mergeado; não bloqueia).
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.
> Revisão 2026-11-08: alinhado à `main` em `13c2ae0` (imagem `infra/jobs/Dockerfile`, serviços `health`, `postgres` e `jobs` no compose, subcomando `weather-forecast` do PR 15, ADR 0003, ADR 0004, VPS `x86_64` com Ubuntu 24.04, 1 vCPU e 1 GB de RAM). As perguntas que tinham recomendação foram fechadas como decisões D1 a D12 (seção 9), por autorização do usuário. Nenhuma pergunta aberta bloqueia o PR.

## 1. Objetivo

Rodar `python -m ingestion weather-forecast` todo dia às 06:30 em `America/Sao_Paulo` na VPS, sem o Prefect, com um serviço `scheduler` de longa duração no compose (supercronic lendo o crontab versionado `infra/cron/crontab`).
O serviço usa só a credencial do `ingestor`, não publica porta, volta sozinho após reboot e loga no stdout; os PRs 22 e 26 acrescentam as próprias linhas ao crontab.

## 2. Fora do escopo

- Prefect, flows e deployments (Fase 3, PRs 32 a 36). Alertas de falha (PR 55).
- Linhas do crontab para `ons-load` (PR 22) e `weather-observed` (PR 26).
- Ligar a coleta na VPS (`git pull`, build, `up -d scheduler`): é o item manual 17.
- Healthcheck do `scheduler`, métricas Prometheus do supercronic (`-prometheus-listen-address`) ou qualquer porta: abriria um serviço novo e exigiria revisar o ADR 0003 (D9).
- Rotação de logs do Docker, `stop_grace_period` e outras opções de operação não exigidas pelas regras (seção 9, riscos).
- Imagem no GHCR (PR 37) e deploy automático (PR 39); até lá, a imagem é construída na VPS (ADR 0004).
- Binário `arm64` do supercronic (a VPS é `x86_64`, D3).
- Alterar `ingestion/`, migrações, `infra/.env.example`, `.dockerignore`, `.claude/`, ADRs ou outros planos. A redação de `.claude/rules/infra.md` já é cumprida pelo `scheduler` (ele tem `restart: unless-stopped`) e não muda aqui.

## 3. Fase do roadmap

Fase 2 — Clima, item "`raw.weather_forecast` coletando todo dia (prioridade)" (`docs/plataforma-ml.md`, "Roadmap"), antecipado pela P5. O agendamento definitivo é da Fase 3 ("Ingestões migradas para flows do Prefect").

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/cron/crontab` | Novo: agenda dos jobs (só `weather-forecast` neste PR) |
| `infra/jobs/Dockerfile` | Instalar o supercronic com versão e SHA-256 fixados; copiar `infra/cron/` para `/app/infra/cron/` |
| `infra/docker-compose.yml` | Novo serviço `scheduler` |
| `.github/workflows/ci.yml` | Job `compose-smoke`: construir o `scheduler`, validar o crontab com `supercronic -test`, conferir o fuso, a ausência da URL de admin e que o serviço fica de pé |
| `AGENTS.md` | Seção "Comandos": comandos do agendador (cada PR registra os seus) |
| `tests/infra/test_crontab.py` | Novo (test-writer): regras do crontab |
| `tests/infra/test_compose.py` | Casos do serviço `scheduler` (test-writer) |
| `tests/infra/test_jobs_image.py` | Casos do supercronic no Dockerfile (test-writer) |

### Estado atual que o PR altera (`main` em `13c2ae0`)

`infra/jobs/Dockerfile` (inteiro):

```dockerfile
FROM ghcr.io/astral-sh/uv:0.9.30-python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    TZ=America/Sao_Paulo

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

COPY ingestion/ ingestion/
COPY flows/ flows/
COPY migrations/ migrations/
COPY alembic.ini ./
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"

RUN useradd --create-home --uid 10001 app
USER app

ENTRYPOINT []
CMD ["python", "-m", "ingestion", "--help"]
```

Restrições que os testes existentes de `tests/infra/test_jobs_image.py` já impõem ao Dockerfile e que continuam valendo: todo `FROM` é `ghcr.io/astral-sh/uv:<x.y.z>-python3.12-bookworm-slim`; o último `USER` não é root; **nenhum `ADD`** e nenhum `COPY .`; nenhum `ENV`/`ARG` cujo nome contenha `PASSWORD`, `TOKEN`, `SECRET` ou `DATABASE_URL`; todo `uv sync` com `--locked --no-dev`. O `.dockerignore` exclui `docs`, `tests`, `.claude` e `**/.env*`, mas **não** exclui `infra/`, então `COPY infra/cron/ ...` funciona.

`infra/docker-compose.yml`, serviço `jobs` (os outros são `health`, `busybox` em `127.0.0.1:8080`, e `postgres`, `postgres:16.15` em `${POSTGRES_BIND_IP:-127.0.0.1}:5432`, ambos com `restart: unless-stopped` e `mem_limit`):

```yaml
  jobs:
    build:
      context: ..
      dockerfile: infra/jobs/Dockerfile
    profiles: ["jobs"]
    restart: "no"
    mem_limit: 512m
    environment:
      DATABASE_URL: postgresql+psycopg://ingestor:${POSTGRES_INGESTOR_PASSWORD:?POSTGRES_INGESTOR_PASSWORD is required}@postgres:5432/ml
      DATABASE_URL_ADMIN: postgresql+psycopg://${POSTGRES_ADMIN_USER:?POSTGRES_ADMIN_USER is required}:${POSTGRES_ADMIN_PASSWORD:?POSTGRES_ADMIN_PASSWORD is required}@postgres:5432/ml
    depends_on:
      postgres:
        condition: service_healthy
```

`tests/infra/test_compose.py` já tem as funções de checagem reutilizáveis (definidas no próprio arquivo): `load_compose`, `services_of`, `environment_items`, `literal_secret_keys`, `ingestor_url_problems` (regex `^postgresql\+psycopg://ingestor:\$\{POSTGRES_INGESTOR_PASSWORD[^}]*\}@postgres:5432/ml$`), `database_url_credential_problems`, `depends_on_postgres_problems`, `jobs_build_problems` e o fixture `main_compose`. As regras gerais (sem `profiles` ⇒ `restart: unless-stopped`; todo serviço com `mem_limit`; só `health` e `postgres` em `PORT_PUBLISHING_SERVICES`; toda variável obrigatória do compose declarada no `infra/.env.example`) passam a valer para o `scheduler` automaticamente. O padrão do arquivo é: cada função de checagem nova tem exemplos negativos embutidos.

`tests/infra/test_jobs_image.py` tem `instructions(dockerfile_text) -> list[tuple[str, str]]` (junta continuações, ignora comentários); `tests/infra/__init__.py` existe, então o arquivo novo pode importar `from tests.infra.test_jobs_image import instructions` ou o caso pode ficar no próprio `test_jobs_image.py` (preferível).

`ingestion/cli.py`: `SUBCOMMANDS: dict[str, Subcommand]` com a chave `"weather-forecast"`, que não aceita argumentos (extra → código 2). `python -m ingestion weather-forecast` devolve 0 em sucesso e 1 em falha de execução ou de checagem, com traceback no stderr.

`ingestion/jobs.py`: `issue_date()` devolve a data de agora em `America/Sao_Paulo` (`FORECAST_TIMEZONE` de `ingestion/openmeteo.py`), e o cliente exige que o primeiro dia da resposta da API seja essa data. O `ingestor` não tem `UPDATE` em `raw.weather_forecast`; o job usa `on_conflict="ignore"` (primeiro snapshot do dia vence, ADR 0005).

`.github/workflows/ci.yml`, job `compose-smoke` (trecho):

```yaml
  compose-smoke:
    runs-on: ubuntu-latest
    env:
      COMPOSE: docker compose -f infra/docker-compose.yml --env-file infra/.env.example
    steps:
      - uses: actions/checkout@v7
      - run: $COMPOSE up -d --wait postgres
      # ... checagens do postgres ...
      - run: $COMPOSE build jobs
      - run: $COMPOSE run --rm jobs
      - name: Check the jobs image runs as a non-root user
        run: test "$($COMPOSE run --rm -T jobs whoami)" = app
      - run: $COMPOSE run --rm jobs alembic upgrade head
      - name: Check migrations reached head
        run: $COMPOSE run --rm -T jobs alembic current | grep -F '(head)'
      - if: always()
        run: $COMPOSE down -v
```

O job `lint-and-test` já roda `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q`, que valida o compose com o serviço novo. O `scheduler` não usa nenhuma variável nova, então o `infra/.env.example` não muda (e **ninguém deve abri-lo**: o `Read` está bloqueado e a regra do `AGENTS.md` proíbe ler `.env*` por qualquer ferramenta; os testes do compose o leem em Python).

### Regras que valem aqui

- `AGENTS.md`: nenhum segredo no git; segredos só por variável de ambiente; identificadores, comentários, mensagens de commit e PR em inglês (ADR 0001).
- `.claude/rules/infra.md`: todo serviço com `restart: unless-stopped`; nenhuma porta em `0.0.0.0`; não abrir porta para "testar".
- ADR 0003: nenhuma porta pública; só `health` e `postgres` publicam, em loopback.
- ADR 0004: serviço `scheduler` de longa duração, `restart: unless-stopped`, `mem_limit`, sem porta, logs no stdout; supercronic com versão e checksum fixados no Dockerfile; imagem construída na VPS até o PR 37; não construir imagem com um job agendado em execução.
- `docs/plataforma-ml.md`, "Ingestão" (horários em BRT): 06:30 `ingest_weather_forecast`, 06:45 `ingest_weather_observed`, 07:00 `ingest_ons_load`.

## 5. Passos

1. (test-writer) Escreva os casos da seção 8: `tests/infra/test_crontab.py` (novo), casos do `scheduler` no fim de `tests/infra/test_compose.py` (bloco `# === plan 16`) e casos do supercronic no fim de `tests/infra/test_jobs_image.py`. Siga o padrão dos arquivos: cada função de checagem nova com exemplos negativos embutidos. Confirme a falha pelo motivo certo: `infra/cron/crontab` não existe; `infra/docker-compose.yml has no 'scheduler' service`; o Dockerfile não tem `ARG SUPERCRONIC_VERSION`. `uv run pytest -m "not db"` deve mostrar só esses novos testes vermelhos. Commit `test: add interim scheduler tests`.
2. (implementer) Descubra e fixe a versão do supercronic, fora do repo (pasta temporária vazia, nunca dentro do worktree):
   - Versão: a release mais recente marcada como estável em `https://github.com/aptible/supercronic/releases` (por exemplo com `gh release view --repo aptible/supercronic --json tagName`). Não use `latest` na URL.
   - SHA-256 do asset `supercronic-linux-amd64` dessa tag: `gh api repos/aptible/supercronic/releases/tags/<tag> --jq '.assets[] | select(.name=="supercronic-linux-amd64") | .digest'` (devolve `sha256:<64 hex>`).
   - Confira por um segundo caminho: baixe o asset e compare o SHA-1 com o publicado nas notas da release e o SHA-256 com o do passo anterior (PowerShell: `Get-FileHash -Algorithm SHA1 <arquivo>` e `Get-FileHash -Algorithm SHA256 <arquivo>`). Se divergirem, **pare** e reporte. Se o `gh api` não devolver `digest`, use o SHA-256 calculado do arquivo cujo SHA-1 bateu com o das notas, e registre isso no corpo do PR.
   - Registre no corpo do PR a tag, o SHA-1 das notas e o SHA-256 fixado.
3. `infra/jobs/Dockerfile` (logo depois do `RUN apt-get ...` existente, antes do `WORKDIR`, para o cache não ser invalidado por mudança de código):
   ```dockerfile
   # Interim scheduler until Prefect (ADR 0004). Pinned by version and SHA-256.
   ARG SUPERCRONIC_VERSION=<tag, ex.: v0.2.NN>
   ARG SUPERCRONIC_SHA256=<64 hex>
   RUN apt-get update \
       && apt-get install -y --no-install-recommends ca-certificates curl \
       && curl -fsSLo /tmp/supercronic \
          "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
       && echo "${SUPERCRONIC_SHA256}  /tmp/supercronic" | sha256sum -c - \
       && install -m 0755 /tmp/supercronic /usr/local/bin/supercronic \
       && rm /tmp/supercronic \
       && apt-get purge -y --auto-remove curl \
       && rm -rf /var/lib/apt/lists/*
   ```
   Mantenha o `ca-certificates` (não remova). Pode juntar ao `RUN` do `tzdata` se preferir um layer só, desde que os casos da seção 8 continuem verdes. Depois do `COPY alembic.ini ./`, acrescente `COPY infra/cron/ infra/cron/` (fica em `/app/infra/cron/crontab`). Não mude o `FROM`, o `USER`, o `ENTRYPOINT` nem o `CMD`.
4. `infra/cron/crontab`:
   ```
   # Interim schedule until Prefect (ADR 0004). Times are America/Sao_Paulo (TZ from the image).
   # The forecast job snapshots "today" in America/Sao_Paulo: keep it far from midnight.
   30 6 * * * python -m ingestion weather-forecast
   ```
   Sem redirecionamento de saída, sem `CRON_TZ`, sem variáveis de ambiente no arquivo. Termine o arquivo com quebra de linha.
5. `infra/docker-compose.yml`, serviço `scheduler` (entre `postgres` e `jobs`):
   ```yaml
     scheduler:
       build:
         context: ..
         dockerfile: infra/jobs/Dockerfile
       command: ["supercronic", "/app/infra/cron/crontab"]
       restart: unless-stopped
       mem_limit: 512m
       environment:
         DATABASE_URL: postgresql+psycopg://ingestor:${POSTGRES_INGESTOR_PASSWORD:?POSTGRES_INGESTOR_PASSWORD is required}@postgres:5432/ml
       depends_on:
         postgres:
           condition: service_healthy
   ```
   Sem `profiles`, sem `ports`, sem `DATABASE_URL_ADMIN` e sem nenhuma referência a `POSTGRES_ADMIN_*`, sem `TZ` (vem da imagem), sem `image:` (D6).
6. `.github/workflows/ci.yml`, job `compose-smoke`, depois do passo `Check migrations reached head` e antes do `down -v`:
   ```yaml
         - run: $COMPOSE build scheduler
         - name: Check the crontab parses
           run: $COMPOSE run --rm -T scheduler supercronic -test /app/infra/cron/crontab
         - name: Check the scheduler runs in America/Sao_Paulo
           run: test "$($COMPOSE run --rm -T scheduler date +%Z)" = "-03"
         - name: Check the scheduler has no admin database URL
           run: |
             if $COMPOSE run --rm -T scheduler printenv DATABASE_URL_ADMIN; then exit 1; fi
         - run: $COMPOSE up -d scheduler
         - name: Check the scheduler stays up
           run: |
             sleep 10
             $COMPOSE ps --status running --services | grep -x scheduler
             $COMPOSE logs scheduler
   ```
7. `AGENTS.md`, seção "Comandos", depois da linha da imagem dos jobs:
   `- Agendador interino (supercronic, até o PR 36): validar o crontab com docker run --rm platform-jobs supercronic -test /app/infra/cron/crontab; na VPS: docker compose -f infra/docker-compose.yml build scheduler, docker compose -f infra/docker-compose.yml up -d scheduler e docker compose -f infra/docker-compose.yml logs scheduler`.
8. Rode os critérios de pronto, `uv run ruff check .` e `uv run ruff format --check .`; refatore com a suíte verde.

## 6. Critérios de pronto

Comandos em PowerShell (ambiente do usuário), com Docker Desktop.

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/` | Todos passam |
| `docker build -f infra/jobs/Dockerfile -t platform-jobs .` | Termina sem erro; o log do build mostra `/tmp/supercronic: OK` (checksum conferido) |
| `docker run --rm platform-jobs supercronic -test /app/infra/cron/crontab; echo $LASTEXITCODE` | Sem erro de parse e `0` |
| `docker run --rm platform-jobs date +%Z` | `-03` |
| `docker run --rm platform-jobs whoami` | `app` |
| `docker run --rm platform-jobs python -m ingestion --help` | Lista `weather-forecast` |
| `Select-String -Path infra/docker-compose.yml -Pattern 'ADMIN'` | Só linhas dos serviços `postgres` e `jobs` (nenhuma do `scheduler`) |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem erros |
| `uv run pytest` (com `docker compose -f infra/docker-compose.dev.yml up -d`) | Suíte verde |
| `gh pr checks` | Verde, incluindo `compose-smoke` com os passos novos |

A verificação em produção (supercronic de pé na VPS, job rodando às 06:30, volta após reboot) é do item manual 17.

## 7. Testes necessários

`sim`: um erro de digitação no crontab, um subcomando inexistente, o fuso errado ou a URL de admin no serviço fazem o job mais urgente deixar de rodar (ou rodar com privilégio demais) sem ninguém perceber.

## 8. Casos de teste

Crontab (`tests/infra/test_crontab.py`, sem banco, lê `infra/cron/crontab`):

1. O arquivo existe e tem ao menos uma linha de agenda (não vazia e não comentário).
2. Toda linha de agenda tem 5 campos de agenda seguidos de um comando não vazio. Exemplos negativos: `30 6 * * python -m ingestion weather-forecast` (4 campos) e `30 6 * * *` (sem comando) são rejeitados.
3. Todo comando tem a forma `python -m ingestion <subcomando> [args...]` e `<subcomando>` é uma chave de `ingestion.cli.SUBCOMMANDS`. Exemplos negativos: `python -m ingestion weather_forecast`, `python -m ingestion`, `uv run python -m ingestion weather-forecast`, `/bin/sh -c "..."` são rejeitados.
4. Existe exatamente uma linha para `weather-forecast`, com agenda `30 6 * * *` e sem argumentos depois do subcomando.
5. Minuto e hora de toda linha são números fixos (sem `*`, `/`, `,` ou `-`): cada job roda uma vez por dia. Exemplo negativo: `*/5 6 * * *` e `30 * * * *` são rejeitados.
6. Nenhuma linha agenda entre 23:00 e 00:59 (hora 23 ou 0): o dia do snapshot é o dia em `America/Sao_Paulo` e não pode virar durante a execução. Exemplos negativos: `55 23 * * *` e `5 0 * * *` são rejeitados; `30 6 * * *` é aceito.
7. Nenhuma linha redireciona saída (`>`, `>>`, `2>`, `|`): os logs vão para o stdout do container. Exemplo negativo: `30 6 * * * python -m ingestion weather-forecast >> /tmp/log` é rejeitado.
8. O arquivo não define fuso nem variável de ambiente (nenhuma linha `CRON_TZ=`, `TZ=` ou `NOME=valor`): o fuso vem só da imagem.

Compose (`tests/infra/test_compose.py`, bloco do plano 16, serviço `scheduler` de `infra/docker-compose.yml`):

9. O serviço `scheduler` existe, não tem `profiles`, tem `restart: unless-stopped`, tem `mem_limit` e não declara `ports`. Exemplos negativos: com `profiles: ["jobs"]`, com `restart: "no"`, sem `mem_limit` ou com `ports: ["127.0.0.1:1:1"]` → rejeitado.
10. O `command` é a lista `["supercronic", "/app/infra/cron/crontab"]`. Exemplos negativos: string `supercronic /app/infra/cron/crontab`, `["supercronic", "-test", "/app/infra/cron/crontab"]` e `["python", "-m", "ingestion", "--help"]` → rejeitados.
11. O `build` é o mesmo do `jobs`: `context: ..` e `dockerfile: infra/jobs/Dockerfile`.
12. O `environment` tem `DATABASE_URL` igual à URL do `ingestor` (mesma regra do caso 11 do plano 11) e a senha é uma referência `${...}`.
13. O `environment` não tem `DATABASE_URL_ADMIN`, e nenhum valor do serviço (o serviço inteiro serializado) referencia `POSTGRES_ADMIN_USER`, `POSTGRES_ADMIN_PASSWORD` ou outra variável com `ADMIN` no nome. Exemplos negativos: um serviço com `DATABASE_URL_ADMIN` → rejeitado; um serviço com `DATABASE_URL: postgresql+psycopg://${POSTGRES_ADMIN_USER}:${POSTGRES_ADMIN_PASSWORD}@postgres:5432/ml` → rejeitado.
14. O `environment` não define `TZ`, ou, se definir, é exatamente `America/Sao_Paulo`. Exemplo negativo: `TZ: UTC` → rejeitado.
15. O serviço espera o `postgres` saudável (`depends_on.postgres.condition: service_healthy`).
16. As regras gerais continuam verdes com o serviço novo: `PORT_PUBLISHING_SERVICES` continua `{"health", "postgres"}` (não deve ser ampliado) e toda variável obrigatória do compose segue declarada no `infra/.env.example`.

Imagem (`tests/infra/test_jobs_image.py`, sem Docker, lê `infra/jobs/Dockerfile`):

17. Existe `ARG SUPERCRONIC_VERSION=<valor>` com valor no formato `v<n>.<n>.<n>`. Exemplos negativos: sem valor padrão, `latest`, `0.2.33` sem `v`, `v0.2` → rejeitados.
18. Existe `ARG SUPERCRONIC_SHA256=<valor>` com exatamente 64 caracteres hexadecimais minúsculos. Exemplos negativos: 40 hex (SHA-1), 63 hex, vazio, com prefixo `sha256:` → rejeitados.
19. Algum `RUN` baixa de `https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-amd64` e, no mesmo `RUN`, confere com `sha256sum -c` usando `${SUPERCRONIC_SHA256}`. Exemplos negativos: URL com `/releases/latest/`, URL `linux-arm64`, `RUN` sem `sha256sum -c`, conferência com `sha1sum` → rejeitados.
20. O Dockerfile copia `infra/cron/` para `infra/cron/` (relativo ao `WORKDIR /app`) e continua sem `ADD` (regra existente).
21. O Dockerfile mantém `TZ=America/Sao_Paulo` num `ENV`. Exemplo negativo: `ENV TZ=UTC` ou ausência de `TZ` → rejeitado.
22. As regras existentes continuam verdes: nenhum `ARG`/`ENV` novo tem nome com `PASSWORD`, `TOKEN`, `SECRET` ou `DATABASE_URL`; o último `USER` continua `app`.

## 9. Riscos e perguntas em aberto

Decisões tomadas nesta revisão (recomendações adotadas por autorização do usuário):

- **D1. Supercronic no compose, não crontab do host.** Já decidido no ADR 0004 (P7): fica versionado, sobe com o compose, volta após reboot pela política de restart e loga no stdout.
- **D2. Só a credencial do `ingestor` no `scheduler`.** O serviço fica no ar o tempo todo e só roda jobs de ingestão; a URL de admin (migrações) continua só no `jobs`, de execução única. Se o container for comprometido, o estrago fica limitado ao que o `ingestor` pode (sem `UPDATE`/`DELETE` em `raw.weather_forecast`). Casos 13 e o passo do CI travam isso.
- **D3. Só o binário `supercronic-linux-amd64`.** A VPS é `x86_64` (Ubuntu 24.04), assim como os runners do GitHub Actions. Sem `TARGETARCH` nem multi-arquitetura: menos caminhos não testados. Se a VPS mudar de arquitetura (item 28b), o PR do upgrade troca o asset e o checksum.
- **D4. Fixar SHA-256, não o SHA-1 das notas.** O SHA-1 que a release publica serve só para conferir uma vez, no passo 2; o pin no Dockerfile é SHA-256 (exigência desta revisão, e o SHA-1 é fraco contra colisão). `curl` é removido depois do download; `ca-certificates` fica (é o que valida o TLS do download e serve ao `httpx`).
- **D5. 06:30 interpretado em `America/Sao_Paulo` pelo `TZ` da imagem.** O job calcula `issued_at` como o dia corrente em `America/Sao_Paulo` e o cliente exige que o primeiro dia da resposta da API seja esse dia. Rodar às 06:30 locais (09:30 UTC; o Brasil não tem horário de verão desde 2019, e se voltar a ter o `tzdata` resolve) deixa 17 horas e meia de folga até a virada do dia, o que cobre o retry de rede, um reinício do container e uma reexecução manual no mesmo dia (item 17). Sem `CRON_TZ` no crontab: uma fonte só para o fuso (o `ENV TZ` do Dockerfile, que o PR 15 já usa), conferida por teste estático (caso 21) e em execução (`date +%Z` = `-03` no CI). O caso 6 impede agendar perto da meia-noite.
- **D6. `scheduler` com o mesmo `build` do `jobs`, sem `image:` compartilhada.** Com `image:` igual nos dois serviços, o `up -d scheduler` tentaria puxar do registro uma imagem que só existe local (e o `jobs` está em profile). O compose constrói duas imagens a partir do mesmo Dockerfile; o segundo build sai inteiro do cache e as camadas são as mesmas, então o custo em disco e tempo é pequeno. O PR 37 (GHCR) unifica.
- **D7. `mem_limit: 512m`, igual ao `jobs`.** O job roda como processo filho do supercronic, dentro deste container; o pico estimado do job com pandas é 200–400 MB e o supercronic ocioso é da ordem de 10 MB. Soma dos limites sempre de pé: `health` 16m + `postgres` 256m + `scheduler` 512m = 784m, abaixo de 1 GB; um `run --rm jobs` simultâneo (mais 512m) passa de 1 GB e depende dos 2 GB de swap. O supercronic, por padrão, não sobrepõe execuções da mesma linha.
- **D8. Logs no stdout, sem redirecionamento.** `docker compose logs scheduler` é a única trilha até o PR 55; o caso 7 trava isso.
- **D9. Sem healthcheck nem porta no `scheduler`.** Não há o que sondar sem abrir porta (o endpoint de métricas do supercronic exigiria uma), e abrir porta é contra o ADR 0003. A vigilância é o `restart: unless-stopped` mais a checagem diária manual do item 17.
- **D10. Validação do crontab no CI com o próprio `scheduler`** (`supercronic -test` dentro do container construído pelo compose), em vez de um `docker build` separado: prova o binário, o checksum, o caminho do crontab e o serviço de uma vez.
- **D11. Mensagens e comentários em inglês** (ADR 0001); nome do serviço `scheduler` e do arquivo `infra/cron/crontab` como no ADR 0004 e na tabela do ADR 0001.
- **D12. Comandos registrados no `AGENTS.md`** neste PR, como os PRs anteriores.

Riscos:

- **R1. Falha silenciosa até o PR 55.** Falha de job só aparece em `docker compose logs scheduler`. O item 17 inclui a checagem diária manual e a regra de reexecutar no mesmo dia, antes da meia-noite em `America/Sao_Paulo`.
- **R2. Deploy durante o job.** `docker compose up -d` ou `build` às 06:30 pode matar o job no meio (o `stop` dá 10 s antes do `SIGKILL`). A gravação é numa transação, então nada fica pela metade, mas o dia precisa ser reexecutado à mão. ADR 0004 já manda não construir com job em execução; evite deploy entre 06:25 e 06:40.
- **R3. Build na VPS** (1 vCPU, 1 GB + swap) fica um pouco mais longo com o `apt-get` do `curl`; o layer do supercronic fica em cache depois do primeiro build.
- **R4. Asset ou release removida do GitHub.** O build passa a falhar (o checksum protege contra troca, não contra remoção). A imagem já construída na VPS continua rodando; o PR 37 tira essa dependência do build na VPS.
- **R5. Logs do Docker sem rotação.** O supercronic gera poucas linhas por dia, então o risco a 25 GB de disco é pequeno até o PR 36 remover o serviço; o vigia de disco é o PR 56.
- **R6. Formato da saída de `supercronic -test` e dos logs** pode variar entre versões; os critérios dependem só do código de saída e do estado `running`, não do texto.

Perguntas em aberto (não bloqueiam este PR):

- Nenhuma que bloqueie. O índice (`docs/plans/00-indice.md`, P3) ainda diz "Falta confirmar SO e arquitetura"; o dado (`x86_64`, Ubuntu 24.04) já é conhecido, e a atualização do índice fica para um PR só de `docs/**`, fora deste.

## 10. Decisões que exigem ADR

Nenhuma nova. O agendador supercronic, o `restart: unless-stopped`, o `mem_limit`, a ausência de porta e o checksum fixado já estão no ADR 0004 (aceito e mergeado). O PR não publica porta nem expõe serviço (ADR 0003), não muda `raw`/`ref` nem o contrato. Exigiria ADR novo: publicar qualquer porta do `scheduler` (por exemplo para métricas ou healthcheck HTTP) ou trocar o agendador interino por outro mecanismo.
