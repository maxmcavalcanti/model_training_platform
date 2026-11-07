---
paths:
  - "infra/**"
  - ".github/**"
---

# Infra e CI/CD

- Todo serviço no compose tem `restart: unless-stopped`.
- MLflow e Prefect não têm autenticação própria: nunca expor sem proxy com auth ou sem Tailscale.
- Firewall: só 22 e 443 abertos, ou nenhuma porta pública. Não abrir porta para "testar".
- `.env` da VPS fica fora do git, permissão 600. Segredos do CI vão em GitHub Secrets.
- Deploy só sai de merge na `main`. Nada de SSH manual para mudar produção.
- Backup sem restore testado não conta como backup.
