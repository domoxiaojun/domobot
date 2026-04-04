"""
API 凭证管理模块

用于保存、获取和删除 Pyrofork API 凭证（API ID 和 API Hash）
API Hash 使用加密存储以确保安全性

Redis Key 按 bot_id 隔离: pyrofork:{bot_id}:api_id / pyrofork:{bot_id}:api_hash
"""

import logging

from utils.encryption import encrypt_credential, decrypt_credential

logger = logging.getLogger(__name__)


def _key_api_id(bot_id: int) -> str:
    return f"pyrofork:{bot_id}:api_id"


def _key_api_hash(bot_id: int) -> str:
    return f"pyrofork:{bot_id}:api_hash"


async def save_pyrofork_credentials(
    redis_client, api_id: int, api_hash: str, bot_id: int = 0
) -> bool:
    """
    保存 Pyrofork API 凭证到 Redis

    Args:
        redis_client: Redis 客户端实例
        api_id: Telegram API ID
        api_hash: Telegram API Hash
        bot_id: Bot ID，用于 key 隔离

    Returns:
        bool: 保存是否成功
    """
    try:
        await redis_client.set(_key_api_id(bot_id), str(api_id))
        encrypted_api_hash = encrypt_credential(api_hash)
        await redis_client.set(_key_api_hash(bot_id), encrypted_api_hash)
        logger.info(f"Pyrofork API 凭证已保存到 Redis (bot_id={bot_id})")
        return True
    except Exception as e:
        logger.error(f"保存 Pyrofork API 凭证失败: {e}")
        return False


async def get_pyrofork_credentials(redis_client, bot_id: int = 0) -> dict | None:
    """
    从 Redis 获取 Pyrofork API 凭证

    Args:
        redis_client: Redis 客户端实例
        bot_id: Bot ID，用于 key 隔离

    Returns:
        包含 api_id 和 api_hash 的字典，如果未配置则返回 None
    """
    try:
        api_id_str = await redis_client.get(_key_api_id(bot_id))
        api_hash = await redis_client.get(_key_api_hash(bot_id))

        if api_id_str and api_hash:
            api_hash_str = (
                api_hash.decode() if isinstance(api_hash, bytes) else api_hash
            )
            decrypted_api_hash = decrypt_credential(api_hash_str)
            return {
                "api_id": int(
                    api_id_str.decode() if isinstance(api_id_str, bytes) else api_id_str
                ),
                "api_hash": decrypted_api_hash,
            }
        return None
    except Exception as e:
        logger.error(f"读取 Pyrofork API 凭证失败: {e}")
        return None


async def delete_pyrofork_credentials(redis_client, bot_id: int = 0) -> bool:
    """
    删除已保存的 Pyrofork API 凭证

    Args:
        redis_client: Redis 客户端实例
        bot_id: Bot ID，用于 key 隔离

    Returns:
        bool: 删除是否成功
    """
    try:
        await redis_client.delete(_key_api_id(bot_id))
        await redis_client.delete(_key_api_hash(bot_id))
        logger.info(f"✅ Pyrofork API 凭证已删除 (bot_id={bot_id})")
        return True
    except Exception as e:
        logger.error(f"❌ 删除 Pyrofork API 凭证失败: {e}")
        return False
