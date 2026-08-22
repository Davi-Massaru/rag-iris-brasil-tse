Class IRISPolitical.Model.ProposalDocument Extends %Persistent
    [ DdlAllowed, SqlTableName = ProposalDocument ]
{

Relationship Candidate As IRISPolitical.Model.Candidate
    [ Cardinality = one, Inverse = ProposalDocuments ];

Property ElectionYear As %Integer [ Required ];

Property Title As %String(MAXLEN = 500);

Property SourceUrl As %String(MAXLEN = 1000) [ Required ];

/// ID do recurso CKAN do TSE.
Property SourceResourceId As %String(MAXLEN = 100);

Property FileName As %String(MAXLEN = 500);

/// SHA-256 do arquivo original.
Property DocumentHash As %String(MAXLEN = 64) [ Required ];

/// Texto integral extraído do PDF.
/// Os embeddings são gerados nos PoliticalChunk, não neste campo.
Property RawText As %Stream.GlobalCharacter;

Property SourceCollectedAt As %TimeStamp;

Property CreatedAt As %TimeStamp;

Property UpdatedAt As %TimeStamp;

Index CandidateIDX On Candidate;

Index CandidateYearIDX On (Candidate, ElectionYear);

Index CandidateDocumentHashIDX On (Candidate, DocumentHash) [ Unique ];

Index ResourceIDX On SourceResourceId;

}
