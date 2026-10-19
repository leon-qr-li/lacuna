# LACUNA in the cloud (decision 2026-10-19-cloud-deploy): one container per server, behind Cloudflare
# Tunnel + Access. Built by .github/workflows/deploy.yml on every green main; the desktop app is unaffected.
#
#   docker build --build-arg VERSION=<sha> -t lacuna .
#   docker run -e LACUNA_CLOUD=1 -e CF_ACCESS_TEAM_DOMAIN=… -e CF_ACCESS_AUD=… -v /data:/data lacuna

FROM node:20-bookworm-slim AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-noto-cjk tini \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY lacuna_core/ lacuna_core/
COPY lacuna_app/ lacuna_app/
COPY scripts/ scripts/
RUN pip install ".[claude,asr,cloud]"
COPY --from=web /src/web/dist web/dist
ARG VERSION=dev
RUN echo "$VERSION" > VERSION \
    && useradd --uid 10001 --create-home --home-dir /data/home lacuna \
    && mkdir -p /data/workspace && chown -R lacuna:lacuna /data
# keys and settings the app saves land under the data volume, never inside the image
ENV HOME=/data/home LACUNA_CLOUD=1 LACUNA_WORKSPACE=/data/workspace
USER lacuna
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=4).status == 200 else 1)"
ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "lacuna_app", "--host", "0.0.0.0", "--port", "8765", "--no-browser"]
