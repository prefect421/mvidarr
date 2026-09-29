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

# Create temporary file with updated metadata
cat > version.json.tmp << EOF
{
  "version": "$CURRENT_VERSION",
  "build_date": "$CURRENT_TIMESTAMP",
  "git_commit": "$CURRENT_COMMIT",
  "git_branch": "$CURRENT_BRANCH",
  "release_name": "$CURRENT_RELEASE_NAME",
  "features": [
    "Advanced Artist Management with multi-criteria search and bulk operations",
    "Comprehensive Video Discovery with dual-source integration (MusicBrainz + YouTube)",
    "Professional Thumbnail Management with multi-source search and cropping",
    "Intelligent Organization with automatic folder creation and cleanup",
    "Advanced Search System with real-time suggestions and filtering",
    "Bulk Operations with multi-select editing and batch processing",
    "Video Streaming with built-in player and transcoding",
    "System Health monitoring with comprehensive diagnostics",
    "Database-Driven Settings with complete configuration management",
    "Download Management with queue visualization and progress tracking",
    "Multi-User Authentication with role-based access control",
    "Advanced Security with password policies and audit logging",
    "Modern UI with left sidebar navigation and theme system",
    "MvTV Continuous Player with cinematic mode",
    "Two-Factor Authentication with TOTP support",
    "Fixed Video Search Results Display with improved CSS and field mapping",
    "Robust CI/CD Integration with comprehensive testing and deployment",
    "Enhanced Database Initialization with secure admin user creation"
  ]
}
EOF

# Replace the original file
mv version.json.tmp version.json

echo "✅ Version metadata updated successfully!"
echo "💡 Remember to commit this change:"
echo "   git add version.json"
echo "   git commit -m 'Update version metadata with current commit information'"
echo ""
echo "🐳 After pushing, the Docker image will show: v$CURRENT_VERSION ($CURRENT_COMMIT)"