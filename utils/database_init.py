"""
数据库初始化检查和执行
"""

import logging
from pathlib import Path

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
                "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s", (config.db_name,)
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

            # 检查表是否存在
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME IN ('users', 'admin_permissions', 'user_whitelist', 'group_whitelist')",
                (config.db_name,),
            )
            table_count = (await cursor.fetchone())[0]

            if table_count < 4:  # 如果表不完整
                logger.info("检测到数据库表不完整，正在初始化...")

                # 读取并执行初始化 SQL
                init_sql_path = Path(__file__).parent.parent / "database" / "init.sql"
                if init_sql_path.exists():
                    with open(init_sql_path, encoding="utf-8") as f:
                        sql_content = f.read()

                    # 分割 SQL 语句并逐个执行
                    sql_statements = [s.strip() for s in sql_content.split(";") if s.strip()]

                    for statement in sql_statements:
                        if statement:
                            try:
                                # 跳过注释和空行
                                if not statement.startswith("--") and not statement.startswith("/*"):
                                    # 处理 DELIMITER 语句
                                    if "DELIMITER" in statement:
                                        continue
                                    await cursor.execute(statement)
                            except Exception as e:
                                # 忽略某些可以忽略的错误（如表已存在）
                                if "already exists" not in str(e):
                                    logger.warning(f"执行 SQL 语句时出现警告: {e}")

                    await conn.commit()
                    logger.info("✅ 数据库表初始化完成")
                else:
                    logger.warning("未找到 init.sql 文件，跳过数据库初始化")
                    # 即使没有 init.sql，也尝试创建基本表
                    await create_basic_tables(cursor)
                    await conn.commit()
            else:
                logger.info("✅ 数据库已初始化")

        conn.close()
        return True

    except Exception as e:
        logger.error(f"数据库初始化检查失败: {e}")
        return False


async def create_basic_tables(cursor):
    """创建基本的数据库表"""
    # 用户表
    await cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username VARCHAR(255),
            first_name VARCHAR(255),
            last_name VARCHAR(255),
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_username (username),
            INDEX idx_last_seen (last_seen)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 管理员权限表
    await cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_permissions (
            user_id BIGINT PRIMARY KEY,
            granted_by BIGINT NOT NULL,
            granted_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_granted_by (granted_by),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 超级管理员表
    await cursor.execute("""
        CREATE TABLE IF NOT EXISTS super_admins (
            user_id BIGINT PRIMARY KEY,
            added_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 用户白名单表
    await cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_whitelist (
            user_id BIGINT PRIMARY KEY,
            added_by BIGINT NOT NULL,
            added_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_added_by (added_by),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 群组白名单表
    await cursor.execute("""
        CREATE TABLE IF NOT EXISTS group_whitelist (
            group_id BIGINT PRIMARY KEY,
            group_name VARCHAR(255),
            added_by BIGINT NOT NULL,
            added_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_added_by (added_by)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    logger.info("✅ 基本数据库表创建完成")
