# type: ignore
import logging
from datetime import datetime

from telegram import Update, Message
from telegram.ext import ContextTypes

from utils.command_factory import command_factory
from utils.formatter import foldable_text_with_markdown_v2
from utils.message_manager import delete_user_command, send_search_result
from utils.permissions import Permission
from utils.pyrofork import get_user_full_info
from utils.pyrofork.session import REDIS_KEY_USER_REG_DATE_PREFIX

logger = logging.getLogger(__name__)


# ============ 辅助工具函数 ============

# 对话类型映射
CHAT_TYPE_MAP = {
    "private": "私聊",
    "group": "群组",
    "supergroup": "超级群组",
    "channel": "频道",
}


def get_message_type(message: Message) -> str:
    """
    检测消息类型并返回中文描述。
    """
    if message.text:
        return "文本"
    elif message.photo:
        return "图片"
    elif message.video:
        return "视频"
    elif message.document:
        return "文档"
    elif message.audio:
        return "音频"
    elif message.voice:
        return "语音"
    elif message.sticker:
        return "贴纸"
    elif message.animation:
        return "动画/GIF"
    elif message.location:
        return "位置"
    elif message.contact:
        return "联系人"
    elif message.poll:
        return "投票"
    elif message.dice:
        return "骰子"
    elif message.video_note:
        return "视频消息"
    else:
        return "其他"


def format_timestamp(timestamp) -> str:
    """
    将时间戳或 datetime 对象转换为可读格式。

    Args:
        timestamp: Unix 时间戳（int）或 datetime 对象

    Returns:
        格式化的时间字符串
    """
    # 如果已经是 datetime 对象，直接使用
    if isinstance(timestamp, datetime):
        dt = timestamp
        # 如果有时区信息,转换为本地时区
        if dt.tzinfo is not None:
            dt = dt.astimezone()  # 自动转换为系统本地时区
    else:
        # 否则假设是 Unix 时间戳
        dt = datetime.fromtimestamp(timestamp)

    return dt.strftime("%Y年%m月%d日 %H:%M:%S")


async def format_user_info_with_advanced(
    user,
    context: ContextTypes.DEFAULT_TYPE,
    prefix: str = "",
    bot=None,
    force_refresh: bool = False,
) -> str:
    """
    格式化用户信息（包含高级信息）。

    Args:
        user: Telegram User 对象
        context: Telegram Context 对象（用于获取依赖）
        prefix: 字段名称前缀（如 "发送者"、"被回复用户" 等）
        bot: Telegram Bot 实例 (可选,用于从头像获取 DC)
        force_refresh: 强制跳过缓存直接查询 Raw API（/cinfo 使用）

    Returns:
        格式化的用户信息文本
    """
    if not user:
        return ""

    info_lines = []
    bottom_tips = []  # 收集需要显示在最下面的提示

    # 用户 ID
    info_lines.append(f"{prefix}ID: `{user.id}`")

    # 姓名
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    if full_name:
        info_lines.append(f"{prefix}姓名: {full_name}")

    # 用户名
    if user.username:
        info_lines.append(f"{prefix}用户名: @{user.username}")

    # 语言
    if hasattr(user, "language_code") and user.language_code:
        info_lines.append(f"{prefix}语言: {user.language_code}")

    # 机器人状态
    if user.is_bot:
        info_lines.append(f"{prefix}类型: 🤖 机器人")
        return "\n".join(info_lines)  # 机器人不显示高级信息

    # 获取高级用户信息（注册日期、账号年龄、DC、Premium 状态）
    logger.debug(f"开始获取用户 {user.id} 的高级信息...")
    try:
        # 从 context.bot_data 获取依赖
        mysql_manager = context.bot_data.get("user_cache_manager")
        cache_manager = context.bot_data.get("cache_manager")
        redis_client = cache_manager.redis_client if cache_manager else None

        advanced_info = await get_user_full_info(
            user_id=user.id,
            redis_client=redis_client,
            user=user,
            bot=bot,
            mysql_manager=mysql_manager,
            force_refresh=force_refresh,
        )
        if advanced_info:
            logger.debug(f"成功获取用户 {user.id} 的高级信息: {advanced_info.keys()}")

            # Premium 状态
            if "is_premium" in advanced_info and advanced_info["is_premium"]:
                info_lines.append(f"{prefix}Premium 用户: ⭐ 是")
                logger.debug("添加 Premium 状态: 是")

            # 注册时间 (根据数据来源显示不同图标)
            if (
                "registration_year" in advanced_info
                and advanced_info["registration_year"]
            ):
                year = advanced_info["registration_year"]
                month = advanced_info["registration_month"]
                source = advanced_info.get("registration_source", "unknown")

                # 根据数据来源显示不同的标记
                if source == "peersettings":
                    marker = " (官方)"  # 官方数据
                elif source == "id_estimation":
                    marker = " (ID估算)"  # 推测数据
                    # 添加提示到底部（引导用户私聊登录账号以建立 peer 关系）
                    from utils.pyrofork.client import get_logged_in_username

                    logged_in_username = get_logged_in_username()
                    if logged_in_username:
                        bottom_tips.append(
                            f"💡 要获取准确的注册时间，请先[私聊 @{logged_in_username}]"
                            f"(https://t.me/{logged_in_username})发送任意消息，"
                            f"然后使用 /cinfo 重新查询"
                        )
                    else:
                        bot_username = context.bot.username or "bot"
                        bottom_tips.append(
                            f"💡 要获取准确的注册时间，请[点击私聊](https://t.me/{bot_username})发送 /info"
                        )
                else:
                    marker = " (ID估算)"  # 未知来源，默认标记为估算

                info_lines.append(f"{prefix}注册时间: {year}年{month}月{marker}")
                logger.debug(f"添加注册时间: {year}年{month}月 (来源: {source})")
            # 账号年龄（显示年月，不显示天数）
            if "account_age_years" in advanced_info:
                age_years = advanced_info.get("account_age_years", 0)
                age_months = advanced_info.get("account_age_months", 0)

                age_parts = []
                if age_years > 0:
                    age_parts.append(f"{age_years}年")
                if age_months > 0:
                    age_parts.append(f"{age_months}个月")

                if age_parts:
                    info_lines.append(f"{prefix}账号年龄: {''.join(age_parts)}")
                    logger.debug(f"添加账号年龄: {age_years}年{age_months}个月")

            # 数据中心（仅当获取到 dc_id 时显示）
            if "dc_id" in advanced_info and advanced_info["dc_id"] is not None:
                dc_id = advanced_info["dc_id"]
                dc_location = advanced_info.get("dc_location", f"Unknown DC{dc_id}")
                info_lines.append(f"{prefix}数据中心: DC{dc_id} ({dc_location})")
                logger.debug(f"添加数据中心: DC{dc_id}")

            # PeerSettings 附加字段（仅官方数据时才有值）
            if advanced_info.get("registration_source") == "peersettings":
                phone_country = advanced_info.get("phone_country")
                name_change_date = advanced_info.get("name_change_date")
                photo_change_date = advanced_info.get("photo_change_date")

                if phone_country:
                    info_lines.append(f"{prefix}手机地区: {phone_country}")
                if name_change_date:
                    info_lines.append(
                        f"{prefix}改名时间: {format_timestamp(name_change_date)}"
                    )
                if photo_change_date:
                    info_lines.append(
                        f"{prefix}换头像时间: {format_timestamp(photo_change_date)}"
                    )
        else:
            logger.warning(f"未获取到用户 {user.id} 的高级信息（返回值为空）")
    except Exception as e:
        # 如果获取高级信息失败，不显示，但不中断整个流程
        logger.error(f"获取用户 {user.id} 高级信息失败: {e}", exc_info=True)

    # 在最后添加底部提示
    if bottom_tips:
        info_lines.append("")  # 空行分隔
        info_lines.extend(bottom_tips)

    return "\n".join(info_lines)


# ============ 公共构建函数 ============


async def _build_info_blocks(
    chat,
    message: Message,
    user,
    context: ContextTypes.DEFAULT_TYPE,
    bot,
    *,
    cache_cleared: bool = False,
) -> list:
    """构建信息展示块（info 和 cinfo 共用）"""
    info_blocks = []

    # ━━━━━━━━ 📱 对话信息 ━━━━━━━━
    chat_info = ["━━━━━━━━ 📱 对话信息 ━━━━━━━━"]
    id_label = "对话 ID" if chat.type == "private" else "群组 ID"
    chat_info.append(f"{id_label}: `{chat.id}`")
    chat_info.append(f"对话类型: {CHAT_TYPE_MAP.get(chat.type, chat.type)}")
    if chat.title:
        chat_info.append(f"对话标题: {chat.title}")
    info_blocks.append("\n".join(chat_info))

    # ━━━━━━━━ 🔁 / 👤 用户信息 ━━━━━━━━
    if message.reply_to_message:
        reply_msg = message.reply_to_message
        reply_info = ["━━━━━━━━ 🔁 回复消息信息 ━━━━━━━━"]
        if cache_cleared:
            reply_info.append("🔄 已清除缓存,重新查询中...")
        reply_info.append(f"消息 ID: `{reply_msg.message_id}`")
        reply_info.append(f"消息类型: {get_message_type(reply_msg)}")

        if reply_msg.from_user:
            reply_info.append("")  # 空行分隔
            user_text = await format_user_info_with_advanced(
                reply_msg.from_user,
                context,
                prefix="",
                bot=bot,
                force_refresh=cache_cleared,
            )
            reply_info.append(user_text)

        reply_info.append("")  # 空行分隔
        reply_info.append(f"发送时间: {format_timestamp(reply_msg.date)}")
        if reply_msg.edit_date:
            reply_info.append(f"编辑时间: {format_timestamp(reply_msg.edit_date)}")
        if reply_msg.chat and reply_msg.chat.id != chat.id:
            reply_info.append(f"来源对话 ID: `{reply_msg.chat.id}`")

        info_blocks.append("\n".join(reply_info))
    else:
        sender_info = ["━━━━━━━━ 👤 用户信息 ━━━━━━━━"]
        user_text = await format_user_info_with_advanced(
            user,
            context,
            prefix="",
            bot=bot,
            force_refresh=cache_cleared,
        )
        sender_info.append(user_text)
        info_blocks.append("\n".join(sender_info))

    return info_blocks


# ============ 命令函数 ============


async def get_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    获取对话、用户和消息的详细信息。
    """
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    # 添加 null 检查
    if not message or not chat or not user:
        return

    info_blocks = await _build_info_blocks(chat, message, user, context, context.bot)
    reply_text = "\n\n".join(info_blocks)

    await send_search_result(
        context,
        chat.id,
        foldable_text_with_markdown_v2(reply_text),
        parse_mode="MarkdownV2",
    )
    await delete_user_command(context, chat.id, message.message_id)


async def clear_and_get_info_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """
    清除用户缓存并重新获取对话、用户和消息的详细信息。

    使用方法: 回复某条消息后发送 /cinfo
    """
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    # 添加 null 检查
    if not message or not chat or not user:
        return

    # 必须回复消息才能使用此命令
    if not message.reply_to_message:
        await send_search_result(
            context,
            chat.id,
            foldable_text_with_markdown_v2("⚠️ 请回复一条消息后使用此命令"),
            parse_mode="MarkdownV2",
        )
        await delete_user_command(context, chat.id, message.message_id)
        return

    reply_msg = message.reply_to_message

    # 确保回复的消息有发送者
    if not reply_msg.from_user:
        await send_search_result(
            context,
            chat.id,
            foldable_text_with_markdown_v2("⚠️ 无法获取该消息的发送者信息"),
            parse_mode="MarkdownV2",
        )
        await delete_user_command(context, chat.id, message.message_id)
        return

    target_user_id = reply_msg.from_user.id

    # 清除该用户的 Redis 缓存
    # ⚠️ 注意：仅清除 Redis 缓存，不清除 MySQL 中的官方数据
    try:
        cache_manager = context.bot_data.get("cache_manager")
        if cache_manager and cache_manager.redis_client:
            cache_key = f"{REDIS_KEY_USER_REG_DATE_PREFIX}{target_user_id}"
            deleted = await cache_manager.redis_client.delete(cache_key)
            logger.info(
                f"用户 {user.id} 清除了用户 {target_user_id} 的 Redis 缓存 (结果: {deleted})"
            )
        else:
            logger.warning("Redis 客户端未初始化,无法清除缓存")
    except Exception as e:
        logger.error(f"清除用户 {target_user_id} 的缓存失败: {e}", exc_info=True)

    # 重新查询信息
    info_blocks = await _build_info_blocks(
        chat, message, user, context, context.bot, cache_cleared=True
    )
    reply_text = "\n\n".join(info_blocks)

    await send_search_result(
        context,
        chat.id,
        foldable_text_with_markdown_v2(reply_text),
        parse_mode="MarkdownV2",
    )
    await delete_user_command(context, chat.id, message.message_id)


# 注册命令
command_factory.register_command(
    "info",
    get_info_command,
    permission=Permission.USER,
    description="获取对话、用户和消息的详细信息",
)

command_factory.register_command(
    "cinfo",
    clear_and_get_info_command,
    permission=Permission.USER,
    description="清除缓存并重新获取用户信息",
)
