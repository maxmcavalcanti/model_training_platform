# 20 — Leitura do parquet de carga diária do ONS

> Executa: agente. Depende de: 14 (usa `ingestion/http.py`), 18 (nomes de arquivo e colunas confirmados). Branch sugerida: `feat/ons-leitura`.
> TDD: passo 0 (dependência) → test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Baixar o parquet anual de carga diária do bucket público do ONS e normalizá-lo para o formato de `raw.ons_carga_diaria` (`subsistema`, `data`, `carga_mwmed`).
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
| `ingestion/ons.py` | `url_arquivo(ano)`, `normalizar_carga(conteudo: bytes)`, `baixar_carga(cliente, ano, *, espera_base)` |
| `tests/test_ons_leitura.py` | Testes (test-writer) |

Fonte (`docs/plataforma-ml.md`): ONS — Carga de Energia Diária, por subsistema (SE/CO, S, NE, N), em MWmed. Bucket S3 público `ons-aws-prod-opendata`, prefixo `dataset/carga_energia_di/`, sem conta AWS. 1 linha por subsistema por dia.

Código existente: `ingestion/http.py` → `obter_bytes(cliente, url, params=None, *, tentativas=3, espera_base=1.0)` com retry só para rede/429/5xx (PR 14).

**Valores esperados das colunas** (confirmar com o resultado do item 18; se diferirem, use os do item 18 e anote no PR):

| Coluna no parquet do ONS | Coluna normalizada |
| --- | --- |
| `id_subsistema` | `subsistema` |
| `din_instante` | `data` (só a parte de data) |
| `val_cargaenergiamwmed` | `carga_mwmed` |

Arquivo esperado: `https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/carga_energia_di/CARGA_ENERGIA_<ANO>.parquet`.

## 5. Passos

0. (implementer) `uv add pyarrow`. Commit `build: add pyarrow`.
1. (test-writer) Escreva `tests/test_ons_leitura.py`. Os testes geram o parquet em memória com um DataFrame no formato da tabela acima (`df.to_parquet(buffer)`) e usam `httpx.MockTransport`; nenhum acesso à rede. Casos na seção 8. Confirme falha por `ModuleNotFoundError: ingestion.ons`. Commit `test: add ons reader tests`.
2. (implementer) `ingestion/ons.py`:
   - Constantes `BUCKET_URL`, `PREFIXO`, `MAPA_COLUNAS`, `SUBSISTEMAS = ("SE", "S", "NE", "N")`.
   - `url_arquivo(ano: int) -> str`.
   - `normalizar_carga(conteudo: bytes) -> pd.DataFrame`: lê o parquet, renomeia pelas constantes, converte `data` para `date`, `carga_mwmed` para `float`, mantém só `SUBSISTEMAS` (descarta, por exemplo, um total `SIN` se existir), ordena por (`data`, `subsistema`). Coluna esperada ausente → `ValueError` com o nome da coluna.
   - `baixar_carga(cliente, ano, *, espera_base=1.0) -> pd.DataFrame`: `obter_bytes(url_arquivo(ano))` e `normalizar_carga`.
3. Rode os critérios de pronto e refatore com a suíte verde.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_ons_leitura.py` | Todos passam, sem rede |
| `uv run python -c "import httpx; from ingestion.ons import baixar_carga; d=baixar_carga(httpx.Client(timeout=60), 2025); print(sorted(d.subsistema.unique()), len(d))"` (manual, com rede) | `['N', 'NE', 'S', 'SE'] 1460` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: a normalização (nomes, tipos, filtro de subsistema) é onde o formato do ONS encontra o nosso contrato.

## 8. Casos de teste

1. Parquet com 2 dias × 4 subsistemas → 8 linhas com colunas exatamente `subsistema, data, carga_mwmed`.
2. `din_instante` como timestamp `2026-11-05 00:00:00` → `data = date(2026, 11, 5)`.
3. Parquet com linhas de `SIN` além dos 4 subsistemas → `SIN` descartado.
4. Parquet sem `val_cargaenergiamwmed` → `ValueError` mencionando a coluna.
5. `url_arquivo(2015)` termina com `dataset/carga_energia_di/CARGA_ENERGIA_2015.parquet`.
6. `baixar_carga` com transporte que devolve 503 e depois o parquet → devolve o DataFrame (retry).
7. `baixar_carga` com 404 → `httpx.HTTPStatusError` (sem retry; arquivo do ano não existe).

## 9. Riscos e perguntas em aberto

- Se o item 18 não tiver sido feito, pare e reporte: nomes de coluna errados fazem o backfill inteiro falhar.
- Em 1º de janeiro o arquivo do ano novo pode não existir ainda; o PR 22 trata isso pela janela de 30 dias, que cruza os dois anos.

## 10. Decisões que exigem ADR

Nenhuma.
