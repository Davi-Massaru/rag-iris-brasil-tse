# IMPLEMENTATION_PLAN — IRIS Political Insight

## 1. Objetivo

Este documento define a ordem de implementação do **IRIS Political Insight** considerando a estrutura atual do repositório:

```text
intersystems-iris-dev-template/
│
├── .devcontainer/
├── .github/
├── .vscode/
│
├── app/
│   ├── config/
│   ├── database/
│   ├── ingestion/
│   │   ├── tse/
│   │   ├── camara/
│   │   ├── matching/
│   │   └── chunking/
│   ├── repositories/
│   ├── embeddings/
│   ├── retrieval/
│   ├── rag/
│   ├── api/
│   └── ui/
│
├── docs/
│   ├── SPEC.md
│   ├── IMPLEMENTATION_PLAN.md
│   ├── IMPLEMENTACAO_INGESTAO_TSE_CAMARA_IRIS.md
│   └── CLASSES_IRIS_E_MAPEAMENTO_INGESTAO_ATUAL.md
│
├── iris/
│   └── IRISPolitical/
│       └── Model/
│           ├── Candidate.cls
│           ├── PoliticalHistory.cls
│           ├── Proposition.cls
│           ├── PropositionAuthor.cls
│           ├── PropositionTopic.cls
│           ├── ProposalDocument.cls
│           ├── PoliticalChunk.cls
│           └── IngestionRun.cls
│
├── tests/
│
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

O objetivo da implementação é entregar uma aplicação capaz de:

1. ingerir candidatos do TSE;
2. persistir os candidatos no InterSystems IRIS;
3. relacionar candidatos com deputados da Câmara quando houver correspondência confiável;
4. ingerir histórico parlamentar, mandatos, proposições, autores e temas;
5. ingerir propostas de governo do TSE;
6. criar `PoliticalChunk` com proveniência;
7. gerar e persistir embeddings;
8. executar busca lexical;
9. executar busca vetorial;
10. combinar resultados com Reciprocal Rank Fusion — RRF;
11. fornecer as evidências recuperadas a um LLM;
12. responder somente com base nas evidências recuperadas;
13. apresentar as fontes oficiais utilizadas;
14. disponibilizar a demonstração em Streamlit.

---

# 2. Documentos normativos do projeto

Antes de implementar qualquer tarefa, considerar esta ordem de autoridade:

```text
SPEC.md
    ↓
contrato funcional

CLASSES_IRIS_E_MAPEAMENTO_INGESTAO_ATUAL.md
    ↓
modelo persistente atual

IMPLEMENTACAO_INGESTAO_TSE_CAMARA_IRIS.md
    ↓
detalhes técnicos da ingestão

IMPLEMENTATION_PLAN.md
    ↓
ordem de execução
```

Quando houver divergência:

1. não criar uma nova regra por conta própria;
2. preservar as classes persistentes atuais;
3. registrar a divergência;
4. usar o contrato mais específico para a responsabilidade alterada.

---

# 3. Regra arquitetural principal

A aplicação deve preservar a separação:

```text
Fonte externa
     │
     ▼
Client
     │
     ▼
External DTO
     │
     ▼
Parser / Mapper
     │
     ▼
Internal DTO
     │
     ▼
Repository
     │
     ▼
%Persistent
     │
     ▼
InterSystems IRIS
```

As classes `.cls` não executam:

- HTTP;
- download de ZIP;
- leitura de CSV;
- extração de PDF;
- matching;
- chunking;
- embeddings;
- chamadas de LLM.

Essas responsabilidades pertencem à aplicação Python.

Os repositories não executam HTTP.

Os clients HTTP não acessam banco de dados.

---

# 4. Modelo persistente

As classes persistentes são:

```text
IRISPolitical.Model.Candidate
IRISPolitical.Model.PoliticalHistory
IRISPolitical.Model.Proposition
IRISPolitical.Model.PropositionAuthor
IRISPolitical.Model.PropositionTopic
IRISPolitical.Model.ProposalDocument
IRISPolitical.Model.PoliticalChunk
IRISPolitical.Model.IngestionRun
```

Relacionamentos:

```text
Candidate
│
├── PoliticalHistory
│
├── Proposition
│   ├── PropositionAuthor
│   └── PropositionTopic
│
├── ProposalDocument
│
└── PoliticalChunk

IngestionRun
```

Identificadores externos devem permanecer separados do `%ID` interno do IRIS.

Principais identidades:

```text
TSE SQ_CANDIDATO
→ Candidate.TseId

Câmara id deputado
→ Candidate.CamaraDeputyId

Câmara id proposição
→ Proposition.CamaraId

TSE / CKAN resource id
→ ProposalDocument.SourceResourceId

SHA-256 do documento
→ ProposalDocument.DocumentHash
```

---

# 5. Ordem geral de implementação

A implementação deve seguir esta sequência:

```text
01. configuração
02. infraestrutura IRIS
03. conexão e transação
04. repositories
05. IngestionRun
06. cliente TSE / CKAN
07. parser e mapper TSE
08. ingestão Candidate
09. propostas de governo
10. cliente Câmara
11. matching TSE × Câmara
12. histórico parlamentar
13. proposições
14. autores e temas
15. PoliticalChunk
16. embeddings
17. pipeline completo de ingestão
18. busca lexical
19. busca vetorial
20. RRF
21. Hybrid Search
22. RAG
23. API
24. Streamlit
25. testes integrados
26. Docker e execução reproduzível
```

Uma etapa só deve ser considerada concluída quando seus testes correspondentes estiverem funcionando.

---

# 6. Etapa 1 — Configuração

## Arquivos

```text
app/config/settings.py
.env.example
requirements.txt
```

## Implementar

Centralizar:

```text
IRIS_HOST
IRIS_PORT
IRIS_NAMESPACE
IRIS_USERNAME
IRIS_PASSWORD
IRIS_SQL_SCHEMA

TSE_CKAN_BASE_URL
TSE_DATASET_ID
TSE_PORTAL_URL

CAMARA_BASE_URL
CAMARA_MATCH_START_DATE
CAMARA_PAGE_SIZE

INGEST_ELECTION_YEAR
INGEST_STATES
INGEST_OFFICES

HTTP_CONNECT_TIMEOUT_SECONDS
HTTP_READ_TIMEOUT_SECONDS
HTTP_MAX_RETRIES

CHUNK_SIZE_TOKENS
CHUNK_OVERLAP_TOKENS

EMBEDDING_PROVIDER
EMBEDDING_MODEL
EMBEDDING_DIMENSION

LLM_PROVIDER
LLM_API_KEY
LLM_MODEL
```

Valores iniciais de referência:

```env
IRIS_SQL_SCHEMA=IRISPolitical_Model

TSE_CKAN_BASE_URL=https://dadosabertos.tse.jus.br/api/3/action
TSE_DATASET_ID=candidatos-2026

CAMARA_BASE_URL=https://dadosabertos.camara.leg.br/api/v2
CAMARA_MATCH_START_DATE=2000-01-01
CAMARA_PAGE_SIZE=100

INGEST_ELECTION_YEAR=2026
INGEST_STATES=SP
INGEST_OFFICES=DEPUTADO FEDERAL,GOVERNADOR

HTTP_CONNECT_TIMEOUT_SECONDS=10
HTTP_READ_TIMEOUT_SECONDS=60
HTTP_MAX_RETRIES=4

CHUNK_SIZE_TOKENS=700
CHUNK_OVERLAP_TOKENS=100

EMBEDDING_DIMENSION=1536
```

## Testar

- leitura de `.env`;
- parsing de listas;
- parsing de inteiros;
- configuração obrigatória ausente;
- dimensão do embedding inválida.

## Concluído quando

A aplicação puder carregar toda a configuração sem valores hardcoded espalhados pelo código.

---

# 7. Etapa 2 — Infraestrutura IRIS

## Diretório

```text
iris/IRISPolitical/Model/
```

## Validar

Compilar:

```text
Candidate.cls
PoliticalHistory.cls
Proposition.cls
PropositionAuthor.cls
PropositionTopic.cls
ProposalDocument.cls
PoliticalChunk.cls
IngestionRun.cls
```

Confirmar no IRIS:

- schema SQL;
- tabelas;
- colunas;
- relacionamentos;
- índices;
- streams;
- coluna vetorial;
- dimensão do vetor.

## Regra

Não modificar as classes apenas para adaptar o Python sem primeiro verificar o contrato persistente atual.

## Concluído quando

As oito classes compilarem e puderem ser consultadas via SQL.

---

# 8. Etapa 3 — Conexão e transação

## Arquivos

```text
app/database/iris_connection.py
app/database/transaction.py
```

## Implementar

`iris_connection.py`:

- criação de conexão;
- fechamento;
- cursor;
- configuração a partir de `settings.py`.

`transaction.py`:

- `BEGIN`;
- `COMMIT`;
- `ROLLBACK`;
- context manager transacional.

## Regra

HTTP e processamento de arquivos ficam fora da transação.

Fluxo:

```text
obter
 ↓
validar
 ↓
normalizar
 ↓
BEGIN
 ↓
persistir
 ↓
COMMIT
```

Em falha:

```text
ROLLBACK
```

## Unidades transacionais

```text
Candidate
→ lote de até 500

dados Câmara
→ um candidato

Proposition
→ proposição + autores + temas

ProposalDocument
→ documento + chunks

embedding
→ lote de chunks
```

## Concluído quando

For possível persistir e reverter uma transação de teste no IRIS.

---

# 9. Etapa 4 — Repositories

## Diretório

```text
app/repositories/
```

Criar:

```text
candidate_repository.py
political_history_repository.py
proposition_repository.py
proposition_author_repository.py
proposition_topic_repository.py
proposal_document_repository.py
political_chunk_repository.py
ingestion_run_repository.py
```

## CandidateRepository

Operações mínimas:

```text
find_by_id
find_by_tse_id
insert
update
upsert
save_match
list
list_for_camara_matching
```

Chave funcional:

```text
TseId
```

## PoliticalHistoryRepository

Garantir idempotência por:

```text
Candidate + ExternalId
```

## PropositionRepository

Garantir idempotência por:

```text
CamaraId
```

Uma proposição persistida não pode trocar silenciosamente de candidato durante reingestão.

## PropositionAuthorRepository

Persistir autores relacionados à proposição usando a identidade definida no modelo atual.

## PropositionTopicRepository

Evitar duplicidade por:

```text
Proposition + Name
```

## ProposalDocumentRepository

Evitar duplicidade por:

```text
Candidate + DocumentHash
```

## PoliticalChunkRepository

Operações mínimas:

```text
insert
update
upsert
find_by_source
list_without_embedding
update_embedding
keyword_search
vector_search
```

## IngestionRunRepository

Operações mínimas:

```text
start
increment_processed
increment_success
increment_failed
finish_success
finish_partial
finish_failed
```

## Concluído quando

Fixtures puderem ser persistidas duas vezes sem duplicação.

---

# 10. Etapa 5 — IngestionRun

Toda ingestão deve registrar execução técnica.

Fontes lógicas:

```text
TSE_CANDIDATES
TSE_PROPOSALS
CAMARA
```

Ao iniciar:

```text
Source
StartedAt
Status = RUNNING
contadores = 0
ParametersJson
```

Ao finalizar:

```text
SUCCESS
PARTIAL
FAILED
```

Regras:

```text
SUCCESS
→ nenhum item falhou

PARTIAL
→ houve dados persistidos e também falhas

FAILED
→ fonte indisponível ou nenhuma unidade pôde ser processada
```

`SourceHash`:

```text
TSE_CANDIDATES
→ SHA-256 do ZIP

TSE_PROPOSALS
→ SHA-256 do ZIP

CAMARA
→ NULL
```

Nenhuma execução finalizada deve permanecer como `RUNNING`.

---

# 11. Etapa 6 — Cliente TSE / CKAN

## Arquivos

```text
app/ingestion/tse/client.py
app/ingestion/tse/contracts.py
```

## Implementar

Consultar:

```http
GET /package_show?id=candidatos-2026
```

Validar:

```text
HTTP 200
success == true
result.name == TSE_DATASET_ID
resources é lista
resource.state == active
URL usa HTTPS
domínio pertence ao TSE
```

Não selecionar recurso por índice do array.

Selecionar candidatos por metadados do recurso.

Selecionar propostas de governo por metadados do recurso.

---

# 12. Etapa 7 — Download e parser TSE

## Arquivos

```text
app/ingestion/tse/parser.py
app/ingestion/tse/mapper.py
```

## Download

Implementar:

- streaming;
- SHA-256;
- validação ZIP;
- bloqueio de path traversal;
- validação do arquivo esperado.

## CSV

Formato:

```text
encoding = latin-1
delimiter = ;
quotechar = "
```

Consumir:

```text
ANO_ELEICAO
SG_UF
CD_CARGO
DS_CARGO
SQ_CANDIDATO
NR_CANDIDATO
NM_CANDIDATO
NM_URNA_CANDIDATO
NR_PARTIDO
SG_PARTIDO
```

Normalizar:

```text
#NULO           → None
#NE             → None
NÃO DIVULGÁVEL  → None
-1              → None quando numérico especial
-3              → None quando numérico especial
-4              → None quando numérico especial
```

`SQ_CANDIDATO` permanece `str`.

Não persistir dados pessoais fora do domínio.

---

# 13. Etapa 8 — Mapper e ingestão Candidate

## DTO externo

Implementar contrato equivalente a:

```python
@dataclass(frozen=True)
class TseCandidateRaw:
    election_year: int
    state: str
    office_code: int | None
    office_name: str
    candidate_sequence: str
    candidate_number: int | None
    candidate_name: str
    ballot_name: str | None
    party_number: int | None
    party_abbreviation: str | None
```

## Mapeamento

```text
SQ_CANDIDATO
→ Candidate.TseId

NM_CANDIDATO
→ Candidate.Name

NM_URNA_CANDIDATO
→ Candidate.BallotName

SG_PARTIDO
→ Candidate.Party

NR_PARTIDO
→ Candidate.PartyNumber

DS_CARGO
→ Candidate.Office

SG_UF
→ Candidate.State

NR_CANDIDATO
→ Candidate.CandidateNumber
```

## Persistência

```text
TseCandidateRaw
      ↓
mapper
      ↓
internal DTO
      ↓
CandidateRepository
      ↓
find_by_tse_id
      ↓
INSERT / UPDATE
```

Datas:

```text
CreatedAt
→ somente INSERT

UpdatedAt
→ INSERT e UPDATE

SourceCollectedAt
→ instante da coleta

instantes técnicos
→ UTC
```

---

# 14. Etapa 9 — Propostas de governo

## Arquivo

```text
app/ingestion/tse/proposal_reader.py
```

## Fluxo

```text
CKAN
 ↓
recurso proposta de governo
 ↓
download ZIP
 ↓
SHA-256
 ↓
extrair PDF
 ↓
identificar SQ_CANDIDATO no nome oficial
 ↓
CandidateRepository
 ↓
extrair texto
 ↓
DocumentHash
 ↓
ProposalDocumentRepository
```

Não associar PDF somente pelo nome do candidato.

## Extração

Preservar:

- ordem das páginas;
- texto por página quando disponível;
- URL de origem;
- hash;
- identificador CKAN.

Persistir texto longo usando stream/CLOB parametrizado.

Não concatenar o corpo do PDF em SQL.

---

# 15. Etapa 10 — Cliente Câmara

## Arquivos

```text
app/ingestion/camara/client.py
app/ingestion/camara/contracts.py
app/ingestion/camara/pagination.py
app/ingestion/camara/mapper.py
```

Base:

```text
https://dadosabertos.camara.leg.br/api/v2
```

Header:

```http
Accept: application/json
```

Contratos esperados:

Coleção:

```json
{
  "dados": [],
  "links": []
}
```

Entidade:

```json
{
  "dados": {},
  "links": []
}
```

Ausência dos campos esperados deve gerar erro de contrato.

---

# 16. Etapa 11 — Paginação Câmara

Configuração:

```text
pagina inicial = 1
itens = 100
```

Seguir:

```text
links[].rel == "next"
```

Não inferir páginas futuras quando a API já fornece o link `next`.

---

# 17. Etapa 12 — Matching TSE × Câmara

## Arquivo

```text
app/ingestion/matching/candidate_matcher.py
```

Entrada:

```text
Candidate.Name
Candidate.BallotName
Candidate.State
Candidate.Party
```

Fluxo:

```text
Candidate
 ↓
normalização
 ↓
consulta Câmara
 ↓
comparação
 ↓
score técnico
 ↓
MatchStatus
```

Persistir:

```text
CamaraDeputyId
MatchStatus
MatchConfidence
```

Estados adotados pela implementação atual:

```text
MATCHED
REVIEW
UNMATCHED
```

Somente `MATCHED` inicia automaticamente a ingestão parlamentar.

`MatchConfidence` é apenas um mecanismo técnico de identidade.

Não usar para avaliação política.

---

# 18. Etapa 13 — Histórico parlamentar

Para candidato `MATCHED`:

```text
CamaraDeputyId
 ↓
histórico
 ↓
mandatos externos
 ↓
mapper
 ↓
PoliticalHistoryRepository
```

Persistir:

```text
Candidate
Institution
Position
Party
State
StartDate
EndDate
ExternalId
Situation
SourceUrl
SourceCollectedAt
RawJson
CreatedAt
UpdatedAt
```

Manter proveniência.

---

# 19. Etapa 14 — Proposições, autores e temas

Fluxo:

```text
Candidate.CamaraDeputyId
        ↓
listar proposições
        ↓
seguir paginação
        ↓
obter detalhe
        ↓
obter autores
        ↓
obter temas
        ↓
BEGIN
        ↓
Proposition
PropositionAuthor
PropositionTopic
        ↓
COMMIT
```

Em falha de uma proposição:

```text
ROLLBACK da proposição
registrar erro
continuar demais itens
```

Garantir idempotência.

---

# 20. Etapa 15 — Política HTTP

Retry somente para:

```text
timeout de conexão
timeout de leitura
HTTP 429
HTTP 500
HTTP 502
HTTP 503
HTTP 504
```

Política:

```text
máximo = 4 tentativas
backoff = 1s, 2s, 4s, 8s
+ jitter
```

Respeitar `Retry-After`.

Não repetir automaticamente:

```text
HTTP 400
erro de contrato
erro de validação
```

---

# 21. Etapa 16 — PoliticalChunk

## Arquivo

```text
app/ingestion/chunking/political_chunk_builder.py
```

Fontes:

```text
Proposition
ProposalDocument
PoliticalHistory
```

Mapeamento:

```text
Proposition
SourceType = PROPOSITION
SourceId = CamaraId

ProposalDocument
SourceType = GOVERNMENT_PROPOSAL
SourceId = DocumentHash

PoliticalHistory
SourceType = POLITICAL_HISTORY
SourceId = ExternalId
```

Não usar `%ID` como `SourceId` quando houver identificador externo estável.

Todo chunk deve preservar:

```text
Candidate
SourceType
SourceId
Title
Content
SourceUrl
ContentHash
MetadataJson
```

---

# 22. Etapa 17 — Chunking

## Proposição

Estrutura textual:

```text
Título: PL 100/2026
Autores: ...
Temas: ...
Ementa: ...
Ementa detalhada: ...
Situação: ...
```

Proposição pequena:

```text
ChunkIndex = 0
```

Se exceder o limite:

```text
usar chunker
```

## Proposta de governo

Configuração:

```text
chunk alvo = 700 tokens
overlap = 100 tokens
```

Preservar:

- ordem;
- páginas;
- metadados;
- limite físico de `PoliticalChunk.Content`.

## Histórico

Transformar somente os campos realmente persistidos em texto recuperável semanticamente.

---

# 23. Etapa 18 — ContentHash

Calcular SHA-256 determinístico do conteúdo normalizado.

Se:

```text
hash novo == hash persistido
```

não gerar embedding novamente.

Se:

```text
hash novo != hash persistido
```

atualizar conteúdo e invalidar/regenerar o embedding.

---

# 24. Etapa 19 — Embeddings

## Arquivo

```text
app/embeddings/embedder.py
```

Contrato:

```python
embed(text: str) -> list[float]
```

Requisitos:

```text
modelo configurável
mesmo modelo para documentos e queries
dimensão = 1536
validação antes de persistir
tratamento de falha do provedor
```

Antes de persistir:

```python
assert len(vector) == EMBEDDING_DIMENSION
```

Persistir em:

```text
PoliticalChunk.Embedding
```

---

# 25. Etapa 20 — Pipeline de ingestão

## Arquivo

```text
app/ingestion/pipeline.py
```

Fluxo:

```text
START
 │
 ├── TSE_CANDIDATES IngestionRun
 │   ├── CKAN
 │   ├── ZIP candidatos
 │   ├── CSV
 │   ├── parser
 │   ├── filtros
 │   ├── mapper
 │   └── Candidate upsert
 │
 ├── TSE_PROPOSALS IngestionRun
 │   ├── CKAN
 │   ├── ZIP
 │   ├── PDFs
 │   ├── SQ_CANDIDATO
 │   └── ProposalDocument
 │
 ├── CAMARA IngestionRun
 │   ├── candidatos para matching
 │   ├── matching
 │   └── MATCHED
 │       ├── histórico
 │       ├── mandatos
 │       ├── proposições
 │       ├── autores
 │       └── temas
 │
 ├── PoliticalChunk
 │
 ├── ContentHash
 │
 └── embeddings pendentes
 │
END
```

Executável por:

```bash
python -m app.ingestion.pipeline
```

---

# 26. Etapa 21 — Idempotência

Executar a mesma entrada duas vezes deve resultar em:

```text
Candidate
→ nenhum duplicado por TseId

PoliticalHistory
→ nenhum duplicado por Candidate + ExternalId

Proposition
→ nenhum duplicado por CamaraId

PropositionAuthor
→ nenhum duplicado pela chave definida

PropositionTopic
→ nenhum duplicado por Proposition + Name

ProposalDocument
→ nenhum duplicado por Candidate + DocumentHash

PoliticalChunk
→ nenhum duplicado conforme identidade de chunk
```

Datas:

```text
CreatedAt
→ não muda na segunda execução

UpdatedAt
→ muda somente quando houver alteração real
```

---

# 27. Etapa 22 — Busca lexical

## Arquivo

```text
app/retrieval/lexical.py
```

Interface:

```python
search(
    query,
    candidate_id=None,
    source_type=None,
    top_k=20,
)
```

Objetivo:

favorecer correspondência explícita de termos presentes na consulta.

Retornar resultados normalizados.

---

# 28. Etapa 23 — Busca vetorial

## Arquivo

```text
app/retrieval/vector.py
```

Fluxo:

```text
query
 ↓
embedding
 ↓
IRIS VECTOR
 ↓
similaridade
 ↓
Top K
```

Aplicar os mesmos filtros da busca lexical.

---

# 29. Etapa 24 — Reciprocal Rank Fusion

## Arquivo

```text
app/retrieval/rrf.py
```

Entrada:

```text
ranking lexical
ranking vetorial
```

Saída:

```text
ranking unificado
```

A implementação deve ser determinística.

Não normalizar diretamente os scores dos mecanismos diferentes.

---

# 30. Etapa 25 — Hybrid Search

## Arquivo

```text
app/retrieval/hybrid.py
```

Fluxo:

```text
Query
 │
 ├──────────────┐
 ▼              ▼
Lexical        Vector
Top 20         Top 20
 │              │
 └──────┬───────┘
        ▼
       RRF
        ↓
      Top K
```

Configuração inicial:

```text
lexical = 20
vector = 20
final = 8
```

Resultado:

```text
candidate
source_type
source_id
title
content
source_url
score
```

---

# 31. Etapa 26 — RAG

## Arquivos

```text
app/rag/prompt.py
app/rag/service.py
```

Fluxo:

```text
pergunta
 ↓
filtros
 ↓
Hybrid Search
 ↓
Top evidências
 ↓
prompt
 ↓
LLM
 ↓
resposta
 ↓
fontes
```

Política obrigatória do prompt:

```text
usar somente as evidências fornecidas
não inventar fatos
não recomendar voto
não classificar candidato como bom ou ruim
não determinar ideologia automaticamente
diferenciar fato de inferência
informar falta de evidência
não tratar ausência de dado como evidência de ausência
apresentar fontes
```

Sem evidência suficiente:

```text
Não foram encontradas evidências suficientes nas fontes
indexadas para responder a esta pergunta.
```

---

# 32. Etapa 27 — API

## Diretório

```text
app/api/
```

Implementar:

```text
GET /candidates
GET /candidates/{id}
GET /candidates/{id}/propositions
POST /search
POST /ask
```

## GET /candidates

Filtros:

```text
name
party
state
office
```

## POST /search

Exemplo:

```json
{
  "query": "projetos relacionados à inteligência artificial",
  "candidateId": 123,
  "topK": 10
}
```

## POST /ask

Exemplo:

```json
{
  "question": "Quais projetos deste candidato estão relacionados à educação?",
  "candidateId": 123
}
```

Resposta:

```json
{
  "answer": "...",
  "sources": []
}
```

---

# 33. Etapa 28 — Streamlit

## Arquivo

```text
app/ui/streamlit_app.py
```

Tela:

```text
IRIS Political Insight

Candidato:
[ selecionar ]

Pergunta:
[                                      ]

[ Pesquisar ]
```

Exibir:

```text
candidato
pergunta
resposta
evidências
título da fonte
trecho
URL oficial
```

A interface não deve esconder as evidências utilizadas pelo RAG.

---

# 34. Etapa 29 — Logs

## Ingestão

Registrar:

```text
ingestion_run
source
candidate_id quando aplicável
source_id quando aplicável
records_processed
records_success
records_failed
elapsed_ms
erro técnico
```

Não registrar:

```text
CPF
título eleitoral
e-mail pessoal
dados pessoais excluídos
corpo integral dos PDFs
```

## Retrieval / RAG

Registrar:

```text
question
retrieval_time_ms
vector_search_time_ms
keyword_search_time_ms
generation_time_ms
total_time_ms
chunks_retrieved
```

Logs estruturados são suficientes.

---

# 35. Etapa 30 — Testes

## Diretório

```text
tests/
```

Organização sugerida:

```text
tests/
├── unit/
├── integration/
└── smoke/
```

## Testes unitários

Cobrir:

```text
settings
normalização TSE
parser CSV
mapper TSE
matching
paginação Câmara
chunking
ContentHash
RRF
prompt
```

## Testes de repository

Executar contra IRIS de teste:

```text
INSERT
UPDATE
UPSERT
relacionamentos
streams
VECTOR
índices únicos
transação
rollback
```

## Testes TSE

Cobrir:

```text
CKAN
seleção de resource
ZIP
Latin-1
delimiter ;
normalização
Candidate upsert
```

Erros:

```text
success=false
resource inativo
ZIP inválido
header incompatível
linha inválida
```

## Testes Câmara

Cobrir:

```text
dados/links
paginação
deputado
histórico
mandatos
proposições
detalhe
autores
temas
```

Erros:

```text
400
404
429
500
timeout
```

## Teste de idempotência

Executar a mesma fixture duas vezes e comparar contagens.

## Teste de retrieval

Validar:

```text
termo exato
→ lexical

termo semanticamente equivalente
→ vector

ranking misto
→ RRF

candidate_id
→ filtro

source_type
→ filtro
```

## Teste RAG

Validar:

```text
resposta baseada nas evidências
fontes apresentadas
falta de evidência tratada
nenhuma recomendação eleitoral
nenhum fato criado fora do contexto
```

---

# 36. Etapa 31 — Smoke test das fontes oficiais

Antes de carga real:

```text
1. CKAN responde success=true
2. recurso Candidatos está active
3. ZIP abre
4. CSV contém cabeçalho mínimo
5. API Câmara responde
6. /deputados retorna dados e links
7. proposição conhecida retorna detalhe
8. autores são recuperados
9. temas são recuperados
```

O smoke test não grava no IRIS.

---

# 37. Etapa 32 — Docker

Arquivos:

```text
Dockerfile
docker-compose.yml
```

O ambiente deve permitir:

```bash
docker compose up -d
```

Depois:

```bash
python -m app.ingestion.pipeline
```

E:

```bash
streamlit run app/ui/streamlit_app.py
```

Outro desenvolvedor deve conseguir executar o projeto apenas com:

```text
README.md
.env.example
Docker
Docker Compose
```

---

# 38. Critérios de aceite

## CA01 — Candidate

Candidatos filtrados do TSE devem existir no IRIS.

```text
Candidate.TseId == SQ_CANDIDATO
```

## CA02 — Idempotência

Reexecutar a ingestão não cria candidatos duplicados.

## CA03 — Propostas de governo

PDFs devem ser associados utilizando o identificador oficial do candidato presente no arquivo.

## CA04 — Matching

Candidato correspondente deve possuir:

```text
CamaraDeputyId
MatchStatus = MATCHED
```

Somente `MATCHED` recebe ingestão parlamentar automática.

## CA05 — Histórico

Histórico e mandatos devem possuir dados estruturados, `RawJson` e proveniência.

## CA06 — Proposições

Todas as páginas devem ser consumidas.

Cada proposição deve possuir detalhe, autores e temas antes do commit.

## CA07 — PoliticalChunk

Cada chunk deve preservar:

```text
Candidate
SourceType
SourceId
SourceUrl
Content
ContentHash
MetadataJson
```

## CA08 — Embeddings

Embeddings persistidos devem possuir exatamente:

```text
1536 dimensões
```

## CA09 — Busca lexical

Termos explícitos devem ser recuperados.

## CA10 — Busca vetorial

Conteúdo semanticamente relacionado deve ser recuperado.

## CA11 — Hybrid Search

Lexical e vector devem ser combinados por RRF.

## CA12 — RAG

O LLM deve responder utilizando as evidências recuperadas.

## CA13 — Proveniência

Toda resposta deve apresentar fontes rastreáveis.

## CA14 — Ausência de evidência

O sistema deve informar explicitamente quando o contexto não for suficiente.

## CA15 — IngestionRun

Toda execução termina em:

```text
SUCCESS
PARTIAL
FAILED
```

## CA16 — Privacidade

Dados pessoais excluídos do domínio não aparecem em tabelas ou logs.

## CA17 — Reprodutibilidade

Outro desenvolvedor consegue subir, ingerir e executar a aplicação seguindo o README.

---

# 39. Definição de pronto

O projeto está concluído quando esta execução funcionar de ponta a ponta:

```text
Dados oficiais TSE
        ↓
Candidate
        ↓
matching Câmara
        ↓
histórico + proposições
        ↓
proposta de governo
        ↓
PoliticalChunk
        ↓
embedding
        ↓
InterSystems IRIS
        ↓
usuário seleciona candidato
        ↓
pergunta
        ↓
Keyword Search
        +
Vector Search
        ↓
RRF
        ↓
Top evidências
        ↓
LLM
        ↓
resposta fundamentada
        ↓
fontes oficiais
```

Checklist final:

```text
[ ] Docker inicializa o ambiente
[ ] classes IRIS compilam
[ ] ingestão TSE funciona
[ ] ingestão Câmara funciona
[ ] propostas de governo são persistidas
[ ] reexecução não duplica dados
[ ] chunks mantêm proveniência
[ ] embeddings possuem 1536 dimensões
[ ] lexical search funciona
[ ] vector search funciona
[ ] RRF funciona
[ ] Hybrid Search funciona
[ ] RAG responde com evidências
[ ] ausência de evidência é tratada
[ ] fontes oficiais são apresentadas
[ ] Streamlit executa a demonstração
[ ] testes passam
[ ] README reproduz a instalação
```

Critério central:

> **Selecionar candidato → fazer pergunta → recuperar evidências do IRIS → Hybrid Search → RAG → resposta fundamentada → fontes oficiais.**

---

# 40. Regras de execução para Codex

O Codex deve:

1. ler `docs/SPEC.md` antes de alterar comportamento funcional;
2. ler `docs/CLASSES_IRIS_E_MAPEAMENTO_INGESTAO_ATUAL.md` antes de alterar persistência;
3. ler `docs/IMPLEMENTACAO_INGESTAO_TSE_CAMARA_IRIS.md` antes de alterar ingestão;
4. seguir este plano como ordem de implementação;
5. não criar nova classe persistente sem justificativa no escopo atual;
6. não mover HTTP para ObjectScript;
7. não colocar SQL em client HTTP;
8. não executar HTTP em repository;
9. não usar `%ID` como identificador externo;
10. preservar idempotência;
11. preservar proveniência;
12. validar embeddings com 1536 dimensões;
13. não regenerar embedding de conteúdo inalterado;
14. não persistir dados pessoais excluídos;
15. não recomendar candidatos;
16. não gerar fatos políticos sem evidência;
17. não alterar arquivos não relacionados à tarefa;
18. executar os testes relevantes após cada alteração;
19. informar arquivos criados e modificados ao concluir cada tarefa;
20. registrar divergência documental em vez de inventar comportamento.

---

# 41. Estratégia de implementação com Codex

Trabalhar em tarefas pequenas.

Exemplo de sequência:

```text
TASK 01
configuração

TASK 02
conexão IRIS + transações

TASK 03
repositories básicos

TASK 04
IngestionRun

TASK 05
TSE CKAN + parser

TASK 06
Candidate ingestion

TASK 07
proposal documents

TASK 08
Câmara client + pagination

TASK 09
candidate matching

TASK 10
history ingestion

TASK 11
proposition ingestion

TASK 12
PoliticalChunk

TASK 13
embeddings

TASK 14
pipeline integration

TASK 15
lexical retrieval

TASK 16
vector retrieval

TASK 17
RRF + hybrid

TASK 18
RAG

TASK 19
API

TASK 20
Streamlit

TASK 21
integration tests

TASK 22
Docker validation
```

Cada tarefa deve terminar com:

```text
código implementado
+
testes relevantes
+
lista de arquivos alterados
+
resultado dos testes
```

Não solicitar ao Codex:

```text
"implemente todo o projeto"
```

Preferir tarefas delimitadas por responsabilidade e arquivos.
