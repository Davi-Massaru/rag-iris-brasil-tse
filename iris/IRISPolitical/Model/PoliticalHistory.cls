Class IRISPolitical.Model.PoliticalHistory Extends %Persistent
    [ DdlAllowed, SqlTableName = PoliticalHistory ]
{

Relationship Candidate As IRISPolitical.Model.Candidate
    [ Cardinality = one, Inverse = PoliticalHistories ];

/// Instituição de origem, por exemplo CAMARA.
Property Institution As %String(MAXLEN = 50) [ Required ];

/// Cargo, função ou situação histórica.
Property Position As %String(MAXLEN = 255);

Property Party As %String(MAXLEN = 30);

Property State As %String(MAXLEN = 2);

Property StartDate As %Date;

Property EndDate As %Date;

/// Identificador externo, quando existir.
Property ExternalId As %String(MAXLEN = 100);

Property Situation As %String(MAXLEN = 255);

Property SourceUrl As %String(MAXLEN = 1000);

Property SourceCollectedAt As %TimeStamp;

/// JSON bruto opcional para auditoria do contrato externo.
Property RawJson As %Stream.GlobalCharacter;

Property CreatedAt As %TimeStamp;

Property UpdatedAt As %TimeStamp;

Index CandidateIDX On Candidate;

Index InstitutionIDX On Institution;

Index ExternalIdIDX On ExternalId;

}
