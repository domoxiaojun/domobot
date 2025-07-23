"""
专门管理消息删除任务的模块

这个模块优化了消息自动删除机制，避免重复创建删除任务，
并提供智能的删除调度功能。
"""

import asyncio
import time
import logging
from typing import Dict, Set, Optional, Tuple
from utils.task_manager import create_task

logger = logging.getLogger(__name__)

class DeletionTaskManager:
    """专门管理消息删除任务的管理器
    
    Features:
    - 避免重复创建删除任务
    - 智能调度删除时间
    - 自动清理过期的调度信息
    - 支持取消已调度的删除
    """
    
    def __init__(self):
        """初始化删除任务管理器"""
        self.scheduled_deletions: Dict[Tuple[int, int], Dict] = {}  # (chat_id, message_id) -> task_info
        self.active_tasks: Set[asyncio.Task] = set()
        self._cleanup_interval = 300  # 5分钟清理一次
        self._last_cleanup = time.time()
        
        logger.info("删除任务管理器已初始化")
    
    def schedule_deletion(self, context, chat_id: int, message_id: int, delay: int, 
                         task_name: Optional[str] = None) -> bool:
        """智能调度删除任务
        
        Args:
            context: Telegram bot context
            chat_id: 聊天ID
            message_id: 消息ID
            delay: 延迟时间（秒）
            task_name: 任务名称
            
        Returns:
            bool: 是否成功调度（True表示新建或更新，False表示已存在更早的删除时间）
        """
        key = (chat_id, message_id)
        scheduled_time = time.time() + delay
        
        # 定期清理
        self._periodic_cleanup()
        
        # 检查是否已经有删除任务
        if key in self.scheduled_deletions:
            existing_info = self.scheduled_deletions[key]
            existing_time = existing_info.get('scheduled_time', 0)
            
            # 如果新的删除时间更早，取消原任务并创建新任务
            if scheduled_time < existing_time:
                self._cancel_existing_task(key)
                self._create_deletion_task(context, chat_id, message_id, delay, key, task_name)
                logger.debug(f"更新删除任务: {message_id} (新延迟: {delay}s)")
                return True
            else:
                logger.debug(f"保持现有删除任务: {message_id} (现有延迟更短)")
                return False
        else:
            self._create_deletion_task(context, chat_id, message_id, delay, key, task_name)
            logger.debug(f"创建删除任务: {message_id} (延迟: {delay}s)")
            return True
    
    def _create_deletion_task(self, context, chat_id: int, message_id: int, 
                             delay: int, key: Tuple[int, int], task_name: Optional[str] = None):
        """创建删除任务"""
        async def delete_after_delay():
            try:
                await asyncio.sleep(delay)
                await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                logger.debug(f"成功删除消息: {message_id}")
            except Exception as e:
                # 只记录非预期的错误，忽略常见的删除失败情况
                error_msg = str(e).lower()
                if ("message can't be deleted" not in error_msg and 
                    "message to delete not found" not in error_msg and
                    "bad request" not in error_msg):
                    logger.warning(f"删除消息失败 {message_id}: {e}")
            finally:
                # 清理调度信息
                self.scheduled_deletions.pop(key, None)
        
        # 创建任务
        name = task_name or f"delete_msg_{message_id}"
        task = create_task(
            delete_after_delay(),
            name=name,
            context="message_deletion"
        )
        
        # 记录任务信息
        self.scheduled_deletions[key] = {
            'task': task,
            'scheduled_time': time.time() + delay,
            'chat_id': chat_id,
            'message_id': message_id,
            'delay': delay
        }
        
        self.active_tasks.add(task)
        task.add_done_callback(self.active_tasks.discard)
    
    def _cancel_existing_task(self, key: Tuple[int, int]):
        """取消现有的删除任务"""
        if key in self.scheduled_deletions:
            task_info = self.scheduled_deletions[key]
            task = task_info.get('task')
            if task and not task.done():
                task.cancel()
            del self.scheduled_deletions[key]
    
    def cancel_deletion(self, chat_id: int, message_id: int) -> bool:
        """取消指定消息的删除任务
        
        Args:
            chat_id: 聊天ID
            message_id: 消息ID
            
        Returns:
            bool: 是否成功取消
        """
        key = (chat_id, message_id)
        if key in self.scheduled_deletions:
            self._cancel_existing_task(key)
            logger.debug(f"取消删除任务: {message_id}")
            return True
        return False
    
    def _periodic_cleanup(self):
        """定期清理过期的调度信息"""
        current_time = time.time()
        if current_time - self._last_cleanup > self._cleanup_interval:
            self._force_cleanup()
            self._last_cleanup = current_time
    
    def _force_cleanup(self):
        """强制清理已完成或过期的任务"""
        keys_to_remove = []
        for key, task_info in self.scheduled_deletions.items():
            task = task_info.get('task')
            if task and task.done():
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self.scheduled_deletions[key]
        
        if keys_to_remove:
            logger.debug(f"清理了 {len(keys_to_remove)} 个已完成的删除任务")
    
    def get_pending_deletions(self) -> Dict[str, int]:
        """获取待删除的消息统计"""
        pending_count = 0
        expired_count = 0
        current_time = time.time()
        
        for task_info in self.scheduled_deletions.values():
            scheduled_time = task_info.get('scheduled_time', 0)
            if scheduled_time > current_time:
                pending_count += 1
            else:
                expired_count += 1
        
        return {
            'pending': pending_count,
            'expired': expired_count,
            'total': len(self.scheduled_deletions)
        }
    
    def cancel_all_deletions(self):
        """取消所有删除任务"""
        cancelled_count = 0
        for key in list(self.scheduled_deletions.keys()):
            if self.cancel_deletion(key[0], key[1]):
                cancelled_count += 1
        
        logger.info(f"取消了 {cancelled_count} 个删除任务")
        return cancelled_count
    
    def get_stats(self) -> Dict[str, int]:
        """获取删除任务统计信息"""
        pending_stats = self.get_pending_deletions()
        return {
            **pending_stats,
            'active_tasks': len(self.active_tasks)
        }

# 全局删除任务管理器实例
deletion_manager = DeletionTaskManager()

def get_deletion_manager() -> DeletionTaskManager:
    """获取全局删除任务管理器实例"""
    return deletion_manager

# 便捷函数
def schedule_message_deletion(context, chat_id: int, message_id: int, delay: int, 
                            task_name: Optional[str] = None) -> bool:
    """调度消息删除的便捷函数"""
    return deletion_manager.schedule_deletion(context, chat_id, message_id, delay, task_name)

def cancel_message_deletion(chat_id: int, message_id: int) -> bool:
    """取消消息删除的便捷函数"""
    return deletion_manager.cancel_deletion(chat_id, message_id)
