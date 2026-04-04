# commands/max.py

import logging

from telegram import Update
from telegram.ext import ContextTypes

from utils.cache_commands import delegate_to_cache_cleaner, delegate_to_service_handler
from utils.command_factory import command_factory
from utils.permissions import Permission

logger = logging.getLogger(__name__)


# --- Command Handler Setup ---


async def max_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /max command.

    支持 category 参数: all, monthly, yearly, ultimate, ultimate_yearly, mobile, standard
    默认: ultimate_yearly

    示例:
    - /max - 显示 ultimate_yearly 全球排名
    - /max yearly - 显示 yearly 全球排名
    - /max us uk - 查询美国和英国的价格
    - /max yearly us uk - 查询美国和英国的价格（忽略 category）
    """
    await delegate_to_service_handler(
        update,
        context,
        service_key="max_price_bot",
        service_display_name="HBO Max",
    )


async def max_clean_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /max_cleancache command."""
    await delegate_to_cache_cleaner(
        update,
        context,
        service_key="max_price_bot",
        service_display_name="HBO Max",
    )


# Register commands
command_factory.register_command(
    "max", max_command, permission=Permission.USER, description="HBO Max订阅价格查询"
)
command_factory.register_command(
    "max_cleancache",
    max_clean_cache_command,
    permission=Permission.ADMIN,
    description="清理HBO Max缓存",
)
