#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
消息删除数据库管理器
用于管理待删除的消息任务
"""

import sqlite3
import logging
import time
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

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
    retries: int = 0

class MessageDeleteManager:
    """消息删除管理器"""
    
    def __init__(self, db_path: str = "data/bot_data.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    def _init_database(self):
        """初始化数据库表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS delete_tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id INTEGER NOT NULL,
                        message_id INTEGER NOT NULL,
                        delete_at REAL NOT NULL,
                        task_type TEXT NOT NULL DEFAULT 'bot_message',
                        user_id INTEGER,
                        session_id TEXT,
                        created_at REAL NOT NULL,
                        metadata TEXT,
                        retries INTEGER NOT NULL DEFAULT 0
                    )
                """)
                
                # 检查 retries 列是否存在
                cursor.execute("PRAGMA table_info(delete_tasks)")
                columns = [column[1] for column in cursor.fetchall()]
                if 'retries' not in columns:
                    cursor.execute("ALTER TABLE delete_tasks ADD COLUMN retries INTEGER NOT NULL DEFAULT 0")

                # 创建索引
                conn.execute("CREATE INDEX IF NOT EXISTS idx_delete_at ON delete_tasks (delete_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_session_id ON delete_tasks (session_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON delete_tasks (user_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_task_lookup ON delete_tasks (chat_id, message_id, task_type)")
                
                conn.commit()
                logger.info("消息删除数据库初始化完成")
        except Exception as e:
            logger.error(f"初始化数据库失败: {e}")
            raise
    
    def schedule_deletion(self, task: DeleteTask) -> Optional[int]:
        """调度一个删除任务"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 检查是否已存在相同的任务
                existing = conn.execute("""
                    SELECT id, delete_at FROM delete_tasks 
                    WHERE chat_id = ? AND message_id = ? AND task_type = ?
                """, (task.chat_id, task.message_id, task.task_type)).fetchone()
                
                if existing:
                    existing_id, existing_delete_at = existing
                    # 如果新任务的执行时间更早，则更新；否则忽略
                    if task.delete_at < existing_delete_at:
                        conn.execute("""
                            UPDATE delete_tasks 
                            SET delete_at = ?, user_id = ?, session_id = ?, created_at = ?, metadata = ?, retries = 0
                            WHERE id = ?
                        """, (task.delete_at, task.user_id, task.session_id, task.created_at, task.metadata, existing_id))
                        conn.commit()
                        logger.debug(f"已更新删除任务 {existing_id}: 消息 {task.message_id} (提前到 {task.delete_at})")
                        return existing_id
                    else:
                        logger.debug(f"跳过重复的删除任务: 消息 {task.message_id} (已存在更早的任务)")
                        return existing_id
                
                # 插入新任务
                cursor = conn.execute("""
                    INSERT INTO delete_tasks 
                    (chat_id, message_id, delete_at, task_type, user_id, session_id, created_at, metadata, retries)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task.chat_id,
                    task.message_id, 
                    task.delete_at,
                    task.task_type,
                    task.user_id,
                    task.session_id,
                    task.created_at,
                    task.metadata,
                    0  # 初始重试次数为0
                ))
                task_id = cursor.lastrowid
                conn.commit()
                
                logger.debug(f"已调度删除任务 {task_id}: 消息 {task.message_id} (类型: {task.task_type})")
                return task_id
        except Exception as e:
            logger.error(f"调度删除任务失败: {e}")
            return None
    
    def get_due_tasks(self, limit: int = 100) -> List[DeleteTask]:
        """获取到期的删除任务"""
        current_time = time.time()
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM delete_tasks 
                    WHERE delete_at <= ? 
                    ORDER BY delete_at ASC 
                    LIMIT ?
                """, (current_time, limit))
                
                tasks = []
                for row in cursor.fetchall():
                    task = DeleteTask(
                        id=row['id'],
                        chat_id=row['chat_id'],
                        message_id=row['message_id'],
                        delete_at=row['delete_at'],
                        task_type=row['task_type'],
                        user_id=row['user_id'],
                        session_id=row['session_id'],
                        created_at=row['created_at'],
                        metadata=row['metadata'],
                        retries=row['retries']
                    )
                    tasks.append(task)
                
                return tasks
        except Exception as e:
            logger.error(f"获取到期任务失败: {e}")
            return []

    def retry_task(self, task_id: int, retry_delay: int) -> bool:
        """
        更新任务以进行重试
        :param task_id: 任务ID
        :param retry_delay: 重试延迟（秒）
        :return: 如果成功更新则返回True
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                new_delete_at = time.time() + retry_delay
                cursor = conn.execute("""
                    UPDATE delete_tasks
                    SET delete_at = ?, retries = retries + 1
                    WHERE id = ?
                """, (new_delete_at, task_id))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"重试任务 {task_id} 失败: {e}")
            return False

    def remove_task(self, task_id: int) -> bool:
        """移除一个删除任务"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("DELETE FROM delete_tasks WHERE id = ?", (task_id,))
                conn.commit()
                
                if cursor.rowcount > 0:
                    logger.debug(f"已移除删除任务 {task_id}")
                    return True
                else:
                    logger.warning(f"删除任务 {task_id} 不存在")
                    return False
        except Exception as e:
            logger.error(f"移除删除任务 {task_id} 失败: {e}")
            return False
    
    def remove_tasks(self, task_ids: List[int]) -> int:
        """批量移除删除任务"""
        if not task_ids:
            return 0
            
        try:
            with sqlite3.connect(self.db_path) as conn:
                placeholders = ','.join('?' * len(task_ids))
                cursor = conn.execute(
                    f"DELETE FROM delete_tasks WHERE id IN ({placeholders})", 
                    task_ids
                )
                conn.commit()
                
                removed_count = cursor.rowcount
                logger.debug(f"批量移除了 {removed_count} 个删除任务")
                return removed_count
        except Exception as e:
            logger.error(f"批量移除删除任务失败: {e}")
            return 0
    
    def cancel_session_tasks(self, session_id: str) -> int:
        """取消指定会话的所有删除任务"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "DELETE FROM delete_tasks WHERE session_id = ?", 
                    (session_id,)
                )
                conn.commit()
                
                cancelled_count = cursor.rowcount
                if cancelled_count > 0:
                    logger.info(f"已取消会话 {session_id} 的 {cancelled_count} 个删除任务")
                return cancelled_count
        except Exception as e:
            logger.error(f"取消会话任务失败: {e}")
            return 0
    
    def cancel_user_tasks(self, user_id: int, task_type: Optional[str] = None) -> int:
        """取消指定用户的删除任务"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                if task_type:
                    cursor = conn.execute(
                        "DELETE FROM delete_tasks WHERE user_id = ? AND task_type = ?", 
                        (user_id, task_type)
                    )
                else:
                    cursor = conn.execute(
                        "DELETE FROM delete_tasks WHERE user_id = ?", 
                        (user_id,)
                    )
                conn.commit()
                
                cancelled_count = cursor.rowcount
                if cancelled_count > 0:
                    type_info = f" (类型: {task_type})" if task_type else ""
                    logger.info(f"已取消用户 {user_id} 的 {cancelled_count} 个删除任务{type_info}")
                return cancelled_count
        except Exception as e:
            logger.error(f"取消用户任务失败: {e}")
            return 0
    
    def get_task_count(self) -> int:
        """获取待处理任务数量"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM delete_tasks")
                count = cursor.fetchone()[0]
                return count
        except Exception as e:
            logger.error(f"获取任务数量失败: {e}")
            return 0
    
    def cleanup_old_tasks(self, days: int = 7) -> int:
        """清理过期的任务记录"""
        cutoff_time = time.time() - (days * 24 * 3600)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "DELETE FROM delete_tasks WHERE created_at < ?", 
                    (cutoff_time,)
                )
                conn.commit()
                
                cleaned_count = cursor.rowcount
                if cleaned_count > 0:
                    logger.info(f"清理了 {cleaned_count} 个过期任务记录")
                return cleaned_count
        except Exception as e:
            logger.error(f"清理过期任务失败: {e}")
            return 0
    
    def cleanup_expired_tasks(self, max_age_hours: int = 24) -> int:
        """清理过期的删除任务"""
        try:
            max_age_seconds = max_age_hours * 3600
            cutoff_time = time.time() - max_age_seconds
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "DELETE FROM delete_tasks WHERE created_at < ?", 
                    (cutoff_time,)
                )
                conn.commit()
                
                cleaned_count = cursor.rowcount
                if cleaned_count > 0:
                    logger.info(f"清理了 {cleaned_count} 个超过 {max_age_hours} 小时的过期删除任务")
                return cleaned_count
        except Exception as e:
            logger.error(f"清理过期任务失败: {e}")
            return 0
    
    def get_session_tasks(self, session_id: str) -> List[DeleteTask]:
        """获取指定会话的所有任务"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM delete_tasks WHERE session_id = ? ORDER BY delete_at ASC", 
                    (session_id,)
                )
                
                tasks = []
                for row in cursor.fetchall():
                    task = DeleteTask(
                        id=row['id'],
                        chat_id=row['chat_id'],
                        message_id=row['message_id'],
                        delete_at=row['delete_at'],
                        task_type=row['task_type'],
                        user_id=row['user_id'],
                        session_id=row['session_id'],
                        created_at=row['created_at'],
                        metadata=row['metadata'],
                        retries=row['retries']
                    )
                    tasks.append(task)
                
                return tasks
        except Exception as e:
            logger.error(f"获取会话任务失败: {e}")
            return []

# 全局实例
message_delete_manager = MessageDeleteManager()