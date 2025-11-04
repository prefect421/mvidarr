#!/bin/bash
# Diagnostic script to get FastAPI error from production

echo "=== Checking container status ==="
docker ps -a | grep mvidarr

echo -e "\n=== Getting last 100 lines of FastAPI error log ==="
CONTAINER_ID=$(docker ps | grep mvidarr | grep -v redis | grep -v mariadb | awk '{print $1}')
docker exec $CONTAINER_ID tail -100 /app/data/logs/fastapi_error.log 2>&1

echo -e "\n=== Getting Python traceback from supervisord logs ==="
docker logs $CONTAINER_ID 2>&1 | grep -A 20 "Traceback\|Error\|Exception" | tail -50

echo -e "\n=== Checking if container has new image ==="
docker inspect $CONTAINER_ID | grep -A 5 "Image"
