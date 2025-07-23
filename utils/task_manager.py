"""
统一的异步任务管理器

这个模块提供了一个中央化的任务管理系统，负责所有异步任务的创建、跟踪和清理。
主要解决项目中过度使用 asyncio.create_task() 导致的任务泄漏和资源消耗问题。
"""

import asyncio
import logging
import time
from asyncio import Task
from typing import Any


logger = logging.getLogger(__name__)


class TaskManager:
    """统一的异步任务管理器

    Features:
    - 自动跟踪和清理任务
    - 任务数量限制
    - 定期清理机制
    - 详细的任务统计
    - 优雅关闭支持
    """

    def __init__(self, max_tasks: int = 1000, cleanup_interval: int = 60):
        """
        初始化任务管理器

        Args:
            max_tasks: 最大任务数量限制
            cleanup_interval: 清理间隔（秒）
        """
        self.max_tasks = max_tasks
        self.cleanup_interval = cleanup_interval
        self.tasks: set[Task] = set()
        self.task_metadata: dict[Task, dict[str, Any]] = {}
        self._last_cleanup = time.time()
        self._is_shutting_down = False

        logger.info(f"任务管理器已初始化，最大任务数: {max_tasks}")

    def create_task(self, coro, name: str | None = None, context: str | None = None) -> Task:
        """创建并跟踪异步任务

        Args:
            coro: 协程对象
            name: 任务名称（用于调试）
            context: 任务上下文（用于分类统计）

        Returns:
            创建的任务对象

        Raises:
            RuntimeError: 当任务数量超过限制时
        """
        if self._is_shutting_down:
            raise RuntimeError("任务管理器正在关闭，无法创建新任务")

        # 检查任务数量限制
        if len(self.tasks) >= self.max_tasks:
            self._force_cleanup()
            if len(self.tasks) >= self.max_tasks:
                raise RuntimeError(f"任务数量超过限制 ({self.max_tasks})")

        # 创建任务
        task = asyncio.create_task(coro, name=name)

        # 注册任务
        self.tasks.add(task)
        self.task_metadata[task] = {
            "created_at": time.time(),
            "name": name or "unnamed",
            "context": context or "unknown",
        }

        # 添加完成回调
        task.add_done_callback(self._task_done_callback)

        # 定期清理
        self._periodic_cleanup()

        logger.debug(f"创建任务: {name} (总数: {len(self.tasks)})")
        return task

    def _task_done_callback(self, task: Task):
        """任务完成时的回调"""
        self.tasks.discard(task)
        metadata = self.task_metadata.pop(task, {})

        if task.cancelled():
            logger.debug(f"任务被取消: {metadata.get('name', 'unknown')}")
        elif task.exception():
            logger.warning(f"任务执行失败: {metadata.get('name', 'unknown')}, 错误: {task.exception()}")
        else:
            logger.debug(f"任务完成: {metadata.get('name', 'unknown')}")

    def _periodic_cleanup(self):
        """定期清理已完成的任务"""
        current_time = time.time()
        if current_time - self._last_cleanup > self.cleanup_interval:
            self._force_cleanup()
            self._last_cleanup = current_time

    def _force_cleanup(self):
        """强制清理已完成的任务"""
        completed_tasks = {task for task in self.tasks if task.done()}
        for task in completed_tasks:
            self.tasks.discard(task)
            self.task_metadata.pop(task, None)

        if completed_tasks:
            logger.info(f"清理了 {len(completed_tasks)} 个已完成的任务")

    def cancel_all_tasks(self):
        """取消所有未完成的任务"""
        cancelled_count = 0
        for task in list(self.tasks):
            if not task.done():
                task.cancel()
                cancelled_count += 1

        if cancelled_count > 0:
            logger.info(f"取消了 {cancelled_count} 个任务")

    async def shutdown(self):
        """优雅关闭任务管理器"""
        self._is_shutting_down = True
        logger.info(f"开始关闭任务管理器，当前有 {len(self.tasks)} 个任务")

        # 取消所有任务
        self.cancel_all_tasks()

        # 等待任务完成或取消（最多等待30秒）
        if self.tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*self.tasks, return_exceptions=True), timeout=30.0)
            except TimeoutError:
                logger.warning("等待任务完成超时，强制结束")

        # 清理
        self.tasks.clear()
        self.task_metadata.clear()

        logger.info("任务管理器已关闭")

    def get_stats(self) -> dict[str, Any]:
        """获取任务统计信息"""
        total = len(self.tasks)
        running = sum(1 for task in self.tasks if not task.done())
        completed = sum(1 for task in self.tasks if task.done())
        cancelled = sum(1 for task in self.tasks if task.cancelled())
        failed = sum(1 for task in self.tasks if task.done() and task.exception())

        # 按上下文分组统计
        context_stats = {}
        for _task, metadata in self.task_metadata.items():
            context = metadata.get("context", "unknown")
            if context not in context_stats:
                context_stats[context] = 0
            context_stats[context] += 1

        return {
            "total_tasks": total,
            "running_tasks": running,
            "completed_tasks": completed,
            "cancelled_tasks": cancelled,
            "failed_tasks": failed,
            "context_breakdown": context_stats,
            "max_tasks": self.max_tasks,
            "is_shutting_down": self._is_shutting_down,
        }

    def print_stats(self):
        """打印任务统计信息"""
        stats = self.get_stats()
        logger.info("=== 任务管理器统计 ===")
        logger.info(f"总任务数: {stats['total_tasks']}/{stats['max_tasks']}")
        logger.info(f"运行中: {stats['running_tasks']}")
        logger.info(f"已完成: {stats['completed_tasks']}")
        logger.info(f"已取消: {stats['cancelled_tasks']}")
        logger.info(f"失败: {stats['failed_tasks']}")
        if stats["context_breakdown"]:
            logger.info("按上下文分组:")
            for context, count in stats["context_breakdown"].items():
                logger.info(f"  {context}: {count}")


# 全局任务管理器实例
task_manager = TaskManager()


def get_task_manager() -> TaskManager:
    """获取全局任务管理器实例"""
    return task_manager


# 便捷函数
def create_task(coro, name: str | None = None, context: str | None = None) -> Task:
    """创建任务的便捷函数"""
    return task_manager.create_task(coro, name=name, context=context)


async def shutdown_task_manager():
    """关闭任务管理器的便捷函数"""
    await task_manager.shutdown()
