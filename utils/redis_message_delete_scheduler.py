"""
Redis 消息删除管理器
使用 Redis 的过期键功能实现消息自动删除
"""

import asyncio
import json
import logging

import redis.asyncio as redis
from telegram import Bot
from telegram.error import TelegramError


logger = logging.getLogger(__name__)


class RedisMessageDeleteScheduler:
    """Redis 消息删除调度器，替代文件系统版本"""

    def __init__(self, redis_client: redis.Redis):
        """初始化调度器"""
        self.redis = redis_client
        self.bot: Bot | None = None
        self._running = False
        self._task: asyncio.Task | None = None

    def start(self, bot: Bot):
        """启动调度器"""
        self.bot = bot
        self._running = True

        # 启动监听任务
        self._task = asyncio.create_task(self._deletion_worker())
        logger.info("✅ Redis 消息删除调度器已启动")

        # 启动时处理遗留的删除任务
        asyncio.create_task(self._process_existing_deletions())

    async def _process_existing_deletions(self):
        """处理启动时存在的遗留删除任务"""
        try:
            # 等待1秒确保调度器完全启动
            await asyncio.sleep(1)

            import time

            current_time = time.time()
            processed_count = 0

            logger.info("🔍 检查遗留的消息删除任务...")

            # 获取所有已到期的任务（包括遗留任务）
            expired_tasks = await self.redis.zrangebyscore("msg:delete:schedule", 0, current_time, withscores=False)

            if expired_tasks:
                for key in expired_tasks:
                    # 获取任务数据
                    task_data_str = await self.redis.hget("msg:delete:tasks", key)
                    if task_data_str:
                        try:
                            task_data = json.loads(task_data_str)
                            chat_id = task_data.get("chat_id")
                            message_id = task_data.get("message_id")
                            session_id = task_data.get("session_id")

                            if chat_id and message_id:
                                # 删除消息
                                await self._delete_message(chat_id, message_id)
                                processed_count += 1

                                # 从会话集合中移除
                                if session_id:
                                    session_key = f"msg:session:{session_id}"
                                    await self.redis.srem(session_key, key)

                        except (json.JSONDecodeError, TypeError) as e:
                            logger.error(f"解析遗留任务数据失败 {key}: {e}")

                    # 清理任务
                    await self.redis.hdel("msg:delete:tasks", key)
                    await self.redis.zrem("msg:delete:schedule", key)

            if processed_count > 0:
                logger.info(f"📧 已处理 {processed_count} 个遗留的消息删除任务")
            else:
                logger.info("✅ 没有遗留的消息删除任务")

        except Exception as e:
            logger.error(f"处理遗留删除任务时出错: {e}")

    def stop(self):
        """停止调度器"""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Redis 消息删除调度器已停止")

    async def schedule_deletion(self, chat_id: int, message_id: int, delay: int, session_id: str | None = None):
        """
        调度消息删除

        Args:
            chat_id: 聊天ID
            message_id: 消息ID
            delay: 延迟时间（秒）
            session_id: 会话ID（可选）
        """
        if delay <= 0:
            # 立即删除
            await self._delete_message(chat_id, message_id)
        else:
            # 计算执行时间
            import time

            execute_at = time.time() + delay

            # 创建删除任务的数据
            task_data = {
                "chat_id": chat_id,
                "message_id": message_id,
                "session_id": session_id,
                "execute_at": execute_at,
            }

            # 使用不过期的键存储任务数据，并在 sorted set 中管理时间
            key = f"msg:delete:{chat_id}:{message_id}"
            await self.redis.hset("msg:delete:tasks", key, json.dumps(task_data))

            # 添加到时间排序集合
            await self.redis.zadd("msg:delete:schedule", {key: execute_at})

            # 如果有 session_id，维护会话索引
            if session_id:
                session_key = f"msg:session:{session_id}"
                # 添加消息键到会话集合
                await self.redis.sadd(session_key, key)
                # 设置会话键的过期时间（比消息稍长）
                await self.redis.expire(session_key, delay + 60)

            logger.debug(f"已调度消息删除: {key}, 延迟: {delay}秒, 会话: {session_id}")

    async def _deletion_worker(self):
        """监听到期任务并执行删除"""
        logger.info("消息删除工作器已启动")

        while self._running:
            try:
                import time

                current_time = time.time()

                # 获取所有到期的任务
                expired_tasks = await self.redis.zrangebyscore("msg:delete:schedule", 0, current_time, withscores=False)

                if expired_tasks:
                    for key in expired_tasks:
                        # 获取任务数据
                        task_data_str = await self.redis.hget("msg:delete:tasks", key)
                        if task_data_str:
                            try:
                                task_data = json.loads(task_data_str)
                                chat_id = task_data.get("chat_id")
                                message_id = task_data.get("message_id")
                                session_id = task_data.get("session_id")

                                if chat_id and message_id:
                                    # 删除消息
                                    await self._delete_message(chat_id, message_id)

                                    # 从会话集合中移除
                                    if session_id:
                                        session_key = f"msg:session:{session_id}"
                                        await self.redis.srem(session_key, key)

                            except (json.JSONDecodeError, TypeError) as e:
                                logger.error(f"解析任务数据失败 {key}: {e}")

                        # 清理任务
                        await self.redis.hdel("msg:delete:tasks", key)
                        await self.redis.zrem("msg:delete:schedule", key)

                # 每秒检查一次
                await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"消息删除工作器错误: {e}")
                await asyncio.sleep(5)  # 错误后等待5秒再重试

        logger.info("消息删除工作器已停止")

    async def _delete_message(self, chat_id: int, message_id: int):
        """删除指定消息"""
        if not self.bot:
            logger.warning("Bot 未初始化，无法删除消息")
            return

        try:
            await self.bot.delete_message(chat_id=chat_id, message_id=message_id)
            logger.debug(f"消息已删除: chat_id={chat_id}, message_id={message_id}")
        except TelegramError as e:
            # 忽略消息已删除的错误
            if "message to delete not found" not in str(e).lower():
                logger.error(f"删除消息失败: {e}")

    async def cancel_deletion(self, chat_id: int, message_id: int):
        """取消调度的消息删除"""
        key = f"msg:delete:{chat_id}:{message_id}"

        # 获取任务数据以获取 session_id
        task_data_str = await self.redis.hget("msg:delete:tasks", key)
        if task_data_str:
            try:
                task_data = json.loads(task_data_str)
                session_id = task_data.get("session_id")

                # 从会话集合中移除
                if session_id:
                    session_key = f"msg:session:{session_id}"
                    await self.redis.srem(session_key, key)
            except (json.JSONDecodeError, TypeError):
                pass

        # 删除任务
        await self.redis.hdel("msg:delete:tasks", key)
        result = await self.redis.zrem("msg:delete:schedule", key)
        if result:
            logger.debug(f"已取消消息删除: {key}")

    async def cancel_session_deletions(self, session_id: str) -> int:
        """取消会话的所有删除任务"""
        if not session_id:
            return 0

        session_key = f"msg:session:{session_id}"

        # 获取会话中的所有消息键
        message_keys = await self.redis.smembers(session_key)

        if not message_keys:
            return 0

        cancelled_count = 0

        # 删除所有相关的消息任务
        for key in message_keys:
            # 从任务表中删除
            result1 = await self.redis.hdel("msg:delete:tasks", key)
            # 从调度表中删除
            result2 = await self.redis.zrem("msg:delete:schedule", key)
            if result1 or result2:
                cancelled_count += 1

        # 删除会话键
        await self.redis.delete(session_key)

        logger.info(f"已取消会话 {session_id} 的 {cancelled_count} 个删除任务")
        return cancelled_count

    async def get_pending_deletions_count(self) -> int:
        """获取待删除消息数量"""
        return await self.redis.zcard("msg:delete:schedule")

    async def get_session_deletions_count(self, session_id: str) -> int:
        """获取特定会话的待删除消息数量"""
        if not session_id:
            return 0

        session_key = f"msg:session:{session_id}"
        return await self.redis.scard(session_key)

    async def clear_all_pending_deletions(self):
        """清除所有待删除的消息"""
        # 清除任务表
        await self.redis.delete("msg:delete:tasks")
        # 清除调度表
        await self.redis.delete("msg:delete:schedule")

        # 清除所有会话索引
        cursor = 0
        pattern = "msg:session:*"

        while True:
            cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
            if keys:
                await self.redis.delete(*keys)
            if cursor == 0:
                break

        logger.info("已清除所有待删除消息和会话索引")


# 全局实例（用于兼容性）
_redis_message_delete_scheduler: RedisMessageDeleteScheduler | None = None


def get_message_delete_scheduler(redis_client: redis.Redis) -> RedisMessageDeleteScheduler:
    """获取消息删除调度器实例"""
    global _redis_message_delete_scheduler
    if _redis_message_delete_scheduler is None:
        _redis_message_delete_scheduler = RedisMessageDeleteScheduler(redis_client)
    return _redis_message_delete_scheduler
