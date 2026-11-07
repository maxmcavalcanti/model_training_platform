# 09 — Tabela `ref.locations` com as quatro capitais

> Executa: agente. Depende de: 07. Branch sugerida: `feat/ref-locations`.
> Pré-requisito: ADR "Contrato de dados v1 (`raw` e `ref`)" aprovado (ver seção 10).
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Criar por migração a tabela `ref.locations` e carregar as quatro capitais, uma por subsistema.
É de onde os jobs de clima tiram a lista de lugares; cidade nova entra por dado, não por código.

## 2. Fora do escopo

- `ref.calendar` (PR 19).
- Interface para cadastrar cidade (uma migração de dados ou um `INSERT` pelo admin bastam por enquanto).

## 3. Fase do roadmap

Fase 1 — "`ref.locations`, `ref.calendar`".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `migrations/versions/0003_ref_locations.py` | Cria a tabela e insere as 4 linhas; `downgrade` apaga a tabela |
| `tests/test_ref_locations.py` | Testes (test-writer) |

Modelo de dados (`docs/plataforma-ml.md`):

| Tabela | Colunas principais | Chave | Escreve | Lê |
| --- | --- | --- | --- | --- |
| `ref.locations` | `location_id`, `nome`, `lat`, `lon`, `subsistema` | `location_id` | Plataforma | Todos |

"Locais de clima (proposta): uma capital por subsistema — São Paulo (SE/CO), Porto Alegre (S), Recife (NE), Belém (N)."

## 5. Passos

1. (test-writer) Escreva `tests/test_ref_locations.py` (`@pytest.mark.db`, banco migrado até `head`) com os casos da seção 8. Confirme falha porque `ref.locations` não existe. Commit `test: add ref.locations tests`.
2. (implementer) `uv run alembic revision -m "ref_locations" --rev-id 0003`.
3. `upgrade`: crie a tabela:
   - `location_id text primary key` (slug minúsculo, `^[a-z_]+$`, via `CHECK`)
   - `nome text not null`
   - `lat double precision not null check (lat between -90 and 90)`
   - `lon double precision not null check (lon between -180 and 180)`
   - `subsistema text not null check (subsistema in ('SE','S','NE','N'))` (códigos usados pelo ONS; SE inclui CO)
   - Depois, `op.bulk_insert` com:

   | location_id | nome | lat | lon | subsistema |
   | --- | --- | --- | --- | --- |
   | `sao_paulo` | São Paulo | -23.55 | -46.63 | SE |
   | `porto_alegre` | Porto Alegre | -30.03 | -51.23 | S |
   | `recife` | Recife | -8.05 | -34.88 | NE |
   | `belem` | Belém | -1.46 | -48.49 | N |

4. `downgrade`: `DROP TABLE ref.locations`.
5. As permissões vêm dos privilégios padrão do PR 07 (admin cria → `ingestor` escreve, todos leem). Não repetir `GRANT`.
6. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_ref_locations.py tests/test_migrations.py` | Todos passam |
| `uv run alembic heads` | `0003 (head)` |
| `uv run pytest` | Suíte verde |
| `uv run ruff check .` e `uv run ruff format --check .` | Sem erro |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: a tabela tem restrições (códigos de subsistema, faixas de coordenada) e dados iniciais que os jobs de clima assumem.

## 8. Casos de teste

1. Após `upgrade head`, `SELECT location_id, subsistema FROM ref.locations ORDER BY location_id` devolve exatamente as 4 linhas da tabela do passo 3.
2. Cada subsistema `SE`, `S`, `NE`, `N` aparece exatamente uma vez.
3. Inserir `subsistema = 'CO'` falha (violação de `CHECK`).
4. Inserir `lat = 91` falha.
5. Inserir `location_id = 'São Paulo'` falha (slug inválido).
6. Como `leitura`, `SELECT` funciona; como `ingestor`, `INSERT` de uma 5ª cidade funciona; como `cientista`, `INSERT` falha.
7. `downgrade` até `0002` remove a tabela.

## 9. Riscos e perguntas em aberto

- P18: formato de `location_id` (slug texto) é proposta deste plano; o doc não define. Confirmar com o usuário antes do merge, porque vira chave em `raw.clima_*` e em `predictions.model_predictions.chave` do `rain_d1`.
- Coordenadas com 2 casas (~1 km) bastam para a grade do Open-Meteo.

## 10. Decisões que exigem ADR

- ADR "Contrato de dados v1 (`raw` e `ref`)": tipos, chaves e semântica das tabelas `ref.locations`, `ref.calendar`, `raw.ons_daily_load`, `raw.weather_observed`, `raw.weather_forecast` (inclui `issued_at` e `horizon_days`, ver PR 13). A regra de `.claude/rules/migrations-e-dados.md` diz que mudar `raw` ou `ref` é mudança de contrato e exige ADR; criar as primeiras tabelas fixa esse contrato. Um ADR só cobre os PRs 09, 13, 19, 21 e 25. Deve ser escrito e aprovado antes deste PR.
