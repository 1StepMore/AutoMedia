# AutoMedia — Multi-stage production Docker image
# Build:   docker build -t automedia:prod .
# Run:     docker run --rm automedia:prod automedia doctor
# Dev:     docker build -f Dockerfile.dev -t automedia:dev .

# ==============================================================================
# Stage 1: Build wheel
# ==============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN pip install --no-cache-dir build

# Copy only what's needed to build the wheel
COPY pyproject.toml README.md ./
COPY src/automedia/ src/automedia/

# Build a distributable wheel (no dev deps, no editable install)
RUN python -m build --wheel --outdir /build/dist

# ==============================================================================
# Stage 2: Production runtime
# ==============================================================================
FROM python:3.11-slim AS runtime

# Runtime system dependencies
# - ffmpeg: audio/video processing (required by audio/video pipelines)
# - curl: health checks and debugging
# - git: version info in doctor output
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the wheel (no cache, no build artifacts)
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -f /tmp/*.whl

# Smoke-test: verify the package imports correctly
RUN python -c "from automedia import __version__; print(f'AutoMedia {__version__} installed')"

# Create non-root user and switch to it
RUN adduser --disabled-password --gecos '' automedia
RUN chown -R automedia:automedia /app
USER automedia

# Default entrypoint
ENTRYPOINT ["automedia"]
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD pgrep -f "automedia" || exit 1

CMD ["doctor"]

# ==============================================================================
# Stage 3: Full runtime with all external deps (bun, edge-tts, whisper, chromium)
# Build: docker build --target mcp-full -t automedia:mcp-full .
# Use with: docker compose --profile full up mcp-full
# ==============================================================================
FROM runtime AS mcp-full

USER root
RUN curl -fsSL https://bun.sh/install | bash \
    && mv /root/.bun/bin/bun /usr/local/bin/bun \
    && rm -rf /root/.bun \
    && bun --version
RUN pip install --no-cache-dir edge-tts faster-whisper
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium-browser \
    && rm -rf /var/lib/apt/lists/*
RUN python -c "import edge_tts; print(f'edge-tts {edge_tts.__version__}')" \
    && python -c "import faster_whisper; print(f'faster-whisper {faster_whisper.__version__}')" \
    && chromium-browser --version
USER automedia
