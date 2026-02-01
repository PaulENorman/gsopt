#!/bin/bash
set -e

PROJECT_ID="gsopt-478412"
REGION="europe-west1"
SERVICE_NAME="gsopt"

echo "🚀 Starting deployment script..."
echo "📂 Working directory: $(pwd)"
echo "📄 Using cloudbuild.yaml..."

# Force submission with the config and ensure authentication on GCP while relying on email header auth for app logic
gcloud builds submit --config cloudbuild.yaml --region $REGION .

# Re-enable requirement for a Google account (allAuthenticatedUsers)
gcloud run services add-iam-policy-binding $SERVICE_NAME \
  --member="allAuthenticatedUsers" \
  --role="roles/run.invoker" \
  --region=$REGION \
  --platform=managed \
  --quiet

echo "✅ Success!"
