"""
配置管理模块
"""

import logging
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from utils import constants

logger = logging.getLogger(__name__)


class BotConfig:
    """机器人配置类"""

    def __init__(self):

        # Webhook 配置
        self.webhook_url = ""
        self.webhook_listen = "0.0.0.0"
        self.webhook_port = 8443
        self.webhook_secret_token = ""
        self.webhook_key = ""
        self.webhook_cert = ""

        # 基础配置
        self.bot_token = ""
        self.bot_id: int = 0  # 从 BOT_TOKEN 提取的 Bot ID，用于多 Bot 隔离
        self.super_admin_ids: list[int] = []  # 支持多个超级管理员
        self.whitelisted_groups: list[int] = []  # 静态配置的白名单群组
        self.debug = False

        # Telegram API 配置（用于 Pyrofork 客户端）
        self.telegram_api_id: int = 0
        self.telegram_api_hash = ""

        # 数据库配置（已统一使用 MySQL）

        # 缓存配置
        self.cache_dir = "cache"
        self.default_cache_duration = constants.DEFAULT_CACHE_DURATION

        # 分层缓存配置（方案C: Redis热缓存 + MySQL持久化）

        # API配置

        # 性能配置
        self.max_concurrent_requests = constants.DEFAULT_MAX_CONCURRENT_REQUESTS
        self.request_timeout = constants.DEFAULT_REQUEST_TIMEOUT
        self.max_retries = constants.DEFAULT_MAX_RETRIES

        # 速率限制配置
        self.rate_limit_enabled = True
        self.max_requests_per_minute = constants.DEFAULT_MAX_REQUESTS_PER_MINUTE

        # 日志配置
        self.log_level = "INFO"
        self.log_file = ""  # 将在ConfigManager中动态生成
        self.log_max_size = constants.LOG_MAX_SIZE  # 10MB
        self.log_backup_count = constants.LOG_BACKUP_COUNT

        # 功能开关
        self.features = {
            "steam_enabled": True,
            "netflix_enabled": True,
            "spotify_enabled": True,
            "disney_enabled": True,
            "appstore_enabled": True,
            "googleplay_enabled": True,
            "apple_services_enabled": True,
            "rate_conversion_enabled": True,
        }

        # UI 配置
        self.folding_threshold = (
            constants.FOLDING_THRESHOLD
        )  # 消息折叠阈值（行数），超过此行数的消息将被折叠显示

        # 消息自动删除配置
        self.auto_delete_delay = (
            constants.DEFAULT_MESSAGE_DELETE_DELAY
        )  # 自动删除延迟时间（秒），默认3分钟
        self.delete_user_commands = True  # 是否删除用户命令消息
        self.user_command_delete_delay = (
            constants.USER_COMMAND_DELETE_DELAY
        )  # 用户命令删除延迟时间（秒），默认立即删除

        # 用户缓存配置
        self.enable_user_cache = False
        self.user_cache_group_ids = []

        # 自定义脚本配置
        self.alerter_config = {}
        self.load_custom_scripts = False
        self.custom_scripts_dir = "custom_scripts"

        # 国家代码配置
        self.default_countries = {
            "steam": ["CN", "US", "TR", "RU", "AR"],
            "netflix": ["CN", "US", "TR", "NG", "IN"],
            "spotify": ["US", "NG", "TR", "IN", "MY"],
            "disney": ["US", "TR", "IN"],
        }

        # Redis 配置
        self.redis_host = "localhost"
        self.redis_port = constants.DEFAULT_REDIS_PORT
        self.redis_password = None
        self.redis_db = constants.DEFAULT_REDIS_DB
        # Redis 连接池配置
        self.redis_max_connections = constants.REDIS_MAX_CONNECTIONS  # 最大连接数
        self.redis_health_check_interval = (
            constants.REDIS_HEALTH_CHECK_INTERVAL
        )  # 健康检查间隔（秒）

        # MySQL 配置
        self.db_host = "localhost"
        self.db_port = constants.DEFAULT_MYSQL_PORT
        self.db_name = "bot"
        self.db_user = "bot"
        self.db_password = ""
        # MySQL 连接池配置
        self.db_min_connections = constants.MYSQL_MIN_CONNECTIONS  # 最小连接数
        self.db_max_connections = constants.MYSQL_MAX_CONNECTIONS  # 最大连接数


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_file: str | None = None):
        self.config_file = config_file or ".env"
        self.config = BotConfig()
        self._load_config()

    def _load_config(self):
        """加载配置"""
        try:
            # 尝试加载.env文件
            if os.path.exists(self.config_file):
                self._load_from_env_file()

            # 加载环境变量
            self._load_from_environment()
            # 验证配置
            self._validate_config()

            logger.info("Configuration loaded successfully")

        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            raise

    def _load_from_env_file(self):
        """从.env文件加载配置"""
        try:
            from dotenv import load_dotenv

            load_dotenv(self.config_file)
            logger.info(f"Loaded configuration from {self.config_file}")
        except ImportError:
            logger.warning("python-dotenv not installed, skipping .env file loading")

    def _load_from_environment(self):
        """从环境变量加载配置"""

        # 辅助方法：读取布尔值环境变量
        def get_bool_env(key: str, default: str = "False") -> bool:
            return os.getenv(key, default).lower() == "true"

        # 辅助方法：读取整数环境变量
        def get_int_env(key: str, default: str) -> int:
            return int(os.getenv(key, default))

        # 辅助方法：解析超级管理员ID列表（支持逗号分隔）
        def parse_super_admin_ids() -> list[int]:
            """
            解析超级管理员ID列表
            支持格式:
            - 单个ID: SUPER_ADMIN_ID=123456
            - 多个ID: SUPER_ADMIN_ID=123456,789012,345678
            """
            ids_str = os.getenv("SUPER_ADMIN_ID", "").strip()
            if not ids_str:
                return []

            # 按逗号分隔并解析为整数列表
            ids = []
            for id_str in ids_str.split(","):
                id_str = id_str.strip()
                if id_str:
                    try:
                        admin_id = int(id_str)
                        if admin_id > 0:
                            ids.append(admin_id)
                    except ValueError:
                        logger.warning(f"⚠️ 无效的超级管理员ID: {id_str}")

            return ids

        # 基础配置
        self.config.bot_token = os.getenv("BOT_TOKEN", "")
        self.config.super_admin_ids = parse_super_admin_ids()

        # 解析群组白名单
        whitelisted_groups_str = os.getenv("WHITELISTED_GROUPS", "").strip()
        self.config.whitelisted_groups = []
        if whitelisted_groups_str:
            for gid in whitelisted_groups_str.split(","):
                gid = gid.strip()
                if gid:
                    try:
                        self.config.whitelisted_groups.append(int(gid))
                    except ValueError:
                        logger.warning(f"⚠️ 无效的白名单群组ID: {gid}")

        self.config.debug = get_bool_env("DEBUG")

        # 缓存配置
        self.config.cache_dir = os.getenv("CACHE_DIR", "cache")
        self.config.default_cache_duration = get_int_env(
            "DEFAULT_CACHE_DURATION", str(constants.DEFAULT_CACHE_DURATION)
        )

        # 性能配置
        self.config.max_concurrent_requests = get_int_env(
            "MAX_CONCURRENT_REQUESTS", str(constants.DEFAULT_MAX_CONCURRENT_REQUESTS)
        )
        self.config.request_timeout = get_int_env(
            "REQUEST_TIMEOUT", str(constants.DEFAULT_REQUEST_TIMEOUT)
        )
        self.config.max_retries = get_int_env(
            "MAX_RETRIES", str(constants.DEFAULT_MAX_RETRIES)
        )

        # 速率限制配置
        self.config.rate_limit_enabled = get_bool_env("RATE_LIMIT_ENABLED", "True")
        self.config.max_requests_per_minute = get_int_env(
            "MAX_REQUESTS_PER_MINUTE", str(constants.DEFAULT_MAX_REQUESTS_PER_MINUTE)
        )

        # 日志配置
        self.config.log_level = os.getenv("LOG_LEVEL", "INFO")
        log_filename = f"bot-{datetime.now().strftime('%Y-%m-%d')}.log"
        self.config.log_file = os.getenv("LOG_FILE", f"logs/{log_filename}")
        self.config.log_max_size = get_int_env(
            "LOG_MAX_SIZE", str(constants.LOG_MAX_SIZE)
        )
        self.config.log_backup_count = get_int_env(
            "LOG_BACKUP_COUNT", str(constants.LOG_BACKUP_COUNT)
        )

        # 功能开关
        for feature in self.config.features:
            env_key = f"{feature.upper()}"
            self.config.features[feature] = get_bool_env(env_key, "True")

        # UI 配置
        self.config.folding_threshold = get_int_env(
            "FOLDING_THRESHOLD", str(constants.FOLDING_THRESHOLD)
        )  # 默认15行

        # 消息自动删除配置
        # 支持 DEFAULT_MESSAGE_DELETE_DELAY 作为 AUTO_DELETE_DELAY 的别名
        default_delay = os.getenv(
            "DEFAULT_MESSAGE_DELETE_DELAY",
            os.getenv("AUTO_DELETE_DELAY", str(constants.DEFAULT_MESSAGE_DELETE_DELAY)),
        )
        self.config.auto_delete_delay = int(default_delay)
        self.config.delete_user_commands = get_bool_env("DELETE_USER_COMMANDS", "True")
        self.config.user_command_delete_delay = get_int_env(
            "USER_COMMAND_DELETE_DELAY", str(constants.USER_COMMAND_DELETE_DELAY)
        )

        # 用户缓存配置
        self.config.enable_user_cache = get_bool_env("ENABLE_USER_CACHE")
        cache_group_ids_str = os.getenv("USER_CACHE_GROUP_IDS", "")
        if cache_group_ids_str:
            self.config.user_cache_group_ids = [
                int(gid.strip())
                for gid in cache_group_ids_str.split(",")
                if gid.strip()
            ]

        # 自定义脚本配置
        alerter_config_str = os.getenv("ALERTER_CONFIG", "{}")
        try:
            import json

            self.config.alerter_config = json.loads(alerter_config_str)
        except json.JSONDecodeError:
            logger.error(
                "Failed to parse ALERTER_CONFIG JSON string. Using empty config."
            )
            self.config.alerter_config = {}
        self.config.load_custom_scripts = get_bool_env("LOAD_CUSTOM_SCRIPTS")
        self.config.custom_scripts_dir = os.getenv(
            "CUSTOM_SCRIPTS_DIR", "custom_scripts"
        )

        # Redis 配置
        self.config.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.config.redis_port = get_int_env(
            "REDIS_PORT", str(constants.DEFAULT_REDIS_PORT)
        )
        self.config.redis_password = os.getenv("REDIS_PASSWORD")
        self.config.redis_db = get_int_env("REDIS_DB", str(constants.DEFAULT_REDIS_DB))
        # Redis 连接池配置
        self.config.redis_max_connections = get_int_env(
            "REDIS_MAX_CONNECTIONS", str(constants.REDIS_MAX_CONNECTIONS)
        )
        self.config.redis_health_check_interval = get_int_env(
            "REDIS_HEALTH_CHECK_INTERVAL", str(constants.REDIS_HEALTH_CHECK_INTERVAL)
        )

        # Telegram API 配置
        api_id_str = os.getenv("TELEGRAM_API_ID", "")
        self.config.telegram_api_id = int(api_id_str) if api_id_str.isdigit() else 0
        self.config.telegram_api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()

        # MySQL 配置
        self.config.db_host = os.getenv("DB_HOST", "localhost")
        self.config.db_port = get_int_env("DB_PORT", str(constants.DEFAULT_MYSQL_PORT))
        self.config.db_name = os.getenv("DB_NAME", "bot")
        self.config.db_user = os.getenv("DB_USER", "bot")
        self.config.db_password = os.getenv("DB_PASSWORD", "")
        # MySQL 连接池配置
        self.config.db_min_connections = get_int_env(
            "DB_MIN_CONNECTIONS", str(constants.MYSQL_MIN_CONNECTIONS)
        )
        self.config.db_max_connections = get_int_env(
            "DB_MAX_CONNECTIONS", str(constants.MYSQL_MAX_CONNECTIONS)
        )

        # Webhook 配置
        self.config.webhook_url = os.getenv("WEBHOOK_URL", "")
        if self.config.webhook_url:
            self.config.webhook_listen = os.getenv(
                "WEBHOOK_LISTEN", constants.DEFAULT_WEBHOOK_LISTEN
            )
            self.config.webhook_port = get_int_env(
                "WEBHOOK_PORT", str(constants.DEFAULT_WEBHOOK_PORT)
            )
            self.config.webhook_secret_token = os.getenv(
                "WEBHOOK_SECRET_TOKEN"
            ) or secrets.token_hex(32)

    def _validate_config(self):
        """验证配置"""
        # ========================================
        # 必需配置验证
        # ========================================
        if not self.config.bot_token:
            raise ValueError("BOT_TOKEN is required")

        # 从 BOT_TOKEN 提取 bot_id（格式: "123456:ABC-DEF..."）
        try:
            self.config.bot_id = int(self.config.bot_token.split(":")[0])
        except (ValueError, IndexError) as e:
            raise ValueError(f"BOT_TOKEN 格式无效，无法提取 bot_id: {e}") from e

        if not self.config.super_admin_ids:
            raise ValueError(
                "SUPER_ADMIN_ID is required. "
                "支持多个ID（逗号分隔）: SUPER_ADMIN_ID=123456,789012"
            )

        # ========================================
        # MySQL 配置验证
        # ========================================
        if not self.config.db_host:
            raise ValueError("DB_HOST is required")
        if not self.config.db_user:
            raise ValueError("DB_USER is required")
        if not self.config.db_name:
            raise ValueError("DB_NAME is required")
        if not 1 <= self.config.db_port <= 65535:
            raise ValueError(
                f"DB_PORT must be between 1 and 65535, got {self.config.db_port}"
            )

        # ========================================
        # Redis 配置验证
        # ========================================
        if not self.config.redis_host:
            raise ValueError("REDIS_HOST is required")
        if not 1 <= self.config.redis_port <= 65535:
            raise ValueError(
                f"REDIS_PORT must be between 1 and 65535, got {self.config.redis_port}"
            )

        if not self.config.telegram_api_id or not self.config.telegram_api_hash:
            logger.warning(
                "⚠️ 未配置 TELEGRAM_API_ID/TELEGRAM_API_HASH，"
                "Pyrofork 用户信息查询将使用 ID 推测算法"
            )

        # ========================================
        # 创建必要的目录
        # ========================================
        Path(self.config.cache_dir).mkdir(parents=True, exist_ok=True)
        Path("logs").mkdir(exist_ok=True)

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return getattr(self.config, key, default)

    def is_feature_enabled(self, feature: str) -> bool:
        """检查功能是否启用"""
        return self.config.features.get(feature, False)

    def get_default_countries(self, service: str) -> list:
        """获取服务的默认国家列表"""
        return self.config.default_countries.get(service, ["US"])

    def update_config(self, **kwargs):
        """更新配置"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                logger.info(f"Configuration updated: {key} = {value}")

    def reload(self):
        """重新加载配置"""
        self._load_config()


# 全局配置管理器实例
config_manager = ConfigManager()


def get_config() -> BotConfig:
    """获取全局配置"""
    return config_manager.config


def is_feature_enabled(feature: str) -> bool:
    """检查功能是否启用"""
    return config_manager.is_feature_enabled(feature)
