"""
MVidarr - User Management Service
Handles user authentication, password management, and user operations
"""

import logging
from typing import Dict, List, Optional

# Optional bcrypt import with fallback
try:
    import bcrypt

    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False
    import hashlib

logger = logging.getLogger(__name__)


class UserService:
    """User management service with authentication and password handling"""

    def __init__(self, database_manager):
        self.db = database_manager
        self._ensure_admin_user()

    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt or fallback to SHA256"""
        if BCRYPT_AVAILABLE:
            return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode(
                "utf-8"
            )
        else:
            # Fallback to SHA256 (not recommended for production)
            logger.warning(
                "Using SHA256 password hashing - install bcrypt for better security"
            )
            return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash"""
        if BCRYPT_AVAILABLE:
            try:
                return bcrypt.checkpw(
                    password.encode("utf-8"), password_hash.encode("utf-8")
                )
            except (ValueError, TypeError):
                # Fallback for non-bcrypt hashes
                return (
                    hashlib.sha256(password.encode("utf-8")).hexdigest()
                    == password_hash
                )
        else:
            return hashlib.sha256(password.encode("utf-8")).hexdigest() == password_hash

    def authenticate(self, username: str, password: str) -> Optional[Dict]:
        """Authenticate user and return user data"""
        try:
            query = """
            SELECT id, username, password_hash, is_admin, force_password_change, email, last_login
            FROM users WHERE username = %s
            """
            result = self.db.execute_query(query, (username,), fetch=True)

            if result and self.verify_password(password, result[0]["password_hash"]):
                user = result[0]

                # Update last login
                self.db.execute_query(
                    "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s",
                    (user["id"],),
                )

                logger.info(f"User '{username}' authenticated successfully")
                return user
            else:
                logger.warning(f"Authentication failed for user '{username}'")
                return None

        except Exception as e:
            logger.error(f"Authentication error for user '{username}': {e}")
            return None

    def change_password(self, user_id: int, new_password: str) -> bool:
        """Change user password"""
        try:
            if len(new_password) < 6:
                raise ValueError("Password must be at least 6 characters long")

            password_hash = self.hash_password(new_password)

            query = """
            UPDATE users SET 
                password_hash = %s, 
                force_password_change = FALSE, 
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """

            rows_affected = self.db.execute_query(query, (password_hash, user_id))

            if rows_affected > 0:
                logger.info(f"Password changed for user ID {user_id}")
                return True
            else:
                logger.warning(f"No user found with ID {user_id}")
                return False

        except Exception as e:
            logger.error(f"Password change error for user ID {user_id}: {e}")
            return False

    def create_user(
        self, username: str, password: str, email: str = None, is_admin: bool = False
    ) -> Optional[int]:
        """Create a new user"""
        try:
            # Check if username already exists
            existing_user = self.db.execute_query(
                "SELECT id FROM users WHERE username = %s", (username,), fetch=True
            )

            if existing_user:
                logger.warning(f"Username '{username}' already exists")
                return None

            password_hash = self.hash_password(password)

            query = """
            INSERT INTO users (username, email, password_hash, is_admin, force_password_change)
            VALUES (%s, %s, %s, %s, %s)
            """

            self.db.execute_query(
                query, (username, email, password_hash, is_admin, False)
            )

            # Get the created user ID
            user_result = self.db.execute_query(
                "SELECT id FROM users WHERE username = %s", (username,), fetch=True
            )

            if user_result:
                user_id = user_result[0]["id"]
                logger.info(f"User '{username}' created with ID {user_id}")
                return user_id

        except Exception as e:
            logger.error(f"User creation error for '{username}': {e}")
            return None

    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user by ID"""
        try:
            query = """
            SELECT id, username, email, is_admin, force_password_change, created_at, last_login
            FROM users WHERE id = %s
            """
            result = self.db.execute_query(query, (user_id,), fetch=True)

            if result:
                return result[0]
            return None

        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None

    def update_user(self, user_id: int, **kwargs) -> bool:
        """Update user information"""
        try:
            allowed_fields = ["username", "email", "is_admin"]
            updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

            if not updates:
                return False

            set_clause = ", ".join([f"{k} = %s" for k in updates.keys()])
            values = list(updates.values()) + [user_id]

            query = f"""
            UPDATE users SET {set_clause}, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """

            rows_affected = self.db.execute_query(query, tuple(values))

            if rows_affected > 0:
                logger.info(f"User {user_id} updated: {list(updates.keys())}")
                return True
            return False

        except Exception as e:
            logger.error(f"Error updating user {user_id}: {e}")
            return False

    def delete_user(self, user_id: int) -> bool:
        """Delete user (admin users cannot be deleted)"""
        try:
            # Check if user is admin
            user = self.get_user(user_id)
            if not user:
                return False

            if user["is_admin"]:
                logger.warning(f"Cannot delete admin user {user_id}")
                return False

            rows_affected = self.db.execute_query(
                "DELETE FROM users WHERE id = %s", (user_id,)
            )

            if rows_affected > 0:
                logger.info(f"User {user_id} deleted")
                return True
            return False

        except Exception as e:
            logger.error(f"Error deleting user {user_id}: {e}")
            return False

    def list_users(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """List all users with pagination"""
        try:
            query = """
            SELECT id, username, email, is_admin, force_password_change, created_at, last_login
            FROM users
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """

            result = self.db.execute_query(query, (limit, offset), fetch=True)
            return result or []

        except Exception as e:
            logger.error(f"Error listing users: {e}")
            return []

    def check_default_password_status(self) -> bool:
        """Check if the default admin password has been changed"""
        try:
            # Get the admin user
            query = "SELECT password_hash FROM users WHERE username = 'Admin' LIMIT 1"
            result = self.db.execute_query(query, fetch=True)

            if result:
                current_hash = result[0]["password_hash"]
                # Check if current password is still 'Admin' (default)
                return not self.verify_password("Admin", current_hash)

            # No admin user found, assume password has been changed
            return True

        except Exception as e:
            logger.error(f"Error checking default password status: {e}")
            return False

    def _ensure_admin_user(self):
        """Ensure default admin user exists"""
        try:
            # Check if admin user exists
            admin_user = self.db.execute_query(
                "SELECT id FROM users WHERE username = 'Admin'", fetch=True
            )

            if not admin_user:
                # Create default admin user
                logger.info("Creating default admin user")
                admin_id = self.create_user(
                    username="Admin",
                    password="Admin",
                    email="admin@mvidarr.local",
                    is_admin=True,
                )

                if admin_id:
                    # Set force password change for default admin
                    self.db.execute_query(
                        "UPDATE users SET force_password_change = TRUE WHERE id = %s",
                        (admin_id,),
                    )
                    logger.info("✅ Default admin user created (Admin/Admin)")
                    logger.warning(
                        "⚠️  Please change the default password after first login"
                    )
                else:
                    logger.error("❌ Failed to create default admin user")

        except Exception as e:
            logger.error(f"Error ensuring admin user exists: {e}")

    def get_user_count(self) -> int:
        """Get total number of users"""
        try:
            result = self.db.execute_query(
                "SELECT COUNT(*) as count FROM users", fetch=True
            )
            if result:
                return result[0]["count"]
            return 0
        except Exception as e:
            logger.error(f"Error getting user count: {e}")
            return 0

    def is_setup_required(self) -> bool:
        """Check if initial setup is required"""
        return self.get_user_count() == 0
