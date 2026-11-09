# 40 — Prova do deploy automático e CI do repo `models` (manual / coordenação)

> Executa: **usuário**, com a cientista de dados para a parte do repo `models`. Depende de: 36 e 39 mergeados, itens 38 e S6 concluídos, o **verificador instalado e o bootstrap do plano 39 (passos 9A e 9B) feitos, com o primeiro deploy automático em `success`**, e o PR de `.claude/rules/infra.md` que remove a exceção do ADR 0004 (plano 39, seção 10) mergeado.
> Fase do roadmap: Fase 3 de `docs/plataforma-ml.md` — "Pipelines do GitHub Actions nos dois repositórios"; "Pronto quando: um merge na `main` chega à VPS sem eu entrar nela".
> Revisado em 2026-11-08 contra a `main` em `05c32c9`, com as correções da revisão independente (aceitas pelo usuário). A prova não usa SSH nem para conferir (a evidência vem do log do Actions e da tailnet), confere digest e attestation (`actions/attest`, PR 37), e o CI do `models` vem completo, com actions por SHA e `permissions` mínimas. Revisão final (mesmo dia): pré-condição do bootstrap do primeiro deploy (plano 39, passo 9).
> **Alinhado em 2026-11-09 ao ADR 0007** (`main` em `7fc1923`): conferência do SHA antes do "Re-run" do bootstrap; checagem de vazamento de host/IP também num run **com falha**; a attestation é controle **no deploy** (o `deploy.sh` verifica antes do `pull` e imprime `provenance ok`), e a conferência manual daqui é uma confirmação independente, não o controle.

## Por que é manual

A prova exige observar produção e fazer um merge real. O repositório `models` é de outra dona: este plano não escreve nada lá; dá o arquivo pronto para ela (ou um agente no repo dela, com a aprovação dela) colar.

Marcadores: `<owner>`, `<repo>` (este repo, `platform`), `<models-owner>/models`, `<vps-host>`, `<tailnet>`. Nunca grave os valores reais em arquivo do repo.

## Checklist — pré-condição: bootstrap do primeiro deploy (plano 39, passo 9)

O item 38 deixa a VPS num commit anterior ao PR 39, e a forced command aponta para `/opt/platform/infra/scripts/deploy.sh`, que só existe a partir do PR 39. Por isso o run do `deploy.yml` disparado pelo merge do PR 39 falha no job `deploy`, sem tocar em nada. O verificador de attestation (`gh` fixado) já precisa estar na VPS (plano 39, passo 9A, antes do merge). Se o bootstrap ainda não foi feito:

- [ ] No notebook: `gh pr view <número do PR 39> --json mergeCommit -q .mergeCommit.oid` → `S` (o SHA do merge mostrado no GitHub).
- [ ] Fora de 06:00–08:00 BRT, na VPS, como `deploy`, **só** isto (sem `docker`):

  ```bash
  git -C /opt/platform fetch origin main && git -C /opt/platform checkout --detach origin/main
  git -C /opt/platform rev-parse HEAD
  ```

  → tem de ser `S` ou o SHA de um merge **posterior já revisado**. Outro valor: pare e siga o procedimento de emergência (`docs/plans/38-segredos-ci-cd-manual.md`).
- [ ] No notebook, reexecutar o run **desse** SHA, não outro: `gh run list --workflow deploy.yml --branch main --json databaseId,headSha -q '.[] | select(.headSha=="<HEAD conferido>") | .databaseId'` e `gh run rerun <databaseId> --failed` (com a opção (b2) do S6, aprovar o deployment). A reexecução de um run antigo é recusada pelo fast-forward (`refusing to deploy an older commit`), sem efeito.
- [ ] `gh run view <databaseId> --log | grep -E "provenance ok jobs=sha256:[0-9a-f]{64} mlflow=sha256:[0-9a-f]{64}"` → uma linha; `gh run view <databaseId> --log | grep -E "deploy ok [0-9a-f]{40} jobs=sha256:"` → uma linha. A exceção do ADR 0004 termina aqui (ADR 0007, item 8); depois disso, nenhum comando manual na VPS muda produção fora do procedimento de emergência, e o PR de `.claude/rules/infra.md` e o PR de status do ADR 0004 podem ser abertos.

Esse checkout é a única ação manual permitida entre o item 38 e o primeiro deploy automático bem-sucedido. A prova abaixo é outro merge, depois dele, sem nenhum acesso manual.

## Checklist — vazamento no log público, também em run com falha

O GitHub mascara o valor **exato** de cada segredo (`VPS_HOST`), não variações: outro IP da tailnet (por exemplo, o do próprio nó efêmero do CI), IPv6, o nome `*.ts.net` ou mensagens de erro do `ssh`/Tailscale. Um run com falha tende a imprimir mais do que um run verde. Por isso a checagem roda nos dois:

- [ ] Run **com falha**: o run do merge do PR 39 antes do bootstrap (falhou por desenho). `gh run view <id do run que falhou> --log | grep -Ei "ts\.net|100\.[0-9]+\.[0-9]+\.[0-9]+|fd7a:115c:a1e0"` → nada. Se houver outro run com falha disponível (janela fechada, deploy falho), repetir nele.
- [ ] Run **com sucesso**: o mesmo `grep` no run da prova (abaixo) → nada.
- [ ] Se algum `grep` achar algo: tratar como vazamento (o log é público), registrar numa issue sem copiar o valor, avaliar trocar o que vazou e ajustar o workflow (`log-mode`, redirecionamento do stderr do `ssh`) em PR próprio. Se nenhum run com falha estiver disponível, registre no fechamento da fase que só runs verdes foram conferidos (risco aceito conscientemente).

## Checklist — prova do deploy (este repo)

Faça fora da janela de deploy (não entre 06:00 e 08:00 BRT).

- [ ] Abrir um PR inofensivo: um comentário novo em `infra/docker-compose.yml` (ex.: `# deploy proof <data>`). Não use `infra/health/health`: o conteúdo dele é a resposta da rota de saúde. Passa pelo `code-reviewer` e pelo `pr-reviewer` (toca fora de `docs/**`).
- [ ] CI e `security` verdes (checks required); merge squash (com a opção (b1) do S6, o merge é feito pela conta do mantenedor, não pela dos agentes).
- [ ] **Sem entrar na VPS**, acompanhar: `gh run watch $(gh run list --workflow deploy.yml --branch main --limit 1 --json databaseId -q '.[0].databaseId')` até o fim (com (b2), aprovar o deployment quando ele pedir).
- [ ] No log do job `deploy`: `provenance ok jobs=sha256:... mlflow=sha256:...` **antes** de qualquer linha do `pull`, e `deploy ok <sha do merge> jobs=sha256:... mlflow=sha256:...`. Os digests batem com as linhas `platform-jobs sha256:...` e `platform-mlflow sha256:...` do job `publish`. A linha `provenance ok` é a evidência de que o **controle no deploy** (ADR 0007, item 5) rodou: o `deploy.sh` recusa, antes do `pull`, digest sem attestation do mesmo commit, da `main`, do `deploy.yml`, em runner hospedado.
- [ ] Do notebook, pela tailnet: `curl -s https://<vps-host>.<tailnet>.ts.net:8080/health` → `ok`; na UI do Prefect (`https://<vps-host>.<tailnet>.ts.net:4200`), os deployments `.../production` continuam com agenda; o MLflow (`:5000`) abre.
- [ ] Confirmação independente da attestation (a mesma política do `deploy.sh`, rodada do notebook): para `platform-jobs` e `platform-mlflow`,

  ```bash
  gh attestation verify oci://ghcr.io/<owner>/platform-jobs@<digest> --bundle-from-oci \
    --repo <owner>/<repo> --signer-workflow <owner>/<repo>/.github/workflows/deploy.yml \
    --source-ref refs/heads/main --source-digest <sha do merge> --deny-self-hosted-runners
  ```

  → verificação bem-sucedida. Teste negativo: com `--source-digest` de outro commit da `main` → falha. Isso confere que a política é a esperada; o controle que impede implantar um digest errado é o do `deploy.sh`, não esta conferência.
- [ ] Sem login, de qualquer máquina: `docker pull ghcr.io/<owner>/platform-jobs@<digest>` funciona (pacote público).
- [ ] (Opcional) Se um merge cair entre 06:00 e 08:00, o job `deploy` falha com `deploy window closed`; depois das 08:00, "Re-run failed jobs" na UI do run → `success`, com os mesmos digests do `publish` original. Esse run com falha também serve para o `grep` de vazamento acima.
- [ ] No dia seguinte, depois das 07:30 BRT, pela UI do Prefect: as três ingestões do dia rodaram com sucesso depois do deploy.

Não faça "teste de rollback" nem "teste de attestation inválida" em produção quebrando um deploy de propósito: o rollback, suas exceções, a verificação de proveniência e o backup antes da migração são cobertos pelos testes do PR 39 (casos 15 a 21, 39 a 44 e 46 a 61). Se um deploy real falhar, o log mostra `deploy failed <sha>, rolled back to <sha anterior>`, `provenance verification failed for ...` ou `manual intervention required`; no último caso, siga o procedimento de emergência do item 38 e registre a issue.

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
| Run do merge do PR 39, depois do bootstrap: `gh run view <id> --log \| grep -E "deploy ok [0-9a-f]{40}"` | Uma linha (primeiro deploy automático bem-sucedido), com o SHA conferido no bootstrap |
| `gh run list --workflow deploy.yml --branch main --limit 1 --json conclusion,headSha -q '.[0]'` | `conclusion` `success`; `headSha` = SHA do merge da prova |
| `gh run view <id> --log \| grep -E "provenance ok jobs=sha256:[0-9a-f]{64} mlflow=sha256:[0-9a-f]{64}"` (run da prova) | Uma linha, antes do `pull` (controle no deploy) |
| `gh run view <id> --log \| grep -E "deploy ok [0-9a-f]{40}"` | O SHA do merge da prova |
| `gh run view <id> --log \| grep -Ei "ts\.net\|100\.[0-9]+\.[0-9]+\.[0-9]+\|fd7a:115c:a1e0"` no run da prova **e** no run que falhou antes do bootstrap | Nada nos dois (ou risco registrado se não houver run com falha) |
| `curl -s https://<vps-host>.<tailnet>.ts.net:8080/health` (notebook, tailnet) | `ok` |
| `gh attestation verify oci://ghcr.io/<owner>/platform-jobs@<digest> --bundle-from-oci --repo <owner>/<repo> --signer-workflow <owner>/<repo>/.github/workflows/deploy.yml --source-ref refs/heads/main --source-digest <sha do merge> --deny-self-hosted-runners` | Verificação bem-sucedida (e falha com outro `--source-digest`) |
| Nenhum SSH à mão na VPS durante a prova (o bootstrap é anterior e não conta) | Confirmado por você (é o critério da fase) |
| `gh run list -R <models-owner>/models --workflow ci.yml --limit 1 --json conclusion -q '.[0].conclusion'` | `success` |
| `git ls-remote --tags https://github.com/<models-owner>/models 'v*'` | Pelo menos uma tag `vX.Y.Z` |
| `gh api repos/<models-owner>/models/contents/.github/workflows/ci.yml --jq .content \| base64 -d \| grep -cE "uses: [^@]+@[0-9a-f]{40} # v[0-9]+\.[0-9]+\.[0-9]+"` | `2` (as duas actions por SHA) |

Com isso a Fase 3 está pronta: marcar os checkboxes da Fase 3 em `docs/plataforma-ml.md` num PR só de `docs/**`, e a cientista pode registrar modelos no MLflow.

## Riscos e perguntas em aberto

- **Não verificado:**
  - Se `gh attestation verify` exige autenticação mesmo para pacote público. Na VPS isso já foi provado no plano 39, passo 9A (sem login). No notebook, rode logado se pedir; não muda o critério.
  - Se `uv version --short` existe na versão do `uv` da cientista. Checagem: `uv version --help | grep -- --short` (passo do checklist acima).
- O repo `models` pode não ter `uv.lock`, `ruff` ou testes ainda; nesse caso, o CI dela começa menor e cresce com ela. Não bloquear a Fase 3 pela cobertura de testes do repo dela, mas o arquivo tem de existir e estar verde.
- A prova cobre um merge sem migração. O primeiro merge com migração depois disto é o teste real da ordem `pg_dump` do `ml` → `alembic upgrade head` → `up -d`; faça-o fora da janela e acompanhe o log.
- Se o bootstrap for esquecido, todo merge depois do PR 39 falha no job `deploy` do mesmo jeito, sem efeito na VPS; a correção é sempre o mesmo checkout, a conferência do SHA e o "Re-run" do run desse SHA.
- O mascaramento de segredos cobre só o valor exato; a checagem em run com falha reduz, mas não elimina, o risco de um formato novo de mensagem expor dado da tailnet num run futuro.

## Decisões que exigem ADR

Nenhuma. M4 (versão do pacote no MLflow) é do ADR de execução de modelos (P12, antes do PR 42), listado em `docs/plans/00-indice.md`. O fim da exceção do ADR 0004 no primeiro deploy automático bem-sucedido está registrado no ADR 0007 (`docs/adr/0007-delivery-pipeline.md`, item 8).
