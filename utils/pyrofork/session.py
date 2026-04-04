"""
会话管理和用户信息缓存模块

用于：
- 保存和获取 Pyrofork 会话字符串
- 获取登录状态
- 缓存完整用户信息到 Redis（支持不同 TTL 策略）

会话 Redis Key 按 bot_id 隔离: pyrofork:{bot_id}:session_string 等
用户注册日期缓存为共享数据，不加 bot_id 前缀。
"""

import json
import logging
from datetime import datetime

from utils.constants import TIME_ONE_DAY

logger = logging.getLogger(__name__)

# 共享数据前缀（不按 bot_id 隔离）
REDIS_KEY_USER_REG_DATE_PREFIX = "user_registration_date:"


def compute_account_age(reg_year: int | None, reg_month: int | None) -> tuple[int, int]:
    """
    计算账号年龄（年, 月）

    Args:
        reg_year: 注册年份（可能为 None）
        reg_month: 注册月份（可能为 None）

    Returns:
        (years, months) 元组，如果输入为 None 则返回 (0, 0)
    """
    if not reg_year or not reg_month:
        return 0, 0
    now = datetime.now()
    years = now.year - reg_year
    months = now.month - reg_month
    if months < 0:
        years -= 1
        months += 12
    return years, months


def _key_session_string(bot_id: int) -> str:
    return f"pyrofork:{bot_id}:session_string"


def _key_phone_number(bot_id: int) -> str:
    return f"pyrofork:{bot_id}:phone_number"


def _key_login_time(bot_id: int) -> str:
    return f"pyrofork:{bot_id}:login_time"


def _key_user_id(bot_id: int) -> str:
    return f"pyrofork:{bot_id}:user_id"


def _key_username(bot_id: int) -> str:
    return f"pyrofork:{bot_id}:username"


def _key_temp_phone_code_hash(bot_id: int, uid: int) -> str:
    return f"pyrofork:{bot_id}:temp_phone_code_hash:{uid}"


async def save_session_string(
    redis_client,
    session_string: str,
    phone_number: str,
    user_id: int = None,
    username: str = None,
    bot_id: int = 0,
) -> bool:
    """
    保存 Pyrofork 会话字符串到 Redis

    Args:
        redis_client: Redis 客户端实例
        session_string: Pyrofork 会话字符串
        phone_number: 登录的手机号
        user_id: 登录用户的 ID (可选)
        username: 登录用户的用户名 (可选)
        bot_id: Bot ID，用于 key 隔离

    Returns:
        bool: 保存是否成功
    """
    try:
        await redis_client.set(_key_session_string(bot_id), session_string)
        await redis_client.set(_key_phone_number(bot_id), phone_number)
        await redis_client.set(_key_login_time(bot_id), datetime.now().isoformat())
        if user_id:
            await redis_client.set(_key_user_id(bot_id), str(user_id))
        if username:
            await redis_client.set(_key_username(bot_id), username)
        logger.info(
            f"Pyrofork 会话已保存到 Redis "
            f"(手机号: {phone_number[:3]}****{phone_number[-4:]}, bot_id={bot_id})"
        )
        return True
    except Exception as e:
        logger.error(f"保存 Pyrofork 会话失败: {e}")
        return False


async def get_session_info(redis_client, bot_id: int = 0) -> dict | None:
    """
    从 Redis 获取 Pyrofork 会话信息

    Args:
        redis_client: Redis 客户端实例
        bot_id: Bot ID，用于 key 隔离

    Returns:
        包含会话信息的字典，如果未登录则返回 None
    """
    try:
        session_string = await redis_client.get(_key_session_string(bot_id))
        phone_number = await redis_client.get(_key_phone_number(bot_id))
        login_time_str = await redis_client.get(_key_login_time(bot_id))
        user_id_str = await redis_client.get(_key_user_id(bot_id))
        username_raw = await redis_client.get(_key_username(bot_id))

        if session_string:
            return {
                "session_string": (
                    session_string.decode()
                    if isinstance(session_string, bytes)
                    else session_string
                ),
                "phone_number": (
                    phone_number.decode()
                    if isinstance(phone_number, bytes)
                    else phone_number if phone_number else "未知"
                ),
                "login_time": (
                    datetime.fromisoformat(
                        login_time_str.decode()
                        if isinstance(login_time_str, bytes)
                        else login_time_str
                    )
                    if login_time_str
                    else None
                ),
                "user_id": (
                    int(
                        user_id_str.decode()
                        if isinstance(user_id_str, bytes)
                        else user_id_str
                    )
                    if user_id_str
                    else None
                ),
                "username": (
                    (
                        username_raw.decode()
                        if isinstance(username_raw, bytes)
                        else username_raw
                    )
                    if username_raw
                    else None
                ),
            }
        return None
    except Exception as e:
        logger.error(f"读取 Pyrofork 会话信息失败: {e}")
        return None


async def get_pyrofork_login_status(
    redis_client, pyrofork_client=None, bot_id: int = 0
) -> dict:
    """
    获取 Pyrofork 登录状态

    Args:
        redis_client: Redis 客户端实例
        pyrofork_client: Pyrofork Client 实例（可选）
        bot_id: Bot ID，用于 key 隔离

    Returns:
        包含登录状态的字典
    """
    from utils.pyrofork.credentials import get_pyrofork_credentials

    credentials = await get_pyrofork_credentials(redis_client, bot_id=bot_id)
    session_info = await get_session_info(redis_client, bot_id=bot_id)

    return {
        "api_configured": credentials is not None,
        "is_logged_in": session_info is not None
        and pyrofork_client is not None
        and pyrofork_client.is_connected,
        "phone_number": session_info["phone_number"] if session_info else None,
        "login_time": session_info["login_time"] if session_info else None,
    }


async def save_user_info_to_cache(redis_client, user_id: int, user_info: dict) -> bool:
    """
    保存完整用户信息到 Redis（共享数据，不按 bot_id 隔离）

    Args:
        redis_client: Redis 客户端
        user_id: 用户 ID
        user_info: 完整用户信息字典

    Returns:
        bool: 是否保存成功
    """
    try:
        cache_data = {
            "user_id": user_id,
            "full_name": user_info.get("full_name"),
            "username": user_info.get("username"),
            "is_premium": user_info.get("is_premium"),
            "dc_id": user_info.get("dc_id"),
            "dc_location": user_info.get("dc_location"),
            "registration_year": user_info.get("registration_year"),
            "registration_month": user_info.get("registration_month"),
            "registration_source": user_info.get("registration_source"),
            "phone_country": user_info.get("phone_country"),
            "name_change_date": user_info.get("name_change_date"),
            "photo_change_date": user_info.get("photo_change_date"),
            "queried_at": datetime.now().isoformat(),
        }

        key = f"{REDIS_KEY_USER_REG_DATE_PREFIX}{user_id}"

        source = user_info.get("registration_source")
        if source == "peersettings":
            await redis_client.set(key, json.dumps(cache_data))
            logger.info(
                f"✅ 官方数据已永久缓存: 用户 {user_id} "
                f"(注册时间: {user_info.get('registration_year')}年"
                f"{user_info.get('registration_month')}月)"
            )
        elif source == "id_estimation":
            await redis_client.setex(key, TIME_ONE_DAY, json.dumps(cache_data))
            logger.info(
                f"✅ 估算数据已缓存 24 小时: 用户 {user_id} "
                f"(注册时间: {user_info.get('registration_year')}年"
                f"{user_info.get('registration_month')}月)"
            )
        else:
            await redis_client.setex(key, TIME_ONE_DAY, json.dumps(cache_data))
            logger.info(
                f"✅ 数据已缓存 24 小时: 用户 {user_id} (来源: {source or '未知'})"
            )
        return True

    except Exception as e:
        logger.error(f"保存用户 {user_id} 的缓存失败: {e}")
        return False


async def get_cached_user_info(redis_client, user_id: int) -> dict | None:
    """
    从 Redis 获取缓存的完整用户信息（共享数据）

    Args:
        redis_client: Redis 客户端
        user_id: 用户 ID

    Returns:
        包含完整用户信息的字典，如果未缓存则返回 None
    """
    try:
        key = f"{REDIS_KEY_USER_REG_DATE_PREFIX}{user_id}"
        cached_data = await redis_client.get(key)

        if not cached_data:
            return None

        if isinstance(cached_data, bytes):
            cached_data = cached_data.decode()

        data = json.loads(cached_data)

        # 动态计算账号年龄（避免永久缓存中的 account_age 过期）
        reg_year = data.get("registration_year")
        reg_month = data.get("registration_month")
        age_years, age_months = compute_account_age(reg_year, reg_month)

        return {
            "user_id": data["user_id"],
            "full_name": data.get("full_name"),
            "username": data.get("username"),
            "is_premium": data.get("is_premium"),
            "dc_id": data.get("dc_id"),
            "dc_location": data.get("dc_location"),
            "registration_year": reg_year,
            "registration_month": reg_month,
            "registration_source": data.get("registration_source"),
            "phone_country": data.get("phone_country"),
            "name_change_date": data.get("name_change_date"),
            "photo_change_date": data.get("photo_change_date"),
            "account_age_years": age_years,
            "account_age_months": age_months,
            "queried_at": (
                datetime.fromisoformat(data["queried_at"])
                if data.get("queried_at")
                else None
            ),
        }

    except Exception as e:
        logger.error(f"读取用户 {user_id} 的缓存失败: {e}")
        return None
