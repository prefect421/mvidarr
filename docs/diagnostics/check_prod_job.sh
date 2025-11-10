#!/bin/bash
# Check production job status and worker health

PROD_URL="http://192.168.1.132:5050"
JOB_ID="ddb1ae09-2335-482e-a7c4-30b990463b0a"

echo "=== Checking Production MVidarr ==="
echo ""

echo "1. Checking application health..."
curl -s "${PROD_URL}/health" | python3 -m json.tool
echo ""

echo "2. Checking worker stats..."
curl -s "${PROD_URL}/api/advanced-jobs/analytics?days=1" | python3 -m json.tool
echo ""

echo "3. Checking specific job status (Job ID: ${JOB_ID})..."
curl -s "${PROD_URL}/api/advanced-jobs/${JOB_ID}" | python3 -m json.tool
echo ""

echo "4. Listing recent jobs..."
curl -s "${PROD_URL}/api/advanced-jobs/?limit=10" | python3 -m json.tool
echo ""

echo "5. Checking video indexing stats..."
curl -s "${PROD_URL}/api/video-indexing/stats" | python3 -m json.tool
echo ""
