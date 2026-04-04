# Description: Steam 模块的命令处理器
# 从原 steam.py 拆分

import logging

from telegram import Update
from telegram.ext import ContextTypes

from utils.command_factory import command_factory
from utils.formatter import foldable_text_v2, foldable_text_with_markdown_v2
from utils.message_manager import (
    delete_user_command,
    send_error,
    send_help,
    send_success,
)
from utils.permissions import Permission
from utils.session_manager import steam_search_sessions

from .models import Config, ErrorHandler
from .parser import get_country_code
from .search import search_game
from .ui import (
    create_steam_search_keyboard,
    format_steam_search_results,
)

logger = logging.getLogger(__name__)
config = Config()
error_handler = ErrorHandler()


async def steam_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /steam 命令进行游戏价格查询（带交互式搜索）"""
    if not update.message:
        return

    if not context.args:
        help_message = (
            "*🎮 Steam游戏价格查询*\n"
            "_Author:_ Domo\n\n"
            "*指令列表：*\n"
            "`/steam` [游戏名称/ID] [国家代码] - 查询游戏价格\n"
            "`/steamcc` - 清理缓存\n\n"
            "*功能说明：*\n"
            "• 支持跨区价格对比,可同时查询多个地区,用空格分隔\n"
            "• 自动转换为人民币显示价格参考\n"
            "• 智能解析价格格式，支持多种货币符号\n"
            "• 支持查询捆绑包价格和内容\n"
            "• 使用OpenExchangeRate免费API进行汇率转换\n"
            "• 价格数据缓存3天,汇率每小时更新\n"
            "• 游戏ID永久缓存,无需重复获取\n\n"
            "*使用示例：*\n"
            "• `/steam 双人成行` - 查询国区价格\n"
            "• `/steam CS2 US RU TR AR` - 查询多区价格\n\n"
            "*提示：* 默认使用中国区(CN)查询"
        )
        await send_help(
            context,
            update.message.chat_id,
            foldable_text_with_markdown_v2(help_message),
            parse_mode="MarkdownV2",
        )
        await delete_user_command(
            context, update.message.chat_id, update.message.message_id
        )
        return

    user_id = update.effective_user.id

    loading_message = "🔍 正在搜索游戏... ⏳"
    message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=foldable_text_v2(loading_message),
        parse_mode="MarkdownV2",
    )

    args = context.args
    # 解析参数：分离游戏名称和国家代码
    country_inputs = []
    game_name_parts = []

    for arg in reversed(args):
        country_code = get_country_code(arg)
        if country_code:
            country_inputs.insert(0, arg)
        else:
            game_name_parts = args[: len(args) - len(country_inputs)]
            break

    query = " ".join(game_name_parts)
    if not country_inputs:
        country_inputs = [config.DEFAULT_CC]

    try:
        # 搜索游戏 (不使用缓存，确保每次都显示完整搜索结果)
        search_results = await search_game(query, country_inputs[0], use_cache=False)

        if not search_results:
            error_message = f"🔍 没有找到关键词 '{query}' 的相关内容"
            await message.edit_text(
                foldable_text_v2(error_message), parse_mode="MarkdownV2"
            )
            return

        # 始终显示交互式搜索界面
        per_page = 5
        total_results = len(search_results)
        total_pages = (
            min(10, (total_results + per_page - 1) // per_page)
            if total_results > 0
            else 1
        )

        page_results = search_results[0:per_page]

        search_data_for_session = {
            "query": query,
            "country_inputs": country_inputs,
            "all_results": search_results,
            "current_page": 1,
            "total_pages": total_pages,
            "total_results": total_results,
            "per_page": per_page,
            "results": page_results,
        }

        # 存储用户搜索会话
        steam_search_sessions[user_id] = {
            "query": query,
            "search_data": search_data_for_session,
            "message_id": message.message_id,
            "country_inputs": country_inputs,
        }

        # 格式化并显示结果
        result_text = format_steam_search_results(search_data_for_session)
        keyboard = create_steam_search_keyboard(search_data_for_session)

        await message.edit_text(
            foldable_text_v2(result_text),
            reply_markup=keyboard,
            parse_mode="MarkdownV2",
            disable_web_page_preview=True,
        )

        # 计划自动删除消息
        await delete_user_command(
            context, update.effective_chat.id, update.message.message_id
        )

    except Exception as e:
        error_msg = error_handler.log_error(e, "搜索游戏")
        await message.delete()
        await send_error(
            context,
            update.effective_chat.id,
            foldable_text_v2(error_msg),
            parse_mode="MarkdownV2",
        )
        await delete_user_command(
            context, update.effective_chat.id, update.message.message_id
        )


async def steam_clean_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /steamcc 命令清理 Steam 缓存"""
    if not update.message:
        return

    try:
        cache_mgr = context.bot_data.get("cache_manager")
        if cache_mgr is not None:
            await cache_mgr.clear_cache(subdirectory="steam")
            success_message = "✅ Steam 缓存已清理。"
            await send_success(
                context,
                update.message.chat_id,
                foldable_text_v2(success_message),
                parse_mode="MarkdownV2",
            )
            await delete_user_command(
                context, update.message.chat_id, update.message.message_id
            )
        else:
            error_message = "❌ 缓存管理器未初始化。"
            await send_error(
                context,
                update.message.chat_id,
                foldable_text_v2(error_message),
                parse_mode="MarkdownV2",
            )
            await delete_user_command(
                context, update.message.chat_id, update.message.message_id
            )
    except Exception as e:
        logger.error(f"Error clearing Steam cache: {e}")
        error_msg = f"❌ 清理 Steam 缓存时发生错误: {e}"
        await send_error(
            context,
            update.message.chat_id,
            foldable_text_v2(error_msg),
            parse_mode="MarkdownV2",
        )
        await delete_user_command(
            context, update.message.chat_id, update.message.message_id
        )


async def steam_clear_item_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """清理指定 Steam 条目（游戏或捆绑包）的缓存（Redis+MySQL）。

    用法:
      /steam_clearitem <AppID|bundle_捆绑ID> [国家...]
      例如: /steam_clearitem 730 US CN
            /steam_clearitem bundle_216938 US
    """
    if not update.message:
        return

    # 权限校验
    user_manager = context.bot_data.get("user_cache_manager")
    if not user_manager or not update.effective_user:
        return
    user_id = update.effective_user.id
    if not (
        await user_manager.is_super_admin(user_id)
        or await user_manager.is_admin(user_id)
    ):
        await send_error(
            context,
            update.message.chat_id,
            foldable_text_v2("❌ 你没有缓存管理权限。"),
            parse_mode="MarkdownV2",
        )
        return

    # 删除用户命令消息
    await delete_user_command(
        context, update.message.chat_id, update.message.message_id
    )

    if not context.args:
        await send_error(
            context,
            update.message.chat_id,
            foldable_text_v2(
                "❌ 用法: /steam_clearitem <AppID|bundle_捆绑ID> [国家...]"
            ),
            parse_mode="MarkdownV2",
        )
        return

    target = context.args[0].strip().lower()
    is_bundle = False
    bundle_id = None
    app_id = None

    if target.startswith("bundle_"):
        is_bundle = True
        bundle_id = target.split("_", 1)[1]
        if not bundle_id.isdigit():
            await send_error(
                context,
                update.message.chat_id,
                foldable_text_v2("❌ 捆绑包ID格式不正确，应为 bundle_<数字>"),
                parse_mode="MarkdownV2",
            )
            return
    else:
        if not target.isdigit():
            await send_error(
                context,
                update.message.chat_id,
                foldable_text_v2("❌ AppID 格式不正确，应为数字，或使用 bundle_<ID>"),
                parse_mode="MarkdownV2",
            )
            return
        app_id = target

    # 解析可选国家
    from .parser import get_country_code

    countries = []
    for p in context.args[1:]:
        code = get_country_code(p)
        if code and code not in countries:
            countries.append(code)

    cache_mgr = context.bot_data.get("cache_manager")
    db_mgr = context.bot_data.get("price_history_manager")

    # 清理 Redis
    try:
        if cache_mgr:
            if is_bundle:
                if countries:
                    for c in countries:
                        prefix = f"steam:bundle:{bundle_id}:{c.upper()}"
                        await cache_mgr.clear_cache(
                            key_prefix=prefix, subdirectory="steam"
                        )
                else:
                    prefix = f"steam:bundle:{bundle_id}:"
                    await cache_mgr.clear_cache(key_prefix=prefix, subdirectory="steam")
            else:
                if countries:
                    for c in countries:
                        prefix = f"steam:game:{app_id}:{c.upper()}"
                        await cache_mgr.clear_cache(
                            key_prefix=prefix, subdirectory="steam"
                        )
                else:
                    prefix = f"steam:game:{app_id}:"
                    await cache_mgr.clear_cache(key_prefix=prefix, subdirectory="steam")
    except Exception as e:
        await send_error(
            context,
            update.message.chat_id,
            foldable_text_v2(f"❌ 清理 Redis 失败: {e!s}"),
            parse_mode="MarkdownV2",
        )
        return

    # 清理 MySQL
    deleted_db = 0
    try:
        if db_mgr:
            if is_bundle:
                item_id = f"bundle_{bundle_id}"
            else:
                item_id = app_id

            if countries:
                for c in countries:
                    deleted_db += await db_mgr.delete_item(
                        service="steam", item_id=item_id, country_code=c
                    )
            else:
                deleted_db += await db_mgr.delete_item(service="steam", item_id=item_id)
    except Exception as e:
        await send_error(
            context,
            update.message.chat_id,
            foldable_text_v2(f"❌ 清理 MySQL 失败: {e!s}"),
            parse_mode="MarkdownV2",
        )
        return

    scope_text = ", ".join([c.upper() for c in countries]) if countries else "所有国家"
    target_text = f"bundle_{bundle_id}" if is_bundle else app_id
    await send_success(
        context,
        update.message.chat_id,
        foldable_text_v2(
            f"✅ 已清理 Steam 缓存\n• 目标: {target_text}\n• 范围: {scope_text}\n• MySQL 删除记录: {deleted_db}"
        ),
        parse_mode="MarkdownV2",
    )


# 注册命令
command_factory.register_command(
    "steam", steam_command, permission=Permission.USER, description="Steam游戏价格查询"
)
command_factory.register_command(
    "steamcc",
    steam_clean_cache_command,
    permission=Permission.ADMIN,
    description="清理Steam缓存",
)
command_factory.register_command(
    "steam_clearitem",
    steam_clear_item_command,
    permission=Permission.ADMIN,
    description="清理Steam指定条目缓存（Redis+MySQL）",
)
