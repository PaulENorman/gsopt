# Stage 1: Builder
# This stage installs dependencies.
FROM python:3.12-slim as builder

# Set environment variables to prevent pyc files and buffering
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required for compilation (scipy/numpy often need these)
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
RUN pip install --no-cache-dir -r requirements.txt

# --- Final Stage ---
FROM python:3.12-slim

WORKDIR /app

# Build Argument for Versioning
ARG COMMIT_SHA=unknown
ENV COMMIT_SHA=${COMMIT_SHA}

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy the application code
# This is the layer that changes most often, so we put it last.
COPY . .

# Expose port
EXPOSE 8080

# Command to calculate number of workers based on CPU cores for better performance
CMD exec gunicorn --bind :8080 --workers 1 --threads 8 --timeout 0 gsopt:app
