#!/usr/bin/env python3
"""
Reset Admin Credentials Script
Resets admin login credentials to a freshly generated random password in MVidarr
"""

import subprocess
import sys
import secrets
from pathlib import Path

from werkzeug.security import generate_password_hash

def run_mysql_command(sql_command, database="mvidarr"):
    """Execute MySQL command"""
    try:
        cmd = ["sudo", "mysql", database, "-e", sql_command]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr

def hash_password(password):
    """Hash password using the same scheme as the real login path (werkzeug)"""
    return generate_password_hash(password)

def reset_simple_auth_credentials(new_password):
    """Reset simple authentication credentials in settings table"""

    print("🔧 Resetting simple authentication credentials...")

    default_username = "admin"
    hashed_password = hash_password(new_password)

    # Check if settings table exists
    success, result = run_mysql_command("SHOW TABLES LIKE 'settings';")
    if not success:
        print(f"❌ Error checking settings table: {result}")
        return False

    if "settings" not in result:
        print("❌ Settings table not found. Creating it...")
        # Create settings table if it doesn't exist
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS settings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            `key` VARCHAR(255) NOT NULL UNIQUE,
            value TEXT,
            description TEXT,
            created_at DATETIME,
            updated_at DATETIME
        );
        """
        success, result = run_mysql_command(create_table_sql)
        if not success:
            print(f"❌ Error creating settings table: {result}")
            return False

    # Reset/set the admin credentials
    credentials_sql = f"""
    INSERT INTO settings (`key`, value) VALUES
    ('simple_auth_username', '{default_username}'),
    ('simple_auth_password', '{hashed_password}')
    ON DUPLICATE KEY UPDATE
    value = VALUES(value),
    updated_at = CURRENT_TIMESTAMP;
    """

    success, result = run_mysql_command(credentials_sql)
    if not success:
        print(f"❌ Error setting credentials: {result}")
        return False

    # Also ensure authentication is enabled
    auth_settings_sql = """
    INSERT INTO settings (`key`, value) VALUES
    ('require_authentication', 'true'),
    ('authentication_type', 'simple')
    ON DUPLICATE KEY UPDATE
    value = VALUES(value),
    updated_at = CURRENT_TIMESTAMP;
    """

    success, result = run_mysql_command(auth_settings_sql)
    if not success:
        print(f"❌ Error setting auth settings: {result}")
        return False

    print("✅ Simple authentication credentials reset successfully!")
    print(f"   Username: {default_username}")

    return True

def reset_full_auth_admin(new_password):
    """Reset full authentication admin user if it exists"""

    print("🔧 Checking for full authentication admin user...")

    # Check if users table exists
    success, result = run_mysql_command("SHOW TABLES LIKE 'users';")
    if not success or "users" not in result:
        print("ℹ️  No users table found - skipping full auth reset")
        return True

    # Check if admin user exists
    success, result = run_mysql_command("SELECT COUNT(*) as count FROM users WHERE username = 'admin';")
    if not success:
        print(f"❌ Error checking admin user: {result}")
        return False

    # Parse count
    lines = result.strip().split('\n')
    admin_exists = len(lines) >= 2 and int(lines[1]) > 0

    if admin_exists:
        print("👤 Found existing admin user - resetting password...")

        # Hash password using the same scheme the real login path expects
        hashed_password = hash_password(new_password)

        # Reset admin user password
        reset_sql = f"""
        UPDATE users
        SET password_hash = '{hashed_password}',
            updated_at = CURRENT_TIMESTAMP
        WHERE username = 'admin';
        """

        success, result = run_mysql_command(reset_sql)
        if not success:
            print(f"❌ Error resetting admin password: {result}")
            return False

        print("✅ Full auth admin password reset successfully!")
    else:
        print("ℹ️  No admin user found in full auth system")

    return True

def clear_user_sessions():
    """Clear all active user sessions to force re-login"""

    print("🔧 Clearing active user sessions...")

    # Check if user_sessions table exists
    success, result = run_mysql_command("SHOW TABLES LIKE 'user_sessions';")
    if not success or "user_sessions" not in result:
        print("ℹ️  No user_sessions table found - skipping session clear")
        return True

    # Clear all sessions
    success, result = run_mysql_command("DELETE FROM user_sessions;")
    if not success:
        print(f"❌ Error clearing sessions: {result}")
        return False

    print("✅ All user sessions cleared - users will need to re-login")
    return True

def main():
    """Main execution function"""

    print("=" * 60)
    print("MVidarr - Reset Admin Credentials")
    print("=" * 60)

    # Test MySQL connection
    success, result = run_mysql_command("SELECT 1;")
    if not success:
        print(f"❌ Cannot connect to MariaDB: {result}")
        print("   Make sure MariaDB is running and you have sudo access")
        sys.exit(1)

    print("✅ Connected to MariaDB successfully")
    print()

    # Generate a fresh random password for this run - never reuse a fixed default
    new_password = secrets.token_urlsafe(16)

    # Reset simple auth credentials (primary system)
    if not reset_simple_auth_credentials(new_password):
        print("❌ Failed to reset simple auth credentials!")
        sys.exit(1)

    print()

    # Reset full auth admin if exists
    if not reset_full_auth_admin(new_password):
        print("❌ Failed to reset full auth admin!")
        sys.exit(1)

    print()

    # Clear active sessions
    if not clear_user_sessions():
        print("❌ Failed to clear user sessions!")
        sys.exit(1)

    print()
    print("=" * 60)
    print("✅ Admin credentials reset completed successfully!")
    print("=" * 60)
    print("🔑 New Login Credentials (copy this now - it is not stored anywhere):")
    print("   Username: admin")
    print(f"   Password: {new_password}")
    print()
    print("📋 Next steps:")
    print("  1. Restart the application: ./manage.sh restart")
    print("  2. Access the application: http://localhost:5000")
    print("  3. Login with the credentials above")
    print("  4. Change the password immediately in Settings > General")
    print()
    print("⚠️  IMPORTANT: This password was generated randomly for this reset only.")
    print("   It will not be shown again - store it in a password manager now.")

if __name__ == "__main__":
    main()
