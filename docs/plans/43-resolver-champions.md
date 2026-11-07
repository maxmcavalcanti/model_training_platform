# 43 — Descobrir os modelos `champion` no MLflow

> Executa: agente. Depende de: 42 e do ADR "Execução de modelos" (PR 44, seção 10) aprovado na parte da tag de versão do pacote. Branch sugerida: `feat/score-champions`.
> TDD: passo 0 (dependência) → test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Listar, no model registry do MLflow, todo modelo que tem o alias `champion`, com versão, URI e a versão do pacote `modelos` que o gerou.
É o que torna o score genérico: modelo novo com `champion` entra no job sem mudança na plataforma.

## 2. Fora do escopo

- Carregar o modelo e instalar o pacote (PRs 44 e 45).

## 3. Fase do roadmap

Fase 4 — "Job genérico de score lendo `@champion`".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `pyproject.toml`, `uv.lock` | `mlflow==<mesma versão do servidor, PR 29>` (passo 0) |
| `flows/registro.py` | `Champion` (dataclass), `TAG_PACOTE = "pacote_modelos"`, `listar_champions(cliente)` |
| `tests/test_registro_champions.py` | Testes com MLflow local em SQLite (test-writer) |

Do doc: "O único ponto de passagem é o alias `champion` no MLflow. Trocar o alias é o deploy de um modelo." "O treino (`train.py`) … termina registrando o modelo no MLflow com o nome do módulo (`carga_d1`)." "O job de score da plataforma instala o pacote `modelos` numa versão marcada (tag)".

Proposta deste plano (a confirmar no ADR, P12): a versão do pacote vem de uma **tag da versão do modelo** no registry, `pacote_modelos`, com o valor da tag git do repo `modelos` (ex.: `v0.3.0`), gravada por ela no `train.py`.

## 5. Passos

0. (implementer) `uv add mlflow==<versão>`. Commit `build: add mlflow`.
1. (test-writer) Testes da seção 8. Fixture: `mlflow.set_tracking_uri(f"sqlite:///{tmp_path}/mlflow.db")`, registra modelos `pyfunc` triviais (uma classe `PythonModel` que devolve a entrada) com `mlflow.pyfunc.log_model(..., registered_model_name=...)`, define aliases com `MlflowClient().set_registered_model_alias` e tags com `set_model_version_tag`. Confirme falha por `ModuleNotFoundError: flows.registro`. Commit `test: add champion discovery tests`.
2. (implementer) `flows/registro.py`:
   - `@dataclass(frozen=True) class Champion: nome: str; versao: str; uri: str; pacote_versao: str | None`.
   - `listar_champions(cliente: MlflowClient) -> list[Champion]`: percorre `search_registered_models` (com paginação), para cada um tenta `get_model_version_by_alias(nome, "champion")`; sem alias → ignora; com alias → `Champion(nome, versao, f"models:/{nome}@champion", tags.get(TAG_PACOTE))`. Ordena por `nome`.
   - Nomes de modelo precisam ser identificadores Python válidos (viram `modelos.<nome>`); nome inválido → o `Champion` sai com `pacote_versao=None` e um aviso no log (o PR 46 trata `None` como erro daquele modelo).
3. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_registro_champions.py` | Todos passam |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: alias ausente, várias versões e paginação são casos que decidem quais modelos rodam em produção.

## 8. Casos de teste

1. Registry vazio → lista vazia.
2. Modelo `carga_d1` com versões 1 e 2, alias `champion` na 1 e tag `pacote_modelos=v0.1.0` → um `Champion("carga_d1", "1", "models:/carga_d1@champion", "v0.1.0")`.
3. Trocar o alias para a versão 2 → `versao == "2"` e o `pacote_versao` da versão 2.
4. Modelo registrado sem alias `champion` → não aparece.
5. Dois modelos com champion → dois itens, ordenados por nome.
6. Champion sem a tag `pacote_modelos` → aparece com `pacote_versao=None`.
7. 120 modelos registrados (acima de uma página padrão de busca, se a versão fixada paginar em 100) com champion em todos → 120 itens.

## 9. Riscos e perguntas em aberto

- P12: tag na versão do modelo é proposta; alternativa é um campo fixo (ex.: o pacote sempre na última tag). O ADR decide e ela precisa concordar, porque o `train.py` dela grava a tag.
- O `mlflow` como dependência deixa a imagem `jobs` bem maior. Aceitável; alternativa (`mlflow-skinny`) pode ser avaliada depois.

## 10. Decisões que exigem ADR

Depende do ADR "Execução de modelos" (PR 44).
