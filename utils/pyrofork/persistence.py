"""
MySQL 持久化模块

用于保存和查询 Telegram 用户的官方注册信息（来自 PeerSettings）
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


async def save_telegram_reg_to_db(
    mysql_manager,
    user_id: int,
    registration_year: int,
    registration_month: int,
    dc_id: int | None = None,
    is_premium: bool = False,
) -> bool:
    """
    将 Telegram 注册信息保存到 MySQL users 表

    ⚠️ 注意：此函数仅应在获取到 PeerSettings 官方数据时调用
    不应保存 ID 推测的数据

    Args:
        mysql_manager: MySQLUserManager 实例
        user_id: 用户 ID
        registration_year: 注册年份（来自 PeerSettings）
        registration_month: 注册月份（来自 PeerSettings）
        dc_id: 数据中心 ID
        is_premium: Premium 状态

    Returns:
        bool: 保存是否成功
    """
    try:
        async with mysql_manager.get_cursor() as cursor:
            sql = """
            INSERT INTO users (user_id, telegram_reg_year, telegram_reg_month,
                               dc_id, is_premium, telegram_info_updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                telegram_reg_year = VALUES(telegram_reg_year),
                telegram_reg_month = VALUES(telegram_reg_month),
                dc_id = VALUES(dc_id),
                is_premium = VALUES(is_premium),
                telegram_info_updated_at = VALUES(telegram_info_updated_at)
            """

            await cursor.execute(
                sql,
                (
                    user_id,
                    registration_year,
                    registration_month,
                    dc_id,
                    is_premium,
                    datetime.now(),
                ),
            )

            # autocommit=True，不需要手动 commit
            logger.debug(
                f"✅ [MySQL] 已保存用户 {user_id} 的官方注册信息 "
                f"({registration_year}年{registration_month}月, 来源: PeerSettings)"
            )
            return True

    except Exception as e:
        logger.error(f"❌ [MySQL] 保存注册信息失败: {e}", exc_info=True)
        return False


async def get_telegram_reg_from_db(mysql_manager, user_id: int) -> dict | None:
    """
    从 MySQL users 表查询 Telegram 注册信息

    返回的数据均为 PeerSettings 官方数据（telegram_reg_year 非空时）

    Args:
        mysql_manager: MySQLUserManager 实例
        user_id: 用户 ID

    Returns:
        包含注册信息的字典，如果未获取到官方数据则返回 None
        {
            "registration_year": int,
            "registration_month": int,
            "dc_id": int,
            "is_premium": bool,
            "updated_at": datetime
        }
    """
    try:
        async with mysql_manager.get_cursor() as cursor:
            sql = """
            SELECT telegram_reg_year, telegram_reg_month,
                   dc_id, is_premium, telegram_info_updated_at
            FROM users
            WHERE user_id = %s
            """

            await cursor.execute(sql, (user_id,))
            row = await cursor.fetchone()

            if row and row["telegram_reg_year"] is not None:
                return {
                    "registration_year": row["telegram_reg_year"],
                    "registration_month": row["telegram_reg_month"],
                    "dc_id": row["dc_id"],
                    "is_premium": row["is_premium"],
                    "updated_at": row["telegram_info_updated_at"],
                }

            return None

    except Exception as e:
        logger.error(f"❌ [MySQL] 查询注册信息失败: {e}", exc_info=True)
        return None
