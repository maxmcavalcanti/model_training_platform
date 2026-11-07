# 44 — Executor isolado: rodar código do pacote `modelos` numa versão marcada

> Executa: agente. Depende de: 43. Branch sugerida: `feat/executor-modelos`.
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
| `flows/executor.py` | `ExecucaoFalhou`, `especificacao_pacote(versao)`, `montar_comando(versao, modulo_python, args)`, `executar(comando, *, env_extra)` |
| `infra/jobs/Dockerfile` | Instalar `git` (para `git+https`); `UV_CACHE_DIR` gravável pelo usuário `app` |
| `infra/.env.example` | `MODELOS_REPO=https://github.com/<dono>/modelos`, `MODELOS_GIT_TOKEN=` (vazio se público) |
| `tests/fixtures/modelos_fake/` | Pacote instalável mínimo chamado `modelos` com `src/modelos/teste_fake/__init__.py` (test-writer) |
| `tests/test_executor.py` | Testes (test-writer) |

Do doc: "O job de score da plataforma instala o pacote `modelos` numa versão marcada (tag) e chama as funções do contrato. Ela nunca precisa mexer no repositório `plataforma` para colocar um modelo novo em produção." "Erro dentro do código dela aparece no Prefect com o traceback, e quem investiga é ela."

Por que `uv run --with` (ver PR 01): cria um ambiente efêmero em cache, sobreposto ao do projeto, com o pacote pedido; versões diferentes por modelo não colidem; nada é instalado no ambiente do worker.

## 5. Passos

1. (test-writer) Crie `tests/fixtures/modelos_fake/` (`pyproject.toml` com `name = "modelos"`, `version = "0.0.1"`, build hatchling, pacote `src/modelos`; `src/modelos/__init__.py`; `src/modelos/teste_fake/__init__.py` com `build_features`, `predict`, `evaluate` triviais). Escreva os testes da seção 8. Os que chamam `uv` de verdade rodam sem marcador (levam poucos segundos; o `uv` existe no CI e na máquina de desenvolvimento). Confirme falha por `ModuleNotFoundError: flows.executor`. Commit `test: add isolated executor tests`.
2. (implementer) `flows/executor.py`:
   - `especificacao_pacote(versao: str) -> str`: se `MODELOS_FONTE_LOCAL` estiver definida (testes e desenvolvimento), devolve esse caminho; senão `f"modelos @ git+{MODELOS_REPO}@{versao}"`. `versao` deve casar `^v?\d+\.\d+\.\d+([-.+][0-9A-Za-z.]+)?$`; senão `ValueError`.
   - `montar_comando(versao, modulo_python, args) -> list[str]`: `["uv", "run", "--frozen", "--with", especificacao_pacote(versao), "python", "-m", modulo_python, *args]`.
   - `executar(comando, *, env_extra=None) -> None`: roda com `subprocess.run`, repassa stdout/stderr linha a linha para o logger; código ≠ 0 → `ExecucaoFalhou(codigo, ultimas_linhas_stderr)` (últimas 50 linhas, onde está o traceback dela).
   - Token: se `MODELOS_GIT_TOKEN` existir, passa ao subprocesso por variáveis de config do git (`GIT_CONFIG_COUNT=1`, `GIT_CONFIG_KEY_0=url.https://x-access-token:<token>@github.com/.insteadOf`, `GIT_CONFIG_VALUE_0=https://github.com/`), nunca na linha de comando; e qualquer ocorrência do token em mensagens de log ou de exceção é trocada por `***`.
3. `infra/jobs/Dockerfile`: `apt-get install -y --no-install-recommends git`; `ENV UV_CACHE_DIR=/home/app/.cache/uv`.
4. Rode os critérios de pronto.

## 6. Critérios de pronto

| Comando | Saída esperada |
| --- | --- |
| `uv run pytest tests/test_executor.py` | Todos passam |
| `MODELOS_FONTE_LOCAL=tests/fixtures/modelos_fake uv run --frozen --with tests/fixtures/modelos_fake python -c "import modelos.teste_fake; print('ok')"` | `ok` |
| `docker build -f infra/jobs/Dockerfile -t plataforma-jobs .` e `docker run --rm plataforma-jobs git --version` | `git version ...` |
| `uv run pytest` | Suíte verde |
| `gh pr checks` | Verde |

## 7. Testes necessários

`sim`: isolamento de versões, propagação do traceback e não vazar o token são os requisitos de segurança e de operação deste mecanismo.

## 8. Casos de teste

1. `montar_comando("v0.3.0", "flows.score_um", ["--modelo", "carga_d1"])` sem `MODELOS_FONTE_LOCAL` e com `MODELOS_REPO=https://github.com/x/modelos` → `["uv","run","--frozen","--with","modelos @ git+https://github.com/x/modelos@v0.3.0","python","-m","flows.score_um","--modelo","carga_d1"]`.
2. `versao = "main; rm -rf /"` → `ValueError`.
3. Com `MODELOS_FONTE_LOCAL` apontando para a fixture: `executar(montar_comando("v0.0.1", ...))` de um módulo que importa `modelos.teste_fake` → termina sem exceção.
4. Comando que levanta `ZeroDivisionError` no subprocesso → `ExecucaoFalhou` com código 1 e a mensagem contém `ZeroDivisionError` e `Traceback`.
5. Com `MODELOS_GIT_TOKEN=segredo123`: o comando montado não contém `segredo123`; o ambiente passado ao subprocesso contém `GIT_CONFIG_KEY_0` com o token; um erro do subprocesso que imprime `segredo123` vira `***` na `ExecucaoFalhou`.
6. O pacote da fixture não fica importável no ambiente do teste depois da execução (`importlib.util.find_spec("modelos")` é `None`).

## 9. Riscos e perguntas em aberto

- Conflito de dependências entre o pacote dela e o da plataforma (ex.: versões de `pandas`) faz o `uv run --with` falhar. Isso aparece como `ExecucaoFalhou` do modelo dela; o ADR deve dizer quem resolve.
- Primeira execução de cada versão baixa e instala o pacote (segundos a minutos). Depois fica em cache no `UV_CACHE_DIR`; considerar volume para o cache no worker.

## 10. Decisões que exigem ADR

- ADR "Execução de modelos" (P12, P13, P14), antes deste PR e dos PRs 42 e 43:
  - como a versão do pacote é escolhida (tag `pacote_modelos` na versão do modelo no MLflow);
  - mecanismo de instalação (`uv run --with`, subprocesso por modelo);
  - tipo de `conn` passado a `build_features` (proposta: `sqlalchemy.Connection` com usuário `scorer`);
  - objeto `model` passado a `predict` (proposta: `mlflow.pyfunc.load_model(uri)`);
  - saída de `predict` estrita (só `chave`, `data_alvo`, `valor_previsto`).
  Como a assinatura do contrato não muda, mas a semântica dos argumentos é fixada, o ADR precisa da concordância da cientista (`AGENTS.md`: "A assinatura de `build_features`, `predict` e `evaluate` só muda por decisão registrada em ADR").
