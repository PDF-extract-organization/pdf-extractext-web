# --- Etapa 1: compilar el CSS de Tailwind a partir de la plantilla ---
FROM node:22-slim AS css

WORKDIR /build
COPY package.json package-lock.json tailwind.config.js postcss.config.js ./
RUN npm ci
COPY static/css/input.css ./static/css/input.css
COPY app/presentation/templates ./app/presentation/templates
RUN npm run build:css

# --- Etapa 2: la aplicación ---
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1     UV_LINK_MODE=copy     PATH="/app/.venv/bin:$PATH"

# Dependencias primero, para aprovechar la caché de capas
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY static ./static
COPY --from=css /build/static/css/output.css ./static/css/output.css

RUN useradd --system app && chown -R app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5     CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
