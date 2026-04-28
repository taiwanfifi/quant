# Reliability Workbench Gateway
FROM python:3.11-slim

WORKDIR /app

# System deps for lxml + chromium (browser-use uses playwright; install on demand)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libxml2-dev libxslt1-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project (monorepo flat copy; gateway needs packages + skills)
COPY pyproject.toml ./
COPY packages/ ./packages/
COPY apps/ ./apps/
COPY .claude/ ./.claude/

# Install deps
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] pydantic anthropic curl_cffi \
    beautifulsoup4 lxml pyyaml chardet jsonschema rich

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "apps.gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
