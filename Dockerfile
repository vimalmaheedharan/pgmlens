FROM node:22-slim AS web
WORKDIR /w
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web ./
RUN npm run build

FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY apps/api ./apps/api
RUN uv sync --frozen --no-dev --package pgmlens-api
COPY --from=web /w/dist ./web
ENV PGMLENS_WEB_DIR=/app/web PGMLENS_DATA_DIR=/data PATH="/app/.venv/bin:$PATH"
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "pgmlens_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
