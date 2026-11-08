FROM node:24-slim@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim@sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54 AS app
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
# Debian's fixes land before a new base image does (zlib CVE-2026-76844 and CVE-2026-85091).
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.13.5
WORKDIR /src
COPY pyproject.toml uv.lock README.md LICENSE .python-version ./
COPY backend/src backend/src
RUN uv sync --frozen --no-dev --no-editable && pip uninstall -y uv

COPY --from=frontend /build/frontend/dist /app/frontend/dist
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin wiredbench \
    && mkdir /data && chown wiredbench /data && rm -rf /src
WORKDIR /app
ENV WB_DATA_DIR=/data WB_HOST=0.0.0.0 WB_STATIC_DIR=/app/frontend/dist PYTHONDONTWRITEBYTECODE=1
USER wiredbench
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD ["/app/.venv/bin/python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"]
ENTRYPOINT ["/app/.venv/bin/wiredbench"]
CMD ["serve"]
