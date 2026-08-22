Class IRISPolitical.Model.PropositionTopic Extends %Persistent
    [ DdlAllowed, SqlTableName = PropositionTopic ]
{

Relationship Proposition As IRISPolitical.Model.Proposition
    [ Cardinality = one, Inverse = Topics ];

/// Código oficial do tema na Câmara, quando disponibilizado.
Property ExternalCode As %Integer;

Property Name As %String(MAXLEN = 255) [ Required ];

Property CreatedAt As %TimeStamp;

Property UpdatedAt As %TimeStamp;

Index PropositionIDX On Proposition;

Index PropositionTopicUniqueIDX On (Proposition, Name) [ Unique ];

Index NameIDX On Name;

}
