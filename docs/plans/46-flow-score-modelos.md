# 46 — Flow `score_models` e deployment às 07:30

> Executa: agente. Depende de: 45. Branch sugerida: `feat/flow-score`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar o flow diário que, para cada modelo com `champion`, roda `flows.score_one` no ambiente isolado da versão certa do pacote `modelos`, e agendá-lo às 07:30 BRT.
Falha de um modelo não impede os outros; o flow termina `Failed` se algum falhou.

## 2. Fora do escopo

- Monitoramento (Fase 5). Alertas (PR 55).

## 3. Fase do roadmap

Fase 4 — "Job genérico de score lendo `@champion`".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `flows/score_flow.py` | `@flow(name="score_models")` e `@task score_model` |
| `flows/deployments.py` | Entrada `score_models` com cron `30 7 * * *` |
| `infra/docker-compose.yml` | `prefect-worker`: `DATABASE_URL_SCORER`, `MLFLOW_TRACKING_URI=http://mlflow:5000`, `MODELS_REPO` (repo público, sem token); `depends_on: mlflow` |
| `infra/.env.example` | `POSTGRES_SCORER_PASSWORD` |
| `tests/test_flow_score.py`, `tests/test_deployments.py`, `tests/infra/test_compose.py` | Testes (test-writer) |

Do doc: "07:30 `score_models` — Para cada modelo com `champion`, gera previsões do dia". "Trocar o alias `champion` para outra versão é o deploy. Nenhum PR na plataforma, nenhuma ação minha."

Código existente: `flows/registry.py` (`list_champions`), `flows/executor.py` (`build_command`, `executar`, `RunFailed`), `flows/deployments.py` (`DEPLOYMENTS`, `registrar`), `flows/score_one.py` (argumentos `--model --version --date --generated-at`).

## 5. Passos

1. (test-writer) Testes da seção 8 com `prefect_test_harness`, `monkeypatch` de `list_champions` e de `executar` (registrando comandos). Acrescente em `tests/test_deployments.py`: `score_models` com `30 7 * * *`. Em `tests/infra/test_compose.py`: o worker tem `DATABASE_URL_SCORER` com o usuário `scorer` e `MLFLOW_TRACKING_URI` interno. Confirme falha. Commit `test: add score flow tests`.
2. (implementer) `flows/score_flow.py`:
   - `score_models(ref_date: date | None = None)`: `ref_date` padrão = hoje em `America/Sao_Paulo`; `generated_at` = agora (UTC), o mesmo para todos os modelos da execução.
   - Lista os champions; nenhum → log "nenhum modelo com champion" e `Completed`.
   - Para cada champion, a task `score_model` (sem retries): `package_version` ausente → falha da task com mensagem "modelo X sem tag models_package"; senão `executar(build_command(package_version, "flows.score_one", [...]))`.
   - Submete as tasks e espera todas; se alguma falhou, o flow levanta erro listando os modelos que falharam (depois de todas terminarem).
3. `flows/deployments.py`: entrada `score_models` às `30 7 * * *`.
4. Compose: variáveis do worker como na tabela; `.env.example` com `POSTGRES_SCORER_PASSWORD`.
5. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_flow_score.py tests/test_deployments.py tests/infra/` | Todos passam |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: isolamento de falhas entre modelos e o comportamento sem champion são regras de operação.

## 8. Casos de teste

1. Dois champions (`a` com `v0.1.0`, `b` com `v0.2.0`) → `executar` chamado duas vezes, cada uma com o `--with` da sua versão e o mesmo `--generated-at`; flow `Completed`.
2. Nenhum champion → `executar` não é chamado; `Completed`.
3. `a` falha (`RunFailed`) e `b` funciona → `executar` chamado para os dois; flow `Failed` com mensagem citando `a`.
4. Champion sem `package_version` → essa task falha, as outras rodam; flow `Failed` citando o modelo.
5. `score_models(ref_date=date(2026,11,7))` → todos os comandos com `--date 2026-11-07`.
6. Deployment `score_models` com `30 7 * * *`, fuso `America/Sao_Paulo`, pool `plataforma`.

## 9. Riscos e perguntas em aberto

- O worker passa a ter duas credenciais (`ingestor` e `scorer`). Alternativa mais rígida: um segundo worker, num pool `score`, só com `scorer`. Este plano fica com um worker (um segundo worker custaria mais memória numa VPS de 1 GB); o subprocesso só recebe `DATABASE_URL_SCORER` (o executor deve repassar só as variáveis necessárias). Confirmar com o usuário.

## 10. Decisões que exigem ADR

Nenhuma além do ADR "Execução de modelos".
