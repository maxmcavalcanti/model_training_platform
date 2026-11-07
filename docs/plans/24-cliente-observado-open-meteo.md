# 24 — Cliente do clima observado (arquivo ERA5 do Open-Meteo)

> Executa: agente. Depende de: 14, 18 (atraso do ERA5 confirmado). Branch sugerida: `feat/openmeteo-observado`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Buscar na API de arquivo do Open-Meteo o clima diário observado de um local num intervalo de datas e devolver um DataFrame no formato de `raw.clima_observado`.
Serve ao job diário (últimos 10 dias) e ao backfill desde 2015.

## 2. Fora do escopo

- Tabela (PR 25), job, checagem e CLI (PR 26).

## 3. Fase do roadmap

Fase 2 — "`raw.clima_observado` + backfill desde 2015".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `ingestion/openmeteo.py` | `URL_ARQUIVO` e `buscar_observado(cliente, local, inicio, fim, *, espera_base)` |
| `tests/fixtures/openmeteo_arquivo_sao_paulo.json` | Resposta real gravada uma vez (test-writer) |
| `tests/test_openmeteo_observado.py` | Testes (test-writer) |

Fonte (`docs/plataforma-ml.md`): `archive-api.open-meteo.com/v1/archive`, clima observado (reanálise ERA5), diário desde 1940; serve para backfill e para o "real" do modelo de clima.

Código existente em `ingestion/openmeteo.py` (PR 14): `Local`, `VARIAVEIS` (mapa nome da API → coluna), `buscar_previsao`; em `ingestion/http.py`: `obter_json` com retry. Reutilize `VARIAVEIS` e `obter_json`.

## 5. Passos

1. (test-writer) Grave a fixture uma vez, com um intervalo que inclua os dias mais recentes (para ter nulos do atraso do ERA5):
   `curl -s "https://archive-api.open-meteo.com/v1/archive?latitude=-23.55&longitude=-46.63&start_date=<hoje-15>&end_date=<hoje>&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,relative_humidity_2m_mean&timezone=America%2FSao_Paulo" -o tests/fixtures/openmeteo_arquivo_sao_paulo.json`
2. (test-writer) Escreva os testes da seção 8 com `httpx.MockTransport`. Confirme falha por `ImportError: cannot import name 'buscar_observado'`. Commit `test: add open-meteo archive client tests`.
3. (implementer) Em `ingestion/openmeteo.py`:
   - `URL_ARQUIVO = "https://archive-api.open-meteo.com/v1/archive"`.
   - `buscar_observado(cliente, local, inicio: date, fim: date, *, espera_base=1.0) -> pd.DataFrame`: parâmetros `latitude`, `longitude`, `start_date`, `end_date` (ISO), `daily` (mesmas variáveis de `VARIAVEIS`), `timezone=America/Sao_Paulo`.
   - Colunas: `local_id, data, temp_max, temp_min, precip_mm, vento_max, umidade_media`.
   - Descarta dias em que **todas** as variáveis são nulas (ERA5 ainda não publicou); mantém dias com nulos parciais.
   - `inicio > fim` → `ValueError`.
   - Extraia o que for comum com `buscar_previsao` (montar `daily`, converter resposta em DataFrame) numa função privada, sem mudar o comportamento de `buscar_previsao` (os testes do PR 14 continuam verdes).
4. Rode os critérios de pronto e refatore com a suíte verde.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_openmeteo_observado.py tests/test_openmeteo_previsao.py` | Todos passam, sem rede |
| `uv run python -c "import httpx; from datetime import date; from ingestion.openmeteo import Local, buscar_observado; print(len(buscar_observado(httpx.Client(timeout=60), Local('sao_paulo', -23.55, -46.63), date(2015,1,1), date(2015,12,31))))"` (manual, com rede) | `365` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: o descarte de dias ainda não publicados evita gravar linhas vazias que a checagem acusaria todo dia.

## 8. Casos de teste

1. Fixture → colunas exatamente `local_id, data, temp_max, temp_min, precip_mm, vento_max, umidade_media`; `local_id` igual ao do `Local` passado.
2. Dias da fixture com todas as variáveis nulas não aparecem no resultado.
3. Dia com só `relative_humidity_2m_mean` nulo aparece, com `umidade_media` `NaN`.
4. A requisição tem `start_date` e `end_date` em ISO, `timezone=America/Sao_Paulo` e as 5 variáveis.
5. `inicio > fim` → `ValueError`, sem chamada HTTP.
6. 503, 503, 200 → devolve o resultado (retry herdado de `obter_json`).

## 9. Riscos e perguntas em aberto

- Se o item 18 mostrar que o ERA5 atrasa mais de 10 dias, a janela diária do PR 26 precisa crescer.
- Limite justo do Open-Meteo: o backfill é 1 chamada por cidade (intervalo inteiro); a API conta chamadas ponderadas pelo volume, ainda longe de 10 mil/dia.

## 10. Decisões que exigem ADR

Nenhuma.
