# 28 — Bancos e usuários `mlflow` e `prefect` no Postgres

> Executa: agente. Depende de: 11. Branch sugerida: `feat/mlflow-prefect-databases`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar de forma idempotente os bancos `mlflow` e `prefect`, cada um com dono próprio, no mesmo Postgres do banco `ml`.
É pré-requisito para subir MLflow (PR 29) e Prefect (PR 30), que usam o Postgres como backend.

## 2. Fora do escopo

- Os serviços MLflow e Prefect (PRs 29 e 30).
- Migrações dentro desses bancos: cada ferramenta cria e migra o próprio schema.

## 3. Fase do roadmap

Fase 3 — "MLflow e Prefect no compose" (pré-requisito). O doc diz "atrás do Caddy"; pelo ADR de rede do PR 03 (rede só Tailscale, desvio do doc), o acesso é pela tailnet.

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `ingestion/admin.py` | `ensure_database(admin_url, name, password)` |
| `ingestion/cli.py` | Subcomando `create-databases` que lê `MLFLOW_DB_PASSWORD` e `PREFECT_DB_PASSWORD` e chama `ensure_database` para `mlflow` e `prefect` |
| `infra/.env.example` | `MLFLOW_DB_PASSWORD`, `PREFECT_DB_PASSWORD` (fictícias) |
| `tests/test_admin_databases.py` | Testes (test-writer) |

Do doc (`docs/plataforma-ml.md`, "Stack na VPS"): "PostgreSQL 16 — também é backend do MLflow e do Prefect — Um banco por serviço (`ml`, `mlflow`, `prefect`)".

Por que não migração Alembic: `CREATE DATABASE` não roda dentro de transação nem dentro do banco `ml`; e Alembic versiona o schema do `ml`, não o servidor.

## 5. Passos

1. (test-writer) Escreva `tests/test_admin_databases.py` (`@pytest.mark.db`), usando nomes únicos por execução (ex.: `mlflow_t<hex>`) para não colidir no servidor de teste, e apagando banco e papel no teardown. Casos na seção 8. Confirme falha por `ModuleNotFoundError: ingestion.admin`. Commit `test: add database bootstrap tests`.
2. (implementer) `ingestion/admin.py`, `ensure_database(admin_url: str, name: str, password: str) -> None`, com conexão `AUTOCOMMIT`:
   - Valida `name` com `^[a-z_][a-z0-9_]*$` (vai em SQL como identificador); inválido → `ValueError`.
   - Cria o papel `name` com `LOGIN PASSWORD` se não existir; se existir, `ALTER ROLE ... PASSWORD` (permite trocar a senha rodando de novo). Senha passada como literal com `quote_literal` do psycopg (`psycopg.sql.Literal`), nunca por f-string.
   - Cria o banco `name` com `OWNER name` se não existir.
   - `REVOKE CONNECT ON DATABASE name FROM PUBLIC`.
3. CLI `create-databases`: usa `DATABASE_URL_ADMIN`; senha ausente → mensagem citando a variável e código 1.
4. `infra/.env.example`: acrescente as duas variáveis.
5. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_admin_databases.py` | Todos passam |
| `uv run python -m ingestion create-databases --help` | Uso, código 0 |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: idempotência (rodar de novo na VPS sem quebrar) e isolamento entre bancos são verificáveis e fáceis de errar.

## 8. Casos de teste

1. Servidor sem o banco → depois de `ensure_database`, o banco existe e o dono é o papel de mesmo nome.
2. Rodar duas vezes → não falha.
3. Rodar de novo com senha nova → conectar com a senha nova funciona e com a antiga falha.
4. O papel criado conecta no próprio banco e consegue `CREATE TABLE` nele.
5. O papel criado **não** conecta no banco `ml` (de teste) nem no banco do outro serviço.
6. `name = "x; drop"` → `ValueError`, nada executado.
7. Senha com aspas simples (`a'b`) funciona.
8. CLI sem `PREFECT_DB_PASSWORD` → código 1 e stderr contém `PREFECT_DB_PASSWORD`.

## 9. Riscos e perguntas em aberto

- O caso 5 depende de `REVOKE CONNECT ... FROM PUBLIC` também no banco `ml`. Se o `ml` ainda permitir `CONNECT` para `PUBLIC`, o papel `mlflow` conectaria lá (sem ler nada, pelas permissões do PR 07). Se o teste falhar por isso, a correção é uma migração Alembic nova revogando `CONNECT` de `PUBLIC` no `ml` e concedendo aos quatro papéis; reporte antes de fazer, porque é outro escopo.

## 10. Decisões que exigem ADR

Nenhuma.
