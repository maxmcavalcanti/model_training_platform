# 14 — Cliente da previsão do Open-Meteo (com retry)

> Executa: agente. Depende de: 08 (usa pandas). Branch sugerida: `feat/openmeteo-previsao`.
> **Antecipado** (Fase 2 antes do fim da Fase 1, decisão P5).
> TDD: passo 0 (dependências) → test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Buscar na API de previsão do Open-Meteo a previsão diária de um local e devolver um DataFrame no formato de `raw.clima_previsao`, com retry só para erro de rede.
Não grava nada: o job que grava é o PR 15.

## 2. Fora do escopo

- Gravar no banco, checagem pandera, CLI (PR 15).
- API de histórico/arquivo (PR 24).
- Ler `ref.locais` do banco (PR 15).

## 3. Fase do roadmap

Fase 2 — "`raw.clima_previsao` coletando todo dia (prioridade)".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `pyproject.toml`, `uv.lock` | `httpx`, `tenacity` (passo 0) |
| `ingestion/http.py` | `obter_json(cliente, url, params, *, tentativas=3, espera_base=1.0)` com retry e backoff |
| `ingestion/openmeteo.py` | `Local` (dataclass) e `buscar_previsao(...)` |
| `tests/fixtures/openmeteo_previsao_sao_paulo.json` | Resposta real gravada uma vez (test-writer) |
| `tests/test_http.py`, `tests/test_openmeteo_previsao.py` | Testes (test-writer) |

Fonte (`docs/plataforma-ml.md`, "Fontes de dados"): `api.open-meteo.com/v1/forecast`, sem chave, previsão diária de temperatura máx/mín, chuva, vento, umidade, até 16 dias; gratuito para uso não comercial, ~10 mil chamadas/dia.
Job (`docs/plataforma-ml.md`, "Ingestão"): "Snapshot da previsão para os próximos 7 dias, um registro por local e data-alvo, com `emitida_em` = hoje".
Regra: "Retry com backoff para erro de rede (3 tentativas)".

## 5. Passos

0. (implementer) `uv add httpx tenacity`. Commit `build: add httpx and tenacity`.
1. (test-writer) Grave a fixture com uma chamada real (única vez, fora dos testes):
   `curl -s "https://api.open-meteo.com/v1/forecast?latitude=-23.55&longitude=-46.63&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,relative_humidity_2m_mean&timezone=America%2FSao_Paulo&forecast_days=8" -o tests/fixtures/openmeteo_previsao_sao_paulo.json`
   Se a resposta não tiver alguma das variáveis em `daily`, pare e reporte (o nome mudou na API).
2. (test-writer) Escreva os testes da seção 8 usando `httpx.Client(transport=httpx.MockTransport(...))`; nenhum teste acessa a rede. Confirme falha por `ModuleNotFoundError: ingestion.http`. Commit `test: add open-meteo forecast client tests`.
3. (implementer) `ingestion/http.py`:
   - `class ErroDeRede(RuntimeError)`.
   - `obter_json(...)`: faz `GET`; repete até `tentativas` vezes, com espera exponencial `espera_base * 2**n` (tenacity), em `httpx.TransportError`, HTTP 429 e HTTP 5xx. Outro 4xx levanta `httpx.HTTPStatusError` na primeira vez, sem repetir. Esgotadas as tentativas, levanta `ErroDeRede` com a URL e a última causa.
   - Também `obter_bytes(...)` com a mesma política (o PR 20 usa para o parquet do ONS).
4. `ingestion/openmeteo.py`:
   - `@dataclass(frozen=True) class Local: local_id: str; lat: float; lon: float`.
   - `URL_PREVISAO = "https://api.open-meteo.com/v1/forecast"`.
   - `VARIAVEIS = {"temperature_2m_max": "temp_max", "temperature_2m_min": "temp_min", "precipitation_sum": "precip_mm", "wind_speed_10m_max": "vento_max", "relative_humidity_2m_mean": "umidade_media"}`.
   - `buscar_previsao(cliente, local, emitida_em: date, dias: int = 7, *, espera_base=1.0) -> pd.DataFrame`: parâmetros `latitude`, `longitude`, `daily` (chaves de `VARIAVEIS` separadas por vírgula), `timezone=America/Sao_Paulo`, `forecast_days=dias + 1`.
   - Valida que o primeiro dia de `daily.time` é `emitida_em`; se não for, levanta `ValueError` (indica fuso errado ou execução fora do dia).
   - Devolve só `data_alvo` de `emitida_em + 1` até `emitida_em + dias` (horizontes 1 a 7; ver P8), colunas `local_id, emitida_em, data_alvo, temp_max, temp_min, precip_mm, vento_max, umidade_media`, tipos `date` e `float`; valores `null` da API viram `NaN`.
5. Rode os critérios de pronto e refatore com a suíte verde.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_http.py tests/test_openmeteo_previsao.py` | Todos passam, sem acesso à rede |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem erro |
| `uv run python -c "import httpx; from datetime import date; from ingestion.openmeteo import Local, buscar_previsao; print(buscar_previsao(httpx.Client(), Local('sao_paulo', -23.55, -46.63), date.today()).shape)"` (manual, com rede) | `(7, 8)` |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: o recorte de horizontes e a validação do dia de emissão decidem se o snapshot é válido; o retry precisa repetir só o que é erro de rede.

## 8. Casos de teste

`obter_json`:
1. Resposta 200 na primeira → devolve o JSON; 1 chamada.
2. Duas falhas `httpx.ConnectError` e depois 200 → devolve o JSON; 3 chamadas.
3. Três respostas 503 → `ErroDeRede`; 3 chamadas.
4. Resposta 429 e depois 200 → devolve o JSON; 2 chamadas.
5. Resposta 400 → `httpx.HTTPStatusError`; 1 chamada (sem retry).

`buscar_previsao` (com a fixture e `emitida_em` igual ao primeiro dia da fixture):
6. Devolve 7 linhas, `data_alvo` de D+1 a D+7, todas com `local_id = 'sao_paulo'` e `emitida_em = D`.
7. Colunas exatamente `local_id, emitida_em, data_alvo, temp_max, temp_min, precip_mm, vento_max, umidade_media`.
8. `temp_max` de D+1 no DataFrame é igual ao valor da fixture para esse dia.
9. A requisição enviada tem `timezone=America/Sao_Paulo`, `forecast_days=8` e as 5 variáveis em `daily`.
10. Fixture alterada com `null` em `precipitation_sum` → `NaN` em `precip_mm`.
11. `emitida_em` diferente do primeiro dia da resposta → `ValueError`.
12. `dias=3` → 3 linhas e `forecast_days=4` na requisição.

## 9. Riscos e perguntas em aberto

- P8: guardar também o horizonte 0 (previsão para o próprio dia de emissão)? O doc diz "próximos 7 dias". Custo zero; útil para o `chuva_d1`. Padrão deste plano: 1 a 7.
- Retry duplo: quando a ingestão virar flow do Prefect (PR 32), o retry fica só aqui; o flow não deve ter `retries` próprio para erro de rede.
- Uso não comercial do Open-Meteo: este projeto é de estudo; se virar comercial, exige plano pago.

## 10. Decisões que exigem ADR

Nenhuma.
