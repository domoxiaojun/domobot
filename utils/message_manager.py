#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
消息管理工具模块
提供基于数据库的持久化消息删除调度功能
"""

import logging
import time
from typing import Optional

from utils.message_delete_manager import message_delete_manager, DeleteTask

logger = logging.getLogger(__name__)

def schedule_message_deletion(
    chat_id: int,
    message_id: int,
    delay: int,
    task_type: str = "bot_message",
    user_id: Optional[int] = None,
    session_id: Optional[str] = None,
    metadata: Optional[str] = None
) -> Optional[int]:
    """
    调度消息删除任务到数据库
    
    Args:
        chat_id: 聊天ID
        message_id: 消息ID
        delay: 延迟删除的秒数
        task_type: 任务类型 (bot_message, user_command, search_result)
        user_id: 用户ID（可选）
        session_id: 会话ID（可选）
        metadata: 元数据JSON字符串（可选）
        
    Returns:
        int: 任务ID，失败时返回 None
    """
    if delay <= 0:
        return None
    
    current_time = time.time()
    delete_at = current_time + delay
    
    task = DeleteTask(
        chat_id=chat_id,
        message_id=message_id,
        delete_at=delete_at,
        task_type=task_type,
        user_id=user_id,
        session_id=session_id,
        created_at=current_time,
        metadata=metadata
    )
    
    task_id = message_delete_manager.schedule_deletion(task)
    if task_id:
        logger.debug(f"已调度消息删除: 聊天 {chat_id}, 消息 {message_id}, 延迟 {delay}秒, 任务ID {task_id}")
    
    return task_id

def cancel_session_deletions(session_id: str) -> int:
    """
    取消指定会话的所有删除任务
    
    Args:
        session_id: 会话ID
        
    Returns:
        int: 取消的任务数量
    """
    return message_delete_manager.cancel_session_tasks(session_id)

def cancel_user_deletions(user_id: int, task_type: Optional[str] = None) -> int:
    """
    取消指定用户的删除任务
    
    Args:
        user_id: 用户ID
        task_type: 任务类型过滤（可选）
        
    Returns:
        int: 取消的任务数量
    """
    return message_delete_manager.cancel_user_tasks(user_id, task_type)

