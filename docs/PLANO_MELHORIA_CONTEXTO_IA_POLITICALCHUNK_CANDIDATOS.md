# ORDEM DE OPERAÇÕES — Contexto RAG e descoberta de candidatos

> **Missão:** carregar candidatos, chunks e dados das propostas antes de chamar o modelo.  
> **Área de atuação:** `app/rag`.  
> **Restrição:** não criar ou alterar tabelas e classes `.cls`.

```text
SITUAÇÃO: APROVADA, EXECUTADA E VALIDADA
EFEITO: DESCOBERTA POR CANDIDATO OPERACIONAL COM candidateId NULO
PERSISTÊNCIA IRIS: SEM ALTERAÇÕES
```

---

# 1. SITUAÇÃO ANTERIOR À EXECUÇÃO

O fluxo atual do Ask está concentrado em:

```text
app/rag/service.py
app/rag/prompt.py
```

## 1.1 Fluxo atual

```text
pergunta + candidateId opcional
        │
        ▼
RagService.ask()
        │
        ├── plan_query(question)
        │
        ├── CandidateRepository.find_by_id(candidateId), quando informado
        │
        ├── HybridSearch.search(question, candidateId)
        │
        ├── valida evidence.candidate_id
        │
        ├── build_prompt(candidate, evidence)
        │
        └── language_model.generate()
```

## 1.2 O que já funciona

O candidato já é carregado:

```python
candidate = self._candidate(candidate_id)
```

Os chunks já são consultados por candidato:

```python
self.retrieval.search(
    question,
    candidate_id=candidate_id,
    top_k=top_k,
)
```

O serviço já bloqueia evidência de outro candidato:

```python
candidate is None or item.candidate_id == candidate.id
```

Quando `candidateId` é nulo, a busca atual é global e pode retornar chunks de candidatos
diferentes. Esse comportamento é necessário para perguntas de descoberta.

Exemplo:

```text
Quero saber quais candidatos possuem propostas sobre o fim da escala 6x1
ou redução da carga de trabalho.
```

O prompt já recebe os dados básicos do candidato:

```text
nome
nome de urna
partido
cargo
UF
ID interno
ID TSE
```

Cada evidência já contém:

```text
candidate_id
source_type
source_id
title
content
source_url
metadata
```

## 1.3 Lacuna

O `app/rag` recebe o texto do chunk, mas não carrega novamente os dados estruturados da
entidade que originou o chunk.

No modo global existe uma segunda lacuna: o bloco de evidência não apresenta o nome e os
demais dados do candidato associado a cada chunk. O `SearchResult` possui
`candidate_id`, mas o modelo não recebe a identidade correspondente dentro de cada
evidência.

Exemplo atual:

```text
PoliticalChunk
   ├── SourceType = PROPOSITION
   ├── SourceId = CamaraId
   └── Content = texto renderizado
```

O modelo recebe o `Content`, porém não recebe necessariamente todos os campos atuais de:

```text
Proposition
PropositionAuthor
PropositionTopic
```

O mesmo vale para:

```text
ProposalDocument
PoliticalHistory
```

---

# 2. MISSÃO

Ao recuperar os `PoliticalChunk`, carregar também:

```text
Candidato ou candidatos relacionados
+
entidade de origem do chunk
+
dados relacionados da proposta
+
conteúdo do chunk
```

Enviar esse conjunto ao modelo para interpretação.

O Ask terá dois modos válidos:

```text
candidateId informado
→ CONSULTA INDIVIDUAL

candidateId nulo
→ DESCOBERTA DE CANDIDATOS
```

Não alterar persistência.

Não alterar o algoritmo de embedding.

Não criar nova tabela.

---

# 3. FLUXO ALVO

```text
pergunta + candidateId opcional
              │
              ▼
       candidateId existe?
         ┌────┴────┐
         │         │
        SIM       NÃO
         │         │
         ▼         ▼
 carregar um    buscar chunks
 Candidate      em toda a base
         │         │
 buscar chunks    carregar Candidate
 desse Candidate  de cada candidate_id
         └────┬────┘
              ▼
 para cada chunk, verificar SourceType
              │
              ├── PROPOSITION
              │      └── Proposition + Authors + Topics
              │
              ├── GOVERNMENT_PROPOSAL
              │      └── ProposalDocument
              │
              └── POLITICAL_HISTORY
                     └── PoliticalHistory
              │
              ▼
 montar evidências enriquecidas
              │
              ├── Candidate do chunk
              ├── dados estruturados da origem
              └── trecho recuperado
              │
              ▼
 modelo interpreta e agrupa por candidato
              │
              ▼
 resposta com candidatos + propostas + fontes
```

---

# 4. EXECUÇÃO CONCLUÍDA

```text
[X] carregador de contexto em memória
[X] candidatos carregados em lote pelos chunks
[X] proposições enriquecidas com autores e temas
[X] documentos de proposta de governo carregados pela correlação atual
[X] histórico político carregado pela correlação atual
[X] prompt individual e prompt de descoberta
[X] diversificação dos resultados por candidato
[X] testes unitários, integração, lint e tipagem
[X] imagens Docker reconstruídas e serviços saudáveis
```

## 4.1 Criar carregador de contexto

Criar módulo Python:

```text
app/rag/context.py
```

Responsabilidade:

```python
load_context(
    selected_candidate,
    evidence,
) -> RagContext
```

O carregador não executará busca vetorial.

Ele receberá os chunks já selecionados e carregará as entidades relacionadas.

Também carregará em lote todos os candidatos identificados por:

```python
candidate_ids = {item.candidate_id for item in evidence}
```

No modo individual, o conjunto terá apenas o candidato selecionado.

No modo descoberta, poderá conter vários candidatos.

## 4.2 Carregar proposições

Para evidência:

```text
SourceType = PROPOSITION
SourceId = Proposition.CamaraId
```

Executar consulta usando as tabelas atuais:

```sql
SELECT ...
FROM Proposition
WHERE Candidate = ?
  AND CamaraId IN (...)
```

Carregar também:

```text
PropositionAuthor
PropositionTopic
```

Dados enviados ao prompt:

```text
tipo
número
ano
título
ementa
ementa detalhada
data de apresentação
situação
autores
autores principais
temas
URL oficial
```

## 4.3 Carregar propostas de governo

Para evidência:

```text
SourceType = GOVERNMENT_PROPOSAL
SourceId = ProposalDocument.DocumentHash
```

Consultar:

```sql
SELECT ...
FROM ProposalDocument
WHERE Candidate = ?
  AND DocumentHash IN (...)
```

Dados enviados ao prompt:

```text
título
ano eleitoral
arquivo
resource ID
hash do documento
URL oficial
página do chunk
trecho recuperado
```

Não enviar o PDF inteiro.

## 4.4 Carregar histórico político

Para evidência:

```text
SourceType = POLITICAL_HISTORY
SourceId = PoliticalHistory.ExternalId
```

Consultar:

```sql
SELECT ...
FROM PoliticalHistory
WHERE Candidate = ?
  AND ExternalId IN (...)
```

Dados enviados ao prompt:

```text
instituição
cargo/função
partido
UF
período
situação
URL oficial
```

## 4.5 Montar o contexto

DTO somente Python:

```python
@dataclass(frozen=True)
class RagContext:
    mode: str
    selected_candidate: Candidate | None
    evidence: tuple[EnrichedEvidence, ...]
```

```python
@dataclass(frozen=True)
class EnrichedEvidence:
    candidate: Candidate
    chunk: SearchResult
    source_data: dict
```

Esses objetos não serão persistidos.

## 4.6 Alterar o `RagService`

Fluxo proposto:

```python
selected_candidate = self._candidate(candidate_id)

retrieved = self.retrieval.search(
    question,
    candidate_id=candidate_id,
    top_k=top_k,
)

evidence = self._valid_evidence(
    retrieved,
    selected_candidate,
)

context = self.context_loader.load(
    selected_candidate,
    evidence,
)

prompt = build_prompt(
    question,
    context,
    plan.intent,
)

answer = self.language_model.generate(
    POLICY,
    prompt,
)
```

Regra de validação:

```text
modo individual
→ aceitar somente evidence.candidate_id == selected_candidate.id

modo descoberta
→ aceitar candidatos diferentes
→ carregar cada Candidate pelo candidate_id do chunk
→ nunca deduzir o candidato pelo texto ou pela lista de autores
```

## 4.7 Alterar o prompt

Formato de cada evidência, nos dois modos:

```text
[E1]
Candidato: NOME DO CANDIDATO
Tipo da fonte: PROPOSITION
Identificador oficial: 123456

DADOS ESTRUTURADOS:
Tipo: PL
Número: 100
Ano: 2026
Autores: ...
Temas: ...
Situação: ...

TRECHO RECUPERADO:
...

FONTE OFICIAL:
https://...
```

Para plano de governo:

```text
[E2]
Candidato: NOME DO CANDIDATO
Tipo da fonte: GOVERNMENT_PROPOSAL
Documento: ...
Ano eleitoral: 2026
Página: 10
Trecho: ...
Fonte oficial: ...
```

O modelo deverá:

1. interpretar os dados estruturados e o trecho;
2. usar somente o contexto recebido;
3. diferenciar proposta de governo de proposição legislativa;
4. citar `[E1]`, `[E2]`;
5. não deduzir outro candidato pelos nomes dos autores.

No modo descoberta, acrescentar a instrução:

```text
Agrupe as evidências por candidato.
Liste somente candidatos sustentados pelas evidências.
Para cada candidato, apresente a proposta ou proposição relacionada e cite a fonte.
Não atribua a proposta de um candidato a outro.
```

Resposta esperada para a pergunta sobre escala 6x1:

```text
Foram encontradas evidências relacionadas para:

1. CANDIDATO A — partido/cargo/UF
   - Proposta ou proposição relacionada à redução da jornada ... [E1]

2. CANDIDATO B — partido/cargo/UF
   - Proposta ou proposição relacionada ao fim da escala 6x1 ... [E2]
```

---

# 5. ARQUIVOS A ALTERAR

```text
app/rag/context.py                         novo
app/rag/service.py                         integrar carregador
app/rag/prompt.py                          receber contexto enriquecido
app/rag/__init__.py                        exportar DTOs
app/api/services.py                        injetar repositories
app/repositories/candidate_repository.py   carregar candidatos em lote
app/repositories/proposition_repository.py consulta por Candidate + CamaraId
app/repositories/proposal_document_repository.py consulta por Candidate + hash
app/repositories/political_history_repository.py consulta por Candidate + ExternalId
app/repositories/proposition_author_repository.py carregar autores em lote
app/repositories/proposition_topic_repository.py carregar temas em lote
tests/test_retrieval_rag.py                 validar o contexto
```

Nenhum arquivo `.cls` será alterado.

---

# 6. TESTES

## 6.1 Candidato

```text
dado candidateId = 46
todas as evidências devem possuir candidate_id = 46
```

## 6.2 Descoberta sem candidato selecionado

```text
dado candidateId = null
e chunks pertencentes aos candidatos 46, 97 e 146
o contexto deve carregar os três Candidates
cada evidência deve permanecer ligada ao seu Candidate
a resposta deve poder listar os três candidatos e suas propostas
```

## 6.3 Proposição

```text
dado chunk PROPOSITION com SourceId = 123456
o contexto deve carregar Proposition.CamaraId = 123456
autores e temas devem estar presentes
```

## 6.4 Proposta de governo

```text
dado chunk GOVERNMENT_PROPOSAL com SourceId = hash
o contexto deve carregar ProposalDocument do mesmo Candidate e hash
```

## 6.5 Histórico

```text
dado chunk POLITICAL_HISTORY com SourceId = ExternalId
o contexto deve carregar PoliticalHistory do mesmo Candidate
```

## 6.6 Segurança

```text
modo individual + chunk de outro candidato
→ rejeitar antes do prompt
```

```text
modo descoberta + chunks de candidatos diferentes
→ aceitar
→ carregar cada candidato pelo candidate_id
→ manter a correlação em cada evidência
```

```text
SourceId sem entidade correspondente
→ manter o trecho
→ marcar dados estruturados como não localizados
→ não inventar valores
```

---

# 7. ESTADO IMPLEMENTADO

```text
candidateId informado                 candidateId nulo
        │                                   │
        ▼                                   ▼
um Candidate                         vários Candidates
        │                                   │
        └──────────────┬────────────────────┘
                       ▼
              PoliticalChunk recuperado
                       │
                       ▼
              dados estruturados da origem
                       │
                       ▼
              contexto enriquecido em memória
                       │
                       ▼
                  LLM interpreta
                       │
                       ▼
              resposta citada por candidato
```

Resultado entregue:

- processo simples;
- nenhuma mudança no IRIS `.cls`;
- candidato selecionado carregado uma vez no modo individual;
- candidatos dos chunks carregados em lote no modo descoberta;
- chunks filtrados no modo individual e globais no modo descoberta;
- propostas carregadas a partir do `SourceId`;
- modelo recebe dados estruturados e trechos;
- modelo pode descobrir e listar candidatos quando `candidateId` for nulo;
- fontes permanecem rastreáveis.
