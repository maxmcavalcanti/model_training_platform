---
paths:
  - "infra/**"
  - ".github/**"
---

# Infra e CI/CD

- Todo serviço do compose sem `profiles` tem `restart: unless-stopped`. Serviço de execução única, declarado em `profiles` e rodado com `docker compose run --rm` (ex.: `jobs`), tem `restart: "no"`, com aspas, porque sem aspas o YAML lê `false` (ADR 0004). Todo serviço, com ou sem `profiles`, tem `mem_limit`.
- MLflow, Prefect e Grafana não têm autenticação adequada: só em `127.0.0.1`, expostos na tailnet por `tailscale serve`; a ACL do Tailscale é o controle de acesso (ADR 0003).
- Firewall: nenhuma porta pública (ADR 0003). A 22 pública só durante o provisionamento. Nenhuma porta do compose em `0.0.0.0` (o Docker passa por cima do ufw). Não ligar o Tailscale SSH. Não abrir porta para "testar".
- `.env` da VPS fica fora do git, permissão 600. Segredos do CI vão em GitHub Secrets.
- Deploy só sai de merge na `main`. Nada de SSH manual para mudar produção. Exceção registrada até o PR 39 (ADR 0004): o usuário atualiza a VPS à mão, por SSH pela tailnet (ADR 0003), com `git pull` e `docker compose up`, e a imagem dos jobs é construída na própria VPS até o PR 37. Quem aplica esse deploy é o usuário, nunca um agente.
- Backup sem restore testado não conta como backup.
