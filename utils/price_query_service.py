# utils/price_query_service.py

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from utils.constants import TIME_FOUR_HOURS
from utils.country_data import (
    COUNTRY_CODE_TO_CHINESE,
    COUNTRY_CODE_TO_ENGLISH,
    COUNTRY_NAME_TO_CODE,
    SUPPORTED_COUNTRIES,
)

# Note: CacheManager import removed - now uses injected Redis cache manager
from utils.formatter import escape_v2, foldable_text_v2
from utils.message_manager import (
    delete_user_command,
    send_error,
    send_search_result,
    send_success,
)
from utils.rate_converter import RateConverter

logger = logging.getLogger(__name__)


class PriceQueryService(ABC):
    """
    Abstract base class for services that query prices, cache them, and format them for Telegram.
    """

    def __init__(
        self,
        service_name: str,
        cache_manager,
        rate_converter: RateConverter,
        cache_duration_seconds: int = TIME_FOUR_HOURS,
        subdirectory: str | None = None,
    ):
        self.service_name = service_name
        self.cache_manager = cache_manager
        self.rate_converter = rate_converter
        self.cache_duration = cache_duration_seconds
        self.subdirectory = subdirectory
        self.cache_key = f"{service_name.lower().replace(' ', '_')}_prices"

        self.data: Any = None
        self.cache_timestamp: int = 0
        self.country_mapping: dict[str, Any] = {}
        self.reverse_mapping: dict[int, str] = (
            {}
        )  # 反向映射：data object id -> country_code (性能优化)
        self._country_mapping_data_id: int | None = None  # 用于缓存 country_mapping

    @abstractmethod
    async def _fetch_data(self, context: ContextTypes.DEFAULT_TYPE) -> Any:
        """
        Fetches the raw data for the service from the network.
        Must be implemented by subclasses.
        """
        pass

    def _init_country_mapping(self) -> dict[str, Any]:
        """
        Initializes the country name/code to data mapping from self.data.
        Default implementation for dict-based data structure (like Spotify, Max).
        Subclasses with different data structures should override this.

        注意：子类实现时应该同时构建 self.reverse_mapping，映射格式为:
        self.reverse_mapping[id(data_value)] = country_code
        这样可以在 query_prices() 中实现 O(1) 查找而非 O(n) 遍历。
        """
        mapping = {}
        if not self.data:
            return mapping

        # Default implementation assumes self.data is a dict with country codes as keys
        if not isinstance(self.data, dict):
            logger.warning(
                f"{self.service_name}: data is not a dict, subclass should override _init_country_mapping"
            )
            return mapping

        for key, value in self.data.items():
            # Skip metadata entries (keys starting with _)
            if key.startswith("_"):
                continue

            country_code = key.upper()
            # Build reverse mapping for O(1) lookup
            self.reverse_mapping[id(value)] = country_code

            mapping[country_code] = value

            # 1. Map by Chinese name from SUPPORTED_COUNTRIES (highest priority)
            if country_code in SUPPORTED_COUNTRIES:
                country_info = SUPPORTED_COUNTRIES[country_code]
                if "name_cn" in country_info:
                    mapping[country_info["name_cn"]] = value
                if "name" in country_info:
                    mapping[country_info["name"]] = value

            # 2. Map by English name from COUNTRY_CODE_TO_ENGLISH
            if country_code in COUNTRY_CODE_TO_ENGLISH:
                mapping[COUNTRY_CODE_TO_ENGLISH[country_code]] = value

            # 3. Map by Chinese name from COUNTRY_CODE_TO_CHINESE
            if country_code in COUNTRY_CODE_TO_CHINESE:
                mapping[COUNTRY_CODE_TO_CHINESE[country_code]] = value

            # 4. Map by country name from the JSON data (fallback)
            if isinstance(value, dict) and "country_name" in value:
                mapping[value["country_name"]] = value

            # 5. Map from COUNTRY_NAME_TO_CODE for Chinese input support
            for chinese_name, code in COUNTRY_NAME_TO_CODE.items():
                if code.upper() == country_code:
                    mapping[chinese_name] = value

        return mapping

    @abstractmethod
    async def _format_price_message(
        self, country_code: str, price_info: Any
    ) -> str | None:
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
        cached_data = await self.cache_manager.load_cache(
            self.cache_key,
            max_age_seconds=self.cache_duration,
            subdirectory=self.subdirectory,
        )

        if cached_data:
            self.data = cached_data
            self.cache_timestamp = await self.cache_manager.get_cache_timestamp(
                self.cache_key, subdirectory=self.subdirectory
            )
            logger.info(f"Loaded {self.service_name} data from cache.")
        else:
            logger.info(
                f"{self.service_name} cache is stale or non-existent. Fetching from network..."
            )
            fetched_data = await self._fetch_data(context)
            if fetched_data:
                self.data = fetched_data
                await self.cache_manager.save_cache(
                    self.cache_key,
                    fetched_data,
                    subdirectory=self.subdirectory,
                    ttl=self.cache_duration,
                )
                self.cache_timestamp = int(time.time())
                logger.info(
                    f"Fetched {self.service_name} data from network and cached successfully."
                )
            else:
                logger.error(
                    f"Failed to fetch {self.service_name} data from network. Attempting to load expired cache as fallback."
                )
                expired_cache = await self.cache_manager.load_cache(
                    self.cache_key, max_age_seconds=None, subdirectory=self.subdirectory
                )
                if expired_cache:
                    self.data = expired_cache
                    self.cache_timestamp = await self.cache_manager.get_cache_timestamp(
                        self.cache_key, subdirectory=self.subdirectory
                    )
                    logger.warning(
                        f"Loaded expired {self.service_name} cache as fallback."
                    )
                else:
                    logger.critical(
                        f"Could not load any {self.service_name} data (neither fresh nor expired cache)."
                    )

        if self.data:
            # 只在数据变化时才重新初始化 country_mapping（性能优化）
            current_data_id = id(self.data)
            if self._country_mapping_data_id != current_data_id:
                self.reverse_mapping = {}  # 清空旧的反向映射
                self.country_mapping = self._init_country_mapping()
                self._country_mapping_data_id = current_data_id
                logger.debug(f"{self.service_name} country_mapping 已重新初始化")

    async def query_prices(self, query_list: list[str]) -> str:
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
            price_info = self.country_mapping.get(
                normalized_query.upper()
            ) or self.country_mapping.get(normalized_query)

            if not price_info:
                not_found.append(query)
                continue

            # 使用反向映射进行 O(1) 查找（性能优化：避免 O(n) 遍历）
            found_code = self.reverse_mapping.get(id(price_info))

            if found_code:
                formatted_message = await self._format_price_message(
                    found_code, price_info
                )
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
            not_found_str = ", ".join(not_found)
            body_parts.append(f"❌ 未找到以下地区的价格信息：{not_found_str}")

        if self.cache_timestamp:
            update_time_str = datetime.fromtimestamp(self.cache_timestamp).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
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
                await send_error(
                    context,
                    update.message.chat_id,
                    escape_v2(
                        f"❌ 错误：未能加载 {self.service_name} 价格数据，请检查网络连接或稍后再试。"
                    ),
                    parse_mode="MarkdownV2",
                )
                await delete_user_command(
                    context, update.message.chat_id, update.message.message_id
                )
                return

            if not context.args:
                result = await self.get_top_cheapest()
            else:
                result = await self.query_prices(context.args)

            await send_search_result(
                context,
                update.message.chat_id,
                result,
                parse_mode="MarkdownV2",
                disable_web_page_preview=True,
            )
            await delete_user_command(
                context, update.message.chat_id, update.message.message_id
            )

        except Exception as e:
            logger.error(
                f"Error processing {self.service_name} command: {e}", exc_info=True
            )
            await send_error(
                context,
                update.message.chat_id,
                escape_v2(f"❌ 执行查询时发生错误: {e}"),
                parse_mode="MarkdownV2",
            )
            await delete_user_command(
                context, update.message.chat_id, update.message.message_id
            )

    async def clean_cache_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handles the command to clear the cache for this service."""
        if not update.message:
            return

        try:
            await self.cache_manager.clear_cache(
                key=self.cache_key, subdirectory=self.subdirectory
            )
            await send_success(
                context,
                update.message.chat_id,
                escape_v2(f"✅ {self.service_name} 缓存已清理。"),
                parse_mode="MarkdownV2",
            )
            await delete_user_command(
                context, update.message.chat_id, update.message.message_id
            )
        except Exception as e:
            logger.error(f"Error clearing {self.service_name} cache: {e}")
            await send_error(
                context,
                update.message.chat_id,
                escape_v2(f"❌ 清理 {self.service_name} 缓存时发生错误: {e!s}"),
                parse_mode="MarkdownV2",
            )
            await delete_user_command(
                context, update.message.chat_id, update.message.message_id
            )
