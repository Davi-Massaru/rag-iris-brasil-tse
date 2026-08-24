ARG IRIS_IMAGE=intersystems/iris-community:latest-cd

FROM ${IRIS_IMAGE} AS iris

WORKDIR /home/irisowner/dev
ENV IRISUSERNAME=_SYSTEM \
    IRISPASSWORD=SYS \
    IRISNAMESPACE=IRISAPP \
    PATH=/usr/irissys/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/home/irisowner/bin

COPY merge.cpf iris.script module.xml ./
COPY iris ./iris
COPY app ./app
COPY wsgi_app.py requirements-api.txt ./

USER root
RUN mkdir -p /data/IRISAPP_DATA/irisapp_dataenstemp \
    /data/IRISAPP_DATA/irisapp_datasecondary \
    && chown -R irisowner:irisowner /data
USER irisowner

RUN iris start IRIS \
    && iris merge iris ./merge.cpf \
    && iris session IRIS < iris.script | tee /tmp/iris-load.log \
    && ! grep -Eiq '(<SYNTAX>|<NOROUTINE>|ERROR|FAILURE)' /tmp/iris-load.log \
    && iris stop IRIS quietly

# Install application packages after IPM so its bundled Python dependencies
# cannot leave older package metadata ahead of the API requirements.
USER root
RUN python3 -m pip install --no-cache-dir --upgrade \
    --target /usr/irissys/mgr/python \
    -r requirements-api.txt \
    && python3 -m pip check
USER irisowner

FROM python:3.12-slim AS ui

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /opt/iris-political

COPY requirements-ui.txt ./
RUN pip install --no-cache-dir -r requirements-ui.txt
COPY app ./app
COPY .streamlit ./.streamlit

EXPOSE 8501
CMD ["streamlit", "run", "app/ui/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]

FROM python:3.12-slim AS test

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /opt/iris-political

COPY requirements.txt requirements-api.txt requirements-ui.txt requirements-dev.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY app ./app
COPY tests ./tests
COPY wsgi_app.py ./wsgi_app.py

CMD ["python", "-m", "pytest", "-m", "unit", "-p", "no:cacheprovider"]
