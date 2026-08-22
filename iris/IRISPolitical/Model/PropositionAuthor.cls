Class IRISPolitical.Model.PropositionAuthor Extends %Persistent
    [ DdlAllowed, SqlTableName = PropositionAuthor ]
{

Relationship Proposition As IRISPolitical.Model.Proposition
    [ Cardinality = one, Inverse = Authors ];

/// Identificador do autor na Câmara, quando disponibilizado.
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
