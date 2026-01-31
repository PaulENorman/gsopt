#!/bin/bash
set -e

PROJECT_ID="gsopt-478412"
REGION="europe-west1"
SERVICE_NAME="gsopt"

echo "🚀 Starting deployment script..."
echo "📂 Working directory: $(pwd)"
echo "📄 Using cloudbuild.yaml..."

# Force submission with the config
gcloud builds submit --config cloudbuild.yaml --region $REGION .

echo "✅ Success!"
