# Índice dos planos: roadmap das Fases 0 a 5 em PRs atômicos

Nov 7, 2026. Fonte: `docs/plataforma-ml.md` (roadmap, modelo de dados, jobs, contrato, CI/CD) e `docs/guia-ciencia-de-dados.md` (lado do contrato).

Revisão v2 (2026-11-07): aplica as decisões P1 a P5 e a P15 do usuário (toolchain, repos públicos, VPS de 1 GB, rede só Tailscale, coleta da previsão antes do ONS). Ver "Decisões resolvidas".

Revisão v3 (2026-11-08): alinha o índice aos planos 28 a 40 revisados (recomendações aceitas pelo usuário): migrações `0008` (CONNECT no `ml`), `0009` (previsões) e `0010` (métricas); decisão de memória da Fase 3 (28b de 2 GB como padrão antes do item 31); API do Prefect autenticada desde o PR 30; dois ADRs novos a escrever ("Agendamento e execução pelo Prefect", antes do 33, e "Pipeline de entrega", antes do 37); P13 bloqueia só o 42; estado dos itens de segurança S1 a S4, H1 e R1 (já na `main`). Revisão final (mesmo dia): bootstrap do primeiro deploy automático (plano 39, passo 9) e fim da exceção do ADR 0004 nesse deploy; plano do S5 (`S5-settings-seguranca-manual.md`).

Revisão v4 (2026-11-09): os dois ADRs da v3 foram escritos (ADR 0007 "Pipeline de entrega", com revisão de segurança, e ADR 0008 "Agendamento e execução pelo Prefect"; status Aceito, ainda não mergeados na `main` em `7fc1923`). Planos 37 a 40 alinhados ao ADR 0007: digest pela saída do `docker push` (37); claim `job_workflow_ref`, rotação, revogação e procedimento de emergência (38); verificação de attestation antes do `pull`, `pg_dump` do `ml` antes de migrar, exceções do rollback, `.deploy/history.log` e conferência do SHA no bootstrap (39); checagem de vazamento em run com falha e attestation como controle no deploy (40). Novo item **S6** (âncora de confiança, ADR 0007, item 11), que bloqueia o PR 39.

## Como usar

- Cada linha **agente** tem uma spec `NN-<slug>.md` com as 10 seções do `task-planner`. Cada linha **usuário** tem um `NN-<slug>-manual.md` com checklist e verificação de pronto.
- Fluxo de cada PR de agente (`AGENTS.md`, "Fluxo de trabalho"): usuário aprova a spec → `test-writer` escreve os testes e mostra que falham pelo motivo certo → `task-implementer` implementa até ficarem verdes e refatora com a suíte verde → CI → `code-reviewer` → `pr-reviewer`.
- **Passo 0**: quando os testes importam uma dependência nova (ex.: SQLAlchemy no `conftest.py`), o primeiro commit da branch é do implementador, só com `uv add`, antes do test-writer. Assim o teste falha por comportamento ausente e não por import quebrado. As specs que precisam disso dizem "passo 0".
- Comandos que já existem (PR 01, ver `.github/workflows/ci.yml`): `uv sync` (no CI, `uv sync --locked`), `uv run ruff check .`, `uv run ruff format --check .` e `uv run pytest`. O Postgres de teste vem do PR 05 e `uv run alembic ...` do PR 06. Cada PR registra os seus na seção "Comandos" do `AGENTS.md`. Nenhuma spec usa comando que não exista no ponto em que ela roda.
- Uma spec por vez. Antes de começar uma spec, confira se as dependências da coluna "Depende de" já estão na `main` e se os ADRs que ela pede estão aprovados e mergeados.

## Restrições que valem para todas as specs

- **Rede só Tailscale** (P4, 2026-11-07). Nenhuma porta pública: sem domínio, sem proxy com autenticação, sem certificado público. As UIs (MLflow, Prefect, Grafana e a rota de saúde) são publicadas só em `127.0.0.1` e expostas na tailnet por `tailscale serve`, num hostname `*.ts.net` com uma porta por UI (ADR 0003, `docs/adr/0003-tailscale-only-network.md`). O Postgres fica em `127.0.0.1:5432`, exposto na tailnet por `tailscale serve --tcp=5432` (P15). Nenhuma porta de serviço é publicada em `0.0.0.0`; os testes do PR 03 travam isso. A ACL do Tailscale é o controle de acesso.
- **VPS de 1 GB nas Fases 0 a 2; 2 GB por padrão a partir do item 31** (P3, 2026-11-07, e decisão de memória da Fase 3, 2026-11-08): 1 vCPU, 1 GB de RAM, 25 GB de SSD, 1 TB de transferência, provedor "Regular Cloud Compute", com 2 GB de swap (item 02) e `mem_limit` em todo serviço do compose (teste do PR 03). **As Fases 0 a 2 devem caber em 1 GB. A Fase 3 não fecha em 1 GB: o upgrade para 2 GB (item 28b) é o caminho padrão antes do item 31**, dispensável só com dispensa registrada pelo usuário e baseada na medição do 28a em D+7 ou depois (`available` mediano em repouso de 700 MB ou mais e nenhum gatilho G1 a G5). Depois do item 31, o 28b volta a ser condicional (para 4 GB), se um gatilho disparar nos itens 31, 35, 50 ou 59. `mem_limit` da Fase 3: `mlflow` 512m, `prefect-server` 640m, `prefect-worker` 768m. Estimativas a medir, não fatos: Postgres 100–250 MB, MLflow 200–350 MB, Prefect server 250–450 MB, worker 250–400 MB, Grafana 100–200 MB, Tailscale ~30 MB, job de ingestão com pandas 200–400 MB de pico.
- **Repositórios públicos** (P2, 2026-11-07), do próprio usuário. A VPS clona o repo e puxa as imagens do GHCR sem token nem `docker login`; o job de score instala o pacote `models` sem token. **Nenhum segredo entra no git, nem no histórico**: num repo público, um segredo commitado uma vez é público para sempre e precisa ser trocado (reescrever o histórico não basta). Segredos só no `infra/.env` da VPS (`chmod 600`, fora do git) e nos GitHub Secrets do environment `production`.
- **Compose de produção não sobe localmente sem autorização do usuário**: ele colide com o Postgres de teste na 5432. Critérios que dependem dele são do `compose-smoke` do CI (planos 29, 30, 33, 34).

## Tabela

Legenda: **A** = agente implementa; **U** = usuário executa (VPS, Tailscale, contas, segredos, coordenação). "Antecipado" = item da Fase 2 feito antes do fim da Fase 1 (aprovado pelo usuário em 2026-11-07, P5). Na coluna "Depende de", "ADR 0008" (`docs/adr/0008-prefect-scheduling-and-execution.md`, "Agendamento e execução pelo Prefect") e "ADR 0007" (`docs/adr/0007-delivery-pipeline.md`, "Pipeline de entrega") estão escritos desde 2026-11-09 (status Aceito) e precisam estar **mergeados na `main`** antes da implementação que bloqueiam.

| Id | Título | Fase | Depende de | Quem | Testes | Valor entregue |
| --- | --- | --- | --- | --- | --- | --- |
| 01 | Bootstrap do ambiente (uv, ruff, pytest, CI) | 0 (repo) | — | A | não (verificação por comandos) | Todo PR seguinte tem lint, teste e CI reais |
| 02 | Provisionar a VPS | 0 | — | U | — | VPS com Docker, firewall, Tailscale, usuário não-root |
| 03 | Compose de produção e rede só Tailscale (`tailscale serve`) | 0 | 01 | A | sim | Serviço de saúde em loopback, script do `tailscale serve`; testes que travam as regras de infra (nada em `0.0.0.0`, `mem_limit`) |
| 04 | Publicar a saúde na tailnet e testar reboot | 0 | 02, 03 | U | — | **Fase 0 pronta**: reboot traz tudo de volta; nada escuta na internet |
| 05 | Conexão Postgres e banco de teste | 1 | 01, 03 | A | sim | `build_engine()`; Postgres descartável local e no CI |
| 06 | Alembic e schemas | 1 | 05 | A | sim | Migrações versionadas; CI roda `alembic upgrade head` |
| 07 | Papéis e permissões | 1 | 06 | A | sim | `ingestor`, `scientist`, `scorer`, `reader` com privilégios padrão |
| 08 | Upsert idempotente | 1 | 07 | A | sim | Uma função única de upsert com `ingested_at` |
| 09 | `ref.locations` | 1 | 07 | A | sim | As 4 capitais, base dos jobs de clima |
| 10 | Postgres no compose de produção | 1 | 03, 05 | A | sim | Banco na VPS exposto só na tailnet |
| 11 | Imagem dos jobs e CLI | 1 | 06, 10 | A | sim | `python -m ingestion` e migrações rodando na VPS |
| 12 | Subir Postgres na VPS | 1 | 04, 09, 10, 11 | U | — | Banco migrado em produção; acesso da cientista via Tailscale |
| 13 | `raw.weather_forecast` | 2 (antecipado) | 09 | A | sim | Tabela de snapshots de previsão |
| 14 | Cliente da previsão Open-Meteo | 2 (antecipado) | 08 | A | sim | Busca a previsão com retry só para rede |
| 15 | Job `weather-forecast` | 2 (antecipado) | 11, 13, 14 | A | sim | Snapshot diário com checagem pandera |
| 16 | Agendador interino (supercronic) | 2 (antecipado) | 15 | A | sim | Job rodando sozinho às 06:30 |
| 17 | Ligar a coleta da previsão | 2 (antecipado) | 12, 13, 15, 16 | U | — | **Histórico de previsões começa a acumular** |
| 18 | Verificar as fontes (ONS, ERA5) | 1 | — | U | — | Atrasos e revisões conhecidos; horários e janelas ajustados |
| 19 | `ref.calendar` | 1 | 11, 15 | A | sim | Calendário com feriados nacionais |
| 20 | Leitura do parquet do ONS | 1 | 14, 18 | A | sim | Carga do ONS normalizada |
| 21 | `raw.ons_daily_load` | 1 | 19 | A | sim | Tabela de carga |
| 22 | Job `ons-load` | 1 | 16, 20, 21 | A | sim | Ingestão diária (07:00) e backfill por intervalo |
| 23 | Backfill do ONS e pronto da Fase 1 | 1 | 12, 19, 22 | U | — | **Fase 1 pronta**: ela consulta a carga do notebook |
| 24 | Cliente do observado (ERA5) | 2 | 14, 18 | A | sim | Clima observado por intervalo |
| 25 | `raw.weather_observed` | 2 | 21 | A | sim | Tabela do observado |
| 26 | Job `weather-observed` | 2 | 16, 24, 25 | A | sim | Ingestão diária (06:45) e backfill |
| 27 | Backfill do observado e pronto da Fase 2 | 2 | 17, 26 | U | — | **Fase 2 pronta**: 7 dias de snapshots sem falha |
| 28 | Bancos `mlflow` e `prefect` (`create-databases`) e migração `0008` | 3 | 07, 11 | A | sim | Backends prontos, idempotente; `0008_ml_database_connect` fecha o `CONNECT` de `PUBLIC` no `ml` |
| 28a | Checkpoint de memória da VPS | 3 | 27 (só para a linha de base: pode começar durante a janela D a D+7 do 27; a medição que decide é a de D+7 ou depois) | U | — | RAM medida com a stack da Fase 2; decisão registrada: 28b padrão ou dispensa |
| 28b | Upgrade da VPS para 2 GB (**padrão antes do 31**; depois, condicional) | 3 | 28a | U | — | VPS de 2 GB antes do item 31 (dispensável só com dispensa registrada pelo 28a); depois, 4 GB só se um gatilho do 31, 35, 50 ou 59 disparar (gatilho no 31: antes do item 35); verificação: `free -m` mostra a RAM nova |
| 29 | MLflow no compose | 3 | 03, 10, 28, 28a | A | sim | Tracking e registry só na tailnet (`mem_limit` 512m) |
| 30 | Prefect server no compose, com API autenticada | 3 | 28, 29 | A | sim | Orquestrador com UI só na tailnet (`mem_limit` 640m); `PREFECT_SERVER_API_AUTH_STRING` a partir de `PREFECT_API_AUTH` do `.env`; `/api/health` e `/api/ready` fora da autenticação; imagem `X.Y.Z-python3.12` + digest |
| 31 | Subir MLflow e Prefect | 3 | 27 (fechado), 28, 28a, 28b (ou dispensa registrada), 29, 30 | U | — | **Ela registra experimentos no MLflow**; memória medida de novo |
| 32 | Flows de ingestão | 3 | 15, 22, 26, 30 | A | sim | Ingestões como flows do Prefect; `prefect==X.Y.Z` igual à imagem do server (última estável com 7 dias ou mais; hoje `3.9.1`) |
| 33 | Deployments do Prefect | 3 | 32, ADR 0008 | A | sim | Agendas declaradas em código; pool `platform` (`process`, limite 1); deployments `<flow>/production` |
| 34 | Worker do Prefect | 3 | 30 (API autenticada), 33, ADR 0008 | A | sim | Execução dos deployments na VPS (`mem_limit` 768m); `PREFECT_API_AUTH_STRING` no worker e no `jobs` |
| 35 | Cutover supercronic → Prefect | 3 | 27, 28a, 31, 32, 33, 34, ADR 0008 | U | — | Prefect agendando em produção; memória medida de novo |
| 36 | Remover o agendador interino | 3 | 29, 30, 34, 35 | A | sim | Uma fonte de verdade para horários |
| 37 | Imagens no GHCR (Trivy + attestation) | 3 | 34, 36, S5 (checks required ativos), ADR 0007 | A | sim | Build reproduzível a cada merge; `jobs` e `prefect-worker` em `platform-jobs@${JOBS_IMAGE_DIGEST}`, `mlflow` em `platform-mlflow@${MLFLOW_IMAGE_DIGEST}`; digest tirado da saída do `docker push` (a tag `:<sha>` é mutável; só o digest é implantado) |
| 38 | Acessos e segredos do CI/CD | 3 | 37, S5, ADR 0007 | U | — | CI entra na tailnet por federação OIDC do Tailscale (subject do environment **e** claim `job_workflow_ref` do `deploy.yml` na `main`), só na 22 da VPS; chave restrita com rotação anual e revogação documentadas; procedimento de emergência; pacotes do GHCR públicos, sem token de leitura; último deploy manual completo |
| 39 | Deploy via SSH | 3 | 37, 38, S5, **S6**, ADR 0007 | A | sim | Merge na `main` chega à VPS, depois do verificador instalado (passo 9A) e de um único checkout manual de bootstrap com conferência do SHA (passo 9B); attestation de cada digest verificada antes do `pull`; `pg_dump` do `ml` antes de migrar, do `mlflow` antes do `mlflow db upgrade` e do `prefect` antes de trocar a imagem; rollback com exceções que exigem intervenção manual; trilha `.deploy/history.log` |
| 40 | Prova do deploy e CI do `models` | 3 | 36, 38, S6, 39 (com o bootstrap feito e o primeiro deploy automático com `success`), PR que remove a exceção de deploy manual de `.claude/rules/infra.md` | U | — | **Fase 3 pronta** |
| 41 | `predictions.model_predictions` (migração `0009`) | 4 | 25, 28, 40 | A | sim | Tabela única de previsões |
| 42 | Núcleo do score | 4 | 41 | A | sim | Contrato validado e gravado |
| 43 | Descobrir champions no MLflow | 4 | 42 | A | sim | Score genérico por alias |
| 44 | Executor isolado (`uv run --with`) | 4 | 43 | A | sim | Cada modelo roda com a sua versão do pacote |
| 45 | `flows.score_one` | 4 | 42, 43, 44 | A | sim | Ponta a ponta MLflow → pacote → banco |
| 46 | Flow `score_models` (07:30) | 4 | 45 | A | sim | Score diário de todos os champions |
| 47 | Grafana no compose | 4 | 30, 41 | A | sim | Painéis com usuário `reader`, só na tailnet |
| 48 | Painel de dados brutos | 4 | 47 | A | sim | Saúde das fontes visível |
| 49 | Painel de previsões | 4 | 48 | A | sim | Previsto × real visível |
| 50 | Modelo de teste e pronto da Fase 4 | 4 | 46, 47, 48, 49 | U | — | **Fase 4 pronta**: média móvel grava todo dia |
| 51 | `monitoring.model_metrics` (migração `0010`) | 5 | 41, 50 | A | sim | Tabela de métricas |
| 52 | Núcleo do monitoramento | 5 | 51 | A | sim | `evaluate` chamado e gravado |
| 53 | `flows.monitor_one` e fonte do real | 5 | 44, 45, 52 | A | sim | Real obtido e reavaliado em janela |
| 54 | Flow `monitor_models` (08:00) | 5 | 46, 53 | A | sim | Métricas diárias de todos os champions |
| 55 | Alertas no Telegram | 5 | 54 | A | sim | Falha de flow vira mensagem |
| 56 | Vigia de saúde | 5 | 55 | A | sim | Disco > 80% e serviço fora do ar viram mensagem |
| 57 | Backup e restore | 5 | 28, 29 | A | sim | Backup diário com restore provado no CI |
| 58 | Painel de erro | 5 | 49, 51 | A | sim | Erro real × previsto com médias móveis |
| 59 | Alertas, backups e pronto da Fase 5 | 5 | 54, 55, 56, 57, 58 | U | — | **Fase 5 pronta** |

### Segurança em CI (em paralelo à Fase 2) e itens transversais

Fase própria, decidida no ADR 0006 (`docs/adr/0006-security-validation-in-ci.md`). Os ids S1 a S6, H1 e R1 não renumeram os itens acima. Roda em paralelo à Fase 2, sem esperar o item 27 (decisão do usuário em 2026-11-08). O item S5 precisa estar pronto (com os checks required ativos) antes dos PRs 37 e 39 e do item 38 (ADR 0007, item 10); o item S6 precisa estar pronto antes do merge do PR 39 (ADR 0007, item 11). Os planos 37 e 39 usam pin por SHA com comentário `# vX.Y.Z`. Estado em 2026-11-08: S1 a S4, H1 e R1 estão na `main`; falta o S5 (menor data para os checks required: 2026-11-22). Em 2026-11-09: plano do S6 criado (pendente; depende do S5).

| Id | Título | Fase | Depende de | Quem | Testes | Valor entregue |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | Pin por SHA das actions e `permissions` no `ci.yml` (também imagens por digest) | Segurança em CI | — | A | sim | **Na `main`** (#46, `a722b74`): tags de action não redirecionáveis; token do CI com o mínimo |
| S2 | `dependabot.yml` e `SECURITY.md` | Segurança em CI | S1 | A | sim | **Na `main`** (#48, `dd15c59`): SHAs e digests mantidos por PRs semanais |
| S3 | Workflow `security.yml` (zizmor, dependency-review, Trivy) | Segurança em CI | S1 | A | sim | **Na `main`** (#49, `f8cca44`): varredura de workflows, dependências e Dockerfile, só avisando; testes estáticos travam a forma do workflow |
| S4 | Regra `S` do `ruff` | Segurança em CI | S1 | A | sim | **Na `main`** (#45, `2ffc2c8`): lint de segurança Python com ignores justificados |
| S5 | Settings de segurança e checks required (`S5-settings-seguranca-manual.md`) | Segurança em CI | S2, S3 | U | — | Settings conferidas uma a uma por `gh api` (secret scanning, push protection, CodeQL, Dependabot alerts e security updates, private vulnerability reporting, aprovação de contribuidores externos, workflow permissions read-only); a partir de 2026-11-22, com zero HIGH/CRITICAL abertos sem exceção, os seis checks (`lint-and-test`, `compose-smoke`, `zizmor`, `dependency-review`, `trivy-config`, `trivy-fs`) required com "Do not allow bypassing" |
| S6 | Âncora de confiança do deploy (`S6-ancora-de-confianca-manual.md`) | Segurança em CI | S5 | U | — | **Bloqueia o 39.** ADR 0007, item 11: branch protection do S5 conferida e, à escolha do usuário, (b1) credenciais dos agentes sem poder de merge na `main` nem de aprovar deployment (conta separada + ruleset) ou (b2) mantenedor como required reviewer do environment `production`; escolha e verificações registradas no plano |
| H1 | Endurecimento: follow-ups de revisões anteriores | Transversal | — | A | sim | **Na `main`** (#51, `4090313`): `parse_load` sem carga não finita, `upsert` valida argumentos, dtype do clima, `.dockerignore` |
| R1 | Regras de workflows e imagens em `.claude/rules/infra.md` | Transversal | S1, S3 | U (ou agente com autorização explícita para `.claude/`) | — | **Na `main`** (#52, `05c32c9`): regras do ADR 0006 carregadas pelos agentes |

Totais da tabela principal: 46 PRs de agente (45 com TDD; o 01 não tem, por ser o bootstrap) e 15 itens do usuário (o 28b é padrão antes do 31 e condicional depois). Fora desses totais: S1 a S6, H1 e R1.

## Grafo de dependências

```
Fase 0
  01 ──> 03 ──┬──────────────> 04(U) <── 02(U)
              │
Fase 1 (base) │
  01,03 ──> 05 ──> 06 ──> 07 ──┬─> 08
                               └─> 09
  03,05 ──> 10 ;  06,10 ──> 11
  04,09,10,11 ──> 12(U)

Fase 2 antecipada: caminho mais curto até a coleta da previsão
  09 ──> 13 ─┐
  08 ──> 14 ─┼─> 15 ──> 16 ──> 17(U)  <── 12(U)
  11 ────────┘

Fase 1 (resto)
  18(U) ──> 20 ;  11,15 ──> 19 ──> 21 ;  16,20,21 ──> 22 ──> 23(U) <── 12,19

Fase 2 (resto)
  14,18 ──> 24 ;  21 ──> 25 ;  16,24,25 ──> 26 ──> 27(U) <── 17

Fase 3
  27(U, linha de base) ··> 28a(U) ──> 28b(U, padrão; dispensa registrada) ──┐
  07,11 ──> 28 ──┬─> 29 ──> 30 ─────────────────────────────────────────────┴─> 31(U) <── 27 fechado
          28a ───┘
  15,22,26,30 ──> 32 ──> 33 ──> 34 ──> 35(U) ──> 36 ──> 37 ──> 38(U) ──> 39 ──> bootstrap(U, 39 passo 9B) ──> 1º deploy automático
  ADR 0008 ──> 33, 34, 35 ;  30 (API autenticada) ──> 34 ;  27,28a,31 ──> 35 ;  29,30 ──> 36
  S5(U), ADR 0007 ──> 37, 38, 39 ;  S5(U) ──> S6(U) ──> 39 ;  verificador na VPS (U, 39 passo 9A) ──> merge do 39
  1º deploy automático ──> PR de .claude/rules/infra.md + PR de status do ADR 0004 ──> 40(U)
  28b(U, condicional para 4 GB) depois do 31: só se um gatilho disparar no 31, 35, 50 ou 59

Fase 4
  25,28,40 ──> 41 ──> 42 ──> 43 ──> 44 ──> 45 ──> 46 ─┐
  30,41 ──> 47 ──> 48 ──> 49 ─────────────────────────┴─> 50(U)

Fase 5
  41,50 ──> 51 ──> 52 ──> 53 ──> 54 ──> 55 ──> 56
  44,45 ──────────────────^
  28,29 ──> 57          49,51 ──> 58
  54..58 ──> 59(U)
```

Paralelizável: 02 com 01; 18 a qualquer momento antes do 20; 13 com 14; 28 com 28a; as medições do 28a durante a janela D a D+7 do 27 (só leitura); 28b antes ou depois dos PRs 29 e 30 (são só código), sempre antes do 31; as Settings do S5 (5.1 a 5.6) a qualquer momento, e os checks required a partir de 2026-11-22; o S6 a qualquer momento depois do S5 (a opção (b2) só depois do item 38); 57 a partir da Fase 3; 47–49 em paralelo com 42–46.

Caminho crítico até ligar `raw.weather_forecast` (prioridade do doc): 01 → 03 → 05 → 06 → 07 → 08/09 → 10 → 11 → 13/14 → 15 → 16, com 02 → 04 → 12 em paralelo, e então 17. São 13 PRs de agente e 3 itens manuais; nenhum depende do ONS.

## Decisões resolvidas (2026-11-07 e 2026-11-08)

| Id | Pergunta | Decisão do usuário | Specs afetadas |
| --- | --- | --- | --- |
| P1 | Toolchain | **Aprovada**: uv, ruff, pytest, hatchling, Python 3.12, CI no GitHub Actions, pacotes na raiz. A instalação do `uv` e do Docker Desktop no Windows é conferida no passo 1 do 01 e nos riscos do 05 | 01, 05 |
| P2 | Dono e visibilidade dos repositórios | **Públicos, do próprio usuário**. A VPS puxa código e imagens do GHCR sem token de leitura; o score instala `models` sem token. Nenhum segredo no git, nem no histórico | 01, 02, 37, 38, 39, 40, 44, 46, 50 |
| P3 | VPS | **Resolvida em parte**: provedor "Regular Cloud Compute", 1 vCPU, 1 GB de RAM, 25 GB de SSD, 1 TB de transferência. Swap de 2 GB, `mem_limit` por serviço, checkpoint de memória 28a antes do PR 29. **Decisão de memória da Fase 3 (2026-11-08): o orçamento da Fase 3 não fecha em 1 GB; o upgrade para 2 GB (28b) é o padrão antes do item 31**, dispensável só com dispensa registrada pelo usuário e baseada na medição do 28a em D+7 ou depois; depois do 31, 28b para 4 GB só sob gatilho. Falta confirmar SO e arquitetura (`uname -m`), registrados no item 02 | 02, 03, 05, 10, 11, 16, 28a, 28b, 29, 30, 31, 34, 35, 39, 44, 46, 47, 50, 57, 59 |
| P4 | Rede | **Só Tailscale**. Sem domínio, sem proxy com autenticação, sem certificado público, sem 443 pública. HTTPS e acesso por `tailscale serve` (um hostname `*.ts.net`, uma porta por UI) (ADR 0003). A 22 pública fica aberta só no provisionamento e é fechada quando o SSH pela tailnet funciona | 02, 03, 04, 10, 12, 28, 29, 30, 31, 35, 38, 39, 40, 47, 50, 55, 56 |
| P5 | Coleta da previsão antes do ONS | **Aprovada**: 13–17 ficam antes do ONS, como planejado | 13, 14, 15, 17 |
| P15 | Postgres na tailnet | **Loopback + `tailscale serve --tcp=5432`**: `127.0.0.1:5432`, sem sidecar do Tailscale no compose e sem dependência da ordem de boot; o `After=tailscaled.service` deixa de ser necessário (ADR 0003) | 02, 03, 10, 12 |
| P6 | Deploy manual até a Fase 3 (2026-11-07) | **Aceito** como exceção registrada a "nada de SSH manual para mudar produção" (ADR 0004, `docs/adr/0004-interim-operation-before-prefect.md`). O item 38 é o último deploy manual completo. A exceção **termina no primeiro deploy automático bem-sucedido**, depois do merge do PR 39 (ADR 0007, item 8); entre o item 38 e esse deploy, só é permitido um único checkout manual de bootstrap (plano 39, passo 9B: `git fetch` + `git checkout --detach origin/main`, sem `docker`, com conferência de que o `HEAD` é o SHA do merge do PR 39 ou de um merge posterior revisado antes do "Re-run"), além da instalação do verificador de attestation (passo 9A), que não muda produção. Daí em diante, o merge na `main` é a única forma de mudar produção, salvo o procedimento de emergência do usuário (ADR 0007, item 12; plano 38) | 04, 12, 31, 35, 38, 39, 40 |
| P7 | Agendador interino e `restart` em `profiles` (2026-11-07) | **Supercronic no compose**; serviços em `profiles` (execução única) dispensam `restart: unless-stopped` (ADR 0004) | 11, 16 |
| P8 | `issued_at` e horizontes (2026-11-07) | **`date`, o primeiro snapshot vence, horizontes 1 a 7** (`horizon_days`). Guardar o horizonte 0 segue a avaliar com a cientista (ADR 0005, `docs/adr/0005-data-contract-v1.md`) | 13 |
| P9 | `ingested_at` no upsert (2026-11-07) | **Última escrita**, sem coluna nova (ADR 0005) | 08 |
| P18 | Formato de `location_id` (2026-11-07) | **Slug minúsculo** (`sao_paulo`) (ADR 0005) | 09 |
| P19 | Autenticação da API do Prefect (2026-11-08) | **Ligada desde o PR 30**: `PREFECT_API_AUTH` no `infra/.env` (formato `admin:<senha>`), que vira `PREFECT_SERVER_API_AUTH_STRING` no `prefect-server` e `PREFECT_API_AUTH_STRING` nos clientes (`jobs`, `prefect-worker`, PR 34). `/api/health`, `/api/ready`, `/ui-settings` e a UI ficam fora da autenticação (comportamento do Prefect, confirmado no passo 0 do PR 30). Segunda camada além da ACL; registrada no ADR 0008 ("Agendamento e execução pelo Prefect", item 2) | 28b, 30, 31, 33, 34, 35, 39 |

## Pontos de decisão em aberto para o usuário

Decidir antes do PR indicado. Os marcados com ADR precisam do ADR aprovado antes do código. A numeração P6–P18 foi mantida (a P15, a P6, a P7, a P8, a P9 e a P18 estão em "Decisões resolvidas") para não quebrar as referências nas specs.

| Id | Pergunta | Recomendação deste plano | Bloqueia |
| --- | --- | --- | --- |
| P10 | Backfill de previsões passadas pela API "Historical Forecast" do Open-Meteo? O doc exclui | Fora do escopo agora; vale uma conversa com a cientista, porque resolveria a "decisão dela" sobre treinar com previsão | — |
| P11 | Onde vive o modelo de teste (média móvel)? | No repo `models`, com PR aprovado por ela | 50 |
| P12 (ADR de execução) | Como o score sabe a versão do pacote `models`? Esquema de tags do repo `models` | Tag `models_package=<tag git>` na versão do modelo no MLflow; semver | 43, 44 |
| P13 (ADR de execução) | Tipo de `conn` em `build_features`; objeto `model` em `predict`; colunas extras na saída; versão do MLflow igual em servidor, notebook e score | `sqlalchemy.Connection`; `mlflow.pyfunc.load_model`; saída estrita; mesma versão. Até o ADR, a regra prática é "cliente na mesma versão do servidor", comunicada no item 31 | 42 |
| P14 (ADR de contrato) | De onde vem o "real" do monitoramento? | Função `load_actuals(conn, target_date)` no módulo dela | 53 |
| P16 (ADR) | Backup: destino (B2 ou S3), agendamento (systemd no host ou Prefect), criptografia | B2, systemd, avaliar `rclone crypt` | 57, 59 |
| P17 | Monitor externo para quando o próprio Prefect cair? Com rede só Tailscale, um monitor de uptime externo não alcança a VPS | Heartbeat de saída: o vigia pinga um serviço tipo healthchecks.io; a falta do ping gera o aviso | 56 |
| P20 (S6) | Âncora de confiança (ADR 0007, item 11): (b1) credenciais dos agentes sem poder de merge nem de aprovar deployment, ou (b2) mantenedor como required reviewer de `production` | (b1) com conta separada e contexto separado para os agentes; (b2) só se (b1) não for viável, com o risco residual registrado | 39 |

Perguntas menores, registradas na seção 9 de cada spec: gravar dado fora de faixa antes de falhar (15); o Prefect OSS não tem papéis de usuário, então não há "só leitura" para a cientista, e a 4200 só é liberada a ela no item 50 (30, 31); uma credencial ou dois workers para ingestão e score, lembrando o custo de memória (34, 46); montar `/` do host no worker para medir disco (56); checar memória no vigia (56); ligar o recurso "Tailscale SSH" exigiria replanejar 38 e 39 (02, 39); restrição de portas do `tailscale serve` na versão instalada (03); `gh` ou `cosign` como verificador e se o `gh` verifica sem login na VPS (39, Q1 e Q2); claim `job_workflow_ref` no painel do Tailscale (38, Q2).

## ADRs já escritos

- `docs/adr/0001-english-naming-convention.md`: convenção de nomes em inglês. Pendência documental (plano 28, seção 9): o plano 28 usa `ingestion/service_databases.py`, `ensure_service_database(...)` e `tests/test_service_databases.py` no lugar dos nomes da tabela do ADR, e as migrações de previsões e métricas passam a `0009` e `0010`; o usuário acrescenta uma nota ao ADR num PR só de `docs/**` (ou aceita que os planos prevaleçam). Não bloqueia o PR 28.
- `docs/adr/0002-python-toolchain-and-package-layout.md`: toolchain Python e layout de pacotes (P1).
- `docs/adr/0003-tailscale-only-network.md`: rede só Tailscale (P4, P15).
- `docs/adr/0004-interim-operation-before-prefect.md`: operação interina, deploy manual e supercronic (P6, P7). Com ele mergeado, os PRs 11 e 16 deixam de estar bloqueados por esse ADR. A atualização de status (`superseded` no agendador, pelo ADR 0008, e no deploy, pelo ADR 0007) vai num **único PR só de `docs/**` logo depois do primeiro deploy automático bem-sucedido do PR 39**, aberto junto do PR que remove a exceção de deploy manual de `.claude/rules/infra.md` (este não é só `docs/**` e passa pelo `code-reviewer` e pelo `pr-reviewer`). Os PRs 36 e 39 não editam o ADR.
- `docs/adr/0005-data-contract-v1.md`: contrato de dados v1 de `raw` e `ref` (P8, P9, P18). Com ele mergeado, os PRs 09 e 13 deixam de estar bloqueados por esse ADR.
- `docs/adr/0006-security-validation-in-ci.md`: validação de segurança no CI (pin por SHA e digest, Dependabot, `security.yml`, regra `S` do ruff, Settings, checks required, segredos só no environment `production`). Base dos itens S1 a S5 e R1; o item manual de Settings previsto no item 1 do ADR é o `docs/plans/S5-settings-seguranca-manual.md`.
- `docs/adr/0007-delivery-pipeline.md` ("Pipeline de entrega", escrito em 2026-11-09 pela skill `generate-adr`, com revisão de segurança; status Aceito; **ainda não mergeado** na `main` em `7fc1923`): publicação no GHCR por digest com Trivy bloqueante e attestation; compose de produção por digest; federação OIDC do Tailscale com subject e claim `job_workflow_ref`; SSH com chave restrita; `deploy.sh` com validação, trava, fast-forward, janela, verificação de attestation antes do `pull`, `pg_dump` antes de migrar, rollback com exceções e `.deploy/history.log`; segredos só no environment `production`; `harden-runner` só no `publish` (desvio do ADR 0006); fim da exceção do ADR 0004 no primeiro deploy automático, com bootstrap conferido; upgrades de schema; critério de saída do S5 antes do PR 37; âncora de confiança (S6); emergência; rotação e revogação. **Bloqueia 37, 38 e 39** até o merge.
- `docs/adr/0008-prefect-scheduling-and-execution.md` ("Agendamento e execução pelo Prefect", escrito em 2026-11-09 pela skill `generate-adr`; status Aceito; **ainda não mergeado** na `main` em `7fc1923`): Prefect 3 server só na tailnet, API autenticada (P19), worker e agendas em código, substituição do agendador interino do ADR 0004. **Bloqueia 33, 34 e 35** até o merge.

## ADRs a escrever (o planner não escreve ADR)

O número de cada ADR é dado quando ele for escrito. Cada um é escrito pelo usuário ou pela skill `generate-adr`, em PR próprio, e precisa estar mergeado antes de a implementação que ele bloqueia começar. Os antigos itens "Agendamento e execução pelo Prefect" e "Pipeline de entrega" foram escritos como ADR 0008 e ADR 0007 (seção acima).

1. Execução de modelos (P12, P13) — antes do 42; precisa da concordância da cientista.
2. Fonte do real no monitoramento (P14) — antes do 53; precisa da concordância dela.
3. Backup (P16) — antes do 57.

## Desvios em relação às instruções do `task-planner`

- Nome dos arquivos: `NN-<slug>.md` (pedido nesta tarefa) em vez de `<AAAA-MM-DD>-<slug>.md`. Os itens 28a e 28b foram inseridos sem renumerar os demais; os itens S1 a S6, H1 e R1 seguem o mesmo desvio (`S<n>-<slug>.md`, `H1-<slug>.md`, `R1-<slug>.md`).
- "Uma fase por vez": as specs 13–17 são da Fase 2 e vêm antes do fim da Fase 1, pela prioridade do doc. **Aprovado pelo usuário em 2026-11-07 (P5).**
- As specs referenciam arquivos criados por PRs anteriores (pelo caminho no repo) em vez de colar o código, porque esse código ainda não existe; quando a spec for executada, ele existirá na `main`.
