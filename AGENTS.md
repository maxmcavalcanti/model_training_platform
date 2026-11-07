# Plataforma ML

Plataforma de dados e execução de modelos numa VPS (Postgres, MLflow, Prefect, Grafana, Caddy, Tailscale). Este repositório é o `plataforma` do desenho em `docs/plataforma-ml.md`. Os modelos vivem em outro repositório (`modelos`) e falam com a plataforma pelo contrato.

## Fronteira (nunca cruzar sem combinar)

- Este repo cuida de "o job rodou?". O repo `modelos` cuida de "o modelo está certo?".
- O único ponto de passagem é o alias `champion` no MLflow. Trocar o alias é o deploy de um modelo.
- Schema de `raw` e `ref` só muda com migração Alembic. A assinatura de `build_features`, `predict` e `evaluate` só muda por decisão registrada em ADR.

## Onde ler mais (carregue só o que a tarefa pedir)

- `docs/plataforma-ml.md`: arquitetura, modelo de dados, jobs, contrato, CI/CD, roadmap por fases.
- `docs/guia-ciencia-de-dados.md`: o lado da cientista de dados. Útil para entender o contrato, não para editar.
- `docs/adr/`: decisões de arquitetura já tomadas. Leia antes de propor mudança estrutural.

## Regras de código

- Todo job de ingestão é idempotente: upsert por chave primária (`INSERT ... ON CONFLICT DO UPDATE`), nunca append cego.
- Toda linha em `raw` leva `ingerido_em`.
- Todo job termina com checagem de qualidade (pandera). Checagem falha = execução falha.
- Nenhum segredo no git. Segredos entram por variável de ambiente.
- Merge na `main` é a única forma de mudar produção.

## Comandos

Ainda não há código. Quando o ambiente de desenvolvimento existir, liste aqui os comandos exatos de lint, teste (arquivo único e suíte) e migração. Enquanto isso, não invente comandos.

## Fluxo de trabalho

- Todo o código é escrito por agentes, com um plano aprovado antes de implementar.
- Mudança estrutural gera ADR em `docs/adr/` antes do código.
- Antes de abrir PR, rode o agente `code-reviewer`. O agente `pr-reviewer` revisa o PR contra o plano.
- Uma fase do roadmap por vez. Não adiante itens de fases futuras.
- Dê evidência de que funciona: o comando rodado e a saída, não só "deve funcionar".
