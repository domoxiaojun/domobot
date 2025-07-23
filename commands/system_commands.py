# type: ignore
from telegram import Update
from telegram.ext import ContextTypes

from utils.command_factory import command_factory
from utils.formatter import foldable_text_with_markdown_v2
from utils.message_manager import delete_user_command, send_search_result
from utils.permissions import Permission


async def get_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    获取用户、群组或回复目标的ID。
    """
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    # 添加 null 检查
    if not message or not chat or not user:
        return

    reply_text = ""

    # 检查是否有回复的消息
    if message.reply_to_message:
        replied_user = message.reply_to_message.from_user
        replied_chat = message.reply_to_message.chat

        if replied_user:
            reply_text += f"👤 *被回复用户ID*: `{replied_user.id}`\n"

            # 添加用户名信息 - 改进显示逻辑
            username = replied_user.username
            first_name = replied_user.first_name or ""
            last_name = replied_user.last_name or ""

            # 优先显示用户名，其次显示完整姓名
            if username:
                reply_text += f"📛 *被回复用户名*: @{username}\n"
            else:
                full_name = f"{first_name} {last_name}".strip()
                if full_name:
                    reply_text += f"📛 *被回复昵称*: {full_name}\n"

            # 显示是否为机器人
            if replied_user.is_bot:
                reply_text += "🤖 *用户类型*: 机器人\n"

        if replied_chat and replied_chat.id != chat.id:
            reply_text += f"➡️ *来源对话ID*: `{replied_chat.id}`\n"

        reply_text += "\n"  # 添加分隔

    # 显示当前对话和用户的ID
    reply_text += f"👤 *您的用户ID*: `{user.id}`\n"
    if chat.type != "private":
        reply_text += f"👨‍👩‍👧‍👦 *当前群组ID*: `{chat.id}`"

    await send_search_result(context, chat.id, foldable_text_with_markdown_v2(reply_text), parse_mode="MarkdownV2")
    await delete_user_command(context, chat.id, message.message_id)


# 注册命令
command_factory.register_command("id", get_id_command, permission=Permission.USER, description="获取用户或群组的ID")
