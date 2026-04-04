# Description: Telegram bot command for direct currency exchange rate lookup.
# This module provides a /rate command to convert amounts between currencies.

import logging

from telegram import Update
from telegram.ext import ContextTypes

from utils.command_factory import command_factory
from utils.formatter import foldable_text_v2, foldable_text_with_markdown_v2
from utils.message_manager import (
    delete_user_command,
    send_error,
    send_help,
    send_search_result,
    send_success,
)
from utils.permissions import Permission
from utils.price_parser import get_currency_symbol

# Configure logging - 避免重复配置日志
logger = logging.getLogger(__name__)


async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /rate command for currency conversion."""
    if not update.message:
        return

    # 从 context.bot_data 获取依赖
    rate_converter = context.bot_data.get("rate_converter")
    if not rate_converter:
        error_message = "汇率转换器未初始化。请联系机器人管理员。"
        await send_error(
            context,
            update.message.chat_id,
            foldable_text_v2(error_message),
            parse_mode="MarkdownV2",
        )
        return

    loading_message = "🔍 正在查询中... ⏳"
    message = await context.bot.send_message(
        chat_id=update.message.chat_id,
        text=foldable_text_v2(loading_message),
        parse_mode="MarkdownV2",
    )

    args = context.args
    from_currency = "USD"
    to_currency = "CNY"
    amount = 100.0
    expression = None

    if not args:
        # Display help message if no arguments
        help_message = (
            "*💱 货币汇率插件*\n\n"
            "*使用方法:* `/rate [from_currency] [to_currency] [amount]`\n"
            "`[amount]` 是可选的，默认为 100。\n"
            "`[to_currency]` 是可选的，默认为 CNY。\n\n"
            "*示例:*\n"
            "`/rate` (显示帮助)\n"
            "`/rate USD` (USD -> CNY, 100 USD)\n"
            "`/rate USD JPY` (USD -> JPY, 100 USD)\n"
            "`/rate USD CNY 50` (USD -> CNY, 50 USD)\n"
            "`/rate USD 1+1` (USD -> CNY, 计算 1+1)\n\n"
            "📣 数据约每小时更新\n"
            "🌐 数据来源: Open Exchange Rates"
        )

        await message.delete()
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

    # Parse arguments
    if len(args) == 1:
        from_currency = args[0].upper()
    elif len(args) == 2:
        from_currency = args[0].upper()
        # Check if second arg is a currency or an amount expression
        if len(args[1]) == 3 and args[1].isalpha():  # Likely a currency code
            to_currency = args[1].upper()
        else:
            # Assume it's an amount expression
            amount_str = args[1]
            try:
                amount = float(amount_str)
            except ValueError:
                # Try to evaluate as math expression
                try:
                    from utils.safe_math_evaluator import safe_eval_math

                    amount = safe_eval_math(amount_str)
                    expression = amount_str
                except ValueError:
                    error_message = f"❌ 无效的金额或表达式: {amount_str}"
                    await message.delete()
                    await send_error(
                        context,
                        update.message.chat_id,
                        foldable_text_v2(error_message),
                        parse_mode="MarkdownV2",
                    )
                    await delete_user_command(
                        context, update.message.chat_id, update.message.message_id
                    )
                    return
    elif len(args) == 3:
        from_currency = args[0].upper()
        to_currency = args[1].upper()
        amount_str = args[2]
        try:
            amount = float(amount_str)
        except ValueError:
            try:
                from utils.safe_math_evaluator import safe_eval_math

                amount = safe_eval_math(amount_str)
                expression = amount_str
            except ValueError:
                error_message = f"❌ 无效的金额或表达式: {amount_str}"
                await message.delete()
                await send_error(
                    context,
                    update.message.chat_id,
                    foldable_text_v2(error_message),
                    parse_mode="MarkdownV2",
                )
                await delete_user_command(
                    context, update.message.chat_id, update.message.message_id
                )
                return
    else:
        error_message = "❌ 参数过多。请检查使用方法。"
        await message.delete()
        await send_error(
            context,
            update.message.chat_id,
            foldable_text_v2(error_message),
            parse_mode="MarkdownV2",
        )
        await delete_user_command(
            context, update.message.chat_id, update.message.message_id
        )
        return

    # 快速检查数据可用性（无需等待网络）
    if not await rate_converter.is_data_available():
        # 数据太旧或不存在，尝试快速加载
        await rate_converter.get_rates()
        if not rate_converter.rates:
            error_message = "❌ 汇率数据暂时不可用。请稍后重试。"
            await message.delete()
            await send_error(
                context,
                update.message.chat_id,
                foldable_text_v2(error_message),
                parse_mode="MarkdownV2",
            )
            await delete_user_command(
                context, update.message.chat_id, update.message.message_id
            )
            return

    if from_currency not in rate_converter.rates:
        error_message = f"❌ 不支持的起始货币: {from_currency}"
        await message.delete()
        await send_error(
            context,
            update.message.chat_id,
            foldable_text_v2(error_message),
            parse_mode="MarkdownV2",
        )
        await delete_user_command(
            context, update.message.chat_id, update.message.message_id
        )
        return
    if to_currency not in rate_converter.rates:
        error_message = f"❌ 不支持的目标货币: {to_currency}"
        await message.delete()
        await send_error(
            context,
            update.message.chat_id,
            foldable_text_v2(error_message),
            parse_mode="MarkdownV2",
        )
        await delete_user_command(
            context, update.message.chat_id, update.message.message_id
        )
        return

    try:
        # 直接转换，无需额外的 get_rates() 调用
        converted_amount = await rate_converter.convert(
            amount, from_currency, to_currency
        )
        if converted_amount is None:
            error_message = "❌ 转换失败，请检查货币代码。"
            await message.delete()
            await send_error(
                context,
                update.message.chat_id,
                foldable_text_v2(error_message),
                parse_mode="MarkdownV2",
            )
            await delete_user_command(
                context, update.message.chat_id, update.message.message_id
            )
            return

        from_symbol = get_currency_symbol(from_currency)
        to_symbol = get_currency_symbol(to_currency)

        # 格式化数字，移除不必要的小数位
        formatted_amount = f"{amount:.8f}".rstrip("0").rstrip(".")
        formatted_converted = f"{converted_amount:.2f}".rstrip("0").rstrip(".")

        # 美化排版的组装原始文本
        result_lines = ["💰 *汇率转换结果*"]
        result_lines.append("━━━━━━━━━━━━━━━━")

        if expression:
            result_lines.extend(
                ["", "🧮 *计算公式*", f"   `{expression}` = `{formatted_amount}`"]
            )

        result_lines.extend(
            [
                "",
                "💱 *转换详情*",
                f"   {from_symbol} `{formatted_amount}` *{from_currency}* → {to_symbol} `{formatted_converted}` *{to_currency}*",
                "",
                "━━━━━━━━━━━━━━━━",
                "📣 数据约每小时更新",
                "🌐 来源: Open Exchange Rates",
            ]
        )

        result_text = "\n".join(result_lines)

        await message.delete()
        await send_search_result(
            context,
            update.message.chat_id,
            foldable_text_with_markdown_v2(result_text),
            parse_mode="MarkdownV2",
        )
        await delete_user_command(
            context, update.message.chat_id, update.message.message_id
        )

    except Exception as e:
        logger.error(f"Error during rate conversion: {e}")
        error_message = f"❌ 转换时发生错误: {e!s}"
        await message.delete()
        await send_error(
            context,
            update.message.chat_id,
            foldable_text_v2(error_message),
            parse_mode="MarkdownV2",
        )
        await delete_user_command(
            context, update.message.chat_id, update.message.message_id
        )


async def rate_clean_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /rate_cleancache command to clear rate converter cache."""
    if not update.message:
        return

    try:
        # 从 context.bot_data 获取依赖
        rate_converter = context.bot_data.get("rate_converter")
        if rate_converter:
            await rate_converter.cache_manager.clear_cache(key="exchange_rates")
            success_message = "✅ 汇率缓存已清理。"
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
            warning_message = "⚠️ 汇率转换器未初始化，无需清理缓存。"
            await send_error(
                context,
                update.message.chat_id,
                foldable_text_v2(warning_message),
                parse_mode="MarkdownV2",
            )
            await delete_user_command(
                context, update.message.chat_id, update.message.message_id
            )
    except Exception as e:
        logger.error(f"Error clearing rate cache: {e}")
        error_message = f"❌ 清理汇率缓存时发生错误: {e!s}"
        await send_error(
            context,
            update.message.chat_id,
            foldable_text_v2(error_message),
            parse_mode="MarkdownV2",
        )
        await delete_user_command(
            context, update.message.chat_id, update.message.message_id
        )


# Register commands
command_factory.register_command(
    "rate", rate_command, permission=Permission.USER, description="汇率查询和转换"
)
command_factory.register_command(
    "rate_cleancache",
    rate_clean_cache_command,
    permission=Permission.ADMIN,
    description="清理汇率缓存",
)
