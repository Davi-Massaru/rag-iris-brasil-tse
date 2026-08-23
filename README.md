# IRIS Political Insight

Aplicação Python + InterSystems IRIS para consolidar candidaturas do TSE, histórico e proposições da Câmara dos Deputados, indexar conteúdo político e responder perguntas com busca híbrida e RAG rastreável.

O arquivo [SPEC — IRIS Political Insight.md](docs/SPEC%20%E2%80%94%20IRIS%20Political%20Insight.md) define o produto. Os demais documentos em `docs/` registram o desenho técnico e o mapeamento das fontes oficiais.

## Componentes

- InterSystems IRIS: oito classes persistentes e vetores de 1536 dimensões;
- ingestão: CKAN/TSE, arquivos ZIP/CSV/PDF e API da Câmara;
- matching: resolução conservadora de identidade TSE–Câmara;
- retrieval: busca lexical + vetorial combinadas por Reciprocal Rank Fusion;
- RAG: embeddings e Responses API da OpenAI, sempre com fontes;
- API Flask hospedada pelo WSGI nativo do IRIS e interface Streamlit.

Arquitetura de execução:

```text
Streamlit -> IRIS Web Gateway -> %SYS.Python.WSGI -> Flask -> Embedded Python -> IRISAPP
```

## Executar com Docker

Pré-requisitos: Docker com acesso à imagem `intersystems/iris-community:latest-cd` e uma chave da OpenAI para embeddings/RAG.

```bash
cp .env.example .env
# preencha LLM_API_KEY no .env
docker compose up --build -d
docker compose exec iris irispython -m app.ingestion.pipeline
```

Serviços:

- API WSGI: `http://localhost:52773/api`;
- Streamlit: `http://localhost:8501`;
- portal IRIS: `http://localhost:52773/csp/sys/UtilHome.csp`;
- SuperServer IRIS: `localhost:1972`.

As credenciais locais padrão são `_SYSTEM` / `SYS`. Troque-as fora de um ambiente de desenvolvimento.

## API

```text
GET  /api/candidates?name=&party=&state=&office=
GET  /api/candidates/{id}
GET  /api/candidates/{id}/propositions
POST /api/search
POST /api/ask
GET  /api/health
```

Exemplo:

```bash
curl -X POST http://localhost:52773/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Quais propostas tratam de educação?","candidateId":123}'
```

## Desenvolvimento local

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt
copy .env.example .env
pytest -m unit
ruff check app tests
```

Com o IRIS ativo, o servidor HTTP da API é o próprio IRIS. Para desenvolvimento dos componentes externos, execute `python -m app.ingestion.pipeline` e `streamlit run app/ui/streamlit_app.py` em terminais separados.

Para validar a integração real no PowerShell:

```powershell
$env:RUN_IRIS_TESTS="1"; pytest -m integration
$env:RUN_SMOKE_TESTS="1"; pytest -m smoke
```

## WSGI nativo do IRIS

O build instala as dependências Flask em `/usr/irissys/mgr/python` e o IPM cria a Web Application `/api` no namespace `IRISAPP` com:

```text
WSGIAppName     = wsgi_app
WSGICallable    = app
DispatchClass   = %SYS.Python.WSGI
```

O acesso não autenticado recebe `%All` somente para este MVP de desenvolvimento. Essa configuração é intencional para simplificar a demonstração, mas não deve ser usada em produção; antes de publicar o serviço, exija autenticação e aplique privilégios mínimos.

## Segurança e proveniência

O projeto aceita somente hosts HTTPS oficiais configurados para TSE e Câmara, usa SQL parametrizado, limita caminhos extraídos de ZIP e preserva URL, horário de coleta e hash das fontes. A resposta RAG não deve inventar fatos quando não houver evidência indexada.
