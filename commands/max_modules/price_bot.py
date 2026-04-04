"""
Max 价格查询机器人类

提供 Max (HBO Max) 订阅价格查询功能
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


class MaxPriceBot(PriceQueryService):
    PRICE_URL = "https://raw.githubusercontent.com/SzeMeng76/hbo-max-global-prices/refs/heads/main/max_prices_cny_sorted.json"

    async def _fetch_data(
        self, context: ContextTypes.DEFAULT_TYPE
    ) -> dict[str, Any] | None:
        """Fetches HBO Max price data from the specified URL."""
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
            logger.error(f"Failed to fetch HBO Max price data: {e}")
            return None
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while fetching HBO Max data: {e}"
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

        # Plan name translation mapping for HBO Max
        plan_names = {
            # Basic HBO Max plans
            "HBO Max Basic": "基础版 (HBO Max Basic)",
            "HBO Max Ultimate": "旗舰版 (HBO Max Ultimate)",
            "HBO Max (With Ads)": "含广告版 (HBO Max With Ads)",
            "HBO Max (Ad-Free)": "无广告版 (HBO Max Ad-Free)",
            # Standard plan types (统一后的标准名称)
            "Mobile": "手机版 (Mobile)",
            "Standard": "标准版 (Standard)",
            "Ultimate": "至尊版 (Ultimate)",  # Platino映射后的统一名称
            "Premium": "高级版 (Premium)",
            "Basic": "基础版 (Basic)",
            # Legacy names (向后兼容)
            "Ponsel": "手机版 (Ponsel)",
            "Standar": "标准版 (Standar)",
            "Platinum": "白金版 (Platinum)",
            # Spanish/Latin America plans (原始名称显示)
            "Básico con Anuncios": "基础版含广告 (Básico con Anuncios)",
            "Estándar": "标准版 (Estándar)",
            "Platino": "至尊版 (Platino → Ultimate)",  # 显示映射关系
            # 繁体中文套餐名（台湾、香港）
            "標準": "标准版 (標準 → Standard)",
            "高級": "至尊版 (高級 → Ultimate)",
            "手機": "手机版 (手機 → Mobile)",
            "基礎": "基础版 (基礎 → Basic)",
            # Bundle plans
            "HBO Max + TNT Sports Basic": "HBO Max + TNT Sports 基础版",
            "HBO Max + TNT Sports Standard": "HBO Max + TNT Sports 标准版",
            "HBO Max + TNT Sports Premium": "HBO Max + TNT Sports 高级版",
        }

        # Group plans by billing cycle for better organization
        monthly_plans = []
        yearly_plans = []
        other_plans = []

        for plan in plans:
            plan_group = plan.get("plan_group", "unknown")
            if plan_group == "monthly":
                monthly_plans.append(plan)
            elif plan_group == "yearly":
                yearly_plans.append(plan)
            else:
                other_plans.append(plan)

        # Display monthly plans first, then yearly, then others
        sorted_plans = monthly_plans + yearly_plans + other_plans

        for i, plan in enumerate(sorted_plans):
            plan_name = plan.get("plan_name", "未知套餐")
            plan_group = plan.get("plan_group", "unknown")

            # For bundle plans, use original_name or name instead of translated plan_name
            if plan_group == "bundle":
                bundle_name = plan.get("original_name") or plan.get("name", plan_name)
                plan_name_cn = f"套餐包 ({bundle_name})"
            else:
                plan_name_cn = plan_names.get(plan_name, plan_name)

            # Extract currency, price_number and price_cny
            original_currency = plan.get("original_currency", "")
            original_price_number = plan.get("original_price_number", "")
            monthly_price = plan.get(
                "monthly_price", original_price_number
            )  # 获取月价格用于显示
            price_cny = plan.get("price_cny", 0)
            original_price = plan.get("original_price", "价格未知")
            billing_cycle = plan.get("billing_cycle", "")

            # Determine the connector
            is_last_plan = i == len(sorted_plans) - 1
            connector = "" if is_last_plan else ""

            # Format price display with currency, price_number, and CNY
            # 对于年付套餐，显示月价格但标注是年付
            if original_currency and price_cny > 0:
                if billing_cycle and "年" in billing_cycle:
                    # 年付套餐：显示月价格 × 12 = 年价格
                    if monthly_price and float(monthly_price) != float(
                        original_price_number
                    ):
                        price_display = f"{original_currency} {monthly_price}/月 × 12 = {original_currency} {original_price_number}/年 ≈ ¥{price_cny:.2f}"
                    else:
                        price_display = f"{original_currency} {original_price_number} ({billing_cycle}) ≈ ¥{price_cny:.2f}"
                elif billing_cycle:
                    price_display = f"{original_currency} {original_price_number} ({billing_cycle}) ≈ ¥{price_cny:.2f}"
                else:
                    price_display = f"{original_currency} {original_price_number} ≈ ¥{price_cny:.2f}"
            elif price_cny > 0:
                if billing_cycle:
                    price_display = (
                        f"{original_price} ({billing_cycle}) ≈ ¥{price_cny:.2f}"
                    )
                else:
                    price_display = f"{original_price} ≈ ¥{price_cny:.2f}"
            else:
                price_display = original_price

            lines.append(f"{connector}💰 {plan_name_cn}：{price_display}")

        return "\n".join(lines)

    def _extract_comparison_price(self, item: dict) -> float | None:
        """Extracts the cheapest plan's CNY price for ranking."""
        plans = item.get("plans", [])
        if not plans:
            return None

        # Find the cheapest plan among all available plans
        min_price = None
        for plan in plans:
            price_cny = plan.get("price_cny")
            if price_cny and price_cny > 0:
                if min_price is None or price_cny < min_price:
                    min_price = float(price_cny)

        return min_price

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

            country_code = None
            # Extract country code from price_info
            if "plans" in price_info and price_info["plans"]:
                country_code = price_info["plans"][0].get("country_code")

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
        raw_message_parts.append(f"*📺 {self.service_name} 订阅价格查询*")
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

    async def get_top_cheapest(
        self, top_n: int = 10, category: str = "ultimate_yearly"
    ) -> str:
        """Gets the top cheapest countries by category."""
        if not self.data:
            error_msg = f"❌ 错误：未能加载 {self.service_name} 价格数据。"
            return foldable_text_v2(error_msg)

        # Map categories to data keys - 新增ultimate年付分类
        category_mapping = {
            "all": "_top_10_cheapest_all",
            "monthly": "_top_10_cheapest_monthly",
            "yearly": "_top_10_cheapest_yearly",
            "ultimate": "_top_10_cheapest_ultimate",
            "ultimate_yearly": "_top_10_cheapest_ultimate_yearly",  # 新增
            "mobile": "_top_10_cheapest_mobile",
            "standard": "_top_10_cheapest_standard",
        }

        category_names = {
            "all": "全部套餐",
            "monthly": "月付套餐",
            "yearly": "年付套餐",
            "ultimate": "Ultimate套餐",
            "ultimate_yearly": "Ultimate年付套餐",  # 新增
            "mobile": "Mobile套餐",
            "standard": "Standard套餐",
        }

        data_key = category_mapping.get(
            category, "_top_10_cheapest_ultimate_yearly"
        )  # 默认改为ultimate年付
        category_name = category_names.get(category, "Ultimate年付套餐")

        # Use the pre-calculated top 10 data if available
        top_10_data = self.data.get(data_key, {}).get("data", [])

        if top_10_data:
            # 组装原始文本，不转义
            message_lines = [
                f"*🏆 {self.service_name} 全球最低价格排名 ({category_name})*"
            ]
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
                original_currency = item.get("original_currency", "")
                original_price_number = item.get("original_price_number", "")
                monthly_price = item.get(
                    "monthly_price", original_price_number
                )  # 获取月价格用于显示
                price_cny = item.get("price_cny", 0)
                original_price = item.get("original_price", "价格未知")
                plan_name = item.get("plan_name", "未知套餐")
                billing_cycle = item.get("billing_cycle", "")

                # Format price display with currency, price_number, and CNY
                # 对于年付套餐，显示更清晰的价格格式
                if original_currency and price_cny > 0:
                    if billing_cycle and "年" in billing_cycle:
                        # 年付套餐：显示月价格 × 12 = 年价格
                        if monthly_price and float(monthly_price) != float(
                            original_price_number
                        ):
                            price_display = f"{original_currency} {monthly_price}/月 × 12 = {original_currency} {original_price_number}/年 ≈ ¥{price_cny:.2f}"
                        else:
                            price_display = f"{original_currency} {original_price_number} ({billing_cycle}) ≈ ¥{price_cny:.2f}"
                    elif billing_cycle:
                        price_display = f"{original_currency} {original_price_number} ({billing_cycle}) ≈ ¥{price_cny:.2f}"
                    else:
                        price_display = f"{original_currency} {original_price_number} ≈ ¥{price_cny:.2f}"
                elif price_cny > 0:
                    if billing_cycle:
                        price_display = (
                            f"{original_price} ({billing_cycle}) ≈ ¥{price_cny:.2f}"
                        )
                    else:
                        price_display = f"{original_price} ≈ ¥{price_cny:.2f}"
                else:
                    price_display = original_price

                # Rank emoji
                # Rank emoji
                rank_emoji = get_rank_emoji(rank)

                message_lines.append(
                    f"{rank_emoji} {country_name_cn} ({country_code}) {country_flag}"
                )
                message_lines.append(f"💰 {plan_name}: {price_display}")

                # Add blank line between countries (except for the last one)
                if rank < len(top_10_data[:top_n]):
                    message_lines.append("")

            # Use update time from metadata, or cache timestamp as fallback
            updated_at = self.data.get(data_key, {}).get("updated_at", "")
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
                error_msg = f"未能找到足够的可比较 {self.service_name} 价格信息。"
                return foldable_text_v2(error_msg)

            countries_with_prices.sort(key=lambda x: x["price"])
            top_countries = countries_with_prices[:top_n]

            # 组装原始文本，不转义
            message_lines = [
                f"*📺 {self.service_name} 全球最低价格排名 ({category_name})*"
            ]
            message_lines.append("")  # Empty line after header

            for idx, country_data in enumerate(top_countries, 1):
                item = country_data["data"]
                plans = item.get("plans", [])
                if not plans:
                    continue

                country_code = plans[0].get("country_code", "N/A").upper()
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

                # Find the cheapest plan details
                cheapest_plan = None
                for plan in plans:
                    plan_price = plan.get("price_cny", 0)
                    if plan_price == price_cny:
                        cheapest_plan = plan
                        break

                if cheapest_plan:
                    original_currency = cheapest_plan.get("original_currency", "")
                    original_price_number = cheapest_plan.get(
                        "original_price_number", ""
                    )
                    original_price = cheapest_plan.get("original_price", "价格未知")
                    plan_name = cheapest_plan.get("plan_name", "未知套餐")
                    billing_cycle = cheapest_plan.get("billing_cycle", "")

                    # Format price display
                    if original_currency and original_price_number and price_cny > 0:
                        if billing_cycle:
                            price_display = f"{original_currency} {original_price_number} ({billing_cycle}) ≈ ¥{price_cny:.2f}"
                        else:
                            price_display = f"{original_currency} {original_price_number} ≈ ¥{price_cny:.2f}"
                    elif price_cny > 0:
                        if billing_cycle:
                            price_display = (
                                f"{original_price} ({billing_cycle}) ≈ ¥{price_cny:.2f}"
                            )
                        else:
                            price_display = f"{original_price} ≈ ¥{price_cny:.2f}"
                    else:
                        price_display = original_price
                else:
                    plan_name = "最低价格套餐"
                    price_display = f"≈ ¥{price_cny:.2f}"

                # Rank emoji
                rank_emojis = [
                    "1️⃣",
                    "2️⃣",
                    "3️⃣",
                    "4️⃣",
                    "5️⃣",
                    "6️⃣",
                    "7️⃣",
                    "8️⃣",
                    "9️⃣",
                    "🔟",
                ]
                if idx == 1:
                    rank_emoji = "🥇"
                elif idx == 2:
                    rank_emoji = "🥈"
                elif idx == 3:
                    rank_emoji = "🥉"
                elif idx <= 10:
                    rank_emoji = rank_emojis[idx - 1]
                else:
                    rank_emoji = f"{idx}."

                message_lines.append(
                    f"{rank_emoji} {country_name_cn} ({country_code}) {country_flag}"
                )
                message_lines.append(f"💰 {plan_name}: {price_display}")

                # Add blank line between countries (except for the last one)
                if idx < len(top_countries):
                    message_lines.append("")

            if self.cache_timestamp:
                message_lines.append("")  # Empty line before timestamp
                message_lines.append(format_cache_timestamp(self.cache_timestamp))

        # 组装完整文本，使用 foldable_text_with_markdown_v2 处理MarkdownV2格式
        body_text = "\n".join(message_lines).strip()
        return foldable_text_with_markdown_v2(body_text)

    async def command_handler(self, update, context):
        """
        重写基类的 command_handler 以支持 category 参数。

        支持的 category: all, monthly, yearly, ultimate, ultimate_yearly, mobile, standard
        默认: ultimate_yearly
        """
        from utils.formatter import escape_v2
        from utils.message_manager import (
            delete_user_command,
            send_error,
            send_search_result,
        )

        if not update.message:
            logger.warning("command_handler received an update with no message.")
            return

        try:
            # 解析 category 参数
            category = "ultimate_yearly"  # 默认
            args = context.args or []

            valid_categories = [
                "all",
                "monthly",
                "yearly",
                "ultimate",
                "ultimate_yearly",
                "mobile",
                "standard",
            ]

            # 如果第一个参数是 category，提取它
            if args and args[0].lower() in valid_categories:
                category = args[0].lower()
                args = args[1:]  # 移除 category 参数

            # 加载数据
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

            # 根据参数决定查询类型
            if not args:
                # 无国家参数：显示全球排名（使用 category）
                result = await self.get_top_cheapest(category=category)
            else:
                # 有国家参数：查询指定国家
                result = await self.query_prices(args)

            # 发送结果
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
