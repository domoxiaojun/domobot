#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
兼容性适配器
为现有的管理器提供兼容接口，使用统一数据库后端
"""

import logging
from typing import Set, List, Dict, Optional, Any
from utils.unified_database import get_db_manager, DeleteTask

logger = logging.getLogger(__name__)

class WhitelistManager:
    """白名单管理器 - 兼容性适配器"""
    
    def __init__(self, db_path: Optional[str] = None):
        """初始化 - db_path参数保留兼容性，但实际使用统一数据库"""
        self.db_manager = get_db_manager()
        if db_path:
            logger.warning(f"WhitelistManager: db_path参数 '{db_path}' 已忽略，使用统一数据库")
    
    def add_user(self, user_id: int) -> bool:
        """添加用户到白名单"""
        return self.db_manager.add_user_to_whitelist(user_id)
    
    def remove_user(self, user_id: int) -> bool:
        """从白名单移除用户"""
        return self.db_manager.remove_user_from_whitelist(user_id)
    
    def is_whitelisted(self, user_id: int) -> bool:
        """检查用户是否在白名单中"""
        return self.db_manager.is_user_whitelisted(user_id)
    
    def get_all_whitelisted_users(self) -> Set[int]:
        """获取所有白名单用户"""
        return self.db_manager.get_all_whitelisted_users()
    
    def add_group(self, group_id: int, group_name: str, added_by: int) -> bool:
        """添加群组到白名单"""
        return self.db_manager.add_group_to_whitelist(group_id, group_name, added_by)
    
    def remove_group(self, group_id: int) -> bool:
        """从白名单移除群组"""
        return self.db_manager.remove_group_from_whitelist(group_id)
    
    def is_group_whitelisted(self, group_id: int) -> bool:
        """检查群组是否在白名单中"""
        return self.db_manager.is_group_whitelisted(group_id)
    
    def get_all_whitelisted_groups(self) -> List[Dict]:
        """获取所有白名单群组"""
        return self.db_manager.get_all_whitelisted_groups()

class AdminManager:
    """管理员管理器 - 兼容性适配器"""
    
    def __init__(self, db_path: Optional[str] = None):
        """初始化 - db_path参数保留兼容性，但实际使用统一数据库"""
        self.db_manager = get_db_manager()
        self.whitelist_manager = WhitelistManager()
        
        # 从环境变量获取超级管理员ID
        import os
        self.super_admin_id = int(os.getenv('SUPER_ADMIN_ID', 0))
        
        if db_path:
            logger.warning(f"AdminManager: db_path参数 '{db_path}' 已忽略，使用统一数据库")
    
    def is_super_admin(self, user_id: int) -> bool:
        """检查是否为超级管理员"""
        return user_id == self.super_admin_id
    
    def is_admin(self, user_id: int) -> bool:
        """检查是否为管理员（包括超级管理员）"""
        if self.is_super_admin(user_id):
            return True
        return self.db_manager.is_admin(user_id)
    
    def has_permission(self, user_id: int, permission: str) -> bool:
        """检查用户是否有特定权限"""
        if self.is_super_admin(user_id):
            return True
        return self.db_manager.has_permission(user_id, permission)
    
    def add_admin(self, user_id: int, username: Optional[str] = None, granted_by: Optional[int] = None, 
                  **permissions) -> bool:
        """添加管理员"""
        return self.db_manager.add_admin(
            user_id=user_id,
            username=username,
            granted_by=granted_by,
            can_manage_users=permissions.get('can_manage_users', False),
            can_manage_groups=permissions.get('can_manage_groups', False),
            can_clear_cache=permissions.get('can_clear_cache', False)
        )
    
    def remove_admin(self, user_id: int) -> bool:
        """移除管理员"""
        return self.db_manager.remove_admin(user_id)
    
    def update_admin_permissions(self, user_id: int, **permissions) -> bool:
        """更新管理员权限"""
        return self.db_manager.update_admin_permissions(user_id, **permissions)
    
    def get_all_admins(self) -> List[Dict]:
        """获取所有管理员"""
        return self.db_manager.get_all_admins()

class MessageDeleteManager:
    """消息删除管理器 - 兼容性适配器"""
    
    def __init__(self, db_path: Optional[str] = None):
        """初始化 - db_path参数保留兼容性，但实际使用统一数据库"""
        self.db_manager = get_db_manager()
        if db_path:
            logger.warning(f"MessageDeleteManager: db_path参数 '{db_path}' 已忽略，使用统一数据库")
    
    def schedule_deletion(self, task: DeleteTask) -> Optional[int]:
        """调度一个删除任务"""
        return self.db_manager.schedule_deletion(task)
    
    def get_due_tasks(self, limit: int = 100) -> List[DeleteTask]:
        """获取到期的删除任务"""
        return self.db_manager.get_due_tasks(limit)
    
    def remove_task(self, task_id: int) -> bool:
        """移除删除任务"""
        return self.db_manager.remove_task(task_id)
    
    def remove_tasks_by_session(self, session_id: str) -> int:
        """根据会话ID移除任务"""
        return self.db_manager.remove_tasks_by_session(session_id)
    
    def cleanup_expired_tasks(self, days_old: int = 7) -> int:
        """清理过期的任务记录"""
        return self.db_manager.cleanup_expired_tasks(days_old)
    
    def get_task_stats(self) -> Dict[str, Any]:
        """获取任务统计信息"""
        return self.db_manager.get_task_stats()
    
    # 为了完全兼容原有接口，添加一些可能缺少的方法
    def create_delete_task(self, chat_id: int, message_id: int, delete_after: int,
                          task_type: str = "bot_message", user_id: Optional[int] = None,
                          session_id: Optional[str] = None, metadata: Optional[str] = None) -> Optional[int]:
        """创建删除任务的便捷方法"""
        import time
        
        task = DeleteTask(
            chat_id=chat_id,
            message_id=message_id,
            delete_at=time.time() + delete_after,
            task_type=task_type,
            user_id=user_id,
            session_id=session_id,
            created_at=time.time(),
            metadata=metadata
        )
        
        return self.schedule_deletion(task)
