# SPEC — IRIS Political Insight

## 1. Visão do produto

**IRIS Political Insight** é uma aplicação RAG construída sobre InterSystems IRIS para consultar informações públicas e oficiais sobre candidatos e políticos brasileiros.

O sistema deverá consolidar dados eleitorais e históricos políticos provenientes de fontes oficiais e permitir consultas em linguagem natural com respostas fundamentadas nas evidências recuperadas.

Exemplos:

- Quais projetos este candidato apresentou relacionados à educação?
- Qual é o histórico político deste candidato?
- Quais temas aparecem com maior frequência nos projetos deste candidato?
- Existem projetos relacionados à inteligência artificial?
- O que consta nas fontes oficiais sobre a atuação deste candidato na área da saúde?
- Quais assuntos aparecem tanto no histórico parlamentar quanto na proposta de governo?

A aplicação não deverá recomendar candidatos, atribuir notas políticas ou indicar em quem o usuário deve votar.

---

# 2. Objetivo do MVP

Construir, uma aplicação capaz de:

1. obter candidatos através de dados públicos do TSE;
2. relacionar candidatos com parlamentares da Câmara quando possível;
3. obter histórico parlamentar e proposições;
4. armazenar dados estruturados no InterSystems IRIS;
5. transformar conteúdos textuais relevantes em embeddings;
6. armazenar os embeddings utilizando recursos vetoriais do IRIS;
7. executar busca lexical;
8. executar busca vetorial;
9. combinar ambas em uma Hybrid Search;
10. fornecer os documentos recuperados a um LLM;
11. responder perguntas utilizando exclusivamente as evidências recuperadas;
12. apresentar ao usuário as fontes utilizadas.

---

# 3. Escopo do MVP

## Fontes

### TSE

Utilizar os Dados Abertos do TSE para obter:

- nome;
- nome de urna;
- cargo;
- partido;
- UF;
- número;
- identificadores da candidatura;
- proposta de governo, quando disponível.

### Câmara dos Deputados

Utilizar a API Dados Abertos da Câmara para obter:

- parlamentar;
- histórico parlamentar;
- mandatos externos;
- proposições;
- autoria de proposições;
- temas das proposições.

---

# 4. Fora do escopo inicial

Não implementar no MVP:

- Senado Federal;
- despesas parlamentares;
- patrimônio;
- análise de redes sociais;
- notícias;
- fact-checking externo;
- previsão eleitoral;
- recomendação de voto;
- classificação ideológica;
- score de candidatos;
- agentes autônomos;
- autenticação;
- processamento distribuído;
- filas;
- Angular;
- microsserviços.

Esses recursos poderão ser adicionados posteriormente.

---

# 5. Princípio fundamental

Toda afirmação política apresentada pela aplicação deverá possuir uma origem recuperável.

Regra:

**Resposta sem evidência não deve ser apresentada como fato.**

Cada informação utilizada pelo RAG deve, sempre que possível, possuir:

- fonte;
- identificador externo;
- URL de origem;
- tipo da fonte;
- data;
- candidato relacionado;
- trecho utilizado.

---

# 6. Arquitetura

```text
                FONTES OFICIAIS

             TSE          Câmara
              │              │
              └──────┬───────┘
                     │
                INGESTÃO
                     │
          normalização / vínculo
                     │
                     ▼
           InterSystems IRIS
       ┌─────────────┼─────────────┐
       │             │             │
       ▼             ▼             ▼
  Candidate     Proposition   PoliticalChunk
  Relacional     Relacional      VECTOR
       │             │             │
       └─────────────┼─────────────┘
                     │
                Retrieval
            ┌────────┴────────┐
            │                 │
        Keyword           Vector
         Search            Search
            │                 │
            └────────┬────────┘
                     │
               Hybrid Search
                     │
                     │
                     ▼
                    LLM
                     │
                     ▼
             Resposta fundamentada
                     +
                   fontes
```

---

# 7. Modelo de dados

## Candidate

Representa uma pessoa candidata identificada pelo TSE.

```text
Candidate
---------
id
tse_id
name
ballot_name
party
party_number
office
state
candidate_number
camara_deputy_id
source_url
```

### Regras

`camara_deputy_id` poderá ser nulo.

Nem todo candidato possui histórico parlamentar na Câmara.

---

## PoliticalHistory

Representa registros históricos associados ao parlamentar.

```text
PoliticalHistory
----------------
id
candidate_id
institution
position
party
state
start_date
end_date
external_id
source_url
```

---

## Proposition

Representa uma proposição legislativa.

```text
Proposition
-----------
id
external_id
candidate_id
type
number
year
title
summary
presentation_date
status
source_url
```

---

## PropositionTopic

```text
PropositionTopic
----------------
id
proposition_id
external_code
name
```

---

## ProposalDocument

Representa uma proposta de governo.

```text
ProposalDocument
----------------
id
candidate_id
title
election_year
source_url
document_hash
```

---

## PoliticalChunk

Unidade textual utilizada para recuperação semântica.

```text
PoliticalChunk
--------------
id
candidate_id
source_type
source_id
title
content
embedding
source_url
metadata
```

### `source_type`

Valores iniciais:

```text
PROPOSITION
GOVERNMENT_PROPOSAL
POLITICAL_HISTORY
```

Posteriormente:

```text
SPEECH
VOTE
EXPENSE
SENATE_PROPOSITION
```

---

# 8. Estratégia multimodelo

O IRIS deverá armazenar diferentes representações da informação.

## Modelo relacional

Utilizado para informações determinísticas:

- candidato;
- partido;
- cargo;
- proposição;
- data;
- histórico;
- relacionamento candidato/proposição.

Exemplo:

> Quantos projetos foram encontrados para determinado candidato?

Deve ser SQL.

---

## Modelo vetorial

Utilizado para recuperação semântica.

Exemplo:

> Quais projetos tratam de inteligência artificial?

Mesmo que o texto contenha:

- algoritmos;
- machine learning;
- automação;
- sistemas inteligentes;
- inteligência computacional.

A recuperação poderá acontecer por similaridade semântica.

---

# 9. Ingestão

A ingestão deverá ser executável manualmente.

Exemplo:

```bash
python -m app.ingestion
```

Fluxo:

```text
consultar TSE
    ↓
persistir candidatos
    ↓
identificar candidatos com correspondência na Câmara
    ↓
consultar Câmara
    ↓
obter histórico
    ↓
obter proposições
    ↓
normalizar texto
    ↓
chunking
    ↓
embedding
    ↓
persistir no IRIS
```

Não será necessário scheduler no MVP.

---

# 10. Resolução de identidade

Um candidato do TSE pode corresponder a um parlamentar da Câmara.

O MVP deverá tentar identificar essa correspondência utilizando informações como:

1. nome;
2. UF;
3. nome parlamentar;
4. partido, como informação auxiliar.

Uma correspondência não suficientemente confiável não deverá ser persistida automaticamente como verdadeira.

O sistema poderá armazenar:

```text
match_status:
MATCHED
UNMATCHED
AMBIGUOUS
```

Para o MVP, poderá existir também um pequeno arquivo de mapeamentos confirmados manualmente.

Exemplo:

```json
{
  "tse_candidate_id": "123",
  "camara_deputy_id": 456
}
```

Isso reduz risco e complexidade durante a demonstração.

---

# 11. Estratégia de chunking

## Proposições

Para proposições pequenas, utilizar:

- ementa;
- descrição;
- tema;
- metadados.

Um documento pequeno poderá formar um único chunk.

## Propostas de governo

Utilizar chunks maiores.

Valor inicial sugerido:

```text
500–800 tokens
```

Overlap:

```text
80–120 tokens
```

O objetivo do overlap é evitar perda de contexto entre segmentos.

Cada chunk deve manter metadados:

```text
candidate_id
candidate_name
source_type
source_id
title
page
source_url
```

---

# 12. Embeddings

O embedding deverá ser gerado durante a ingestão.

Requisitos:

- mesmo modelo para documentos e consultas;
- dimensão compatível com a coluna VECTOR do IRIS;
- modelo configurável por variável de ambiente;
- não gerar novamente embeddings quando o conteúdo não mudou.

Hash do conteúdo poderá ser utilizado para detectar alterações.

---

# 13. Busca lexical

A busca lexical deverá favorecer termos explícitos presentes na consulta.

Exemplo:

```text
"inteligência artificial"
```

deve favorecer documentos contendo exatamente essa expressão.

---

# 14. Busca vetorial

A consulta será convertida em embedding.

O IRIS deverá calcular similaridade entre:

```text
query_embedding
```

e:

```text
PoliticalChunk.embedding
```

Retornar os resultados mais semanticamente relacionados.

---

# 15. Hybrid Search

A aplicação deverá combinar:

```text
Keyword Search
      +
Vector Search
```

Implementação sugerida:

```text
Query
 ├── lexical top 20
 └── vector top 20
          │
          ▼
 Reciprocal Rank Fusion
          │
          ▼
        Top 8
```

Utilizar inicialmente **Reciprocal Rank Fusion — RRF** por ser simples, determinístico e não exigir normalização dos scores dos dois mecanismos.

---

# 16. Retrieval

O retrieval deverá aceitar:

```text
query
candidate_id?
source_type?
top_k?
```

Exemplo:

```text
search(
    query="inteligência artificial",
    candidate_id=123,
    top_k=8
)
```

Resultado:

```text
[
  {
    candidate,
    source_type,
    title,
    content,
    source_url,
    score
  }
]
```

---

# 17. RAG

Fluxo:

```text
Pergunta
   ↓
classificação/filtros
   ↓
Hybrid Search
   ↓
Top K evidências
   ↓
Prompt
   ↓
LLM
   ↓
Resposta
   ↓
Fontes
```

---

# 18. Política do prompt

O LLM deverá receber instruções explícitas:

1. utilize somente as evidências fornecidas;
2. não invente fatos;
3. não recomende voto;
4. não classifique candidato como bom ou ruim;
5. diferencie fatos de inferências;
6. informe quando não houver evidência suficiente;
7. cite as fontes utilizadas;
8. não transforme ausência de informação em evidência de ausência.

Resposta esperada quando não houver informação:

```text
Não foram encontradas evidências suficientes nas fontes
indexadas para responder a esta pergunta.
```

---

# 19. API

## GET /candidates

Filtros:

```text
name
party
state
office
```

---

## GET /candidates/{id}

Retorna perfil básico.

---

## GET /candidates/{id}/propositions

Retorna proposições armazenadas.

---

## POST /search

Request:

```json
{
  "query": "projetos relacionados à inteligência artificial",
  "candidateId": 123,
  "topK": 10
}
```

Response:

```json
{
  "results": []
}
```

---

## POST /ask

Request:

```json
{
  "question": "Quais projetos deste candidato estão relacionados à educação?",
  "candidateId": 123
}
```

Response:

```json
{
  "answer": "...",
  "sources": []
}
```

---

# 20. Interface

Para o MVP utilizar Streamlit.

Tela principal:

```text
IRIS Political Insight

[Candidato ▼]

Pergunte sobre o histórico político:

[ Quais projetos estão relacionados à IA? ]

                  [Pesquisar]
```

Resultado:

```text
Resposta
─────────────────────────────

Foram encontradas proposições relacionadas...

Evidências
─────────────────────────────

PL XXXX/2024

Trecho...

Fonte: Câmara dos Deputados
```

---

# 21. Estrutura do projeto

```text
iris-political-insight/
│
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── README.md
│
├── docs/
│   ├── SPEC.md
│   ├── IMPLEMENTATION_PLAN.md
│   └── architecture.md
│
├── app/
│   ├── main.py
│   │
│   ├── config/
│   │   └── settings.py
│   │
│   ├── database/
│   │   ├── connection.py
│   │   └── schema.sql
│   │
│   ├── ingestion/
│   │   ├── tse.py
│   │   ├── camara.py
│   │   ├── candidate_matcher.py
│   │   └── pipeline.py
│   │
│   ├── embeddings/
│   │   └── embedder.py
│   │
│   ├── retrieval/
│   │   ├── lexical.py
│   │   ├── vector.py
│   │   ├── hybrid.py
│   │   └── rrf.py
│   │
│   ├── rag/
│   │   ├── service.py
│   │   └── prompt.py
│   │
│   └── ui/
│       └── streamlit_app.py
│
└── tests/
    ├── test_rrf.py
    ├── test_chunking.py
    └── test_retrieval.py
```

---

# 22. Variáveis de ambiente

```text
IRIS_HOST
IRIS_PORT
IRIS_NAMESPACE
IRIS_USERNAME
IRIS_PASSWORD

LLM_PROVIDER
LLM_API_KEY
LLM_MODEL

EMBEDDING_PROVIDER
EMBEDDING_MODEL

TSE_BASE_URL
CAMARA_BASE_URL
```

---

# 23. Observabilidade mínima

Registrar:

```text
question
retrieval_time_ms
vector_search_time_ms
keyword_search_time_ms
generation_time_ms
total_time_ms
chunks_retrieved
```

Não é necessário implementar stack externa de observabilidade.

Logs estruturados são suficientes para o MVP.

---

# 24. Critérios de aceite

## CA01 — candidatos

Dado que a ingestão foi executada, candidatos devem existir no IRIS.

## CA02 — Câmara

Quando houver parlamentar correspondente, seu identificador da Câmara deve estar associado ao candidato.

## CA03 — proposições

O sistema deve armazenar proposições relacionadas ao parlamentar.

## CA04 — embeddings

Chunks devem possuir representação vetorial persistida no IRIS.

## CA05 — vector search

Uma consulta semântica deve retornar conteúdos semanticamente relacionados.

## CA06 — keyword search

Termos exatos devem ser recuperados pela busca lexical.

## CA07 — hybrid search

Os resultados lexical e vetorial devem ser combinados.

## CA08 — RAG

O LLM deve responder utilizando os documentos recuperados.

## CA09 — proveniência

Cada resposta deve apresentar as fontes que sustentam o conteúdo.

## CA10 — ausência de evidência

Quando o retrieval não fornecer evidências suficientes, o LLM deve informar explicitamente a limitação.

---

# 25. Definição de pronto do MVP

O MVP estará pronto quando for possível demonstrar:

```text
Selecionar candidato
        ↓
fazer pergunta temática
        ↓
buscar histórico/proposições no IRIS
        ↓
Hybrid Search
        ↓
RAG
        ↓
resposta
        ↓
fontes oficiais
```

com instalação reproduzível via Docker e documentação suficiente para outro desenvolvedor executar o projeto.

---

# 26. Roadmap

## V1

- TSE;
- Câmara;
- candidatos;
- histórico;
- proposições;
- RAG;
- Hybrid Search.


---

# 27. Princípio de neutralidade

O sistema é uma ferramenta de recuperação e organização de informações públicas.

Não deverá:

- recomendar candidatos;
- prever eleição;
- atribuir score de qualidade;
- definir ideologia automaticamente;
- afirmar intenção ou motivação não registrada;
- gerar conclusões políticas sem evidência documental.

O papel do sistema é:

**encontrar → contextualizar → apresentar evidências.**