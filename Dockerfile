# Minimal Docker image for ASTograph MCP server
FROM python:3.12-slim

# OCI labels for Docker Desktop and registries
LABEL org.opencontainers.image.source="https://github.com/Thaylo/astograph"
LABEL org.opencontainers.image.url="https://github.com/Thaylo/astograph"
LABEL org.opencontainers.image.documentation="https://github.com/Thaylo/astograph#readme"
LABEL org.opencontainers.image.description="Detect structural code duplication using AST graph isomorphism"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

# Copy all required files
COPY pyproject.toml README.md ./
COPY src/ src/

# Install (non-editable for production)
RUN pip install --no-cache-dir .

# Enable event-driven mode for in-memory caching and file watching
ENV ASTOGRAPH_EVENT_DRIVEN=1

# MCP server runs on stdio
ENTRYPOINT ["python", "-m", "astograph.server"]
