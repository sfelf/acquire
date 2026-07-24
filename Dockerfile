# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS client-assets

WORKDIR /app

ENV PYTHONPATH=/app/src

RUN apt-get update \
    && apt-get install -y --no-install-recommends python-is-python3 \
    && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json ./
RUN npm ci

COPY client ./client
COPY server/enumsgen.py ./server/
COPY src/acquire/__init__.py src/acquire/enums.py ./src/acquire/
RUN npm run build:client

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        zopfli \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.local-docker.txt .
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir -r requirements.local-docker.txt

COPY . .
COPY --from=client-assets /app/client/main/css/main.css ./client/main/css/main.css
COPY --from=client-assets /app/client/main/js/enums.js ./client/main/js/enums.js
COPY --from=client-assets /app/client/main/js/main.js ./client/main/js/main.js
COPY --from=client-assets /app/client/main/js/main.js.map ./client/main/js/main.js.map
COPY --from=client-assets /app/client/stats/css/stats.css ./client/stats/css/stats.css

EXPOSE 9000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:9000/sockjs/info >/dev/null || exit 1

WORKDIR /app/server
CMD ["python", "http_server.py", "--host", "0.0.0.0", "--port", "9000"]
