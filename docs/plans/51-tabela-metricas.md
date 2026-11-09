# 51 — Tabela `monitoring.model_metrics`

> Executa: agente. Depende de: 41 (próxima revisão Alembic) e da Fase 4 pronta (item 50). Branch sugerida: `feat/monitoring-metrics`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.
> Nota 2026-11-08: número da migração ajustado de `0009` para `0010`, porque o plano 28 usa a `0008` e o 41 passa a usar a `0009`. Se outra migração entrar antes, use o próximo número livre.

## 1. Objetivo

Criar por migração a tabela onde o job de monitoramento grava, por modelo e dia, cada métrica devolvida por `evaluate`.
É a base do painel "erro real × previsto" que fecha a Fase 5.

## 2. Fora do escopo

- Job de monitoramento (PRs 52 a 54). Painel (PR 58).

## 3. Fase do roadmap

Fase 5 — Monitoramento e alertas: "Job de monitoramento + `monitoring.model_metrics`".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `migrations/versions/0010_monitoring_model_metrics.py` | Tabela; `downgrade` a remove |
| `tests/test_monitoring_model_metrics.py` | Testes (test-writer) |

Modelo de dados (`docs/plataforma-ml.md`): `monitoring.model_metrics` — `model_name`, `model_version`, `date`, `metric`, `value`; chave (`model_name`, `date`, `metric`); escreve Job de monitoramento (usuário `scorer`); lê Todos.

`date` = a `target_date` avaliada (o dia cujo real foi comparado com a previsão).

## 5. Passos

1. (test-writer) Testes da seção 8 (`@pytest.mark.db`, banco migrado). Confirme falha. Commit `test: add monitoring.model_metrics tests`.
2. (implementer) `uv run alembic revision -m "monitoring_model_metrics" --rev-id 0010` (ou o próximo livre).
3. `upgrade`: `monitoring.model_metrics (model_name text not null, model_version text not null, date date not null, metric text not null check (metric ~ '^[a-z][a-z0-9_]*$'), value double precision not null, primary key (model_name, date, metric))`.
4. `downgrade`: `DROP TABLE monitoring.model_metrics`.
5. Permissões pelos privilégios padrão (PR 07): `scorer` escreve, todos leem.
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_monitoring_model_metrics.py tests/test_migrations.py` | Todos passam |
| `uv run alembic heads` | `0010 (head)` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: chave e permissões fazem parte do contrato com o painel e com ela.

## 8. Casos de teste

1. Inserir (`moving_average`, `1`, 2026-11-07, `mape`, 3.1) funciona.
2. Mesma (`model_name`, `date`, `metric`) duas vezes → violação de chave primária.
3. `metric = 'MAPE %'` → violação de `CHECK`.
4. `value` nulo → violação.
5. Como `scorer`, `INSERT` e `UPDATE` funcionam; como `ingestor`, `scientist` e `reader`, só `SELECT`.

## 9. Riscos e perguntas em aberto

- A chave não inclui `model_version` (como no doc): se o champion mudar, a métrica de um dia reflete a versão que fez a previsão avaliada, e uma reexecução pode trocar `model_version`. Aceitável; o log de trocas de champion é dela.

## 10. Decisões que exigem ADR

Coberto pelo ADR "Contrato de dados" se for considerado contrato com a ciência de dados; senão nenhuma.
