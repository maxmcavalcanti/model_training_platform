# ADR 0006: Validação de segurança em CI

Status: Aceito
Data: 2026-11-08
Decisores: Maximiliano

## Contexto

Este ADR foi escrito pela skill `generate-adr` a pedido do usuário, com revisão do Opus. Os nomes seguem o ADR 0001.

- O repositório é público, tem um único mantenedor e o CI atual roda apenas lint, testes e `compose-smoke`. Não há varredura de segredos, de dependências, de imagens nem dos próprios workflows.
- "Merge na `main` é a única forma de mudar produção", e o deploy futuro será por SSH pelo CI, usando Tailscale e imagens no GHCR (PRs 37 a 39). O CI passa a ser superfície de ataque.
- Em 2026-03-19, 76 das 77 tags do `aquasecurity/trivy-action` foram redirecionadas para commits maliciosos (Aqua Security: https://www.aquasec.com/blog/trivy-supply-chain-attack-what-you-need-to-know/). Fonte citada pela pesquisa que embasou este ADR; o número exato não foi reconferido na página (sem acesso de rede no momento da revisão). Tags de action não são imutáveis; só o SHA do commit é.
- Os recursos de segurança do GitHub (secret scanning, CodeQL, Dependabot, dependency review) são gratuitos em repositório público.
- A revisão de segurança por IA já existe localmente (`pr-reviewer` e `/security-review`), sem expor chave de API no CI.

## Decisão

Vamos adotar um fluxo de validação de segurança em CI, em camadas e em etapas:

1. **Settings do GitHub** (feitas pelo dono do repositório): secret scanning e push protection, CodeQL em default setup (que também analisa `actions`), alertas e atualizações de segurança do Dependabot, private vulnerability reporting, "Require approval for all external contributors" e "Workflow permissions" em read-only. As Settings são exceção controlada à regra "merge na `main` é a única forma de mudar produção": mudam segurança, não produção. Como vivem fora do git, haverá um item manual verificável (`docs/plans/NNa-settings-seguranca-manual.md`, a ser criado pelo `task-planner`) com uma checagem por `gh api` para cada Setting. O `SECURITY.md` não é Setting: entra no PR do `dependabot.yml`.
2. **`.github/dependabot.yml`** para os ecossistemas `github-actions`, `docker`, `docker-compose` e `uv`, com `directories` `/`, `/infra/jobs` e `/infra`, `cooldown` e `groups`, semanal.
3. **Workflow `security.yml`**, sem filtro `paths:` (um check required com `paths:` fica pendente para sempre em PR só de docs) e com nomes de job estáveis. Três checagens:
   - `zizmor`, que analisa os workflows;
   - `dependency-review-action` com `fail-on-severity: high`;
   - Trivy `config` no(s) Dockerfile(s) e `fs` para vulnerabilidades e segredos, severidades HIGH e CRITICAL, com `ignore-unfixed`. Não se afirma que o `trivy config` cobre o `docker-compose`: as regras do compose seguem nos testes de `tests/infra/` e no `compose-smoke`. O Trivy roda por action pinada por SHA conferido ou por imagem fixada por digest.
4. **Todas as actions pinadas por SHA** com comentário `# vX.Y.Z` ao lado (o Dependabot atualiza os dois), inclusive as do `ci.yml` atual, e `persist-credentials: false` no checkout. O comentário do `setup-uv` no `ci.yml` ("publishes no floating major tag") deixa de valer e é substituído por esse padrão. Os planos 37 e 39, que mandam fixar "por major", passam a pin por SHA; o alinhamento dos planos entra no PR do pin.
5. **Imagens de terceiros** no Dockerfile e no compose (uv, postgres, busybox) fixadas por `tag@sha256:digest`, mantidas pelo Dependabot (`docker` e `docker-compose`).
6. **Permissões mínimas.** O `security.yml` tem `permissions: {}` no topo; cada job declara o mínimo (`contents: read`, e `security-events: write` só onde sobe SARIF). O `ci.yml` ganha `permissions: contents: read` no topo. Nenhum workflow usa `pull_request_target` nem `workflow_run` com código de PR. Em PR de fork o upload de SARIF é pulado.
7. **Segredos.** Nenhum segredo no nível do repositório. Os segredos do deploy ficam só no environment `production`, restrito à `main` (item 38). `security.yml` e `ci.yml` não usam segredos.
8. **Modo "só avisa".** O job falha (fica vermelho) mas não é required. Critério de saída: zero achados HIGH ou CRITICAL abertos sem exceção registrada, por 2 semanas seguidas de PRs. Cumprido o critério, o usuário torna os checks required no item manual, antes de o deploy automático entrar (até o PR 39). O CodeQL segue o mesmo critério, sobre os alertas do code scanning. OSV-Scanner e Scorecard ficam fora dos quatro PRs abaixo (futuros; o Scorecard exige `id-token: write`).
9. **Política de exceções.** Rebaixar um check é permitido só por exceção versionada (`.trivyignore`, `# zizmor: ignore[...]`, `allow-ghsas`) com motivo, link do alerta e data de revisão, ou por `continue-on-error`. Alerta dispensado no GitHub leva o motivo no campo próprio. A branch protection da `main` usa "Do not allow bypassing".
10. **Dependency graph e `uv.lock`.** Não se afirma que o dependency graph cobre o `uv.lock`. O critério de pronto do PR do `security.yml` inclui conferir o SBOM (`gh api repos/{o}/{r}/dependency-graph/sbom`) e abrir um PR de teste com uma versão vulnerável. Se o grafo não cobrir o `uv.lock`, entra dependency submission ou OSV-Scanner também nos PRs.
11. **Mudanças em `.github/`** passam pelo `code-reviewer` e pelo `pr-reviewer`, como qualquer PR fora de `docs/**`.
12. **Ordem de implementação:** em paralelo à Fase 2, por decisão do usuário em 2026-11-08, em quatro PRs pequenos: (1) pin por SHA e `permissions` no `ci.yml`; (2) `dependabot.yml` (com `SECURITY.md`); (3) `security.yml`; (4) regra `S` do `ruff`.

O CodeQL também analisa `actions` e sobrepõe o `zizmor`; a sobreposição foi aceita.

Ficam fora de escopo agora, e exigem ADR próprio quando entrarem: agente de IA no CI que use segredo de API; Trivy da imagem com attestation, junto da publicação no GHCR (PR 37); `harden-runner` em modo `audit`, quando o deploy por SSH entrar.

## Consequências

**Positivo:**

- Cobre segredos, dependências, workflows e Dockerfile sem custo (o compose segue nos testes de `tests/infra/`).
- O pin por SHA fecha o vetor do incidente do Trivy, e o Dependabot mantém os SHAs atualizados.
- `permissions: {}` por padrão reduz o dano de um workflow comprometido.
- Entrar só avisando permite limpar os achados antes de bloquear merge.

**Negativo:**

- Mais minutos de CI e algum ruído de falso positivo no início.
- O pin por SHA gera PRs semanais do Dependabot para revisar.
- Com um único mantenedor, checks bloqueantes podem travar um merge urgente; o ajuste é corrigir o achado ou rebaixar o check pela política de exceções, por PR próprio, nunca burlar a branch protection.
- Parte da configuração (Settings) vive fora do git e depende do dono do repositório.

## Alternativas consideradas

**Agente de IA no CI** (`claude-code-security-review`, `claude-code-action`): comenta nos PRs automaticamente. Rejeitado por ora porque o README do primeiro diz que não é endurecido contra prompt injection e exige chave de API no CI; o `pr-reviewer` local e o `/security-review` cobrem a necessidade.

**Semgrep:** SAST com regras da comunidade. Rejeitado porque sobrepõe o CodeQL e a própria documentação admite alta tolerância a falsos positivos.

**bandit:** linter de segurança para Python. Rejeitado em favor de ligar a regra `S` do `ruff` (flake8-bandit), que cobre o mesmo. O `pyproject.toml` hoje seleciona só `E`, `F`, `I`, `B` e `UP`, então a regra `S` entra num PR próprio (o quarto da ordem), com ignores justificados (por exemplo `S101` em `tests/`).

**checkov:** IaC e Dockerfile. Rejeitado porque o Trivy `config` cobre o Dockerfile com menos ruído.

**pip-audit:** auditoria de dependências Python. Rejeitado porque o `dependency-review-action` (PRs) e o OSV-Scanner (agendado, lê `uv.lock`) cobrem o caso (o OSV-Scanner é um acréscimo futuro, ver o item 8 da Decisão).

**Tags de versão nas actions em vez de SHA:** mais simples de ler. Rejeitado porque tags podem ser redirecionadas, como no incidente do `trivy-action`.
