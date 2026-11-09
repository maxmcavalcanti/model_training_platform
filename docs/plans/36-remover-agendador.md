# 36 — Remover o agendador interino (supercronic)

> Executa: agente. Depende de: 34 (worker na `main`), dos PRs 29 e 30 (lista de serviços que publicam porta) e do item manual 35 concluído (5.9: C+1 e C+2 com três `Completed` cada e reboot ok). Branch sugerida: `chore/remove-supercronic` (ADR 0001).
> TDD: test-writer (migra e remove os testes do agendador, escreve os de ausência, que ficam vermelhos) → implementação (verde) → refatorar.
> Revisão 2026-11-08: reescrito contra a `main` em `05c32c9`. Revisão 2 (mesmo dia): aplica a revisão independente aceita pelo usuário. Nenhum `docker compose config` sem `-q`; a igualdade de `PORT_PUBLISHING_SERVICES` migra para um teste neutro antes de o teste do `scheduler` ser apagado; o grep fica restrito aos arquivos de compose e aos workflows; `docker image rm ... || true` na nota de deploy. Alinhamento entre planos (mesmo dia): a atualização de status do ADR 0004 sai num único PR de docs depois do primeiro deploy automático do PR 39 (D4); lista de portas literal depois dos PRs 29 e 30. Revisão final (mesmo dia): `docker rm platform-scheduler-1` no lugar de `docker container prune` na nota de deploy.

## 1. Objetivo

Tirar do repositório o serviço `scheduler`, o `infra/cron/crontab` e o supercronic da imagem, deixando os deployments do Prefect como única fonte de verdade dos horários.
As regras que o crontab travava (horário fixo, longe da meia-noite, 15 minutos de espaço, fuso) continuam travadas pelos testes de deployment do PR 33. Este PR migra o que ainda é útil, remove só o que testa o agendador antigo e acrescenta testes que impedem a volta dele.

## 2. Fora do escopo

- Mudar horários, janelas, flows, deployments ou o worker.
- Editar o ADR 0004 (seção 10: atualização de status em PR próprio, só de `docs/**`, depois do primeiro deploy automático do PR 39).
- Deploy automático (PR 39). Aqui o deploy continua manual (nota do passo 4 para o usuário).
- `tzdata` e `TZ` da imagem, além do que o D3 diz.

## 3. Fase do roadmap

Fase 3 — "MLflow, Prefect e CI/CD", item "Ingestões migradas para flows do Prefect".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/docker-compose.yml` | Remover o serviço `scheduler` |
| `infra/cron/crontab` (e o diretório `infra/cron/`) | Apagar |
| `infra/jobs/Dockerfile` | Remover o bloco do supercronic (comentário, `ARG SUPERCRONIC_VERSION`, `ARG SUPERCRONIC_SHA256` e o `RUN` que baixa e confere) e o `COPY infra/cron/ infra/cron/` |
| `.github/workflows/ci.yml` | Remover os passos do `scheduler` e migrar a checagem de fuso para o `jobs` |
| `AGENTS.md` | Remover a linha "Agendador interino (supercronic, até o PR 36)" |
| `tests/infra/test_crontab.py` (test-writer) | Apagar: as regras já estão migradas no `tests/test_deployments.py` (PR 33, casos 2 a 5) |
| `tests/test_deployments.py` (test-writer) | Apagar só o caso de transição (comparação com o crontab, PR 33 caso 6) |
| `tests/infra/test_compose.py` (test-writer) | Migrar a igualdade de `PORT_PUBLISHING_SERVICES` para um teste neutro; apagar os testes do serviço `scheduler`; acrescentar os de ausência; tirar `scheduler` dos exemplos negativos das allow-lists dos planos 28, 30 e 34 (trocar por outro nome de serviço fictício) |
| `tests/infra/test_jobs_image.py` (test-writer) | Apagar os testes do supercronic; manter o do fuso; acrescentar os de ausência |

### Trechos atuais que saem

`infra/jobs/Dockerfile`:

```dockerfile
# Interim scheduler until Prefect (ADR 0004). Pinned by version and SHA-256.
ARG SUPERCRONIC_VERSION=v0.2.51
ARG SUPERCRONIC_SHA256=cc232108374e8e2b537045f2d5eaa1229f619db314c3ba6a14d38b35dc0aa123
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSLo /tmp/supercronic \
       "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
    && echo "${SUPERCRONIC_SHA256}  /tmp/supercronic" | sha256sum -c - \
    && install -m 0755 /tmp/supercronic /usr/local/bin/supercronic \
    && rm /tmp/supercronic \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*
...
COPY infra/cron/ infra/cron/
```

Ficam: o `FROM` com digest, `ENV ... TZ=America/Sao_Paulo`, o `RUN` do `tzdata`, os `COPY` de `ingestion/`, `flows/`, `migrations/` e `alembic.ini`, os `uv sync --locked --no-dev` e `USER app`.

`.github/workflows/ci.yml`, job `compose-smoke`, passos que saem:

```yaml
      - run: $COMPOSE build scheduler
      - name: Check the crontab parses
        run: $COMPOSE run --rm -T scheduler supercronic -test /app/infra/cron/crontab
      - name: Check the scheduler runs in America/Sao_Paulo
        run: test "$($COMPOSE run --rm -T scheduler date +%Z)" = "-03"
      - name: Check the scheduler has no admin database URL
        run: |
          if $COMPOSE run --rm -T scheduler printenv DATABASE_URL_ADMIN; then exit 1; fi
      - run: $COMPOSE up -d scheduler
      - name: Check the scheduler stays up
        run: |
          sleep 10
          $COMPOSE ps --status running --services | grep -x scheduler
          $COMPOSE logs scheduler
```

O passo de fuso migra para `name: Check the jobs image runs in America/Sao_Paulo` com `run: test "$($COMPOSE run --rm -T jobs date +%Z)" = "-03"`. O de "sem admin" já existe para o worker (PR 34, `Check the worker has no admin database URL`). Os demais saem. Os passos dos PRs 28 a 34 (bancos de serviço, MLflow, Prefect server, worker) ficam como estão.

`tests/infra/test_compose.py`, teste que sai, mas cuja primeira asserção é migrada (passo 1):

```python
def test_general_rules_still_hold_with_the_scheduler(scheduler_service):
    # The port allow-list must not grow for the scheduler, and its variables must be declared.
    assert PORT_PUBLISHING_SERVICES == frozenset({"health", "postgres"})
    ...
```

Depois dos PRs 29 e 30, a lista literal já não é `{"health", "postgres"}`: o plano 30 (caso 18) a fixa em `{"health", "postgres", "mlflow", "prefect-server"}`. O teste neutro usa a lista que estiver na `main` (esperado esse conjunto).

`AGENTS.md`, "Comandos" (linha que sai):

> - Agendador interino (supercronic, até o PR 36): validar o crontab com `docker run --rm platform-jobs supercronic -test /app/infra/cron/crontab`; na VPS: `docker compose -f infra/docker-compose.yml build scheduler`, `docker compose -f infra/docker-compose.yml up -d scheduler` e `docker compose -f infra/docker-compose.yml logs scheduler`

## 5. Passos

1. (test-writer) Num commit só, `test: expect prefect as the only scheduler`:
   - **Migrações primeiro, antes de apagar qualquer coisa.**
     - Em `tests/infra/test_compose.py`, crie um teste neutro (sem fixture de `scheduler`), por exemplo `test_port_allow_list_is_exactly_the_published_services`. Ele afirma a igualdade exata de `PORT_PUBLISHING_SERVICES` com a lista vigente na `main` depois dos PRs 29/30 (leia o valor atual da constante no arquivo e escreva o conjunto literal no teste; esperado `{"health", "postgres", "mlflow", "prefect-server"}`) e que `undeclared_variables` do compose contra o `infra/.env.example` é vazio. Assim a lista de portas continua travada contra crescimento acidental.
     - Confira que `tests/test_deployments.py` (PR 33) cobre a tabela fixa (06:30, 06:45, 07:00), o fuso `America/Sao_Paulo`, o horário fixo diário, nada nas horas 23 e 0 e os 15 minutos de espaço, com exemplos negativos. Se faltar alguma regra, porte-a para lá neste mesmo commit.
   - Apague `tests/infra/test_crontab.py`.
   - Em `tests/test_deployments.py`, apague só o caso de transição (o que lê `infra/cron/crontab`).
   - Em `tests/infra/test_compose.py`, seção "plan 16": apague a fixture `scheduler_service`, os testes `test_scheduler_*` e `test_general_rules_still_hold_with_the_scheduler` (já migrado), e `SCHEDULER_COMMAND`, `scheduler_command_problems` e seus exemplos negativos. Mantenha toda função que a seção "plan 34" (worker) usa, como `admin_credential_problems` e `scheduler_timezone_problems`, com os exemplos negativos; renomear para um nome neutro é opcional. Função que ficar sem uso sai junto com os negativos dela. Nos exemplos negativos das allow-lists de variáveis (planos 28, 30 e 34) que usam `scheduler` como serviço proibido, troque o nome por um serviço fictício (ex.: `other`), para o caso de ausência 1 não conflitar com eles.
   - Em `tests/infra/test_jobs_image.py`, seção "plan 16": apague `test_supercronic_version_is_pinned_to_a_release_tag`, `test_supercronic_checksum_is_a_sha256`, `test_supercronic_is_downloaded_from_the_pinned_release_and_verified`, `test_crontab_directory_is_copied_into_the_image_without_add` e `test_existing_rules_hold_with_the_supercronic_args`, os negativos de versão, checksum, download e cópia do cron, e os auxiliares sem uso. Mantenha `test_image_keeps_the_sao_paulo_timezone` e os negativos de fuso. A proibição de `ADD` continua coberta por `test_image_never_copies_the_whole_context_or_uses_add`.
   - Acrescente os casos 1 a 6 da seção 8.
   - Rode `uv run pytest tests/infra/ tests/test_deployments.py` e confirme que só os casos novos de ausência falham, pelo motivo certo (o `scheduler` existe, `supercronic` aparece no Dockerfile, no compose e no CI, `infra/cron` existe), e que todo o resto, inclusive o teste neutro de portas, passa.
2. (implementer) Remova o serviço `scheduler` do `infra/docker-compose.yml`, apague `infra/cron/` (`git rm -r infra/cron`), tire o bloco do supercronic e o `COPY infra/cron/` do Dockerfile, troque os passos do CI como na seção 4 e tire a linha do `AGENTS.md`. Não mexa no resto do Dockerfile (D2, D3).
3. (implementer) Rode `uv run zizmor .github/workflows/` e os critérios de pronto.
4. (implementer) No corpo do PR, a nota para o usuário (deploy manual até o PR 39, fora de 06:25–07:15 BRT, com nada `Running` na UI do Prefect):

   ```bash
   cd /opt/platform
   dc() { docker compose -f /opt/platform/infra/docker-compose.yml "$@"; }
   dc logs --no-color scheduler > ~/scheduler-final.log   # opcional: guarda o log do agendador antigo
   git pull --ff-only
   dc build jobs prefect-worker
   dc up -d --remove-orphans
   dc ps --format '{{.Service}} {{.Status}}'
   docker rm platform-scheduler-1 2>/dev/null || true
   docker image rm platform-scheduler || true
   ```

   → o `up` mostra `Container platform-scheduler-1  Removed` (órfão) e recria o `prefect-worker` (imagem nova); o `ps` não lista `scheduler` e mostra o worker `Up ... (healthy)`. O `docker rm platform-scheduler-1` remove o container parado do agendador, se o `--remove-orphans` não o tiver removido (só esse container; nunca `docker container prune`, que apagaria qualquer outro container parado). O `docker image rm` remove a imagem antiga; se ela já não existir (`No such image`), o `|| true` evita que isso pareça falha do deploy. No dia seguinte, depois das 07:15 BRT: três `Completed` na UI. Aqui o `up -d` sem nome de serviço já é seguro, porque o `scheduler` não existe mais no compose.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest` (com `docker compose -f infra/docker-compose.dev.yml up -d`) | Suíte verde |
| `uv run pytest tests/infra/test_compose.py -k "scheduler or supercronic or port_allow_list"` | Passam os testes de ausência (casos 1 e 2) e o teste neutro de portas (caso 7); nenhum teste ligado ao serviço `scheduler` antigo |
| `git ls-files infra/cron tests/infra/test_crontab.py` | Vazio |
| `git grep -n -i supercronic -- infra .github AGENTS.md` | Nada |
| `git grep -n -w scheduler -- 'infra/docker-compose*.yml' .github` | Nada. O grep fica restrito aos arquivos de compose e aos workflows, porque o Prefect usa a palavra `scheduler` em outros contextos, que não são o serviço antigo |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q; echo "exit=$?"` | Só `exit=0` (regra de infra: `config` só com `-q`) |
| `docker build -f infra/jobs/Dockerfile -t platform-jobs .` | Sem erro |
| `docker run --rm platform-jobs sh -c 'command -v supercronic \|\| echo absent'` | `absent` |
| `docker run --rm platform-jobs date +%Z` | `-03` |
| `docker run --rm platform-jobs python -c "import httpx; print(httpx.get('https://archive-api.open-meteo.com/v1/archive', timeout=20).status_code)"` | Um código HTTP (ex.: `400` sem parâmetros), o que prova que o TLS funciona sem os `ca-certificates` daquele bloco (D2) |
| `uv run zizmor .github/workflows/` | Sem achados |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem achados |
| `gh pr checks` | Verde, inclusive `Check the jobs image runs in America/Sao_Paulo` |

## 7. Testes necessários

`sim`: os testes novos impedem que o agendador antigo volte por engano, e a remoção dos testes do crontab e do `scheduler` só é segura porque as regras úteis (horários, lista de portas) são migradas antes.

## 8. Casos de teste

1. Nenhum arquivo `infra/docker-compose*.yml` tem serviço `scheduler`.
2. Nenhum serviço de nenhum compose tem `command` ou `entrypoint` contendo `supercronic`, e o texto dos arquivos de compose não contém `supercronic`.
3. `infra/cron/` não existe.
4. `infra/jobs/Dockerfile` não contém `supercronic` (em `ARG`, `RUN`, `ENV` ou comentário), não declara `ARG SUPERCRONIC_*` e não tem `COPY` de `infra/cron`. Exemplos negativos: um Dockerfile com `ARG SUPERCRONIC_VERSION=v0.2.51`, um com `COPY infra/cron/ infra/cron/` e um com `RUN install -m 0755 /tmp/supercronic ...` são rejeitados; o Dockerfile sem o bloco é aceito.
5. Nenhum workflow em `.github/workflows/` contém `supercronic`, `infra/cron` nem um passo que rode o serviço `scheduler`.
6. O `compose-smoke` do `ci.yml` tem um passo que roda `date +%Z` no serviço `jobs` e compara com `-03`.
7. Teste neutro (migrado de `test_general_rules_still_hold_with_the_scheduler`): `PORT_PUBLISHING_SERVICES` é exatamente o conjunto vigente depois dos PRs 29/30 (`{"health", "postgres", "mlflow", "prefect-server"}`), escrito literalmente no teste; toda variável obrigatória do compose está no `infra/.env.example`.
8. Continuam valendo, sem alteração (rede de segurança): `test_image_keeps_the_sao_paulo_timezone` (o `TZ` final do Dockerfile é `America/Sao_Paulo`); os casos do worker do PR 34 (só `ingestor`, sem admin, pool `platform`); os casos 1 a 5 e 7 a 13 do `tests/test_deployments.py` (tabela 06:30/06:45/07:00, fuso, horário fixo, meia-noite, 15 minutos, registro idempotente).

## 9. Riscos e perguntas em aberto

### Decisões (com recomendação; aceitas pelo usuário)

- **D1. Apagar ou migrar os testes do crontab e do `scheduler`: migrar antes, apagar depois.** As regras de horário já estão nos deployments (PR 33) e a igualdade da lista de portas vai para um teste neutro. Saem só as regras que não fazem sentido sem crontab: formato de linha, "sem redirecionamento", "sem `CRON_TZ=`" e o comando `python -m ingestion`.
- **D2. `ca-certificates` do bloco do supercronic: remover o bloco inteiro.** O `httpx` e o Prefect usam o bundle do `certifi`; o critério de pronto do TLS prova isso. Se falhar, devolva para o planejamento.
- **D3. `TZ=America/Sao_Paulo` e `tzdata` na imagem: manter.** O fuso fica nos logs e no `date`; a checagem do CI migra para o `jobs`.
- **D4. ADR 0004:** a atualização de status (agendador → `superseded` pelo ADR "Agendamento e execução pelo Prefect"; deploy → `superseded` pelo ADR "Pipeline de entrega") vai num **único PR só de `docs/**` logo depois do primeiro deploy automático bem-sucedido do PR 39**, aberto junto do PR que remove a exceção de deploy manual de `.claude/rules/infra.md` (plano 39, seção 10). Usuário ou skill `generate-adr`. Não há PR de status logo depois deste.
- **D5. Guardar o log final do `scheduler` antes do `--remove-orphans`:** sim (opcional, um comando na nota do PR).

### Riscos

- **Merge antes do fim do item 35.** Sem dois dias provados pelo Prefect, a volta fica cara (5.10.3 do item 35). Não faça merge sem a confirmação da 5.9 do item 35.
- **Deploy no meio de um flow.** O `up -d --remove-orphans` recria o worker (imagem nova). Fora de 06:25–07:15 BRT e com nada `Running` na UI.
- **Lista de portas.** Se os PRs 29/30 ainda não estiverem na `main`, o teste neutro trava a lista que existir; quem acrescentar serviço depois atualiza o teste. A dependência está no cabeçalho.
- **Planos futuros.** O PR 39 já usa `up -d --remove-orphans`, e o plano 37 lista `jobs` e `prefect-worker` (os dois em `platform-jobs@${JOBS_IMAGE_DIGEST}`), sem `scheduler`.
- **ADR 0004 desatualizado entre este PR e o primeiro deploy automático.** Ele continua dizendo que o PR 36 o marca como `superseded`; o registro fica certo no PR de docs depois do PR 39 (D4). É uma defasagem documental curta, aceita.
- **Referências em `docs/`.** Planos antigos (16, 17, 23, 27) e o ADR 0004 continuam citando o `scheduler`. São registro histórico; não edite.

### Perguntas em aberto

- Nenhuma bloqueante.

## 10. Decisões que exigem ADR

**Sim, uma atualização de status, não um ADR novo.** O ADR 0004 diz: "o PR 36 remove o `scheduler` depois do cutover manual (item 35) e marca este ADR como `superseded` no que toca ao agendador". Como nenhum agente escreve ou edita ADR, essa marcação sai deste PR e vai, junto com a parte do deploy, para um único PR só de `docs/**` logo depois do primeiro deploy automático bem-sucedido do PR 39 (D4), feito pelo usuário ou pela skill `generate-adr` e apontando para o ADR "Agendamento e execução pelo Prefect" (plano 33, seção 10, obrigatório e já mergeado antes do 33). A decisão em si já está no ADR 0004 e no ADR do plano 33, então a implementação deste PR não depende do PR de status, que só evita deixar o registro desatualizado.
