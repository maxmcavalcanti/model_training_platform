# 45 — Ponto de entrada `python -m flows.score_one` (roda dentro do ambiente isolado)

> Executa: agente. Depende de: 42, 43, 44. Branch sugerida: `feat/score-one`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar o módulo executável que, já dentro do ambiente com o pacote `models` (PR 44), importa `models.<nome>`, carrega `models:/<nome>@champion` do MLflow e chama `generate_predictions` (PR 42) com uma conexão do usuário `scorer`.
É a cola entre as três peças anteriores, para um modelo e uma data.

## 2. Fora do escopo

- Percorrer todos os champions e agendar (PR 46).

## 3. Fase do roadmap

Fase 4 — "Job genérico de score lendo `@champion`".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `flows/score_one.py` | `main(argv) -> int` e `if __name__ == "__main__"` |
| `tests/fixtures/fake_models/src/models/fake_model/__init__.py` | Garantir que `build_features` lê `ref.locations` e `predict` usa o modelo (test-writer) |
| `tests/test_score_one.py` | Teste de ponta a ponta: MLflow SQLite + banco de teste + executor (test-writer) |

Código existente (leia): `flows/score.py` (`generate_predictions(conn, *, name, version, module, model, ref_date, now)`, `InvalidOutput`), `flows/registry.py` (`Champion`, `list_champions`), `flows/executor.py` (`build_command`, `run`, `RunFailed`, `MODELS_LOCAL_SOURCE`), `ingestion/db.py` (`build_engine`). Decisões do ADR "Execução de modelos": `conn` é `sqlalchemy.Connection`; `model` é `mlflow.pyfunc.load_model(uri)`.

## 5. Passos

1. (test-writer) Ajuste o pacote falso: `build_features(conn, ref_date)` devolve um DataFrame com os `subsystem` distintos de `ref.locations` e `ref_date`; `predict(model, features)` devolve `key=subsystem`, `target_date=ref_date + 1 dia`, `predicted_value=model.predict(features)` onde o modelo pyfunc de teste devolve uma constante. Escreva os testes da seção 8: registram o modelo `fake_model` num MLflow SQLite em `tmp_path` com alias `champion` e tag `models_package=v0.0.1`, e usam `migrated_database`. Confirme falha. Commit `test: add single-model score entrypoint tests`.
2. (implementer) `flows/score_one.py`:
   - Argumentos: `--model NOME --version N --date AAAA-MM-DD --generated-at ISO8601`.
   - `MLFLOW_TRACKING_URI` e `DATABASE_URL_SCORER` vêm do ambiente; ausentes → mensagem e código 2.
   - `module = importlib.import_module(f"models.{name}")`; `model = mlflow.pyfunc.load_model(f"models:/{name}/{version}")` (versão explícita, para não trocar de versão no meio se o alias mudar durante a execução).
   - `with build_engine(DATABASE_URL_SCORER).begin() as conn: generate_predictions(...)`.
   - Imprime `previsoes gravadas: <n>` e devolve 0. Exceções sobem (o traceback vai para o stderr e o executor do PR 44 o captura).
3. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_score_one.py` | Todos passam |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: é o primeiro teste de ponta a ponta do contrato (MLflow → pacote → banco).

## 8. Casos de teste

1. Via `run(build_command("v0.0.1", "flows.score_one", [...]))` com `MODELS_LOCAL_SOURCE` = fixture: 4 linhas em `predictions.model_predictions` com `model_name='fake_model'`, `model_version='1'` e o `generated_at` passado.
2. `--model does_not_exist` → `RunFailed` contendo `ModuleNotFoundError`.
3. Pacote falso com `predict` que devolve `NaN` (variante da fixture selecionada por variável de ambiente do teste) → `RunFailed` contendo `InvalidOutput`; nada gravado.
4. Sem `DATABASE_URL_SCORER` → código 2.
5. A conexão usada é do papel `scorer` (o `build_features` falso grava `current_user` num atributo; ou o teste confere que um `INSERT` em `raw` dentro de `build_features` falha com `permission denied`).

## 9. Riscos e perguntas em aberto

- `mlflow.pyfunc.load_model` dentro do ambiente efêmero precisa das dependências do modelo dela (ex.: `lightgbm`). Elas vêm do pacote `models` (dependências fixadas no `pyproject.toml` dela, como o doc pede). Se faltar, o erro é dela.

## 10. Decisões que exigem ADR

Depende do ADR "Execução de modelos" (PR 44).
