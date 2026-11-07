# 20 — Leitura do parquet de carga diária do ONS

> Executa: agente. Depende de: 14 (usa `ingestion/http.py`), 18 (nomes de arquivo e colunas confirmados). Branch sugerida: `feat/ons-reader`.
> TDD: passo 0 (dependência) → test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Baixar o parquet anual de carga diária do bucket público do ONS e normalizá-lo para o formato de `raw.ons_daily_load` (`subsistema`, `data`, `load_avg_mw`).
Só leitura e transformação; gravar é o PR 22.

## 2. Fora do escopo

- Tabela (PR 21), job, checagem e CLI (PR 22).
- MCP do ONS (o doc o cita como referência; aqui o acesso é HTTP direto ao S3).

## 3. Fase do roadmap

Fase 1 — "Ingestão do ONS + backfill desde 2015 + checagens".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `pyproject.toml`, `uv.lock` | `pyarrow` (passo 0; os testes geram parquet com pandas) |
| `ingestion/ons.py` | `file_url(ano)`, `normalize_load(conteudo: bytes)`, `download_load(cliente, ano, *, base_delay)` |
| `tests/test_ons_reader.py` | Testes (test-writer) |

Fonte (`docs/plataforma-ml.md`): ONS — Carga de Energia Diária, por subsistema (SE/CO, S, NE, N), em MWmed. Bucket S3 público `ons-aws-prod-opendata`, prefixo `dataset/carga_energia_di/`, sem conta AWS. 1 linha por subsistema por dia.

Código existente: `ingestion/http.py` → `fetch_bytes(cliente, url, params=None, *, tentativas=3, base_delay=1.0)` com retry só para rede/429/5xx (PR 14).

**Valores esperados das colunas** (confirmar com o resultado do item 18; se diferirem, use os do item 18 e anote no PR):

| Coluna no parquet do ONS | Coluna normalizada |
| --- | --- |
| `id_subsistema` | `subsistema` |
| `din_instante` | `data` (só a parte de data) |
| `val_cargaenergiamwmed` | `load_avg_mw` |

Arquivo esperado: `https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/carga_energia_di/CARGA_ENERGIA_<ANO>.parquet`.

## 5. Passos

0. (implementer) `uv add pyarrow`. Commit `build: add pyarrow`.
1. (test-writer) Escreva `tests/test_ons_reader.py`. Os testes geram o parquet em memória com um DataFrame no formato da tabela acima (`df.to_parquet(buffer)`) e usam `httpx.MockTransport`; nenhum acesso à rede. Casos na seção 8. Confirme falha por `ModuleNotFoundError: ingestion.ons`. Commit `test: add ons reader tests`.
2. (implementer) `ingestion/ons.py`:
   - Constantes `BUCKET_URL`, `PREFIXO`, `COLUMN_MAP`, `SUBSISTEMAS = ("SE", "S", "NE", "N")`.
   - `file_url(ano: int) -> str`.
   - `normalize_load(conteudo: bytes) -> pd.DataFrame`: lê o parquet, renomeia pelas constantes, converte `data` para `date`, `load_avg_mw` para `float`, mantém só `SUBSISTEMAS` (descarta, por exemplo, um total `SIN` se existir), ordena por (`data`, `subsistema`). Coluna esperada ausente → `ValueError` com o nome da coluna.
   - `download_load(cliente, ano, *, base_delay=1.0) -> pd.DataFrame`: `fetch_bytes(file_url(ano))` e `normalize_load`.
3. Rode os critérios de pronto e refatore com a suíte verde.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_ons_reader.py` | Todos passam, sem rede |
| `uv run python -c "import httpx; from ingestion.ons import download_load; d=download_load(httpx.Client(timeout=60), 2025); print(sorted(d.subsistema.unique()), len(d))"` (manual, com rede) | `['N', 'NE', 'S', 'SE'] 1460` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: a normalização (nomes, tipos, filtro de subsistema) é onde o formato do ONS encontra o nosso contrato.

## 8. Casos de teste

1. Parquet com 2 dias × 4 subsistemas → 8 linhas com colunas exatamente `subsistema, data, load_avg_mw`.
2. `din_instante` como timestamp `2026-11-05 00:00:00` → `data = date(2026, 11, 5)`.
3. Parquet com linhas de `SIN` além dos 4 subsistemas → `SIN` descartado.
4. Parquet sem `val_cargaenergiamwmed` → `ValueError` mencionando a coluna.
5. `file_url(2015)` termina com `dataset/carga_energia_di/CARGA_ENERGIA_2015.parquet`.
6. `download_load` com transporte que devolve 503 e depois o parquet → devolve o DataFrame (retry).
7. `download_load` com 404 → `httpx.HTTPStatusError` (sem retry; arquivo do ano não existe).

## 9. Riscos e perguntas em aberto

- Se o item 18 não tiver sido feito, pare e reporte: nomes de coluna errados fazem o backfill inteiro falhar.
- Em 1º de janeiro o arquivo do ano novo pode não existir ainda; o PR 22 trata isso pela janela de 30 dias, que cruza os dois anos.

## 10. Decisões que exigem ADR

Nenhuma.
