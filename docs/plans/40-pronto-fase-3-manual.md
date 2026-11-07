# 40 — Prova do deploy automático e CI do repo `modelos` (manual / coordenação)

> Executa: **usuário**, com a cientista de dados. Depende de: 36, 39 (merges na `main`).
> Fase do roadmap: Fase 3 — "Pipelines do GitHub Actions nos dois repositórios"; "Pronto quando: um merge na `main` chega à VPS sem eu entrar nela".

## Por que é manual

A prova exige observar produção. O CI do repositório `modelos` é de outro repo e de outra dona: este plano não escreve nada lá; lista o que combinar com ela.

## Checklist — prova do deploy (este repo)

- [ ] Abrir um PR trivial (ex.: um comentário em `infra/docker-compose.yml`), CI verde, merge.
- [ ] Sem entrar na VPS: `gh run watch` do `deploy.yml` até `success`.
- [ ] Conferir do notebook, pela tailnet: `curl -s https://<host>.ts.net:8080/saude` → `ok`; na UI do Prefect (`https://<host>.ts.net:4200`), os deployments continuam com agenda.
- [ ] Na VPS (só leitura, para conferir): `git -C /opt/platform rev-parse HEAD` = SHA do merge; `docker compose -f /opt/platform/infra/docker-compose.yml ps --format '{{.Image}}'` mostra `:<sha>`.

## Checklist — repo `modelos` (combinar com ela)

Do doc ("CI/CD e operação"): no PR, `ruff` e `pytest` (testes das funções do contrato com dados de amostra); no merge na `main`, criar tag de versão; o job de score passa a instalar essa versão.

- [ ] Ela (ou um agente no repo dela, com aprovação dela) cria `.github/workflows/ci.yml` com `ruff` e `pytest`.
- [ ] Combinar o esquema de tag (ex.: `v0.1.0`, semver) e quem cria a tag (workflow no merge ou manual por ela).
- [ ] Combinar como o modelo registrado no MLflow aponta para a versão do pacote (decisão P12: uma tag na versão do modelo no MLflow, ex.: `models_package=v0.1.0`). Isso é contrato e precisa do ADR do PR 44 antes da Fase 4.
- [ ] O repo `modelos` é público (P2 resolvida): o job de score instala o pacote sem token. Combinar com ela que nada de segredo entra nesse repo, nem em notebook commitado.

## Verificação de pronto

| Verificação | Esperado |
| --- | --- |
| `gh run list --workflow deploy.yml --limit 1 --json conclusion -q '.[0].conclusion'` | `success` |
| SHA em produção | Igual ao do último merge |
| `gh run list -R <dono>/modelos --workflow ci.yml --limit 1` | Existe e está verde |
| Tag no repo `modelos` (`gh release list -R <dono>/modelos` ou `git ls-remote --tags`) | Pelo menos uma |

Com isso a Fase 3 está pronta e a cientista pode registrar modelos no MLflow.
