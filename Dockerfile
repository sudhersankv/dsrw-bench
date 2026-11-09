# One image, two Fly process groups: web (the site) and runner (the job queue).

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
# Site data is served from SWB_DATA_DIR, so it stays out of the static bundle.
RUN rm -rf public/data && npm run build

FROM python:3.12-slim AS python-base
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
RUN pip install --no-cache-dir uv==0.7.12
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY configs ./configs
RUN uv sync --frozen --no-dev

# Ships whatever `swb analyze` last wrote to web/public/data; a clean checkout gets fresh demo data.
FROM python-base AS site-data
COPY web/public/data /seed
RUN if [ -f /seed/index.json ]; then cp -r /seed /site-data; \
    else swb demo --out /tmp/demo.jsonl --data /site-data; fi

FROM python-base AS runtime
COPY --from=web /web/dist ./web/dist
COPY --from=site-data /site-data ./data
ENV SWB_DATA_DIR=/app/data \
    SWB_WEB_DIST=/app/web/dist
EXPOSE 8080
CMD ["uvicorn", "swb.dashboard.app:app", "--host", "0.0.0.0", "--port", "8080"]
