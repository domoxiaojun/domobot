"""
用户信息查询模块（顶层整合模块）

整合多个数据源获取完整用户信息：
1. MySQL 官方数据（最高优先级）- 来自 PeerSettings 的准确数据
2. Pyrofork Raw API 实时查询 - 尝试从 PeerSettings 获取
3. 从头像 file_id 提取 DC（降级）
4. ID 推测算法 - 兜底方案

依赖模块：
- persistence: MySQL 持久化
- dc_extractor: DC 位置提取
- id_estimation: ID 推测算法
- session: 用户信息缓存
- client: 获取 Pyrofork 客户端实例
"""

import logging
from datetime import datetime

from pyrogram import raw

logger = logging.getLogger(__name__)

# DC 位置映射
DC_LOCATIONS = {
    1: "MIA (Miami, Florida, US)",
    2: "AMS (Amsterdam, Netherlands, NL)",
    3: "MIA (Miami, Florida, US)",
    4: "AMS (Amsterdam, Netherlands, NL)",
    5: "SIN (Singapore, SG)",
}


async def get_user_info_via_raw_api(pyrofork_client, user_id: int) -> dict | None:
    """
    通过 Pyrofork Raw API 获取用户完整信息

    调用 users.GetFullUser 获取:
    - registration_year: 注册年份
    - registration_month: 注册月份 (1-12)
    - dc_id: 数据中心 ID
    - is_premium: Premium 状态

    Args:
        pyrofork_client: Pyrofork Client 实例
        user_id: 用户 ID

    Returns:
        包含用户信息的字典,失败返回 None
        {
            "registration_year": 2024,
            "registration_month": 3,
            "dc_id": 4,
            "is_premium": False,
            "method": "Raw API"
        }
    """
    if not pyrofork_client:
        logger.debug("Pyrofork 客户端未初始化,无法使用 Raw API")
        return None

    try:
        from utils.pyrofork.client import is_user_mode
        from utils.pyrofork.id_estimation import estimate_registration_date

        # 入口日志：检查客户端模式
        if not is_user_mode():
            logger.info(
                f"⚠️ [Raw API] 当前为 Bot 模式，无法获取 PeerSettings（用户 {user_id}）"
            )

        # 记录 Pyrofork Layer 版本
        try:
            layer = raw.layer
            logger.info(f"📋 [Raw API] Pyrofork Layer: {layer}")
        except Exception:
            pass

        logger.debug(f"🔍 [Raw API] 正在查询用户 {user_id} 的完整信息...")

        # 0. 预加载用户到 peer 缓存,避免 PEER_ID_INVALID 错误
        try:
            await pyrofork_client.get_users(user_id)
            logger.debug(f"已通过 get_users 预加载用户 {user_id} 到 peer 缓存")
        except Exception as e:
            logger.debug(f"预加载用户 {user_id} 失败: {e}, 继续尝试 resolve_peer")

        # 1. 解析 Peer
        peer = await pyrofork_client.resolve_peer(user_id)
        logger.debug(f"已解析 peer: {peer}")

        # 2. 调用 GetFullUser
        full_user_data = await pyrofork_client.invoke(
            raw.functions.users.GetFullUser(id=peer)
        )

        user_info = full_user_data.full_user
        logger.debug(f"收到 FullUser 对象: {type(user_info)}")
        logger.debug(f"FullUser 详细信息: {str(user_info)[:200]}...")

        # PeerSettings 诊断日志
        settings = getattr(user_info, "settings", None)
        if settings is not None:
            reg_month_raw = getattr(settings, "registration_month", None)
            logger.info(
                f"📋 [PeerSettings] 用户 {user_id} — "
                f"settings 存在, registration_month='{reg_month_raw}'"
            )
            # 完整 dump PeerSettings 对象，排查服务端返回的全部字段
            logger.info(f"📋 [PeerSettings] 完整对象: {settings}")
        else:
            logger.info(
                f"📋 [PeerSettings] 用户 {user_id} — settings 为 None"
                f"（可能原因: Bot 模式 / 未建立私聊 peer 关系）"
            )

        # 3. 初始化结果字典
        user_data = full_user_data.users[0] if full_user_data.users else None
        result = {
            "registration_year": None,
            "registration_month": None,
            "registration_source": None,
            "dc_id": None,
            "is_premium": (
                getattr(user_data, "premium", False) if user_data else False
            ),
            "method": "Raw API",
            "full_name": None,
            "username": None,
            "phone_country": None,
            "name_change_date": None,
            "photo_change_date": None,
        }

        # 从 users[0] 提取基本信息（复用 GetFullUser 返回的 User 对象）
        if user_data:
            first = getattr(user_data, "first_name", "") or ""
            last = getattr(user_data, "last_name", "") or ""
            result["full_name"] = f"{first} {last}".strip()
            result["username"] = getattr(user_data, "username", None)

        # 4. 尝试从 PeerSettings 获取注册时间
        # 访问路径: user_info.settings.registration_month
        # 字段格式: "MM.YYYY" (例如 "05.2024")
        # 注意: 服务器仅对陌生人私聊场景返回此字段
        if hasattr(user_info, "settings") and hasattr(
            user_info.settings, "registration_month"
        ):
            reg_month_str = user_info.settings.registration_month

            if reg_month_str:
                # 解析 "MM.YYYY" 格式
                try:
                    parts = reg_month_str.split(".")
                    if len(parts) == 2:
                        result["registration_month"] = int(parts[0])
                        result["registration_year"] = int(parts[1])
                        result["registration_source"] = "peersettings"
                        logger.info(
                            f"✅ [PeerSettings] 获取到官方注册时间: "
                            f"{result['registration_year']}年{result['registration_month']}月"
                        )
                except ValueError as e:
                    logger.warning(
                        f"⚠️ [PeerSettings] 解析失败: {reg_month_str}, 错误: {e}"
                    )

        # 4.1 从 PeerSettings 提取附加字段（phone_country / name_change_date / photo_change_date）
        if settings:
            result["phone_country"] = getattr(settings, "phone_country", None)
            result["name_change_date"] = getattr(settings, "name_change_date", None)
            result["photo_change_date"] = getattr(settings, "photo_change_date", None)

        # 5. 如果 PeerSettings 未返回，降级到 ID 推测
        if not result["registration_year"]:
            logger.info(
                f"ℹ️ [PeerSettings] 用户 {user_id} 未获取到注册时间"
                f"（settings={'有' if settings else '无'}, "
                f"registration_month='{getattr(settings, 'registration_month', 'N/A')}'）"
            )
            logger.debug("   正在降级到 ID 推测算法...")

            estimated_date = await estimate_registration_date(user_id)
            if estimated_date:
                result["registration_year"] = estimated_date.year
                result["registration_month"] = estimated_date.month
                result["registration_source"] = "id_estimation"
                logger.debug(
                    f"✅ [ID 推测] 估算注册时间: "
                    f"{result['registration_year']}年{result['registration_month']}月"
                )
            else:
                logger.warning(f"⚠️ 无法估算用户 {user_id} 的注册时间")
                result["registration_source"] = "unavailable"

        # 6. 尝试从头像获取 DC
        if user_info.profile_photo and hasattr(user_info.profile_photo, "dc_id"):
            result["dc_id"] = user_info.profile_photo.dc_id
            logger.debug(f"从 profile_photo 获取 DC: {result['dc_id']}")

        if result["dc_id"]:
            logger.debug(f"✅ [Raw API] 用户 {user_id} DC: DC{result['dc_id']}")

        return result

    except Exception as e:
        logger.warning(f"❌ [Raw API] 查询失败: {e}", exc_info=True)
        return None


async def get_user_dc_and_premium(
    user_id: int,
    _chat_id: int | None = None,
    _message_id: int | None = None,
    _user=None,
    bot=None,
) -> dict | None:
    """
    获取用户的 DC 和 Premium 状态 (多方案降级)

    方案优先级 (新):
    1. Raw API (最优先) - 如果 Pyrofork 已初始化
    2. 从头像 file_id 获取 (降级) - 如果未配置 API ID/Hash 或 Raw API 失败

    Args:
        user_id: 用户 ID
        _chat_id: (已弃用)
        _message_id: (已弃用)
        _user: (已弃用)
        bot: Telegram Bot 实例 (可选,用于从头像获取 DC)

    Returns:
        包含 DC 和 Premium 信息的字典
        {
            "dc_id": int,                  # 数据中心 ID (可能为 None)
            "dc_location": str,            # 数据中心位置
            "is_premium": bool,            # Premium 状态
            "registration_year": int,      # 注册年份 (可能为 None)
            "registration_month": int,     # 注册月份 (可能为 None)
            "method": str,                 # 获取方法
            "method_desc": str,            # 方法描述
        }
    """
    from utils.pyrofork.client import get_pyrofork_client
    from utils.pyrofork.dc_extractor import get_dc_from_profile_photo

    pyrofork_client = get_pyrofork_client()

    # 方案 1: Raw API (最优先)
    if pyrofork_client:
        logger.debug(f"方案1（Raw API）: 尝试通过 Raw API 获取用户 {user_id} 信息...")
        raw_info = await get_user_info_via_raw_api(pyrofork_client, user_id)
        if raw_info:
            dc_id = raw_info.get("dc_id")
            is_premium = raw_info.get("is_premium")
            registration_year = raw_info.get("registration_year")
            registration_month = raw_info.get("registration_month")
            registration_source = raw_info.get("registration_source")
            method = "方案1"
            method_desc = "Raw API"

            logger.debug("✅ [方案1] Raw API 成功获取完整信息")
            return {
                "dc_id": dc_id,
                "dc_location": (
                    DC_LOCATIONS.get(dc_id, f"Unknown DC{dc_id}") if dc_id else None
                ),
                "is_premium": is_premium,
                "registration_year": registration_year,
                "registration_month": registration_month,
                "registration_source": registration_source,
                "method": method,
                "method_desc": method_desc,
                "full_name": raw_info.get("full_name"),
                "username": raw_info.get("username"),
                "phone_country": raw_info.get("phone_country"),
                "name_change_date": raw_info.get("name_change_date"),
                "photo_change_date": raw_info.get("photo_change_date"),
            }
        else:
            logger.debug("⚠️ [方案1] Raw API 未返回有效数据,降级到方案2")

    # 方案 2: 从头像 file_id 获取 (降级)
    if bot:
        logger.debug(f"方案2（file_id）: 尝试从用户 {user_id} 的头像获取 DC...")
        dc_id = await get_dc_from_profile_photo(bot, user_id)
        if dc_id:
            method = "方案2"
            method_desc = "从头像 file_id 获取"
            logger.debug(f"✅ [方案2] file_id 成功获取 DC{dc_id}")
            return {
                "dc_id": dc_id,
                "dc_location": DC_LOCATIONS.get(dc_id, f"Unknown DC{dc_id}"),
                "is_premium": None,
                "registration_year": None,
                "registration_month": None,
                "phone_country": None,
                "name_change_date": None,
                "photo_change_date": None,
                "method": method,
                "method_desc": method_desc,
            }

    # 所有方案失败
    logger.warning(f"❌ 所有方案均失败,无法获取用户 {user_id} 的 DC 信息")
    return {
        "dc_id": None,
        "dc_location": None,
        "is_premium": None,
        "registration_year": None,
        "registration_month": None,
        "phone_country": None,
        "name_change_date": None,
        "photo_change_date": None,
        "method": None,
        "method_desc": "所有方案失败",
    }


async def get_user_full_info(
    user_id: int,
    redis_client=None,
    _chat_id: int | None = None,
    _message_id: int | None = None,
    user=None,
    bot=None,
    mysql_manager=None,
    force_refresh: bool = False,
) -> dict | None:
    """
    获取用户的完整信息（整合多个数据源）

    数据来源优先级：
    1. MySQL 官方数据（最高优先级） - 来自 PeerSettings 的准确数据
    2. Pyrofork Raw API 实时查询 - 尝试从 PeerSettings 获取
    3. ID 推测算法 - 兜底方案

    当 force_refresh=True 时（/cinfo 场景），跳过 Redis 和 MySQL 缓存，
    直接走 Raw API 重新获取 PeerSettings 并覆盖写入 MySQL。

    Args:
        user_id: 用户 ID
        redis_client: Redis 客户端实例
        _chat_id: (已弃用)
        _message_id: (已弃用)
        user: Telegram Bot API User 对象 (可选,当 Pyrogram 无法获取用户信息时作为备用)
        bot: Telegram Bot 实例
        mysql_manager: MySQLUserManager 实例（可选，用于查询和保存官方数据）
        force_refresh: 强制跳过所有缓存层，直接查询 Raw API（/cinfo 使用）

    Returns:
        包含以下字段的字典：
        - user_id: 用户 ID
        - full_name: 全名
        - username: 用户名
        - is_premium: Premium 状态
        - dc_id: 数据中心 ID
        - dc_location: 数据中心位置
        - registration_year: 注册年份
        - registration_month: 注册月份
        - registration_source: 数据来源（peersettings/id_estimation/unavailable）
        - account_age_years: 账号年龄（年）
        - account_age_months: 账号年龄（月）
        - cached: 是否来自缓存
        如果获取失败则返回 None
    """
    from utils.pyrofork.client import get_pyrofork_client
    from utils.pyrofork.session import (
        compute_account_age,
        get_cached_user_info,
        save_user_info_to_cache,
    )
    from utils.pyrofork.persistence import (
        get_telegram_reg_from_db,
        save_telegram_reg_to_db,
    )
    from utils.pyrofork.id_estimation import save_registration_sample

    pyrofork_client = get_pyrofork_client()
    pyrofork_connected = pyrofork_client and pyrofork_client.is_connected

    if not pyrofork_connected:
        logger.debug("Pyrofork 未连接，将仅使用 MySQL 和 Bot API 数据")

    try:
        if force_refresh:
            logger.info(f"🔄 [强制刷新] 用户 {user_id}: 跳过缓存，直接查询 Raw API")
        else:
            logger.debug(f"正在获取用户 {user_id} 的完整信息...")

        # 1. 先从 Redis 缓存查询（force_refresh 时跳过）
        if redis_client and not force_refresh:
            cached_data = await get_cached_user_info(redis_client, user_id)
            if cached_data:
                logger.debug(f"从缓存获取用户 {user_id} 的信息")
                cached_data["cached"] = True
                return cached_data

        # 2. 缓存未命中，分别查询多个数据源（每个数据源独立处理异常）
        logger.debug("缓存未命中，正在查询多个数据源...")

        # 初始化用户信息字典
        user_info = {
            "user_id": user_id,
            "full_name": None,
            "username": None,
            "dc_id": None,
            "dc_location": None,
            "is_premium": False,
            "registration_year": None,
            "registration_month": None,
            "registration_source": None,
            "account_age_years": 0,
            "account_age_months": 0,
            "phone_country": None,
            "name_change_date": None,
            "photo_change_date": None,
        }

        # 2.0 优先从 MySQL 查询准确数据（force_refresh 时跳过，直接走 Raw API）
        if mysql_manager and not force_refresh:
            try:
                db_data = await get_telegram_reg_from_db(mysql_manager, user_id)
                if db_data:  # 有官方数据
                    logger.debug(
                        f"✅ [MySQL] 从数据库获取用户 {user_id} 的官方注册数据"
                    )
                    # 使用数据库中的准确数据
                    user_info["registration_year"] = db_data["registration_year"]
                    user_info["registration_month"] = db_data["registration_month"]
                    user_info["registration_source"] = "peersettings"  # 标记为官方数据
                    user_info["dc_id"] = db_data["dc_id"]
                    user_info["is_premium"] = db_data["is_premium"]

                    # 计算账号年龄
                    years, months = compute_account_age(
                        db_data["registration_year"],
                        db_data["registration_month"],
                    )
                    user_info["account_age_years"] = years
                    user_info["account_age_months"] = months

                    # 如果有 DC 信息，设置位置
                    if user_info["dc_id"]:
                        user_info["dc_location"] = DC_LOCATIONS.get(
                            user_info["dc_id"],
                            f"Unknown DC{user_info['dc_id']}",
                        )
            except Exception as e:
                logger.warning(
                    f"⚠️ [MySQL] 查询注册信息失败: {e}, 将继续尝试其他数据源"
                )

        # 2.1 获取 DC 和 Premium 信息（包含注册年月，来自 Raw API）
        # 仅当 MySQL 中没有准确数据时才查询
        if not user_info.get("registration_year"):
            if pyrofork_connected:
                try:
                    dc_premium_info = await get_user_dc_and_premium(user_id, bot=bot)
                    if dc_premium_info:
                        user_info["dc_id"] = dc_premium_info.get("dc_id")
                        user_info["dc_location"] = dc_premium_info.get("dc_location")
                        user_info["is_premium"] = dc_premium_info.get(
                            "is_premium", False
                        )

                        # 从 Raw API 提取基本信息（避免后续重复调用 get_users）
                        if dc_premium_info.get("full_name"):
                            user_info["full_name"] = dc_premium_info["full_name"]
                        if dc_premium_info.get("username"):
                            user_info["username"] = dc_premium_info["username"]

                        # 从 Raw API 获取注册年月
                        registration_year = dc_premium_info.get("registration_year")
                        registration_month = dc_premium_info.get("registration_month")
                        registration_source = dc_premium_info.get("registration_source")

                        # ⚠️ 关键逻辑：只有 PeerSettings 官方数据才保存到 MySQL
                        if (
                            mysql_manager
                            and registration_year
                            and registration_source == "peersettings"
                        ):
                            await save_telegram_reg_to_db(
                                mysql_manager,
                                user_id,
                                registration_year,
                                registration_month,
                                dc_premium_info.get("dc_id"),
                                dc_premium_info.get("is_premium", False),
                            )
                            logger.info(
                                f"✅ 已保存用户 {user_id} 的官方注册数据到数据库"
                            )

                            # 保存到 ID-时间映射表，用于改进 ID 推测算法
                            if redis_client:
                                registration_date = datetime(
                                    registration_year, registration_month, 1
                                )
                                await save_registration_sample(
                                    redis_client, user_id, registration_date
                                )
                        elif registration_source == "id_estimation":
                            logger.debug(
                                f"ℹ️ 用户 {user_id} 使用 ID 推测数据（不持久化）"
                            )

                        # 填充 user_info（无论是官方数据还是推测数据）
                        user_info["registration_year"] = registration_year
                        user_info["registration_month"] = registration_month
                        user_info["registration_source"] = registration_source

                        # 透传 PeerSettings 附加字段
                        user_info["phone_country"] = dc_premium_info.get(
                            "phone_country"
                        )
                        user_info["name_change_date"] = dc_premium_info.get(
                            "name_change_date"
                        )
                        user_info["photo_change_date"] = dc_premium_info.get(
                            "photo_change_date"
                        )

                        # 如果获取到注册年月,计算账号年龄
                        if registration_year and registration_month:
                            years, months = compute_account_age(
                                registration_year, registration_month
                            )
                            user_info["account_age_years"] = years
                            user_info["account_age_months"] = months
                            logger.debug(
                                f"✅ 成功获取用户 {user_id} 的完整信息 "
                                f"(注册时间: {registration_year}年{registration_month}月)"
                            )
                        else:
                            logger.debug(
                                f"✅ 成功获取用户 {user_id} 的 DC 和 Premium 信息"
                            )
                    else:
                        logger.warning(
                            f"⚠️ 未获取到用户 {user_id} 的 DC 和 Premium 信息"
                        )
                except Exception as e:
                    logger.warning(
                        f"⚠️ 获取用户 {user_id} 的 DC 和 Premium 信息时出错: {e}"
                    )

            # Pyrofork 未连接时，仍尝试从头像 file_id 提取 DC（不依赖 Pyrofork）
            if not user_info.get("dc_id") and bot:
                try:
                    from utils.pyrofork.dc_extractor import get_dc_from_profile_photo

                    dc_id = await get_dc_from_profile_photo(bot, user_id)
                    if dc_id:
                        user_info["dc_id"] = dc_id
                        user_info["dc_location"] = DC_LOCATIONS.get(
                            dc_id, f"Unknown DC{dc_id}"
                        )
                        logger.debug(
                            f"✅ [头像 file_id] 获取到用户 {user_id} DC: DC{dc_id}"
                        )
                except Exception as e:
                    logger.debug(f"从头像提取 DC 失败: {e}")

        # 2.2 获取基本用户信息（姓名、用户名）
        # 优先从 Bot API User 对象获取（始终最新）
        if user:
            try:
                user_info["full_name"] = (
                    f"{user.first_name or ''} {user.last_name or ''}".strip()
                )
                user_info["username"] = user.username
                logger.debug(
                    f"✅ 成功从 Bot API User 对象获取用户 {user_id} 的基本信息"
                )
            except Exception as e:
                logger.warning(
                    f"⚠️ 从 Bot API User 对象获取基本信息失败: {e}, 尝试 Pyrogram..."
                )

        # 如果仍无基本信息，尝试从 Pyrofork 获取
        if not user_info.get("full_name") and pyrofork_connected:
            try:
                user_basic = await pyrofork_client.get_users(user_id)
                user_info["full_name"] = (
                    f"{user_basic.first_name or ''} {user_basic.last_name or ''}".strip()
                )
                if not user_info.get("username"):
                    user_info["username"] = user_basic.username
                logger.debug(f"✅ 成功从 Pyrofork 获取用户 {user_id} 的基本信息")
            except Exception as e:
                logger.warning(f"⚠️ 无法从 Pyrofork 获取用户 {user_id} 的基本信息: {e}")
                # 继续执行，不影响其他数据源

        # 2.3 兜底：如果以上数据源均未获取到注册年月，使用 ID 推测算法
        if not user_info.get("registration_year"):
            try:
                from utils.pyrofork.id_estimation import estimate_registration_date

                estimated_date = await estimate_registration_date(user_id)
                if estimated_date:
                    user_info["registration_year"] = estimated_date.year
                    user_info["registration_month"] = estimated_date.month
                    user_info["registration_source"] = "id_estimation"

                    years, months = compute_account_age(
                        estimated_date.year, estimated_date.month
                    )
                    user_info["account_age_years"] = years
                    user_info["account_age_months"] = months
                    logger.debug(
                        f"✅ [ID 推测兜底] 用户 {user_id} 估算注册时间: "
                        f"{estimated_date.year}年{estimated_date.month}月"
                    )
                else:
                    logger.warning(f"⚠️ ID 推测算法也无法估算用户 {user_id} 的注册时间")
            except Exception as e:
                logger.warning(f"⚠️ ID 推测算法异常: {e}")

        # 4. 保存到 Redis 缓存 (仅当有注册年月时)
        if redis_client and user_info.get("registration_year"):
            # 保存用户完整信息缓存
            await save_user_info_to_cache(redis_client, user_id, user_info)

        user_info["cached"] = False
        logger.debug(
            f"成功获取用户 {user_id} 的完整信息，" f"包含字段: {list(user_info.keys())}"
        )
        return user_info

    except Exception as e:
        logger.error(f"获取用户 {user_id} 信息时发生错误: {e}", exc_info=True)
        return None
