# Classes persistentes — TSE Public Data RAG Explorer

Pacote ObjectScript:

`IRISPolitical.Model`

Classes:

- `Candidate`
- `PoliticalHistory`
- `Proposition`
- `PropositionAuthor`
- `PropositionTopic`
- `ProposalDocument`
- `PoliticalChunk`
- `IngestionRun`

## Observação sobre vetor

`PoliticalChunk.Embedding` está definido inicialmente como:

```objectscript
Property Embedding As %Vector(DATATYPE = "DOUBLE", LEN = 1536);
```

A dimensão **deve ser ajustada ao modelo de embeddings escolhido antes de compilar**.

Para busca pequena do MVP, `VECTOR_COSINE()` pode ser utilizado sem HNSW.
Se HNSW for utilizado, mantenha comprimento fixo e um datatype compatível com os requisitos da versão do IRIS em uso.

## Responsabilidades

Estas classes representam persistência e relacionamentos.

Não devem conter:

- chamadas HTTP ao TSE;
- chamadas HTTP à Câmara;
- parsing de CSV/PDF;
- geração de embeddings;
- lógica do LLM.

Essas responsabilidades permanecem na aplicação Python.

## Persistência

Os IDs do IRIS continuam internos.

Identificadores externos são propriedades com índices próprios:

- `Candidate.TseId`
- `Candidate.CamaraDeputyId`
- `Proposition.CamaraId`

Isso evita acoplamento do `%ID` do IRIS aos contratos externos.
