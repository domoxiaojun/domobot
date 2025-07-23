import os
import sqlite3
import logging
from utils.compatibility_adapters import WhitelistManager
from utils.cache_manager import CacheManager

logger = logging.getLogger(__name__)

class AdminManager:
    def __init__(self, db_path: str = "data/permissions.db"):
        self.db_path = db_path
        self.super_admin_id = int(os.getenv('SUPER_ADMIN_ID', 0))
        self.whitelist_manager = WhitelistManager()
        self.cache_manager = CacheManager()
        self._initialize_db()

    def _initialize_db(self):
        """初始化管理员数据库"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 创建管理员权限表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admin_permissions (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    can_manage_users BOOLEAN DEFAULT 0,
                    can_manage_groups BOOLEAN DEFAULT 0,
                    can_clear_cache BOOLEAN DEFAULT 0,
                    granted_by INTEGER,
                    granted_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()
            conn.close()
            logger.info(f"Admin database initialized at {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Error initializing admin database: {e}")
            raise

    def _execute_query(self, query: str, params: tuple = (), fetch_one: bool = False, fetch_all: bool = False):
        """执行数据库查询"""
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

    def is_super_admin(self, user_id: int) -> bool:
        """检查是否为超级管理员"""
        return user_id == self.super_admin_id

    def is_admin(self, user_id: int) -> bool:
        """检查是否为管理员（包括超级管理员）"""
        if self.is_super_admin(user_id):
            return True

        try:
            result = self._execute_query(
                "SELECT 1 FROM admin_permissions WHERE user_id = ?",
                (user_id,),
                fetch_one=True
            )
            return result is not None
        except Exception:
            return False

    def has_permission(self, user_id: int, permission: str) -> bool:
        """检查用户是否有特定权限"""
        if self.is_super_admin(user_id):
            return True

        try:
            column_map = {
                'manage_users': 'can_manage_users',
                'manage_groups': 'can_manage_groups',
                'clear_cache': 'can_clear_cache'
            }

            if permission not in column_map:
                return False

            result = self._execute_query(
                f"SELECT {column_map[permission]} FROM admin_permissions WHERE user_id = ?",
                (user_id,),
                fetch_one=True
            )
            return bool(result and result[0]) if result else False
        except Exception:
            return False

    def add_admin(self, user_id: int, username: str = None, permissions: dict = None, granted_by: int = None) -> bool:
        """添加管理员"""
        try:
            if permissions is None:
                permissions = {'can_manage_users': False, 'can_manage_groups': False, 'can_clear_cache': False}

            self._execute_query("""
                INSERT OR REPLACE INTO admin_permissions
                (user_id, username, can_manage_users, can_manage_groups, can_clear_cache, granted_by)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                user_id, username,
                permissions.get('can_manage_users', False),
                permissions.get('can_manage_groups', False),
                permissions.get('can_clear_cache', False),
                granted_by
            ))
            logger.info(f"Admin {user_id} added by {granted_by}")
            return True
        except Exception as e:
            logger.error(f"Error adding admin: {e}")
            return False

    def remove_admin(self, user_id: int) -> bool:
        """移除管理员"""
        try:
            self._execute_query("DELETE FROM admin_permissions WHERE user_id = ?", (user_id,))
            logger.info(f"Admin {user_id} removed")
            return True
        except Exception:
            return False

    def get_all_admins(self) -> list:
        """获取所有管理员"""
        try:
            results = self._execute_query("""
                SELECT user_id, username, can_manage_users, can_manage_groups, can_clear_cache, granted_time
                FROM admin_permissions
            """, fetch_all=True)
            return results if results else []
        except Exception:
            return []

    def get_all_whitelisted_groups(self) -> list:
        """获取所有白名单群组"""
        return self.whitelist_manager.get_all_whitelisted_groups()

    def clear_all_cache(self) -> bool:
        """清空所有缓存"""
        try:
            # 清理缓存目录
            import shutil
            import os
            cache_dir = os.getenv('CACHE_DIR', 'cache')
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir)
                os.makedirs(cache_dir)

            # 重新初始化缓存管理器
            self.cache_manager = CacheManager()
            logger.info("All cache cleared")
            return True
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return False

# 创建全局管理员管理器实例
admin_manager = AdminManager()
