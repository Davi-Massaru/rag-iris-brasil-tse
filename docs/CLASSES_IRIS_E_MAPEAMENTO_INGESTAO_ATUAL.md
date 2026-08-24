# Classes Persistentes IRIS e Mapeamento do Processo de Ingestão

> **Projeto:** IRIS Political Insight  
> **Escopo:** implementação atual  
> **Persistência:** InterSystems IRIS / ObjectScript  
> **Base das classes:** `Extends %Persistent`  
> **Fontes de dados:** Tribunal Superior Eleitoral (TSE) e Câmara dos Deputados  
> **Idioma:** PT-BR  

---

# 1. Objetivo

Este documento descreve exclusivamente as classes persistentes atualmente utilizadas pelo projeto e como cada uma delas participa do processo de ingestão.

Classes cobertas:

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

O documento também define:

- origem de cada informação;
- mapeamento TSE → IRIS;
- mapeamento Câmara → IRIS;
- relacionamentos;
- identificadores externos;
- regras de persistência;
- criação dos chunks;
- geração dos embeddings;
- ordem de execução da ingestão.

---

# 2. Responsabilidade das camadas

A arquitetura separa a obtenção de dados da persistência.

```text
TSE / Câmara
     │
     ▼
Cliente HTTP Python
     │
     ▼
DTO externo
     │
     ▼
Parser / Mapper
     │
     ▼
DTO interno
     │
     ▼
Repository
     │
     ▼
Classes %Persistent
     │
     ▼
InterSystems IRIS
```

As classes `.cls` não realizam:

```text
requisições HTTP
download de ZIP
leitura de CSV
extração de PDF
matching de nomes
geração de embedding
chamada ao LLM
```

Essas responsabilidades ficam na aplicação Python.

As classes `.cls` representam:

```text
estado persistido
relacionamentos
índices
identificadores externos
dados usados pelo RAG
controle de ingestão
```

---

# 3. Visão geral das classes

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

Relacionamentos:

```text
Candidate 1:N PoliticalHistory

Candidate 1:N Proposition

Proposition 1:N PropositionAuthor

Proposition 1:N PropositionTopic

Candidate 1:N ProposalDocument

Candidate 1:N PoliticalChunk
```

---

# 4. Identificadores

O `%ID` gerado pelo IRIS é utilizado somente como identificador interno.

Identificadores das fontes externas são armazenados em propriedades próprias.

```text
Fonte                  Campo externo           Classe / propriedade
──────────────────────────────────────────────────────────────────────
TSE                    SQ_CANDIDATO            Candidate.TseId

Câmara                 id deputado             Candidate.CamaraDeputyId

Câmara                 id proposição           Proposition.CamaraId

TSE / CKAN             resource id             ProposalDocument.SourceResourceId

Arquivo TSE            SHA-256                 ProposalDocument.DocumentHash
```

Exemplo:

```text
Candidate.%ID = 15
Candidate.TseId = "250000123456"
Candidate.CamaraDeputyId = 123456
```

O `%ID` não substitui os identificadores oficiais das APIs.

---

# 5. Classe `Candidate`

## 5.1 Responsabilidade

`Candidate` representa a candidatura eleitoral utilizada como entidade central do sistema.

A origem principal dos dados é o TSE.

Após a criação do candidato, o processo de ingestão tenta encontrar o deputado correspondente na Câmara dos Deputados.

---

## 5.2 Implementação atual

```objectscript
Class IRISPolitical.Model.Candidate Extends %Persistent
    [ DdlAllowed, SqlTableName = Candidate ]
{

Property TseId As %String(MAXLEN = 40) [ Required ];

Property CamaraDeputyId As %Integer;

Property Name As %String(MAXLEN = 255) [ Required ];

Property BallotName As %String(MAXLEN = 255);

Property Party As %String(MAXLEN = 30);

Property PartyNumber As %Integer;

Property Office As %String(MAXLEN = 100) [ Required ];

Property State As %String(MAXLEN = 2) [ Required ];

Property CandidateNumber As %Integer;

Property MatchStatus As %String(MAXLEN = 20);

Property MatchConfidence As %Decimal(PRECISION = 5, SCALE = 2);

Property SourceUrl As %String(MAXLEN = 1000);

Property SourceCollectedAt As %TimeStamp;

Property CreatedAt As %TimeStamp;

Property UpdatedAt As %TimeStamp;

Relationship PoliticalHistories As IRISPolitical.Model.PoliticalHistory
    [ Cardinality = many, Inverse = Candidate ];

Relationship Propositions As IRISPolitical.Model.Proposition
    [ Cardinality = many, Inverse = Candidate ];

Relationship ProposalDocuments As IRISPolitical.Model.ProposalDocument
    [ Cardinality = many, Inverse = Candidate ];

Relationship PoliticalChunks As IRISPolitical.Model.PoliticalChunk
    [ Cardinality = many, Inverse = Candidate ];

Index TseIdIDX On TseId [ Unique ];

Index CamaraDeputyIdIDX On CamaraDeputyId;

Index OfficeStateIDX On (Office, State);

Index PartyIDX On Party;

}
```

---

# 6. Mapeamento TSE → `Candidate`

O arquivo de candidatos do TSE é lido pela aplicação Python.

DTO externo:

```python
@dataclass
class TseCandidateRaw:
    election_year: str
    state: str
    office_code: str | None
    office_name: str
    candidate_sequence: str
    candidate_number: str
    candidate_name: str
    ballot_name: str
    party_number: str | None
    party_abbreviation: str
    party_name: str | None
    candidacy_status: str | None
```

Mapeamento:

| TSE | DTO Python | Classe IRIS |
|---|---|---|
| `SQ_CANDIDATO` | `candidate_sequence` | `Candidate.TseId` |
| `NM_CANDIDATO` | `candidate_name` | `Candidate.Name` |
| `NM_URNA_CANDIDATO` | `ballot_name` | `Candidate.BallotName` |
| `SG_PARTIDO` | `party_abbreviation` | `Candidate.Party` |
| `NR_PARTIDO` | `party_number` | `Candidate.PartyNumber` |
| `DS_CARGO` | `office_name` | `Candidate.Office` |
| `SG_UF` | `state` | `Candidate.State` |
| `NR_CANDIDATO` | `candidate_number` | `Candidate.CandidateNumber` |

Campos preenchidos pela própria aplicação:

```text
SourceUrl
SourceCollectedAt
CreatedAt
UpdatedAt
```

---

# 7. Persistência de `Candidate`

A chave externa utilizada para garantir a identidade da candidatura é:

```text
TseId
```

Índice:

```objectscript
Index TseIdIDX On TseId [ Unique ];
```

Fluxo:

```text
TseCandidateRaw
      │
      ▼
normalize_candidate()
      │
      ▼
CandidateUpsert
      │
      ▼
find Candidate by TseId
      │
 ┌────┴─────┐
 │          │
não existe  existe
 │          │
 ▼          ▼
INSERT     UPDATE
```

DTO interno:

```python
@dataclass
class CandidateUpsert:
    tse_id: str
    name: str
    ballot_name: str
    party: str
    party_number: int | None
    office: str
    state: str
    candidate_number: int | None
    source_url: str
```

---

# 8. Associação TSE ↔ Câmara

Após persistir o `Candidate`, o processo tenta encontrar a representação correspondente na API da Câmara.

Entrada:

```text
Candidate.Name
Candidate.BallotName
Candidate.State
Candidate.Party
```

Consulta:

```text
GET /deputados
```

Fluxo:

```text
Candidate
    │
    ▼
normalização de nome
    │
    ▼
consulta Câmara
    │
    ▼
comparação dos candidatos encontrados
    │
    ▼
resultado do matching
```

Campos atualizados:

```text
Candidate.CamaraDeputyId
Candidate.MatchStatus
Candidate.MatchConfidence
```

Valores atuais de `MatchStatus`:

```text
MATCHED
REVIEW
UNMATCHED
```

Exemplo:

```text
TSE
SQ_CANDIDATO = 250000123456
NM_CANDIDATO = JOÃO DA SILVA
SG_UF = SP
SG_PARTIDO = ABC

             ↓

Câmara
id = 123456
nome = JOÃO DA SILVA
siglaUf = SP
siglaPartido = ABC

             ↓

Candidate.CamaraDeputyId = 123456
Candidate.MatchStatus = "MATCHED"
```

`MatchConfidence` é utilizado apenas para a resolução técnica de identidade entre as duas bases.

---

# 9. Classe `PoliticalHistory`

## 9.1 Responsabilidade

`PoliticalHistory` armazena registros estruturados do histórico político/parlamentar associado ao candidato.

Fonte:

```text
Câmara dos Deputados
```

Dados utilizados:

```text
histórico parlamentar
mandatos externos
```

---

## 9.2 Implementação atual

```objectscript
Class IRISPolitical.Model.PoliticalHistory Extends %Persistent
    [ DdlAllowed, SqlTableName = PoliticalHistory ]
{

Relationship Candidate As IRISPolitical.Model.Candidate
    [ Cardinality = one, Inverse = PoliticalHistories ];

Property Institution As %String(MAXLEN = 50) [ Required ];

Property Position As %String(MAXLEN = 255);

Property Party As %String(MAXLEN = 30);

Property State As %String(MAXLEN = 2);

Property StartDate As %Date;

Property EndDate As %Date;

Property ExternalId As %String(MAXLEN = 100);

Property Situation As %String(MAXLEN = 255);

Property SourceUrl As %String(MAXLEN = 1000);

Property SourceCollectedAt As %TimeStamp;

Property RawJson As %Stream.GlobalCharacter;

Property CreatedAt As %TimeStamp;

Property UpdatedAt As %TimeStamp;

Index CandidateIDX On Candidate;

Index InstitutionIDX On Institution;

Index ExternalIdIDX On ExternalId;

}
```

---

# 10. Mapeamento Câmara → `PoliticalHistory`

Endpoints utilizados:

```text
GET /deputados/{id}/historico

GET /deputados/{id}/mandatosExternos
```

Fluxo:

```text
Câmara
   │
   ▼
CamaraDeputyHistoryItem
   │
   ▼
normalize_history()
   │
   ▼
PoliticalHistory
```

Mapeamento:

| Informação | `PoliticalHistory` |
|---|---|
| instituição | `Institution` |
| cargo/função | `Position` |
| partido | `Party` |
| UF | `State` |
| início | `StartDate` |
| fim | `EndDate` |
| identificador externo | `ExternalId` |
| situação | `Situation` |
| URL oficial | `SourceUrl` |
| resposta original | `RawJson` |

Para dados da Câmara:

```text
Institution = "CAMARA"
```

---

# 11. Relacionamento `Candidate → PoliticalHistory`

No candidato:

```objectscript
Relationship PoliticalHistories As IRISPolitical.Model.PoliticalHistory
    [ Cardinality = many, Inverse = Candidate ];
```

No histórico:

```objectscript
Relationship Candidate As IRISPolitical.Model.Candidate
    [ Cardinality = one, Inverse = PoliticalHistories ];
```

Representação:

```text
Candidate
   │
   ├── PoliticalHistory
   ├── PoliticalHistory
   └── PoliticalHistory
```

---

# 12. Classe `Proposition`

## 12.1 Responsabilidade

`Proposition` representa uma proposição legislativa obtida da Câmara dos Deputados.

Fonte:

```text
Câmara dos Deputados
```

Endpoints:

```text
GET /proposicoes?idDeputadoAutor={id}

GET /proposicoes/{id}
```

---

## 12.2 Implementação atual

```objectscript
Class IRISPolitical.Model.Proposition Extends %Persistent
    [ DdlAllowed, SqlTableName = Proposition ]
{

Relationship Candidate As IRISPolitical.Model.Candidate
    [ Cardinality = one, Inverse = Propositions ];

Property CamaraId As %Integer [ Required ];

Property Type As %String(MAXLEN = 30);

Property Number As %Integer;

Property Year As %Integer;

Property Title As %String(MAXLEN = 500);

Property Summary As %String(MAXLEN = 12000);

Property DetailedSummary As %String(MAXLEN = 32000);

Property PresentationDate As %Date;

Property Status As %String(MAXLEN = 500);

Property SourceUrl As %String(MAXLEN = 1000);

Property SourceCollectedAt As %TimeStamp;

Property CreatedAt As %TimeStamp;

Property UpdatedAt As %TimeStamp;

Relationship Authors As IRISPolitical.Model.PropositionAuthor
    [ Cardinality = many, Inverse = Proposition ];

Relationship Topics As IRISPolitical.Model.PropositionTopic
    [ Cardinality = many, Inverse = Proposition ];

Index CamaraIdIDX On CamaraId [ Unique ];

Index CandidateIDX On Candidate;

Index CandidateYearIDX On (Candidate, Year);

Index TypeNumberYearIDX On (Type, Number, Year);

}
```

---

# 13. Mapeamento Câmara → `Proposition`

Contrato externo simplificado:

```python
@dataclass
class CamaraPropositionSummary:
    id: int
    uri: str
    acronym: str
    number: int
    year: int
    summary: str
```

Mapeamento:

| Câmara | `Proposition` |
|---|---|
| `id` | `CamaraId` |
| `siglaTipo` | `Type` |
| `numero` | `Number` |
| `ano` | `Year` |
| `ementa` | `Summary` |
| `ementaDetalhada` | `DetailedSummary` |
| `dataApresentacao` | `PresentationDate` |
| situação | `Status` |
| `uri` | `SourceUrl` |

Título gerado:

```text
{Type} {Number}/{Year}
```

Exemplo:

```text
PL 1234/2025
```

---

# 14. Persistência de `Proposition`

Chave externa:

```text
CamaraId
```

Índice:

```objectscript
Index CamaraIdIDX On CamaraId [ Unique ];
```

Fluxo:

```text
Candidate.CamaraDeputyId
      │
      ▼
GET /proposicoes?idDeputadoAutor={id}
      │
      ▼
proposições
      │
      ▼
GET /proposicoes/{id}
      │
      ▼
PropositionUpsert
      │
      ▼
upsert por CamaraId
```

DTO interno:

```python
@dataclass
class PropositionUpsert:
    camara_id: int
    candidate_id: int
    type: str
    number: int | None
    year: int | None
    title: str
    summary: str
    detailed_summary: str | None
    presentation_date: str | None
    status: str | None
    source_url: str
```

---

# 15. Classe `PropositionAuthor`

## 15.1 Responsabilidade

`PropositionAuthor` armazena a autoria de uma proposição.

Fonte:

```text
Câmara dos Deputados
```

Endpoint:

```text
GET /proposicoes/{id}/autores
```

---

## 15.2 Implementação atual

```objectscript
Class IRISPolitical.Model.PropositionAuthor Extends %Persistent
    [ DdlAllowed, SqlTableName = PropositionAuthor ]
{

Relationship Proposition As IRISPolitical.Model.Proposition
    [ Cardinality = one, Inverse = Authors ];

Property CamaraAuthorId As %Integer;

Property Name As %String(MAXLEN = 255) [ Required ];

Property AuthorType As %String(MAXLEN = 100);

Property Uri As %String(MAXLEN = 1000);

Property IsMainAuthor As %Boolean;

Property CreatedAt As %TimeStamp;

Property UpdatedAt As %TimeStamp;

Index PropositionIDX On Proposition;

Index CamaraAuthorIdIDX On CamaraAuthorId;

Index PropositionNameIDX On (Proposition, Name);

}
```

---

# 16. Mapeamento Câmara → `PropositionAuthor`

Fluxo:

```text
Proposition
    │
    ▼
GET /proposicoes/{id}/autores
    │
    ▼
PropositionAuthor DTO
    │
    ▼
IRISPolitical.Model.PropositionAuthor
```

Mapeamento:

| Câmara | `PropositionAuthor` |
|---|---|
| ID do autor | `CamaraAuthorId` |
| nome | `Name` |
| tipo do autor | `AuthorType` |
| URI | `Uri` |
| autor principal | `IsMainAuthor` |

---

# 17. Relacionamento `Proposition → PropositionAuthor`

Na proposição:

```objectscript
Relationship Authors As IRISPolitical.Model.PropositionAuthor
    [ Cardinality = many, Inverse = Proposition ];
```

No autor:

```objectscript
Relationship Proposition As IRISPolitical.Model.Proposition
    [ Cardinality = one, Inverse = Authors ];
```

Representação:

```text
Proposition
   │
   ├── PropositionAuthor
   ├── PropositionAuthor
   └── PropositionAuthor
```

---

# 18. Classe `PropositionTopic`

## 18.1 Responsabilidade

`PropositionTopic` armazena os temas oficiais associados a uma proposição pela Câmara dos Deputados.

Endpoint:

```text
GET /proposicoes/{id}/temas
```

---

## 18.2 Implementação atual

```objectscript
Class IRISPolitical.Model.PropositionTopic Extends %Persistent
    [ DdlAllowed, SqlTableName = PropositionTopic ]
{

Relationship Proposition As IRISPolitical.Model.Proposition
    [ Cardinality = one, Inverse = Topics ];

Property ExternalCode As %Integer;

Property Name As %String(MAXLEN = 255) [ Required ];

Property CreatedAt As %TimeStamp;

Property UpdatedAt As %TimeStamp;

Index PropositionIDX On Proposition;

Index PropositionTopicUniqueIDX On (Proposition, Name) [ Unique ];

Index NameIDX On Name;

}
```

---

# 19. Mapeamento Câmara → `PropositionTopic`

Fluxo:

```text
Proposition
    │
    ▼
GET /proposicoes/{id}/temas
    │
    ▼
tema oficial
    │
    ▼
PropositionTopic
```

Mapeamento:

| Câmara | `PropositionTopic` |
|---|---|
| código do tema | `ExternalCode` |
| nome do tema | `Name` |

Índice de unicidade:

```objectscript
Index PropositionTopicUniqueIDX On (Proposition, Name) [ Unique ];
```

Isso impede a duplicação do mesmo tema dentro da mesma proposição.

---

# 20. Relacionamento `Proposition → PropositionTopic`

Na proposição:

```objectscript
Relationship Topics As IRISPolitical.Model.PropositionTopic
    [ Cardinality = many, Inverse = Proposition ];
```

No tema:

```objectscript
Relationship Proposition As IRISPolitical.Model.Proposition
    [ Cardinality = one, Inverse = Topics ];
```

Representação:

```text
Proposition
   │
   ├── PropositionTopic
   ├── PropositionTopic
   └── PropositionTopic
```

---

# 21. Classe `ProposalDocument`

## 21.1 Responsabilidade

`ProposalDocument` representa um documento de proposta de governo obtido do TSE.

Origem:

```text
TSE
```

Processo:

```text
CKAN
  ↓
recurso de proposta
  ↓
ZIP
  ↓
PDF
  ↓
texto
  ↓
ProposalDocument
```

---

## 21.2 Implementação atual

```objectscript
Class IRISPolitical.Model.ProposalDocument Extends %Persistent
    [ DdlAllowed, SqlTableName = ProposalDocument ]
{

Relationship Candidate As IRISPolitical.Model.Candidate
    [ Cardinality = one, Inverse = ProposalDocuments ];

Property ElectionYear As %Integer [ Required ];

Property Title As %String(MAXLEN = 500);

Property SourceUrl As %String(MAXLEN = 1000) [ Required ];

Property SourceResourceId As %String(MAXLEN = 100);

Property FileName As %String(MAXLEN = 500);

Property DocumentHash As %String(MAXLEN = 64) [ Required ];

Property RawText As %Stream.GlobalCharacter;

Property SourceCollectedAt As %TimeStamp;

Property CreatedAt As %TimeStamp;

Property UpdatedAt As %TimeStamp;

Index CandidateIDX On Candidate;

Index CandidateYearIDX On (Candidate, ElectionYear);

Index CandidateDocumentHashIDX On (Candidate, DocumentHash) [ Unique ];

Index ResourceIDX On SourceResourceId;

}
```

---

# 22. Mapeamento PDF TSE → `ProposalDocument`

DTO interno:

```python
@dataclass
class ProposalDocumentUpsert:
    candidate_id: int
    election_year: int
    title: str
    source_url: str
    source_resource_id: str
    file_name: str
    file_hash: str
    extracted_text: str
```

Mapeamento:

| DTO Python | `ProposalDocument` |
|---|---|
| `candidate_id` | relacionamento `Candidate` |
| `election_year` | `ElectionYear` |
| `title` | `Title` |
| `source_url` | `SourceUrl` |
| `source_resource_id` | `SourceResourceId` |
| `file_name` | `FileName` |
| `file_hash` | `DocumentHash` |
| `extracted_text` | `RawText` |

---

# 23. Persistência de `ProposalDocument`

O documento é identificado pelo candidato e pelo hash do arquivo.

Índice:

```objectscript
Index CandidateDocumentHashIDX On (Candidate, DocumentHash) [ Unique ];
```

Fluxo:

```text
PDF
 │
 ▼
SHA-256
 │
 ▼
extração de texto
 │
 ▼
find Candidate + DocumentHash
 │
 ├── não existe → INSERT
 │
 └── existe     → UPDATE quando necessário
```

---

# 24. Relacionamento `Candidate → ProposalDocument`

No candidato:

```objectscript
Relationship ProposalDocuments As IRISPolitical.Model.ProposalDocument
    [ Cardinality = many, Inverse = Candidate ];
```

No documento:

```objectscript
Relationship Candidate As IRISPolitical.Model.Candidate
    [ Cardinality = one, Inverse = ProposalDocuments ];
```

---

# 25. Classe `PoliticalChunk`

## 25.1 Responsabilidade

`PoliticalChunk` é a estrutura utilizada pelo mecanismo de recuperação do RAG.

Ela armazena:

```text
conteúdo textual
origem
metadados
hash
embedding
modelo do embedding
quantidade de tokens
```

As fontes atuais de chunks são:

```text
PROPOSITION
GOVERNMENT_PROPOSAL
POLITICAL_HISTORY
```

---

## 25.2 Implementação atual

```objectscript
Class IRISPolitical.Model.PoliticalChunk Extends %Persistent
    [ DdlAllowed, SqlTableName = PoliticalChunk ]
{

Relationship Candidate As IRISPolitical.Model.Candidate
    [ Cardinality = one, Inverse = PoliticalChunks ];

Property SourceType As %String(MAXLEN = 50) [ Required ];

Property SourceId As %String(MAXLEN = 100) [ Required ];

Property ChunkIndex As %Integer [ Required ];

Property Title As %String(MAXLEN = 500);

Property Content As %String(MAXLEN = 32000) [ Required ];

Property SourceUrl As %String(MAXLEN = 1000);

Property MetadataJson As %String(MAXLEN = 32000);

Property ContentHash As %String(MAXLEN = 64) [ Required ];

Property EmbeddingModel As %String(MAXLEN = 255);

Property TokenCount As %Integer;

Property Embedding As %Vector(DATATYPE = "DOUBLE", LEN = 1536);

Property SourceCollectedAt As %TimeStamp;

Property CreatedAt As %TimeStamp;

Property UpdatedAt As %TimeStamp;

Index CandidateIDX On Candidate;

Index CandidateSourceTypeIDX On (Candidate, SourceType);

Index SourceIDX On (SourceType, SourceId);

Index SourceChunkUniqueIDX On
    (Candidate, SourceType, SourceId, ChunkIndex, ContentHash) [ Unique ];

Index ContentHashIDX On ContentHash;

}
```

---

# 26. Origem dos `PoliticalChunk`

```text
Proposition
     │
     └──────────────► PoliticalChunk


ProposalDocument
     │
     └──────────────► PoliticalChunk[]


PoliticalHistory
     │
     └──────────────► PoliticalChunk
```

---

# 27. Mapeamento `Proposition → PoliticalChunk`

Para uma proposição, o texto é montado a partir dos dados persistidos.

Exemplo:

```text
Tipo: PL
Número: 1234/2025
Autor: NOME DO PARLAMENTAR

Temas:
- Ciência, Tecnologia e Inovação
- Administração Pública

Ementa:
Dispõe sobre ...

Situação:
Em tramitação
```

Mapeamento:

| Origem | `PoliticalChunk` |
|---|---|
| `Proposition.Candidate` | `Candidate` |
| valor fixo `PROPOSITION` | `SourceType` |
| `Proposition.CamaraId` | `SourceId` |
| `0` | `ChunkIndex` |
| `Proposition.Title` | `Title` |
| texto renderizado | `Content` |
| `Proposition.SourceUrl` | `SourceUrl` |
| metadados | `MetadataJson` |
| SHA-256 do conteúdo | `ContentHash` |

---

# 28. Metadata da proposição

Exemplo:

```json
{
  "source": "CAMARA",
  "sourceType": "PROPOSITION",
  "camaraId": 123456,
  "type": "PL",
  "number": 1234,
  "year": 2025,
  "topics": [
    "Ciência, Tecnologia e Inovação"
  ],
  "authors": [
    "NOME DO PARLAMENTAR"
  ]
}
```

---

# 29. Mapeamento `ProposalDocument → PoliticalChunk`

Uma proposta de governo é dividida em múltiplos chunks.

Fluxo:

```text
ProposalDocument.RawText
        │
        ▼
     chunking
        │
        ▼
PoliticalChunk[0]
PoliticalChunk[1]
PoliticalChunk[2]
...
```

Mapeamento:

| Origem | `PoliticalChunk` |
|---|---|
| `ProposalDocument.Candidate` | `Candidate` |
| valor fixo `GOVERNMENT_PROPOSAL` | `SourceType` |
| ID lógico do documento | `SourceId` |
| posição do chunk | `ChunkIndex` |
| `ProposalDocument.Title` | `Title` |
| texto do chunk | `Content` |
| `ProposalDocument.SourceUrl` | `SourceUrl` |
| dados do documento/página | `MetadataJson` |
| SHA-256 do chunk | `ContentHash` |

---

# 30. Metadata da proposta de governo

Exemplo:

```json
{
  "source": "TSE",
  "sourceType": "GOVERNMENT_PROPOSAL",
  "electionYear": 2026,
  "documentId": 42,
  "fileName": "proposta_governo.pdf",
  "page": 18,
  "chunkIndex": 6
}
```

---

# 31. Mapeamento `PoliticalHistory → PoliticalChunk`

O histórico persistido é convertido em texto para permitir recuperação semântica.

Exemplo:

```text
Instituição: Câmara dos Deputados
Cargo/Função: Deputado Federal
Partido: ABC
UF: SP
Período: 2023-2026
Situação: Exercício
```

Mapeamento:

| Origem | `PoliticalChunk` |
|---|---|
| `PoliticalHistory.Candidate` | `Candidate` |
| `POLITICAL_HISTORY` | `SourceType` |
| `%ID` ou identificador lógico | `SourceId` |
| `0` | `ChunkIndex` |
| título do histórico | `Title` |
| texto renderizado | `Content` |
| `PoliticalHistory.SourceUrl` | `SourceUrl` |
| SHA-256 | `ContentHash` |

---

# 32. Geração do embedding

A aplicação Python lê:

```text
PoliticalChunk.Content
```

e executa:

```text
Content
   │
   ▼
modelo de embedding
   │
   ▼
list[float]
   │
   ▼
PoliticalChunk.Embedding
```

Os campos atualizados são:

```text
Embedding
EmbeddingModel
TokenCount
UpdatedAt
```

A classe atual define:

```objectscript
Property Embedding As %Vector(DATATYPE = "DOUBLE", LEN = 1536);
```

Portanto o modelo utilizado no processo deve produzir vetor compatível com `LEN = 1536`.

---

# 33. Persistência de `PoliticalChunk`

Índice de unicidade:

```objectscript
Index SourceChunkUniqueIDX On
    (Candidate, SourceType, SourceId, ChunkIndex, ContentHash) [ Unique ];
```

A identidade do chunk considera:

```text
Candidate
+
tipo da origem
+
identificador da origem
+
posição do chunk
+
hash do conteúdo
```

Fluxo:

```text
documento renderizado
      │
      ▼
chunk
      │
      ▼
SHA-256(content)
      │
      ▼
consulta por origem / posição / hash
      │
 ┌────┴────┐
 │         │
novo      existente
 │         │
 ▼         ▼
INSERT    reutilizar / atualizar dados técnicos
```

---

# 34. Relacionamento `Candidate → PoliticalChunk`

No candidato:

```objectscript
Relationship PoliticalChunks As IRISPolitical.Model.PoliticalChunk
    [ Cardinality = many, Inverse = Candidate ];
```

No chunk:

```objectscript
Relationship Candidate As IRISPolitical.Model.Candidate
    [ Cardinality = one, Inverse = PoliticalChunks ];
```

Isso permite filtrar diretamente a recuperação semântica por candidato.

---

# 35. Classe `IngestionRun`

## 35.1 Responsabilidade

`IngestionRun` registra a execução técnica do processo de ingestão.

Ela permite saber:

```text
quando iniciou
quando terminou
qual fonte foi processada
quantos registros foram lidos
quantos foram criados
quantos foram atualizados
quantos foram ignorados
quantos falharam
qual foi o status final
```

---

## 35.2 Implementação atual

```objectscript
Class IRISPolitical.Model.IngestionRun Extends %Persistent
    [ DdlAllowed, SqlTableName = IngestionRun ]
{

Property Source As %String(MAXLEN = 30) [ Required ];

Property StartedAt As %TimeStamp [ Required ];

Property FinishedAt As %TimeStamp;

Property Status As %String(MAXLEN = 20) [ Required ];

Property RecordsRead As %Integer;

Property RecordsCreated As %Integer;

Property RecordsUpdated As %Integer;

Property RecordsSkipped As %Integer;

Property RecordsFailed As %Integer;

Property SourceHash As %String(MAXLEN = 64);

Property ErrorMessage As %String(MAXLEN = 32000);

Property ParametersJson As %String(MAXLEN = 32000);

Index SourceStartedAtIDX On (Source, StartedAt);

Index StatusIDX On Status;

}
```

---

# 36. Status de `IngestionRun`

Valores utilizados:

```text
RUNNING
SUCCESS
PARTIAL
FAILED
```

Fluxo:

```text
início
  │
  ▼
IngestionRun
Status = RUNNING
  │
  ▼
executar ingestão
  │
  ├── sucesso completo
  │       ▼
  │    SUCCESS
  │
  ├── parte falhou
  │       ▼
  │     PARTIAL
  │
  └── falha do pipeline
          ▼
        FAILED
```

---

# 37. Exemplo de `IngestionRun`

```text
Source = CAMARA

StartedAt = 2026-08-22 13:00:00

FinishedAt = 2026-08-22 13:04:17

Status = SUCCESS

RecordsRead = 135

RecordsCreated = 120

RecordsUpdated = 15

RecordsSkipped = 0

RecordsFailed = 0
```

---

# 38. Fluxo completo TSE

```text
TSE CKAN
   │
   ▼
descobrir recurso de candidatos
   │
   ▼
download ZIP
   │
   ▼
extrair CSV
   │
   ▼
TseCandidateRaw
   │
   ▼
normalização
   │
   ▼
CandidateUpsert
   │
   ▼
IRISPolitical.Model.Candidate
```

---

# 39. Fluxo completo de associação com Câmara

```text
Candidate
   │
   ▼
search deputy
   │
   ▼
Câmara /deputados
   │
   ▼
comparação de identidade
   │
   ▼
MatchStatus
   │
   ├── MATCHED
   │      │
   │      ▼
   │ CamaraDeputyId
   │
   ├── REVIEW
   │
   └── UNMATCHED
```

Somente candidatos com uma associação válida possuem os dados parlamentares da Câmara relacionados.

---

# 40. Fluxo de histórico político

```text
Candidate.CamaraDeputyId
          │
          ▼
GET /deputados/{id}/historico
          │
          ├─────────────┐
          │             │
          ▼             ▼
       parser       normalização
                         │
                         ▼
                 PoliticalHistory
```

Também é processado:

```text
GET /deputados/{id}/mandatosExternos
```

com persistência em `PoliticalHistory`.

---

# 41. Fluxo de proposições

```text
Candidate.CamaraDeputyId
          │
          ▼
GET /proposicoes?idDeputadoAutor={id}
          │
          ▼
lista de proposições
          │
          ▼
GET /proposicoes/{id}
          │
          ▼
Proposition
      ┌───┴────┐
      │        │
      ▼        ▼
 autores     temas
      │        │
      ▼        ▼
Proposition  Proposition
Author       Topic
```

Depois:

```text
Proposition
+
Authors
+
Topics
      │
      ▼
renderização textual
      │
      ▼
PoliticalChunk
      │
      ▼
Embedding
```

---

# 42. Fluxo de proposta de governo

```text
TSE CKAN
   │
   ▼
recurso de proposta de governo
   │
   ▼
ZIP
   │
   ▼
PDF
   │
   ▼
identificar Candidate
   │
   ▼
SHA-256
   │
   ▼
extração do texto
   │
   ▼
ProposalDocument
   │
   ▼
chunking
   │
   ▼
PoliticalChunk[]
   │
   ▼
embeddings
```

---

# 43. Fluxo de ingestão consolidado

```text
                         IngestionRun
                              │
                              ▼
                             TSE
                              │
                              ▼
                          Candidate
                              │
                              ▼
                       CandidateMatcher
                              │
                              ▼
                           Câmara
                              │
               ┌──────────────┼──────────────┐
               │              │              │
               ▼              ▼              ▼
        PoliticalHistory  Proposition   mandatos externos
                              │
                         ┌────┴─────┐
                         │          │
                         ▼          ▼
                    Authors       Topics
                         │          │
                         └────┬─────┘
                              │
                              ▼
                      PoliticalChunk
                              │
                              ▼
                          Embedding
```

Em paralelo, os documentos do TSE:

```text
TSE proposta PDF
       │
       ▼
ProposalDocument
       │
       ▼
PoliticalChunk[]
       │
       ▼
Embedding
```

---

# 44. Ordem de persistência

Ordem utilizada pelo processo:

```text
1. IngestionRun

2. Candidate

3. atualização do matching do Candidate

4. PoliticalHistory

5. Proposition

6. PropositionAuthor

7. PropositionTopic

8. ProposalDocument

9. PoliticalChunk

10. Embedding do PoliticalChunk

11. atualização final de IngestionRun
```

---

# 45. Estrutura Python da ingestão

```text
app/
├── ingestion/
│   ├── tse/
│   │   ├── client.py
│   │   ├── contracts.py
│   │   ├── parser.py
│   │   └── mapper.py
│   │
│   ├── camara/
│   │   ├── client.py
│   │   ├── contracts.py
│   │   └── mapper.py
│   │
│   ├── matching/
│   │   └── candidate_matcher.py
│   │
│   └── pipeline.py
│
├── repositories/
│   ├── candidate_repository.py
│   ├── political_history_repository.py
│   ├── proposition_repository.py
│   ├── proposition_author_repository.py
│   ├── proposition_topic_repository.py
│   ├── proposal_document_repository.py
│   ├── political_chunk_repository.py
│   └── ingestion_run_repository.py
│
└── embeddings/
    └── embedder.py
```

---

# 46. Responsabilidade dos clients

Clients:

```text
TseClient
CamaraClient
```

Responsabilidades:

```text
HTTP
download
paginação
status HTTP
desserialização do contrato externo
```

Os clients não persistem objetos.

---

# 47. Responsabilidade dos mappers

Exemplo:

```python
def to_candidate(raw: TseCandidateRaw) -> CandidateUpsert:
    ...
```

Função:

```text
contrato externo
      │
      ▼
normalização
      │
      ▼
DTO interno
```

---

# 48. Responsabilidade dos repositories

Os repositories fazem a comunicação entre Python e IRIS.

Exemplo:

```python
class CandidateRepository:

    def find_by_tse_id(self, tse_id: str):
        ...

    def upsert(self, candidate: CandidateUpsert):
        ...

    def update_camara_match(
        self,
        candidate_id: int,
        camara_deputy_id: int | None,
        status: str,
        confidence: float
    ):
        ...
```

---

# 49. DTO `CandidateUpsert`

```python
@dataclass
class CandidateUpsert:
    tse_id: str
    name: str
    ballot_name: str
    party: str
    party_number: int | None
    office: str
    state: str
    candidate_number: int | None
    source_url: str
```

Destino:

```text
IRISPolitical.Model.Candidate
```

---

# 50. DTO `PropositionUpsert`

```python
@dataclass
class PropositionUpsert:
    camara_id: int
    candidate_id: int
    type: str
    number: int | None
    year: int | None
    title: str
    summary: str
    detailed_summary: str | None
    presentation_date: str | None
    status: str | None
    source_url: str
```

Destino:

```text
IRISPolitical.Model.Proposition
```

---

# 51. DTO `ProposalDocumentUpsert`

```python
@dataclass
class ProposalDocumentUpsert:
    candidate_id: int
    election_year: int
    title: str
    source_url: str
    source_resource_id: str
    file_name: str
    file_hash: str
    extracted_text: str
```

Destino:

```text
IRISPolitical.Model.ProposalDocument
```

---

# 52. DTO `PoliticalChunkUpsert`

```python
@dataclass
class PoliticalChunkUpsert:
    candidate_id: int
    source_type: str
    source_id: str
    chunk_index: int
    title: str
    content: str
    source_url: str
    metadata_json: str
    content_hash: str
    embedding_model: str | None
    token_count: int | None
    embedding: list[float] | None
```

Destino:

```text
IRISPolitical.Model.PoliticalChunk
```

---

# 53. Origem de cada classe

| Classe | Origem |
|---|---|
| `Candidate` | TSE + associação Câmara |
| `PoliticalHistory` | Câmara |
| `Proposition` | Câmara |
| `PropositionAuthor` | Câmara |
| `PropositionTopic` | Câmara |
| `ProposalDocument` | TSE |
| `PoliticalChunk` | dados persistidos transformados |
| `IngestionRun` | aplicação |

---

# 54. Transformação de dados

| Origem | Processo | Destino |
|---|---|---|
| CSV TSE | parse + normalização | `Candidate` |
| Câmara `/deputados` | matching | `Candidate.CamaraDeputyId` |
| Câmara `/historico` | normalização | `PoliticalHistory` |
| Câmara `/mandatosExternos` | normalização | `PoliticalHistory` |
| Câmara `/proposicoes` | normalização | `Proposition` |
| Câmara `/autores` | normalização | `PropositionAuthor` |
| Câmara `/temas` | normalização | `PropositionTopic` |
| PDF TSE | extração de texto | `ProposalDocument` |
| `Proposition` | renderização textual | `PoliticalChunk` |
| `PoliticalHistory` | renderização textual | `PoliticalChunk` |
| `ProposalDocument` | chunking | `PoliticalChunk` |
| `PoliticalChunk.Content` | embedding | `PoliticalChunk.Embedding` |

---

# 55. Dados estruturados e dados RAG

Dados estruturados:

```text
Candidate
PoliticalHistory
Proposition
PropositionAuthor
PropositionTopic
ProposalDocument
```

Dados utilizados diretamente na recuperação textual/vetorial:

```text
PoliticalChunk.Title
PoliticalChunk.Content
PoliticalChunk.MetadataJson
PoliticalChunk.Embedding
PoliticalChunk.SourceUrl
```

---

# 56. Busca por candidato

O relacionamento de `PoliticalChunk` com `Candidate` permite limitar a busca a uma candidatura.

Exemplo conceitual:

```sql
SELECT
    ID,
    SourceType,
    SourceId,
    Title,
    Content
FROM PoliticalChunk
WHERE Candidate = ?
```

---

# 57. Busca vetorial

O embedding da pergunta é comparado com:

```text
PoliticalChunk.Embedding
```

Exemplo conceitual:

```sql
SELECT TOP 10
    ID,
    Candidate,
    SourceType,
    SourceId,
    Title,
    Content,
    SourceUrl,
    VECTOR_COSINE(
        Embedding,
        TO_VECTOR(?, DOUBLE)
    ) AS Similarity
FROM PoliticalChunk
WHERE Candidate = ?
ORDER BY Similarity DESC
```

---

# 58. Busca textual

Os campos textuais utilizados são:

```text
PoliticalChunk.Title
PoliticalChunk.Content
```

Filtros estruturados podem utilizar:

```text
Candidate
SourceType
Party
State
Office
Year
```

---

# 59. Construção do contexto RAG

Depois da recuperação:

```text
PoliticalChunk[]
       │
       ▼
ordenação
       │
       ▼
Top K
       │
       ▼
contexto do prompt
```

Cada chunk possui:

```text
Candidate
SourceType
SourceId
Title
Content
SourceUrl
MetadataJson
```

Isso permite que a resposta mantenha ligação com a fonte original.

---

# 60. Proveniência

Exemplo Câmara:

```text
PoliticalChunk
SourceType = PROPOSITION
SourceId = 123456
       │
       ▼
Proposition.CamaraId = 123456
       │
       ▼
Câmara dos Deputados
```

Exemplo TSE:

```text
PoliticalChunk
SourceType = GOVERNMENT_PROPOSAL
       │
       ▼
ProposalDocument
       │
       ▼
SourceResourceId
DocumentHash
SourceUrl
       │
       ▼
TSE
```

---

# 61. Datas técnicas

Campos:

```text
SourceCollectedAt
CreatedAt
UpdatedAt
```

Significado:

```text
SourceCollectedAt
= momento em que a informação foi coletada na fonte

CreatedAt
= momento da criação do registro no IRIS

UpdatedAt
= momento da última atualização do registro
```

---

# 62. Controle de duplicidade

## Candidate

```text
TseId
```

Índice:

```objectscript
Index TseIdIDX On TseId [ Unique ];
```

---

## Proposition

```text
CamaraId
```

Índice:

```objectscript
Index CamaraIdIDX On CamaraId [ Unique ];
```

---

## PropositionTopic

```text
Proposition + Name
```

Índice:

```objectscript
Index PropositionTopicUniqueIDX On (Proposition, Name) [ Unique ];
```

---

## ProposalDocument

```text
Candidate + DocumentHash
```

Índice:

```objectscript
Index CandidateDocumentHashIDX On (Candidate, DocumentHash) [ Unique ];
```

---

## PoliticalChunk

```text
Candidate
SourceType
SourceId
ChunkIndex
ContentHash
```

Índice:

```objectscript
Index SourceChunkUniqueIDX On
    (Candidate, SourceType, SourceId, ChunkIndex, ContentHash) [ Unique ];
```

---

# 63. Tratamento de falha de embedding

A origem persistida não depende do sucesso do embedding.

Fluxo:

```text
Proposition / ProposalDocument
        │
        ▼
PoliticalChunk
        │
        ▼
tentativa de embedding
        │
   ┌────┴─────┐
   │          │
sucesso      erro
   │          │
   ▼          ▼
Embedding   chunk permanece persistido
```

Quando o embedding é gerado:

```text
PoliticalChunk.Embedding
PoliticalChunk.EmbeddingModel
PoliticalChunk.TokenCount
```

são preenchidos.

---

# 64. Unidade de processamento por candidato

A ingestão parlamentar é organizada por candidato.

```text
Candidate
   │
   ├── PoliticalHistory
   │
   ├── Proposition
   │    ├── Authors
   │    └── Topics
   │
   └── PoliticalChunk
```

Isso mantém os relacionamentos consistentes durante o processamento.

---

# 65. Atualização do `IngestionRun`

Ao iniciar:

```text
Status = RUNNING
StartedAt = now()
```

Durante o processo:

```text
RecordsRead
RecordsCreated
RecordsUpdated
RecordsSkipped
RecordsFailed
```

Ao terminar:

```text
FinishedAt = now()
Status = SUCCESS | PARTIAL | FAILED
```

---

# 66. Processo principal em pseudocódigo

```python
def ingest():

    run = ingestion_run_repository.start(
        source="ALL"
    )

    try:

        # TSE
        for raw_candidate in tse_client.read_candidates():

            run.records_read += 1

            candidate_dto = tse_mapper.to_candidate(raw_candidate)

            candidate = candidate_repository.upsert(candidate_dto)

            # Match com Câmara
            match = candidate_matcher.match(candidate)

            candidate_repository.update_camara_match(
                candidate.id,
                match.deputy_id,
                match.status,
                match.confidence
            )

            if match.status != "MATCHED":
                continue

            # Histórico
            history_items = camara_client.get_deputy_history(
                match.deputy_id
            )

            for history in history_items:
                political_history_repository.upsert(
                    candidate.id,
                    history
                )

            external_mandates = camara_client.get_external_mandates(
                match.deputy_id
            )

            for mandate in external_mandates:
                political_history_repository.upsert(
                    candidate.id,
                    mandate
                )

            # Proposições
            propositions = camara_client.get_propositions_by_deputy(
                match.deputy_id
            )

            for proposition_summary in propositions:

                detail = camara_client.get_proposition(
                    proposition_summary.id
                )

                proposition = proposition_repository.upsert(
                    candidate.id,
                    detail
                )

                authors = camara_client.get_proposition_authors(
                    detail.id
                )

                proposition_author_repository.replace(
                    proposition.id,
                    authors
                )

                topics = camara_client.get_proposition_topics(
                    detail.id
                )

                proposition_topic_repository.replace(
                    proposition.id,
                    topics
                )

                chunk = build_proposition_chunk(
                    candidate,
                    proposition,
                    authors,
                    topics
                )

                political_chunk_repository.upsert(chunk)

        # Propostas de governo TSE
        for proposal_file in tse_client.read_government_proposals():

            candidate = resolve_candidate(proposal_file)

            document = proposal_document_repository.upsert(
                extract_proposal_document(candidate, proposal_file)
            )

            for chunk in chunk_proposal_document(document):

                political_chunk_repository.upsert(chunk)

        # Embeddings
        for chunk in political_chunk_repository.find_without_embedding():

            embedding = embedder.embed(chunk.content)

            political_chunk_repository.update_embedding(
                chunk.id,
                embedding.vector,
                embedding.model,
                embedding.token_count
            )

        ingestion_run_repository.success(run)

    except Exception as exc:

        ingestion_run_repository.failed(
            run,
            str(exc)
        )

        raise
```

---

# 67. Fluxo final

```text
TSE
 │
 ├── candidatos
 │      │
 │      ▼
 │   Candidate
 │      │
 │      ▼
 │   matching Câmara
 │      │
 │      ├── PoliticalHistory
 │      │
 │      └── Proposition
 │             ├── PropositionAuthor
 │             ├── PropositionTopic
 │             └── PoliticalChunk
 │
 └── proposta de governo
        │
        ▼
  ProposalDocument
        │
        ▼
  PoliticalChunk[]
        │
        ▼
     Embedding

Todos os processos
        │
        ▼
   IngestionRun
```

---

# 68. Resultado esperado da ingestão

Ao final de uma execução válida, o IRIS contém:

```text
Candidate
    │
    ├── dados eleitorais TSE
    │
    ├── vínculo com Câmara
    │
    ├── histórico político
    │
    ├── proposições
    │     ├── autores
    │     └── temas
    │
    ├── propostas de governo
    │
    └── chunks com embeddings
```

O RAG consulta os `PoliticalChunk`, enquanto as demais classes mantêm os dados estruturados e a proveniência da informação.

---

# 69. Resumo das responsabilidades

```text
Candidate
= identidade eleitoral e vínculo TSE/Câmara

PoliticalHistory
= histórico parlamentar estruturado

Proposition
= proposição legislativa

PropositionAuthor
= autoria da proposição

PropositionTopic
= temas oficiais da proposição

ProposalDocument
= documento de proposta de governo

PoliticalChunk
= unidade textual/vetorial utilizada na recuperação

IngestionRun
= controle técnico de cada execução de ingestão
```

---

# 70. Regra arquitetural do processo

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
Mapper
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
PoliticalChunk
     │
     ▼
Embedding
     │
     ▼
RAG
```

A fonte externa é conhecida pela camada de ingestão.

As classes `%Persistent` representam somente os dados persistidos.

`PoliticalChunk` concentra a representação textual e vetorial utilizada no RAG.

Cada informação utilizada para gerar uma resposta deve permanecer rastreável até a entidade persistida e sua fonte oficial.
