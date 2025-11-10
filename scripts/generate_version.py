#!/usr/bin/env python3
"""
Generate version.json at Docker build time with correct git information.
This ensures the Docker image always shows the correct commit hash.

Usage:
    python3 scripts/generate_version.py --output version.json

Environment Variables:
    GIT_COMMIT: Git commit hash (short or full)
    GIT_BRANCH: Git branch name
    BUILD_DATE: Build timestamp (ISO 8601 format)
    VERSION: Application version (defaults to reading from src/__init__.py)
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def get_version_from_init():
    """Read version from src/__init__.py"""
    init_file = Path(__file__).parent.parent / "src" / "__init__.py"

    if not init_file.exists():
        return "1.0.0-dev"

    with open(init_file, "r") as f:
        for line in f:
            if line.startswith("__version__"):
                # Extract version from: __version__ = "1.0.0-dev"
                return line.split("=")[1].strip().strip('"').strip("'")

    return "1.0.0-dev"


def generate_version_json(output_path: str):
    """
    Generate version.json with git information from environment variables.

    Args:
        output_path: Path where version.json should be written
    """
    # Get git information from environment (set by Docker build args)
    git_commit = os.getenv("GIT_COMMIT", "unknown")
    git_branch = os.getenv("GIT_BRANCH", "unknown")
    build_date = os.getenv("BUILD_DATE", datetime.utcnow().isoformat())
    version = os.getenv("VERSION", get_version_from_init())

    # Determine release name based on version
    if "dev" in version:
        release_name = "v1.0.0 Development - First Production Release"
    elif version.startswith("1.0.0"):
        release_name = "v1.0.0 - First Production Release"
    else:
        release_name = f"v{version}"

    # Build version data structure
    version_data = {
        "version": version,
        "build_date": build_date,
        "git_commit": git_commit,
        "git_branch": git_branch,
        "release_name": release_name,
        "features": [
            "🎉 First production-ready release milestone",
            "🔧 Installation Wizard for first-run setup (Issue #163)",
            "🎬 Reliable video import system (no duplicates)",
            "✅ API validation before configuration",
            "📁 Directory validation and auto-configuration",
            "🔌 IMVDb and YouTube cookie setup",
            "📊 Real-time import progress tracking",
            "🚀 Production-ready onboarding experience"
        ]
    }

    # Write version.json
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w") as f:
        json.dump(version_data, f, indent=2)

    print(f"✅ Generated {output_path}")
    print(f"   Version: {version}")
    print(f"   Commit: {git_commit}")
    print(f"   Branch: {git_branch}")
    print(f"   Build Date: {build_date}")

    return version_data


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Generate version.json for Docker builds"
    )
    parser.add_argument(
        "--output",
        default="version.json",
        help="Output path for version.json (default: version.json)"
    )

    args = parser.parse_args()

    try:
        generate_version_json(args.output)
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error generating version.json: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
