# 59 — Telegram, destino de backup, restore real e critério de pronto da Fase 5 (manual)

> Executa: **usuário**. Depende de: 54, 55, 56, 57, 58 (merges na `main`, deploy automático). O bot do Telegram pode ser criado antes, a qualquer momento.
> Fase do roadmap: Fase 5 — "Alertas no Telegram, backups com restore testado"; "Pronto quando: o painel mostra erro real × previsto atualizando sozinho".

## Por que é manual

Criar bot e bucket exige contas externas; instalar units systemd e testar restore exige SSH na VPS e julgamento.

## Checklist — Telegram

- [ ] Criar o bot com o @BotFather (`/newbot`), guardar o token.
- [ ] Mandar uma mensagem ao bot (ou criar um grupo e adicioná-lo) e obter o `chat_id`: `curl -s https://api.telegram.org/bot<token>/getUpdates`.
- [ ] Na VPS, `infra/.env`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Reaplicar o último deploy (`gh run rerun <id>` do `deploy.yml`).
- [ ] Teste de ponta a ponta: na UI do Prefect, disparar `ingest_ons_carga/producao` com `inicio` depois de `fim` (falha de propósito) → chega mensagem no Telegram com o nome do flow e o link.

## Checklist — backup

- [ ] Criar bucket privado (Backblaze B2 ou S3, decisão P16) e uma chave restrita a ele.
- [ ] Na VPS, `infra/.env`: `RCLONE_DESTINO` e as variáveis `RCLONE_CONFIG_<REMOTO>_*` do provedor (ver documentação do rclone para B2/S3).
- [ ] Instalar as units: `sudo cp /opt/plataforma/infra/systemd/plataforma-backup* /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now plataforma-backup.timer`.
- [ ] Rodar uma vez: `sudo systemctl start plataforma-backup.service && journalctl -u plataforma-backup.service -n 20` → `backup ok <data>`.
- [ ] Teste de falha: trocar temporariamente `RCLONE_DESTINO` por um inválido, rodar o serviço, ver a mensagem de falha no Telegram, restaurar o valor.

## Checklist — restore real (e depois todo mês)

- [ ] Restaurar num ambiente separado, não em produção: no notebook, com o compose de dev (`docker compose -f infra/docker-compose.dev.yml up -d`), rodar a imagem `backup` com `restore.sh <data>` apontando para o Postgres de dev e um diretório local de artefatos.
- [ ] Conferir: `select count(*) from raw.ons_carga_diaria` igual ao de produção no dia do backup; uma execução do MLflow com artefato abre.
- [ ] Agendar lembrete mensal (calendário) para repetir.

## Verificação de pronto da Fase 5

| Onde | Comando / ação | Esperado |
| --- | --- | --- |
| VPS | `systemctl list-timers plataforma-backup.timer` | Próxima execução às 03:00 |
| Destino | `rclone lsd "$RCLONE_DESTINO"` (na VPS, com o `.env` carregado) | Pastas diárias, nenhuma com mais de 14 dias |
| Grafana | Painel "Erro dos modelos", modelo `media_movel` | Métrica diária e médias móveis, com o último ponto de ontem ou anteontem |
| Dia seguinte | Mesmo painel, sem nenhuma ação | Um ponto novo (atualizou sozinho) |
| Telegram | Simular disco cheio não é prático; parar o MLflow por 20 min (`docker compose stop mlflow`) | Alerta `mlflow` e depois `RESOLVIDO` ao subir de novo (`docker compose start mlflow`) |

Parar o MLflow à mão é uma intervenção em produção para teste; combinar a janela com a cientista. Com tudo acima, o roadmap das Fases 0 a 5 está completo.
