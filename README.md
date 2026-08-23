# IRIS Political Insight

## 1. Missão

Consolidar dados políticos oficiais do TSE e da Câmara dos Deputados. Persistir os dados no InterSystems IRIS. Executar busca lexical, busca vetorial e RAG com fontes rastreáveis.

Use este documento como ordem de execução para desenvolvimento, teste e diagnóstico.

## 2. Situação operacional

Arquitetura oficial:

```text
Navegador
    |
    +--> Streamlit :8501
            |
            +--> IRIS Web Gateway :52773/api
                    |
                    +--> %SYS.Python.WSGI
                            |
                            +--> Flask
                                    |
                                    +--> Embedded Python
                                            |
                                            +--> IRISAPP
```

Serviços ativos:

| Serviço | Função | Acesso local |
|---|---|---|
| `iris` | Banco, Web Gateway, WSGI e API Flask | `http://localhost:52773` |
| `ui` | Interface Streamlit | `http://localhost:8501` |

Não existe serviço `api`. Não existe Waitress. O servidor HTTP oficial da API é o IRIS.

## 3. Pré-requisitos

Confirme antes de avançar:

- Docker Desktop ativo;
- Docker Compose disponível;
- acesso à imagem `intersystems/iris-community:latest-cd`;
- portas `1972`, `52773` e `8501` livres;
- Python 3.12 para desenvolvimento local;
- chave OpenAI para ingestão com embeddings, `/search` e `/ask`.

Comandos de inspeção:

```powershell
docker version
docker compose version
python --version
```

Critério: nenhum comando deve falhar.

## 4. Subir o projeto com Docker

### Passo 1 — Preparar o ambiente

Execute na raiz do projeto:

```powershell
Copy-Item .env.example .env
notepad .env
```

Preencha, no mínimo:

```dotenv
LLM_API_KEY=sua-chave
```

A chave é dispensável para `/health` e consultas básicas. Ela é obrigatória para embeddings e respostas RAG.

### Passo 2 — Construir as imagens

Para o primeiro build ou para validar uma alteração estrutural:

```powershell
docker compose build --no-cache
```

Para o ciclo normal:

```powershell
docker compose build
```

Critério: o build deve terminar sem `ERROR`, `FAILURE`, `<SYNTAX>` ou dependências quebradas.

### Passo 3 — Subir os containers

```powershell
docker compose up -d
docker compose ps
```

Resultado esperado:

```text
iris    Up ... (healthy)
ui      Up ...
```

Não prossiga se o IRIS não estiver `healthy`.

### Passo 4 — Inspecionar os logs

```powershell
docker compose logs --tail 100 iris
docker compose logs --tail 100 ui
```

Para acompanhar continuamente:

```powershell
docker compose logs -f iris ui
```

Interrompa o acompanhamento com `Ctrl+C`. Os containers continuarão ativos.

## 5. Testar a aplicação

### Teste 1 — API WSGI

```powershell
Invoke-RestMethod http://localhost:52773/api/health
```

Resultado esperado:

```text
status
------
ok
```

Alternativa com curl real no Windows:

```powershell
curl.exe -i http://localhost:52773/api/health
```

Critério: HTTP `200` e corpo `{"status":"ok"}`.

### Teste 2 — Consulta real ao IRISAPP

```powershell
Invoke-RestMethod http://localhost:52773/api/candidates
```

Resultado mínimo esperado:

```json
{"items":[]}
```

Uma lista vazia é válida antes da ingestão. HTTP `500` não é válido.

### Teste 3 — Interface

Abra:

```text
http://localhost:8501
```

Teste técnico:

```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:8501/_stcore/health
```

Critério: HTTP `200` e corpo `ok`.

### Teste 4 — Ambiente Embedded Python

```powershell
docker compose exec -T iris irispython -c "from importlib.metadata import version; import wsgi_app; print(version('flask')); print(callable(wsgi_app.app))"
docker compose exec -T iris python3 -m pip check
```

Critério: o callable deve ser `True` e o `pip check` deve informar `No broken requirements found`.

## 6. Carregar dados

Execute a ingestão dentro do IRIS. Este é o caminho oficial em container:

```powershell
docker compose exec iris irispython -m app.ingestion.pipeline
```

Aguarde a conclusão. Não interrompa durante gravações no banco.

Depois, confirme:

```powershell
Invoke-RestMethod http://localhost:52773/api/candidates
```

Se a ingestão falhar, capture os logs antes de reiniciar:

```powershell
docker compose logs --tail 200 iris
```

## 7. Rotas HTTP

Base oficial em Docker:

```text
http://localhost:52773/api
```

| Método | Rota | Finalidade |
|---|---|---|
| `GET` | `/health` | Validar WSGI, Flask e acesso SQL ao IRIS |
| `GET` | `/candidates` | Listar candidatos |
| `GET` | `/candidates/{id}` | Consultar um candidato |
| `GET` | `/candidates/{id}/propositions` | Listar proposições do candidato |
| `POST` | `/search` | Executar busca híbrida |
| `POST` | `/ask` | Responder com RAG e fontes |

### Listar e filtrar candidatos

Filtros opcionais: `name`, `party`, `state` e `office`.

```powershell
curl.exe "http://localhost:52773/api/candidates?state=SP&office=DEPUTADO%20FEDERAL"
```

### Consultar candidato

```powershell
curl.exe http://localhost:52773/api/candidates/123
```

### Consultar proposições

```powershell
curl.exe http://localhost:52773/api/candidates/123/propositions
```

### Executar busca híbrida

```powershell
curl.exe -X POST http://localhost:52773/api/search `
  -H "Content-Type: application/json" `
  -d '{"query":"educação pública","candidateId":123,"sourceType":"proposition","topK":8}'
```

Campos:

- `query`: obrigatório; máximo de 2.000 caracteres;
- `candidateId`: opcional; inteiro positivo;
- `sourceType`: opcional;
- `topK`: opcional; valor entre 1 e 50; padrão 8.

### Perguntar ao RAG

```powershell
curl.exe -X POST http://localhost:52773/api/ask `
  -H "Content-Type: application/json" `
  -d '{"question":"Quais propostas tratam de educação?","candidateId":123}'
```

Campos:

- `question`: obrigatório; máximo de 4.000 caracteres;
- `candidateId`: opcional; inteiro positivo.

Respostas de erro previstas:

| HTTP | Significado |
|---|---|
| `400` | Corpo, filtro ou valor inválido |
| `404` | Candidato não encontrado |
| `500` | Falha não tratada; inspecione `WSGI.log` |

## 8. Desenvolvimento Python local

Use o IRIS no Docker. Execute o código Python no Windows. Esse arranjo permite breakpoints, reload e inspeção do processo.

### Passo 1 — Subir somente o IRIS

```powershell
docker compose up -d iris
docker compose ps
```

Critério: `iris` deve estar `healthy`.

### Passo 2 — Criar o ambiente virtual

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

O arquivo `.env` é carregado automaticamente. Confirme estes valores:

```dotenv
IRIS_HOST=localhost
IRIS_PORT=1972
IRIS_NAMESPACE=IRISAPP
IRIS_USERNAME=_SYSTEM
IRIS_PASSWORD=SYS
```

### Missão A — Executar somente a UI local

Mantenha a API no WSGI nativo do IRIS:

```powershell
$env:API_BASE_URL="http://localhost:52773/api"
python -m streamlit run app/ui/streamlit_app.py --server.port 8501
```

Use este modo para depurar a interface sem alterar o runtime oficial da API.

### Missão B — Executar Flask local com reload

Pare a UI do Compose para liberar a porta 8501, se necessário:

```powershell
docker compose stop ui
```

Suba o Flask local:

```powershell
python -m flask --app app.api.app:create_app --debug run --host 0.0.0.0 --port 8000
```

Base local neste modo:

```text
http://localhost:8000
```

As rotas ficam sem o prefixo `/api` porque o prefixo pertence ao mount point do IRIS:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/candidates
```

Não use o servidor Flask de desenvolvimento em produção.

### Missão C — Executar UI e Flask locais

Terminal 1:

```powershell
python -m flask --app app.api.app:create_app --debug run --host 0.0.0.0 --port 8000
```

Terminal 2:

```powershell
.\.venv\Scripts\Activate.ps1
$env:API_BASE_URL="http://localhost:8000"
python -m streamlit run app/ui/streamlit_app.py --server.port 8501
```

Fluxo resultante:

```text
Streamlit local :8501 -> Flask local :8000 -> TCP 1972 -> IRIS no Docker
```

## 9. Debug com breakpoint remoto

### Passo 1 — Iniciar o processo e aguardar o depurador

```powershell
python -m debugpy --listen 5678 --wait-for-client `
  -m flask --app app.api.app:create_app run `
  --no-reload --host 0.0.0.0 --port 8000
```

O processo ficará parado até o IDE conectar.

### Passo 2 — Conectar o IDE

Configure `Python: Attach` com:

```text
host: localhost
port: 5678
```

### Passo 3 — Posicionar o breakpoint

Posicione o breakpoint em `app/api/app.py`, `app/repositories/` ou `app/database/connection.py`. Faça uma requisição para `http://localhost:8000`.

Critério: o depurador deve interromper na linha marcada.

## 10. Testes automatizados

Ative o ambiente virtual:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Testes unitários

```powershell
pytest -m unit
```

Não exigem IRIS nem rede externa.

### Testes de integração com IRIS

Suba o IRIS e execute:

```powershell
docker compose up -d iris
$env:RUN_IRIS_TESTS="1"
pytest -m integration
Remove-Item Env:RUN_IRIS_TESTS
```

Esses testes gravam dados temporários no namespace `IRISAPP` e executam operações de repositório e busca.

### Smoke tests dos serviços

Suba os dois serviços e execute:

```powershell
docker compose up -d
$env:RUN_SMOKE_TESTS="1"
pytest -m smoke
Remove-Item Env:RUN_SMOKE_TESTS
```

### Qualidade estática

```powershell
ruff check app tests wsgi_app.py
mypy app wsgi_app.py
```

Ordem de aceite:

1. Execute testes unitários.
2. Execute análise estática.
3. Execute testes de integração.
4. Execute smoke tests.
5. Não entregue código com falha conhecida.

## 11. Parar e limpar

Parar sem remover containers:

```powershell
docker compose stop
```

Remover containers e preservar dados:

```powershell
docker compose down
```

Remover containers e apagar o volume IRIS:

```powershell
docker compose down -v
```

> ATENÇÃO: `docker compose down -v` apaga os dados persistidos pelo projeto. Use somente quando a perda for intencional.

## 12. Diagnóstico

### API retorna HTTP 500

Execute:

```powershell
docker compose exec -T iris sh -lc "tail -100 /usr/irissys/mgr/WSGI.log"
docker compose logs --tail 200 iris
```

### API retorna HTTP 401 ou 403

Verifique a Web Application `/api`, a autenticação e os papéis associados. Para este MVP/dev, a configuração esperada é:

```text
AutheEnabled = 64
MatchRoles   = :%All
```

### Alteração Python não aparece no WSGI

Reconstrua e recrie o IRIS:

```powershell
docker compose build iris
docker compose up -d --force-recreate iris
```

O IRIS mantém módulos Python em memória. Reinicie o serviço após alterar código carregado pelo WSGI.

### Flask local não conecta ao IRIS

Confirme:

```powershell
docker compose ps iris
Test-NetConnection localhost -Port 1972
```

Revise `IRIS_HOST`, `IRIS_PORT`, `IRIS_NAMESPACE`, `IRIS_USERNAME` e `IRIS_PASSWORD` no `.env`.

### UI não acessa a API

No Docker, use:

```text
API_BASE_URL=http://iris:52773/api
```

No host, use:

```text
API_BASE_URL=http://localhost:52773/api
```

No modo Flask local, use:

```text
API_BASE_URL=http://localhost:8000
```

## 13. WSGI e segurança

Configuração instalada automaticamente pelo IPM:

```text
URL               = /api
NameSpace         = IRISAPP
DispatchClass     = %SYS.Python.WSGI
WSGIAppLocation   = /usr/irissys/lib/iris-political-insight/
WSGIAppName       = wsgi_app
WSGICallable      = app
```

As dependências da API são instaladas em `/usr/irissys/mgr/python`, diretório acessível ao Embedded Python do IRIS.

> SEGURANÇA: o acesso não autenticado recebe `%All` somente neste MVP de desenvolvimento. Antes de publicar, habilite autenticação e substitua `%All` por papéis de privilégio mínimo.

Credenciais padrão locais:

```text
usuário: _SYSTEM
senha:   SYS
```

Troque essas credenciais fora do ambiente local.

## 14. Documentação

- [Especificação do produto](docs/SPEC%20%E2%80%94%20IRIS%20Political%20Insight.md)
- [Plano de implementação](docs/IMPLEMENTATION_PLAN.md)
- [Tecnologias e bibliotecas](docs/IMPLEMENTACAO_TECNICA_TECNOLOGIAS_E_LIBS.md)
- [Ingestão TSE, Câmara e IRIS](docs/IMPLEMENTACAO_INGESTAO_TSE_CAMARA_IRIS.md)
- [Classes IRIS e mapeamento](docs/CLASSES_IRIS_E_MAPEAMENTO_INGESTAO_ATUAL.md)
- [Migração para WSGI nativo](docs/MIGRACAO_FLASK_WAITRESS_PARA_IRIS_WSGI.md)
- [WSGI no InterSystems IRIS](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=AWSGI)
- [Embedded Python](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=GEPYTHON)
- [Instalação de pacotes Python](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=GEPYTHON_loadlib)

## 15. Comandos rápidos

```powershell
# Subir
docker compose up --build -d

# Estado
docker compose ps

# Health
Invoke-RestMethod http://localhost:52773/api/health

# Logs
docker compose logs --tail 100 iris ui

# Testes unitários
pytest -m unit

# Parar preservando dados
docker compose down
```

No Linux ou macOS, troque `Copy-Item` por `cp` e ative o ambiente com:

```bash
source .venv/bin/activate
```
