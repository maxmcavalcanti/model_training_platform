# 07 — Usuários do Postgres e permissões por schema

> Executa: agente. Depende de: 06. Branch sugerida: `feat/db-papeis`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar, por migração Alembic, os papéis `ingestor`, `cientista`, `scorer` e `leitura` e as permissões por schema, incluindo privilégios padrão para tabelas que migrações futuras criarem.
Assim cada tabela nova já nasce com quem escreve e quem lê corretos, sem `GRANT` manual.

## 2. Fora do escopo

- Senhas dos papéis: são segredos e entram à mão na VPS (item 12), nunca em migração.
- Usuários `mlflow` e `prefect` e seus bancos (PR 28).
- Tabelas.

## 3. Fase do roadmap

Fase 1 — "Postgres, migrações com Alembic, usuários e permissões" (parte "usuários e permissões").

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `migrations/versions/0002_papeis.py` | Cria papéis (se não existirem) e concede permissões |
| `tests/test_permissoes.py` | Testes de permissão por papel (test-writer) |

Regra e modelo de dados (de `.claude/rules/migrations-e-dados.md` e `docs/plataforma-ml.md`):

> Permissões por usuário do Postgres: `ingestor` escreve `raw` e `ref`; `cientista` escreve `features`; `scorer` escreve `predictions` e `monitoring`; `leitura` só lê. Toda tabela nova declara quem escreve e quem lê.

Na tabela do modelo de dados, a coluna "Lê" é "Todos" para todas as tabelas.

## 5. Passos

1. (test-writer) Escreva `tests/test_permissoes.py` (`@pytest.mark.db`) usando um banco novo migrado até `head`. No arranjo de cada teste, como usuário admin, crie uma tabela de teste `x (id int primary key)` em cada schema (`raw`, `ref`, `predictions`, `monitoring`) — isso simula uma migração futura. Use `SET ROLE <papel>` para agir como cada papel e `RESET ROLE` depois. Casos na seção 8. Confirme falha porque os papéis não existem. Commit `test: add role permission tests`.
2. (implementer) `uv run alembic revision -m "papeis" --rev-id 0002`.
3. `upgrade`:
   - Para cada papel, crie com `LOGIN` se não existir (papéis são globais ao servidor):
     `DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ingestor') THEN CREATE ROLE ingestor LOGIN; END IF; END $$;`
   - `GRANT USAGE ON SCHEMA raw, ref, features, predictions, monitoring TO ingestor, cientista, scorer, leitura;`
   - Leitura geral: para cada schema, `GRANT SELECT ON ALL TABLES IN SCHEMA <s> TO ingestor, cientista, scorer, leitura;` e `ALTER DEFAULT PRIVILEGES IN SCHEMA <s> GRANT SELECT ON TABLES TO ingestor, cientista, scorer, leitura;`
   - Escrita: `ALTER DEFAULT PRIVILEGES IN SCHEMA raw, ref GRANT INSERT, UPDATE ON TABLES TO ingestor;` (mais o `GRANT` equivalente em `ALL TABLES` já existentes). Idem `predictions, monitoring` para `scorer`.
   - `features`: `GRANT CREATE ON SCHEMA features TO cientista;` e `ALTER DEFAULT PRIVILEGES FOR ROLE cientista IN SCHEMA features GRANT SELECT ON TABLES TO ingestor, scorer, leitura;` (tabelas que ela criar ficam legíveis por todos).
   - Sem `DELETE` para ninguém: os jobs fazem upsert, nunca apagam.
4. `downgrade`: revogue tudo o que o `upgrade` concedeu neste banco (inclusive os privilégios padrão, com `ALTER DEFAULT PRIVILEGES ... REVOKE`). **Não** apague os papéis: eles são do servidor e podem ter privilégios em outros bancos; `DROP ROLE` falharia. Documente isso num comentário no topo do arquivo.
5. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_permissoes.py` | Todos passam |
| `uv run pytest tests/test_migracoes.py` | Passa (a ida e volta agora inclui 0002) |
| `uv run alembic heads` | `0002 (head)` |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem erro |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: permissão errada só aparece em produção (um job falhando ou alguém escrevendo onde não devia); o teste com `SET ROLE` pega isso antes.

## 8. Casos de teste

Em todos, a tabela `x` foi criada pelo admin **depois** da migração (cobre os privilégios padrão).

1. `ingestor`: `INSERT` e `UPDATE` em `raw.x` e `ref.x` funcionam; `INSERT` em `predictions.x` falha com `permission denied`.
2. `ingestor`: `DELETE FROM raw.x` falha com `permission denied`.
3. `scorer`: `INSERT` em `predictions.x` e `monitoring.x` funciona; `INSERT` em `raw.x` falha.
4. `leitura`: `SELECT` em `raw.x`, `ref.x`, `predictions.x`, `monitoring.x` funciona; qualquer `INSERT` falha.
5. `cientista`: `CREATE TABLE features.minha (id int)` funciona; depois disso, `leitura` e `scorer` conseguem `SELECT` em `features.minha`.
6. `cientista`: `CREATE TABLE raw.y (id int)` falha; `INSERT` em `raw.x` falha.
7. Nenhum dos quatro papéis consegue `CREATE TABLE` em `raw`, `ref`, `predictions` ou `monitoring`.
8. Rodar `upgrade head` num segundo banco do mesmo servidor (papéis já existem) não falha.

## 9. Riscos e perguntas em aberto

- `ALTER DEFAULT PRIVILEGES` vale para objetos criados pelo papel que rodou a migração. As migrações devem rodar sempre com o mesmo usuário admin (`DATABASE_URL_ADMIN`); se isso mudar, as tabelas novas nascem sem permissão. Registrar isso no AGENTS.md não cabe aqui (é regra de operação); fica como risco.
- `ALTER DEFAULT PRIVILEGES FOR ROLE cientista` exige que o admin seja superusuário ou membro de `cientista`. Na VPS, o admin é o `POSTGRES_USER` da imagem (superusuário).
- O `scorer` também precisará ler o MLflow e escrever no Prefect, mas isso é outro banco (Fase 3).

## 10. Decisões que exigem ADR

Nenhuma: os papéis e a divisão estão no modelo de dados de `docs/plataforma-ml.md`.
