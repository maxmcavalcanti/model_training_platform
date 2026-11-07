# Plataforma ML — Infra e Dados

Nov 7, 2026 · @Maximiliano

## Visão geral

A plataforma entrega dados diários confiáveis, um registro de modelos e uma esteira que roda os modelos sozinha; a ciência de dados entrega modelos que cumprem um contrato e cuida deles depois. A regra de fronteira: **eu cuido de "o job rodou?", ela cuida de "o modelo está certo?"**.

| Camada | Dono | O que significa "pronto" |
| --- | --- | --- |
| VPS, rede, backups, segredos | Plataforma | Serviços sobem com um comando e voltam após reboot |
| Ingestão e dados brutos (`raw`, `ref`) | Plataforma | Dado do dia chega todo dia, sem duplicata, com checagem de qualidade |
| MLflow, orquestrador, CI/CD | Plataforma | Ela registra um modelo e ele entra em produção sem ninguém fazer deploy à mão |
| Features, treino, avaliação, promoção | Ciência de dados | Modelo bate o baseline em backtest e está marcado como `champion` |
| Execução diária do score | Plataforma (executa) / CD (código) | Previsão do dia gravada em `predictions` |
| Métricas e decisão de retreino | Ciência de dados | Painel mostra erro real × previsto e há regra escrita de quando retreinar |

&#91;embedded content: fluxo da plataforma · 9 componentes, 2 donos\]

A faixa do meio é dela; o resto é meu. O único ponto de passagem é o alias `champion` no MLflow.

## Fontes de dados

Duas fontes públicas, gratuitas e diárias, que se conversam: o clima explica boa parte da carga de energia, então a mesma base serve a dois modelos diferentes.

| Fonte | O que traz | Acesso | Granularidade | Observações |
| --- | --- | --- | --- | --- |
| [ONS — Carga de Energia Diária](https://registry.opendata.aws/ons-opendata-portal/) | Carga por subsistema (SE/CO, S, NE, N) em MWmed | Bucket S3 público `ons-aws-prod-opendata`, prefixo `dataset/carga_energia_di/`, sem conta AWS | 1 linha por subsistema por dia | O [MCP do próprio ONS](https://pypi.org/project/mcp-tiago-dados-abertos) lê esses arquivos em parquet direto do S3 |
| [Open-Meteo](https://dev.to/0012303/open-meteo-has-a-free-api-get-weather-data-for-any-location-without-an-api-key-2028) — previsão | Previsão diária: temperatura máx/mín, chuva, vento, umidade | `api.open-meteo.com/v1/forecast`, sem chave | Até 16 dias à frente | Gratuito para uso não comercial, limite justo de \~10 mil chamadas/dia |
| [Open-Meteo](https://openmeteo.substack.com/i/64601201/how-data-are-stored-and-made-available-through-api) — histórico | Clima observado (reanálise ERA5) | `archive-api.open-meteo.com/v1/archive` | Diário, desde 1940 | Serve para backfill e para o "real" do modelo de clima |

**Detalhe que muda tudo:** guardar a previsão do tempo **como ela estava no dia em que foi emitida**. O modelo de carga só pode usar, no dia D, a previsão disponível em D — usar o clima observado de D+1 seria vazamento de dados. Por isso existe uma tabela só de snapshots de previsão, e o histórico dela começa a contar no dia em que a ingestão ligar.

**Locais de clima (proposta):** uma capital por subsistema — São Paulo (SE/CO), Porto Alegre (S), Recife (NE), Belém (N). Fica numa tabela de referência, então dá para adicionar cidades sem mexer em código.

**Para verificar antes da Fase 1:**

- [ ] Com que atraso o ONS publica o dia anterior, e se revisa dados já publicados
- [ ] Atraso do arquivo ERA5 do Open-Meteo para os dias mais recentes

## Stack na VPS

Tudo roda num único `docker compose`, com ferramentas open source que ela vai encontrar em empresas de verdade.

| Serviço | Para quê | Quem usa | Notas |
| --- | --- | --- | --- |
| PostgreSQL 16 | Dados brutos, features, previsões, métricas; também é backend do MLflow e do Prefect | Os dois | Um banco por serviço (`ml`, `mlflow`, `prefect`) |
| MLflow | Tracking de experimentos + model registry | Ela (principal) | Artefatos em volume local servidos pelo próprio MLflow (`--serve-artifacts`); MinIO só se crescer |
| Prefect 3 (server + worker) | Agenda e executa os jobs; UI com histórico de execuções e logs | Os dois | Dagster é alternativa válida; Prefect é mais simples para começar |
| Grafana | Painéis de dados, previsões e erro; alertas | Os dois | Lê o Postgres com usuário somente leitura |
| Caddy | Proxy reverso com HTTPS automático | Plataforma | MLflow e Prefect não têm autenticação própria: nunca expor sem proxy com auth |
| Tailscale | Acesso privado à VPS e às UIs | Os dois | Alternativa a abrir portas; ela acessa Postgres e MLflow do notebook local como se fosse rede local |

**Onde ela trabalha:** localmente, no notebook dela, conectada via Tailscale ao Postgres (usuário próprio) e ao MLflow da VPS. Não precisa de Jupyter no servidor.

**Tamanho da VPS:** estimativa de 4 GB de RAM como mínimo confortável para essa stack; treino de modelos tabulares desse porte é leve. Confirmar com `docker stats` depois da Fase 3.

## Repositórios

Dois repositórios, um por dono: assim a fronteira fica visível no próprio GitHub, igual em uma empresa.

**`platform`** (meu)

```
plataforma/
├── infra/
│   ├── docker-compose.yml
│   ├── caddy/Caddyfile
│   └── scripts/          # bootstrap da VPS, backup, restore
├── migrations/           # Alembic: schemas raw, ref, features, predictions, monitoring
├── ingestion/
│   ├── ons.py            # carga diária
│   ├── openmeteo.py      # previsão + observado
│   └── checks.py         # validações (pandera)
├── flows/                # flows Prefect: ingestão, score, monitoramento
├── tests/
└── .github/workflows/    # ci.yml, deploy.yml
```

**`models`** (dela)

```
modelos/
├── notebooks/            # exploração; nunca importados por produção
├── src/models/
│   ├── load_d1/         # features.py, train.py, predict.py, evaluate.py
│   └── rain_d1/
├── tests/
├── pyproject.toml        # pacote instalável, dependências fixadas
└── .github/workflows/ci.yml
```

O job de score da plataforma instala o pacote `models` numa versão marcada (tag) e chama as funções do contrato. Ela nunca precisa mexer no repositório `platform` para colocar um modelo novo em produção.

## Modelo de dados

Um schema por responsabilidade no banco `ml`; as permissões seguem a mesma divisão, então ninguém altera sem querer o que é do outro.

| Tabela | Colunas principais | Chave | Escreve | Lê |
| --- | --- | --- | --- | --- |
| `ref.locations` | `location_id`, `name`, `lat`, `lon`, `subsystem` | `location_id` | Plataforma | Todos |
| `ref.calendar` | `date`, `weekday`, `is_national_holiday`, `holiday_name` | `date` | Plataforma (lib `holidays`) | Todos |
| `raw.ons_daily_load` | `subsystem`, `date`, `load_avg_mw`, `ingested_at` | (`subsystem`, `date`) | Plataforma | Todos |
| `raw.weather_observed` | `location_id`, `date`, `temp_max`, `temp_min`, `precip_mm`, `wind_speed_max`, `humidity_mean`, `ingested_at` | (`location_id`, `date`) | Plataforma | Todos |
| `raw.weather_forecast` | `location_id`, `issued_at`, `target_date`, `horizon_days`, mesmas variáveis, `ingested_at` | (`location_id`, `issued_at`, `target_date`) | Plataforma | Todos |
| `features.*` | Definidas por ela | Definidas por ela | Ciência de dados | Todos |
| `predictions.model_predictions` | `model_name`, `model_version`, `key`, `target_date`, `predicted_value`, `generated_at` | (`model_name`, `key`, `target_date`, `generated_at`) | Job de score | Todos |
| `monitoring.model_metrics` | `model_name`, `model_version`, `date`, `metric`, `value` | (`model_name`, `date`, `metric`) | Job de monitoramento | Todos |

`key` é o que o modelo prevê: o subsistema no modelo de carga, o `location_id` no de chuva. Assim uma única tabela de previsões serve a todos os modelos.

**Usuários do Postgres:** `ingestor` (escreve `raw` e `ref`), `scientist` (lê tudo, escreve `features`), `scorer` (escreve `predictions` e `monitoring`), `reader` (Grafana).

## Ingestão

Cada job é idempotente e reprocessável por data: rodar duas vezes o mesmo dia dá o mesmo resultado, e um backfill é só o mesmo job com um intervalo maior.

| Horário (BRT) | Job | O que faz |
| --- | --- | --- |
| 06:30 | `ingest_weather_forecast` | Snapshot da previsão para os próximos 7 dias, um registro por local e data-alvo, com `issued_at` = hoje |
| 06:45 | `ingest_weather_observed` | Upsert dos últimos 10 dias de clima observado (cobre atraso e correções da fonte) |
| 07:00 | `ingest_ons_load` | Lê o parquet do ano corrente no S3 e faz upsert dos últimos 30 dias (cobre revisões do ONS) |
| 07:30 | `score_models` | Para cada modelo com `champion`, gera previsões do dia (ver Contrato) |
| 08:00 | `monitor_models` | Junta previsões antigas com o real que chegou e grava métricas |

Os horários são um ponto de partida; ajustar depois de verificar quando o ONS publica.

**Regras de todos os jobs:**

- Upsert por chave primária (`INSERT … ON CONFLICT DO UPDATE`), nunca `append` cego
- Coluna `ingested_at` em toda linha, para saber quando cada dado entrou
- Checagem depois de gravar: linhas esperadas por dia, sem nulos nas colunas-chave, valores dentro de faixas plausíveis (carga positiva, temperatura entre −10 e 50 °C)
- Falha de checagem = execução falha no Prefect = alerta no Telegram
- Retry com backoff para erro de rede (3 tentativas)

**Backfill inicial:** carga do ONS e clima observado desde 2015 (cerca de 10 anos dá sazonalidade de sobra). Previsões históricas não entram no backfill: essa tabela só cresce a partir de agora, por isso ligá-la primeiro é prioridade.

## Contrato com a ciência de dados

O contrato é o que deixa os dois trabalharem sem depender um do outro no dia a dia: enquanto ele for cumprido, ela troca o modelo inteiro sem me chamar e eu troco a infra sem quebrar o modelo dela.

**O que ela entrega, por modelo** (módulo em `src/models/<nome>/`):

```python
def build_features(conn, ref_date: date) -> pd.DataFrame: ...
    # lê raw/ref; só usa dados disponíveis até ref_date (sem vazamento)

def predict(model, features: pd.DataFrame) -> pd.DataFrame: ...
    # devolve colunas: chave, target_date, predicted_value

def evaluate(previsto: pd.DataFrame, real: pd.DataFrame) -> dict[str, float]: ...
    # ex.: {"mape": 3.1, "mae": 1520.0}
```

O treino (`train.py`) roda onde ela quiser e termina registrando o modelo no MLflow com o nome do módulo (`load_d1`).

**O que a plataforma garante:**

1. Todo dia, o job de score busca `models:/<nome>@champion` no MLflow, chama `build_features` → `predict` e grava em `predictions.model_predictions`.
2. O job de monitoramento cruza previsões com o real e grava o retorno de `evaluate` em `monitoring.model_metrics`.
3. Trocar o alias `champion` para outra versão é o deploy. Nenhum PR na plataforma, nenhuma ação minha.

**Regras de mudança:** schema de `raw` e `ref` só muda com aviso e migração; a assinatura das três funções só muda se combinarmos. Erro dentro do código dela aparece no Prefect com o traceback, e quem investiga é ela.

## CI/CD e operação

Merge na `main` é a única forma de algo mudar em produção, nos dois repositórios.

| Repositório | No PR | No merge na `main` |
| --- | --- | --- |
| `platform` | `ruff`, `pytest` com Postgres de serviço, `alembic upgrade` num banco vazio | Build da imagem → GHCR → SSH na VPS: `alembic upgrade head`, `docker compose pull && up -d`, registra deployments do Prefect |
| `models` | `ruff`, `pytest` (testes das funções do contrato com dados de amostra) | Cria tag de versão; o job de score passa a instalar essa versão |

**Operação:**

- **Segredos:** GitHub Secrets para o CI; `.env` na VPS fora do git, com permissão 600
- **Backups:** `pg_dump` diário dos três bancos + volume de artefatos do MLflow, enviados para fora da VPS (S3 ou Backblaze B2), retenção de 14 dias; testar um restore uma vez por mês
- **Alertas:** falha de flow no Prefect, disco acima de 80%, serviço fora do ar → Telegram
- **Rede:** firewall com só 22 e 443 abertos, ou nenhuma porta pública usando só Tailscale
- **Reboot:** `restart: unless-stopped` em todos os serviços; testar reiniciando a VPS

## Roadmap

A previsão do tempo entra no ar logo na Fase 2, porque cada dia sem coletar é histórico que não volta. Ela pode começar a explorar os dados assim que a Fase 1 terminar.

**Fase 0 — Base da VPS**

- [ ] Docker, firewall, Tailscale, usuário não-root
- [ ] Caddy com HTTPS e autenticação
- [ ] Pronto quando: um reboot traz tudo de volta sem intervenção

**Fase 1 — Banco e carga do ONS** → libera a exploração dela

- [ ] Postgres, migrações com Alembic, usuários e permissões
- [ ] `ref.locations`, `ref.calendar`
- [ ] Ingestão do ONS + backfill desde 2015 + checagens
- [ ] Pronto quando: ela consulta `raw.ons_daily_load` do notebook dela via Tailscale

**Fase 2 — Clima**

- [ ] `raw.weather_forecast` coletando todo dia (prioridade)
- [ ] `raw.weather_observed` + backfill desde 2015
- [ ] Pronto quando: 7 dias seguidos de snapshots sem falha

**Fase 3 — MLflow, Prefect e CI/CD** → libera o treino com registro

- [ ] MLflow e Prefect no compose, atrás do Caddy
- [ ] Ingestões migradas para flows do Prefect
- [ ] Pipelines do GitHub Actions nos dois repositórios
- [ ] Pronto quando: um merge na `main` chega à VPS sem eu entrar nela

**Fase 4 — Score e painéis** → libera o primeiro modelo em produção

- [ ] Job genérico de score lendo `@champion`
- [ ] Grafana com dados brutos e previsões
- [ ] Pronto quando: um modelo de teste (média móvel) grava previsões todo dia

**Fase 5 — Monitoramento e alertas**

- [ ] Job de monitoramento + `monitoring.model_metrics`
- [ ] Alertas no Telegram, backups com restore testado
- [ ] Pronto quando: o painel mostra erro real × previsto atualizando sozinho
