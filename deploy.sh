#!/bin/bash
# Deploy the Cloud Function for automated BOOX PDF optimization.
#
# Prerequisites:
#   1. gcloud CLI installed and authenticated (gcloud auth login)
#   2. A GCP project with Cloud Functions API and Google Drive API enabled
#
# Usage:
#   ./deploy.sh <PROJECT_ID> [REGION]
#
# After deploying:
#   1. Share your Drive folder with: <PROJECT_ID>@appspot.gserviceaccount.com (Editor)
#   2. Set up the Apps Script (see apps_script/Code.gs)

set -euo pipefail

PROJECT_ID="${1:?Usage: ./deploy.sh <PROJECT_ID> [REGION]}"
REGION="${2:-us-central1}"
FUNCTION_NAME="boox-pdf-optimizer"
AUTH_TOKEN="$(openssl rand -hex 32)"

echo "==> Deploying to project: $PROJECT_ID, region: $REGION"

# Enable required APIs
echo "==> Enabling APIs..."
gcloud services enable cloudfunctions.googleapis.com drive.googleapis.com \
  --project="$PROJECT_ID" --quiet

# Copy pdfsimpler.py into cloud/ for deployment
cp pdfsimpler.py cloud/pdfsimpler.py

# Deploy
echo "==> Deploying Cloud Function..."
gcloud functions deploy "$FUNCTION_NAME" \
  --gen2 \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --runtime=python312 \
  --source=cloud/ \
  --entry-point=handle_request \
  --trigger-http \
  --allow-unauthenticated \
  --memory=1GiB \
  --timeout=540s \
  --set-env-vars="AUTH_TOKEN=$AUTH_TOKEN" \
  --max-instances=1

# Clean up copied file
rm cloud/pdfsimpler.py

# Get function URL
FUNCTION_URL=$(gcloud functions describe "$FUNCTION_NAME" \
  --gen2 --project="$PROJECT_ID" --region="$REGION" \
  --format='value(serviceConfig.uri)')

SERVICE_ACCOUNT="${PROJECT_ID}@appspot.gserviceaccount.com"

echo ""
echo "========================================"
echo "  Deployment complete!"
echo "========================================"
echo ""
echo "Cloud Function URL:"
echo "  $FUNCTION_URL"
echo ""
echo "Auth Token (save this!):"
echo "  $AUTH_TOKEN"
echo ""
echo "Next steps:"
echo "  1. Share your Google Drive folder with (Editor access):"
echo "     $SERVICE_ACCOUNT"
echo ""
echo "  2. Go to https://script.google.com and create a new project"
echo "     Paste the contents of apps_script/Code.gs"
echo ""
echo "  3. Set Script Properties (File > Project settings > Script properties):"
echo "     FOLDER_ID          = <your Drive folder ID>"
echo "     CLOUD_FUNCTION_URL = $FUNCTION_URL"
echo "     AUTH_TOKEN          = $AUTH_TOKEN"
echo ""
echo "  4. Add a trigger: Triggers > Add > watchFolder > Time-driven > Every 5 minutes"
echo ""
