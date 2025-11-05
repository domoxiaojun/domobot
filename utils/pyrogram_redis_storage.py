"""
Pyrogram Redis 存储适配器

使用 Redis 存储 Pyrogram 会话数据，避免文件系统依赖。
"""

import base64
import logging
from typing import List

from pyrogram import raw, utils
from pyrogram.storage import Storage
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


def get_input_peer(peer_id: int, access_hash: int, peer_type: str):
    """
    根据 peer 信息构造 InputPeer 对象。

    Args:
        peer_id: 对等点 ID
        access_hash: 访问哈希
        peer_type: 对等点类型 ("user", "bot", "group", "channel", "supergroup")

    Returns:
        InputPeerUser, InputPeerChat 或 InputPeerChannel 对象
    """
    if peer_type in ["user", "bot"]:
        return raw.types.InputPeerUser(
            user_id=peer_id,
            access_hash=access_hash
        )

    if peer_type == "group":
        return raw.types.InputPeerChat(
            chat_id=-peer_id
        )

    if peer_type in ["channel", "supergroup"]:
        return raw.types.InputPeerChannel(
            channel_id=utils.get_channel_id(peer_id),
            access_hash=access_hash
        )

    raise ValueError(f"Invalid peer type: {peer_type}")


class RedisStorage(Storage):
    """
    Redis 存储后端，用于 Pyrogram 会话管理。

    数据结构:
    - pyrogram:session:{name}:dc_id -> String (数据中心 ID)
    - pyrogram:session:{name}:auth_key -> String (Base64 编码的认证密钥)
    - pyrogram:session:{name}:user_id -> String (用户 ID)
    - pyrogram:session:{name}:is_bot -> String (是否为机器人)
    - pyrogram:session:{name}:date -> String (会话创建时间)
    - pyrogram:session:{name}:test_mode -> String (是否为测试模式)
    - pyrogram:session:{name}:peers -> Hash (对等点缓存: peer_id -> peer_data)
    - pyrogram:session:{name}:usernames -> Hash (用户名缓存: username -> peer_id)
    - pyrogram:session:{name}:phone_numbers -> Hash (电话号码缓存: phone -> peer_id)
    """

    def __init__(self, redis_client: Redis, name: str):
        """
        初始化 Redis 存储。

        Args:
            redis_client: Redis 客户端实例
            name: 会话名称（用于生成 Redis 键）
        """
        super().__init__(name)
        self.redis_client = redis_client
        self.name = name

        # Redis 键前缀
        self._key_prefix = f"pyrogram:session:{name}"

    def _key(self, field: str) -> str:
        """生成 Redis 键"""
        return f"{self._key_prefix}:{field}"

    def _decode_redis_value(self, value):
        """解码 Redis 返回值（处理 bytes 和 str 两种情况）"""
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value

    async def open(self):
        """打开存储连接"""
        logger.info(f"Pyrogram Redis 存储已打开: {self.name}")

    async def save(self):
        """保存会话数据（Redis 自动持久化，此方法为空）"""
        pass

    async def close(self):
        """关闭存储连接"""
        logger.info(f"Pyrogram Redis 存储已关闭: {self.name}")

    async def delete(self):
        """删除所有会话数据"""
        keys = await self.redis_client.keys(f"{self._key_prefix}:*")
        if keys:
            await self.redis_client.delete(*keys)
            logger.info(f"已删除 Pyrogram 会话数据: {self.name}")

    async def update(self):
        """更新会话数据（Redis 自动更新，此方法为空）"""
        pass

    # ==================== DC ID ====================

    async def dc_id(self, value: int = object):
        """获取或设置数据中心 ID"""
        if value is object:
            # 获取
            dc_id_str = self._decode_redis_value(
                await self.redis_client.get(self._key("dc_id"))
            )
            return int(dc_id_str) if dc_id_str else None
        else:
            # 设置
            if value is None:
                await self.redis_client.delete(self._key("dc_id"))
            else:
                await self.redis_client.set(self._key("dc_id"), str(value))

    # ==================== Auth Key ====================

    async def auth_key(self, value: bytes = object):
        """获取或设置认证密钥"""
        if value is object:
            # 获取
            auth_key_b64 = await self.redis_client.get(self._key("auth_key"))
            return base64.b64decode(auth_key_b64) if auth_key_b64 else None
        else:
            # 设置
            if value is None:
                await self.redis_client.delete(self._key("auth_key"))
            else:
                # Base64 编码存储
                auth_key_b64 = base64.b64encode(value).decode("utf-8")
                await self.redis_client.set(self._key("auth_key"), auth_key_b64)

    # ==================== Date ====================

    async def date(self, value: int = object):
        """获取或设置会话创建时间"""
        if value is object:
            # 获取
            date_str = self._decode_redis_value(
                await self.redis_client.get(self._key("date"))
            )
            return int(date_str) if date_str else None
        else:
            # 设置
            if value is None:
                await self.redis_client.delete(self._key("date"))
            else:
                await self.redis_client.set(self._key("date"), str(value))

    # ==================== User ID ====================

    async def user_id(self, value: int = object):
        """获取或设置用户 ID"""
        if value is object:
            # 获取
            user_id_str = self._decode_redis_value(
                await self.redis_client.get(self._key("user_id"))
            )
            return int(user_id_str) if user_id_str else None
        else:
            # 设置
            if value is None:
                await self.redis_client.delete(self._key("user_id"))
            else:
                await self.redis_client.set(self._key("user_id"), str(value))

    # ==================== Is Bot ====================

    async def is_bot(self, value: bool = object):
        """获取或设置是否为机器人"""
        if value is object:
            # 获取
            is_bot_str = self._decode_redis_value(
                await self.redis_client.get(self._key("is_bot"))
            )
            return is_bot_str == "1" if is_bot_str else None
        else:
            # 设置
            if value is None:
                await self.redis_client.delete(self._key("is_bot"))
            else:
                await self.redis_client.set(self._key("is_bot"), "1" if value else "0")

    # ==================== Test Mode ====================

    async def test_mode(self, value: bool = object):
        """获取或设置测试模式"""
        if value is object:
            # 获取
            test_mode_str = self._decode_redis_value(
                await self.redis_client.get(self._key("test_mode"))
            )
            return test_mode_str == "1" if test_mode_str else None
        else:
            # 设置
            if value is None:
                await self.redis_client.delete(self._key("test_mode"))
            else:
                await self.redis_client.set(
                    self._key("test_mode"), "1" if value else "0"
                )

    # ==================== Peers 管理 ====================

    async def update_peers(self, peers: List[tuple]):
        """
        更新对等点缓存。

        Args:
            peers: [(peer_id, access_hash, peer_type, username, phone_number), ...]
        """
        if not peers:
            return

        # 准备批量数据
        peers_hash = {}
        usernames_hash = {}
        phone_numbers_hash = {}

        for peer_data in peers:
            peer_id, access_hash, peer_type, username, phone_number = peer_data

            # 存储 peer 数据 (格式: "access_hash,peer_type")
            peers_hash[str(peer_id)] = f"{access_hash},{peer_type}"

            # 存储用户名映射
            if username:
                usernames_hash[username.lower()] = str(peer_id)

            # 存储电话号码映射
            if phone_number:
                phone_numbers_hash[phone_number] = str(peer_id)

        # 批量更新 Redis
        if peers_hash:
            await self.redis_client.hset(self._key("peers"), mapping=peers_hash)
        if usernames_hash:
            await self.redis_client.hset(self._key("usernames"), mapping=usernames_hash)
        if phone_numbers_hash:
            await self.redis_client.hset(
                self._key("phone_numbers"), mapping=phone_numbers_hash
            )

    async def get_peer_by_id(self, peer_id: int):
        """
        通过 ID 获取对等点信息。

        Returns:
            InputPeer 对象 (InputPeerUser/InputPeerChat/InputPeerChannel)

        Raises:
            KeyError: 当缓存中不存在该 peer_id 时
        """
        logger.debug(f"[RedisStorage] 查询 peer_id={peer_id} 的缓存")

        peer_data = await self.redis_client.hget(self._key("peers"), str(peer_id))
        if not peer_data:
            logger.debug(f"[RedisStorage] Peer {peer_id} 不在缓存中,Pyrogram 将通过 API 查询")
            raise KeyError(f"Peer {peer_id} not found in cache")

        # 解析数据（处理 bytes 和 str 两种情况）
        peer_data = self._decode_redis_value(peer_data)
        logger.debug(f"[RedisStorage] 找到缓存数据: {peer_data}")

        parts = peer_data.split(",")

        # 解析 access_hash 和 peer_type
        access_hash = int(parts[0])
        peer_type = parts[1] if len(parts) > 1 else "user"

        logger.debug(f"[RedisStorage] 构造 InputPeer: peer_id={peer_id}, access_hash={access_hash}, type={peer_type}")

        # 返回 InputPeer 对象(使用辅助函数)
        return get_input_peer(peer_id, access_hash, peer_type)

    async def get_peer_by_username(self, username: str):
        """
        通过用户名获取对等点信息。

        Returns:
            (peer_id, access_hash, peer_type, username, phone_number)

        Raises:
            KeyError: 当缓存中不存在该 username 时
        """
        logger.debug(f"[RedisStorage] 查询 username={username} 的缓存")

        peer_id_data = await self.redis_client.hget(
            self._key("usernames"), username.lower()
        )
        if not peer_id_data:
            logger.debug(f"[RedisStorage] Username {username} 不在缓存中")
            raise KeyError(f"Username {username} not found in cache")

        # 处理 bytes 和 str 两种情况
        peer_id_data = self._decode_redis_value(peer_id_data)
        peer_id = int(peer_id_data)
        return await self.get_peer_by_id(peer_id)

    async def get_peer_by_phone_number(self, phone_number: str):
        """
        通过电话号码获取对等点信息。

        Returns:
            (peer_id, access_hash, peer_type, username, phone_number)

        Raises:
            KeyError: 当缓��中不存在该 phone_number 时
        """
        logger.debug(f"[RedisStorage] 查询 phone_number={phone_number} 的缓存")

        peer_id_data = await self.redis_client.hget(
            self._key("phone_numbers"), phone_number
        )
        if not peer_id_data:
            logger.debug(f"[RedisStorage] Phone {phone_number} 不在缓存中")
            raise KeyError(f"Phone {phone_number} not found in cache")

        # 处理 bytes 和 str 两种情况
        peer_id_data = self._decode_redis_value(peer_id_data)
        peer_id = int(peer_id_data)
        return await self.get_peer_by_id(peer_id)

    # ==================== Version ====================

    async def version(self, value: int = object):
        """获取或设置存储版本（Pyrogram 内部使用）"""
        if value is object:
            # 获取
            version_str = self._decode_redis_value(
                await self.redis_client.get(self._key("version"))
            )
            return int(version_str) if version_str else 3  # 默认版本 3
        else:
            # 设置
            if value is None:
                await self.redis_client.delete(self._key("version"))
            else:
                await self.redis_client.set(self._key("version"), str(value))

    # ==================== API ID ====================

    async def api_id(self, value: int = object):
        """获取或设置 API ID"""
        if value is object:
            # 获取
            api_id_str = self._decode_redis_value(
                await self.redis_client.get(self._key("api_id"))
            )
            return int(api_id_str) if api_id_str else None
        else:
            # 设置
            if value is None:
                await self.redis_client.delete(self._key("api_id"))
            else:
                await self.redis_client.set(self._key("api_id"), str(value))

    # ==================== API Hash ====================

    async def api_hash(self, value: str = object):
        """获取或设置 API Hash"""
        if value is object:
            # 获取
            api_hash_data = self._decode_redis_value(
                await self.redis_client.get(self._key("api_hash"))
            )
            return api_hash_data if api_hash_data else None
        else:
            # 设置
            if value is None:
                await self.redis_client.delete(self._key("api_hash"))
            else:
                await self.redis_client.set(self._key("api_hash"), value)
