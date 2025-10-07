#!/bin/bash

# MVidarr Phase 2 Health Check Script
# Validates all components are running correctly

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🏥 MVidarr Phase 2 Health Check"
echo "================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SUCCESS=0
WARNINGS=0
ERRORS=0

check_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✅ $2${NC}"
        ((SUCCESS++))
    else
        echo -e "${RED}❌ $2${NC}"
        ((ERRORS++))
    fi
}

check_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
    ((WARNINGS++))
}

echo "📋 Checking System Components..."
echo "================================"

# Check Docker
echo -n "Checking Docker service... "
if systemctl is-active --quiet docker; then
    check_status 0 "Docker service is running"
else
    check_status 1 "Docker service is not running"
fi

# Check Docker Compose
echo -n "Checking Docker Compose... "
if command -v docker-compose &> /dev/null; then
    check_status 0 "Docker Compose is available"
else
    check_status 1 "Docker Compose is not available"
fi

# Check Python Virtual Environment
echo -n "Checking Python virtual environment... "
if [ -f "$PROJECT_DIR/venv/bin/python" ]; then
    check_status 0 "Python virtual environment exists"
else
    check_status 1 "Python virtual environment not found"
fi

echo ""
echo "📦 Checking Phase 2 Infrastructure..."
echo "====================================="

cd "$PROJECT_DIR"

# Check Redis Container
echo -n "Checking Redis container... "
if docker ps --format "table {{.Names}}" | grep -q "mvidarr_redis"; then
    if docker exec mvidarr_redis redis-cli ping > /dev/null 2>&1; then
        check_status 0 "Redis container is running and responsive"
    else
        check_status 1 "Redis container exists but not responsive"
    fi
else
    check_status 1 "Redis container not found"
fi

# Check Celery Worker
echo -n "Checking Celery worker... "
if docker ps --format "table {{.Names}}" | grep -q "mvidarr_celery_worker"; then
    if docker exec mvidarr_celery_worker celery -A src.jobs.celery_app inspect ping > /dev/null 2>&1; then
        check_status 0 "Celery worker is running and responsive"
    else
        check_status 1 "Celery worker exists but not responsive"
    fi
else
    check_status 1 "Celery worker container not found"
fi

# Check Celery Beat
echo -n "Checking Celery beat scheduler... "
if docker ps --format "table {{.Names}}" | grep -q "mvidarr_celery_beat"; then
    check_status 0 "Celery beat scheduler is running"
else
    check_status 1 "Celery beat scheduler not found"
fi

# Check Flower Monitoring
echo -n "Checking Flower monitoring... "
if docker ps --format "table {{.Names}}" | grep -q "mvidarr_celery_flower"; then
    if curl -f http://localhost:5555 > /dev/null 2>&1; then
        check_status 0 "Flower monitoring is accessible"
    else
        check_warning "Flower container running but not accessible on port 5555"
    fi
else
    check_status 1 "Flower monitoring container not found"
fi

echo ""
echo "🎯 Checking Application Services..."
echo "=================================="

# Check FastAPI Application
echo -n "Checking FastAPI application... "
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    check_status 0 "FastAPI application is responding on port 8000"
elif curl -f http://localhost:5000/health > /dev/null 2>&1; then
    check_status 0 "Application is responding on port 5000"
else
    check_status 1 "Application not responding on expected ports"
fi

# Check WebSocket endpoint
echo -n "Checking WebSocket endpoint... "
if curl -f http://localhost:8000/docs > /dev/null 2>&1; then
    check_status 0 "WebSocket documentation accessible"
elif curl -f http://localhost:5000/docs > /dev/null 2>&1; then
    check_status 0 "Application documentation accessible"
else
    check_warning "Application documentation not accessible"
fi

echo ""
echo "🔧 Checking FFmpeg and Dependencies..."
echo "====================================="

# Check FFmpeg
echo -n "Checking FFmpeg installation... "
if command -v ffmpeg &> /dev/null; then
    check_status 0 "FFmpeg is available"
else
    check_status 1 "FFmpeg not found - required for video processing"
fi

# Check FFprobe
echo -n "Checking FFprobe installation... "
if command -v ffprobe &> /dev/null; then
    check_status 0 "FFprobe is available"
else
    check_status 1 "FFprobe not found - required for metadata extraction"
fi

echo ""
echo "📁 Checking Directory Structure..."
echo "================================="

# Check required directories
directories=(
    "data/logs"
    "data/downloads" 
    "data/thumbnails"
    "data/cache"
    "data/backups"
    "data/processing"
)

for dir in "${directories[@]}"; do
    echo -n "Checking $dir... "
    if [ -d "$PROJECT_DIR/$dir" ]; then
        check_status 0 "$dir exists"
    else
        check_status 1 "$dir missing"
    fi
done

echo ""
echo "🚀 Checking Phase 2 Week 19 Features..."
echo "======================================="

# Check Phase 2 Week 19 task files
echo -n "Checking advanced FFmpeg tasks... "
if [ -f "$PROJECT_DIR/src/jobs/ffmpeg_processing_tasks.py" ]; then
    if grep -q "FFmpegAdvancedFormatConversionTask" "$PROJECT_DIR/src/jobs/ffmpeg_processing_tasks.py"; then
        check_status 0 "Advanced FFmpeg tasks are implemented"
    else
        check_status 1 "Advanced FFmpeg tasks not found in file"
    fi
else
    check_status 1 "FFmpeg processing tasks file not found"
fi

# Check video quality tasks
echo -n "Checking video quality tasks... "
if [ -f "$PROJECT_DIR/src/jobs/video_quality_tasks.py" ]; then
    check_status 0 "Video quality tasks are available"
else
    check_warning "Video quality tasks file not found (optional)"
fi

# Check service files
echo -n "Checking systemd service file... "
if [ -f "$PROJECT_DIR/mvidarr.service" ]; then
    if grep -q "PHASE_2_ADVANCED_PROCESSING=enabled" "$PROJECT_DIR/mvidarr.service"; then
        check_status 0 "Service file updated for Phase 2"
    else
        check_status 1 "Service file not updated for Phase 2"
    fi
else
    check_status 1 "Service file not found"
fi

echo ""
echo "📊 Health Check Summary"
echo "======================"
echo -e "${GREEN}✅ Successful checks: $SUCCESS${NC}"
echo -e "${YELLOW}⚠️  Warnings: $WARNINGS${NC}"
echo -e "${RED}❌ Failed checks: $ERRORS${NC}"

if [ $ERRORS -eq 0 ]; then
    if [ $WARNINGS -eq 0 ]; then
        echo -e "${GREEN}🎉 All systems operational! MVidarr Phase 2 is ready.${NC}"
        exit 0
    else
        echo -e "${YELLOW}✅ Core systems operational with minor warnings.${NC}"
        exit 0
    fi
else
    echo -e "${RED}💥 Critical issues found. Please resolve errors before running.${NC}"
    echo ""
    echo "🔧 Common fixes:"
    echo "  - Start Docker: sudo systemctl start docker"
    echo "  - Start containers: docker-compose -f docker-compose.redis.yml up -d"
    echo "  - Create venv: python3 -m venv venv"
    echo "  - Install FFmpeg: sudo apt-get install ffmpeg"
    exit 1
fi