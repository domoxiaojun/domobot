#!/usr/bin/env python3
"""
自定义脚本：特定用户消息提醒器 (合租/拼车/共享群优化版)
功能：
- 通过 .env 文件配置，可同时监听多个群组。
- 当在指定群组中，由指定的用户（或频道身份）发送的消息包含 @其他用户 时，
  自动在下方回复一条可配置的安全提醒。
"""

import logging
import re

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, MessageHandler, filters


# 使用主程序的日志记录器
logger = logging.getLogger(__name__)

# 回复消息模板
ALERT_TEMPLATE = """🚗 <b>发车啦！请仔细核对车主信息</b> 🚙

<b>唯一车主：</b> @{owner_username} 🆔 <code>{owner_id}</code>
<b>核对链接：</b><a href='{user_link}'>✅ 点击这里，核对车主身份</a>

🚨 <b>安全提醒：</b>
1.  <b>主动私聊你的都是骗子！</b> 请务必通过上方链接联系车主。
2.  上车前请确认好价格、时长和使用规则。
3.  祝您拼车愉快！"""

# 全局变量，在 load 函数中初始化
user_cache_manager = None
alerter_config = {}


def get_script_info():
    """
    返回一个包含脚本信息的字典。
    """
    info = {
        "name": "Digital Immigrants丨Want Want Channel",
        "version": "1.0.0",
        "description": "自动回复车主用户信息！",
        "author": "Domo",
    }
    return info


async def group_message_alerter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理群组消息并回复的处理器。
    """
    logger.debug(f"[Alerter] 处理器被调用，更新ID: {update.update_id}")

    message = update.message

    # 确保消息和聊天存在
    if not message or not message.chat:
        logger.debug("[Alerter] 没有消息或聊天，忽略")
        return

    chat_id_str = str(message.chat.id)
    logger.debug(f"[Alerter] 处理群组 {chat_id_str} 的消息")

    # 1. 检查当前群组是否在我们的监听列表里
    if chat_id_str not in alerter_config:
        return

    # 2. 从配置中获取此群组对应的授权用户名
    authorized_username = alerter_config[chat_id_str]
    logger.debug(f"[Alerter] 群组 {chat_id_str} 命中监听规则，目标用户: @{authorized_username}")

    # 3. 检查消息发送者是否为指定的频道或用户
    sender = message.from_user
    sender_chat = message.sender_chat
    is_authorized = False

    # 使用 .lower() 进行不区分大小写的比较
    auth_user_lower = authorized_username.lower()

    if sender and sender.username and sender.username.lower() == auth_user_lower:
        logger.debug(f"[Alerter] 匹配到授权用户: @{sender.username}")
        is_authorized = True
    elif sender_chat and sender_chat.username and sender_chat.username.lower() == auth_user_lower:
        logger.debug(f"[Alerter] 匹配到授权频道: @{sender_chat.username}")
        is_authorized = True

    if not is_authorized:
        return

    # 4. 检查消息内容是否 @ 了其他用户
    text_to_search = message.text or message.caption or ""
    if not text_to_search:
        return

    # 正则表达式查找 @username
    usernames = re.findall(r"@([a-zA-Z_]\w{0,31})(?=\s|$|[^\w])", text_to_search)
    if not usernames:
        logger.debug("[Alerter] 消息中未找到@提及，跳过。")
        return

    # 5. 获取第一个被@的用户，并从缓存中查询其ID
    mentioned_username = usernames[0]
    logger.info(f"[Alerter] 检测到 @{authorized_username} 在群组 {chat_id_str} 中提及了 @{mentioned_username}")

    real_user_id = None
    if user_cache_manager:
        # 使用 .get_user_by_username()
        cached_user = await user_cache_manager.get_user_by_username(mentioned_username)
        if cached_user:
            real_user_id = cached_user.get("user_id")

    # 6. 构建回复消息
    if real_user_id:
        logger.info(f"[Alerter] 从缓存中找到 @{mentioned_username} 的ID: {real_user_id}")
        user_link = f"tg://user?id={real_user_id}"
    else:
        logger.warning(f"[Alerter] 无法在缓存中找到 @{mentioned_username} 的ID，将使用用户名链接。")
        user_link = f"https://t.me/{mentioned_username}"

    reply_text = ALERT_TEMPLATE.format(
        owner_username=mentioned_username, owner_id=real_user_id if real_user_id else "未知ID", user_link=user_link
    )

    # 7. 发送回复
    try:
        await message.reply_text(text=reply_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        logger.info(f"[Alerter] 已成功在群组 {chat_id_str} 中为 @{authorized_username} 的消息发送提醒。")
    except Exception as e:
        logger.error(f"[Alerter] 在群组 {chat_id_str} 回复提醒消息失败: {e}", exc_info=True)


def load(bot_context):
    """
    脚本加载入口函数。
    """
    global user_cache_manager, alerter_config

    application = bot_context.get("application")
    config = bot_context.get("config")

    # 检查是否获取到核心组件
    if not application or not config:
        logger.error("[Alerter] 无法从 bot_context 中获取 application 或 config 实例。")
        return

    # 从 bot_context 获取 UserCacheManager
    user_cache_manager = bot_context.get("user_cache_manager")
    if not user_cache_manager:
        logger.error("[Alerter] 无法从 bot_context 中获取 user_cache_manager 实例。")
        return

    # 从配置中获取提醒器配置
    # 注意：JSON的键是字符串，所以我们需要将TARGET_GROUP_ID转为字符串来匹配
    alerter_config = {str(k): v for k, v in config.alerter_config.items()}

    if not alerter_config:
        logger.info("自定义脚本 [Alerter] 未在 .env 中找到 ALERTER_CONFIG 配置，脚本将不会激活。")
        return

    # 监听所有包含文本或标题的非命令超级群组消息
    # 使用 group=2 确保在用户缓存处理器之后执行
    handler = MessageHandler(
        filters.ChatType.SUPERGROUP & (~filters.COMMAND) & (filters.TEXT | filters.CAPTION), group_message_alerter
    )
    application.add_handler(handler, group=2)

    logger.info(f"自定义脚本 [Alerter] 加载成功，监听 {len(alerter_config)} 个群组。")
