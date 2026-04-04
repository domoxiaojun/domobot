"""
Apple Services 价格查询命令
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from utils.cache_commands import delegate_to_cache_cleaner, delegate_to_service_handler
from utils.command_factory import command_factory
from utils.permissions import Permission

logger = logging.getLogger(__name__)


async def apple_services_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handles the /aps command to query Apple service prices."""
    await delegate_to_service_handler(
        update,
        context,
        service_key="apple_services_service",
        service_display_name="Apple Services",
    )


async def apple_services_clean_cache_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handles the /aps_cleancache command to clear Apple Services related caches."""
    await delegate_to_cache_cleaner(
        update,
        context,
        service_key="apple_services_service",
        service_display_name="Apple Services",
    )


# Register the commands
command_factory.register_command(
    "aps",
    apple_services_command,
    permission=Permission.USER,
    description="查询Apple服务价格 (iCloud, Apple One, Apple Music)",
)
command_factory.register_command(
    "aps_cleancache",
    apple_services_clean_cache_command,
    permission=Permission.ADMIN,
    description="清理Apple服务缓存",
)
