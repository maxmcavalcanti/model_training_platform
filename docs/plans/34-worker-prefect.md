# 34 — Worker do Prefect no compose

> Executa: agente. Depende de: 33. Branch sugerida: `feat/compose-prefect-worker`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Subir um worker do Prefect (tipo `process`, pool `platform`) usando a imagem `jobs`, que já tem o código e as dependências, para executar os deployments do PR 33.
Também passar a registrar os deployments num serviço de execução única do compose.

## 2. Fora do escopo

- Desligar o supercronic (PR 36). Deploy automático (PRs 37 e 39).

## 3. Fase do roadmap

Fase 3 — "MLflow e Prefect no compose" e "Ingestões migradas para flows do Prefect".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/docker-compose.yml` | Serviço `prefect-worker` e `environment` com `PREFECT_API_URL` interna |
| `tests/infra/test_compose.py` | Casos do worker (test-writer) |
| `.github/workflows/ci.yml` | Smoke: worker conecta e um flow de teste roda |

Código existente: `flows/deployments.py` (`POOL = "platform"`, `register()`, executável com `python -m flows.deployments`); serviço `jobs` (profile `jobs`) e `scheduler` em `infra/docker-compose.yml`; `infra/jobs/Dockerfile`.

## 5. Passos

1. (test-writer) Casos da seção 8. Confirme falha. Commit `test: add prefect worker compose tests`.
2. (implementer) Serviço `prefect-worker`:
   - Mesmo `build` do `jobs`; `command: ["prefect", "worker", "start", "--pool", "platform", "--type", "process"]`; `restart: unless-stopped`; `mem_limit: 384m` (parte do worker na estimativa de 500–800 MB de server + worker; os flows rodam como subprocesso dentro deste container, então o limite cobre o pico do job com pandas; ajuste pelo 28a); sem `ports`; `depends_on: prefect-server` saudável e `postgres` saudável.
   - `environment`: o mesmo do `jobs` (`DATABASE_URL` com `ingestor`), mais `PREFECT_API_URL: http://prefect-server:4200/api`.
3. No serviço `jobs`, acrescente `PREFECT_API_URL: http://prefect-server:4200/api`, para registrar deployments com `docker compose run --rm jobs python -m flows.deployments`.
4. `ci.yml`, no smoke: subir `postgres`, `prefect-server`, `prefect-worker`; `run --rm jobs python -m flows.deployments`; disparar `run --rm jobs prefect deployment run ingest_ons_load/production --param days=1` não serve (precisa de rede e banco migrado); em vez disso, confira só que o worker aparece: `run --rm jobs prefect work-pool inspect platform` contém `platform` e, nos logs do worker, `Worker ... started`.
5. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/` | Todos passam |
| Compose local com `.env.example`: `up -d --wait postgres prefect-server prefect-worker` | Todos `Healthy`/`Running` |
| `docker compose ... run --rm jobs python -m flows.deployments` | Sem erro |
| `docker compose ... logs prefect-worker` | Contém o pool `platform` e nenhum `Traceback` |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: o worker precisa usar o usuário `ingestor` e a API interna; erro aqui faz os flows rodarem com credencial errada ou não rodarem.

## 8. Casos de teste

1. `prefect-worker` tem `restart: unless-stopped` e `mem_limit`, sem `ports`.
2. `prefect-worker` usa a mesma imagem/`build` que `jobs` (código idêntico).
3. `PREFECT_API_URL` do worker e do `jobs` é `http://prefect-server:4200/api` (rede interna do compose, não a URL da tailnet).
4. `DATABASE_URL` do worker usa `ingestor`.
5. O `command` do worker contém `--pool platform` e o pool é o mesmo `POOL` de `flows/deployments.py` (o teste importa a constante).

## 9. Riscos e perguntas em aberto

- Na Fase 4 o worker também roda o score, que escreve com o usuário `scorer`. Um worker só com duas credenciais (`ingestor` e `scorer`) ou dois workers? Decidir no PR 46; aqui fica só `ingestor`.

## 10. Decisões que exigem ADR

Nenhuma.
