# 42 — Núcleo do score: chamar o contrato, validar a saída e gravar

> Executa: agente. Depende de: 41. Branch sugerida: `feat/score-core`.
> Pré-requisito: ADR "Execução de modelos" (ver PR 44, seção 10) aprovado, pelo menos na parte do tipo de `conn` e do objeto `model`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar `generate_predictions`, que recebe o módulo do modelo e o modelo já carregados, chama `build_features` → `predict`, valida a saída contra o contrato e grava um lote em `predictions.model_predictions`.
Função pura em relação a MLflow e instalação de pacote, para ser testável com um módulo falso.

## 2. Fora do escopo

- Descobrir os modelos `champion` no MLflow (PR 43). Instalar a versão do pacote `modelos` (PR 44). Ponto de entrada e flow (PRs 45 e 46).

## 3. Fase do roadmap

Fase 4 — "Job genérico de score lendo `@champion`".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `flows/score.py` | `InvalidOutput`, `SCHEMA_PREDICT_OUTPUT`, `generate_predictions(...)` |
| `tests/test_score_core.py` | Testes com módulo e modelo falsos (test-writer) |

Contrato (`docs/plataforma-ml.md`, "Contrato com a ciência de dados"):

```python
def build_features(conn, ref_date: date) -> pd.DataFrame: ...
    # lê raw/ref; só usa dados disponíveis até ref_date (sem vazamento)

def predict(model, features: pd.DataFrame) -> pd.DataFrame: ...
    # devolve colunas: chave, target_date, predicted_value
```

"Todo dia, o job de score busca `models:/<nome>@champion` no MLflow, chama `build_features` → `predict` e grava em `predictions.model_predictions`." "Erro dentro do código dela aparece no Prefect com o traceback, e quem investiga é ela."

Código existente: `ingestion/db.py` (`upsert`), `ingestion/checks.py` (`checar`).

## 5. Passos

1. (test-writer) Testes da seção 8 com um módulo falso (`types.SimpleNamespace` com `build_features` e `predict`) e `migrated_database`. Confirme falha por `ModuleNotFoundError: flows.score`. Commit `test: add score core tests`.
2. (implementer) `flows/score.py`:
   - `class InvalidOutput(RuntimeError)`.
   - `SCHEMA_PREDICT_OUTPUT` (pandera): colunas `chave` (texto, não nula), `target_date` (data, não nula), `predicted_value` (float, não nulo, finito); unicidade (`chave`, `target_date`); colunas extras são rejeitadas.
   - `generate_predictions(conn, *, nome: str, versao: str, modulo, modelo, ref_date: date, agora: datetime) -> int`:
     1. `features = modulo.build_features(conn, ref_date)`. Exceção aqui **não** é capturada (o traceback dela precisa aparecer inteiro).
     2. `saida = modulo.predict(modelo, features)`. Idem.
     3. Valida `saida`; falha → `InvalidOutput` com o nome do modelo e o detalhe.
     4. `target_date` < `ref_date` → `InvalidOutput` (previsão para o passado).
     5. Saída vazia → `InvalidOutput` (um champion que não prevê nada é falha, não sucesso).
     6. Grava com `upsert(conn, "predictions.model_predictions", df, chaves=["modelo","chave","target_date","generated_at"], on_conflict="ignorar", stamp_ingested_at=False)` com `modelo=nome`, `model_version=versao`, `generated_at=agora` (o mesmo valor para o lote inteiro).
     7. Devolve o número de linhas.
3. Rode os critérios de pronto e refatore com a suíte verde.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_score_core.py` | Todos passam |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: a validação da saída é a fronteira do contrato; sem ela, um modelo quebrado grava lixo silenciosamente.

## 8. Casos de teste

1. Módulo falso que devolve 4 linhas (`SE`, `S`, `NE`, `N`, `target_date` = D+1) → 4 linhas em `predictions.model_predictions` com `modelo`, `model_version` e o mesmo `generated_at`; retorno 4.
2. `build_features` recebe exatamente `conn` e `ref_date`; `predict` recebe o `modelo` passado e o DataFrame de `build_features`.
3. Rodar duas vezes com `agora` diferente → 8 linhas (dois lotes).
4. Rodar duas vezes com o mesmo `agora` → 4 linhas.
5. `predict` sem a coluna `predicted_value` → `InvalidOutput` citando a coluna; nada gravado.
6. `predicted_value` com `NaN` → `InvalidOutput`.
7. `(chave, target_date)` duplicado → `InvalidOutput`.
8. Coluna extra `classe` → `InvalidOutput`.
9. `target_date` anterior a `ref_date` → `InvalidOutput`.
10. Saída vazia → `InvalidOutput`.
11. `build_features` levantando `KeyError("x")` → a mesma `KeyError` sobe (não é embrulhada).

## 9. Riscos e perguntas em aberto

- P13 (tipo de `conn`): este plano assume `sqlalchemy.Connection` (funciona com `pd.read_sql`). Se o ADR escolher outro tipo, os testes mudam aqui.
- Colunas extras rejeitadas é escolha deste plano (contrato estrito). Alternativa: ignorar extras. Decidir no ADR.

## 10. Decisões que exigem ADR

Depende do ADR "Execução de modelos" (PR 44).
