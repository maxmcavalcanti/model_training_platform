# Acesso da cientista de dados ao banco da plataforma

Este guia leva você do convite do Tailscale até a primeira consulta no Postgres `ml`. Leia em ordem, leva cerca de 15 minutos.

## 1. Visão geral e pré-requisitos

A plataforma roda numa VPS que não tem nenhuma porta aberta na internet (ADR 0003, `docs/adr/0003-tailscale-only-network.md`). A única porta que você alcança é a **5432** (Postgres), e só depois de entrar na rede privada do Tailscale (a "tailnet").

Você precisa receber, em canais **separados**:

1. Um **convite do Tailscale**, por e-mail.
2. A **senha** do papel `scientist`, por gerenciador de senhas ou outro canal seguro. Este documento nunca contém senha, e a senha não deve ir por e-mail nem chat aberto.
3. O nome da máquina na tailnet, no formato `<host>.<tailnet>.ts.net`. Neste guia ele aparece como placeholder; use o valor que receber.

## 2. Tailscale, passo a passo

1. Abra o e-mail do convite e aceite. Crie ou entre na conta usando **o mesmo e-mail** que recebeu o convite (a ACL de acesso é ligada a ele).
2. Instale o cliente em <https://tailscale.com/download>:
   - Windows: instalador `.exe`.
   - macOS: App Store ou instalador `.pkg`.
   - Linux: `curl -fsSL https://tailscale.com/install.sh | sh` e depois `sudo tailscale up`.
3. Abra o Tailscale, entre com o e-mail convidado e deixe-o **conectado** sempre que for usar o banco.
4. Confira que a VPS aparece e está online:

   ```bash
   tailscale status
   ```

   A linha de `<host>` deve estar presente, sem `offline`. No Windows e no macOS a mesma lista aparece no menu do ícone do Tailscale.
5. A ACL libera para você **somente a porta 5432** da VPS. Ping, SSH, MLflow e demais serviços não respondem para você; isso é esperado.

## 3. Parâmetros de conexão

| Parâmetro | Valor |
| --- | --- |
| Host | `<host>.<tailnet>.ts.net` |
| Porta | `5432` |
| Banco | `ml` |
| Usuário | `scientist` |
| Senha | a que você recebeu (nunca neste repositório) |
| `sslmode` | `disable` |

Por que `sslmode=disable`: o tráfego dentro da tailnet já é cifrado de ponta a ponta pelo WireGuard, e o Postgres não publica TLS próprio. Clientes que exigem `sslmode=require` falham; use `disable` (ou `prefer`).

## 4. Três formas de conectar

### psql

Instalação:

- Windows: o `psql` costuma **não vir instalado**. Instale o PostgreSQL pelo instalador oficial (<https://www.postgresql.org/download/windows/>) marcando só "Command Line Tools", ou use `winget install PostgreSQL.PostgreSQL.16`. Reabra o terminal depois.
- macOS: `brew install libpq` (e `brew link --force libpq`) ou `brew install postgresql@16`.
- Linux (Debian/Ubuntu): `sudo apt install postgresql-client`.

Conexão (o `psql` pede a senha sem eco):

```bash
psql "host=<host>.<tailnet>.ts.net port=5432 dbname=ml user=scientist sslmode=disable"
```

### DBeaver

Nova conexão, tipo PostgreSQL, aba "Main":

- Host: `<host>.<tailnet>.ts.net`
- Port: `5432`
- Database: `ml`
- Username: `scientist`
- Password: a sua (marque "Save password" só se o computador for pessoal e criptografado)

Na aba "Driver properties" (ou "SSL"), deixe o SSL desligado (`sslmode=disable`). Use "Test Connection" antes de salvar.

### Python com psycopg

Instale `psycopg[binary]` e leia a senha **fora do código**:

```python
import getpass
import os

import psycopg

password = os.environ.get("PGPASSWORD") or getpass.getpass("scientist password: ")

with psycopg.connect(
    host="<host>.<tailnet>.ts.net",
    port=5432,
    dbname="ml",
    user="scientist",
    password=password,
    sslmode="disable",
) as conn:
    print(conn.execute("select count(*) from ref.calendar").fetchone())
```

Alternativas que mantêm a senha fora do notebook:

- Variável de ambiente `PGPASSWORD` definida no terminal, não no notebook.
- Arquivo `.pgpass` (Linux/macOS: `~/.pgpass`, permissão `0600`; Windows: `%APPDATA%\postgresql\pgpass.conf`), uma linha `<host>.<tailnet>.ts.net:5432:ml:scientist:<senha>`.
- `~/.pg_service.conf` com um serviço nomeado (host, porta, dbname, user, sslmode) e `psycopg.connect(service="ml")`; a senha continua no `.pgpass` ou na variável.

Nunca escreva a senha em célula de notebook, script ou arquivo que vá para o git.

## 5. O que você pode e não pode fazer

Conforme a migração `0002` (`migrations/versions/0002_roles.py`):

| Schema | O que o papel `scientist` pode |
| --- | --- |
| `raw`, `ref` | Somente **ler** (`SELECT`). Nunca escreve: `INSERT`, `UPDATE`, `DELETE` e `TRUNCATE` dão `permission denied` |
| `predictions`, `monitoring` | Somente ler |
| `features` | Ler e **criar tabelas** (`CREATE`). As tabelas que você cria são suas, e nelas você tem controle total (inclusive `DELETE` e `TRUNCATE`). Os papéis da plataforma (`ingestor`, `scorer`, `reader`) conseguem ler o que você criar aqui |

Você não cria objetos fora de `features`. Mudança em `raw` ou `ref` só acontece por migração, com aviso a você.

## 6. Tabelas disponíveis hoje

| Tabela | O que é |
| --- | --- |
| `ref.locations` | As 4 capitais usadas para clima (`belem`, `porto_alegre`, `recife`, `sao_paulo`), com latitude, longitude e subsistema |
| `ref.calendar` | Um dia por linha, de 2015-01-01 a 2030-12-31, com dia da semana ISO e feriados nacionais |
| `raw.weather_forecast` | Snapshots diários da previsão do Open-Meteo para as 4 capitais, com horizonte de 1 a 7 dias |
| `raw.ons_daily_load` | Carga diária do ONS por subsistema (`N`, `NE`, `S`, `SE`), desde 2015-01-01 |

Antes de usar `ref.calendar`, `raw.ons_daily_load` e `raw.weather_forecast` no modelo, leia o detalhamento (unidades, `weekday` ISO, dia sem dado do ONS, revisões de valores recentes, `issued_at`) na seção "Aviso à cientista" de `docs/plans/23-backfill-ons-e-pronto-fase-1-manual.md`. O modelo de dados completo está em `docs/plataforma-ml.md`.

## 7. Teste de pronto

Com o Tailscale conectado, rode as duas consultas:

```sql
select subsystem, max("date"), count(*) from raw.ons_daily_load group by 1 order by 1;
```

Esperado: **4 linhas**, `N`, `NE`, `S`, `SE`, com a mesma data máxima (no máximo uns 5 dias antes de hoje) e a mesma contagem nas quatro.

```sql
select count(*) from ref.calendar;
```

Esperado: `5844`.

Quando as duas passarem, responda ao responsável pela plataforma confirmando a **data** em que rodou e colando as 4 linhas e o `5844`. Essa confirmação é o critério de pronto da Fase 1.

## 8. Problemas comuns

| Sintoma | Causa provável e o que fazer |
| --- | --- |
| Trava e dá timeout, ou `could not translate host name` | Tailscale desligado ou VPS offline. Rode `tailscale status`, reconecte e confira se `<host>` está online. Se a VPS aparecer `offline`, avise o responsável |
| `password authentication failed for user "scientist"` | Senha errada (cuidado com espaço no fim ao colar) ou usuário digitado errado. Confira no gerenciador; se persistir, peça uma nova senha |
| `no pg_hba.conf entry for host ...` | Quase sempre cliente exigindo SSL. Use `sslmode=disable`. Se já usa, avise o responsável |
| `permission denied for table ...` ou `... for schema ...` | Você tentou escrever em `raw`, `ref`, `predictions` ou `monitoring`, ou criar objeto fora de `features`. É esperado; escreva em `features` |

Como pedir ajuda: envie o comando que rodou, a mensagem de erro completa e a saída de `tailscale status` (sem a senha, nunca).

## 9. Segurança

- Não compartilhe a senha com ninguém, nem a guarde em arquivo solto ou nota sem proteção.
- Não faça commit de credenciais, `.pgpass`, `.env` ou notebooks com a senha dentro. Antes de versionar um notebook, limpe as saídas e confira as células.
- Se suspeitar de vazamento (senha digitada no lugar errado, notebook enviado, computador perdido), avise o responsável **na hora**. Ele rotaciona a senha do papel `scientist`; até lá, desconecte o Tailscale.
- Não repasse o convite do Tailscale nem compartilhe o seu login.
