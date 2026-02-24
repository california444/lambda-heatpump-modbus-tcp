FROM python:3.9.2-slim

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

# Create non-root user and switch
RUN addgroup --system app && adduser --system --ingroup app app || true
USER app

ENTRYPOINT ["python", "lambda-modbus-tcp.py"]
