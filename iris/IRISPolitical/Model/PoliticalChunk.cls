Class IRISPolitical.Model.PoliticalChunk Extends %Persistent
    [ DdlAllowed, SqlTableName = PoliticalChunk ]
{

Relationship Candidate As IRISPolitical.Model.Candidate
    [ Cardinality = one, Inverse = PoliticalChunks ];

/// Origem do conteúdo.
/// Valores iniciais: PROPOSITION, GOVERNMENT_PROPOSAL, POLITICAL_HISTORY.
Property SourceType As %String(MAXLEN = 50) [ Required ];

/// Identificador lógico do documento de origem.
/// Pode conter ID da Câmara ou ID interno/externo do documento TSE.
Property SourceId As %String(MAXLEN = 100) [ Required ];

/// Posição do chunk dentro do documento de origem.
Property ChunkIndex As %Integer [ Required ];

Property Title As %String(MAXLEN = 500);

/// Conteúdo textual usado em keyword search e para construção do contexto RAG.
Property Content As %String(MAXLEN = 32000) [ Required ];

Property SourceUrl As %String(MAXLEN = 1000);

/// Metadados auxiliares serializados em JSON.
Property MetadataJson As %String(MAXLEN = 32000);

/// SHA-256 do conteúdo normalizado.
Property ContentHash As %String(MAXLEN = 64) [ Required ];

/// Modelo que gerou o embedding.
Property EmbeddingModel As %String(MAXLEN = 255);

/// Quantidade aproximada de tokens do chunk.
Property TokenCount As %Integer;

/// IMPORTANTE:
/// LEN deve ser igual à dimensão do modelo de embedding escolhido.
/// 1536 é um valor inicial comum para determinados modelos.
/// Se o projeto usar um modelo de 384/768/etc., alterar antes de compilar.
/// DOUBLE + comprimento fixo permite criação de índice HNSW nas versões atuais do IRIS.
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
