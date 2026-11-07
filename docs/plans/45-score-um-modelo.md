# 45 — Ponto de entrada `python -m flows.score_um` (roda dentro do ambiente isolado)

> Executa: agente. Depende de: 42, 43, 44. Branch sugerida: `feat/score-um`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar o módulo executável que, já dentro do ambiente com o pacote `modelos` (PR 44), importa `modelos.<nome>`, carrega `models:/<nome>@champion` do MLflow e chama `gerar_previsoes` (PR 42) com uma conexão do usuário `scorer`.
É a cola entre as três peças anteriores, para um modelo e uma data.

## 2. Fora do escopo

- Percorrer todos os champions e agendar (PR 46).

## 3. Fase do roadmap

Fase 4 — "Job genérico de score lendo `@champion`".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `flows/score_um.py` | `main(argv) -> int` e `if __name__ == "__main__"` |
| `tests/fixtures/modelos_fake/src/modelos/teste_fake/__init__.py` | Garantir que `build_features` lê `ref.locais` e `predict` usa o modelo (test-writer) |
| `tests/test_score_um.py` | Teste de ponta a ponta: MLflow SQLite + banco de teste + executor (test-writer) |

Código existente (leia): `flows/score.py` (`gerar_previsoes(conn, *, nome, versao, modulo, modelo, data_ref, agora)`, `SaidaInvalida`), `flows/registro.py` (`Champion`, `listar_champions`), `flows/executor.py` (`montar_comando`, `executar`, `ExecucaoFalhou`, `MODELOS_FONTE_LOCAL`), `ingestion/db.py` (`criar_engine`). Decisões do ADR "Execução de modelos": `conn` é `sqlalchemy.Connection`; `model` é `mlflow.pyfunc.load_model(uri)`.

## 5. Passos

1. (test-writer) Ajuste o pacote falso: `build_features(conn, data_ref)` devolve um DataFrame com os `subsistema` distintos de `ref.locais` e `data_ref`; `predict(model, features)` devolve `chave=subsistema`, `data_alvo=data_ref + 1 dia`, `valor_previsto=model.predict(features)` onde o modelo pyfunc de teste devolve uma constante. Escreva os testes da seção 8: registram o modelo `teste_fake` num MLflow SQLite em `tmp_path` com alias `champion` e tag `pacote_modelos=v0.0.1`, e usam `banco_migrado`. Confirme falha. Commit `test: add single-model score entrypoint tests`.
2. (implementer) `flows/score_um.py`:
   - Argumentos: `--modelo NOME --versao N --data AAAA-MM-DD --gerado-em ISO8601`.
   - `MLFLOW_TRACKING_URI` e `DATABASE_URL_SCORER` vêm do ambiente; ausentes → mensagem e código 2.
   - `modulo = importlib.import_module(f"modelos.{nome}")`; `modelo = mlflow.pyfunc.load_model(f"models:/{nome}/{versao}")` (versão explícita, para não trocar de versão no meio se o alias mudar durante a execução).
   - `with criar_engine(DATABASE_URL_SCORER).begin() as conn: gerar_previsoes(...)`.
   - Imprime `previsoes gravadas: <n>` e devolve 0. Exceções sobem (o traceback vai para o stderr e o executor do PR 44 o captura).
3. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_score_um.py` | Todos passam |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: é o primeiro teste de ponta a ponta do contrato (MLflow → pacote → banco).

## 8. Casos de teste

1. Via `executar(montar_comando("v0.0.1", "flows.score_um", [...]))` com `MODELOS_FONTE_LOCAL` = fixture: 4 linhas em `predictions.previsoes` com `modelo='teste_fake'`, `versao_modelo='1'` e o `gerado_em` passado.
2. `--modelo nao_existe` → `ExecucaoFalhou` contendo `ModuleNotFoundError`.
3. Pacote falso com `predict` que devolve `NaN` (variante da fixture selecionada por variável de ambiente do teste) → `ExecucaoFalhou` contendo `SaidaInvalida`; nada gravado.
4. Sem `DATABASE_URL_SCORER` → código 2.
5. A conexão usada é do papel `scorer` (o `build_features` falso grava `current_user` num atributo; ou o teste confere que um `INSERT` em `raw` dentro de `build_features` falha com `permission denied`).

## 9. Riscos e perguntas em aberto

- `mlflow.pyfunc.load_model` dentro do ambiente efêmero precisa das dependências do modelo dela (ex.: `lightgbm`). Elas vêm do pacote `modelos` (dependências fixadas no `pyproject.toml` dela, como o doc pede). Se faltar, o erro é dela.

## 10. Decisões que exigem ADR

Depende do ADR "Execução de modelos" (PR 44).
