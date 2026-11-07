# Índice dos planos: roadmap das Fases 0 a 5 em PRs atômicos

Nov 7, 2026. Fonte: `docs/plataforma-ml.md` (roadmap, modelo de dados, jobs, contrato, CI/CD) e `docs/guia-ciencia-de-dados.md` (lado do contrato).

## Como usar

- Cada linha **agente** tem uma spec `NN-<slug>.md` com as 10 seções do `task-planner`. Cada linha **usuário** tem um `NN-<slug>-manual.md` com checklist e verificação de pronto.
- Fluxo de cada PR de agente (`AGENTS.md`, "Fluxo de trabalho"): usuário aprova a spec → `test-writer` escreve os testes e mostra que falham pelo motivo certo → `task-implementer` implementa até ficarem verdes e refatora com a suíte verde → CI → `code-reviewer` → `pr-reviewer`.
- **Passo 0**: quando os testes importam uma dependência nova (ex.: SQLAlchemy no `conftest.py`), o primeiro commit da branch é do implementador, só com `uv add`, antes do test-writer. Assim o teste falha por comportamento ausente e não por import quebrado. As specs que precisam disso dizem "passo 0".
- Os comandos (`uv sync`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`, `uv run alembic ...`) são criados pelos PRs 01, 05 e 06 e ficam na seção "Comandos" do `AGENTS.md`. Nenhuma spec usa comando que não exista no ponto em que ela roda.
- Uma spec por vez. Antes de começar uma spec, confira se as dependências da coluna "Depende de" já estão na `main` e se os ADRs que ela pede estão aprovados.

## Tabela

Legenda: **A** = agente implementa; **U** = usuário executa (VPS, DNS, contas, segredos, coordenação). "Antecipado" = item da Fase 2 feito antes do fim da Fase 1 (P5).

| Id | Título | Fase | Depende de | Quem | Testes | Valor entregue |
| --- | --- | --- | --- | --- | --- | --- |
| 01 | Bootstrap do ambiente (uv, ruff, pytest, CI) | 0 (repo) | — | A | não (verificação por comandos) | Todo PR seguinte tem lint, teste e CI reais |
| 02 | Provisionar a VPS | 0 | — | U | — | VPS com Docker, firewall, Tailscale, usuário não-root |
| 03 | Compose de produção com Caddy | 0 | 01 | A | sim | Proxy HTTPS com auth; testes que travam as regras de infra |
| 04 | Publicar Caddy e testar reboot | 0 | 02, 03 | U | — | **Fase 0 pronta**: reboot traz tudo de volta |
| 05 | Conexão Postgres e banco de teste | 1 | 01, 03 | A | sim | `criar_engine()`; Postgres descartável local e no CI |
| 06 | Alembic e schemas | 1 | 05 | A | sim | Migrações versionadas; CI roda `alembic upgrade head` |
| 07 | Papéis e permissões | 1 | 06 | A | sim | `ingestor`, `cientista`, `scorer`, `leitura` com privilégios padrão |
| 08 | Upsert idempotente | 1 | 07 | A | sim | Uma função única de upsert com `ingerido_em` |
| 09 | `ref.locais` | 1 | 07 | A | sim | As 4 capitais, base dos jobs de clima |
| 10 | Postgres no compose de produção | 1 | 03, 05 | A | sim | Banco na VPS exposto só no Tailscale |
| 11 | Imagem dos jobs e CLI | 1 | 06, 10 | A | sim | `python -m ingestion` e migrações rodando na VPS |
| 12 | Subir Postgres na VPS | 1 | 04, 09, 10, 11 | U | — | Banco migrado em produção; acesso da cientista via Tailscale |
| 13 | `raw.clima_previsao` | 2 (antecipado) | 09 | A | sim | Tabela de snapshots de previsão |
| 14 | Cliente da previsão Open-Meteo | 2 (antecipado) | 08 | A | sim | Busca a previsão com retry só para rede |
| 15 | Job `clima-previsao` | 2 (antecipado) | 11, 13, 14 | A | sim | Snapshot diário com checagem pandera |
| 16 | Agendador interino (supercronic) | 2 (antecipado) | 15 | A | sim | Job rodando sozinho às 06:30 |
| 17 | Ligar a coleta da previsão | 2 (antecipado) | 12, 13, 15, 16 | U | — | **Histórico de previsões começa a acumular** |
| 18 | Verificar as fontes (ONS, ERA5) | 1 | — | U | — | Atrasos e revisões conhecidos; horários e janelas ajustados |
| 19 | `ref.calendario` | 1 | 11, 15 | A | sim | Calendário com feriados nacionais |
| 20 | Leitura do parquet do ONS | 1 | 14, 18 | A | sim | Carga do ONS normalizada |
| 21 | `raw.ons_carga_diaria` | 1 | 19 | A | sim | Tabela de carga |
| 22 | Job `ons-carga` | 1 | 16, 20, 21 | A | sim | Ingestão diária (07:00) e backfill por intervalo |
| 23 | Backfill do ONS e pronto da Fase 1 | 1 | 12, 19, 22 | U | — | **Fase 1 pronta**: ela consulta a carga do notebook |
| 24 | Cliente do observado (ERA5) | 2 | 14, 18 | A | sim | Clima observado por intervalo |
| 25 | `raw.clima_observado` | 2 | 21 | A | sim | Tabela do observado |
| 26 | Job `clima-observado` | 2 | 16, 24, 25 | A | sim | Ingestão diária (06:45) e backfill |
| 27 | Backfill do observado e pronto da Fase 2 | 2 | 17, 26 | U | — | **Fase 2 pronta**: 7 dias de snapshots sem falha |
| 28 | Bancos `mlflow` e `prefect` | 3 | 11 | A | sim | Backends prontos, idempotente |
| 29 | MLflow no compose | 3 | 03, 10, 28 | A | sim | Tracking e registry atrás de auth |
| 30 | Prefect server no compose | 3 | 29 | A | sim | Orquestrador com UI atrás de auth |
| 31 | Subir MLflow e Prefect | 3 | 28, 29, 30 | U | — | **Ela registra experimentos no MLflow** |
| 32 | Flows de ingestão | 3 | 15, 22, 26, 30 | A | sim | Ingestões como flows do Prefect |
| 33 | Deployments do Prefect | 3 | 32 | A | sim | Agendas declaradas em código |
| 34 | Worker do Prefect | 3 | 33 | A | sim | Execução dos deployments na VPS |
| 35 | Cutover supercronic → Prefect | 3 | 31, 32, 33, 34 | U | — | Prefect agendando em produção |
| 36 | Remover o agendador interino | 3 | 34, 35 | A | sim | Uma fonte de verdade para horários |
| 37 | Imagens no GHCR | 3 | 34, 36 | A | sim | Build reproduzível a cada merge |
| 38 | Segredos do CI/CD | 3 | 37 | U | — | Acesso do CI à VPS via Tailscale, sem porta extra |
| 39 | Deploy via SSH | 3 | 37, 38 | A | sim | Merge na `main` chega à VPS |
| 40 | Prova do deploy e CI do `modelos` | 3 | 36, 39 | U | — | **Fase 3 pronta** |
| 41 | `predictions.previsoes` | 4 | 25, 40 | A | sim | Tabela única de previsões |
| 42 | Núcleo do score | 4 | 41 | A | sim | Contrato validado e gravado |
| 43 | Descobrir champions no MLflow | 4 | 42 | A | sim | Score genérico por alias |
| 44 | Executor isolado (`uv run --with`) | 4 | 43 | A | sim | Cada modelo roda com a sua versão do pacote |
| 45 | `flows.score_um` | 4 | 42, 43, 44 | A | sim | Ponta a ponta MLflow → pacote → banco |
| 46 | Flow `score_modelos` (07:30) | 4 | 45 | A | sim | Score diário de todos os champions |
| 47 | Grafana no compose | 4 | 30, 41 | A | sim | Painéis com usuário `leitura` |
| 48 | Painel de dados brutos | 4 | 47 | A | sim | Saúde das fontes visível |
| 49 | Painel de previsões | 4 | 48 | A | sim | Previsto × real visível |
| 50 | Modelo de teste e pronto da Fase 4 | 4 | 46, 47, 48, 49 | U | — | **Fase 4 pronta**: média móvel grava todo dia |
| 51 | `monitoring.metricas` | 5 | 41, 50 | A | sim | Tabela de métricas |
| 52 | Núcleo do monitoramento | 5 | 51 | A | sim | `evaluate` chamado e gravado |
| 53 | `flows.monitor_um` e fonte do real | 5 | 44, 45, 52 | A | sim | Real obtido e reavaliado em janela |
| 54 | Flow `monitorar_modelos` (08:00) | 5 | 46, 53 | A | sim | Métricas diárias de todos os champions |
| 55 | Alertas no Telegram | 5 | 54 | A | sim | Falha de flow vira mensagem |
| 56 | Vigia de saúde | 5 | 55 | A | sim | Disco > 80% e serviço fora do ar viram mensagem |
| 57 | Backup e restore | 5 | 28, 29 | A | sim | Backup diário com restore provado no CI |
| 58 | Painel de erro | 5 | 49, 51 | A | sim | Erro real × previsto com médias móveis |
| 59 | Alertas, backups e pronto da Fase 5 | 5 | 54, 55, 56, 57, 58 | U | — | **Fase 5 pronta** |

Totais: 46 PRs de agente (45 com TDD; o 01 não tem, por ser o bootstrap) e 13 itens do usuário.

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
  11 ──> 28 ──> 29 ──> 30 ──> 31(U)
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

Paralelizável: 02 com 01; 18 a qualquer momento antes do 20; 13 com 14; 57 a partir da Fase 3; 47–49 em paralelo com 42–46.

Caminho crítico até ligar `raw.clima_previsao` (prioridade do doc): 01 → 03 → 05 → 06 → 07 → 08/09 → 10 → 11 → 13/14 → 15 → 16, com 02 → 04 → 12 em paralelo, e então 17. São 13 PRs de agente e 3 itens manuais; nenhum depende do ONS.

## Pontos de decisão em aberto para o usuário

Decidir antes do PR indicado. Os marcados com ADR precisam do ADR aprovado antes do código.

| Id | Pergunta | Recomendação deste plano | Bloqueia |
| --- | --- | --- | --- |
| P1 | Aprovar a toolchain (uv, ruff, pytest, hatchling, Python 3.12, pacotes na raiz). O `uv` e o Docker Desktop estão instalados no Windows? | Aprovar; instalar os dois | 01, 05 |
| P2 | Dono e nome dos repositórios no GitHub; `plataforma` e `modelos` são privados? | Definir; se privados, tokens só leitura (itens 38 e 50) | 37, 38, 44 |
| P3 | Provedor, SO, tamanho e arquitetura (amd64/arm64) da VPS | Ubuntu 24.04 LTS, 4 GB, amd64 | 02, 16 |
| P4 (ADR) | Rede: 22 e 443 públicas com domínio, ou só Tailscale? Qual domínio? | Pública com domínio próprio: subdomínios para MLflow, Prefect e Grafana ficam simples; Postgres só no Tailscale | 03, 29 |
| P5 | Antecipar a coleta de `raw.clima_previsao` (Fase 2) para antes do ONS (Fase 1)? `AGENTS.md` diz "uma fase por vez" | Sim: o doc diz que cada dia sem coletar é histórico perdido, e o caminho não depende do ONS. Se não aprovar, mover 13–17 para depois do 23 | 13 |
| P6 (ADR) | Deploy manual (SSH + `git pull` + `compose up`) até a Fase 3, como exceção a "nada de SSH manual para mudar produção" | Aceitar como exceção temporária e registrada; termina no PR 39 | 04, 12 |
| P7 (ADR, junto com P6) | Agendador interino: supercronic no compose (recomendado) ou crontab do host? Serviços em `profiles` (execução única) dispensam `restart: unless-stopped`? | Supercronic; sim para a exceção de profiles | 11, 16 |
| P8 (ADR de contrato) | `emitida_em` como `date` (um snapshot por dia, o primeiro vence) ou `timestamptz`? Guardar horizonte 0? | `date`, primeiro vence, horizontes 1 a 7; avaliar horizonte 0 com a cientista | 13 |
| P9 | `ingerido_em` no upsert com atualização: "última escrita" ou "primeira entrada" + `atualizado_em`? | Última escrita (sem coluna nova) | 08 |
| P10 | Backfill de previsões passadas pela API "Historical Forecast" do Open-Meteo? O doc exclui | Fora do escopo agora; vale uma conversa com a cientista, porque resolveria a "decisão dela" sobre treinar com previsão | — |
| P11 | Onde vive o modelo de teste (média móvel)? | No repo `modelos`, com PR aprovado por ela | 50 |
| P12 (ADR de execução) | Como o score sabe a versão do pacote `modelos`? Esquema de tags do repo `modelos` | Tag `pacote_modelos=<tag git>` na versão do modelo no MLflow; semver | 43, 44 |
| P13 (ADR de execução) | Tipo de `conn` em `build_features`; objeto `model` em `predict`; colunas extras na saída; versão do MLflow igual em servidor, notebook e score | `sqlalchemy.Connection`; `mlflow.pyfunc.load_model`; saída estrita; mesma versão | 29, 42 |
| P14 (ADR de contrato) | De onde vem o "real" do monitoramento? | Função `carregar_real(conn, data_alvo)` no módulo dela | 53 |
| P15 | Postgres publicado no IP do Tailscale (depende da ordem de boot) ou sidecar do Tailscale no compose? | IP do Tailscale com `After=tailscaled.service`; trocar se o reboot falhar | 10, 12 |
| P16 (ADR) | Backup: destino (B2 ou S3), agendamento (systemd no host ou Prefect), criptografia | B2, systemd, avaliar `rclone crypt` | 57, 59 |
| P17 | Monitor externo de uptime para quando o próprio Prefect cair? | Sim, um serviço gratuito batendo em `/saude` | 56 |
| P18 (ADR de contrato) | Formato de `local_id` | Slug minúsculo (`sao_paulo`) | 09 |

Perguntas menores, registradas na seção 9 de cada spec: gravar dado fora de faixa antes de falhar (15); "só leitura" da cientista no Prefect não é garantido pelo OSS (30); uma credencial ou dois workers para ingestão e score (46); montar `/` do host no worker para medir disco (56); dupla autenticação no Grafana (47).

## ADRs a escrever (o planner não escreve ADR)

1. Toolchain Python e layout de pacotes (P1) — antes do 01.
2. Exposição de rede (P4) — antes do 03.
3. Operação interina antes do Prefect: deploy manual e supercronic (P6, P7) — antes do 11/16; marcado `superseded` nos PRs 36 e 39.
4. Contrato de dados v1 de `raw` e `ref` (P8, P18) — antes do 09.
5. Execução de modelos (P12, P13) — antes do 42; precisa da concordância da cientista.
6. Fonte do real no monitoramento (P14) — antes do 53; precisa da concordância dela.
7. Backup (P16) — antes do 57.

## Desvios em relação às instruções do `task-planner`

- Nome dos arquivos: `NN-<slug>.md` (pedido nesta tarefa) em vez de `<AAAA-MM-DD>-<slug>.md`.
- "Uma fase por vez": as specs 13–17 são da Fase 2 e vêm antes do fim da Fase 1, pela prioridade do doc. Depende de P5.
- As specs referenciam arquivos criados por PRs anteriores (pelo caminho no repo) em vez de colar o código, porque esse código ainda não existe; quando a spec for executada, ele existirá na `main`.
