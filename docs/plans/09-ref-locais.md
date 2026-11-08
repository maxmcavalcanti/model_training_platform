# 09 — Tabela `ref.locations` com as quatro capitais

> Executa: agente. Depende de: 07 (na `main`). Branch sugerida: `feat/ref-locations`.
> Pré-requisito: ADR 0005 (`docs/adr/0005-data-contract-v1.md`), já mergeado em `a22c0df`. Falta só o usuário confirmar o formato do slug (seção 9, P1) **antes do test-writer**, porque os testes fixam a regex.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.
> Revisão 2026-11-07: alinhado à `main` em `a22c0df` (migrações 0001 e 0002, `tests/conftest.py`, padrões de `tests/test_permissions.py` e `tests/test_upsert.py`, ADR 0005).

## 1. Objetivo

Criar por migração Alembic (`0003`) a tabela `ref.locations` e carregar nela as quatro capitais, uma por subsistema.
É de onde os jobs de clima tiram a lista de lugares; cidade nova entra por dado, não por código.

## 2. Fora do escopo

- `ref.calendar` (PR 19).
- Interface ou job para cadastrar cidade. Cidade nova entra por migração de dados (preferível, fica no git) ou por `INSERT` do admin.
- Coluna `timezone` (ou qualquer coluna além das cinco do modelo de dados). Ver seção 9, P2.
- Coluna `ingested_at`: a regra "toda linha em `raw` leva `ingested_at`" vale para `raw`; o modelo de dados de `ref.locations` não tem essa coluna.
- Chaves estrangeiras que apontam para `ref.locations` (PRs 13 e 25).
- `GRANT` explícito: as permissões vêm dos privilégios padrão da migração `0002`.
- Alterar `tests/test_migrations.py`, `tests/conftest.py`, `migrations/env.py`, `alembic.ini`, `ci.yml` ou `pyproject.toml`. Nenhuma dependência nova.
- Marcar o checkbox "`ref.locations`, `ref.calendar`" do roadmap em `docs/plataforma-ml.md` (só fecha com o PR 19).
- Corrigir a linha obsoleta "Migrações e Postgres de teste: ainda não existem" do `AGENTS.md` (outro PR).

## 3. Fase do roadmap

Fase 1 — "Banco e carga do ONS", item "`ref.locations`, `ref.calendar`" (`docs/plataforma-ml.md`, seção do roadmap).

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `tests/test_ref_locations.py` | Novo: testes da tabela, das restrições, das permissões e do `downgrade` (test-writer) |
| `migrations/versions/0003_ref_locations.py` | Novo: cria `ref.locations`, insere as 4 linhas; `downgrade` apaga a tabela (implementer) |

Nada mais muda. `tests/test_migrations.py` já compara a revisão com o `head` dinamicamente (`ScriptDirectory.from_config(config).get_current_head()`) e exige ids de 4 dígitos e um único head; continua passando sem edição com a `0003`.

### Contrato e modelo de dados

`docs/plataforma-ml.md`:

| Tabela | Colunas principais | Chave | Escreve | Lê |
| --- | --- | --- | --- | --- |
| `ref.locations` | `location_id`, `name`, `lat`, `lon`, `subsystem` | `location_id` | Plataforma | Todos |

"Locais de clima (proposta): uma capital por subsistema — São Paulo (SE/CO), Porto Alegre (S), Recife (NE), Belém (N). Fica numa tabela de referência, então dá para adicionar cidades sem mexer em código."

ADR 0005 (`docs/adr/0005-data-contract-v1.md`), P18:

> `location_id` é texto em slug minúsculo, sem acento e sem espaço, por exemplo `sao_paulo`, `porto_alegre`, `recife`, `belem`. É a chave de `ref.locations` e a chave estrangeira em `raw.weather_observed` e `raw.weather_forecast`, e aparece como `key` de modelos de chuva em `predictions.model_predictions`. Um valor fora do formato (por exemplo `São Paulo`) é recusado pela tabela.
>
> Em aberto: o formato exato do slug (conjunto de caracteres permitido e restrição no banco). O plano do PR 09 propõe `^[a-z_]+$` via `CHECK`; confirmar no PR 09.

`.claude/rules/migrations-e-dados.md`:

> - Mudança de schema só por migração Alembic, com `upgrade` e `downgrade`. Nunca `ALTER` manual.
> - Mudança em `raw` ou `ref` exige migração Alembic + ADR + aviso à ciência de dados.
> - Permissões por usuário do Postgres: `ingestor` escreve `raw` e `ref`; `scientist` escreve `features`; `scorer` escreve `predictions` e `monitoring`; `reader` só lê. Toda tabela nova declara quem escreve e quem lê.

Quem escreve e quem lê (resultado dos privilégios padrão de `migrations/versions/0002_roles.py`, válidos para tabelas criadas pelo admin que roda as migrações):

| Papel | `ref.locations` |
| --- | --- |
| admin (`DATABASE_URL_ADMIN`) | dono; cria, insere, apaga |
| `ingestor` | `SELECT`, `INSERT`, `UPDATE` (sem `DELETE`) |
| `scientist`, `scorer`, `reader` | só `SELECT` |

Trecho relevante de `0002_roles.py`:

```python
op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT ON TABLES TO {ALL_ROLES}")
...
op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schemas} GRANT INSERT, UPDATE ON TABLES TO {role}")
# (raw, ref) -> ingestor ; (predictions, monitoring) -> scorer
```

### Quem é dono da carga das 4 linhas

A migração. São dados de referência que fazem parte do contrato (são a chave estrangeira dos PRs 13 e 25), mudam raramente e precisam estar presentes em todo banco migrado (CI, testes, produção), sem depender de um job ter rodado. A idempotência vem do Alembic: a `0003` roda uma única vez por banco, numa transação junto com o `CREATE TABLE` (`migrations/env.py` usa `context.begin_transaction()`), e `upgrade head` repetido é no-op (já testado em `tests/test_migrations.py::test_upgrade_head_twice_is_a_no_op`). Por isso o `INSERT` é simples, sem `ON CONFLICT`: a tabela acabou de ser criada e não pode ter conflito. A regra de upsert do `AGENTS.md` vale para jobs de ingestão, não para esta migração.

### Padrões existentes a seguir

- Migrações existentes (`0001_schemas.py`, `0002_roles.py`) usam só `op.execute` com SQL e `from alembic import op`; seguir o mesmo estilo.
- O template `migrations/script.py.mako` não importa `op` nem `sa` e deixa o comentário `# Add "from alembic import op" (and "import sqlalchemy as sa" if needed) ...`. Na revisão gerada: adicionar `from alembic import op` logo após `from collections.abc import Sequence`, **não** importar `sqlalchemy` (não será usado; import não usado falha no ruff `F401`) e apagar o comentário do template, como em `0002_roles.py`.
- `alembic revision` sem `--autogenerate` não roda `env.py` (`revision_environment` está desligado em `alembic.ini`), então não precisa de banco. O nome do arquivo sai `0003_ref_locations.py` pelo template padrão `%(rev)s_%(slug)s`.

Fixtures de `tests/conftest.py` (não alterar):

- `migrated_database` (sessão): banco em `head`, **compartilhado e só leitura**. Usar só para `SELECT`.
- `fresh_database` (por teste): banco vazio, apagado no teardown. Todo teste que escreve (`INSERT`, `UPDATE`, `DELETE`, `downgrade`) usa este, migrando com:

```python
monkeypatch.setenv("DATABASE_URL_ADMIN", fresh_database)
command.upgrade(alembic_config(), "head")
```

  como no fixture `permissions_database` de `tests/test_permissions.py`.
- Para agir como papel: `SET ROLE <papel>` na mesma conexão (ver `_execute_as` e `_assert_denied` em `tests/test_permissions.py`). Erros chegam como exceções do SQLAlchemy (`ProgrammingError`, `IntegrityError`) com `error.orig.sqlstate`; o nome da restrição violada fica em `error.orig.diag.constraint_name`.
- SQLSTATEs: `42501` permissão negada, `23514` violação de `CHECK`, `23502` `NOT NULL`, `23505` chave duplicada.
- Marcar os testes de banco com `@pytest.mark.db` (ou `pytestmark = pytest.mark.db`, como em `tests/test_upsert.py`).

## 5. Passos

1. (usuário) Confirmar P1 (formato do slug) da seção 9. Se escolher outra regex, ajustar a seção 5, passo 4, e os casos 5 e 6 antes do test-writer.
2. (test-writer) Escreva `tests/test_ref_locations.py` com os casos da seção 8, seguindo os padrões da seção 4 (leituras em `migrated_database`; escritas e `downgrade` num fixture próprio sobre `fresh_database` + `upgrade head`). Rode `uv run pytest tests/test_ref_locations.py` e confirme que falham porque `ref.locations` não existe (`UndefinedTable`) ou porque a revisão `0003` não existe. Rode `uv run ruff check .` e `uv run ruff format --check .`. Commit `test: add ref.locations tests`.
3. (implementer) Partindo da branch com os testes: `uv run alembic revision -m "ref_locations" --rev-id 0003`. Confira que `down_revision = "0002"`. Ajuste os imports como na seção 4 (só `from alembic import op`; apague o comentário do template). Escreva no docstring do módulo uma linha dizendo que a migração cria e carrega a tabela e que as permissões vêm dos privilégios padrão da `0002`.
4. `upgrade`, primeiro `op.execute`, a tabela (nomes de restrição fixos, os testes conferem o nome):
   - `location_id text PRIMARY KEY`, com `CONSTRAINT locations_location_id_slug CHECK (location_id ~ '^[a-z][a-z0-9]*(_[a-z0-9]+)*$')`
   - `name text NOT NULL`
   - `lat double precision NOT NULL`, com `CONSTRAINT locations_lat_range CHECK (lat BETWEEN -90 AND 90)`
   - `lon double precision NOT NULL`, com `CONSTRAINT locations_lon_range CHECK (lon BETWEEN -180 AND 180)`
   - `subsystem text NOT NULL`, com `CONSTRAINT locations_subsystem_code CHECK (subsystem IN ('SE', 'S', 'NE', 'N'))` (códigos do ONS, iguais aos de `raw.ons_daily_load` no PR 21; `SE` é o subsistema Sudeste/Centro-Oeste)
   - Sem `UNIQUE` em `subsystem`: mais de uma cidade por subsistema é permitido ("cidade nova entra por dado").
5. `upgrade`, segundo `op.execute`, um `INSERT INTO ref.locations (location_id, name, lat, lon, subsystem) VALUES ...` com exatamente:

   | location_id | name | lat | lon | subsystem |
   | --- | --- | --- | --- | --- |
   | `sao_paulo` | São Paulo | -23.55 | -46.63 | SE |
   | `porto_alegre` | Porto Alegre | -30.03 | -51.23 | S |
   | `recife` | Recife | -8.05 | -34.88 | NE |
   | `belem` | Belém | -1.46 | -48.49 | N |

   `name` leva acento (é o nome de exibição); o arquivo é UTF-8. Os valores de São Paulo são os mesmos da fixture do PR 14 (`latitude=-23.55&longitude=-46.63`).
6. `downgrade`: `op.execute("DROP TABLE ref.locations")` (sem `CASCADE`: se um dia houver tabela dependente, a migração dela já terá sido revertida antes, pela ordem do Alembic). O schema `ref` continua (é da `0001`).
7. Não escrever `GRANT` (passo coberto pelos privilégios padrão da `0002`).
8. Rode os critérios de pronto e cole comando e saída no PR.
9. (usuário, depois que a `0003` estiver em produção, no item 12) Enviar à cientista o aviso da seção 9, "Aviso à ciência de dados".

## 6. Critérios de pronto

Precisa do Postgres de teste: `docker compose -f infra/docker-compose.dev.yml up -d` (mensagem de `tests/conftest.py`).

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_ref_locations.py tests/test_migrations.py tests/test_permissions.py` | Todos passam, nenhum `skipped` |
| `uv run alembic heads` | `0003 (head)` |
| `uv run alembic history` | `0002 -> 0003 (head), ref_locations` na primeira linha |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | Nenhum arquivo a reformatar |
| `git diff --name-only main...HEAD` | Só `tests/test_ref_locations.py` e `migrations/versions/0003_ref_locations.py` |
| `gh pr checks` | Verde (o CI roda `alembic upgrade head` e a suíte com Postgres 16) |

## 7. Testes necessários

`sim`: a tabela tem restrições (slug, faixas de coordenada, códigos de subsistema) e dados iniciais que os jobs de clima e as chaves estrangeiras dos PRs 13 e 25 assumem.

## 8. Casos de teste

Leitura, no banco compartilhado em `head`:

1. `SELECT location_id, name, lat, lon, subsystem FROM ref.locations ORDER BY location_id` devolve exatamente, nesta ordem: (`belem`, `Belém`, -1.46, -48.49, `N`), (`porto_alegre`, `Porto Alegre`, -30.03, -51.23, `S`), (`recife`, `Recife`, -8.05, -34.88, `NE`), (`sao_paulo`, `São Paulo`, -23.55, -46.63, `SE`).
2. Nos dados carregados, cada subsistema `SE`, `S`, `NE`, `N` aparece exatamente uma vez.
3. As colunas, pelo `information_schema.columns`, são exatamente `location_id text`, `name text`, `lat double precision`, `lon double precision`, `subsystem text`, todas `NOT NULL`; a chave primária é só `location_id`.

Escrita, cada teste num banco novo em `head`, como admin salvo indicação:

4. Inserir uma linha válida com `subsystem` = `CO`, `SE/CO` ou `se` falha com `23514` na restrição `locations_subsystem_code`.
5. Inserir uma linha válida com `location_id` = `São Paulo`, `belém`, `SAO_PAULO`, `sao paulo`, `sao-paulo`, `` (vazio), `_recife`, `recife_`, `sao__paulo` ou `1recife` falha com `23514` na restrição `locations_location_id_slug`.
6. Inserir `location_id` = `curitiba`, `rio_de_janeiro` ou `zona2` (com dados válidos) funciona.
7. Inserir `lat` = 91 ou -91 falha com `23514` em `locations_lat_range`; `lon` = 181 ou -181 falha em `locations_lon_range`; `lat` = 90 com `lon` = -180 (limites) funciona.
8. Inserir linha com `NULL` em `name`, `lat`, `lon` ou `subsystem` falha com `23502`.
9. Inserir de novo `location_id = 'recife'` falha com `23505`.
10. Como `ingestor`: inserir `('curitiba', 'Curitiba', -25.43, -49.27, 'S')` funciona (subsistema repetido é aceito) e a tabela passa a ter 5 linhas; `UPDATE` do `name` de `curitiba` funciona; `DELETE` de `curitiba` falha com `42501`.
11. Como `reader`, `scientist` e `scorer`: `SELECT count(*) FROM ref.locations` devolve 4; `INSERT` de uma 5ª cidade falha com `42501`.
12. `downgrade` até `0002`: antes, `ref.locations` existe; depois, `ref.locations` não existe e o schema `ref` continua; um novo `upgrade head` recria a tabela com as mesmas 4 linhas do caso 1.

Já existentes, que precisam continuar verdes sem edição: `tests/test_migrations.py` (ida e volta até `base`, `upgrade head` duas vezes, ids de 4 dígitos e head único) e `tests/test_permissions.py` (inclui `downgrade` até `0001` a partir do `head`).

## 9. Riscos e perguntas em aberto

- **P1 (decisão do usuário, antes do test-writer): regex do slug.** O ADR 0005 deixou para este PR. A versão anterior deste plano propunha `^[a-z_]+$`, que aceita `_`, `__`, `recife_` e `sao__paulo` e recusa dígitos. Proposta: `^[a-z][a-z0-9]*(_[a-z0-9]+)*$` (começa com letra, palavras de `a-z0-9` separadas por um único `_`). Aceita as quatro capitais e casos como `rio_de_janeiro`; recusa acento, maiúscula, espaço, hífen, `_` na ponta e `_` duplo. Se o usuário preferir `^[a-z_]+$`, tirar dos casos 5 e 6 os exemplos `_recife`, `recife_`, `sao__paulo` e `zona2` (este passa a ser recusado). A regex vira contrato: mudar depois exige migração, ADR e aviso.
- **P2 (decisão do usuário): fuso por local.** Os PRs 14 e 24 fixam `timezone=America/Sao_Paulo` para todas as cidades. As 4 capitais estão em UTC-3 sem horário de verão, então hoje não há erro. Uma cidade em outro fuso (Manaus, Cuiabá, Rio Branco) teria "o dia" do Open-Meteo deslocado. Recomendação: não adicionar coluna agora (fica fora do modelo de dados e do ADR 0005) e registrar a limitação no aviso à cientista; se for adicionar, é agora ou com migração + ADR + aviso depois.
- **Coordenadas.** Com 2 casas decimais (~1 km), o ponto cai no centro da cidade; bastam para a grade do Open-Meteo (~11 km na previsão, ~25 km no ERA5 do arquivo histórico). Recife -8.05/-34.88 e Belém -1.46/-48.49 são aproximações do centro; o usuário pode trocar por outro ponto de referência (por exemplo, a estação do INMET) antes do merge, ajustando passo 5 e caso 1.
- **Caso 1 em `head`.** Se uma migração futura de dados adicionar cidades, o caso 1 precisará ser atualizado nesse PR; isso é esperado (é mudança de contrato).
- **Comparação de `double precision`.** Os valores do passo 5 voltam do Postgres como os mesmos `float` do Python (literais idênticos, sem aritmética); comparar por igualdade é seguro.
- **Remover cidade.** `ingestor` não tem `DELETE` em `ref` (privilégios da `0002`). Remover uma cidade depois que houver dados em `raw.weather_*` também esbarra na chave estrangeira. Remoção é tarefa do admin, por migração.
- **Produção.** O item 12 (`docs/plans/12-subir-postgres-vps-manual.md`) já espera `select count(*) from ref.locations` = `4` como `scientist` e `permission denied` no `INSERT`; este plano é coerente com isso. As migrações precisam rodar com o mesmo admin para os privilégios padrão valerem (docstring da `0002`).
- **Postgres de teste.** O comando de subida citado em `tests/conftest.py` é `docker compose -f infra/docker-compose.dev.yml up -d`; o `AGENTS.md` ainda diz que o Postgres de teste não existe (linha obsoleta, fora do escopo).

### Aviso à ciência de dados

A regra exige aviso para mudança em `ref`. Quem envia é o usuário (passo 9), quando a `0003` estiver em produção. Conteúdo mínimo:

- Existe `ref.locations` (`location_id`, `name`, `lat`, `lon`, `subsystem`), chave `location_id`, com 4 linhas: `sao_paulo` (SE), `porto_alegre` (S), `recife` (NE), `belem` (N).
- `location_id` é slug minúsculo no formato `<regex confirmada em P1>`; é a chave usada em `raw.weather_forecast` e `raw.weather_observed` e a `key` dos modelos de chuva em `predictions.model_predictions` (ADR 0005).
- `subsystem` usa os códigos do ONS `SE`, `S`, `NE`, `N`; `SE` é Sudeste/Centro-Oeste. São os mesmos de `raw.ons_daily_load`.
- `lat`/`lon` (2 casas) são o ponto consultado no Open-Meteo, não uma área.
- Não assumir uma cidade por subsistema nem exatamente 4 cidades: cidades novas entram por dado e podem repetir subsistema. Ler a lista da tabela, nunca fixar no código do modelo.
- O papel `scientist` só lê a tabela; pedido de cidade nova vai para a plataforma.
- O "dia" dos dados de clima é o de `America/Sao_Paulo` (PRs 14 e 24), válido para as 4 capitais (todas UTC-3).

## 10. Decisões que exigem ADR

- Nenhum ADR novo. O ADR 0005 (mergeado) cobre `ref.locations` no formato de `location_id` e remete os demais tipos e colunas a este plano e a `docs/plataforma-ml.md`; ele mesmo diz que a regex se confirma "no PR 09", então a confirmação de P1 pelo usuário basta para destravar este PR.
- Opcional, decisão do usuário: uma emenda curta ao ADR 0005 (PR só de `docs/**`) registrando a regex escolhida e fechando o ponto em aberto. Não bloqueia este PR.
- Se P2 for decidido como "adicionar `timezone`", isso muda o modelo de dados de `ref` e exige ADR (novo ou emenda ao 0005) mergeado antes deste PR.
