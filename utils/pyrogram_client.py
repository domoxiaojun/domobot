"""
Pyrogram 客户端管理器

用于获取 Bot API 无法提供的高级用户信息，如：
- 用户注册日期（通过 @regdate_clone_bot）
- 账号年龄
- 数据中心（DC）位置
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict
from pyrogram import Client
from pyrogram.errors import (
    SessionPasswordNeeded,
    PhoneCodeInvalid,
    PhoneCodeExpired,
    PhoneNumberInvalid,
)

logger = logging.getLogger(__name__)

# 数据中心位置映射
DC_LOCATIONS = {
    1: "MIA (Miami, Florida, US)",
    2: "AMS (Amsterdam, Netherlands, NL)",
    3: "MIA (Miami, Florida, US)",
    4: "AMS (Amsterdam, Netherlands, NL)",
    5: "SIN (Singapore, SG)",
}

# 全局 Pyrogram 客户端实例
_pyrogram_client: Optional[Client] = None
_redis_client = None

# 临时登录 Client 管理（支持多用户并发登录）
_temp_login_clients: Dict[int, Client] = {}  # {user_id: Client}
_temp_login_timestamps: Dict[int, datetime] = {}  # {user_id: 创建时间}

# Redis Key 前缀
REDIS_KEY_API_ID = "pyrogram:api_id"
REDIS_KEY_API_HASH = "pyrogram:api_hash"
REDIS_KEY_SESSION_STRING = "pyrogram:session_string"
REDIS_KEY_PHONE_NUMBER = "pyrogram:phone_number"
REDIS_KEY_LOGIN_TIME = "pyrogram:login_time"
REDIS_KEY_TEMP_PHONE_CODE_HASH = "pyrogram:temp_phone_code_hash"
REDIS_KEY_USER_REG_DATE_PREFIX = "user_registration_date:"  # 用户注册日期缓存前缀


async def save_pyrogram_credentials(redis_client, api_id: int, api_hash: str) -> bool:
    """
    保存 Pyrogram API 凭证到 Redis。

    Args:
        redis_client: Redis 客户端实例
        api_id: Telegram API ID
        api_hash: Telegram API Hash

    Returns:
        bool: 保存是否成功
    """
    try:
        await redis_client.set(REDIS_KEY_API_ID, str(api_id))
        await redis_client.set(REDIS_KEY_API_HASH, api_hash)
        logger.info("Pyrogram API 凭证已保存到 Redis")
        return True
    except Exception as e:
        logger.error(f"保存 Pyrogram API 凭证失败: {e}")
        return False


async def get_pyrogram_credentials(redis_client) -> Optional[Dict[str, any]]:
    """
    从 Redis 获取 Pyrogram API 凭证。

    Args:
        redis_client: Redis 客户端实例

    Returns:
        包含 api_id 和 api_hash 的字典，如果未配置则返回 None
    """
    try:
        api_id_str = await redis_client.get(REDIS_KEY_API_ID)
        api_hash = await redis_client.get(REDIS_KEY_API_HASH)

        if api_id_str and api_hash:
            return {
                "api_id": int(
                    api_id_str.decode() if isinstance(api_id_str, bytes) else api_id_str
                ),
                "api_hash": (
                    api_hash.decode() if isinstance(api_hash, bytes) else api_hash
                ),
            }
        return None
    except Exception as e:
        logger.error(f"读取 Pyrogram API 凭证失败: {e}")
        return None


async def save_session_string(
    redis_client, session_string: str, phone_number: str
) -> bool:
    """
    保存 Pyrogram 会话字符串到 Redis。

    Args:
        redis_client: Redis 客户端实例
        session_string: Pyrogram 会话字符串
        phone_number: 登录的手机号

    Returns:
        bool: 保存是否成功
    """
    try:
        await redis_client.set(REDIS_KEY_SESSION_STRING, session_string)
        await redis_client.set(REDIS_KEY_PHONE_NUMBER, phone_number)
        await redis_client.set(REDIS_KEY_LOGIN_TIME, datetime.now().isoformat())
        logger.info(
            f"Pyrogram 会话已保存到 Redis（手机号: {phone_number[:3]}****{phone_number[-4:]}）"
        )
        return True
    except Exception as e:
        logger.error(f"保存 Pyrogram 会话失败: {e}")
        return False


async def get_session_info(redis_client) -> Optional[Dict]:
    """
    从 Redis 获取 Pyrogram 会话信息。

    Args:
        redis_client: Redis 客户端实例

    Returns:
        包含会话信息的字典，如果未登录则返回 None
    """
    try:
        session_string = await redis_client.get(REDIS_KEY_SESSION_STRING)
        phone_number = await redis_client.get(REDIS_KEY_PHONE_NUMBER)
        login_time_str = await redis_client.get(REDIS_KEY_LOGIN_TIME)

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
            }
        return None
    except Exception as e:
        logger.error(f"读取 Pyrogram 会话信息失败: {e}")
        return None


async def get_pyrogram_login_status(redis_client) -> Dict:
    """
    获取 Pyrogram 登录状态。

    Args:
        redis_client: Redis 客户端实例

    Returns:
        包含登录状态的字典
    """
    credentials = await get_pyrogram_credentials(redis_client)
    session_info = await get_session_info(redis_client)

    return {
        "api_configured": credentials is not None,
        "is_logged_in": session_info is not None
        and _pyrogram_client is not None
        and _pyrogram_client.is_connected,
        "phone_number": session_info["phone_number"] if session_info else None,
        "login_time": session_info["login_time"] if session_info else None,
    }


async def save_user_info_to_cache(redis_client, user_id: int, user_info: Dict) -> bool:
    """
    保存完整用户信息到 Redis（永久存储）。

    Args:
        redis_client: Redis 客户端
        user_id: 用户 ID
        user_info: 完整用户信息字典，包含:
            - full_name: 全名
            - username: 用户名
            - is_premium: Premium 状态
            - dc_id: 数据中心 ID
            - dc_location: 数据中心位置
            - registration_date: 注册日期（来自regdate_clone_bot）
            - smartutil_reg_date: 注册日期（来自SmartUtilBot）
            - account_age_years: 账号年龄（年）
            - account_age_months: 账号年龄（月）
            - account_age_days: 账号年龄（天）

    Returns:
        bool: 是否保存成功
    """
    try:
        import json

        cache_data = {
            "user_id": user_id,
            "full_name": user_info.get("full_name"),
            "username": user_info.get("username"),
            "is_premium": user_info.get("is_premium"),
            "dc_id": user_info.get("dc_id"),
            "dc_location": user_info.get("dc_location"),
            "registration_date": (
                user_info["registration_date"].isoformat()
                if user_info.get("registration_date")
                else None
            ),
            "smartutil_reg_date": (
                user_info["smartutil_reg_date"].isoformat()
                if user_info.get("smartutil_reg_date")
                else None
            ),
            "account_age_years": user_info.get("account_age_years"),
            "account_age_months": user_info.get("account_age_months"),
            "queried_at": datetime.now().isoformat(),
        }

        key = f"{REDIS_KEY_USER_REG_DATE_PREFIX}{user_id}"
        await redis_client.set(key, json.dumps(cache_data))

        logger.info(
            f"已缓存用户 {user_id} 的完整信息 "
            f"(注册日期: {user_info['registration_date'].strftime('%Y-%m-%d') if user_info.get('registration_date') else '未知'}, "
            f"SmartUtil: {user_info['smartutil_reg_date'].strftime('%Y-%m-%d') if user_info.get('smartutil_reg_date') else '无'})"
        )
        return True

    except Exception as e:
        logger.error(f"保存用户 {user_id} 的缓存失败: {e}")
        return False


async def save_registration_sample(
    redis_client, user_id: int, registration_date: datetime
) -> bool:
    """
    保存用户 ID 和注册日期到样本数据集，用于改进 estimate_registration_date() 算法。

    双重保存策略：
    1. Redis Sorted Set (实时查询)
    2. JSON 文件 (持久化备份)

    Redis 存储：
    - Key: "registration_samples"
    - Score: user_id
    - Member: registration_date (ISO格式)

    JSON 文件：
    - 路径: database/registration_samples.json
    - 格式: [{"user_id": 123, "registration_date": "2025-11-01T00:00:00", "saved_at": "2025-11-04T01:30:00"}, ...]

    Args:
        redis_client: Redis 客户端
        user_id: 用户 ID
        registration_date: 注册日期

    Returns:
        bool: 保存是否成功
    """
    import json
    from pathlib import Path

    success = True

    try:
        # 1. 保存到 Redis Sorted Set
        await redis_client.zadd(
            "registration_samples", {registration_date.isoformat(): user_id}
        )
        logger.debug(f"✅ Redis: 已保存样本 user_id={user_id}")

    except Exception as e:
        logger.error(f"❌ Redis: 保存样本失败: {e}")
        success = False

    try:
        # 2. 保存到 JSON 文件
        json_file_path = Path("database/registration_samples.json")

        # 确保目录存在
        json_file_path.parent.mkdir(parents=True, exist_ok=True)

        # 读取现有数据
        samples = []
        if json_file_path.exists():
            try:
                with open(json_file_path, "r", encoding="utf-8") as f:
                    samples = json.load(f)
            except json.JSONDecodeError:
                logger.warning("JSON 文件格式错误,将重新创建")
                samples = []

        # 检查是否已存在该用户的样本
        existing_index = None
        for i, sample in enumerate(samples):
            if sample.get("user_id") == user_id:
                existing_index = i
                break

        # 构造新样本数据
        new_sample = {
            "user_id": user_id,
            "registration_date": registration_date.isoformat(),
            "saved_at": datetime.now().isoformat(),
        }

        # 更新或添加样本
        if existing_index is not None:
            samples[existing_index] = new_sample
            logger.debug(f"✅ JSON: 已更新样本 user_id={user_id}")
        else:
            samples.append(new_sample)
            logger.debug(f"✅ JSON: 已添加样本 user_id={user_id}")

        # 按 user_id 排序
        samples.sort(key=lambda x: x["user_id"])

        # 保存到文件
        with open(json_file_path, "w", encoding="utf-8") as f:
            json.dump(samples, f, ensure_ascii=False, indent=2)

        logger.debug(
            f"已保存注册样本: user_id={user_id}, "
            f"date={registration_date.strftime('%Y年%m月')}, "
            f"总样本数={len(samples)}"
        )

    except Exception as e:
        logger.error(f"❌ JSON: 保存样本失败: {e}", exc_info=True)
        success = False

    return success


async def get_cached_user_info(redis_client, user_id: int) -> Optional[Dict]:
    """
    从 Redis 获取缓存的完整用户信息。

    Args:
        redis_client: Redis 客户端
        user_id: 用户 ID

    Returns:
        包含完整用户信息的字典，如果未缓存则返回 None
    """
    try:
        import json

        key = f"{REDIS_KEY_USER_REG_DATE_PREFIX}{user_id}"
        cached_data = await redis_client.get(key)

        if not cached_data:
            return None

        # 解码 Redis 数据
        if isinstance(cached_data, bytes):
            cached_data = cached_data.decode()

        data = json.loads(cached_data)

        # 解析并返回完整信息
        result = {
            "user_id": data["user_id"],
            "full_name": data.get("full_name"),
            "username": data.get("username"),
            "is_premium": data.get("is_premium"),
            "dc_id": data.get("dc_id"),
            "dc_location": data.get("dc_location"),
            "registration_date": (
                datetime.fromisoformat(data["registration_date"])
                if data.get("registration_date")
                else None
            ),
            "smartutil_reg_date": (
                datetime.fromisoformat(data["smartutil_reg_date"])
                if data.get("smartutil_reg_date")
                else None
            ),
            "account_age_years": data.get("account_age_years"),
            "account_age_months": data.get("account_age_months"),
            "queried_at": (
                datetime.fromisoformat(data["queried_at"])
                if data.get("queried_at")
                else None
            ),
        }

        return result

    except Exception as e:
        logger.error(f"读取用户 {user_id} 的缓存失败: {e}")
        return None


def parse_account_age(age_str: str) -> tuple:
    """
    解析账号年龄字符串。

    Args:
        age_str: 如 "6 years, 7 months" 或 "2 months" 或 "15 days"

    Returns:
        (years, months, days): 年、月、天
    """
    import re

    years = 0
    months = 0
    days = 0

    # 匹配 "6 years"
    year_match = re.search(r"(\d+)\s+year", age_str)
    if year_match:
        years = int(year_match.group(1))

    # 匹配 "7 months"
    month_match = re.search(r"(\d+)\s+month", age_str)
    if month_match:
        months = int(month_match.group(1))

    # 匹配 "15 days"
    day_match = re.search(r"(\d+)\s+day", age_str)
    if day_match:
        days = int(day_match.group(1))

    return years, months, days


async def get_user_dc_and_premium(
    user_id: int,
    chat_id: Optional[int] = None,
    message_id: Optional[int] = None,
    user=None,
) -> Optional[Dict]:
    """
    使用 Pyrogram 获取用户的数据中心和 Premium 状态。

    Args:
        user_id: 用户 ID
        chat_id: 群组/频道 ID (可选,用于从消息中获取用户信息)
        message_id: 消息 ID (可选,用于从消息中获取用户信息)
        user: Telegram Bot API User 对象 (可选,用于获取 Premium 状态)

    Returns:
        包含 DC 和 Premium 信息的字典，失败返回 None
        {
            "dc_id": int,           # 数据中心 ID (可能为 None)
            "dc_location": str,     # 数据中��位置
            "is_premium": bool      # Premium 状态
        }
    """
    if not _pyrogram_client:
        logger.warning("Pyrogram 客户端未初始化，无法获取用户 DC 和 Premium 信息")
        return None

    if not _pyrogram_client.is_connected:
        logger.warning("Pyrogram 客户端未连接，无法获取用户 DC 和 Premium 信息")
        return None

    try:
        user_obj = None
        dc_id = None
        is_premium = False

        # 方案1 (优先): 如果提供了 chat_id 和 message_id,从消息中获取用户信息
        if chat_id and message_id:
            try:
                logger.info(
                    f"方案1: 从消息获取用户 {user_id} 的信息 (chat_id={chat_id}, message_id={message_id})..."
                )
                messages = await _pyrogram_client.get_messages(chat_id, message_id)

                if messages and messages.from_user and messages.from_user.id == user_id:
                    user_obj = messages.from_user
                    if user_obj.dc_id:
                        dc_id = user_obj.dc_id
                    is_premium = user_obj.is_premium if user_obj.is_premium else False
                    logger.info(f"✅ 成功从消息中获取用户 {user_id} 的完整信息")
                else:
                    logger.warning(f"消息中的发送者不是目标用户 {user_id}")
            except Exception as e:
                logger.warning(f"从消息获取用户信息失败: {e}")

        # 方案2: 直接查询用户 (可能失败)
        if not user_obj:
            try:
                logger.info(f"方案2: 尝试直接获取用户 {user_id} 的信息...")
                user_obj = await _pyrogram_client.get_users(user_id)
                if not dc_id and user_obj.dc_id:
                    dc_id = user_obj.dc_id
                if not is_premium:
                    is_premium = user_obj.is_premium if user_obj.is_premium else False
                logger.info(f"✅ 成功直接获取用户 {user_id} 的信息")
            except Exception as e:
                logger.warning(f"直接获取用户信息失败: {e}")

        # 方案3 (最后备选): 如果提供了 Bot API User 对象,从中获取 Premium 状态
        if user and not is_premium:
            if hasattr(user, "is_premium") and user.is_premium:
                is_premium = True
                logger.info(
                    f"✅ 从 Bot API User 对象获取用户 {user_id} 的 Premium 状态"
                )

        # 提取 DC 位置
        dc_location = None
        if dc_id:
            dc_location = DC_LOCATIONS.get(dc_id, f"Unknown DC{dc_id}")

        result = {
            "dc_id": dc_id,
            "dc_location": dc_location,
            "is_premium": is_premium,
        }

        logger.info(
            f"成功获取用户 {user_id} 的信息: " f"DC={dc_id}, Premium={is_premium}"
        )

        return result

    except Exception as e:
        logger.error(f"获取用户 {user_id} 的 DC 和 Premium 失败: {e}", exc_info=True)
        return None


async def query_regdate_bot(user_id: int) -> Optional[Dict]:
    """
    向 @regdate_clone_bot 查询用户注册日期。

    Args:
        user_id: 用户 ID

    Returns:
        包含注册日期信息的字典，失败返回 None
        {
            "user_id": int,
            "registration_date": datetime,  # 只有年月精度
        }
    """
    if not _pyrogram_client:
        logger.warning("Pyrogram 客户端未初始化，无法查询 @regdate_clone_bot")
        return None

    if not _pyrogram_client.is_connected:
        logger.warning("Pyrogram 客户端未连接，无法查询 @regdate_clone_bot")
        return None

    try:
        logger.info(f"向 @regdate_clone_bot 查询用户 {user_id} 的注册日期...")

        # 记录发送消息前的最后一条消息 ID
        last_message_id = None
        async for message in _pyrogram_client.get_chat_history(
            "regdate_clone_bot", limit=1
        ):
            last_message_id = message.id
            break

        # 发送用户 ID（不带命令）
        await _pyrogram_client.send_message("regdate_clone_bot", str(user_id))

        # 智能等待机制：轮询检查回复（最多等待 10 秒）
        max_wait_time = 10  # 最长等待 10 秒
        check_interval = 0.5  # 每 0.5 秒检查一次
        waited_time = 0

        while waited_time < max_wait_time:
            await asyncio.sleep(check_interval)
            waited_time += check_interval

            # 检查是否有新消息
            async for message in _pyrogram_client.get_chat_history(
                "regdate_clone_bot", limit=1
            ):
                # 如果是新消息（ID 大于之前记录的）
                if last_message_id is None or message.id > last_message_id:
                    if not message.text:
                        continue

                    logger.info(
                        f"收到 @regdate_clone_bot 回复（等待 {waited_time:.1f}s）:\n{message.text}"
                    )

                    # 解析返回信息
                    # 格式: "ID: 5341278389\nEstimated registration date: April 2022"
                    lines = message.text.split("\n")

                    for line in lines:
                        line = line.strip()

                        # Estimated registration date: April 2022
                        if (
                            "Estimated registration date:" in line
                            or "registration date:" in line.lower()
                        ):
                            date_str = line.split(":")[-1].strip()
                            try:
                                # 解析 "April 2022" -> datetime(2022, 4, 1)
                                registration_date = datetime.strptime(date_str, "%B %Y")

                                logger.info(
                                    f"成功从 @regdate_clone_bot 获取用户 {user_id} 的注册日期: "
                                    f"{registration_date.strftime('%Y年%m月')}"
                                )

                                return {
                                    "user_id": user_id,
                                    "registration_date": registration_date,
                                }
                            except ValueError as e:
                                logger.warning(
                                    f"无法解析注册日期: {date_str}, 错误: {e}"
                                )

                    # 如果消息不包含注册日期信息，继续等待
                    break

        logger.warning(f"等待 {max_wait_time} 秒后未收到 @regdate_clone_bot 的有效回复")
        return None

    except Exception as e:
        logger.error(f"查询 @regdate_clone_bot 失败: {e}", exc_info=True)
        return None


async def query_smartutil_bot(username: str) -> Optional[Dict]:
    """
    向 @SmartUtilBot 查询用户注册日期。

    Args:
        username: 用户名（不带@符号）

    Returns:
        包含注册日期信息的字典，失败返回 None
        {
            "registration_date": datetime,  # 完整日期（年月日）
        }
    """
    if not _pyrogram_client:
        logger.warning("Pyrogram 客户端未初始化，无法查询 @SmartUtilBot")
        return None

    if not _pyrogram_client.is_connected:
        logger.warning("Pyrogram 客户端未连接，无法查询 @SmartUtilBot")
        return None

    try:
        logger.info(f"向 @SmartUtilBot 查询用户 @{username} 的注册日期...")

        # 记录发送消息前的最后一条消息 ID
        last_message_id = None
        async for message in _pyrogram_client.get_chat_history("SmartUtilBot", limit=1):
            last_message_id = message.id
            break

        # 发送命令 /id @username
        command = f"/id @{username}"
        await _pyrogram_client.send_message("SmartUtilBot", command)

        # 智能等待机制：轮询检查回复（最多等待 10 秒）
        max_wait_time = 10  # 最长等待 10 秒
        check_interval = 0.5  # 每 0.5 秒检查一次
        waited_time = 0

        while waited_time < max_wait_time:
            await asyncio.sleep(check_interval)
            waited_time += check_interval

            # 检查是否有新消息
            async for message in _pyrogram_client.get_chat_history(
                "SmartUtilBot", limit=1
            ):
                # 如果是新消息（ID 大于之前记录的）
                if last_message_id is None or message.id > last_message_id:
                    if not message.text:
                        continue

                    logger.info(
                        f"收到 @SmartUtilBot 回复（等待 {waited_time:.1f}s）:\n{message.text}"
                    )

                    # 解析返回信息
                    # 格式示例:
                    # 👨‍🦰 User Information
                    # ━━━━━━━━━━━━━━━
                    #   - Full Name: Bio
                    #   - User ID: 7301526092
                    #   - Username: @jumbm
                    #   - Premium User: Yes
                    #   - Data Center: 5 (SIN, Singapore, SG))
                    #   - Account Created On: November 28, 2023
                    #   - Account Age: 2 years
                    import re

                    # 提取 "Account Created On: November 28, 2023"
                    created_match = re.search(
                        r"Account Created On:\s*([A-Za-z]+)\s+(\d+),\s+(\d+)",
                        message.text,
                    )

                    # 提取 "Data Center: 5 (SIN, Singapore, SG)"
                    dc_match = re.search(r"Data Center:\s*(\d+)", message.text)

                    registration_date = None
                    dc_id = None

                    if created_match:
                        month_str = created_match.group(1)
                        day = int(created_match.group(2))
                        year = int(created_match.group(3))

                        try:
                            # 解析 "November 28, 2023" -> datetime(2023, 11, 28)
                            registration_date = datetime.strptime(
                                f"{month_str} {day}, {year}", "%B %d, %Y"
                            )

                            logger.info(
                                f"成功从 @SmartUtilBot 获取用户 @{username} 的注册日期: "
                                f"{registration_date.strftime('%Y年%m月%d日')}"
                            )
                        except ValueError as e:
                            logger.warning(
                                f"无法解析注册日期: {month_str} {day}, {year}, 错误: {e}"
                            )

                    if dc_match:
                        dc_id = int(dc_match.group(1))
                        logger.info(
                            f"成功从 @SmartUtilBot 获取用户 @{username} 的 DC: {dc_id}"
                        )

                    if registration_date or dc_id:
                        result = {}
                        if registration_date:
                            result["registration_date"] = registration_date
                        if dc_id:
                            result["dc_id"] = dc_id

                        return result

                    # 如果消息不包含注册日期信息，继续等待
                    break

        logger.warning(f"等待 {max_wait_time} 秒后未收到 @SmartUtilBot 的有效回复")
        return None

    except Exception as e:
        logger.error(f"查询 @SmartUtilBot 失败: {e}", exc_info=True)
        return None


async def start_phone_login(phone_number: str, user_id: int) -> Dict:
    """
    开始手机号登录流程，发送验证码。

    Args:
        phone_number: 国际格式手机号（如 +8613812341234）
        user_id: 发起登录的用户 ID

    Returns:
        包含结果的字典：
        {
            "success": bool,
            "phone_code_hash": str,  # 验证码 hash，用于后续验证
            "message": str  # 提示消息
        }
    """
    global _pyrogram_client, _redis_client, _temp_login_clients, _temp_login_timestamps

    if not _redis_client:
        return {"success": False, "message": "Redis 客户端未初始化"}

    try:
        # 获取 API 凭证
        credentials = await get_pyrogram_credentials(_redis_client)
        if not credentials:
            return {
                "success": False,
                "message": "API 凭证未配置，请先配置 API ID 和 API Hash",
            }

        api_id = credentials["api_id"]
        api_hash = credentials["api_hash"]

        logger.info(
            f"用户 {user_id} 开始为手机号 {phone_number[:3]}****{phone_number[-4:]} 发送验证码..."
        )

        # 如果该用户已有临时 Client，先清理
        if user_id in _temp_login_clients:
            old_client = _temp_login_clients[user_id]
            if old_client.is_connected:
                await old_client.disconnect()
            del _temp_login_clients[user_id]
            del _temp_login_timestamps[user_id]
            logger.info(f"清理用户 {user_id} 的旧登录会话")

        # 创建临时客户端用于登录流程
        temp_client = Client(
            name=f"domoapp_bot_login_{user_id}",
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
        await _redis_client.setex(
            f"{REDIS_KEY_TEMP_PHONE_CODE_HASH}:{user_id}",
            300,  # 5分钟过期
            sent_code.phone_code_hash,
        )

        # ⚠️ 不要 disconnect，保持连接用于后续验证
        # await temp_client.disconnect()

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
        # 清理可能创建的临时 Client
        if user_id in _temp_login_clients:
            try:
                await _temp_login_clients[user_id].disconnect()
            except Exception:
                pass
            del _temp_login_clients[user_id]
            del _temp_login_timestamps[user_id]
        return {"success": False, "message": f"发送验证码失败: {str(e)}"}


async def complete_phone_login(
    phone_number: str, phone_code: str, user_id: int, password: str = None
) -> Dict:
    """
    完成手机号登录，提交验证码（和可选的 2FA 密码）。

    Args:
        phone_number: 国际格式手机号
        phone_code: 收到的验证码
        user_id: 发起登录的用户 ID
        password: 可选的双重验证密码

    Returns:
        包含结果的字典：
        {
            "success": bool,
            "requires_password": bool,  # 是否需要 2FA 密码
            "message": str
        }
    """
    global _pyrogram_client, _redis_client, _temp_login_clients, _temp_login_timestamps

    if not _redis_client:
        return {"success": False, "message": "Redis 客户端未初始化"}

    try:
        # 检查是否有该用户的临时登录 Client
        if user_id not in _temp_login_clients:
            return {"success": False, "message": "登录会话已过期，请重新发送验证码"}

        client = _temp_login_clients[user_id]

        if not client.is_connected:
            return {"success": False, "message": "登录会话已断开，请重新发送验证码"}

        # 获取 phone_code_hash
        phone_code_hash_bytes = await _redis_client.get(
            f"{REDIS_KEY_TEMP_PHONE_CODE_HASH}:{user_id}"
        )
        if not phone_code_hash_bytes:
            # 清理临时 Client
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
            # ⚠️ 使用同一个 Client 进行验证
            await client.sign_in(phone_number, phone_code_hash, phone_code)

            # 导出会话字符串
            session_string = await client.export_session_string()

            # 保存会话到 Redis
            await save_session_string(_redis_client, session_string, phone_number)

            # 清除临时 phone_code_hash
            await _redis_client.delete(f"{REDIS_KEY_TEMP_PHONE_CODE_HASH}:{user_id}")

            # 将临时 Client 转为全局 Client
            _pyrogram_client = client
            del _temp_login_clients[user_id]
            del _temp_login_timestamps[user_id]

            logger.info(
                f"用户 {user_id} 手机号 {phone_number[:3]}****{phone_number[-4:]} 登录成功"
            )

            return {
                "success": True,
                "requires_password": False,
                "message": "登录成功！",
            }

        except SessionPasswordNeeded:
            # 需要双重验证密码
            if password:
                # 如果提供了密码，尝试验证
                try:
                    await client.check_password(password)

                    # 导出会话字符串
                    session_string = await client.export_session_string()

                    # 保存会话到 Redis
                    await save_session_string(
                        _redis_client, session_string, phone_number
                    )

                    # 清除临时 phone_code_hash
                    await _redis_client.delete(
                        f"{REDIS_KEY_TEMP_PHONE_CODE_HASH}:{user_id}"
                    )

                    # 将临时 Client 转为全局 Client
                    _pyrogram_client = client
                    del _temp_login_clients[user_id]
                    del _temp_login_timestamps[user_id]

                    logger.info(
                        f"用户 {user_id} 手机号 {phone_number[:3]}****{phone_number[-4:]} 登录成功（2FA）"
                    )

                    return {
                        "success": True,
                        "requires_password": False,
                        "message": "登录成功！",
                    }
                except Exception as e:
                    logger.error(f"双重验证密码错误: {e}")
                    # 保持连接，允许重试
                    return {
                        "success": False,
                        "requires_password": True,
                        "message": "双重验证密码错误，请重试",
                    }
            else:
                # 需要密码但未提供，保持连接
                return {
                    "success": False,
                    "requires_password": True,
                    "message": "此账号启用了双重验证，请输入密码",
                }

        except PhoneCodeInvalid:
            # 验证码错误，保持连接允许重试
            logger.warning(f"用户 {user_id} 验证码错误")
            return {
                "success": False,
                "requires_password": False,
                "message": "验证码错误，请重试",
            }

        except PhoneCodeExpired:
            # 验证码过期，清理连接
            logger.warning(f"用户 {user_id} 验证码已过期")
            await client.disconnect()
            del _temp_login_clients[user_id]
            del _temp_login_timestamps[user_id]
            await _redis_client.delete(f"{REDIS_KEY_TEMP_PHONE_CODE_HASH}:{user_id}")
            return {
                "success": False,
                "requires_password": False,
                "message": "验证码已过期，请重新发送",
            }

    except Exception as e:
        logger.error(f"登录失败: {e}", exc_info=True)
        # 清理临时 Client
        if user_id in _temp_login_clients:
            try:
                await _temp_login_clients[user_id].disconnect()
            except Exception:
                pass
            del _temp_login_clients[user_id]
            del _temp_login_timestamps[user_id]
        return {"success": False, "message": f"登录失败: {str(e)}"}


async def logout_pyrogram_user() -> bool:
    """
    登出 Pyrogram 用户会话。

    Returns:
        bool: 登出是否成功
    """
    global _pyrogram_client, _redis_client

    if not _redis_client:
        logger.error("Redis 客户端未初始化")
        return False

    try:
        # 停止客户端
        if _pyrogram_client:
            try:
                await _pyrogram_client.stop()
                logger.info("Pyrogram 客户端已停止")
            except Exception as e:
                logger.error(f"停止 Pyrogram 客户端时出错: {e}")
            finally:
                _pyrogram_client = None

        # 清除 Redis 中的会话信息
        await _redis_client.delete(REDIS_KEY_SESSION_STRING)
        await _redis_client.delete(REDIS_KEY_PHONE_NUMBER)
        await _redis_client.delete(REDIS_KEY_LOGIN_TIME)

        logger.info("Pyrogram 会话已清除")
        return True

    except Exception as e:
        logger.error(f"登出失败: {e}", exc_info=True)
        return False


def get_pyrogram_client() -> Optional[Client]:
    """
    获取 Pyrogram 客户端实例。

    Returns:
        Client 实例，如果未初始化则返回 None
    """
    return _pyrogram_client


async def initialize_pyrogram_client(redis_client=None) -> bool:
    """
    初始化 Pyrogram 客户端（从 Redis 恢复会话）。

    Args:
        redis_client: Redis 客户端实例

    Returns:
        bool: 初始化是否成功
    """
    global _pyrogram_client, _redis_client

    if not redis_client:
        logger.error("Redis 客户端未提供")
        return False

    _redis_client = redis_client

    try:
        logger.info("正在检查 Pyrogram 配置...")

        # 从 Redis 获取 API 凭证
        credentials = await get_pyrogram_credentials(redis_client)
        if not credentials:
            logger.warning("Pyrogram API 凭证未配置")
            logger.warning("提示：请通过 /admin 面板配置 API ID 和 API Hash")
            return False

        # 从 Redis 获取会话信息
        session_info = await get_session_info(redis_client)
        if not session_info:
            logger.warning("Pyrogram 用户未登录")
            logger.warning("提示：请通过 /admin 面板使用手机号登录")
            return False

        api_id = credentials["api_id"]
        api_hash = credentials["api_hash"]
        session_string = session_info["session_string"]

        logger.info("开始从会话字符串恢复 Pyrogram 客户端...")

        # 从会话字符串创建客户端
        _pyrogram_client = Client(
            name="domoapp_bot",
            api_id=api_id,
            api_hash=api_hash,
            session_string=session_string,
            in_memory=True,
        )

        await _pyrogram_client.start()
        logger.info("✅ Pyrogram 客户端已从会话恢复")
        return True

    except Exception as e:
        logger.error(f"Pyrogram 客户端初始化失败: {e}", exc_info=True)
        _pyrogram_client = None
        return False


async def stop_pyrogram_client():
    """
    停止 Pyrogram 客户端。
    """
    global _pyrogram_client

    if _pyrogram_client:
        try:
            await _pyrogram_client.stop()
            logger.info("Pyrogram 客户端已停止")
        except Exception as e:
            logger.error(f"停止 Pyrogram 客户端时出错: {e}")
        finally:
            _pyrogram_client = None


async def get_user_full_info(
    user_id: int,
    chat_id: Optional[int] = None,
    message_id: Optional[int] = None,
    user=None,
) -> Optional[Dict]:
    """
    获取用户的完整信息（整合多个数据源）。

    数据来源：
    - DC 和 Premium: Pyrogram 原生 API (优先从消息中获取)
    - 注册日期: @regdate_clone_bot
    - 注册日期（SmartUtilBot）: @SmartUtilBot (仅当有用户名时)

    Args:
        user_id: 用户 ID
        chat_id: 群组/频道 ID (可选,用于从消息中获取用户信息)
        message_id: 消息 ID (可选,用于从消息中获取用户信息)
        user: Telegram Bot API User 对象 (可选,当 Pyrogram 无法获取用户信息时作为备用)

    Returns:
        包含以下字段的字典：
        - user_id: 用户 ID
        - full_name: 全名
        - username: 用户名
        - is_premium: Premium 状态
        - dc_id: 数据中心 ID
        - dc_location: 数据中心位置
        - registration_date: 注册日期（年月精度，来自regdate_clone_bot）
        - smartutil_reg_date: 注册日期（完整日期，来自SmartUtilBot）
        - account_age_years: 账号年龄（年）
        - account_age_months: 账号年龄（月）
        - cached: 是否来自缓存
        如果获取失败则返回 None
    """
    if not _pyrogram_client or not _pyrogram_client.is_connected:
        logger.warning("Pyrogram 客户端未初始化或未连接")
        return None

    if not _redis_client:
        logger.warning("Redis 客户端未初始化")
        # 可以继续查询，但不缓存
        pass

    try:
        logger.info(f"正在获取用户 {user_id} 的完整信息...")

        # 1. 先从 Redis 缓存查询
        if _redis_client:
            cached_data = await get_cached_user_info(_redis_client, user_id)
            if cached_data:
                logger.info(f"从缓存获取用户 {user_id} 的信息")
                cached_data["cached"] = True
                return cached_data

        # 2. 缓存未命中，分别查询多个数据源（每个数据源独立处理异常）
        logger.info("缓存未命中，正在查询多个数据源...")

        # 初始化用户信息字典
        user_info = {
            "user_id": user_id,
            "full_name": None,
            "username": None,
            "dc_id": None,
            "dc_location": None,
            "is_premium": False,
            "registration_date": None,
            "smartutil_reg_date": None,
            "account_age_years": 0,
            "account_age_months": 0,
        }

        # 2.1 获取基本用户信息（姓名、用户名）
        # 优先从 Bot API User 对象获取
        if user:
            try:
                user_info["full_name"] = (
                    f"{user.first_name or ''} {user.last_name or ''}".strip()
                )
                user_info["username"] = user.username
                logger.info(f"✅ 成功从 Bot API User 对象获取用户 {user_id} 的基本信息")
            except Exception as e:
                logger.warning(
                    f"⚠️ 从 Bot API User 对象获取基本信息失败: {e}, 尝试 Pyrogram..."
                )

        # 如果 Bot API 没有提供,尝试从 Pyrogram 获取
        if not user_info.get("username") or not user_info.get("full_name"):
            try:
                user_basic = await _pyrogram_client.get_users(user_id)
                if not user_info.get("full_name"):
                    user_info["full_name"] = (
                        f"{user_basic.first_name or ''} {user_basic.last_name or ''}".strip()
                    )
                if not user_info.get("username"):
                    user_info["username"] = user_basic.username
                logger.info(f"✅ 成功从 Pyrogram 获取用户 {user_id} 的基本信息")
            except Exception as e:
                logger.warning(f"⚠️ 无法从 Pyrogram 获取用户 {user_id} 的基本信息: {e}")
                # 继续执行，不影响其他数据源

        # 2.2 获取 DC 和 Premium 信息（优先从头像获取 DC）
        try:
            dc_premium_info = await get_user_dc_and_premium(
                user_id, chat_id, message_id, user
            )
            if dc_premium_info:
                user_info["dc_id"] = dc_premium_info.get("dc_id")
                user_info["dc_location"] = dc_premium_info.get("dc_location")
                user_info["is_premium"] = dc_premium_info.get("is_premium", False)
                logger.info(f"✅ 成功获取用户 {user_id} 的 DC 和 Premium 信息")
            else:
                logger.warning(f"⚠️ 未获取到用户 {user_id} 的 DC 和 Premium 信息")
        except Exception as e:
            logger.warning(f"⚠️ 获取用户 {user_id} 的 DC 和 Premium 信息时出错: {e}")

        # 2.3 查询注册日期（独立执行，不受前面步骤影响）
        try:
            regdate_info = await query_regdate_bot(user_id)
            if regdate_info and "registration_date" in regdate_info:
                reg_date = regdate_info["registration_date"]
                user_info["registration_date"] = reg_date

                # 计算账号年龄（只到月份）
                now = datetime.now()
                years = now.year - reg_date.year
                months = now.month - reg_date.month

                # 调整月份差值
                if months < 0:
                    years -= 1
                    months += 12

                user_info["account_age_years"] = years
                user_info["account_age_months"] = months
                logger.info(
                    f"✅ 成功从 @regdate_clone_bot 获取用户 {user_id} 的注册日期"
                )
            else:
                logger.warning(
                    f"⚠️ 未能从 @regdate_clone_bot 获取用户 {user_id} 的注册日期"
                )
        except Exception as e:
            logger.warning(f"⚠️ 查询 @regdate_clone_bot 时出错: {e}")

        # 2.4 查询 SmartUtilBot 注册日期（仅当有用户名时）
        if user_info.get("username"):
            try:
                smartutil_info = await query_smartutil_bot(user_info["username"])
                if smartutil_info:
                    if "registration_date" in smartutil_info:
                        user_info["smartutil_reg_date"] = smartutil_info[
                            "registration_date"
                        ]
                        logger.info(
                            f"✅ 成功从 @SmartUtilBot 获取用户 {user_id} 的注册日期"
                        )

                    # 如果头像获取 DC 失败,使用 SmartUtilBot 的 DC 作为备选
                    if "dc_id" in smartutil_info and not user_info.get("dc_id"):
                        user_info["dc_id"] = smartutil_info["dc_id"]
                        user_info["dc_location"] = DC_LOCATIONS.get(
                            smartutil_info["dc_id"],
                            f"Unknown DC{smartutil_info['dc_id']}",
                        )
                        logger.info(
                            f"✅ 使用 @SmartUtilBot 的 DC 信息作为备选: DC{smartutil_info['dc_id']}"
                        )

                    if not smartutil_info.get("registration_date"):
                        logger.warning(
                            f"⚠️ 未能从 @SmartUtilBot 获取用户 {user_id} 的注册日期"
                        )
            except Exception as e:
                logger.warning(f"⚠️ 查询 @SmartUtilBot 时出错: {e}")
        else:
            logger.info(f"用户 {user_id} 没有用户名，跳过 @SmartUtilBot 查询")

        # 4. 保存到 Redis 缓存
        if _redis_client and user_info.get("registration_date"):
            # 4.1 保存用户完整信息缓存
            await save_user_info_to_cache(_redis_client, user_id, user_info)

            # 4.2 保存到 ID-注册日期样本数据集（用于改进估算算法）
            await save_registration_sample(
                _redis_client, user_id, user_info["registration_date"]
            )

        user_info["cached"] = False
        logger.info(
            f"成功获取用户 {user_id} 的完整信息，" f"包含字段: {list(user_info.keys())}"
        )
        return user_info

    except Exception as e:
        logger.error(f"获取用户 {user_id} 信息时发生错误: {e}", exc_info=True)
        return None


# ============ 以下为旧代码，保留以备不时之需 ============


async def estimate_registration_date(
    user_id: int, redis_client=None
) -> Optional[datetime]:
    """
    根据用户 ID 估算注册日期。

    优先使用 Redis 中积累的真实样本数据进行插值，
    如果样本不足则回退到固定数据点估算。

    参考数据点（基于开源项目 lastochkin-group/telegram-account-age-estimator）：
    - 使用真实用户数据进行精确估算
    - 数据来源：50万+用户验证的开源数据集
    - 特别优化了 2015-2021 年的估算准确性

    Args:
        user_id: 用户 ID
        redis_client: Redis 客户端（可选，用于获取真实样本数据）

    Returns:
        估算的注册日期，如果无法估算则返回 None
    """
    # 尝试使用 Redis 中积累的真实样本数据
    if redis_client:
        try:
            # 获取所有样本数据 (score=user_id, member=registration_date)
            samples = await redis_client.zrange(
                "registration_samples", 0, -1, withscores=True
            )

            if len(samples) >= 10:  # 至少需要 10 个样本才使用动态数据
                # 将样本转换为 (user_id, date) 列表
                data_points = []
                for date_str, uid in samples:
                    if isinstance(date_str, bytes):
                        date_str = date_str.decode()
                    data_points.append((int(uid), datetime.fromisoformat(date_str)))

                # 按 user_id 排序
                data_points.sort(key=lambda x: x[0])

                # 使用样本数据进行插值
                for i in range(len(data_points) - 1):
                    id1, date1 = data_points[i]
                    id2, date2 = data_points[i + 1]

                    if id1 <= user_id < id2:
                        # 线性插值
                        ratio = (user_id - id1) / (id2 - id1)
                        time_diff = (date2 - date1).total_seconds()
                        estimated_seconds = date1.timestamp() + (time_diff * ratio)
                        logger.info(
                            f"使用 {len(data_points)} 个真实样本估算用户 {user_id} 的注册日期"
                        )
                        return datetime.fromtimestamp(estimated_seconds)

                # 如果不在样本范围内，回退到固定数据点
                logger.debug(f"用户 {user_id} 超出样本范围，回退到固定数据点")

        except Exception as e:
            logger.warning(f"使用样本数据估算失败，回退到固定数据点: {e}")

    # 回退到固定数据点估算
    # 数据点映射 (user_id, 对应的精确/估算日期)
    # 数据来源：lastochkin-group/telegram-account-age-estimator
    data_points = [
        # 早期估算数据（2013-2014）
        (10000, datetime(2013, 1, 1)),
        (100000, datetime(2013, 8, 1)),
        (1000000, datetime(2014, 1, 1)),
        (10000000, datetime(2015, 1, 1)),
        # 2015年精确数据（开源项目）
        (101260938, datetime(2015, 3, 6)),
        (101323197, datetime(2015, 3, 13)),
        (111220210, datetime(2015, 4, 21)),
        (116812045, datetime(2015, 7, 24)),
        (143445125, datetime(2015, 12, 1)),
        # 2016年精确数据（开源项目）
        (181783990, datetime(2016, 4, 10)),
        (294851037, datetime(2016, 11, 20)),
        # 2017年精确数据（开源项目）
        (337808429, datetime(2017, 2, 21)),
        (369669043, datetime(2017, 3, 31)),
        (400169472, datetime(2017, 7, 30)),
        # 2018-2019年数据
        (500000000, datetime(2018, 6, 1)),
        (805158066, datetime(2019, 7, 16)),  # 开源精确数据
        (1000000000, datetime(2019, 3, 1)),
        # 2020-2025年数据
        (1974255900, datetime(2021, 10, 12)),  # 开源精确数据
        (2000000000, datetime(2020, 9, 1)),
        (3000000000, datetime(2021, 6, 1)),
        (4000000000, datetime(2022, 3, 1)),
        (5000000000, datetime(2023, 1, 1)),
        (6000000000, datetime(2024, 1, 1)),
        (7000000000, datetime(2025, 1, 1)),
    ]

    # 找到合适的区间进行线性插值
    for i in range(len(data_points) - 1):
        id1, date1 = data_points[i]
        id2, date2 = data_points[i + 1]

        if id1 <= user_id < id2:
            # 线性插值
            ratio = (user_id - id1) / (id2 - id1)
            time_diff = (date2 - date1).total_seconds()
            estimated_seconds = date1.timestamp() + (time_diff * ratio)
            return datetime.fromtimestamp(estimated_seconds)

    # 如果 ID 超出范围，返回最近的边界
    if user_id < data_points[0][0]:
        return data_points[0][1]
    else:
        # 对于超出最大 ID 的情况，基于最后一个数据点外推
        last_id, last_date = data_points[-1]
        if user_id >= last_id:
            # 假设每天新增约 5000000 个 ID（根据最近几年的增长速度）
            days_since = (user_id - last_id) / 5000000
            return last_date + timedelta(days=days_since)

    return None
