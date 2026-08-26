#!/bin/bash
# Deploy the background worker fix to production

echo "=== Deploying Worker Fix to Production ==="
echo ""

# SSH into production and deploy
echo "Step 1: Pull latest code..."
ssh mike@192.168.1.132 "cd mvidarr && git fetch && git pull origin main"
echo ""

echo "Step 2: Check current Docker image version..."
ssh mike@192.168.1.132 "docker exec mvidarr-prod cat /app/version.json | grep -E '(version|git_commit|release_name)'"
echo ""

echo "Step 3: Pull latest Docker image..."
ssh mike@192.168.1.132 "docker pull ghcr.io/prefect421/mvidarr:dev"
echo ""

echo "Step 4: Restart production container..."
ssh mike@192.168.1.132 "cd mvidarr && docker-compose -f docker-compose.production.yml down && docker-compose -f docker-compose.production.yml up -d"
echo ""

echo "Step 5: Wait for startup..."
sleep 10
echo ""

echo "Step 6: Verify new version is running..."
curl -s "http://192.168.1.132:5050/health" | python3 -m json.tool
echo ""

echo "=== Deployment Complete ==="
echo ""
echo "The fix has been deployed. You can now try re-indexing your videos."
echo "The job should now complete properly instead of getting stuck!"
