# 44 — Executor isolado: rodar código do pacote `modelos` numa versão marcada

> Executa: agente. Depende de: 43. Branch sugerida: `feat/model-executor`.
> Pré-requisito: ADR "Execução de modelos" aprovado (seção 10). **Este PR não começa sem ele.**
> TDD: test-writer (vermelho) → implementação (verde) → refatorar.

## 1. Objetivo

Executar um comando Python num ambiente que tem o código da plataforma **mais** o pacote `modelos` numa versão específica, sem instalar nada no ambiente do worker, usando `uv run --with`.
Cada modelo roda com a sua versão do pacote, num subprocesso; erro dela sobe com o traceback.

## 2. Fora do escopo

- O que roda dentro do subprocesso (PR 45 para score, PR 53 para monitoramento).
- Flow e agenda (PR 46).

## 3. Fase do roadmap

Fase 4 — "Job genérico de score lendo `@champion`".

## 4. Arquivos a criar ou alterar

| Caminho | Motivo |
| --- | --- |
| `flows/executor.py` | `RunFailed`, `package_spec(versao)`, `build_command(versao, python_module, args)`, `executar(comando, *, extra_env)` |
| `infra/jobs/Dockerfile` | Instalar `git` (para `git+https`); `UV_CACHE_DIR` gravável pelo usuário `app` |
| `infra/.env.example` | `MODELS_REPO=https://github.com/<dono>/modelos` (repo público, P2 resolvida: sem token) |
| `tests/fixtures/fake_models/` | Pacote instalável mínimo chamado `modelos` com `src/models/fake_model/__init__.py` (test-writer) |
| `tests/test_executor.py` | Testes (test-writer) |

Do doc: "O job de score da plataforma instala o pacote `modelos` numa versão marcada (tag) e chama as funções do contrato. Ela nunca precisa mexer no repositório `plataforma` para colocar um modelo novo em produção." "Erro dentro do código dela aparece no Prefect com o traceback, e quem investiga é ela."

Por que `uv run --with` (ver PR 01): cria um ambiente efêmero em cache, sobreposto ao do projeto, com o pacote pedido; versões diferentes por modelo não colidem; nada é instalado no ambiente do worker.

## 5. Passos

1. (test-writer) Crie `tests/fixtures/fake_models/` (`pyproject.toml` com `name = "modelos"`, `version = "0.0.1"`, build hatchling, pacote `src/models`; `src/models/__init__.py`; `src/models/fake_model/__init__.py` com `build_features`, `predict`, `evaluate` triviais). Escreva os testes da seção 8. Os que chamam `uv` de verdade rodam sem marcador (levam poucos segundos; o `uv` existe no CI e na máquina de desenvolvimento). Confirme falha por `ModuleNotFoundError: flows.executor`. Commit `test: add isolated executor tests`.
2. (implementer) `flows/executor.py`:
   - `package_spec(versao: str) -> str`: se `MODELS_LOCAL_SOURCE` estiver definida (testes e desenvolvimento), devolve esse caminho; senão `f"modelos @ git+{MODELS_REPO}@{versao}"`. `versao` deve casar `^v?\d+\.\d+\.\d+([-.+][0-9A-Za-z.]+)?$`; senão `ValueError`.
   - `build_command(versao, python_module, args) -> list[str]`: `["uv", "run", "--frozen", "--with", package_spec(versao), "python", "-m", python_module, *args]`.
   - `executar(comando, *, extra_env=None) -> None`: roda com `subprocess.run`, repassa stdout/stderr linha a linha para o logger; código ≠ 0 → `RunFailed(codigo, stderr_tail)` (últimas 50 linhas, onde está o traceback dela).
   - Sem token de leitura: o repo `modelos` é público (decisão do usuário, 2026-11-07, P2 resolvida). Não implemente suporte a token.
3. `infra/jobs/Dockerfile`: `apt-get install -y --no-install-recommends git`; `ENV UV_CACHE_DIR=/home/app/.cache/uv`.
4. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_executor.py` | Todos passam |
| `MODELS_LOCAL_SOURCE=tests/fixtures/fake_models uv run --frozen --with tests/fixtures/fake_models python -c "import modelos.fake_model; print('ok')"` | `ok` |
| `docker build -f infra/jobs/Dockerfile -t platform-jobs .` e `docker run --rm platform-jobs git --version` | `git version ...` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: isolamento de versões, validação da versão e propagação do traceback são os requisitos de segurança e de operação deste mecanismo.

## 8. Casos de teste

1. `build_command("v0.3.0", "flows.score_one", ["--model", "load_d1"])` sem `MODELS_LOCAL_SOURCE` e com `MODELS_REPO=https://github.com/x/modelos` → `["uv","run","--frozen","--with","modelos @ git+https://github.com/x/modelos@v0.3.0","python","-m","flows.score_one","--model","load_d1"]`.
2. `versao = "main; rm -rf /"` → `ValueError`.
3. Com `MODELS_LOCAL_SOURCE` apontando para a fixture: `executar(build_command("v0.0.1", ...))` de um módulo que importa `modelos.fake_model` → termina sem exceção.
4. Comando que levanta `ZeroDivisionError` no subprocesso → `RunFailed` com código 1 e a mensagem contém `ZeroDivisionError` e `Traceback`.
5. `MODELS_REPO` que não começa com `https://github.com/` (ex.: `https://x-access-token:abc@github.com/x/modelos`) → `ValueError`: credencial nunca entra na URL do pacote.
6. O pacote da fixture não fica importável no ambiente do teste depois da execução (`importlib.util.find_spec("modelos")` é `None`).

## 9. Riscos e perguntas em aberto

- Conflito de dependências entre o pacote dela e o da plataforma (ex.: versões de `pandas`) faz o `uv run --with` falhar. Isso aparece como `RunFailed` do modelo dela; o ADR deve dizer quem resolve.
- Primeira execução de cada versão baixa e instala o pacote (segundos a minutos). Depois fica em cache no `UV_CACHE_DIR`; considerar volume para o cache no worker. Disco de 25 GB: o cache cresce com cada versão; limpar versões antigas (`uv cache prune`) se `df -h /` passar de 60%.
- Memória: cada modelo roda num subprocesso Python próprio dentro do `prefect-worker` (`mem_limit` do PR 34). Rodar os modelos em sequência, não em paralelo, enquanto a VPS tiver 1 GB.

## 10. Decisões que exigem ADR

- ADR "Execução de modelos" (P12, P13, P14), antes deste PR e dos PRs 42 e 43:
  - como a versão do pacote é escolhida (tag `models_package` na versão do modelo no MLflow);
  - mecanismo de instalação (`uv run --with`, subprocesso por modelo);
  - tipo de `conn` passado a `build_features` (proposta: `sqlalchemy.Connection` com usuário `scorer`);
  - objeto `model` passado a `predict` (proposta: `mlflow.pyfunc.load_model(uri)`);
  - saída de `predict` estrita (só `chave`, `target_date`, `predicted_value`).
  Como a assinatura do contrato não muda, mas a semântica dos argumentos é fixada, o ADR precisa da concordância da cientista (`AGENTS.md`: "A assinatura de `build_features`, `predict` e `evaluate` só muda por decisão registrada em ADR").
