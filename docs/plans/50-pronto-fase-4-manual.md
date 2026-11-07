# 50 — Modelo de teste (média móvel) em produção e critério de pronto da Fase 4 (manual / coordenação)

> Executa: **usuário**, com a cientista de dados. Depende de: 46, 47, 48, 49 (merges na `main`, deploy automático) e do ADR "Execução de modelos" aprovado.
> Fase do roadmap: Fase 4 — "Pronto quando: um modelo de teste (média móvel) grava previsões todo dia".

## Por que é manual

O modelo de teste é código do pacote `models` (outro repositório, outra dona) e registrá-lo no MLflow é a ação de deploy de modelo do contrato. Decisão P11: onde vive o modelo de teste. Recomendação: em `models/src/models/moving_average/`, por PR aprovado por ela, porque é exatamente o caminho que os modelos reais vão seguir.

## Checklist

- [ ] Senhas: `POSTGRES_SCORER_PASSWORD` e `POSTGRES_READER_PASSWORD` e `GRAFANA_ADMIN_PASSWORD` no `infra/.env` da VPS; `ALTER ROLE scorer PASSWORD ...` e `ALTER ROLE reader PASSWORD ...` no Postgres (como no item 12). `MODELS_REPO` (repo público, sem token).
- [ ] Na VPS: `infra/scripts/tailscale-serve.sh` (ou o deploy já reaplicou); `tailscale serve status` lista a porta 3000. ACL do Tailscale: acrescentar `tag:platform:3000` para a cientista.
- [ ] Reaplicar o deploy (re-executar o último `deploy.yml` com `gh run rerun <id>` ou um merge trivial) para os serviços lerem o `.env` novo.
- [ ] No repo `models`, PR com `src/models/moving_average/`:
  - `build_features(conn, ref_date)`: lê `raw.ons_daily_load` até `ref_date - 1` e calcula a média dos últimos 7 dias por subsistema.
  - `predict(model, features)`: devolve `key=subsystem`, `target_date=ref_date + 1`, `predicted_value=média` (o `model` é um pyfunc trivial; o contrato exige que exista).
  - `evaluate(predicted, actual)`: MAPE e MAE.
  - `train.py`: registra no MLflow como `moving_average`, com a tag `models_package=<tag git>` na versão.
- [ ] Tag no repo `models` (ex.: `v0.1.0`), `train.py` rodado, alias `champion` na versão.
- [ ] Disparar `score_models/production` à mão na UI do Prefect uma vez.

## Verificação de pronto

| Onde | Comando / ação | Esperado |
| --- | --- | --- |
| UI do Prefect | Última execução de `score_models` | `Completed`, com a task `moving_average` |
| VPS | `... psql -c "select model_name, model_version, count(*), max(generated_at) from predictions.model_predictions group by 1,2"` | `moving_average`, 4 linhas por execução |
| Grafana (`https://<host>.ts.net:3000`, pela tailnet) | Painéis "Dados brutos" e "Previsões" | Mostram dados; "Previsto × real" com as duas séries para dias passados |
| Em 7 dias | `select generated_at::date, count(*) from predictions.model_predictions where model_name='moving_average' group by 1 order by 1` | Uma linha por dia, 4 previsões cada |

- [ ] Prova do deploy de modelo sem a plataforma: ela muda o alias `champion` para outra versão; no dia seguinte, `model_version` nas previsões é a nova, sem PR neste repo.

Memória (mesmos comandos e gatilhos do 28a):

- [ ] Com a stack desta fase no ar, em repouso e durante um job: `free -m`, `docker stats --no-stream`, `vmstat 5 12`, `sudo dmesg -T | grep -i -E 'out of memory|killed process'`. Anote os números.
- [ ] Se um gatilho do 28b disparar (`available` abaixo de ~150 MB, swap em uso constante ou OOM do kernel), faça o 28b antes do próximo PR que acrescenta serviço. Sem gatilho, segue em 1 GB.
