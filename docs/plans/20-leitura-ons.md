# 20 — Leitura do parquet de carga diária do ONS

> Executa: agente. Depende de: 14 (usa `ingestion/http.py`), 18 (formato do arquivo, já registrado em `docs/plataforma-ml.md` pelo PR #30). Branch sugerida: `feat/ons-reader`.
> TDD: passo 0 (dependência) → test-writer (vermelho) → implementação (verde) → refatorar.
> Revisado em 2026-11-08 com os fatos do item 18 sobre o formato. As medições de atraso e de revisão do item 18 seguem pendentes (coleta rodando na VPS); este PR só precisa do formato.

## 1. Objetivo

Baixar o parquet anual de carga diária do bucket público do ONS e devolvê-lo como DataFrame pronto para upsert em `raw.ons_daily_load` (`subsystem`, `date`, `load_avg_mw`).
Só leitura e transformação pura, no mesmo molde de `ingestion/openmeteo.py`; gravar, filtrar a janela e checar atraso é o PR 22.

## 2. Fora do escopo

- Tabela `raw.ons_daily_load` (PR 21), job, checagem pandera, CLI e crontab (PR 22).
- Qualquer valor de atraso de publicação ou de janela de upsert (30 dias, `max_delay_days`): pertencem ao PR 22, como parâmetros, e dependem das medições pendentes do item 18.
- Filtro por intervalo de datas: o leitor devolve o ano inteiro; o PR 22 filtra `start <= date <= end`.
- Tratar 404 de ano novo em janeiro: o leitor só propaga o erro; a decisão de tolerar é do PR 22.
- MCP do ONS (o doc o cita como referência; aqui o acesso é HTTP direto ao S3).
- Arquivos `.csv`/`.xlsx` e o dicionário de dados do mesmo prefixo.
- Plano 19 (`ref.calendar`, migração 0005, `ingestion/calendar.py`), em andamento em outra worktree: este PR não toca migrações nem esses arquivos.

## 3. Fase do roadmap

Fase 1 — "Ingestão do ONS + backfill desde 2015 + checagens" (`docs/plataforma-ml.md`, "Roadmap").

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `pyproject.toml`, `uv.lock` | Dependência `pyarrow` (passo 0). Hoje não está no `uv.lock`; `pandas.read_parquet` e `DataFrame.to_parquet` (usado pelos testes) precisam dela |
| `ingestion/ons.py` | Novo. Constantes, `file_url(year)`, `parse_load(content)`, `fetch_load(client, year, *, base_delay, sleep)` |
| `tests/test_ons_reader.py` | Novo. Testes (test-writer) |

Nenhum outro arquivo muda. Nada em `migrations/`, `ingestion/checks.py`, `ingestion/jobs.py` ou `ingestion/cli.py`.

### Fatos da fonte (de `docs/plataforma-ml.md`, "Para verificar antes da Fase 1", verificado em 2026-11-08)

- Bucket S3 público `ons-aws-prod-opendata`, prefixo `dataset/carga_energia_di/`, sem conta AWS.
- Um arquivo por ano, padrão `CARGA_ENERGIA_<ANO>.parquet` (também há `.csv` e `.xlsx`), de 2000 a 2026.
- URL: `https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/carga_energia_di/CARGA_ENERGIA_<ANO>.parquet`.
- Esquema do parquet de 2026 (1236 linhas, 4 colunas):

| Coluna no parquet | Tipo | Valores | Coluna normalizada |
| --- | --- | --- | --- |
| `id_subsistema` | string | `N`, `NE`, `S`, `SE` | `subsystem` |
| `nom_subsistema` | string | `Norte`, `Nordeste`, `Sul`, `Sudeste/Centro-Oeste` | descartada |
| `din_instante` | datetime64[ns] | só a data, hora 00:00:00 | `date` (objeto `datetime.date`) |
| `val_cargaenergiamwmed` | float64 | MWmed | `load_avg_mw` (float64) |

- **Atenção:** o código do Sudeste/Centro-Oeste no arquivo é `SE`, não `SE/CO` (a tabela "Fontes de dados" de `docs/plataforma-ml.md` diz "SE/CO", mas é o nome, não o código). O `CHECK` do PR 21 também usa `SE`.
- Os arquivos anuais são reescritos de tempos em tempos pelo ONS (o de 2025 foi modificado em 2026-01-31).

### Código existente que o módulo usa

`ingestion/http.py` (PR 14):

```python
class NetworkError(RuntimeError):
    """Raised when every attempt failed with a network-level error."""

def fetch_bytes(
    client: httpx.Client,
    url: str,
    params: Mapping[str, Any] | None = None,
    *,
    attempts: int = DEFAULT_ATTEMPTS,      # 3
    base_delay: float = DEFAULT_BASE_DELAY,  # 1.0
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
```

Comportamento: retry com backoff exponencial (`base_delay * 2 ** (n-1)`) só para `httpx.TransportError`, 429 e 5xx; esgotadas as tentativas, `NetworkError` (com a causa encadeada). Qualquer outro status de erro (por exemplo 404) levanta `httpx.HTTPStatusError` na primeira tentativa, sem retry.

Padrão a seguir, `ingestion/openmeteo.py`: constantes de módulo (`FORECAST_URL`, `DAILY_VARIABLES` como dicionário nome-da-fonte → coluna, em ordem de saída), validação que levanta `ValueError` com mensagem que cita o nome problemático, e uma função `fetch_forecast(client, ..., *, base_delay=1.0, sleep=time.sleep) -> pd.DataFrame` que chama `fetch_json`, valida e devolve um DataFrame com as colunas na ordem da tabela, datas como `datetime.date`, valores `float64`, índice `0..n-1`, sem `ingested_at` (quem carimba é `ingestion.db.upsert`). `upsert` recusa chaves duplicadas no DataFrame com `ValueError`.

Regras de nome (ADR 0001, `docs/adr/0001-english-naming-convention.md`): identificadores, mensagens de erro, comentários e commits em inglês.

## 5. Passos

0. (implementer, antes do test-writer, na branch `feat/ons-reader`) `uv add pyarrow`. Confirme `uv run python -c "import pyarrow"` sem erro. Commit `build: add pyarrow` com `pyproject.toml` e `uv.lock`.
1. (test-writer) Escreva `tests/test_ons_reader.py` com os casos da seção 8. Os parquets são gerados em memória (`df.to_parquet(io.BytesIO())`) a partir de um DataFrame com as quatro colunas da tabela acima e os tipos dela (`din_instante` como `datetime64[ns]`); a rede é simulada com `httpx.MockTransport` (pode reaproveitar o molde `Harness` de `tests/test_openmeteo_forecast.py`, que registra requisições e `sleep`s). Nenhum teste acessa a rede nem o banco (sem marcador `db`). Confirme falha por `ModuleNotFoundError: No module named 'ingestion.ons'`. Commit `test: add ons reader tests`.
2. (implementer) Crie `ingestion/ons.py`:
   - Constantes: `BUCKET_URL = "https://ons-aws-prod-opendata.s3.amazonaws.com"`, `LOAD_PREFIX = "dataset/carga_energia_di/"`, `COLUMN_MAP = {"id_subsistema": "subsystem", "din_instante": "date", "val_cargaenergiamwmed": "load_avg_mw"}` (ordem = ordem de saída), `SUBSYSTEMS = ("SE", "S", "NE", "N")`.
   - Nenhuma constante de atraso, janela, "última data esperada" ou ano corrente. O módulo não conhece "hoje".
   - `file_url(year: int) -> str`: `f"{BUCKET_URL}/{LOAD_PREFIX}CARGA_ENERGIA_{year}.parquet"`.
3. `parse_load(content: bytes) -> pd.DataFrame`, nesta ordem:
   1. Lê o parquet. Bytes que não são parquet → `ValueError` (envolva o erro do leitor).
   2. Coluna de `COLUMN_MAP` ausente → `ValueError` com o nome da coluna. Colunas extras (`nom_subsistema` ou outras) são ignoradas.
   3. Nulo em `id_subsistema` ou `din_instante` → `ValueError`.
   4. Código fora de `SUBSYSTEMS` → `ValueError` listando os códigos desconhecidos (ex.: `SE/CO`, `SIN`).
   5. `din_instante` com hora diferente de 00:00:00 → `ValueError`.
   6. Linhas com `val_cargaenergiamwmed` nulo são descartadas (a tabela do PR 21 não aceita nulo; o dia some e a checagem de continuidade do PR 22 acusa).
   7. (`id_subsistema`, `din_instante`) duplicado → `ValueError` citando a chave.
   8. Renomeia por `COLUMN_MAP`, mantém só essas três colunas nessa ordem, `date` como `datetime.date`, `load_avg_mw` como `float64`, ordena por (`date`, `subsystem`) e reinicia o índice.
   - Arquivo válido sem nenhuma linha → DataFrame vazio com as três colunas, sem erro.
4. `fetch_load(client: httpx.Client, year: int, *, base_delay: float = 1.0, sleep: Callable[[float], None] = time.sleep) -> pd.DataFrame`: `parse_load(fetch_bytes(client, file_url(year), base_delay=base_delay, sleep=sleep))`. Não captura `NetworkError` nem `httpx.HTTPStatusError`.
5. Rode os critérios de pronto, `uv run ruff check .` e `uv run ruff format --check .`, e refatore com a suíte verde.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run python -c "import pyarrow"` | Sem saída, código 0 |
| `uv run pytest tests/test_ons_reader.py` | Todos passam, sem rede |
| `uv run pytest -m "not db"` | Suíte sem banco verde |
| `uv run pytest` (com o Postgres de teste: `docker compose -f infra/docker-compose.dev.yml up -d`) | Suíte verde |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | Nenhum arquivo a reformatar |
| Manual, com rede: `uv run python -c "import httpx; from ingestion.ons import fetch_load; d=fetch_load(httpx.Client(timeout=60), 2025); print(sorted(d.subsystem.unique()), len(d), d.date.min(), d.date.max())"` | `['N', 'NE', 'S', 'SE'] 1460 2025-01-01 2025-12-31` (365 dias × 4; se diferir, anote no PR, não ajuste o código para bater) |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: a normalização (nomes, tipos, códigos, datas, nulos, duplicatas) é onde o formato do ONS encontra o contrato de `raw.ons_daily_load`.

## 8. Casos de teste

1. Parquet com 2 dias × 4 subsistemas (`SE`, `S`, `NE`, `N`) e a coluna `nom_subsistema` → 8 linhas, colunas exatamente `["subsystem", "date", "load_avg_mw"]`, índice `0..7`, sem `nom_subsistema` nem `ingested_at`.
2. `din_instante = 2026-11-05 00:00:00` → `date == datetime.date(2026, 11, 5)` e `type(value) is datetime.date` em todas as linhas.
3. `val_cargaenergiamwmed = 41234.5` para (`SE`, 2026-11-05) → linha com `load_avg_mw == 41234.5`; dtype da coluna `float64`.
4. Linhas embaralhadas na entrada → saída ordenada por (`date`, `subsystem`).
5. Parquet sem `val_cargaenergiamwmed` → `ValueError` cuja mensagem contém `val_cargaenergiamwmed` (idem para `id_subsistema` e `din_instante`, parametrizado).
6. Parquet com `id_subsistema = "SE/CO"` → `ValueError` cuja mensagem contém `SE/CO`.
7. Parquet com linhas `SIN` além dos 4 subsistemas → `ValueError` cuja mensagem contém `SIN`.
8. `din_instante = 2026-11-05 12:00:00` → `ValueError`.
9. Uma linha com `val_cargaenergiamwmed` nulo num parquet de 2 dias × 4 → 7 linhas, sem a linha do nulo.
10. Mesmo (`SE`, 2026-11-05) duas vezes → `ValueError`.
11. Bytes `b"not a parquet"` → `ValueError`.
12. Parquet válido com zero linhas → DataFrame vazio com as três colunas, sem erro.
13. Parquet cuja última data é 2015-01-31 (muito antes de hoje) → devolvido sem erro (o leitor não julga atraso).
14. `file_url(2015) == "https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/carga_energia_di/CARGA_ENERGIA_2015.parquet"`.
15. `fetch_load(client, 2026)` → uma requisição `GET` para `file_url(2026)` e o DataFrame igual a `parse_load` dos mesmos bytes.
16. Transporte que devolve 503 e depois o parquet → DataFrame devolvido, 2 requisições, 1 `sleep` de `base_delay`.
17. Transporte que devolve 503 sempre → `NetworkError` após 3 requisições.
18. Transporte que devolve 404 → `httpx.HTTPStatusError` após 1 requisição, sem `sleep`.

## 9. Riscos e perguntas em aberto

- Medições de atraso e revisão do item 18 pendentes: não afetam este PR, porque o leitor não tem valor de atraso nem janela. Afetam o PR 22 (`max_delay_days`, horário do crontab, janela de 30 dias), que deve recebê-los como parâmetros.
- O ONS reescreve o arquivo do ano inteiro de tempos em tempos; o leitor sempre baixa o arquivo todo (poucos milhares de linhas, cabe em memória). Se a reescrita trocar o esquema, os `ValueError` dos passos 3.2 a 3.5 fazem a execução falhar alto, como pede `AGENTS.md`.
- Arquivos antigos (2015 a 2024) não tiveram o esquema conferido, só o de 2026. Se o backfill (item 23) encontrar outro esquema, o leitor falha com a coluna ou o código citados; aí abre-se um plano novo, sem afrouxar o leitor no escuro.
- O plano 22 cita `download_load(client, year)`; o nome passa a ser `fetch_load` (decisão abaixo). Ao revisar o plano 22, troque a referência.
- O plano 22 diz que `checks.py` filtra `SE, S, NE, N`; confirma o código `SE`, coerente com este plano e com o `CHECK` do PR 21.

Decisões tomadas aqui (perguntas que tinham opção recomendada; o usuário autorizou seguir as recomendações):

- **Código fora de `SUBSYSTEMS` → `ValueError`, não descarte silencioso.** O arquivo real só tem os 4 códigos; um código novo (ex.: `SIN`, ou `SE` renomeado para `SE/CO`) significa mudança de formato, e descartar em silêncio poderia sumir com um subsistema inteiro. Substitui o antigo caso "SIN descartado".
- **Nulo em `val_cargaenergiamwmed` → linha descartada; nulo na chave → `ValueError`.** A tabela não aceita carga nula ("dia sem valor simplesmente não tem linha", plano 21) e a continuidade do PR 22 acusa o dia faltante; chave nula é arquivo corrompido.
- **Hora diferente de meia-noite → `ValueError`.** O formato confirmado é só data; truncar em silêncio esconderia uma mudança de granularidade.
- **Duplicata de chave → `ValueError` no leitor.** `upsert` já recusa, mas falhar no leitor dá a mensagem mais perto da causa.
- **Nomes `parse_load`/`fetch_load`** em vez de `normalize_load`/`download_load`, para seguir `fetch_json`/`fetch_bytes`/`fetch_forecast`. Constantes em inglês (`LOAD_PREFIX`, `SUBSYSTEMS`) pelo ADR 0001.
- **`sleep` injetável em `fetch_load`**, como em `fetch_forecast`, para testar retry sem esperar.
- **O leitor devolve o ano inteiro, sem filtro nem checagem de atraso.** Mantém o leitor puro e deixa todo valor dependente do item 18 como parâmetro do PR 22.
- **`pyarrow` em vez de `fastparquet`.** É o motor padrão do pandas e o usado na verificação do item 18 (`uv run --with pandas --with pyarrow`).

Bloqueios: nenhum.

## 10. Decisões que exigem ADR

Nenhuma. O leitor não muda `raw` nem `ref` (a tabela é do PR 21, coberta pelo ADR 0005), não mexe no contrato `build_features`/`predict`/`evaluate` nem expõe serviço. Adicionar `pyarrow` é dependência comum, dentro da toolchain do ADR 0002.
