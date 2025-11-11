#!/usr/bin/env python3
"""
Reset Database for Wizard Testing
Clears wizard_state and users tables to simulate first-run experience
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database.connection import get_db_session, DatabaseManager
from database.models import WizardState, User
from config.config import Config
from sqlalchemy import text

def reset_for_wizard():
    """Reset database to trigger installation wizard"""

    print("🔄 Resetting database for wizard testing...")
    print()

    try:
        # Initialize database connection
        print("📡 Initializing database connection...")
        config = Config()
        import src.database.connection as db_conn
        db_manager = DatabaseManager(config)
        db_conn.db_manager = db_manager
        engine = db_manager.create_engine()
        db_conn.engine = engine
        SessionLocal = db_manager.create_session_factory()
        db_conn.SessionLocal = SessionLocal
        print("✅ Database connection initialized")
        print()

        # Get database session directly
        session = SessionLocal()

        # 1. Check current wizard state
        wizard_state = session.query(WizardState).first()
        if wizard_state:
            print(f"📊 Current wizard state: {wizard_state.status.value}")
            print(f"   Current step: {wizard_state.current_step.value}")
            print(f"   Completed at: {wizard_state.completed_at}")
        else:
            print("📊 No wizard state found")

        print()

        # 2. Check users
        user_count = session.query(User).count()
        print(f"👥 Current users: {user_count}")

        print()
        print("=" * 60)
        print("RESET ACTIONS:")
        print("=" * 60)

        # 3. Delete wizard state
        deleted_wizard = session.query(WizardState).delete()
        print(f"✅ Deleted {deleted_wizard} wizard state record(s)")

        # 4. Disable foreign key checks temporarily
        session.execute(text("SET FOREIGN_KEY_CHECKS = 0"))

        # 5. Delete all users (CAUTION!)
        deleted_users = session.query(User).delete()
        print(f"✅ Deleted {deleted_users} user(s)")

        # 6. Re-enable foreign key checks
        session.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

        # 7. Commit changes
        session.commit()
        print()
        print("✅ Database reset complete!")
        print()

        # 6. Verify reset
        wizard_state_after = session.query(WizardState).first()
        user_count_after = session.query(User).count()

        print("=" * 60)
        print("VERIFICATION:")
        print("=" * 60)
        print(f"📊 Wizard state: {'None' if not wizard_state_after else 'EXISTS (ERROR!)'}")
        print(f"👥 Users: {user_count_after}")
        print()

        if not wizard_state_after and user_count_after == 0:
            print("🎉 SUCCESS! Database is ready for wizard testing")
            print()
            print("Next steps:")
            print("1. Start/restart your MVidarr dev server")
            print("2. Navigate to http://localhost:5000")
            print("3. You should be redirected to /wizard")
            print()
        else:
            print("⚠️  WARNING: Reset may not be complete")

        session.close()
        return True

    except Exception as e:
        print(f"❌ Error resetting database: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║     MVidarr Wizard Testing - Database Reset Utility       ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    print("⚠️  WARNING: This will DELETE:")
    print("   - All wizard state records")
    print("   - ALL users (including admin accounts)")
    print()
    print("This is intended for development/testing only!")
    print()

    response = input("Are you sure you want to continue? (yes/no): ")

    if response.lower() == 'yes':
        print()
        success = reset_for_wizard()
        sys.exit(0 if success else 1)
    else:
        print()
        print("❌ Reset cancelled")
        sys.exit(0)
