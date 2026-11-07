# 41 — Tabela `predictions.previsoes`

> Executa: agente. Depende de: 25 (próxima revisão Alembic) e da Fase 3 pronta (item 40). Branch sugerida: `feat/predictions-previsoes`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar por migração a tabela única de previsões de todos os modelos, escrita pelo job de score com o usuário `scorer`.
Cada execução do score grava um lote novo (identificado por `gerado_em`), sem apagar lotes anteriores.

## 2. Fora do escopo

- Job de score (PRs 42 a 46). `monitoring.metricas` (PR 51).

## 3. Fase do roadmap

Fase 4 — Score e painéis: "Job genérico de score lendo `@champion`" (pré-requisito).

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `migrations/versions/0008_predictions_previsoes.py` | Tabela; `downgrade` a remove |
| `tests/test_predictions_previsoes.py` | Testes (test-writer) |

Modelo de dados (`docs/plataforma-ml.md`):

| Tabela | Colunas principais | Chave | Escreve | Lê |
| --- | --- | --- | --- | --- |
| `predictions.previsoes` | `modelo`, `versao_modelo`, `chave`, `data_alvo`, `valor_previsto`, `gerado_em` | (`modelo`, `chave`, `data_alvo`, `gerado_em`) | Job de score | Todos |

"`chave` é o que o modelo prevê: o subsistema no modelo de carga, o `local_id` no de chuva. Assim uma única tabela de previsões serve a todos os modelos."

## 5. Passos

1. (test-writer) Testes da seção 8 (`@pytest.mark.db`, banco migrado). Confirme falha porque a tabela não existe. Commit `test: add predictions.previsoes tests`.
2. (implementer) `uv run alembic revision -m "predictions_previsoes" --rev-id 0008` (ou o próximo livre).
3. `upgrade`: `predictions.previsoes (modelo text not null, versao_modelo text not null, chave text not null, data_alvo date not null, valor_previsto double precision not null, gerado_em timestamptz not null, primary key (modelo, chave, data_alvo, gerado_em))` e um índice em (`modelo`, `data_alvo`) para os painéis e o monitoramento.
4. `downgrade`: `DROP TABLE predictions.previsoes`.
5. Permissões pelos privilégios padrão (PR 07): `scorer` escreve, todos leem.
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_predictions_previsoes.py tests/test_migracoes.py` | Todos passam |
| `uv run alembic heads` | `0008 (head)` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: a chave com `gerado_em` define como reexecuções convivem; permissão de escrita é só do `scorer`.

## 8. Casos de teste

1. Inserir uma previsão (`carga_d1`, `3`, `SE`, 2026-11-08, 41000.0, now()) funciona.
2. Mesma (`modelo`, `chave`, `data_alvo`) com `gerado_em` diferente → duas linhas coexistem.
3. Mesma chave completa duas vezes → violação de chave primária.
4. `valor_previsto` nulo → violação de `NOT NULL`.
5. Como `scorer`, `INSERT` funciona; como `ingestor`, `cientista` e `leitura`, `INSERT` falha e `SELECT` funciona.

## 9. Riscos e perguntas em aberto

- Classificação (`chuva_d1`): `valor_previsto` guarda a probabilidade (0 a 1). Se ela quiser guardar também a classe, é mudança de contrato; anotar para o ADR do PR 44.

## 10. Decisões que exigem ADR

Nenhuma além do ADR de execução de modelos (PR 44), que fixa o formato da saída de `predict`.
