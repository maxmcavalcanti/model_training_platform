# 11 — Imagem Docker dos jobs e CLI `python -m ingestion`

> Executa: agente. Depende de: 06, 10. Branch sugerida: `feat/jobs-image`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Empacotar o código do repo numa imagem Docker (`jobs`) e criar o ponto de entrada `python -m ingestion <subcomando>`, ainda sem subcomandos de ingestão.
Com isso a VPS consegue rodar migrações e, nos PRs seguintes, cada job, com o mesmo código do CI.

## 2. Fora do escopo

- Subcomandos de ingestão (PRs 15, 19, 22, 26).
- Agendamento (PR 16).
- Publicar a imagem no GHCR (PR 37; até lá a VPS constrói a imagem localmente).

## 3. Fase do roadmap

Fase 1 — infraestrutura necessária para "Ingestão do ONS" e para as migrações na VPS.

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `ingestion/cli.py` | `main(argv: list[str] \| None = None) -> int` com argparse e registro de subcomandos |
| `ingestion/__main__.py` | `raise SystemExit(main())` |
| `infra/jobs/Dockerfile` | Imagem com o pacote instalado, sem dependências de dev |
| `.dockerignore` | Exclui `.venv`, `.git`, `.env*`, caches, `docs/` |
| `infra/docker-compose.yml` | Serviço `jobs` no profile `jobs` (execução sob demanda) |
| `infra/.env.example` | `POSTGRES_INGESTOR_PASSWORD` (fictícia) |
| `tests/test_cli.py` | Testes da CLI (test-writer) |
| `tests/infra/test_compose.py` | Casos do serviço `jobs` (test-writer) |
| `.github/workflows/ci.yml` | `docker build` da imagem e `--help` dentro dela |
| `AGENTS.md` | Comandos: rodar a CLI e construir a imagem |

## 5. Passos

1. (test-writer) Escreva `tests/test_cli.py` e os casos de compose (seção 8). Confirme falha porque `ingestion.cli` não existe. Commit `test: add cli and jobs image tests`.
2. (implementer) `ingestion/cli.py`:
   - `SUBCOMMANDS: dict[str, Subcommand]`, onde cada subcomando registra seus argumentos e uma função `executar(args) -> int`. Os PRs seguintes só acrescentam entradas.
   - Códigos de saída: `0` sucesso; `1` falha de execução ou de checagem; `2` uso incorreto (padrão do argparse).
   - Exceção não tratada dentro de um subcomando: registra o traceback no stderr e devolve `1`.
   - Logging: `logging.basicConfig(level=INFO)` com formato que inclui data/hora e nome do logger.
3. `ingestion/__main__.py`: `from ingestion.cli import main; raise SystemExit(main())`.
4. `infra/jobs/Dockerfile`:
   - Base `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` (confira a tag no GHCR do Astral).
   - `WORKDIR /app`; copie `pyproject.toml`, `uv.lock`, `.python-version`; `uv sync --locked --no-dev --no-install-project`; copie `ingestion/`, `flows/`, `migrations/`, `alembic.ini`; `uv sync --locked --no-dev`.
   - `ENV PATH="/app/.venv/bin:$PATH" TZ=America/Sao_Paulo`.
   - Usuário não-root (`useradd -m app`, `USER app`).
   - Sem `ENTRYPOINT` fixo; `CMD ["python", "-m", "ingestion", "--help"]`.
5. Serviço `jobs` no `infra/docker-compose.yml`:
   - `build: {context: .., dockerfile: infra/jobs/Dockerfile}`, `profiles: ["jobs"]`, `restart: "no"`, `mem_limit: 512m` (pico estimado do job com pandas: 200–400 MB, a medir no checkpoint 28a), `depends_on: {postgres: {condition: service_healthy}}`.
   - `environment`: `DATABASE_URL: postgresql+psycopg://ingestor:${POSTGRES_INGESTOR_PASSWORD}@postgres:5432/ml`, `DATABASE_URL_ADMIN: postgresql+psycopg://${POSTGRES_ADMIN_USER}:${POSTGRES_ADMIN_PASSWORD}@postgres:5432/ml`.
   - Sem `ports`.
6. `.github/workflows/ci.yml`: passo `docker build -f infra/jobs/Dockerfile -t platform-jobs:ci .` e `docker run --rm platform-jobs:ci python -m ingestion --help`.
7. `AGENTS.md`, Comandos:
   - CLI local: `uv run python -m ingestion --help`
   - Imagem: `docker build -f infra/jobs/Dockerfile -t platform-jobs .`
   - Na VPS: `docker compose -f infra/docker-compose.yml run --rm jobs <comando>`
8. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_cli.py tests/infra/test_compose.py` | Todos passam |
| `uv run python -m ingestion --help` | Texto de uso, código 0 |
| `uv run python -m ingestion does-not-exist; echo $?` | Mensagem de erro do argparse e `2` |
| `docker build -f infra/jobs/Dockerfile -t platform-jobs .` | Termina sem erro |
| `docker run --rm platform-jobs alembic heads` | Mostra a cabeça atual (ex.: `0003 (head)`) |
| `docker run --rm platform-jobs whoami` | `app` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde, com os passos de build |

## 7. Testes necessários

`sim`: a CLI define códigos de saída que o agendador e, depois, o Prefect usam para saber se o job falhou.

## 8. Casos de teste

1. `main(["--help"])` sai com código 0 (via `SystemExit`) e a saída contém `usage`.
2. `main([])` (sem subcomando) devolve 2 e mostra o uso.
3. `main(["does-not-exist"])` sai com código 2.
4. Um subcomando registrado no teste (por `monkeypatch` em `SUBCOMMANDS`) que devolve 0 → `main` devolve 0.
5. Um subcomando de teste que levanta `RuntimeError("boom")` → `main` devolve 1 e o stderr contém `boom` e `Traceback`.
6. Compose: o serviço `jobs` está no profile `jobs`, não publica porta, tem `mem_limit` e não tem `restart: unless-stopped` (é execução única). A regra geral de restart continua valendo para todos os serviços sem profile.
7. Compose: `DATABASE_URL` do `jobs` usa o usuário `ingestor`, não o admin.

## 9. Riscos e perguntas em aberto

- P7: `.claude/rules/infra.md` diz "Todo serviço no compose tem `restart: unless-stopped`". O `jobs` é execução única e com essa política ficaria reiniciando em loop. Este plano trata serviços em `profiles` como exceção. Confirmar com o usuário; alternativa é tirar o `jobs` do compose e usar `docker run` com a rede do compose.
- O build na VPS (até o PR 37) usa CPU, memória e disco da própria VPS (1 vCPU, 1 GB de RAM + 2 GB de swap, 25 GB de SSD). Para este tamanho de imagem é aceitável, mas o build é lento e pode usar swap; não rode build com o job agendado em execução.

## 10. Decisões que exigem ADR

Nenhuma além da exceção acima, que pode entrar no ADR de deploy interino (ver índice, P6).
