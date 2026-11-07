# 42 — Núcleo do score: chamar o contrato, validar a saída e gravar

> Executa: agente. Depende de: 41. Branch sugerida: `feat/score-nucleo`.
> Pré-requisito: ADR "Execução de modelos" (ver PR 44, seção 10) aprovado, pelo menos na parte do tipo de `conn` e do objeto `model`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar `gerar_previsoes`, que recebe o módulo do modelo e o modelo já carregados, chama `build_features` → `predict`, valida a saída contra o contrato e grava um lote em `predictions.previsoes`.
Função pura em relação a MLflow e instalação de pacote, para ser testável com um módulo falso.

## 2. Fora do escopo

- Descobrir os modelos `champion` no MLflow (PR 43). Instalar a versão do pacote `modelos` (PR 44). Ponto de entrada e flow (PRs 45 e 46).

## 3. Fase do roadmap

Fase 4 — "Job genérico de score lendo `@champion`".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `flows/score.py` | `SaidaInvalida`, `SCHEMA_SAIDA_PREDICT`, `gerar_previsoes(...)` |
| `tests/test_score_nucleo.py` | Testes com módulo e modelo falsos (test-writer) |

Contrato (`docs/plataforma-ml.md`, "Contrato com a ciência de dados"):

```python
def build_features(conn, data_ref: date) -> pd.DataFrame: ...
    # lê raw/ref; só usa dados disponíveis até data_ref (sem vazamento)

def predict(model, features: pd.DataFrame) -> pd.DataFrame: ...
    # devolve colunas: chave, data_alvo, valor_previsto
```

"Todo dia, o job de score busca `models:/<nome>@champion` no MLflow, chama `build_features` → `predict` e grava em `predictions.previsoes`." "Erro dentro do código dela aparece no Prefect com o traceback, e quem investiga é ela."

Código existente: `ingestion/db.py` (`upsert`), `ingestion/checks.py` (`checar`).

## 5. Passos

1. (test-writer) Testes da seção 8 com um módulo falso (`types.SimpleNamespace` com `build_features` e `predict`) e `banco_migrado`. Confirme falha por `ModuleNotFoundError: flows.score`. Commit `test: add score core tests`.
2. (implementer) `flows/score.py`:
   - `class SaidaInvalida(RuntimeError)`.
   - `SCHEMA_SAIDA_PREDICT` (pandera): colunas `chave` (texto, não nula), `data_alvo` (data, não nula), `valor_previsto` (float, não nulo, finito); unicidade (`chave`, `data_alvo`); colunas extras são rejeitadas.
   - `gerar_previsoes(conn, *, nome: str, versao: str, modulo, modelo, data_ref: date, agora: datetime) -> int`:
     1. `features = modulo.build_features(conn, data_ref)`. Exceção aqui **não** é capturada (o traceback dela precisa aparecer inteiro).
     2. `saida = modulo.predict(modelo, features)`. Idem.
     3. Valida `saida`; falha → `SaidaInvalida` com o nome do modelo e o detalhe.
     4. `data_alvo` < `data_ref` → `SaidaInvalida` (previsão para o passado).
     5. Saída vazia → `SaidaInvalida` (um champion que não prevê nada é falha, não sucesso).
     6. Grava com `upsert(conn, "predictions.previsoes", df, chaves=["modelo","chave","data_alvo","gerado_em"], ao_conflitar="ignorar", carimbar_ingerido_em=False)` com `modelo=nome`, `versao_modelo=versao`, `gerado_em=agora` (o mesmo valor para o lote inteiro).
     7. Devolve o número de linhas.
3. Rode os critérios de pronto e refatore com a suíte verde.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_score_nucleo.py` | Todos passam |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: a validação da saída é a fronteira do contrato; sem ela, um modelo quebrado grava lixo silenciosamente.

## 8. Casos de teste

1. Módulo falso que devolve 4 linhas (`SE`, `S`, `NE`, `N`, `data_alvo` = D+1) → 4 linhas em `predictions.previsoes` com `modelo`, `versao_modelo` e o mesmo `gerado_em`; retorno 4.
2. `build_features` recebe exatamente `conn` e `data_ref`; `predict` recebe o `modelo` passado e o DataFrame de `build_features`.
3. Rodar duas vezes com `agora` diferente → 8 linhas (dois lotes).
4. Rodar duas vezes com o mesmo `agora` → 4 linhas.
5. `predict` sem a coluna `valor_previsto` → `SaidaInvalida` citando a coluna; nada gravado.
6. `valor_previsto` com `NaN` → `SaidaInvalida`.
7. `(chave, data_alvo)` duplicado → `SaidaInvalida`.
8. Coluna extra `classe` → `SaidaInvalida`.
9. `data_alvo` anterior a `data_ref` → `SaidaInvalida`.
10. Saída vazia → `SaidaInvalida`.
11. `build_features` levantando `KeyError("x")` → a mesma `KeyError` sobe (não é embrulhada).

## 9. Riscos e perguntas em aberto

- P13 (tipo de `conn`): este plano assume `sqlalchemy.Connection` (funciona com `pd.read_sql`). Se o ADR escolher outro tipo, os testes mudam aqui.
- Colunas extras rejeitadas é escolha deste plano (contrato estrito). Alternativa: ignorar extras. Decidir no ADR.

## 10. Decisões que exigem ADR

Depende do ADR "Execução de modelos" (PR 44).
