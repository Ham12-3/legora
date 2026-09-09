# Production image for both the API and the worker: same code, same
# dependencies, different command. Build context is apps/api.
#
# Differences from Dockerfile.dev that matter: dev dependencies are excluded,
# the lockfile is enforced rather than resolved, only the packages the service
# actually reads are copied (no tests, no eval, no fixtures), and the process
# runs as a non-root user with no reloader.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/usr/local \
    UV_COMPILE_BYTECODE=1

# Tesseract backs PyMuPDF's OCR for scanned pages. TESSDATA_PREFIX is where
# Debian puts the language files; PyMuPDF reads it from the environment.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Dependency layer, cached independently of source. --frozen fails the build
# rather than silently resolving something the lockfile does not describe.
COPY pyproject.toml uv.lock ./
RUN uv sync --no-install-project --no-dev --frozen

# Prompts are read from disk at request time and are versioned alongside the
# code: changing one means bumping PROMPT_VERSION, which invalidates the cell
# cache. They have to be in the image.
COPY alembic.ini ./
COPY alembic ./alembic
COPY prompts ./prompts
COPY app ./app

RUN useradd --system --uid 10001 --create-home legora
USER legora

EXPOSE 8000

# Migrations are a separate step (see docker-compose.prod.yml), not something
# every replica races to run on boot.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
