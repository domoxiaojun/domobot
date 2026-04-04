import logging

from telegram import Update
from telegram.ext import ContextTypes

from commands.google_play_modules import GooglePlayService
from utils.command_factory import command_factory
from utils.constants import (
    DEFAULT_LANGUAGE_CODE,
    GOOGLE_PLAY_DEFAULT_COUNTRIES,
)
from utils.formatter import foldable_text_v2
from utils.message_manager import delete_user_command, send_help
from utils.permissions import Permission

# Configure logging
logger = logging.getLogger(__name__)

# 使用 constants.py 中定义的默认搜索国家
DEFAULT_SEARCH_COUNTRIES = GOOGLE_PLAY_DEFAULT_COUNTRIES


async def googleplay_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handles the /gp command to query Google Play app information."""
    if not update.message:
        return

    # 从 context.bot_data 获取服务实例
    service: GooglePlayService = context.bot_data.get("google_play_service")
    if not service:
        await send_help(
            context,
            update.message.chat_id,
            foldable_text_v2("❌ 错误：Google Play 查询服务未初始化。"),
            parse_mode="MarkdownV2",
        )
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
    lang_code = DEFAULT_LANGUAGE_CODE.lower()

    if len(args_list) > 1:
        # 尝试使用统一国家映射工具解析（支持国家代码、中文名、英文名）
        from utils.country_mapper import get_country_code

        resolved_country = get_country_code(args_list[1])
        if resolved_country:
            user_country = resolved_country
            if len(args_list) > 2:
                lang_code = args_list[2].lower()
        else:
            # 如果不是国家参数，则视为语言代码
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
        search_results = await service.sensor_tower_api.search_apps(query, top_n=5)

        if not search_results:
            error_msg = f"😕 未找到应用: {query}"
            await service._handle_error(
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
            await service._query_app_details(
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
        await service._show_search_results(
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
        await service._handle_error(
            context,
            update.message.chat_id,
            update.message.message_id,
            f"❌ 搜索失败: {type(e).__name__}",
            message,
        )


async def googleplay_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handles callback queries from search result buttons."""
    query = update.callback_query
    if not query:
        return

    await query.answer()

    # 从 context.bot_data 获取服务实例
    service: GooglePlayService = context.bot_data.get("google_play_service")
    if not service:
        await query.edit_message_text("❌ 错误：Google Play 查询服务未初始化。")
        return

    callback_data = query.data
    if not callback_data or not callback_data.startswith("gp_"):
        return

    # Parse callback data: gp_索引|国家列表|消息ID
    parts = callback_data[3:].split("|")
    if len(parts) < 2:
        await query.edit_message_text("❌ 无效的回调数据")
        return

    # 处理取消按钮
    if parts[0] == "cancel":
        try:
            await query.message.delete()
            user_message_id = int(parts[1])
            await delete_user_command(context, query.message.chat_id, user_message_id)
        except Exception as e:
            logger.error(f"取消操作失败: {e}")
        return

    # 解析选择的应用索引
    try:
        app_index = int(parts[0])
        countries = parts[1].split(",")
        user_message_id = int(parts[2])
    except (ValueError, IndexError) as e:
        logger.error(f"解析回调数据失败: {e}")
        await query.edit_message_text("❌ 数据解析错误")
        return

    # 从缓存中获取搜索结果
    cache_key = f"google_play:search:{query.message.chat_id}:{user_message_id}"
    search_data = await service.cache_manager.load_cache(
        cache_key, subdirectory="google_play"
    )

    if not search_data:
        await query.edit_message_text(
            "❌ 搜索结果已过期，请重新搜索",
            reply_markup=None,
        )
        await delete_user_command(context, query.message.chat_id, user_message_id)
        return

    search_results = search_data.get("results", [])
    lang_code = search_data.get("lang_code", DEFAULT_LANGUAGE_CODE)

    if app_index >= len(search_results):
        await query.edit_message_text("❌ 应用索引无效")
        return

    selected_app = search_results[app_index]
    app_id = selected_app["appId"]
    app_title = selected_app["title"]

    # 查询应用详情
    await service._query_app_details(
        context,
        query.message.chat_id,
        user_message_id,
        app_id,
        app_title,
        countries,
        lang_code,
        query.message,
    )


async def google_play_clean_cache_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handles the /gp_cleancache command to clear Google Play caches."""
    if not update.message:
        return

    # 从 context.bot_data 获取服务实例
    service: GooglePlayService = context.bot_data.get("google_play_service")
    if not service:
        await send_help(
            context,
            update.message.chat_id,
            foldable_text_v2("❌ 错误：Google Play 查询服务未初始化。"),
            parse_mode="MarkdownV2",
        )
        return

    try:
        # 清理 Google Play 相关的 Redis 缓存
        from utils.message_manager import send_success

        redis_client = service.cache_manager.redis_client
        pattern = "*google_play*"
        deleted_count = 0

        async for key in redis_client.scan_iter(match=pattern):
            await redis_client.delete(key)
            deleted_count += 1

        success_message = f"✅ 已清理 {deleted_count} 个 Google Play 缓存键"
        await send_success(
            context,
            update.message.chat_id,
            foldable_text_v2(success_message),
            parse_mode="MarkdownV2",
        )
        await delete_user_command(
            context, update.message.chat_id, update.message.message_id
        )

        logger.info(f"管理员 {update.effective_user.id} 清理了 Google Play 缓存")

    except Exception as e:
        error_message = f"❌ 清理缓存失败: {type(e).__name__}"
        logger.error(f"清理 Google Play 缓存失败: {e}")
        from utils.message_manager import send_error

        await send_error(
            context,
            update.message.chat_id,
            foldable_text_v2(error_message),
            parse_mode="MarkdownV2",
        )


# Register commands
command_factory.register_command(
    "gp",
    googleplay_command,
    permission=Permission.USER,
    description="Google Play应用价格查询",
)
command_factory.register_command(
    "gp_cleancache",
    google_play_clean_cache_command,
    permission=Permission.ADMIN,
    description="清理Google Play缓存",
)


async def google_play_clear_item_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """清理指定 Google Play 应用（包名）的缓存（Redis+MySQL）。用法: /gp_clearitem <包名> [国家...] [语言]"""
    if not update.message:
        return

    service: GooglePlayService = context.bot_data.get("google_play_service")
    db_manager = context.bot_data.get("price_history_manager")

    # 管理员判定
    user_manager = context.bot_data.get("user_cache_manager")
    if not user_manager or not update.effective_user:
        return
    user_id = update.effective_user.id
    if not (
        await user_manager.is_super_admin(user_id) or await user_manager.is_admin(user_id)
    ):
        from utils.message_manager import send_error
        await send_error(context, update.message.chat_id, "❌ 你没有缓存管理权限。")
        return

    # 删除用户命令消息
    await delete_user_command(
        context, update.message.chat_id, update.message.message_id
    )

    if not service or not service.cache_manager:
        await send_help(
            context,
            update.message.chat_id,
            foldable_text_v2("❌ 错误：Google Play 查询服务未初始化。"),
            parse_mode="MarkdownV2",
        )
        return

    if not context.args:
        await send_help(
            context,
            update.message.chat_id,
            foldable_text_v2("❌ 用法: /gp_clearitem <包名> [国家...]"),
            parse_mode="MarkdownV2",
        )
        return

    package_name = context.args[0].strip()
    # 解析可选国家
    extra = context.args[1:] if len(context.args) > 1 else []
    from utils.country_mapper import get_country_code

    countries = []
    for p in extra:
        code = get_country_code(p)
        if code and code not in countries:
            countries.append(code)

    # 清理 Redis 缓存（所有语言）
    try:
        if countries:
            for c in countries:
                prefix = f"google_play:app:{package_name}:{c.upper()}:"
                await service.cache_manager.clear_cache(
                    key_prefix=prefix, subdirectory="google_play"
                )
        else:
            prefix = f"google_play:app:{package_name}:"
            await service.cache_manager.clear_cache(
                key_prefix=prefix, subdirectory="google_play"
            )
    except Exception as e:
        await send_help(
            context,
            update.message.chat_id,
            foldable_text_v2(f"❌ 清理 Redis 失败: {e!s}"),
            parse_mode="MarkdownV2",
        )
        return

    # 清理 MySQL 记录
    deleted_db = 0
    if db_manager:
        try:
            if countries:
                for c in countries:
                    deleted_db += await db_manager.delete_item(
                        service="google_play", item_id=package_name, country_code=c
                    )
            else:
                deleted_db += await db_manager.delete_item(
                    service="google_play", item_id=package_name
                )
        except Exception as e:
            await send_help(
                context,
                update.message.chat_id,
                foldable_text_v2(f"❌ 清理 MySQL 失败: {e!s}"),
                parse_mode="MarkdownV2",
            )
            return

    result_text = (
        f"✅ 已清理 Google Play 缓存\n"
        f"• 包名: {package_name}\n"
        f"• 范围: {', '.join([c.upper() for c in countries]) if countries else '所有国家'}\n"
        f"• MySQL 删除记录: {deleted_db}"
    )
    await send_help(
        context,
        update.message.chat_id,
        foldable_text_v2(result_text),
        parse_mode="MarkdownV2",
    )


command_factory.register_command(
    "gp_clearitem",
    google_play_clear_item_command,
    permission=Permission.ADMIN,
    description="清理Google Play指定包名缓存（Redis+MySQL）",
)
