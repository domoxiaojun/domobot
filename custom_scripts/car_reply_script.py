#!/usr/bin/env python3
"""
自定义脚本：群组关键词自动回复

功能：
- 监控指定群组的消息
- 匹配关键词（发车、上车、有车吗等）
- 自动回复来自 Telegram 频道的消息内容
- 定时更新消息内容以获取最新编辑
"""

import logging
import os
import re
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

# ============================================
# 全局变量（在 load 函数中初始化）
# ============================================
_cached_reply_message = None
_last_fetch_time = None
_pyrofork_client = None
_task_scheduler = None

# ============================================
# 配置（硬编码）
# ============================================
# 监控的群组 ID
MONITORED_GROUP_ID = "-1001161866581"

# 目标消息配置
TARGET_CHANNEL = "Licensesss"
TARGET_MESSAGE_ID = 9542

# 更新间隔（秒）
UPDATE_INTERVAL = 3600  # 1小时

# 消息缓存文件路径
CACHE_FILE = "custom_scripts/car_reply_message.txt"

# 正则表达式模式：匹配 发车、上车、有车吗 等关键词
CAR_PATTERN = re.compile(r"(发车|上车|(?:有.*?车|.*?车有)(?:吗|嘛|么)?)")


def get_script_info():
    """返回脚本元数据"""
    return {
        "name": "群组关键词自动回复",
        "version": "1.0.0",
        "description": f"监控群组 {MONITORED_GROUP_ID}，自动回复关键词消息",
        "author": "Domo",
    }


async def load_message_from_file():
    """
    从文件加载缓存的消息

    Returns:
        bool: 是否成功加载
    """
    global _cached_reply_message

    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                _cached_reply_message = f.read()
            logger.info(
                f"[CarReply] 从缓存文件加载消息，长度: {len(_cached_reply_message)}"
            )
            return True
        else:
            logger.info(f"[CarReply] 缓存文件不存在: {CACHE_FILE}")
    except Exception as e:
        logger.error(f"[CarReply] 读取缓存文件失败: {e}", exc_info=True)
    return False


async def save_message_to_file(message_text):
    """
    保存消息到文件

    Args:
        message_text: 消息文本内容
    """
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)

        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            f.write(message_text)
        logger.info(f"[CarReply] 消息已保存到缓存文件: {CACHE_FILE}")
    except Exception as e:
        logger.error(f"[CarReply] 保存缓存文件失败: {e}", exc_info=True)


async def fetch_target_message():
    """
    从 Telegram 频道获取目标消息

    Returns:
        str: 消息文本，失败返回 None
    """
    global _cached_reply_message, _last_fetch_time

    if not _pyrofork_client:
        logger.error("[CarReply] Pyrofork 客户端未初始化")
        return None

    try:
        logger.info(
            f"[CarReply] 正在从频道 {TARGET_CHANNEL} 获取消息 ID {TARGET_MESSAGE_ID}..."
        )

        message = await _pyrofork_client.get_messages(TARGET_CHANNEL, TARGET_MESSAGE_ID)

        if message and message.text:
            _cached_reply_message = message.text
            _last_fetch_time = datetime.now()

            # 保存到文件
            await save_message_to_file(message.text)

            logger.info(
                f"[CarReply] 成功获取目标消息，长度: {len(message.text)} "
                f"字符，最后更新时间: {_last_fetch_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            return message.text
        else:
            logger.warning("[CarReply] 目标消息为空或无文本内容")
            return None

    except Exception as e:
        logger.error(f"[CarReply] 获取目标消息失败: {e}", exc_info=True)
        return None


async def update_message_cache():
    """定时任务：更新消息缓存"""
    logger.info("[CarReply] 执行定时任务：更新消息缓存")
    await fetch_target_message()


async def car_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    群组消息处理器：检测关键词并自动回复

    Args:
        update: Telegram update 对象
        context: 上下文对象
    """
    message = update.message

    if not message:
        return

    chat_id = str(message.chat.id)

    # 1. 检查群组是否在监听列表
    if chat_id != MONITORED_GROUP_ID:
        return

    # 2. 检查消息文本
    text = message.text or message.caption or ""
    if not text:
        return

    # 3. 正则匹配关键词
    if not CAR_PATTERN.search(text):
        return

    # 4. 检查是否有缓存的回复内容
    if not _cached_reply_message:
        logger.warning(
            f"[CarReply] 检测到关键词但回复消息未缓存，跳过回复。"
            f"用户: {message.from_user.id}, 消息: {text[:50]}"
        )
        return

    # 5. 发送引用回复
    try:
        await message.reply_text(
            text=_cached_reply_message,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        logger.info(
            f"[CarReply] 已回复用户 {message.from_user.id} "
            f"的消息（关键词: {CAR_PATTERN.search(text).group()}）"
        )
    except Exception as e:
        logger.error(f"[CarReply] 发送回复失败: {e}", exc_info=True)


def load(bot_context):
    """
    脚本加载入口函数

    Args:
        bot_context: 字典，包含所有机器人组件
            - application: Telegram Application 实例
            - task_scheduler: 定时任务调度器
            - 其他组件...
    """
    global _pyrofork_client, _task_scheduler

    # 获取必需的组件
    application = bot_context.get("application")
    _task_scheduler = bot_context.get("task_scheduler")

    if not application:
        logger.error("[CarReply] 无法获取 application，脚本加载失败")
        return

    logger.info("[CarReply] 脚本加载开始...")

    # 获取 Pyrofork 客户端
    from utils.pyrofork import get_pyrofork_client

    _pyrofork_client = get_pyrofork_client()

    if not _pyrofork_client:
        logger.error(
            "[CarReply] Pyrofork 客户端未初始化，脚本无法工作。"
            "请确保 Pyrofork 已配置并成功登录。"
        )
        return

    logger.info("[CarReply] Pyrofork 客户端已就绪")

    # 优先从文件加载缓存
    import asyncio

    try:
        # 在同步上下文中运行异步函数
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 如果事件循环正在运行，创建任务
            asyncio.create_task(load_and_fetch_message())
        else:
            # 否则直接运行
            file_loaded = loop.run_until_complete(load_message_from_file())
            if not file_loaded or not _cached_reply_message:
                logger.info("[CarReply] 缓存文件不存在或为空，从 Telegram 获取消息")
                asyncio.create_task(fetch_target_message())
            else:
                logger.info("[CarReply] 已从缓存文件加载消息，跳过立即获取")
    except Exception as e:
        logger.error(f"[CarReply] 加载消息缓存时出错: {e}", exc_info=True)
        # 如果加载失败，尝试立即从 Telegram 获取
        asyncio.create_task(fetch_target_message())

    # 注册定时任务：每小时更新消息
    if _task_scheduler:
        try:
            # 注册自定义任务处理器
            async def car_reply_update_handler(task_id: str, data: dict):
                """处理车队回复消息更新任务"""
                logger.info("[CarReply] 执行定时任务：更新消息缓存")
                await update_message_cache()

                # 重新调度下一次任务（实现周期性效果）
                import time

                next_run = time.time() + UPDATE_INTERVAL
                await _task_scheduler.schedule_task(
                    task_id=task_id,
                    task_type="car_reply_update",
                    execute_at=next_run,
                    data=data,
                )
                logger.info(
                    f"[CarReply] 已调度下次更新任务，"
                    f"执行时间: {UPDATE_INTERVAL // 60} 分钟后"
                )

            _task_scheduler.register_handler(
                "car_reply_update", car_reply_update_handler
            )

            # 调度第一次任务
            import time

            first_run = time.time() + UPDATE_INTERVAL
            import asyncio

            asyncio.create_task(
                _task_scheduler.schedule_task(
                    task_id="car_reply_message_updater",
                    task_type="car_reply_update",
                    execute_at=first_run,
                    data={},
                )
            )

            logger.info(
                f"[CarReply] 已注册定时任务，更新间隔: {UPDATE_INTERVAL} 秒 "
                f"({UPDATE_INTERVAL // 60} 分钟)"
            )
        except Exception as e:
            logger.error(f"[CarReply] 注册定时任务失败: {e}", exc_info=True)
    else:
        logger.warning("[CarReply] task_scheduler 未提供，无法注册定时更新任务")

    # 注册消息处理器
    handler = MessageHandler(
        filters.ChatType.SUPERGROUP  # 仅超级群组
        & (~filters.COMMAND)  # 排除命令
        & (filters.TEXT | filters.CAPTION),  # 文本或标题
        car_reply_handler,
    )
    application.add_handler(handler, group=2)

    logger.info("[CarReply] 已注册消息处理器，group=2")
    logger.info(f"[CarReply] 监控群组: {MONITORED_GROUP_ID}")
    logger.info(f"[CarReply] 目标频道: {TARGET_CHANNEL}")
    logger.info(f"[CarReply] 目标消息 ID: {TARGET_MESSAGE_ID}")
    logger.info(f"[CarReply] 消息缓存文件: {CACHE_FILE}")
    logger.info(f"[CarReply] 匹配模式: {CAR_PATTERN.pattern}")
    logger.info("[CarReply] 脚本加载完成")


async def load_and_fetch_message():
    """辅助函数：加载缓存或获取新消息"""
    file_loaded = await load_message_from_file()
    if not file_loaded or not _cached_reply_message:
        logger.info("[CarReply] 缓存文件不存在或为空，从 Telegram 获取消息")
        await fetch_target_message()
    else:
        logger.info("[CarReply] 已从缓存文件加载消息")
