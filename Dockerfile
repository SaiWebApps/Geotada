FROM python:3.13-slim

WORKDIR /app

# Copy pre-exported requirements (pinned versions + hashes)
COPY requirements.txt ./

# Install production dependencies from public PyPI
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ src/
COPY frontend/ frontend/

# Expose port
EXPOSE 8000

# Run with uvicorn
CMD uvicorn src.api.app:app --host 0.0.0.0 --port ${PORT:-8000}
