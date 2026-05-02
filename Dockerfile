FROM python:3.13-slim

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first (layer caching)
COPY pyproject.toml uv.lock ./

# Install production dependencies (override Apple-internal PyPI URLs in lockfile)
RUN uv sync --no-dev --frozen --index-url https://pypi.org/simple/

# Copy application code
COPY src/ src/
COPY frontend/ frontend/

# Expose port
EXPOSE 8000

# Run with uvicorn
CMD ["uv", "run", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
