# IRIS Political Insight

> **Brazil is already campaigning for its 2026 general election. What if exploring public electoral data were as easy as asking a question?**

[Versão em português](README.pt.md) · [Technical pipeline](PIPELINE.md) · [English article](ARTICLE.md)

Brazil's official campaign season is underway in August 2026. On **October 4**, 158,745,463 eligible voters may cast ballots for six offices; a possible presidential and gubernatorial runoff will follow on **October 25**. These dates and electorate figures come from Brazil's [Superior Electoral Court (TSE)](https://www.tse.jus.br/comunicacao/noticias/2026/Julho/mais-de-158-milhoes-de-eleitores-estao-aptos-votar-nas-eleicoes-2026).

Brazil publishes a remarkable amount of information about candidates and legislative activity. The hard part is turning distributed files, APIs, identifiers, and documents into information people can actually explore. **IRIS Political Insight** uses InterSystems IRIS, official public data, Hybrid Search, and Retrieval-Augmented Generation (RAG) to provide a natural-language access layer over that evidence.

This is not an “election chatbot” or a voting recommender. It is a **public electoral and political data intelligence platform** that integrates, structures, links, indexes, retrieves, and contextualizes official records while preserving political neutrality and traceability to the source.

## Brazil's 2026 election meets AI

In October, voters will choose the president, state governors, senators, federal representatives, and state or Federal District representatives. Relevant records are published across agencies, formats, and access models.

> **During an election year, how can we turn a massive volume of public data about candidates and elected officials into information any citizen can explore?**

Public data is not automatically accessible information. Research may require government APIs, ZIP and CSV files, PDFs, SQL, several identifiers for the same person, and multiple official portals. The project lowers that barrier without replacing original sources.

## The solution

The platform connects two dimensions of Brazilian public life:

- the **TSE — Brazil's Superior Electoral Court** — provides candidacies, offices, parties, states, and government programs when available;
- the **Chamber of Deputies — the lower house of Brazil's National Congress** — provides history, external mandates, bills, authors, and topics for safely linked candidates.

A candidacy tells us who is running. Legislative records can add context for someone who has served in the Chamber. Cross-source identity resolution is deterministic and auditable; detailed parliamentary ingestion runs only for a <code>MATCHED</code> result.

Structured filters, lexical matching, and vector similarity retrieve evidence. The system enriches each passage with its authoritative source record, then asks a language model to synthesize only that context.

## Imagine asking...

These questions map to implemented query paths. Answers depend on the configured ingestion slice and evidence present in the corpus.

> “Summarize this candidate's government program.”

> “Which bills associated with this candidate discuss public education?”

> “Which official topics occur most often in this candidate's bills?”

> “What parliamentary history is available for this candidate?”

> “Which candidates have evidence related to reducing the six-day workweek?”

> “Which official sources support this answer?”

Individual mode rejects evidence belonging to anyone other than the selected candidate. Discovery mode searches globally, diversifies results across candidates, and keeps every passage attached to its authoritative identity. A candidate is never inferred from an author's name.

## Why this matters now

Brazil's campaign period began on **August 16**, according to the [official TSE calendar](https://www.tse.jus.br/comunicacao/noticias/2026/Marco/eleicoes-2026-confira-as-principais-datas-do-calendario-eleitoral). This project is being built while the election is underway, not for a hypothetical future event.

Its public-interest value is reducing the distance between **published data** and **explorable information**. It does not endorse candidates, assign political scores or labels, predict results, or create rankings. It distinguishes missing evidence from evidence of absence, exposes the passages and official links behind an answer, and remains nonpartisan.

## How it works

~~~mermaid
flowchart LR
    A[Official data<br/>TSE + Chamber] --> B[Ingestion and<br/>identity resolution]
    B --> C[(InterSystems IRIS<br/>relational + streams + vectors)]
    C --> D[Lexical search]
    C --> E[Vector Search]
    D --> F[Hybrid Search<br/>RRF]
    E --> F
    F --> G[Enriched evidence<br/>E1...En]
    G --> H[RAG<br/>restrictive prompt + LLM]
    H --> I[Grounded answer<br/>+ official sources]
~~~

The implemented path is **collect → validate → link → persist → chunk → represent → retrieve → contextualize → explain**.

## Why InterSystems IRIS?

IRIS is not merely where records happen to be stored. It unifies the representations and access paths the application needs:

| Capability | Verified use |
|---|---|
| Persistent classes | Eight <code>%Persistent</code> classes model candidates, history, bills, authors, topics, documents, chunks, and ingestion runs. |
| SQL | Parameterized SQL handles filters, aggregates, relationships, context, and audit queries. |
| Object API | Embedded Python uses <code>_OpenId()</code>, <code>_New()</code>, and <code>_Save()</code> for selected <code>Candidate</code> and <code>IngestionRun</code> operations. |
| Streams | Extracted PDF text and history JSON are retained in <code>%Stream.GlobalCharacter</code>. |
| Vector Search | 1,536-dimensional embeddings live in <code>%Vector</code>; IRIS computes <code>VECTOR_COSINE</code>. |
| Multimodel data | Relationships, objects, streams, and vectors form one knowledge base without a separate vector database. |
| Embedded Python | Ingestion, API, retrieval, and RAG execute in <code>IRISAPP</code>. |
| Native WSGI | IRIS Web Gateway hosts Flask through <code>%SYS.Python.WSGI</code> at <code>/api</code>. |
| Transactions/audit | Explicit commit/rollback units and <code>IngestionRun</code> make processing observable and repeatable. |

SQL answers deterministic questions, streams preserve source documents, vectors bridge vocabulary, and RAG joins these representations inside the IRIS-centered backend.

## RAG + Hybrid Search

Election data contains names, acronyms, party labels, states, offices, numbers, and IDs where exact wording matters. Human questions also express the same idea in different ways.

| Mechanism | Role |
|---|---|
| Lexical search | Rewards exact phrases and terms after case/accent normalization. |
| Vector Search | Embeds the query and uses IRIS <code>VECTOR_COSINE</code>. |
| Hybrid Search | Merges rankings through RRF (<code>k=60</code>) without conflating raw scores. |
| RAG | Gives evidence to the LLM for a cited, context-conditioned synthesis. |

The LLM is not called when no valid evidence exists. Its policy requires neutral language, evidence-only claims, <code>[E1]</code>/<code>[E2]</code> citations, and an explicit statement when context is insufficient. RAG does not eliminate hallucinations; it narrows the generation space through retrieved material.

## Official data sources

| Source | Data used | Access |
|---|---|---|
| [TSE Open Data](https://dadosabertos.tse.jus.br/dataset/candidatos-2026) | 2026 candidacies and government programs when available | CKAN, ZIP, Latin-1 CSV, PDFs |
| [Chamber Open Data](https://dadosabertos.camara.leg.br/) | Deputies, history, mandates, bills, authors, topics | Paginated REST v2 JSON |

Every chunk retains its source type, external ID, official URL, candidate, metadata, content hash, and passage.

## Architecture

~~~mermaid
flowchart TB
    UI[Streamlit :8501] --> API[IRIS Web Gateway :52773/api]
    API --> WSGI[%SYS.Python.WSGI + Flask]
    WSGI --> PY[Embedded Python]
    PY --> OBJ[Object API]
    PY --> SQL[SQL]
    OBJ --> DB[(IRISAPP)]
    SQL --> DB
    DB --> REL[Relational data]
    DB --> STR[Streams]
    DB --> VEC[%Vector]
    VEC --> RET[VECTOR_COSINE]
    REL --> RET
    RET --> RRF[Lexical + Vector + RRF]
    RRF --> RAG[Context + LLM]
    RAG --> UI
~~~

There is no separate <code>api</code> container and no Waitress process. IRIS serves Flask; the second container contains only Streamlit.

## Data pipeline

One command runs TSE candidates, government programs, Chamber matching/collection, and the RAG index. Downloads are validated, writes are idempotent, chunks default to 700 tokens with 100-token overlap, and <code>text-embedding-3-small</code> produces 1,536 dimensions.

See **[PIPELINE.md](PIPELINE.md)** for contracts, matching, transactions, pagination, hashes, failures, chunking, and retrieval. This README deliberately avoids duplicating it.

## Reproducible demo

After ingestion, open <code>http://localhost:8501</code>, select a candidate — or “All candidates” — and ask a question. The UI displays the answer and its sources.

Exercise the API without hard-coding an ID:

~~~powershell
$candidates = Invoke-RestMethod http://localhost:52773/api/candidates
$candidate = $candidates.items | Select-Object -First 1
$body = @{ question = "Which topics occur most often in this candidate's bills?"; candidateId = [int]$candidate.id } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:52773/api/ask -ContentType "application/json" -Body $body
~~~

~~~text
question
  → deterministic planning
  → structured retrieval or Hybrid Search
  → chunk + authoritative source record
  → [E1]...[En] context
  → LLM
  → answer + sources[] with official URLs
~~~

No screenshots are currently committed, so this README does not present a fabricated response as a live result. Output varies with scope, date, and upstream data.

## InterSystems 2026 Programming Contest

The project targets the **RAG topic** in the [2026 InterSystems Portuguese Developer Community Programming Contest](https://pt.community.intersystems.com/post/concurso-de-programa%C3%A7%C3%A3o-da-comunidade-de-desenvolvedores-da-intersystems-pt-2026).

| Criterion | Evidence | Status |
|---|---|---|
| RAG | Retrieval → context → prompt → Responses API → answer with sources | Implemented |
| Hybrid Search | Lexical + vector rankings merged by RRF | Implemented |
| Vector Search | <code>%Vector(DOUBLE, 1536)</code> + <code>VECTOR_COSINE</code> | Implemented |
| Public APIs | TSE CKAN and Chamber REST v2 | Implemented |
| Multimodel data | Relational/object + stream + vector in IRIS | Implemented |
| Chunking | 700/100 token windows, hashes, provenance, page metadata | Implemented and explained |
| Embeddings | <code>text-embedding-3-small</code>; same model for corpus and queries | Implemented and explained |
| Explicit pipeline | Ingestion, chunking, vector, retrieval, prompt, generation | Implemented and documented |
| Native WSGI | <code>%SYS.Python.WSGI</code> at <code>/api</code> | Implemented; the formal bonus belongs to PyProd |

The AI-assisted method, specification prompts, human review, and real corrections are described in [ARTICLE.md](ARTICLE.md) and [ARTICLE.pt.md](ARTICLE.pt.md).

## Run the project

### Requirements

- Docker with Compose v2;
- access to <code>intersystems/iris-community:latest-cd</code>;
- an OpenAI key for embeddings, vector search, and <code>/ask</code>;
- ports <code>1972</code>, <code>52773</code>, and <code>8501</code> available;
- Python 3.12 only for host-side development/tests.

### 1. Clone

This checkout has no configured <code>origin</code>, so the documentation does not guess a publication URL. Use the HTTPS URL shown on the published repository page:

~~~powershell
$repositoryUrl = Read-Host "Repository HTTPS URL"
git clone $repositoryUrl
Set-Location tse-iris-rag
~~~

### 2. Configure

~~~powershell
Copy-Item .env.example .env
notepad .env
~~~

On Linux/macOS, use <code>cp .env.example .env</code>. Set at least:

~~~dotenv
LLM_API_KEY=your-openai-key
~~~

The example targets 2026, state <code>SP</code>, and offices in <code>INGEST_OFFICES</code>. Reduce scope and Chamber caps for a smaller load.

### 3. Build and start

~~~powershell
docker compose up --build -d
docker compose ps
~~~

Wait for <code>iris</code> to become healthy and <code>ui</code> to run.

### 4. Health checks

~~~powershell
Invoke-RestMethod http://localhost:52773/api/health
Invoke-WebRequest -UseBasicParsing http://localhost:8501/_stcore/health
~~~

Expected: <code>{"status":"ok"}</code> and <code>ok</code>.

### 5. Ingest data

~~~powershell
docker compose exec iris irispython -m app.ingestion.pipeline
~~~

This contacts public services and creates embeddings; runtime and volume vary. To rebuild only chunks/embeddings:

~~~powershell
docker compose exec -T iris irispython -m app.ingestion.chunk_index
~~~

### 6. Validate and open

~~~powershell
Invoke-RestMethod http://localhost:52773/api/candidates
~~~

- UI: <code>http://localhost:8501</code>
- API: <code>http://localhost:52773/api</code>

### 7. Local tests

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
pytest -m unit
ruff check app tests wsgi_app.py
mypy app wsgi_app.py
~~~

Integration and smoke suites require live IRIS/Docker plus <code>RUN_IRIS_TESTS=1</code> and <code>RUN_SMOKE_TESTS=1</code>, respectively.

## Essential troubleshooting

| Symptom | Action |
|---|---|
| IRIS is unhealthy | <code>docker compose logs --tail 200 iris</code> |
| API returns 500 | <code>docker compose exec -T iris sh -lc "tail -100 /usr/irissys/mgr/WSGI.log"</code> |
| Candidate list is empty | Run ingestion; check the key, <code>INGEST_*</code> filters, and logs. |
| <code>RAG_INDEX</code> is partial | Check the key; chunks may lack embeddings. |
| UI cannot reach API | Container uses <code>http://iris:52773/api</code>; host uses <code>http://localhost:52773/api</code>. |
| WSGI serves old code | Rebuild/recreate <code>iris</code>; imported modules may be cached. |

<code>docker compose down</code> preserves the volume. <code>docker compose down -v</code> **deletes IRIS project data**.

## Project structure

~~~text
app/
├── api/          # Flask and HTTP contracts
├── config/       # validated settings
├── database/     # SQL, DB-API, Object API, transactions
├── embeddings/   # embeddings
├── ingestion/    # TSE, Chamber, matching, chunking
├── rag/          # context, prompt, generation
├── repositories/ # IRIS persistence
├── retrieval/    # structured, lexical, vector, RRF
└── ui/           # Streamlit
iris/             # eight ObjectScript classes
tests/            # unit, integration, smoke
docs/             # specifications, decisions, audits
~~~

## Documentation

- [Technical pipeline](PIPELINE.md)
- [Product specification](docs/SPEC%20%E2%80%94%20IRIS%20Political%20Insight.md)
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [TSE + Chamber + IRIS ingestion](docs/IMPLEMENTACAO_INGESTAO_TSE_CAMARA_IRIS.md)
- [IRIS classes and mappings](docs/CLASSES_IRIS_E_MAPEAMENTO_INGESTAO_ATUAL.md)
- [Native WSGI migration](docs/MIGRACAO_FLASK_WAITRESS_PARA_IRIS_WSGI.md)
- [English technical article](ARTICLE.md)

## License and responsibility

Released under the [MIT License](LICENSE).

Independent project with no affiliation to the TSE, Chamber, candidates, or parties. It organizes public information and does not replace official sources or voter judgment.
