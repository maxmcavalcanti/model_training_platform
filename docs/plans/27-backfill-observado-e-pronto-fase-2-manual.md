# 27 — Deploy do `weather-observed`, backfill do clima observado desde 2015 e critério de pronto da Fase 2 (manual)

> Executa: **usuário** (VPS e Tailscale; agentes não têm acesso à VPS). Depende de: 17 (coleta da previsão ligada), 23 (Fase 1 em produção: migração `0006`, `ons-load` agendado), 24, 25 e 26 (na `main`: cliente `fetch_observed`, migração `0007`, job `weather-observed` e linha das 06:45 no crontab).
> Revisão 2026-11-08: alinhado à `main` em `2ffc2c8` (migrações até `0007`; jobs `weather-forecast`, `calendar`, `ons-load` e `weather-observed`; crontab com 06:30 `weather-forecast`, 06:45 `weather-observed` e 07:00 `ons-load`). Substitui a versão anterior deste plano, que não fazia deploy da `0007` antes do backfill, usava `--end $(date +%F)` (fuso do host, incluindo o dia corrente possivelmente parcial), não conferia continuidade nem `max(date)` e não tinha aviso à cientista nem tratamento de falhas. Incorpora os ajustes listados no plano 26, seção 9.

## 1. Objetivo

Levar a `main` (`0007` e `weather-observed` agendado às 06:45) à VPS, carregar `raw.weather_observed` de 2015-01-01 até ontem (BRT) e avisar a cientista.
Provar o critério de pronto da Fase 2 ("7 dias seguidos de snapshots sem falha") com consultas e logs concretos, sete dias depois do deploy.

## 2. Fora do escopo

- Qualquer mudança de código, crontab, compose ou migração (inclusive na VPS). Correção é PR na `main`.
- Fechar o item 18 (coleta em `/home/deploy/source-checks`) e ajustar os valores provisórios do observado (janela de 10 dias, atraso máximo de 7 dias, fim em ontem, horário 06:45) ou do ONS (07:00, 30 dias, 5 dias): PR próprio depois do item 18.
- Dividir o backfill por ano **no código** (plano 26, D7). Rodar o mesmo subcomando em pedaços pela CLI, só se o backfill inteiro falhar por timeout, está previsto em 5.10 e não muda código.
- Marcar os checkboxes da Fase 2 em `docs/plataforma-ml.md`, acrescentar `raw.weather_observed` em `docs/acesso-cientista.md` e a linha `weather-observed` em "Comandos" do `AGENTS.md`: PRs posteriores (passo 5.9). Este plano não edita nada disso.
- Checkpoint de memória da VPS (item 28a, Fase 3), backup (PR 57), alertas (PR 55), Prefect (PR 32).
- Credenciais, convite do Tailscale e cliente da cientista: ficam em `docs/acesso-cientista.md`.

## 3. Fase do roadmap

Fase 2 — "Clima" (`docs/plataforma-ml.md`, "Roadmap"):

> - [ ] `raw.weather_forecast` coletando todo dia (prioridade)
> - [ ] `raw.weather_observed` + backfill desde 2015
> - [ ] Pronto quando: 7 dias seguidos de snapshots sem falha

Este item entrega a evidência dos três. Os checkboxes são marcados depois, num PR só de `docs/**`.

## 4. Arquivos a criar ou alterar

**Nenhum arquivo do repositório.** Tudo acontece na VPS (`/opt/platform`, como `deploy`): imagens `platform-jobs` e `platform-scheduler`, schema do banco (`0006 → 0007`), container `scheduler` recriado e dados em `raw.weather_observed`.

### Por que é manual

Até o PR 39, atualizar a VPS é manual, por SSH pela tailnet: `git pull`, build da imagem na própria VPS e `docker compose up` (ADR 0004, `docs/adr/0004-interim-operation-before-prefect.md`). Trecho de `.claude/rules/infra.md`:

> Deploy só sai de merge na `main`. Nada de SSH manual para mudar produção. Exceção registrada até o PR 39 (ADR 0004): o usuário atualiza a VPS à mão, por SSH pela tailnet (ADR 0003), com `git pull` e `docker compose up`, e a imagem dos jobs é construída na própria VPS até o PR 37. Quem aplica esse deploy é o usuário, nunca um agente.

ADR 0004, sobre memória (1 vCPU, 1 GB de RAM, 2 GB de swap): "Não construir imagem com um job agendado em execução. Dois jobs ao mesmo tempo (por exemplo, backfill manual durante o job agendado) podem passar do `mem_limit`."

### O que está na `main` e este item usa

- **Migração `0007`** (`migrations/versions/0007_raw_weather_observed.py`, revisa `0006`): cria `raw.weather_observed`:

  ```sql
  CREATE TABLE raw.weather_observed (
      location_id text NOT NULL,
      "date" date NOT NULL,
      temp_max double precision,
      temp_min double precision,
      precip_mm double precision,
      wind_speed_max double precision,
      humidity_mean double precision,
      ingested_at timestamptz NOT NULL,
      CONSTRAINT weather_observed_pkey PRIMARY KEY (location_id, "date"),
      CONSTRAINT weather_observed_location_id_fkey
          FOREIGN KEY (location_id) REFERENCES ref.locations (location_id)
  )
  ```

  Permissões vêm dos privilégios padrão da `0002`: `scientist` e `reader` leem; `ingestor` tem `SELECT`, `INSERT`, `UPDATE` (o job reescreve a janela recente). `"date"` é o dia em `America/Sao_Paulo`; `ingested_at` é a última escrita (ADR 0005). A cabeça passa a ser `0007`. Em produção hoje: `0006`.
- **Subcomando `weather-observed`** (`ingestion/cli.py`, `ingestion/jobs.py`): `python -m ingestion weather-observed [--end <AAAA-MM-DD>] [--start <AAAA-MM-DD> | --days <n>]`.
  - Sem `--end`: **ontem** em `America/Sao_Paulo` (`issue_date() - OBSERVED_END_LAG_DAYS`, com `OBSERVED_END_LAG_DAYS = 1`). Sem `--start`: janela de `OBSERVED_WINDOW_DAYS = 10` dias terminando em `--end`. Intervalo com mais de 10 dias usa timeout HTTP de 120 s; até 10 dias, 30 s.
  - Uma requisição por local (4 locais de `ref.locations`: `belem`, `porto_alegre`, `recife`, `sao_paulo`) ao arquivo ERA5 do Open-Meteo para o intervalo inteiro; 3 tentativas com espera de 1 s e 2 s só para erro de rede, 429 e 5xx. Dias com as 5 variáveis nulas são descartados pelo cliente.
  - Upsert (`on_conflict="update"`) em `raw.weather_observed`, **commit antes da checagem**, releitura do intervalo e `check_weather_observed`: faixas (temperaturas −10 a 50 °C, `precip_mm >= 0`, `wind_speed_max >= 0`, `humidity_mean` 0 a 100), `temp_min <= temp_max`, chave única, e por local: `no rows between <start> and <end>`, `missing dates: ...` (de `--start` até a maior data do local) e `stale: last date <d> is older than <end - 7>` (`OBSERVED_MAX_DELAY_DAYS = 7`).
  - Falha num local não para os outros: grava o que veio e termina com `PartialIngestionError` (`observed weather failed for locations: ...`).
  - Log de sucesso: `weather-observed ok: <n locais> locations, <n> rows written from <start> to <end>`. Erro por local: `observed weather failed for <id>: <erro>`. Falha do subcomando: `subcommand weather-observed failed` (com traceback).
  - Códigos de saída: `0` sucesso, `1` falha de execução ou de checagem, `2` uso incorreto.
- **Logs dos outros jobs** (para conferir no `scheduler`): `weather-forecast ok: 4 locations, 28 rows inserted, 0 already existed`; `ons-load ok: <n> rows written from <start> to <end>, last date <d>`.
- **`infra/cron/crontab`** (embutido na imagem em `/app/infra/cron/crontab`; horários em `America/Sao_Paulo`):

  ```
  30 6 * * * python -m ingestion weather-forecast
  45 6 * * * python -m ingestion weather-observed
  0 7 * * * python -m ingestion ons-load
  ```

- **`infra/docker-compose.yml`**: `scheduler` e `jobs` usam o mesmo `infra/jobs/Dockerfile`, mas cada um tem a sua imagem (nenhum declara `image:`). `dc build jobs` sozinho não atualiza o `scheduler`, e `dc up -d scheduler` reaproveita a imagem antiga se ela existir. Por isso o build é dos dois. Ambos com `mem_limit: 512m`; o `scheduler` divide esse limite entre o supercronic e o job que ele dispara.
- **Item 18 em andamento:** a coleta de verificação das fontes (cron do usuário `deploy`, fora do compose) grava em `/home/deploy/source-checks` desde 2026-11-08. Ela faz poucas chamadas `curl` ao ONS e ao Open-Meteo, não usa o banco nem os containers e **não conflita** com este item. Não a pare nem a altere aqui.

## 5. Passos

### Regras deste item

- Não rodar build, backfill, `dc up -d scheduler` nem o modo diário à mão entre **06:25 e 07:15 BRT**: os jobs agendados rodam às 06:30, 06:45 e 07:00, e dois jobs ao mesmo tempo podem passar do `mem_limit` (ADR 0004). Confira com `TZ=America/Sao_Paulo date '+%F %H:%M'`.
- Nunca rodar o backfill durante um `dc build` (nem o contrário): um de cada vez.
- Nunca `dc down -v` nem `docker volume rm platform_pgdata`: o histórico de `raw.weather_forecast` não volta e ainda não há backup (PR 57).
- Nunca `alembic downgrade` em produção (a `0007` apagaria a tabela).
- Nunca `dc config` sem `-q` (imprime as senhas). Para validar o compose: `dc config -q && echo ok`.
- Não editar código, crontab ou compose na VPS. Não ler nem imprimir `infra/.env`.
- Não recriar nem reiniciar o `scheduler` depois do passo 5.4 até o passo 5.8 (D+7): o log do container é a evidência de "sem falha" e some quando o container é recriado.

### Bloco inicial de toda sessão SSH

Na VPS, como `deploy` (`ssh deploy@<host>.<tailnet>.ts.net`). **Toda sessão SSH nova** começa com este bloco (a função `dc` e o atalho `q` não sobrevivem entre sessões):

```bash
cd /opt/platform
dc() { docker compose -f /opt/platform/infra/docker-compose.yml "$@"; }
q() { dc exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -q -A -t -F "|" -v ON_ERROR_STOP=1'; }
```

`q` roda o `psql` dentro do container do Postgres como admin, pelo socket local, sem digitar senha; o SQL entra pelo stdin (`q <<'SQL' ... SQL`), sem escape de aspas. Saída sem cabeçalho, colunas separadas por `|`. As consultas usam `(now() at time zone 'America/Sao_Paulo')::date` para "hoje" em Brasília, porque o servidor do Postgres está em UTC e `current_date` vira o dia seguinte depois das 21:00 BRT.

Para saber se algum job agendado está rodando agora (use antes de build, backfill e recriação):

```bash
dc top scheduler | grep -c 'python -m ingestion'
```

→ `0`. Se der `1` ou mais, espere o job terminar e confira de novo.

### 5.1. Ponto de partida

- [ ] Hora fora da janela proibida:

  ```bash
  TZ=America/Sao_Paulo date '+%F %H:%M'
  ```

  → uma hora fora de 06:25–07:15.

- [ ] Serviços no ar e banco saudável:

  ```bash
  dc ps --format '{{.Service}} {{.Status}}'
  ```

  → `health Up ... (healthy)`, `postgres Up ... (healthy)` e `scheduler Up ...`.

- [ ] Nenhum job rodando: o comando `dc top scheduler | grep -c ...` do bloco inicial → `0`.
- [ ] Coleta da previsão em dia e desde quando ela existe:

  ```bash
  q <<'SQL'
  select min(issued_at), max(issued_at), count(distinct issued_at) from raw.weather_forecast;
  select issued_at, count(*) from raw.weather_forecast
  where issued_at > (now() at time zone 'America/Sao_Paulo')::date - 8 group by 1 order by 1;
  SQL
  ```

  → primeira linha: início da coleta (item 17), último snapshot e número de dias; anote o início. Depois, uma linha por dia, cada uma com `28`, a última com a data de hoje se já passou das 06:30 BRT.

- [ ] ONS em dia (Fase 1 continua valendo):

  ```bash
  q <<'SQL'
  select max("date"), max(ingested_at) from raw.ons_daily_load;
  SQL
  ```

  → última data no máximo 5 dias antes de hoje; `max(ingested_at)` de hoje por volta das 10:00 UTC (07:00 BRT), se já passou das 07:00.

- [ ] Espaço e memória:

  ```bash
  df -h / && free -m
  ```

  → pelo menos 2 GB livres em `/` (build de duas imagens). Anote a coluna `available` do `free -m`.

### 5.2. Atualizar o código e construir as imagens

- [ ] Puxar a `main`:

  ```bash
  git pull --ff-only && git log -1 --oneline
  ```

  → `2ffc2c8 chore: enable the ruff S rule with justified ignores (#45)` ou um commit mais novo da `main`. Se o `git pull` reclamar de mudança local, pare: ninguém edita código na VPS; devolva para o planejamento com `git status`.

- [ ] O crontab do repositório tem as três linhas:

  ```bash
  grep -v '^#' infra/cron/crontab
  ```

  →

  ```
  30 6 * * * python -m ingestion weather-forecast
  45 6 * * * python -m ingestion weather-observed
  0 7 * * * python -m ingestion ons-load
  ```

- [ ] Hora fora de 06:25–07:15 e nenhum job rodando (bloco inicial). Construir as duas imagens (lento em 1 vCPU; pode usar swap):

  ```bash
  dc build jobs scheduler
  ```

  → termina sem erro, com `jobs Built` e `scheduler Built` (o texto exato varia com a versão do compose).

- [ ] Imagens novas:

  ```bash
  docker image ls --format '{{.Repository}} {{.CreatedSince}}' | grep '^platform-'
  ```

  → `platform-jobs` e `platform-scheduler`, ambas criadas há poucos minutos.

- [ ] A imagem dos jobs conhece a migração e o subcomando novos:

  ```bash
  dc run --rm -T jobs alembic heads
  dc run --rm -T jobs python -m ingestion --help
  dc run --rm -T jobs python -m ingestion weather-observed --help
  ```

  → `0007 (head)`; o help geral lista `weather-forecast`, `calendar`, `ons-load` e `weather-observed`; o do `weather-observed` lista `--end`, `--start` e `--days`, com `default yesterday` no `--end`.

### 5.3. Migrar (`0006 → 0007`)

- [ ] Estado antes:

  ```bash
  dc run --rm -T jobs alembic current
  ```

  → última linha `0006` (sem `(head)`, porque a imagem nova já conhece a `0007`). Se aparecer outro número, pare e devolva para o planejamento.

- [ ] Aplicar:

  ```bash
  dc run --rm -T jobs alembic upgrade head; echo "exit=$?"
  ```

  → uma linha `Running upgrade 0006 -> 0007, raw_weather_observed`; e `exit=0`.

- [ ] Só depois do `exit=0`, estado depois:

  ```bash
  dc run --rm -T jobs alembic current
  ```

  → última linha `0007 (head)`.

- [ ] Tabela nova vazia, permissões padrão e chave estrangeira:

  ```bash
  q <<'SQL'
  select count(*) from raw.weather_observed;
  select has_table_privilege('scientist', 'raw.weather_observed', 'SELECT'),
         has_table_privilege('scientist', 'raw.weather_observed', 'INSERT'),
         has_table_privilege('reader', 'raw.weather_observed', 'SELECT'),
         has_table_privilege('ingestor', 'raw.weather_observed', 'INSERT'),
         has_table_privilege('ingestor', 'raw.weather_observed', 'UPDATE'),
         has_table_privilege('ingestor', 'raw.weather_observed', 'DELETE');
  select conname from pg_constraint where conrelid = 'raw.weather_observed'::regclass order by 1;
  SQL
  ```

  →

  ```
  0
  t|f|t|t|t|f
  weather_observed_location_id_fkey
  weather_observed_pkey
  ```

### 5.4. Recriar o agendador com o crontab novo

- [ ] Hora fora de 06:25–07:15 e nenhum job rodando (bloco inicial). Então:

  ```bash
  dc up -d scheduler
  ```

  → `Container platform-scheduler-1  Recreated` e `Started` (o compose recria porque a imagem mudou no 5.2).

- [ ] O container em execução tem as três linhas:

  ```bash
  dc exec -T scheduler grep -v '^#' /app/infra/cron/crontab
  ```

  → as três linhas do 5.2. Se faltar a do `weather-observed`, a imagem do `scheduler` não foi reconstruída: `dc build scheduler && dc up -d scheduler` (fora da janela) e confira de novo.

- [ ] O supercronic leu o arquivo sem erro:

  ```bash
  dc logs --since 5m scheduler
  ```

  → uma linha com `read crontab: /app/infra/cron/crontab` e nenhuma com `level=error` ou `level=fatal`.

- [ ] Anote o momento da recriação (é o dia **D** deste plano; o passo 5.8 acontece em D+7):

  ```bash
  docker inspect -f '{{.State.StartedAt}} restarts={{.RestartCount}}' "$(dc ps -q scheduler)"
  ```

  → data e hora de agora, em UTC, e `restarts=0`.

### 5.5. Backfill do observado (2015-01-01 até ontem)

- [ ] Hora fora de 06:25–07:15, nenhum job rodando e nenhum build em andamento. Fixe "ontem" no fuso do job (só para conferir; o comando do backfill **não** recebe `--end`):

  ```bash
  YESTERDAY=$(TZ=America/Sao_Paulo date -d yesterday +%F); echo "$YESTERDAY"
  ```

  → a data de ontem em Brasília. `TZ=America/Sao_Paulo` porque o relógio da VPS pode estar em UTC.

- [ ] Rodar o backfill (4 requisições, uma por local, cada uma com ~4330 dias; timeout de 120 s por requisição):

  ```bash
  time dc run --rm -T jobs python -m ingestion weather-observed --start 2015-01-01; echo "exit=$?"
  ```

  → no log, `weather-observed ok: 4 locations, <n> rows written from 2015-01-01 to <ontem>`, com `<ontem>` igual a `$YESTERDAY` e `<n>` = 4 × (dias de 2015-01-01 até ontem, inclusive); e `exit=0`. Exemplo: com ontem = `2026-11-08`, são 4330 dias por local e `<n>` = `17320`. Anote `<n>` e o tempo `real` do `time` (insumo do item 18 e do 28a). Se der `exit=1`, veja 5.10.

  Não use `--end $(date +%F)`: incluiria o dia corrente, possivelmente parcial, e `date` usa o fuso do host.

### 5.6. Verificar o backfill

- [ ] Por local: início, fim, contagem e continuidade:

  ```bash
  q <<'SQL'
  select location_id, min("date"), max("date"), count(*),
         max("date") - min("date") + 1 as expected,
         max("date") = (now() at time zone 'America/Sao_Paulo')::date - 1 as ends_yesterday
  from raw.weather_observed group by 1 order by 1;
  SQL
  ```

  → exatamente 4 linhas, na ordem `belem`, `porto_alegre`, `recife`, `sao_paulo`; em todas, `min` = `2015-01-01`, `max` = ontem (BRT), `count` = `expected` (igual nas 4) e `ends_yesterday` = `t`. Exemplo com ontem = `2026-11-08`: cada linha termina em `|2015-01-01|2026-11-08|4330|4330|t`.

- [ ] Contagem total:

  ```bash
  q <<'SQL'
  select count(*), 4 * ((now() at time zone 'America/Sao_Paulo')::date - 1 - date '2015-01-01' + 1) as expected
  from raw.weather_observed;
  SQL
  ```

  → os dois números iguais (= `<n>` do 5.5; com ontem = `2026-11-08`, `17320|17320`).

- [ ] Datas faltando por local (deve ser vazio):

  ```bash
  q <<'SQL'
  select l.location_id, g::date
  from ref.locations l
  cross join generate_series(date '2015-01-01', (now() at time zone 'America/Sao_Paulo')::date - 1, interval '1 day') as g
  except
  select location_id, "date" from raw.weather_observed
  order by 1, 2;
  SQL
  ```

  → nenhuma linha.

- [ ] Por ano:

  ```bash
  q <<'SQL'
  select extract(year from "date")::int as year, count(*), count(distinct "date")
  from raw.weather_observed group by 1 order by 1;
  SQL
  ```

  → 12 linhas:

  ```
  2015|1460|365
  2016|1464|366
  2017|1460|365
  2018|1460|365
  2019|1460|365
  2020|1464|366
  2021|1460|365
  2022|1460|365
  2023|1460|365
  2024|1464|366
  2025|1460|365
  2026|<4 × N>|<N>
  ```

  2026 é ano parcial: `N` = dias de 2026-01-01 até ontem, inclusive (com ontem = `2026-11-08`, `N` = 312 e a linha é `2026|1248|312`).

- [ ] `ingested_at`, nulos e plausibilidade:

  ```bash
  q <<'SQL'
  select count(*) filter (where ingested_at is null),
         count(*) filter (where temp_max is null), count(*) filter (where temp_min is null),
         count(*) filter (where precip_mm is null), count(*) filter (where wind_speed_max is null),
         count(*) filter (where humidity_mean is null)
  from raw.weather_observed;
  select location_id,
         round(min(temp_min)::numeric, 1), round(avg(temp_max)::numeric, 1), round(max(temp_max)::numeric, 1),
         round((sum(precip_mm) / count(distinct extract(year from "date")))::numeric) as precip_per_year,
         round(avg(humidity_mean)::numeric), round(max(wind_speed_max)::numeric)
  from raw.weather_observed where "date" < date '2026-01-01' group by 1 order by 1;
  SQL
  ```

  → primeira linha começando com `0|` (nenhum `ingested_at` nulo); anote os nulos por variável (o esperado é `0` em todas; nulo parcial é permitido, mas anote). Depois 4 linhas (anos completos 2015–2025): anote os números. Esperado, não bloqueante: `porto_alegre` com o menor `min(temp_min)`, `belem` com a maior umidade média, nenhum valor fora das faixas (a checagem do job já barra). Se algo parecer absurdo, anote e devolva para o planejamento, sem apagar nada.

- [ ] Cruzamento com a previsão (só informativo; mede a diferença de grade e de horizonte):

  ```bash
  q <<'SQL'
  select f.location_id, count(*), round(avg(abs(f.temp_max - o.temp_max))::numeric, 1)
  from raw.weather_forecast f
  join raw.weather_observed o on o.location_id = f.location_id and o."date" = f.target_date
  where f.horizon_days = 1
  group by 1 order by 1;
  SQL
  ```

  → até 4 linhas (uma por local com previsão já vencida); anote a diferença média de `temp_max` (em °C). Sem linhas é normal se a coleta da previsão começou há menos de 2 dias.

- [ ] Idempotência e o modo diário (sem argumentos, janela de 10 dias até ontem, como o agendador roda). Hora fora de 06:25–07:15:

  ```bash
  q <<'SQL'
  select count(*) from raw.weather_observed;
  SQL
  dc run --rm -T jobs python -m ingestion weather-observed; echo "exit=$?"
  q <<'SQL'
  select count(*), max("date") from raw.weather_observed;
  select count(*), min("date"), max("date") from raw.weather_observed
  where ingested_at > now() - interval '5 minutes';
  SQL
  ```

  → `exit=0`; o log diz `weather-observed ok: 4 locations, 40 rows written from <hoje − 10> to <ontem>`; a contagem total não muda e `max` continua ontem; as linhas reescritas agora são `40|<hoje − 10>|<ontem>`.

### 5.7. No dia seguinte (D+1), depois das 06:50 BRT

- [ ] O `weather-observed` agendado terminou bem (e, depois das 07:15, os outros dois):

  ```bash
  dc logs --since 3h scheduler | grep -E 'weather-forecast ok|weather-observed ok|ons-load ok|failed|level=error'
  ```

  → uma linha `weather-forecast ok: 4 locations, 28 rows inserted, 0 already existed` (≈ 06:30), uma `weather-observed ok: 4 locations, 40 rows written from <hoje − 10> to <ontem>` (≈ 06:45) e, se já passou das 07:15, uma `ons-load ok: ...` (≈ 07:00); nenhuma linha com `failed` ou `level=error`.

- [ ] O banco reflete a execução agendada do observado:

  ```bash
  q <<'SQL'
  select count(*), min("date"), max("date") from raw.weather_observed
  where (ingested_at at time zone 'America/Sao_Paulo')::date = (now() at time zone 'America/Sao_Paulo')::date;
  select location_id, max("date") from raw.weather_observed group by 1 order by 1;
  SQL
  ```

  → `40|<hoje − 10>|<ontem>` (se você não rodou nada à mão hoje); depois 4 linhas com `max` = ontem.

- [ ] Coleta do item 18 seguindo (só conferir que não parou):

  ```bash
  ls -lt /home/deploy/source-checks | head
  ```

  → arquivos com data de hoje.

- [ ] Enviar à cientista o aviso de 5.11 (pode ser já no fim do 5.6, se tudo bateu; recomendado não esperar a Fase 2 fechar, pergunta 3 da seção 9).

### 5.8. Prova de pronto da Fase 2 (dia D+7, depois das 07:15 BRT)

"7 dias seguidos de snapshots sem falha" vira: nos 7 dias de D+1 a D+7, o `weather-forecast` agendado gravou 28 linhas (4 locais × horizontes 1 a 7) em cada dia, e o log do `scheduler`, que roda sem recriação desde D, mostra 7 sucessos e nenhuma falha. O mesmo vale para o `weather-observed` (pergunta 2 da seção 9).

- [ ] O `scheduler` não foi recriado nem reiniciado desde D:

  ```bash
  docker inspect -f '{{.State.StartedAt}} restarts={{.RestartCount}}' "$(dc ps -q scheduler)"
  ```

  → o mesmo `StartedAt` anotado no 5.4 e `restarts=0`. Se mudou, a janela de 7 dias recomeça do novo `StartedAt` (ver 5.10).

- [ ] Snapshots dos últimos 7 dias, completos e consecutivos:

  ```bash
  q <<'SQL'
  select issued_at, count(*), count(distinct location_id), min(horizon_days), max(horizon_days)
  from raw.weather_forecast
  where issued_at between (now() at time zone 'America/Sao_Paulo')::date - 6
                      and (now() at time zone 'America/Sao_Paulo')::date
  group by 1 order by 1;
  SQL
  ```

  → exatamente 7 linhas, de hoje − 6 (= D+1) a hoje (= D+7), sem pular dia, cada uma terminando em `|28|4|1|7`.

- [ ] Nenhum snapshot incompleto e nenhum dia sem snapshot desde o início da coleta:

  ```bash
  q <<'SQL'
  select count(*) from (select issued_at from raw.weather_forecast group by 1 having count(*) <> 28) x;
  select g::date
  from generate_series((select min(issued_at) from raw.weather_forecast),
                       (now() at time zone 'America/Sao_Paulo')::date, interval '1 day') as g
  except select issued_at from raw.weather_forecast
  order by 1;
  SQL
  ```

  → `0`; depois nenhuma linha. Um dia listado aqui fora dos últimos 7 não bloqueia a fase, mas é histórico perdido: anote as datas.

- [ ] Log dos 7 dias:

  ```bash
  dc logs --since 168h scheduler | grep -c 'weather-forecast ok'
  dc logs --since 168h scheduler | grep -c 'weather-observed ok'
  dc logs --since 168h scheduler | grep -c 'ons-load ok'
  dc logs --since 168h scheduler | grep -E 'failed|level=error|level=fatal'
  ```

  → `7`, `7`, `7` e nenhuma linha. O `ons-load` é da Fase 1 e não bloqueia a Fase 2: se ele tiver falhado (por exemplo `stale` num dia útil), anote para o item 18.

- [ ] Observado em dia:

  ```bash
  q <<'SQL'
  select location_id, min("date"), max("date"), count(*), max("date") - min("date") + 1
  from raw.weather_observed group by 1 order by 1;
  SQL
  ```

  → 4 linhas com `min` = `2015-01-01`, `max` = ontem e `count` igual à última coluna.

- [ ] Se tudo bateu, a Fase 2 está pronta: anote a data (D+7) e os números (dias de previsão, linhas do observado por local, `max(date)`). Eles vão no PR de docs do 5.9.

### 5.9. Depois (não faz parte deste plano)

- PR só de `docs/**`: marcar os três checkboxes da Fase 2 em `docs/plataforma-ml.md` com data e números (como o item do ONS na Fase 1) e acrescentar `raw.weather_observed` na tabela de `docs/acesso-cientista.md`, apontando para o aviso de 5.11. Dispensa revisores de agente.
- PR que toca `AGENTS.md` (linha `weather-observed` em "Comandos"): não é só `docs/**`, passa pelo `code-reviewer` e pelo `pr-reviewer`.
- Ajuste dos valores provisórios depois do item 18: PR próprio.

### 5.10. Se algo falhar

Não mexa em código, crontab ou compose na VPS. Guarde o log (`... 2>&1 | tee /tmp/<nome>.log`) e devolva para o planejamento quando indicado.

- **`dc build` falha ou é morto por falta de memória:** `free -m`, confira que nenhum job está rodando (bloco inicial) e tente uma vez de novo. Se repetir, devolva com o log.
- **`alembic upgrade head` falha:** a migração roda numa transação; `alembic current` continua `0006`. Devolva com o log. Não rode `downgrade`. Não siga para o 5.4 (o job novo agendado falharia sem a tabela).
- **O `scheduler` recriado não tem a linha `weather-observed`:** imagem antiga. `dc build scheduler && dc up -d scheduler` (fora da janela) e repita o 5.4, anotando o novo `StartedAt`.
- **Backfill sai com `exit=1`.** O upsert grava antes da checagem: pode haver linhas gravadas mesmo com falha, e rodar de novo é seguro (upsert por chave). Pela mensagem:
  - `observed weather failed for <id>: ...` com `NetworkError`, `ReadTimeout` ou HTTP 5xx/429: espere alguns minutos e rode o mesmo comando do 5.5 uma vez. Se repetir por timeout, rode em pedaços pela CLI, um de cada vez, fora da janela: `--start 2015-01-01 --end 2018-12-31`, `--start 2019-01-01 --end 2022-12-31` e, por último, `--start 2023-01-01` (sem `--end`). Cada pedaço passa pela mesma checagem. Depois, repita o 5.6 inteiro e anote, para o PR de docs do 5.9, que o backfill precisou de pedaços (pergunta 5 da seção 9).
  - `observed weather failed for <id>: <id>: ...` com unidade, `time` malformado, dias faltando na resposta ou `non-numeric value`: a API mudou o formato. Devolva com o log.
  - HTTP 4xx que não seja 429 (sem retry): devolva com o log; não tente outros intervalos.
  - `<id>: missing dates: ...`: a fonte devolveu dias inteiramente nulos no meio do histórico. Devolva com o log e a lista de datas; uma lacuna conhecida só entra por PR com teste. Não rode as consultas de pronto como se estivessem certas.
  - `<id>: stale: last date <d> is older than <limite>`: o arquivo está atrasado mais de 7 dias. Confira `select location_id, max("date") from raw.weather_observed group by 1;`, anote para o item 18 e rode o modo diário no dia seguinte; se repetir, devolva.
  - `schema validation failed ... temp_max: ...` (ou outra coluna) ou `temp_min must not exceed temp_max`: valor fora da faixa gravado. Devolva com o log e a linha (`select * from raw.weather_observed where temp_max > 50 or temp_min < -10 or temp_min > temp_max;`). Não apague nada.
  - Morto sem mensagem (`exit=137`): falta de memória. Confira que nenhum job agendado estava rodando e tente uma vez; se repetir, devolva com `free -m`.
- **`max(date)` do 5.6 é anterior a ontem (de 1 a 7 dias) e o job deu `exit=0`:** a fonte ainda não publicou os dias mais recentes. Não é falha; anote os dias de atraso por local para o item 18 e confira de novo no 5.7 (a janela diária preenche).
- **No D+1, `weather-observed` falhou no agendador:** rode o modo diário à mão (`dc run --rm -T jobs python -m ingestion weather-observed; echo "exit=$?"`) fora da janela e siga os casos acima. Uma falha conta contra o "sem falha" da Fase 2 (pergunta 2 da seção 9): a janela de 7 dias recomeça no dia seguinte ao da falha.
- **No 5.8, faltou um snapshot da previsão ou houve `failed` no log:** a janela de 7 dias recomeça no dia seguinte ao da falha; repita o 5.8 sete dias depois. Se o dia sem snapshot é de hoje ou ontem e o job não falhou no log, confira `dc ps` (o `scheduler` pode ter caído) e devolva com `dc logs --since 48h scheduler`.
- **O `scheduler` foi recriado ou reiniciado entre D e D+7** (reboot, deploy de outro PR): o log anterior se perde (recriação) ou fica incompleto. A janela de 7 dias recomeça do novo `StartedAt`. Evite deploys na VPS nesse período.

### 5.11. Aviso à cientista

A regra exige aviso para mudança em `raw` (`AGENTS.md`, "Fronteira"). Este aviso junta os dos planos 24 (seção 9) e 25 (seção 9). Texto pronto para enviar (ajuste o tom; o conteúdo é o mínimo):

> **Nova tabela: `raw.weather_observed` (clima observado, desde 2015-01-01).** Mesmo banco `ml`, mesmo papel `scientist`, só leitura. O acesso continua como no documento que te mandei.
>
> - Uma linha por local por dia, para as 4 capitais de `ref.locations` (`belem`, `porto_alegre`, `recife`, `sao_paulo`), de 2015-01-01 até **ontem**. Chave (`location_id`, `date`). Colunas: `location_id`, `date`, `temp_max`, `temp_min`, `precip_mm`, `wind_speed_max`, `humidity_mean`, `ingested_at`.
> - Mesmas variáveis e unidades de `raw.weather_forecast`: `temp_max` e `temp_min` em **°C** (a 2 m), `precip_mm` em **mm** (soma do dia), `wind_speed_max` em **km/h** (máxima a 10 m), `humidity_mean` em **%** (média a 2 m). `date` é o dia em `America/Sao_Paulo`.
> - **Fonte:** reanálise ERA5 pelo arquivo do Open-Meteo. É o valor de uma **célula de grade de ~25 km (0,25°)**, não de uma estação meteorológica. Essa célula **não é a mesma** da previsão (a previsão vem de outra grade; para São Paulo, por exemplo, a previsão responde pelo ponto -23.51, -46.61 para o ponto pedido -23.55, -46.63, e o arquivo responde por outro). Parte da diferença entre previsão e observado vem disso, não só do erro da previsão.
> - **Valores recentes podem mudar.** Todo dia às 06:45 o job reescreve os últimos 10 dias (até ontem; o dia corrente nunca entra). Os dias mais recentes podem não ser o valor final da reanálise e são **sobrescritos** quando a fonte corrige; não há versões. `ingested_at` é o momento da **última** escrita da linha, não da primeira. Para reprodutibilidade, congele o recorte em `features` ou registre a data da extração. A janela de 10 dias e o atraso tolerado (7 dias) são provisórios: estou medindo atraso e revisões da fonte e aviso se mudarem.
> - Uma variável pode vir nula num dia (nulo parcial). Dia em que a fonte não tem nenhuma das cinco variáveis não tem linha.
> - Para comparar previsão e observado: `JOIN raw.weather_forecast f ON f.location_id = o.location_id AND f.target_date = o."date"`. Para não vazar informação, numa previsão feita em D use só observado com `date < D`.
> - O que já valia para `ref.calendar`, `raw.ons_daily_load` e `raw.weather_forecast` continua no aviso anterior (`docs/plans/23-backfill-ons-e-pronto-fase-1-manual.md`, "Aviso à cientista").
>
> Mudanças de schema em `raw` e `ref` só acontecem com migração, registro de decisão e aviso a você.

## 6. Critérios de pronto

Todos na VPS, com o bloco inicial carregado, salvo indicação.

| Quando | Comando | Saída esperada |
| --- | --- | --- |
| D | `dc run --rm -T jobs alembic current` | `0007 (head)` |
| D | `dc exec -T scheduler grep -v '^#' /app/infra/cron/crontab` | as 3 linhas: `30 6 ... weather-forecast`, `45 6 ... weather-observed`, `0 7 ... ons-load` |
| D | `time dc run --rm -T jobs python -m ingestion weather-observed --start 2015-01-01; echo "exit=$?"` | `weather-observed ok: 4 locations, <4 × dias> rows written from 2015-01-01 to <ontem>` e `exit=0` |
| D | consulta por local do 5.6 | 4 linhas, `min` = `2015-01-01`, `max` = ontem, `count` = `expected`, `ends_yesterday` = `t` |
| D | consulta de datas faltando do 5.6 | nenhuma linha |
| D | consulta por ano do 5.6 | `2015\|1460\|365`; `2016`, `2020` e `2024` com `1464\|366`; os outros anos completos com `1460\|365`; 2026 parcial com `4 × N\|N` |
| D | modo diário do 5.6 (`weather-observed` sem argumentos) | `exit=0`; `40 rows written from <hoje − 10> to <ontem>`; contagem total inalterada |
| D+1, depois das 06:50 | `dc logs --since 3h scheduler \| grep -E 'weather-observed ok\|failed\|level=error'` | uma linha `weather-observed ok: 4 locations, 40 rows written ...`; nenhuma `failed` ou `level=error` |
| D+7, depois das 07:15 | `docker inspect -f '{{.State.StartedAt}} restarts={{.RestartCount}}' "$(dc ps -q scheduler)"` | o `StartedAt` de D e `restarts=0` |
| D+7 | consulta dos 7 snapshots do 5.8 | 7 linhas consecutivas terminando hoje, cada uma `\|28\|4\|1\|7` |
| D+7 | `dc logs --since 168h scheduler \| grep -c 'weather-forecast ok'` e `... grep -c 'weather-observed ok'` | `7` e `7` |
| D+7 | `dc logs --since 168h scheduler \| grep -E 'failed\|level=error\|level=fatal'` | nenhuma linha |
| Fora da VPS | aviso de 5.11 enviado | data do envio anotada |

## 7. Testes necessários

`não`: procedimento manual na VPS (deploy, migração já testada no CI, backfill e verificação); nenhuma mudança de código ou de comportamento no repositório.

## 8. Casos de teste

n/a

## 9. Riscos e perguntas em aberto

Riscos:

- **Backfill concorrendo com job agendado ou build** pode passar do `mem_limit` de 512 MB (ADR 0004). Mitigação: janela proibida 06:25–07:15, `dc top scheduler` antes, um comando pesado por vez.
- **Timeout no backfill** (4 respostas grandes, 120 s cada, sem divisão no código, plano 26 D7). Mitigação: retry automático de rede e, se repetir, pedaços pela CLI (5.10).
- **Dias recentes não finais ou atrasados** no ERA5 do Open-Meteo: `max(date)` pode ficar antes de ontem ou valores podem mudar; é o motivo da janela diária de 10 dias com `update`. Os números do item 18 decidem os valores definitivos.
- **Perda do log do `scheduler`** se o container for recriado entre D e D+7 (deploy de outro PR; os itens S da segurança em CI não precisam de deploy na VPS): a prova de "sem falha" recomeça.
- **`docker logs` sem rotação configurada** no compose: o log do `scheduler` cresce sem limite. Pequeno (algumas linhas por dia); fica para quando houver `logging:` no compose (fora deste item).
- **Item 18 rodando em paralelo:** não conflita (cron do host, só `curl`, sem banco); não pare a coleta.

Perguntas em aberto (com recomendação; o usuário aceita as recomendações salvo objeção):

1. **Quando provar a Fase 2: imediatamente com o histórico do banco ou em D+7?** O banco pode já ter 7 dias de previsão desde o item 17, mas o log anterior a D se perde na recriação do `scheduler`, e "sem falha" não se prova só pelo banco (uma execução manual de recuperação também grava 28 linhas). **Recomendação:** provar em D+7, com banco e log juntos (5.8), o que também cobre 7 execuções agendadas do `weather-observed`.
2. **O "sem falha" inclui o `weather-observed` e o `ons-load`?** O roadmap fala em "snapshots" (previsão). **Recomendação:** bloqueiam a fase a previsão e o observado (os dois são da Fase 2); o `ons-load` é da Fase 1 e só é anotado (falha `stale` é insumo do item 18).
3. **Mandar o aviso à cientista já no D (depois do 5.6) ou só ao fechar a Fase 2?** **Recomendação:** no D, depois que o 5.6 bater: o dado está pronto para explorar e a regra pede aviso junto da mudança em `raw`.
4. **O aviso do plano 23 (Fase 1) já foi enviado?** A memória do projeto registra o envio como pendente em 2026-11-08. **Recomendação:** se não foi, envie os dois juntos (o de 5.11 aponta para o do plano 23); se já foi, envie só o de 5.11.
5. **Backfill em pedaços se der timeout: aceitar sem PR?** Rodar o mesmo subcomando com intervalos menores não muda código nem comportamento (o plano 26, D7, proíbe dividir **no código** sem combinar). **Recomendação:** aceitar como fallback manual, registrando no PR de docs do 5.9 que foi necessário; se o diário também der timeout, aí sim PR.
6. **Data de início da coleta da previsão (item 17).** O plano não sabe a data exata; o 5.1 a obtém (`min(issued_at)`). **Recomendação:** anotar no PR de docs do 5.9 junto com os números da Fase 2.

## 10. Decisões que exigem ADR

- **Nenhuma.** O item aplica, pelo procedimento interino do ADR 0004, uma migração (`0007`) e um job já revisados e mergeados (planos 25 e 26), cobertos pelo ADR 0005. Não muda schema além do que está na `main`, não muda o contrato `build_features`/`predict`/`evaluate`, não publica porta nem expõe serviço (ADR 0003) e não adiciona dependência.
- Passaria a exigir ADR: qualquer correção que mude `raw.weather_observed` (coluna de origem do dado, versões das revisões, chave, unidades ou fuso de `date`), que exigiria também migração e novo aviso.
