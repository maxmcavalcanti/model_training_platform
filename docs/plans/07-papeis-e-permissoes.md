# 07 — Usuários do Postgres e permissões por schema

> Executa: agente. Depende de: 06 (na `main` em `6256fd9`). Branch sugerida: `feat/db-roles`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.
> Revisão 2026-11-07: alinhado ao que existe na `main` depois dos PRs 05 e 06 (fixtures, template do Alembic, CI, teste de migração que fixa `0001`).

## 1. Objetivo

Criar, por migração Alembic, os papéis `ingestor`, `scientist`, `scorer` e `reader` e as permissões por schema, incluindo privilégios padrão para tabelas que migrações futuras criarem.
Assim cada tabela nova já nasce com quem escreve e quem lê corretos, sem `GRANT` manual.

## 2. Fora do escopo

- Senhas dos papéis. São segredos: nunca entram em migração, teste, `.env.example` com valor real ou qualquer arquivo do git. A migração cria os papéis **sem senha** (não conseguem logar por senha até alguém definir uma). A senha é definida na VPS a partir do `infra/.env` (item 12, `docs/plans/12-subir-postgres-vps-manual.md`, `ALTER ROLE ... PASSWORD`). Automatizar isso a partir de variáveis de ambiente é decisão em aberto (seção 9), não deste PR.
- Usuários `mlflow` e `prefect` e seus bancos (PR 28).
- `REVOKE CONNECT ON DATABASE ml FROM PUBLIC` (risco citado no PR 28; outro escopo).
- Privilégios em sequências (`USAGE ON SEQUENCES`): as tabelas planejadas usam chave natural, sem `serial`/`identity`.
- Tabelas de verdade (PRs 09, 13, 21 etc.).
- Corrigir a linha obsoleta de `AGENTS.md` ("Migrações e Postgres de teste: ainda não existem (PRs 05 e 06).") — ver seção 9.

## 3. Fase do roadmap

Fase 1 — "Postgres, migrações com Alembic, usuários e permissões" (parte "usuários e permissões").

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `tests/test_permissions.py` | Novo: testes de permissão por papel (test-writer) |
| `tests/test_migrations.py` | Alterar `test_upgrade_head_twice_is_a_no_op`: hoje compara com `"0001"` fixo e quebraria com a `0002` (test-writer; o implementer não edita testes) |
| `migrations/versions/0002_roles.py` | Novo: cria papéis (se não existirem) e concede permissões; `downgrade` revoga |

Nenhuma dependência nova: `alembic`, `sqlalchemy` e `psycopg[binary]` já estão em `pyproject.toml`. Não há passo de `uv add`. `ci.yml`, `alembic.ini`, `migrations/env.py` e `tests/conftest.py` **não** mudam.

### Regra e modelo de dados

`.claude/rules/migrations-e-dados.md`:

> Mudança de schema só por migração Alembic, com `upgrade` e `downgrade`. Nunca `ALTER` manual.
> Permissões por usuário do Postgres: `ingestor` escreve `raw` e `ref`; `scientist` escreve `features`; `scorer` escreve `predictions` e `monitoring`; `reader` só lê. Toda tabela nova declara quem escreve e quem lê.

`docs/plataforma-ml.md`, "Modelo de dados": a coluna "Lê" é "Todos" em todas as tabelas; "**Usuários do Postgres:** `ingestor` (escreve `raw` e `ref`), `scientist` (lê tudo, escreve `features`), `scorer` (escreve `predictions` e `monitoring`), `reader` (Grafana)."

Nomes (ADR 0001, seções D e K): papéis `ingestor`, `scientist`, `scorer`, `reader`; arquivo `0002_roles.py`; teste `test_permissions`; tabela de teste `features.mine`.

Planos seguintes dependem disto: 09, 13, 21, 25, 41 e 51 dizem "Permissões vêm dos privilégios padrão (PR 07). Não repetir `GRANT`." e o 09 testa `downgrade` até `0002`.

### Código existente na `main` (`6256fd9`) que o plano usa

`tests/conftest.py` (não alterar):

- `alembic_config() -> Config`: função (não fixture) com caminhos absolutos; importável como `from tests.conftest import alembic_config` (padrão já usado em `tests/test_migrations.py`).
- Fixture `fresh_database` (escopo função): banco vazio `ml_test_<8 hex>`, devolve a URL como string, apagado no teardown com `DROP DATABASE ... WITH (FORCE)`.
- Fixture `migrated_database` (escopo sessão): banco já em `head`, **compartilhado pela sessão e de uso só leitura** (docstring: "Read-only use"). Não criar tabelas nele.
- A URL admin vem de `DATABASE_URL_TEST` (padrão `postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres`); o usuário `postgres` é superusuário no compose de dev (`infra/docker-compose.dev.yml`, imagem `postgres:16.15`) e no CI (`postgres:16`).

`tests/test_migrations.py`, teste que precisa mudar:

```python
@pytest.mark.db
def test_upgrade_head_twice_is_a_no_op(fresh_database, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
    config = alembic_config()

    command.upgrade(config, "head")
    command.upgrade(config, "head")

    assert _current_revision(fresh_database) == "0001"
    assert _existing_schemas(fresh_database) == EXPECTED_SCHEMAS
```

O round trip (`test_upgrade_downgrade_upgrade_round_trip`) já cobre a `0002` sem mudança: sobe até `head`, desce até `base` (a `0001` faz `DROP SCHEMA IF EXISTS <s>` sem `CASCADE`) e sobe de novo.

`migrations/script.py.mako`: o template **não** importa `op` nem `sa`; ele gera este comentário no arquivo da revisão:

```python
# Add "from alembic import op" (and "import sqlalchemy as sa" if needed) when the
# revision uses them; unused imports fail ruff.
```

`migrations/versions/0001_schemas.py` (modelo de estilo): `from collections.abc import Sequence`, `from alembic import op`, constante `SCHEMAS = ("raw", "ref", "features", "predictions", "monitoring")`, `op.execute(...)` em `upgrade`/`downgrade`.

`migrations/env.py`: usa `DATABASE_URL_ADMIN` ou `DATABASE_URL`, roda tudo numa transação (`context.begin_transaction()`). `CREATE ROLE`, `GRANT` e `ALTER DEFAULT PRIVILEGES` podem rodar em transação.

`.github/workflows/ci.yml`: passo `uv run alembic upgrade head` com `DATABASE_URL_ADMIN=postgresql+psycopg://postgres:postgres@localhost:5432/ml_ci`, **antes** do `uv run pytest`. Consequência: no CI os quatro papéis já existem no servidor quando os testes rodam. Nenhum segredo novo é necessário no CI (papéis sem senha; a senha `postgres` é do banco efêmero).

Lint: ruff com `select = ["E", "F", "I", "B", "UP"]`, `line-length = 100`; `migrations/` é lintado e formatado (só `docs` é excluído).

## 5. Passos

1. (test-writer) Em `tests/test_migrations.py`, troque a asserção `== "0001"` de `test_upgrade_head_twice_is_a_no_op` pela cabeça do script: `ScriptDirectory.from_config(alembic_config()).get_current_head()` (`ScriptDirectory` já é importado no arquivo). Isso continua verde na `main` atual (cabeça `0001`) e não quebra em migrações futuras.
2. (test-writer) Crie `tests/test_permissions.py`, todos os testes com `@pytest.mark.db`, seguindo estas regras de arranjo:
   - Fixture local de escopo função (nome sugerido `permissions_database`) baseada em `fresh_database` + `monkeypatch.setenv("DATABASE_URL_ADMIN", url)` + `command.upgrade(alembic_config(), "head")`. Depois do `upgrade`, ainda como admin (a URL da fixture), crie `x (id int primary key)` em `raw`, `ref`, `predictions` e `monitoring` — simula uma migração futura feita pelo mesmo admin. Não use `migrated_database` para isso (é só leitura).
   - Para agir como um papel: abrir uma conexão com `ingestion.db.build_engine(url)`, executar `SET ROLE <papel>` **fora** do bloco `pytest.raises`, executar o comando, `commit`. Uma conexão por ação, para que um erro não deixe transação abortada para a próxima.
   - Falha esperada = `sqlalchemy.exc.ProgrammingError` cujo `.orig.sqlstate == "42501"` (`insufficient_privilege`). Não aceitar qualquer exceção: "papel não existe" (`42704`) não pode contar como "permissão negada".
   - Não use `DROP ROLE` em teste nenhum: papéis são globais ao servidor e compartilhados com outros bancos (inclusive `ml_ci` no CI).
   - Nenhuma senha literal no arquivo. O caso 10 gera a senha em tempo de execução (`secrets.token_hex`) e a passa ao SQL com `psycopg.sql.Literal` (nunca por f-string).
   - Casos na seção 8, um teste por caso no mínimo.
3. (test-writer) Rode `uv run pytest tests/test_permissions.py tests/test_migrations.py` com o compose de dev de pé. Esperado: `test_migrations.py` todo verde; os testes de `test_permissions.py` falham por papel inexistente (`SET ROLE` com `role "ingestor" does not exist`) ou, se o servidor local já tiver os papéis de uma execução anterior, por `permission denied`/asserção. Nenhuma falha por import, sintaxe ou fixture. Commit `test: add role permission tests`.
4. (implementer, a partir da branch com os testes) `uv run alembic revision -m "roles" --rev-id 0002`. Gera `migrations/versions/0002_roles.py` com `down_revision = "0001"`. Troque o comentário do template por `from alembic import op` (o `sa` não é necessário).
5. `upgrade`, como `op.execute(...)`, nesta ordem (constantes no topo, como em `0001`):
   - Para cada papel, crie com `LOGIN` só se não existir, sem senha e sem tocar num papel já existente (não pode apagar a senha definida na VPS):
     `DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ingestor') THEN CREATE ROLE ingestor LOGIN; END IF; END $$;`
   - `GRANT USAGE ON SCHEMA raw, ref, features, predictions, monitoring TO ingestor, scientist, scorer, reader;`
   - Leitura geral, para cada schema `<s>`: `GRANT SELECT ON ALL TABLES IN SCHEMA <s> TO ingestor, scientist, scorer, reader;` e `ALTER DEFAULT PRIVILEGES IN SCHEMA <s> GRANT SELECT ON TABLES TO ingestor, scientist, scorer, reader;`
   - Escrita do `ingestor`: `GRANT INSERT, UPDATE ON ALL TABLES IN SCHEMA raw, ref TO ingestor;` e `ALTER DEFAULT PRIVILEGES IN SCHEMA raw, ref GRANT INSERT, UPDATE ON TABLES TO ingestor;`
   - Escrita do `scorer`: o mesmo par para `predictions, monitoring`.
   - `features`: `GRANT CREATE ON SCHEMA features TO scientist;` e `ALTER DEFAULT PRIVILEGES FOR ROLE scientist IN SCHEMA features GRANT SELECT ON TABLES TO ingestor, scorer, reader;` (tabelas que ela criar ficam legíveis por todos).
   - Sem `DELETE`, `TRUNCATE` nem `CREATE` em `raw`, `ref`, `predictions` e `monitoring` para ninguém: os jobs fazem upsert, nunca apagam; tabelas nascem só por migração.
   - `ALTER DEFAULT PRIVILEGES` sem `FOR ROLE` vale para objetos criados pelo papel que roda a migração (o admin). Não acrescente `FOR ROLE <admin>` com nome fixo.
6. `downgrade`: revogue tudo o que o `upgrade` concedeu neste banco, na ordem inversa, inclusive os privilégios padrão (`ALTER DEFAULT PRIVILEGES [FOR ROLE scientist] IN SCHEMA ... REVOKE ... FROM ...`), de modo que `pg_default_acl` do banco fique vazio. **Não** apague os papéis: são do servidor e podem ter privilégios em outros bancos; `DROP ROLE` falharia. Documente isso num comentário (em inglês) no topo do arquivo.
7. `uv run ruff format .` e rode os critérios de pronto.

## 6. Critérios de pronto

Com o compose de dev de pé (`docker compose -f infra/docker-compose.dev.yml up -d`). Comandos com variável em Bash; no PowerShell, `$env:DATABASE_URL_ADMIN="postgresql+psycopg://postgres:postgres@127.0.0.1:5432/ml"` antes.

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_permissions.py` | Todos passam |
| `uv run pytest tests/test_migrations.py` | Todos passam (o round trip agora passa pela `0002`) |
| `uv run alembic heads` | `0002 (head)` |
| `docker compose -f infra/docker-compose.dev.yml exec postgres createdb -U postgres ml` (ignorar erro "already exists") e `DATABASE_URL_ADMIN=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/ml uv run alembic upgrade head` | Log com `Running upgrade 0001 -> 0002, roles` (ou nada a fazer, se já estiver em `0002`) |
| `DATABASE_URL_ADMIN=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/ml uv run alembic current` | `0002 (head)` |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem erro (inclui `migrations/versions/0002_roles.py`) |
| `git grep -nE "PASSWORD '[A-Za-z0-9]" -- migrations tests` | Sem saída (nenhuma senha literal em SQL) |
| `gh pr checks` | Verde; o log do passo `uv run alembic upgrade head` mostra `0001 -> 0002, roles` |

## 7. Testes necessários

`sim`: permissão errada só aparece em produção (um job falhando ou alguém escrevendo onde não devia); o teste com `SET ROLE` pega isso antes.

## 8. Casos de teste

Nos casos 1 a 7, o banco foi migrado até `head` e a tabela `x` foi criada pelo admin **depois** da migração (cobre os privilégios padrão). "Falha" = erro de permissão negada (SQLSTATE `42501`).

1. `ingestor`: `INSERT` e `UPDATE` em `raw.x` e `ref.x` funcionam, inclusive um upsert `INSERT ... ON CONFLICT (id) DO UPDATE`; `INSERT` em `predictions.x` falha.
2. `ingestor`: `DELETE FROM raw.x` falha.
3. `scorer`: `INSERT` em `predictions.x` e `monitoring.x` funciona; `INSERT` em `raw.x` falha.
4. `reader`: `SELECT` em `raw.x`, `ref.x`, `predictions.x` e `monitoring.x` funciona; `INSERT` em qualquer uma delas falha.
5. `scientist`: `CREATE TABLE features.mine (id int)` funciona; depois disso, `reader` e `scorer` conseguem `SELECT` em `features.mine`.
6. `scientist`: `CREATE TABLE raw.y (id int)` falha; `INSERT` em `raw.x` falha; `SELECT` em `raw.x` funciona.
7. Nenhum dos quatro papéis consegue `CREATE TABLE` em `raw`, `ref`, `predictions` ou `monitoring`.
8. Papéis já existentes no servidor (garanta com a fixture `migrated_database`, que já rodou `upgrade head` noutro banco): `upgrade head` num `fresh_database` não falha e a revisão atual é a cabeça.
9. Depois de `upgrade head`, os quatro papéis existem com `rolcanlogin = true`, `rolsuper = false`, `rolcreatedb = false` e `rolcreaterole = false` (`pg_roles`).
10. Papel com senha já definida não perde a senha: defina uma senha gerada em tempo de execução para `ingestor` (`ALTER ROLE`), rode `upgrade head` num `fresh_database` e confirme que `pg_authid.rolpassword` de `ingestor` continua não nulo. Teardown: `ALTER ROLE ingestor PASSWORD NULL`.
11. `downgrade` até `0001` num banco em `head`: os quatro papéis continuam existindo; `has_schema_privilege(<papel>, <schema>, 'USAGE')` é falso para os quatro papéis e os cinco schemas; `pg_default_acl` do banco está vazio.

## 9. Riscos e perguntas em aberto

- `ALTER DEFAULT PRIVILEGES` vale para objetos criados pelo papel que rodou a migração. As migrações devem rodar sempre com o mesmo admin (`DATABASE_URL_ADMIN`); se isso mudar, as tabelas novas nascem sem permissão. Registrar isso no `AGENTS.md` não cabe aqui (é regra de operação); fica como risco.
- `ALTER DEFAULT PRIVILEGES FOR ROLE scientist` exige que o admin seja superusuário ou membro de `scientist`. No CI e no dev é `postgres` (superusuário); na VPS, o `POSTGRES_USER` da imagem (`platform_admin`, plano 10), também superusuário.
- Papéis globais ao servidor: os testes não podem rodar em paralelo no mesmo servidor (plano 05). O caso 10 altera estado global e precisa restaurar no teardown; se o teste for interrompido, o `ingestor` do servidor local fica com uma senha aleatória (inofensivo, mas convém saber).
- Vermelho "falso verde": num servidor local onde os papéis já existam, os casos 8 e 9 podem passar antes da implementação. Os demais falham por falta de `GRANT` no banco novo, o que basta como vermelho.
- `DROP SCHEMA` da `0001` (sem `CASCADE`) depois do `downgrade` da `0002`: se algum privilégio padrão sobrar, o round trip pode não acusar (as entradas por schema caem junto com o schema); por isso o caso 11 checa `pg_default_acl` explicitamente.
- O `scorer` também precisará ler o MLflow e escrever no Prefect, mas isso é outro banco (Fase 3).
- **Pergunta ao usuário (senhas a partir do ambiente):** o desenho atual é "migração cria sem senha; senha entra à mão na VPS com `ALTER ROLE` usando o valor do `infra/.env`" (item 12). Quer automatizar (por exemplo, um subcomando como o `create-databases` do PR 28 lendo `POSTGRES_INGESTOR_PASSWORD`, `POSTGRES_SCORER_PASSWORD`, `POSTGRES_READER_PASSWORD`)? Se sim, é outro PR; a recomendação é nunca ler senha dentro da migração, porque o CI e os testes rodariam a migração sem esses segredos.
- **Pergunta ao usuário (variável da cientista):** o item 12 gera senha para `scientist`, mas o ADR 0001 (seção I) não lista `POSTGRES_SCIENTIST_PASSWORD`. A senha dela fica só no gerenciador de senhas (ela não roda nada na VPS) ou também no `infra/.env`?
- **Pergunta ao usuário (aviso):** a cientista recebe o papel `scientist` com escrita só em `features`. Avisar agora, por cortesia, ou só no item 12?
- `AGENTS.md`, seção "Comandos", ainda diz "Migrações e Postgres de teste: ainda não existem (PRs 05 e 06)", embora existam. Fora deste PR (tarefa própria, que passa por `code-reviewer` e `pr-reviewer` por tocar `AGENTS.md`).

## 10. Decisões que exigem ADR

Nenhuma obrigatória pelas regras do `AGENTS.md` ("Fronteira"):

- Não muda a forma de `raw` nem de `ref` (nenhuma tabela ou coluna), não muda a assinatura do contrato e não publica porta.
- Os quatro papéis e a divisão de escrita/leitura já estão decididos em `docs/plataforma-ml.md` ("Modelo de dados") e nos nomes do ADR 0001.
- Nenhum segredo entra no git: papéis sem senha; senha só no `infra/.env` da VPS (ADR 0003 e `.claude/rules/infra.md`: "`.env` da VPS fica fora do git, permissão 600").

Decisões tomadas aqui que vão além do doc e que o usuário pode querer registrar num ADR (não bloqueia, se ele disser que não): "ninguém tem `DELETE`", "permissões de tabelas futuras só por privilégio padrão do admin que roda a migração" e "senhas dos papéis fora da migração".
