# 53 — Ponto de entrada `python -m flows.monitor_one` e a fonte do real

> Executa: agente. Depende de: 52, 44, 45. Branch sugerida: `feat/monitor-one`.
> Pré-requisito: ADR "Fonte do real no monitoramento" aprovado com a cientista (seção 10). **Este PR não começa sem ele.**
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar o módulo que roda dentro do ambiente isolado (PR 44) e, para um modelo, avalia os últimos N dias de data-alvo com `evaluate_day` (PR 52), obtendo o real pela função `load_actuals` do módulo dela (opção recomendada no ADR).
Dias cujo real ainda não chegou são pulados sem erro; reavaliar dias recentes cobre revisões do real.

## 2. Fora do escopo

- Flow e agenda (PR 54).

## 3. Fase do roadmap

Fase 5 — "Job de monitoramento + `monitoring.model_metrics`".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `flows/monitor_one.py` | `main(argv) -> int` |
| `tests/fixtures/fake_models/src/models/fake_model/__init__.py` | Acrescentar `load_actuals` e `evaluate` (test-writer) |
| `tests/test_monitor_one.py` | Teste de ponta a ponta com executor, banco e módulo falso (test-writer) |

O contrato do doc tem três funções; ele não diz de onde vem o `real`. Opção recomendada para o ADR (P14): uma quarta função **opcional por modelo**, no módulo dela:

```python
def load_actuals(conn, target_date: date) -> pd.DataFrame: ...
    # colunas: chave, target_date, actual_value; vazio se o real ainda não chegou
```

Por quê: só ela sabe o que é o real de cada modelo (carga do ONS para `load_d1`, `precip_mm >= 1` do observado para `rain_d1`), e assim a plataforma continua sem PR por modelo novo. Alternativa: um mapa na plataforma (modelo → consulta SQL), que exige PR aqui a cada tipo de modelo novo. **Se o ADR escolher a alternativa, este plano precisa ser refeito pelo task-planner antes de implementar.**

Código existente: `flows/monitor.py` (`evaluate_day`, `ActualsUnavailable`, `InvalidMetrics`), `flows/executor.py`, `flows/score_one.py` (mesmo padrão de argumentos e variáveis de ambiente), `ingestion/db.py` (`build_engine`).

## 5. Passos

1. (test-writer) Acrescente ao pacote falso `load_actuals(conn, target_date)` (lê de uma tabela de teste ou devolve vazio para datas recentes) e `evaluate` (MAE simples). Escreva os testes da seção 8, via `executar(build_command(...))` com `MODELS_LOCAL_SOURCE`. Confirme falha. Commit `test: add single-model monitor entrypoint tests`.
2. (implementer) `flows/monitor_one.py`:
   - Argumentos: `--model NOME --today AAAA-MM-DD [--days 14]`. Variável `DATABASE_URL_SCORER` obrigatória (código 2 sem ela).
   - `modulo = importlib.import_module(f"modelos.{nome}")`; sem `load_actuals` → mensagem "modelo <nome> não define load_actuals" e código 1.
   - Para cada `target_date` de `hoje - dias` até `hoje - 1`, numa transação própria: `evaluate_day(conn, nome=..., modulo=modulo, target_date=d, get_actuals=modulo.load_actuals)`; `ActualsUnavailable` → registra "real de <d> ainda não chegou" e segue; outras exceções sobem.
   - Imprime um resumo (`dias avaliados: N, sem real: M`) e devolve 0.
3. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_monitor_one.py` | Todos passam |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: a janela de reavaliação e o "real ainda não chegou não é erro" decidem se o painel tem buracos ou alarmes falsos.

## 8. Casos de teste

1. Previsões de `fake_model` para os últimos 14 dias e real para os 10 mais antigos → métricas gravadas para 10 dias; saída contém `sem real: 4`; código 0 (via executor, sem `RunFailed`).
2. Rodar de novo com o real de um dia alterado → a métrica desse dia muda; nenhum dia duplicado.
3. Módulo sem `load_actuals` → `RunFailed` contendo `load_actuals`.
4. `evaluate` falhando num dia → `RunFailed` com o traceback dela; os dias já avaliados antes dele ficam gravados (transação por dia).
5. Sem `DATABASE_URL_SCORER` → código 2.

## 9. Riscos e perguntas em aberto

- `--days 14` cobre o atraso do ERA5 (real do `rain_d1`) e as revisões do ONS dentro de duas semanas; ajustar com o item 18.

## 10. Decisões que exigem ADR

- ADR "Fonte do real no monitoramento" (P14): `load_actuals` no módulo dela (recomendado) ou mapa na plataforma; formato `chave, target_date, actual_value`. É mudança de contrato (`AGENTS.md`: assinatura das funções só muda por ADR) e precisa da concordância dela.
