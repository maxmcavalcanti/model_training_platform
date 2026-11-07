# 18 — Verificar as fontes antes da ingestão do ONS e do clima observado (manual)

> Executa: **usuário** (pode delegar a um agente de pesquisa; o resultado volta como edição de `docs/plataforma-ml.md` num PR de docs). Depende de: nada; pode ser feito a qualquer momento antes do PR 20.
> Fase do roadmap: Fase 1 — "Para verificar antes da Fase 1" (`docs/plataforma-ml.md`, "Fontes de dados").

## Por que é manual

São perguntas sobre o comportamento das fontes ao longo de dias. Não há código a escrever; as respostas mudam os horários dos jobs e as janelas de upsert, e os PRs 20 a 26 dependem delas.

## Checklist

ONS (bucket público `ons-aws-prod-opendata`, prefixo `dataset/carga_energia_di/`):

- [ ] Listar os arquivos e a data de modificação:
  `curl -s "https://ons-aws-prod-opendata.s3.amazonaws.com/?list-type=2&prefix=dataset/carga_energia_di/" | grep -oE "<Key>[^<]+</Key>|<LastModified>[^<]+</LastModified>"`
- [ ] Anotar o padrão de nome do arquivo anual em parquet (ex.: `CARGA_ENERGIA_<ANO>.parquet`) e se existe um por ano.
- [ ] Baixar o do ano corrente e listar colunas e tipos:
  `curl -s -o /tmp/carga.parquet "https://ons-aws-prod-opendata.s3.amazonaws.com/<Key>"` e
  `uv run --with pandas --with pyarrow python -c "import pandas as pd; d=pd.read_parquet('/tmp/carga.parquet'); print(d.dtypes); print(d.tail(8)); print(sorted(d.iloc[:,0].unique()))"`
- [ ] Anotar: nome da coluna de subsistema e os códigos (esperado `SE`, `S`, `NE`, `N`), coluna de data, coluna de carga em MWmed.
- [ ] Atraso: em 3 dias diferentes, por volta das 07:00 BRT, anotar a última data presente no arquivo do ano. Resultado: "o dia D−1 está disponível às __:__".
- [ ] Revisões: guardar o arquivo de hoje e comparar com o de daqui a 7 dias; anotar se valores de dias já publicados mudaram e até quantos dias para trás.

Open-Meteo, arquivo (ERA5):

- [ ] Ver a última data com valor não nulo:
  `curl -s "https://archive-api.open-meteo.com/v1/archive?latitude=-23.55&longitude=-46.63&start_date=<hoje-10>&end_date=<hoje>&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,relative_humidity_2m_mean&timezone=America%2FSao_Paulo"`
- [ ] Anotar o atraso (em dias) e se os valores recentes mudam de um dia para o outro.

## Verificação de pronto

- [ ] As respostas estão registradas em `docs/plataforma-ml.md` (os dois itens da lista "Para verificar antes da Fase 1" marcados, com os números) via PR de docs.
- [ ] Se o atraso do ONS tornar 07:00 cedo demais, o novo horário está anotado (o PR 22 usa esse valor no crontab).
- [ ] Se o ONS revisa mais de 30 dias para trás ou o ERA5 atrasa mais de 10 dias, as janelas do doc (30 e 10 dias) foram ajustadas.
