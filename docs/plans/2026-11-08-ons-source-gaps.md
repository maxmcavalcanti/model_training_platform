# Correção: cargas vazias e lacunas conhecidas da fonte do ONS

> Executa: agente. Depende de: PRs 20, 21 e 22 mergeados (`main` em `107f039`). Branch sugerida: `fix/ons-source-gaps`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.
> Decisões D1 a D10 (seção 9) adotadas por recomendação, com autorização do usuário. Bloqueia o item 23 (backfill em produção).

## 1. Objetivo

Fazer `parse_load` aceitar os arquivos reais de 2013 a 2015 (carga `''` ou só espaços vira nula e a linha cai; a checagem de meia-noite passa a olhar só as linhas que ficam).
Fazer `check_ons_daily_load` tolerar só as lacunas da fonte já conhecidas (dia inteiro, 4 subsistemas), sem afrouxar nada mais: o backfill de 2015 passa com 1456 linhas.

## 2. Fora do escopo

- Rodar o backfill em produção e avisar a cientista (item 23, `docs/plans/23-backfill-ons-e-pronto-fase-1-manual.md`). **Não editar o plano 23**: as mudanças que ele precisa estão listadas no relatório desta tarefa e na seção 9 (R6).
- Mudar o escopo do backfill: continua 2015-01-01 em diante. As entradas de 2013-12-01 e 2014-02-01 só ficam documentadas na constante.
- Mudar `ONS_WINDOW_DAYS`, `ONS_MAX_DELAY_DAYS`, o crontab, `ingestion/cli.py` ou `ingestion/jobs.py` (D7: o job não muda).
- Mudar `raw.ons_daily_load` (sem migração), o contrato `build_features`/`predict`/`evaluate`, ADRs, `docs/guia-ciencia-de-dados.md`, `.claude/`, `AGENTS.md`.
- Preencher, interpolar ou buscar em outra fonte os dias sem dado (o dia simplesmente não existe na tabela).
- Logar quantas linhas foram descartadas por carga nula (o comportamento atual para nulos já é silencioso; quem acusa buraco é a checagem).
- Corrigir `SE/CO` na tabela de fontes de `docs/plataforma-ml.md`.
- Fechar o item 18 (atraso e revisões).

## 3. Fase do roadmap

Fase 1 — "Banco e carga do ONS", item "Ingestão do ONS + backfill desde 2015 + checagens" (`docs/plataforma-ml.md`, "Roadmap"). É correção do job entregue nos PRs 20 e 22, necessária para o backfill do item 23.

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `tests/test_ons_reader.py` | Alterar (test-writer): casos 19 a 27 (cargas em texto, vazias, espaços, não numéricas, linha órfã) |
| `tests/test_checks_ons_load.py` | Alterar (test-writer): casos 28 a 35 (lacunas conhecidas) |
| `tests/test_job_ons_load.py` | Alterar (test-writer): casos 36 a 38 (backfill de 2015 com banco) |
| `ingestion/ons.py` | `parse_load`: normalizar a coluna de carga e mover a checagem de meia-noite para depois do descarte; nova constante `ONS_KNOWN_GAPS` |
| `ingestion/checks.py` | `check_ons_daily_load`: parâmetro `known_gaps` (padrão `ONS_KNOWN_GAPS`) e exclusão dessas datas da continuidade |
| `docs/plataforma-ml.md` | Um subitem no bloco do ONS em "Para verificar antes da Fase 1" registrando o levantamento 2000–2026 (D9) |

### 4.1 Fatos da fonte (levantamento de todos os arquivos anuais 2000–2026, feito por agente em 2026-11-08)

- Sintoma: `ons-load --start 2015-01-01 --end 2015-12-31` com rede real falhou em `parse_load` com `ValueError: could not convert string to float: ''`.
- `val_cargaenergiamwmed` é **texto** nos arquivos até 2021 e `float64` a partir de 2022.
- Só 2013, 2014 e 2015 têm anomalias; nenhuma outra em 2000–2026:
  - 2015-04-09: carga `''` nos 4 subsistemas (buraco real na fonte).
  - 2014-02-01: idem.
  - 2013-12-01: idem.
  - 2013: uma linha órfã do subsistema `S` em `2013-02-02 00:00:01` com carga vazia; a linha verdadeira de `2013-02-02 00:00:00` também existe. Hoje ela derruba a checagem de meia-noite.
- 2026 é ano parcial (termina em 2026-11-06 no levantamento).
- Linhas esperadas no backfill: 2015 tem 365 dias, menos 1 dia sem dado = 364 × 4 = **1456** (não 1460).

### 4.2 Regras que se aplicam

`.claude/rules/migrations-e-dados.md`:

> Job de ingestão: idempotente, reprocessável por data, upsert por chave, `ingested_at`, checagem pandera depois de gravar, retry com backoff (3 tentativas) só para erro de rede.
> Mudança em `raw` ou `ref` exige migração Alembic + ADR + aviso à ciência de dados.

`AGENTS.md`: "Todo job termina com checagem de qualidade (pandera). Checagem falha = execução falha." Identificadores, comentários, logs e mensagens de erro em inglês (ADR 0001); prosa de `docs/` em português. TDD estrito: código de produção só depois de teste vermelho.

### 4.3 Código atual a alterar

`ingestion/ons.py` (PR 20), trecho relevante de `parse_load`:

```python
SUBSYSTEMS = ("SE", "S", "NE", "N")

def parse_load(content: bytes) -> pd.DataFrame:
    """Validate and normalize a daily-load parquet into ``subsystem, date, load_avg_mw``."""
    try:
        raw = pd.read_parquet(io.BytesIO(content))
    except (pa.ArrowException, OSError, ValueError) as error:
        raise ValueError(f"content is not a readable parquet file: {error}") from error

    for column in COLUMN_MAP:
        if column not in raw.columns:
            raise ValueError(f"missing column in ONS load file: {column}")

    frame = raw[list(COLUMN_MAP)].copy()
    for column in ("id_subsistema", "din_instante"):
        if frame[column].isna().any():
            raise ValueError(f"null values in key column: {column}")

    unknown = sorted(set(frame["id_subsistema"]) - set(SUBSYSTEMS))
    if unknown:
        raise ValueError(f"unknown subsystem codes: {unknown}")

    instants = pd.to_datetime(frame["din_instante"])
    if (instants != instants.dt.normalize()).any():
        raise ValueError("din_instante has timestamps that are not at midnight")
    frame["din_instante"] = instants

    frame = frame.dropna(subset=["val_cargaenergiamwmed"])

    duplicated = frame.duplicated(subset=["id_subsistema", "din_instante"], keep=False)
    if duplicated.any():
        ...  # raise ValueError(f"duplicate (subsystem, date) keys: {keys}")

    result = frame.rename(columns=COLUMN_MAP)
    result["date"] = result["date"].dt.date
    result["load_avg_mw"] = result["load_avg_mw"].astype("float64")   # <- falha com '' (texto)
    return result.sort_values(["date", "subsystem"]).reset_index(drop=True)
```

Observação para o implementer: o projeto usa `pandas>=3.1.1` e `pyarrow>=26.0.1` (`pyproject.toml`). No pandas 3, uma coluna de texto lida de parquet costuma vir com dtype `str` (não `object`); a normalização tem de funcionar para os dois e também para `float64` (arquivos de 2022 em diante), sem mudar o resultado destes.

`ingestion/checks.py` (PR 22), atual:

```python
_ONS_SUBSYSTEM_COUNT = 4

def check_ons_daily_load(df: pd.DataFrame, start: date, end: date, max_delay_days: int) -> None:
    """Check stored ONS daily load: schema, 4 subsystems per day, continuity and freshness.

    All problems are reported together in a single :class:`CheckFailed`.
    """
    problems: list[str] = []
    try:
        ONS_DAILY_LOAD_SCHEMA.validate(df, lazy=True)
    except pandera.errors.SchemaErrors as error:
        problems.append(_describe(error))

    if df.empty:
        problems.append(f"no rows between {start} and {end}")
    else:
        counts = df.groupby("date").size()
        for day, count in counts.items():
            if count != _ONS_SUBSYSTEM_COUNT:
                problems.append(f"{day} has {count} rows, expected {_ONS_SUBSYSTEM_COUNT}")
        present = set(counts.index)
        last = max(present)
        missing = [
            day.isoformat()
            for day in (start + timedelta(days=n) for n in range((last - start).days + 1))
            if day not in present
        ]
        if missing:
            problems.append(f"missing dates: {', '.join(missing)}")
        limit = end - timedelta(days=max_delay_days)
        if last < limit:
            problems.append(f"stale: last date {last} is older than {limit}")
    if problems:
        raise CheckFailed("; ".join(problems))
```

`ingestion/jobs.py` (PR 22), **não muda**: `ingest_ons_load(engine, client, start, end, *, max_delay_days=ONS_MAX_DELAY_DAYS, base_delay=1.0)` baixa os anos, filtra `start <= date <= end`, faz upsert, relê o intervalo e chama `check_ons_daily_load(stored, start, end, max_delay_days)` (sem passar `known_gaps`, portanto com o padrão). O job não calcula linhas esperadas: a expectativa vem toda da checagem (4 por data presente, nenhuma data faltando de `start` até a última presente).

### 4.4 Padrões de teste existentes (reusar)

- `tests/test_ons_reader.py`: `_frame(rows)` monta as 4 colunas do ONS com `val_cargaenergiamwmed` em `float64`; `_to_parquet(frame)`; `_grid()` = 2026-11-05 e 2026-11-06 × `SE`, `S`, `NE`, `N`. Os casos novos precisam de uma variante com a carga em **texto** (Series de strings, `dtype="object"` ou `"str"`), como nos arquivos até 2021, e com `din_instante` com hora (para a linha órfã).
- `tests/test_checks_ons_load.py`: `_grid(first, last)` monta o DataFrame relido (`subsystem`, `date`, `load_avg_mw`) com `LOADS = {"SE": 40000.0, "S": 12000.0, "NE": 11000.0, "N": 7000.0}`; `_drop(frame, mask)`; `_expect_failure(frame)` usa `START`/`END` fixos de 2026, então os casos de 2015 chamam `check_ons_daily_load` direto com as datas de 2015.
- `tests/test_job_ons_load.py`: marcador `db`, fixture `load_database`, `Source({ano: _file(rows)})` (MockTransport por ano), `_run_as_ingestor(url, source, start, end)`, `_stored(url, where)`. `_parquet(rows)` grava a carga em `float64`; os casos novos precisam de uma variante com a carga em texto, para reproduzir o arquivo de 2015.
- Nenhum teste toca a rede real.

## 5. Passos

0. (test-writer e implementer) Confirme a base: `git log --oneline -1` na `main` mostra `107f039` ou posterior, e `uv run pytest tests/test_ons_reader.py tests/test_checks_ons_load.py -q` está verde. Se não, **parar**.
1. (test-writer) Na branch `fix/ons-source-gaps`, a partir da `main`, escreva os casos 19 a 38 (seção 8) nos três arquivos de teste da seção 4, sem alterar os casos existentes. Rode `uv run pytest tests/test_ons_reader.py tests/test_checks_ons_load.py tests/test_job_ons_load.py` com o Postgres de teste no ar (`docker compose -f infra/docker-compose.dev.yml up -d`) e confirme que os novos falham pelo motivo certo: `ValueError` de conversão ou de meia-noite em `parse_load`, `ImportError` de `ONS_KNOWN_GAPS`, `TypeError` por `known_gaps` inexistente, ou `CheckFailed` citando `2015-04-09`. Casos que já passam antes da mudança (19 e 26, caracterização) devem ser apontados no commit como tal. `uv run ruff check .` e `uv run ruff format --check .` limpos. Commit `test: cover empty ONS loads and known source gaps`.
2. (implementer) `ingestion/ons.py`: crie, logo abaixo de `SUBSYSTEMS`, a constante com comentário em inglês citando o levantamento (D4):

   ```python
   # Days with no load for any subsystem in the ONS source itself (survey of 2000-2026 files,
   # 2026-11-08). check_ons_daily_load tolerates them only as whole-day gaps.
   ONS_KNOWN_GAPS = frozenset({date(2013, 12, 1), date(2014, 2, 1), date(2015, 4, 9)})
   ```

3. `parse_load`, nesta ordem, mantendo as validações atuais de parquet, colunas, chave nula e subsistema desconhecido no início:
   1. Normalizar `val_cargaenergiamwmed` (D1): se a coluna não for numérica, retirar espaços nas pontas; texto vazio depois disso vira nulo; o resto é convertido para `float64`. Texto não vazio que não converte para número, ou que converte para NaN (ex.: `"nan"`), levanta `ValueError` com mensagem em inglês que cita `val_cargaenergiamwmed` e o(s) valor(es) problemático(s) (no máximo alguns, ordenados). Coluna já numérica passa como está.
   2. Descartar as linhas com carga nula (mesma regra de hoje).
   3. Só então converter `din_instante` e checar meia-noite **nas linhas que ficaram** (D2). A mensagem atual (`din_instante has timestamps that are not at midnight`) não muda.
   4. Duplicatas, renomeação, `date` como `datetime.date`, `float64` e ordenação seguem como hoje.
4. `ingestion/checks.py`:
   - `from ingestion.ons import ONS_KNOWN_GAPS` (não cria ciclo: `ingestion/ons.py` não importa `checks`).
   - Nova assinatura: `check_ons_daily_load(df, start, end, max_delay_days, *, known_gaps: frozenset[date] = ONS_KNOWN_GAPS) -> None`. Docstring cita a tolerância.
   - Na lista `missing`, ignorar datas que estão em `known_gaps` (D3). Nada mais muda: a contagem por data (4 por data presente) continua valendo para datas de `known_gaps` (lacuna parcial falha), o "no rows" continua para DataFrame vazio (D6) e a regra `stale` continua calculada sobre a última data presente (D5).
5. `docs/plataforma-ml.md`: no bloco "Com que atraso o ONS publica..." de "Para verificar antes da Fase 1", acrescente um subitem em português (D9) com: carga em texto até 2021 e `float64` desde 2022; dias sem carga na fonte (2013-12-01, 2014-02-01, 2015-04-09, os 4 subsistemas); a linha órfã de 2013-02-02 00:00:01; tratamento adotado (carga vazia descartada, lacunas listadas em `ONS_KNOWN_GAPS`). Não marque checkbox nenhum.
6. Rode os critérios de pronto e cole comando e saída no PR. No corpo do PR, liste D1 a D10 e diga que o plano 23 precisa ser atualizado antes do backfill (R6).

## 6. Critérios de pronto

Precisa do Postgres de teste: `docker compose -f infra/docker-compose.dev.yml up -d`. Os comandos com `echo $?` são de bash; no PowerShell use `echo $LASTEXITCODE`.

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_ons_reader.py tests/test_checks_ons_load.py tests/test_job_ons_load.py` | Todos passam (antigos e novos), nenhum `skipped` |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | Nenhum arquivo a reformatar |
| Com rede: `uv run python -c "import httpx; from ingestion.ons import fetch_load; c = httpx.Client(timeout=60); print({y: len(fetch_load(c, y)) for y in (2013, 2014, 2015)})"` | `{2013: 1456, 2014: 1456, 2015: 1456}`, sem exceção. Se algum número diferir, colar a saída no PR e parar |
| Com rede: `uv run python -c "import httpx; from ingestion.ons import fetch_load; c = httpx.Client(timeout=60); [fetch_load(c, y) for y in range(2000, 2027)]; print('ok')"` | `ok` (os 27 arquivos anuais são lidos sem `ValueError`) |
| Banco local migrado (`uv run alembic upgrade head`), `DATABASE_URL` apontando para ele, com rede: `uv run python -m ingestion ons-load --start 2015-01-01 --end 2015-12-31; echo $?` | `0` |
| Em seguida: `select count(*), count(distinct "date") from raw.ons_daily_load where "date" between '2015-01-01' and '2015-12-31'` | `1456`, `364` |
| `select count(*) from raw.ons_daily_load where "date" = '2015-04-09'` | `0` |
| `git diff --name-only main...HEAD` | Só os 6 arquivos da seção 4 (mais este plano, se for no mesmo PR) |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: muda a lógica de `parse_load` (conversão da carga e ordem da checagem de meia-noite) e da continuidade em `check_ons_daily_load`.

## 8. Casos de teste

Os casos 1 a 18 (`tests/test_ons_reader.py`), 1 a 10 (`tests/test_checks_ons_load.py`) e 11 a 34 (`tests/test_job_ons_load.py`) continuam verdes sem edição. Numeração nova segue a partir de 19 para não colidir com a do leitor; o test-writer pode renumerar por arquivo, desde que cite este plano.

Leitor (`tests/test_ons_reader.py`, sem banco nem rede; "carga em texto" = coluna `val_cargaenergiamwmed` de strings no parquet, como até 2021):

19. Grade de 2 dias × 4 subsistemas com carga em texto (`"41234.5"`, ...) → 8 linhas; `load_avg_mw` em `float64`; `SE` de 2026-11-05 = `41234.5` (caracterização: já passa hoje).
20. Carga em texto com `""` numa linha → essa (`subsystem`, `date`) não aparece; 7 linhas; sem nulos em `load_avg_mw`; índice 0..6.
21. Carga em texto só com espaços (parametrizar: `"   "`, `"\t"`, `" \n "`) e com nulo verdadeiro na coluna de texto (`None`) numa linha → linha descartada; 7 linhas.
22. Carga em texto com espaços nas pontas (`" 41234.5 "`) → mantida, valor `41234.5`.
23. Carga em texto não numérica e não vazia (parametrizar: `"abc"`, `"12,5"`, `"nan"`) → `ValueError` cuja mensagem contém `val_cargaenergiamwmed`.
24. Dia inteiro vazio: grade de 2015-04-08 a 2015-04-10 em texto, com `""` nos 4 subsistemas de 2015-04-09 → 8 linhas; nenhuma de 2015-04-09; 2015-04-08 e 2015-04-10 com 4 subsistemas cada.
25. Linha órfã: grade de 2013-02-01 a 2013-02-03 em texto, mais uma linha (`S`, `2013-02-02 00:00:01`, `""`) → sem exceção; 12 linhas; (`S`, 2013-02-02) aparece uma vez, com o valor da linha de `00:00:00`.
26. Linha fora da meia-noite com carga não vazia: grade em texto mais (`S`, `2013-02-02 00:00:01`, `"123.0"`) → `ValueError` (meia-noite). O caso 8 existente cobre o mesmo para carga `float64`.
27. Linha fora da meia-noite com carga `float64` nula (NaN) e a linha verdadeira de meia-noite presente → sem exceção; a linha órfã some (mesma regra do caso 25 para arquivos de 2022 em diante).

Checagem pura (`tests/test_checks_ons_load.py`, sem banco; grade = todos os dias × 4 subsistemas com `LOADS`; `max_delay_days = 5` salvo indicação):

28. `ONS_KNOWN_GAPS` (importado de `ingestion.ons`) é exatamente `{2013-12-01, 2014-02-01, 2015-04-09}`.
29. Lacuna conhecida aceita: grade de 2015-01-01 a 2015-12-31 sem 2015-04-09, `start = 2015-01-01`, `end = 2015-12-31` → passa (1456 linhas).
30. Lacuna desconhecida no mesmo intervalo: como o caso 29, mas sem 2015-04-10 também → `CheckFailed` cuja mensagem cita `2015-04-10` e **não** cita `2015-04-09`.
31. Lacuna parcial na data conhecida: grade de 2015 com 2015-04-09 só para 3 subsistemas (sem `N`) → `CheckFailed` citando `2015-04-09`.
32. Data conhecida com os 4 subsistemas presentes (fonte corrigida depois) → passa.
33. Intervalo que começa na lacuna: `start = 2015-04-09`, `end = 2015-04-30`, grade de 2015-04-10 a 2015-04-30 → passa.
34. Parâmetro `known_gaps`: grade de 2026-10-10 a 2026-11-05 sem 2026-10-20, `start = 2026-10-10`, `end = 2026-11-08`, `known_gaps = frozenset({2026-10-20})` → passa; a grade de 2015 do caso 29 com `known_gaps = frozenset()` → `CheckFailed` citando `2015-04-09`.
35. Intervalo só com a lacuna: DataFrame vazio, `start = end = 2015-04-09` → `CheckFailed` com `no rows`.

Job com banco (`tests/test_job_ons_load.py`, `db`, como `ingestor`, `base_delay=0`, parquet de 2015 com carga em texto):

36. Backfill de 2015 como o arquivo real: grade de 2015-01-01 a 2015-12-31 com `""` nos 4 subsistemas de 2015-04-09; `start = 2015-01-01`, `end = 2015-12-31` → sem exceção; devolve 1456; 1456 linhas na tabela; nenhuma de 2015-04-09; uma requisição, para `CARGA_ENERGIA_2015.parquet`.
37. Como o caso 36, mas também com `""` nos 4 subsistemas de 2015-07-01 → `CheckFailed` citando `2015-07-01`; 1452 linhas gravadas.
38. Como o caso 36, mas com `""` só em 3 subsistemas de 2015-04-09 (o `N` tem valor) → `CheckFailed` citando `2015-04-09`; 1457 linhas gravadas.

## 9. Riscos e perguntas em aberto

Nenhuma pergunta em aberto bloqueia. Decisões (recomendações adotadas, com autorização do usuário):

- **D1. `''` e texto só com espaços viram nulo; qualquer outro texto não numérico levanta `ValueError`.** É a mesma regra que já vale para carga nula (linha descartada), estendida ao jeito como os arquivos até 2021 representam o nulo. Texto não numérico que não seja vazio é formato desconhecido e tem de falhar alto. `"nan"` também falha: não aparece na fonte e aceitar seria um descarte silencioso novo. Espaços nas pontas de um número são retirados porque a mesma limpeza que reconhece "só espaços" já os retira; não muda nenhum valor válido.
- **D2. Checagem de meia-noite só nas linhas que sobram depois do descarte.** A linha órfã de 2013 (`00:00:01`, carga vazia) não carrega dado nenhum; descartá-la antes de julgar o horário resolve 2013 sem afrouxar a regra: uma linha fora da meia-noite **com** carga continua levantando `ValueError` (casos 8 e 26).
- **D3. Lacunas conhecidas só como dia inteiro.** A tolerância age apenas na lista de datas faltantes. A contagem "4 linhas por data presente" não muda, então 1 a 3 subsistemas numa data conhecida continuam falhando (casos 31 e 38); qualquer outra data ausente continua falhando (casos 30 e 37). Data conhecida que volte a ter os 4 subsistemas passa (caso 32): se o ONS corrigir a fonte, o upsert simplesmente grava.
- **D4. `ONS_KNOWN_GAPS` em `ingestion/ons.py`, como fato da fonte, com as 3 datas.** Fica ao lado de `SUBSYSTEMS` (outro fato da fonte); a checagem importa dali. 2013-12-01 e 2014-02-01 ficam fora do backfill (que começa em 2015-01-01), mas entram na constante para documentar o levantamento e para que um backfill futuro mais antigo não falhe por elas. Lista explícita e pequena: uma lacuna nova exige PR com teste, de propósito.
- **D5. Atraso (`stale`) não muda.** As lacunas são de 2013–2015; a regra de atraso olha a última data presente contra `end - max_delay_days` e não é afetada nos usos reais (backfill de anos fechados e janela diária de 2026).
- **D6. DataFrame vazio continua falhando, mesmo que o intervalo só contenha datas conhecidas (caso 35).** Rodar o job só sobre um dia sem dado não tem uso; falhar alto é mais simples que um caso especial.
- **D7. `ingestion/jobs.py` não muda.** O job não calcula linhas esperadas: chama `check_ons_daily_load` com o padrão `known_gaps = ONS_KNOWN_GAPS`, e a checagem espera 4 linhas por data presente e todas as datas de `start` até a última presente, menos as conhecidas. Para 2015: 364 datas × 4 = 1456.
- **D8. `known_gaps` é parâmetro só-palavra-chave com padrão.** A assinatura existente continua funcionando (testes 1 a 10 e o job), e os testes podem fixar lacunas sintéticas sem depender das datas reais (caso 34).
- **D9. Registrar o levantamento em `docs/plataforma-ml.md`.** É onde estão os fatos verificados da fonte (item 18); o plano 22 e o código citam essa seção. Sem marcar checkbox.
- **D10. Sem ADR e sem migração.** É tratamento de qualidade da fonte dentro do job: não muda schema de `raw`/`ref`, o contrato `build_features`/`predict`/`evaluate`, rede nem dependências.

Riscos:

- **R1. O levantamento foi feito por agente e não foi refeito aqui.** Se 2016–2021 tiverem outro formato de texto (ex.: vírgula decimal), o backfill falha com `ValueError` citando o valor (falha alta, D1). Os dois critérios de pronto com rede (contagens de 2013–2015 e leitura de 2000–2026) confirmam antes do merge.
- **R2. dtype `str` do pandas 3.** Teste com coluna `object` pode passar e o arquivo real (lido como `str`) não, ou o contrário. O round-trip por parquet nos testes e o critério com rede cobrem os dois.
- **R3. O ONS pode reescrever anos fechados** (o item 18 sugere reescrita do ano inteiro). Lacuna nova ou formato novo num ano antigo faz o backfill falhar até um PR acrescentar a data; é o comportamento desejado.
- **R4. O ONS pode preencher uma lacuna conhecida depois.** O upsert grava normalmente e a checagem passa (D3, caso 32); a entrada na constante fica obsoleta, mas inofensiva.
- **R5. Postgres de teste:** sem o container, os testes `db` (casos 36 a 38) falham, não pulam, por desenho de `tests/conftest.py`.
- **R6. O plano 23 fica desatualizado e não é editado aqui.** Antes de rodar o backfill, o usuário (ou um plano próprio) precisa: (a) pôr este PR como dependência; (b) trocar a expectativa da consulta de buracos (`generate_series ... except ...`) de "nenhuma linha" para "exatamente uma linha, `2015-04-09`"; (c) registrar que cada subsistema tem `count = (current_date − 2 − 2015-01-01 + 1) − 1` linhas e as contagens continuam iguais entre subsistemas; (d) no aviso à cientista, dizer que 2015-04-09 não tem dado do ONS em nenhum subsistema (buraco da própria fonte, não falha do job) e que a carga de 2015 tem 1456 linhas, não 1460. O critério "2015 = 1460" do plano 22 (já mergeado) também fica superado por este plano.
- **R7. Aviso à cientista:** sim, deve mencionar 2015-04-09 (único dia sem dado dentro do intervalo que ela vai ver). 2013-12-01 e 2014-02-01 só precisam ser citados se o backfill um dia for antes de 2015.

## 10. Decisões que exigem ADR

- **Nenhum ADR.** É tratamento de qualidade da fonte dentro do job de ingestão (D10): não muda o schema de `raw.ons_daily_load` nem de `ref`, não muda a assinatura de `build_features`, `predict` ou `evaluate`, não expõe serviço e não adiciona dependência. O comportamento novo fica registrado neste plano, na constante comentada e em `docs/plataforma-ml.md`.
