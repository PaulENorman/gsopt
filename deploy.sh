#!/bin/bash
set -e

PROJECT_ID="gsopt-478412"
REGION="europe-west1"
SERVICE_NAME="gsopt"

echo "🚀 Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --source . \
  --dockerfile Dockerfile \
  --region $REGION \
  --no-allow-unauthenticated

echo "✅ Success!"
