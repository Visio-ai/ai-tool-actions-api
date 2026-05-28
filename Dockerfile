# syntax=docker/dockerfile:1
FROM python:3.13-slim AS builder

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.11.2

ARG GITHUB_SSH_KEY
RUN mkdir -p /root/.ssh \
    && printf "%s\n" "$GITHUB_SSH_KEY" > /root/.ssh/id_rsa \
    && chmod 400 /root/.ssh/id_rsa \
    && ssh-keyscan github.com >> /root/.ssh/known_hosts

# visio-ml-utils is pinned via an HTTPS git URL in pyproject/uv.lock; rewrite to
# SSH so uv authenticates with the mounted key instead of prompting for HTTPS creds.
RUN git config --global url."git@github.com:".insteadOf "https://github.com/"

COPY pyproject.toml uv.lock ./

RUN uv sync

COPY capabilities_solutions_api/ capabilities_solutions_api/
COPY tests/ tests/

# tests/ has no __init__.py, so pytest's prepend importmode would put tests/unit
# on sys.path instead of the project root; PYTHONPATH=/app makes the top-level
# package importable during collection.
RUN PYTHONPATH=/app uv run pytest tests/unit/

RUN uv sync --no-dev


FROM python:3.13-slim

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"

COPY --from=builder /app/.venv /app/.venv
COPY capabilities_solutions_api/ capabilities_solutions_api/
COPY database/ database/
COPY scripts/ scripts/

CMD ["uvicorn", "capabilities_solutions_api.main.app:app", "--host", "0.0.0.0", "--port", "8000"]
