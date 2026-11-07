# 57 — Backup diário (3 bancos + artefatos do MLflow) e restore testado

> Executa: agente. Depende de: 29 (volume de artefatos), 28 (bancos). Pode ser feito em paralelo com 51–56. Branch sugerida: `feat/backup-restore`.
> TDD: passo 0 (marcador) → test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar uma imagem `backup` com `pg_dump` e `rclone` e dois scripts: `backup.sh` (dump dos bancos `ml`, `mlflow`, `prefect` e tar do volume de artefatos, enviados para fora da VPS, retenção de 14 dias) e `restore.sh` (traz um backup de uma data e restaura).
Um teste automatizado faz backup, apaga dados e restaura, porque "backup sem restore testado não conta como backup".

## 2. Fora do escopo

- Criar o bucket e as credenciais (item 59). Agendamento no host (item 59 instala as units deste PR).
- Restore em produção (o teste mensal é rotina do item 59).

## 3. Fase do roadmap

Fase 5 — "Alertas no Telegram, backups com restore testado".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `pyproject.toml` | Marcador `docker` em `[tool.pytest.ini_options].markers` (passo 0) |
| `infra/backup/Dockerfile` | `FROM postgres:16.<minor>` (mesma do compose) + `rclone` + `tar` |
| `infra/backup/backup.sh` | Dump, tar, upload, retenção |
| `infra/backup/restore.sh` | Download de uma data e restore |
| `infra/docker-compose.yml` | Serviço `backup` no profile `jobs` (execução única), com o volume `mlflow_artifacts` montado somente leitura |
| `infra/systemd/plataforma-backup.service`, `.timer`, `plataforma-backup-falhou.service` | Agenda diária no host e aviso de falha no Telegram |
| `infra/.env.example` | `RCLONE_DESTINO`, `RCLONE_CONFIG_*` (fictícios), `BACKUP_RETENCAO_DIAS=14` |
| `tests/infra/test_backup_restore.py` | Teste de ida e volta (test-writer) |
| `.github/workflows/ci.yml` | `shellcheck infra/backup/*.sh` (o passo de `infra/scripts` do PR 39 pode ser ampliado) |

Do doc: "Backups: `pg_dump` diário dos três bancos + volume de artefatos do MLflow, enviados para fora da VPS (S3 ou Backblaze B2), retenção de 14 dias; testar um restore uma vez por mês". Regra: "Backup sem restore testado não conta como backup."

## 5. Passos

0. (implementer) Registre o marcador `docker: precisa de Docker para construir e rodar imagens` em `pyproject.toml`. Commit `build: add docker test marker`.
1. (test-writer) `tests/infra/test_backup_restore.py` (`@pytest.mark.db`, `@pytest.mark.docker`): constrói a imagem `infra/backup/Dockerfile`; cria no servidor de teste três bancos temporários com uma tabela e linhas conhecidas; cria um diretório temporário fazendo papel do volume de artefatos com um arquivo conhecido; roda `backup.sh` no container com `--network host`, `RCLONE_DESTINO=/destino` (diretório local montado: o rclone aceita caminho local) e as URLs dos bancos; apaga as tabelas e o arquivo; roda `restore.sh <data>`; confere as linhas e o arquivo. Casos na seção 8. Confirme falha porque a imagem não existe. Commit `test: add backup and restore round trip test`.
2. (implementer) `backup.sh` (`set -euo pipefail`):
   - Para cada banco em `BACKUP_BANCOS` (padrão `ml mlflow prefect`): `pg_dump -Fc` usando `PGHOST`, `PGUSER`, `PGPASSWORD` do ambiente.
   - `tar czf artefatos.tgz -C /artefatos .`.
   - `rclone copy <dir> "$RCLONE_DESTINO/<AAAA-MM-DD>/"`; depois `rclone delete --min-age "${BACKUP_RETENCAO_DIAS}d" "$RCLONE_DESTINO"` e `rclone rmdirs --leave-root "$RCLONE_DESTINO"`.
   - Imprime `backup ok <data> <tamanhos>`.
3. `restore.sh <AAAA-MM-DD>`: valida a data; `rclone copy "$RCLONE_DESTINO/<data>/" <tmp>`; para cada banco, `pg_restore --clean --if-exists --no-owner -d <banco>`; extrai os artefatos em `/artefatos` (que no restore é montado com escrita). Imprime `restore ok <data>`.
4. Compose: serviço `backup` com `build: ./backup`, `profiles: ["jobs"]`, `restart: "no"`, `environment` com o usuário admin e `RCLONE_*`, volume `mlflow_artifacts:/artefatos:ro`.
5. Units systemd: `plataforma-backup.service` (`Type=oneshot`, `ExecStart=/usr/bin/docker compose -f /opt/plataforma/infra/docker-compose.yml run --rm backup`, `OnFailure=plataforma-backup-falhou.service`); `.timer` às 03:00 (`OnCalendar=*-*-* 03:00:00`, `Persistent=true`); `plataforma-backup-falhou.service` chama `curl` para a API do Telegram com `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` lidos de `EnvironmentFile=/opt/plataforma/infra/.env`.
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/infra/test_backup_restore.py` (com Docker e o Postgres de teste) | Passa |
| `shellcheck infra/backup/*.sh` | Sem saída |
| `systemd-analyze verify infra/systemd/*.service infra/systemd/*.timer` (Linux; manual se não houver no CI) | Sem erro |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: o próprio doc e a regra de infra exigem restore testado; o teste de ida e volta é essa prova, a cada PR.

## 8. Casos de teste

1. Backup de três bancos com linhas conhecidas e um arquivo de artefato → o destino tem `<data>/ml.dump`, `mlflow.dump`, `prefect.dump`, `artefatos.tgz`.
2. Depois de apagar as tabelas e o arquivo, `restore.sh <data>` → linhas e arquivo de volta, idênticos.
3. Destino com uma pasta de 20 dias atrás (arquivos com data de modificação antiga) e `BACKUP_RETENCAO_DIAS=14` → a pasta antiga some; a de hoje fica.
4. Banco inacessível → `backup.sh` sai com código ≠ 0 e nada é enviado ao destino para essa data.
5. `restore.sh 2026-13-01` → código ≠ 0, nenhum banco tocado.
6. Compose: `backup` em profile, sem `ports`, artefatos montados `:ro`.

## 9. Riscos e perguntas em aberto

- P16: destino (Backblaze B2 ou S3) e agendamento (systemd no host, como aqui, ou flow do Prefect). Systemd foi escolhido para o backup não depender do Prefect, que é um dos bancos salvos.
- Restaurar `prefect` e `mlflow` com os serviços no ar pode corromper o estado; o `restore.sh` não para serviços. O procedimento do item 59 manda parar `mlflow`, `prefect-server` e `prefect-worker` antes.
- Dumps sem criptografia no destino; se o bucket não for privado, isso vaza dados. Considerar `rclone crypt` (decisão do usuário).

## 10. Decisões que exigem ADR

- ADR curto "Backup: destino, agendamento e retenção" (P16), antes do item 59.
