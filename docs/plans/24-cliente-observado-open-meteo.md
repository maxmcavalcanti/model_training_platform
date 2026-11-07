# 24 — Cliente do clima observado (arquivo ERA5 do Open-Meteo)

> Executa: agente. Depende de: 14, 18 (atraso do ERA5 confirmado). Branch sugerida: `feat/openmeteo-observed`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Buscar na API de arquivo do Open-Meteo o clima diário observado de um local num intervalo de datas e devolver um DataFrame no formato de `raw.weather_observed`.
Serve ao job diário (últimos 10 dias) e ao backfill desde 2015.

## 2. Fora do escopo

- Tabela (PR 25), job, checagem e CLI (PR 26).

## 3. Fase do roadmap

Fase 2 — "`raw.weather_observed` + backfill desde 2015".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `ingestion/openmeteo.py` | `ARCHIVE_URL` e `fetch_observed(client, location, start, end, *, base_delay)` |
| `tests/fixtures/openmeteo_archive_sao_paulo.json` | Resposta real gravada uma vez (test-writer) |
| `tests/test_openmeteo_observed.py` | Testes (test-writer) |

Fonte (`docs/plataforma-ml.md`): `archive-api.open-meteo.com/v1/archive`, clima observado (reanálise ERA5), diário desde 1940; serve para backfill e para o "real" do modelo de clima.

Código existente em `ingestion/openmeteo.py` (PR 14): `Location`, `VARIAVEIS` (mapa nome da API → coluna), `fetch_forecast`; em `ingestion/http.py`: `fetch_json` com retry. Reutilize `VARIAVEIS` e `fetch_json`.

## 5. Passos

1. (test-writer) Grave a fixture uma vez, com um intervalo que inclua os dias mais recentes (para ter nulos do atraso do ERA5):
   `curl -s "https://archive-api.open-meteo.com/v1/archive?latitude=-23.55&longitude=-46.63&start_date=<hoje-15>&end_date=<hoje>&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,relative_humidity_2m_mean&timezone=America%2FSao_Paulo" -o tests/fixtures/openmeteo_archive_sao_paulo.json`
2. (test-writer) Escreva os testes da seção 8 com `httpx.MockTransport`. Confirme falha por `ImportError: cannot import name 'fetch_observed'`. Commit `test: add open-meteo archive client tests`.
3. (implementer) Em `ingestion/openmeteo.py`:
   - `ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"`.
   - `fetch_observed(client, location, start: date, end: date, *, base_delay=1.0) -> pd.DataFrame`: parâmetros `latitude`, `longitude`, `start_date`, `end_date` (ISO), `daily` (mesmas variáveis de `VARIAVEIS`), `timezone=America/Sao_Paulo`.
   - Colunas: `location_id, date, temp_max, temp_min, precip_mm, wind_speed_max, humidity_mean`.
   - Descarta dias em que **todas** as variáveis são nulas (ERA5 ainda não publicou); mantém dias com nulos parciais.
   - `start > end` → `ValueError`.
   - Extraia o que for comum com `fetch_forecast` (montar `daily`, converter resposta em DataFrame) numa função privada, sem mudar o comportamento de `fetch_forecast` (os testes do PR 14 continuam verdes).
4. Rode os critérios de pronto e refatore com a suíte verde.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_openmeteo_observed.py tests/test_openmeteo_forecast.py` | Todos passam, sem rede |
| `uv run python -c "import httpx; from datetime import date; from ingestion.openmeteo import Location, fetch_observed; print(len(fetch_observed(httpx.Client(timeout=60), Location('sao_paulo', -23.55, -46.63), date(2015,1,1), date(2015,12,31))))"` (manual, com rede) | `365` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: o descarte de dias ainda não publicados evita gravar linhas vazias que a checagem acusaria todo dia.

## 8. Casos de teste

1. Fixture → colunas exatamente `location_id, date, temp_max, temp_min, precip_mm, wind_speed_max, humidity_mean`; `location_id` igual ao do `Location` passado.
2. Dias da fixture com todas as variáveis nulas não aparecem no resultado.
3. Dia com só `relative_humidity_2m_mean` nulo aparece, com `humidity_mean` `NaN`.
4. A requisição tem `start_date` e `end_date` em ISO, `timezone=America/Sao_Paulo` e as 5 variáveis.
5. `start > end` → `ValueError`, sem chamada HTTP.
6. 503, 503, 200 → devolve o resultado (retry herdado de `fetch_json`).

## 9. Riscos e perguntas em aberto

- Se o item 18 mostrar que o ERA5 atrasa mais de 10 dias, a janela diária do PR 26 precisa crescer.
- Limite justo do Open-Meteo: o backfill é 1 chamada por cidade (intervalo inteiro); a API conta chamadas ponderadas pelo volume, ainda longe de 10 mil/dia.

## 10. Decisões que exigem ADR

Nenhuma.
