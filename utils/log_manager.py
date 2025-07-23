"""
日志管理模块
提供日志清理和归档功能
"""

import os
import gzip
import shutil
import logging
from datetime import datetime, timedelta
from typing import List
import glob

logger = logging.getLogger(__name__)


class LogManager:
    """日志管理器"""
    
    def __init__(self, log_dir: str = "logs", archive_dir: str = "logs/archive"):
        self.log_dir = log_dir
        self.archive_dir = archive_dir
        
        # 确保目录存在
        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(self.archive_dir, exist_ok=True)
    
    def get_log_files(self) -> List[str]:
        """获取所有日志文件"""
        pattern = os.path.join(self.log_dir, "bot-*.log")
        return glob.glob(pattern)
    
    def archive_old_logs(self, days_old: int = 7) -> int:
        """归档超过指定天数的日志文件"""
        archived_count = 0
        cutoff_date = datetime.now() - timedelta(days=days_old)
        
        log_files = self.get_log_files()
        
        for log_file in log_files:
            try:
                # 从文件名提取日期
                filename = os.path.basename(log_file)
                if filename.startswith("bot-") and filename.endswith(".log"):
                    date_str = filename[4:-4]  # 提取日期部分
                    try:
                        file_date = datetime.strptime(date_str, "%Y-%m-%d")
                        
                        if file_date < cutoff_date:
                            # 移动到归档目录
                            year_month = file_date.strftime("%Y-%m")
                            archive_subdir = os.path.join(self.archive_dir, year_month)
                            os.makedirs(archive_subdir, exist_ok=True)
                            
                            archive_path = os.path.join(archive_subdir, filename)
                            shutil.move(log_file, archive_path)
                            
                            # 压缩归档文件
                            self._compress_file(archive_path)
                            
                            archived_count += 1
                            logger.info(f"归档日志文件: {filename}")
                            
                    except ValueError:
                        logger.warning(f"无法解析日志文件日期: {filename}")
                        
            except Exception as e:
                logger.error(f"归档日志文件失败 {log_file}: {e}")
        
        return archived_count
    
    def _compress_file(self, file_path: str) -> None:
        """压缩文件"""
        try:
            with open(file_path, 'rb') as f_in:
                with gzip.open(f"{file_path}.gz", 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # 删除原文件
            os.remove(file_path)
            logger.debug(f"压缩文件: {file_path}")
            
        except Exception as e:
            logger.error(f"压缩文件失败 {file_path}: {e}")
    
    def cleanup_old_archives(self, days_old: int = 90) -> int:
        """清理超过指定天数的归档文件"""
        cleaned_count = 0
        cutoff_date = datetime.now() - timedelta(days=days_old)
        
        # 查找所有压缩的归档文件
        pattern = os.path.join(self.archive_dir, "**", "*.log.gz")
        archive_files = glob.glob(pattern, recursive=True)
        
        for archive_file in archive_files:
            try:
                # 获取文件修改时间
                file_mtime = datetime.fromtimestamp(os.path.getmtime(archive_file))
                
                if file_mtime < cutoff_date:
                    os.remove(archive_file)
                    cleaned_count += 1
                    logger.info(f"删除旧归档文件: {os.path.basename(archive_file)}")
                    
            except Exception as e:
                logger.error(f"删除归档文件失败 {archive_file}: {e}")
        
        return cleaned_count
    
    def get_log_stats(self) -> dict:
        """获取日志统计信息"""
        stats = {
            "current_logs": 0,
            "current_size_mb": 0.0,
            "archive_files": 0,
            "archive_size_mb": 0.0
        }
        
        try:
            # 统计当前日志
            log_files = self.get_log_files()
            stats["current_logs"] = len(log_files)
            
            current_size = 0
            for log_file in log_files:
                current_size += os.path.getsize(log_file)
            stats["current_size_mb"] = round(current_size / 1024 / 1024, 2)
            
            # 统计归档文件
            pattern = os.path.join(self.archive_dir, "**", "*.log.gz")
            archive_files = glob.glob(pattern, recursive=True)
            stats["archive_files"] = len(archive_files)
            
            archive_size = 0
            for archive_file in archive_files:
                archive_size += os.path.getsize(archive_file)
            stats["archive_size_mb"] = round(archive_size / 1024 / 1024, 2)
            
        except Exception as e:
            logger.error(f"获取日志统计失败: {e}")
        
        return stats
    
    def run_maintenance(self, archive_days: int = 7, cleanup_days: int = 90) -> dict:
        """运行日志维护任务"""
        result = {
            "archived": 0,
            "cleaned": 0,
            "error": None
        }
        
        try:
            logger.info("开始日志维护任务")
            
            # 归档旧日志
            result["archived"] = self.archive_old_logs(archive_days)
            
            # 清理旧归档
            result["cleaned"] = self.cleanup_old_archives(cleanup_days)
            
            logger.info(f"日志维护完成: 归档 {result['archived']} 个文件, 清理 {result['cleaned']} 个文件")
            
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"日志维护任务失败: {e}")
        
        return result


# 全局日志管理器实例
log_manager = LogManager()


def schedule_log_maintenance():
    """调度日志维护任务"""
    try:
        import schedule
        
        # 每周日凌晨2点执行日志维护
        schedule.every().sunday.at("02:00").do(log_manager.run_maintenance, archive_days=7, cleanup_days=90)
        
        logger.info("日志维护任务已调度: 每周日 02:00 执行")
        
    except Exception as e:
        logger.error(f"调度日志维护任务失败: {e}")


def get_log_manager() -> LogManager:
    """获取日志管理器实例"""
    return log_manager
