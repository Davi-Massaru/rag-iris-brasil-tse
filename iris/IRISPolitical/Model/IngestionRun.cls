Class IRISPolitical.Model.IngestionRun Extends %Persistent
    [ DdlAllowed, SqlTableName = IngestionRun ]
{

/// Fonte principal da execução: TSE, CAMARA ou ALL.
Property Source As %String(MAXLEN = 30) [ Required ];

Property StartedAt As %TimeStamp [ Required ];

Property FinishedAt As %TimeStamp;

/// RUNNING, SUCCESS, PARTIAL ou FAILED.
Property Status As %String(MAXLEN = 20) [ Required ];

Property RecordsRead As %Integer;

Property RecordsCreated As %Integer;

Property RecordsUpdated As %Integer;

Property RecordsSkipped As %Integer;

Property RecordsFailed As %Integer;

/// Hash do artefato-fonte quando aplicável.
Property SourceHash As %String(MAXLEN = 64);

Property ErrorMessage As %String(MAXLEN = 32000);

/// Parâmetros usados na execução, serializados em JSON.
Property ParametersJson As %String(MAXLEN = 32000);

Index SourceStartedAtIDX On (Source, StartedAt);

Index StatusIDX On Status;

}
