# Implementação — seleção, perfil e propostas do candidato

> Situação: implementado e validado em 24/08/2026.
> Escopo principal: `app/ui/streamlit_app.py`.
> Persistência e classes IRIS: sem alterações.

## 1. Objetivo final

Organizar a interface Streamlit em duas áreas:

```text
ÁREA PRINCIPAL
TSE Public Data RAG Explorer
Consulte propostas e atuações políticas com respostas baseadas em fontes oficiais...
[ selecionar candidato ]
pergunta + resposta + evidências

BARRA LATERAL, somente quando houver seleção individual
perfil do candidato selecionado
propostas armazenadas desse candidato
```

O modo `Todos os candidatos` continua disponível e envia `candidateId = null` ao
`POST /ask`. Nesse modo, nenhum card de candidato é renderizado na barra lateral.

## 2. Contratos utilizados

### `GET /candidates`

Alimenta o seletor da área principal. A seleção usa o `id` como valor estável e uma função
separada produz o rótulo visível.

### `GET /candidates/{id}`

Carrega o perfil do candidato selecionado:

- nome e nome de urna;
- cargo e UF;
- partido e números eleitoral/partidário;
- vínculo técnico com a Câmara;
- IDs interno, TSE e Câmara;
- fonte oficial.

### `GET /candidates/{id}/propositions`

Carrega as proposições do candidato selecionado. Cada item lateral apresenta:

- título da proposição;
- situação e data de apresentação;
- ementa ou detalhamento disponível;
- IDs interno e da Câmara;
- link para a proposta oficial.

## 3. Fluxo implementado

```text
GET /candidates
      ↓
seletor abaixo do texto introdutório
      ↓
candidateId selecionado?
   ┌──┴──┐
  não   sim
   │     ├── GET /candidates/{id}
   │     ├── GET /candidates/{id}/propositions
   │     └── perfil + propostas na sidebar
   ↓
POST /ask com candidateId ou null
```

Coleção, perfil e proposições usam cache de 60 segundos para evitar chamadas repetidas em
reruns do Streamlit.

## 4. Tratamento de estados

- falha na coleção: bloqueia a consulta, pois o seletor não pode ser construído;
- lista vazia: mantém somente `Todos os candidatos`;
- falha no perfil: mostra erro localizado na sidebar;
- falha nas proposições: preserva o perfil e mostra erro localizado abaixo dele;
- nenhuma proposição: informa que não há propostas armazenadas;
- campos nulos: exibe `Não informado`;
- links são habilitados somente para URLs HTTP ou HTTPS válidas.

## 5. Arquivos alterados

- `app/ui/streamlit_app.py`;
- `tests/test_streamlit_app.py`;
- `tests/test_api.py`;
- `docs/SPEC — TSE Public Data RAG Explorer.md`;
- este documento.

Não foram alterados:

- `app/api/app.py`;
- repositories;
- classes `.cls`;
- schema IRIS;
- retrieval, prompt ou RAG.

## 6. Cobertura automatizada

Os testes validam:

1. seleção por ID estável mesmo com rótulos iguais;
2. seletor na área principal;
3. ausência de card lateral no modo global;
4. carregamento do perfil após seleção;
5. carregamento e renderização das proposições;
6. envio do mesmo `candidateId` ao `POST /ask`;
7. fallbacks para valores ausentes;
8. rejeição de links inválidos;
9. erros do detalhe restritos à sidebar;
10. contratos das três rotas de candidato.

## 7. Critérios de aceite

- o seletor aparece imediatamente abaixo do texto introdutório;
- a barra lateral não contém o seletor;
- a barra lateral só apresenta conteúdo para seleção individual;
- o candidato exibido corresponde ao ID selecionado;
- as proposições exibidas pertencem ao candidato selecionado;
- o modo global continua funcional;
- resposta e evidências permanecem na área principal;
- testes, Ruff e mypy passam;
- nenhuma mudança de persistência é necessária.
