# Build context: repository root (see docker-compose.yml), so infra/ can be copied in.
FROM python:3.13-slim

ARG TOFU_VERSION=1.12.7
# Optional: set to e.g. 1.13.3 to also install HashiCorp Terraform (then IAC_BINARY=terraform).
ARG TERRAFORM_VERSION=""
ARG TARGETARCH=amd64

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TF_PLUGIN_CACHE_DIR=/opt/tofu-plugin-cache

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl unzip jq openssh-client \
 && rm -rf /var/lib/apt/lists/*

# OpenTofu CLI
RUN curl -fsSL -o /tmp/tofu.zip \
      "https://github.com/opentofu/opentofu/releases/download/v${TOFU_VERSION}/tofu_${TOFU_VERSION}_linux_${TARGETARCH}.zip" \
 && unzip -q /tmp/tofu.zip tofu -d /usr/local/bin && rm /tmp/tofu.zip \
 && tofu version

# Optional Terraform CLI
RUN if [ -n "$TERRAFORM_VERSION" ]; then \
      curl -fsSL -o /tmp/tf.zip "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_${TARGETARCH}.zip" \
      && unzip -q /tmp/tf.zip terraform -d /usr/local/bin && rm /tmp/tf.zip; \
    fi

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY infra /app/infra
# Pre-download the bpg/proxmox provider so live plans work without registry access.
RUN mkdir -p "$TF_PLUGIN_CACHE_DIR" \
 && TF_DATA_DIR=/tmp/tfinit tofu -chdir=/app/infra init -backend=false -input=false -no-color \
 && rm -rf /tmp/tfinit

COPY backend/app /app/app

RUN useradd --system --uid 10001 --home /app app \
 && mkdir -p /data /workspace \
 && chown -R app:app /data /workspace /app/infra /opt/tofu-plugin-cache
USER app

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
