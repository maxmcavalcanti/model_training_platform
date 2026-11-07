# Guia de Ciência de Dados — Modelos em Produção

Nov 7, 2026 · @Maximiliano

## O que você vai construir

Você vai colocar dois modelos em produção e cuidar deles: um que prevê a carga de energia do Brasil para o dia seguinte e outro que prevê se vai chover amanhã em quatro capitais. No fim, você terá a experiência exata que as vagas pedem: um modelo rodando todo dia sozinho, com erro medido contra a realidade e uma decisão sua de quando retreinar.

**A sua parte é ser a dona do modelo.** Isso quer dizer:

- Definir o problema, a métrica e o que é "bom o suficiente"
- Construir features, treinar e provar que o modelo bate um baseline simples
- Empacotar o código no formato combinado (o contrato)
- Decidir quando uma versão nova entra em produção
- Acompanhar o erro e investigar quando ele piorar

**O que não é sua parte:** servidor, banco, agendamento dos jobs, deploy, backups. A plataforma já cuida disso, como aconteceria em uma empresa com time de ML engineering. Os detalhes estão no documento *Plataforma ML — Infra e Dados*.

**Você não precisa esperar a plataforma ficar pronta.** Os dados do ONS e do Open-Meteo são públicos: dá para começar a exploração hoje, baixando direto das fontes.

## Ferramentas

Todas são padrão de mercado e aparecem nas vagas; não use nada além disso no começo.

| Ferramenta | Para quê | Nível que você precisa |
| --- | --- | --- |
| Python 3.12 + VS Code ou Jupyter | Escrever e rodar código | Já usa |
| pandas | Manipular os dados | Já usa |
| scikit-learn | Baselines, validação, métricas, regressão logística | Médio |
| LightGBM | Modelo principal (árvores com boosting), ótimo para dados tabulares | Básico: `fit`, `predict`, alguns hiperparâmetros |
| MLflow | Registrar cada experimento e publicar o modelo escolhido | Básico: `log_param`, `log_metric`, `log_model`, aliases |
| SQL (Postgres) | Ler os dados da plataforma | Médio: `SELECT`, `JOIN`, janelas por data |
| Git + GitHub | Versionar o código e abrir PRs | Básico: branch, commit, PR |
| pytest | Testar as funções do contrato | Básico: 3 ou 4 testes por modelo |
| Prefect (só a interface) | Ver se o job do seu modelo rodou e ler o erro | Só leitura |
| Grafana | Painel de erro do seu modelo | Montar 2 ou 3 gráficos |

**Estrutura de pastas:** o repositório `modelos` é seu e segue o esqueleto do documento da plataforma. Notebook é para explorar; tudo que vai para produção mora em `src/models/`.

## Os dois modelos

Dois tipos de problema diferentes de propósito: uma regressão de série temporal e uma classificação. São os dois formatos mais comuns em vagas.

|  | `load_d1` | `rain_d1` |
| --- | --- | --- |
| Pergunta | Quanta energia cada subsistema vai consumir amanhã? | Vai chover amanhã nesta cidade? |
| Tipo | Regressão (série temporal) | Classificação binária |
| Alvo | `load_avg_mw` do dia D+1, por subsistema (SE/CO, S, NE, N) | 1 se `precip_mm` ≥ 1 em D+1, senão 0, por cidade |
| Métrica principal | MAPE (erro percentual médio) | Brier score (qualidade da probabilidade) |
| Métricas de apoio | MAE em MWmed | ROC AUC, precisão e recall no limiar escolhido |
| Baseline a bater | Carga do mesmo dia da semana anterior (D−7) | Frequência de chuva no mês na cidade (climatologia) |
| Referência de teto | — | A própria previsão do Open-Meteo: dificilmente você vai bater, e tudo bem |
| Modelo sugerido | LightGBM com features de calendário, defasagens e clima | Regressão logística primeiro, depois LightGBM |

**Por que baseline importa:** um MAPE de 4% não diz nada sozinho. Se "repetir a semana passada" já dá 5%, o seu modelo ganhou um ponto; se dá 3,5%, ele é pior que não fazer nada. Toda apresentação de resultado começa pela comparação com o baseline.

**Uma decisão que é sua (e é ótima para entrevista):** a previsão do tempo só começa a ser guardada agora, então não há histórico dela para treinar. Para usar clima no `load_d1`, as opções são treinar com o clima observado e servir com a previsão, aceitando a diferença, ou esperar alguns meses de previsões acumuladas. Documente qual escolheu e por quê.

## Passo a passo

Faça primeiro o `load_d1` inteiro, até produção, e só depois o `rain_d1`: um modelo simples no ar ensina mais do que dois modelos ótimos no notebook. Cada etapa termina com um entregável concreto.

**Etapa 1 — Exploração** (pode começar hoje, com os dados baixados direto das fontes)

- [ ] Gráfico da carga diária por subsistema desde 2015
- [ ] Padrões: dia da semana, mês, feriados, tendência, quedas estranhas (ex.: pandemia em 2020)
- [ ] Entregável: notebook com 5 a 8 gráficos e uma frase de conclusão em cada

**Etapa 2 — Baseline e validação**

- [ ] Implementar o baseline D−7 e medir MAPE e MAE
- [ ] Montar a validação temporal (backtest): treinar até uma data, testar no mês seguinte, avançar e repetir. Nunca separar treino e teste de forma aleatória em série temporal
- [ ] Entregável: tabela com o erro do baseline por subsistema, que vira a régua de tudo

**Etapa 3 — Features e modelo**

- [ ] Features de calendário (dia da semana, mês, feriado, véspera de feriado)
- [ ] Defasagens da carga (D−7, D−14, média móvel), usando só o que já existe no momento da previsão
- [ ] Treinar LightGBM no mesmo backtest e registrar cada tentativa no MLflow
- [ ] Entregável: comparação modelo × baseline, por subsistema, no MLflow

**Etapa 4 — Empacotar no contrato**

- [ ] Mover o código para `src/models/load_d1/`: `build_features`, `predict`, `evaluate`, `train`
- [ ] Escrever testes: features sem nulos, sem datas futuras, saída com as colunas certas
- [ ] Entregável: PR aprovado no repositório `modelos`, com CI verde

**Etapa 5 — Ir para produção**

- [ ] Rodar `train.py` e registrar o modelo `load_d1` no MLflow
- [ ] Marcar a versão com o alias `champion`: a partir daí, o job diário usa o seu modelo
- [ ] Entregável: previsões aparecendo em `predictions.model_predictions` todo dia

**Etapa 6 — Monitorar**

- [ ] Painel no Grafana: previsto × real e MAPE móvel de 7 e 30 dias
- [ ] Escrever a regra de retreino (ex.: MAPE de 30 dias acima do baseline por 2 semanas, ou retreino mensal fixo)
- [ ] Entregável: um mês de histórico no painel

**Etapa 7 — Documentar**

- [ ] Model card de uma página: objetivo, dados, métrica, resultado contra o baseline, limitações, regra de retreino
- [ ] Repetir as etapas 2 a 7 para o `rain_d1`

## Armadilhas

Quase todo modelo que vai bem no notebook e mal em produção cai em uma destas. Vale reler esta lista antes da Etapa 5.

| Armadilha | Como aparece | Como evitar |
| --- | --- | --- |
| Vazamento de dados | Backtest bom demais; em produção, o erro dobra | Para cada feature, perguntar: "no dia D, às 7h, eu já teria esse dado?" |
| Separação aleatória em série temporal | O modelo "vê o futuro" durante o treino | Sempre treinar no passado e testar no futuro (backtest) |
| Dado que ainda não chegou | Em produção, a feature D−1 vem vazia porque o ONS ainda não publicou | Usar só defasagens que existem no horário do job; testar `build_features` com a data de hoje |
| Treino e produção calculam diferente | Feature feita no notebook e reescrita depois | Uma única função `build_features`, usada no treino e no score |
| Otimizar só a métrica | Ganhar 0,1 ponto de MAPE com um modelo impossível de explicar | Ganho pequeno sobre o baseline não justifica complexidade grande |
| Esquecer eventos raros | Feriados e 2020 distorcem o modelo | Feature de feriado; considerar tirar ou marcar o período da pandemia |

## Rotina com o modelo no ar

Uns 20 minutos por semana. É essa rotina que transforma "fiz um modelo" em "mantenho um modelo em produção".

**Toda semana**

- [ ] Olhar o painel: o MAPE de 7 dias está acima do de 30 dias? Algum subsistema destoa?
- [ ] Conferir no Prefect se o job do seu modelo rodou todos os dias
- [ ] Anotar num log (um arquivo no repositório basta) qualquer coisa estranha e a explicação: feriado, onda de calor, dado atrasado

**Quando o erro piorar**

1. É problema de dado? Ver se as tabelas `raw` chegaram completas. Se não chegaram, avisar a plataforma.
2. É um evento pontual? Anotar e esperar.
3. É mudança de padrão (drift)? Retreinar com dados recentes, comparar com o `champion` atual no mesmo backtest e só trocar o alias se o novo for melhor.

**Toda troca de `champion` vai para o log:** data, versão antiga, versão nova, motivo e métrica antes e depois. Esse log é a sua prova de que operou o modelo.

## Como contar em entrevista

Recrutador não quer ouvir o nome do algoritmo; quer ouvir que o modelo rodou sozinho, foi medido contra a realidade e que você tomou decisões com base nisso.

**No currículo (modelo de frase, troque pelos seus números):**

> Desenvolvi e operei em produção um modelo de previsão de carga de energia D+1 (LightGBM) com dados do ONS e Open-Meteo, com inferência diária automatizada, registro de modelos no MLflow e monitoramento de erro no Grafana. Reduziu o MAPE de X% (baseline sazonal) para Y% e foi retreinado N vezes a partir de regras de drift.

**Perguntas que vão aparecer, e onde está a sua resposta:**

| Pergunta | Onde está a resposta |
| --- | --- |
| Como você validou o modelo? | Etapa 2: backtest temporal e comparação com o baseline |
| Como garantiu que não havia vazamento? | Armadilhas e os testes de `build_features` |
| Como o modelo chega em produção? | Registro no MLflow + alias `champion`; o job diário usa a versão promovida |
| Como sabe que o modelo está funcionando? | Painel e métricas diárias de erro real × previsto |
| Já precisou retreinar? Por quê? | O log de trocas de `champion` |
| O que você faria diferente? | A decisão sobre usar clima observado × previsão |

Seja honesta sobre a divisão: "a infraestrutura foi feita por um engenheiro, eu fui a dona do modelo" é exatamente como funciona em empresas maduras, e é uma resposta forte.

## Glossário

| Termo | O que é |
| --- | --- |
| Alias `champion` | Etiqueta no MLflow que diz qual versão do modelo está em produção. Mudar a etiqueta é fazer o deploy |
| Backtest | Validação que simula o passado: treina até uma data, testa no período seguinte, avança e repete |
| Baseline | Previsão ingênua (ex.: repetir a semana passada) que o modelo precisa bater para valer a pena |
| Brier score | Erro médio entre a probabilidade prevista e o que aconteceu (0 ou 1); quanto menor, melhor |
| Data drift | Mudança na distribuição dos dados de entrada ao longo do tempo |
| Concept drift | Mudança na relação entre entrada e alvo: o padrão que o modelo aprendeu deixou de valer |
| MAPE | Erro percentual absoluto médio; 3% quer dizer que, em média, a previsão erra 3% para mais ou para menos |
| Model card | Documento curto que descreve o modelo, seus dados, métricas e limitações |
| Model registry | Catálogo de versões de modelos com estado (qual está em produção); aqui é o MLflow |
| Vazamento (leakage) | Usar no treino uma informação que não existiria no momento real da previsão |
