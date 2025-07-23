#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
消息删除调度器
后台任务，定期处理到期的消息删除任务
"""

import asyncio
import logging
import time
from typing import List
from telegram.error import TelegramError

from .message_delete_manager import message_delete_manager, DeleteTask

logger = logging.getLogger(__name__)

class MessageDeleteScheduler:
    """消息删除调度器"""
    
    def __init__(self):
        self.is_running = False
        self.task = None
        self.check_interval = 10  # 检查间隔（秒）
        self.batch_size = 50  # 每次处理的批量大小
        self.context = None
    
    def start(self, bot):
        """启动调度器"""
        if self.is_running:
            return
        
        self.bot = bot
        self.is_running = True
        self.task = asyncio.create_task(self._run_scheduler())
        logger.info("消息删除调度器已启动")
    
    def stop(self):
        """停止调度器"""
        if not self.is_running:
            return
        
        self.is_running = False
        if self.task:
            self.task.cancel()
        logger.info("消息删除调度器已停止")
    
    async def _run_scheduler(self):
        """运行调度器主循环"""
        while self.is_running:
            try:
                await self._process_due_tasks()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"消息删除调度器运行错误: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _process_due_tasks(self):
        """处理到期的删除任务"""
        self.last_check_time = time.time()
        try:
            due_tasks = message_delete_manager.get_due_tasks(self.batch_size)
            if not due_tasks:
                return
            
            successful_ids = []
            failed_tasks = []
            
            for task in due_tasks:
                if await self._delete_message(task):
                    successful_ids.append(task.id)
                else:
                    failed_tasks.append(task)
            
            if successful_ids:
                message_delete_manager.remove_tasks(successful_ids)
            
            if failed_tasks:
                await self._handle_failed_tasks(failed_tasks)
                
        except Exception as e:
            logger.error(f"处理到���任务时发生错误: {e}")
    
    async def _delete_message(self, task: DeleteTask) -> bool:
        """
        删除单个消息
        Returns: True if successful, False otherwise.
        """
        try:
            await self.bot.delete_message(
                chat_id=task.chat_id,
                message_id=task.message_id
            )
            
            if task.task_type == "search_result" and task.user_id:
                await self._cleanup_search_session(task)
            
            return True
            
        except TelegramError as e:
            # 即使删除失败（例如消息不存在），也清理会话
            if task.task_type == "search_result" and task.user_id:
                await self._cleanup_search_session(task)
            return False
                
        except Exception:
            return False
    
    async def _cleanup_search_session(self, task: DeleteTask):
        """清理搜索会话"""
        # SessionManager会自动处理过期，这里保持为空或只做日志记录
        pass
    
    async def _handle_failed_tasks(self, failed_tasks: List[DeleteTask]):
        """处理失败的任务"""
        tasks_to_remove = []
        
        for task in failed_tasks:
            if task.retries < 1:
                # 第一次失败，安排重试
                message_delete_manager.retry_task(task.id, retry_delay=120)  # 2分钟后重试
            else:
                # 重试次数已达上限，直接移除
                tasks_to_remove.append(task.id)
        
        if tasks_to_remove:
            message_delete_manager.remove_tasks(tasks_to_remove)
    
    def get_status(self) -> dict:
        """获取调度器状态"""
        pending_count = message_delete_manager.get_task_count()
        
        return {
            "is_running": self.is_running,
            "check_interval": self.check_interval,
            "batch_size": self.batch_size,
            "pending_tasks": pending_count,
            "last_check": getattr(self, 'last_check_time', None)
        }

# 全局调度器实例
message_delete_scheduler = MessageDeleteScheduler()