#!/usr/bin/env python3
"""
Database Migration Management Script for MVidarr
Provides easy-to-use interface for Alembic database migrations

Usage:
    python3 scripts/manage_migrations.py upgrade       # Upgrade to latest
    python3 scripts/manage_migrations.py upgrade +1    # Upgrade one version
    python3 scripts/manage_migrations.py downgrade -1  # Downgrade one version
    python3 scripts/manage_migrations.py current       # Show current version
    python3 scripts/manage_migrations.py history       # Show migration history
    python3 scripts/manage_migrations.py heads         # Show head revisions
    python3 scripts/manage_migrations.py create "description"  # Create new migration
"""

import argparse
import subprocess
import sys
from pathlib import Path


def run_alembic_command(args):
    """Run an alembic command with proper environment setup"""
    project_root = Path(__file__).parent.parent

    # Use venv python if available, otherwise use system python
    venv_python = project_root / "venv" / "bin" / "python3"
    python_cmd = str(venv_python) if venv_python.exists() else sys.executable

    # Build command - use alembic directly from venv
    venv_alembic = project_root / "venv" / "bin" / "alembic"
    if venv_alembic.exists():
        cmd = [str(venv_alembic)] + args
    else:
        cmd = [python_cmd, "-m", "alembic"] + args

    # Run command from project root
    result = subprocess.run(
        cmd,
        cwd=project_root,
        capture_output=False,
        text=True
    )

    return result.returncode


def upgrade(target="head"):
    """Upgrade database to a specific revision"""
    print(f"🔄 Upgrading database to: {target}")
    return run_alembic_command(["upgrade", target])


def downgrade(target):
    """Downgrade database to a specific revision"""
    print(f"🔄 Downgrading database to: {target}")
    response = input(f"⚠️  Are you sure you want to downgrade to {target}? (yes/no): ")
    if response.lower() != "yes":
        print("❌ Downgrade cancelled")
        return 1

    return run_alembic_command(["downgrade", target])


def current():
    """Show current database revision"""
    print("📍 Current database revision:")
    return run_alembic_command(["current"])


def history():
    """Show migration history"""
    print("📜 Migration history:")
    return run_alembic_command(["history", "--verbose"])


def heads():
    """Show head revisions"""
    print("🎯 Head revisions:")
    return run_alembic_command(["heads", "--verbose"])


def create_revision(message):
    """Create a new migration"""
    print(f"✨ Creating new migration: {message}")
    return run_alembic_command(["revision", "-m", message])


def create_autogenerate(message):
    """Create a new migration with autogenerate"""
    print(f"🔍 Auto-generating migration: {message}")
    print("⚠️  WARNING: Always review auto-generated migrations before applying!")
    return run_alembic_command(["revision", "--autogenerate", "-m", message])


def stamp(revision):
    """Stamp database with a specific revision without running migrations"""
    print(f"🏷️  Stamping database with revision: {revision}")
    response = input(f"⚠️  Are you sure you want to stamp the database with {revision}? (yes/no): ")
    if response.lower() != "yes":
        print("❌ Stamp cancelled")
        return 1

    return run_alembic_command(["stamp", revision])


def main():
    parser = argparse.ArgumentParser(
        description="Manage MVidarr database migrations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upgrade to latest version
  python3 scripts/manage_migrations.py upgrade

  # Upgrade one version
  python3 scripts/manage_migrations.py upgrade +1

  # Downgrade one version
  python3 scripts/manage_migrations.py downgrade -1

  # Show current version
  python3 scripts/manage_migrations.py current

  # Show migration history
  python3 scripts/manage_migrations.py history

  # Create new migration
  python3 scripts/manage_migrations.py create "add user preferences"

  # Auto-generate migration from model changes
  python3 scripts/manage_migrations.py autogenerate "add new fields"
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Migration command to execute")

    # Upgrade command
    upgrade_parser = subparsers.add_parser("upgrade", help="Upgrade database to a specific revision")
    upgrade_parser.add_argument("target", nargs="?", default="head", help="Target revision (default: head)")

    # Downgrade command
    downgrade_parser = subparsers.add_parser("downgrade", help="Downgrade database to a specific revision")
    downgrade_parser.add_argument("target", help="Target revision (e.g., -1, base, <revision_id>)")

    # Current command
    subparsers.add_parser("current", help="Show current database revision")

    # History command
    subparsers.add_parser("history", help="Show migration history")

    # Heads command
    subparsers.add_parser("heads", help="Show head revisions")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new migration")
    create_parser.add_argument("message", help="Migration description")

    # Autogenerate command
    auto_parser = subparsers.add_parser("autogenerate", help="Auto-generate migration from model changes")
    auto_parser.add_argument("message", help="Migration description")

    # Stamp command
    stamp_parser = subparsers.add_parser("stamp", help="Stamp database with a revision without running migrations")
    stamp_parser.add_argument("revision", help="Revision to stamp")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Execute command
    command_map = {
        "upgrade": lambda: upgrade(args.target if hasattr(args, 'target') else "head"),
        "downgrade": lambda: downgrade(args.target),
        "current": current,
        "history": history,
        "heads": heads,
        "create": lambda: create_revision(args.message),
        "autogenerate": lambda: create_autogenerate(args.message),
        "stamp": lambda: stamp(args.revision),
    }

    exit_code = command_map[args.command]()

    if exit_code == 0:
        print("✅ Migration command completed successfully")
    else:
        print("❌ Migration command failed")
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
