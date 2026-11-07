# 31 — Subir MLflow e Prefect na VPS e dar acesso à cientista (manual)

> Executa: **usuário**. Depende de: 28, 28a, 29, 30 (merges na `main` e checkpoint de memória feito).
> Fase do roadmap: Fase 3 — "MLflow e Prefect no compose" → libera o treino com registro. Rede só Tailscale (ADR do PR 03): sem DNS, sem senha de proxy.

## Checklist

- [ ] Gerar senhas para `MLFLOW_DB_SENHA` e `PREFECT_DB_SENHA` (ex.: `openssl rand -base64 24`). Guardar no gerenciador de senhas.
- [ ] Na VPS, em `/opt/plataforma`: `git pull`; acrescentar ao `infra/.env` as variáveis novas de `infra/.env.example`; conferir `TS_HOSTNAME` e `chmod 600`.
- [ ] `docker compose -f infra/docker-compose.yml build jobs mlflow`.
- [ ] `docker compose -f infra/docker-compose.yml run --rm jobs python -m ingestion criar-bancos; echo $?` → `0`.
- [ ] `docker compose -f infra/docker-compose.yml up -d mlflow prefect-server`.
- [ ] `infra/scripts/tailscale-serve.sh`; `tailscale serve status` lista as portas 8080, 5000 e 4200.
- [ ] ACL do Tailscale: liberar para a cientista `tag:plataforma:5432,5000,4200` (Grafana, 3000, entra no item 50). Nada além disso.
- [ ] Enviar à cientista: `MLFLOW_TRACKING_URI=https://<host>.ts.net:5000` e a URL da UI do Prefect `https://<host>.ts.net:4200`. Não há senha de proxy; o acesso é estar na tailnet.

## Verificação de pronto

Do notebook (na tailnet):

| Comando | Saída esperada |
| --- | --- |
| `curl -s https://<host>.ts.net:5000/health` | `OK` |
| `curl -s https://<host>.ts.net:4200/api/health` | `true` |

De fora da tailnet (celular no 4G): `curl -s --max-time 5 http://<ip-publico>:5000/health` e `...:4200/api/health` falham.

Na VPS: `docker ps --format '{{.Names}} {{.Ports}}' | grep -c '0\.0\.0\.0'` → `0`.

No notebook dela (prova de que o registro funciona):

```
MLFLOW_TRACKING_URI=https://<host>.ts.net:5000 \
uv run --with mlflow==<versão do servidor> python -c "import mlflow; mlflow.set_experiment('smoke'); 
with mlflow.start_run(): mlflow.log_metric('x', 1); mlflow.log_text('ok', 'a.txt')"
```

- [ ] A execução aparece na UI do MLflow com a métrica `x` e o artefato `a.txt` baixável (prova de `--serve-artifacts`).

Reboot:

- [ ] `sudo reboot`; depois, os dois `curl` acima dão o mesmo resultado sem intervenção.

Memória (mesmos comandos e gatilhos do 28a):

- [ ] Com MLflow e Prefect no ar, em repouso e durante um job: `free -m`, `docker stats --no-stream`, `vmstat 5 12`, `sudo dmesg -T | grep -i -E 'out of memory|killed process'`.
- [ ] Se um gatilho do 28b disparar (`available` abaixo de ~150 MB, swap em uso constante ou OOM do kernel), faça o 28b antes do PR 32. Sem gatilho, segue em 1 GB. Anote os números.
