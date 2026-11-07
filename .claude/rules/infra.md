---
paths:
  - "infra/**"
  - ".github/**"
---

# Infra e CI/CD

- Todo serviço no compose tem `restart: unless-stopped`.
- MLflow, Prefect e Grafana não têm autenticação adequada: só em `127.0.0.1`, expostos na tailnet por `tailscale serve`; a ACL do Tailscale é o controle de acesso (ADR 0003).
- Firewall: nenhuma porta pública (ADR 0003). A 22 pública só durante o provisionamento. Nenhuma porta do compose em `0.0.0.0` (o Docker passa por cima do ufw). Não ligar o Tailscale SSH. Não abrir porta para "testar".
- `.env` da VPS fica fora do git, permissão 600. Segredos do CI vão em GitHub Secrets.
- Deploy só sai de merge na `main`. Nada de SSH manual para mudar produção.
- Backup sem restore testado não conta como backup.
