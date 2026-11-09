# 40 — Prova do deploy automático e CI do repo `models` (manual / coordenação)

> Executa: **usuário**, com a cientista de dados para a parte do repo `models`. Depende de: 36 e 39 mergeados, item 38 concluído, o **bootstrap do plano 39 (passo 9) feito e o primeiro deploy automático com `success`**, e o PR de `.claude/rules/infra.md` que remove a exceção do ADR 0004 (plano 39, seção 10) mergeado.
> Fase do roadmap: Fase 3 de `docs/plataforma-ml.md` — "Pipelines do GitHub Actions nos dois repositórios"; "Pronto quando: um merge na `main` chega à VPS sem eu entrar nela".
> Revisado em 2026-11-08 contra a `main` em `05c32c9`, com as correções da revisão independente (aceitas pelo usuário). A prova não usa SSH nem para conferir (a evidência vem do log do Actions e da tailnet), confere digest e attestation (`actions/attest`, PR 37), e o CI do `models` vem completo, com actions por SHA e `permissions` mínimas. Revisão final (mesmo dia): pré-condição do bootstrap do primeiro deploy (plano 39, passo 9).

## Por que é manual

A prova exige observar produção e fazer um merge real. O repositório `models` é de outra dona: este plano não escreve nada lá; dá o arquivo pronto para ela (ou um agente no repo dela, com a aprovação dela) colar.

Marcadores: `<owner>`, `<repo>` (este repo, `platform`), `<models-owner>/models`, `<vps-host>`, `<tailnet>`. Nunca grave os valores reais em arquivo do repo.

## Checklist — pré-condição: bootstrap do primeiro deploy (plano 39, passo 9)

O item 38 deixa a VPS num commit anterior ao PR 39, e a forced command aponta para `/opt/platform/infra/scripts/deploy.sh`, que só existe a partir do PR 39. Por isso o run do `deploy.yml` disparado pelo merge do PR 39 falha no job `deploy`, sem tocar em nada. Se isso ainda não foi resolvido:

- [ ] Fora de 06:00–08:00 BRT, na VPS, como `deploy`, **só** isto (sem `docker`):

  ```bash
  git -C /opt/platform fetch origin main && git -C /opt/platform checkout --detach origin/main
  git -C /opt/platform rev-parse HEAD
  ```

  → o SHA do merge do PR 39 (ou o último da `main`).
- [ ] No Actions, no run que falhou: "Re-run failed jobs". O segundo run vê `HEAD` igual ao SHA implantado, passa a checagem de fast-forward e faz o deploy.
- [ ] `gh run view <id> --log | grep -E "deploy ok [0-9a-f]{40} jobs=sha256:"` → uma linha. A exceção do ADR 0004 termina aqui; depois disso, nenhum comando manual na VPS muda produção, e o PR de `.claude/rules/infra.md` e o PR de status do ADR 0004 podem ser abertos.

Esse checkout é a única ação manual permitida entre o item 38 e o primeiro deploy automático bem-sucedido. A prova abaixo é outro merge, depois dele, sem nenhum acesso manual.

## Checklist — prova do deploy (este repo)

Faça fora da janela de deploy (não entre 06:00 e 08:00 BRT).

- [ ] Abrir um PR inofensivo: um comentário novo em `infra/docker-compose.yml` (ex.: `# deploy proof <data>`). Não use `infra/health/health`: o conteúdo dele é a resposta da rota de saúde. Passa pelo `code-reviewer` e pelo `pr-reviewer` (toca fora de `docs/**`).
- [ ] CI e `security` verdes; merge squash.
- [ ] **Sem entrar na VPS**, acompanhar: `gh run watch $(gh run list --workflow deploy.yml --branch main --limit 1 --json databaseId -q '.[0].databaseId')` até o fim.
- [ ] No log do job `deploy`: `deploy ok <sha do merge> jobs=sha256:... mlflow=sha256:...`. Os digests batem com as linhas `platform-jobs sha256:...` e `platform-mlflow sha256:...` do job `publish`.
- [ ] Do notebook, pela tailnet: `curl -s https://<vps-host>.<tailnet>.ts.net:8080/health` → `ok`; na UI do Prefect (`https://<vps-host>.<tailnet>.ts.net:4200`), os deployments `.../production` continuam com agenda; o MLflow (`:5000`) abre.
- [ ] Attestation da imagem implantada (gerada por `actions/attest` no PR 37): `gh attestation verify oci://ghcr.io/<owner>/platform-jobs@<digest> --repo <owner>/<repo>` e o mesmo para `platform-mlflow` → verificação bem-sucedida.
- [ ] Sem login, de qualquer máquina: `docker pull ghcr.io/<owner>/platform-jobs@<digest>` funciona (pacote público).
- [ ] (Opcional) Se um merge cair entre 06:00 e 08:00, o job `deploy` falha com `deploy window closed`; depois das 08:00, "Re-run failed jobs" na UI do run → `success`, com os mesmos digests do `publish` original.
- [ ] No dia seguinte, depois das 07:30 BRT, pela UI do Prefect: as três ingestões do dia rodaram com sucesso depois do deploy.

Não faça "teste de rollback" em produção quebrando um deploy de propósito: o rollback é coberto pelos testes do PR 39 (casos 15 a 21 e 39 a 44). Se um deploy real falhar, o log mostra `deploy failed <sha>, rolled back to <sha anterior>`; registre o caso.

## Checklist — repo `models` (combinar com ela)

Do doc ("CI/CD e operação"): no PR, `ruff` e `pytest` (testes das funções do contrato com dados de amostra); no merge na `main`, cria tag de versão; o job de score passa a instalar essa versão. A instalação pelo score é Fase 4 (PRs 43 a 45); aqui só o CI e o esquema de tag.

Decisões (recomendações aceitas pelo usuário; a cientista confirma no repo dela):

| Id | Decisão |
| --- | --- |
| M1 | Tag de versão criada **por ela, à mão, depois do merge** (`git tag -a vX.Y.Z` + `git push origin vX.Y.Z`). Sem workflow com `contents: write`. |
| M2 | Esquema **semver `vX.Y.Z`**, igual à `version` do `pyproject.toml` do pacote; o CI confere a igualdade quando roda numa tag. |
| M3 | Mesmos padrões deste repo: actions por SHA com `# vX.Y.Z`, `permissions` mínimas, `persist-credentials: false`, nenhum segredo. Também `.github/dependabot.yml` para `github-actions` e `uv`, e secret scanning + push protection nas Settings. |
| M4 | Versão do pacote no MLflow: fica para o ADR de execução de modelos (P12, antes do PR 42). Não decidir aqui. |

- [ ] Ela (ou um agente no repo dela, com aprovação dela) cria `.github/workflows/ci.yml` no repo `models`. Ponto de partida, com os mesmos SHAs que este repo usa hoje (se o Dependabot deste repo já os atualizou, usar os atuais de `.github/workflows/ci.yml` daqui):

  ```yaml
  name: ci

  on:
    pull_request:
    push:
      branches: [main]
      tags: ["v*"]

  permissions:
    contents: read

  jobs:
    lint-and-test:
      runs-on: ubuntu-latest
      permissions:
        contents: read
      steps:
        - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
          with:
            persist-credentials: false
        - uses: astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3
        - run: uv sync --locked
        - run: uv run ruff check .
        - run: uv run ruff format --check .
        - run: uv run pytest
        - name: Check the tag matches the package version
          if: startsWith(github.ref, 'refs/tags/v')
          run: |
            version="$(uv version --short)"
            test "v$version" = "$GITHUB_REF_NAME"
  ```

  Pressupõe que o repo dela usa `uv` com `uv.lock` versionado, `ruff` e `pytest` no grupo `dev`. Se não usar, ajustar com ela (é o repo dela).
- [ ] Antes, conferir se `uv version --short` existe na versão do `uv` dela: `uv version --help | grep -- --short`. Se não sair nada, trocar a linha por `version="$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"`.
- [ ] Antes do commit, ela roda `uvx zizmor .github/workflows/` no repo dela e corrige os achados.
- [ ] Ela abre o PR com esse arquivo; o CI roda verde; merge.
- [ ] Primeira tag (M1, M2), depois do merge: `git checkout main && git pull && git tag -a v0.1.0 -m "v0.1.0" && git push origin v0.1.0` (com `version = "0.1.0"` no `pyproject.toml`). O CI roda na tag e confere a versão.
- [ ] Combinar com ela que nenhum segredo entra no repo `models` (público, P2), nem em notebook commitado, e que o pacote é instalado pelo score sem token.
- [ ] (M3) `.github/dependabot.yml` no repo dela para `github-actions` e `uv`, e Settings de secret scanning e push protection ligadas.

## Verificação de pronto

| Verificação | Esperado |
| --- | --- |
| Run do merge do PR 39, depois do bootstrap: `gh run view <id> --log \| grep -E "deploy ok [0-9a-f]{40}"` | Uma linha (primeiro deploy automático bem-sucedido) |
| `gh run list --workflow deploy.yml --branch main --limit 1 --json conclusion,headSha -q '.[0]'` | `conclusion` `success`; `headSha` = SHA do merge da prova |
| `gh run view <id> --log \| grep -E "deploy ok [0-9a-f]{40}"` | O SHA do merge da prova |
| `gh run view <id> --log \| grep -Ei "ts\.net\|100\.[0-9]+\.[0-9]+\.[0-9]+"` | Nada |
| `curl -s https://<vps-host>.<tailnet>.ts.net:8080/health` (notebook, tailnet) | `ok` |
| `gh attestation verify oci://ghcr.io/<owner>/platform-jobs@<digest> --repo <owner>/<repo>` | Verificação bem-sucedida |
| Nenhum SSH à mão na VPS durante a prova (o bootstrap é anterior e não conta) | Confirmado por você (é o critério da fase) |
| `gh run list -R <models-owner>/models --workflow ci.yml --limit 1 --json conclusion -q '.[0].conclusion'` | `success` |
| `git ls-remote --tags https://github.com/<models-owner>/models 'v*'` | Pelo menos uma tag `vX.Y.Z` |
| `gh api repos/<models-owner>/models/contents/.github/workflows/ci.yml --jq .content \| base64 -d \| grep -cE "uses: [^@]+@[0-9a-f]{40} # v[0-9]+\.[0-9]+\.[0-9]+"` | `2` (as duas actions por SHA) |

Com isso a Fase 3 está pronta: marcar os checkboxes da Fase 3 em `docs/plataforma-ml.md` num PR só de `docs/**`, e a cientista pode registrar modelos no MLflow.

## Riscos e perguntas em aberto

- **Não verificado:**
  - Se `gh attestation verify` exige autenticação mesmo para pacote público. Checagem: `gh auth status`; rodar o `verify` com `GH_TOKEN` vazio numa sessão sem login (`env -u GH_TOKEN gh attestation verify ...` depois de `gh auth logout`, ou numa máquina sem `gh auth`). Se exigir, rode logado; não muda o critério.
  - Se `uv version --short` existe na versão do `uv` da cientista. Checagem: `uv version --help | grep -- --short` (passo do checklist acima).
- O repo `models` pode não ter `uv.lock`, `ruff` ou testes ainda; nesse caso, o CI dela começa menor e cresce com ela. Não bloquear a Fase 3 pela cobertura de testes do repo dela, mas o arquivo tem de existir e estar verde.
- A prova cobre um merge sem migração. O primeiro merge com migração depois disto é o teste real da ordem `alembic upgrade head` → `up -d`; faça-o fora da janela e acompanhe o log.
- Se o bootstrap for esquecido, todo merge depois do PR 39 falha no job `deploy` do mesmo jeito, sem efeito na VPS; a correção é sempre o mesmo checkout seguido de "Re-run failed jobs".

## Decisões que exigem ADR

Nenhuma. M4 (versão do pacote no MLflow) é do ADR de execução de modelos (P12, antes do PR 42), já listado em `docs/plans/00-indice.md`. O fim da exceção do ADR 0004 no primeiro deploy automático bem-sucedido é registrado no ADR "Pipeline de entrega".
