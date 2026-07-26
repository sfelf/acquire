# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS client-assets

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends python-is-python3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.22 /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

COPY client/package.json client/package-lock.json ./client/
RUN npm --prefix client ci

COPY client ./client
RUN npm --prefix client run build:client
RUN npm --prefix client run verify:client

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_PROJECT_ENVIRONMENT=/opt/acquire
ENV PATH="/opt/acquire/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        zopfli \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.22 /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

COPY client ./client
COPY --from=client-assets /app/client/main/css/main.css ./client/main/css/main.css
COPY --from=client-assets /app/client/main/js/enums.js ./client/main/js/enums.js
COPY --from=client-assets /app/client/main/js/main.js ./client/main/js/main.js
COPY --from=client-assets /app/client/main/js/main.js.map ./client/main/js/main.js.map
COPY --from=client-assets /app/client/stats/css/stats.css ./client/stats/css/stats.css

EXPOSE 9000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:9000/sockjs/info >/dev/null || exit 1

CMD ["acquire-http-server", "--host", "0.0.0.0", "--port", "9000", "--main-static-root", "/app/client/main", "--stats-static-root", "/app/client/stats"]
