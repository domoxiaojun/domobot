"""
权限管理装饰器和工具函数
"""
import functools
import logging
from enum import Enum
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from utils.compatibility_adapters import AdminManager, WhitelistManager

logger = logging.getLogger(__name__)

# Create instances using the new compatibility adapters
admin_manager = AdminManager()
whitelist_manager = WhitelistManager()

class Permission(Enum):
    """权限等级枚举"""
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"

def require_permission(permission: Permission):
    """
    权限检查装饰器
    
    Args:
        permission: 所需权限等级
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            chat_type = update.effective_chat.type
            
            # 记录使用日志
            logger.info(f"User {user_id} attempting to use {func.__name__} in {chat_type}")
            
            # 检查权限
            has_permission = False
            
            if permission == Permission.SUPER_ADMIN:
                has_permission = admin_manager.is_super_admin(user_id)
            elif permission == Permission.ADMIN:
                has_permission = admin_manager.is_admin(user_id)
            else:  # Permission.USER
                if admin_manager.is_admin(user_id):
                    has_permission = True
                elif chat_type in ['group', 'supergroup']:
                    chat_id = update.effective_chat.id
                    if whitelist_manager.is_group_whitelisted(chat_id):
                        has_permission = True
                elif chat_type == 'private':
                    has_permission = whitelist_manager.is_whitelisted(user_id)
            
            if not has_permission:
                permission_msg = {
                    Permission.SUPER_ADMIN: "此命令仅限超级管理员使用。",
                    Permission.ADMIN: "此命令仅限管理员使用。",
                    Permission.USER: "你没有使用此机器人的权限。\n请联系管理员申请权限。"
                }
                
                # 使用自动删除功能发送权限错误消息
                from utils.message_manager import schedule_message_deletion
                from utils.config_manager import get_config
                config = get_config()
                
                if update.message:
                    sent_message = await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"❌ **权限不足**\n\n{permission_msg[permission]}",
                        parse_mode='Markdown',
                    )
                    schedule_message_deletion(
                        chat_id=sent_message.chat_id,
                        message_id=sent_message.message_id,
                        delay=config.auto_delete_delay,
                        user_id=update.effective_user.id,
                    )
                    if config.delete_user_commands:
                        schedule_message_deletion(
                            chat_id=update.effective_chat.id,
                            message_id=update.message.message_id,
                            delay=config.user_command_delete_delay,
                            task_type="user_command",
                            user_id=update.effective_user.id,
                        )
                elif update.callback_query and update.callback_query.message:
                    sent_message = await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"❌ **权限不足**\n\n{permission_msg[permission]}",
                        parse_mode='Markdown',
                    )
                    schedule_message_deletion(
                        chat_id=sent_message.chat_id,
                        message_id=sent_message.message_id,
                        delay=config.auto_delete_delay,
                        user_id=update.effective_user.id,
                    )
                return
            
            # 执行原函数
            try:
                return await func(update, context)
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ 处理请求时发生错误，请稍后重试。\n"
                         "如果问题持续存在，请联系管理员。"
                )
        
        return wrapper
    return decorator

# 保留向后兼容性的装饰器
def permission_required(require_admin=False):
    """
    权限检查装饰器 (向后兼容)
    
    Args:
        require_admin: 是否需要管理员权限
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            from utils.message_manager import schedule_message_deletion
            from utils.config_manager import get_config
            config = get_config()
            
            user_id = update.effective_user.id
            chat_type = update.effective_chat.type
            
            # 记录使用日志
            logger.info(f"User {user_id} attempting to use {func.__name__} in {chat_type}")
            
            # 检查管理员权限
            if require_admin:
                if not admin_manager.is_admin(user_id):
                    sent_message = await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="❌ **管理员权限不足**\n\n"
                             "此命令仅限管理员使用。",
                        parse_mode='Markdown',
                    )
                    schedule_message_deletion(
                        chat_id=sent_message.chat_id,
                        message_id=sent_message.message_id,
                        delay=config.auto_delete_delay,
                        user_id=update.effective_user.id,
                    )
                    if config.delete_user_commands and update.message:
                        schedule_message_deletion(
                            chat_id=update.effective_chat.id,
                            message_id=update.message.message_id,
                            delay=config.user_command_delete_delay,
                            task_type="user_command",
                            user_id=update.effective_user.id,
                        )
                    return
            else:
                # 检查基本使用权限
                has_permission = False
                
                # 管理员在任何地方都有权限
                if admin_manager.is_admin(user_id):
                    has_permission = True
                # 私聊检查用户白名单
                elif chat_type == 'private':
                    has_permission = whitelist_manager.is_whitelisted(user_id)
                # 群聊检查群组白名单
                elif chat_type in ['group', 'supergroup']:
                    chat_id = update.effective_chat.id
                    has_permission = whitelist_manager.is_group_whitelisted(chat_id)
                
                if not has_permission:
                    sent_message = await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="❌ **权限不足**\n\n"
                             "你没有使用此机器人的权限。\n"
                             "请联系管理员申请权限。",
                        parse_mode='Markdown',
                    )
                    schedule_message_deletion(
                        chat_id=sent_message.chat_id,
                        message_id=sent_message.message_id,
                        delay=config.auto_delete_delay,
                        user_id=update.effective_user.id,
                    )
                    if config.delete_user_commands and update.message:
                        schedule_message_deletion(
                            chat_id=update.effective_chat.id,
                            message_id=update.message.message_id,
                            delay=config.user_command_delete_delay,
                            task_type="user_command",
                            user_id=update.effective_user.id,
                        )
                    return
            
            # 执行原函数
            try:
                return await func(update, context)
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ 处理请求时发生错误，请稍后重试。\n"
                         "如果问题持续存在，请联系管理员。"
                )
        
        return wrapper
    return decorator

async def check_user_permissions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> dict:
    """
    检查用户权限并返回详细信息
    
    Returns:
        dict: 包含权限信息的字典
    """
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    
    result = {
        'user_id': user_id,
        'chat_type': chat_type,
        'is_super_admin': admin_manager.is_super_admin(user_id),
        'is_admin': admin_manager.is_admin(user_id),
        'is_whitelisted': False,
        'group_whitelisted': False,
        'has_permission': False,
        'permissions': {}
    }
    
    # 检查管理员权限
    if result['is_admin']:
        result['permissions'] = {
            'manage_users': admin_manager.has_permission(user_id, 'manage_users'),
            'manage_groups': admin_manager.has_permission(user_id, 'manage_groups'),
            'clear_cache': admin_manager.has_permission(user_id, 'clear_cache')
        }
        result['has_permission'] = True
    else:
        # 检查普通用户权限
        if chat_type == 'private':
            result['is_whitelisted'] = whitelist_manager.is_whitelisted(user_id)
            result['has_permission'] = result['is_whitelisted']
        elif chat_type in ['group', 'supergroup']:
            chat_id = update.effective_chat.id
            result['group_whitelisted'] = whitelist_manager.is_group_whitelisted(chat_id)
            result['has_permission'] = result['group_whitelisted']
    
    return result

async def get_user_permission(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[Permission]:
    """
    获取用户的权限等级
    
    Args:
        update: Telegram更新对象
        context: 上下文对象
        
    Returns:
        用户的权限等级，如果没有权限则返回None
    """
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    
    # 检查超级管理员
    if admin_manager.is_super_admin(user_id):
        return Permission.SUPER_ADMIN
    
    # 检查管理员
    if admin_manager.is_admin(user_id):
        return Permission.ADMIN
    
    # 检查普通用户权限
    if chat_type == 'private':
        # 私聊中需要用户在白名单中
        if whitelist_manager.is_whitelisted(user_id):
            return Permission.USER
    elif chat_type in ['group', 'supergroup']:
        # 群组中需要群组在白名单中
        chat_id = update.effective_chat.id
        if whitelist_manager.is_group_whitelisted(chat_id):
            return Permission.USER
    
    # 没有权限
    return None
