# 36 — Remover o agendador interino (supercronic)

> Executa: agente. Depende de: 34 e do item manual 35 concluído (um dia com os dois agendadores sem problema). Branch sugerida: `chore/remove-supercronic`.
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Tirar do repo o serviço `agendador`, o `infra/cron/crontab` e o supercronic da imagem, deixando o Prefect como único agendador.
Evita duas fontes de verdade para horários.

## 2. Fora do escopo

- Mudar horários. Qualquer mudança nos flows.

## 3. Fase do roadmap

Fase 3 — "Ingestões migradas para flows do Prefect".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `infra/docker-compose.yml` | Remover o serviço `agendador` |
| `infra/cron/crontab` | Apagar |
| `infra/jobs/Dockerfile` | Remover download do supercronic e a cópia de `infra/cron/` |
| `.github/workflows/ci.yml` | Remover o passo `supercronic -test` |
| `tests/infra/test_crontab.py` | Apagar (test-writer) |
| `tests/test_deployments.py` | Caso "cron igual ao crontab" passa a comparar com a tabela fixa do doc (test-writer) |
| `tests/infra/test_compose.py` | Novo caso: não existe serviço `agendador` (test-writer) |

## 5. Passos

1. (test-writer) Apague `tests/infra/test_crontab.py`. Em `tests/test_deployments.py`, troque a comparação com o crontab pela tabela: `ingest_weather_forecast` `30 6 * * *`, `ingest_weather_observed` `45 6 * * *`, `ingest_ons_load` `0 7 * * *` (ou os horários vigentes no crontab no momento, se o item 18 os mudou — copie-os do arquivo antes de apagá-lo). Em `tests/infra/test_compose.py`, acrescente: nenhum serviço `agendador` e nenhum `command` contendo `supercronic`; `infra/cron/` não existe. Confirme que os casos novos falham. Commit `test: expect prefect as the only scheduler`.
2. (implementer) Remova o serviço, o diretório `infra/cron/`, o trecho do Dockerfile e o passo do CI.
3. Rode os critérios de pronto.
4. Nota para o usuário, no corpo do PR: depois do merge, na VPS, `docker compose -f infra/docker-compose.yml up -d --remove-orphans` (ou o deploy automático do PR 39, se já existir, deve usar `--remove-orphans`).

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest` | Suíte verde |
| `git ls-files infra/cron` | Vazio |
| `grep -rn supercronic infra .github` | Nada |
| `docker build -f infra/jobs/Dockerfile -t platform-jobs .` | Sem erro |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: o teste garante que o agendador antigo não volta por engano e que os horários sobrevivem à remoção do crontab.

## 8. Casos de teste

1. Nenhum serviço `agendador` em `infra/docker-compose.yml`.
2. Nenhum `command` com `supercronic`.
3. `infra/cron/` não existe.
4. Deployments continuam com os horários vigentes (tabela fixa no teste).

## 9. Riscos e perguntas em aberto

- Se o item 35 não tiver mostrado um dia completo pelo Prefect, não fazer merge.

## 10. Decisões que exigem ADR

Atualizar o ADR "Operação interina" (P6/P7) para `superseded` no que toca ao agendador.
