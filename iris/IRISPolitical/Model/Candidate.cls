Class IRISPolitical.Model.Candidate Extends %Persistent
    [ DdlAllowed, SqlTableName = Candidate ]
{

/// Identificador da candidatura no TSE (SQ_CANDIDATO).
Property TseId As %String(MAXLEN = 40) [ Required ];

/// Identificador do deputado na API da Câmara, quando houver correspondência.
Property CamaraDeputyId As %Integer;

/// Nome civil/oficial disponibilizado pelo TSE.
Property Name As %String(MAXLEN = 255) [ Required ];

/// Nome utilizado na urna.
Property BallotName As %String(MAXLEN = 255);

/// Sigla partidária.
Property Party As %String(MAXLEN = 30);

/// Número do partido.
Property PartyNumber As %Integer;

/// Cargo da candidatura.
Property Office As %String(MAXLEN = 100) [ Required ];

/// Unidade federativa ou BR.
Property State As %String(MAXLEN = 2) [ Required ];

/// Número da candidatura.
Property CandidateNumber As %Integer;

/// Situação do vínculo TSE <-> Câmara.
/// Valores esperados: MATCHED, REVIEW, UNMATCHED.
Property MatchStatus As %String(MAXLEN = 20);

/// Confiança técnica da resolução de identidade (0-100).
/// Não representa qualquer avaliação política.
Property MatchConfidence As %Decimal(PRECISION = 5, SCALE = 2);

/// URL oficial de origem.
Property SourceUrl As %String(MAXLEN = 1000);

/// Data/hora da coleta da fonte.
Property SourceCollectedAt As %TimeStamp;

/// Data/hora da criação do registro pela aplicação.
Property CreatedAt As %TimeStamp;

/// Data/hora da última atualização pela aplicação.
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
