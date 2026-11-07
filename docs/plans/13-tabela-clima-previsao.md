# 13 — Tabela `raw.clima_previsao`

> Executa: agente. Depende de: 09. Branch sugerida: `feat/raw-clima-previsao`.
> Pré-requisitos: ADR "Contrato de dados v1" (PR 09) aprovado, com a decisão P8 (semântica de `emitida_em`) registrada.
> **Antecipado**: item da Fase 2 feito antes do fim da Fase 1, porque cada dia sem coleta é histórico perdido (decisão P5 no índice).
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar por migração a tabela de snapshots de previsão do tempo, um registro por local, data de emissão e data-alvo.
É a tabela mais urgente da plataforma: o histórico dela só começa no dia em que a coleta ligar.

## 2. Fora do escopo

- Cliente HTTP (PR 14) e job (PR 15).
- `raw.clima_observado` (PR 25).
- Backfill de previsões passadas (o doc exclui; ver P10 no índice).

## 3. Fase do roadmap

Fase 2 — Clima: "`raw.clima_previsao` coletando todo dia (prioridade)".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `migrations/versions/0004_raw_clima_previsao.py` | Cria a tabela; `downgrade` a remove |
| `tests/test_raw_clima_previsao.py` | Testes (test-writer) |

Modelo de dados (`docs/plataforma-ml.md`):

| Tabela | Colunas principais | Chave | Escreve | Lê |
| --- | --- | --- | --- | --- |
| `raw.clima_previsao` | `local_id`, `emitida_em`, `data_alvo`, `horizonte_dias`, mesmas variáveis (`temp_max`, `temp_min`, `precip_mm`, `vento_max`, `umidade_media`), `ingerido_em` | (`local_id`, `emitida_em`, `data_alvo`) | Plataforma | Todos |

Por que existe (do doc): "O modelo de carga só pode usar, no dia D, a previsão disponível em D — usar o clima observado de D+1 seria vazamento de dados."

## 5. Passos

1. (test-writer) Escreva `tests/test_raw_clima_previsao.py` (`@pytest.mark.db`, banco migrado) com os casos da seção 8. Confirme falha porque a tabela não existe. Commit `test: add raw.clima_previsao tests`.
2. (implementer) `uv run alembic revision -m "raw_clima_previsao" --rev-id 0004`.
3. `upgrade`, tabela `raw.clima_previsao`:
   - `local_id text not null references ref.locais(local_id)`
   - `emitida_em date not null` (dia, no fuso `America/Sao_Paulo`, em que o snapshot foi tirado; ver P8)
   - `data_alvo date not null`
   - `horizonte_dias smallint generated always as (data_alvo - emitida_em) stored`, com `check (horizonte_dias between 0 and 16)`
   - `temp_max`, `temp_min`, `precip_mm`, `vento_max`, `umidade_media`: `double precision`, aceitam nulo (a fonte pode não ter a variável; a checagem do PR 15 decide)
   - `ingerido_em timestamptz not null`
   - `primary key (local_id, emitida_em, data_alvo)`
   - Comentário na tabela (`COMMENT ON TABLE`): "Previsão como emitida. Nunca sobrescrever um snapshot antigo."
4. `downgrade`: `DROP TABLE raw.clima_previsao`.
5. Permissões vêm dos privilégios padrão (PR 07). Não repetir `GRANT`.
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_raw_clima_previsao.py tests/test_migracoes.py` | Todos passam |
| `uv run alembic heads` | `0004 (head)` |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem erro |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: chave, coluna gerada e restrições definem o contrato que a cientista vai consultar; erro aqui é caro de corrigir depois que o histórico começa.

## 8. Casos de teste

1. Inserir (`sao_paulo`, emitida `2026-11-07`, alvo `2026-11-10`) → `horizonte_dias` = 3.
2. Inserir a mesma chave duas vezes (sem `ON CONFLICT`) → violação de chave primária.
3. Mesmo `local_id` e `data_alvo` com `emitida_em` diferentes → duas linhas coexistem (snapshots distintos).
4. `local_id = 'nao_existe'` → violação de chave estrangeira.
5. `data_alvo` anterior a `emitida_em` → violação de `CHECK`.
6. `data_alvo` 17 dias depois de `emitida_em` → violação de `CHECK`.
7. Tentar informar `horizonte_dias` no `INSERT` → erro (coluna gerada).
8. Como `ingestor`, `INSERT` funciona; como `leitura` e `cientista`, só `SELECT`.
9. `downgrade` até `0003` remove a tabela; `ref.locais` continua.

## 9. Riscos e perguntas em aberto

- P8: `emitida_em` como `date` segue o doc ("`emitida_em` = hoje"). Alternativa: `timestamptz` com a hora da coleta, que permitiria mais de um snapshot por dia. Com `date`, uma segunda execução no mesmo dia não cria snapshot novo (o PR 15 usa `ignorar` no conflito e preserva o primeiro). Decidir antes do merge; mudar depois exige migração de contrato.
- Coluna gerada é proposta deste plano: garante que `horizonte_dias` nunca fique inconsistente. O job do PR 15 não envia essa coluna.

## 10. Decisões que exigem ADR

Coberto pelo ADR "Contrato de dados v1" (PR 09), que deve registrar P8.
