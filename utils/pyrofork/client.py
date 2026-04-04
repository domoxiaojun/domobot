"""
客户端生命周期管理模块

负责 Pyrofork 客户端的：
- 初始化（支持用户会话模式 + Bot Token 回退模式）
- 停止
- 全局实例获取

全局状态管理：
- _pyrofork_client: Pyrofork 客户端实例
- _bot_id: 当前 Bot ID（用于 Redis key 隔离）
"""

import logging

from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler

logger = logging.getLogger(__name__)

# 全局 Pyrofork 客户端实例（Pyrofork 保持了 pyrogram 包名）
_pyrofork_client: Client | None = None
_bot_id: int = 0
_logged_in_username: str | None = None
_is_user_mode: bool = False  # True=用户会话模式（可获取 PeerSettings），False=Bot 模式


def get_pyrofork_client() -> Client | None:
    """获取 Pyrofork 客户端实例"""
    return _pyrofork_client


def get_bot_id() -> int:
    """获取当前 Bot ID"""
    return _bot_id


def get_logged_in_username() -> str | None:
    """获取 Pyrofork 登录账号的用户名"""
    return _logged_in_username


def is_user_mode() -> bool:
    """检查 Pyrofork 是否以用户会话模式登录（仅用户模式可获取 PeerSettings）"""
    return _is_user_mode


async def initialize_pyrofork_client(
    redis_client=None,
    bot_token: str | None = None,
    api_id: int | None = None,
    api_hash: str | None = None,
    bot_id: int = 0,
) -> bool:
    """
    初始化 Pyrofork 客户端,支持两种模式:
    1. 用户模式: 从 Redis 恢复会话 (优先, 可获取 PeerSettings)
    2. Bot 模式: 使用 bot_token + api_id/hash (回退, 无法获取 PeerSettings)

    凭证来源优先级: Redis > .env 参数
    若 .env 有凭证但 Redis 无，自动同步到 Redis（管理面板可见）

    Args:
        redis_client: Redis 客户端实例
        bot_token: Bot Token (可选,用于 Bot 模式回退)
        api_id: API ID (可选,来自 .env 或调用方)
        api_hash: API Hash (可选,来自 .env 或调用方)
        bot_id: Bot ID，用于 Redis key 隔离和客户端命名

    Returns:
        bool: 初始化是否成功
    """
    global _pyrofork_client, _bot_id, _logged_in_username, _is_user_mode

    from utils.pyrofork.credentials import (
        get_pyrofork_credentials,
        save_pyrofork_credentials,
    )
    from utils.pyrofork.session import get_session_info

    if bot_id:
        _bot_id = bot_id

    client_name = f"bot_{_bot_id}" if _bot_id else "domoapp_bot"

    # 统一凭证解析: Redis 优先 → .env 回退
    effective_api_id = api_id
    effective_api_hash = api_hash

    if redis_client:
        credentials = await get_pyrofork_credentials(redis_client, bot_id=_bot_id)
        if credentials:
            effective_api_id = int(credentials["api_id"])
            effective_api_hash = credentials["api_hash"]
            logger.info("✅ 从 Redis 加载 API 凭证")
        elif effective_api_id and effective_api_hash:
            # .env 有凭证但 Redis 无 → 自动同步到 Redis（管理面板可见）
            await save_pyrofork_credentials(
                redis_client, int(effective_api_id), effective_api_hash, bot_id=_bot_id
            )
            logger.info("✅ 环境变量 API 凭证已同步到 Redis")

    if not effective_api_id or not effective_api_hash:
        logger.warning(
            "⚠️ 未配置 API_ID/API_HASH（环境变量和 Redis 均无配置）\n"
            "提示: 在 .env 中设置 TELEGRAM_API_ID/TELEGRAM_API_HASH 或通过 /admin 面板配置"
        )
        return False

    # 确保 api_id 为 int
    effective_api_id = int(effective_api_id)

    # 模式 1: 用户会话恢复 (优先)
    if redis_client:
        try:
            session_info = await get_session_info(redis_client, bot_id=_bot_id)
            if session_info:
                session_string = session_info["session_string"]
                phone_number = session_info.get("phone_number", "未知")
                user_id = session_info.get("user_id", "未知")

                logger.info("开始从会话字符串恢复 Pyrofork 客户端 (用户会话模式)...")
                logger.info(f"📱 登录账号: {phone_number} (User ID: {user_id})")

                _pyrofork_client = Client(
                    name=client_name,
                    api_id=effective_api_id,
                    api_hash=effective_api_hash,
                    session_string=session_string,
                    in_memory=True,
                )

                await _pyrofork_client.start()

                # 获取登录账号的 username（优先从 session_info 读取，避免重复 API 调用）
                _logged_in_username = session_info.get("username")
                if not _logged_in_username:
                    try:
                        me = await _pyrofork_client.get_me()
                        _logged_in_username = me.username
                        # 回填 username 到 Redis
                        if _logged_in_username and redis_client:
                            from utils.pyrofork.session import _key_username

                            await redis_client.set(
                                _key_username(_bot_id), _logged_in_username
                            )
                    except Exception as e:
                        logger.warning(f"获取登录账号用户名失败: {e}")

                if _logged_in_username:
                    logger.info(f"📱 登录账号用户名: @{_logged_in_username}")

                logger.info(
                    f"✅ Pyrofork 客户端已使用用户会话登录 "
                    f"(用户模式: {phone_number}, bot_id={_bot_id})"
                )
                logger.info("💡 用户模式可以获取 PeerSettings 获得准确的注册日期")

                # 注册私聊消息监听：记录消息 + 自动检测 PeerSettings
                async def _on_private_message(_client, message):
                    sender = message.from_user
                    if not sender:
                        return

                    sender_info = (
                        f"{sender.id}(@{sender.username})"
                        if sender.username
                        else str(sender.id)
                    )
                    logger.info(
                        f"📩 [小号私聊] 收到来自 {sender_info} 的消息: "
                        f"{(message.text or '<非文本>')[:50]}"
                    )

                    # 自动尝试获取 PeerSettings 注册时间
                    try:
                        from pyrogram import raw

                        peer = await _client.resolve_peer(sender.id)
                        full = await _client.invoke(
                            raw.functions.users.GetFullUser(id=peer)
                        )
                        settings = getattr(full.full_user, "settings", None)
                        reg = (
                            getattr(settings, "registration_month", None)
                            if settings
                            else None
                        )

                        if reg:
                            logger.info(
                                f"✅ [小号私聊] 用户 {sender_info} "
                                f"PeerSettings 注册时间: {reg}"
                            )
                        else:
                            # 诊断：输出关键 flag 帮助理解为何无数据
                            flags = {}
                            if settings:
                                for f_name in [
                                    "report_spam",
                                    "add_contact",
                                    "block_contact",
                                    "need_contacts_exception",
                                ]:
                                    flags[f_name] = getattr(settings, f_name, None)
                            logger.info(
                                f"⚠️ [小号私聊] 用户 {sender_info} "
                                f"PeerSettings 无注册时间 "
                                f"(settings={'有' if settings else '无'}, "
                                f"flags={flags})"
                            )
                    except Exception as e:
                        logger.warning(
                            f"⚠️ [小号私聊] 获取 {sender_info} PeerSettings 失败: {e}"
                        )

                _pyrofork_client.add_handler(
                    MessageHandler(_on_private_message, filters.private)
                )
                logger.info("📩 已注册小号私聊消息监听（诊断用）")

                _is_user_mode = True
                return True
            else:
                logger.debug("Pyrofork 用户未登录，尝试 Bot Token 模式")

        except Exception as e:
            logger.warning(f"用户会话恢复失败: {e}，尝试 Bot Token 模式")
            _pyrofork_client = None

    # 模式 2: Bot Token 登录 (回退)
    if bot_token:
        try:
            logger.debug("尝试使用 Bot Token 初始化 Pyrofork 客户端...")
            _pyrofork_client = Client(
                name=client_name,
                api_id=effective_api_id,
                api_hash=effective_api_hash,
                bot_token=bot_token,
                in_memory=True,
            )
            await _pyrofork_client.start()
            logger.info(
                f"✅ Pyrofork 客户端已使用 Bot Token 登录 "
                f"(Bot 模式, bot_id={_bot_id})"
            )
            logger.warning("⚠️ Bot 模式无法获取 PeerSettings，将使用 ID 推测算法")
            logger.warning("提示: 通过 /admin 面板配置用户会话以获取准确的注册日期")
            return True
        except Exception as e:
            logger.error(f"Bot Token 登录失败: {e}")
            _pyrofork_client = None
            return False

    # 所有模式都失败
    logger.error("❌ 所有 Pyrofork 初始化模式均失败")
    return False


async def stop_pyrofork_client():
    """停止 Pyrofork 客户端"""
    global _pyrofork_client, _logged_in_username, _is_user_mode

    if _pyrofork_client:
        try:
            await _pyrofork_client.stop()
            logger.info("Pyrofork 客户端已停止")
        except Exception as e:
            logger.error(f"停止 Pyrofork 客户端时出错: {e}")
        finally:
            _pyrofork_client = None
            _logged_in_username = None
            _is_user_mode = False
