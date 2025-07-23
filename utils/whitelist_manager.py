import sqlite3
import logging
from typing import Set

logger = logging.getLogger(__name__)

class WhitelistManager:
    def __init__(self, db_path: str = "data/permissions.db"):
        self.db_path = db_path
        self._initialize_db()

    def _initialize_db(self):
        """Initializes the SQLite database and creates tables if they don't exist."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
            cursor.execute("CREATE TABLE IF NOT EXISTS groups (group_id INTEGER PRIMARY KEY, group_name TEXT, added_by INTEGER)")
            conn.commit()
            conn.close()
            logger.info(f"SQLite database initialized at {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Error initializing database: {e}")
            raise

    def _execute_query(self, query: str, params: tuple = (), fetch_one: bool = False, fetch_all: bool = False):
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            if fetch_one:
                return cursor.fetchone()
            if fetch_all:
                return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Database error during query '{query}' with params {params}: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

    def add_user(self, user_id: int) -> bool:
        """Adds a user ID to the whitelist. Returns True if added, False if already exists."""
        try:
            if not self.is_whitelisted(user_id):
                self._execute_query("INSERT INTO users (user_id) VALUES (?)", (user_id,))
                logger.info(f"User {user_id} added to whitelist.")
                return True
            return False
        except Exception:
            return False

    def remove_user(self, user_id: int) -> bool:
        """Removes a user ID from the whitelist. Returns True if removed, False if not found."""
        try:
            if self.is_whitelisted(user_id):
                self._execute_query("DELETE FROM users WHERE user_id = ?", (user_id,))
                logger.info(f"User {user_id} removed from whitelist.")
                return True
            return False
        except Exception:
            return False

    def is_whitelisted(self, user_id: int) -> bool:
        """Checks if a user ID is in the whitelist."""
        try:
            result = self._execute_query("SELECT 1 FROM users WHERE user_id = ?", (user_id,), fetch_one=True)
            return result is not None
        except Exception:
            return False

    def get_all_whitelisted_users(self) -> Set[int]:
        """Returns a set of all user IDs in the whitelist."""
        try:
            results = self._execute_query("SELECT user_id FROM users", fetch_all=True)
            return set(row[0] for row in results) if results else set()
        except Exception:
            return set()

    def add_group(self, group_id: int, group_name: str, added_by: int) -> bool:
        """Adds a group to the whitelist."""
        try:
            if not self.is_group_whitelisted(group_id):
                self._execute_query("INSERT INTO groups (group_id, group_name, added_by) VALUES (?, ?, ?)", (group_id, group_name, added_by))
                logger.info(f"Group {group_id} ({group_name}) added to whitelist by {added_by}.")
                return True
            return False
        except Exception:
            return False

    def remove_group(self, group_id: int) -> bool:
        """Removes a group from the whitelist."""
        try:
            if self.is_group_whitelisted(group_id):
                self._execute_query("DELETE FROM groups WHERE group_id = ?", (group_id,))
                logger.info(f"Group {group_id} removed from whitelist.")
                return True
            return False
        except Exception:
            return False

    def is_group_whitelisted(self, group_id: int) -> bool:
        """Checks if a group ID is in the whitelist."""
        try:
            result = self._execute_query("SELECT 1 FROM groups WHERE group_id = ?", (group_id,), fetch_one=True)
            return result is not None
        except Exception:
            return False

    def get_all_whitelisted_groups(self) -> Set[int]:
        """Returns a set of all group IDs in the whitelist."""
        try:
            results = self._execute_query("SELECT group_id FROM groups", fetch_all=True)
            return set(row[0] for row in results) if results else set()
        except Exception:
            return set()
