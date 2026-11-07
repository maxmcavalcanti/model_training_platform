# 38 — Segredos e acessos para o deploy automático (manual)

> Executa: **usuário**. Depende de: 37 (merge na `main`, imagens publicadas). Precisa estar pronto antes do merge do PR 39.
> Fase do roadmap: Fase 3 — "Pipelines do GitHub Actions" (parte que exige contas e segredos).

## Por que é manual

Envolve criar credenciais em três lugares (Tailscale, VPS, GitHub) que nenhum agente pode ver.
Regra (`.claude/rules/infra.md`): "Segredos do CI vão em GitHub Secrets". Os repositórios são públicos (P2 resolvida, 2026-11-07): nenhum destes valores pode aparecer em arquivo do repo, em log do Actions ou em commit, nem por um instante; um segredo que vaze para o histórico precisa ser trocado. A VPS não precisa de credencial de leitura: o repo e as imagens são públicos.

## Checklist

Tailscale (o runner do GitHub entra na tailnet só durante o deploy):

- [ ] Na ACL, criar a tag `tag:ci` e permitir `tag:ci` → `tag:plataforma:22,8080` apenas (22 para o SSH do deploy; 8080 para a checagem final de `/saude` do PR 39).
- [ ] Criar um OAuth client (Settings → OAuth clients) com escopo para dispositivos efêmeros e a tag `tag:ci`. Guardar `client_id` e `secret`.

VPS:

- [ ] Gerar um par de chaves só para o deploy: `ssh-keygen -t ed25519 -f deploy_ci -C github-actions -N ""`.
- [ ] Em `~deploy/.ssh/authorized_keys`, adicionar a pública com restrições: `restrict,command="/opt/plataforma/infra/scripts/deploy.sh" ssh-ed25519 AAAA... github-actions` (o script vem no PR 39; até lá a chave não funciona, o que é o esperado).
- [ ] Conferir a visibilidade dos pacotes no GitHub (perfil → Packages → `plataforma-jobs` e `plataforma-mlflow` → Package settings): **Public**. Pacote do GHCR pode nascer privado mesmo com repo público. Não crie token de leitura nem faça `docker login` na VPS.
- [ ] Em `infra/.env`: `GHCR_DONO=<dono em minúsculas>`, `IMAGEM_TAG=main`.
- [ ] Trocar o fluxo manual: `docker compose -f infra/docker-compose.yml pull && docker compose -f infra/docker-compose.yml up -d --remove-orphans` (sem `build`).

GitHub (Settings → Environments → `producao`):

- [ ] Criar o environment `producao`, restrito à branch `main`.
- [ ] Secrets do environment: `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET`, `VPS_HOST` (nome no Tailscale), `VPS_SSH_KEY` (conteúdo da chave privada `deploy_ci`), `VPS_KNOWN_HOSTS` (saída de `ssh-keyscan <nome-tailscale>` feita de dentro da tailnet).
- [ ] Variável (não segredo) do environment: `TS_HOSTNAME` (`<host>.<tailnet>.ts.net`), usada na checagem final do deploy.
- [ ] Apagar `deploy_ci` (privada) do disco local depois de colar no GitHub.

## Verificação de pronto

| Comando | Saída esperada |
| --- | --- |
| `gh secret list --env producao` | Os cinco nomes acima |
| Na VPS: `docker logout ghcr.io; docker compose -f infra/docker-compose.yml pull jobs` | Baixa `ghcr.io/<dono>/plataforma-jobs:main` sem login e sem erro de autenticação |
| Na VPS: `test -f ~/.docker/config.json && grep -c ghcr.io ~/.docker/config.json` | Vazio ou `0` (nenhuma credencial do GHCR salva) |
| `gh variable list --env producao` | `TS_HOSTNAME` |
| Na VPS: `docker compose -f infra/docker-compose.yml up -d --remove-orphans && docker compose -f infra/docker-compose.yml ps` | Todos `Up`, imagens do GHCR |
| No painel do Tailscale | ACL com `tag:ci` só para as portas 22 e 8080 da VPS |
