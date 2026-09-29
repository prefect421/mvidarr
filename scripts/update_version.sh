#!/bin/bash

# MVidarr Version Update Script
# Automatically updates version.json with current commit and timestamp

set -e

echo "🔄 Updating MVidarr version metadata..."

# Get current commit and timestamp
CURRENT_COMMIT=$(git rev-parse --short HEAD)
CURRENT_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S.%6N")
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo "📝 Current commit: $CURRENT_COMMIT"
echo "⏰ Current timestamp: $CURRENT_TIMESTAMP"
echo "🌿 Current branch: $CURRENT_BRANCH"

# Read current version from version.json
CURRENT_VERSION=$(grep '"version"' version.json | sed 's/.*"version": "\([^"]*\)".*/\1/')
CURRENT_RELEASE_NAME=$(grep '"release_name"' version.json | sed 's/.*"release_name": "\([^"]*\)".*/\1/')

echo "📦 Keeping version: $CURRENT_VERSION"
echo "🏷️  Release name: $CURRENT_RELEASE_NAME"

# Update only the build metadata; keep version, release_name and the
# hand-maintained features list exactly as committed
CURRENT_TIMESTAMP="$CURRENT_TIMESTAMP" CURRENT_COMMIT="$CURRENT_COMMIT" CURRENT_BRANCH="$CURRENT_BRANCH" python3 - << 'PYEOF'
import json
import os

with open("version.json") as f:
    data = json.load(f)
data["build_date"] = os.environ["CURRENT_TIMESTAMP"]
data["git_commit"] = os.environ["CURRENT_COMMIT"]
data["git_branch"] = os.environ["CURRENT_BRANCH"]
with open("version.json", "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
PYEOF

echo "✅ Version metadata updated successfully!"
echo "💡 Remember to commit this change:"
echo "   git add version.json"
echo "   git commit -m 'Update version metadata with current commit information'"
echo ""
echo "🐳 After pushing, the Docker image will show: v$CURRENT_VERSION ($CURRENT_COMMIT)"