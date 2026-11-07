# ADR 0001: Convenção de nomes em inglês para identificadores de implementação

Status: Aceito
Data: 2026-11-07
Decisores: Maximiliano

## Contexto

Os docs e planos misturam identificadores em português e em inglês (por exemplo, `raw.clima_previsao` ao lado de `build_features`). Ferramentas, bibliotecas e o mercado usam inglês, e código gerado por assistentes tende a seguir o mesmo padrão. Ainda não há código nem tabela, então renomear agora custa só texto.

## Decisão

Identificadores e artefatos de implementação em inglês: código, variáveis, funções, classes, módulos e nomes de arquivo de código, schemas, tabelas, colunas, papéis do Postgres, jobs, flows, deployments, subcomandos e flags de CLI, variáveis de ambiente, serviços, imagens e volumes, painéis, nomes de modelo, branches, comentários de código, mensagens de log e de erro emitidas pelo código, mensagens de commit e títulos e corpos de PR.

A prosa de `docs/` (planos, guias, ADRs) continua em português, assim como os nomes dos arquivos de `docs/`. Mensagens de log e de erro citadas em prosa nos docs ficam em português; no código serão em inglês.

## Regras de formação

- Python: `snake_case` para funções, variáveis, parâmetros e módulos; `PascalCase` para classes e exceções; `UPPER_SNAKE_CASE` para constantes e variáveis de ambiente.
- SQL: `snake_case`. Tabela no plural para coleção de entidades (`locations`, `model_predictions`) e no singular quando for mais natural (`calendar`, `weather_forecast`).
- Colunas: sufixo `_at` para o momento de um evento (`ingested_at`, `generated_at`, `issued_at`), sufixo `_date` para o dia a que o dado se refere (`target_date`, `ref_date`), prefixo `is_` para booleanos, unidade como sufixo (`_mm`, `_mw`, `_days`).
- `kebab-case`: subcomandos e flags de CLI, serviços do compose, imagens, uids de painéis, unidades systemd, branches.
- Nome de modelo: `<alvo>_<horizonte>` em `snake_case` (`load_d1`, `rain_d1`).
- Commits e PR (título e corpo) em inglês. Comentários de código em inglês. Mensagens de log e de erro emitidas pelo código também em inglês.
- Fica como está: nomes de fontes externas, valores de dados, nomes próprios, nomes dos arquivos de `docs/`, placeholders em prosa.
- A prosa de `docs/` (planos, guias, ADRs) continua em português.

## Tabela de nomes

Esta é a tabela português → inglês aplicada aos identificadores de `docs/plataforma-ml.md`, `docs/guia-ciencia-de-dados.md` e `docs/plans/**`.

**A. Já em inglês, sem mudança:** bancos `ml`, `mlflow`, `prefect`; schemas `raw`, `ref`, `features`, `predictions`, `monitoring`; volumes `pgdata`, `mlflow_artifacts`, `grafana_data`; serviços `jobs`, `postgres`, `mlflow`, `prefect-server`, `prefect-worker`, `grafana`; papéis `ingestor` e `scorer`; funções `build_features`, `predict`, `evaluate`, `upsert`; alias `champion`; usuário `deploy`; datasource `ml`.

**B. Tabelas**

| Atual | Novo |
| --- | --- |
| `ref.locais` | `ref.locations` |
| `ref.calendario` | `ref.calendar` |
| `raw.ons_carga_diaria` | `raw.ons_daily_load` |
| `raw.clima_observado` | `raw.weather_observed` |
| `raw.clima_previsao` | `raw.weather_forecast` |
| `predictions.previsoes` | `predictions.model_predictions` |
| `monitoring.metricas` | `monitoring.model_metrics` |
| `features.minha` (tabela de teste, plano 07) | `features.mine` |
| `teste_upsert` (tabela de teste, plano 08) | `upsert_test` |

**C. Colunas**

| Atual | Novo | Atual | Novo |
| --- | --- | --- | --- |
| `local_id` | `location_id` | `emitida_em` | `issued_at` |
| `nome` | `name` | `data_alvo` | `target_date` |
| `lat`, `lon` | sem mudança | `horizonte_dias` | `horizon_days` |
| `subsistema` | `subsystem` | `modelo` | `model_name` |
| `data` | `date` | `versao_modelo` | `model_version` |
| `dia_semana` | `weekday` | `chave` | `key` |
| `feriado_nacional` | `is_national_holiday` | `valor_previsto` | `predicted_value` |
| `nome_feriado` | `holiday_name` | `gerado_em` | `generated_at` |
| `carga_mwmed` | `load_avg_mw` | `metrica` | `metric` |
| `ingerido_em` | `ingested_at` | `valor` | `value` |
| `temp_max`, `temp_min`, `precip_mm` | sem mudança | `valor_real` | `actual_value` |
| `vento_max` | `wind_speed_max` | `atualizado_em` (hipótese do P9) | `updated_at` |
| `umidade_media` | `humidity_mean` | | |

**D. Papéis e usuários do Postgres**

| Atual | Novo |
| --- | --- |
| `cientista` | `scientist` |
| `leitura` | `reader` |
| `plataforma_admin` | `platform_admin` |

**E. Contrato com o repo de modelos (exige aviso à ciência de dados; ver Consequências)**

| Atual | Novo |
| --- | --- |
| repositório e pacote `modelos` (`src/modelos/`, `modelos.<nome>`, `find_spec("modelos")`) | `models` (`src/models/`, `models.<nome>`) |
| repositório `plataforma` (e a raiz `plataforma/` da árvore) | `platform` |
| `carga_d1` | `load_d1` |
| `chuva_d1` | `rain_d1` |
| `media_movel` (modelo de teste) | `moving_average` |
| `build_features(conn, data_ref: date)` | `build_features(conn, ref_date: date)` |
| saída de `predict`: `chave`, `data_alvo`, `valor_previsto` | `key`, `target_date`, `predicted_value` |
| `evaluate(previsto, real)` | `evaluate(predicted, actual)` |
| `carregar_real(conn, data_alvo)` (proposta P14), saída `chave, data_alvo, valor_real` | `load_actuals(conn, target_date)`, saída `key, target_date, actual_value` |
| tag MLflow `pacote_modelos` (proposta P12) | `models_package` |
| `train.py`, `features.py`, `predict.py`, `evaluate.py`, `models:/<nome>@champion` | sem mudança |

**F. Jobs, flows e deployments**

| Atual | Novo |
| --- | --- |
| `ingest_clima_previsao` | `ingest_weather_forecast` |
| `ingest_clima_observado` | `ingest_weather_observed` |
| `ingest_ons_carga` | `ingest_ons_load` |
| `score_modelos` | `score_models` |
| `monitorar_modelos` | `monitor_models` |
| `vigiar_saude` | `watch_health` |
| `flows.score_um` / `flows/score_um.py` | `flows.score_one` / `flows/score_one.py` |
| `flows.monitor_um` / `flows/monitor_um.py` | `flows.monitor_one` / `flows/monitor_one.py` |
| deployment `producao` | `production` |
| `POOL = "plataforma"` | `POOL = "platform"` |
| `FUSO` | `TIMEZONE` |
| `registrar()` | `register()` |
| `score_flow`, `monitor_flow`, `DEPLOYMENTS` | sem mudança |

**G. CLI (`python -m ingestion <subcomando>`)**

| Atual | Novo |
| --- | --- |
| `clima-previsao` | `weather-forecast` |
| `clima-observado` | `weather-observed` |
| `ons-carga` | `ons-load` |
| `calendario` | `calendar` |
| `criar-bancos` | `create-databases` |
| `--inicio`, `--fim`, `--dias`, `--hoje` | `--start`, `--end`, `--days`, `--today` |
| `--modelo`, `--versao`, `--data`, `--gerado-em` | `--model`, `--version`, `--date`, `--generated-at` |
| `SUBCOMANDOS`, `Subcomando`, `executar(args)` | `SUBCOMMANDS`, `Subcommand`, `run(args)` |
| `main(["nao-existe"])` | `main(["does-not-exist"])` |

**H. Funções, classes, constantes e parâmetros**

| Atual | Novo | Atual | Novo |
| --- | --- | --- | --- |
| `criar_engine` | `build_engine` | `ConfiguracaoAusente` | `MissingConfiguration` |
| `ao_conflitar` | `on_conflict` | `"atualizar"` / `"ignorar"` | `"update"` / `"ignore"` |
| `carimbar_ingerido_em` | `stamp_ingested_at` | `tabela`, `linhas`, `chaves` | `table`, `rows`, `keys` |
| `obter_json`, `obter_bytes` | `fetch_json`, `fetch_bytes` | `tentativas`, `espera_base` | `attempts`, `base_delay` |
| `ErroDeRede` | `NetworkError` | `class Local` | `class Location` |
| `buscar_previsao` | `fetch_forecast` | `buscar_observado` | `fetch_observed` |
| `URL_PREVISAO` | `FORECAST_URL` | `URL_ARQUIVO` | `ARCHIVE_URL` |
| `listar_locais` | `list_locations` | `locais` (variável) | `locations` |
| `checar` | `check` | `ChecagemFalhou` | `CheckFailed` |
| `linhas_esperadas` | `expected_rows` | `SCHEMA_CLIMA_PREVISAO` | `SCHEMA_WEATHER_FORECAST` |
| `SCHEMA_CLIMA_OBSERVADO` | `SCHEMA_WEATHER_OBSERVED` | `SCHEMA_ONS_CARGA` | `SCHEMA_ONS_LOAD` |
| `SCHEMA_CALENDARIO` | `SCHEMA_CALENDAR` | `SCHEMA_SAIDA_PREDICT` | `SCHEMA_PREDICT_OUTPUT` |
| `montar_calendario` | `build_calendar` | `carregar_calendario` | `load_calendar` |
| `url_arquivo` | `file_url` | `normalizar_carga` | `normalize_load` |
| `baixar_carga` | `download_load` | `MAPA_COLUNAS` | `COLUMN_MAP` |
| `conteudo`, `ano` | `content`, `year` | `checar_continuidade_ons` | `check_ons_continuity` |
| `checar_continuidade_clima` | `check_weather_continuity` | `atraso_max_dias` | `max_delay_days` |
| `garantir_banco` | `ensure_database` | `url_admin`, `senha` | `admin_url`, `password` |
| `janela_padrao` | `default_window` | `hoje`, `inicio`, `fim`, `dias` | `today`, `start`, `end`, `days` |
| `listar_champions` | `list_champions` | `TAG_PACOTE` | `PACKAGE_TAG` |
| `Champion(nome, versao, uri, pacote_versao)` | `Champion(name, version, uri, package_version)` | `pacote_versao` | `package_version` |
| `gerar_previsoes` | `generate_predictions` | `SaidaInvalida` | `InvalidOutput` |
| `nome`, `versao`, `modulo`, `agora` (parâmetros) | `name`, `version`, `module`, `now` | `modelo` (parâmetro Python) | `model` |
| `saida` (variável) | `output` | `classe` (coluna extra de teste) | `label` |
| `especificacao_pacote` | `package_spec` | `montar_comando` | `build_command` |
| `modulo_python` | `python_module` | `env_extra` | `extra_env` |
| `executar(comando, *, env_extra)` | `run(command, *, extra_env)` | `ExecucaoFalhou` | `RunFailed` |
| `ultimas_linhas_stderr` | `stderr_tail` | `pontuar_modelo` | `score_model` |
| `ultimo_lote` | `latest_batch` | `avaliar_dia` | `evaluate_day` |
| `obter_real` | `get_actuals` | `RealIndisponivel` | `ActualsUnavailable` |
| `MetricasInvalidas` | `InvalidMetrics` | `avaliar_modelo` | `evaluate_model` |
| `previsto`, `real` (variáveis, séries de painel) | `predicted`, `actual` | `enviar_telegram` | `send_telegram` |
| `ao_falhar` | `notify_failure` | `texto`, `cliente` | `text`, `client` |
| `checar_disco` | `check_disk` | `checar_servicos` | `check_services` |
| `caminho`, `limite`, `alvos` | `path`, `threshold`, `targets` | `local` (parâmetro) | `location` |
| `inexistente` (coluna de teste) | `nonexistent` | `teste` (modelo de teste nos painéis) | `test` |
| `disco` (texto de alerta citado em teste) | `disk` | | |

**I. Variáveis de ambiente**

| Atual | Novo |
| --- | --- |
| `POSTGRES_ADMIN_USUARIO`, `POSTGRES_ADMIN_SENHA` | `POSTGRES_ADMIN_USER`, `POSTGRES_ADMIN_PASSWORD` |
| `POSTGRES_INGESTOR_SENHA`, `POSTGRES_SCORER_SENHA`, `POSTGRES_LEITURA_SENHA` | `POSTGRES_INGESTOR_PASSWORD`, `POSTGRES_SCORER_PASSWORD`, `POSTGRES_READER_PASSWORD` |
| `MLFLOW_DB_SENHA`, `PREFECT_DB_SENHA`, `GRAFANA_ADMIN_SENHA` | `MLFLOW_DB_PASSWORD`, `PREFECT_DB_PASSWORD`, `GRAFANA_ADMIN_PASSWORD` |
| `SAUDE_BIND_IP` | `HEALTH_BIND_IP` |
| `GHCR_DONO`, `IMAGEM_TAG` | `GHCR_OWNER`, `IMAGE_TAG` |
| `PLATAFORMA_DIR` | `PLATFORM_DIR` |
| `RCLONE_DESTINO`, `BACKUP_RETENCAO_DIAS`, `BACKUP_BANCOS` | `RCLONE_DESTINATION`, `BACKUP_RETENTION_DAYS`, `BACKUP_DATABASES` |
| `MODELOS_REPO`, `MODELOS_FONTE_LOCAL` | `MODELS_REPO`, `MODELS_LOCAL_SOURCE` |
| demais (`DATABASE_URL*`, `POSTGRES_BIND_IP`, `POSTGRES_DEV_PASSWORD`, `TS_*`, `PREFECT_*`, `MLFLOW_TRACKING_URI`, `TELEGRAM_*`, `GF_*`, `VPS_*`, `UV_CACHE_DIR`, `BUCKET_URL`) | sem mudança |

**J. Infra, CI e painéis**

| Atual | Novo |
| --- | --- |
| serviço `saude`, `infra/saude/saude`, rota `/saude`, container `plataforma-saude-1` | `health`, `infra/health/health`, `/health`, `platform-health-1` |
| serviço `agendador` | `scheduler` |
| imagens `plataforma-jobs`, `plataforma-mlflow` | `platform-jobs`, `platform-mlflow` |
| `/opt/plataforma` | `/opt/platform` |
| tag Tailscale `tag:plataforma` | `tag:platform` |
| `plataforma-backup.service`, `plataforma-backup.timer`, `plataforma-backup-falhou.service` | `platform-backup.service`, `platform-backup.timer`, `platform-backup-failed.service` |
| `artefatos.tgz` | `artifacts.tgz` |
| painel `dados-brutos` / `dados-brutos.json` | `raw-data` / `raw-data.json` |
| painel `previsoes` / `previsoes.json` | `predictions` / `predictions.json` |
| painel `erro-modelos` / `erro-modelos.json` | `model-error` / `model-error.json` |
| `infra/grafana/provisioning/dashboards/plataforma.yaml` | `infra/grafana/provisioning/dashboards/platform.yaml` |
| environment do GitHub `producao` | `production` |
| job de CI `lint-e-testes`; job do deploy `imagens` | `lint-and-test`; `images` |
| `infra/cron/crontab`, `infra/jobs/`, `infra/mlflow/`, `infra/backup/`, `infra/systemd/`, `ml.yaml`, `deploy_ci` | sem mudança |

**K. Arquivos Python, migrações, testes e fixtures**

| Atual | Novo | Atual | Novo |
| --- | --- | --- | --- |
| `ingestion/calendario.py` | `ingestion/calendar_ref.py` | `flows/ingestao.py` | `flows/ingest.py` |
| `flows/registro.py` | `flows/registry.py` | `flows/alertas.py` | `flows/alerts.py` |
| `flows/vigia.py` | `flows/watchdog.py` | `0002_papeis.py` | `0002_roles.py` |
| `0003_ref_locais.py` | `0003_ref_locations.py` | `0004_raw_clima_previsao.py` | `0004_raw_weather_forecast.py` |
| `0005_ref_calendario.py` | `0005_ref_calendar.py` | `0006_raw_ons_carga_diaria.py` | `0006_raw_ons_daily_load.py` |
| `0007_raw_clima_observado.py` | `0007_raw_weather_observed.py` | `0008_predictions_previsoes.py` | `0008_predictions_model_predictions.py` |
| `0009_monitoring_metricas.py` | `0009_monitoring_model_metrics.py` | `test_migracoes` | `test_migrations` |
| `test_permissoes` | `test_permissions` | `test_ref_locais` | `test_ref_locations` |
| `test_raw_clima_previsao` | `test_raw_weather_forecast` | `test_checks_clima_previsao` | `test_checks_weather_forecast` |
| `test_job_clima_previsao` | `test_job_weather_forecast` | `test_openmeteo_previsao` | `test_openmeteo_forecast` |
| `test_openmeteo_observado` | `test_openmeteo_observed` | `test_calendario` | `test_calendar` |
| `test_ons_leitura` | `test_ons_reader` | `test_raw_ons_carga_diaria` | `test_raw_ons_daily_load` |
| `test_job_ons_carga` | `test_job_ons_load` | `test_raw_clima_observado` | `test_raw_weather_observed` |
| `test_job_clima_observado` | `test_job_weather_observed` | `test_admin_bancos` | `test_admin_databases` |
| `test_flows_ingestao` | `test_flows_ingest` | `test_predictions_previsoes` | `test_predictions_model_predictions` |
| `test_score_nucleo` | `test_score_core` | `test_registro_champions` | `test_registry_champions` |
| `test_score_um` | `test_score_one` | `test_monitoring_metricas` | `test_monitoring_model_metrics` |
| `test_monitor_nucleo` | `test_monitor_core` | `test_monitor_um` | `test_monitor_one` |
| `test_alertas` | `test_alerts` | `test_vigia` | `test_watchdog` |
| `test_paineis_sql` | `test_dashboards_sql` | `nome_do_teste` | `test_name` |
| `openmeteo_previsao_sao_paulo.json` | `openmeteo_forecast_sao_paulo.json` | `openmeteo_arquivo_sao_paulo.json` | `openmeteo_archive_sao_paulo.json` |
| `modelos_fake` (`tests/fixtures/modelos_fake/src/modelos/teste_fake/`) | `fake_models` (`tests/fixtures/fake_models/src/models/fake_model/`) | `teste_fake` | `fake_model` |
| fixture `banco_teste` | `temp_database_url` | `novo_banco`, `banco_migrado` | `fresh_database`, `migrated_database` |
| `nao_existe` | `does_not_exist` | `raw_clima_previsao`, `raw_clima_observado`, `raw_ons_carga_diaria`, `ref_locais`, `predictions_previsoes`, `monitoring_metricas` (fragmentos em nomes) | `raw_weather_forecast`, `raw_weather_observed`, `raw_ons_daily_load`, `ref_locations`, `predictions_model_predictions`, `monitoring_model_metrics` |

Sem mudança: `test_smoke`, `test_db`, `test_http`, `test_cli`, `test_compose`, `test_crontab`, `test_deployments`, `test_executor`, `test_flow_score`, `test_flow_monitor`, `test_deploy_sh`, `test_backup_restore`, `test_grafana_provisioning`, `test_tailscale_serve`, `test_upsert`, `ingestion/db.py`, `ingestion/http.py`, `ingestion/ons.py`, `ingestion/openmeteo.py`, `ingestion/checks.py`, `ingestion/jobs.py`, `ingestion/cli.py`, `ingestion/admin.py`, `flows/score.py`, `flows/monitor.py`, `flows/executor.py`, `flows/deployments.py`, `flows/score_flow.py`, `flows/monitor_flow.py`.

**L. Branches sugeridas nos planos (cabeçalho "Branch sugerida")**

| Atual | Novo | Atual | Novo |
| --- | --- | --- | --- |
| `feat/db-conexao` | `feat/db-connection` | `feat/db-papeis` | `feat/db-roles` |
| `feat/compose-rede-tailscale` | `feat/compose-tailscale-network` | `feat/ref-locais` | `feat/ref-locations` |
| `feat/imagem-jobs` | `feat/jobs-image` | `feat/raw-clima-previsao` | `feat/raw-weather-forecast` |
| `feat/openmeteo-previsao` | `feat/openmeteo-forecast` | `feat/job-clima-previsao` | `feat/job-weather-forecast` |
| `feat/agendador-interino` | `feat/interim-scheduler` | `feat/ref-calendario` | `feat/ref-calendar` |
| `feat/ons-leitura` | `feat/ons-reader` | `feat/raw-ons-carga` | `feat/raw-ons-load` |
| `feat/job-ons-carga` | `feat/job-ons-load` | `feat/openmeteo-observado` | `feat/openmeteo-observed` |
| `feat/raw-clima-observado` | `feat/raw-weather-observed` | `feat/job-clima-observado` | `feat/job-weather-observed` |
| `feat/bancos-mlflow-prefect` | `feat/mlflow-prefect-databases` | `feat/flows-ingestao` | `feat/flows-ingest` |
| `chore/remover-supercronic` | `chore/remove-supercronic` | `ci/publicar-imagens` | `ci/publish-images` |
| `feat/predictions-previsoes` | `feat/predictions-table` | `feat/score-nucleo` | `feat/score-core` |
| `feat/executor-modelos` | `feat/model-executor` | `feat/score-um` | `feat/score-one` |
| `feat/painel-dados-brutos` | `feat/dashboard-raw-data` | `feat/painel-previsoes` | `feat/dashboard-predictions` |
| `feat/monitoring-metricas` | `feat/monitoring-metrics` | `feat/monitor-nucleo` | `feat/monitor-core` |
| `feat/monitor-um` | `feat/monitor-one` | `feat/alertas-telegram` | `feat/telegram-alerts` |
| `feat/vigia-saude` | `feat/health-watchdog` | `feat/painel-erro` | `feat/dashboard-model-error` |

As demais branches dos planos já estão em inglês (`chore/bootstrap-dev-env`, `feat/compose-postgres`, `feat/db-upsert`, `feat/alembic-schemas`, `feat/compose-mlflow`, `feat/compose-prefect`, `feat/prefect-deployments`, `feat/compose-prefect-worker`, `ci/deploy-ssh`, `feat/score-champions`, `feat/flow-score`, `feat/compose-grafana`, `feat/flow-monitor`, `feat/backup-restore`).

**M. Mantidos de propósito (não renomear):** os nomes externos do ONS e do Open-Meteo listados na seção 2; `America/Sao_Paulo`; ids das cidades; códigos de subsistema; `mape`, `mae`; `ml_test_`, `ml_ci`; caminhos de arquivo em `docs/` (`docs/plataforma-ml.md`, `plataforma-ml.md`, `docs/guia-ciencia-de-dados.md`, `00-indice.md`, `.claude/rules/migrations-e-dados.md`); placeholders em prosa.

## Consequências

- Mudam os nomes de `raw` e `ref` e a assinatura do contrato (`build_features`, saída de `predict`, `evaluate`), e este ADR cobre essas mudanças. Como ainda não há tabela nem código, não há migração Alembic a fazer. A ciência de dados precisa ser avisada (`AGENTS.md`, "Fronteira"), em especial sobre os nomes de modelo (`load_d1`, `rain_d1`) e o pacote `models`.
- `.claude/` (regras e agentes) ainda cita nomes antigos (`ingerido_em`, `cientista`, `leitura`, `raw.clima_previsao`, `emitida_em`) até uma tarefa própria de alinhamento; as linhas do `AGENTS.md` que citavam `plataforma`, `modelos` e `ingerido_em` foram atualizadas neste mesmo PR.
- Os nomes de arquivo de `docs/` continuam em português.
- A semântica das perguntas P8, P9, P12, P14 e P18 do índice (`docs/plans/00-indice.md`) não muda: só os nomes.
- Os ADRs previstos no índice devem usar os nomes novos quando forem escritos.

## Alternativas consideradas

- Manter tudo em português: rejeitada, por atrito com bibliotecas, mercado e código gerado.
- Misto, com o contrato em inglês e o resto em português: rejeitada, por ser uma regra difícil de aplicar e de revisar.
