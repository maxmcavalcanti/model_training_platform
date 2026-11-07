# ADR 0003: rede só Tailscale, mais a limpeza dos textos que citam Caddy

> Executa: agente (`task-implementer`). Depende de: ADR 0001 e ADR 0002 (já na `main`). Bloqueia: PR 03 (`docs/plans/03-compose-rede-tailscale.md`). Branch sugerida: `docs/tailscale-only-network-adr`.
> Testes necessários: não. O PR toca `AGENTS.md` e `.claude/`, então **passa por `code-reviewer` e `pr-reviewer`** (`AGENTS.md`, "Fluxo de trabalho": "Qualquer PR que toque algo fora de `docs/**` ... passa por ambos, mesmo quando só há Markdown").
> **Exceções autorizadas pelo usuário (2026-11-07), válidas só para este PR:** (a) o `task-implementer` escreve o ADR `docs/adr/0003-tailscale-only-network.md`, ao contrário de "Nenhum agente escreve ADR" (`AGENTS.md`); (b) o `task-implementer` pode editar `.claude/rules/infra.md`, ao contrário de "implementer não edita ... `.claude/`" (`CLAUDE.md`). Fora isso, continua proibido editar testes, `docs/plans/` e qualquer outro arquivo de `.claude/`.

## 1. Objetivo

Registrar em `docs/adr/0003-tailscale-only-network.md` a decisão de rede só Tailscale (P4, mais a P15 respondida em 2026-11-07), adotando `tailscale serve` com os serviços em loopback.
No mesmo PR, tirar Caddy, domínio e "22 e 443" de `AGENTS.md`, `docs/plataforma-ml.md` e `.claude/rules/infra.md`.

## 2. Fora do escopo

- Implementar compose, `infra/scripts/tailscale-serve.sh`, testes de infra (PR 03), Postgres no compose (PR 10) ou qualquer configuração na VPS ou no painel do Tailscale (itens 02, 04, 12, 38).
- Editar `docs/plans/**`. O implementer não pode, e os planos já foram refeitos para Tailscale-only. As sobras estão na seção 9 (Q5) e ficam para um PR separado do `task-planner`.
- Corrigir outros desvios de `docs/plataforma-ml.md`: "4 GB de RAM" (linha 56, assunto da P3) e "Nada de SSH manual" em `.claude/rules/infra.md` (linha 13, assunto do ADR de operação interina, P6/P7).
- Decidir pontos que continuam em aberto: monitor externo/heartbeat (P17), Tailscale SSH no futuro, regras exatas da ACL por pessoa e por tag (itens 04, 12, 31, 38, 50), `tailscale serve reset` no deploy (PR 39).
- Escrever ou alterar outros ADRs.

## 3. Fase do roadmap

Pré-requisito da Fase 0 ("Base da VPS") de `docs/plataforma-ml.md`. O índice pede este ADR mergeado antes do PR 03 (`docs/plans/00-indice.md`, "ADRs a escrever", item 2).

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `docs/adr/0003-tailscale-only-network.md` | Criar o ADR. Nome em inglês, prosa em português, identificadores em inglês (ADR 0001) |
| `AGENTS.md` | Linha 3: tirar `Caddy` da lista da stack |
| `docs/plataforma-ml.md` | Stack (linhas 51 e 52), árvore do repo (linha 68), "Operação" (linha 179), roadmap (linhas 189 e 207) |
| `.claude/rules/infra.md` | Linhas 10 e 11: regra de exposição e regra do firewall (exceção autorizada) |

Não existe template nem skill `generate-adr` no repo. O formato segue os ADRs 0001 e 0002: título `# ADR NNNN: ...`, linhas `Status:`, `Data:` e `Decisores:`, e seções `##`.

### 4.1 Fonte das decisões (copiar para o ADR sem acrescentar nada)

Do índice (`docs/plans/00-indice.md`):

- Linha 17 ("Restrições"): "**Rede só Tailscale** (P4, 2026-11-07). Nenhuma porta pública: sem domínio, sem proxy com autenticação, sem certificado público. As UIs (MLflow, Prefect, Grafana e a rota de saúde) são publicadas só em `127.0.0.1` e expostas na tailnet por `tailscale serve`, num hostname `*.ts.net` com uma porta por UI (recomendado; a alternativa, acesso direto pelo IP/nome do tailnet, é a decisão fina do ADR de rede). [...] Nenhuma porta de serviço é publicada em `0.0.0.0`; os testes do PR 03 travam isso. A ACL do Tailscale é o controle de acesso."
- P4: "**Só Tailscale**. Sem domínio, sem Caddy, sem certificado público, sem 443 pública. [...] A 22 pública fica aberta só no provisionamento e é fechada quando o SSH pela tailnet funciona."
- P15, **resposta do usuário em 2026-11-07**: Postgres em loopback (`127.0.0.1:5432`) + `tailscale serve --tcp=5432`, **sem sidecar**. A opção "IP do Tailscale com `After=tailscaled.service`" fica descartada.
- Item 2 de "ADRs a escrever": SSH pelo OpenSSH dentro da tailnet, não o recurso "Tailscale SSH", por causa do `command=` do deploy.

Decisão fina, tomada por este ADR conforme a recomendação do índice: **adotar `tailscale serve`**. O acesso direto pelo IP/nome do tailnet vira alternativa rejeitada.

Fatos dos planos, para citar no Contexto e nas Consequências (sem decidir nada além deles):

- Portas publicadas pelo Docker com `ports:` passam por cima do ufw. Uma porta em `0.0.0.0` fica na internet mesmo com o firewall fechado (`docs/plans/02-provisionar-vps-manual.md`, linha 35; `03`, linha 43).
- Firewall do item 02: `ufw default deny incoming`, `ufw allow in on tailscale0`. A `22/tcp` pública fica liberada só durante o provisionamento e é removida depois.
- MLflow e Prefect não têm autenticação própria (`docs/plataforma-ml.md`, linha 51). Sem proxy, a ACL do Tailscale é a única barreira (`03`, linha 117).
- Mapeamento planejado no PR 03 (`docs/plans/03-compose-rede-tailscale.md`, linhas 47 a 55). As portas são do plano, não do ADR (Q2):

  | Serviço | Host (compose) | Tailnet |
  | --- | --- | --- |
  | Saúde | `127.0.0.1:8080` | `https://<host>.ts.net:8080/health` |
  | MLflow | `127.0.0.1:5000` | `https://<host>.ts.net:5000` |
  | Prefect | `127.0.0.1:4200` | `https://<host>.ts.net:4200` |
  | Grafana | `127.0.0.1:3000` | `https://<host>.ts.net:3000` |
  | Postgres | `127.0.0.1:5432` | `<host>.ts.net:5432` via `tailscale serve --tcp=5432` |

- O `tailscale serve` exige MagicDNS e HTTPS Certificates ligados no painel e o usuário `deploy` como operador (`sudo tailscale set --operator=deploy`) (`03`, linha 116; item 04).
- Deploy (itens 38 e 39): o runner entra na tailnet (`tailscale/github-action`, `tag:ci`) e faz SSH pelo OpenSSH da VPS. A chave do CI tem `restrict,command="/opt/platform/infra/scripts/deploy.sh"` no `authorized_keys`. Com o Tailscale SSH (`tailscale up --ssh`) ligado, o tailscaled atende a porta 22 da tailnet e ignora o `authorized_keys` (`39`, linha 76; `02`, linha 30).
- Com Postgres em loopback + `tailscale serve --tcp`, o Docker não precisa esperar o tailscaled no boot. O `After=tailscaled.service` do item 02 passa a ser desnecessário (`02`, linha 31).
- Com a rede só Tailscale, um monitor de uptime externo não alcança a VPS. Isso continua em aberto na P17.

## 5. Passos

1. Crie a branch `docs/tailscale-only-network-adr` a partir da `main`. Não edite este plano nem nada em `docs/plans/`.
2. Crie `docs/adr/0003-tailscale-only-network.md`, em português, nesta ordem:
   - `# ADR 0003: Rede só Tailscale`
   - `Status: Aceito`, `Data: 2026-11-07`, `Decisores: Maximiliano` (ver Q1).
   - `## Contexto`: o doc previa Caddy com HTTPS e autenticação e um firewall com 22 e 443 (ou nenhuma porta pública). O usuário decidiu rede só Tailscale (P4) e Postgres em loopback (P15), ambos em 2026-11-07. MLflow e Prefect não têm autenticação própria. O Docker passa por cima do ufw. Escrito pelo `task-implementer` por instrução expressa do usuário, como exceção válida só para este ADR.
   - `## Decisão`, com subseções `###`:
     1. Sem exposição pública: nenhuma porta pública, sem domínio, sem Caddy, sem certificado público. O ufw nega toda entrada e aceita só `tailscale0`. A 22 pública fica aberta só no provisionamento e é fechada quando o SSH pela tailnet funciona.
     2. Publicação no host: toda porta de serviço do compose fica em `127.0.0.1`, nunca em `0.0.0.0`, porque o Docker ignora o ufw.
     3. Exposição na tailnet por `tailscale serve`: um hostname `*.ts.net` (MagicDNS), uma porta por UI, HTTPS com o certificado `*.ts.net`. Cite a tabela da seção 4.1 como mapeamento planejado no PR 03.
     4. Postgres (P15): `127.0.0.1:5432` + `tailscale serve --tcp=5432`, sem sidecar do Tailscale no compose e sem depender da ordem de boot.
     5. Controle de acesso: a ACL do Tailscale, por tag da VPS e por porta. Não há proxy com senha. As regras concretas ficam nos itens 04, 12, 31, 38 e 50.
     6. SSH: OpenSSH dentro da tailnet. O recurso Tailscale SSH (`tailscale up --ssh`) **não** é ligado, porque ignora o `authorized_keys` e quebraria a restrição `command=` da chave do deploy (itens 38 e 39).
   - `## Consequências`, usando os fatos da seção 4.1:
     - (a) Os testes do PR 03 travam "nada em `0.0.0.0`".
     - (b) O estado do `tailscale serve` é versionado num script do repo (PR 03). Cada nova UI acrescenta uma entrada (PRs 29, 30 e 47).
     - (c) Pré-requisitos no painel e na VPS: MagicDNS, HTTPS Certificates e operador `deploy`.
     - (d) A cientista e o CI só alcançam a VPS entrando na tailnet, e a ACL limita as portas de cada um.
     - (e) O `After=tailscaled.service` deixa de ser necessário.
     - (f) Um monitor externo não alcança a VPS. O caminho fica em aberto na P17.
     - (g) Ligar o Tailscale SSH no futuro exige revisar este ADR e replanejar os itens 38 e 39.
     - (h) Qualquer mudança que publique porta ou exponha serviço fora do tailnet/loopback exige novo ADR (`AGENTS.md`, "Fronteira").
     - (i) Este PR também atualiza `AGENTS.md`, `docs/plataforma-ml.md` e `.claude/rules/infra.md`.
   - `## Alternativas consideradas`:
     - Caddy com domínio, HTTPS público, `basic_auth` e 443 aberta: o desenho original, rejeitado pela P4.
     - Acesso direto pelo IP/nome do tailnet (`*_BIND_IP` = IP do Tailscale): HTTP puro dentro do WireGuard, sem script, mas sem HTTPS válido e com dependência da ordem de boot em todo serviço. Rejeitado em favor do `tailscale serve`.
     - Postgres no IP do Tailscale com `After=tailscaled.service`: rejeitado na P15.
     - Sidecar do Tailscale no compose: rejeitado pelo usuário na P15.
     - Tailscale SSH: rejeitado pelo motivo do item 6 da Decisão.
     - Não acrescente motivos nem alternativas que não estejam nesta lista (ver Q3).
3. `AGENTS.md`, linha 3: troque `(Postgres, MLflow, Prefect, Grafana, Caddy, Tailscale)` por `(Postgres, MLflow, Prefect, Grafana, Tailscale)`. O resto da linha e do arquivo não muda.
4. `docs/plataforma-ml.md`:
   - Linha 51: apague a linha da tabela `| Caddy | ... |`.
   - Linha 52: troque por `| Tailscale | Rede privada: acesso à VPS, às UIs (`tailscale serve`, HTTPS `*.ts.net`) e ao Postgres | Os dois | Nenhuma porta pública (ADR 0003). MLflow e Prefect não têm autenticação própria: ficam em loopback, expostos só na tailnet; a ACL do Tailscale é o controle de acesso. Ela acessa Postgres e MLflow do notebook local como se fosse rede local |`.
   - Linha 68: apague `│   ├── caddy/Caddyfile`. Na linha 69, troque o comentário por `# bootstrap da VPS, tailscale serve, backup, restore`.
   - Linha 179: troque por `- **Rede:** só Tailscale, nenhuma porta pública (ADR 0003). Serviços em loopback, expostos na tailnet por `tailscale serve` (Postgres por `--tcp=5432`); ACL do Tailscale como controle de acesso; SSH pelo OpenSSH dentro da tailnet`.
   - Linha 189: troque por `- [ ] UIs na tailnet por `tailscale serve` (HTTPS `*.ts.net`), ACL do Tailscale como controle de acesso`.
   - Linha 207: troque por `- [ ] MLflow e Prefect no compose, só na tailnet (`tailscale serve`)`.
   - Não mexa em mais nada, inclusive na linha 56 (fora do escopo).
5. `.claude/rules/infra.md` (exceção autorizada). Mantenha o frontmatter e as linhas 9, 12, 13 e 14 como estão. Troque:
   - Linha 10 por `- MLflow, Prefect e Grafana não têm autenticação adequada: só em `127.0.0.1`, expostos na tailnet por `tailscale serve`; a ACL do Tailscale é o controle de acesso (ADR 0003).` (ver Q4).
   - Linha 11 por `- Firewall: nenhuma porta pública (ADR 0003). A 22 pública só durante o provisionamento. Nenhuma porta do compose em `0.0.0.0` (o Docker passa por cima do ufw). Não ligar o Tailscale SSH. Não abrir porta para "testar".`
6. Se algo necessário não estiver na seção 4.1 ou nos passos, não decida: anote no corpo do PR como pergunta ao usuário.
7. Rode os critérios da seção 6 e cole os comandos e as saídas no corpo do PR.
8. Commit em inglês: `docs: add ADR 0003 tailscale-only network and drop caddy references`. Título e corpo do PR em inglês, com as duas exceções do cabeçalho registradas no corpo. Abra o PR só se o usuário pedir. Antes do PR, rode o `code-reviewer`. Depois, o PR passa por CI e `pr-reviewer`.

## 6. Critérios de pronto

Rode todos em PowerShell, na raiz do repo e na branch do PR. Os critérios usam só `git`. O CI do PR (`uv run ruff check .`, `uv run pytest`) precisa ficar verde, mas este PR não mexe em código.

```powershell
# 1. Estrutura do ADR
git grep -n '^## ' -- docs/adr/0003-tailscale-only-network.md

# 2. Conteúdo obrigatório do ADR (nenhuma linha MISSING)
$f = 'docs/adr/0003-tailscale-only-network.md'
foreach ($s in @('Status: Aceito', 'P4', 'P15', 'Caddy', 'tailscale serve', '--tcp=5432', '127.0.0.1', '0.0.0.0', 'ts.net', 'ufw', 'tailscale0', 'ACL', 'OpenSSH', 'Tailscale SSH', 'command=', 'sidecar', 'After=tailscaled.service', 'P17', 'task-implementer')) { git grep -qF -e $s -- $f; if ($LASTEXITCODE -ne 0) { "MISSING: $s" } }

# 3. Caddy e 443 sumiram dos textos fora de docs/plans e do ADR
git grep -n -i -e caddy -e 443 -- AGENTS.md .claude docs/plataforma-ml.md

# 4. Os textos novos apontam para o ADR
git grep -n 'ADR 0003' -- docs/plataforma-ml.md .claude/rules/infra.md

# 5. Stack no AGENTS.md
git grep -n 'Grafana, Tailscale)' -- AGENTS.md

# 6. docs/plans intocado: Caddy só nas linhas conhecidas
git grep -n -i caddy -- docs/plans

# 7. Arquivos do PR
git diff --name-only main...HEAD
```

Saída esperada:

1. Exatamente, nesta ordem: `## Contexto`, `## Decisão`, `## Consequências`, `## Alternativas consideradas`.
2. Nada, nenhuma linha `MISSING:`.
3. Nada.
4. Duas linhas em `docs/plataforma-ml.md` (Tailscale na stack e "Rede" em Operação) e duas em `.claude/rules/infra.md`.
5. Uma linha: `AGENTS.md:3:...`.
6. Só estas linhas, iguais às da `main` (mais este plano, que cita Caddy): `00-indice.md:142`, `00-indice.md:170`, `03-compose-rede-tailscale.md:5`, `:21`, `:122`, `28-bancos-mlflow-prefect.md:18`, `29-mlflow-no-compose.md:20`, `30-prefect-server-no-compose.md:18`, mais as linhas de `docs/plans/2026-11-07-tailscale-only-network-adr.md`.
7. Exatamente `.claude/rules/infra.md`, `AGENTS.md`, `docs/adr/0003-tailscale-only-network.md`, `docs/plataforma-ml.md` (e este plano, se entrar no PR sem alteração).

## 7. Testes necessários

não: só documentação e regras em Markdown (ADR, `AGENTS.md`, `docs/plataforma-ml.md`, `.claude/rules/infra.md`), sem código nem mudança de comportamento. A verificação é pelos `git grep` da seção 6, e as regras de infra viram teste no PR 03.

## 8. Casos de teste

n/a

## 9. Riscos e perguntas em aberto

Riscos:

- **O ADR decidir algo novo sem querer**, como portas, nomes de tag da ACL, porta do Tailscale SSH ou heartbeat. Mitigação: passo 6, e o ADR cita portas e tags só como planejamento dos PRs/itens.
- **A versão instalada do `tailscale serve` restringir as portas HTTPS** (risco do PR 03, linha 115). Nesse caso a saída seria servir por caminho (`--set-path`), o que muda o "uma porta por UI" deste ADR e exige revisá-lo. Mitigação: o ADR diz que o mapeamento é verificado no PR 03.
- **Mudar `.claude/rules/infra.md` altera o comportamento dos agentes** em `infra/**` e `.github/**`. Mitigação: `code-reviewer` e `pr-reviewer` obrigatórios.

Perguntas em aberto. O implementer não as resolve; sem resposta, segue o padrão:

- **Q1.** Status `Aceito` já no PR, como nos ADRs 0001 e 0002, ou `Proposto` até o merge? Padrão: `Aceito`.
- **Q2.** As portas por UI (8080, 5000, 4200, 3000, 5432) entram como parte da decisão ou só como referência ao plano 03? Padrão: só como referência ("mapeamento planejado no PR 03"), para que mudar uma porta não exija novo ADR.
- **Q3.** Incluir motivos que os planos não dão, como o custo de memória do sidecar numa VPS de 1 GB? Padrão: não. O sidecar fica só como "rejeitado pelo usuário na P15".
- **Q4.** A regra nova da linha 10 de `infra.md` inclui o Grafana, que tem login próprio, mas fica na tailnet pela mesma decisão. Manter "MLflow, Prefect e Grafana" ou voltar para "MLflow e Prefect"? Padrão: incluir o Grafana, porque a linha 17 do índice põe todas as UIs em loopback.
- **Q5. Sobras em `docs/plans/`**, que o implementer não pode editar. Padrão: um PR só de `docs/**`, feito pelo `task-planner` depois do merge deste ADR.
  - `00-indice.md`, linhas 17 e 160: a P15 ainda aparece como aberta, e a linha 17 ainda oferece "IP do Tailscale". Mover a P15 para "Decisões resolvidas" e marcar o item 2 de "ADRs a escrever" como `docs/adr/0003-tailscale-only-network.md`.
  - `02-provisionar-vps-manual.md`, linha 31: o passo condicional `After=tailscaled.service` deixa de valer.
  - `03-compose-rede-tailscale.md`:
    - Linhas 5, 21, 113 e 122: "decidir entre os dois" já está decidido.
    - Linha 38: cita a regra antiga do firewall ("só 22 e 443").
    - Linha 53 e casos de teste 4 e 5: ainda aceitam `*_BIND_IP` no IP do Tailscale. Avaliar se o teste deve passar a exigir só `127.0.0.1`.
  - `10-postgres-no-compose.md`, linhas 8, 46 e 76, e `12-subir-postgres-vps-manual.md`, linhas 16 e 37: texto condicional da P15.
  - `28-bancos-mlflow-prefect.md:18`, `29-mlflow-no-compose.md:20` e `30-prefect-server-no-compose.md:18`: dizem "O doc diz 'atrás do Caddy'", o que fica histórico depois deste PR. Basta trocar por uma referência ao ADR 0003.
- **Q6.** `docs/plataforma-ml.md`, linha 171 (CI/CD, "SSH na VPS"): acrescentar "pela tailnet"? Padrão: não. A linha 179 nova e o ADR já dizem isso.

## 10. Decisões que exigem ADR

- Esta tarefa **é** o ADR `docs/adr/0003-tailscale-only-network.md`. O `task-implementer` o escreve por instrução expressa do usuário, como exceção à regra "Nenhum agente escreve ADR", válida só para este PR. O ADR precisa estar mergeado antes do PR 03 (e, por consequência, dos PRs 10, 29, 30, 39 e 47).
- Nenhum outro ADR é necessário. Ligar o Tailscale SSH ou servir as UIs por caminho exigiria revisar este ADR, mas nenhuma das duas coisas está no escopo.
