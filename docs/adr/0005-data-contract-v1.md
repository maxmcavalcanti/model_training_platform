# ADR 0005: Contrato de dados v1 de `raw` e `ref`

Status: Aceito
Data: 2026-11-07
Decisores: Maximiliano

## Contexto

Mudança em `raw` ou `ref` é mudança de contrato e exige migração Alembic, ADR e aviso à ciência de dados (`AGENTS.md`, "Fronteira"). Criar as primeiras tabelas dessas camadas fixa esse contrato, e a cientista de dados consulta `raw` e `ref` direto. O usuário decidiu em 2026-11-07 três pontos que estavam em aberto no índice (`docs/plans/00-indice.md`):

- P8: semântica de `issued_at` e faixa de horizontes de `raw.weather_forecast`.
- P9: semântica de `ingested_at` quando o upsert atualiza uma linha.
- P18: formato de `location_id`.

Os nomes seguem o ADR 0001 (convenção de nomes em inglês). Este ADR foi escrito pelo `task-implementer` por instrução expressa do usuário, como exceção à regra do `AGENTS.md` ("Nenhum agente escreve ADR"). A exceção vale só para este ADR e para o 0004.

## Decisão

### `issued_at` e snapshots de previsão (P8)

Em `raw.weather_forecast`, `issued_at` é do tipo `date`: o dia em que o snapshot da previsão foi tirado, não um instante. Há no máximo um snapshot por local e data-alvo por dia: a chave primária é (`location_id`, `issued_at`, `target_date`), e quando o job roda de novo no mesmo dia **o primeiro snapshot vence** (insert que ignora o conflito, nunca sobrescreve). Previsão é guardada como emitida; um snapshot antigo nunca é reescrito.

`horizon_days` é a distância em dias entre `target_date` e `issued_at`, e o job grava os horizontes de **1 a 7**.

### `ingested_at` é a última escrita (P9)

`ingested_at` guarda o momento da **última escrita** da linha, carimbado pelo relógio do servidor no insert e, nos upserts que atualizam, também no `SET` do conflito. Não há coluna nova (nenhum `updated_at`): a "primeira entrada" não é registrada. Nas tabelas com insert que ignora o conflito (como `raw.weather_forecast`), a linha preserva o `ingested_at` da primeira e única escrita.

### `location_id` é um slug minúsculo (P18)

`location_id` é texto em slug minúsculo, sem acento e sem espaço, por exemplo `sao_paulo`, `porto_alegre`, `recife`, `belem`. É a chave de `ref.locations` e a chave estrangeira em `raw.weather_observed` e `raw.weather_forecast`, e aparece como `key` de modelos de chuva em `predictions.model_predictions`. Um valor fora do formato (por exemplo `São Paulo`) é recusado pela tabela.

## Consequências

- O ADR cobre as tabelas dos PRs 09 (`ref.locations`), 13 (`raw.weather_forecast`), 19 (`ref.calendar`), 21 (`raw.ons_daily_load`) e 25 (`raw.weather_observed`), no que toca a estas três decisões. Os demais tipos e colunas dessas tabelas estão nos planos e em `docs/plataforma-ml.md`.
- Com `issued_at` como `date`, não existe mais de um snapshot por dia. Mudar para `timestamptz` depois exige migração de contrato, ADR novo e aviso à cientista.
- A faixa de horizontes 1 a 7 não guarda o horizonte 0 (previsão para o próprio dia de emissão). O plano do PR 13 propõe hoje `check (horizon_days between 0 and 16)`; o PR 13 deve alinhar a restrição a esta decisão ou registrar por que ela é mais larga. O ponto fica em aberto aqui.
- Em aberto: guardar o horizonte 0, que o usuário recomendou avaliar com a cientista (P8). Se for incluído, muda `expected_rows` e a faixa de `horizon_days` (PRs 13, 14 e 15) e exige novo ADR ou emenda a este.
- Em aberto: o fuso que define "o dia" de `issued_at`. O plano do PR 13 propõe `America/Sao_Paulo`; confirmar no PR 13.
- Resolvido no PR 09 (confirmado pelo usuário em 2026-11-07): o slug segue a regex `^[a-z][a-z0-9]*(_[a-z0-9]+)*$`, aplicada via `CHECK`; a proposta anterior `^[a-z_]+$` foi descartada. `ref.locations` não tem coluna `timezone`: o dia dos dados de clima é `America/Sao_Paulo`, definido pelos jobs.
- Com "última escrita", quem precisar saber quando uma linha entrou pela primeira vez não tem como saber em tabelas que atualizam. Se isso virar necessidade, a coluna nova muda o contrato de `raw` e precisa de ADR.
- O PR 08 (upsert) não depende deste ADR enquanto P9 ficar com "última escrita", como decidido. Os PRs 09 e 13 dependem dele.
- Aviso à ciência de dados: a cientista consulta `raw` e `ref` e deve ser avisada deste contrato e do horizonte 0 em aberto.

## Alternativas consideradas

- `issued_at` como `timestamptz` com a hora da coleta: permitiria mais de um snapshot por dia. Não adotado (P8).
- Guardar o horizonte 0: a ser avaliado com a cientista, ver "Consequências".
- "Primeira entrada" mais `updated_at` para `ingested_at`: exigiria coluna nova em `raw`. Não adotado (P9).
