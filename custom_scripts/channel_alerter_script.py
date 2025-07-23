#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
from telegram.ext import ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

# 使用主程序的日志记录器
logger = logging.getLogger(__name__)

# 回复消息模板
ALERT_TEMPLATE = """🚗 <b>发车啦！请仔细核对车主信息</b> 🚙

<b>唯一车主：</b> @{owner_username} 🆔 <code>{owner_id}</code>
<b>点击核对车主身份：</b> {user_link}

🚨 <b>安全提醒：</b>
1.  <b>主动私聊你的都是骗子！</b> 请务必通过上方链接联系车主。
2.  上车前请确认好价格、时长和使用规则。
3.  祝您拼车愉快！"""

# 全局变量，在 load 函数中初始化
user_cache_manager = None
alerter_config = {}

def extract_usernames_from_message(message):
    """
    从消息中提取@用户名，使用混合方案确保最大可靠性
    返回: List[str] - 用户名列表（不含@符号）
    """
    usernames = []
    text = message.text or message.caption or ""
    
    if not text:
        return usernames
    
    # 方案1：优先使用 Telegram entities（最准确）
    if message.entities:
        logger.debug(f"[Alerter] 发现 {len(message.entities)} 个消息实体")
        for i, entity in enumerate(message.entities):
            logger.debug(f"[Alerter] 实体 {i}: type={entity.type}, offset={entity.offset}, length={entity.length}")
            if entity.type == "mention":  # @username 类型
                start = entity.offset
                end = start + entity.length
                mention_text = text[start:end]
                username = mention_text[1:]  # 去掉 @ 符号
                logger.debug(f"[Alerter] 从entities提取到用户名: {username}")
                if username:  # 确保不为空
                    usernames.append(username)
            elif entity.type == "text_mention":  # 无用户名用户的@提及
                logger.debug(f"[Alerter] 发现text_mention，用户: {entity.user.first_name if entity.user else 'Unknown'}")
                # 这种情况下可以获取用户ID但没有用户名
                # 可以选择跳过或特殊处理
                continue
    else:
        logger.debug("[Alerter] 消息中没有entities")
    
    # 方案2：如果 entities 没找到任何提及，使用正则作为备份
    if not usernames:
        logger.debug("[Alerter] entities未找到用户名，使用正则表达式备份方案")
        usernames = re.findall(r'@\w{5,}', text)
        # 去掉@符号
        usernames = [username[1:] for username in usernames]
        logger.debug(f"[Alerter] 正则表达式找到的用户名: {usernames}")
    else:
        logger.debug(f"[Alerter] entities成功找到用户名: {usernames}")
    
    return usernames

def resilient_handler(func):
    """让Handler更加resilient的装饰器"""
    async def wrapper(update, context):
        try:
            return await func(update, context)
        except Exception as e:
            logger.error(f"[Alerter] Handler异常但继续运行: {e}", exc_info=True)
            # 发送错误通知给超级管理员
            try:
                config = context.bot_data.get('config') or context.bot_data.get('application', {}).get('config')
                if config and hasattr(config, 'super_admin_id') and config.super_admin_id:
                    await context.bot.send_message(
                        chat_id=config.super_admin_id,
                        text=f"⚠️ Alerter脚本异常: {str(e)[:100]}..."
                    )
            except:
                pass
    return wrapper

@resilient_handler
async def group_message_alerter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理群组消息并回复的处理器。
    """
    # 全局调试日志 - 记录所有进入此函数的消息
    logger.debug(f"[Alerter] === 函数被调用 ===")
    
    message = update.message

    # 确保消息和聊天存在
    if not message or not message.chat:
        logger.debug(f"[Alerter] 消息或聊天为空，返回")
        return

    chat_id_str = str(message.chat.id)
    chat_type = message.chat.type
    chat_title = message.chat.title or "未知群组"
    
    # 添加调试日志：记录所有收到的群组消息
    logger.debug(f"[Alerter] 收到消息 - 群组ID: {chat_id_str}, 类型: {chat_type}, 标题: {chat_title}")
    logger.debug(f"[Alerter] 当前监听配置: {alerter_config}")

    # 1. 检查当前群组是否在我们的监听列表里
    if chat_id_str not in alerter_config:
        logger.debug(f"[Alerter] 群组 {chat_id_str} 不在监听列表中，跳过处理")
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
        logger.info(f"[Alerter] 匹配到授权用户: @{sender.username}")
        is_authorized = True
    elif sender_chat and sender_chat.username and sender_chat.username.lower() == auth_user_lower:
        logger.info(f"[Alerter] 匹配到授权频道: @{sender_chat.username}")
        is_authorized = True

    if not is_authorized:
        return

    # 4. 检查消息内容是否 @ 了其他用户
    usernames = extract_usernames_from_message(message)
    logger.debug(f"[Alerter] 找到的@用户名: {usernames}")
    
    if not usernames:
        logger.debug("[Alerter] 消息中未找到@提及，跳过。")
        return

    # 5. 获取第一个被@的用户，并从缓存中查询其ID
    mentioned_username = usernames[0]
    logger.info(f"[Alerter] 检测到 @{authorized_username} 在群组 {chat_id_str} 中提及了 @{mentioned_username}")

    real_user_id = None
    if user_cache_manager:
        # 使用 .get_user_by_username()
        cached_user = user_cache_manager.get_user_by_username(mentioned_username)
        if cached_user:
            real_user_id = cached_user.get('user_id')

    # 6. 构建回复消息
    if real_user_id:
        logger.info(f"[Alerter] 从缓存中找到 @{mentioned_username} 的ID: {real_user_id}")
        user_link = f"tg://user?id={real_user_id}"
    else:
        logger.warning(f"[Alerter] 无法在缓存中找到 @{mentioned_username} 的ID，将使用用户名链接。")
        user_link = f"https://t.me/{mentioned_username}"

    reply_text = ALERT_TEMPLATE.format(
        owner_username=mentioned_username,
        owner_id=real_user_id if real_user_id else "未知ID",
        user_link=user_link
    )

    # 7. 发送回复
    try:
        await message.reply_text(
            text=reply_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            quote=True
        )
        logger.info(f"[Alerter] 已成功在群组 {chat_id_str} 中为 @{authorized_username} 的消息发送提醒。")
    except Exception as e:
        logger.error(f"[Alerter] 在群组 {chat_id_str} 回复提醒消息失败: {e}", exc_info=True)


def load(bot_context):
    """
    脚本加载入口函数。
    """
    global user_cache_manager, alerter_config

    application = bot_context.get('application')
    config = bot_context.get('config')

    # 检查是否获取到核心组件
    if not application or not config:
        logger.error("[Alerter] 无法从 bot_context 中获取 application 或 config 实例。")
        return

    # 从 bot_context 获取 UserCacheManager
    user_cache_manager = bot_context.get('user_cache_manager')
    if not user_cache_manager:
        logger.error("[Alerter] 无法从 bot_context 中获取 user_cache_manager 实例。")
        return

    # 从配置中获取提醒器配置
    # 注意：JSON的键是字符串，所以我们需要将TARGET_GROUP_ID转为字符串来匹配
    alerter_config = {str(k): v for k, v in config.alerter_config.items()}

    if not alerter_config:
        logger.debug("自定义脚本 [Alerter] 未在 .env 中找到 ALERTER_CONFIG 配置，脚本将不会激活。")
        return

    # 监听文本和图片说明消息（去掉过于严格的命令过滤）
    handler = MessageHandler(
        filters.TEXT | filters.CAPTION,
        group_message_alerter
    )
    # 使用高优先级确保在用户缓存处理器之前处理
    application.add_handler(handler, group=-1)
    
    logger.info(f"自定义脚本 [Alerter] 加载成功，监听 {len(alerter_config)} 个群组。")
    logger.info(f"[Alerter] 处理器过滤器: TEXT | CAPTION，优先级: -1")
    logger.info(f"[Alerter] 监听的群组列表: {list(alerter_config.keys())}")
