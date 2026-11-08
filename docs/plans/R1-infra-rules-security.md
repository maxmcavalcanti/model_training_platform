# R1: Regras de segurança de workflows e imagens em `.claude/rules/infra.md`

> Executa: o usuário, ou um agente que receba na instrução a autorização explícita do usuário (dada em 2026-11-08) para editar `.claude/`. Por padrão o `task-implementer` não edita `.claude/` (`CLAUDE.md`); ver Q1. Branch sugerida: `chore/infra-rules-security`.
> Origem: S1, Q6 (`docs/plans/S1-pin-sha-e-permissoes-ci.md`) e S3, Q11 (`docs/plans/S3-security-yml.md`), as duas resolvidas como "o usuário acrescenta a regra". S1, S2, S3 e S4 já estão na `main`.
> Nome do arquivo: `R1-<slug>.md`, por pedido desta tarefa, em vez de `<AAAA-MM-DD>-<slug>.md` (mesmo desvio dos planos `S*`, ver `docs/plans/00-indice.md`, "Desvios").
> Revisão: o PR toca `.claude/`, então passa pelo `code-reviewer` e pelo `pr-reviewer`, mesmo sendo só Markdown (`AGENTS.md`, "Fluxo de trabalho").

## 1. Objetivo

Registrar em `.claude/rules/infra.md` as regras do ADR 0006 que já valem nos workflows e nas imagens (pin por SHA, `permissions` mínimas, imagens por digest, zizmor antes do commit), para que planos e agentes que tocam `.github/**` e `infra/**` as recebam automaticamente.
Esclarecer quando um agente pode rodar `docker compose ... --env-file infra/.env.example config -q` sem violar a regra de nunca ler arquivos `.env`.

## 2. Fora do escopo

- A frase da exceção de deploy manual (linha 13 de `.claude/rules/infra.md`, "Exceção registrada até o PR 39 ..."): fica intacta. Ela sai no PR 39.
- Qualquer mudança em `.github/workflows/*.yml`, `infra/**`, `tests/**`, `pyproject.toml`, `uv.lock`, `AGENTS.md`, `CLAUDE.md` ou nos agentes de `.claude/agents/`.
- Mudar o frontmatter `paths:` da regra (continua `infra/**` e `.github/**`).
- Regras de `.github/dependabot.yml` (cooldown, groups, diretórios): já travadas por `tests/infra/test_dependabot.py`.
- Política de exceções do ADR 0006, item 9 (`.trivyignore`, `# zizmor: ignore[...]`, `allow-ghsas`): já travada por `tests/infra/test_security_workflow.py`; não entra na regra (ver D5).
- Regras de deploy por SSH, GHCR, environment `production` e `actionlint` (PRs 37 a 39, fases futuras), salvo o ajuste mínimo da linha 12 em D4.
- Linha nova no `docs/plans/00-indice.md` (ver Q2).
- Escrever ou editar ADR.

## 3. Fase do roadmap

"Segurança em CI (em paralelo à Fase 2)", fase própria criada pelo ADR 0006 (`docs/plans/00-indice.md`, seção de mesmo nome). Não é fase de `docs/plataforma-ml.md`. É o acompanhamento das perguntas S1-Q6 e S3-Q11; não adianta nenhum item de fase futura.

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `.claude/rules/infra.md` | Acrescentar três bullets (workflows, imagens de terceiros, `.env.example` com Docker) e ajustar uma frase da linha 12 (D4) |
| `docs/plans/R1-infra-rules-security.md` | Este plano (já gravado; só entra no PR se o usuário quiser versioná-lo junto) |

### Estado atual de `.claude/rules/infra.md` (cópia literal, 15 linhas)

```markdown
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
```

Estilo a manter: um bullet por tema, frases curtas no imperativo ou afirmativas, identificadores entre crases, ADR citado entre parênteses. Prosa em português, identificadores em inglês (ADR 0001).

### Contexto que o implementador precisa (fontes das regras)

- ADR 0006 (`docs/adr/0006-security-validation-in-ci.md`), Decisão:
  - item 3: `security.yml` sem filtro `paths:` ("um check required com `paths:` fica pendente para sempre em PR só de docs"); o Trivy roda "por action pinada por SHA conferido ou por imagem fixada por digest";
  - item 4: "Todas as actions pinadas por SHA com comentário `# vX.Y.Z` ao lado ... e `persist-credentials: false` no checkout";
  - item 5: "Imagens de terceiros no Dockerfile e no compose (uv, postgres, busybox) fixadas por `tag@sha256:digest`, mantidas pelo Dependabot";
  - item 6: `security.yml` com `permissions: {}` no topo, cada job com o mínimo; `ci.yml` com `permissions: contents: read` no topo; "Nenhum workflow usa `pull_request_target` nem `workflow_run` com código de PR";
  - item 7: "Nenhum segredo no nível do repositório. Os segredos do deploy ficam só no environment `production`, restrito à `main` (item 38). `security.yml` e `ci.yml` não usam segredos."
- Plano S3, Q1 (resolvida): Trivy pela imagem `ghcr.io/aquasecurity/trivy:<X.Y.Z>@sha256:<digest>` via `docker run`, nunca `aquasecurity/trivy-action` nem `aquasecurity/setup-trivy`. Hoje: `TRIVY_IMAGE` no `env:` do topo de `.github/workflows/security.yml`, linha 12.
- Plano S3, nota da forma-alvo: "Nenhum `${{ }}` dentro de `run:` ... o que o shell precisa entra por `env:`".
- `AGENTS.md`, "Comandos": "Auditoria dos workflows: `uv run zizmor .github/workflows/` (auditorias online: `GH_TOKEN` no ambiente do comando, nunca em arquivo)". O zizmor é dependência de dev (`pyproject.toml`, linha 55), então o comando existe.
- `AGENTS.md`, "Fluxo de trabalho": "PR do Dependabot que troca o `postgres` de `infra/docker-compose.yml`: levar o mesmo `tag@sha256:` ao serviço `postgres` do `.github/workflows/ci.yml` (e ao `infra/docker-compose.dev.yml`, se o Dependabot não o atualizar), por commit na própria branch do Dependabot; o teste `test_postgres_reference_is_identical_in_prod_dev_and_ci` fica vermelho até isso."
- `AGENTS.md`, "Regras de código": "O deny de `Read` não impede leitura via Bash (`cat .env`); portanto agentes nunca devem ler arquivos `.env`, com nenhuma ferramenta. O deny também bloqueia `.env.example`; se um agente precisar das variáveis documentadas, o usuário cola o conteúdo."
- `.github/workflows/ci.yml` já roda `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q` (linha 43) e usa o mesmo `--env-file` no `compose-smoke` (linha 51). O plano S1 também lista esse comando como critério de pronto.
- Por que o `-q` e o `--env-file` importam: `infra/docker-compose.yml` interpola `POSTGRES_ADMIN_USER`, `POSTGRES_ADMIN_PASSWORD` e `POSTGRES_INGESTOR_PASSWORD` (linhas 24, 25, 48, 61 e 62). `docker compose config` sem `-q` imprime o compose já interpolado, isto é, os valores. Sem `--env-file`, o compose procura o `.env` no diretório do projeto (`infra/`), ou seja, `infra/.env`, que numa máquina local pode ter segredos reais.

### Texto-alvo (aplicar literalmente, salvo ajuste do usuário nas decisões)

Linha 12, só a segunda frase muda (D4):

```markdown
- `.env` da VPS fica fora do git, permissão 600. Segredos de CI e deploy vão em GitHub Secrets do environment `production`, nunca no nível do repositório; `ci.yml` e `security.yml` não usam segredos (ADR 0006, item 7).
```

Linha 13 (deploy manual) e linha 14 (backup): sem mudança. Três bullets novos, depois da linha 14 (fim do arquivo):

```markdown
- Workflows (`.github/workflows/**`, ADR 0006): toda action por SHA completo de commit com `# vX.Y.Z` na mesma linha, nunca por tag; `permissions` no topo (`{}` ou `contents: read`) e o mínimo declarado em cada job; `actions/checkout` com `persist-credentials: false`; nenhum gatilho `pull_request_target` nem `workflow_run`; nenhum `secrets.` no `ci.yml` nem no `security.yml`; nenhum `${{ }}` dentro de `run:` (o valor entra por `env:`); `if:` em uma linha só; workflow de check sem filtro `paths:`; o Trivy roda pela imagem fixada por digest (`TRIVY_IMAGE` do `security.yml`), nunca por `aquasecurity/trivy-action` ou `setup-trivy`. Antes de commitar mudança em workflow, rode `uv run zizmor .github/workflows/` e corrija os achados.
- Imagens de terceiros no Dockerfile, no compose e nos `services` do CI: fixadas por `tag@sha256:<digest do índice multi-arch>`, nunca só por tag nem `latest` (ADR 0006, item 5). PR do Dependabot que troca o `postgres` do compose leva o mesmo `tag@sha256:` ao `ci.yml` (e ao `docker-compose.dev.yml`), como descrito no `AGENTS.md`.
- `.env.example` com Docker: o agente pode rodar `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q`, porque quem lê o arquivo é o Docker e o `-q` não imprime nada; o agente continua sem abrir, copiar ou imprimir o arquivo, com qualquer ferramenta (`AGENTS.md`). Nunca rode `config` sem `-q` (imprime os valores interpolados) nem sem `--env-file infra/.env.example` (o compose carregaria `infra/.env`).
```

## 5. Passos

1. Criar a branch `chore/infra-rules-security` a partir da `main` atualizada: `git switch main && git pull && git switch -c chore/infra-rules-security`.
2. Conferir que `.claude/rules/infra.md` na branch é igual à cópia da seção 4 (`git diff main -- .claude/rules/infra.md` sem saída e `wc -l .claude/rules/infra.md` → 15). Se diferir, parar e perguntar ao usuário.
3. Em `.claude/rules/infra.md`, linha 12, trocar só a frase "Segredos do CI vão em GitHub Secrets." pelo texto-alvo (D4). Se o usuário rejeitar D4, pular este passo.
4. Acrescentar os três bullets do texto-alvo depois da linha "Backup sem restore testado não conta como backup.", nessa ordem (workflows, imagens, `.env.example`). Não mexer no frontmatter, no título nem nas linhas 9 a 11, 13 e 14.
5. Não abrir `infra/.env` nem `infra/.env.example` em nenhum passo; os critérios da seção 6 não precisam deles além do `config -q`.
6. Rodar os critérios de pronto (seção 6) e colar as saídas no PR.
7. Commit `docs(rules): add workflow and image pinning rules to infra rules` (mensagem em inglês, ADR 0001). Abrir o PR (o usuário, ou o agente se instruído) com título `chore: add CI security rules to .claude/rules/infra.md` e corpo citando ADR 0006, S1-Q6 e S3-Q11.
8. Revisão: `code-reviewer` antes do PR e `pr-reviewer` no PR (o PR toca `.claude/`).

## 6. Critérios de pronto

Comandos em bash (Git Bash no Windows). Nenhum deles lê `.env`. Nas linhas de diff, a linha removida aparece como `-- ...` e as acrescentadas como `+- ...` (bullet Markdown depois do marcador do diff); os cabeçalhos `---`/`+++` não casam com os padrões.

| Comando | Saída esperada |
| --- | --- |
| `git diff --name-only main...HEAD` | `.claude/rules/infra.md` (e `docs/plans/R1-infra-rules-security.md`, se o plano for no mesmo PR); nada mais |
| `git diff main...HEAD -- .claude/rules/infra.md \| grep -cE '^-- '` | `1` (só a linha 12 sai; `0` se D4 for rejeitada) |
| `git diff main...HEAD -- .claude/rules/infra.md \| grep -cE '^\+- '` | `4` (linha 12 nova + três bullets; `3` se D4 for rejeitada) |
| `git diff main...HEAD -- .claude/rules/infra.md \| grep -c 'PR 39'` | `0` (linha 13 intacta) |
| `head -5 .claude/rules/infra.md` | O frontmatter original, com `infra/**` e `.github/**` |
| `grep -cF 'persist-credentials: false' .claude/rules/infra.md` | `1` |
| `grep -cF '# vX.Y.Z' .claude/rules/infra.md` | `1` |
| `grep -cF 'uv run zizmor .github/workflows/' .claude/rules/infra.md` | `1` |
| `grep -cF 'tag@sha256:' .claude/rules/infra.md` | `1` (as duas ocorrências ficam na mesma linha, o bullet de imagens) |
| `grep -cF -- '--env-file infra/.env.example config -q' .claude/rules/infra.md` | `1` |
| `grep -cF 'pull_request_target' .claude/rules/infra.md` | `1` |
| `uv run zizmor .github/workflows/` | Código 0, sem achados (a regra descreve o estado atual da `main`) |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q` | Código 0, sem saída (o comando que a regra autoriza funciona e não imprime nada) |
| `uv run pytest -m "not db"` | Todos passam (sanidade; nada de código mudou) |
| `uv run ruff check .` e `uv run ruff format --check .` | Código 0 |

## 7. Testes necessários

`não`: muda só instrução de agente em Markdown (documentação), sem comportamento de código; nenhum teste de `tests/` lê `.claude/rules/` (Grep por `.claude` e `rules/infra` em `tests/` em 2026-11-08: zero resultados), e as regras descritas já são impostas por `tests/infra/test_supply_chain_pins.py`, `tests/infra/test_security_workflow.py` e `tests/infra/test_compose.py`. Ver D6.

## 8. Casos de teste

n/a

## 9. Riscos e perguntas em aberto

Riscos:

- **Regra e teste divergem com o tempo.** Se um teste de `tests/infra/` mudar (por exemplo o PR 37 abrir exceção de digest para as imagens próprias do GHCR), a regra fica desatualizada. Mitigação: a regra cita o ADR, não números de linha; as imagens próprias `ghcr.io/${GHCR_OWNER}/platform-*` não são "de terceiros", então o texto atual não as obriga a ter digest e não conflita com o PR 37.
- **`--env-file` e o `infra/.env` local.** O bullet assume que, com `--env-file`, o Compose v2 não carrega também o `infra/.env` padrão. Não foi conferido nesta tarefa (conferir exigiria um `infra/.env`). Com `-q` nada é impresso de qualquer forma, então o risco residual é só de erro de interpolação citar o nome de uma variável, nunca o valor. Ninguém deve "conferir" isso abrindo o `.env`.
- **Mensagem de erro do `config -q`.** Com variável obrigatória faltando, o compose imprime a mensagem do `:?` (por exemplo `POSTGRES_ADMIN_USER is required`), que contém só o nome. Aceitável.
- **Bullet de workflows longo.** Fica parecido em tamanho com a linha 13; se o revisor preferir, dá para quebrar em dois bullets (pin e permissões; execução e zizmor) sem mudar conteúdo (ajustar a contagem `^\+- ` da seção 6).
- **Redundância entre a linha 12 e o bullet de workflows** (ambos dizem que `ci.yml` e `security.yml` não usam segredos). Aceita: a linha 12 trata de onde ficam os segredos; o bullet, do que o workflow pode referenciar. Se o revisor preferir, tirar a cláusula final da linha 12.
- **Agentes que não tocam os caminhos.** A regra só carrega quando o agente mexe em `infra/**` ou `.github/**`. É o comportamento esperado das regras por caminho.

Perguntas (cada uma com recomendação):

- **Q1. Quem aplica.** O `task-implementer` não edita `.claude/` por instrução do próprio prompt (`CLAUDE.md`). Recomendação: o usuário aplica o texto-alvo à mão (é uma edição de Markdown), ou passa ao agente a autorização de 2026-11-08 por escrito na instrução. O test-writer não participa (Testes: não).
- **Q2. Linha no índice.** Recomendação: não acrescentar R1 ao `docs/plans/00-indice.md`; é acompanhamento de S1-Q6 e S3-Q11, sem PR numerado. Se o usuário quiser rastreabilidade, uma linha "R1" na seção "Segurança em CI" é um PR só de docs à parte.
- **Q3. `AGENTS.md` precisa da mesma ressalva sobre `.env.example`?** Recomendação: não neste PR. O bullet novo não contradiz o `AGENTS.md`: a regra lá é "agentes nunca devem ler arquivos `.env`", e o que o bullet permite é o Docker ler o arquivo de exemplo, público e versionado, sem que o conteúdo chegue ao agente (o `-q` não imprime). O CI já faz exatamente isso. Se o usuário entender que "com nenhuma ferramenta" cobre também o Bash que chama o Docker, a alternativa mais segura é trocar o bullet por "o agente não roda `docker compose config`; quem confere o compose é o job `lint-and-test` do CI (`ci.yml`, linha 43)", tirar o `config -q` da seção 6 deste plano e dos critérios de pronto de planos futuros.

## 10. Decisões que exigem ADR

Nenhuma. Todas as regras vêm do ADR 0006 (Aceito, 2026-11-08) e do `AGENTS.md`; o PR só as registra na regra por caminho. Decisões de redação, cada uma com recomendação:

- **D1. `pull_request_target` e `workflow_run`.** O ADR 0006, item 6, fala em "com código de PR"; o teste `test_no_workflow_uses_dangerous_triggers` (`tests/infra/test_supply_chain_pins.py`, S1 caso 5) proíbe os dois gatilhos em qualquer caso. Recomendação: a regra diz "nenhum gatilho `pull_request_target` nem `workflow_run`", igual ao teste, para não sugerir uma permissão que o CI recusa. Alternativa: manter "com código de PR" e citar o teste.
- **D2. Itens extras da S3-Q11** (`if:` em uma linha, sem `paths:` em workflow de check, `permissions: {}` como opção do topo). Recomendação: incluir, porque são curtos, já estão travados por `tests/infra/test_security_workflow.py` e são exatamente o que os planos 37 e 39 precisam saber. Alternativa: só a lista pedida, deixando os extras aos testes.
- **D3. Digest do índice multi-arch.** Recomendação: escrever "digest do índice multi-arch" no bullet de imagens, porque é o erro mais provável ao fixar uma imagem nova (S1, passo 6) e o Dependabot depende disso. Alternativa: só `tag@sha256:`.
- **D4. Linha 12, "Segredos do CI vão em GitHub Secrets".** Ela não contradiz o ADR 0006, mas é menos precisa: o item 7 proíbe segredo no nível do repositório e o põe só no environment `production`. Recomendação: ajustar só essa frase, como no texto-alvo, para que a linha 12 e o bullet novo de workflows digam a mesma coisa. Alternativa: deixar a linha 12 como está (o diff fica só de acréscimos; ajustar os critérios de pronto conforme anotado).
- **D5. Política de exceções do ADR 0006, item 9, na regra.** Recomendação: não incluir agora; está imposta por `tests/infra/test_security_workflow.py` (casos 23 a 26 do S3) e só aparece quando há achado. Alternativa: meia linha "exceção só com motivo, link e data de revisão, aprovada pelo usuário".
- **D6. Teste barato sobre o conteúdo da regra.** Considerado: um teste em `tests/` que leia `.claude/rules/infra.md` e exija as strings-chave (`persist-credentials: false`, `tag@sha256:`, `uv run zizmor .github/workflows/`, frontmatter com `.github/**`). Recomendação: não escrever. Ele testaria prosa, quebraria a cada ajuste de redação sem pegar regressão real (as regras em si já são impostas pelos testes de `tests/infra/`) e obrigaria o test-writer a ler `.claude/` em toda mudança de texto. Os `grep` da seção 6 bastam para este PR. Se o usuário quiser algo, o único caso com valor seria "o frontmatter de `.claude/rules/infra.md` cobre `infra/**` e `.github/**`" (entrada: o arquivo; resultado: as duas globs presentes em `paths:`).
