import logging

from telegram import Update
from telegram.ext import ContextTypes

from utils.cache_commands import delegate_to_cache_cleaner, delegate_to_service_handler
from utils.command_factory import command_factory
from utils.permissions import Permission

logger = logging.getLogger(__name__)


# --- Command Handler Setup ---


async def disney_plus_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handles the /ds command for Disney+ price queries."""
    await delegate_to_service_handler(
        update,
        context,
        service_key="disney_price_bot",
        service_display_name="Disney+",
    )


async def disney_plus_clean_cache_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handles the /ds_cleancache command to clear Disney+ related caches."""
    await delegate_to_cache_cleaner(
        update,
        context,
        service_key="disney_price_bot",
        service_display_name="Disney+",
    )


# Alias for the command
disney_command = disney_plus_command

# Register commands
command_factory.register_command(
    "ds", disney_command, permission=Permission.USER, description="Disney+订阅价格查询"
)
command_factory.register_command(
    "ds_cleancache",
    disney_plus_clean_cache_command,
    permission=Permission.ADMIN,
    description="清理Disney+缓存",
)
