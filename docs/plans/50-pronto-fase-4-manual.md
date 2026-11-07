# 50 — Modelo de teste (média móvel) em produção e critério de pronto da Fase 4 (manual / coordenação)

> Executa: **usuário**, com a cientista de dados. Depende de: 46, 47, 48, 49 (merges na `main`, deploy automático) e do ADR "Execução de modelos" aprovado.
> Fase do roadmap: Fase 4 — "Pronto quando: um modelo de teste (média móvel) grava previsões todo dia".

## Por que é manual

O modelo de teste é código do pacote `modelos` (outro repositório, outra dona) e registrá-lo no MLflow é a ação de deploy de modelo do contrato. Decisão P11: onde vive o modelo de teste. Recomendação: em `modelos/src/modelos/media_movel/`, por PR aprovado por ela, porque é exatamente o caminho que os modelos reais vão seguir.

## Checklist

- [ ] Senhas: `POSTGRES_SCORER_SENHA` e `POSTGRES_LEITURA_SENHA` e `GRAFANA_ADMIN_SENHA` no `infra/.env` da VPS; `ALTER ROLE scorer PASSWORD ...` e `ALTER ROLE leitura PASSWORD ...` no Postgres (como no item 12). `MODELOS_REPO` e, se privado, `MODELOS_GIT_TOKEN` (token só leitura do repo `modelos`).
- [ ] DNS de `grafana.<dominio>`.
- [ ] Reaplicar o deploy (re-executar o último `deploy.yml` com `gh run rerun <id>` ou um merge trivial) para os serviços lerem o `.env` novo.
- [ ] No repo `modelos`, PR com `src/modelos/media_movel/`:
  - `build_features(conn, data_ref)`: lê `raw.ons_carga_diaria` até `data_ref - 1` e calcula a média dos últimos 7 dias por subsistema.
  - `predict(model, features)`: devolve `chave=subsistema`, `data_alvo=data_ref + 1`, `valor_previsto=média` (o `model` é um pyfunc trivial; o contrato exige que exista).
  - `evaluate(previsto, real)`: MAPE e MAE.
  - `train.py`: registra no MLflow como `media_movel`, com a tag `pacote_modelos=<tag git>` na versão.
- [ ] Tag no repo `modelos` (ex.: `v0.1.0`), `train.py` rodado, alias `champion` na versão.
- [ ] Disparar `score_modelos/producao` à mão na UI do Prefect uma vez.

## Verificação de pronto

| Onde | Comando / ação | Esperado |
| --- | --- | --- |
| UI do Prefect | Última execução de `score_modelos` | `Completed`, com a task `media_movel` |
| VPS | `... psql -c "select modelo, versao_modelo, count(*), max(gerado_em) from predictions.previsoes group by 1,2"` | `media_movel`, 4 linhas por execução |
| Grafana (`https://grafana.<dominio>`) | Painéis "Dados brutos" e "Previsões" | Mostram dados; "Previsto × real" com as duas séries para dias passados |
| Em 7 dias | `select gerado_em::date, count(*) from predictions.previsoes where modelo='media_movel' group by 1 order by 1` | Uma linha por dia, 4 previsões cada |

- [ ] Prova do deploy de modelo sem a plataforma: ela muda o alias `champion` para outra versão; no dia seguinte, `versao_modelo` nas previsões é a nova, sem PR neste repo.
