"""
数据库初始化检查和执行
"""

import logging

import aiomysql

logger = logging.getLogger(__name__)


async def check_and_init_database(config) -> bool:
    """
    检查数据库是否已初始化，如果没有则执行初始化

    Args:
        config: 配置对象

    Returns:
        bool: 是否成功初始化
    """
    try:
        # 连接到 MySQL（不指定数据库）
        conn = await aiomysql.connect(
            host=config.db_host,
            port=config.db_port,
            user=config.db_user,
            password=config.db_password,
            charset="utf8mb4",
        )

        async with conn.cursor() as cursor:
            # 检查数据库是否存在
            await cursor.execute(
                "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s",
                (config.db_name,),
            )
            db_exists = await cursor.fetchone()

            if not db_exists:
                logger.info(f"数据库 {config.db_name} 不存在，正在创建...")
                await cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS {config.db_name} "
                    "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
                await conn.commit()
                logger.info(f"✅ 数据库 {config.db_name} 创建成功")

            # 切换到目标数据库
            await cursor.execute(f"USE {config.db_name}")

            # 定义核心表列表
            core_tables = [
                "users",
                "admin_permissions",
                "super_admins",
                "user_whitelist",
                "group_whitelist",
                "admin_logs",
                "command_stats",
                "price_history",
            ]

            # 检查核心表是否存在
            placeholders = ",".join(["%s"] * len(core_tables))
            await cursor.execute(
                f"SELECT COUNT(*) FROM information_schema.TABLES "
                f"WHERE TABLE_SCHEMA = %s AND TABLE_NAME IN ({placeholders})",
                (config.db_name, *core_tables),
            )
            table_count = (await cursor.fetchone())[0]

            if table_count < len(core_tables):  # 如果表不完整
                logger.info("检测到数据库表不完整，正在初始化...")

                # 使用 Python 代码创建所有表
                await create_basic_tables(cursor)
                await conn.commit()

                # 验证表是否成功创建
                await cursor.execute(
                    f"SELECT COUNT(*) FROM information_schema.TABLES "
                    f"WHERE TABLE_SCHEMA = %s AND TABLE_NAME IN ({placeholders})",
                    (config.db_name, *core_tables),
                )
                verified_count = (await cursor.fetchone())[0]

                if verified_count == len(core_tables):
                    logger.info(
                        f"✅ 数据库初始化验证通过：{verified_count}/{len(core_tables)} 核心表存在"
                    )
                else:
                    logger.error(
                        f"❌ 数据库初始化验证失败：仅创建了 {verified_count}/{len(core_tables)} 个核心表"
                    )
                    conn.close()
                    return False
            else:
                logger.info("✅ 数据库已初始化")

            # 检查并更新索引
            await check_and_update_indexes(cursor)

        conn.close()
        return True

    except Exception as e:
        logger.error(f"数据库初始化检查失败: {e}")
        return False


async def create_basic_tables(cursor) -> None:
    """
    创建所有数据库表和视图

    按照依赖顺序创建：
    1. users（基础表，无依赖）
    2. 依赖 users 的表（admin_permissions, super_admins, user_whitelist）
    3. 独立表（group_whitelist, admin_logs, command_stats, price_history）
    4. 视图（active_admins）
    """
    try:
        # 1. 用户表（基础表）
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                first_name VARCHAR(255),
                last_name VARCHAR(255),
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                telegram_reg_year INT COMMENT 'Telegram 账号注册年份（仅官方数据）',
                telegram_reg_month INT COMMENT 'Telegram 账号注册月份(1-12)（仅官方数据）',
                dc_id INT COMMENT '数据中心 ID (1-5)',
                is_premium BOOLEAN DEFAULT FALSE COMMENT 'Premium 会员状态',
                telegram_info_updated_at TIMESTAMP NULL COMMENT 'Telegram 信息最后更新时间',
                INDEX idx_username (username),
                INDEX idx_last_seen (last_seen),
                INDEX idx_telegram_reg (telegram_reg_year, telegram_reg_month),
                INDEX idx_dc_id (dc_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        logger.info("✅ users 表创建成功")

        # 2. 管理员权限表（依赖 users）
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_permissions (
                user_id BIGINT PRIMARY KEY,
                granted_by BIGINT NOT NULL,
                granted_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_granted_by (granted_by),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        logger.info("✅ admin_permissions 表创建成功")

        # 3. 超级管理员表（依赖 users）
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS super_admins (
                user_id BIGINT PRIMARY KEY,
                added_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        logger.info("✅ super_admins 表创建成功")

        # 4. 用户白名单表（依赖 users）
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_whitelist (
                user_id BIGINT PRIMARY KEY,
                added_by BIGINT NOT NULL,
                added_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_added_by (added_by),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        logger.info("✅ user_whitelist 表创建成功")

        # 5. 群组白名单表（独立表）
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS group_whitelist (
                group_id BIGINT PRIMARY KEY,
                group_name VARCHAR(255),
                added_by BIGINT NOT NULL,
                added_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_added_by (added_by)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        logger.info("✅ group_whitelist 表创建成功")

        # 6. 管理员操作日志表（独立表）
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_logs (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                admin_id BIGINT NOT NULL,
                action VARCHAR(100) NOT NULL,
                target_type VARCHAR(50),
                target_id BIGINT,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_admin_id (admin_id),
                INDEX idx_action (action),
                INDEX idx_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        logger.info("✅ admin_logs 表创建成功")

        # 7. 命令使用统计表（独立表）
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS command_stats (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                command VARCHAR(50) NOT NULL,
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                chat_type VARCHAR(20),
                executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_command (command),
                INDEX idx_user_id (user_id),
                INDEX idx_executed_at (executed_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        logger.info("✅ command_stats 表创建成功")

        # 8. 价格历史表（独立表）
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                service VARCHAR(50) NOT NULL COMMENT '服务名称: steam/app_store/netflix/spotify/disney/max等',
                item_id VARCHAR(255) NOT NULL COMMENT '商品ID: 游戏ID/应用ID',
                item_name VARCHAR(500) COMMENT '商品名称',
                country_code CHAR(2) COMMENT '国家代码: CN/US/TR等',
                currency CHAR(3) COMMENT '货币代码: CNY/USD/EUR等',
                original_price DECIMAL(10,2) COMMENT '原价',
                current_price DECIMAL(10,2) COMMENT '当前价格/折扣价',
                discount_percent INT COMMENT '折扣百分比: 0-100',
                price_cny DECIMAL(10,2) COMMENT 'CNY等值价格',
                extra_data JSON COMMENT '额外数据: 平台/版本/套餐类型等',
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '记录时间',
                INDEX idx_service_item (service, item_id) COMMENT '按服务和商品ID查询',
                INDEX idx_service_item_country (service, item_id, country_code) COMMENT '按服务、商品和国家查询',
                INDEX idx_recorded_at (recorded_at) COMMENT '按时间查询',
                INDEX idx_service_item_country_time (service, item_id, country_code, recorded_at DESC) COMMENT '复合索引-覆盖常用查询'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='价格历史记录表'
        """)
        logger.info("✅ price_history 表创建成功")

        # 9. 创建视图：活跃管理员（包括超级管理员）
        await cursor.execute("""
            CREATE OR REPLACE VIEW active_admins AS
            SELECT u.user_id, u.username, u.first_name, u.last_name,
                   CASE WHEN sa.user_id IS NOT NULL THEN 'super_admin' ELSE 'admin' END as admin_type
            FROM users u
            LEFT JOIN admin_permissions ap ON u.user_id = ap.user_id
            LEFT JOIN super_admins sa ON u.user_id = sa.user_id
            WHERE ap.user_id IS NOT NULL OR sa.user_id IS NOT NULL
        """)
        logger.info("✅ active_admins 视图创建成功")

        logger.info("✅ 数据库表和视图创建完成")

    except Exception as e:
        logger.error(f"❌ 创建数据库表时发生错误: {e}")
        raise


async def check_and_update_indexes(cursor) -> None:
    """
    检查并更新数据库索引
    特别是为了性能优化添加的唯一索引
    """
    try:
        # 检查 price_history 表的 uk_service_item_country_date 索引是否存在
        await cursor.execute("""
            SELECT COUNT(1) IndexIsThere 
            FROM INFORMATION_SCHEMA.STATISTICS 
            WHERE table_schema = DATABASE() 
            AND table_name = 'price_history' 
            AND index_name = 'uk_service_item_country_date'
            """)
        result = await cursor.fetchone()

        if result[0] == 0:
            logger.info("正在为 price_history 表添加唯一索引（性能优化）...")
            try:
                # 使用函数索引 (MySQL 8.0.13+)
                await cursor.execute("""
                    CREATE UNIQUE INDEX uk_service_item_country_date 
                    ON price_history (service, item_id, country_code, (CAST(recorded_at AS DATE)))
                    """)
                logger.info("✅ 成功添加唯一索引 uk_service_item_country_date")
            except Exception as e:
                # 可能由于重复数据导致失败
                logger.warning(f"⚠️ 添加唯一索引失败（可能存在重复数据）: {e}")

    except Exception as e:
        logger.error(f"检查索引失败: {e}")
