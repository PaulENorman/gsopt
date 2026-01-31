#!/bin/bash
set -e

echo "🐳 Testing local Docker build with BuildKit..."

# Enable BuildKit
export DOCKER_BUILDKIT=1

# Check docker version
docker --version

# Attempt build
docker build -t gsopt-test:latest .

echo "✅ Local build successful! BuildKit is working locally."
