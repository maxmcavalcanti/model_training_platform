# 38 — Segredos e acessos para o deploy automático (manual)

> Executa: **usuário**. Depende de: 37 (merge na `main`, imagens publicadas). Precisa estar pronto antes do merge do PR 39.
> Fase do roadmap: Fase 3 — "Pipelines do GitHub Actions" (parte que exige contas e segredos).

## Por que é manual

Envolve criar credenciais em três lugares (Tailscale, VPS, GitHub) que nenhum agente pode ver.
Regra (`.claude/rules/infra.md`): "Segredos do CI vão em GitHub Secrets".

## Checklist

Tailscale (o runner do GitHub entra na tailnet só durante o deploy):

- [ ] Na ACL, criar a tag `tag:ci` e permitir `tag:ci` → `vps:22` apenas.
- [ ] Criar um OAuth client (Settings → OAuth clients) com escopo para dispositivos efêmeros e a tag `tag:ci`. Guardar `client_id` e `secret`.

VPS:

- [ ] Gerar um par de chaves só para o deploy: `ssh-keygen -t ed25519 -f deploy_ci -C github-actions -N ""`.
- [ ] Em `~deploy/.ssh/authorized_keys`, adicionar a pública com restrições: `restrict,command="/opt/plataforma/infra/scripts/deploy.sh" ssh-ed25519 AAAA... github-actions` (o script vem no PR 39; até lá a chave não funciona, o que é o esperado).
- [ ] Se o repositório for privado (P2): criar um token do GitHub com escopo `read:packages` e fazer, na VPS, `echo <token> | docker login ghcr.io -u <usuario> --password-stdin`.
- [ ] Em `infra/.env`: `GHCR_DONO=<dono em minúsculas>`, `IMAGEM_TAG=main`.
- [ ] Trocar o fluxo manual: `docker compose -f infra/docker-compose.yml pull && docker compose -f infra/docker-compose.yml up -d --remove-orphans` (sem `build`).

GitHub (Settings → Environments → `producao`):

- [ ] Criar o environment `producao`, restrito à branch `main`.
- [ ] Secrets do environment: `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET`, `VPS_HOST` (nome no Tailscale), `VPS_SSH_KEY` (conteúdo da chave privada `deploy_ci`), `VPS_KNOWN_HOSTS` (saída de `ssh-keyscan <nome-tailscale>` feita de dentro da tailnet).
- [ ] Apagar `deploy_ci` (privada) do disco local depois de colar no GitHub.

## Verificação de pronto

| Comando | Saída esperada |
| --- | --- |
| `gh secret list --env producao` | Os cinco nomes acima |
| Na VPS: `docker compose -f infra/docker-compose.yml pull jobs` | Baixa `ghcr.io/<dono>/plataforma-jobs:main` sem erro de autenticação |
| Na VPS: `docker compose -f infra/docker-compose.yml up -d --remove-orphans && docker compose -f infra/docker-compose.yml ps` | Todos `Up`, imagens do GHCR |
| No painel do Tailscale | ACL com `tag:ci` só para a porta 22 da VPS |
