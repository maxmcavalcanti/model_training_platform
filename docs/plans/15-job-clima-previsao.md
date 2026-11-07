# 15 — Job `clima-previsao`: snapshot diário, checagem e CLI

> Executa: agente. Depende de: 11, 13, 14. Branch sugerida: `feat/job-clima-previsao`.
> **Antecipado** (Fase 2 antes do fim da Fase 1, decisão P5).
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar o job que tira o snapshot da previsão de hoje para todos os locais de `ref.locais`, grava em `raw.clima_previsao` sem sobrescrever snapshot existente e termina com checagem pandera.
Exposto como `python -m ingestion clima-previsao`; o agendamento é o PR 16.

## 2. Fora do escopo

- Agendamento (PR 16) e deploy (item 17).
- Alertas no Telegram (PR 55); até lá, falha = código de saída 1 e log.
- Flow do Prefect (PR 32).

## 3. Fase do roadmap

Fase 2 — "`raw.clima_previsao` coletando todo dia (prioridade)".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `pyproject.toml`, `uv.lock` | `pandera` |
| `ingestion/checks.py` | `ChecagemFalhou`, `checar(df, schema, linhas_esperadas=None)` e `SCHEMA_CLIMA_PREVISAO` |
| `ingestion/jobs.py` | `listar_locais(conn)` e `ingest_clima_previsao(engine, cliente, hoje)` |
| `ingestion/cli.py` | Subcomando `clima-previsao` |
| `tests/test_checks_clima_previsao.py`, `tests/test_job_clima_previsao.py` | Testes (test-writer) |

Código existente que este PR usa (leia antes):

- `ingestion/db.py`: `criar_engine()`, `upsert(conn, tabela, linhas, chaves, *, ao_conflitar, carimbar_ingerido_em)` (PR 08).
- `ingestion/openmeteo.py`: `Local`, `buscar_previsao(cliente, local, emitida_em, dias=7, *, espera_base)` (PR 14).
- `ingestion/cli.py`: registro `SUBCOMANDOS` e códigos de saída 0/1/2 (PR 11).

Regras (`.claude/rules/migrations-e-dados.md`):

> Job de ingestão: idempotente, reprocessável por data, upsert por chave, `ingerido_em`, checagem pandera depois de gravar, retry com backoff (3 tentativas) só para erro de rede.
> `raw.clima_previsao` guarda a previsão como emitida (`emitida_em`). Nunca sobrescrever uma previsão antiga com uma nova.

Checagem (`docs/plataforma-ml.md`): "linhas esperadas por dia, sem nulos nas colunas-chave, valores dentro de faixas plausíveis (… temperatura entre −10 e 50 °C)".

## 5. Passos

1. (test-writer) Escreva os testes da seção 8. Os do job usam `banco_migrado` (`@pytest.mark.db`), `httpx.MockTransport` que responde com a fixture `tests/fixtures/openmeteo_previsao_sao_paulo.json` (ajustando `latitude`/`longitude` não é preciso: o local vem do parâmetro) e `hoje` fixo igual ao primeiro dia da fixture. Confirme falha por `ModuleNotFoundError: ingestion.checks`. Commit `test: add clima-previsao job tests`.
2. (implementer) `uv add pandera`. Use o caminho de import recomendado pela versão instalada (nas versões recentes, `import pandera.pandas as pa`).
3. `ingestion/checks.py`:
   - `class ChecagemFalhou(RuntimeError)`.
   - `checar(df, schema, linhas_esperadas: int | None = None) -> None`: valida com `schema.validate(df, lazy=True)`; se `linhas_esperadas` for dado e diferente de `len(df)`, falha. Toda falha vira `ChecagemFalhou` com mensagem legível (quais colunas/linhas).
   - `SCHEMA_CLIMA_PREVISAO`: `local_id`, `emitida_em`, `data_alvo` não nulos; `horizonte_dias` entre 1 e 7; `temp_max` e `temp_min` entre −10 e 50 (nulos permitidos); `precip_mm` ≥ 0; `vento_max` ≥ 0; `umidade_media` entre 0 e 100; checagem de DataFrame `temp_min <= temp_max` onde ambos existem; unicidade de (`local_id`, `emitida_em`, `data_alvo`).
4. `ingestion/jobs.py`:
   - `listar_locais(conn) -> list[Local]` lendo `ref.locais` ordenado por `local_id`.
   - `ingest_clima_previsao(engine, cliente, hoje: date, *, espera_base=1.0) -> None`:
     1. Lê os locais.
     2. Para cada local, chama `buscar_previsao`. Se um local falhar, registra o erro e **continua** com os outros (cada local que falha é histórico perdido; os outros não devem pagar por ele).
     3. Grava o que deu certo com `upsert(..., "raw.clima_previsao", chaves=["local_id", "emitida_em", "data_alvo"], ao_conflitar="ignorar")`, numa transação.
     4. Relê `raw.clima_previsao` com `emitida_em = hoje` e roda `checar(df, SCHEMA_CLIMA_PREVISAO, linhas_esperadas=len(locais) * 7)`.
     5. Se algum local falhou no passo 2, levanta `RuntimeError` listando os locais, **depois** de gravar os demais.
   - Não há parâmetro de data: a API só devolve a previsão atual, então não existe reprocessar um dia passado. Reexecutar no mesmo dia completa locais que faltaram e não muda os que já existem.
5. `ingestion/cli.py`: subcomando `clima-previsao`, sem argumentos; usa `criar_engine()`, `httpx.Client(timeout=30)` e `hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()`. `ChecagemFalhou` ou qualquer exceção → código 1.
6. Rode os critérios de pronto e refatore com a suíte verde.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_checks_clima_previsao.py tests/test_job_clima_previsao.py` | Todos passam |
| `uv run python -m ingestion --help` | Lista `clima-previsao` |
| Com o compose de dev rodando e o banco migrado: `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/<banco> uv run python -m ingestion clima-previsao; echo $?` (manual, com rede) | Log com 4 locais e `0` |
| Em seguida: `psql ... -c "select count(*) from raw.clima_previsao"` | `28` |
| Rodar o mesmo comando de novo e contar | Continua `28` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: é o job de maior prioridade e as regras "nunca sobrescrever", "falha parcial grava os outros" e "checagem falha = execução falha" precisam de prova.

## 8. Casos de teste

Checagem:
1. DataFrame válido de 28 linhas com `linhas_esperadas=28` → não levanta.
2. `linhas_esperadas=28` e 27 linhas → `ChecagemFalhou` mencionando `28` e `27`.
3. `temp_max = 51` → `ChecagemFalhou` mencionando `temp_max`.
4. `temp_min > temp_max` numa linha → `ChecagemFalhou`.
5. `precip_mm = -0.1` → `ChecagemFalhou`.
6. `local_id` nulo → `ChecagemFalhou`.
7. `temp_max` nulo (valor ausente na fonte) → não levanta.

Job (banco com os 4 locais do PR 09):
8. Primeira execução → 28 linhas com `emitida_em = hoje`, horizontes 1 a 7 para cada local; sem exceção.
9. Segunda execução no mesmo dia, com a API devolvendo temperaturas diferentes → continua 28 linhas e os valores são os da **primeira** execução.
10. Execução no dia seguinte → 56 linhas; os snapshots do dia anterior intactos.
11. API falha (503 nas 3 tentativas) só para `recife` → 21 linhas gravadas e o job levanta erro que menciona `recife`. (A checagem de linhas também acusaria; o erro deve citar o local.)
12. Execução seguinte no mesmo dia com `recife` funcionando → 28 linhas; as 21 anteriores inalteradas.
13. API devolve `temperature_2m_max = 80` para um dia → linhas gravadas e o job levanta `ChecagemFalhou`.
14. CLI: `main(["clima-previsao"])` com o job levantando `ChecagemFalhou` (via `monkeypatch`) devolve 1.

## 9. Riscos e perguntas em aberto

- Caso 13 grava o dado ruim antes de falhar (a checagem é "depois de gravar", como manda a regra). Como a previsão é snapshot e não se repete, guardar o dado e alertar é melhor que perder o dia. Confirmar com o usuário.
- P8 (horizonte 0 e semântica de `emitida_em`) muda `linhas_esperadas` e a faixa de `horizonte_dias`.

## 10. Decisões que exigem ADR

Nenhuma além do ADR "Contrato de dados v1".
