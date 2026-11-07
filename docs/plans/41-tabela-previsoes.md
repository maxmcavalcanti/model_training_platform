# 41 — Tabela `predictions.model_predictions`

> Executa: agente. Depende de: 25 (próxima revisão Alembic) e da Fase 3 pronta (item 40). Branch sugerida: `feat/predictions-table`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar por migração a tabela única de previsões de todos os modelos, escrita pelo job de score com o usuário `scorer`.
Cada execução do score grava um lote novo (identificado por `generated_at`), sem apagar lotes anteriores.

## 2. Fora do escopo

- Job de score (PRs 42 a 46). `monitoring.model_metrics` (PR 51).

## 3. Fase do roadmap

Fase 4 — Score e painéis: "Job genérico de score lendo `@champion`" (pré-requisito).

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `migrations/versions/0008_predictions_model_predictions.py` | Tabela; `downgrade` a remove |
| `tests/test_predictions_model_predictions.py` | Testes (test-writer) |

Modelo de dados (`docs/plataforma-ml.md`):

| Tabela | Colunas principais | Chave | Escreve | Lê |
| --- | --- | --- | --- | --- |
| `predictions.model_predictions` | `model_name`, `model_version`, `key`, `target_date`, `predicted_value`, `generated_at` | (`model_name`, `key`, `target_date`, `generated_at`) | Job de score | Todos |

"`key` é o que o modelo prevê: o subsistema no modelo de carga, o `location_id` no de chuva. Assim uma única tabela de previsões serve a todos os modelos."

## 5. Passos

1. (test-writer) Testes da seção 8 (`@pytest.mark.db`, banco migrado). Confirme falha porque a tabela não existe. Commit `test: add predictions.model_predictions tests`.
2. (implementer) `uv run alembic revision -m "predictions_model_predictions" --rev-id 0008` (ou o próximo livre).
3. `upgrade`: `predictions.model_predictions (model_name text not null, model_version text not null, key text not null, target_date date not null, predicted_value double precision not null, generated_at timestamptz not null, primary key (model_name, key, target_date, generated_at))` e um índice em (`model_name`, `target_date`) para os painéis e o monitoramento.
4. `downgrade`: `DROP TABLE predictions.model_predictions`.
5. Permissões pelos privilégios padrão (PR 07): `scorer` escreve, todos leem.
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_predictions_model_predictions.py tests/test_migrations.py` | Todos passam |
| `uv run alembic heads` | `0008 (head)` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: a chave com `generated_at` define como reexecuções convivem; permissão de escrita é só do `scorer`.

## 8. Casos de teste

1. Inserir uma previsão (`load_d1`, `3`, `SE`, 2026-11-08, 41000.0, now()) funciona.
2. Mesma (`model_name`, `key`, `target_date`) com `generated_at` diferente → duas linhas coexistem.
3. Mesma chave completa duas vezes → violação de chave primária.
4. `predicted_value` nulo → violação de `NOT NULL`.
5. Como `scorer`, `INSERT` funciona; como `ingestor`, `scientist` e `reader`, `INSERT` falha e `SELECT` funciona.

## 9. Riscos e perguntas em aberto

- Classificação (`rain_d1`): `predicted_value` guarda a probabilidade (0 a 1). Se ela quiser guardar também a classe, é mudança de contrato; anotar para o ADR do PR 44.

## 10. Decisões que exigem ADR

Nenhuma além do ADR de execução de modelos (PR 44), que fixa o formato da saída de `predict`.
