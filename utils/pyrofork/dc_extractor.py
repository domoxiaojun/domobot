"""
DC（数据中心）位置提取模块

通过 Bot API 从用户头像的 file_id 中提取 DC 信息（不需要 Pyrofork 登录）

原理：
1. 用户头像文件存储在用户所属的数据中心
2. file_id 是 Base64URL 编码的二进制数据
3. 解码后需要进行 RLE 解码
4. DC ID 存储在第 4-5 字节（小端序）

参考: https://woomai.me/talk/telegram-determine-dc-by-file-id/
"""

import base64
import logging
import struct

logger = logging.getLogger(__name__)


def _rle_decode(data: bytes) -> bytes:
    """
    RLE (游程长度编码) 解码函数

    Telegram file_id 使用 RLE 编码压缩数据。解码规则：
    - 遇到 0x00 字节时，下一个字节表示需要填充的 0 的个数
    - 其他字节直接保留

    Args:
        data: RLE 编码的字节数据

    Returns:
        解码后的字节数据
    """
    result = bytearray()
    i = 0
    while i < len(data):
        if data[i] == 0x00 and i + 1 < len(data):
            # 遇到 0x00，下一个字节表示填充 0 的个数
            zero_count = data[i + 1]
            result.extend(b"\x00" * zero_count)
            i += 2
        else:
            result.append(data[i])
            i += 1
    return bytes(result)


async def get_dc_from_profile_photo(bot, user_id: int) -> int | None:
    """
    通过 Bot API 从用户头像的 file_id 中提取 DC 信息（不需要 Pyrofork 登录）

    这是获取用户 DC 信息的首选方法，因为：
    1. 不需要 Pyrofork 用户登录
    2. 只使用普通的 Bot API
    3. 速度快，无需额外的 API 调用

    Args:
        bot: Telegram Bot 实例
        user_id: 用户 ID

    Returns:
        DC ID (1-5)，如果失败则返回 None
    """
    try:
        # 获取用户头像
        logger.debug(f"尝试从用户 {user_id} 的头像获取 DC...")
        profile_photos = await bot.get_user_profile_photos(user_id, limit=1)

        if not profile_photos or not profile_photos.photos:
            logger.debug(f"用户 {user_id} 没有设置头像，无法从头像获取 DC")
            return None

        # 获取最大尺寸的头像（通常是最后一个）
        photo_sizes = profile_photos.photos[0]
        if not photo_sizes:
            logger.debug(f"用户 {user_id} 的头像数据为空")
            return None

        # 选择最大的照片尺寸
        largest_photo = photo_sizes[-1]
        file_id = largest_photo.file_id

        # Base64 解码提取 DC ID
        logger.debug(f"解析 file_id 提取 DC: {file_id[:20]}...")

        # 将 base64url 转换为标准 base64
        file_id_normalized = file_id.replace("-", "+").replace("_", "/")

        # 添加填充
        padding = 4 - len(file_id_normalized) % 4
        if padding != 4:
            file_id_normalized += "=" * padding

        # Base64 解码
        data = base64.b64decode(file_id_normalized)
        logger.debug(f"Base64 解码后长度: {len(data)} 字节")

        # RLE 解码
        decoded_data = _rle_decode(data)
        logger.debug(f"RLE 解码后长度: {len(decoded_data)} 字节")

        # 从第 4-5 字节提取 DC ID (小端序, [4:6] 切片需要长度 >= 6)
        if len(decoded_data) >= 6:
            # 使用小端序读取 2 字节整数
            dc_id = struct.unpack("<H", decoded_data[4:6])[0]

            # DC ID 应该在 1-5 范围内
            if 1 <= dc_id <= 5:
                logger.debug(f"✅ 成功从头像 file_id 获取用户 {user_id} 的 DC{dc_id}")
                return dc_id
            else:
                logger.debug(f"提取的 DC ID {dc_id} 不在有效范围 (1-5) 内")
                return None
        else:
            logger.debug(f"解码后的数据长度不足 ({len(decoded_data)} < 6 字节)")
            return None

    except Exception as e:
        logger.warning(f"从头像获取 DC 失败: {e}", exc_info=True)
        return None
