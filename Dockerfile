FROM python:3.14-slim-trixie

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

# Allow runtime configuration via environment variables (overridden by docker run -e or compose `environment:`)
# These ENV assignments use build-time expansion if provided, but will be overridden at container runtime by environment variables.
ENV SOURCE_TYPE=${SOURCE_TYPE} \
		SOURCE_HOST=${SOURCE_HOST} \
		DEST_HOST=${DEST_HOST} \
		SOURCE_PORT=${SOURCE_PORT} \
		DEST_PORT=${DEST_PORT} \
		SOURCE_UNIT=${SOURCE_UNIT} \
		INTERVAL=${INTERVAL} \
		LOG_LEVEL=${LOG_LEVEL}

# Herkunft des Builds bewusst am Ende: APP_REVISION aendert sich mit jedem
# Commit und wuerde weiter oben den pip-Layer jedes Mal invalidieren.
ARG APP_REVISION=""
ENV APP_REVISION=${APP_REVISION}

USER app

# ENTRYPOINT in shell form so $ENV variables are expanded at container start
ENTRYPOINT python /app/lambda-modbus-tcp.py \
	--source-type=$SOURCE_TYPE \
	--source-host=$SOURCE_HOST \
	--dest-host=$DEST_HOST \
	--source-port=$SOURCE_PORT \
	--dest-port=$DEST_PORT \
	--source-unit=$SOURCE_UNIT \
	-d \
	-i $INTERVAL \
	--log $LOG_LEVEL
