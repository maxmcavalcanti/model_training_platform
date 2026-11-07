# Índice dos planos: roadmap das Fases 0 a 5 em PRs atômicos

Nov 7, 2026. Fonte: `docs/plataforma-ml.md` (roadmap, modelo de dados, jobs, contrato, CI/CD) e `docs/guia-ciencia-de-dados.md` (lado do contrato).

Revisão v2 (2026-11-07): aplica as decisões P1 a P5 e a P15 do usuário (toolchain, repos públicos, VPS de 1 GB, rede só Tailscale, coleta da previsão antes do ONS). Ver "Decisões resolvidas".

## Como usar

- Cada linha **agente** tem uma spec `NN-<slug>.md` com as 10 seções do `task-planner`. Cada linha **usuário** tem um `NN-<slug>-manual.md` com checklist e verificação de pronto.
- Fluxo de cada PR de agente (`AGENTS.md`, "Fluxo de trabalho"): usuário aprova a spec → `test-writer` escreve os testes e mostra que falham pelo motivo certo → `task-implementer` implementa até ficarem verdes e refatora com a suíte verde → CI → `code-reviewer` → `pr-reviewer`.
- **Passo 0**: quando os testes importam uma dependência nova (ex.: SQLAlchemy no `conftest.py`), o primeiro commit da branch é do implementador, só com `uv add`, antes do test-writer. Assim o teste falha por comportamento ausente e não por import quebrado. As specs que precisam disso dizem "passo 0".
- Comandos que já existem (PR 01, ver `.github/workflows/ci.yml`): `uv sync` (no CI, `uv sync --locked`), `uv run ruff check .`, `uv run ruff format --check .` e `uv run pytest`. O Postgres de teste vem do PR 05 e `uv run alembic ...` do PR 06. Cada PR registra os seus na seção "Comandos" do `AGENTS.md`. Nenhuma spec usa comando que não exista no ponto em que ela roda.
- Uma spec por vez. Antes de começar uma spec, confira se as dependências da coluna "Depende de" já estão na `main` e se os ADRs que ela pede estão aprovados.

## Restrições que valem para todas as specs

- **Rede só Tailscale** (P4, 2026-11-07). Nenhuma porta pública: sem domínio, sem proxy com autenticação, sem certificado público. As UIs (MLflow, Prefect, Grafana e a rota de saúde) são publicadas só em `127.0.0.1` e expostas na tailnet por `tailscale serve`, num hostname `*.ts.net` com uma porta por UI (ADR 0003, `docs/adr/0003-tailscale-only-network.md`). O Postgres fica em `127.0.0.1:5432`, exposto na tailnet por `tailscale serve --tcp=5432` (P15). Nenhuma porta de serviço é publicada em `0.0.0.0`; os testes do PR 03 travam isso. A ACL do Tailscale é o controle de acesso.
- **VPS de 1 GB** (P3, 2026-11-07): 1 vCPU, 1 GB de RAM, 25 GB de SSD, 1 TB de transferência, provedor "Regular Cloud Compute", com 2 GB de swap (item 02) e `mem_limit` em todo serviço do compose (teste do PR 03). **As Fases 0 a 2 devem caber em 1 GB. Da Fase 3 em diante a memória é medida (checkpoint 28a antes do PR 29, e de novo nos itens 31, 35, 50 e 59) e pode exigir upgrade**, que só acontece sob necessidade (item 28b, condicional). Estimativas a medir, não fatos: Postgres 100–250 MB, MLflow 300–500 MB, Prefect server + worker 500–800 MB, Grafana 100–200 MB, Tailscale ~30 MB, job de ingestão com pandas 200–400 MB de pico.
- **Repositórios públicos** (P2, 2026-11-07), do próprio usuário. A VPS clona o repo e puxa as imagens do GHCR sem token nem `docker login`; o job de score instala o pacote `models` sem token. **Nenhum segredo entra no git, nem no histórico**: num repo público, um segredo commitado uma vez é público para sempre e precisa ser trocado (reescrever o histórico não basta). Segredos só no `infra/.env` da VPS (`chmod 600`, fora do git) e nos GitHub Secrets.

## Tabela

Legenda: **A** = agente implementa; **U** = usuário executa (VPS, Tailscale, contas, segredos, coordenação). "Antecipado" = item da Fase 2 feito antes do fim da Fase 1 (aprovado pelo usuário em 2026-11-07, P5).

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
| 28 | Bancos `mlflow` e `prefect` | 3 | 11 | A | sim | Backends prontos, idempotente |
| 28a | Checkpoint de memória da VPS | 3 | 27 | U | — | RAM medida com a stack da Fase 2; decisão registrada sobre o 28b |
| 28b | Upgrade da VPS (**condicional, só sob necessidade**) | 3+ | — (só se um gatilho do 28a, 31, 35, 50 ou 59 disparar) | U | — | VPS de 2 a 4 GB; verificação: `free -m` mostra a RAM nova |
| 29 | MLflow no compose | 3 | 03, 10, 28, 28a | A | sim | Tracking e registry só na tailnet |
| 30 | Prefect server no compose | 3 | 29 | A | sim | Orquestrador com UI só na tailnet |
| 31 | Subir MLflow e Prefect | 3 | 28, 28a, 29, 30 | U | — | **Ela registra experimentos no MLflow**; memória medida de novo |
| 32 | Flows de ingestão | 3 | 15, 22, 26, 30 | A | sim | Ingestões como flows do Prefect |
| 33 | Deployments do Prefect | 3 | 32 | A | sim | Agendas declaradas em código |
| 34 | Worker do Prefect | 3 | 33 | A | sim | Execução dos deployments na VPS |
| 35 | Cutover supercronic → Prefect | 3 | 31, 32, 33, 34 | U | — | Prefect agendando em produção |
| 36 | Remover o agendador interino | 3 | 34, 35 | A | sim | Uma fonte de verdade para horários |
| 37 | Imagens no GHCR | 3 | 34, 36 | A | sim | Build reproduzível a cada merge |
| 38 | Segredos do CI/CD | 3 | 37 | U | — | Acesso do CI à VPS via Tailscale, sem porta pública; pacotes do GHCR públicos, sem token de leitura |
| 39 | Deploy via SSH | 3 | 37, 38 | A | sim | Merge na `main` chega à VPS |
| 40 | Prova do deploy e CI do `models` | 3 | 36, 39 | U | — | **Fase 3 pronta** |
| 41 | `predictions.model_predictions` | 4 | 25, 40 | A | sim | Tabela única de previsões |
| 42 | Núcleo do score | 4 | 41 | A | sim | Contrato validado e gravado |
| 43 | Descobrir champions no MLflow | 4 | 42 | A | sim | Score genérico por alias |
| 44 | Executor isolado (`uv run --with`) | 4 | 43 | A | sim | Cada modelo roda com a sua versão do pacote |
| 45 | `flows.score_one` | 4 | 42, 43, 44 | A | sim | Ponta a ponta MLflow → pacote → banco |
| 46 | Flow `score_models` (07:30) | 4 | 45 | A | sim | Score diário de todos os champions |
| 47 | Grafana no compose | 4 | 30, 41 | A | sim | Painéis com usuário `reader`, só na tailnet |
| 48 | Painel de dados brutos | 4 | 47 | A | sim | Saúde das fontes visível |
| 49 | Painel de previsões | 4 | 48 | A | sim | Previsto × real visível |
| 50 | Modelo de teste e pronto da Fase 4 | 4 | 46, 47, 48, 49 | U | — | **Fase 4 pronta**: média móvel grava todo dia |
| 51 | `monitoring.model_metrics` | 5 | 41, 50 | A | sim | Tabela de métricas |
| 52 | Núcleo do monitoramento | 5 | 51 | A | sim | `evaluate` chamado e gravado |
| 53 | `flows.monitor_one` e fonte do real | 5 | 44, 45, 52 | A | sim | Real obtido e reavaliado em janela |
| 54 | Flow `monitor_models` (08:00) | 5 | 46, 53 | A | sim | Métricas diárias de todos os champions |
| 55 | Alertas no Telegram | 5 | 54 | A | sim | Falha de flow vira mensagem |
| 56 | Vigia de saúde | 5 | 55 | A | sim | Disco > 80% e serviço fora do ar viram mensagem |
| 57 | Backup e restore | 5 | 28, 29 | A | sim | Backup diário com restore provado no CI |
| 58 | Painel de erro | 5 | 49, 51 | A | sim | Erro real × previsto com médias móveis |
| 59 | Alertas, backups e pronto da Fase 5 | 5 | 54, 55, 56, 57, 58 | U | — | **Fase 5 pronta** |

Totais: 46 PRs de agente (45 com TDD; o 01 não tem, por ser o bootstrap) e 15 itens do usuário (um deles, o 28b, condicional).

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
  27(U) ──> 28a(U) ──┐
  11 ──> 28 ────────┴─> 29 ──> 30 ──> 31(U)
  28b(U, condicional): sem aresta; só se um gatilho disparar no 28a, 31, 35, 50 ou 59
  15,22,26,30 ──> 32 ──> 33 ──> 34 ──> 35(U) ──> 36 ──> 37 ──> 38(U) ──> 39 ──> 40(U)

Fase 4
  25,40 ──> 41 ──> 42 ──> 43 ──> 44 ──> 45 ──> 46 ─┐
  30,41 ──> 47 ──> 48 ──> 49 ──────────────────────┴─> 50(U)

Fase 5
  41,50 ──> 51 ──> 52 ──> 53 ──> 54 ──> 55 ──> 56
  44,45 ──────────────────^
  28,29 ──> 57          49,51 ──> 58
  54..58 ──> 59(U)
```

Paralelizável: 02 com 01; 18 a qualquer momento antes do 20; 13 com 14; 28 com 28a; 57 a partir da Fase 3; 47–49 em paralelo com 42–46.

Caminho crítico até ligar `raw.weather_forecast` (prioridade do doc): 01 → 03 → 05 → 06 → 07 → 08/09 → 10 → 11 → 13/14 → 15 → 16, com 02 → 04 → 12 em paralelo, e então 17. São 13 PRs de agente e 3 itens manuais; nenhum depende do ONS.

## Decisões resolvidas (2026-11-07)

| Id | Pergunta | Decisão do usuário | Specs afetadas |
| --- | --- | --- | --- |
| P1 | Toolchain | **Aprovada**: uv, ruff, pytest, hatchling, Python 3.12, CI no GitHub Actions, pacotes na raiz. A instalação do `uv` e do Docker Desktop no Windows é conferida no passo 1 do 01 e nos riscos do 05 | 01, 05 |
| P2 | Dono e visibilidade dos repositórios | **Públicos, do próprio usuário**. A VPS puxa código e imagens do GHCR sem token de leitura; o score instala `models` sem token. Nenhum segredo no git, nem no histórico | 01, 02, 37, 38, 39, 40, 44, 46, 50 |
| P3 | VPS | **Resolvida em parte**: provedor "Regular Cloud Compute", 1 vCPU, 1 GB de RAM, 25 GB de SSD, 1 TB de transferência. Swap de 2 GB, `mem_limit` por serviço, checkpoint de memória 28a antes do PR 29 e upgrade 28b só sob necessidade. Falta confirmar SO e arquitetura (`uname -m`), registrados no item 02 | 02, 03, 05, 10, 11, 16, 28a, 28b, 29, 30, 31, 34, 35, 44, 46, 47, 50, 57, 59 |
| P4 | Rede | **Só Tailscale**. Sem domínio, sem proxy com autenticação, sem certificado público, sem 443 pública. HTTPS e acesso por `tailscale serve` (um hostname `*.ts.net`, uma porta por UI) (ADR 0003). A 22 pública fica aberta só no provisionamento e é fechada quando o SSH pela tailnet funciona | 02, 03, 04, 10, 12, 28, 29, 30, 31, 35, 38, 39, 40, 47, 50, 55, 56 |
| P5 | Coleta da previsão antes do ONS | **Aprovada**: 13–17 ficam antes do ONS, como planejado | 13, 14, 15, 17 |
| P15 | Postgres na tailnet | **Loopback + `tailscale serve --tcp=5432`**: `127.0.0.1:5432`, sem sidecar do Tailscale no compose e sem dependência da ordem de boot; o `After=tailscaled.service` deixa de ser necessário (ADR 0003) | 02, 03, 10, 12 |

## Pontos de decisão em aberto para o usuário

Decidir antes do PR indicado. Os marcados com ADR precisam do ADR aprovado antes do código. A numeração P6–P18 foi mantida (a P15 está em "Decisões resolvidas") para não quebrar as referências nas specs.

| Id | Pergunta | Recomendação deste plano | Bloqueia |
| --- | --- | --- | --- |
| P6 (ADR) | Deploy manual (SSH + `git pull` + `compose up`) até a Fase 3, como exceção a "nada de SSH manual para mudar produção" | Aceitar como exceção temporária e registrada; termina no PR 39 | 04, 12 |
| P7 (ADR, junto com P6) | Agendador interino: supercronic no compose (recomendado) ou crontab do host? Serviços em `profiles` (execução única) dispensam `restart: unless-stopped`? | Supercronic; sim para a exceção de profiles | 11, 16 |
| P8 (ADR de contrato) | `issued_at` como `date` (um snapshot por dia, o primeiro vence) ou `timestamptz`? Guardar horizonte 0? | `date`, primeiro vence, horizontes 1 a 7; avaliar horizonte 0 com a cientista | 13 |
| P9 | `ingested_at` no upsert com atualização: "última escrita" ou "primeira entrada" + `updated_at`? | Última escrita (sem coluna nova) | 08 |
| P10 | Backfill de previsões passadas pela API "Historical Forecast" do Open-Meteo? O doc exclui | Fora do escopo agora; vale uma conversa com a cientista, porque resolveria a "decisão dela" sobre treinar com previsão | — |
| P11 | Onde vive o modelo de teste (média móvel)? | No repo `models`, com PR aprovado por ela | 50 |
| P12 (ADR de execução) | Como o score sabe a versão do pacote `models`? Esquema de tags do repo `models` | Tag `models_package=<tag git>` na versão do modelo no MLflow; semver | 43, 44 |
| P13 (ADR de execução) | Tipo de `conn` em `build_features`; objeto `model` em `predict`; colunas extras na saída; versão do MLflow igual em servidor, notebook e score | `sqlalchemy.Connection`; `mlflow.pyfunc.load_model`; saída estrita; mesma versão | 29, 42 |
| P14 (ADR de contrato) | De onde vem o "real" do monitoramento? | Função `load_actuals(conn, target_date)` no módulo dela | 53 |
| P16 (ADR) | Backup: destino (B2 ou S3), agendamento (systemd no host ou Prefect), criptografia | B2, systemd, avaliar `rclone crypt` | 57, 59 |
| P17 | Monitor externo para quando o próprio Prefect cair? Com rede só Tailscale, um monitor de uptime externo não alcança a VPS | Heartbeat de saída: o vigia pinga um serviço tipo healthchecks.io; a falta do ping gera o aviso | 56 |
| P18 (ADR de contrato) | Formato de `location_id` | Slug minúsculo (`sao_paulo`) | 09 |

Perguntas menores, registradas na seção 9 de cada spec: gravar dado fora de faixa antes de falhar (15); "só leitura" da cientista no Prefect não é garantido pelo OSS, e sem proxy a ACL é a única barreira (30); camada opcional de autenticação embutida do Prefect (30); uma credencial ou dois workers para ingestão e score, lembrando o custo de memória (46); montar `/` do host no worker para medir disco (56); checar memória no vigia (56); ligar o recurso "Tailscale SSH" exigiria replanejar 38 e 39 (02, 39); restrição de portas do `tailscale serve` na versão instalada (03).

## ADRs já escritos

- `docs/adr/0001-english-naming-convention.md`: convenção de nomes em inglês.
- `docs/adr/0002-python-toolchain-and-package-layout.md`: toolchain Python e layout de pacotes (P1).
- `docs/adr/0003-tailscale-only-network.md`: rede só Tailscale (P4, P15).

## ADRs a escrever (o planner não escreve ADR)

O número de cada ADR é dado quando ele for escrito.

1. Operação interina antes do Prefect: deploy manual e supercronic (P6, P7) — antes do 11/16; marcado `superseded` nos PRs 36 e 39.
2. Contrato de dados v1 de `raw` e `ref` (P8, P18) — antes do 09.
3. Execução de modelos (P12, P13) — antes do 42; precisa da concordância da cientista.
4. Fonte do real no monitoramento (P14) — antes do 53; precisa da concordância dela.
5. Backup (P16) — antes do 57.

## Desvios em relação às instruções do `task-planner`

- Nome dos arquivos: `NN-<slug>.md` (pedido nesta tarefa) em vez de `<AAAA-MM-DD>-<slug>.md`. Os itens 28a e 28b foram inseridos sem renumerar os demais.
- "Uma fase por vez": as specs 13–17 são da Fase 2 e vêm antes do fim da Fase 1, pela prioridade do doc. **Aprovado pelo usuário em 2026-11-07 (P5).**
- As specs referenciam arquivos criados por PRs anteriores (pelo caminho no repo) em vez de colar o código, porque esse código ainda não existe; quando a spec for executada, ele existirá na `main`.
