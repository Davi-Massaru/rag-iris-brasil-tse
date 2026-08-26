# TASK — Migrar Flask/Waitress para WSGI nativo do InterSystems IRIS

> Projeto: **TSE Public Data RAG Explorer**
> Objetivo deste documento: instruir um agente de código a alterar o repositório atual.  
> Data de referência técnica: **2026-08-23**.

---

## 1. MISSÃO

Migrar a API Flask atualmente hospedada por **Waitress em um container Python separado** para uma aplicação **WSGI hospedada diretamente pelo InterSystems IRIS**, utilizando o suporte WSGI do IRIS e Embedded Python.

A migração deve:

- manter Flask como framework da API;
- eliminar Waitress como servidor da API;
- eliminar o serviço/container `api` do `docker-compose.yml`;
- hospedar o callable Flask pelo IRIS usando `%SYS.Python.WSGI`;
- manter o namespace `IRISAPP` como namespace da aplicação;
- manter o Streamlit em container separado;
- fazer o Streamlit consumir a API pelo endpoint HTTP exposto pelo IRIS;
- instalar as dependências Python da API no ambiente acessível ao Embedded Python do IRIS;
- preferir **IPM/module.xml** para empacotar/configurar a aplicação WSGI;
- preservar os endpoints e regras de negócio existentes;
- evitar reescrever a aplicação Flask sem necessidade.

---

## 2. FONTE DE VERDADE

Antes de implementar, ler estas referências.

### 2.1 Documentação oficial atual — prioridade máxima

**Creating WSGI Applications — InterSystems IRIS Data Platform**  
https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=AWSGI

**Install and Import Python Packages — Embedded Python**  
https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=GEPYTHON_loadlib

**Using Embedded Python**  
https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=GEPYTHON

**Releases and Prerelease Software**  
https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=PAGE_rel_streams

### 2.2 Referências de implementação

**Hosting a Flask REST API on InterSystems IRIS using WSGI**  
https://community.intersystems.com/post/hosting-flask-rest-api-intersystems-iris-using-wsgi

**Running WSGI applications with IPM**  
https://community.intersystems.com/post/running-wsgi-applications-ipm

**IPM — Installing WSGI Application**  
https://github-wiki-see.page/m/intersystems/ipm/wiki/06.-Installing-WSGI-Application

### 2.3 Regra de precedência

Se houver divergência entre um artigo da Developer Community e a documentação atual do IRIS:

1. documentação oficial da versão atual;
2. documentação oficial da versão usada pelo container;
3. documentação/IPM;
4. artigos da Developer Community.

Não copiar literalmente configurações antigas marcadas como experimentais sem verificar a documentação atual.

---

## 3. FATO IMPORTANTE SOBRE VERSÃO

WSGI foi introduzido no IRIS 2024.1 como recurso experimental.

O suporte a **WSGI Applications tornou-se GA no IRIS 2025.1**.

Portanto:

- não tratar WSGI como experimental se o projeto estiver usando IRIS >= 2025.1;
- adicionar ao pacote um requisito mínimo coerente com o uso GA, preferencialmente:

```xml
<SystemRequirements Version=">=2025.1" />
```

- o Dockerfile atual usa uma tag flutuante:

```dockerfile
ARG IRIS_IMAGE=intersystems/iris-community:latest-cd
```

Não é obrigatório alterar a política de versionamento nesta tarefa, mas o agente deve registrar no relatório final qual versão efetiva do IRIS foi utilizada nos testes.

---

## 4. ESTADO ATUAL DO PROJETO

O projeto possui um Dockerfile multi-stage.

Arquitetura atual:

```text
                         docker-compose
                              |
              +---------------+---------------+
              |               |               |
              v               v               v
            iris             api              ui
          container       container        container
              |               |               |
              |           Waitress         Streamlit
              |               |
              |              WSGI
              |               |
              |             Flask
              |               |
              +<------ TCP 1972 ------+
```

### 4.1 Dockerfile atual

A imagem IRIS e a imagem da API são separadas:

```dockerfile
FROM ${IRIS_IMAGE} AS iris
...
FROM python:3.12-slim AS app
```

A API é iniciada por:

```dockerfile
CMD ["waitress-serve", "--call", "--listen=0.0.0.0:8000", "app.api.app:create_app"]
```

### 4.2 docker-compose atual

Existem três serviços:

```yaml
services:
  iris:
  api:
  ui:
```

O serviço `api` conecta ao IRIS usando TCP:

```yaml
IRIS_HOST: iris
IRIS_PORT: 1972
IRIS_NAMESPACE: IRISAPP
IRIS_USERNAME: ...
IRIS_PASSWORD: ...
```

O Streamlit consome:

```yaml
API_BASE_URL: http://api:8000
```

### 4.3 module.xml atual

O módulo já existe:

```xml
<Module>
  <Name>tse-public-data-rag-explorer</Name>
  <Version>1.0.0</Version>
  <Description>Dados políticos oficiais, busca híbrida e RAG no InterSystems IRIS</Description>
  <Packaging>module</Packaging>
  <SourcesRoot>iris</SourcesRoot>
  <Resource Name="IRISPolitical.PKG"/>
</Module>
```

Essa estrutura deve ser aproveitada para o WSGI/IPM.

---

## 5. ARQUITETURA ALVO

```text
                       docker-compose
                              |
                    +---------+---------+
                    |                   |
                    v                   v
             +-------------+      +-------------+
             |    IRIS     |      |  Streamlit  |
             |  container  |      |  container  |
             +------+------+      +------+------+
                    ^                    |
                    | HTTP               |
                    +--------------------+
                    |
            IRIS Web Application
                    |
             %SYS.Python.WSGI
                    |
                  Flask
                    |
             application/services
                    |
          Embedded Python / IRIS APIs
                    |
                 IRISAPP
```

A API deverá ser acessível, inicialmente, por:

```text
http://localhost:52773/api/
```

Endpoints Flask existentes deverão continuar abaixo do mount point, por exemplo:

```text
Flask route:       /health
URL externa:       /api/health
```

Não adicionar `/api` manualmente em todas as rotas Flask se o mount point WSGI já fornecer esse prefixo.

---

## 6. DECISÕES DE ARQUITETURA

### 6.1 Flask continua

Não substituir Flask por `%CSP.REST`, FastAPI, Django ou outro framework.

A tarefa é trocar o **host WSGI**, não reescrever a API.

Antes:

```text
Waitress -> Flask
```

Depois:

```text
IRIS Web Gateway -> %SYS.Python.WSGI -> Flask
```

### 6.2 Application Factory

A aplicação atual aparentemente utiliza:

```python
create_app()
```

O IRIS WSGI precisa receber um **WSGI callable**, não uma factory arbitrária sem a assinatura WSGI.

Preservar `create_app()` e criar um entrypoint simples.

Criar, por exemplo:

```text
wsgi_app.py
```

Conteúdo esperado:

```python
from app.api.app import create_app

app = create_app()
```

Configuração WSGI:

```text
Application Name = wsgi_app
Callable Name    = app
```

Não iniciar `app.run()` e não iniciar Waitress dentro desse módulo.

### 6.3 Namespace

A Web Application WSGI deve executar no namespace:

```text
IRISAPP
```

Esse namespace passa a definir o contexto padrão do Embedded Python executado pela aplicação.

### 6.4 Banco de dados

O objetivo principal desta tarefa é a migração do hosting WSGI.

Entretanto, como a API passará a executar dentro do IRIS, preferir o módulo Embedded Python:

```python
import iris
```

para acesso ao próprio IRIS, quando isso puder ser feito sem reescrever a aplicação inteira.

Se atualmente houver uma camada/repository responsável pela conexão TCP com IRIS:

1. preservar a interface dessa camada;
2. criar/adaptar a implementação para Embedded Python;
3. preservar SQL e regras existentes sempre que possível;
4. migrar incrementalmente;
5. somente remover `IRIS_HOST`, `IRIS_PORT`, `IRIS_USERNAME` e `IRIS_PASSWORD` depois que nenhum código da API depender deles.

Não misturar uma grande refatoração de domínio com esta tarefa.

---

## 7. INSTALAÇÃO DAS DEPENDÊNCIAS PYTHON

### REGRA CRÍTICA

Não instalar Flask apenas no stage/container Python externo.

O IRIS WSGI executa usando Embedded Python. Logo, Flask e as dependências importadas pela API precisam estar disponíveis para esse ambiente.

Para container IRIS sem durable `%SYS`, a documentação atual recomenda instalar pacotes em:

```text
/usr/irissys/mgr/python
```

Modelo:

```dockerfile
RUN python3 -m pip install \
    --target /usr/irissys/mgr/python \
    -r /caminho/requirements.txt
```

O agente deve verificar se `python3 -m pip` está disponível na imagem utilizada.

Se não estiver, instalar `python3-pip` usando o mecanismo apropriado da imagem base. Não presumir `apt`, `yum` ou outro gerenciador sem verificar a distribuição do container.

### Dependências

Inspecionar `requirements.txt`.

Remover `waitress` se não houver outro consumidor.

Se a UI e a API tiverem conjuntos muito diferentes de dependências, é permitido separar em:

```text
requirements-api.txt
requirements-ui.txt
```

ou nomenclatura equivalente.

Evitar duplicação desnecessária.

Se a API migrar totalmente para `import iris` em Embedded Python, verificar se `intersystems-irispython` continua necessário para algum componente externo antes de removê-lo.

---

## 8. ALTERAÇÃO DO `module.xml`

### Preferência

Usar IPM para:

- copiar os arquivos Python da aplicação para um diretório com leitura garantida;
- criar/configurar a Web Application WSGI.

O artigo de IPM demonstra os elementos:

```xml
<FileCopy ... />
<WSGIApplication ... />
```

Adaptar o `module.xml` existente, não substituir a configuração das classes IRIS.

Estrutura alvo aproximada:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Export generator="Cache" version="25">
  <Document name="tse-public-data-rag-explorer.ZPM">
    <Module>
      <Name>tse-public-data-rag-explorer</Name>
      <Version>1.0.0</Version>
      <Description>Dados políticos oficiais, busca híbrida e RAG no InterSystems IRIS</Description>
      <Packaging>module</Packaging>

      <SystemRequirements Version=">=2025.1" />

      <SourcesRoot>iris</SourcesRoot>
      <Resource Name="IRISPolitical.PKG"/>

      <!-- Ajustar paths depois de inspecionar a árvore real do projeto. -->
      <FileCopy
        Name="app/"
        Target="${libdir}tse-public-data-rag-explorer/app/"
      />

      <FileCopy
        Name="wsgi_app.py"
        Target="${libdir}tse-public-data-rag-explorer/"
      />

      <WSGIApplication
        Url="/api"
        Description="TSE Public Data RAG Explorer Flask API"
        WSGIAppLocation="${libdir}tse-public-data-rag-explorer/"
        WSGIAppName="wsgi_app"
        WSGICallable="app"
      />

    </Module>
  </Document>
</Export>
```

### ATENÇÃO

O exemplo acima é um **alvo conceitual**.

O agente deve validar a sintaxe suportada pela versão do IPM presente no container antes de fechar a alteração.

Não inventar atributos de `WSGIApplication`.

### Autenticação

Os artigos de demonstração usam configurações como:

```xml
UnauthenticatedEnabled="1"
MatchRoles=":${dbrole}"
```

Não copiar isso cegamente.

A documentação atual alerta que:

- acesso `Unauthenticated` precisa estar permitido na instância;
- caso contrário, a aplicação poderá responder HTTP 403.

Para o ambiente local/demo do concurso, acesso não autenticado pode ser habilitado conscientemente se for necessário.

Registrar explicitamente essa decisão.

Não apresentar configuração de demo como recomendação de produção.

---

## 9. ALTERAÇÃO DO `iris.script`

Atualmente o script apenas carrega as classes ObjectScript:

```objectscript
zn "IRISAPP"
set sc=$SYSTEM.OBJ.LoadDir("/home/irisowner/dev/iris","ck",,1)
```

Como o projeto já possui `module.xml`, preferir tornar o módulo IPM parte real do processo de build.

Objetivo conceitual:

```objectscript
zn "IRISAPP"
zpm "load /home/irisowner/dev"
```

ou comando equivalente válido para a versão de IPM instalada.

### O agente deve

1. verificar se `zpm`/IPM existe na imagem atual;
2. verificar a versão;
3. executar a instalação no namespace correto;
4. garantir que as classes `IRISPolitical.PKG` continuem sendo importadas;
5. garantir que a `WSGIApplication` seja criada durante build/setup;
6. fazer o build falhar se a instalação IPM falhar.

Evitar carregar duas vezes as mesmas classes sem necessidade.

Se o `zpm load` substituir corretamente o `LoadDir`, remover a duplicidade.

### Fallback

Somente se IPM não puder ser utilizado de forma confiável no projeto, configurar a aplicação programaticamente usando `Security.Applications`.

O padrão de referência é:

```objectscript
zn "%SYS"
Kill props
Set props("Description") = "TSE Public Data RAG Explorer Flask API"
Set props("WSGIAppLocation") = "/path/to/flaskapp"
Set props("WSGIAppName") = "wsgi_app"
Set props("WSGICallable") = "app"
Set props("DispatchClass") = "%SYS.Python.WSGI"
Set sc = ##class(Security.Applications).Create("/api", .props)
```

Se usar esse fallback, configurar também o namespace apropriado usando a API suportada pela versão instalada.

Não implementar simultaneamente IPM + criação manual da mesma Web Application.

---

## 10. ALTERAÇÃO DO `Dockerfile`

### Estado atual

```dockerfile
FROM ${IRIS_IMAGE} AS iris
...
FROM python:3.12-slim AS app
...
CMD ["waitress-serve", ...]
```

### Estado alvo

O stage IRIS deve conter:

- classes ObjectScript;
- código Flask necessário para API;
- `wsgi_app.py`;
- dependências Python da API instaladas no diretório do Embedded Python;
- configuração da Web Application WSGI.

O stage Python separado deve existir apenas se ainda for necessário para a UI Streamlit.

Modelo conceitual:

```dockerfile
FROM ${IRIS_IMAGE} AS iris

WORKDIR /home/irisowner/dev

COPY merge.cpf iris.script module.xml ./
COPY iris ./iris
COPY app ./app
COPY wsgi_app.py ./wsgi_app.py
COPY requirements-api.txt ./requirements-api.txt

USER root

RUN python3 -m pip install \
    --no-cache-dir \
    --target /usr/irissys/mgr/python \
    -r requirements-api.txt

# manter criação/chown dos diretórios IRIS existentes

USER irisowner

RUN iris start IRIS \
    && iris merge iris ./merge.cpf \
    && iris session IRIS < iris.script | tee /tmp/iris-load.log \
    && ! grep -q "ERROR #" /tmp/iris-load.log \
    && iris stop IRIS quietly
```

Ajustar esse exemplo à árvore real.

### Remover

Não deve permanecer como comando ativo da API:

```dockerfile
waitress-serve
```

Não expor `8000` por causa da API.

O acesso HTTP da API passa pelo serviço HTTP/Web Gateway do IRIS, atualmente exposto em `52773` no compose.

---

## 11. ALTERAÇÃO DO `docker-compose.yml`

### Remover o serviço

```yaml
api:
```

por completo após a migração funcionar.

### Mover variáveis de ambiente

Variáveis utilizadas pela aplicação Flask agora precisam estar disponíveis no processo/container IRIS.

Mover para `iris.environment`, quando forem necessárias:

```yaml
TSE_DATASET_ID: ${TSE_DATASET_ID:-candidatos-2026}
INGEST_ELECTION_YEAR: ${INGEST_ELECTION_YEAR:-2026}
INGEST_STATES: ${INGEST_STATES:-SP}
INGEST_OFFICES: ${INGEST_OFFICES:-DEPUTADO FEDERAL,GOVERNADOR}
LLM_API_KEY: ${LLM_API_KEY:-}
LLM_MODEL: ${LLM_MODEL:-gpt-5-mini}
EMBEDDING_MODEL: ${EMBEDDING_MODEL:-text-embedding-3-small}
IRIS_SQL_SCHEMA: IRISPolitical_Model
```

Não mover automaticamente credenciais de conexão TCP se a API deixar de precisar delas.

### Streamlit

Alterar:

```yaml
API_BASE_URL: http://api:8000
```

para:

```yaml
API_BASE_URL: http://iris:52773/api
```

ou URL equivalente validada no runtime.

Alterar:

```yaml
depends_on:
  - api
```

para depender do `iris`, idealmente usando o healthcheck já existente.

### Arquitetura final esperada

```yaml
services:
  iris:
    ...

  ui:
    ...

volumes:
  iris-data:
```

---

## 12. ALTERAÇÃO DO CÓDIGO FLASK

### Não quebrar os endpoints existentes

Antes de alterar rotas, listar todos os blueprints/endpoints existentes.

Preservar:

- paths;
- métodos HTTP;
- payloads;
- códigos HTTP;
- contratos JSON;
- tratamento de erro.

### Criar healthcheck

Se ainda não existir, criar endpoint leve:

```python
@app.get("/health")
def health():
    return {"status": "ok"}, 200
```

Com a aplicação montada em `/api`, o teste externo deve ser:

```text
GET /api/health
```

### Evitar servidor embutido

Nenhum fluxo de produção deve executar:

```python
app.run(...)
```

Pode existir apenas sob:

```python
if __name__ == "__main__":
    ...
```

para desenvolvimento local, desde que não seja usado pelo IRIS WSGI.

### Imports

Garantir que todos os imports funcionem quando o diretório configurado em `WSGIAppLocation` for usado como raiz de importação.

Evitar depender de `cwd` acidental do antigo container Waitress.

---

## 13. ACESSO AO IRIS VIA EMBEDDED PYTHON

A documentação atual fornece o módulo:

```python
import iris
```

para chamadas ao IRIS a partir de Embedded Python.

Onde for apropriado, preferir:

```python
result = iris.sql.exec("SELECT ...")
```

ou APIs equivalentes suportadas pela versão instalada.

### Regra de refatoração

Não espalhar `iris.sql.exec()` diretamente pelas rotas Flask se o projeto já possui repositories/services.

Exemplo desejado:

```text
route
  -> service
     -> repository
        -> Embedded IRIS adapter
```

Preservar separação de responsabilidades.

### Transição

Se substituir o driver TCP pelo Embedded Python exigir mudanças amplas, executar em duas fases dentro do mesmo branch:

**Fase A — hosting**

```text
IRIS WSGI -> Flask -> camada de dados existente
```

**Fase B — acesso nativo**

```text
IRIS WSGI -> Flask -> repository -> iris module
```

Garantir testes entre as fases.

---

## 14. WEB APPLICATION WSGI — CONFIGURAÇÃO ESPERADA

Segundo a documentação atual, validar os seguintes campos/conceitos:

```text
Name / URL        = /api
Namespace         = IRISAPP
Enable            = WSGI
Application Name  = wsgi_app
Callable Name     = app
WSGI App Directory= diretório contendo wsgi_app.py
```

Internamente, a aplicação deve utilizar:

```text
DispatchClass = %SYS.Python.WSGI
```

quando configurada programaticamente pela API `Security.Applications`.

Com IPM, usar `<WSGIApplication>` suportado pela versão instalada em vez de duplicar essa configuração manualmente.

---

## 15. TESTES OBRIGATÓRIOS

### 15.1 Build limpo

Executar build sem reutilizar artefatos antigos relevantes:

```bash
docker compose build --no-cache
```

ou equivalente apropriado.

Build deve terminar sem:

```text
ERROR #
```

### 15.2 Containers

Subir:

```bash
docker compose up -d
```

Validar:

```bash
docker compose ps
```

Esperado:

```text
iris
ui
```

Não esperado:

```text
api
```

### 15.3 Embedded Python consegue importar Flask

Validar dentro do IRIS/container que o Python usado pelo IRIS encontra Flask.

Exemplo conceitual:

```python
import flask
```

O teste deve usar o ambiente Embedded Python/IRIS, não apenas `python` de outro container.

### 15.4 Callable

Validar:

```python
import wsgi_app
assert callable(wsgi_app.app)
```

no ambiente em que o WSGI do IRIS fará o import.

### 15.5 Endpoint

Validar:

```bash
curl -i http://localhost:52773/api/health
```

Esperado:

```text
HTTP 200
```

### 15.6 Endpoints existentes

Executar smoke tests nos endpoints Flask já existentes.

Não considerar a migração concluída apenas porque `/health` funciona.

### 15.7 Streamlit

Validar:

```text
http://localhost:8501
```

A UI deve conseguir consumir:

```text
http://iris:52773/api
```

pela rede interna do Docker.

### 15.8 Banco

Executar pelo menos uma rota que realmente consulte `IRISAPP`.

Garantir que a aplicação não esteja apenas respondendo endpoints estáticos.

---

## 16. TROUBLESHOOTING WSGI IRIS

### 16.1 IRIS não encontra a aplicação

Verificar:

- `WSGIAppLocation`;
- `WSGIAppName`;
- `WSGICallable`;
- permissões de leitura do arquivo e dos diretórios pais;
- import do módulo no Embedded Python.

### 16.2 Logs

Consultar no diretório `mgr` da instalação:

```text
messages.log
WSGI.log
```

A documentação oficial cita esses arquivos especificamente para troubleshooting WSGI.

### 16.3 Mudança Python não aparece

O IRIS pode manter módulos Python em cache.

Durante testes da aplicação WSGI, se alterações não forem refletidas:

```text
restart IRIS
```

Não perder tempo supondo imediatamente que o código novo não foi copiado.

### 16.4 HTTP 403

Verificar configuração de autenticação da Web Application.

Não assumir que `Unauthenticated` está habilitado globalmente.

### 16.5 URL raiz

Nos exemplos comunitários, atenção ao trailing slash da aplicação:

```text
/api/
```

Testar tanto o mount point quanto endpoints explícitos de acordo com as rotas Flask.

### 16.6 ImportError

Se ocorrer:

```text
ModuleNotFoundError: flask
```

ou similar, verificar se as dependências foram instaladas em:

```text
/usr/irissys/mgr/python
```

para o container IRIS sem durable `%SYS`.

Não corrigir instalando Flask apenas no container da UI.

---

## 17. CRITÉRIOS DE ACEITE

A tarefa está concluída somente se TODOS os itens abaixo forem verdadeiros.

- [ ] Flask continua sendo o framework HTTP da API.
- [ ] Waitress não hospeda mais a API.
- [ ] Não existe serviço `api` ativo no `docker-compose.yml`.
- [ ] Não existe porta `8000` necessária para a API.
- [ ] A aplicação Flask é carregada pelo WSGI do IRIS.
- [ ] A Web Application usa o namespace `IRISAPP`.
- [ ] O callable Flask é importável pelo Embedded Python.
- [ ] Flask e suas dependências estão disponíveis ao Embedded Python do IRIS.
- [ ] `/api/health` responde HTTP 200.
- [ ] Pelo menos uma rota com acesso real ao IRIS funciona.
- [ ] Os contratos dos endpoints existentes foram preservados.
- [ ] O Streamlit continua funcionando em `8501`.
- [ ] O Streamlit usa o IRIS como host da API.
- [ ] `module.xml` declara/configura a aplicação WSGI via IPM, salvo justificativa técnica documentada.
- [ ] O build do Docker configura a aplicação automaticamente; não depende de clicar manualmente no Management Portal.
- [ ] Logs/erros de instalação fazem o build falhar de maneira visível.
- [ ] README/documentação operacional foi atualizada com a arquitetura nova.

---

## 18. NÃO FAZER

Não:

- trocar Flask por outro framework;
- manter Waitress “por segurança” como segundo servidor da mesma API;
- manter um container `api` ocioso;
- configurar manualmente a Web Application no Portal como única forma de instalação;
- instalar Flask apenas em `python:3.12-slim` e esperar que Embedded Python encontre o pacote;
- hardcodar `/api` nas rotas Flask e também no mount WSGI, produzindo `/api/api/...`;
- expor credenciais `_SYSTEM/SYS` para a aplicação se o acesso Embedded Python não precisar delas;
- copiar `UnauthenticatedEnabled="1"` para produção sem decisão explícita de segurança;
- fazer uma refatoração geral de RAG, ingestão, chunking ou regras de negócio nesta tarefa;
- alterar contratos TSE/Câmara sem necessidade para a migração WSGI;
- declarar sucesso sem testar uma rota que consulta o IRIS.

---

## 19. ORDEM DE EXECUÇÃO RECOMENDADA

1. Inspecionar árvore `app/`, `requirements.txt`, factory Flask e camada de acesso ao IRIS.
2. Identificar todos os endpoints/blueprints existentes.
3. Criar `wsgi_app.py` com `app = create_app()`.
4. Fazer Flask ser importável dentro do container IRIS.
5. Instalar dependências da API em `/usr/irissys/mgr/python`.
6. Testar o callable dentro do ambiente IRIS antes de alterar o compose.
7. Alterar `module.xml` para copiar a aplicação e declarar `<WSGIApplication>`.
8. Integrar `zpm load` ao processo automático de build/setup.
9. Validar `/api/health` diretamente pelo IRIS.
10. Validar endpoints existentes.
11. Migrar/adaptar acesso ao banco para Embedded Python quando aplicável.
12. Mover variáveis necessárias para o serviço `iris`.
13. Alterar `API_BASE_URL` do Streamlit.
14. Remover serviço `api`.
15. Remover Waitress e dependências obsoletas.
16. Executar build limpo e smoke tests completos.
17. Atualizar README/arquitetura.

Não remover o caminho antigo antes de o WSGI do IRIS responder corretamente durante o desenvolvimento da alteração. No estado final do commit, entretanto, não deixar infraestrutura morta de Waitress/API.

---

## 20. SAÍDA ESPERADA DO AGENTE

Ao finalizar, fornecer um relatório curto contendo:

### Arquivos alterados

Exemplo:

```text
Dockerfile
iris.script
module.xml
docker-compose.yml
requirements*.txt
wsgi_app.py
app/api/...
README.md
```

### Arquitetura antes

```text
Streamlit -> Waitress -> Flask -> TCP -> IRIS
```

### Arquitetura depois

```text
Streamlit -> IRIS Web Gateway -> %SYS.Python.WSGI -> Flask -> IRIS
```

### Informações obrigatórias

- versão efetiva do IRIS testada;
- versão do IPM/ZPM usada;
- URL da Web Application;
- `WSGIAppLocation` efetivo;
- `WSGIAppName`;
- `WSGICallable`;
- estratégia de autenticação usada no ambiente de desenvolvimento;
- comandos executados para teste;
- resultados dos smoke tests;
- qualquer endpoint incompatível ou comportamento que não pôde ser preservado.

---

## 21. DEFINIÇÃO DE PRONTO

A definição de pronto é:

```text
docker compose up
        |
        +--> IRIS :52773
        |      |
        |      +--> /api/*
        |             |
        |             +--> %SYS.Python.WSGI
        |                    |
        |                    +--> Flask
        |                           |
        |                           +--> IRISAPP
        |
        +--> Streamlit :8501
               |
               +--> http://iris:52773/api
```

Sem:

```text
Waitress
container api
porta 8000 para API
conexão TCP externa desnecessária da API para o próprio IRIS
```

---

## 22. NOTAS TÉCNICAS DAS FONTES

### Documentação oficial atual

A documentação atual do InterSystems IRIS define WSGI conforme PEP-3333 e estabelece que:

- o framework WSGI deve estar instalado no mesmo servidor do IRIS;
- a aplicação callable deve estar em diretório acessível pelo IRIS;
- a Web Application define o namespace do Embedded Python;
- `Enable` deve estar configurado como WSGI;
- `Application Name` identifica o módulo/arquivo;
- `Callable Name` identifica o callable;
- `WSGI App Directory` identifica o diretório do módulo;
- `messages.log` e `WSGI.log` são fontes de diagnóstico;
- módulos Python podem ficar em cache e um restart do IRIS pode ser necessário durante desenvolvimento.

### Artigo Flask + IRIS

O artigo demonstra diretamente:

```text
Flask app
  -> variável app
  -> configuração WSGI no IRIS
  -> IRIS gerencia o servidor
```

Portanto `app.run()` não é o servidor de produção quando hospedado pelo IRIS.

### Artigo IPM

O artigo demonstra:

```objectscript
DispatchClass = "%SYS.Python.WSGI"
```

para configuração via `Security.Applications`, e mostra o recurso IPM:

```xml
<WSGIApplication ... />
```

como forma de empacotar/configurar a aplicação automaticamente.

---

# FIM DA TASK
