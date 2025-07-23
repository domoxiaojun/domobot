# utils/price_query_service.py

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any

from telegram import Update
from telegram.ext import ContextTypes

from utils.cache_manager import CacheManager
from utils.rate_converter import RateConverter
from utils.formatter import escape_v2, foldable_text_v2
from utils.message_manager import schedule_message_deletion
from utils.config_manager import get_config

logger = logging.getLogger(__name__)


class PriceQueryService(ABC):
    """
    Abstract base class for services that query prices, cache them, and format them for Telegram.
    """

    def __init__(self, service_name: str, cache_manager: CacheManager, rate_converter: RateConverter, cache_duration_seconds: int = 4 * 3600, subdirectory: str | None = None):
        self.service_name = service_name
        self.cache_manager = cache_manager
        self.rate_converter = rate_converter
        self.cache_duration = cache_duration_seconds
        self.subdirectory = subdirectory
        self.cache_key = f"{service_name.lower().replace(' ', '_')}_prices"

        self.data: Any = None
        self.cache_timestamp: int = 0
        self.country_mapping: Dict[str, Any] = {}

    @abstractmethod
    async def _fetch_data(self, context: ContextTypes.DEFAULT_TYPE) -> Any:
        """
        Fetches the raw data for the service from the network.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    def _init_country_mapping(self) -> Dict[str, Any]:
        """
        Initializes the country name/code to data mapping from self.data.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    async def _format_price_message(self, country_code: str, price_info: Any) -> str | None:
        """
        Formats the price information for a single country into a Markdown string.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    def _extract_comparison_price(self, country_data: Any) -> float | None:
        """
        Extracts a specific price (e.g., premium plan in CNY) for ranking.
        Must be implemented by subclasses.
        """
        pass
    
    @abstractmethod
    async def get_top_cheapest(self, top_n: int = 10) -> str:
        """
        Gets the top N cheapest countries based on the comparison price.
        Must be implemented by subclasses to handle specific data structures.
        """
        pass


    async def load_or_fetch_data(self, context: ContextTypes.DEFAULT_TYPE):
        """
        Loads data from cache or fetches new data from the network.
        This is a generic implementation that should work for most services.
        """
        cached_data = self.cache_manager.load_cache(self.cache_key, max_age_seconds=self.cache_duration, subdirectory=self.subdirectory)

        if cached_data:
            self.data = cached_data
            self.cache_timestamp = self.cache_manager.get_cache_timestamp(self.cache_key, subdirectory=self.subdirectory)
            logger.info(f"Loaded {self.service_name} data from cache.")
        else:
            logger.info(f"{self.service_name} cache is stale or non-existent. Fetching from network...")
            fetched_data = await self._fetch_data(context)
            if fetched_data:
                self.data = fetched_data
                self.cache_manager.save_cache(self.cache_key, fetched_data, subdirectory=self.subdirectory)
                self.cache_timestamp = int(time.time())
                logger.info(f"Fetched {self.service_name} data from network and cached successfully.")
            else:
                logger.error(f"Failed to fetch {self.service_name} data from network. Attempting to load expired cache as fallback.")
                expired_cache = self.cache_manager.load_cache(self.cache_key, max_age_seconds=None, subdirectory=self.subdirectory)
                if expired_cache:
                    self.data = expired_cache
                    self.cache_timestamp = self.cache_manager.get_cache_timestamp(self.cache_key, subdirectory=self.subdirectory)
                    logger.warning(f"Loaded expired {self.service_name} cache as fallback.")
                else:
                    logger.critical(f"Could not load any {self.service_name} data (neither fresh nor expired cache).")

        if self.data:
            self.country_mapping = self._init_country_mapping()

    async def query_prices(self, query_list: List[str]) -> str:
        """
        Queries prices for a list of specified countries.
        """
        if not self.data:
            error_msg = f"❌ 错误：未能加载 {self.service_name} 价格数据。请稍后再试或检查日志。"
            return foldable_text_v2(error_msg)

        result_messages = []
        not_found = []

        for query in query_list:
            # Normalize GB to UK for services that use UK
            normalized_query = "UK" if query.upper() == "GB" else query
            price_info = self.country_mapping.get(normalized_query.upper()) or self.country_mapping.get(normalized_query)

            if not price_info:
                not_found.append(query)
                continue

            # Find the primary country code for the matched data
            found_code = None
            # Handle cases where data is a list of dicts vs. a dict of dicts
            if isinstance(self.data, dict):
                for code, data_val in self.data.items():
                    if data_val == price_info:
                        found_code = code
                        break
            elif isinstance(self.data, list):
                 for item in self.data:
                    # This condition needs to be robust. Let's assume a 'Code' field.
                    if item == price_info:
                        found_code = item.get('Code')
                        break
            
            if found_code:
                formatted_message = await self._format_price_message(found_code, price_info)
                if formatted_message:
                    result_messages.append(formatted_message)
                else:
                    not_found.append(query)
            else:
                # This case should ideally not be reached if mapping is correct
                not_found.append(query)

        # 组装原始文本
        header = f"📱 {self.service_name} 订阅价格查询"
        body_parts = []
        
        if result_messages:
            body_parts.extend(result_messages)
        elif query_list:
            body_parts.append("未能查询到您指定的国家/地区的价格信息。")

        if not_found:
            not_found_str = ', '.join(not_found)
            body_parts.append(f"❌ 未找到以下地区的价格信息：{not_found_str}")

        if self.cache_timestamp:
            update_time_str = datetime.fromtimestamp(self.cache_timestamp).strftime('%Y-%m-%d %H:%M:%S')
            body_parts.append(f"⏱ 数据更新时间 (缓存)：{update_time_str}")

        if body_parts:
            body_text = "\n\n".join(body_parts)
            full_text = f"{header}\n\n{body_text}"
            return foldable_text_v2(full_text)
        else:
            return foldable_text_v2(header)

    async def command_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Generic command handler for a price query service.
        """
        if not update.message:
            logger.warning("command_handler received an update with no message.")
            return

        try:
            await self.load_or_fetch_data(context)

            if not self.data:
                config = get_config()
                sent_message = await context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text=escape_v2(f"❌ 错误：未能加载 {self.service_name} 价格数据，请检查网络连接或稍后再试。"),
                    parse_mode="MarkdownV2",
                )
                schedule_message_deletion(
                    chat_id=sent_message.chat_id,
                    message_id=sent_message.message_id,
                    delay=config.auto_delete_delay,
                    user_id=update.effective_user.id,
                )
                if config.delete_user_commands:
                    schedule_message_deletion(
                        chat_id=update.message.chat_id,
                        message_id=update.message.message_id,
                        delay=config.user_command_delete_delay,
                        task_type="user_command",
                        user_id=update.effective_user.id,
                    )
                return

            if not context.args:
                result = await self.get_top_cheapest()
            else:
                result = await self.query_prices(context.args)
            
            config = get_config()
            sent_message = await context.bot.send_message(
                chat_id=update.message.chat_id,
                text=result,
                parse_mode="MarkdownV2",
                disable_web_page_preview=True
            )
            schedule_message_deletion(
                chat_id=sent_message.chat_id,
                message_id=sent_message.message_id,
                delay=config.auto_delete_delay,
                user_id=update.effective_user.id,
            )
            if config.delete_user_commands:
                schedule_message_deletion(
                    chat_id=update.message.chat_id,
                    message_id=update.message.message_id,
                    delay=config.user_command_delete_delay,
                    task_type="user_command",
                    user_id=update.effective_user.id,
                )

        except Exception as e:
            logger.error(f"Error processing {self.service_name} command: {e}", exc_info=True)
            config = get_config()
            sent_message = await context.bot.send_message(
                chat_id=update.message.chat_id,
                text=escape_v2(f"❌ 执行查询时发生错误: {e}"),
                parse_mode="MarkdownV2",
            )
            schedule_message_deletion(
                chat_id=sent_message.chat_id,
                message_id=sent_message.message_id,
                delay=config.auto_delete_delay,
                user_id=update.effective_user.id,
            )
            if config.delete_user_commands:
                schedule_message_deletion(
                    chat_id=update.message.chat_id,
                    message_id=update.message.message_id,
                    delay=config.user_command_delete_delay,
                    task_type="user_command",
                    user_id=update.effective_user.id,
                )

    async def clean_cache_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles the command to clear the cache for this service."""
        if not update.message:
            return
            
        config = get_config()
        try:
            self.cache_manager.clear_cache(key=self.cache_key, subdirectory=self.subdirectory)
            sent_message = await context.bot.send_message(
                chat_id=update.message.chat_id,
                text=escape_v2(f"✅ {self.service_name} 缓存已清理。"),
                parse_mode="MarkdownV2",
            )
            schedule_message_deletion(
                chat_id=sent_message.chat_id,
                message_id=sent_message.message_id,
                delay=config.auto_delete_delay,
                user_id=update.effective_user.id,
            )
            if config.delete_user_commands:
                schedule_message_deletion(
                    chat_id=update.message.chat_id,
                    message_id=update.message.message_id,
                    delay=config.user_command_delete_delay,
                    task_type="user_command",
                    user_id=update.effective_user.id,
                )
        except Exception as e:
            logger.error(f"Error clearing {self.service_name} cache: {e}")
            sent_message = await context.bot.send_message(
                chat_id=update.message.chat_id,
                text=escape_v2(f"❌ 清理 {self.service_name} 缓存时发生错误: {str(e)}"),
                parse_mode="MarkdownV2",
            )
            schedule_message_deletion(
                chat_id=sent_message.chat_id,
                message_id=sent_message.message_id,
                delay=config.auto_delete_delay,
                user_id=update.effective_user.id,
            )
            if config.delete_user_commands:
                schedule_message_deletion(
                    chat_id=update.message.chat_id,
                    message_id=update.message.message_id,
                    delay=config.user_command_delete_delay,
                    task_type="user_command",
                    user_id=update.effective_user.id,
                )