# Auditoria da Pipeline de Ingestão

> Projeto: TSE Public Data RAG Explorer
> Auditoria estática: 24/08/2026; validação operacional final: 25/08/2026  
> Escopo: TSE, Câmara dos Deputados, persistência IRIS e reconstrução do índice RAG  
> Regra de evidência: “comprovável” significa derivado diretamente do código ou de
> execuções já registradas no IRIS; “hipótese” exige profiling adicional.

## 1. Resumo Executivo

A pipeline funciona, preserva as chaves de idempotência e utiliza uma única
`requests.Session` no fluxo principal. A lentidão não vem do parsing do CSV do TSE. As
execuções completas já registradas mostram que a etapa Câmara consumiu entre 79,4% e
86,6% do tempo total observado. A causa estrutural é a combinação de milhares de
requisições HTTP sequenciais com persistência e auditoria registro a registro.

Baseline obtido diretamente de `IRISPolitical_Model.IngestionRun` antes das mudanças:

| Execução | TSE candidatos | TSE propostas | Câmara | RAG index | Total | Câmara/total |
|---|---:|---:|---:|---:|---:|---:|
| IDs 1–4 | 4,06 s | 31,67 s | 496,28 s | 41,36 s | 573,37 s | 86,6% |
| IDs 5–8 | 6,28 s | 46,95 s | 414,27 s | 54,15 s | 521,65 s | 79,4% |

Volume observado no baseline:

| Entidade | Registros |
|---|---:|
| Candidate | 1.139 |
| PoliticalHistory | 185 |
| Proposition | 1.241 |
| PropositionAuthor | 4.372 |
| PropositionTopic | 797 |
| ProposalDocument | 20 |
| PoliticalChunk | 2.466 |

Os dois runs Câmara do baseline registraram, respectivamente, 4.418 e 4.431 resultados
de persistência (`created + updated + skipped`). A execução final processou 20.470. Por
isso, a duração absoluta antiga e a nova **não representam o mesmo volume**. A métrica
comparável adotada no fechamento é resultados auditados por segundo, além das contagens
finais por entidade.

Distribuição relevante: 72 candidatos `MATCHED`, 1.060 `UNMATCHED`, média de 40,03 e
máximo de 50 proposições por candidato com proposições; média de 3,54 autores por
proposição. Esses valores explicam o efeito multiplicador do fluxo Câmara.

As três mudanças com maior probabilidade de reduzir o tempo total são:

1. eliminar chamadas Câmara repetidas e buscar, com concorrência limitada, os três
   recursos independentes de cada proposição (`detalhe`, `autores`, `temas`);
2. substituir contadores e resoluções de existência por registro por operações em lote,
   mantendo commits por unidade de negócio;
3. tornar Câmara e RAG incrementais, evitando refazer matching, detalhes e chunks de
   fontes inalteradas.

As duas primeiras mudanças foram implementadas nesta ação, junto com otimizações de
contexto e persistência do RAG. A terceira permanece como evolução P1 porque exige uma
política explícita de atualização das fontes, não apenas uma otimização local.

## 2. Arquitetura Atual

Arquitetura executável encontrada:

```text
python -m app.ingestion.pipeline
    -> IngestionPipeline
       -> HttpClient (requests.Session + tenacity)
       -> TseClient
       -> CamaraClient
       -> mappers/DTOs
       -> repositories
          -> Embedded Python iris.sql + Object API, ou DB-API externo
          -> classes IRISPolitical.Model.*
       -> ChunkIndexPipeline
          -> TokenChunker
          -> OpenAI embeddings
          -> PoliticalChunk.%Vector
```

O composition root está em `app/ingestion/pipeline.py:48`. A fábrica de conexão escolhe
Embedded Python quando o módulo `iris` expõe `sql`, e DB-API em execução externa
(`app/database/connection.py:114`). O modo `hybrid` usa Object API somente para
`Candidate` e `IngestionRun`; operações relacionais, streams e vetores permanecem em
SQL.

A separação client → mapper → repository é real. A principal exceção está na construção
de chunks de proposição: antes da refatoração, o builder consultava autores e temas no
IRIS, escondendo I/O dentro de uma transformação (`political_chunk_builder.py`, método
`proposition`). A execução otimizada passa os dados carregados em lote.

## 3. Fluxo Atual da Pipeline

### Câmara

```text
CandidateRepository.list_for_matching
    -> lista deputados da UF (cache por UF)
    -> matching local por nome
    -> GET detalhe para cada deputado candidato ao match
    -> GET histórico para pontuação partidária
    -> save_match + commit
    -> para MATCHED, até CAMARA_MAX_MATCHED_CANDIDATES
       -> histórico + mandatos
       -> janelas trimestrais de proposições, até o limite configurado
       -> [concorrência limitada]
          -> detalhe da proposição
          -> autores
          -> temas
       -> persistência serial por proposição
    -> ChunkIndexPipeline
```

Responsabilidades e custos:

| Etapa | Entrada | Saída | Dependências | Custo provável | Gargalo |
|---|---|---|---|---|---|
| Matching | Candidate | MatchResult | Câmara + normalização | rede por candidato/resumo | alto |
| Histórico | deputy id | HistoryWrite | Câmara | rede + upserts | médio |
| Listagem | deputy id | PropositionSummary | Câmara paginada/janelas | rede sequencial | alto |
| Pacote proposição | CamaraId | detalhe/autores/temas | 3 endpoints | 3 chamadas por proposição | crítico |
| Persistência | DTOs | entidades IRIS | repositories | vários comandos por entidade | alto |
| Chunks | entidades persistidas | PoliticalChunk | IRIS + tiktoken | varredura completa | alto |
| Embeddings | chunks pendentes | `%Vector` | OpenAI + IRIS | rede em batch + update unitário | médio/alto |

### TSE

```text
CKAN package_show
    -> download streaming do ZIP de candidatos
    -> validação ZIP
    -> CSV Latin-1
    -> filtro de ano/UF/cargo
    -> Candidate upsert em transações de 500
    -> download dos ZIPs de propostas
    -> leitura e extração PDF
    -> associação por SQ_CANDIDATO
    -> ProposalDocument upsert por Candidate + DocumentHash
    -> ChunkIndexPipeline
```

O download usa streaming e SHA-256 (`app/ingestion/tse/client.py`, método `download`). O
CSV, porém, é materializado integralmente em uma lista (`parser.py:46`) e os filtros só
são aplicados depois (`pipeline.py`, método `_tse_candidates`). O “lote de 500” agrupa a
transação, mas não executa bulk insert/upsert.

## 4. Pontos de Entrada

| Entrada | Arquivo | Função | Comportamento |
|---|---|---|---|
| pipeline completa | `app/ingestion/pipeline.py:434` | `main()` | TSE candidatos → propostas → Câmara → RAG |
| reconstrução RAG | `app/ingestion/chunk_index.py:183` | `main()` | relê fontes persistidas e indexa |
| comando oficial | `README.md`, seção 6 | `irispython -m app.ingestion.pipeline` | execução no namespace IRISAPP |
| Docker/IPM | `Dockerfile`, `iris.script`, `module.xml` | build/provisionamento | instala classes, app e WSGI |

## 5. Fluxo de Dados

| Fluxo | Entrada | Normalização | Persistência | Chave de idempotência |
|---|---|---|---|---|
| TSE candidato | linha CSV | sentinelas, inteiros, uppercase | Candidate | `TseId` |
| TSE proposta | PDF | texto por página + SHA-256 | ProposalDocument | `Candidate + DocumentHash` |
| Câmara histórico | JSON | datas + JSON canônico | PoliticalHistory | `Candidate + ExternalId` |
| Câmara proposição | JSON | datas, título e status | Proposition | `CamaraId` |
| Câmara autor | JSON | id da URI + principal | PropositionAuthor | URI ou nome/tipo no repository |
| Câmara tema | JSON | código + nome | PropositionTopic | `Proposition + Name` |
| fonte textual | entidade IRIS | tokenização + hash | PoliticalChunk | origem + índice + hash |
| chunk | texto | embedding 1.536 dimensões | `%Vector` | `Embedding IS NULL` |

## 6. Gargalos Encontrados

### Críticos

| Evidência | Local | Comportamento atual/original | Impacto | Solução |
|---|---|---|---|---|
| comprovável + medido | `pipeline.py:_candidate_camara`; `camara/client.py:124–138` | três GETs sequenciais por proposição | Câmara representa 79–87% do total | concorrência limitada apenas para coleta; persistência continua serial |
| comprovável | `pipeline.py:_record`; `ingestion_run_repository.py:49` | um `UPDATE IngestionRun` por resultado/linha | milhares de round trips sem valor transacional adicional | acumular e executar um UPDATE por unidade transacional |
| comprovável | repositories `upsert` | `SELECT → INSERT/UPDATE`, frequentemente seguido de outro `SELECT` | 2–3 comandos por entidade | pré-carregar chaves, operações batch e retorno de IDs em conjunto |
| comprovável | toda a pipeline | nenhuma consulta a checkpoint/watermark | toda reexecução refaz matching, HTTP e indexação | incremental com política de frescor e checkpoint |

### Altos

| Evidência | Local | Problema | Solução |
|---|---|---|---|
| comprovável | `candidate_matcher.py:42` + `pipeline.py:_candidate_camara` | histórico era chamado no score e novamente na ingestão | cache por deputy id |
| comprovável | `proposition_author_repository.py:11` | para cada autor, lia todos os autores e relia após insert; custo de linhas O(A²) | `upsert_many` com duas leituras por proposição |
| comprovável | `chunk_index.py:_rebuild` | duas queries por proposição para nomes de autores/temas | contextos em lote por `IN (...)` |
| comprovável | `political_chunk_repository.py:12` | cada chunk repetia consulta de existência e consulta pós-insert | usar a leitura da origem como mapa e reler uma vez após inserts |
| comprovável | `chunk_index.py:_rebuild` | reconstrói todas as fontes em toda execução | selecionar fontes alteradas desde último RAG_INDEX bem-sucedido |
| comprovável | `proposal_document_repository.py:57` | materializa todos os documentos e lê stream em fragmentos de 30k com N queries | iterador/paginação e stream reader dedicado |

### Médios

| Evidência | Local | Problema | Solução |
|---|---|---|---|
| comprovável | `parser.py:46–54` | CSV nacional inteiro em memória | generator + filtro durante leitura |
| comprovável | `proposal_reader.py:39` | todos os PDFs/textos de um ZIP são materializados | iterator; hash/identidade antes da extração |
| comprovável | `repositories/base.py:20–43` | cursor novo por comando, sem prepared statement/executemany | cursor por lote quando suportado |
| comprovável | `PoliticalHistory.cls:38–42` | upsert consulta `(Candidate, ExternalId)`, mas não existe índice composto | índice composto validado por plano de consulta |
| comprovável | `pipeline.py` | commit de match por candidato e de proposta por PDF | agrupar unidades seguras mantendo rollback local |

### Baixos

| Evidência | Local | Problema | Solução |
|---|---|---|---|
| comprovável | `settings.py` | `camara_match_start_date` não é consumido | remover após validar compatibilidade externa |
| comprovável | `settings.py` | `tse_portal_url`, `embedding_provider`, `llm_provider` não controlam a ingestão | documentar como reservado ou remover |
| hipótese | normalizações | pequenas conversões repetidas | só otimizar se profiling apontar CPU relevante |

## 7. Gargalos que Precisam de Profiling

Não é possível atribuir, sem instrumentação, a fração exata da etapa Câmara entre rede,
JSON/Pydantic, SQL, Object API e commits. Devem ser medidos:

- latência p50/p95/p99 por endpoint da Câmara;
- tempo total de retry/backoff e incidência de 429;
- tempo e contagem de cada classe de SQL;
- custo de `_OpenId/_Save` versus SQL no upsert de Candidate;
- tempo de extração por PDF e páginas/segundo;
- tempo de tokenização e memória máxima;
- tempo da OpenAI por lote e tempo de persistência dos vetores;
- planos de consulta de `PoliticalHistory` e `PoliticalChunk`.

Hipóteses que não devem ser tratadas como fato: “IRIS é lento”, “Object API é mais
rápida que SQL”, “PDF é o maior custo” e “mais workers sempre melhora”.

## 8. Consultas e Round Trips ao IRIS

Estimativa estática do caminho original:

| Unidade | Comandos mínimos aproximados |
|---|---:|
| candidato TSE inalterado | `RecordsRead UPDATE + SELECT Candidate + counter UPDATE` = 3 |
| candidato novo em hybrid | anteriores + `_Save` = 4 |
| proposição nova sem filhos | `SELECT + INSERT + SELECT + counter` = 4 |
| tema novo | `SELECT + INSERT + SELECT + counter` = 4 |
| autor novo | duas leituras de todos os autores + insert + counter = 4 |
| chunk novo | leitura da origem + `SELECT + INSERT + SELECT + counter` |
| embedding | um UPDATE do vetor + um UPDATE de contador por chunk |

Após a implementação desta ação:

- contadores são consolidados por transação;
- autores/temas são resolvidos uma vez por proposição;
- chunks existentes são resolvidos pela leitura já necessária da origem;
- embedding ainda usa um UPDATE por vetor, mas o contador é atualizado por lote.

Próximo passo de maior retorno no IRIS: staging temporário por lote e operações SQL de
conjunto (`INSERT` dos ausentes e `UPDATE` dos alterados), mantendo índices únicos como
última defesa de idempotência. `MERGE` só deve ser adotado após teste na versão IRIS
2026.2 usada pelo projeto.

## 9. Análise da Persistência

Pontos positivos:

- queries parametrizadas;
- transações explícitas e rollback;
- HTTP fora das transações de gravação;
- chaves externas e índices únicos nas entidades centrais;
- vetores e streams permanecem no caminho SQL adequado;
- uma falha de proposição não desfaz outras proposições já confirmadas.

Pontos de atenção:

- “batch de 500” de candidatos é batch de commit, não bulk persistence;
- `PoliticalHistory` não tem unicidade física em `(Candidate, ExternalId)`;
- `PropositionAuthor` depende de regra Python sem índice único equivalente;
- `SourceCollectedAt` de Candidate não muda quando os campos comparados permanecem
  iguais, pois `_same` não inclui a data;
- atualizações de filhos que desapareceram da API não os removem; upsert não equivale a
  sincronização completa;
- a contagem `RecordsRead` da Câmara conta candidatos, enquanto created/updated/skipped
  inclui filhos. As métricas não compartilham a mesma unidade.

## 10. Análise das Chamadas HTTP

`HttpClient` implementa pooling via `requests.Session`, timeout de conexão/leitura,
retry limitado, backoff, jitter e respeito a `Retry-After` numérico. Não há sleeps fixos.

Problemas encontrados:

- detalhe e histórico eram repetidos quando o mesmo deputy aparecia novamente;
- histórico era duplicado entre matching e ingestão;
- cada proposição exigia três chamadas independentes executadas serialmente;
- 404/erro durante matching ou histórico do candidato aborta toda a etapa Câmara; apenas
  erros dentro do loop de proposições são isolados;
- `Retry-After` no formato HTTP-date não é interpretado;
- o cliente de coleção materializa cada coleção em lista.

Mudança aplicada: cache por `deputy_id` e pool configurável de 1–16 workers (padrão 6)
para os pacotes de proposições. Cada worker possui sua própria Session; não há Session
compartilhada entre threads. A persistência e os commits permanecem no thread principal.

## 11. Análise de Paginação

A paginação segue corretamente `links[rel=next]` e valida HTTPS/host oficial. O page size
é 100, máximo aceito pela Câmara. A implementação atual usa janelas trimestrais de até
quatro anos e limite de 50 proposições por candidato, divergindo dos documentos antigos
que prometem percorrer todas as proposições.

Trade-off atual: o teto protege a edição Community e o tempo de demonstração, porém os
dados são uma amostra recente, não o histórico integral. O critério de aceite deve dizer
“todas as páginas dentro da janela e até o teto configurado”, não “todas as páginas” sem
qualificação.

## 12. Código Desnecessário / Duplicado

| Item | Situação | Recomendação segura |
|---|---|---|
| `camara_match_start_date` | legado sem uso | remover em mudança de configuração versionada |
| `tse_portal_url` | reservado, não ingerido | manter só se API/UI o consumirá; caso contrário remover |
| `embedding_provider`/`llm_provider` | não escolhem implementação | validar roadmap; remover ou implementar factory real |
| normalização de nomes | existe em client e matcher | consolidar função pura sem criar `utils.py` genérico |
| `upsert` unitário de autor/tópico | ainda útil para testes/uso pontual | manter; pipeline usa `upsert_many` |
| documentos históricos de arquitetura | descrevem estados anteriores | não apagar; marcar claramente como histórico |

Nenhuma classe persistente é inútil no fluxo atual. Os métodos batch de contexto dos
repositories são usados pelo RAG e agora também servem de modelo para a indexação.

## 13. Problemas de Clean Code

- `IngestionPipeline` coordena quatro pipelines, workers, métricas e tratamento de falha;
  são múltiplos motivos de mudança (`pipeline.py:51–433`).
- `_candidate_camara` combina coleta, filtro, concorrência, mapping, persistência e
  auditoria. Deve ser dividido por responsabilidade depois que a baseline estiver verde.
- `ChunkIndexPipeline._rebuild` mistura reparo de dados, leitura, chunking, persistência,
  embedding e encerramento do run.
- `UpsertResult.action` é `str`; um Enum eliminaria estados inválidos.
- contadores de `IngestionRun` têm semântica inconsistente entre etapas.
- o builder de chunks possuía efeitos colaterais de banco escondidos; o caminho otimizado
  já injeta os nomes em lote, mas a dependência antiga ainda existe por compatibilidade.
- repositories repetem manualmente padrão de upsert; uma abstração genérica não é
  recomendada, mas helpers locais de batch e chaves explícitas reduzem duplicação.

## 14. Object Calisthenics

Aplicação pragmática recomendada:

- retornos antecipados já são bem usados em clients e repositories;
- separar `_candidate_camara` em “collect bundle”, “persist history” e “persist
  proposition bundle” reduzirá indentação e facilitará testes;
- encapsular contadores em `RunCounters` em evolução futura, em vez de espalhar nomes de
  colunas;
- não criar value object para todo `str`/`int`;
- não criar uma classe por endpoint;
- manter DTOs imutáveis com `slots`, prática já presente no domínio;
- preferir coleção encapsulada somente quando houver invariantes reais, como um lote de
  uma única proposição ou uma única origem de chunks.

## 15. Arquitetura Proposta

```text
IngestionApplication
  ├── TseCandidateStage
  │     └── CSV iterator -> CandidateBatch -> CandidateRepository.bulk_upsert
  ├── TseProposalStage
  │     └── PDF metadata/hash -> changed only -> extract -> DocumentBatch
  ├── CamaraStage
  │     ├── DeputyCatalogCache
  │     ├── CandidateMatcher
  │     ├── CamaraChangePlanner
  │     └── bounded FetchPool -> validated bundles -> serial BatchWriter
  └── RagIndexStage
        └── changed sources -> pure ChunkBuilder -> ChunkBatch -> EmbeddingBatch

Cross-cutting
  ├── CheckpointRepository
  ├── IngestionMetrics
  ├── Retry/RateLimitPolicy
  └── IRIS repositories (set-based SQL + Object API pontual)
```

Não é necessária reescrita. A evolução pode manter os módulos e repositories atuais,
extraindo stages e adicionando métodos batch de forma incremental.

## 16. Estratégia de Batch

Valores iniciais recomendados:

| Operação | Lote inicial | Motivo |
|---|---:|---|
| Candidate | 500 | já é limite transacional; converter para resolução/persistência em conjunto |
| ProposalDocument | 20–50 | texto pode ser grande; limitar memória/rollback |
| proposição + filhos | 1 bundle por transação; 25 bundles por flush de métricas | isola falha da proposição |
| chunks | uma origem por transação | substituição atômica da origem |
| embeddings HTTP | 50 | padrão atual e compatível com memória |
| updates vetoriais | mesmo lote de 50 | um commit e um incremento de contador |

O tamanho deve ser ajustado por registros/s, p95 de commit e memória, não por palpite.
Rollback continua limitado à unidade funcional. Staging deve incluir `run_id` e chave da
fonte para limpeza/reentrada segura.

## 17. Processamento Incremental

Estado atual: não há checkpoint, watermark nem consulta ao último `SourceHash`. O
`IngestionRun` é auditoria, não mecanismo de retomada.

Estratégia alvo:

1. TSE candidatos: comparar `metadata_modified`, ETag/Last-Modified quando fornecido e
   `SourceHash`; pular parse/upsert se artefato e parâmetros forem idênticos.
2. TSE PDFs: ler nome e hash antes de `PdfReader`; se `Candidate + DocumentHash` existir,
   não extrair texto novamente.
3. Câmara matching: rematch somente candidatos novos, alterados ou com TTL expirado.
4. Câmara proposições: listar IDs; buscar existentes em conjunto; detalhar novos e
   atualizar existentes apenas conforme TTL/política de frescor.
5. RAG: selecionar entidades com `UpdatedAt` posterior ao último RAG_INDEX bem-sucedido;
   substituir chunks somente dessas origens.
6. Persistir checkpoint somente depois do commit do lote correspondente.

Como a API Câmara não oferece no código um watermark global confiável, incrementalidade
deve usar uma política explícita de frescor, com opção de `--full-refresh`.

## 18. Concorrência

Classificação:

- I/O bound: GETs de detalhe/autores/temas e embeddings;
- database bound: upserts e vetores, mantidos serialmente até profiling de locks;
- CPU bound: PDF e tiktoken; volume atual não justifica multiprocessing.

Implementado: `ThreadPoolExecutor` configurável por `CAMARA_HTTP_WORKERS`, padrão 6,
somente para os três GETs de cada proposição. Cada worker usa cliente/Session próprio.
Não há escrita concorrente no IRIS.

Controles de aceite:

- nenhum aumento de 429/5xx/retries;
- resultado idempotente igual com 1 e 6 workers;
- permitir reduzir para 1 sem alterar código;
- testar 4, 6 e 8; não exceder 16;
- reduzir automaticamente/adotar backpressure se a fonte sinalizar rate limit.

## 19. Observabilidade e Profiling

Instrumentação mínima a adicionar:

```text
stage, operation, source, run_id
elapsed_ms
records/pages/batches
http_requests, http_retries, status
iris_statements, iris_rows, commits, rollbacks
bytes_downloaded, pdf_pages
embedding_items, embedding_tokens
rss_mb
```

Histogramas: HTTP por endpoint, SQL por operação, commit, PDF por documento, embedding
por batch. Contadores: registros/s, páginas/s, retries, duplicados, falhas, round trips.

O baseline desta auditoria usa `StartedAt/FinishedAt`, suficiente para localizar a etapa
dominante, mas não para separar rede de banco. Os logs atuais não registram `elapsed_ms`.

## 20. Quick Wins

| Ordem | Mudança | Estado | Benefício |
|---:|---|---|---|
| 1 | acumular contadores por transação | implementado | remove milhares de UPDATEs |
| 2 | cachear detalhe/histórico por deputado | implementado | remove GETs duplicados |
| 3 | buscar bundle de proposição com workers limitados | implementado | sobrepõe espera de rede |
| 4 | upsert de autores/temas com uma leitura por proposição | implementado | elimina releituras O(A²) |
| 5 | autores/temas em lote para chunks | implementado | elimina 2N queries |
| 6 | reutilizar mapa de chunks existentes | implementado | elimina SELECT por chunk |
| 7 | PDF hash antes da extração | planejado | economiza CPU em reexecução |
| 8 | filtro incremental de fontes/chunks | planejado | evita reconstrução completa |

## 21. Plano de Refatoração

### Fase 1 — Medição e baseline

- Arquivos: `IngestionRun`, pipeline, logs.
- Alteração: tempos e contagens por subetapa.
- Teste: comparar soma de subetapas com tempo total.
- Aceite: diferença inferior a 5%; nenhuma informação sensível.

### Fase 2 — Round trips redundantes

- Arquivos: pipeline e repositories.
- Alteração: `increment_many`, `upsert_many`, mapas de existência.
- Benefício: menos comandos Python → IRIS.
- Risco: contadores e IDs incorretos.
- Teste: unitário + duas cargas idênticas + contagens SQL.
- Aceite: segunda carga sem duplicatas; contadores coerentes.

### Fase 3 — HTTP Câmara

- Arquivos: `camara/client.py`, matching, pipeline, settings/Compose.
- Alteração: cache e concorrência limitada de leitura.
- Risco: rate limit e ordem não determinística de chegada.
- Teste: 1 versus 6 workers, mesmas entidades/chaves.
- Aceite: zero perda/duplicidade, redução do tempo Câmara.

### Fase 4 — Incrementalidade

- Arquivos: pipeline, repositories, `IngestionRun` ou checkpoint dedicado.
- Alteração: hash/TTL/watermark e `--full-refresh`.
- Risco: deixar de captar atualização legítima.
- Teste: nova fonte, fonte igual, fonte alterada, falha no meio e retomada.
- Aceite: fonte igual faz trabalho mínimo; delta é aplicado; full refresh preservado.

### Fase 5 — Batch/staging IRIS

- Arquivos: repositories e, se necessário, classes/tabelas de staging.
- Alteração: resolução e persistência set-based.
- Risco: SQL específico e tamanho transacional.
- Teste: 1, 100, 500, duplicados e rollback.
- Aceite: mesmas regras/idempotência, menos statements e maior throughput.

### Fase 6 — Simplificação estrutural

- Arquivos: `pipeline.py`, `chunk_index.py`, builders.
- Alteração: stages pequenos, builder puro, métricas encapsuladas.
- Risco: regressão por movimentação de código.
- Teste: contratos existentes e snapshots de DTOs.
- Aceite: nenhuma mudança funcional; menor complexidade ciclomática.

## 22. Matriz Impacto × Complexidade × Risco

| Prioridade | Mudança | Impacto performance | Complexidade | Risco |
|---|---|---:|---:|---:|
| P0 | concorrência limitada no bundle Câmara | muito alto | média | médio |
| P0 | contadores de run consolidados | alto | baixa | baixo |
| P0 | cache detalhe/histórico | alto | baixa | baixo |
| P0 | autores/temas batch | alto | média | baixo |
| P0 | profiling por subetapa/round trip | indireto alto | média | baixo |
| P1 | Câmara incremental com TTL/full refresh | muito alto | média | médio |
| P1 | RAG somente de fontes alteradas | alto | média | médio |
| P1 | Candidate bulk upsert/staging | médio | média | médio |
| P1 | hash PDF antes de extração | médio | baixa | baixo |
| P1 | índice `(Candidate, ExternalId)` | médio | baixa | baixo/médio |
| P2 | iteradores para CSV/PDF/streams | baixo no volume atual | média | baixo |
| P2 | prepared statements/cursor por lote | médio | média | médio |
| P3 | multiprocessing de PDF/tokenização | incerto | alta | alto |

## 23. Arquivos que Devem Ser Modificados

Modificados nesta ação:

- `app/config/settings.py`: número de workers Câmara;
- `docker-compose.yml`: encaminhamento de `CAMARA_HTTP_WORKERS`;
- `app/ingestion/http.py`: fechamento explícito da Session;
- `app/ingestion/camara/client.py`: caches por deputado;
- `app/ingestion/pipeline.py`: contadores consolidados e coleta concorrente;
- `app/ingestion/chunk_index.py`: contextos e métricas em lote;
- `app/ingestion/chunking/political_chunk_builder.py`: contexto pré-carregado;
- `app/repositories/ingestion_run_repository.py`: `increment_many`;
- `app/repositories/proposition_author_repository.py`: `upsert_many`;
- `app/repositories/proposition_topic_repository.py`: `upsert_many`;
- `app/repositories/political_chunk_repository.py`: mapa por origem;
- `.env.example` e `README.md`: configuração e operação de `CAMARA_HTTP_WORKERS`;
- testes de settings, HTTP, banco e lote seguro de contexto do RAG;
- este documento.

Próximos arquivos prováveis: TSE parser/proposal reader, repositories de Candidate e
Proposition, classes/índices IRIS e README.

## 24. Código que Pode Ser Removido

Remoção imediata não foi feita para não quebrar configuração externa. Candidatos:

- `Settings.camara_match_start_date`: remover junto com `.env.example`, Compose e docs
  após confirmar que nenhum operador o utiliza;
- `Settings.tse_portal_url`: remover se não houver link de UI planejado;
- providers declarativos sem factory: implementar ou remover;
- fallback de consulta interna do `PoliticalChunkBuilder`: remover depois que todos os
  chamadores fornecerem contexto em lote;
- pseudocódigos/documentos superados: não apagar; adicionar cabeçalho “histórico”.

## 25. Critérios de Performance

Critérios para a reconstrução limpa desta ação:

- build completo sem cache funcionalmente válido;
- IRIS saudável e `/api/health` HTTP 200;
- dependências sem conflito (`pip check`);
- unitários, lint e mypy aprovados;
- pipeline TSE/Câmara/RAG termina sem run `RUNNING` residual da nova execução;
- nenhuma duplicata segundo as chaves documentadas;
- embeddings com 1.536 dimensões e nenhum chunk pendente quando houver chave;
- Câmara inferior ao melhor baseline de 414,27 s somente para volume comparável;
- quando o volume diferir, alvo de aumento de pelo menos 30% no throughput da Câmara;
- TSE candidatos não piora mais de 20% sobre 6,28 s;
- RAG index não piora sobre 54,15 s para volume comparável;
- segunda execução idempotente reduz trabalho de banco e não altera contagens; a
  reexecução integral pode ser dispensada por orientação operacional explícita.

Comparações só são válidas com parâmetros, conectividade e volume registrados. Se o
volume da fonte mudar, também serão informados requisições, candidatos e proposições.

## 26. Arquitetura Alvo

```text
Official Source
    -> pooled/retrying client
    -> validated page/artifact iterator
    -> change planner (hash/watermark/TTL)
    -> bounded fetch pool for independent HTTP only
    -> pure mapper/validator
    -> domain batch
    -> IRIS set-based repository
    -> transactional checkpoint + aggregated metrics
    -> changed-source chunk builder
    -> embedding batch
    -> vector batch persistence
```

### Resposta objetiva à pergunta principal

O tempo medido está concentrado na Câmara: 414–496 segundos por execução completa,
79–87% do total. O código mostra que essa etapa multiplica chamadas por candidato e por
proposição e, originalmente, intercalava cada resultado com consultas/upserts e updates
de contador individuais. RAG index (34–54 s em execuções observadas) e extração de
propostas TSE (20–47 s) são os custos secundários; candidatos TSE consomem apenas 4–6 s.

As três ações prioritárias são: (1) reduzir e sobrepor de forma controlada os GETs da
Câmara; (2) persistir e auditar em lotes/set-based, reduzindo round trips; (3) processar
somente deltas em Câmara, TSE/PDF e RAG. A primeira e parte substancial da segunda foram
implementadas. A execução limpa comprovou o ganho de throughput da Câmara; a terceira
continua necessária para reduzir o custo absoluto e o número de chamadas de embeddings.

### Registro de execução pós-refatoração

#### Ciclos executados

1. O ambiente legado foi derrubado com `docker compose down --volumes
   --remove-orphans`; contêineres, rede e volume foram removidos e a ausência foi
   conferida.
2. As imagens foram reconstruídas sem cache, o IRIS/IPM compilou as oito classes da
   aplicação, as dependências Python foram instaladas e `pip check` passou.
3. No primeiro ciclo limpo, TSE e Câmara concluíram, mas o RAG falhou de forma real com
   `RuntimeError: Arg stack` ao enviar 2.753 IDs em um único `IN` ao Embedded SQL.
4. A causa raiz foi corrigida no código: contextos de autor e tema são carregados em
   lotes de no máximo 200 IDs. A correção foi validada sobre os dados coletados: 4.425
   chunks, 4.425 embeddings e zero pendências.
5. Esse ambiente diagnóstico foi removido por completo. Um segundo build sem cache e
   um volume novo foram criados; a pipeline integral final terminou com todos os quatro
   runs em `SUCCESS`. Por orientação posterior, não houve um terceiro teardown nem uma
   segunda execução integral sobre o banco final.

#### Alterações efetivamente realizadas

- contadores de `IngestionRun` consolidados por transação via `increment_many`;
- cache por deputado para detalhe e histórico Câmara;
- pool limitado e configurável por `CAMARA_HTTP_WORKERS` para os três GETs independentes
  de cada proposição, com uma sessão HTTP por worker e fechamento explícito;
- `upsert_many` de autores e temas, incluindo deduplicação dentro do próprio payload;
- carregamento em lote de autores/temas para o chunk builder, eliminando o N+1;
- divisão dos IDs de contexto em lotes seguros para o limite de argumentos do IRIS;
- reutilização do mapa de chunks já existentes em `replace_source`;
- agregação das métricas de criação/skip do RAG e de embeddings por lote;
- nova configuração documentada `CAMARA_HTTP_WORKERS=6`;
- testes para limites de settings, cache HTTP, contadores consolidados e batches de 200.

#### Problemas encontrados e correções

| Problema observado | Causa raiz | Tratamento definitivo |
|---|---|---|
| RAG `FAILED` com `Arg stack` | `IN` único com 2.753 parâmetros excedia a pilha de argumentos do Embedded SQL | loader de contexto em batches de 200 e teste com 450 IDs (`200/200/50`) |
| risco de duplicata em `upsert_many` | duas ocorrências novas iguais não estavam presentes no snapshot inicial do banco | deduplicação determinística por URI ou nome/tipo de autor e por nome de tema |
| `PoliticalChunk` vazia durante a execução | estado esperado: a pipeline ainda estava na etapa Câmara | nenhuma correção artificial; aguardou-se o `RAG_INDEX` e o commit final |
| avisos `Ignoring wrong pointing object` | referências internas defeituosas em PDFs oficiais do TSE | avisos mantidos para auditoria; os 20 PDFs foram extraídos e persistidos sem falha |
| `%Vector` não materializável diretamente pelo cursor Embedded SQL | limitação do iterador do driver para esse tipo | validação pela restrição `LEN=1536`, guarda de 1.536 valores no repository, zero nulos e consulta `VECTOR_COSINE` funcional |

O startup também informou expansão automática dos buffers/banco e diretórios de journal
iguais. São avisos da imagem Community/configuração de desenvolvimento; não houve erro de
aplicação, transação aberta ou perda de dado.

#### Resultado do ambiente final limpo

Parâmetros auditados: eleição 2026; UFs `SP,BR`; cargos `DEPUTADO FEDERAL`,
`GOVERNADOR`, `PRESIDENTE`; lookback Câmara 4 anos; máximo 100 candidatos
correspondentes, 50 proposições e 10 autores; 6 workers HTTP; chunks `700/100` tokens;
embeddings `text-embedding-3-small`, batches de 50 e dimensão 1.536.

| Run | Status | Lidos | Criados | Atualizados | Ignorados | Falhos | Duração |
|---|---|---:|---:|---:|---:|---:|---:|
| TSE_CANDIDATES | SUCCESS | 20.721 | 1.139 | 0 | 19.582 | 0 | 0,59 s |
| TSE_PROPOSALS | SUCCESS | 20 | 20 | 0 | 0 | 0 | 25,11 s |
| CAMARA | SUCCESS | 1.139 | 12.369 | 644 | 7.457 | 0 | 932,94 s |
| RAG_INDEX | SUCCESS | 3.172 fontes | 4.425 | 4.425 embeddings | 0 | 0 | 141,98 s |

Tempo somado dos runs: 1.100,62 s (18 min 20,62 s). O tempo externo total inclui ainda
descoberta/download inicial e foi aproximadamente 1.103,64 s.

| Entidade final | Registros |
|---|---:|
| Candidate | 1.139 |
| PoliticalHistory | 399 |
| Proposition | 2.753 |
| PropositionAuthor | 7.351 |
| PropositionTopic | 1.866 |
| ProposalDocument | 20 |
| PoliticalChunk | 4.425 |

Distribuição de chunks: 2.755 `PROPOSITION`, 1.271 `GOVERNMENT_PROPOSAL` e 399
`POLITICAL_HISTORY`. Todos os 4.425 usam `text-embedding-3-small`; não há embedding,
conteúdo ou texto de documento ausente.

#### Performance antes/depois

| Etapa | Baseline | Final | Comparação válida |
|---|---:|---:|---|
| TSE candidatos | 4,06–6,28 s | 0,59 s | 85,5% menor que o melhor baseline |
| TSE propostas | 31,67–46,95 s | 25,11 s | 20,7% menor que o melhor baseline |
| Câmara | 414,27–496,28 s para 4.418–4.431 resultados | 932,94 s para 20.470 resultados | 21,94 resultados/s contra 8,90–10,70: ganho de 105,1% a 146,5% |
| RAG | 41,36–54,15 s para 2.466 chunks | 141,98 s para 4.425 chunks | 31,17 chunks/s contra 45,54–59,62: alvo não atingido |

A duração absoluta da Câmara cresceu porque o run final auditou aproximadamente 4,6
vezes mais resultados; normalizada pelo volume, superou com margem o alvo de 30%. O RAG
teve 79,4% mais chunks e 89 chamadas externas de embeddings. Mesmo normalizado, ficou
31,6% a 47,7% abaixo do throughput antigo. A causa dominante observada é o custo serial
dos batches externos e das atualizações vetoriais individuais, não o antigo N+1 de
contexto. As próximas ações P1 são indexação somente de fontes alteradas, batch de
embeddings maior após ensaio de limite e persistência vetorial em lote.

#### Critérios de aceite

| Critério | Resultado |
|---|---|
| teardown comprovado, build sem cache e instalação do zero | aprovado |
| IRIS/UI saudáveis, 8 classes, WSGI e dependências válidas | aprovado |
| lint, mypy, unitários, integração e smoke | aprovado: 60 testes |
| coleta TSE/Câmara, transformação, persistência e RAG completos | aprovado; quatro runs `SUCCESS` |
| duplicatas, órfãos, anos inválidos, runs `RUNNING` | aprovado: zero em todas as verificações |
| 1.536 dimensões, embeddings pendentes e busca vetorial | aprovado: guarda no código/schema, zero pendentes e busca real retornando resultados |
| ganho mínimo de 30% na Câmara para volume comparável | aprovado por throughput: +105,1% a +146,5% |
| TSE sem regressão | aprovado |
| RAG sem regressão para volume comparável | não aprovado; mantido como P1 mensurado, sem mascarar o resultado |
| reexecução integral idempotente no banco final | não executada por orientação posterior; coberta parcialmente por índices únicos, zero duplicatas e testes de integração |

O repositório e o ambiente final permanecem funcionais: IRIS e UI estão ativos, a API de
candidato retornou 50 proposições para o caso validado e a busca híbrida/vetorial
retornou três chunks com score, confirmando conectividade até `PoliticalChunk.Embedding`.
