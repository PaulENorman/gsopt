# Stage 1: Builder
# This stage installs dependencies.
FROM python:3.12-slim as builder
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Final image
# This stage copies the installed dependencies and source code to a clean base image.
FROM python:3.12-slim
WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create a non-root user and switch to it
RUN useradd --create-home appuser
USER appuser
WORKDIR /home/appuser/app

# Copy application code
COPY . .

EXPOSE 8080
CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:8080", "gsopt:app"]
