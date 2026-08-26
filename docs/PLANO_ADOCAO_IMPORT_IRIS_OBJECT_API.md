# ORDEM DE OPERAÇÕES 01/2026 — Adoção incremental de `import iris`

> **Projeto:** TSE Public Data RAG Explorer
> **Área de operações:** acesso a dados no Embedded Python do InterSystems IRIS  
> **Estado:** plano técnico; nenhuma alteração de comportamento autorizada por este documento  
> **Princípio:** empregar Object API em operações pontuais e manter SQL em operações de conjunto

## REFERÊNCIAS

1. [Introduction to Embedded Python](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=AFL_epython).
2. [Welcome, Python Developers](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=GPYDEV_journey).
3. [Bridge the Gap Between ObjectScript and Embedded Python](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=GEPYTHON_sharedata).
4. [Transaction Processing](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=GAPPS_tp).
5. [Object Concurrency Options](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=GOBJ_concurrency).
6. [Working with Streams](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=GOBJ_propstream).
7. [Defining and Using Relationships](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=GOBJ_relationships).
8. Documentos Markdown existentes em `docs/`, com ênfase em arquitetura, implementação técnica, ingestão, classes persistentes e migração WSGI.

---

# 1. SITUAÇÃO

## 1.1 Situação geral

O sistema em execução já alcançou a arquitetura alvo da migração WSGI:

```text
Streamlit
    -> HTTP /api
    -> IRIS Web Gateway
    -> %SYS.Python.WSGI
    -> Flask
    -> services/repositories
    -> Embedded Python no namespace IRISAPP
    -> InterSystems IRIS
```

Situação verificada em 24/08/2026:

```text
IRIS: 2026.2, Build 221U
namespace da aplicação: IRISAPP
serviço iris: saudável
serviço ui: ativo
GET /api/health: {"status":"ok"}
```

A implementação atual já contém uma ponte híbrida:

```text
Embedded Python disponível
    -> iris.sql.exec()

processo Python externo
    -> iris.dbapi.connect()
```

Portanto, a missão não é migrar novamente o WSGI nem substituir toda a camada SQL. A missão é introduzir a Object API do módulo `iris` em pontos de vantagem comprovada, sem alterar os contratos da aplicação.

## 1.2 Situação documental

Os oito arquivos `docs/*.md` foram inventariados. Há documentos normativos, planos históricos e relatórios de implementação.

| Documento consultado | Emprego nesta ordem |
|---|---|
| `SPEC — TSE Public Data RAG Explorer.md` | arquitetura funcional, multimodelo, API e critérios do MVP |
| `IMPLEMENTATION_PLAN.md` | separação de camadas, repositories, transações e ordem original |
| `IMPLEMENTACAO_TECNICA_TECNOLOGIAS_E_LIBS.md` | decisões de stack e fronteira de persistência |
| `IMPLEMENTACAO_INGESTAO_TSE_CAMARA_IRIS.md` | upsert, chaves, streams, lotes e idempotência |
| `CLASSES_IRIS_E_MAPEAMENTO_INGESTAO_ATUAL.md` | oito classes, relacionamentos, índices e `%ID` |
| `MIGRACAO_FLASK_WAITRESS_PARA_IRIS_WSGI.md` | WSGI Embedded e arquitetura alvo já alcançada |
| `PLANO_MELHORIA_CONTEXTO_IA_POLITICALCHUNK_CANDIDATOS.md` | leituras em lote para enriquecimento RAG |
| `PLANO_IMPLEMENTACAO_SIDEBAR_CANDIDATO_STREAMLIT.md` | contratos de leitura consumidos pela UI |

Divergências identificadas:

- `IMPLEMENTACAO_TECNICA_TECNOLOGIAS_E_LIBS.md` descreve um estado anterior em que `app/`, API, repositories e testes ainda não existiam;
- `MIGRACAO_FLASK_WAITRESS_PARA_IRIS_WSGI.md` chama de “arquitetura atual” o antigo conjunto IRIS + API/Waitress + UI, porém seu alvo já está implementado;
- `IMPLEMENTACAO_INGESTAO_TSE_CAMARA_IRIS.md` documenta DB-API TCP como único caminho, enquanto o código atual já usa `iris.sql.exec()` no processo Embedded;
- os documentos de sidebar e contexto RAG registram corretamente implementações já concluídas e sem mudança de persistência.

Regra de inteligência técnica:

```text
código executável + testes + infraestrutura atual
    têm precedência para descrever o estado presente;

SPEC + documentos de ingestão/classes
    permanecem normativos para contratos, regras de domínio e persistência.
```

## 1.3 Forças amigas

- oito classes `IRISPolitical.Model.*` estendem `%Persistent`;
- os repositories isolam acesso a dados das rotas e dos clients HTTP;
- a API já executa no mesmo processo lógico do IRIS;
- `module.xml` exige IRIS `>=2025.1`, compatível com a sintaxe recomendada `iris.IRISPolitical...`;
- a fábrica preserva fallback DB-API para execução externa e testes de integração;
- consultas são parametrizadas;
- transações possuem `tstart`, `tcommit` e `trollbackone` no adapter Embedded;
- contratos HTTP, DTOs, RAG e UI não dependem da tecnologia interna do repository.

## 1.4 Restrições e riscos

1. `_OpenId()` pesquisa exclusivamente pelo `%ID` interno. Não substitui consultas por `TseId`, `CamaraId`, hash ou chaves compostas.
2. No runtime verificado, `_Id()` retorna `str`, não `int`.
3. `_OpenId()` de ID inexistente retorna a string vazia `""`, não `None`.
4. Timestamps lidos pela Object API foram observados como `str`.
5. `%Stream.GlobalCharacter` retorna um objeto de stream e exige disciplina de `Read`, `Write`, `Rewind` e substituição de conteúdo.
6. O acesso observado a `PoliticalChunk.Embedding` pela Object API falhou com `TypeError: Unsupported type`.
7. Relações `Cardinality = one` recebem referência de objeto no modelo orientado a objetos. O ID SQL bruto não deve ser atribuído como se fosse uma propriedade literal.
8. `_Save()` retorna `%Status`; sucesso não pode ser inferido apenas pela ausência de exceção. Deve-se executar `iris.check_status(status)`.
9. Objeto aberto para modificação exige política explícita de concorrência. A documentação recomenda concorrência adequada, incluindo valor `4` quando o objeto será salvo.
10. O context manager `transaction()` atual não inicia uma transação por si. Hoje a primeira execução SQL a inicia. Uma gravação exclusivamente por `_Save()` deve ordenar o início transacional pelo adapter antes de salvar.
11. A `.venv` local está inválida porque aponta para um interpretador Python removido. `ruff` e `mypy` passaram; `pytest` local não pôde ser iniciado por essa causa.

## 1.5 Pontos atuais de conexão e acesso ao banco

| Setor | Arquivos | Situação atual | Ordem inicial |
|---|---|---|---|
| Fronteira de conexão | `app/database/connection.py` | escolhe Embedded `iris.sql` ou `iris.dbapi` | concentrar aqui toda capacidade Object API |
| Fronteira transacional | `app/database/transaction.py` | commit/rollback por context manager | preservar contrato; garantir `tstart` antes de `_Save()` |
| Ciclo HTTP | `app/api/app.py` | uma conexão por request; `/health` executa `SELECT 1` | não importar `iris` nas rotas |
| Composição de leitura | `app/api/services.py` | injeta repositories e mecanismos de retrieval | não alterar assinaturas públicas |
| Ingestão | `app/ingestion/pipeline.py` | abre conexões, repositories e unidades transacionais | migrar somente após prova em repository isolado |
| Indexação RAG | `app/ingestion/chunk_index.py` | lê fontes, grava chunks e embeddings | manter caminho SQL para `%Vector` |
| Leitura/escrita de candidato | `app/repositories/candidate_repository.py` | SQL por ID/TseId, listas, insert/update | primeiro alvo de `_OpenId()`; piloto de `_New()`/`_Save()` |
| Controle de execução | `app/repositories/ingestion_run_repository.py` | insert, `MAX(ID)`, incrementos e finish | candidato a `_New()` para obter `_Id()`; manter incrementos SQL atômicos |
| Entidades filhas | repositories de history, proposition, author, topic e document | upsert, relacionamentos, streams | manter SQL na primeira vaga; migrar somente após ensaio de relacionamento/stream |
| Chunks | `app/repositories/political_chunk_repository.py` | replace, delete, insert, pendências e embedding | manter SQL |
| Busca | `app/retrieval/lexical.py`, `vector.py`, `structured.py` | filtros, ranking, vetor, agregação e join | manter SQL permanentemente |
| Testes de integração | `tests/test_iris_integration.py` | setup, verificação e limpeza SQL | ampliar com testes Object API; manter limpeza SQL |

---

# 2. MISSÃO

A equipe de desenvolvimento adotará o módulo Embedded Python `iris` como acesso nativo orientado a objetos para leituras pontuais por `%ID` e gravações unitárias selecionadas, preservando:

- endpoints e payloads HTTP;
- DTOs e regras de domínio;
- chaves de idempotência;
- oito classes `%Persistent` atuais;
- SQL para consultas de conjunto, busca e tipos especiais;
- fallback `iris.dbapi` para execução externa;
- limites transacionais e comportamento de rollback;
- proveniência, neutralidade e resultados do RAG.

Estado final desejado:

```text
route/client
    -> service/pipeline
    -> repository existente
    -> adapter de acesso
         ├── Object API: _OpenId/_New/_Save em operação pontual
         └── SQL: filtros, listas, joins, agregações, streams e vetores
    -> IRISPolitical.Model.*
    -> IRISAPP
```

---

# 3. EXECUÇÃO

## 3.1 Intenção do comandante

Executar migração por substituição interna e reversível. Não reescrever repositories em massa. Não criar ORM. Não transferir regra de domínio para `.cls`. Não tocar em retrieval vetorial/lexical.

Prioridades:

1. preservar comportamento;
2. preservar transação e idempotência;
3. provar Object API em leitura pontual;
4. provar gravação simples;
5. avançar apenas mediante paridade automatizada;
6. manter SQL onde ele é tecnicamente superior.

## 3.2 Regras de engajamento

### EMPREGAR Object API

- leitura por `%ID` conhecido;
- criação unitária de objeto sem stream, vetor ou relacionamento obrigatório;
- atualização unitária por `%ID`, com concorrência e transação explícitas;
- obtenção imediata do ID novo por `_Id()`;
- invocação futura de método de domínio da classe, se vier a existir.

### MANTER SQL

- pesquisa por chave funcional ou índice que não seja `%ID`;
- `IN (...)`, filtros opcionais, ordenação e paginação;
- joins, contagens, `MIN`, `MAX` e incrementos atômicos;
- busca lexical, vetorial, structured search e RRF;
- leitura em lote para contexto RAG;
- `SUBSTRING` de stream;
- gravação/leitura de `%Vector`;
- exclusão e substituição em lote;
- caminhos executados por DB-API externo.

## 3.3 Matriz de decisão por operação

| Operação | Técnica alvo | Motivo |
|---|---|---|
| `Candidate.find_by_id` | `_OpenId()` no Embedded; SQL no DB-API | leitura pontual natural pela Object API |
| `Candidate.find_by_tse_id` | SQL | `TseId` é chave externa, não `%ID` |
| `Candidate.find_by_ids` e `list` | SQL | operação de conjunto |
| `Candidate._insert` | piloto `_New()` + `_Save()` | classe sem stream/vetor e ID novo disponível em `_Id()` |
| `Candidate._update` e `save_match` | piloto `_OpenId(id, 4)` + `_Save()` | atualização pontual; exige concorrência e paridade |
| `IngestionRun.start` | segunda gravação piloto | elimina `SELECT MAX(ID)` e obtém ID do próprio objeto |
| `IngestionRun.increment` | SQL | incremento `COALESCE(coluna,0)+?` deve permanecer atômico |
| `IngestionRun.finish` | manter SQL inicialmente | usa update condicional de estado e `rowcount` |
| upsert de entidades filhas | SQL na primeira campanha | relacionamentos e/ou streams aumentam o risco |
| `ProposalDocument.RawText` | SQL/stream adapter dedicado | não substituir stream por atribuição literal indiscriminada |
| `PoliticalHistory.RawJson` | SQL/stream adapter dedicado | mesma disciplina de stream |
| `PoliticalChunk.Embedding` | SQL | Object API não suportou o tipo no runtime observado |
| retrieval | SQL | filtros, agregações, ranking e vetor são set-based |

## 3.4 Organização para o combate

Estrutura mínima proposta:

```text
app/database/
├── connection.py          # mantém conexão SQL e transação
├── transaction.py         # contrato atual preservado
└── object_access.py       # única fronteira nova para iris classes/objetos
```

Responsabilidades de `object_access.py`:

```python
class EmbeddedObjectAccess:
    def open_id(self, class_name: str, object_id: int, *, for_update: bool = False): ...
    def new(self, class_name: str): ...
    def save(self, value) -> int: ...
```

Regras do adapter:

- executar `import iris` apenas na fronteira de infraestrutura;
- resolver classes por mapa fechado de nomes permitidos;
- normalizar `""` de `_OpenId()` para `None`;
- converter `_Id()` para `int` antes de devolver ao domínio;
- chamar `iris.check_status()` depois de cada `_Save()`;
- iniciar transação Embedded antes de qualquer `_Save()`;
- usar `_OpenId(id, 4)` em atualização que será salva;
- não receber nomes de classe, propriedade ou schema provenientes de entrada HTTP;
- não vazar OREFs para DTOs, rotas, RAG ou UI;
- indicar indisponibilidade no caminho DB-API, acionando o SQL já existente.

O `EmbeddedIrisConnection` deverá expor capacidade Object API sem alterar o contrato dos consumidores. Exemplo conceitual:

```text
EmbeddedIrisConnection
    ├── cursor()       -> SQL existente
    ├── objects        -> EmbeddedObjectAccess
    ├── commit()
    ├── rollback()
    └── close()

DB-API connection
    ├── cursor()       -> SQL existente
    └── objects        -> indisponível
```

## 3.5 Fases da operação

### FASE 0 — RECONHECIMENTO E BASELINE

Tarefas:

1. recriar `.venv` a partir dos requirements do projeto;
2. executar unitários, Ruff e mypy;
3. executar integração IRIS atual somente em SQL;
4. registrar respostas JSON dos endpoints de candidato, search e ask;
5. registrar contagens e idempotência de uma fixture controlada;
6. registrar tempo das leituras críticas sem estabelecer meta arbitrária.

Condição para prosseguir:

```text
baseline reproduzível
+ testes atuais verdes
+ nenhum dado de fixture residual
```

### FASE 1 — ADAPTER OBJECT API

Tarefas:

1. criar o adapter centralizado;
2. adicionar detecção explícita de capacidade Embedded;
3. normalizar ausência, IDs e `%Status`;
4. acoplar o adapter ao `EmbeddedIrisConnection`;
5. manter o cursor SQL atual intacto;
6. criar chave de recuo operacional:

```text
IRIS_DATA_ACCESS_MODE=sql|hybrid
```

Durante desenvolvimento, usar `sql` como padrão. Somente mudar o padrão após a fase de paridade.

Condição para prosseguir:

```text
adapter testado isoladamente
+ nenhum import iris em route/service/retrieval
+ fallback DB-API preservado
```

### FASE 2 — LEITURA PONTUAL POR `_OpenId()`

Primeiro objetivo:

```text
CandidateRepository.find_by_id()
```

Fluxo Embedded:

```text
candidate_id
    -> iris.IRISPolitical.Model.Candidate._OpenId(candidate_id)
    -> "" significa não localizado
    -> mapear propriedades para Candidate dataclass
    -> converter _Id() para int
```

Fluxo externo:

```text
candidate_id
    -> SELECT atual
    -> mesmo Candidate dataclass
```

Não migrar nesta fase:

- `find_by_tse_id`;
- `find_by_ids`;
- listas;
- proposições por candidato;
- enriquecimento RAG;
- retrieval.

Condição para prosseguir:

```text
GET /candidates/{id} idêntico nos modos sql e hybrid
+ 404 idêntico para ID ausente
+ nenhum OREF após fechamento do request
```

### FASE 3 — GRAVAÇÃO PILOTO DE `Candidate`

Inserção:

```text
SELECT por TseId continua SQL
    -> ausente
    -> Candidate._New()
    -> atribuir propriedades literais
    -> iniciar transação pelo adapter
    -> status = object._Save()
    -> iris.check_status(status)
    -> int(object._Id())
```

Atualização:

```text
SELECT por TseId continua SQL
    -> obter %ID
    -> Candidate._OpenId(id, 4)
    -> alterar propriedades
    -> _Save()
    -> check_status()
```

Controles:

- `CreatedAt` somente na criação;
- `UpdatedAt` conforme regra atual;
- datas/timestamps devem ser comparados com o caminho SQL real;
- valores opcionais exigem teste de conversão; não assumir que `None` equivale a SQL `NULL`;
- erro de `_Save()` deve provocar rollback da unidade atual;
- índice único de `TseId` continua sendo a defesa final contra corrida.

Condição para prosseguir:

```text
duas ingestões da mesma fixture sem duplicação
+ rollback comprovado
+ JSON/API sem diferença
+ timestamps e nulos equivalentes
```

### FASE 4 — GRAVAÇÃO PILOTO DE `IngestionRun.start`

Objetivo:

- criar `IngestionRun` com `_New()`/`_Save()`;
- obter o ID pela própria instância;
- remover apenas desse método a dependência de `SELECT MAX(ID)`.

Manter SQL para:

- incrementos de contadores;
- transição condicional `RUNNING -> estado final`;
- consultas agregadas.

Condição para prosseguir:

```text
execuções concorrentes recebem IDs próprios
+ contadores e estados finais permanecem corretos
```

### FASE 5 — ENTIDADES COM RELACIONAMENTO E STREAM

Esta fase é opcional e depende de benefício mensurável.

Ordem de ensaio:

1. `PropositionTopic`;
2. `PropositionAuthor`;
3. `Proposition`;
4. `PoliticalHistory`;
5. `ProposalDocument`.

Para cada filho:

- abrir o objeto pai e atribuir a referência à relação `Cardinality = one`, ou manter a coluna relacional em SQL;
- validar que o inverso da relação permanece correto;
- validar locks e tempo de vida do OREF;
- testar idempotência pela chave funcional antes de `_New()`;
- tratar stream por `Write`/`Rewind`, nunca criar e reassociar stream de forma que deixe órfão;
- comparar conteúdo completo e Unicode com o caminho SQL.

Ordem de parada:

```text
se a Object API aumentar complexidade, round-trips ou risco sem ganho funcional,
manter o repository em SQL e encerrar a migração daquela classe.
```

### FASE 6 — CONSOLIDAÇÃO

Tarefas:

1. executar a matriz completa de testes;
2. operar em `hybrid` no ambiente de validação;
3. comparar logs, payloads, contagens e tempos com o baseline;
4. tornar `hybrid` padrão apenas após aceite;
5. manter `sql` como recuo por pelo menos uma versão de entrega;
6. atualizar os documentos históricos com aviso de estado superado, sem apagar seu valor de decisão;
7. atualizar README e diagrama da arquitetura efetiva.

## 3.6 Fogos proibidos

Não executar:

- migração de todas as consultas para `_OpenId()`;
- substituição de busca vetorial ou lexical por iteração de objetos;
- acesso direto a globals;
- `import iris` em rotas Flask, Streamlit, clients HTTP ou RAG;
- remoção imediata de `iris.dbapi`;
- mudança das classes `.cls` apenas para facilitar o adapter Python;
- persistência de relacionamento usando inteiro onde a Object API espera referência;
- uso de `_Save()` sem `check_status()`;
- gravação Object API fora de uma transação controlada;
- alteração simultânea de domínio, API e persistência.

---

# 4. ADMINISTRAÇÃO E LOGÍSTICA

## 4.1 Dependências

Nenhuma biblioteca nova é necessária.

- Embedded: módulo `iris` fornecido pelo ambiente IRIS;
- externo: `intersystems-irispython` continua necessário para DB-API;
- Flask, Pydantic, OpenAI, Streamlit e demais dependências permanecem sem alteração.

## 4.2 Configuração

Manter durante a transição:

```text
IRIS_HOST
IRIS_PORT
IRIS_NAMESPACE
IRIS_USERNAME
IRIS_PASSWORD
IRIS_SQL_SCHEMA
```

Motivo: testes e processos externos ainda dependem do DB-API. No Embedded Python, o namespace continua definido pela Web Application WSGI.

Adicionar somente se a implementação iniciar:

```text
IRIS_DATA_ACCESS_MODE=sql|hybrid
```

## 4.3 Material de teste

- fixture de Candidate com campos obrigatórios, opcionais e acentos;
- Candidate inexistente;
- atualização concorrente controlada;
- IngestionRun concorrente;
- relacionamento pai/filho;
- stream curto, vazio, Unicode e acima do limite de string comum;
- embedding de exatamente 1536 posições pelo caminho SQL.

Todo dado de ensaio integrado deve usar identificador reservado e ser removido na própria fixture.

## 4.4 Recuo

Recuo imediato:

```text
IRIS_DATA_ACCESS_MODE=sql
```

O recuo não pode exigir:

- rollback de schema;
- recompilação de classes;
- transformação de dados;
- mudança de endpoint;
- reinicialização da ingestão histórica.

---

# 5. COMANDO E SINAL

## 5.1 Comando

Autoridade para avançar de fase:

```text
responsável técnico
    confirma testes e paridade
    -> autoriza próxima fase
```

Qualquer diferença de payload, idempotência, rollback ou proveniência interrompe o avanço.

## 5.2 Sinais e observabilidade

Registrar sem dados sensíveis:

- modo de acesso: `sql` ou `hybrid`;
- operação e classe lógica;
- duração;
- sucesso/erro;
- tipo de exceção;
- status convertido por `check_status`;
- rollback executado;
- contagem de registros, quando aplicável.

Não registrar:

- senha;
- payload bruto de fonte externa;
- conteúdo completo de stream;
- embedding;
- prompt integral;
- OREF interno.

## 5.3 Relatório pós-ação

Cada fase deverá produzir:

```text
arquivos alterados
operações migradas
operações mantidas em SQL
testes executados e resultado
diferenças observadas
tempo comparativo
riscos remanescentes
decisão: AVANÇAR | MANTER POSIÇÃO | RECUAR
```

---

# 6. CRITÉRIOS DE ACEITE FINAL

- `import iris` permanece confinado à infraestrutura;
- `_OpenId()` atende leitura pontual por `%ID` no Embedded Python;
- ID inexistente mantém o mesmo `None`/404 do repository atual;
- `_New()`/`_Save()` são usados somente em operações aprovadas;
- todo `%Status` é verificado;
- transações e rollback mantêm atomicidade;
- chaves de idempotência não mudam;
- endpoints e JSON permanecem compatíveis;
- ingestão repetida não cria duplicatas;
- streams permanecem íntegros;
- `%Vector` e retrieval permanecem em SQL;
- caminho DB-API externo continua operacional;
- nenhuma classe `%Persistent` nova é criada;
- nenhum schema é alterado;
- `sql` continua disponível como recuo operacional;
- documentação passa a distinguir estado histórico de estado executável atual.

# 7. RESULTADO FINAL ESPERADO

```text
Object API onde o acesso é individual e orientado a objeto
+
SQL onde o acesso é relacional, vetorial, agregado ou em lote
=
integração nativa com menor risco e sem mudança do comportamento do sistema
```

# 8. RELATÓRIO PÓS-AÇÃO

## 8.1 Situação

```text
MISSÃO: CONCLUÍDA
DECISÃO: AVANÇAR EM MODO HÍBRIDO
RECUO: IRIS_DATA_ACCESS_MODE=sql
```

## 8.2 Operações migradas

- `Candidate.find_by_id`: `_OpenId()`;
- `Candidate.insert`: `_New()` + `_Save()`;
- `Candidate.update` e `save_match`: `_OpenId(%ID, 4)` + `_Save()`;
- `IngestionRun.start`: `_New()` + `_Save()`;
- normalização de `None`, `%Date` e `%TimeStamp` centralizada;
- todo retorno de `_Save()` verificado com `iris.check_status()`.

## 8.3 Operações mantidas em SQL

- filtros, listagens, agregações e upserts relacionais;
- relacionamentos persistentes;
- streams de documentos e JSON;
- `%Vector`, busca lexical, vetorial e fusão híbrida;
- acesso DB-API externo usado pelos testes de integração.

## 8.4 Verificação executada

- `ruff`: aprovado;
- `mypy`: aprovado;
- testes unitários: `53 passed`;
- testes de integração com IRIS: `2 passed`;
- ensaio Embedded Python real: criação, `_OpenId()`, auditoria e rollback aprovados;
- imagens IRIS/API e UI: build aprovado;
- API: saúde, filtros, detalhe, ausência `404`, proposições e busca aprovados;
- UI: saúde aprovada;
- `/ask`: controle final único, executado somente após congelamento das alterações.

## 8.5 Correções decorrentes dos ensaios

- recompilação final conjunta de `Candidate` e `Proposition` adicionada ao provisionamento para eliminar rotina SQL de relacionamento obsoleta;
- teto configurável de candidatos da Câmara preservado em `100`, mantendo compatibilidade com ambientes existentes;
- padrão preservado em `50`; em eventual teste completo do pipeline, usar `CAMARA_MAX_MATCHED_CANDIDATES=20`;
- pipeline externo completo não foi executado nesta ação; persistência, idempotência, streams, vetores e rollback foram cobertos pelos testes controlados.
