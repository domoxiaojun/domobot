#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一数据库管理器
整合所有SQLite数据库到一个文件中，提供统一的数据访问接口
"""

import sqlite3
import logging
import time
import random
from pathlib import Path
from typing import List, Optional, Set, Dict, Any
from dataclasses import dataclass
from contextlib import contextmanager

logger = logging.getLogger(__name__)

@dataclass
class DeleteTask:
    """删除任务数据类"""
    id: Optional[int] = None
    chat_id: int = 0
    message_id: int = 0
    delete_at: float = 0.0  # Unix timestamp
    task_type: str = "bot_message"  # bot_message, user_command, search_result
    user_id: Optional[int] = None
    session_id: Optional[str] = None  # 用于关联搜索会话
    created_at: float = 0.0
    metadata: Optional[str] = None  # JSON 字符串，存储额外信息

class UnifiedDatabaseManager:
    """统一数据库管理器"""
    
    def __init__(self, permissions_db_path: str = "data/permissions.db"):
        self.permissions_db_path = Path(permissions_db_path)
        
        self.permissions_db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._init_permissions_database()
        logger.info(f"权限数据库初始化完成: {self.permissions_db_path}")
    
    @contextmanager
    def get_permissions_connection(self):
        """获取权限数据库连接的上下文管理器"""
        conn = None
        try:
            conn = sqlite3.connect(self.permissions_db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("PRAGMA foreign_keys = ON;")
            yield conn
        except sqlite3.OperationalError as e:
            logger.error(f"权限数据库操作失败: {e} - {self.permissions_db_path}")
            if "database is locked" in str(e):
                time.sleep(random.uniform(0.1, 0.5))
            if conn:
                conn.rollback()
            raise
        except Exception as e:
            logger.error(f"权限数据库发生未知错误: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.commit()
                conn.close()

    

    def _init_permissions_database(self):
        """初始化权限相关的数据库表"""
        try:
            with self.get_permissions_connection() as conn:
                # 用户白名单表
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_whitelist (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        added_by INTEGER,
                        added_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 群组白名单表
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS group_whitelist (
                        group_id INTEGER PRIMARY KEY,
                        group_name TEXT,
                        added_by INTEGER,
                        added_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 管理员权限表
                conn.execute("""
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
                
                # 创建索引
                conn.execute("CREATE INDEX IF NOT EXISTS idx_username ON user_whitelist (username)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_group_name ON group_whitelist (group_name)")
                
                conn.commit()
                logger.info("权限数据库表初始化完成")
        except Exception as e:
            logger.error(f"初始化权限数据库失败: {e}")
            raise

    
    
    # ===========================================
    # 用户白名单相关方法
    # ===========================================
    
    def add_user_to_whitelist(self, user_id: int, username: Optional[str] = None, added_by: Optional[int] = None) -> bool:
        """添加用户到白名单"""
        try:
            with self.get_permissions_connection() as conn:
                # 检查是否已存在
                result = conn.execute("SELECT 1 FROM user_whitelist WHERE user_id = ?", (user_id,)).fetchone()
                if result:
                    return False
                
                conn.execute("""
                    INSERT INTO user_whitelist (user_id, username, added_by) 
                    VALUES (?, ?, ?)
                """, (user_id, username, added_by))
                conn.commit()
                logger.info(f"用户 {user_id} 已添加到白名单")
                return True
        except Exception as e:
            logger.error(f"添加用户到白名单失败: {e}")
            return False
    
    def remove_user_from_whitelist(self, user_id: int) -> bool:
        """从白名单移除用户"""
        try:
            with self.get_permissions_connection() as conn:
                cursor = conn.execute("DELETE FROM user_whitelist WHERE user_id = ?", (user_id,))
                conn.commit()
                if cursor.rowcount > 0:
                    logger.info(f"用户 {user_id} 已从白名单移除")
                    return True
                return False
        except Exception as e:
            logger.error(f"从白名单移除用户失败: {e}")
            return False
    
    def is_user_whitelisted(self, user_id: int) -> bool:
        """检查用户是否在白名单中"""
        try:
            with self.get_permissions_connection() as conn:
                result = conn.execute("SELECT 1 FROM user_whitelist WHERE user_id = ?", (user_id,)).fetchone()
                return result is not None
        except Exception as e:
            logger.error(f"检查用户白名单状态失败: {e}")
            return False
    
    def get_all_whitelisted_users(self) -> Set[int]:
        """获取所有白名单用户"""
        try:
            with self.get_permissions_connection() as conn:
                results = conn.execute("SELECT user_id FROM user_whitelist").fetchall()
                return set(row[0] for row in results) if results else set()
        except Exception as e:
            logger.error(f"获取白名单用户失败: {e}")
            return set()
    
    # ===========================================
    # 群组白名单相关方法
    # ===========================================
    
    def add_group_to_whitelist(self, group_id: int, group_name: Optional[str] = None, added_by: Optional[int] = None) -> bool:
        """添加群组到白名单"""
        try:
            with self.get_permissions_connection() as conn:
                # 检查是否已存在
                result = conn.execute("SELECT 1 FROM group_whitelist WHERE group_id = ?", (group_id,)).fetchone()
                if result:
                    return False
                
                conn.execute("""
                    INSERT INTO group_whitelist (group_id, group_name, added_by) 
                    VALUES (?, ?, ?)
                """, (group_id, group_name, added_by))
                conn.commit()
                logger.info(f"群组 {group_id} ({group_name}) 已添加到白名单")
                return True
        except Exception as e:
            logger.error(f"添加群组到白名单失败: {e}")
            return False
    
    def remove_group_from_whitelist(self, group_id: int) -> bool:
        """从白名单移除群组"""
        try:
            with self.get_permissions_connection() as conn:
                cursor = conn.execute("DELETE FROM group_whitelist WHERE group_id = ?", (group_id,))
                conn.commit()
                if cursor.rowcount > 0:
                    logger.info(f"群组 {group_id} 已从白名单移除")
                    return True
                return False
        except Exception as e:
            logger.error(f"从白名单移除群组失败: {e}")
            return False
    
    def is_group_whitelisted(self, group_id: int) -> bool:
        """检查群组是否在白名单中"""
        try:
            with self.get_permissions_connection() as conn:
                result = conn.execute("SELECT 1 FROM group_whitelist WHERE group_id = ?", (group_id,)).fetchone()
                return result is not None
        except Exception as e:
            logger.error(f"检查群组白名单状态失败: {e}")
            return False
    
    def get_all_whitelisted_groups(self) -> List[Dict]:
        """获取所有白名单群组"""
        try:
            with self.get_permissions_connection() as conn:
                results = conn.execute("""
                    SELECT group_id, group_name, added_by, added_time 
                    FROM group_whitelist ORDER BY added_time DESC
                """).fetchall()
                return [dict(row) for row in results] if results else []
        except Exception as e:
            logger.error(f"获取白名单群组失败: {e}")
            return []
    
    # ===========================================
    # 管理员权限相关方法
    # ===========================================
    
    def add_admin(self, user_id: int, username: Optional[str] = None, granted_by: Optional[int] = None, 
                  can_manage_users: bool = False, can_manage_groups: bool = False, 
                  can_clear_cache: bool = False) -> bool:
        """添加管理员"""
        try:
            with self.get_permissions_connection() as conn:
                # 检查是否已存在
                result = conn.execute("SELECT 1 FROM admin_permissions WHERE user_id = ?", (user_id,)).fetchone()
                if result:
                    return False
                
                conn.execute("""
                    INSERT INTO admin_permissions 
                    (user_id, username, can_manage_users, can_manage_groups, can_clear_cache, granted_by) 
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (user_id, username, can_manage_users, can_manage_groups, can_clear_cache, granted_by))
                conn.commit()
                logger.info(f"管理员 {user_id} ({username}) 添加成功")
                return True
        except Exception as e:
            logger.error(f"添加管理员失败: {e}")
            return False
    
    def remove_admin(self, user_id: int) -> bool:
        """移除管理员"""
        try:
            with self.get_permissions_connection() as conn:
                cursor = conn.execute("DELETE FROM admin_permissions WHERE user_id = ?", (user_id,))
                conn.commit()
                if cursor.rowcount > 0:
                    logger.info(f"管理员 {user_id} 已移除")
                    return True
                return False
        except Exception as e:
            logger.error(f"移除管理员失败: {e}")
            return False
    
    def is_admin(self, user_id: int) -> bool:
        """检查是否为管理员"""
        try:
            with self.get_permissions_connection() as conn:
                result = conn.execute("SELECT 1 FROM admin_permissions WHERE user_id = ?", (user_id,)).fetchone()
                return result is not None
        except Exception as e:
            logger.error(f"检查管理员状态失败: {e}")
            return False
    
    def has_permission(self, user_id: int, permission: str) -> bool:
        """检查用户是否有特定权限"""
        try:
            with self.get_permissions_connection() as conn:
                column_map = {
                    'manage_users': 'can_manage_users',
                    'manage_groups': 'can_manage_groups',
                    'clear_cache': 'can_clear_cache'
                }
                
                if permission not in column_map:
                    return False
                
                result = conn.execute(
                    f"SELECT {column_map[permission]} FROM admin_permissions WHERE user_id = ?", 
                    (user_id,)
                ).fetchone()
                
                return result is not None and result[0] == 1
        except Exception as e:
            logger.error(f"检查权限失败: {e}")
            return False
    
    def update_admin_permissions(self, user_id: int, **permissions) -> bool:
        """更新管理员权限"""
        try:
            with self.get_permissions_connection() as conn:
                # 构建更新语句
                valid_permissions = ['can_manage_users', 'can_manage_groups', 'can_clear_cache']
                updates = []
                params = []
                
                for perm, value in permissions.items():
                    if perm in valid_permissions:
                        updates.append(f"{perm} = ?")
                        params.append(1 if value else 0)
                
                if not updates:
                    return False
                
                params.append(user_id)
                query = f"UPDATE admin_permissions SET {', '.join(updates)} WHERE user_id = ?"
                
                cursor = conn.execute(query, params)
                conn.commit()
                
                if cursor.rowcount > 0:
                    logger.info(f"管理员 {user_id} 权限已更新")
                    return True
                return False
        except Exception as e:
            logger.error(f"更新管理员权限失败: {e}")
            return False
    
    def get_all_admins(self) -> List[Dict]:
        """获取所有管理员"""
        try:
            with self.get_permissions_connection() as conn:
                results = conn.execute("""
                    SELECT user_id, username, can_manage_users, can_manage_groups, 
                           can_clear_cache, granted_by, granted_time 
                    FROM admin_permissions ORDER BY granted_time DESC
                """).fetchall()
                return [dict(row) for row in results] if results else []
        except Exception as e:
            logger.error(f"获取管理员列表失败: {e}")
            return []
    
    # 创建全局实例
_db_manager = None

def get_db_manager() -> UnifiedDatabaseManager:
    """获取数据库管理器实例（单例模式）"""
    global _db_manager
    if _db_manager is None:
        _db_manager = UnifiedDatabaseManager()
    return _db_manager
