# ADR 0004: Operação interina antes do Prefect

Status: Aceito
Data: 2026-11-07
Decisores: Maximiliano

## Contexto

O desenho em `docs/plataforma-ml.md` e a regra de `.claude/rules/infra.md` dizem que o deploy só sai de merge na `main`, sem SSH manual para mudar produção, e que o Prefect agenda as ingestões. Esse caminho só existe na Fase 3: o deploy via SSH automático é o PR 39 e os deployments do Prefect são os PRs 33 a 36 (`docs/plans/00-indice.md`).

A prioridade do roadmap é começar a coletar `raw.weather_forecast` o quanto antes, porque cada dia sem coleta é histórico perdido (P5). Isso põe a Fase 1 (Postgres na VPS) e a coleta da previsão (PRs 13 a 17) antes da Fase 3. Duas perguntas do índice ficaram em aberto até aqui, e o usuário as decidiu em 2026-11-07:

- P6: aceitar deploy manual (SSH, `git pull`, `docker compose up`) como exceção até a Fase 3.
- P7: qual agendador interino usar, e se serviços em `profiles` (execução única) dispensam a política de `restart`.

Este ADR foi escrito pelo `task-implementer` por instrução expressa do usuário, como exceção à regra do `AGENTS.md` ("Nenhum agente escreve ADR"). A exceção vale só para este ADR e para o 0005.

## Decisão

### Deploy manual como exceção registrada (P6)

Até o PR 39, atualizar a VPS é manual: o usuário entra por SSH (pela tailnet, ADR 0003), faz `git pull` e roda `docker compose up`. A imagem dos jobs é construída na própria VPS até o PR 37 (GHCR).

É uma exceção registrada à regra "Nada de SSH manual para mudar produção", não uma mudança dela. A partir do PR 39, o merge na `main` volta a ser a única forma de mudar produção, como diz o `AGENTS.md`. Os itens manuais 04, 12 e 17 dos planos usam esta exceção.

### Agendador interino: supercronic no compose (P7)

Os jobs de ingestão rodam por um serviço `scheduler` no compose, com o supercronic lendo um crontab versionado no repo (`infra/cron/crontab`, PR 16). O serviço é de longa duração, tem `restart: unless-stopped` e `mem_limit`, não publica porta, e os logs vão para o stdout do container.

A alternativa, o crontab do host chamando `docker compose run --rm jobs ...`, foi descartada: o crontab do host não fica versionado no repo, não sobe com o compose e não volta com a política de restart.

### Profiles dispensam `restart` (P7)

Serviço de execução única, declarado em `profiles` (o `jobs` do PR 11, rodado com `docker compose run --rm jobs <comando>`), fica com `restart: "no"`. A regra "todo serviço tem `restart: unless-stopped`" continua valendo para todo serviço sem `profiles`. `mem_limit` continua obrigatório em todos, com ou sem profile (PR 03).

## Consequências

- Os testes de compose (PRs 03 e 11) codificam a regra assim: serviço sem `profiles` tem `restart: unless-stopped`; serviço em `profiles` não precisa dele. A redação de `.claude/rules/infra.md` ("Todo serviço no compose tem `restart: unless-stopped`") deve ser alinhada a esta exceção; isso não é feito por este ADR e fica para o PR que tocar a regra.
- Enquanto a exceção durar, quem aplica o deploy é uma pessoa, sem trilha automática além do histórico do git.- Falha de job só aparece em `docker compose logs scheduler` até os alertas do PR 55; o item 17 inclui checagem diária manual.
- O build da imagem na VPS (1 vCPU, 1 GB de RAM, 2 GB de swap) é lento e pode usar swap. Não construir imagem com um job agendado em execução. Dois jobs ao mesmo tempo (por exemplo, backfill manual durante o job agendado) podem passar do `mem_limit`; a medição do checkpoint 28a confirma.
- O binário do supercronic deve ser instalado com versão e checksum fixados no Dockerfile (PR 16), e a arquitetura da VPS (`uname -m`, item 02) define qual binário baixar.

### Quando a exceção acaba

- O agendador interino é substituído pelos deployments do Prefect: o PR 36 remove o `scheduler` depois do cutover manual (item 35) e marca este ADR como `superseded` no que toca ao agendador.
- O deploy manual acaba no PR 39 (deploy via SSH automático, a partir do merge na `main`); esse PR marca este ADR como `superseded` no que toca ao deploy.
- Enquanto um dos dois PRs não estiver mergeado, a parte correspondente da exceção continua valendo.

## Alternativas consideradas

- Crontab do host: rejeitada pelo motivo descrito em "Agendador interino".
- Esperar o Prefect (Fase 3) para ligar a coleta: rejeitada, porque perde histórico de previsões todo dia sem coleta (P5).
- `restart: unless-stopped` também nos serviços de execução única: o `jobs` ficaria reiniciando em loop depois de terminar. Alternativa não adotada: tirar o `jobs` do compose e usar `docker run` com a rede do compose.
