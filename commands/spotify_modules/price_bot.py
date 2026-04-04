"""
Spotify 价格查询机器人类

提供 Spotify 订阅价格查询功能
"""

import logging
from typing import Any

import httpx
from telegram.ext import ContextTypes

from utils.country_data import (
    COUNTRY_CODE_TO_CHINESE,
    COUNTRY_CODE_TO_ENGLISH,
    SUPPORTED_COUNTRIES,
    get_country_flag,
)
from utils.formatter import foldable_text_v2, foldable_text_with_markdown_v2
from utils.price_formatter import format_cache_timestamp, get_rank_emoji
from utils.price_query_service import PriceQueryService

logger = logging.getLogger(__name__)


class SpotifyPriceBot(PriceQueryService):
    PRICE_URL = "https://raw.githubusercontent.com/domoxiaojun/spotify-prices/refs/heads/main/spotify_prices_cny_sorted.json"

    async def _fetch_data(
        self, context: ContextTypes.DEFAULT_TYPE
    ) -> dict[str, Any] | None:
        """Fetches Spotify price data from the specified URL."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        try:
            from utils.http_client import create_custom_client

            async with create_custom_client(headers=headers) as client:
                response = await client.get(self.PRICE_URL, timeout=20.0)
                response.raise_for_status()
                return response.json()
        except httpx.RequestError as e:
            logger.error(f"Failed to fetch Spotify price data: {e}")
            return None
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while fetching Spotify data: {e}"
            )
            return None

    # _init_country_mapping: 使用基类 PriceQueryService 的默认实现

    async def _format_price_message(self, country_code: str, price_info: dict) -> str:
        """Formats the price information for a single country."""
        country_info = SUPPORTED_COUNTRIES.get(country_code.upper(), {})

        # Try to get Chinese name in this order:
        # 1. From SUPPORTED_COUNTRIES (our central config with Chinese names)
        # 2. From our static COUNTRY_CODE_TO_CHINESE mapping (comprehensive Chinese names)
        # 3. From price_info if it has country_name_cn (from top 10 data)
        # 4. From our static COUNTRY_CODE_TO_ENGLISH mapping (reliable English names)
        # 5. From price_info country_name as fallback
        # 6. Use country_code as last resort
        country_name_cn = (
            country_info.get("name_cn")
            or COUNTRY_CODE_TO_CHINESE.get(country_code.upper())
            or price_info.get("country_name_cn")
            or COUNTRY_CODE_TO_ENGLISH.get(country_code.upper())
            or price_info.get("country_name", country_code)
        )

        country_flag = get_country_flag(country_code)

        lines = [
            f"📍 国家/地区： {country_name_cn} ({country_code.upper()}) {country_flag}"
        ]

        plans = price_info.get("plans", [])
        if not plans:
            return f"📍 国家/地区: {country_name_cn} ({country_code.upper()}) {country_flag}\n❌ 未找到价格信息"

        # Plan name translation mapping
        plan_names = {
            "Premium Individual": "个人版",
            "Premium Student": "学生版",
            "Premium Duo": "双人版",
            "Premium Family": "家庭版",
        }

        for i, plan in enumerate(plans):
            plan_name = plan.get("plan", "未知套餐")
            plan_name_cn = plan_names.get(plan_name, plan_name)

            # Extract currency, price_number and price_cny
            currency = plan.get("currency", "")
            price_number = plan.get("price_number", "")
            price_cny = plan.get("price_cny", 0)
            original_price = plan.get("price", "价格未知")

            # Determine the connector
            is_last_plan = i == len(plans) - 1
            connector = "" if is_last_plan else ""

            # Format price display with currency, price_number, and CNY
            if currency and price_number and price_cny > 0:
                price_display = f"{currency} {price_number} ≈ ¥{price_cny:.2f}"
            elif price_cny > 0:
                price_display = f"{original_price} ≈ ¥{price_cny:.2f}"
            else:
                price_display = original_price

            lines.append(f"{connector}💰 {plan_name_cn}：{price_display}")

        # Add scraped time if available
        if "scraped_at" in price_info:
            lines.append(f"  📅 数据时间：{price_info['scraped_at']}")

        return "\n".join(lines)

    def _extract_comparison_price(self, item: dict) -> float | None:
        """Extracts the Premium Family plan's CNY price for ranking."""
        plans = item.get("plans", [])
        for plan in plans:
            if plan.get("plan") == "Premium Family":
                price_cny = plan.get("price_cny")
                if price_cny and price_cny > 0:
                    return float(price_cny)
        return None

    async def query_prices(self, query_list: list[str]) -> str:
        """
        Queries prices for a list of specified countries.
        重写基类方法以支持MarkdownV2格式和国家间空行分隔。
        """
        if not self.data:
            error_message = f"❌ 错误：未能加载 {self.service_name} 价格数据。请稍后再试或检查日志。"
            return foldable_text_v2(error_message)

        result_messages = []
        not_found = []

        for query in query_list:
            price_info = self.country_mapping.get(
                query.upper()
            ) or self.country_mapping.get(query)

            if not price_info:
                not_found.append(query)
                continue

            country_code = price_info.get("country_code")
            if country_code:
                formatted_message = await self._format_price_message(
                    country_code, price_info
                )
                if formatted_message:
                    result_messages.append(formatted_message)
                else:
                    not_found.append(query)
            else:
                not_found.append(query)

        # 组装原始文本消息
        raw_message_parts = []
        raw_message_parts.append(f"*🎵 {self.service_name} 订阅价格查询*")
        raw_message_parts.append("")  # Empty line after header

        if result_messages:
            # Add blank lines between countries for better readability
            for i, msg in enumerate(result_messages):
                raw_message_parts.append(msg)
                # Add blank line between countries (except for the last one)
                if i < len(result_messages) - 1:
                    raw_message_parts.append("")
        elif query_list:
            raw_message_parts.append("未能查询到您指定的国家/地区的价格信息。")

        if not_found:
            raw_message_parts.append("")  # Empty line before not found section
            not_found_str = ", ".join(not_found)
            raw_message_parts.append(f"❌ 未找到以下地区的价格信息：{not_found_str}")

        if self.cache_timestamp:
            raw_message_parts.append("")  # Empty line before timestamp
            raw_message_parts.append(format_cache_timestamp(self.cache_timestamp))

        # Join and apply formatting
        raw_final_message = "\n".join(raw_message_parts).strip()
        return foldable_text_with_markdown_v2(raw_final_message)

    async def get_top_cheapest(self, top_n: int = 10) -> str:
        """Gets the top 10 cheapest countries for the Premium Family plan."""
        if not self.data:
            error_msg = f"❌ 错误：未能加载 {self.service_name} 价格数据。"
            return foldable_text_v2(error_msg)

        # Use the pre-calculated top 10 data if available
        top_10_data = self.data.get("_top_10_cheapest_premium_family", {}).get(
            "data", []
        )

        if top_10_data:
            # 组装原始文本，不转义
            message_lines = [f"*🏆 {self.service_name} 全球最低价格排名 (家庭版)*"]
            message_lines.append("")  # Empty line after header

            for item in top_10_data[:top_n]:
                rank = item.get("rank", 0)
                country_code = item.get("country_code", "N/A").upper()

                # Try to get Chinese name in this order:
                # 1. From the item itself (country_name_cn)
                # 2. From SUPPORTED_COUNTRIES (Chinese names)
                # 3. From our static COUNTRY_CODE_TO_CHINESE mapping (comprehensive Chinese names)
                # 4. From our static COUNTRY_CODE_TO_ENGLISH mapping (reliable English names)
                # 5. From the item's country_name as fallback
                country_name_cn = (
                    item.get("country_name_cn")
                    or SUPPORTED_COUNTRIES.get(country_code, {}).get("name_cn")
                    or COUNTRY_CODE_TO_CHINESE.get(country_code)
                    or COUNTRY_CODE_TO_ENGLISH.get(country_code)
                    or item.get("country_name", country_code)
                )

                country_flag = get_country_flag(country_code)

                # Extract currency, price_number and price_cny
                currency = item.get("currency", "")
                price_number = item.get("price_number", "")
                price_cny = item.get("price_cny", 0)
                original_price = item.get("original_price", "价格未知")

                # Format price display with currency, price_number, and CNY
                if currency and price_number and price_cny > 0:
                    price_display = f"{currency} {price_number} ≈ ¥{price_cny:.2f}"
                elif price_cny > 0:
                    price_display = f"{original_price} ≈ ¥{price_cny:.2f}"
                else:
                    price_display = original_price

                # Rank emoji
                rank_emoji = get_rank_emoji(rank)

                message_lines.append(
                    f"{rank_emoji} {country_name_cn} ({country_code}) {country_flag}"
                )
                message_lines.append(f"💰 家庭版: {price_display}")

                # Add blank line between countries (except for the last one)
                if rank < len(top_10_data[:top_n]):
                    message_lines.append("")

            # Use update time from metadata, or cache timestamp as fallback
            updated_at = self.data.get("_top_10_cheapest_premium_family", {}).get(
                "updated_at", ""
            )
            if updated_at:
                message_lines.append("")  # Empty line before timestamp
                message_lines.append(f"⏱ 数据更新时间：{updated_at}")
            elif self.cache_timestamp:
                message_lines.append("")  # Empty line before timestamp
                message_lines.append(format_cache_timestamp(self.cache_timestamp))

        else:
            # Fallback: calculate from individual country data
            countries_with_prices = []
            for key, item in self.data.items():
                if key.startswith("_"):  # Skip metadata
                    continue
                price_cny = self._extract_comparison_price(item)
                if price_cny is not None:
                    countries_with_prices.append({"data": item, "price": price_cny})

            if not countries_with_prices:
                error_msg = f"未能找到足够的可比较 {self.service_name} 家庭版价格信息。"
                return foldable_text_v2(error_msg)

            countries_with_prices.sort(key=lambda x: x["price"])
            top_countries = countries_with_prices[:top_n]

            # 组装原始文本，不转义
            message_lines = [f"*🎵 {self.service_name} 全球最低价格排名 (家庭版)*"]
            message_lines.append("")  # Empty line after header

            for idx, country_data in enumerate(top_countries, 1):
                item = country_data["data"]
                country_code = item.get("country_code", "N/A").upper()
                country_info = SUPPORTED_COUNTRIES.get(country_code, {})

                # Try to get Chinese name in this order:
                # 1. From SUPPORTED_COUNTRIES (Chinese names)
                # 2. From our static COUNTRY_CODE_TO_CHINESE mapping (comprehensive Chinese names)
                # 3. From our static COUNTRY_CODE_TO_ENGLISH mapping (reliable English names)
                # 4. From the item's country_name as fallback
                country_name_cn = (
                    country_info.get("name_cn")
                    or COUNTRY_CODE_TO_CHINESE.get(country_code)
                    or COUNTRY_CODE_TO_ENGLISH.get(country_code)
                    or item.get("country_name", country_code)
                )

                country_flag = get_country_flag(country_code)
                price_cny = country_data["price"]

                # Find the Premium Family plan for original price and details
                currency = ""
                price_number = ""
                original_price = "价格未知"
                plans = item.get("plans", [])
                for plan in plans:
                    if plan.get("plan") == "Premium Family":
                        currency = plan.get("currency", "")
                        price_number = plan.get("price_number", "")
                        original_price = plan.get("price", "价格未知")
                        break

                # Format price display with currency, price_number, and CNY
                if currency and price_number and price_cny > 0:
                    price_display = f"{currency} {price_number} ≈ ¥{price_cny:.2f}"
                elif price_cny > 0:
                    price_display = f"{original_price} ≈ ¥{price_cny:.2f}"
                else:
                    price_display = original_price

                # Rank emoji
                rank_emoji = get_rank_emoji(idx)

                message_lines.append(
                    f"{rank_emoji} {country_name_cn} ({country_code}) {country_flag}"
                )
                message_lines.append(f"💰 家庭版: {price_display}")

                # Add blank line between countries (except for the last one)
                if idx < len(top_countries):
                    message_lines.append("")

            if self.cache_timestamp:
                message_lines.append("")  # Empty line before timestamp
                message_lines.append(format_cache_timestamp(self.cache_timestamp))

        # 组装完整文本，使用 foldable_text_with_markdown_v2 处理MarkdownV2格式
        body_text = "\n".join(message_lines).strip()
        return foldable_text_with_markdown_v2(body_text)
