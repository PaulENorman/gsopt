#!/bin/bash
set -e

PROJECT_ID="gsopt-478412"
REGION="europe-west1"
SERVICE_NAME="gsopt"

echo "🚀 Deploying to Cloud Run with BuildKit optimization..."
# Use Cloud Build with cloudbuild.yaml to enable BuildKit caching
gcloud builds submit --config cloudbuild.yaml --region $REGION .

echo "✅ Success!"
