# 33 — Deployments do Prefect com as agendas vigentes

> Executa: agente. Depende de: 32 (flows na `main`) e do **ADR obrigatório** "Agendamento e execução pelo Prefect" (seção 10), escrito pelo usuário ou pela skill `generate-adr` e mergeado antes da implementação. Branch sugerida: `feat/prefect-deployments` (ADR 0001).
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.
> Revisão 2026-11-08: reescrito contra a `main` em `05c32c9`: horários vigentes em `infra/cron/crontab` (06:30, 06:45, 07:00, `America/Sao_Paulo`, pelo menos 15 min entre jobs, regras travadas em `tests/infra/test_crontab.py`) e nomes do ADR 0001 (`POOL = "platform"`, `TIMEZONE`, `register()`, `DEPLOYMENTS`, deployment `production`). Revisão 2 (mesmo dia): aplica a revisão independente aceita pelo usuário. Muda o entrypoint por caminho de módulo, o pool com o template padrão do `ProcessWorker`, o fuso só via `Cron` (nunca lista de schedules vazia) e os critérios executáveis, remove a alternativa `prefect.yaml` e torna o ADR obrigatório. Alinhamento entre planos (mesmo dia): a autenticação da API vem do PR 30 (`PREFECT_API_AUTH` no `.env`, `PREFECT_API_AUTH_STRING` no cliente). Revisão final (mesmo dia): os critérios que sobem o compose de produção localmente ficam opcionais e só com autorização do usuário (colidem com o Postgres de teste na 5432); valor fictício da credencial escrito por extenso.

## 1. Objetivo

Declarar em `flows/deployments.py` os deployments `production` dos três flows de ingestão, com agenda cron no fuso `America/Sao_Paulo`, work pool `platform` do tipo `process` (template padrão do worker) com limite de 1 execução simultânea, e `register()` (`python -m flows.deployments`) para registrá-los no server.
O registro é idempotente (rodar de novo atualiza, não duplica), e as regras de horário do crontab passam a valer para os deployments.

## 2. Fora do escopo

- Serviço `prefect-worker` no compose e `PREFECT_API_URL`/`PREFECT_API_AUTH_STRING` no serviço `jobs` (PR 34). Registrar na VPS (item 35). Chamar o registro no deploy automático (PR 39, que já usa `python -m flows.deployments`).
- Remover o crontab, o supercronic e os testes do crontab (PR 36). Até lá, um teste de transição garante que os horários batem com o crontab.
- Mudar horários (ajuste do item 18 é PR próprio). Deployments de score e monitoramento: os PRs 46 e 54 acrescentam entradas em `DEPLOYMENTS`.
- Pausar ou apagar deployments por código: no cutover, isso é operação manual (item 35).
- Registrar deployments no `compose-smoke` do CI: entra no PR 34, junto com o worker.

## 3. Fase do roadmap

Fase 3 — "MLflow, Prefect e CI/CD", item "Ingestões migradas para flows do Prefect".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `flows/deployments.py` (novo) | `POOL`, `POOL_TYPE`, `POOL_CONCURRENCY_LIMIT`, `TIMEZONE`, `DEPLOYMENT_NAME`, `WORKING_DIR`, `DEPLOYMENTS` e `register()`; `python -m flows.deployments` registra tudo |
| `tests/test_deployments.py` (novo, test-writer) | Tabela de horários, regras migradas do crontab, transição e registro no server de teste |
| `AGENTS.md` | Comando local para registrar deployments (bash e PowerShell) |

### O que existe hoje e precisa bater

`infra/cron/crontab` (horários em `America/Sao_Paulo`, pelo `TZ` da imagem):

```
30 6 * * * python -m ingestion weather-forecast
45 6 * * * python -m ingestion weather-observed
0 7 * * * python -m ingestion ons-load
```

Regras travadas por `tests/infra/test_crontab.py` que migram para os deployments:

- uma linha por job;
- minuto e hora fixos (sem `*`, lista ou intervalo); dia, mês e dia da semana `*`;
- nada nas horas 23 e 0, porque o snapshot da previsão usa "hoje" em `America/Sao_Paulo`;
- nenhum argumento: o modo diário usa a janela padrão;
- dois jobs quaisquer com pelo menos 15 minutos de distância (`MIN_SPACING_MINUTES = 15`).

Correspondência flow → subcomando: `ingest_weather_forecast` → `weather-forecast`, `ingest_weather_observed` → `weather-observed`, `ingest_ons_load` → `ons-load`.

`flows/ingest.py` (PR 32): flows `ingest_weather_forecast()`, `ingest_weather_observed(start=None, end=None, days=None)` e `ingest_ons_load(start=None, end=None, days=None)`. Sem parâmetros, cada um usa a janela diária. O pacote `flows` é instalado na imagem (`pyproject.toml`: `packages = ["ingestion", "flows"]`, com `uv sync` no Dockerfile), então `flows.ingest` é importável por módulo de qualquer diretório.

`infra/jobs/Dockerfile`: `WORKDIR /app`, com `flows/` e `ingestion/` em `/app`, usuário `app`. O worker do PR 34 roda nessa imagem, com o código embutido (sem pull de git nem storage remoto).

### O que o PR 30 entrega (na `main` antes deste PR)

Server Prefect 3.x (imagem `prefecthq/prefect:<X.Y.Z>-python3.12@sha256:<64 hex>`) no serviço `prefect-server`, API em `http://prefect-server:4200/api` dentro do compose e em `http://127.0.0.1:4200/api` no host (porta só em loopback). Banco `prefect` criado pelo subcomando do PR 28 (`python -m ingestion create-databases`, no serviço `jobs`). API autenticada (plano 30, D7): o server usa `PREFECT_SERVER_API_AUTH_STRING`, vindo da variável `PREFECT_API_AUTH` do `infra/.env` (formato `admin:<senha>`); o cliente que registra precisa de `PREFECT_API_AUTH_STRING` no ambiente com o mesmo valor. No compose local, esse valor é o fictício do `infra/.env.example`, **`admin:change-me-prefect-auth`** (plano 30, passo 3; não é segredo). O código de `register()` não muda: o cliente do Prefect lê a variável sozinho.

## 5. Passos

1. (test-writer) Antes dos testes de registro, confira os nomes da API de cliente na versão instalada:

   ```bash
   uv run python -c "from prefect import get_client; import inspect; print(inspect.signature(get_client))"
   uv run python -c "from prefect.client.orchestration import SyncPrefectClient as C; print([m for m in ('read_deployment_by_name','read_deployments','read_work_pool','create_work_pool','update_work_pool') if hasattr(C, m)])"
   ```

   → `get_client` aceita `sync_client`; os cinco métodos existem. Se faltar algum, use o equivalente da versão: o comportamento verificado na seção 8 não muda.
2. (test-writer) Escreva os casos da seção 8 em `tests/test_deployments.py`. Os testes estáticos importam `flows.deployments` e comparam com uma tabela fixa escrita no teste (oráculo independente do código). Os de registro usam `prefect_test_harness()` (fixture de módulo) e consultam o server de teste com `get_client(sync_client=True)`. Porte do `tests/infra/test_crontab.py`, já com os exemplos negativos, as funções de checagem de horário (minuto e hora fixos, meia-noite, espaçamento), adaptadas para receber uma expressão cron. Confirme a falha por `ModuleNotFoundError: No module named 'flows.deployments'`. Commit `test: add deployment definition tests`.
3. (implementer) Antes de codar, confira a API na versão instalada:

   ```bash
   uv run python -c "import inspect; from prefect.flows import Flow; print(inspect.signature(Flow.to_deployment))"
   uv run python -c "import inspect; from prefect.deployments.runner import RunnerDeployment; print(inspect.signature(RunnerDeployment.apply))"
   uv run python -c "from prefect.deployments.runner import EntrypointType; print(list(EntrypointType))"
   uv run python -c "from prefect.schedules import Cron; print(Cron('30 6 * * *', timezone='America/Sao_Paulo'))"
   uv run python -c "from prefect.workers.process import ProcessWorker; t = ProcessWorker.get_default_base_job_template(); print('working_dir' in t['variables']['properties'])"
   ```

   → `to_deployment` aceita `name`, `schedules`, `parameters`, `job_variables`, `work_pool_name` e `entrypoint_type`; `apply` existe (diferente de `deploy()`, ele não exige imagem nem storage); `EntrypointType` tem `MODULE_PATH`; `Cron` com `timezone` existe; `True`. Se `EntrypointType` estiver em outro módulo (por exemplo `prefect.flows`), importe de lá. Se algum outro item não existir, pare e devolva para o planejamento.
4. (implementer) `flows/deployments.py`:
   - Constantes: `POOL = "platform"`, `POOL_TYPE = "process"`, `POOL_CONCURRENCY_LIMIT = 1`, `TIMEZONE = "America/Sao_Paulo"`, `DEPLOYMENT_NAME = "production"`, `WORKING_DIR = "/app"`.
   - `DEPLOYMENTS`: tupla imutável de registros `(flow, cron)`, um por flow de `flows.ingest`, com os crons da tabela da seção 4. Nenhum cron vazio.
   - `register() -> None`:
     1. Garante o pool: lê `POOL`. Se não existe, cria com `type=POOL_TYPE`, `concurrency_limit=1` e `base_job_template=ProcessWorker.get_default_base_job_template()`, para que a variável `working_dir` exista no template. Se existe com outro limite, atualiza o limite para 1 (o worker do PR 34 pode tê-lo criado antes, sem limite).
     2. Para cada item de `DEPLOYMENTS`: `flow.to_deployment(name=DEPLOYMENT_NAME, schedules=[Cron(cron, timezone=TIMEZONE)], parameters={}, job_variables={"working_dir": WORKING_DIR}, entrypoint_type=EntrypointType.MODULE_PATH)`, aplicado no pool `POOL` com `.apply(...)`. O entrypoint fica `flows.ingest.<nome do flow>`, independente do sistema e do diretório de quem registra.
     3. O fuso entra **só** pelo `Cron(cron, timezone=TIMEZONE)` dentro de `schedules`; não use `cron=`/`timezone=` soltos (não são aceitos em todas as rotas). `register()` **nunca** passa `schedules=[]` nem omite `schedules`: lista vazia ou ausente preserva os schedules antigos no server, e uma agenda velha continuaria valendo.
     4. Registra no log (logger `flows.deployments`, INFO) o nome e o cron de cada deployment aplicado.
   - `if __name__ == "__main__":` configura `logging.basicConfig(level=logging.INFO)` e chama `register()`. Exceção sobe, e o processo sai com código diferente de 0.
5. (implementer) `AGENTS.md`, "Comandos": "Registrar deployments do Prefect (local, com o `prefect-server` do compose no ar): bash `PREFECT_API_URL=http://127.0.0.1:4200/api PREFECT_API_AUTH_STRING=admin:change-me-prefect-auth uv run python -m flows.deployments`; PowerShell `$env:PREFECT_API_URL='http://127.0.0.1:4200/api'; $env:PREFECT_API_AUTH_STRING='admin:change-me-prefect-auth'; uv run python -m flows.deployments`". É o valor fictício do `infra/.env.example` (plano 30), não segredo. A forma da VPS entra no PR 34.
6. Rode os critérios de pronto e refatore com a suíte verde.

## 6. Critérios de pronto

Obrigatórios (sem subir o compose de produção):

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_deployments.py tests/infra/test_crontab.py` | Todos passam (o crontab não mudou; os casos 7 a 13 provam registro, idempotência, pool e schedules no server de teste do `prefect_test_harness`) |
| `uv run python -c "from flows.deployments import DEPLOYMENTS, POOL, TIMEZONE; print(POOL, TIMEZONE, sorted(f.name + ' ' + c for f, c in DEPLOYMENTS))"` | `platform America/Sao_Paulo ['ingest_ons_load 0 7 * * *', 'ingest_weather_forecast 30 6 * * *', 'ingest_weather_observed 45 6 * * *']` |
| `uv run ruff check .`, `uv run ruff format --check .` e `uv run pytest` | Sem achados; suíte verde |
| `gh pr checks` | Verde |

Opcionais, **só com autorização explícita do usuário** (sobem o compose de produção localmente, que colide com o Postgres de teste na 5432). No CI, o registro contra o `prefect-server` do compose é provado pelo `compose-smoke` do PR 34. Se autorizado: `docker compose -f infra/docker-compose.dev.yml stop` antes, e no fim `$DC down` (**nunca `-v`**) e `docker compose -f infra/docker-compose.dev.yml start`. `DC` abrevia `docker compose -f infra/docker-compose.yml --env-file infra/.env.example` (bash: `DC="docker compose -f infra/docker-compose.yml --env-file infra/.env.example"`; PowerShell: `function DC { docker compose -f infra/docker-compose.yml --env-file infra/.env.example @args }`). No PowerShell, troque `VAR=valor comando` por `$env:VAR='valor'; comando`.

| Comando | Saída esperada |
| --- | --- |
| `$DC up -d --wait postgres` | `postgres` `Healthy` |
| `$DC --profile jobs run --rm -T jobs python -m ingestion create-databases; echo "exit=$?"` | `exit=0` |
| `$DC up -d --wait prefect-server` | `prefect-server` `Healthy` |
| `PREFECT_API_URL=http://127.0.0.1:4200/api PREFECT_API_AUTH_STRING=admin:change-me-prefect-auth uv run python -m flows.deployments; echo "exit=$?"` | Três linhas de log, uma por deployment, e `exit=0` |
| (mesmas variáveis) `uv run prefect deployment ls` | `ingest_weather_forecast/production`, `ingest_weather_observed/production`, `ingest_ons_load/production` |
| Registrar de novo e listar | Continuam três |
| (mesmas variáveis) `uv run prefect deployment inspect 'ingest_weather_forecast/production'` | Contém `30 6 * * *`, `America/Sao_Paulo`, `platform` e `flows.ingest.ingest_weather_forecast` |
| (mesmas variáveis) `uv run prefect work-pool inspect platform` | Contém `process`, limite de concorrência `1` e `working_dir` no template |
| `$DC down` | Sem erro. **Nunca `-v`**: apagaria os volumes de dados locais |

## 7. Testes necessários

`sim`: horário, fuso ou pool errados fazem o job rodar na hora errada, ou não rodar, sem nenhum erro visível; o registro precisa ser idempotente.

## 8. Casos de teste

Estáticos (sem server):

1. `DEPLOYMENTS` tem exatamente um item por flow de `flows.ingest` (`ingest_weather_forecast`, `ingest_weather_observed`, `ingest_ons_load`), sem repetição.
2. Tabela fixa: `ingest_weather_forecast` → `30 6 * * *`; `ingest_weather_observed` → `45 6 * * *`; `ingest_ons_load` → `0 7 * * *`.
3. `TIMEZONE == "America/Sao_Paulo"`, `POOL == "platform"`, `POOL_TYPE == "process"`, `POOL_CONCURRENCY_LIMIT == 1`, `DEPLOYMENT_NAME == "production"`.
4. Regras migradas do crontab, para todos os crons de `DEPLOYMENTS`: cron não vazio, com cinco campos; minuto e hora números fixos; dia, mês e dia da semana `*`; hora fora de `{23, 0}`; todo par com pelo menos 15 minutos de distância.
5. Exemplos negativos das checagens do caso 4. Rejeitados como "não diário em horário fixo": `*/5 6 * * *`, `30 * * * *`, `30 6,7 * * *`, `30 6-8 * * *`, `30 6 * * 1` e `""`. Rejeitados como "perto da meia-noite": `55 23 * * *` e `5 0 * * *`. Rejeitados como "menos de 15 minutos": os pares `(30 6, 40 6)` e `(30 6, 30 6)`. Aceitos: `(30 6, 45 6)` e os três crons reais.
6. Transição (removido no PR 36): enquanto `infra/cron/crontab` existir, o cron de cada deployment é igual aos cinco primeiros campos da linha do subcomando correspondente, e o crontab não tem nenhum subcomando sem deployment.

Com server de teste (`prefect_test_harness`):

7. Depois de `register()`, o server tem `ingest_weather_forecast/production`, `ingest_weather_observed/production` e `ingest_ons_load/production`, cada um com **exatamente um** schedule, ativo, com o cron da tabela e timezone `America/Sao_Paulo`.
8. Cada deployment registrado tem work pool `platform`, entrypoint exatamente `flows.ingest.<nome do flow>` (caminho de módulo, sem `/`, `\` nem `.py`, inclusive quando o teste roda no Windows), `path` em `(None, ".")` (não grava o diretório de quem registrou), `job_variables` com `working_dir` = `/app` e parâmetros vazios.
9. O pool `platform` existe, tipo `process`, limite de concorrência `1`, e o `base_job_template` dele declara a variável `working_dir` (template padrão do `ProcessWorker`).
10. Pool `platform` criado antes, sem limite (como o worker faria) → depois de `register()`, mesmo pool, tipo `process`, limite `1`.
11. `register()` duas vezes → continuam três deployments desses flows, cada um com um schedule só.
12. `DEPLOYMENTS` trocado no teste (monkeypatch) para `35 6 * * *` na previsão, depois `register()` de novo → o deployment da previsão tem um schedule só, com `35 6 * * *` (atualiza, não acrescenta nem preserva o antigo).
13. `python -m flows.deployments` em subprocesso, com `PREFECT_API_URL=http://127.0.0.1:1/api` e `PREFECT_CLIENT_MAX_RETRIES=0` → código de saída diferente de 0 e stderr não vazio (a falha não é engolida).

## 9. Riscos e perguntas em aberto

### Decisões (com recomendação; aceitas pelo usuário)

- **D1. Como registrar.** **Python: `flows/deployments.py` com `to_deployment(..., entrypoint_type=EntrypointType.MODULE_PATH)` e `.apply()`.** Usa os nomes do ADR 0001 (`DEPLOYMENTS`, `register()`), é o comando que os planos 39, 46 e 54 já chamam e dá para testar no mesmo processo com o harness. O erro "precisa de imagem ou storage remoto" é de `deploy()`/`flow.deploy()`, não de `apply()`, então não há motivo para a rota `prefect.yaml` + `prefect deploy`; ela fica descartada, assim como `flow.serve()` (plano 34, D1).
- **D2. Concorrência.** **Limite 1 no pool, declarado em código**, e `--limit 1` no worker (PR 34). Numa VPS de 1 vCPU (2 GB depois do 28b), dois flows com pandas ao mesmo tempo podem passar do `mem_limit` do worker (768m).
- **D3. Quem cria o pool.** **`register()`**, com o template padrão do `ProcessWorker`, criando ou corrigindo o limite. Tipo, limite e template ficam versionados; o auto-create do worker é só rede de segurança.
- **D4. Entrypoint.** **Caminho de módulo (`flows.ingest.<flow>`)**, mais `working_dir=/app`. O deployment não depende de onde foi registrado: no Windows, um entrypoint por arquivo gravaria `\`.
- **D5. Fuso e schedules.** **Fuso só via `schedules=[Cron(cron, timezone=TIMEZONE)]`; nunca lista vazia.** A lista vazia preservaria schedules antigos no server.
- **D6. Execuções atrasadas.** Se o worker estiver fora no horário, o Prefect marca a execução como `Late` e o worker a executa quando volta. Depois de uma queda longa (mais de um dia), o worker executa **em fila**, uma por vez (limite 1), todas as `Late` acumuladas. **Aceitar o padrão:** é inofensivo, porque os jobs são idempotentes (previsão com `ignore`, os outros com upsert) e cada um recalcula a janela na hora da execução. O único efeito é que a previsão de um dia perdido grava o snapshot do dia corrente, não o do dia perdido (risco que já existe hoje).

### Riscos

- **API do Prefect.** Os pontos vieram de memória e de revisão independente com acesso à web, e o passo 3 os confere: `Flow.to_deployment(..., schedules=, parameters=, job_variables=, work_pool_name=, entrypoint_type=)`, `RunnerDeployment.apply()`, `EntrypointType.MODULE_PATH`, `prefect.schedules.Cron(cron, timezone=)`, `ProcessWorker.get_default_base_job_template()`, os métodos do `get_client(sync_client=True)` e `PREFECT_CLIENT_MAX_RETRIES`. O caso 12 trava a substituição de schedules ao reaplicar.
- **Dois agendadores ao mesmo tempo.** Registrar deployments ativos num server com worker enquanto o supercronic ainda roda faz cada job rodar duas vezes por dia. Os dados aguentam, mas o item 35 define a ordem para isso não acontecer. Este PR não registra nada em produção.
- **Fuso.** Explícito no schedule, não herdado do container; o `TZ` da imagem só afeta horário de log.
- **Compose local.** Subir o compose de produção na máquina do desenvolvedor colide com o Postgres de teste (5432); por isso esses critérios são opcionais e dependem de autorização.

### Perguntas em aberto

- Nenhuma bloqueante, além do ADR da seção 10.

## 10. Decisões que exigem ADR

**Sim, obrigatório, antes da implementação deste PR (e do 34 e do item 35).** É decisão estrutural e de segurança. O ADR "Agendamento e execução pelo Prefect" (número dado quando for escrito; escrito pelo usuário ou pela skill `generate-adr`, em PR próprio, mergeado antes do 33) registra:

- work pool `platform` do tipo `process`, com template padrão; um único worker no compose; limite de 1 execução; código embutido na imagem `jobs`; entrypoint por caminho de módulo. Docker pool (exigiria o socket do Docker) e `serve()` são rejeitados; a justificativa de RAM e segurança está no plano 34, D1;
- agendas declaradas em código (`flows/deployments.py`), em `America/Sao_Paulo`, como única fonte de verdade dos horários depois do PR 36;
- registro idempotente por `python -m flows.deployments` (manual até o PR 39, automático depois);
- autenticação da API do Prefect (`PREFECT_API_AUTH` no `infra/.env`; `PREFECT_SERVER_API_AUTH_STRING` no server, `PREFECT_API_AUTH_STRING` nos clientes), porque, sem ela, qualquer nó da tailnet que alcance a API poderia rodar código no worker com a credencial `ingestor` (plano 34, risco 1);
- fronteira de credenciais do worker: só `DATABASE_URL` do `ingestor`; o `scorer` da Fase 4 é decidido no PR 46;
- a substituição do agendador interino do ADR 0004 (cutover no item 35, remoção no PR 36; status do ADR 0004 atualizado no PR de docs depois do primeiro deploy automático do PR 39).
