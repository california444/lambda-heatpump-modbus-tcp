FROM python:3.9-slim-bullseye

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install git for checking out the repository
RUN apt-get update \
	&& apt-get install -y --no-install-recommends git ca-certificates \
	&& rm -rf /var/lib/apt/lists/*

# Allow overriding the repo URL and branch at build-time
ARG REPO_URL=https://github.com/california444/lambda-heatpump-modbus-tcp.git
ARG REPO_BRANCH=main

# Clone the repository into the image
RUN git clone --depth 1 --branch ${REPO_BRANCH} ${REPO_URL} /app

# Install Python dependencies from the checked-out repo
RUN pip install --no-cache-dir -r /app/requirements.txt

# Create non-root user
RUN addgroup --system app && adduser --system --ingroup app app || true

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
