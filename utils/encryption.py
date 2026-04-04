"""
凭证加密模块

使用 Fernet 对称加密保护敏感数据（如 API Hash）
密钥通过环境变量 REDIS_ENCRYPTION_KEY 配置
"""

import os
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_cipher: Optional[Fernet] = None


def _get_cipher() -> Optional[Fernet]:
    """获取加密器实例（懒加载）"""
    global _cipher
    if _cipher is None:
        key = os.getenv("REDIS_ENCRYPTION_KEY")
        if key:
            try:
                _cipher = Fernet(key.encode())
            except Exception as e:
                logger.error(f"初始化加密器失败: {e}")
    return _cipher


def encrypt_credential(plaintext: str) -> str:
    """
    加密凭证

    Args:
        plaintext: 明文凭证

    Returns:
        加密后的字符串，如果未配置密钥则返回原文
    """
    cipher = _get_cipher()
    if cipher is None:
        logger.warning("加密密钥未配置，凭证将以明文存储")
        return plaintext
    return cipher.encrypt(plaintext.encode()).decode()


def decrypt_credential(ciphertext: str) -> str:
    """
    解密凭证

    Args:
        ciphertext: 加密后的凭证

    Returns:
        解密后的明文，如果解密失败则返回原文（兼容旧数据）
    """
    cipher = _get_cipher()
    if cipher is None:
        return ciphertext  # 未配置密钥，假设是明文
    try:
        return cipher.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        # 解密失败，可能是旧的明文数据
        logger.debug("解密失败，返回原始数据（可能是未加密的旧数据）")
        return ciphertext


def generate_encryption_key() -> str:
    """
    生成新的加密密钥

    Returns:
        Base64 编码的 Fernet 密钥
    """
    return Fernet.generate_key().decode()
