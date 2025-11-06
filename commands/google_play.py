import asyncio
import logging
import re
from typing import Optional

from google_play_scraper import app as gp_app
from google_play_scraper import exceptions as gp_exceptions
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from commands.google_play_modules import SensorTowerAPI
from utils.command_factory import command_factory
from utils.config_manager import config_manager
from utils.country_data import SUPPORTED_COUNTRIES, get_country_flag
from utils.formatter import foldable_text_v2, foldable_text_with_markdown_v2
from utils.message_manager import (
    delete_user_command,
    send_error,
    send_help,
    send_search_result,
    send_success,
)
from utils.permissions import Permission
from utils.price_parser import extract_currency_and_price
from utils.rate_converter import RateConverter


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default search countries if none are specified by the user
DEFAULT_SEARCH_COUNTRIES = ["US", "NG", "TR"]

# Global cache_manager (will be set by main.py)
cache_manager = None


def set_cache_manager(manager):
    global cache_manager
    cache_manager = manager


# Global rate_converter (will be set by main.py)
rate_converter = None


def set_rate_converter(converter: RateConverter):
    global rate_converter
    rate_converter = converter


# Standard Emojis (no custom tg://emoji?id=...)
EMOJI_APP = "📱"
EMOJI_DEV = "👨‍💻"
EMOJI_RATING = "⭐️"
EMOJI_INSTALLS = "⬇️"
EMOJI_PRICE = "💰"
EMOJI_IAP = "🛒"
EMOJI_LINK = "🔗"
EMOJI_COUNTRY = "📍"
EMOJI_FLAG_PLACEHOLDER = "🏳️"  # Fallback if no custom emoji found


# 全局 Sensor Tower API 实例
sensor_tower_api = SensorTowerAPI()


# ========== 辅助函数 ==========


async def _convert_to_cny(amount: float, from_currency: str) -> Optional[float]:
    """
    将金额转换为人民币（CNY）

    Args:
        amount: 原始金额
        from_currency: 原始货币代码

    Returns:
        转换后的人民币金额，失败返回 None
    """
    if not rate_converter or not amount or not from_currency:
        return None

    if from_currency.upper() == "CNY":
        return amount

    try:
        cny_amount = await rate_converter.convert(amount, from_currency, "CNY")
        return cny_amount
    except Exception as e:
        logger.warning(f"货币转换失败 {amount} {from_currency} -> CNY: {e}")
        return None


async def _format_price_with_cny(price: float, currency: str) -> str:
    """
    格式化价格，添加 CNY 转换

    Args:
        price: 价格
        currency: 货币代码

    Returns:
        格式化后的价格字符串
        例如: "$9.99 USD (≈ ¥72.00 CNY)"
    """
    if price == 0:
        return "免费"

    price_str = f"{price} {currency}"

    # 尝试转换为 CNY
    cny_price = await _convert_to_cny(price, currency)
    if cny_price:
        price_str += f" (≈ ¥{cny_price:.2f} CNY)"

    return price_str


def _parse_iap_range(iap_range_str: str, country_code: str = None) -> Optional[tuple[float, float, str]]:
    """
    解析内购价格区间字符串,使用 utils/price_parser.py 进行智能解析

    Args:
        iap_range_str: 内购价格区间,如 "$0.99 - $99.99" 或 "₦2,530.00 - ₦26,500.00 per item"
        country_code: 国家代码,用于辅助货币识别

    Returns:
        (最小价格, 最大价格, 货币代码) 或 None
    """
    if not iap_range_str:
        return None

    # 正则匹配价格区间: 提取 "最小价格部分" 和 "最大价格部分"
    # 支持 - ~ 到 等分隔符,并忽略前后缀文本
    pattern = r"([\d\s.,\$€£¥₹₩₦₺₽₫฿₱₴₲₪₡₸₮៛]+?)\s*[-~到]\s*([\d\s.,\$€£¥₹₩₦₺₽₫฿₱₴₲₪₡₸₮៛]+)"

    match = re.search(pattern, iap_range_str)
    if not match:
        logger.warning(f"无法解析内购价格区间: {iap_range_str}")
        return None

    min_price_part = match.group(1).strip()
    max_price_part = match.group(2).strip()

    # 使用 price_parser 解析价格 (支持 Babel + 正则回退)
    try:
        currency1, min_price = extract_currency_and_price(min_price_part, country_code)
        currency2, max_price = extract_currency_and_price(max_price_part, country_code)

        # 验证价格有效性
        if min_price is None or max_price is None or min_price <= 0 or max_price <= 0:
            logger.warning(f"价格解析结果无效: min={min_price}, max={max_price}")
            return None

        # 优先使用第一个货币代码
        final_currency = currency1 if currency1 and currency1 != "USD" else currency2

        return (min_price, max_price, final_currency)

    except Exception as e:
        logger.warning(f"解析内购价格时出错 '{iap_range_str}': {e}")
        return None


async def _format_iap_range_with_cny(iap_range_str: str, country_code: str = None) -> str:
    """
    格式化内购价格区间，添加 CNY 转换

    Args:
        iap_range_str: 内购价格区间字符串
        country_code: 国家代码,用于辅助货币识别

    Returns:
        格式化后的字符串
        例如: "$0.99-$99.99 (≈ ¥7.12-¥719.28)"
    """
    parsed = _parse_iap_range(iap_range_str, country_code)
    if not parsed:
        # 无法解析，返回原始字符串
        return iap_range_str

    min_price, max_price, currency = parsed

    # 转换为 CNY
    min_cny = await _convert_to_cny(min_price, currency)
    max_cny = await _convert_to_cny(max_price, currency)

    if min_cny and max_cny:
        return f"{iap_range_str} (≈ ¥{min_cny:.2f}-¥{max_cny:.2f})"
    else:
        return iap_range_str


async def _handle_error(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    error_msg: str,
    temp_message=None,
):
    """
    统一的错误处理函数

    Args:
        context: Telegram context
        chat_id: 聊天ID
        message_id: 用户命令消息ID
        error_msg: 错误消息
        temp_message: 临时消息（需要删除）
    """
    if temp_message:
        try:
            await temp_message.delete()
        except Exception:
            pass

    await send_error(
        context, chat_id, foldable_text_v2(error_msg), parse_mode="MarkdownV2"
    )
    await delete_user_command(context, chat_id, message_id)


async def get_app_details_for_country(
    app_id: str, country: str, lang_code: str
) -> tuple[str, dict | None, str | None]:
    """Asynchronously fetches app details for a specific country/region with caching."""
    cache_key = f"gp_app_{app_id}_{country}_{lang_code}"

    # Check cache first (cache for 6 hours)
    cached_data = await cache_manager.load_cache(
        cache_key,
        max_age_seconds=config_manager.config.google_play_app_cache_duration,
        subdirectory="google_play",
    )
    if cached_data:
        return country, cached_data, None

    try:
        # google_play_scraper is not async, so run in executor
        app_details = await asyncio.to_thread(
            gp_app, app_id, lang=lang_code, country=country
        )

        # Save to cache
        await cache_manager.save_cache(
            cache_key, app_details, subdirectory="google_play"
        )

        return country, app_details, None
    except gp_exceptions.NotFoundError:
        return country, None, f"在该区域 ({country}) 未找到应用"
    except Exception as e:
        logger.warning(f"Failed to get app details for {country}: {e}")
        return country, None, f"查询 {country} 区出错: {type(e).__name__}"


async def _show_search_results(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_message_id: int,
    query: str,
    search_results: list[dict],
    countries: list[str],
    lang_code: str,
    temp_message,
):
    """
    显示搜索结果并提供选择按钮

    Args:
        context: Telegram context
        chat_id: 聊天ID
        user_message_id: 用户命令消息ID
        query: 搜索关键词
        search_results: 搜索结果列表
        countries: 要查询的国家列表
        lang_code: 语言代码
        temp_message: 临时消息
    """
    # 存储搜索结果到 Redis 缓存 (使用 GOOGLE_PLAY_SEARCH_CACHE_DURATION 配置)
    cache_key = f"gp_search:{chat_id}:{user_message_id}"
    search_data = {
        "results": search_results,
        "countries": countries,
        "lang_code": lang_code,
    }
    await cache_manager.save_cache(cache_key, search_data, subdirectory="google_play")
    logger.debug(f"搜索结果已缓存: {cache_key}, 结果数: {len(search_results)}")

    # 构建结果消息（原始文本，使用 format_with_markdown_v2 转义）
    result_lines = [f"🔍 搜索「{query}」找到 {len(search_results)} 个结果：\n"]

    # 构建按钮
    keyboard = []
    for idx, app in enumerate(search_results[:5]):  # 最多显示5个，索引从0开始
        title = app["title"]
        publisher = app.get("publisher", "")
        downloads = app.get("downloads", "")
        active_status = "" if app.get("active", True) else " [已下架]"

        # 标题行：序号 + 标题 + 下载量（同行）
        title_line = f"{idx + 1}. *{title}*"
        if downloads:
            title_line += f" | 下载: {downloads}"
        title_line += active_status
        result_lines.append(title_line)

        # 开发者行
        if publisher:
            result_lines.append(f"   开发者: {publisher}")

        # 按钮文本
        button_text = f"{idx + 1}. {title[:30]}"  # 限制长度

        # 新的压缩 Callback data: gp_索引|国家列表|消息ID (节省 67% 空间)
        callback_data = f"gp_{idx}|{','.join(countries)}|{user_message_id}"
        keyboard.append(
            [InlineKeyboardButton(button_text, callback_data=callback_data)]
        )

    # 添加取消按钮
    keyboard.append(
        [InlineKeyboardButton("❌ 取消", callback_data=f"gp_cancel|{user_message_id}")]
    )

    reply_markup = InlineKeyboardMarkup(keyboard)

    # 拼接消息文本并使用 format_with_markdown_v2 转义
    from utils.formatter import format_with_markdown_v2

    result_text = "\n".join(result_lines)
    formatted_text = format_with_markdown_v2(result_text)

    # 更新消息
    try:
        await temp_message.edit_text(
            formatted_text,
            parse_mode="MarkdownV2",
            reply_markup=reply_markup,
        )
    except Exception as e:
        logger.error(f"显示搜索结果失败: {e}")
        await _handle_error(
            context,
            chat_id,
            user_message_id,
            f"❌ 显示搜索结果失败: {type(e).__name__}",
            temp_message,
        )


async def _query_app_details(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_message_id: int,
    app_id: str,
    app_title: str,
    countries: list[str],
    lang_code: str,
    temp_message,
):
    """
    查询应用详情并显示

    Args:
        context: Telegram context
        chat_id: 聊天ID
        user_message_id: 用户命令消息ID
        app_id: 应用包名
        app_title: 应用名称
        countries: 要查询的国家列表
        lang_code: 语言代码
        temp_message: 临时消息
    """
    # 并发查询多个国家 (google_play_scraper - 获取评分、安装量等基本信息)
    tasks = [get_app_details_for_country(app_id, c, lang_code) for c in countries]
    results = await asyncio.gather(*tasks)

    # 并发查询 Sensor Tower API 获取内购价格信息
    async def get_st_iap_for_country(country_code: str):
        """获取 Sensor Tower 的内购价格区间"""
        try:
            st_details = await sensor_tower_api.get_app_details(app_id, country_code)
            if st_details:
                top_iap = st_details.get("top_in_app_purchases", {})
                return country_code, top_iap.get(country_code.upper())
            return country_code, None
        except Exception as e:
            logger.warning(f"获取 {country_code} 的 Sensor Tower 内购信息失败: {e}")
            return country_code, None

    st_iap_tasks = [get_st_iap_for_country(c) for c in countries]
    st_iap_results = await asyncio.gather(*st_iap_tasks)
    st_iap_dict = dict(st_iap_results)  # {country_code: iap_range_str}

    # 构建结果消息
    raw_message_parts = []
    preview_trigger_link = ""

    # 获取基本信息（从第一个有效结果）
    first_valid_details = next((details for _, details, _ in results if details), None)
    if first_valid_details:
        app_title = first_valid_details.get("title", app_title)
        developer = first_valid_details.get("developer", "N/A")
        icon_url = first_valid_details.get("icon", "")

        if icon_url:
            preview_trigger_link = f"[\u200b]({icon_url})"

        raw_message_parts.append(f"{EMOJI_APP} *应用名称: {app_title}*")
        raw_message_parts.append(f"{EMOJI_DEV} 开发者: {developer}")
    else:
        raw_message_parts.append(f"{EMOJI_APP} {app_title}")

    if preview_trigger_link:
        raw_message_parts.insert(0, preview_trigger_link)

    raw_message_parts.append("")

    # 处理每个国家的结果
    for i, (country_code, details, error_msg) in enumerate(results):
        country_info = SUPPORTED_COUNTRIES.get(country_code, {})
        flag = get_country_flag(country_code) or EMOJI_FLAG_PLACEHOLDER
        country_name = country_info.get("name", country_code)

        raw_message_parts.append(
            f"{EMOJI_COUNTRY} {flag} {country_name} ({country_code})"
        )

        if details:
            score = details.get("score")
            installs = details.get("installs", "N/A")
            app_url_country = details.get("url", "")

            # 评分
            score_str = f"{score:.1f}/5.0" if score is not None else "暂无评分"
            rating_stars = "☆☆☆☆☆"
            if score is not None:
                rounded_score = round(score)
                rating_stars = "⭐" * rounded_score + "☆" * (5 - rounded_score)

            # 价格（使用 CNY 转换）
            is_free = details.get("free", False)
            price = details.get("price", 0)
            currency = details.get("currency", "")

            if is_free or price == 0:
                price_str = "免费"
            elif price > 0 and currency:
                # 使用新的 CNY 转换函数
                price_str = await _format_price_with_cny(price, currency)
            else:
                price_str = "价格未知"

            # 内购（从 Sensor Tower API 获取,使用 CNY 转换）
            offers_iap = details.get("offersIAP", False)

            # 优先使用 Sensor Tower 的内购数据
            iap_range_raw = st_iap_dict.get(country_code)

            # 如果 Sensor Tower 没有数据,尝试从 google_play_scraper 获取
            if not iap_range_raw:
                iap_range_raw = details.get("IAPRange")

            iap_str = "无"

            if offers_iap and iap_range_raw:
                # 使用新的内购转换函数,传入国家代码辅助解析
                iap_str = await _format_iap_range_with_cny(iap_range_raw, country_code)
            elif offers_iap and not iap_range_raw:
                iap_str = "有 (范围未知)"

            raw_message_parts.append(
                f"  {EMOJI_RATING} 评分: {rating_stars} ({score_str})"
            )
            raw_message_parts.append(f"  {EMOJI_INSTALLS} 安装量: {installs}")
            raw_message_parts.append(f"  {EMOJI_PRICE} 价格: {price_str}")
            raw_message_parts.append(f"  {EMOJI_IAP} 内购: {iap_str}")

            if app_url_country:
                raw_message_parts.append(
                    f"  {EMOJI_LINK} [Google Play 链接]({app_url_country})"
                )

        else:
            raw_message_parts.append(f"  😕 {error_msg}")

        # 国家之间添加空行
        if i < len(results) - 1:
            raw_message_parts.append("")

    # 拼接最终消息
    raw_final_message = "\n".join(raw_message_parts).strip()

    # 发送结果
    try:
        await temp_message.delete()

        await send_search_result(
            context,
            chat_id,
            foldable_text_with_markdown_v2(raw_final_message),
            parse_mode="MarkdownV2",
            disable_web_page_preview=False,
        )

        await delete_user_command(context, chat_id, user_message_id)

    except Exception as e:
        logger.exception(f"发送结果时出错: {e}")
        await _handle_error(
            context,
            chat_id,
            user_message_id,
            f"❌ 发送结果时出错: {type(e).__name__}",
            temp_message,
        )


async def googleplay_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handles the /gp command to query Google Play app information."""
    if not update.message:
        return

    args_list = context.args

    if not args_list:
        help_message = """❓ 请输入应用名称或包名。

用法: /gp <应用名或包名> [国家代码] [语言代码]

示例:
/gp Youtube us en
/gp Tiktok (查 US, NG, TR)"""

        await send_help(
            context,
            update.message.chat_id,
            foldable_text_v2(help_message),
            parse_mode="MarkdownV2",
        )
        await delete_user_command(
            context, update.message.chat_id, update.message.message_id
        )
        return

    # Parse arguments
    query = args_list[0]
    user_country = None
    lang_code = "zh-cn".lower()

    if len(args_list) > 1:
        if len(args_list[1]) == 2 and args_list[1].isalpha():
            user_country = args_list[1].upper()
            if len(args_list) > 2:
                lang_code = args_list[2].lower()
        else:
            lang_code = args_list[1].lower()

    countries_to_search = []
    if user_country:
        countries_to_search.append(user_country)
        search_info = f"区域: {user_country}, 语: {lang_code}"
    else:
        countries_to_search = DEFAULT_SEARCH_COUNTRIES
        search_info = f"区域: {', '.join(countries_to_search)}, 语言: {lang_code}"

    # Initial search message - use plain text, will be replaced
    search_message = f"🔍 正在搜索 Google Play 应用: {query} ({search_info})..."
    message = await context.bot.send_message(
        chat_id=update.message.chat_id,
        text=foldable_text_v2(search_message),
        parse_mode="MarkdownV2",
    )

    # 使用 Sensor Tower API 搜索应用（返回多个结果）
    try:
        search_results = await sensor_tower_api.search_apps(query, top_n=5)

        if not search_results:
            error_msg = f"😕 未找到应用: {query}"
            await _handle_error(
                context,
                update.message.chat_id,
                update.message.message_id,
                error_msg,
                message,
            )
            return

        # 如果只有一个结果，直接查询详情
        if len(search_results) == 1:
            app_id = search_results[0]["appId"]
            app_title = search_results[0]["title"]
            await _query_app_details(
                context,
                update.message.chat_id,
                update.message.message_id,
                app_id,
                app_title,
                countries_to_search,
                lang_code,
                message,
            )
            return

        # 多个结果：显示选择按钮
        await _show_search_results(
            context,
            update.message.chat_id,
            update.message.message_id,
            query,
            search_results,
            countries_to_search,
            lang_code,
            message,
        )

    except Exception as e:
        logger.exception(f"搜索应用时出错: {e}")
        error_msg = f"❌ 搜索应用时出错: {type(e).__name__}"
        await _handle_error(
            context,
            update.message.chat_id,
            update.message.message_id,
            error_msg,
            message,
        )


async def googleplay_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """处理 Google Play 搜索结果的回调查询"""
    query = update.callback_query
    if not query:
        return

    await query.answer()

    # 解析回调数据
    callback_data = query.data
    if not callback_data or not callback_data.startswith("gp_"):
        return

    parts = callback_data.split("|")
    action = parts[0]

    # 取消操作
    if action == "gp_cancel":
        try:
            user_message_id = int(parts[1])
            await query.message.delete()
            await delete_user_command(context, query.message.chat_id, user_message_id)
        except Exception as e:
            logger.error(f"取消操作失败: {e}")
        return

    # 选择应用 (新格式: gp_0|US,NG,TR|2372806)
    if action.startswith("gp_") and len(action) > 3:  # gp_0, gp_1, etc.
        try:
            # 解析新格式
            idx_str = action[3:]  # 提取索引 "0", "1", etc.
            idx = int(idx_str)
            countries = parts[1].split(",")
            user_message_id = int(parts[2])

            # 从 Redis 缓存获取搜索结果
            cache_key = f"gp_search:{query.message.chat_id}:{user_message_id}"
            search_data = await cache_manager.load_cache(
                cache_key,
                max_age_seconds=config_manager.config.google_play_search_cache_duration,
                subdirectory="google_play",
            )

            if not search_data:
                error_msg = "❌ 搜索结果已过期，请重新搜索"
                await query.message.delete()
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=error_msg,
                )
                return

            # 提取数据
            search_results = search_data["results"]
            lang_code = search_data["lang_code"]

            # 验证索引
            if idx < 0 or idx >= len(search_results):
                logger.error(f"无效的索引: {idx}, 结果数: {len(search_results)}")
                return

            # 获取选中的应用
            selected_app = search_results[idx]
            app_id = selected_app["appId"]
            app_title = selected_app["title"]

            logger.info(f"用户选择应用: {app_title} ({app_id}), 索引: {idx}")

            # 查询应用详情
            await _query_app_details(
                context,
                query.message.chat_id,
                user_message_id,
                app_id,
                app_title,
                countries,
                lang_code,
                query.message,
            )

        except Exception as e:
            logger.exception(f"处理应用选择失败: {e}")
            error_msg = f"❌ 处理选择时出错: {type(e).__name__}"
            try:
                await query.message.delete()
                await send_error(
                    context,
                    query.message.chat_id,
                    foldable_text_v2(error_msg),
                    parse_mode="MarkdownV2",
                )
            except Exception:
                pass


async def google_play_clean_cache_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handles the /gp_cleancache command to clear Google Play related caches."""
    if not update.message:
        return

    try:
        # 从 context 获取缓存管理器
        cache_mgr = context.bot_data.get("cache_manager")
        if cache_mgr:
            await cache_mgr.clear_cache(subdirectory="google_play")
            success_message = "✅ Google Play 缓存已清理。"
        else:
            success_message = "⚠️ 缓存管理器未初始化。"
        await send_success(
            context,
            update.message.chat_id,
            foldable_text_v2(success_message),
            parse_mode="MarkdownV2",
        )
        await delete_user_command(
            context, update.message.chat_id, update.message.message_id
        )
    except Exception as e:
        logger.error(f"Error clearing Google Play cache: {e}")
        error_message = f"❌ 清理 Google Play 缓存时发生错误: {e!s}"
        await send_error(
            context,
            update.message.chat_id,
            foldable_text_v2(error_message),
            parse_mode="MarkdownV2",
        )
        await delete_user_command(
            context, update.message.chat_id, update.message.message_id
        )


# Alias for the command
gp_command = googleplay_command
gp_clean_cache_command = google_play_clean_cache_command
gp_callback_handler = googleplay_callback_handler

# Register commands
command_factory.register_command(
    "gp", gp_command, permission=Permission.USER, description="Google Play应用价格查询"
)
command_factory.register_command(
    "gp_cleancache",
    gp_clean_cache_command,
    permission=Permission.ADMIN,
    description="清理Google Play缓存",
)

# Register callback handler
command_factory.register_callback(
    "^gp_",
    gp_callback_handler,
    permission=Permission.USER,
    description="Google Play搜索回调处理",
)
