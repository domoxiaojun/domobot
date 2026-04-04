"""
登录流程管理模块

负责 Pyrofork 用户登录流程：
- 手机号登录（发送验证码）
- 验证码验证（支持 2FA 双重验证）
- 登出用户会话

全局状态管理：
- _temp_login_clients: 临时登录客户端字典（支持多用户并发）
- _temp_login_timestamps: 临时登录时间戳
"""

import logging
from datetime import datetime

from pyrogram import Client
from pyrogram.errors import (
    PhoneNumberInvalid,
    PhoneCodeInvalid,
    PhoneCodeExpired,
    SessionPasswordNeeded,
)

logger = logging.getLogger(__name__)

# 临时登录 Client 管理（支持多用户并发登录）
_temp_login_clients: dict[int, Client] = {}  # {user_id: Client}
_temp_login_timestamps: dict[int, datetime] = {}  # {user_id: 创建时间}


async def _finalize_login(
    client: Client,
    phone_number: str,
    user_id: int,
    redis_client,
    temp_key: str,
    bot_id: int,
    *,
    via_2fa: bool = False,
) -> dict:
    """登录成功后的收尾：导出会话、保存、重新初始化全局客户端"""
    from utils.pyrofork.client import initialize_pyrofork_client
    from utils.pyrofork.session import save_session_string

    session_string = await client.export_session_string()
    me = await client.get_me()
    logged_user_id = me.id
    logged_username = me.username

    await save_session_string(
        redis_client,
        session_string,
        phone_number,
        logged_user_id,
        username=logged_username,
        bot_id=bot_id,
    )

    await redis_client.delete(temp_key)

    del _temp_login_clients[user_id]
    del _temp_login_timestamps[user_id]

    # 重新初始化全局客户端
    await initialize_pyrofork_client(redis_client, bot_id=bot_id)

    suffix = "（2FA）" if via_2fa else ""
    logger.info(
        f"用户 {user_id} 手机号 "
        f"{phone_number[:3]}****{phone_number[-4:]} 登录成功{suffix}"
    )

    return {
        "success": True,
        "requires_password": False,
        "message": "登录成功！",
    }


async def start_phone_login(
    phone_number: str, user_id: int, redis_client, bot_id: int = 0
) -> dict:
    """
    开始手机号登录流程，发送验证码

    Args:
        phone_number: 国际格式手机号（如 +8613812341234）
        user_id: 发起登录的用户 ID
        redis_client: Redis 客户端实例
        bot_id: Bot ID，用于 Redis key 隔离

    Returns:
        包含结果的字典
    """
    global _temp_login_clients, _temp_login_timestamps

    from utils.pyrofork.credentials import get_pyrofork_credentials
    from utils.pyrofork.session import _key_temp_phone_code_hash

    if not redis_client:
        return {"success": False, "message": "Redis 客户端未初始化"}

    try:
        credentials = await get_pyrofork_credentials(redis_client, bot_id=bot_id)
        if not credentials:
            return {
                "success": False,
                "message": "API 凭证未配置，请先配置 API ID 和 API Hash",
            }

        api_id = credentials["api_id"]
        api_hash = credentials["api_hash"]

        logger.info(
            f"用户 {user_id} 开始为手机号 "
            f"{phone_number[:3]}****{phone_number[-4:]} 发送验证码..."
        )

        # 如果该用户已有临时 Client，先清理
        if user_id in _temp_login_clients:
            old_client = _temp_login_clients[user_id]
            if old_client.is_connected:
                await old_client.disconnect()
            del _temp_login_clients[user_id]
            del _temp_login_timestamps[user_id]
            logger.debug(f"清理用户 {user_id} 的旧登录会话")

        # 创建临时客户端用于登录流程
        client_name = (
            f"bot_{bot_id}_login_{user_id}"
            if bot_id
            else f"domoapp_bot_login_{user_id}"
        )
        temp_client = Client(
            name=client_name,
            api_id=api_id,
            api_hash=api_hash,
            phone_number=phone_number,
            in_memory=True,
        )

        await temp_client.connect()

        # 发送验证码
        sent_code = await temp_client.send_code(phone_number)

        # 保存临时 Client 和时间戳
        _temp_login_clients[user_id] = temp_client
        _temp_login_timestamps[user_id] = datetime.now()

        # 保存 phone_code_hash 到 Redis（5分钟过期）
        await redis_client.setex(
            _key_temp_phone_code_hash(bot_id, user_id),
            300,
            sent_code.phone_code_hash,
        )

        logger.info(
            f"验证码已发送到 {phone_number[:3]}****{phone_number[-4:]}，等待用户输入"
        )

        return {
            "success": True,
            "phone_code_hash": sent_code.phone_code_hash,
            "message": f"验证码已发送到 {phone_number[:3]}****{phone_number[-4:]}，请查收",
        }

    except PhoneNumberInvalid:
        return {
            "success": False,
            "message": "无效的手机号格式，请使用国际格式（如 +8613812341234）",
        }
    except Exception as e:
        logger.error(f"发送验证码失败: {e}", exc_info=True)
        if user_id in _temp_login_clients:
            try:
                await _temp_login_clients[user_id].disconnect()
            except Exception:
                pass
            del _temp_login_clients[user_id]
            del _temp_login_timestamps[user_id]
        return {"success": False, "message": f"发送验证码失败: {str(e)}"}


async def complete_phone_login(
    phone_number: str,
    phone_code: str,
    user_id: int,
    redis_client,
    password: str | None = None,
    bot_id: int = 0,
) -> dict:
    """
    完成手机号登录，提交验证码（和可选的 2FA 密码）

    Args:
        phone_number: 国际格式手机号
        phone_code: 收到的验证码
        user_id: 发起登录的用户 ID
        redis_client: Redis 客户端实例
        password: 可选的双重验证密码
        bot_id: Bot ID，用于 Redis key 隔离

    Returns:
        包含结果的字典
    """
    global _temp_login_clients, _temp_login_timestamps

    from utils.pyrofork.session import _key_temp_phone_code_hash

    if not redis_client:
        return {"success": False, "message": "Redis 客户端未初始化"}

    try:
        if user_id not in _temp_login_clients:
            return {"success": False, "message": "登录会话已过期，请重新发送验证码"}

        client = _temp_login_clients[user_id]

        if not client.is_connected:
            return {"success": False, "message": "登录会话已断开，请重新发送验证码"}

        temp_key = _key_temp_phone_code_hash(bot_id, user_id)
        phone_code_hash_bytes = await redis_client.get(temp_key)
        if not phone_code_hash_bytes:
            await client.disconnect()
            del _temp_login_clients[user_id]
            del _temp_login_timestamps[user_id]
            return {"success": False, "message": "验证码已过期，请重新发送"}

        phone_code_hash = (
            phone_code_hash_bytes.decode()
            if isinstance(phone_code_hash_bytes, bytes)
            else phone_code_hash_bytes
        )

        logger.info(f"用户 {user_id} 正在验证验证码...")

        try:
            await client.sign_in(phone_number, phone_code_hash, phone_code)
            return await _finalize_login(
                client, phone_number, user_id, redis_client, temp_key, bot_id
            )

        except SessionPasswordNeeded:
            if password:
                try:
                    await client.check_password(password)
                    return await _finalize_login(
                        client,
                        phone_number,
                        user_id,
                        redis_client,
                        temp_key,
                        bot_id,
                        via_2fa=True,
                    )
                except Exception as e:
                    logger.error(f"双重验证密码错误: {e}")
                    return {
                        "success": False,
                        "requires_password": True,
                        "message": "双重验证密码错误，请重试",
                    }
            else:
                return {
                    "success": False,
                    "requires_password": True,
                    "message": "此账号启用了双重验证，请输入密码",
                }

        except PhoneCodeInvalid:
            logger.warning(f"用户 {user_id} 验证码错误")
            return {
                "success": False,
                "requires_password": False,
                "message": "验证码错误，请重试",
            }

        except PhoneCodeExpired:
            logger.warning(f"用户 {user_id} 验证码已过期")
            await client.disconnect()
            del _temp_login_clients[user_id]
            del _temp_login_timestamps[user_id]
            await redis_client.delete(temp_key)
            return {
                "success": False,
                "requires_password": False,
                "message": "验证码已过期，请重新发送",
            }

    except Exception as e:
        logger.error(f"登录失败: {e}", exc_info=True)
        if user_id in _temp_login_clients:
            try:
                await _temp_login_clients[user_id].disconnect()
            except Exception:
                pass
            del _temp_login_clients[user_id]
            del _temp_login_timestamps[user_id]
        return {"success": False, "message": f"登录失败: {str(e)}"}


async def logout_pyrofork_user(redis_client, bot_id: int = 0) -> bool:
    """
    登出 Pyrofork 用户会话

    Args:
        redis_client: Redis 客户端实例
        bot_id: Bot ID，用于 Redis key 隔离

    Returns:
        bool: 登出是否成功
    """
    from utils.pyrofork.client import stop_pyrofork_client
    from utils.pyrofork.session import (
        _key_session_string,
        _key_phone_number,
        _key_login_time,
        _key_user_id,
        _key_username,
    )

    if not redis_client:
        logger.error("Redis 客户端未初始化")
        return False

    try:
        await stop_pyrofork_client()

        # 清除 Redis 中的会话信息
        await redis_client.delete(
            _key_session_string(bot_id),
            _key_phone_number(bot_id),
            _key_login_time(bot_id),
            _key_user_id(bot_id),
            _key_username(bot_id),
        )

        logger.info(f"Pyrofork 会话已清除 (bot_id={bot_id})")
        return True

    except Exception as e:
        logger.error(f"登出失败: {e}", exc_info=True)
        return False
