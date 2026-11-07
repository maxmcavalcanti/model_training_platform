# Plataforma ML

Plataforma de dados e execução de modelos numa VPS (Postgres, MLflow, Prefect, Grafana, Caddy, Tailscale). Este repositório é o `plataforma` do desenho em `docs/plataforma-ml.md`. Os modelos vivem em outro repositório (`modelos`) e falam com a plataforma pelo contrato.

## Fronteira (nunca cruzar sem combinar)

- Este repo cuida de "o job rodou?". O repo `modelos` cuida de "o modelo está certo?".
- O único ponto de passagem é o alias `champion` no MLflow. Trocar o alias é o deploy de um modelo.
- Mudança em `raw` ou `ref` exige migração Alembic + ADR + aviso à ciência de dados. Mudança na assinatura de `build_features`, `predict` e `evaluate` exige ADR.

## Onde ler mais (carregue só o que a tarefa pedir)

- `docs/plataforma-ml.md`: arquitetura, modelo de dados, jobs, contrato, CI/CD, roadmap por fases.
- `docs/guia-ciencia-de-dados.md`: o lado da cientista de dados. Útil para entender o contrato, não para editar.
- `docs/adr/`: decisões de arquitetura já tomadas. Leia antes de propor mudança estrutural.

## Regras de código

- Todo job de ingestão é idempotente: upsert por chave primária (`INSERT ... ON CONFLICT DO UPDATE`), nunca append cego.
- Toda linha em `raw` leva `ingerido_em`.
- Todo job termina com checagem de qualidade (pandera). Checagem falha = execução falha.
- Nenhum segredo no git. Segredos entram por variável de ambiente.
- O deny de `Read` não impede leitura via Bash (`cat .env`); portanto agentes nunca devem ler arquivos `.env`, com nenhuma ferramenta. O deny também bloqueia `.env.example`; se um agente precisar das variáveis documentadas, o usuário cola o conteúdo.
- TDD estrito: todo código de produção nasce de um teste vermelho. Ciclo: vermelho (test-writer) → implementação mínima → verde → refatorar com a suíte verde. Sem teste vermelho antes, sem código.
- Merge na `main` é a única forma de mudar produção.

## Comandos

Ainda não há código. Quando o ambiente de desenvolvimento existir, liste aqui os comandos exatos de lint, teste (arquivo único e suíte) e migração. Enquanto isso, não invente comandos.

## Fluxo de trabalho

- Mudança estrutural gera ADR em `docs/adr/` antes do código. Nenhum agente escreve ADR: o `task-planner` só sinaliza a necessidade no plano. O ADR é uma tarefa separada (PR próprio, escrito pelo usuário ou pela skill `generate-adr`) e precisa estar mergeado antes de a implementação começar.
- Fluxo de uma tarefa:
  1. `task-planner` grava o plano com casos de teste em `docs/plans/` e o usuário aprova.
  2. `test-writer` escreve os testes e confirma que falham (pular se o plano disser "Testes necessários: não").
  3. `task-implementer` implementa em worktree partindo da branch com os testes, sem editar testes.
  4. `code-reviewer` revisa antes do PR.
  5. Abrir o PR (o CI roda no PR).
  6. CI + `pr-reviewer`, que revisa o PR contra o plano.
- Uma fase do roadmap por vez. Não adiante itens de fases futuras.
- Dê evidência de que funciona: o comando rodado e a saída, não só "deve funcionar".
