"""
Netflix 价格查询机器人类

提供 Netflix 订阅价格查询功能
"""

import logging
from typing import Any

import httpx
from telegram.ext import ContextTypes

from utils.country_data import (
    COUNTRY_CODE_TO_ENGLISH,
    SUPPORTED_COUNTRIES,
    get_country_flag,
)
from utils.formatter import foldable_text_v2, foldable_text_with_markdown_v2
from utils.price_formatter import format_cache_timestamp, get_rank_emoji
from utils.price_query_service import PriceQueryService

logger = logging.getLogger(__name__)


class NetflixPriceBot(PriceQueryService):
    PRICE_URL = "https://opensheet.elk.sh/1b3qotAFrjHai7ny3AGGCTHsZ1xyl4yXviPU3Grqt940/by+regions"

    async def _fetch_data(
        self, context: ContextTypes.DEFAULT_TYPE
    ) -> list[dict[str, Any]] | None:
        """Fetches Netflix price data from the specified URL."""
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
            logger.error(f"Failed to fetch Netflix price data: {e}")
            return None
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while fetching Netflix data: {e}"
            )
            return None

    def _init_country_mapping(self) -> dict[str, Any]:
        """Initializes country name and code to data mapping."""
        mapping = {}
        if not self.data:
            return mapping

        # 创建代码到数据的快速查找字典
        code_to_data = {}

        for item in self.data:
            # 建立反向映射（性能优化：用于 O(1) 查找）
            if item.get("Code"):
                code_upper = item["Code"].upper()
                self.reverse_mapping[id(item)] = code_upper
                mapping[code_upper] = item
                code_to_data[code_upper] = item

                # 添加中文名称映射
                if (
                    code_upper in SUPPORTED_COUNTRIES
                    and "name" in SUPPORTED_COUNTRIES[code_upper]
                ):
                    mapping[SUPPORTED_COUNTRIES[code_upper]["name"]] = item

            if item.get("Translation"):
                mapping[item["Translation"]] = item
            if item.get("Country"):
                mapping[item["Country"]] = item

        # 添加英文名称映射（使用 utils/country_data.py 中的映射）
        for code, english_name in COUNTRY_CODE_TO_ENGLISH.items():
            code_upper = code.upper()
            if code_upper in code_to_data:
                mapping[english_name] = code_to_data[code_upper]

        return mapping

    async def _format_price_message(self, country_code: str, price_info: dict) -> str:
        """Formats the price information for a single country as raw text."""
        country_info = SUPPORTED_COUNTRIES.get(country_code.upper(), {})
        country_name = country_info.get(
            "name_cn", price_info.get("Translation", country_code)
        )
        country_flag = get_country_flag(country_code)
        currency = price_info.get("Currency", "")

        lines = [
            f"📍 国家/地区: {country_name} ({country_code.upper()}) {country_flag}"
        ]

        plan_map = {
            "Mobile": ("移动版", "MobileUSD"),
            "Standard with ads": ("标准广告版", "With_Ads_USD"),
            "Basic": ("基础版", "BasicUSD"),
            "Standard": ("标准版", "StandardUSD"),
            "Premium": ("高级版", "PremiumUSD"),
        }

        plan_keys = list(plan_map.keys())

        # Filter out plans that are not available in the price_info
        available_plans = [
            key
            for key in plan_keys
            if price_info.get(key) and price_info.get(key) != "N/A"
        ]

        for _i, key in enumerate(available_plans):
            name, usd_key = plan_map[key]
            cny_price_str = ""
            try:
                usd_val = float(price_info[usd_key] or 0)
                if usd_val > 0:
                    cny_price = await self.rate_converter.convert(usd_val, "USD", "CNY")
                    if cny_price:
                        cny_price_str = f" ≈ ¥{cny_price:.2f}"
            except (ValueError, TypeError, KeyError):
                pass  # Ignore if conversion fails

            lines.append(f"  • {name}：{price_info[key]} {currency}{cny_price_str}")

        has_extra_members = (
            price_info.get("Extra member slots")
            and price_info.get("Extra member slots") != "N/A"
        )
        if has_extra_members:
            # Process extra member slots format: "Standard: 1 / Premium: 2"
            extra_members_text = price_info["Extra member slots"]
            # Add currency to numbers in the format
            import re

            # Replace numbers with number + currency
            extra_members_formatted = re.sub(
                r"(\d+)", r"\1 " + currency, extra_members_text
            )
            lines.append(f"  • 额外会员：{extra_members_formatted}")

        return "\n".join(lines)

    def _extract_comparison_price(self, item: dict) -> float | None:
        """Extracts the Premium plan's USD price for ranking."""
        if item.get("PremiumUSD") and item.get("PremiumUSD") != "N/A":
            try:
                return float(item["PremiumUSD"])
            except (ValueError, TypeError):
                pass
        return None

    async def query_prices(self, query_list: list[str]) -> str:
        """
        Queries prices for a list of specified countries.
        Note: This overrides the base method to be async.
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

            country_code = price_info.get("Code")
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

        # Assemble raw text message
        raw_message_parts = []
        raw_message_parts.append(f"*🎬 {self.service_name} 订阅价格查询*")
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
            raw_message_parts.append(
                f"\n{format_cache_timestamp(self.cache_timestamp)}"
            )

        # Join and apply formatting
        raw_final_message = "\n".join(raw_message_parts).strip()
        return foldable_text_with_markdown_v2(raw_final_message)

    async def get_top_cheapest(self, top_n: int = 10) -> str:
        """Gets the top 10 cheapest countries for the Premium plan."""
        if not self.data:
            error_message = f"❌ 错误：未能加载 {self.service_name} 价格数据。"
            return foldable_text_v2(error_message)

        countries_with_prices = []
        for item in self.data:
            premium_usd = self._extract_comparison_price(item)
            if premium_usd is not None:
                countries_with_prices.append({"data": item, "price": premium_usd})

        countries_with_prices.sort(key=lambda x: x["price"])
        top_countries = countries_with_prices[:top_n]

        # Assemble raw text message
        raw_message_parts = []
        raw_message_parts.append(f"*🏆 {self.service_name} 全球最低价格排名 (高级版)*")
        raw_message_parts.append("")  # Empty line after header

        for idx, country_data in enumerate(top_countries, 1):
            item = country_data["data"]
            country_code = item.get("Code", "N/A").upper()
            country_info = SUPPORTED_COUNTRIES.get(country_code, {})
            country_name = country_info.get(
                "name_cn", item.get("Translation", country_code)
            )
            country_flag = get_country_flag(country_code)
            premium_cny = (
                await self.rate_converter.convert(country_data["price"], "USD", "CNY")
                or 0.0
            )
            premium_local = item.get("Premium", "")
            currency = item.get("Currency", "")

            # Rank emoji
            rank_emoji = get_rank_emoji(idx)

            country_block = f"{rank_emoji} {country_name} ({country_code}) {country_flag}\n💰 高级版: {premium_local} {currency} ≈ ¥{premium_cny:.2f}"
            raw_message_parts.append(country_block)

            # Add blank line between countries (except for the last one)
            if idx < len(top_countries):
                raw_message_parts.append("")

        if self.cache_timestamp:
            raw_message_parts.append(format_cache_timestamp(self.cache_timestamp))

        # Join and apply formatting
        raw_final_message = "\n".join(raw_message_parts).strip()
        return foldable_text_with_markdown_v2(raw_final_message)
