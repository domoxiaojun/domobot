#!/usr/bin/env python3
"""
多功能Telegram价格查询机器人
支持汇率查询、Steam游戏价格、流媒体订阅价格、应用商店价格查询等功能

功能特点:
- 汇率实时查询和转换
- Steam游戏价格多国对比
- Netflix、Disney+、Spotify等流媒体价格查询
- App Store、Google Play应用价格查询
- 管理员权限系统
- 用户和群组白名单管理
- 用户缓存管理
"""

import asyncio
import importlib
import logging
import logging.handlers
import os
import pkgutil

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
)

# 导入环境变量配置
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    print("⚠️ python-dotenv 未安装，直接使用环境变量")

# ========================================
# 配置日志系统
# ========================================
from utils.config_manager import get_config, BotConfig

config = get_config()

# 确保日志目录存在
os.makedirs(os.path.dirname(config.log_file), exist_ok=True)

# 配置日志系统（带轮换和压缩）
# 日志级别优先从环境变量 LOG_LEVEL 读取，默认为 INFO
log_level = os.getenv("LOG_LEVEL", config.log_level).upper()
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, log_level, logging.INFO),
    handlers=[
        logging.handlers.RotatingFileHandler(
            config.log_file,
            maxBytes=config.log_max_size,
            backupCount=config.log_backup_count,
            encoding="utf-8",
        ),
        logging.StreamHandler(),
    ],
)

# 设置第三方库日志级别
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("pyrogram").setLevel(logging.WARNING)  # pyrofork 保持了 pyrogram 包名
logging.getLogger("pyrogram.session.session").setLevel(logging.WARNING)
logging.getLogger("pyrogram.connection.connection").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# 输出关键配置信息
logger.info("=" * 50)
logger.info(" Telegram Bot 启动")
logger.info("=" * 50)
logger.info(f" 自动删除延迟: {config.auto_delete_delay} 秒")
logger.info(f" 用户命令删除延迟: {config.user_command_delete_delay} 秒")
logger.info(f" 删除用户命令: {'启用' if config.delete_user_commands else '禁用'}")
logger.info(f" 日志级别: {config.log_level.upper()}")
logger.info("=" * 50)

# ========================================
# 导入核心模块
# ========================================
# ========================================
# 导入命令模块
# ========================================
# 注：所有服务模块（netflix, steam, app_store 等）已通过自动发现机制初始化
# 无需在此手动导入
from handlers.user_cache_handler import (
    setup_user_cache_handler,
)  # 新增：导入用户缓存处理器
from utils.command_factory import command_factory
from utils.error_handling import with_error_handling
from utils.log_manager import schedule_log_maintenance
from utils.mysql_user_manager import MySQLUserManager
from utils.permissions import Permission
from utils.rate_converter import RateConverter

# 导入 Redis 和 MySQL 管理器
from utils.redis_cache_manager import RedisCacheManager
from utils.redis_message_delete_scheduler import get_message_delete_scheduler
from utils.redis_stats_manager import RedisStatsManager
from utils.redis_task_scheduler import init_task_scheduler as redis_init_task_scheduler
from utils.script_loader import init_script_loader


@with_error_handling
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理错误"""
    logger.error("Exception while handling an update:", exc_info=context.error)

    # 尝试向用户发送错误信息
    if isinstance(update, Update) and update.effective_message:
        try:
            from utils.config_manager import get_config
            from utils.message_manager import send_message_with_auto_delete

            config = get_config()

            # 使用自动删除功能发送错误消息
            await send_message_with_auto_delete(
                context=context,
                chat_id=update.effective_chat.id,
                text="❌ 处理请求时发生错误，请稍后重试。\n如果问题持续存在，请联系管理员。",
                custom_delay=config.auto_delete_delay,
                reply_to_message_id=(
                    update.effective_message.message_id
                    if hasattr(update.effective_message, "message_id")
                    else None
                ),
            )
        except Exception as e:
            logger.error(f"发送错误消息失败: {e}")  # 记录失败原因而不是静默忽略


def load_commands() -> None:
    """动态加载并注册所有命令"""
    commands_dir = "commands"
    for _, name, _ in pkgutil.iter_modules([commands_dir]):
        try:
            importlib.import_module(f"{commands_dir}.{name}")
            logger.info(f"成功加载命令模块: {name}")
        except Exception as e:
            logger.error(f"加载命令模块 {name} 失败: {e}")


def setup_handlers(application: Application) -> None:
    """设置命令处理器"""

    # 动态加载所有命令
    load_commands()

    # 使用命令工厂设置处理器
    command_factory.setup_handlers(application)

    # 手动添加管理员对话处理器
    from commands.admin_commands import admin_panel_handler

    application.add_handler(admin_panel_handler.get_conversation_handler())

    # 手动添加 Google Play 回调处理器
    from commands.google_play import googleplay_callback_handler

    application.add_handler(
        CallbackQueryHandler(googleplay_callback_handler, pattern="^gp_")
    )

    # 错误处理器
    application.add_error_handler(error_handler)

    logger.info("所有命令处理器已设置完成")


def init_service_bots(
    application: Application, dependencies: dict
) -> tuple[list[str], list[tuple[str, str]]]:
    """动态初始化所有服务机器人

    支持两种自动发现模式：
    1. *_modules 子目录模式：扫描 commands/*_modules/__init__.py 中的 init_*_bot() 函数
    2. 命令文件模式：扫描 commands/*.py 中的 init_*_bot() 函数

    Args:
        application: Telegram Application 实例
        dependencies: 依赖字典，包含 cache_manager, rate_converter, smart_cache_manager 等

    Returns:
        tuple[list[str], list[tuple[str, str]]]: (已初始化的服务列表, 失败的服务列表)
        失败列表格式: [(服务名, 错误信息), ...]
    """
    commands_dir = "commands"
    initialized_services = []
    failed_services = []

    # 遍历 commands 目录
    for _, module_name, is_pkg in pkgutil.iter_modules([commands_dir]):
        service_name = None
        init_function_name = None

        # 模式 1: *_modules 子目录（优先）
        if is_pkg and module_name.endswith("_modules"):
            service_name = module_name.replace("_modules", "")
            init_function_name = f"init_{service_name}_bot"
            module_path = f"{commands_dir}.{module_name}"

        # 模式 2: 命令文件中的 init 函数 (单文件模块)
        elif not is_pkg and not module_name.startswith("_"):
            service_name = module_name
            init_function_name = f"init_{service_name}_bot"
            module_path = f"{commands_dir}.{module_name}"

        # 模式 3: 普通包目录 (如 steam)
        elif is_pkg and not module_name.startswith("_"):
            service_name = module_name
            init_function_name = f"init_{service_name}_bot"
            module_path = f"{commands_dir}.{module_name}"

        else:
            continue

        try:
            # 导入模块
            module = importlib.import_module(module_path)

            # 检查是否有初始化函数
            if hasattr(module, init_function_name):
                init_func = getattr(module, init_function_name)

                # 调用初始化函数，传递标准依赖
                init_func(
                    application=application,
                    cache_manager=dependencies.get("cache_manager"),
                    rate_converter=dependencies.get("rate_converter"),
                    smart_cache_manager=dependencies.get("smart_cache_manager"),
                    task_scheduler=dependencies.get("task_scheduler"),
                )

                initialized_services.append(service_name)
                logger.info(f"✅ {service_name} 服务机器人已自动初始化")
            else:
                logger.debug(
                    f"ℹ️  {module_path} 未提供 {init_function_name} 函数，跳过自动初始化"
                )

        except Exception as e:
            error_msg = str(e)
            failed_services.append((service_name, error_msg))
            logger.error(f"❌ 初始化 {service_name} 服务失败: {e}", exc_info=True)

    return initialized_services, failed_services


async def setup_application(application: Application, config: BotConfig) -> None:
    """异步设置应用"""
    logger.info(" 开始初始化机器人应用...")

    # ========================================
    # 连接重试辅助函数
    # ========================================
    async def connect_with_retry(
        connector,
        name: str,
        max_retries: int = 3,
        delay: float = 2.0,
    ) -> bool:
        """
        带重试机制的连接函数

        Args:
            connector: 具有 connect() 方法的连接器对象
            name: 连接器名称（用于日志）
            max_retries: 最大重试次数
            delay: 重试间隔（秒）

        Returns:
            bool: 连接是否成功

        Raises:
            Exception: 达到最大重试次数后仍失败
        """
        for attempt in range(max_retries):
            try:
                await connector.connect()
                logger.info(f"✅ {name} 连接成功")
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"⚠️ {name} 连接失败 (尝试 {attempt + 1}/{max_retries}): {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"❌ {name} 连接失败，已达到最大重试次数: {e}")
                    raise

    # ========================================
    # 第零步：检查并初始化数据库
    # ========================================
    logger.info("🔍 检查数据库...")
    from utils.database_init import check_and_init_database

    db_initialized = await check_and_init_database(config)
    if not db_initialized:
        logger.error("❌ 数据库初始化失败，无法继续")
        raise RuntimeError("数据库初始化失败")

    # ========================================
    # 第一步：初始化核心组件
    # ========================================
    logger.info(" 初始化核心组件...")

    # 初始化 Redis 缓存管理器
    cache_manager = RedisCacheManager(
        host=config.redis_host,
        port=config.redis_port,
        password=config.redis_password,
        db=config.redis_db,
    )
    await connect_with_retry(cache_manager, "Redis 缓存管理器")

    # 初始化 MySQL 用户管理器
    user_cache_manager = MySQLUserManager(
        host=config.db_host,
        port=config.db_port,
        database=config.db_name,
        user=config.db_user,
        password=config.db_password,
        redis_client=cache_manager.redis_client,
        bot_id=config.bot_id,
    )
    await connect_with_retry(user_cache_manager, "MySQL 用户管理器")

    # 初始化 Redis 统计管理器
    stats_manager = RedisStatsManager(cache_manager.redis_client)

    # 初始化汇率转换器
    from utils.constants import DEFAULT_RATE_CACHE_DURATION

    exchange_rate_keys_str = os.getenv("EXCHANGE_RATE_API_KEYS") or os.getenv(
        "EXCHANGE_RATE_API_KEY", ""
    )
    exchange_rate_keys = [
        k.strip() for k in exchange_rate_keys_str.split(",") if k.strip()
    ]
    rate_cache_duration = int(
        os.getenv("RATE_CACHE_DURATION", DEFAULT_RATE_CACHE_DURATION)
    )

    rate_converter = RateConverter(
        exchange_rate_keys, cache_manager, rate_cache_duration
    )

    # 初始化优化的 HTTP 客户端
    from utils.http_client import get_http_client

    httpx_client = get_http_client()

    # 初始化 Pyrofork 客户端（用于获取高级用户信息）
    # Pyrofork 是 Pyrogram 的活跃社区维护版本，支持最新 Telegram API
    from utils.pyrofork import initialize_pyrofork_client

    pyrofork_initialized = await initialize_pyrofork_client(
        redis_client=cache_manager.redis_client,
        bot_token=config.bot_token,
        api_id=config.telegram_api_id or None,
        api_hash=config.telegram_api_hash or None,
        bot_id=config.bot_id,
    )
    if pyrofork_initialized:
        logger.info("✅ Pyrofork 客户端初始化成功")
    else:
        logger.warning("⚠️ Pyrofork 未配置或初始化失败")
        logger.warning(
            "提示：在 .env 中配置 TELEGRAM_API_ID/TELEGRAM_API_HASH 或通过 /admin 面板配置"
        )

    # 初始化价格历史管理器
    from utils.price_history_manager import PriceHistoryManager

    price_history_manager = PriceHistoryManager(
        host=config.db_host,
        port=config.db_port,
        database=config.db_name,
        user=config.db_user,
        password=config.db_password,
    )
    await price_history_manager.connect()

    # 初始化智能缓存管理器（方案C: Redis 6h + MySQL 24h）
    from utils.smart_cache_manager import SmartCacheManager

    smart_cache_manager = SmartCacheManager(
        redis_cache_manager=cache_manager, price_history_manager=price_history_manager
    )

    logger.info("⚙️ 初始化任务管理系统...")

    # 初始化任务管理器
    from utils.task_manager import get_task_manager

    task_manager = get_task_manager()
    logger.info(f" 任务管理器已初始化，最大任务数: {task_manager.max_tasks}")

    # 初始化 Redis 定时任务调度器
    task_scheduler = redis_init_task_scheduler(
        cache_manager, cache_manager.redis_client
    )
    task_scheduler.set_rate_converter(rate_converter)  # 设置汇率转换器
    application.bot_data["task_scheduler"] = task_scheduler

    # 将核心组件存储到 bot_data 中
    application.bot_data["cache_manager"] = cache_manager
    application.bot_data["rate_converter"] = rate_converter
    application.bot_data["httpx_client"] = httpx_client
    application.bot_data["user_cache_manager"] = user_cache_manager
    application.bot_data["stats_manager"] = stats_manager
    application.bot_data["price_history_manager"] = price_history_manager
    application.bot_data["smart_cache_manager"] = smart_cache_manager
    application.bot_data["bot_id"] = config.bot_id

    logger.info("✅ 核心组件初始化完成")

    # 使用动态加载机制初始化所有服务机器人
    logger.info("🤖 开始初始化服务机器人...")
    dependencies = {
        "cache_manager": cache_manager,
        "rate_converter": rate_converter,
        "smart_cache_manager": smart_cache_manager,
        "task_scheduler": task_scheduler,
    }
    initialized_services, failed_services = init_service_bots(application, dependencies)

    if initialized_services:
        logger.info(
            f"✅ 已自动初始化 {len(initialized_services)} 个服务: {', '.join(initialized_services)}"
        )
    else:
        logger.warning("⚠️ 未发现任何服务需要初始化")

    if failed_services:
        logger.warning(
            f"⚠️ {len(failed_services)} 个服务初始化失败: "
            f"{', '.join([f[0] for f in failed_services])}"
        )

    # 根据配置添加定时清理任务
    cleanup_tasks_added = 0
    # 注意：各服务的定时清理任务已移至各模块初始化函数中注册

    # 启动任务调度器（包含汇率刷新任务）
    task_scheduler.start()
    if cleanup_tasks_added > 0:
        logger.info(
            f" 定时任务调度器已启动，活动任务: {cleanup_tasks_added + 1} 个（含汇率刷新）"
        )
    else:
        logger.info(" 定时任务调度器已启动，仅汇率刷新任务")

    # 初始化并启动 Redis 消息删除调度器
    message_delete_scheduler = get_message_delete_scheduler(cache_manager.redis_client)
    message_delete_scheduler.start(application.bot)
    application.bot_data["message_delete_scheduler"] = message_delete_scheduler
    logger.info("️ 消息删除调度器已启动")

    # 调度日志维护任务
    schedule_log_maintenance()
    logger.info(" 日志维护任务已调度")

    logger.info("✅ 任务管理系统初始化完成")

    # ========================================
    # 第四步：预加载数据
    # ========================================
    logger.info(" 预加载数据...")
    try:
        await rate_converter.get_rates()
        logger.info("✅ 汇率数据预加载完成")
    except Exception as e:
        logger.warning(f"⚠️ 汇率数据预加载失败: {e}")

    # ========================================
    # 第五步：设置命令处理器
    # ========================================
    logger.info("🔧 设置命令处理器...")
    setup_handlers(application)
    logger.info("✅ 命令处理器设置完成")

    # ========================================
    # 第五步半：设置用户缓存处理器
    # ========================================
    logger.info("🔧 设置用户缓存处理器...")
    setup_user_cache_handler(application)
    logger.info("✅ 用户缓存处理器设置完成")

    # ========================================
    # 第六步：设置机器人命令菜单
    # ========================================
    logger.info(" 设置机器人命令菜单...")

    # 获取所有权限级别的命令
    user_commands = command_factory.get_command_list(Permission.USER)
    admin_commands = command_factory.get_command_list(Permission.ADMIN)
    super_admin_commands = command_factory.get_command_list(Permission.SUPER_ADMIN)

    # 合并所有命令（超级管理员能看到所有命令）
    all_commands = {}
    all_commands.update(user_commands)
    all_commands.update(admin_commands)
    all_commands.update(super_admin_commands)

    # 手动添加由ConversationHandler处理的admin命令
    all_commands["admin"] = "打开管理员面板"

    # 创建机器人命令列表
    bot_commands = [
        BotCommand(command, description)
        for command, description in all_commands.items()
    ]

    try:
        await application.bot.set_my_commands(bot_commands)
        logger.info("✅ 命令菜单设置完成:")
        logger.info(f" 用户命令: {len(user_commands)} 条")
        logger.info(f"‍ 管理员命令: {len(admin_commands)} 条")
        logger.info(f" 超级管理员命令: {len(super_admin_commands)} 条")
        logger.info(f" 总计: {len(bot_commands)} 条命令")
    except Exception as e:
        logger.error(f"❌ 设置机器人命令菜单失败: {e}")

    # ========================================
    # 第六步半：设置机器人描述
    # ========================================
    logger.info("📝 设置机器人描述...")

    try:
        # 读取描述配置
        description = os.getenv("BOT_DESCRIPTION", "")
        short_description = os.getenv("BOT_SHORT_DESCRIPTION", "")

        # 将 \n 转换为真实的换行符
        if description:
            description = description.replace("\\n", "\n")
        if short_description:
            short_description = short_description.replace("\\n", "\n")

        # 设置完整描述
        if description:
            await application.bot.set_my_description(description=description)
            logger.info(f"✅ Bot 完整描述设置成功: {description[:50]}...")
        else:
            logger.warning("⚠️  未配置 Bot 描述 (BOT_DESCRIPTION)")

        # 设置简短描述
        if short_description:
            await application.bot.set_my_short_description(
                short_description=short_description
            )
            logger.info(f"✅ Bot 简短描述设置成功: {short_description}")
        else:
            logger.warning("⚠️  未配置 Bot 简短描述 (BOT_SHORT_DESCRIPTION)")

        logger.info("📝 Bot 描述设置完成")

    except Exception as e:
        logger.error(f"❌ 设置 Bot 描述失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        # 不影响 Bot 启动，继续执行

    # ========================================
    # 第七步：加载自定义脚本（可选）
    # ========================================
    if config.load_custom_scripts:
        logger.info(" 加载自定义脚本...")
        script_loader = init_script_loader(config.custom_scripts_dir)

        # 准备机器人上下文供脚本使用
        bot_context = {
            "application": application,
            "cache_manager": cache_manager,
            "rate_converter": rate_converter,
            "task_scheduler": task_scheduler,
            "user_cache_manager": user_cache_manager,  # 新增：为脚本提供用户缓存管理器
            "stats_manager": stats_manager,  # 新增：统计管理器
            "config": config,
            "logger": logger,
        }

        # 加载脚本
        success = script_loader.load_scripts(bot_context)
        if success:
            logger.info("✅ 自定义脚本加载完成")
        else:
            logger.warning("⚠️ 部分自定义脚本加载失败")

        # 将脚本加载器存储到bot_data中
        application.bot_data["script_loader"] = script_loader
    else:
        logger.info(" 自定义脚本加载已禁用")

    logger.info(" 机器人应用初始化完成！")


async def cleanup_application(application: Application) -> None:
    """清理应用资源

    关闭顺序：
    1. 先停止调度器（阻止新任务产生）
    2. 等待正在执行的任务完成
    3. 关闭网络连接
    4. 关闭任务管理器
    5. 关闭数据库连接
    """
    logger.info(" 开始清理应用资源...")

    try:
        # ========================================
        # 第一步：停止调度器（先阻止新任务产生）
        # ========================================
        if "task_scheduler" in application.bot_data:
            application.bot_data["task_scheduler"].stop()
            logger.info("✅ 定时任务调度器已停止")

        if "message_delete_scheduler" in application.bot_data:
            application.bot_data["message_delete_scheduler"].stop()
            logger.info("✅ 消息删除调度器已停止")

        # 等待正在执行的任务完成
        await asyncio.sleep(0.5)

        # ========================================
        # 第二步：等待后台任务完成（SmartCacheManager）
        # ========================================
        if "smart_cache_manager" in application.bot_data:
            await application.bot_data["smart_cache_manager"].wait_for_background_tasks(
                timeout=10.0
            )
            logger.info("✅ 后台缓存任务已完成")

        # ========================================
        # 第三步：关闭网络连接
        # ========================================
        # 停止 Pyrofork 客户端
        from utils.pyrofork import stop_pyrofork_client

        await stop_pyrofork_client()
        logger.info("✅ Pyrofork 客户端已停止")

        # 关闭 httpx 客户端
        from utils.http_client import close_global_client

        await close_global_client()
        logger.info("✅ httpx客户端已关闭")

        # ========================================
        # 第四步：关闭任务管理器
        # ========================================
        from utils.task_manager import shutdown_task_manager

        await shutdown_task_manager()
        logger.info("✅ 任务管理器已关闭")

        # ========================================
        # 第五步：关闭数据库连接
        # ========================================
        if "cache_manager" in application.bot_data:
            await application.bot_data["cache_manager"].close()
            logger.info("✅ Redis 连接已关闭")

        if "user_cache_manager" in application.bot_data:
            await application.bot_data["user_cache_manager"].close()
            logger.info("✅ MySQL用户管理器已关闭")

        if "price_history_manager" in application.bot_data:
            await application.bot_data["price_history_manager"].close()
            logger.info("✅ 价格历史管理器已关闭")

        logger.info(" 应用资源清理完成")

    except Exception as e:
        logger.error(f"❌ 清理资源时出错: {e}")


def main() -> None:
    """主函数"""
    # ========================================
    # 第一步：验证环境配置
    # ========================================
    logger.info(" 验证环境配置...")
    config = get_config()

    # 验证 Bot Token
    bot_token = config.bot_token
    if not bot_token:
        logger.error("❌ 未设置 BOT_TOKEN 环境变量")
        return

    # 验证超级管理员ID
    super_admin_ids = config.super_admin_ids
    if not super_admin_ids:
        logger.error("❌ 未设置 SUPER_ADMIN_ID 环境变量")
        return

    logger.info(f"✅ 超级管理员ID: {super_admin_ids}")
    logger.info(f"✅ Bot ID: {config.bot_id}")

    # 验证数据库配置
    if not config.db_host or not config.db_user or not config.db_name:
        logger.error("❌ 数据库配置不完整，请检查 DB_HOST, DB_USER, DB_NAME")
        return

    logger.info(
        f"✅ 数据库配置: {config.db_user}@{config.db_host}:{config.db_port}/{config.db_name}"
    )

    # 验证 Redis 配置
    logger.info(f"✅ Redis 配置: {config.redis_host}:{config.redis_port}")

    # ========================================
    # 第二步：创建并配置应用
    # ========================================
    logger.info(" 创建 Telegram Bot 应用...")
    application = Application.builder().token(bot_token).build()

    # 设置异步初始化和清理回调
    async def init_and_run(app: Application) -> None:
        await setup_application(app, config)
        logger.info("✅ 机器人启动完成，开始服务...")

    application.post_init = init_and_run
    application.post_shutdown = cleanup_application

    # ========================================
    # 第三步：启动机器人
    # ========================================
    try:
        if config.webhook_url:
            # Webhook 模式
            url_path = f"/telegram/{config.bot_token}/webhook"
            webhook_url = f"{config.webhook_url.rstrip('/')}{url_path}"

            logger.info(" Webhook 模式启动")
            logger.info(f" Webhook URL: {webhook_url}")
            logger.info(f" 本地监听: {config.webhook_listen}:{config.webhook_port}")

            application.run_webhook(
                listen=config.webhook_listen,
                port=config.webhook_port,
                url_path=url_path,
                secret_token=config.webhook_secret_token,
                webhook_url=webhook_url,
            )
        else:
            # Polling 模式
            logger.info(" Polling 模式启动")
            application.run_polling(allowed_updates=Update.ALL_TYPES)

    except KeyboardInterrupt:
        logger.info("⏹️ 接收到停止信号，正在关闭机器人...")
    except Exception as e:
        logger.error(f"❌ 机器人运行时出错: {e}")
    finally:
        logger.info(" 机器人已停止")


if __name__ == "__main__":
    main()
