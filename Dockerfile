# Stage 1: Builder
# This stage installs dependencies.
FROM python:3.12-slim as builder

# Security: Run as non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set environment variables to prevent pyc files and buffering
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install only necessary build dependencies
# We combine these into one RUN to reduce layer count
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy ONLY requirements first. 
# Docker will cache this layer as long as requirements.txt doesn't change.
COPY requirements.txt .

# Install dependencies into a virtual environment
# This makes copying them to the final image easier
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# --- Final Stage ---
FROM python:3.12-slim

# Security: Run as non-root
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Build Argument for Versioning - remove default to make it required
ARG COMMIT_SHA
ENV COMMIT_SHA=${COMMIT_SHA:-development}

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy the application code
# This is the layer that changes most often, so we put it last.
COPY --chown=appuser:appuser . .

# Security: Remove unnecessary files
RUN find . -type f -name "*.pyc" -delete && \
    find . -type d -name "__pycache__" -delete && \
    rm -rf tests/ .git/ .github/ *.md

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8080

# Use exec form for proper signal handling
CMD ["gunicorn", "--bind", ":8080", "--workers", "1", "--threads", "8", "--timeout", "0", "gsopt:app"]
