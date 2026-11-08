# 12 — Subir o Postgres na VPS, migrar e dar acesso à cientista (manual)

> Executa: **usuário**. Depende de: 04, 09, 10, 11 (todos na `main`; `main` em `8094764`).
> Fase do roadmap: Fase 1 — "Postgres, migrações com Alembic, usuários e permissões" (parte de produção).
> Revisão 2026-11-07: alinhado à `main` em `8094764` (compose com `health`, `postgres` e `jobs` em profile; `infra/scripts/tailscale-serve.sh` com `--tcp=5432`; migrações `0001` a `0003`; ADRs 0001 a 0005).

## Por que é manual

Exige SSH na VPS, criar segredos (senhas dos papéis) e convidar outra pessoa para o Tailscale. Até o PR 39, atualizar a VPS é manual: exceção registrada no ADR 0004 (`docs/adr/0004-interim-operation-before-prefect.md`, P6). É a primeira vez que o Postgres de produção é tocado: ainda não há dado nem backup (PR 57), então qualquer erro até o fim deste item se corrige recriando o volume (ver "Se algo falhar").

## O que já está na `main` e este item usa

- `infra/docker-compose.yml` (projeto `platform`; o compose lê `infra/.env` sozinho, porque o `.env` padrão fica no diretório do arquivo de compose):
  - `postgres`: `postgres:16.15`, `mem_limit: 256m`, banco `ml`, `POSTGRES_USER: ${POSTGRES_ADMIN_USER:?...}`, `POSTGRES_PASSWORD: ${POSTGRES_ADMIN_PASSWORD:?...}`, `POSTGRES_HOST_AUTH_METHOD: scram-sha-256`, `POSTGRES_INITDB_ARGS: "--auth-host=scram-sha-256"`, volume `pgdata` (no host: `platform_pgdata`), porta `${POSTGRES_BIND_IP:-127.0.0.1}:5432:5432`.
  - `jobs` (profile `jobs`, imagem `platform-jobs` construída na VPS, ADR 0004): `DATABASE_URL=postgresql+psycopg://ingestor:${POSTGRES_INGESTOR_PASSWORD:?...}@postgres:5432/ml` e `DATABASE_URL_ADMIN=postgresql+psycopg://${POSTGRES_ADMIN_USER}:${POSTGRES_ADMIN_PASSWORD}@postgres:5432/ml`. O `migrations/env.py` prefere `DATABASE_URL_ADMIN`, então `alembic` dentro do `jobs` roda como admin.
- `infra/scripts/tailscale-serve.sh`: `tailscale serve reset`, depois `--https=8080 http://127.0.0.1:8080` e `--tcp=5432 tcp://127.0.0.1:5432` (ADR 0003, P15).
- Migrações: `0001` (schemas), `0002` (papéis `ingestor`, `scientist`, `scorer`, `reader`, criados `LOGIN` **sem senha**, de propósito), `0003` (`ref.locations` com 4 linhas). Cabeça: `0003`.
- Socket local do Postgres em `trust` (decisão do plano 10): `docker compose exec postgres psql -U platform_admin` entra sem senha; toda conexão TCP exige `scram-sha-256`.

### Variáveis que o `infra/.env` precisa ter ao fim deste item

Derivadas das referências `${VAR}` de `infra/docker-compose.yml` e dos itens 04, 10 e 11. Nenhuma outra é necessária agora.

| Variável | Valor | De onde |
| --- | --- | --- |
| `HEALTH_BIND_IP` | `127.0.0.1` | item 04 (já existe) |
| `TS_HOSTNAME` | `<host>.<tailnet>.ts.net` | item 04 (já existe) |
| `POSTGRES_ADMIN_USER` | `platform_admin` (nunca `postgres`) | plano 10 |
| `POSTGRES_ADMIN_PASSWORD` | 48 caracteres hex (`openssl rand -hex 24`) | plano 10 |
| `POSTGRES_BIND_IP` | `127.0.0.1` (nunca `0.0.0.0`) | plano 10, P15 |
| `POSTGRES_INGESTOR_PASSWORD` | 48 caracteres hex; **igual** à senha do papel `ingestor` no banco | plano 11 |

As senhas de `scientist`, `scorer` e `reader` **não** entram no `infra/.env` (nenhum serviço as usa ainda); ficam só no banco e no gerenciador de senhas.

Senhas em hex (`openssl rand -hex 24`): só `0-9a-f`, então não quebram a URL do SQLAlchemy (`@`, `:`, `%` e `/` quebram ou mudam o parse) nem a aspa simples do `ALTER ROLE`.

### Regras de segurança deste item

- Nenhuma senha digitada ou colada na linha de comando: elas só aparecem como `$(openssl ...)` ou `"$pw"`, que o histórico grava literalmente, sem o valor.
- Nunca rodar `docker compose ... config` sem `-q`: ele imprime as URLs com as senhas.
- Nunca `docker compose down -v` na VPS fora do procedimento de "Se algo falhar".
- Nenhuma porta nova no firewall, nem "para testar" (`.claude/rules/infra.md`).

## Checklist

Na VPS, como `deploy` (`ssh deploy@<nome-tailscale>`), em `/opt/platform`. Comece toda sessão SSH com:

```bash
cd /opt/platform
dc() { docker compose -f /opt/platform/infra/docker-compose.yml "$@"; }
```

### 1. Conferir o ponto de partida

- [ ] `git pull --ff-only && git log -1 --oneline` → `8094764 feat: jobs image, python -m ingestion cli and jobs compose service (#22)` ou um commit mais novo da `main`.
- [ ] `stat -c '%a %U' infra/.env` → `600 deploy`.
- [ ] `cut -d= -f1 infra/.env` (mostra só os nomes) → `HEALTH_BIND_IP` e `TS_HOSTNAME`, nenhum `POSTGRES_*`. Se já houver `POSTGRES_*` de uma tentativa anterior, pare e vá para "Se algo falhar", caso A.
- [ ] `docker volume ls -q | grep -c '^platform_pgdata$'` → `0` (o volume precisa nascer vazio para o `scram-sha-256` do `initdb` valer). Se der `1`, vá para "Se algo falhar", caso A.
- [ ] `tailscale version` (anotar) e `tailscale serve --help 2>&1 | grep -c -- '--tcp'` → `1` ou mais. Se `0`, a versão não tem `--tcp`: atualize o Tailscale pelo repositório oficial ou devolva para o planejamento.
- [ ] `df -h /` com pelo menos 3 GB livres (imagem do Postgres + imagem dos jobs com pandas) e `free -m` (anotar a coluna `available`, insumo do 28a).

### 2. Gerar as senhas e preencher o `infra/.env`

- [ ] Acrescentar as quatro variáveis sem que nenhuma senha passe pelo histórico (o bloco inteiro é uma entrada do histórico, sem valores):

  ```bash
  umask 077
  {
    printf '\n# Postgres (item 12)\n'
    printf 'POSTGRES_ADMIN_USER=platform_admin\n'
    printf 'POSTGRES_ADMIN_PASSWORD=%s\n' "$(openssl rand -hex 24)"
    printf 'POSTGRES_BIND_IP=127.0.0.1\n'
    printf 'POSTGRES_INGESTOR_PASSWORD=%s\n' "$(openssl rand -hex 24)"
  } >> infra/.env
  ```

- [ ] Conferir sem imprimir as senhas:
  - `stat -c '%a' infra/.env` → `600`.
  - `grep -c '^POSTGRES_' infra/.env` → `4`.
  - `grep -cE '^POSTGRES_(ADMIN|INGESTOR)_PASSWORD=[0-9a-f]{48}$' infra/.env` → `2`.
  - `grep -E '^POSTGRES_(ADMIN_USER|BIND_IP)=' infra/.env` → `POSTGRES_ADMIN_USER=platform_admin` e `POSTGRES_BIND_IP=127.0.0.1`.
- [ ] Copiar as duas senhas para o gerenciador de senhas (entradas "platform admin" e "platform ingestor"): `grep -E '^POSTGRES_(ADMIN|INGESTOR)_PASSWORD=' infra/.env`, copiar, e `clear`. A saída vai para a tela, não para o histórico.
- [ ] Gerar as outras três senhas, só na tela: `for r in scientist scorer reader; do printf '%s %s\n' "$r" "$(openssl rand -hex 24)"; done`. Copiar cada uma para o gerenciador ("platform scientist", "platform scorer", "platform reader") e `clear`. (Alternativa: gerar no próprio gerenciador, 48 caracteres só `0-9a-f`.)

### 3. Subir o Postgres

- [ ] `dc up -d --wait postgres` → termina com `Container platform-postgres-1  Healthy`. Se falhar com `... is required`, falta uma variável no passo 2.
- [ ] `dc ps` → `platform-health-1` e `platform-postgres-1` com `Up ... (healthy)`; o `jobs` não aparece (é profile).
- [ ] `dc ps --format '{{.Ports}}' postgres` → `127.0.0.1:5432->5432/tcp`.
- [ ] Autenticação `scram-sha-256` em toda linha TCP do `pg_hba`:
  - `dc exec -T postgres psql -U platform_admin -d ml -tAc "select count(*) from pg_hba_file_rules where type like 'host%' and auth_method <> 'scram-sha-256'"` → `0`.
  - `dc exec -T postgres psql -U platform_admin -d ml -tAc "select type, auth_method, count(*) from pg_hba_file_rules group by 1, 2 order by 1"` → só `host|scram-sha-256|<n>` e `local|trust|<n>` (nenhum `md5`, `password` nem `host|trust`).
  - `dc exec -T postgres psql -U platform_admin -d ml -tAc "show password_encryption"` → `scram-sha-256`.
  - Se o primeiro der diferente de `0`, vá para "Se algo falhar", caso A.

### 4. Expor na tailnet

- [ ] `infra/scripts/tailscale-serve.sh` (sem sudo: `deploy` é operador do Tailscale, item 02). Sai sem erro.
- [ ] `tailscale serve status` → um bloco `https://<host>.<tailnet>.ts.net:8080` apontando para `http://127.0.0.1:8080` e um bloco `tcp://<host>.<tailnet>.ts.net:5432` (ou equivalente com `5432`) apontando para `tcp://127.0.0.1:5432`. O texto exato varia com a versão; o que importa é a 5432 ir para `127.0.0.1:5432`.

### 5. Construir a imagem dos jobs

- [ ] `dc build jobs` (lento em 1 vCPU, pode usar swap; nada mais rodando, ADR 0004) → termina com `platform-jobs  Built` (ou `Image platform-jobs Built`, conforme a versão do compose).
- [ ] `dc run --rm -T jobs whoami` → `app`.
- [ ] `dc run --rm -T jobs alembic heads` → `0003 (head)`.

### 6. Migrar

- [ ] `dc run --rm jobs alembic upgrade head` → no log, três linhas `Running upgrade`: `-> 0001, schemas`, `0001 -> 0002, roles`, `0002 -> 0003, ref_locations`. (Essa conexão é TCP com a senha do admin, então ela também prova que o `POSTGRES_ADMIN_PASSWORD` do `.env` é o do banco.)
- [ ] `dc run --rm -T jobs alembic current` → última linha `0003 (head)`.
- [ ] `dc exec -T postgres psql -U platform_admin -d ml -tAc "select location_id, subsystem from ref.locations order by location_id"` →
  ```
  belem|N
  porto_alegre|S
  recife|NE
  sao_paulo|SE
  ```

### 7. Definir as senhas dos quatro papéis

A `0002` cria os papéis sem senha; até este passo nenhum deles consegue entrar por TCP. A senha do `ingestor` tem de ser **a mesma** do `POSTGRES_INGESTOR_PASSWORD` do `.env` (o serviço `jobs` entra com ela).

- [ ] Rodar o laço abaixo. Ele pede cada senha com `read -s` (sem eco), confere que tem 48 caracteres hex e manda o `ALTER ROLE` pelo stdin do `psql` (`printf` é builtin do bash, então a senha não aparece em `ps` nem no histórico):

  ```bash
  for role in ingestor scientist scorer reader; do
    read -rsp "Password for $role: " pw; echo
    if [[ ! "$pw" =~ ^[0-9a-f]{48}$ ]]; then echo "skipped $role: expected 48 hex chars"; continue; fi
    printf "ALTER ROLE %s PASSWORD '%s';\n" "$role" "$pw" \
      | docker compose -f /opt/platform/infra/docker-compose.yml exec -T postgres psql -U platform_admin -d ml -v ON_ERROR_STOP=1
  done
  unset pw
  ```

  Saída esperada: `ALTER ROLE` quatro vezes, nenhum `skipped`. Para o `ingestor`, cole o valor de "platform ingestor" (o mesmo do `.env`). Se aparecer `skipped`, rode o laço de novo só com o papel que faltou (troque a lista do `for`).
- [ ] Conferir sem expor as senhas: `dc exec -T postgres psql -U platform_admin -d ml -tAc "select rolname, rolcanlogin, left(rolpassword, 14) from pg_authid where rolname in ('ingestor','scientist','scorer','reader') order by rolname"` →
  ```
  ingestor|t|SCRAM-SHA-256$
  reader|t|SCRAM-SHA-256$
  scientist|t|SCRAM-SHA-256$
  scorer|t|SCRAM-SHA-256$
  ```
- [ ] `ingestor` entra com a senha do `.env` (prova que as duas batem): `dc run --rm -T jobs python -c "from sqlalchemy import text; from ingestion.db import build_engine; c = build_engine().connect(); print(c.execute(text('select current_user')).scalar(), c.execute(text('select count(*) from ref.locations')).scalar())"` → `ingestor 4`.
- [ ] Cada um dos outros três entra por TCP (dentro do container, `host=127.0.0.1` usa a regra `host` com `scram-sha-256`; o `psql` pede a senha sem eco): `dc exec postgres psql "host=127.0.0.1 dbname=ml user=scientist" -tAc "select current_user"` → `scientist`. Repita com `scorer` e `reader`.
- [ ] Senha errada é recusada: o mesmo comando com `user=reader` e uma senha qualquer → `password authentication failed for user "reader"`.
- [ ] Nenhuma senha no histórico: `history | grep -cE '[0-9a-f]{40,}'` → `0`.

### 8. Tailscale: ACL e convite da cientista

No painel admin do Tailscale:

- [ ] Convidar a cientista **como usuária da tailnet** (Users → Invite), para que a ACL valha para ela. Ver pergunta em aberto 2 sobre "Share" de máquina.
- [ ] Em Access controls, acrescentar ao policy file existente (manter as regras do item 04; trocar os e-mails):

  ```jsonc
  {
    "groups": {
      "group:scientists": ["<email-da-cientista>"]
    },
    "tagOwners": {
      "tag:platform": ["autogroup:admin"]
    },
    "acls": [
      // item 04 + este item: você alcança SSH, saúde e Postgres
      { "action": "accept", "src": ["<seu-email>"], "dst": ["tag:platform:22,8080,5432"] },
      // item 12: a cientista só alcança o Postgres (MLflow e Prefect no item 31, Grafana no 50)
      { "action": "accept", "src": ["group:scientists"], "dst": ["tag:platform:5432"] }
    ],
    "tests": [
      {
        "src": "<email-da-cientista>",
        "accept": ["tag:platform:5432"],
        "deny": ["tag:platform:22", "tag:platform:8080"]
      }
    ]
  }
  ```

  O painel roda os `tests` ao salvar e recusa a política se algum falhar. Se o seu policy file usa `grants` em vez de `acls`, escreva o equivalente (`"ip": ["5432"]` para o grupo). Confirme que não sobrou a regra padrão "allow all" (`"src": ["*"], "dst": ["*:*"]`): com ela, a cientista alcança todas as portas. A ACL é o único controle de rede (ADR 0003); não há proxy com senha.
- [ ] Enviar a ela, por canal seguro (não por e-mail nem chat em texto aberto; por exemplo, o compartilhamento do gerenciador de senhas): usuário `scientist`, a senha, host `<host>.<tailnet>.ts.net`, porta `5432`, banco `ml`. O tráfego já é cifrado pelo WireGuard; o Postgres não tem TLS, então clientes que exigem `sslmode=require` devem usar `sslmode=disable` ou `prefer`.
- [ ] Enviar junto o aviso de `ref.locations` (plano 09, seção 9, "Aviso à ciência de dados"; regra "mudança em `ref` exige aviso").

## Verificação de pronto

| Onde | Comando | Saída esperada |
| --- | --- | --- |
| VPS | `dc run --rm -T jobs alembic current` | `0003 (head)` |
| VPS | `dc ps` | `health` e `postgres` com `Up ... (healthy)` |
| VPS | `docker ps --format '{{.Names}} {{.Ports}}' \| grep -c '0\.0\.0\.0'` | `0` |
| VPS | `sudo ss -tlnH 'sport = :5432' \| awk '{print $4}'` | Só endereços `127.0.0.1:5432`, `100.x.y.z:5432` ou `[fd7a:...]:5432` (tailscale); nunca `0.0.0.0` nem `*` |
| VPS | `dc exec -T postgres psql -U platform_admin -d ml -tAc "select count(*) from pg_hba_file_rules where type like 'host%' and auth_method <> 'scram-sha-256'"` | `0` |
| Seu notebook (na tailnet) | `psql "host=<host>.<tailnet>.ts.net port=5432 dbname=ml user=reader" -tAc "select count(*) from ref.locations"` | `4` |
| Internet (fora da tailnet, ex.: celular no 4G) | `nc -zv -w 5 <ip-publico> 5432` | Falha (timeout ou recusada) |
| Notebook dela | `psql "host=<host>.<tailnet>.ts.net port=5432 dbname=ml user=scientist" -tAc "select location_id from ref.locations order by location_id"` | `belem`, `porto_alegre`, `recife`, `sao_paulo` |
| Notebook dela | `psql "host=<host>.<tailnet>.ts.net port=5432 dbname=ml user=scientist" -c "insert into ref.locations values ('curitiba', 'Curitiba', -25.43, -49.27, 'S')"` | `ERROR:  permission denied for table locations` |
| Notebook dela | `curl -s --max-time 5 https://<host>.<tailnet>.ts.net:8080/health` | Falha (a ACL dela só libera a 5432) |

### Teste de reboot

- [ ] `sudo reboot` na VPS.
- [ ] Sem entrar na VPS, depois de 2 minutos, do seu notebook: `curl -s https://<host>.<tailnet>.ts.net:8080/health` → `ok`, e `psql "host=<host>.<tailnet>.ts.net port=5432 dbname=ml user=reader" -tAc "select count(*) from ref.locations"` → `4`.
- [ ] Na VPS (nova sessão; redefina `dc`): `dc ps` → `health` e `postgres` com `Up ... (healthy)`; `tailscale serve status` ainda lista a 5432; `docker ps --format '{{.Names}} {{.Ports}}' | grep -c '0\.0\.0\.0'` → `0`.
- [ ] Se o reboot exigir qualquer intervenção (inclusive rodar de novo o `tailscale-serve.sh`), o item não está pronto: anote o que foi preciso e devolva para o planejamento.

### Anotar para o planejamento (insumo do 28a e dos PRs seguintes)

- [ ] `docker stats --no-stream --format '{{.Name}} {{.MemUsage}}'` (memória do `postgres` parado) e `free -m`.
- [ ] Versão do Tailscale e o texto real de `tailscale serve status` para a 5432 (para corrigir a saída esperada deste plano, se for diferente).

## Se algo falhar

Até o item 17 não há dado que não se recrie: as 4 linhas de `ref.locations` vêm da migração. Depois do item 17 (coleta da previsão), **nunca** apague o volume: o histórico de previsões não é reprocessável e ainda não há backup (PR 57).

- **A. Volume nasceu errado** (o `pg_hba` tem linha `host` sem `scram-sha-256`; o volume `platform_pgdata` já existia; ou o `.env` tinha `POSTGRES_*` de outra tentativa e você não sabe que senha o banco tem). Só antes do item 17:
  1. `dc rm -sf postgres`
  2. `docker volume rm platform_pgdata`
  3. Se o `.env` estiver em dúvida, apague só as linhas do Postgres: `sed -i '/^# Postgres (item 12)$/d; /^POSTGRES_/d' infra/.env` e confira `grep -c '^POSTGRES_' infra/.env` → `0`; refaça o passo 2.
  4. Recomece no passo 3.
- **`up` falha com `... is required`**: falta a variável citada no `infra/.env`; volte ao passo 2.
- **`postgres` não fica `healthy`**: `dc logs --tail 50 postgres`. Se `docker inspect platform-postgres-1 --format '{{.State.OOMKilled}}'` der `true`, o `mem_limit: 256m` não bastou: devolva para o planejamento (aumentar o limite é PR, não edição na VPS).
- **`tailscale-serve.sh` falha na linha `--tcp`**: o script já fez `reset` e a linha `--https`, então a saúde continua publicada. Anote a mensagem e a `tailscale version` e devolva para o planejamento (PR de correção do script e do teste, plano 10, passo 5). Não ajuste o script à mão na VPS.
- **`build jobs` falha ou é morto por falta de memória**: confira `free -m` e se nada mais está rodando; tente de novo uma vez. Se repetir, devolva para o planejamento com o log.
- **`alembic upgrade head` falha**: as três migrações rodam numa única transação (`migrations/env.py`, `context.begin_transaction()`), então nada fica aplicado pela metade; `alembic current` não mostra `0003`. Se o erro for `password authentication failed for user "platform_admin"`, o volume foi criado com outra senha: caso A. Outro erro: devolva para o planejamento com o log. Não rode `alembic downgrade` em produção.
- **`ingestor` não entra pelo `jobs`** (`password authentication failed for user "ingestor"`): a senha colada no passo 7 não é a do `.env`. Rode o laço do passo 7 de novo só com `ingestor`, colando o valor de `grep '^POSTGRES_INGESTOR_PASSWORD=' infra/.env` (depois `clear`).
- **Uma senha vazou** (colada num chat, no histórico ou num commit): troque-a. Para `scientist`, `scorer`, `reader`: laço do passo 7 com uma senha nova. Para o `ingestor`: senha nova no laço **e** no `.env` (edite com `nano infra/.env`, sem `echo`). Para o admin: `ALTER ROLE platform_admin` pelo mesmo laço (troque a lista para `platform_admin`) **e** no `.env`; mudar só o `.env` não muda a senha do banco (`POSTGRES_PASSWORD` só vale na criação do volume). Se foi para o histórico: `history -c && history -w`. Se foi para o git (repo público): considere a senha pública para sempre e troque.
- **Desistir do item por ora**: `dc stop postgres` e retire a 5432 das regras da ACL. Não edite o script do `tailscale serve` na VPS: com o Postgres parado, a 5432 da tailnet não alcança nada.

## Perguntas em aberto para o usuário

1. **Senhas de `scorer` e `reader` agora?** O pedido é definir as quatro. Nenhum serviço usa `scorer` (score, Fase 4) nem `reader` (Grafana, PR 47) ainda; sem senha, esses papéis não entram por TCP, o que é menos superfície. Recomendação: definir as quatro agora, como pedido, porque o `reader` serve para a sua verificação do notebook e o checklist já fica completo. Se preferir deixar `scorer` sem senha, tire-o do laço do passo 7 e da conferência do `pg_authid` (a linha dele fica `scorer|t|` sem prefixo).
2. **Convite ou "Share" da máquina?** Com convite, ela é usuária da sua tailnet e a ACL (com `tests`) vale para ela com certeza; pode contar no limite de usuários do seu plano do Tailscale. Com "Share", ela fica na tailnet dela e enxerga só a VPS; a restrição de portas para usuários de nó compartilhado deve ser conferida na documentação atual do Tailscale antes de confiar nela. Recomendação: convite. Diga qual usar.
3. **`\password` em vez do laço com `read -s`?** O `ALTER ROLE ... PASSWORD '...'` manda a senha em texto ao servidor (que só a registra em log se o comando der erro). O `\password <papel>` do `psql` (interativo: `dc exec postgres psql -U platform_admin -d ml`, depois `\password scientist`) manda já o hash SCRAM. O plano usa `read -s` como pedido; trocar é opcional e não muda as verificações.
