# 31 — Subir MLflow e Prefect na VPS e dar acesso à cientista (manual)

> Executa: **usuário**. Depende de: 28, 29, 30 (merges na `main`).
> Fase do roadmap: Fase 3 — "MLflow e Prefect no compose, atrás do Caddy" → libera o treino com registro.

## Checklist

- [ ] DNS (opção de rede pública): registros `A` para `mlflow.<dominio>` e `prefect.<dominio>` apontando para a VPS. Conferir com `dig +short`.
- [ ] Gerar senhas para `MLFLOW_DB_SENHA` e `PREFECT_DB_SENHA`; gerar o hash do `basic_auth` da cientista (`docker run --rm caddy:2 caddy hash-password --plaintext '<senha>'`).
- [ ] Na VPS, em `/opt/plataforma`: `git pull`; acrescentar ao `infra/.env` as variáveis novas de `infra/.env.example` (lembrar `$$` nos hashes); conferir `chmod 600`.
- [ ] `docker compose -f infra/docker-compose.yml build jobs mlflow`.
- [ ] `docker compose -f infra/docker-compose.yml run --rm jobs python -m ingestion criar-bancos; echo $?` → `0`.
- [ ] `docker compose -f infra/docker-compose.yml up -d mlflow prefect-server caddy`.
- [ ] Enviar à cientista, por canal seguro: `MLFLOW_TRACKING_URI=https://mlflow.<dominio>`, usuário e senha do `basic_auth`, URL da UI do Prefect.

## Verificação de pronto

Do notebook:

| Comando | Saída esperada |
| --- | --- |
| `curl -s -o /dev/null -w '%{http_code}' https://mlflow.<dominio>/` | `401` |
| `curl -s -u <usuario>:<senha> https://mlflow.<dominio>/health` | `OK` |
| `curl -s -o /dev/null -w '%{http_code}' https://prefect.<dominio>/` | `401` |
| `curl -s -u <usuario>:<senha> https://prefect.<dominio>/api/health` | `true` |

No notebook dela (prova de que o registro funciona):

```
MLFLOW_TRACKING_URI=https://mlflow.<dominio> MLFLOW_TRACKING_USERNAME=<u> MLFLOW_TRACKING_PASSWORD=<s> \
uv run --with mlflow==<versão do servidor> python -c "import mlflow; mlflow.set_experiment('smoke'); 
with mlflow.start_run(): mlflow.log_metric('x', 1); mlflow.log_text('ok', 'a.txt')"
```

- [ ] A execução aparece na UI do MLflow com a métrica `x` e o artefato `a.txt` baixável (prova de `--serve-artifacts`).

Reboot:

- [ ] `sudo reboot`; depois, os quatro `curl` acima dão o mesmo resultado sem intervenção.
- [ ] `docker stats --no-stream` (critério do doc para o tamanho da VPS): anotar o uso de memória total; se passar de ~80% da RAM, avisar no planejamento.
