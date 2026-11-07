# 51 — Tabela `monitoring.metricas`

> Executa: agente. Depende de: 41 (próxima revisão Alembic) e da Fase 4 pronta (item 50). Branch sugerida: `feat/monitoring-metricas`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar por migração a tabela onde o job de monitoramento grava, por modelo e dia, cada métrica devolvida por `evaluate`.
É a base do painel "erro real × previsto" que fecha a Fase 5.

## 2. Fora do escopo

- Job de monitoramento (PRs 52 a 54). Painel (PR 58).

## 3. Fase do roadmap

Fase 5 — Monitoramento e alertas: "Job de monitoramento + `monitoring.metricas`".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `migrations/versions/0009_monitoring_metricas.py` | Tabela; `downgrade` a remove |
| `tests/test_monitoring_metricas.py` | Testes (test-writer) |

Modelo de dados (`docs/plataforma-ml.md`): `monitoring.metricas` — `modelo`, `versao_modelo`, `data`, `metrica`, `valor`; chave (`modelo`, `data`, `metrica`); escreve Job de monitoramento (usuário `scorer`); lê Todos.

`data` = a `data_alvo` avaliada (o dia cujo real foi comparado com a previsão).

## 5. Passos

1. (test-writer) Testes da seção 8 (`@pytest.mark.db`, banco migrado). Confirme falha. Commit `test: add monitoring.metricas tests`.
2. (implementer) `uv run alembic revision -m "monitoring_metricas" --rev-id 0009` (ou o próximo livre).
3. `upgrade`: `monitoring.metricas (modelo text not null, versao_modelo text not null, data date not null, metrica text not null check (metrica ~ '^[a-z][a-z0-9_]*$'), valor double precision not null, primary key (modelo, data, metrica))`.
4. `downgrade`: `DROP TABLE monitoring.metricas`.
5. Permissões pelos privilégios padrão (PR 07): `scorer` escreve, todos leem.
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_monitoring_metricas.py tests/test_migracoes.py` | Todos passam |
| `uv run alembic heads` | `0009 (head)` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: chave e permissões fazem parte do contrato com o painel e com ela.

## 8. Casos de teste

1. Inserir (`media_movel`, `1`, 2026-11-07, `mape`, 3.1) funciona.
2. Mesma (`modelo`, `data`, `metrica`) duas vezes → violação de chave primária.
3. `metrica = 'MAPE %'` → violação de `CHECK`.
4. `valor` nulo → violação.
5. Como `scorer`, `INSERT` e `UPDATE` funcionam; como `ingestor`, `cientista` e `leitura`, só `SELECT`.

## 9. Riscos e perguntas em aberto

- A chave não inclui `versao_modelo` (como no doc): se o champion mudar, a métrica de um dia reflete a versão que fez a previsão avaliada, e uma reexecução pode trocar `versao_modelo`. Aceitável; o log de trocas de champion é dela.

## 10. Decisões que exigem ADR

Coberto pelo ADR "Contrato de dados" se for considerado contrato com a ciência de dados; senão nenhuma.
