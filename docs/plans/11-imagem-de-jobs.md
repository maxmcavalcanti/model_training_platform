# 11 — Imagem Docker dos jobs e CLI `python -m ingestion`

> Executa: agente. Depende de: 06, 10 (ambos na `main`, commit `5ef914c`). Branch sugerida: `feat/jobs-image`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.
> Revisão 2026-11-07: alinhado à `main` em `5ef914c` e aos ADRs 0001 a 0005 (P7 resolvida pelo ADR 0004).

## 1. Objetivo

Empacotar o código do repo numa imagem Docker (serviço `jobs`, imagem `platform-jobs`) e criar o ponto de entrada `python -m ingestion <subcomando>`, ainda sem subcomandos de ingestão.
Com isso a VPS roda as migrações (`alembic upgrade head` dentro do `jobs`) e, nos PRs seguintes, cada job, com o mesmo código do CI.

## 2. Fora do escopo

- Subcomandos de ingestão e de banco (`weather-forecast` no PR 15, `calendar` no 19, `ons-load` no 22, `weather-observed` no 26, `create-databases` no 28).
- Subcomando `migrate`: **não** é criado. A migração é `alembic upgrade head` rodado dentro da imagem, como já usam os planos 12, 17, 23, 27 e 39.
- Agendador, supercronic e `infra/cron/` (PR 16). O serviço `scheduler` não existe neste PR.
- Publicar a imagem no GHCR e `image:` no compose (PR 37; até lá a VPS constrói localmente, ADR 0004).
- hadolint ou qualquer linter novo de Dockerfile (ver pergunta em aberto 4).
- Alinhar o texto de `.claude/rules/infra.md` ao ADR 0004 (ver pergunta em aberto 1: o implementador não edita `.claude/`).
- Corrigir a linha desatualizada "Migrações e Postgres de teste: ainda não existem" do `AGENTS.md` (ver pergunta em aberto 5).

## 3. Fase do roadmap

Fase 1 (`docs/plataforma-ml.md`, roadmap) — infraestrutura necessária para "Ingestão do ONS", para a coleta antecipada da previsão (PRs 13 a 17) e para as migrações na VPS (item 12).

## 4. Arquivos a criar ou alterar

| Caminho | Quem | Motivo |
| --- | --- | --- |
| `tests/test_cli.py` | test-writer | Casos 1 a 8 da seção 8 |
| `tests/infra/test_jobs_image.py` | test-writer | Casos 14 a 19 da seção 8 (política estática do Dockerfile e do `.dockerignore`) |
| `tests/infra/test_compose.py` | test-writer | Casos 9 a 13 da seção 8 (serviço `jobs`); não mexer na regra geral de `restart`, que já isenta `profiles` |
| `ingestion/cli.py` | implementer | `Subcommand`, `SUBCOMMANDS`, `main(argv) -> int` |
| `ingestion/__main__.py` | implementer | `raise SystemExit(main())` |
| `infra/jobs/Dockerfile` | implementer | Imagem com o pacote instalado, sem dependências de dev, usuário não-root |
| `.dockerignore` (raiz) | implementer | Contexto de build sem `.env`, `.git`, `.venv`, caches, `docs/`, `tests/`, `.claude/` |
| `infra/docker-compose.yml` | implementer | Serviço `jobs` no profile `jobs` |
| `infra/.env.example` | implementer (anexar pelo Bash, passo 6) | `POSTGRES_INGESTOR_PASSWORD` com valor fictício |
| `.github/workflows/ci.yml` | implementer | Build da imagem e smoke no job `compose-smoke` |
| `AGENTS.md` | implementer | Seção "Comandos": CLI e imagem |

Nenhuma dependência nova: a CLI usa `argparse` (stdlib) e os testes usam `pytest` e `pyyaml`, já no grupo `dev`. **Não há passo 0.** Não use click nem typer.

### Contexto que o implementador precisa (estado da `main` em `5ef914c`)

#### Regras e decisões

- `AGENTS.md`: segredos só por variável de ambiente; nenhum segredo no git (repo público, índice P2); agentes nunca leem arquivos `.env` com nenhuma ferramenta, e o deny de `Read` cobre também `infra/.env.example`. Identificadores, mensagens de log, erro, commit e PR em inglês (ADR 0001).
- ADR 0001, seção G: `SUBCOMMANDS`, `Subcommand`, `run(args)`; teste com `main(["does-not-exist"])`. Seção J: imagem `platform-jobs`; `infra/jobs/` sem mudança.
- ADR 0002: Python 3.12 (`.python-version` = `3.12`, `requires-python = ">=3.12,<3.13"`); imagem "baseada em `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` (tag a conferir), `uv sync --locked --no-dev`, copiando `ingestion/`, `flows/`, `migrations/` e `alembic.ini`".
- ADR 0004 (trechos): "Serviço de execução única, declarado em `profiles` (o `jobs` do PR 11, rodado com `docker compose run --rm jobs <comando>`), fica com `restart: "no"`. A regra 'todo serviço tem `restart: unless-stopped`' continua valendo para todo serviço sem `profiles`. `mem_limit` continua obrigatório em todos, com ou sem profile." "A imagem dos jobs é construída na própria VPS até o PR 37." "Não construir imagem com um job agendado em execução."
- `.claude/rules/infra.md` ainda diz "Todo serviço no compose tem `restart: unless-stopped`". O ADR 0004 prevalece; cite-o no corpo do PR para o `code-reviewer` e o `pr-reviewer` (pergunta em aberto 1).

#### Código existente relevante

- `ingestion/db.py`: `build_engine(url=None)` lê `DATABASE_URL`; `MissingConfiguration`; `upsert(...)`.
- `migrations/env.py`: `build_engine(os.environ.get("DATABASE_URL_ADMIN") or os.environ.get("DATABASE_URL"))`. Ou seja, com `DATABASE_URL_ADMIN` no ambiente, o `alembic` usa o admin.
- `migrations/versions/0002_roles.py`: os papéis (`ingestor` etc.) são criados sem senha; "migrations must always run with the same admin (DATABASE_URL_ADMIN)". A senha do `ingestor` é definida à mão no item 12.
- Cabeça atual do Alembic: `0003` (`migrations/versions/0003_ref_locations.py`).
- `alembic.ini` na raiz: `script_location = %(here)s/migrations`, `prepend_sys_path = .`.
- `flows/__init__.py` existe (pacote vazio); `pyproject.toml` empacota `ingestion` e `flows` com hatchling.
- `.gitignore` já ignora `.env`, `.env.*` (exceto `.env.example`), `__pycache__/`, `.venv/` e caches.
- Não existem `.dockerignore`, `.gitattributes`, `infra/jobs/` nem `ingestion/cli.py`.

#### `infra/docker-compose.yml` atual (projeto `name: platform`)

Serviços `health` (busybox) e `postgres` (`postgres:16.15`, `restart: unless-stopped`, `mem_limit: 256m`, `POSTGRES_USER: ${POSTGRES_ADMIN_USER:?POSTGRES_ADMIN_USER is required}`, `POSTGRES_PASSWORD: ${POSTGRES_ADMIN_PASSWORD:?POSTGRES_ADMIN_PASSWORD is required}`, `POSTGRES_DB: ml`, healthcheck com `pg_isready`, porta `${POSTGRES_BIND_IP:-127.0.0.1}:5432:5432`) e volume `pgdata`. Sem `image:` no `jobs`, o compose nomeia a imagem `platform-jobs` (projeto `platform` + serviço `jobs`), que é o nome do ADR 0001.

#### `tests/infra/test_compose.py` atual (o que já vale para o `jobs` sem mudança)

- `services_missing_restart`: só serviços **sem** `profiles` precisam de `restart: unless-stopped` (já alinhado ao ADR 0004, com exemplo negativo embutido em `test_restart_check_rejects_missing_or_wrong_policy_but_skips_profiles`). **Não alterar.**
- `services_missing_mem_limit`: todos, com ou sem profile.
- `PORT_PUBLISHING_SERVICES = frozenset({"health", "postgres"})`: o `jobs` não entra.
- `literal_secret_keys`: chaves com `PASSWORD`, `TOKEN`, `SECRET` etc. só com `${...}`. Atenção: `DATABASE_URL` não tem marcador, então a senha embutida na URL **não** é coberta por essa checagem; o caso 12 cobre.
- `undeclared_variables`: toda `${VAR}` ou `${VAR:?...}` do compose precisa estar em `infra/.env.example`.

#### `.github/workflows/ci.yml` atual

Job `lint-and-test` (uv, ruff, `alembic upgrade head` no Postgres de serviço, `pytest`, `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q`, `shellcheck infra/scripts/*.sh`) e job `compose-smoke` com `COMPOSE: docker compose -f infra/docker-compose.yml --env-file infra/.env.example`, que sobe `postgres` com `--wait`, confere `pg_hba` e porta, e faz `down -v` com `if: always()`. O admin fictício do `.env.example` é `platform_admin`.

## 5. Passos

1. (test-writer) Escreva `tests/test_cli.py`, `tests/infra/test_jobs_image.py` e os casos novos em `tests/infra/test_compose.py` (seção 8), no estilo do arquivo existente: funções de checagem exercitadas por exemplos negativos embutidos. Rode `uv run pytest tests/test_cli.py tests/infra` e confirme que falham porque `ingestion.cli` não existe, `infra/jobs/Dockerfile` e `.dockerignore` não existem e o compose não tem serviço `jobs` (e não por erro de import de dependência). Rode `uv run ruff check .` e `uv run ruff format --check .`. Commit `test: add cli and jobs image tests`.
2. (implementer) `ingestion/cli.py`:
   - `@dataclass(frozen=True) class Subcommand` com `help: str`, `add_arguments: Callable[[argparse.ArgumentParser], None]` e `run: Callable[[argparse.Namespace], int]`.
   - `SUBCOMMANDS: dict[str, Subcommand] = {}` no nível do módulo. Os PRs seguintes só acrescentam entradas.
   - `main(argv: list[str] | None = None) -> int`: monta o parser **dentro** de `main`, a partir de `SUBCOMMANDS` lido na hora (para o `monkeypatch` dos testes funcionar); `prog="python -m ingestion"`; `add_subparsers(dest="command", required=True)`.
   - Códigos de saída: `0` sucesso; `1` falha de execução ou de checagem; `2` uso incorreto. Uso incorreto e `--help` saem pelo `SystemExit` do próprio argparse (2 e 0); não capture esse `SystemExit`.
   - Exceção (`Exception`) não tratada dentro de `run`: escreva o traceback em `sys.stderr` com `traceback.print_exc()` (não dependa só de `logging`: durante o pytest o root logger já tem handler e o `basicConfig` não faz nada), registre `logger.error("subcommand %s failed", name)` e devolva `1`.
   - Logging: `logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")`.
3. `ingestion/__main__.py`: `from ingestion.cli import main` e `raise SystemExit(main())`.
4. `infra/jobs/Dockerfile` (contexto = raiz do repo):
   - `FROM ghcr.io/astral-sh/uv:<versão do uv>-python3.12-bookworm-slim`, com a versão do uv fixada (confira no GHCR do Astral a tag mais recente que existe com o sufixo `-python3.12-bookworm-slim`). Não use a tag flutuante `python3.12-bookworm-slim`. Digest: ver pergunta em aberto 3.
   - `ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never TZ=America/Sao_Paulo`.
   - `RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*` (o `TZ` precisa do `tzdata`; o PR 16 instala o mesmo pacote de novo sem problema).
   - `WORKDIR /app`; `COPY pyproject.toml uv.lock .python-version ./`; `RUN uv sync --locked --no-dev --no-install-project`; `COPY ingestion/ ingestion/`, `COPY flows/ flows/`, `COPY migrations/ migrations/`, `COPY alembic.ini ./`; `RUN uv sync --locked --no-dev`.
   - Nada de `COPY . .` nem `ADD`. Nenhum `ARG`/`ENV` com senha, token ou URL de banco.
   - `ENV PATH="/app/.venv/bin:$PATH"`.
   - Usuário não-root no fim: `RUN useradd --create-home --uid 10001 app` e `USER app`.
   - `ENTRYPOINT []` (zera qualquer entrypoint herdado da base) e `CMD ["python", "-m", "ingestion", "--help"]`.
5. `.dockerignore` na raiz, no mínimo: `.git`, `.venv`, `**/.env`, `**/.env.*`, `**/__pycache__`, `**/*.pyc`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `.claude`, `docs`, `tests`, `node_modules`, `*.pem`, `*.key`. Use `**/` nos padrões de `.env`: no `.dockerignore`, `.env*` só casa na raiz e deixaria passar `infra/.env`. **Não** exclua `infra/` inteiro: o PR 16 copia `infra/cron/`.
6. `infra/.env.example`: o implementador não pode ler o arquivo (deny de `Read`), então Edit/Write não funcionam nele. Anexe sem ler, pelo Bash: `printf '%s\n' '# Password of the ingestor role (set on the server in item 12). Fake value.' 'POSTGRES_INGESTOR_PASSWORD=change-me-ingestor' >> infra/.env.example`. Confira com `uv run pytest tests/infra` (os testes leem o arquivo em Python). Se o usuário preferir outra forma (colar o conteúdo ou editar ele mesmo), siga a decisão dele.
7. Serviço `jobs` em `infra/docker-compose.yml`, depois de `postgres`:
   ```yaml
     jobs:
       build:
         context: ..
         dockerfile: infra/jobs/Dockerfile
       profiles: ["jobs"]
       restart: "no"
       mem_limit: 512m
       environment:
         DATABASE_URL: postgresql+psycopg://ingestor:${POSTGRES_INGESTOR_PASSWORD:?POSTGRES_INGESTOR_PASSWORD is required}@postgres:5432/ml
         DATABASE_URL_ADMIN: postgresql+psycopg://${POSTGRES_ADMIN_USER:?POSTGRES_ADMIN_USER is required}:${POSTGRES_ADMIN_PASSWORD:?POSTGRES_ADMIN_PASSWORD is required}@postgres:5432/ml
       depends_on:
         postgres:
           condition: service_healthy
   ```
   - `restart: "no"` **entre aspas**: sem aspas o YAML 1.1 (PyYAML) lê `no` como `False`.
   - Sem `ports`, sem `volumes`, sem `env_file`, sem `image:` (PR 37).
   - `mem_limit: 512m`: pico estimado do job com pandas 200–400 MB (índice, "VPS de 1 GB"), a medir no checkpoint 28a.
8. `.github/workflows/ci.yml`, job `compose-smoke`, depois do passo "Check Postgres is not published on 0.0.0.0" e antes do `down -v`:
   - `run: $COMPOSE build jobs`
   - `run: $COMPOSE run --rm jobs` (sem comando: roda o `CMD`, que é o `--help`, e deve sair com 0)
   - `name: Check the jobs image runs as a non-root user`, `run: test "$($COMPOSE run --rm -T jobs whoami)" = app`
   - `run: $COMPOSE run --rm jobs alembic upgrade head`
   - `name: Check migrations reached head`, `run: $COMPOSE run --rm -T jobs alembic current | grep -F '(head)'`
   - O `docker compose run` de um serviço com profile ativa o profile sozinho; não precisa de `--profile jobs`. O passo `config -q` do `lint-and-test` continua e passa a validar o `jobs`.
9. `AGENTS.md`, seção "Comandos", acrescente:
   - CLI local: `uv run python -m ingestion --help`
   - Imagem dos jobs: `docker build -f infra/jobs/Dockerfile -t platform-jobs .`
   - Na VPS (até o PR 37 a imagem é construída lá, ADR 0004): `docker compose -f infra/docker-compose.yml build jobs` e `docker compose -f infra/docker-compose.yml run --rm jobs <comando>` (ex.: `alembic upgrade head`)
10. Rode os critérios de pronto e cole comando e saída no corpo do PR. No corpo do PR, cite o ADR 0004 como base do `restart: "no"`.

## 6. Critérios de pronto

Comandos em bash (Git Bash no Windows; no PowerShell use `$LASTEXITCODE` no lugar de `$?`).

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_cli.py tests/infra` | Todos passam |
| `uv run python -m ingestion --help; echo $?` | Texto com `usage: python -m ingestion` e `0` |
| `uv run python -m ingestion does-not-exist; echo $?` | `invalid choice` no stderr e `2` |
| `uv run python -m ingestion; echo $?` | Erro de argumento obrigatório no stderr e `2` |
| `docker build -f infra/jobs/Dockerfile -t platform-jobs .` | Termina sem erro |
| `docker run --rm platform-jobs; echo $?` | Texto de uso e `0` |
| `docker run --rm platform-jobs whoami` | `app` |
| `docker run --rm platform-jobs alembic heads` | `0003 (head)` |
| `docker run --rm platform-jobs date +%Z` | `-03` |
| `docker run --rm platform-jobs ls -A /app` | Exatamente `.python-version`, `.venv`, `alembic.ini`, `flows`, `ingestion`, `migrations`, `pyproject.toml`, `uv.lock` |
| `docker run --rm platform-jobs sh -c "env \| grep -ci -e password -e database_url"` | `0` (nenhum segredo nem URL de banco gravado na imagem) |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q` | Sem saída, código 0 |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example up -d --wait postgres`, depois `... run --rm jobs alembic upgrade head` e `... run --rm jobs alembic current` (mesmo prefixo) | Última linha `0003 (head)`; ao fim, `... down -v` |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem erros |
| `uv run pytest` (com o compose de dev de pé) | Suíte verde |
| `gh pr checks` | Verde, incluindo os passos novos do `compose-smoke` |

## 7. Testes necessários

`sim`: a CLI define os códigos de saída que o agendador (PR 16) e depois o Prefect usam para saber se um job falhou, e o Dockerfile e o compose carregam regras de segurança (não-root, sem segredo, sem porta) que precisam de trava.

## 8. Casos de teste

"Código efetivo" de `main(argv)` = o valor devolvido ou, se `main` levantar `SystemExit`, o `code` dele. Os testes não exigem uma das duas formas para uso incorreto. Nenhum caso precisa de Postgres (sem marcador `db`).

CLI (`tests/test_cli.py`):

1. `main(["--help"])` → código efetivo 0; stdout contém `usage` e `python -m ingestion`.
2. `main([])` (sem subcomando) → código efetivo 2; stderr contém `usage`.
3. `main(["does-not-exist"])` → código efetivo 2; stderr contém `invalid choice`.
4. Com `SUBCOMMANDS` substituído no teste (`monkeypatch.setitem` ou `monkeypatch.setattr`) por um subcomando `ok` que devolve 0 → `main(["ok"])` devolve 0.
5. Subcomando de teste que declara `--day` e devolve 0 só se recebeu `args.day == "2026-11-07"` → `main(["echo", "--day", "2026-11-07"])` devolve 0 (os argumentos chegam ao `run`).
6. Subcomando de teste que devolve 1 → `main` devolve 1.
7. Subcomando de teste que levanta `RuntimeError("boom")` → `main` devolve 1, sem propagar a exceção; stderr contém `Traceback` e `boom`.
8. `subprocess.run([sys.executable, "-m", "ingestion", "--help"])` → código 0 e saída com `usage` (o `__main__` existe e propaga o código).

Compose (`tests/infra/test_compose.py`, serviço `jobs` de `infra/docker-compose.yml`):

9. O serviço `jobs` existe e tem `profiles == ["jobs"]`, `restart == "no"` (a string; o `False` que vem de `restart: no` sem aspas reprova), `mem_limit` definido e nenhuma chave `ports`. Exemplo negativo embutido: `{"profiles": ["jobs"], "restart": False}` reprova.
10. `build.context == ".."` e `build.dockerfile == "infra/jobs/Dockerfile"`, e o arquivo `infra/jobs/Dockerfile` existe.
11. `environment.DATABASE_URL` casa com `postgresql+psycopg://ingestor:${POSTGRES_INGESTOR_PASSWORD...}@postgres:5432/ml` (usuário `ingestor`, nunca o admin). Exemplos negativos: URL com `${POSTGRES_ADMIN_USER}` como usuário reprova; URL com host `localhost` reprova.
12. Em toda variável `DATABASE_URL*` do `jobs`, o usuário é uma referência `${...}` ou o literal `ingestor`, e a senha é uma referência `${...}` inteira, nunca um literal. Exemplos negativos: `postgresql+psycopg://ingestor:hunter2@postgres:5432/ml` e `postgresql+psycopg://admin:${A}x@postgres:5432/ml` reprovam.
13. `depends_on.postgres.condition == "service_healthy"`. Os testes gerais existentes (restart só para serviços sem profile, `mem_limit` em todos, allow-list de portas, variáveis declaradas no `.env.example`, que agora exige `POSTGRES_INGESTOR_PASSWORD`) continuam passando sem alteração.

Imagem (`tests/infra/test_jobs_image.py`, leitura estática de `infra/jobs/Dockerfile` e `.dockerignore`; cada checagem com exemplos negativos embutidos):

14. O `FROM` usa `ghcr.io/astral-sh/uv:<X.Y.Z>-python3.12-bookworm-slim`, com ou sem `@sha256:<64 hex>` no fim. Reprovam: `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`, `ghcr.io/astral-sh/uv:latest`, `ghcr.io/astral-sh/uv` sem tag, `python:3.12-slim`, `ghcr.io/astral-sh/uv:0.9.5-python3.11-bookworm-slim`.
15. A última instrução `USER` existe e não é `root` nem `0`. Reprovam: Dockerfile sem `USER`; `USER root` depois de `USER app`; `USER 0`.
16. Não há `ADD`, nem `COPY` com fonte `.` ou `./` (contexto inteiro). Reprovam: `COPY . .`, `COPY ./ /app/`, `ADD ingestion/ ingestion/`. Passa: `COPY ingestion/ ingestion/`.
17. Nenhuma instrução `ENV` ou `ARG` tem nome com `PASSWORD`, `TOKEN`, `SECRET` ou `DATABASE_URL`. Reprovam: `ENV DATABASE_URL=...`, `ARG POSTGRES_ADMIN_PASSWORD`.
18. Toda linha `RUN` com `uv sync` contém `--locked` e `--no-dev`. Reprovam: `RUN uv sync`, `RUN uv sync --locked`.
19. `.dockerignore` existe e tem padrões que excluem `.env` em qualquer profundidade (`**/.env` e `**/.env.*`, ou `**/.env*`), além de `.git` e `.venv`. Reprova: arquivo só com `.env*` (casa só na raiz).

## 9. Riscos e perguntas em aberto

1. **`.claude/rules/infra.md` desalinhada do ADR 0004 (decisão do usuário).** A regra diz "Todo serviço no compose tem `restart: unless-stopped`" e "Deploy só sai de merge na `main`. Nada de SSH manual para mudar produção", e o ADR 0004 registra as duas exceções e deixa o ajuste "para o PR que tocar a regra". Este PR é o primeiro com serviço em `profiles`, mas o implementador não edita `.claude/` (instrução do `CLAUDE.md`). Recomendação: o usuário abre um PR pequeno só com o ajuste da regra (passa pelos dois revisores, porque `.claude/` não é `docs/**`), mergeado antes da revisão deste PR, para o `code-reviewer` não apontar o `restart: "no"` como violação. Texto sugerido: "Todo serviço sem `profiles` tem `restart: unless-stopped`; serviço de execução única em `profiles` usa `restart: "no"` (ADR 0004). Todo serviço tem `mem_limit`." e, na linha do deploy, "Exceção registrada até o PR 39 (ADR 0004)". Alternativa: o usuário commita o ajuste nesta mesma branch. Não bloqueia a implementação.
2. **Credencial do admin no `jobs`.** O `jobs` recebe `DATABASE_URL_ADMIN` porque roda as migrações (item 12, PR 39) e o `create-databases` (PR 28). Como é execução manual e única, o risco é aceitável. O plano 16 diz que o `scheduler` usa "mesmo `environment` do `jobs`": o PR 16 **não** deve copiar o `DATABASE_URL_ADMIN` para o `scheduler`, que é de longa duração e só precisa do `ingestor`. Registrar isso ao executar o PR 16.
3. **Digest da imagem base (decisão do usuário).** O plano exige tag com a versão do uv (mesmo critério do `postgres:16.15`). Acrescentar `@sha256:` deixa o build reproduzível, mas sem Dependabot (fora do ADR 0002) a atualização é manual. Recomendação: só a tag versionada agora; reavaliar no PR 37.
4. **hadolint (decisão do usuário).** Não existe no repo nem vem instalado no `ubuntu-latest`. Os casos 14 a 18 cobrem as regras que importam aqui. Adicionar hadolint seria ferramenta nova, fora deste PR.
5. **`AGENTS.md` desatualizado.** A linha "Migrações e Postgres de teste: ainda não existem (PRs 05 e 06)" está errada desde os PRs 05 e 06. Não está neste escopo; o usuário decide se entra neste PR (o passo 9 já edita a seção) ou num PR próprio.
6. **Senha na URL.** As senhas entram cruas nas URLs. O SQLAlchemy aceita `/` e `+` na senha, mas `@`, `%` e `:` quebram ou alteram o parse. O item 12 sugere `openssl rand -base64 24` (pode gerar `/` e `+`, aceitos); `openssl rand -hex 24` nunca gera caractere especial e é mais seguro para as senhas do `ingestor` e do admin.
7. **`:?` no compose.** Com `${POSTGRES_INGESTOR_PASSWORD:?...}`, comandos do compose falham se a variável faltar no `infra/.env`, possivelmente inclusive `up -d postgres`. É o comportamento desejado (falha cedo); o item 12 já manda acrescentar a variável antes do primeiro `up`.
8. **Build na VPS** (ADR 0004): 1 vCPU, 1 GB de RAM + 2 GB de swap. O `uv sync` com pandas é lento e pode usar swap; não construir com um job em execução. A arquitetura da VPS (`uname -m`, item 02) define a plataforma da imagem; a base do Astral é multi-arquitetura.
9. **Fim de linha no Windows.** Não há `.gitattributes`. Com `core.autocrlf=true`, o Dockerfile local pode ficar com CRLF; o Docker tolera na maioria dos casos, e a VPS e o CI fazem checkout com LF. Se o build local falhar por `\r`, não adicione `.gitattributes` neste PR: registre e avise o usuário.
10. A variante `bookworm-slim` vem do ADR 0002. Trocar para `trixie-slim` (Debian estável atual) mudaria uma decisão registrada; fica `bookworm` aqui.

## 10. Decisões que exigem ADR

Nenhuma nova. O `restart: "no"` em `profiles` e o build na VPS estão no ADR 0004 (mergeado); a base `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`, o `uv sync --locked --no-dev` e o Python 3.12 estão no ADR 0002 (mergeado). O `jobs` não publica porta (sem ADR de rede). Nenhuma mudança em `raw`, `ref` ou no contrato.
