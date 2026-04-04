"""
用户权限管理器

权限数据（管理员、白名单）存储在 Redis HASH 中，按 bot_id 隔离。
用户信息缓存保留在 MySQL users 表（共享数据）。

Redis 数据结构:
    perm:{bot_id}:super_admins  → HASH { user_id: '{"added_time":"..."}' }
    perm:{bot_id}:admins        → HASH { user_id: '{"granted_by":123,"granted_time":"..."}' }
    perm:{bot_id}:user_wl       → HASH { user_id: '{"added_by":123,"added_time":"..."}' }
    perm:{bot_id}:group_wl      → HASH { group_id: '{"group_name":"...","added_by":123,"added_time":"..."}' }
"""

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from aiomysql import DictCursor, create_pool

logger = logging.getLogger(__name__)


class MySQLUserManager:
    """用户权限管理器（Redis 权限 + MySQL 用户信息缓存）"""

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        redis_client=None,
        bot_id: int = 0,
    ):
        """初始化

        Args:
            host: MySQL 主机
            port: MySQL 端口
            database: 数据库名
            user: MySQL 用户
            password: MySQL 密码
            redis_client: Redis 异步客户端实例
            bot_id: Bot ID，用于 Redis key 隔离
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.pool = None
        self._connected = False

        # Redis 权限存储
        self._redis = redis_client
        self._bot_id = bot_id
        self._prefix = f"perm:{bot_id}"

    async def connect(self):
        """创建 MySQL 连接池并初始化 Redis 权限数据"""
        try:
            from utils.config_manager import get_config

            config = get_config()

            self.pool = await create_pool(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.database,
                charset="utf8mb4",
                autocommit=True,
                minsize=config.db_min_connections,
                maxsize=config.db_max_connections,
                echo=False,
                cursorclass=DictCursor,
            )
            self._connected = True
            logger.info("✅ MySQL 连接池创建成功")

            # 初始化超级管理员到 Redis
            await self._init_super_admin()

        except Exception as e:
            logger.error(f"❌ MySQL 连接失败: {e}")
            raise

    async def close(self):
        """关闭连接池"""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            self._connected = False
            logger.info("MySQL 连接池已关闭")

    @asynccontextmanager
    async def get_cursor(self):
        """获取数据库游标的上下文管理器"""
        async with self.pool.acquire() as conn, conn.cursor(DictCursor) as cursor:
            yield cursor

    # ========================================
    # 超级管理员初始化
    # ========================================

    async def _init_super_admin(self):
        """从环境变量同步超级管理员到 Redis，同时确保 MySQL users 表有记录"""
        if not self._redis:
            raise RuntimeError("Redis 未初始化，无法同步超级管理员权限")

        from utils.config_manager import get_config

        config = get_config()

        if not config.super_admin_ids:
            return

        now = datetime.now().isoformat()
        key = f"{self._prefix}:super_admins"

        for admin_id in config.super_admin_ids:
            try:
                # 写入 Redis HASH
                meta = json.dumps({"added_time": now})
                await self._redis.hset(key, str(admin_id), meta)

                # 确保 MySQL users 表有记录（用户信息缓存）
                async with self.get_cursor() as cursor:
                    await cursor.execute(
                        "INSERT IGNORE INTO users (user_id) VALUES (%s)",
                        (admin_id,),
                    )

                logger.info(f"✅ 超级管理员已同步到 Redis: {admin_id}")

            except Exception as e:
                logger.error(f"❌ 初始化超级管理员失败: {admin_id}, {e}")
                raise RuntimeError(f"初始化超级管理员失败: {e}") from e

        logger.info(
            f"✅ 已初始化 {len(config.super_admin_ids)} 个超级管理员 "
            f"(bot_id={self._bot_id})"
        )

    # ========================================
    # 用户信息缓存（MySQL，共享数据）
    # ========================================

    async def update_user_cache(
        self,
        user_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ):
        """更新用户信息缓存到 MySQL users 表"""
        if not self._connected:
            logger.warning("MySQL 未连接")
            return

        try:
            async with self.get_cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO users (user_id, username, first_name, last_name, last_seen)
                    VALUES (%s, %s, %s, %s, NOW()) AS new_user
                    ON DUPLICATE KEY UPDATE
                        username = new_user.username,
                        first_name = new_user.first_name,
                        last_name = new_user.last_name,
                        last_seen = NOW()
                """,
                    (user_id, username, first_name, last_name),
                )

            logger.debug(f"用户缓存已更新: {user_id}")

        except Exception as e:
            logger.error(f"更新用户缓存失败: {e}")

    async def get_user_from_cache(self, user_id: int) -> dict | None:
        """从 MySQL 获取用户信息"""
        if not self._connected:
            return None

        try:
            async with self.get_cursor() as cursor:
                await cursor.execute(
                    "SELECT user_id, username, first_name, last_name FROM users WHERE user_id = %s",
                    (user_id,),
                )
                return await cursor.fetchone()

        except Exception as e:
            logger.error(f"获取用户缓存失败: {e}")
            return None

    async def get_user_by_username(self, username: str) -> dict | None:
        """通过用户名获取用户信息"""
        if not self._connected:
            return None

        try:
            async with self.get_cursor() as cursor:
                await cursor.execute(
                    "SELECT user_id, username, first_name, last_name FROM users WHERE username = %s",
                    (username,),
                )
                return await cursor.fetchone()

        except Exception as e:
            logger.error(f"通过用户名获取用户失败: {e}")
            return None

    # ========================================
    # 权限读取（Redis HEXISTS，O(1)）
    # ========================================

    async def is_admin(self, user_id: int) -> bool:
        """检查是否为管理员（超级管理员 或 普通管理员）"""
        try:
            uid = str(user_id)
            if await self._redis.hexists(f"{self._prefix}:super_admins", uid):
                return True
            return await self._redis.hexists(f"{self._prefix}:admins", uid)
        except Exception as e:
            logger.error(f"检查管理员权限失败: {e}")
            return False

    async def is_super_admin(self, user_id: int) -> bool:
        """检查是否为超级管理员"""
        try:
            return await self._redis.hexists(
                f"{self._prefix}:super_admins", str(user_id)
            )
        except Exception as e:
            logger.error(f"检查超级管理员权限失败: {e}")
            return False

    async def is_whitelisted(self, user_id: int) -> bool:
        """检查用户是否在白名单中"""
        try:
            return await self._redis.hexists(f"{self._prefix}:user_wl", str(user_id))
        except Exception as e:
            logger.error(f"检查用户白名单失败: {e}")
            return False

    async def is_group_whitelisted(self, group_id: int) -> bool:
        """检查群组是否在白名单中"""
        # 先查内存中的静态配置
        from utils.config_manager import get_config

        config = get_config()
        if group_id in config.whitelisted_groups:
            return True

        try:
            return await self._redis.hexists(f"{self._prefix}:group_wl", str(group_id))
        except Exception as e:
            logger.error(f"检查群组白名单失败: {e}")
            return False

    # ========================================
    # 权限写入（Redis HSET/HDEL）
    # ========================================

    async def add_admin(self, user_id: int, granted_by: int) -> bool:
        """添加管理员"""
        try:
            meta = json.dumps(
                {
                    "granted_by": granted_by,
                    "granted_time": datetime.now().isoformat(),
                }
            )
            await self._redis.hset(f"{self._prefix}:admins", str(user_id), meta)

            # 确保 MySQL users 表有记录
            if self._connected:
                async with self.get_cursor() as cursor:
                    await cursor.execute(
                        "INSERT IGNORE INTO users (user_id) VALUES (%s)", (user_id,)
                    )

            logger.info(f"管理员已添加: {user_id}")
            return True

        except Exception as e:
            logger.error(f"添加管理员失败: {e}")
            return False

    async def remove_admin(self, user_id: int) -> bool:
        """移除管理员"""
        try:
            await self._redis.hdel(f"{self._prefix}:admins", str(user_id))
            logger.info(f"管理员已移除: {user_id}")
            return True

        except Exception as e:
            logger.error(f"移除管理员失败: {e}")
            return False

    async def add_to_whitelist(self, user_id: int, added_by: int) -> bool:
        """添加用户到白名单"""
        try:
            meta = json.dumps(
                {
                    "added_by": added_by,
                    "added_time": datetime.now().isoformat(),
                }
            )
            await self._redis.hset(f"{self._prefix}:user_wl", str(user_id), meta)

            # 确保 MySQL users 表有记录
            if self._connected:
                async with self.get_cursor() as cursor:
                    await cursor.execute(
                        "INSERT IGNORE INTO users (user_id) VALUES (%s)", (user_id,)
                    )

            logger.info(f"用户已添加到白名单: {user_id}")
            return True

        except Exception as e:
            logger.error(f"添加到白名单失败: {e}")
            return False

    async def remove_from_whitelist(self, user_id: int) -> bool:
        """从白名单移除用户"""
        try:
            await self._redis.hdel(f"{self._prefix}:user_wl", str(user_id))
            logger.info(f"用户已从白名单移除: {user_id}")
            return True

        except Exception as e:
            logger.error(f"从白名单移除失败: {e}")
            return False

    async def add_group_to_whitelist(
        self, group_id: int, group_name: str | None, added_by: int
    ) -> bool:
        """添加群组到白名单"""
        try:
            meta = json.dumps(
                {
                    "group_name": group_name,
                    "added_by": added_by,
                    "added_time": datetime.now().isoformat(),
                }
            )
            await self._redis.hset(f"{self._prefix}:group_wl", str(group_id), meta)
            logger.info(f"群组已添加到白名单: {group_id}")
            return True

        except Exception as e:
            logger.error(f"添加群组到白名单失败: {e}")
            return False

    async def remove_group_from_whitelist(self, group_id: int) -> bool:
        """从白名单移除群组"""
        try:
            await self._redis.hdel(f"{self._prefix}:group_wl", str(group_id))
            logger.info(f"群组已从白名单移除: {group_id}")
            return True

        except Exception as e:
            logger.error(f"从白名单移除群组失败: {e}")
            return False

    # ========================================
    # 列表查询（Redis HGETALL + MySQL 补全）
    # ========================================

    async def get_all_admins(self) -> list[int]:
        """获取所有管理员 ID 列表（超级管理员 + 普通管理员）"""
        try:
            super_ids = await self._redis.hkeys(f"{self._prefix}:super_admins")
            admin_ids = await self._redis.hkeys(f"{self._prefix}:admins")

            # 合并去重
            all_ids = set()
            for uid in super_ids:
                all_ids.add(int(uid.decode() if isinstance(uid, bytes) else uid))
            for uid in admin_ids:
                all_ids.add(int(uid.decode() if isinstance(uid, bytes) else uid))

            return list(all_ids)

        except Exception as e:
            logger.error(f"获取管理员列表失败: {e}")
            return []

    async def get_whitelisted_users(self) -> list[dict]:
        """获取白名单用户列表（含用户名称，从 MySQL 补全）"""
        try:
            wl_data = await self._redis.hgetall(f"{self._prefix}:user_wl")

            if not wl_data:
                return []

            # 提取所有 user_id
            user_ids = []
            for uid in wl_data:
                uid_str = uid.decode() if isinstance(uid, bytes) else uid
                user_ids.append(int(uid_str))

            # 批量从 MySQL users 表查询用户信息
            user_info_map = {}
            if self._connected and user_ids:
                try:
                    placeholders = ",".join(["%s"] * len(user_ids))
                    async with self.get_cursor() as cursor:
                        await cursor.execute(
                            f"SELECT user_id, username, first_name, last_name "
                            f"FROM users WHERE user_id IN ({placeholders})",
                            tuple(user_ids),
                        )
                        for row in await cursor.fetchall():
                            user_info_map[row["user_id"]] = row
                except Exception as e:
                    logger.warning(f"从 MySQL 补全用户信息失败: {e}")

            # 组装结果
            results = []
            for uid in sorted(user_ids):
                info = user_info_map.get(uid, {})
                results.append(
                    {
                        "user_id": uid,
                        "username": info.get("username"),
                        "first_name": info.get("first_name"),
                        "last_name": info.get("last_name"),
                    }
                )

            return results

        except Exception as e:
            logger.error(f"获取白名单用户失败: {e}")
            return []

    async def get_whitelisted_groups(self) -> list[dict]:
        """获取白名单群组列表（Redis + 静态配置合并）"""
        try:
            wl_data = await self._redis.hgetall(f"{self._prefix}:group_wl")

            results = []
            existing_ids = set()

            for gid_raw, meta_raw in wl_data.items():
                gid_str = gid_raw.decode() if isinstance(gid_raw, bytes) else gid_raw
                meta_str = (
                    meta_raw.decode() if isinstance(meta_raw, bytes) else meta_raw
                )
                gid = int(gid_str)
                existing_ids.add(gid)

                meta = json.loads(meta_str)
                results.append(
                    {
                        "group_id": gid,
                        "group_name": meta.get("group_name"),
                    }
                )

            # 合并静态配置中的白名单群组
            from utils.config_manager import get_config

            config = get_config()
            for gid in config.whitelisted_groups:
                if gid not in existing_ids:
                    results.append(
                        {
                            "group_id": gid,
                            "group_name": "📜 配置文件白名单",
                        }
                    )

            return results

        except Exception as e:
            logger.error(f"获取白名单群组失败: {e}")
            return []
