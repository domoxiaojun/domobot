"""
权限管理装饰器和工具函数
"""

import functools
import logging
from enum import Enum

from telegram import Update
from telegram.ext import ContextTypes

from utils.config_manager import get_config

logger = logging.getLogger(__name__)

# 获取配置
config = get_config()


class Permission(Enum):
    """权限等级枚举"""

    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


# ============================================================================
# 核心权限检查函数
# ============================================================================


def is_super_admin(user_id: int) -> bool:
    """
    检查用户是否为超级管理员

    Args:
        user_id: 用户ID

    Returns:
        是否为超级管理员
    """
    return user_id in config.super_admin_ids


async def is_admin(user_id: int, user_manager) -> bool:
    """
    检查用户是否为管理员（包括超级管理员和普通管理员）

    Args:
        user_id: 用户ID
        user_manager: 用户管理器实例

    Returns:
        是否为管理员
    """
    if is_super_admin(user_id):
        return True

    return await user_manager.is_admin(user_id)


async def _has_user_permission(
    user_id: int, chat_type: str, chat_id: int, user_manager
) -> bool:
    """
    检查用户是否有基本使用权限

    权限检查逻辑:
    1. 管理员在任何场景都有权限
    2. 私聊需要用户在白名单中
    3. 群组需要群组在白名单中

    Args:
        user_id: 用户ID
        chat_type: 聊天类型 (private/group/supergroup)
        chat_id: 聊天ID
        user_manager: 用户管理器实例

    Returns:
        是否有权限
    """
    # 管理员在任何地方都有权限
    if await is_admin(user_id, user_manager):
        return True

    # 私聊检查用户白名单
    if chat_type == "private":
        return await user_manager.is_whitelisted(user_id)

    # 群聊检查群组白名单
    if chat_type in ["group", "supergroup"]:
        return await user_manager.is_group_whitelisted(chat_id)

    return False


async def _check_permission_level(
    user_id: int,
    chat_type: str,
    chat_id: int,
    user_manager,
    required_permission: Permission,
) -> bool:
    """
    检查用户是否满足指定权限级别

    Args:
        user_id: 用户ID
        chat_type: 聊天类型
        chat_id: 聊天ID
        user_manager: 用户管理器实例
        required_permission: 所需权限级别

    Returns:
        是否满足权限要求
    """
    if required_permission == Permission.SUPER_ADMIN:
        # 只有超级管理员才能通过
        return is_super_admin(user_id)

    if required_permission == Permission.ADMIN:
        # 超级管理员或普通管理员都可以通过
        return await is_admin(user_id, user_manager)

    # Permission.USER：普通用户权限
    return await _has_user_permission(user_id, chat_type, chat_id, user_manager)


async def _send_permission_error(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    permission_level: Permission,
) -> None:
    """
    发送权限错误消息

    Args:
        update: Telegram更新对象
        context: 上下文对象
        permission_level: 所需权限级别
    """
    from utils.message_manager import send_message_with_auto_delete, MessageType

    permission_msg = {
        Permission.SUPER_ADMIN: "此命令仅限超级管理员使用。",
        Permission.ADMIN: "此命令仅限管理员使用。",
        Permission.USER: "你没有使用此机器人的权限。\n请联系管理员申请权限。",
    }

    # 确定是否需要删除用户命令消息
    command_message_id = None
    if update.message and config.delete_user_commands:
        command_message_id = update.message.message_id

    # 只在有消息或回调查询时发送错误（保持向后兼容）
    if update.message or (update.callback_query and update.callback_query.message):
        await send_message_with_auto_delete(
            context=context,
            chat_id=update.effective_chat.id,
            text=f"❌ **权限不足**\n\n{permission_msg[permission_level]}",
            msg_type=MessageType.ERROR,
            custom_delay=config.auto_delete_delay,
            reply_to_message_id=command_message_id,
            parse_mode="Markdown",
        )


# ============================================================================
# 公共装饰器和工具函数
# ============================================================================


def require_permission(permission: Permission):
    """
    权限检查装饰器

    使用示例:
        @require_permission(Permission.USER)
        async def my_command(update, context):
            ...

        @require_permission(Permission.ADMIN)
        async def admin_command(update, context):
            ...

    Args:
        permission: 所需权限等级
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            chat_type = update.effective_chat.type
            chat_id = update.effective_chat.id

            # 记录使用日志
            logger.info(
                f"User {user_id} attempting to use {func.__name__} in {chat_type}"
            )

            # 获取用户管理器
            user_manager = context.bot_data.get("user_cache_manager")
            if not user_manager:
                logger.error("用户管理器未初始化")
                # 向用户发送错误提示
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="❌ 服务暂时不可用，请稍后重试",
                    )
                except Exception as e:
                    logger.error(f"发送错误消息失败: {e}")
                return

            # 检查权限
            try:
                has_permission = await _check_permission_level(
                    user_id, chat_type, chat_id, user_manager, permission
                )

                if not has_permission:
                    # 发送权限错误消息
                    await _send_permission_error(update, context, permission)
                    return

            except Exception as e:
                logger.error(f"权限检查时出错: {e}", exc_info=True)
                # 权限检查失败时拒绝访问
                return

            # 执行原函数
            try:
                return await func(update, context)
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ 处理请求时发生错误，请稍后重试。\n如果问题持续存在，请联系管理员。",
                )

        return wrapper

    return decorator


async def get_user_permission(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> Permission | None:
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
    chat_id = update.effective_chat.id

    # 获取用户管理器
    user_manager = context.bot_data.get("user_cache_manager")
    if not user_manager:
        logger.error("用户管理器未初始化")
        return None

    try:
        # 检查超级管理员
        if is_super_admin(user_id):
            return Permission.SUPER_ADMIN

        # 检查管理员
        if await user_manager.is_admin(user_id):
            return Permission.ADMIN

        # 检查普通用户权限
        if await _has_user_permission(user_id, chat_type, chat_id, user_manager):
            return Permission.USER

    except Exception as e:
        logger.error(f"获取用户权限时出错: {e}", exc_info=True)

    # 没有权限
    return None


async def check_user_permissions(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> dict:
    """
    检查用户权限并返回详细信息

    Returns:
        dict: 包含权限信息的字典
    """
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type

    # 获取用户管理器
    user_manager = context.bot_data.get("user_cache_manager")

    result = {
        "user_id": user_id,
        "chat_type": chat_type,
        "is_super_admin": is_super_admin(user_id),
        "is_admin": False,
        "is_whitelisted": False,
        "group_whitelisted": False,
        "has_permission": False,
        "permissions": {},
    }

    if not user_manager:
        logger.error("用户管理器未初始化")
        return result

    try:
        # 使用 get_user_permission 获取权限等级
        permission_level = await get_user_permission(update, context)

        # 根据权限等级设置详细信息
        if permission_level == Permission.SUPER_ADMIN:
            result["is_admin"] = True
            result["has_permission"] = True
            result["permissions"] = {
                "manage_users": True,
                "manage_groups": True,
                "clear_cache": True,
            }
        elif permission_level == Permission.ADMIN:
            result["is_admin"] = True
            result["has_permission"] = True
            result["permissions"] = {
                "manage_users": True,
                "manage_groups": True,
                "clear_cache": True,
            }
        elif permission_level == Permission.USER:
            result["has_permission"] = True
            # 检查具体是哪种白名单
            if chat_type == "private":
                result["is_whitelisted"] = await user_manager.is_whitelisted(user_id)
            elif chat_type in ["group", "supergroup"]:
                chat_id = update.effective_chat.id
                result["group_whitelisted"] = await user_manager.is_group_whitelisted(
                    chat_id
                )

    except Exception as e:
        logger.error(f"检查用户权限时出错: {e}", exc_info=True)

    return result
