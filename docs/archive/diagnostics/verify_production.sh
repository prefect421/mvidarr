#!/bin/bash
# Verify production deployment

PROD_URL="http://192.168.1.132:5050"

echo "=== Verifying Production Deployment ==="
echo ""

echo "1. Health Check:"
curl -s "${PROD_URL}/health" | python3 -m json.tool
echo ""

echo "2. Check Docker Container Status:"
ssh mike@192.168.1.132 "docker ps | grep mvidarr"
echo ""

echo "3. Check Recent Logs:"
ssh mike@192.168.1.132 "docker logs mvidarr-prod --tail 20"
echo ""

echo "4. Check Worker Status:"
curl -s "${PROD_URL}/api/advanced-jobs/analytics?days=1" | python3 -m json.tool | grep -E "(total_jobs|completed_jobs|failed_jobs|success_rate)"
echo ""

echo "=== Verification Complete ==="
