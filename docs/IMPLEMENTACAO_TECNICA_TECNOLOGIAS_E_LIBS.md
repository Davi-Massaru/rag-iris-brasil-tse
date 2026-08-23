# Implementação técnica — tecnologias e bibliotecas Python

## 1. Objetivo

Definir a stack do MVP antes da implementação Python.

Este documento considera:

- as oito classes `%Persistent` existentes;
- os contratos TSE e Câmara já documentados;
- ingestão, Vector Search, Hybrid Search, RAG, API e Streamlit;
- baixo acoplamento;
- reutilização de bibliotecas maduras;
- calistenia de objetos aplicada sem criar classes artificiais.

Não altera o modelo persistente nem adiciona funcionalidade futura.

## 2. Estado atual auditado

Existem:

- oito classes `IRISPolitical.Model.*`;
- Dockerfile, Docker Compose, ZPM e namespace `IRISAPP`;
- documentação funcional, persistente e de ingestão;
- `requirements.txt` somente com comentários de NumPy/Pandas.

Não existem atualmente:

- pacote Python `app/`;
- API Python;
- clients TSE/Câmara;
- repositories Python;
- pipeline RAG;
- testes Python.

Consequência: criar somente componentes de domínio exigidos. Não duplicar recursos já fornecidos por IRIS ou bibliotecas.

## 3. Stack aprovada

| Responsabilidade | Tecnologia/lib | Decisão |
|---|---|---|
| Runtime | Python 3.11+ | Síncrono no MVP; compatível com Flask e SDK OpenAI atuais |
| Persistência | `intersystems-irispython` | Driver oficial DB-API; SQL parametrizado e transações explícitas |
| Configuração | `pydantic-settings` | `.env`, tipos, listas, inteiros, URLs e validações |
| Contratos externos/API | `pydantic` | Validação somente nas bordas; campos extras aceitos quando o contrato permitir |
| HTTP TSE/Câmara | `requests` | `Session`, streaming, timeouts, TLS e JSON |
| Retry | `tenacity` | Tentativas, backoff, jitter e exceções permitidas pelo contrato |
| CSV/ZIP/hash | biblioteca padrão | `csv`, `zipfile`, `hashlib`, `pathlib`; nenhuma lib adicional |
| PDF | `pypdf` | Extração por página mantendo ordem |
| Tokenização | `tiktoken` | Chunk alvo 700, overlap 100 e contagem reproduzível |
| Embeddings/LLM | `openai` | SDK oficial; embeddings e Responses API |
| API REST | `Flask` | API pequena, síncrona, cinco endpoints e baixo boilerplate |
| Servidor WSGI | `waitress` | Execução fora do servidor de desenvolvimento; Windows/Linux |
| UI | `streamlit` | Obrigatório para demonstração do MVP |
| Testes | `pytest` | Fixtures, parametrização, marcadores unit/integration/smoke |
| Cobertura | `pytest-cov` | Medição por pacote e relatório CI |
| HTTP em testes | `responses` | Simular somente fronteiras HTTP; payloads vêm de fixtures versionadas |
| Qualidade | `ruff` | Formatação, lint, imports e complexidade |
| Tipagem | `mypy` | Verificação gradual das fronteiras e DTOs |

Referências:

- [InterSystems Native Python SDK e DB-API](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls/framework-api/scbi/DocBook.UI.Page.cls?KEY=BPYNAT_install)
- [Flask](https://flask.palletsprojects.com/en/stable/)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [Requests](https://requests.readthedocs.io/en/latest/)
- [Tenacity](https://tenacity.readthedocs.io/en/stable/)
- [pypdf](https://pypdf.readthedocs.io/)
- [OpenAI Python SDK](https://github.com/openai/openai-python)
- [Streamlit](https://docs.streamlit.io/get-started/installation)
- [pytest](https://docs.pytest.org/en/stable/getting-started.html)

## 4. Dependências pip propostas

### 4.1 Runtime — `requirements.txt`

Baseline para validação no contêiner antes de fixar versões exatas:

```text
Flask>=3.1,<4
waitress>=3,<4
pydantic>=2,<3
pydantic-settings>=2,<3
requests>=2,<3
tenacity>=9,<10
intersystems-irispython
pypdf>=5,<7
openai>=2,<4
tiktoken>=0.9,<1
streamlit>=1,<2
```

Regras:

- validar a versão de `intersystems-irispython` contra a imagem IRIS escolhida;
- gerar pins exatos somente após build e testes integrados;
- não declarar dependência transitiva diretamente sem import no projeto;
- remover comentários antigos de NumPy/Pandas quando `requirements.txt` for efetivamente alterado.

### 4.2 Desenvolvimento — `requirements-dev.txt`

```text
pytest>=9,<10
pytest-cov>=7,<8
responses>=0.25,<1
ruff>=0.12,<1
mypy>=1.15,<2
```

`requirements-dev.txt` deve incluir `-r requirements.txt` na primeira linha.

### 4.3 Dependências não selecionadas

| Lib/framework | Motivo |
|---|---|
| FastAPI | Flask atende cinco endpoints sem impor stack ASGI ou duplicar validação |
| SQLAlchemy / `sqlalchemy-iris` | As classes IRIS já representam o modelo; DB-API direto preserva SQL e transações especificadas |
| LangChain / LlamaIndex | Pipeline RAG é pequeno e explícito; frameworks esconderiam retrieval, prompt e proveniência |
| Pandas | CSV TSE deve ser processado em streaming com `csv.DictReader` |
| NumPy | Vetores são persistidos como `list[float]`; IRIS calcula similaridade |
| aiohttp | MVP é síncrono; não há requisito de alta concorrência |
| Celery/Redis | Filas e processamento distribuído estão fora do MVP |
| RapidFuzz | Matching documentado usa igualdade normalizada e pesos determinísticos |
| ORM paralelo | Criaria segundo modelo além das classes `%Persistent` existentes |

## 5. Uso de cada biblioteca

### 5.1 `pydantic-settings`

Responsabilidade exclusiva: `app/config/settings.py`.

Validar:

- variáveis obrigatórias;
- inteiros positivos;
- listas de UFs/cargos;
- `CHUNK_OVERLAP_TOKENS < CHUNK_SIZE_TOKENS`;
- `EMBEDDING_DIMENSION == 1536`;
- URLs HTTPS oficiais.

Não criar parser `.env` próprio.

### 5.2 `intersystems-irispython`

Responsabilidade exclusiva: conexão DB-API com IRIS.

Usar:

```python
import iris

connection = iris.dbapi.connect(...)
```

Regras:

- queries parametrizadas;
- context manager para conexão/cursor/transação;
- HTTP e parsing antes de `BEGIN`;
- `COMMIT` somente na unidade transacional;
- `ROLLBACK` em qualquer erro;
- nenhum ORM.

### 5.3 `requests` + `tenacity`

Um `requests.Session` compartilhado por client.

Clients concretos:

- `TseClient`;
- `CamaraClient`.

Tenacity repete somente:

- timeout/conexão;
- HTTP 429;
- HTTP 500, 502, 503 e 504.

Não repetir HTTP 400, contrato inválido ou validação de domínio.

Download TSE usa `stream=True`, hash incremental, HTTPS, validação de redirecionamento e ZIP seguro.

### 5.4 `pypdf`

Usar `PdfReader` sobre stream/arquivo temporário.

Saída:

- texto por página;
- texto consolidado em ordem;
- página inicial/final nos metadados do chunk quando disponível.

Não incluir OCR no MVP.

### 5.5 `tiktoken`

Responsabilidade exclusiva: tokenização de chunk e contagem.

Parâmetros:

```text
target = 700
overlap = 100
content max = 32000 caracteres
```

O tokenizer é criado uma vez por processo e injetado no chunker.

### 5.6 `openai`

Um client por processo, criado no composition root.

Usar:

- endpoint de embeddings para documentos e consultas;
- mesmo modelo configurado nos dois fluxos;
- Responses API para geração;
- timeout e retries configurados explicitamente;
- validação de 1536 posições antes da persistência.

Não criar cliente HTTP próprio para OpenAI.

### 5.7 Flask

Usar application factory:

```python
def create_app(settings: Settings) -> Flask:
    ...
```

Rotas finas:

```text
GET  /candidates
GET  /candidates/<id>
GET  /candidates/<id>/propositions
POST /search
POST /ask
```

Cada rota:

1. valida entrada com Pydantic;
2. chama um caso de uso existente;
3. serializa resposta;
4. traduz exceção conhecida para HTTP.

Não colocar SQL, retrieval, prompt ou chamada LLM na rota.

Executar com Waitress no Docker. `flask run` somente em desenvolvimento.

### 5.8 Streamlit

Streamlit será cliente da API Flask.

Isso evita duplicar:

- conexão IRIS;
- repositories;
- Hybrid Search;
- RAG;
- validação de pergunta.

A UI somente seleciona candidato, envia pergunta e apresenta resposta/evidências.

## 6. Arquitetura Python mínima

```text
External Source
  -> Requests client
  -> Pydantic external contract
  -> mapper
  -> immutable internal DTO
  -> repository DB-API
  -> existing IRIS %Persistent

HTTP request
  -> Flask route
  -> use case
  -> repository/retrieval/RAG
  -> response DTO

Streamlit
  -> Flask API
```

Componentes permitidos:

- DTO externo por payload consumido;
- DTO interno por escrita/leitura relevante;
- repository por classe persistente existente;
- client por fonte externa;
- serviço somente quando coordena regra real;
- protocolo somente quando há pelo menos duas implementações ou fronteira de teste necessária.

Componentes proibidos:

- repository genérico;
- factory genérica de repositories;
- `BaseService`;
- wrapper de `requests` sem regra de domínio;
- ORM duplicando `%Persistent`;
- classe para função pura simples;
- interface sem consumidor alternativo;
- módulo `utils.py` genérico.

## 7. Calistenia de objetos adaptada

Aplicar como guia, não como dogma.

### Regras adotadas

1. Um nível de indentação por método sempre que a extração melhorar o nome da regra.
2. Retorno antecipado; evitar `else` após `return`/`raise`.
3. Métodos pequenos, uma responsabilidade e nomes de domínio.
4. Estado mutável encapsulado; DTOs externos/internos imutáveis quando possível.
5. Coleções recebidas como `Sequence` e expostas como `tuple` quando não devem mudar.
6. Primitivos críticos validados: `TseId`, `CamaraId`, status, URL oficial, hash e dimensão vetorial.
7. Dependências recebidas no construtor; nenhum singleton global mutável.
8. Uma classe por motivo de mudança, não uma classe por operação.
9. Sem abreviações ambíguas.
10. Limites entre client, mapper, repository e use case testados separadamente.

### Regras não aplicadas literalmente

- não envolver todo `str`/`int` em value object;
- não limitar toda classe a dois atributos;
- não proibir propriedades necessárias aos DTOs documentados;
- não quebrar método pequeno apenas para cumprir contagem de linhas.

Objetivo: reduzir complexidade. Nunca aumentar quantidade de arquivos para satisfazer a técnica.

## 8. Estratégia de testes

### Unitários

Sem IRIS/rede:

- settings;
- parser Latin-1/CSV;
- ZIP seguro;
- contratos Pydantic;
- mappers;
- matching;
- chunking/hash;
- RRF;
- prompt;
- validação Flask.

### Contrato HTTP

`responses` intercepta somente Requests. Respostas reais reduzidas ficam em `tests/fixtures/`.

Cobrir:

- `dados`/`links`;
- paginação `rel=next`;
- 400 sem retry;
- 429/5xx com retry;
- timeout;
- CKAN `success=false`;
- recurso inativo.

### Integração IRIS

Contêiner real:

- compilação das oito classes;
- schema/colunas/índices;
- insert/update/upsert;
- idempotência;
- streams;
- transação/rollback;
- vetor 1536;
- lexical/vector/hybrid.

### API/UI

- Flask `test_client` para os cinco endpoints;
- caso sem evidência;
- fontes preservadas;
- Streamlit: smoke de inicialização e teste dos adaptadores HTTP, sem testar widgets internos.

### Comandos esperados

```bash
ruff check app tests
ruff format --check app tests
mypy app
pytest -m unit
pytest -m integration
pytest -m smoke
pytest --cov=app --cov-report=term-missing
```

## 9. Ordem de adoção das dependências

Adicionar biblioteca somente na etapa que a utiliza:

1. `pydantic` + `pydantic-settings` — configuração/contratos;
2. `intersystems-irispython` — conexão/repositories;
3. `requests` + `tenacity` — clients oficiais;
4. `pypdf` — proposta de governo;
5. `tiktoken` — chunking;
6. `openai` — embedding/RAG;
7. `Flask` + `waitress` — API;
8. `streamlit` — UI;
9. dependências dev — desde o primeiro módulo testável.

Após cada adição:

```text
instalar
-> importar
-> testar unidade
-> testar integração necessária
-> atualizar requirements
-> validar Docker
```

## 10. Critérios de aprovação da stack

- nenhuma classe `%Persistent` nova;
- nenhuma duplicação ORM;
- Flask contém somente transporte HTTP;
- Streamlit consome API, não banco;
- bibliotecas assumem configuração, HTTP, retry, PDF, tokenização e LLM;
- Python mantém somente regras específicas TSE/Câmara/IRIS/RRF;
- `requirements.txt` contém apenas imports de runtime diretos;
- pins exatos validados dentro da imagem Docker;
- testes confirmam idempotência, rollback, retry, proveniência e neutralidade.
