# IRIS Political Insight 🇧🇷

> Pesquisa inteligente sobre histórico político e propostas utilizando dados públicos, RAG, Hybrid Search e InterSystems IRIS.

## Sobre o projeto

**IRIS Political Insight** é uma aplicação experimental que utiliza inteligência artificial e dados públicos oficiais para facilitar a pesquisa sobre candidatos e históricos parlamentares brasileiros.

O projeto integra fontes como:

- Tribunal Superior Eleitoral — TSE;
- Câmara dos Deputados.

As informações são armazenadas e indexadas no **InterSystems IRIS**, combinando dados estruturados com pesquisa vetorial.

O usuário pode fazer perguntas em linguagem natural, por exemplo:

```text
Quais projetos deste candidato estão relacionados à educação?
```

```text
Existem projetos relacionados à inteligência artificial?
```

```text
Quais assuntos aparecem com frequência no histórico parlamentar?
```

```text
O que as fontes oficiais apresentam sobre a atuação deste candidato na área da saúde?
```

O sistema recupera evidências relevantes antes de solicitar ao modelo de linguagem a geração da resposta.

Esse processo é conhecido como **Retrieval-Augmented Generation — RAG**.

---

# Motivação

Informações sobre a trajetória de candidatos e políticos brasileiros estão disponíveis publicamente, mas normalmente distribuídas entre diferentes bases e formatos.

Pesquisar manualmente pode exigir:

1. identificar o candidato;
2. localizar seu histórico parlamentar;
3. pesquisar proposições;
4. consultar temas;
5. analisar textos;
6. comparar diferentes registros.

O objetivo do IRIS Political Insight é demonstrar como o **InterSystems IRIS** pode ser utilizado como uma plataforma central para armazenar, relacionar, pesquisar e recuperar esse conhecimento.

---

# Princípio do projeto

O sistema não tenta responder:

> Qual é o melhor candidato?

O objetivo é responder:

> O que as fontes oficiais disponíveis apresentam sobre esse candidato e sobre o tema pesquisado?

A aplicação não:

- recomenda voto;
- classifica candidatos;
- atribui score político;
- prevê resultados eleitorais;
- determina automaticamente ideologia;
- substitui a leitura das fontes originais.

O sistema fornece **informação + contexto + evidências**.

---

# Arquitetura

```text
                    Fontes públicas

              TSE              Câmara
               │                  │
               └────────┬─────────┘
                        │
                    Ingestão
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
                 Hybrid Search
               ┌────────┴────────┐
               │                 │
          Keyword Search    Vector Search
               │                 │
               └────────┬────────┘
                        │
                       RRF
                        │
                     Top K
                        │
                       LLM
                        │
                        ▼
                 Resposta + fontes
```

---

# Fontes de dados

## Tribunal Superior Eleitoral

Os Dados Abertos do TSE são utilizados para informações eleitorais como:

- candidatos;
- cargos;
- partidos;
- UF;
- informações da candidatura;
- propostas de governo, quando aplicável.

---

## Câmara dos Deputados

A API Dados Abertos da Câmara é utilizada para informações como:

- deputados;
- histórico parlamentar;
- mandatos externos;
- proposições;
- autoria;
- temas.

---

# Por que InterSystems IRIS?

O projeto utiliza o IRIS como núcleo da aplicação para combinar diferentes formas de representação da informação.

## Dados relacionais

Informações como:

```text
Candidate
Proposition
PoliticalHistory
```

podem ser consultadas diretamente por SQL.

## Dados vetoriais

Conteúdos textuais são convertidos em embeddings e armazenados como vetores.

Isso permite encontrar documentos semanticamente relacionados à pergunta do usuário.

Exemplo:

```text
Query:
"uso de IA pelo governo"
```

pode recuperar textos contendo conceitos como:

```text
automação
algoritmos
machine learning
sistemas inteligentes
inteligência artificial
```

mesmo sem correspondência textual exata.

---

# Hybrid Search

Pesquisa somente vetorial pode perder termos exatos importantes.

Pesquisa somente lexical pode perder relações semânticas.

O IRIS Political Insight utiliza as duas.

```text
                  Query
                    │
          ┌─────────┴─────────┐
          │                   │
     Keyword Search      Vector Search
          │                   │
          └─────────┬─────────┘
                    │
                    RRF
                    │
                Ranking final
```

Os rankings são combinados utilizando **Reciprocal Rank Fusion — RRF**.

---

# Pipeline RAG

O pipeline é dividido explicitamente em:

```text
1. Ingestion
2. Normalization
3. Chunking
4. Embedding
5. Vector Indexing
6. Retrieval
7. Hybrid Search
8. Prompt Construction
9. Response Generation
10. Source Presentation
```

---

# Chunking

Documentos extensos não são enviados integralmente ao modelo.

O conteúdo é dividido em fragmentos menores.

Configuração inicial:

```text
Chunk: 500–800 tokens
Overlap: 80–120 tokens
```

O overlap ajuda a preservar informações localizadas entre duas divisões consecutivas.

Cada chunk mantém sua proveniência:

```text
candidate
source_type
source_id
title
source_url
```

---

# Embeddings

Cada chunk é convertido em um vetor utilizando um modelo de embeddings.

```text
Texto
  ↓
Embedding Model
  ↓
VECTOR
  ↓
InterSystems IRIS
```

A pergunta do usuário passa pelo mesmo modelo:

```text
Pergunta
   ↓
Embedding
   ↓
Vector Search
```

---

# Mitigação de alucinações

O projeto aplica algumas estratégias para reduzir respostas não fundamentadas.

## Retrieval antes da geração

O modelo não recebe apenas a pergunta.

Recebe as evidências recuperadas do IRIS.

## Prompt restritivo

O modelo recebe instruções para:

- utilizar somente as evidências fornecidas;
- não inventar fatos;
- indicar quando não houver informação suficiente;
- não recomendar candidatos;
- apresentar fontes.

## Proveniência

Cada chunk possui referência à fonte original.

## Resposta sem evidência

Quando não houver contexto suficiente, a aplicação deve responder:

```text
Não foram encontradas evidências suficientes nas fontes
indexadas para responder a esta pergunta.
```

---

# Estrutura

```text
iris-political-insight/
│
├── app/
│   ├── config/
│   ├── database/
│   ├── ingestion/
│   ├── embeddings/
│   ├── retrieval/
│   ├── rag/
│   └── ui/
│
├── docs/
│   ├── SPEC.md
│   ├── IMPLEMENTATION_PLAN.md
│   ├── architecture.md
│   └── ai/
│
├── tests/
│
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

---

# Pré-requisitos

- Docker;
- Docker Compose;
- Python;
- acesso a um provedor de LLM;
- acesso ao modelo de embeddings configurado.

---

# Configuração

Copie:

```bash
cp .env.example .env
```

Configure:

```text
IRIS_HOST=
IRIS_PORT=
IRIS_NAMESPACE=
IRIS_USERNAME=
IRIS_PASSWORD=

LLM_PROVIDER=
LLM_API_KEY=
LLM_MODEL=

EMBEDDING_PROVIDER=
EMBEDDING_MODEL=

TSE_BASE_URL=
CAMARA_BASE_URL=
```

---

# Executando

Inicialize o ambiente:

```bash
docker compose up -d
```

Execute a ingestão:

```bash
python -m app.ingestion.pipeline
```

Execute a aplicação:

```bash
streamlit run app/ui/streamlit_app.py
```

---

# Exemplo

Selecione um candidato e pergunte:

```text
Quais projetos estão relacionados à inteligência artificial?
```

O sistema executa:

```text
Pergunta
   ↓
Keyword Search
   +
Vector Search
   ↓
RRF
   ↓
Top evidências
   ↓
LLM
   ↓
Resposta
   +
Fontes
```

---

# Tecnologias

- InterSystems IRIS
- Python
- SQL
- Vector Search
- RAG
- Hybrid Search
- embeddings
- Streamlit
- Docker
- API Dados Abertos da Câmara
- Dados Abertos do TSE

---

# Uso de IA durante o desenvolvimento

Este projeto também documenta o uso de ferramentas de inteligência artificial durante sua construção.

O diretório:

```text
docs/ai/
```

contém:

```text
prompts.md
decisions.md
hallucinations.md
development-log.md
```

O objetivo é registrar:

- prompts utilizados;
- especificações fornecidas à IA;
- decisões arquiteturais;
- erros encontrados;
- alucinações;
- alterações realizadas;
- validações humanas.

---

# Limitações

O projeto é experimental.

A ausência de determinada informação no sistema não significa que ela não exista.

Possíveis causas incluem:

- informação não disponível na fonte consultada;
- dados ainda não ingeridos;
- falha de correspondência entre identidades;
- limitação da pesquisa;
- documentação ainda não indexada.

Sempre consulte a fonte oficial para confirmação.

---

# Roadmap

## Próximas fontes

- Senado Federal;
- discursos;
- votações;
- despesas;
- patrimônio declarado.

## Arquitetura

- MCP Server;
- agentes especializados;
- atualização periódica;
- avaliação automática de retrieval;
- métricas de qualidade do RAG.

## Pesquisa

- comparação entre propostas de governo e histórico parlamentar;
- pesquisa temporal;
- evolução de temas;
- expansão para múltiplos tipos de documentos.

---

# Concurso

O projeto foi desenvolvido para o tópico **RAG** do concurso de programação da InterSystems Developer Community.

A solução procura demonstrar:

- InterSystems IRIS;
- RAG;
- Vector Search;
- Hybrid Search;
- dados multimodelo;
- acesso a APIs públicas;
- estratégia explícita de chunking;
- escolha documentada de embeddings;
- pipeline de ingestão e retrieval reproduzível;
- mitigação de alucinações;
- desenvolvimento assistido por IA.

---

# Disclaimer

IRIS Political Insight é uma ferramenta tecnológica para pesquisa em dados públicos.

O projeto não possui vínculo com candidatos, partidos políticos, Câmara dos Deputados ou Tribunal Superior Eleitoral.

As respostas geradas por modelos de linguagem podem conter erros.

Informações relevantes devem ser verificadas diretamente nas fontes oficiais.