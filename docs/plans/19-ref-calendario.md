# 19 — Tabela `ref.calendario` e carga com a lib `holidays`

> Executa: agente. Depende de: 11, 15 (usa `ingestion/checks.py`). Branch sugerida: `feat/ref-calendario`.
> Pré-requisito: ADR "Contrato de dados v1" (PR 09).
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar `ref.calendario` (um dia por linha, com dia da semana e feriado nacional) e o subcomando `python -m ingestion calendario --inicio --fim` que a preenche de forma idempotente.
Migração e carga ficam juntas porque são pequenas (~200 linhas) e uma não tem uso sem a outra.

## 2. Fora do escopo

- Feriados estaduais e municipais, pontos facultativos (ex.: Carnaval), véspera de feriado: a cientista deriva o que precisar em `features`.
- Agendamento: a tabela é carregada uma vez com folga de anos; não entra no crontab.

## 3. Fase do roadmap

Fase 1 — "`ref.locais`, `ref.calendario`".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `pyproject.toml`, `uv.lock` | `holidays` |
| `migrations/versions/0005_ref_calendario.py` | Tabela; `downgrade` a remove |
| `ingestion/calendario.py` | `montar_calendario(inicio, fim) -> pd.DataFrame` (puro) |
| `ingestion/checks.py` | `SCHEMA_CALENDARIO` |
| `ingestion/jobs.py` | `carregar_calendario(engine, inicio, fim)` |
| `ingestion/cli.py` | Subcomando `calendario` |
| `tests/test_calendario.py` | Testes (test-writer) |

Modelo de dados (`docs/plataforma-ml.md`): `ref.calendario` — `data`, `dia_semana`, `feriado_nacional`, `nome_feriado`; chave `data`; escreve Plataforma (lib `holidays`); lê Todos.

Código existente: `ingestion/db.py` (`upsert`), `ingestion/checks.py` (`checar`, `ChecagemFalhou`), `ingestion/cli.py` (`SUBCOMANDOS`).

## 5. Passos

1. (test-writer) Escreva `tests/test_calendario.py` com os casos da seção 8 (os de banco com `@pytest.mark.db`). Confirme falha por `ModuleNotFoundError: ingestion.calendario`. Commit `test: add ref.calendario tests`.
2. (implementer) `uv add holidays`.
3. Migração `0005`: `ref.calendario (data date primary key, dia_semana smallint not null check (dia_semana between 1 and 7), feriado_nacional boolean not null, nome_feriado text, check (feriado_nacional = (nome_feriado is not null)))`. `dia_semana` segue ISO: 1 = segunda, 7 = domingo.
4. `ingestion/calendario.py`: `montar_calendario(inicio: date, fim: date) -> pd.DataFrame` com uma linha por dia (inclusive nas duas pontas), usando `holidays.country_holidays("BR", years=...)` só com feriados nacionais. `inicio > fim` → `ValueError`.
5. `SCHEMA_CALENDARIO` em `checks.py`: `data` única e não nula, `dia_semana` em 1..7, regra feriado ↔ nome.
6. `ingestion/jobs.py`: `carregar_calendario(engine, inicio, fim)`: monta, faz `upsert(..., "ref.calendario", chaves=["data"], ao_conflitar="atualizar", carimbar_ingerido_em=False)` (`ref` não tem `ingerido_em`), relê o intervalo e `checar(..., linhas_esperadas=(fim - inicio).days + 1)`.
7. CLI `calendario --inicio AAAA-MM-DD --fim AAAA-MM-DD` (ambos obrigatórios; data inválida → código 2).
8. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_calendario.py tests/test_migracoes.py` | Todos passam |
| `uv run python -m ingestion calendario --help` | Mostra `--inicio` e `--fim` |
| `uv run alembic heads` | `0005 (head)` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: feriado e dia da semana errados viram vazamento silencioso de erro em todos os modelos de carga.

## 8. Casos de teste

1. `montar_calendario(2026-01-01, 2026-12-31)` → 365 linhas, datas únicas e contínuas.
2. 2026-01-01 → `feriado_nacional = True`, `nome_feriado` não vazio, `dia_semana = 4` (quinta).
3. 2026-11-15 (Proclamação da República, domingo) → feriado, `dia_semana = 7`.
4. 2026-11-20 (Dia Nacional de Zumbi e da Consciência Negra, feriado nacional desde 2024) → feriado.
5. 2026-11-09 (segunda comum) → `feriado_nacional = False`, `nome_feriado` nulo, `dia_semana = 1`.
6. `inicio > fim` → `ValueError`.
7. Ano bissexto: `montar_calendario(2024-01-01, 2024-12-31)` → 366 linhas.
8. (`db`) `carregar_calendario` 2015-01-01 a 2030-12-31 → 5844 linhas; rodar de novo → continua 5844.
9. (`db`) Inserir `feriado_nacional = true` com `nome_feriado` nulo direto no banco → violação de `CHECK`.
10. CLI com `--inicio 2026-13-01` → código 2.

## 9. Riscos e perguntas em aberto

- Feriados móveis nacionais (Sexta-feira Santa) vêm da lib; Carnaval e Corpus Christi são ponto facultativo e não entram. Se a cientista quiser, é feature dela.
- Atualização da lib `holidays` pode mudar nomes de feriados; o `upsert` com `atualizar` reflete isso ao recarregar.

## 10. Decisões que exigem ADR

Coberto pelo ADR "Contrato de dados v1".
