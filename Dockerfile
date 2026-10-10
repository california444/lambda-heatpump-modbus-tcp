# Basis-Image als ARG, damit es nur an einer Stelle steht und das Skript
# es beim Start ausgeben kann.
ARG BASE_IMAGE=python:3.14-slim-trixie
FROM ${BASE_IMAGE}

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Erst nur die Abhaengigkeiten kopieren und installieren: solange sich
# requirements.txt nicht aendert, trifft dieser Layer den Build-Cache,
# auch wenn am Quellcode geschraubt wurde.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Quellcode aus dem Build-Kontext statt per "git clone" zur Build-Zeit.
# Der Clone war ueber seine Kommandozeile cachebar und konnte deshalb
# stillschweigend einen alten Stand liefern; so entspricht das Image
# genau dem Commit, aus dem es gebaut wurde.
COPY lambda-modbus-tcp.py ./

# Create non-root user
RUN useradd --system --user-group --no-create-home app

# Herkunft des Builds bewusst am Ende: APP_REVISION aendert sich mit jedem
# Commit und wuerde weiter oben den pip-Layer jedes Mal invalidieren.
# ARGs von vor dem FROM sind hier nicht mehr sichtbar und muessen erneut
# deklariert werden.
ARG BASE_IMAGE
ARG APP_REVISION=""
ENV APP_BASE_IMAGE=${BASE_IMAGE} \
    APP_REVISION=${APP_REVISION}

USER app

# Die Konfiguration liest das Skript selbst aus den Umgebungsvariablen
# (SOURCE_TYPE, SOURCE_HOST, DEST_HOST, ... siehe README). Exec-Form, damit
# Python PID 1 ist und das Stoppsignal von "docker stop" direkt bekommt.
ENTRYPOINT ["python", "/app/lambda-modbus-tcp.py"]

# Daemon-Modus als Standard, laesst sich ueber "command:" ersetzen.
CMD ["-d"]
