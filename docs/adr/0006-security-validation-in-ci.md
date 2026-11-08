# ADR-0006: Validação de segurança em CI

**Status:** Aceito **Data:** 2026-11-08

## Contexto

- O repositório é público, tem um único mantenedor e o CI atual roda apenas lint, testes e `compose-smoke`. Não há varredura de segredos, de dependências, de imagens nem dos próprios workflows.
- "Merge na `main` é a única forma de mudar produção", e o deploy futuro será por SSH pelo CI, usando Tailscale e imagens no GHCR (PRs 37 a 39). O CI passa a ser superfície de ataque.
- Em 2026-03-19 as tags do `trivy-action` foram redirecionadas para commits maliciosos. Tags de action não são imutáveis; só o SHA do commit é.
- Os recursos de segurança do GitHub (secret scanning, CodeQL, Dependabot, dependency review) são gratuitos em repositório público.
- A revisão de segurança por IA já existe localmente (`pr-reviewer` e `/security-review`), sem expor chave de API no CI.

## Decisão

Vamos adotar um fluxo de validação de segurança em CI, em camadas e em etapas:

1. **Settings do GitHub** (feitas pelo dono do repositório): secret scanning e push protection, CodeQL em default setup, alertas e atualizações de segurança do Dependabot, private vulnerability reporting, `SECURITY.md` e "Require approval for all external contributors".
2. **`.github/dependabot.yml`** para os ecossistemas `github-actions`, `docker`, `docker-compose` e `uv`, agrupado e semanal.
3. **Workflow `security.yml`** com `permissions: {}` no topo e três checagens:
   - `zizmor`, que analisa os workflows;
   - `dependency-review-action` com `fail-on-severity: high`;
   - Trivy `config` e `fs` em Dockerfile e compose, severidades HIGH e CRITICAL, com `ignore-unfixed`.
4. **Todas as actions pinadas por SHA**, inclusive as do `ci.yml` atual, e `persist-credentials: false` no checkout.
5. **Os checks começam só avisando.** Viram bloqueantes (required na branch protection da `main`) depois de limpar os achados atuais. O CodeQL só avisa até calibrar o ruído. OSV-Scanner semanal e Scorecard ficam apenas informativos.
6. **Mudanças em `.github/`** passam pelo `code-reviewer` e pelo `pr-reviewer`, como qualquer PR fora de `docs/**`.
7. **Ordem de implementação:** depois da Fase 2, em três PRs pequenos: `dependabot.yml`; `security.yml`; pin por SHA das actions existentes.

Ficam fora de escopo agora, e exigem ADR próprio quando entrarem: agente de IA no CI que use segredo de API; Trivy da imagem com attestation, junto da publicação no GHCR (PR 37); `harden-runner` em modo `audit`, quando o deploy por SSH entrar.

## Consequências

**Positivo:**

- Cobre segredos, dependências, workflows e Dockerfile/compose sem custo.
- O pin por SHA fecha o vetor do incidente do Trivy, e o Dependabot mantém os SHAs atualizados.
- `permissions: {}` por padrão reduz o dano de um workflow comprometido.
- Entrar só avisando permite limpar os achados antes de bloquear merge.

**Negativo:**

- Mais minutos de CI e algum ruído de falso positivo no início.
- O pin por SHA gera PRs semanais do Dependabot para revisar.
- Com um único mantenedor, checks bloqueantes podem travar um merge urgente; o ajuste é corrigir o achado ou rebaixar o check por PR próprio, nunca burlar a branch protection.
- Parte da configuração (Settings) vive fora do git e depende do dono do repositório.

## Alternativas consideradas

**Agente de IA no CI** (`claude-code-security-review`, `claude-code-action`): comenta nos PRs automaticamente. Rejeitado por ora porque o README do primeiro diz que não é endurecido contra prompt injection e exige chave de API no CI; o `pr-reviewer` local e o `/security-review` cobrem a necessidade.

**Semgrep:** SAST com regras da comunidade. Rejeitado porque sobrepõe o CodeQL e a própria documentação admite alta tolerância a falsos positivos.

**bandit:** linter de segurança para Python. Rejeitado porque a regra `S` do `ruff` (flake8-bandit) cobre o mesmo e o projeto já usa `ruff`.

**checkov:** IaC e Dockerfile. Rejeitado porque o Trivy `config` cobre o necessário com menos ruído.

**pip-audit:** auditoria de dependências Python. Rejeitado porque o `dependency-review-action` (PRs) e o OSV-Scanner (agendado, lê `uv.lock`) cobrem o caso.

**Tags de versão nas actions em vez de SHA:** mais simples de ler. Rejeitado porque tags podem ser redirecionadas, como no incidente do `trivy-action`.
