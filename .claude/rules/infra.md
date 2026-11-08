---
paths:
  - "infra/**"
  - ".github/**"
---

# Infra e CI/CD

- Todo serviço do compose sem `profiles` tem `restart: unless-stopped`. Serviço de execução única, declarado em `profiles` e rodado com `docker compose run --rm` (ex.: `jobs`), tem `restart: "no"`, com aspas, porque sem aspas o YAML lê `false` (ADR 0004). Todo serviço, com ou sem `profiles`, tem `mem_limit`.
- MLflow, Prefect e Grafana não têm autenticação adequada: só em `127.0.0.1`, expostos na tailnet por `tailscale serve`; a ACL do Tailscale é o controle de acesso (ADR 0003).
- Firewall: nenhuma porta pública (ADR 0003). A 22 pública só durante o provisionamento. Nenhuma porta do compose em `0.0.0.0` (o Docker passa por cima do ufw). Não ligar o Tailscale SSH. Não abrir porta para "testar".
- `.env` da VPS fica fora do git, permissão 600. Segredos de CI e deploy vão em GitHub Secrets do environment `production`, nunca no nível do repositório; `ci.yml` e `security.yml` não usam segredos (ADR 0006, item 7).
- Deploy só sai de merge na `main`. Nada de SSH manual para mudar produção. Exceção registrada até o PR 39 (ADR 0004): o usuário atualiza a VPS à mão, por SSH pela tailnet (ADR 0003), com `git pull` e `docker compose up`, e a imagem dos jobs é construída na própria VPS até o PR 37. Quem aplica esse deploy é o usuário, nunca um agente.
- Backup sem restore testado não conta como backup.
- Workflows (`.github/workflows/**`, ADR 0006): toda action por SHA completo de commit com `# vX.Y.Z` na mesma linha, nunca por tag; `permissions` no topo (`{}` ou `contents: read`) e o mínimo declarado em cada job; `actions/checkout` com `persist-credentials: false`; nenhum gatilho `pull_request_target` nem `workflow_run`; nenhum `secrets.` no `ci.yml` nem no `security.yml`; nenhum `${{ }}` dentro de `run:` (o valor entra por `env:`); `if:` em uma linha só; workflow de check sem filtro `paths:`; o Trivy roda pela imagem fixada por digest (`TRIVY_IMAGE` do `security.yml`), nunca por `aquasecurity/trivy-action` ou `setup-trivy`. Antes de commitar mudança em workflow, rode `uv run zizmor .github/workflows/` e corrija os achados.
- Imagens de terceiros no Dockerfile, no compose e nos `services` do CI: fixadas por `tag@sha256:<digest do índice multi-arch>`, nunca só por tag nem `latest` (ADR 0006, item 5). PR do Dependabot que troca o `postgres` do compose leva o mesmo `tag@sha256:` ao `ci.yml` (e ao `docker-compose.dev.yml`), como descrito no `AGENTS.md`.
- `.env.example` com Docker: o agente pode rodar `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q`, porque quem lê o arquivo é o Docker e o `-q` não imprime nada; o agente continua sem abrir, copiar ou imprimir o arquivo, com qualquer ferramenta (`AGENTS.md`). Nunca rode `config` sem `-q` (imprime os valores interpolados) nem sem `--env-file infra/.env.example` (o compose carregaria `infra/.env`).
