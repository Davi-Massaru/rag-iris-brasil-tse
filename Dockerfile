ARG IRIS_IMAGE=intersystems/iris-community:latest-cd

FROM ${IRIS_IMAGE} AS iris

WORKDIR /home/irisowner/dev
ENV IRISUSERNAME=_SYSTEM \
    IRISPASSWORD=SYS \
    IRISNAMESPACE=IRISAPP \
    PATH=/usr/irissys/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/home/irisowner/bin

COPY merge.cpf iris.script module.xml ./
COPY iris ./iris

USER root
RUN mkdir -p /data/IRISAPP_DATA/irisapp_dataenstemp \
    /data/IRISAPP_DATA/irisapp_datasecondary \
    && chown -R irisowner:irisowner /data
USER irisowner

RUN iris start IRIS \
    && iris merge iris ./merge.cpf \
    && iris session IRIS < iris.script | tee /tmp/iris-load.log \
    && ! grep -q "ERROR #" /tmp/iris-load.log \
    && iris stop IRIS quietly

FROM python:3.12-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /opt/iris-political

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

EXPOSE 8000 8501
CMD ["waitress-serve", "--call", "--listen=0.0.0.0:8000", "app.api.app:create_app"]
