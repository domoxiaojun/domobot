"""
定时任务管理器
支持定时清理缓存等周期性任务
"""
import logging
from typing import Dict, List, Callable, Any
import schedule
import time
from threading import Thread

from utils.cache_manager import CacheManager

logger = logging.getLogger(__name__)

class ScheduledTask:
    """定时任务类"""
    def __init__(self, name: str, func: Callable, cron_expression: str | None = None, **kwargs):
        self.name = name
        self.func = func
        self.cron_expression = cron_expression
        self.kwargs = kwargs
        self.last_run = None
        self.next_run = None

class TaskScheduler:
    """定时任务调度器"""
    
    def __init__(self, cache_manager: CacheManager):
        self.cache_manager = cache_manager
        self.tasks: Dict[str, ScheduledTask] = {}
        self.running = False
        self.scheduler_thread = None
        
    def add_weekly_cache_cleanup(self, service_name: str, subdirectory: str, weekday: int = 6, hour: int = 5, minute: int = 0):
        """
        添加每周缓存清理任务
        
        Args:
            service_name: 服务名称
            subdirectory: 缓存子目录
            weekday: 星期几 (0=Monday, 6=Sunday)
            hour: 小时 (UTC)
            minute: 分钟
        """
        task_name = f"weekly_cache_cleanup_{service_name}"
        
        def cleanup_task():
            try:
                logger.info(f"Starting weekly cache cleanup for {service_name}")
                self.cache_manager.clear_cache(subdirectory=subdirectory)
                logger.info(f"Weekly cache cleanup completed for {service_name}")
            except Exception as e:
                logger.error(f"Error during weekly cache cleanup for {service_name}: {e}")
        
        # 使用schedule库设置每周任务
        if weekday == 6:  # Sunday
            schedule.every().sunday.at(f"{hour:02d}:{minute:02d}").do(cleanup_task)
        elif weekday == 0:  # Monday
            schedule.every().monday.at(f"{hour:02d}:{minute:02d}").do(cleanup_task)
        elif weekday == 1:  # Tuesday
            schedule.every().tuesday.at(f"{hour:02d}:{minute:02d}").do(cleanup_task)
        elif weekday == 2:  # Wednesday
            schedule.every().wednesday.at(f"{hour:02d}:{minute:02d}").do(cleanup_task)
        elif weekday == 3:  # Thursday
            schedule.every().thursday.at(f"{hour:02d}:{minute:02d}").do(cleanup_task)
        elif weekday == 4:  # Friday
            schedule.every().friday.at(f"{hour:02d}:{minute:02d}").do(cleanup_task)
        elif weekday == 5:  # Saturday
            schedule.every().saturday.at(f"{hour:02d}:{minute:02d}").do(cleanup_task)
        
        task = ScheduledTask(
            name=task_name,
            func=cleanup_task,
            service_name=service_name,
            subdirectory=subdirectory,
            weekday=weekday,
            hour=hour,
            minute=minute
        )
        
        self.tasks[task_name] = task
        logger.info(f"Added weekly cache cleanup task for {service_name} (every {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][weekday]} at {hour:02d}:{minute:02d} UTC)")
    
    def start(self):
        """启动定时任务调度器"""
        if self.running:
            logger.warning("Task scheduler is already running")
            return
            
        self.running = True
        
        def run_scheduler():
            logger.info("Task scheduler started")
            while self.running:
                try:
                    schedule.run_pending()
                    time.sleep(60)  # 每分钟检查一次
                except Exception as e:
                    logger.error(f"Error in task scheduler: {e}")
                    time.sleep(60)
        
        self.scheduler_thread = Thread(target=run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
    def stop(self):
        """停止定时任务调度器"""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        logger.info("Task scheduler stopped")
        
    def get_next_run_times(self) -> Dict[str, str]:
        """获取所有任务的下次运行时间"""
        next_runs = {}
        for job in schedule.jobs:
            if hasattr(job, 'job_func') and hasattr(job.job_func, '__name__'):
                next_runs[job.job_func.__name__] = str(job.next_run)
        return next_runs
        
    def list_tasks(self) -> List[Dict[str, Any]]:
        """列出所有任务"""
        task_list = []
        for task_name, task in self.tasks.items():
            task_info = {
                'name': task_name,
                'service_name': task.kwargs.get('service_name', 'unknown'),
                'subdirectory': task.kwargs.get('subdirectory', 'unknown'),
                'weekday': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][task.kwargs.get('weekday', 0)],
                'time': f"{task.kwargs.get('hour', 0):02d}:{task.kwargs.get('minute', 0):02d} UTC"
            }
            task_list.append(task_info)
        return task_list

# 全局任务调度器实例
task_scheduler = None

def init_task_scheduler(cache_manager: CacheManager):
    """初始化任务调度器"""
    global task_scheduler
    task_scheduler = TaskScheduler(cache_manager)
    return task_scheduler

def get_task_scheduler() -> TaskScheduler | None:
    """获取任务调度器实例"""
    return task_scheduler
