# commands/spotify.py

import logging

from telegram import Update
from telegram.ext import ContextTypes

from utils.cache_commands import delegate_to_cache_cleaner, delegate_to_service_handler
from utils.command_factory import command_factory
from utils.permissions import Permission

logger = logging.getLogger(__name__)


# --- Command Handler Setup ---


async def spotify_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /sp command."""
    await delegate_to_service_handler(
        update,
        context,
        service_key="spotify_price_bot",
        service_display_name="Spotify",
    )


async def spotify_clean_cache_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handles the /sp_cleancache command."""
    await delegate_to_cache_cleaner(
        update,
        context,
        service_key="spotify_price_bot",
        service_display_name="Spotify",
    )


# Alias for the command
sp_command = spotify_command

# Register commands
command_factory.register_command(
    "sp", sp_command, permission=Permission.USER, description="Spotify订阅价格查询"
)
command_factory.register_command(
    "sp_cleancache",
    spotify_clean_cache_command,
    permission=Permission.ADMIN,
    description="清理Spotify缓存",
)
