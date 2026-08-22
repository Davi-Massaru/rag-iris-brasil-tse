Class IRISPolitical.Model.Proposition Extends %Persistent
    [ DdlAllowed, SqlTableName = Proposition ]
{

Relationship Candidate As IRISPolitical.Model.Candidate
    [ Cardinality = one, Inverse = Propositions ];

/// ID oficial da proposição na Câmara.
Property CamaraId As %Integer [ Required ];

/// Tipo, por exemplo PL, PEC, PLP.
Property Type As %String(MAXLEN = 30);

Property Number As %Integer;

Property Year As %Integer;

/// Título técnico gerado pela aplicação, por exemplo "PL 1234/2025".
Property Title As %String(MAXLEN = 500);

/// Ementa da proposição.
Property Summary As %String(MAXLEN = 12000);

/// Ementa detalhada, quando disponibilizada.
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
