#!/usr/bin/env python3
"""
Backup Management CLI for MVidarr
Provides easy-to-use interface for backup and restore operations

Usage:
    python3 scripts/manage_backups.py create --type database
    python3 scripts/manage_backups.py create --type full
    python3 scripts/manage_backups.py list
    python3 scripts/manage_backups.py restore <backup_id>
    python3 scripts/manage_backups.py delete <backup_id>
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.backup_service import BackupService, BackupType


def create_backup(backup_type: str):
    """Create a new backup"""
    try:
        # Convert string to BackupType enum
        backup_type_enum = BackupType[backup_type.upper()]
    except KeyError:
        print(f"❌ Invalid backup type: {backup_type}")
        print(f"   Valid types: database, configuration, thumbnails, full")
        return 1

    print(f"🔄 Creating {backup_type} backup...")

    backup_service = BackupService()
    metadata = backup_service.create_backup(backup_type_enum)

    if metadata and metadata.status.value == "success":
        print(f"✅ Backup created successfully!")
        print(f"   Backup ID: {metadata.backup_id}")
        print(f"   File: {metadata.file_path}")
        print(f"   Size: {metadata.to_dict()['file_size_mb']}MB")
        print(f"   Timestamp: {metadata.timestamp}")
        return 0
    else:
        print(f"❌ Backup failed!")
        if metadata and metadata.error:
            print(f"   Error: {metadata.error}")
        return 1


def list_backups(backup_type: str = None):
    """List all available backups"""
    backup_service = BackupService()

    # Filter by type if specified
    type_filter = None
    if backup_type:
        try:
            type_filter = BackupType[backup_type.upper()]
        except KeyError:
            print(f"❌ Invalid backup type: {backup_type}")
            return 1

    backups = backup_service.list_backups(type_filter)

    if not backups:
        print("📦 No backups found")
        return 0

    # Print backups in a simple table format
    print("\n📦 Available Backups:")
    print("=" * 100)
    print(
        f"{'Backup ID':<40} {'Type':<15} {'Timestamp':<20} {'Size':<10} {'Status':<10}"
    )
    print("-" * 100)

    for backup in sorted(backups, key=lambda b: b.timestamp, reverse=True):
        data_dict = backup.to_dict()
        print(
            f"{backup.backup_id:<40} "
            f"{backup.backup_type.value:<15} "
            f"{backup.timestamp.strftime('%Y-%m-%d %H:%M:%S'):<20} "
            f"{data_dict['file_size_mb']:<10}MB "
            f"{backup.status.value:<10}"
        )

    print("=" * 100)
    print(f"\nTotal backups: {len(backups)}")

    return 0


def restore_backup(backup_id: str, force: bool = False):
    """Restore from a backup"""
    if not force:
        print("⚠️  WARNING: This will overwrite current data!")
        response = input(f"   Are you sure you want to restore {backup_id}? (yes/no): ")
        if response.lower() != "yes":
            print("❌ Restore cancelled")
            return 1

    print(f"🔄 Restoring from backup: {backup_id}")

    backup_service = BackupService()
    success = backup_service.restore_backup(backup_id)

    if success:
        print("✅ Restore completed successfully!")
        print("   ⚠️  You may need to restart MVidarr for changes to take effect")
        return 0
    else:
        print("❌ Restore failed!")
        return 1


def delete_backup(backup_id: str, force: bool = False):
    """Delete a backup"""
    if not force:
        response = input(f"⚠️  Are you sure you want to delete {backup_id}? (yes/no): ")
        if response.lower() != "yes":
            print("❌ Delete cancelled")
            return 1

    print(f"🗑️  Deleting backup: {backup_id}")

    backup_service = BackupService()
    success = backup_service.delete_backup(backup_id)

    if success:
        print("✅ Backup deleted successfully")
        return 0
    else:
        print("❌ Delete failed!")
        return 1


def show_info():
    """Show backup configuration and statistics"""
    backup_service = BackupService()

    print("📊 Backup Configuration:")
    print(f"   Backup Directory: {backup_service.backup_dir}")
    print(f"   Retention Days: {backup_service.retention_days}")
    print(f"   Max Backups: {backup_service.max_backups}")

    # Count backups by type
    all_backups = backup_service.list_backups()
    type_counts = {}
    total_size = 0

    for backup in all_backups:
        backup_type = backup.backup_type.value
        type_counts[backup_type] = type_counts.get(backup_type, 0) + 1
        total_size += backup.file_size

    print(f"\n📦 Backup Statistics:")
    print(f"   Total Backups: {len(all_backups)}")
    for backup_type, count in type_counts.items():
        print(f"   {backup_type.capitalize()}: {count}")
    print(f"   Total Size: {round(total_size / (1024 * 1024), 2)}MB")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Manage MVidarr backups",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create database backup
  python3 scripts/manage_backups.py create --type database

  # Create full backup (database + config + thumbnails)
  python3 scripts/manage_backups.py create --type full

  # List all backups
  python3 scripts/manage_backups.py list

  # List only database backups
  python3 scripts/manage_backups.py list --type database

  # Restore from backup
  python3 scripts/manage_backups.py restore database_20251110_123456

  # Delete backup
  python3 scripts/manage_backups.py delete database_20251110_123456

  # Show backup info
  python3 scripts/manage_backups.py info
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Backup command to execute")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new backup")
    create_parser.add_argument(
        "--type",
        choices=["database", "configuration", "thumbnails", "full"],
        required=True,
        help="Type of backup to create",
    )

    # List command
    list_parser = subparsers.add_parser("list", help="List available backups")
    list_parser.add_argument(
        "--type",
        choices=["database", "configuration", "thumbnails", "full"],
        help="Filter by backup type",
    )

    # Restore command
    restore_parser = subparsers.add_parser("restore", help="Restore from a backup")
    restore_parser.add_argument("backup_id", help="Backup ID to restore")
    restore_parser.add_argument(
        "--force", action="store_true", help="Skip confirmation prompt"
    )

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a backup")
    delete_parser.add_argument("backup_id", help="Backup ID to delete")
    delete_parser.add_argument(
        "--force", action="store_true", help="Skip confirmation prompt"
    )

    # Info command
    subparsers.add_parser("info", help="Show backup configuration and statistics")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Execute command
    try:
        if args.command == "create":
            return create_backup(args.type)
        elif args.command == "list":
            return list_backups(args.type if hasattr(args, "type") else None)
        elif args.command == "restore":
            return restore_backup(args.backup_id, args.force)
        elif args.command == "delete":
            return delete_backup(args.backup_id, args.force)
        elif args.command == "info":
            return show_info()
        else:
            print(f"❌ Unknown command: {args.command}")
            return 1

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
