#!/bin/bash
set -e

PROJECT_ID="gsopt-478412"
REGION="europe-west1"
SERVICE_NAME="gsopt"

echo "🚀 Starting deployment script..."
echo "📂 Working directory: $(pwd)"
echo "📄 Using cloudbuild.yaml..."

# Force submission with the config and ensure public access as we rely on email header auth
gcloud builds submit --config cloudbuild.yaml --region $REGION .

# Ensure the service allows unauthenticated access so the Apps Script can reach it
gcloud run services add-iam-policy-binding $SERVICE_NAME \
  --member="allUsers" \
  --role="roles/run.invoker" \
  --region=$REGION \
  --platform=managed \
  --quiet

echo "✅ Success!"
