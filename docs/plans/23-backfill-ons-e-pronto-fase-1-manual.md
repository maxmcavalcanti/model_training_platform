# 23 — Backfill do ONS desde 2015, calendário e critério de pronto da Fase 1 (manual)

> Executa: **usuário** (VPS e Tailscale; agentes não têm acesso à VPS). Depende de: 12, 17, 19, 20, 21, 22 e da correção das lacunas da fonte (`docs/plans/2026-11-08-ons-source-gaps.md`, PR #35), todos na `main` (`main` em `0eae535`).
> Fase do roadmap: Fase 1 — "Banco e carga do ONS": itens "`ref.locations`, `ref.calendar`", "Ingestão do ONS + backfill desde 2015 + checagens" e "Pronto quando: ela consulta `raw.ons_daily_load` do notebook dela via Tailscale" (`docs/plataforma-ml.md`, "Roadmap").
> Revisão 2026-11-08: alinhado à `main` em `0eae535` (migrações até `0006`, jobs `weather-forecast`, `calendar` e `ons-load`, crontab com `ons-load` às 07:00, lacunas conhecidas toleradas).

## Por que é manual

Até o PR 39, atualizar a VPS é manual, por SSH pela tailnet: `git pull`, build da imagem na própria VPS e `docker compose up` (exceção registrada no ADR 0004, `docs/adr/0004-interim-operation-before-prefect.md`). Quem aplica é o usuário, nunca um agente (`.claude/rules/infra.md`).

## O que está na `main` e este item usa

- Migrações: `0004` (`raw.weather_forecast`, já em produção desde o item 17), `0005` (`ref.calendar`) e `0006` (`raw.ons_daily_load`). A cabeça é `0006`. As migrações rodam numa única transação: se uma falhar, nenhuma fica aplicada.
- Subcomandos de `python -m ingestion` (código de saída: `0` sucesso, `1` falha de execução ou de checagem, `2` uso incorreto):
  - `weather-forecast`: snapshot diário da previsão (já agendado às 06:30).
  - `calendar --start <AAAA-MM-DD> --end <AAAA-MM-DD>`: upsert de `ref.calendar`; checa 1 linha por dia do intervalo. Log de sucesso: `calendar ok: <n> days from <start> to <end>, <h> national holidays`.
  - `ons-load [--end <AAAA-MM-DD>] [--start <AAAA-MM-DD> | --days <n>]`: baixa os parquets anuais do ONS, faz upsert do intervalo em `raw.ons_daily_load`, relê e checa (faixa de carga, 4 subsistemas por data, nenhuma data faltando de `--start` até a última data presente, exceto as lacunas conhecidas, e atraso de no máximo 5 dias entre a última data e `--end`). Sem argumentos: `--end` = hoje em `America/Sao_Paulo`, janela de 30 dias. Log de sucesso: `ons-load ok: <n> rows written from <start> to <end>, last date <d>`.
- Lacunas conhecidas da fonte (`ONS_KNOWN_GAPS` em `ingestion/ons.py`): 2013-12-01, 2014-02-01 e 2015-04-09, dias sem carga nos 4 subsistemas no próprio arquivo do ONS. Só **2015-04-09** cai dentro do backfill. Por isso 2015 tem **1456** linhas (364 dias × 4), não 1460.
- `infra/cron/crontab` (embutido na imagem, em `/app/infra/cron/crontab`):

  ```
  30 6 * * * python -m ingestion weather-forecast
  0 7 * * * python -m ingestion ons-load
  ```

- `infra/docker-compose.yml`: os serviços `scheduler` e `jobs` usam o mesmo `infra/jobs/Dockerfile`, mas **cada um tem a sua imagem** (nenhum dos dois declara `image:`). `dc build jobs` sozinho não atualiza a imagem do `scheduler`, e `dc up -d scheduler` reaproveita a imagem antiga se ela existir. Por isso o passo 2 constrói os dois (o segundo build sai quase todo do cache).
- Valores **provisórios** até o item 18 fechar (`docs/plans/18-verificar-fontes-manual.md`): horário 07:00, janela diária de 30 dias e atraso máximo de 5 dias. A coleta de verificação das fontes está rodando na VPS desde 2026-11-08 e grava em `/home/deploy/source-checks`. Nada deste item muda esses valores.

## Regras deste item

- Não rodar build nem backfill entre **06:25 e 07:30 BRT**: os jobs agendados rodam às 06:30 e 07:00, e dois jobs ao mesmo tempo podem passar do `mem_limit` (ADR 0004). Confira a hora com `TZ=America/Sao_Paulo date`.
- Nunca `dc down -v` nem `docker volume rm platform_pgdata`: o histórico de `raw.weather_forecast` não volta e ainda não há backup (PR 57).
- Nunca `alembic downgrade` em produção.
- Nunca `dc config` sem `-q` (imprime as senhas).
- Não editar código, crontab ou compose na VPS. Qualquer correção é PR na `main`.

## Checklist

Na VPS, como `deploy` (`ssh deploy@<host>.<tailnet>.ts.net`). **Toda sessão SSH nova** começa com o bloco abaixo (a função `dc` e o atalho `q` não sobrevivem entre sessões):

```bash
cd /opt/platform
dc() { docker compose -f /opt/platform/infra/docker-compose.yml "$@"; }
q() { dc exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -q -A -t -F "|" -v ON_ERROR_STOP=1'; }
```

`q` roda o `psql` dentro do container do Postgres como admin, pelo socket local, sem digitar senha; o SQL entra pelo stdin (`q <<'SQL' ... SQL`), então aspas simples e duplas não precisam de escape. A saída vem sem cabeçalho, com colunas separadas por `|`. Para uma consulta curta, a forma direta também serve: `dc exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select 1"'`.

### 1. Ponto de partida

- [ ] Hora fora da janela proibida:

  ```bash
  TZ=America/Sao_Paulo date '+%F %H:%M'
  ```

  → uma hora fora de 06:25–07:30.

- [ ] Agendador no ar e banco saudável:

  ```bash
  dc ps --format '{{.Service}} {{.Status}}'
  ```

  → `health Up ... (healthy)`, `postgres Up ... (healthy)` e `scheduler Up ...`.

- [ ] Coleta da previsão em dia (o item 17 continua valendo):

  ```bash
  q <<'SQL'
  select issued_at, count(*) from raw.weather_forecast where issued_at > current_date - 8 group by 1 order by 1;
  SQL
  ```

  → uma linha por dia desde que a coleta foi ligada, cada uma com `28`, a última com a data de hoje se já passou das 06:30 BRT.

- [ ] Espaço e memória:

  ```bash
  df -h / && free -m
  ```

  → pelo menos 2 GB livres em `/` (build de duas imagens). Anote a coluna `available` do `free -m`.

### 2. Atualizar o código e construir as imagens

- [ ] Puxar a `main`:

  ```bash
  git pull --ff-only && git log -1 --oneline
  ```

  → `0eae535 fix: tolerate empty ONS loads and known source gaps (#35)` ou um commit mais novo da `main`.

- [ ] Conferir que o crontab do repositório tem as duas linhas:

  ```bash
  grep -v '^#' infra/cron/crontab
  ```

  →

  ```
  30 6 * * * python -m ingestion weather-forecast
  0 7 * * * python -m ingestion ons-load
  ```

- [ ] Construir as duas imagens (lento em 1 vCPU; pode usar swap):

  ```bash
  dc build jobs scheduler
  ```

  → termina sem erro, com `jobs Built` e `scheduler Built` (o texto exato varia com a versão do compose).

- [ ] Conferir as imagens novas:

  ```bash
  docker image ls --format '{{.Repository}} {{.CreatedSince}}' | grep '^platform-'
  ```

  → `platform-jobs` e `platform-scheduler`, ambas criadas há poucos minutos.

- [ ] A imagem dos jobs conhece a migração nova e o subcomando novo:

  ```bash
  dc run --rm -T jobs alembic heads
  dc run --rm -T jobs python -m ingestion --help
  ```

  → `0006 (head)`; e o help lista `weather-forecast`, `calendar` e `ons-load`.

### 3. Migrar

- [ ] Estado antes:

  ```bash
  dc run --rm -T jobs alembic current
  ```

  → última linha `0004` (sem `(head)`). Se aparecer outro número, pare e devolva para o planejamento.

- [ ] Aplicar:

  ```bash
  dc run --rm -T jobs alembic upgrade head; echo "exit=$?"
  ```

  → duas linhas `Running upgrade`: `0004 -> 0005, ref_calendar` e `0005 -> 0006, raw_ons_daily_load`; e `exit=0`.

- [ ] Estado depois:

  ```bash
  dc run --rm -T jobs alembic current
  ```

  → última linha `0006 (head)`.

- [ ] Tabelas novas vazias e permissões padrão aplicadas (`scientist` e `reader` leem; só `ingestor` escreve):

  ```bash
  q <<'SQL'
  select (select count(*) from ref.calendar), (select count(*) from raw.ons_daily_load);
  select t,
         has_table_privilege('scientist', t, 'SELECT'),
         has_table_privilege('scientist', t, 'INSERT'),
         has_table_privilege('reader', t, 'SELECT'),
         has_table_privilege('ingestor', t, 'INSERT'),
         has_table_privilege('ingestor', t, 'UPDATE')
  from unnest(array['ref.calendar', 'raw.ons_daily_load']) as t
  order by t;
  SQL
  ```

  →

  ```
  0|0
  raw.ons_daily_load|t|f|t|t|t
  ref.calendar|t|f|t|t|t
  ```

### 4. Carregar `ref.calendar` (2015-01-01 a 2030-12-31)

- [ ] Rodar o job:

  ```bash
  dc run --rm -T jobs python -m ingestion calendar --start 2015-01-01 --end 2030-12-31; echo "exit=$?"
  ```

  → no log, `calendar ok: 5844 days from 2015-01-01 to 2030-12-31, 151 national holidays`; e `exit=0`.

- [ ] Conferir:

  ```bash
  q <<'SQL'
  select count(*), min("date"), max("date"), count(*) filter (where is_national_holiday) from ref.calendar;
  select "date", weekday, holiday_name from ref.calendar
  where is_national_holiday and "date" between '2026-01-01' and '2026-12-31' order by 1;
  SQL
  ```

  → primeira linha `5844|2015-01-01|2030-12-31|151`; depois 10 linhas de 2026: `2026-01-01`, `2026-04-03`, `2026-04-21`, `2026-05-01`, `2026-09-07`, `2026-10-12`, `2026-11-02`, `2026-11-15`, `2026-11-20` e `2026-12-25`, cada uma com `weekday` de 1 a 7 e nome em português (a de 2026-01-01 com `weekday` `4`; 2026-11-15 com `7`; 2026-11-20 com `5`).

- [ ] Rodar de novo (idempotência) e conferir que nada muda:

  ```bash
  dc run --rm -T jobs python -m ingestion calendar --start 2015-01-01 --end 2030-12-31; echo "exit=$?"
  q <<'SQL'
  select count(*), count(*) filter (where is_national_holiday) from ref.calendar;
  SQL
  ```

  → `exit=0` e `5844|151`.

### 5. Backfill do ONS (2015-01-01 até hoje)

- [ ] Confira de novo a hora (fora de 06:25–07:30) e fixe "hoje" no fuso do job:

  ```bash
  TODAY=$(TZ=America/Sao_Paulo date +%F); echo "$TODAY"
  ```

  → a data de hoje em Brasília (ex.: `2026-11-08`). Use `TZ=America/Sao_Paulo` porque o relógio da VPS pode estar em UTC, e depois das 21:00 BRT o UTC já é o dia seguinte.

- [ ] Rodar o backfill (baixa 12 arquivos anuais, de 2015 a 2026; leva alguns minutos):

  ```bash
  dc run --rm -T jobs python -m ingestion ons-load --start 2015-01-01 --end "$TODAY"; echo "exit=$?"
  ```

  → no log, `ons-load ok: <n> rows written from 2015-01-01 to <hoje>, last date <d>`, com `<d>` no máximo 5 dias antes de hoje (D−3 na medição de 2026-11-08); e `exit=0`. Anote `<n>` e `<d>`. Se der `exit=1`, veja "Se algo falhar".

### 6. Verificar o backfill

- [ ] Por subsistema: mesmo início, mesmo fim, mesma contagem, e contagem igual a `max(date) − 2015-01-01` (dias do intervalo menos a lacuna de 2015-04-09):

  ```bash
  q <<'SQL'
  select subsystem, min("date"), max("date"), count(*), max("date") - date '2015-01-01' as expected
  from raw.ons_daily_load group by 1 order by 1;
  SQL
  ```

  → exatamente 4 linhas, na ordem `N`, `NE`, `S`, `SE`; em todas, `min` = `2015-01-01`, `max` = `<d>` do passo 5, e `count` = `expected`, igual nas 4. Exemplo: com `<d>` = `2026-11-05`, cada linha termina em `|4326|4326`.

- [ ] Datas faltando: só a lacuna conhecida da fonte:

  ```bash
  q <<'SQL'
  select g::date from generate_series(date '2015-01-01', (select max("date") from raw.ons_daily_load), interval '1 day') as g
  except
  select "date" from raw.ons_daily_load
  order by 1;
  SQL
  ```

  → exatamente uma linha: `2015-04-09`.

- [ ] A lacuna é de dia inteiro e os vizinhos estão completos:

  ```bash
  q <<'SQL'
  select "date", count(*) from raw.ons_daily_load where "date" between '2015-04-08' and '2015-04-10' group by 1 order by 1;
  SQL
  ```

  → `2015-04-08|4` e `2015-04-10|4` (nenhuma linha de `2015-04-09`).

- [ ] Por ano:

  ```bash
  q <<'SQL'
  select extract(year from "date")::int as year, count(*), count(distinct "date") from raw.ons_daily_load group by 1 order by 1;
  SQL
  ```

  → 12 linhas:

  ```
  2015|1456|364
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

  2026 é ano parcial: `N` = dias de 2026-01-01 até `<d>`, inclusive (com `<d>` = `2026-11-05`, `N` = 309 e a linha é `2026|1236|309`).

- [ ] Valores plausíveis, `ingested_at` preenchido e cruzamento com o calendário:

  ```bash
  q <<'SQL'
  select subsystem, round(min(load_avg_mw)), round(avg(load_avg_mw)), round(max(load_avg_mw)) from raw.ons_daily_load group by 1 order by 1;
  select count(*) filter (where ingested_at is null), count(*) filter (where load_avg_mw <= 0) from raw.ons_daily_load;
  select count(*) from raw.ons_daily_load l left join ref.calendar c using ("date") where c."date" is null;
  SQL
  ```

  → 4 linhas com mínimo maior que 0 e máximo menor que 100000, e `SE` com a maior média das quatro (anote os números); depois `0|0`; depois `0`.

- [ ] Idempotência e o modo diário (sem argumentos, janela de 30 dias, como o agendador roda):

  ```bash
  q <<'SQL'
  select count(*) from raw.ons_daily_load;
  SQL
  dc run --rm -T jobs python -m ingestion ons-load; echo "exit=$?"
  q <<'SQL'
  select count(*), max("date") from raw.ons_daily_load;
  SQL
  ```

  → `exit=0`; o log diz `ons-load ok: <m> rows written from <hoje − 29> to <hoje>, last date <d>`; a contagem final é igual à inicial (ou maior em múltiplos de 4, se o ONS publicou um dia novo entre as duas execuções).

### 7. Recriar o agendador com o crontab novo

- [ ] Hora fora de 06:25–07:30 e então:

  ```bash
  dc up -d scheduler
  ```

  → `Container platform-scheduler-1  Recreated` e `Started` (o compose recria porque a imagem mudou no passo 2).

- [ ] O container em execução tem o crontab novo:

  ```bash
  dc exec -T scheduler grep -v '^#' /app/infra/cron/crontab
  ```

  → as duas linhas do passo 2 (`30 6 * * * ... weather-forecast` e `0 7 * * * ... ons-load`). Se faltar a do `ons-load`, a imagem do `scheduler` não foi reconstruída: rode `dc build scheduler && dc up -d scheduler` e confira de novo.

- [ ] O supercronic leu o arquivo sem erro:

  ```bash
  dc logs --since 5m scheduler
  ```

  → uma linha com `read crontab: /app/infra/cron/crontab` e nenhuma com `level=error` ou `level=fatal`.

### 8. No dia seguinte, depois das 07:10 BRT

- [ ] As duas execuções agendadas terminaram bem:

  ```bash
  dc logs --since 3h scheduler | grep -E 'weather-forecast ok|ons-load ok|failed'
  ```

  → uma linha `weather-forecast ok: 4 locations, 28 rows inserted, 0 already existed` (por volta das 06:30) e uma `ons-load ok: <m> rows written from <hoje − 29> to <hoje>, last date <d>` (por volta das 07:00); nenhuma linha `subcommand ... failed`.

- [ ] O banco reflete as duas:

  ```bash
  q <<'SQL'
  select count(*) from raw.weather_forecast where issued_at = current_date;
  select max("date"), max(ingested_at) from raw.ons_daily_load;
  SQL
  ```

  → `28`; e a última data do ONS com `max(ingested_at)` de hoje, por volta das 07:00 BRT (o valor aparece em UTC, por volta das 10:00).

- [ ] Coleta do item 18 seguindo (só conferir que não parou; os números são do item 18, não deste):

  ```bash
  ls -lt /home/deploy/source-checks | head
  ```

  → arquivos com data de hoje.

### 9. Prova de pronto da Fase 1 (notebook via Tailscale)

O hostname da VPS na tailnet: na VPS, `tailscale serve status | grep 5432 | head -1` → `|-- tcp://<host>.<tailnet>.ts.net:5432 (tailnet only)`. Use esse `<host>.<tailnet>.ts.net` abaixo.

- [ ] Do **seu** notebook, com o papel `reader` (senha "platform reader" do gerenciador; o `psql` pede sem eco):

  ```bash
  psql "host=<host>.<tailnet>.ts.net port=5432 dbname=ml user=reader sslmode=disable" -tAc "select subsystem, max(\"date\"), count(*) from raw.ons_daily_load group by 1 order by 1"
  ```

  → 4 linhas `N`, `NE`, `S`, `SE`, com o mesmo `max` e a mesma contagem do passo 6.

- [ ] Enviar à cientista o aviso da seção "Aviso à cientista" (abaixo). Credenciais, convite do Tailscale e configuração do cliente **não** estão neste plano: ficam no documento de acesso da cientista, que é separado.
- [ ] Critério da fase: **a cientista**, do notebook dela, roda:

  ```bash
  psql "host=<host>.<tailnet>.ts.net port=5432 dbname=ml user=scientist sslmode=disable" -tAc "select subsystem, max(\"date\"), count(*) from raw.ons_daily_load group by 1 order by 1"
  ```

  → as mesmas 4 linhas do teste com `reader`. Ela confirma também `select count(*) from ref.calendar` → `5844`. Anote a data em que ela confirmou: é a data de pronto da Fase 1.

## Verificação de pronto (resumo)

| Onde | Comando | Saída esperada |
| --- | --- | --- |
| VPS | `dc run --rm -T jobs alembic current` | `0006 (head)` |
| VPS | `q <<'SQL'`<br>`select count(*), min("date"), max("date"), count(*) filter (where is_national_holiday) from ref.calendar;`<br>`SQL` | `5844\|2015-01-01\|2030-12-31\|151` |
| VPS | consulta de datas faltando do passo 6 | exatamente `2015-04-09` |
| VPS | consulta por subsistema do passo 6 | 4 linhas, `min` = `2015-01-01`, `max` ≤ 5 dias antes de hoje, `count` = `expected` e igual nas 4 |
| VPS | consulta por ano do passo 6 | `2015\|1456\|364`; 2016–2025 como a tabela do passo 6; 2026 parcial |
| VPS | `dc exec -T scheduler grep ons-load /app/infra/cron/crontab` | `0 7 * * * python -m ingestion ons-load` |
| VPS, dia seguinte | `dc logs --since 3h scheduler \| grep -E 'weather-forecast ok\|ons-load ok\|failed'` | uma linha `weather-forecast ok`, uma `ons-load ok`, nenhuma `failed` |
| Notebook dela | `psql "host=<host>.<tailnet>.ts.net port=5432 dbname=ml user=scientist sslmode=disable" -tAc "select subsystem, max(\"date\") from raw.ons_daily_load group by 1 order by 1"` | 4 linhas |

## Aviso à cientista

A regra exige aviso para mudança em `raw` e `ref` (`AGENTS.md`, "Fronteira"). Este aviso junta os dos planos 13, 14, 19 e 21. Texto pronto para enviar (ajuste o tom; o conteúdo é o mínimo):

> **A Fase 1 terminou: você já pode explorar os dados no Postgres (banco `ml`, papel `scientist`, só leitura em `raw` e `ref`).** O acesso (Tailscale, usuário, senha, cliente) está no documento de acesso que te mandei à parte.
>
> **`ref.calendar`**: um dia por linha, de 2015-01-01 a 2030-12-31 (5844 linhas), chave `date`. Colunas: `date`, `weekday`, `is_national_holiday`, `holiday_name`.
> - `weekday` é ISO 8601: 1 = segunda ... 7 = domingo (igual a `date.isoweekday()` e a `EXTRACT(ISODOW FROM ...)`; **diferente** de `EXTRACT(DOW ...)` e de `pandas .dt.dayofweek`).
> - Só feriados **nacionais**, da biblioteca `holidays` (versão travada na plataforma), nomes em português. Não entram feriados estaduais ou municipais nem pontos facultativos (Carnaval, Cinzas, Corpus Christi, 24/12, 31/12): se o modelo precisar, é feature sua. Consciência Negra (20/11) é nacional a partir de 2024. Sexta-feira Santa aparece como nacional, como a biblioteca a classifica.
> - A tabela pode ser recarregada quando a biblioteca for atualizada (lei nova); eu aviso quando isso mudar dados.
>
> **`raw.ons_daily_load`**: carga diária do ONS, uma linha por subsistema por dia, desde 2015-01-01. Chave (`subsystem`, `date`). Colunas: `subsystem`, `date`, `load_avg_mw`, `ingested_at`.
> - `subsystem` usa os códigos do ONS: `SE` (Sudeste/Centro-Oeste), `S` (Sul), `NE` (Nordeste), `N` (Norte). Não há total `SIN`: some os quatro, se precisar. `ref.locations.subsystem` usa os mesmos códigos.
> - `load_avg_mw` é a carga média do dia em **MWmed** (`val_cargaenergiamwmed` do ONS).
> - `date` é o dia como o ONS publica; para feriado e dia da semana, `JOIN ref.calendar USING ("date")`.
> - **2015-04-09 não tem dado do ONS em nenhum subsistema.** É um buraco da própria fonte (o arquivo do ONS vem com a carga vazia nesse dia), não falha do job. Por isso 2015 tem 1456 linhas (364 dias × 4), não 1460. É o único dia faltando no intervalo.
> - O ONS revisa dias já publicados: o job reescreve uma janela recente toda manhã (hoje, os últimos 30 dias, às 07:00), então **valores recentes podem mudar** e são sobrescritos (não há versões). `ingested_at` é o momento da **última** escrita da linha, não da primeira. Para reprodutibilidade, congele o recorte em `features` ou registre a data da extração.
> - Os dias mais recentes chegam com atraso (D−3 numa medição de fim de semana). O horário 07:00, a janela de 30 dias e o atraso tolerado (5 dias) são provisórios: estou medindo o atraso e a profundidade das revisões do ONS e aviso se mudarem.
> - 2026 é ano parcial, até o último dia publicado pelo ONS.
>
> **`raw.weather_forecast`**: snapshots diários da previsão do Open-Meteo para as 4 capitais de `ref.locations` (ponto da capital, não média da região). Chave (`location_id`, `issued_at`, `target_date`).
> - `issued_at` é o dia (fuso `America/Sao_Paulo`) em que a previsão foi coletada; o primeiro snapshot do dia vence e nunca é reescrito.
> - `horizon_days = target_date − issued_at`, de **1 a 7** (não há horizonte 0).
> - Unidades: `temp_max` e `temp_min` em **°C**; `precip_mm` em **mm** (soma do dia); `wind_speed_max` em **km/h** (máxima a 10 m); `humidity_mean` em **%** (média a 2 m). Podem vir nulas quando a fonte não tiver o valor.
> - Para usar "a previsão disponível em D" sem vazamento: filtre `issued_at <= D` (normalmente `issued_at = D`).
> - O histórico começa no dia em que a coleta foi ligada; não existe previsão anterior a isso.
>
> Mudanças de schema em `raw` e `ref` só acontecem com migração, registro de decisão e aviso a você.

## Se algo falhar

Não mexa em código, crontab ou compose na VPS. Guarde o log (`... 2>&1 | tee /tmp/<nome>.log`) e devolva para o planejamento quando indicado.

- **`dc build` falha ou é morto por falta de memória:** `free -m`, confira que nenhum job está rodando (`docker ps`) e tente uma vez de novo. Se repetir, devolva com o log.
- **`alembic upgrade head` falha:** nada fica aplicado pela metade (transação única); `alembic current` continua `0004`. Devolva com o log. Não rode `downgrade`.
- **`calendar` sai com `exit=1`:** a checagem ou o banco falhou; o log mostra a causa (`CheckFailed: ...` ou erro do Postgres). Devolva com o log. Rodar de novo é seguro (upsert).
- **`ons-load` sai com `exit=1`.** O upsert grava antes da checagem, então pode haver linhas gravadas mesmo com falha; rodar de novo é seguro (upsert por chave). Pela mensagem:
  - `stale: last date <d> is older than <limite>`: o ONS está atrasado mais de 5 dias. Confira `q <<'SQL'` / `select max("date") from raw.ons_daily_load;` / `SQL`. Rode o mesmo comando do passo 5 no dia seguinte; se repetir, anote para o item 18 e devolva para o planejamento (o limite é provisório).
  - `missing dates: ...` com qualquer data além de `2015-04-09`, ou `<data> has <n> rows, expected 4`: a fonte mudou (lacuna nova ou dia parcial). Devolva com o log; uma lacuna nova só entra por PR com teste. Não rode a consulta de pronto como se estivesse certa.
  - `ValueError` em `parse_load` (ex.: `val_cargaenergiamwmed` com valor não numérico): formato novo num arquivo anual. Devolva com o log.
  - Erro de rede (`NetworkError`, timeout, HTTP 5xx) depois das 3 tentativas: espere alguns minutos e rode de novo uma vez.
  - Morto sem mensagem (`exit=137`): falta de memória. Confira que o agendador não estava rodando um job no mesmo horário e tente de novo uma vez; se repetir, devolva com `free -m`.
- **O `scheduler` recriado não tem a linha `ons-load`:** a imagem dele é antiga. `dc build scheduler && dc up -d scheduler` e repita a conferência do passo 7.
- **No dia seguinte, `ons-load` falhou no agendador:** rode à mão o modo diário (`dc run --rm -T jobs python -m ingestion ons-load; echo "exit=$?"`) fora da janela proibida e siga os casos acima. Uma falha de `stale` às 07:00 em dia útil é insumo direto do item 18.
- **A cientista não conecta:** é assunto do documento de acesso (ACL, convite, senha), não deste plano. Se o seu teste com `reader` do passo 9 passou, o banco e o `tailscale serve` estão certos.

## Perguntas em aberto para o usuário

1. **Onde está o documento de acesso da cientista?** O plano só diz que ele é separado. Se ele já existir no repo, informe o caminho para citá-lo no aviso e no passo 9.
2. **Marcar os checkboxes da Fase 1 em `docs/plataforma-ml.md`:** fica para um PR só de `docs/**` depois do passo 9? O item "Ingestão do ONS + backfill desde 2015 + checagens" pode ser marcado mesmo com o item 18 aberto, já que horário e janela são provisórios e ajustáveis depois; o "Para verificar antes da Fase 1" continua aberto.
3. **`raw.weather_forecast` no aviso:** os avisos dos planos 13 e 14 já foram enviados no item 17? Se sim, o bloco de previsão do aviso pode ser encurtado para "lembrete".
