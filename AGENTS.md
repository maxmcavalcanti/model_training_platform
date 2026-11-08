# Plataforma ML

Plataforma de dados e execução de modelos numa VPS (Postgres, MLflow, Prefect, Grafana, Tailscale). Este repositório é o `platform` do desenho em `docs/plataforma-ml.md`. Os modelos vivem em outro repositório (`models`) e falam com a plataforma pelo contrato.

## Fronteira (nunca cruzar sem combinar)

- Este repo cuida de "o job rodou?". O repo `models` cuida de "o modelo está certo?".
- O único ponto de passagem é o alias `champion` no MLflow. Trocar o alias é o deploy de um modelo.
- Mudança em `raw` ou `ref` exige migração Alembic + ADR + aviso à ciência de dados. Mudança na assinatura de `build_features`, `predict` e `evaluate` exige ADR. Mudança que publica porta ou expõe serviço fora do tailnet/loopback também exige ADR.

## Onde ler mais (carregue só o que a tarefa pedir)

- `docs/plataforma-ml.md`: arquitetura, modelo de dados, jobs, contrato, CI/CD, roadmap por fases.
- `docs/guia-ciencia-de-dados.md`: o lado da cientista de dados. Útil para entender o contrato, não para editar.
- `docs/adr/`: decisões de arquitetura já tomadas. Leia antes de propor mudança estrutural.

## Regras de código

- Todo job de ingestão é idempotente: upsert por chave primária (`INSERT ... ON CONFLICT DO UPDATE`), nunca append cego.
- Toda linha em `raw` leva `ingested_at`.
- Todo job termina com checagem de qualidade (pandera). Checagem falha = execução falha.
- Nenhum segredo no git. Segredos entram por variável de ambiente.
- Lint de segurança pela regra `S` do ruff (ADR 0006). Achado se corrige no código; ignore só em `[tool.ruff.lint.per-file-ignores]` do `pyproject.toml`, restrito a caminho e regra, com comentário de motivo. Nunca `noqa`.
- O deny de `Read` não impede leitura via Bash (`cat .env`); portanto agentes nunca devem ler arquivos `.env`, com nenhuma ferramenta. O deny também bloqueia `.env.example`; se um agente precisar das variáveis documentadas, o usuário cola o conteúdo.
- TDD estrito: todo código de produção nasce de um teste vermelho. Ciclo: vermelho (test-writer) → implementação mínima → verde → refatorar com a suíte verde. Sem teste vermelho antes, sem código. Exceção: refatoração com a suíte já verde não exige teste vermelho novo.
- Merge na `main` é a única forma de mudar produção.
- Identificadores e artefatos de implementação em inglês: código, variáveis, funções, classes, módulos e nomes de arquivo de código, schemas, tabelas, colunas, papéis do Postgres, jobs, flows, subcomandos e flags de CLI, variáveis de ambiente, serviços, imagens, painéis, nomes de modelo, branches, comentários, mensagens de log e de erro do código, mensagens de commit e títulos e corpos de PR. A prosa de `docs/` (planos, guias, ADRs) continua em português. Tabela de nomes e regras de formação: `docs/adr/0001-english-naming-convention.md`.

## Comandos

- Instalar/atualizar ambiente: `uv sync`
- Lint: `uv run ruff check .`
- Formatação (checar): `uv run ruff format --check .` / aplicar: `uv run ruff format .`
- Suíte de testes: `uv run pytest`
- Um arquivo: `uv run pytest tests/test_smoke.py`
- Um teste: `uv run pytest tests/test_smoke.py::<test_name>`
- Adicionar dependência: `uv add <pacote>` (dev: `uv add --dev <pacote>`). Sempre commitar `uv.lock`.
- CLI local: `uv run python -m ingestion --help`
- Snapshot da previsão: `uv run python -m ingestion weather-forecast` (usa `DATABASE_URL`; na VPS: `docker compose -f infra/docker-compose.yml run --rm jobs python -m ingestion weather-forecast`)
- Calendário: `uv run python -m ingestion calendar --start 2015-01-01 --end 2030-12-31` (usa `DATABASE_URL`; na VPS: `docker compose -f infra/docker-compose.yml run --rm jobs python -m ingestion calendar --start 2015-01-01 --end 2030-12-31`)
- Carga do ONS: `uv run python -m ingestion ons-load` (janela dos últimos 30 dias; backfill: `--start 2015-01-01 --end 2015-12-31`; usa `DATABASE_URL`; na VPS: `docker compose -f infra/docker-compose.yml run --rm jobs python -m ingestion ons-load`)
- Clima observado: `uv run python -m ingestion weather-observed` (janela dos últimos 10 dias terminando ontem; backfill: `--start 2015-01-01`; usa `DATABASE_URL`; na VPS: `docker compose -f infra/docker-compose.yml run --rm jobs python -m ingestion weather-observed`)
- Imagem dos jobs: `docker build -f infra/jobs/Dockerfile -t platform-jobs .`
- Agendador interino (supercronic, até o PR 36): validar o crontab com `docker run --rm platform-jobs supercronic -test /app/infra/cron/crontab`; na VPS: `docker compose -f infra/docker-compose.yml build scheduler`, `docker compose -f infra/docker-compose.yml up -d scheduler` e `docker compose -f infra/docker-compose.yml logs scheduler`
- Na VPS (até o PR 37 a imagem é construída lá, ADR 0004): `docker compose -f infra/docker-compose.yml build jobs` e `docker compose -f infra/docker-compose.yml run --rm jobs <comando>` (ex.: `alembic upgrade head`)
- Validar o dependabot.yml: `uvx --from check-jsonschema==0.39.0 check-jsonschema --builtin-schema vendor.dependabot .github/dependabot.yml`
- Postgres de teste local: `docker compose -f infra/docker-compose.dev.yml up -d`
- Rodar só testes sem banco: `uv run pytest -m "not db"`
- Aplicar migrações: `uv run alembic upgrade head` (usa `DATABASE_URL_ADMIN` ou `DATABASE_URL`)
- Reverter uma: `uv run alembic downgrade -1`
- Nova migração: `uv run alembic revision -m "<descrição>" --rev-id <NNNN>` (próximo número livre, 4 dígitos)

## Fluxo de trabalho

- Mudança estrutural gera ADR em `docs/adr/` antes do código. Nenhum agente escreve ADR: o `task-planner` só sinaliza a necessidade no plano. O ADR é uma tarefa separada (PR próprio, escrito pelo usuário ou pela skill `generate-adr`) e precisa estar mergeado antes de a implementação começar.
- Fluxo de uma tarefa:
  1. `task-planner` grava o plano com casos de teste em `docs/plans/` e o usuário aprova.
  2. `test-writer` escreve os testes e confirma que falham (pular se o plano disser "Testes necessários: não").
  3. `task-implementer` implementa em worktree partindo da branch com os testes, sem editar testes.
  4. `code-reviewer` revisa antes do PR (dispensado em PR só de `docs/**`, ver abaixo).
  5. Abrir o PR (o CI roda no PR): quem abre é o usuário, ou o `task-implementer` quando receber essa instrução.
  6. CI + `pr-reviewer`, que revisa o PR contra o plano (dispensado em PR só de `docs/**`, ver abaixo).
- PR que altera somente `docs/**` (planos, ADRs, guias) dispensa o `code-reviewer` e o `pr-reviewer`: o usuário revisa se quiser e o merge pode ser feito sem revisão de agente. Qualquer PR que toque algo fora de `docs/**` (por exemplo `.claude/`, `AGENTS.md`, `CLAUDE.md`, `.gitignore`, código, infra ou CI) passa por ambos, mesmo quando só há Markdown, porque esses arquivos mudam o comportamento dos agentes ou do deploy.
- Uma fase do roadmap por vez. Não adiante itens de fases futuras.
- PR do Dependabot que troca o `postgres` de `infra/docker-compose.yml`: levar o mesmo `tag@sha256:` ao serviço `postgres` do `.github/workflows/ci.yml` (e ao `infra/docker-compose.dev.yml`, se o Dependabot não o atualizar), por commit na própria branch do Dependabot; o teste `test_postgres_reference_is_identical_in_prod_dev_and_ci` fica vermelho até isso. Merge de PR do Dependabot que muda `infra/` só chega à VPS pelo deploy manual do usuário (ADR 0004), fora da janela dos jobs.
- Dê evidência de que funciona: o comando rodado e a saída, não só "deve funcionar".
