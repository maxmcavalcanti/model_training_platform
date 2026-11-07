# ADR 0001: convenção de nomes em inglês + renomeação dos identificadores nos docs

> Executa: agente (`task-implementer`). Depende de: nada. Branch sugerida: `docs/english-naming-convention`.
> Testes necessários: não (só documentação). Revisão: `code-reviewer` e `pr-reviewer` obrigatórios, porque o PR toca `AGENTS.md` (fora de `docs/**`).
> **Exceção registrada por instrução expressa do usuário (2026-11-07):** neste PR o `task-implementer` escreve o ADR `docs/adr/0001-english-naming-convention.md`, ao contrário da regra do `AGENTS.md` ("Nenhum agente escreve ADR"). A exceção vale só para este ADR. Também por decisão do usuário, o ADR e as renomeações saem no mesmo PR: as renomeações mexem só em documentação, não em código.

## 1. Objetivo

Registrar em ADR que todo identificador e artefato de implementação é em inglês (a prosa dos docs continua em português), com a tabela completa português → inglês.
Aplicar a tabela aos identificadores de `docs/plataforma-ml.md`, `docs/guia-ciencia-de-dados.md` e `docs/plans/**`, e registrar a regra no `AGENTS.md`.

## 2. Fora do escopo

- Traduzir prosa: títulos, frases, comentários em prosa, mensagens entre aspas, placeholders (`<nome>`, `<host>`, `AAAA-MM-DD`, `NOME`). Só os identificadores mudam.
- Renomear arquivos de documentação: `docs/plataforma-ml.md`, `docs/guia-ciencia-de-dados.md`, `docs/plans/NN-*.md`, `.claude/rules/migrations-e-dados.md`. Referências a esses caminhos **não** mudam (ver Q19).
- Qualquer arquivo em `.claude/` (regras e agentes ainda citam `ingerido_em`, `cientista`, `leitura`, `raw.clima_previsao`, `emitida_em`; ver Q20).
- Outras linhas do `AGENTS.md` além da regra nova (as linhas 3, 7 e 20 citam `plataforma`, `modelos` e `ingerido_em`; ver Q21).
- Decidir perguntas de contrato já abertas no índice (P8 tipo de `emitida_em`, P9 semântica de `ingerido_em`, P12 esquema de tags, P14 fonte do real, P18 formato de `local_id`). Este PR só troca o nome; a semântica e a recomendação de cada P continuam iguais.
- Mudar valores de dados (ids das cidades `sao_paulo`, `porto_alegre`, `recife`, `belem`; códigos de subsistema `SE/CO`, `S`, `NE`, `N`; métricas `mape`, `mae`).
- Mudar nomes de fontes externas: ONS (`ons-aws-prod-opendata`, `dataset/carga_energia_di/`, `CARGA_ENERGIA_<ANO>.parquet`, `id_subsistema`, `din_instante`, `val_cargaenergiamwmed`), Open-Meteo (`temperature_2m_max`, `forecast_days`, `start_date` etc.), `America/Sao_Paulo`.
- Escrever os outros ADRs listados em `docs/plans/00-indice.md` ou renumerá-los.
- Criar código, migração, teste ou script versionado.

## 3. Fase do roadmap

Nenhuma fase específica de `docs/plataforma-ml.md`: é uma convenção transversal, pré-requisito anterior ao item 01 (Fase 0). Não adianta itens de fases futuras: só troca nomes no texto dos planos que já existem, sem implementar nada deles.

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `docs/adr/0001-english-naming-convention.md` | Criar o ADR (nome do arquivo em inglês, prosa em português), com a regra, as convenções de formação e a tabela completa da seção 4.2 |
| `AGENTS.md` | Acrescentar a regra na seção "Regras de código" (texto exato no passo 9) |
| `docs/plataforma-ml.md` | Renomear identificadores (tabelas, colunas, papéis, jobs, árvore de pastas, bloco do contrato) |
| `docs/guia-ciencia-de-dados.md` | Renomear identificadores (`carga_d1`, `chuva_d1`, `carga_mwmed`, `src/modelos/`, `predictions.previsoes` etc.). O `AGENTS.md` diz que este guia é "não para editar"; o usuário autorizou expressamente a edição nesta tarefa, só de identificadores |
| `docs/plans/00-indice.md` … `docs/plans/59-*.md` (os 62 planos existentes, incluindo 28a e 28b) | Renomear identificadores |

Não alterar: este plano (`docs/plans/2026-11-07-english-naming-convention.md`, que é a fonte da tabela e precisa manter os nomes antigos), `docs/plans/.gitkeep`, `docs/adr/.gitkeep`, nada em `.claude/`, `CLAUDE.md`.

Não existe template nem a skill `generate-adr` no repo (`.claude/` só tem `agents/`, `rules/` e `settings.json`), e `docs/adr/` está vazio. O formato do ADR está no passo 2.

### 4.1 Convenções de formação (copiar para o ADR)

- Python: `snake_case` para funções, variáveis, parâmetros e módulos; `PascalCase` para classes e exceções; `UPPER_SNAKE_CASE` para constantes e variáveis de ambiente.
- SQL: `snake_case`. Tabela no plural para coleção de entidades (`locations`, `model_predictions`) e no singular quando for mais natural (`calendar`, `weather_forecast`).
- Colunas: sufixo `_at` para o momento de um evento (`ingested_at`, `generated_at`, `issued_at`), sufixo `_date` para o dia a que o dado se refere (`target_date`, `ref_date`), prefixo `is_` para booleanos, unidade como sufixo (`_mm`, `_mw`, `_days`).
- `kebab-case`: subcomandos e flags de CLI, serviços do compose, imagens, uids de painéis, unidades systemd, branches.
- Nome de modelo: `<alvo>_<horizonte>` em `snake_case` (`load_d1`, `rain_d1`).
- Commits e PR (título e corpo) em inglês. Comentários de código em inglês.
- Fica como está: nomes de fontes externas, valores de dados, nomes próprios, nomes dos arquivos de `docs/`, placeholders em prosa.
- A prosa de `docs/` (planos, guias, ADRs) continua em português.

### 4.2 Tabela português → inglês (proposta; a aprovação deste plano aprova a tabela)

Itens marcados com (Qn) têm alternativa registrada na seção 9. Se o usuário responder diferente, ele (ou o planner) edita esta tabela antes de passar ao implementer; o implementer usa a tabela como estiver escrita.

**A. Já em inglês, sem mudança:** bancos `ml`, `mlflow`, `prefect`; schemas `raw`, `ref`, `features`, `predictions`, `monitoring`; volumes `pgdata`, `mlflow_artifacts`, `grafana_data`; serviços `jobs`, `postgres`, `mlflow`, `prefect-server`, `prefect-worker`, `grafana`; papéis `ingestor` e `scorer`; funções `build_features`, `predict`, `evaluate`, `upsert`; alias `champion`; usuário `deploy`; datasource `ml`.

**B. Tabelas**

| Atual | Novo |
| --- | --- |
| `ref.locais` | `ref.locations` |
| `ref.calendario` | `ref.calendar` |
| `raw.ons_carga_diaria` | `raw.ons_daily_load` |
| `raw.clima_observado` | `raw.weather_observed` |
| `raw.clima_previsao` | `raw.weather_forecast` |
| `predictions.previsoes` | `predictions.model_predictions` (Q1) |
| `monitoring.metricas` | `monitoring.model_metrics` (Q1) |
| `features.minha` (tabela de teste, plano 07) | `features.mine` |
| `teste_upsert` (tabela de teste, plano 08) | `upsert_test` |

**C. Colunas**

| Atual | Novo | Atual | Novo |
| --- | --- | --- | --- |
| `local_id` | `location_id` | `emitida_em` | `issued_at` (Q4) |
| `nome` | `name` | `data_alvo` | `target_date` |
| `lat`, `lon` | sem mudança | `horizonte_dias` | `horizon_days` |
| `subsistema` | `subsystem` | `modelo` | `model_name` (Q6) |
| `data` | `date` (Q3) | `versao_modelo` | `model_version` |
| `dia_semana` | `weekday` | `chave` | `key` (Q2) |
| `feriado_nacional` | `is_national_holiday` (Q17) | `valor_previsto` | `predicted_value` |
| `nome_feriado` | `holiday_name` | `gerado_em` | `generated_at` |
| `carga_mwmed` | `load_avg_mw` (Q5) | `metrica` | `metric` |
| `ingerido_em` | `ingested_at` | `valor` | `value` |
| `temp_max`, `temp_min`, `precip_mm` | sem mudança | `valor_real` | `actual_value` |
| `vento_max` | `wind_speed_max` | `atualizado_em` (hipótese do P9) | `updated_at` |
| `umidade_media` | `humidity_mean` | | |

**D. Papéis e usuários do Postgres**

| Atual | Novo |
| --- | --- |
| `cientista` | `scientist` (Q14) |
| `leitura` | `reader` (Q14) |
| `plataforma_admin` | `platform_admin` (Q10) |

**E. Contrato com o repo de modelos (exige aviso à ciência de dados; ver seção 10)**

| Atual | Novo |
| --- | --- |
| repositório e pacote `modelos` (`src/modelos/`, `modelos.<nome>`, `find_spec("modelos")`) | `models` (`src/models/`, `models.<nome>`) (Q11) |
| repositório `plataforma` (e a raiz `plataforma/` da árvore) | `platform` (Q10) |
| `carga_d1` | `load_d1` (Q12) |
| `chuva_d1` | `rain_d1` (Q12) |
| `media_movel` (modelo de teste) | `moving_average` (Q12) |
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
| `POOL = "plataforma"` | `POOL = "platform"` (Q10) |
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
| `criar_engine` | `build_engine` (Q7) | `ConfiguracaoAusente` | `MissingConfiguration` |
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
| `ao_falhar` | `notify_failure` (Q15) | `texto`, `cliente` | `text`, `client` |
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
| `PLATAFORMA_DIR` | `PLATFORM_DIR` (Q10) |
| `RCLONE_DESTINO`, `BACKUP_RETENCAO_DIAS`, `BACKUP_BANCOS` | `RCLONE_DESTINATION`, `BACKUP_RETENTION_DAYS`, `BACKUP_DATABASES` |
| `MODELOS_REPO`, `MODELOS_FONTE_LOCAL` | `MODELS_REPO`, `MODELS_LOCAL_SOURCE` |
| demais (`DATABASE_URL*`, `POSTGRES_BIND_IP`, `POSTGRES_DEV_PASSWORD`, `TS_*`, `PREFECT_*`, `MLFLOW_TRACKING_URI`, `TELEGRAM_*`, `GF_*`, `VPS_*`, `UV_CACHE_DIR`, `BUCKET_URL`) | sem mudança |

**J. Infra, CI e painéis**

| Atual | Novo |
| --- | --- |
| serviço `saude`, `infra/saude/saude`, rota `/saude`, container `plataforma-saude-1` | `health`, `infra/health/health`, `/health`, `platform-health-1` (Q10) |
| serviço `agendador` | `scheduler` |
| imagens `plataforma-jobs`, `plataforma-mlflow` | `platform-jobs`, `platform-mlflow` (Q10) |
| `/opt/plataforma` | `/opt/platform` (Q10) |
| tag Tailscale `tag:plataforma` | `tag:platform` (Q10) |
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
| `ingestion/calendario.py` | `ingestion/calendar_ref.py` (Q8) | `flows/ingestao.py` | `flows/ingest.py` (Q9) |
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

## 5. Passos

1. Crie a branch `docs/english-naming-convention` a partir da `main`. Confirme que este plano está na branch e não o edite.
2. Crie `docs/adr/0001-english-naming-convention.md`, em português, com estas seções nesta ordem:
   - `# ADR 0001: Convenção de nomes em inglês para identificadores de implementação`
   - Linhas de metadado: `Status: Aceito`, `Data: 2026-11-07`, `Decisores: Maximiliano` (ver Q25).
   - `## Contexto`: os docs e planos misturam identificadores em português e em inglês (ex.: `raw.clima_previsao` ao lado de `build_features`); ferramentas, bibliotecas e o mercado usam inglês; ainda não há código, então renomear agora custa só texto.
   - `## Decisão`: o texto da regra do passo 9, mais a lista de categorias abrangidas: código, variáveis, funções, classes, módulos, nomes de arquivo de código, schemas, tabelas, colunas, papéis do Postgres, jobs, flows, deployments, subcomandos e flags de CLI, variáveis de ambiente, serviços, imagens e volumes, painéis, nomes de modelo, branches, comentários, mensagens de commit, títulos e corpos de PR.
   - `## Regras de formação`: a seção 4.1 deste plano.
   - `## Tabela de nomes`: as tabelas A a M da seção 4.2, sem as marcas (Qn) e com as respostas do usuário já aplicadas.
   - `## Consequências`: (a) mudam os nomes de `raw` e `ref` e a assinatura do contrato (`build_features`, saída de `predict`, `evaluate`), cobertos por este ADR; como ainda não há tabela nem código, não há migração Alembic a fazer; a ciência de dados precisa ser avisada (`AGENTS.md`, "Fronteira"); (b) `.claude/` e algumas linhas do `AGENTS.md` ainda citam nomes antigos até uma tarefa própria; (c) os nomes de arquivo de `docs/` continuam em português; (d) a semântica das perguntas P8, P9, P12, P14 e P18 do índice não muda.
   - `## Alternativas consideradas`: manter tudo em português (rejeitada: atrito com bibliotecas, mercado e código gerado); misto, com contrato em inglês e o resto em português (rejeitada: regra difícil de aplicar e de revisar).
3. Meça a linha de base e guarde a saída para o corpo do PR: rode os comandos 1 a 6 da seção 6 trocando `-n` por `-c` (conta linhas por arquivo), e o comando 7 como está. Ordem de grandeza esperada: cerca de 580 linhas com tokens compostos em 60 arquivos, cerca de 90 linhas com variáveis de ambiente, cerca de 400 palavras soltas entre crases, cerca de 150 caminhos, 32 branches e cerca de 40 flags; ao todo, entre 1.300 e 1.700 substituições em cerca de 62 arquivos.
4. **Passada A, tokens compostos** (com `_`, `.`, `/`, `-` ou maiúsculas, e as classes `PascalCase`). Esses tokens nunca aparecem em prosa, então podem ser trocados em qualquer lugar dos três locais, sempre como palavra inteira (os limites são início ou fim de linha, espaço, crase, aspas, parênteses, colchetes, vírgula, `.`, `/`, `-`, `:`). Ordem, da mais longa para a mais curta:
   1. Branches (tabela L), antes de tudo, porque contêm `clima-previsao`, `ons-carga`, `vigia-saude` etc.
   2. Caminhos de arquivo completos (tabela K e caminhos da J), antes dos tokens que eles contêm (ex.: `migrations/versions/0004_raw_clima_previsao.py` antes de `clima_previsao`; `tests/fixtures/modelos_fake/src/modelos/teste_fake/__init__.py` antes de `modelos`).
   3. Nomes qualificados `schema.tabela` (tabela B), antes das palavras soltas `locais`, `calendario`, `previsoes`, `metricas`.
   4. Tokens `snake_case` e `UPPER_SNAKE_CASE` (tabelas C, F, H, I, K), do mais longo para o mais curto. Ordens obrigatórias: `carimbar_ingerido_em` antes de `ingerido_em`; `test_raw_clima_previsao`, `test_checks_clima_previsao`, `SCHEMA_CLIMA_PREVISAO`, `ingest_clima_previsao` e `openmeteo_previsao_sao_paulo` antes de `clima_previsao`; `versao_modelo` antes de `modelo`; `pacote_versao` e `pacote_modelos` antes de `modelos`; `score_modelos` e `monitorar_modelos` antes de qualquer `modelos`; `nome_feriado` antes de `nome`; `valor_previsto` e `valor_real` antes de `valor`; `data_alvo` e `data_ref` antes de `data`. Como `_` conta como letra para limite de palavra, `clima_previsao` não casa dentro de `raw_clima_previsao`: cada composto precisa da sua própria linha na tabela (todos já estão nela).
   5. Classes e exceções `PascalCase` (tabela H), e `class Local` → `class Location`.
   6. Itens `kebab-case` e com `.` (tabelas G e J): subcomandos, painéis, imagens, unidades systemd, `lint-e-testes`, `artefatos.tgz`, `/opt/plataforma`, `tag:plataforma`, `plataforma-saude-1`.
   - **Protegidos:** antes de trocar `plataforma` e `modelos`, confira que `docs/plataforma-ml.md`, `plataforma-ml.md`, `docs/guia-ciencia-de-dados.md` e `migrations-e-dados.md` ficam intactos (o limite de palavra casaria `plataforma` dentro de `plataforma-ml.md`). Também não toque em `carga_energia_di`, `CARGA_ENERGIA_<ANO>`, `id_subsistema`, `val_cargaenergiamwmed`, `America/Sao_Paulo` nem nos ids das cidades.
5. **Passada B, palavras soltas** (`nome`, `data`, `subsistema`, `chave`, `chaves`, `modelo`, `metrica`, `valor`, `cientista`, `leitura`, `saude`, `agendador`, `previsoes`, `metricas`, `locais`, `calendario`, `tabela`, `linhas`, `cliente`, `local`, `dias`, `hoje`, `inicio`, `fim`, `ano`, `conteudo`, `senha`, `versao`, `modulo`, `agora`, `comando`, `texto`, `caminho`, `limite`, `alvos`, `previsto`, `real`, `executar`, `registrar`, `checar`, `atualizar`, `ignorar`, `producao`, `imagens`, `disco`, `saida`, `classe`, `teste`, `inexistente`, `minha`, `tentativas`, `modelos`, `plataforma`). Essas palavras também aparecem em prosa, então troque **só** dentro de código: trechos entre crases (inclusive dentro de assinaturas, como `upsert(conn, tabela, linhas, chaves, *, ao_conflitar, carimbar_ingerido_em)`, e de SQL, como `min(data)`) e blocos cercados por três crases. Faça arquivo por arquivo, revisando cada troca. Atenção ao contexto:
   - `modelo` como coluna SQL (em `predictions.previsoes`, `monitoring.metricas`, `chaves=[...]`, consultas e painéis) → `model_name`; `modelo` como parâmetro ou variável Python (ex.: `gerar_previsoes(conn, *, nome, versao, modulo, modelo, ...)`, `predict(modelo, features)`) → `model`.
   - `data` como coluna → `date`; a flag `--data` → `--date`.
   - `real` e `previsto` como parâmetros, variáveis ou séries de painel → `actual` e `predicted`; a palavra "real" em prosa fica.
   - `plataforma` e `modelos` entre crases, como nome de repositório ou de pacote → `platform` e `models` (Q10, Q11).
   - Em blocos de código, renomeie também identificadores citados dentro de comentários (ex.: `# devolve colunas: chave, data_alvo, valor_previsto` → `# devolve colunas: key, target_date, predicted_value`), mas deixe a prosa do comentário em português (Q23).
   - Textos de mensagem entre aspas ficam em português; só os identificadores dentro deles mudam (ex.: "modelo <nome> não define carregar_real" → "modelo <nome> não define load_actuals") (Q24).
6. **Passada C, flags de CLI** (tabela G): `--inicio`, `--fim`, `--dias`, `--hoje`, `--modelo`, `--versao`, `--data`, `--gerado-em`. Não toque em flags de ferramentas externas (`--rev-id`, `--wait`, `--with`, `--env-file` etc.).
7. Confira os 8 arquivos com blocos cercados (`docs/plataforma-ml.md`, `docs/plans/00-indice.md`, `08-upsert-idempotente.md`, `16-agendador-cron.md`, `31-subir-mlflow-prefect-manual.md`, `42-score-nucleo.md`, `52-monitor-nucleo.md`, `53-monitor-um-modelo.md`). Resultado esperado dos principais:
   - `docs/plataforma-ml.md`, bloco do contrato (o de `42-score-nucleo.md` e o de `52-monitor-nucleo.md` ficam iguais às partes correspondentes):
     ```python
     def build_features(conn, ref_date: date) -> pd.DataFrame: ...
         # lê raw/ref; só usa dados disponíveis até ref_date (sem vazamento)

     def predict(model, features: pd.DataFrame) -> pd.DataFrame: ...
         # devolve colunas: key, target_date, predicted_value

     def evaluate(predicted: pd.DataFrame, actual: pd.DataFrame) -> dict[str, float]: ...
         # ex.: {"mape": 3.1, "mae": 1520.0}
     ```
   - `docs/plataforma-ml.md`, árvores de pastas: `plataforma/` → `platform/`, `modelos/` → `models/`, `src/modelos/` → `src/models/`, `carga_d1/` → `load_d1/`, `chuva_d1/` → `rain_d1/`; comentários em prosa (`# carga diária`, `# previsão + observado`) ficam.
   - `docs/plans/08-upsert-idempotente.md`: `upsert(conn: sqlalchemy.Connection, table: str, rows: pd.DataFrame, keys: list[str], *, on_conflict: Literal["update", "ignore"] = "update", stamp_ingested_at: bool = True) -> int` (mantendo a quebra em linhas do original); o comentário `# "schema.nome"` vira `# "schema.table"`.
   - `docs/plans/16-agendador-cron.md`: `30 6 * * * python -m ingestion weather-forecast`.
   - `docs/plans/53-monitor-um-modelo.md`: `def load_actuals(conn, target_date: date) -> pd.DataFrame: ...` com o comentário `# colunas: key, target_date, actual_value; vazio se o real ainda não chegou`.
8. Revise o diff de cada arquivo com `git diff --word-diff main -- <arquivo>`: só identificadores podem ter mudado. Preserve a codificação UTF-8 (acentos), o fim de linha original e os `\|` escapados dentro de tabelas Markdown (ex.: `main(argv: list[str] \| None = None)` no plano 11).
9. Em `AGENTS.md`, seção "Regras de código", acrescente como último item, depois de "Merge na `main` é a única forma de mudar produção.", exatamente:
   ```
   - Identificadores e artefatos de implementação em inglês: código, variáveis, funções, classes, módulos e nomes de arquivo de código, schemas, tabelas, colunas, papéis do Postgres, jobs, flows, subcomandos e flags de CLI, variáveis de ambiente, serviços, imagens, painéis, nomes de modelo, branches, comentários, mensagens de commit e títulos e corpos de PR. A prosa de `docs/` (planos, guias, ADRs) continua em português. Tabela de nomes e regras de formação: `docs/adr/0001-english-naming-convention.md`.
   ```
   Não altere outras linhas do `AGENTS.md`, a menos que o usuário tenha aprovado a Q21.
10. Rode todas as checagens da seção 6 e cole comandos e saídas no corpo do PR, junto com a linha de base do passo 3.
11. Commits em inglês, um por passada, para facilitar a revisão (ex.: `docs: add ADR 0001 english naming convention`, `docs: rename compound identifiers to english`, `docs: rename code-span identifiers to english`, `docs: rename CLI flags and branches to english`, `docs: add english naming rule to AGENTS.md`). Título e corpo do PR em inglês. O PR passa por `code-reviewer` e `pr-reviewer`, porque toca `AGENTS.md`.

## 6. Critérios de pronto

Todos os comandos rodam na raiz do repo, na branch do PR, em PowerShell (aspas simples protegem as crases e os `$`). Quando `git grep` não encontra nada, ele não imprime nada e sai com código 1: é o resultado esperado dos comandos 1 a 6. O repo ainda não tem comandos próprios de lint ou teste (`AGENTS.md`, "Comandos"); só `git` é usado.

```powershell
# 1. Tabelas, colunas e nomes de modelo
git grep -nwE 'ingerido_em|emitida_em|data_alvo|data_ref|local_id|clima_previsao|clima_observado|ons_carga_diaria|carga_mwmed|versao_modelo|valor_previsto|valor_real|gerado_em|atualizado_em|horizonte_dias|umidade_media|vento_max|dia_semana|feriado_nacional|nome_feriado|carga_d1|chuva_d1|media_movel|plataforma_admin|pacote_modelos|pacote_versao' -- docs/plataforma-ml.md docs/guia-ciencia-de-dados.md docs/plans ':(exclude)docs/plans/2026-11-07-english-naming-convention.md'

# 2. Funções, jobs e flows
git grep -nwE 'criar_engine|ao_conflitar|carimbar_ingerido_em|obter_json|obter_bytes|obter_real|buscar_previsao|buscar_observado|espera_base|listar_locais|listar_champions|linhas_esperadas|checar_continuidade_ons|checar_continuidade_clima|checar_disco|checar_servicos|atraso_max_dias|garantir_banco|url_admin|url_arquivo|normalizar_carga|baixar_carga|montar_calendario|carregar_calendario|carregar_real|montar_comando|janela_padrao|gerar_previsoes|especificacao_pacote|modulo_python|env_extra|ultimas_linhas_stderr|pontuar_modelo|avaliar_modelo|ultimo_lote|avaliar_dia|enviar_telegram|ao_falhar|vigiar_saude|ingest_clima_previsao|ingest_clima_observado|ingest_ons_carga|score_modelos|monitorar_modelos|score_um|monitor_um' -- docs/plataforma-ml.md docs/guia-ciencia-de-dados.md docs/plans ':(exclude)docs/plans/2026-11-07-english-naming-convention.md'

# 3. Testes, fixtures e migrações
git grep -nwE 'test_migracoes|test_permissoes|test_ref_locais|test_raw_clima_previsao|test_checks_clima_previsao|test_job_clima_previsao|test_openmeteo_previsao|test_openmeteo_observado|test_calendario|test_ons_leitura|test_raw_ons_carga_diaria|test_job_ons_carga|test_raw_clima_observado|test_job_clima_observado|test_admin_bancos|test_flows_ingestao|test_predictions_previsoes|test_score_nucleo|test_registro_champions|test_score_um|test_monitoring_metricas|test_monitor_nucleo|test_monitor_um|test_alertas|test_vigia|test_paineis_sql|openmeteo_previsao_sao_paulo|openmeteo_arquivo_sao_paulo|modelos_fake|teste_fake|banco_teste|novo_banco|banco_migrado|teste_upsert|nao_existe|nome_do_teste|0002_papeis|0003_ref_locais|0004_raw_clima_previsao|0005_ref_calendario|0006_raw_ons_carga_diaria|0007_raw_clima_observado|0008_predictions_previsoes|0009_monitoring_metricas' -- docs/plataforma-ml.md docs/guia-ciencia-de-dados.md docs/plans ':(exclude)docs/plans/2026-11-07-english-naming-convention.md'

# 4. Variáveis de ambiente, constantes e classes
git grep -nwE 'POSTGRES_ADMIN_USUARIO|POSTGRES_ADMIN_SENHA|POSTGRES_INGESTOR_SENHA|POSTGRES_SCORER_SENHA|POSTGRES_LEITURA_SENHA|MLFLOW_DB_SENHA|PREFECT_DB_SENHA|GRAFANA_ADMIN_SENHA|SAUDE_BIND_IP|GHCR_DONO|IMAGEM_TAG|PLATAFORMA_DIR|RCLONE_DESTINO|BACKUP_RETENCAO_DIAS|BACKUP_BANCOS|MODELOS_REPO|MODELOS_FONTE_LOCAL|TAG_PACOTE|SCHEMA_CLIMA_PREVISAO|SCHEMA_CLIMA_OBSERVADO|SCHEMA_ONS_CARGA|SCHEMA_CALENDARIO|SCHEMA_SAIDA_PREDICT|URL_PREVISAO|URL_ARQUIVO|MAPA_COLUNAS|SUBCOMANDOS|Subcomando|FUSO|ChecagemFalhou|ErroDeRede|SaidaInvalida|ExecucaoFalhou|RealIndisponivel|MetricasInvalidas|ConfiguracaoAusente|class Local' -- docs/plataforma-ml.md docs/guia-ciencia-de-dados.md docs/plans ':(exclude)docs/plans/2026-11-07-english-naming-convention.md'

# 5. Nomes qualificados, kebab-case, caminhos, flags e branches
git grep -nE 'ref\.locais|ref\.calendario|predictions\.previsoes|monitoring\.metricas|clima-previsao|clima-observado|ons-carga|criar-bancos|nao-existe|dados-brutos|erro-modelos|previsoes\.json|lint-e-testes|plataforma-jobs|plataforma-mlflow|plataforma-backup|plataforma-saude|plataforma\.yaml|/opt/plataforma|tag:plataforma|infra/saude|calendario\.py|ingestao\.py|registro\.py|alertas\.py|vigia\.py|artefatos\.tgz|src/modelos|modelos\.\{|--inicio|--fim([^a-z-]|$)|--dias|--hoje|--modelo|--versao|--data([^a-z-]|$)|--gerado-em|feat/(db-conexao|db-papeis|ref-locais|imagem-jobs|vigia-saude|painel-)' -- docs/plataforma-ml.md docs/guia-ciencia-de-dados.md docs/plans ':(exclude)docs/plans/2026-11-07-english-naming-convention.md'

# 6. Palavras soltas entre crases
git grep -nE '`(nome|data|subsistema|chave|chaves|modelo|metrica|valor|cientista|leitura|saude|agendador|previsoes|metricas|locais|calendario|tabela|linhas|cliente|local|Local|dias|hoje|inicio|fim|ano|conteudo|senha|versao|modulo|agora|comando|texto|caminho|limite|alvos|previsto|real|executar|registrar|checar|atualizar|ignorar|producao|imagens|disco|saida|classe|teste|inexistente|minha|tentativas|modelos|plataforma)`' -- docs/plataforma-ml.md docs/guia-ciencia-de-dados.md docs/plans ':(exclude)docs/plans/2026-11-07-english-naming-convention.md'

# 7. Caminho do doc preservado
git grep -c 'plataforma-ml.md' -- docs AGENTS.md

# 8. Nome externo do ONS preservado
git grep -n 'carga_energia_di' -- docs/plataforma-ml.md docs/plans

# 9. Id de cidade preservado
git grep -nw 'sao_paulo' -- docs/plans/09-ref-locais.md

# 10. Regra nova no AGENTS.md
git grep -n 'english-naming-convention' -- AGENTS.md

# 11. Estrutura do ADR
git grep -n '^## ' -- docs/adr/0001-english-naming-convention.md

# 12. Tabela no ADR
git grep -nE 'ref\.locations|raw\.weather_forecast|predictions\.model_predictions|location_id|ingested_at' -- docs/adr/0001-english-naming-convention.md

# 13. Nada fora do escopo mudou
git diff --name-only main...HEAD -- .claude CLAUDE.md docs/plans/2026-11-07-english-naming-convention.md

# 14. Lista de arquivos do PR
git diff --name-only main...HEAD

# 15. Guia da cientista: só identificadores mudaram
git diff --word-diff=plain main...HEAD -- docs/guia-ciencia-de-dados.md
```

Saída esperada:

1. a 6. Nada (código de saída 1).
7. Os mesmos números por arquivo da linha de base do passo 3 (o caminho do doc não foi renomeado; o `AGENTS.md` ganha 0 ocorrências novas).
8. As mesmas linhas de antes da mudança (`docs/plataforma-ml.md`, `18-verificar-fontes-manual.md`, `20-leitura-ons.md`).
9. Ao menos uma linha.
10. Uma linha: a regra nova em "Regras de código".
11. `## Contexto`, `## Decisão`, `## Regras de formação`, `## Tabela de nomes`, `## Consequências`, `## Alternativas consideradas`, nesta ordem.
12. Ao menos uma linha para cada um dos cinco termos.
13. Nada.
14. Só `AGENTS.md`, `docs/adr/0001-english-naming-convention.md`, `docs/plataforma-ml.md`, `docs/guia-ciencia-de-dados.md` e arquivos `docs/plans/NN-*.md` (e este plano, se ele entrar no mesmo PR sem alteração de conteúdo).
15. Revisão manual: toda mudança está entre crases ou em bloco de código (`carga_d1` → `load_d1`, `src/modelos/` → `src/models/`, `predictions.previsoes` → `predictions.model_predictions` etc.); nenhuma frase de prosa mudou.

Se, nos comandos 1 a 6, sobrar uma ocorrência que pareça dever ficar em português (um caso não previsto na seção 4.2), não force a troca: registre no corpo do PR e pergunte ao usuário.

## 7. Testes necessários

não: tarefa só de documentação (ADR, `AGENTS.md` e renomeação de identificadores em Markdown), sem código nem mudança de comportamento; a verificação é feita pelos comandos `git grep` da seção 6.

## 8. Casos de teste

n/a

## 9. Riscos e perguntas em aberto

Riscos:

- **Troca dentro de prosa:** `data`, `nome`, `valor`, `real`, `local`, `modelo` são palavras comuns em português. Mitigação: a passada B só atua dentro de crases e blocos de código, arquivo por arquivo, e o comando 15 confere o guia.
- **Colisão de substrings:** `plataforma` dentro de `plataforma-ml.md`, `clima-previsao` dentro de branches, `modelos` dentro de `src/modelos/`. Mitigação: a ordem da passada A, a lista de protegidos e os comandos 7 a 9.
- **Mesmo nome em português com dois alvos:** `modelo` vira `model_name` (coluna) ou `model` (parâmetro). Mitigação: a regra do passo 5.
- **Diff grande (cerca de 1.500 trocas em 62 arquivos):** revisão cansativa. Mitigação: um commit por passada e a linha de base no PR.
- **Inconsistência temporária:** `.claude/rules/migrations-e-dados.md`, `.claude/agents/code-reviewer.md` e as linhas 3, 7 e 20 do `AGENTS.md` continuam com os nomes antigos depois do merge e podem induzir agentes a usar `ingerido_em`. Ver Q20 e Q21.
- **Fronteira com a ciência de dados:** mudam nomes de `raw`/`ref` e a assinatura do contrato. Ainda não há código nem tabela, mas o `AGENTS.md` exige aviso à ciência de dados. Ver Q22.
- **Ferramenta de edição:** o implementer pode usar um script temporário fora do repo (no scratchpad) nas passadas A e C; o script não é versionado.

Perguntas em aberto (a proposta já está na tabela; o usuário confirma ou troca antes de passar ao implementer):

- **Q1.** `predictions.previsoes` → `predictions.model_predictions` e `monitoring.metricas` → `monitoring.model_metrics` (evita `predictions.predictions`), ou `predictions.predictions` e `monitoring.metrics`?
- **Q2.** `chave` → `key` (palavra não reservada no Postgres, mas genérica) ou `series_key` / `entity_key`?
- **Q3.** `data` → `date` (aceito pelo Postgres, mas é também o nome do tipo e confunde em SQL) ou `day` / `ref_date`?
- **Q4.** `emitida_em` → `issued_at`. O tipo (`date` ou `timestamptz`) continua aberto em P8; se P8 ficar com `date`, prefere `issue_date`?
- **Q5.** `carga_mwmed` (MWmed = média de MW no dia) → `load_avg_mw`, `load_mwavg` ou `load_mw`?
- **Q6.** Coluna `modelo` → `model_name` (evita confusão com o objeto `model` de `predict`) ou `model`?
- **Q7.** `criar_engine` → `build_engine` (evita sombrear `sqlalchemy.create_engine`) ou `create_engine`, `make_engine`, `get_engine`?
- **Q8.** `ingestion/calendario.py` → `ingestion/calendar_ref.py` (`calendar.py` tem o mesmo nome de um módulo da stdlib) ou `ingestion/calendar.py`?
- **Q9.** `flows/ingestao.py` → `flows/ingest.py` (evita um `flows/ingestion.py` ao lado do pacote `ingestion`) ou `flows/ingestion.py`?
- **Q10.** Nome derivado de `plataforma`: `platform` (repo, `/opt/platform`, `tag:platform`, imagens `platform-*`, pool do Prefect, `platform_admin`, `PLATFORM_DIR`, projeto do compose e container `platform-health-1`, units systemd)? Ou usar o nome real deste repo no GitHub, `model_training_platform`? Ou manter os nomes de repositório como nomes próprios e trocar só os artefatos?
- **Q11.** Repositório e pacote `modelos` → `models`? (`models` não conflita tecnicamente com a URI `models:/` do MLflow, mas a leitura pode confundir; alternativa: `ml_models`.) O repo `modelos` já existe no GitHub?
- **Q12.** Nomes de modelo no MLflow: `carga_d1` → `load_d1`, `chuva_d1` → `rain_d1`, `media_movel` → `moving_average`. São nomes da cientista; ela concorda?
- **Q14.** Papéis: `cientista` → `scientist` ou `data_scientist`; `leitura` → `reader` ou `readonly`?
- **Q15.** `ao_falhar` → `notify_failure` (evita confusão com o argumento `on_failure` do Prefect) ou `on_flow_failure`?
- **Q17.** `feriado_nacional` → `is_national_holiday` ou `national_holiday`?
- **Q19.** A regra cobre "nomes de arquivo". Os arquivos de `docs/` (`plataforma-ml.md`, `guia-ciencia-de-dados.md`, os `docs/plans/NN-*.md` com slug em português, `.claude/rules/migrations-e-dados.md`) ficam em português, como prosa, ou entram numa tarefa futura de renomeação?
- **Q20.** `.claude/rules/migrations-e-dados.md` (linhas 12, 13 e 15) e `.claude/agents/code-reviewer.md` (linha 16) citam `ingerido_em`, `cientista`, `leitura`, `raw.clima_previsao` e `emitida_em`. Abrir uma tarefa de acompanhamento para alinhar `.claude/` à tabela? Recomendação: sim, logo depois deste merge.
- **Q21.** O `AGENTS.md` cita `plataforma` e `modelos` (linhas 3 e 7) e `ingerido_em` (linha 20). Aprovar a troca dessas três linhas neste mesmo PR (recomendado, para a regra nova não conviver com um exemplo que a viola)? Sem aprovação, o implementer não as toca.
- **Q22.** Quem avisa a cientista de dados sobre a mudança dos nomes de `raw`/`ref` e do contrato, e quando: antes ou depois do merge? Q11 e Q12 dependem dela.
- **Q23.** Comentários em prosa dentro dos blocos de código dos docs (ex.: `# lê raw/ref; só usa dados disponíveis...`) ficam em português nesta tarefa (proposta) ou já são traduzidos?
- **Q24.** Mensagens de erro e de log citadas nos planos (ex.: "modelo <nome> não define carregar_real", "real de <d> ainda não chegou") ficam em português nos docs (proposta) ou vão para inglês, já que no código serão artefatos de implementação? O ADR deve dizer que mensagens de log e de erro do código são em inglês?
- **Q25.** Status do ADR: `Aceito` já no PR (a decisão é do usuário) ou `Proposto` até o merge?

(Os números Q13, Q16 e Q18 não foram usados, para não confundir com P13, P16 e P18 do índice.)

## 10. Decisões que exigem ADR

- Esta tarefa **é** o ADR `docs/adr/0001-english-naming-convention.md`, escrito pelo `task-implementer` por instrução expressa do usuário (exceção à regra "Nenhum agente escreve ADR" do `AGENTS.md`), e ele sai no mesmo PR das renomeações.
- O ADR cobre as duas mudanças de fronteira que o `AGENTS.md` exige registrar: nomes de tabelas e colunas de `raw` e `ref`, e a assinatura do contrato (`build_features(conn, ref_date)`, colunas de saída de `predict`, `evaluate(predicted, actual)`). Não há migração Alembic a fazer, porque nenhuma tabela existe ainda; o aviso à ciência de dados continua obrigatório (Q22).
- Nenhum outro ADR é necessário. Os ADRs já previstos em `docs/plans/00-indice.md` (toolchain, rede, operação interina, contrato de dados v1, execução de modelos, fonte do real, backup) devem usar os nomes novos quando forem escritos.
