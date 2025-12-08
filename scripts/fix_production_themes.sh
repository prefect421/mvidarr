#!/bin/bash
##############################################################################
# Fix Production Themes - Seed Built-in Themes into Database
# This script addresses the issue where built-in themes were not installed
# during production deployment.
##############################################################################

set -e

echo "=============================================="
echo "🎨 MVidarr Theme Installation Fix"
echo "=============================================="
echo "📅 $(date)"
echo ""

# Check if running on production server
if [ -z "$MVIDARR_PRODUCTION" ]; then
    echo "⚠️  This script is designed for production deployment"
    echo "   Set MVIDARR_PRODUCTION=1 to run on production"
    echo ""
    read -p "Run anyway? (y/N): " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        echo "Aborted."
        exit 0
    fi
fi

echo "🔍 Checking current theme status..."
echo ""

# Method 1: Run inside existing container
if command -v docker &> /dev/null; then
    echo "📦 Detected Docker - attempting to seed themes in container..."

    # Find the mvidarr container
    CONTAINER_ID=$(docker ps -q -f name=mvidarr)

    if [ -z "$CONTAINER_ID" ]; then
        echo "❌ MVidarr container not found"
        echo "   Looking for stopped containers..."
        CONTAINER_ID=$(docker ps -aq -f name=mvidarr | head -1)

        if [ -z "$CONTAINER_ID" ]; then
            echo "❌ No MVidarr containers found at all"
            echo ""
            echo "Manual fix required:"
            echo "1. SSH to production server"
            echo "2. Navigate to MVidarr directory"
            echo "3. Run: docker exec mvidarr python3 /app/scripts/seed_builtin_themes.py"
            exit 1
        else
            echo "⚠️  MVidarr container is stopped"
            echo "   Start it first with: docker start mvidarr"
            exit 1
        fi
    fi

    echo "✅ Found MVidarr container: $CONTAINER_ID"
    echo ""

    # Execute theme seeding script inside container
    echo "🌱 Seeding built-in themes..."
    docker exec $CONTAINER_ID python3 /app/scripts/seed_builtin_themes.py

    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ Theme installation completed successfully!"
        echo ""
        echo "🔄 Restart MVidarr to apply changes:"
        echo "   docker restart mvidarr"
        echo ""
        echo "   OR via docker-compose:"
        echo "   docker-compose restart mvidarr"
    else
        echo ""
        echo "❌ Theme installation failed - check logs above"
        exit 1
    fi

else
    # Method 2: Run directly (if not in Docker)
    echo "🐍 No Docker detected - running theme seeding directly..."

    # Check if seed script exists
    if [ ! -f "scripts/seed_builtin_themes.py" ]; then
        echo "❌ Theme seed script not found"
        echo "   Expected location: scripts/seed_builtin_themes.py"
        echo "   Are you in the MVidarr root directory?"
        exit 1
    fi

    # Run the seed script
    python3 scripts/seed_builtin_themes.py

    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ Theme installation completed successfully!"
        echo ""
        echo "🔄 Restart MVidarr to apply changes"
    else
        echo ""
        echo "❌ Theme installation failed - check logs above"
        exit 1
    fi
fi

echo ""
echo "=============================================="
echo "📚 Installed Themes:"
echo "=============================================="
echo "1. Cyber - Cyberpunk-inspired with cyan accents"
echo "2. Default - Classic dark theme with blue"
echo "3. VaporWave - Synthwave/retro aesthetic"
echo "4. LCARS DS9 - Star Trek Deep Space Nine"
echo "5. LCARS VOY - Star Trek Voyager"
echo "6. LCARS TNG-E - Star Trek Enterprise"
echo ""
echo "Visit Settings → Themes to select your theme!"
echo "=============================================="
