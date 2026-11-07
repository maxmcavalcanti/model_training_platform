# 19 — Tabela `ref.calendar` e carga com a lib `holidays`

> Executa: agente. Depende de: 11, 15 (usa `ingestion/checks.py`). Branch sugerida: `feat/ref-calendar`.
> Pré-requisito: ADR "Contrato de dados v1" (PR 09).
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar `ref.calendar` (um dia por linha, com dia da semana e feriado nacional) e o subcomando `python -m ingestion calendario --start --end` que a preenche de forma idempotente.
Migração e carga ficam juntas porque são pequenas (~200 linhas) e uma não tem uso sem a outra.

## 2. Fora do escopo

- Feriados estaduais e municipais, pontos facultativos (ex.: Carnaval), véspera de feriado: a cientista deriva o que precisar em `features`.
- Agendamento: a tabela é carregada uma vez com folga de anos; não entra no crontab.

## 3. Fase do roadmap

Fase 1 — "`ref.locations`, `ref.calendar`".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `pyproject.toml`, `uv.lock` | `holidays` |
| `migrations/versions/0005_ref_calendar.py` | Tabela; `downgrade` a remove |
| `ingestion/calendar_ref.py` | `build_calendar(inicio, fim) -> pd.DataFrame` (puro) |
| `ingestion/checks.py` | `SCHEMA_CALENDAR` |
| `ingestion/jobs.py` | `load_calendar(engine, inicio, fim)` |
| `ingestion/cli.py` | Subcomando `calendario` |
| `tests/test_calendar.py` | Testes (test-writer) |

Modelo de dados (`docs/plataforma-ml.md`): `ref.calendar` — `data`, `weekday`, `is_national_holiday`, `holiday_name`; chave `data`; escreve Plataforma (lib `holidays`); lê Todos.

Código existente: `ingestion/db.py` (`upsert`), `ingestion/checks.py` (`checar`, `CheckFailed`), `ingestion/cli.py` (`SUBCOMMANDS`).

## 5. Passos

1. (test-writer) Escreva `tests/test_calendar.py` com os casos da seção 8 (os de banco com `@pytest.mark.db`). Confirme falha por `ModuleNotFoundError: ingestion.calendario`. Commit `test: add ref.calendar tests`.
2. (implementer) `uv add holidays`.
3. Migração `0005`: `ref.calendar (data date primary key, weekday smallint not null check (weekday between 1 and 7), is_national_holiday boolean not null, holiday_name text, check (is_national_holiday = (holiday_name is not null)))`. `weekday` segue ISO: 1 = segunda, 7 = domingo.
4. `ingestion/calendar_ref.py`: `build_calendar(inicio: date, fim: date) -> pd.DataFrame` com uma linha por dia (inclusive nas duas pontas), usando `holidays.country_holidays("BR", years=...)` só com feriados nacionais. `inicio > fim` → `ValueError`.
5. `SCHEMA_CALENDAR` em `checks.py`: `data` única e não nula, `weekday` em 1..7, regra feriado ↔ nome.
6. `ingestion/jobs.py`: `load_calendar(engine, inicio, fim)`: monta, faz `upsert(..., "ref.calendar", chaves=["data"], on_conflict="atualizar", stamp_ingested_at=False)` (`ref` não tem `ingested_at`), relê o intervalo e `checar(..., expected_rows=(fim - inicio).days + 1)`.
7. CLI `calendario --start AAAA-MM-DD --end AAAA-MM-DD` (ambos obrigatórios; data inválida → código 2).
8. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_calendar.py tests/test_migrations.py` | Todos passam |
| `uv run python -m ingestion calendario --help` | Mostra `--start` e `--end` |
| `uv run alembic heads` | `0005 (head)` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: feriado e dia da semana errados viram vazamento silencioso de erro em todos os modelos de carga.

## 8. Casos de teste

1. `build_calendar(2026-01-01, 2026-12-31)` → 365 linhas, datas únicas e contínuas.
2. 2026-01-01 → `is_national_holiday = True`, `holiday_name` não vazio, `weekday = 4` (quinta).
3. 2026-11-15 (Proclamação da República, domingo) → feriado, `weekday = 7`.
4. 2026-11-20 (Dia Nacional de Zumbi e da Consciência Negra, feriado nacional desde 2024) → feriado.
5. 2026-11-09 (segunda comum) → `is_national_holiday = False`, `holiday_name` nulo, `weekday = 1`.
6. `inicio > fim` → `ValueError`.
7. Ano bissexto: `build_calendar(2024-01-01, 2024-12-31)` → 366 linhas.
8. (`db`) `load_calendar` 2015-01-01 a 2030-12-31 → 5844 linhas; rodar de novo → continua 5844.
9. (`db`) Inserir `is_national_holiday = true` com `holiday_name` nulo direto no banco → violação de `CHECK`.
10. CLI com `--start 2026-13-01` → código 2.

## 9. Riscos e perguntas em aberto

- Feriados móveis nacionais (Sexta-feira Santa) vêm da lib; Carnaval e Corpus Christi são ponto facultativo e não entram. Se a cientista quiser, é feature dela.
- Atualização da lib `holidays` pode mudar nomes de feriados; o `upsert` com `atualizar` reflete isso ao recarregar.

## 10. Decisões que exigem ADR

Coberto pelo ADR "Contrato de dados v1".
