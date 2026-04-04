import asyncio
import logging
import re

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from utils.command_factory import command_factory
from utils.config_manager import get_config
from utils.constants import (
    ERROR_MESSAGE_DELETE_DELAY,
    INFO_MESSAGE_DELETE_DELAY,
    USER_COMMAND_DELETE_DELAY,
    WARNING_MESSAGE_DELETE_DELAY,
)
from utils.formatter import foldable_text_with_markdown_v2
from utils.message_manager import (
    send_error,
    send_success,
    _schedule_deletion,
)
from utils.mysql_user_manager import MySQLUserManager
from utils.permissions import Permission, is_admin, is_super_admin
from utils.pyrofork import (
    save_pyrofork_credentials,
    get_pyrofork_client,
    get_pyrofork_login_status,
    start_phone_login,
    complete_phone_login,
    logout_pyrofork_user,
    stop_pyrofork_client,
    initialize_pyrofork_client,
)

# 已移除 tasks、scripts、logs 命令（旧系统遗留功能）


logger = logging.getLogger(__name__)

# 获取配置
config = get_config()


# 辅助函数
def get_user_manager(context: ContextTypes.DEFAULT_TYPE) -> MySQLUserManager | None:
    """获取MySQL用户管理器"""
    return context.bot_data.get("user_cache_manager")


# --- Direct Command Handlers ---
async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Adds a user to the whitelist. Prioritizes replied-to user."""
    user_id = update.effective_user.id
    message = update.message

    # 删除用户的命令消息
    if message:
        await _schedule_deletion(
            chat_id=update.effective_chat.id,
            message_id=message.message_id,
            delay=USER_COMMAND_DELETE_DELAY,
            context=context,
        )

    user_manager = get_user_manager(context)
    if not await is_admin(user_id, user_manager):
        await send_error(context, update.effective_chat.id, "❌ 你没有管理用户的权限。")
        return

    target_user_id = None
    if message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id
    elif context.args:
        try:
            target_user_id = int(context.args[0])
        except (IndexError, ValueError):
            sent_message = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ 无效的ID，请输入一个数字或回复一个用户的消息。",
            )
            await _schedule_deletion(
                chat_id=sent_message.chat_id,
                message_id=sent_message.message_id,
                delay=ERROR_MESSAGE_DELETE_DELAY,
                context=context,
            )
            return

    if not target_user_id:
        help_text = "📝 *使用方法:*\n• 回复一个用户的消息并输入 `/add`\n• 或者使用 `/add <user_id>`"
        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=foldable_text_with_markdown_v2(help_text),
            parse_mode="MarkdownV2",
        )
        await _schedule_deletion(
            chat_id=sent_message.chat_id,
            message_id=sent_message.message_id,
            delay=WARNING_MESSAGE_DELETE_DELAY,
            context=context,
        )
        return

    # 使用MySQL用户管理器
    user_manager = get_user_manager(context)
    if not user_manager:
        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id, text="❌ 用户管理器未初始化。"
        )
        await _schedule_deletion(
            chat_id=sent_message.chat_id,
            message_id=sent_message.message_id,
            delay=ERROR_MESSAGE_DELETE_DELAY,
            context=context,
        )
        return

    if await user_manager.add_to_whitelist(target_user_id, user_id):
        reply_text = f"✅ 用户 `{target_user_id}` 已成功添加到白名单。"
    else:
        reply_text = f"❌ 添加失败，用户 `{target_user_id}` 可能已在白名单中。"

    sent_message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=foldable_text_with_markdown_v2(reply_text),
        parse_mode="MarkdownV2",
    )
    await _schedule_deletion(
        chat_id=sent_message.chat_id,
        message_id=sent_message.message_id,
        delay=ERROR_MESSAGE_DELETE_DELAY,
        context=context,
    )
    return


async def addgroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Adds a group to the whitelist. Prioritizes current chat if it's a group."""
    user_id = update.effective_user.id
    message = update.message

    # 删除用户的命令消息
    if message:
        await _schedule_deletion(
            chat_id=update.effective_chat.id,
            message_id=message.message_id,
            delay=USER_COMMAND_DELETE_DELAY,
            context=context,
        )

    user_manager = get_user_manager(context)
    if not await is_admin(user_id, user_manager):
        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id, text="❌ 你没有管理群组的权限。"
        )
        await _schedule_deletion(
            chat_id=sent_message.chat_id,
            message_id=sent_message.message_id,
            delay=ERROR_MESSAGE_DELETE_DELAY,
            context=context,
        )
        return

    target_group_id = None
    group_title = "未知群组"

    if message.chat.type in ["group", "supergroup"]:
        target_group_id = message.chat.id
        group_title = message.chat.title
    elif context.args:
        try:
            target_group_id = int(context.args[0])
            chat_info = await context.bot.get_chat(target_group_id)
            group_title = chat_info.title
        except (IndexError, ValueError):
            sent_message = await context.bot.send_message(
                chat_id=update.effective_chat.id, text="❌ 无效的ID，请输入一个数字。"
            )
            await _schedule_deletion(
                chat_id=sent_message.chat_id,
                message_id=sent_message.message_id,
                delay=ERROR_MESSAGE_DELETE_DELAY,
                context=context,
            )
            return
        except Exception as e:
            logger.warning(
                f"Could not get chat title for {target_group_id}: {e}. Using default title."
            )
            group_title = f"群组 {target_group_id}"

    if not target_group_id:
        help_text = "📝 *使用方法:*\n• 在目标群组中发送 `/addgroup`\n• 或者使用 `/addgroup <group_id>`"
        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=foldable_text_with_markdown_v2(help_text),
            parse_mode="MarkdownV2",
        )
        await _schedule_deletion(
            chat_id=sent_message.chat_id,
            message_id=sent_message.message_id,
            delay=WARNING_MESSAGE_DELETE_DELAY,
            context=context,
        )
        return

    # 使用MySQL用户管理器
    user_manager = get_user_manager(context)
    if not user_manager:
        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id, text="❌ 用户管理器未初始化。"
        )
        await _schedule_deletion(
            chat_id=sent_message.chat_id,
            message_id=sent_message.message_id,
            delay=ERROR_MESSAGE_DELETE_DELAY,
            context=context,
        )
        return

    if await user_manager.add_group_to_whitelist(
        target_group_id, group_title or f"群组 {target_group_id}", user_id
    ):
        reply_text = f"✅ 群组 *{group_title or f'群组 {target_group_id}'}* (`{target_group_id}`) 已成功添加到白名单。"
    else:
        reply_text = f"❌ 添加失败，群组 `{target_group_id}` 可能已在白名单中。"

    sent_message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=foldable_text_with_markdown_v2(reply_text),
        parse_mode="MarkdownV2",
    )
    await _schedule_deletion(
        chat_id=sent_message.chat_id,
        message_id=sent_message.message_id,
        delay=ERROR_MESSAGE_DELETE_DELAY,
        context=context,
    )
    return


# Conversation states
(
    MAIN_PANEL,
    USER_PANEL,
    GROUP_PANEL,
    ADMIN_PANEL,
    AWAITING_USER_ID_TO_ADD,
    AWAITING_USER_ID_TO_REMOVE,
    AWAITING_GROUP_ID_TO_ADD,
    AWAITING_GROUP_ID_TO_REMOVE,
    AWAITING_ADMIN_ID_TO_ADD,
    AWAITING_ADMIN_ID_TO_REMOVE,
    PYROFORK_PANEL,
    AWAITING_API_ID,
    AWAITING_API_HASH,
    AWAITING_PHONE_NUMBER,
    AWAITING_PHONE_CODE,
    AWAITING_2FA_PASSWORD,
) = range(16)


class AdminPanelHandler:
    """管理员面板处理器"""

    async def _show_panel(
        self, query: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup
    ):
        """Helper to edit the message with new panel content."""
        try:
            await query.edit_message_text(
                foldable_text_with_markdown_v2(text),
                parse_mode="MarkdownV2",
                reply_markup=reply_markup,
            )
        except Exception as e:
            logger.error(f"Error updating admin panel: {e}")

    async def show_main_panel(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        # 权限检查
        if not update.effective_user or not update.effective_chat:
            return ConversationHandler.END

        user_id = update.effective_user.id

        # 检查用户是否有管理员权限
        user_manager = get_user_manager(context)
        if not await is_admin(user_id, user_manager):
            sent_message = await context.bot.send_message(
                chat_id=update.effective_chat.id, text="❌ 你没有管理员权限。"
            )
            await _schedule_deletion(
                chat_id=sent_message.chat_id,
                message_id=sent_message.message_id,
                delay=ERROR_MESSAGE_DELETE_DELAY,
                context=context,
            )
            return ConversationHandler.END

        keyboard = [
            [InlineKeyboardButton("👤 管理用户白名单", callback_data="manage_users")],
            [
                InlineKeyboardButton(
                    "👨‍👩‍👧‍👦 管理群组白名单", callback_data="manage_groups"
                )
            ],
            [
                InlineKeyboardButton(
                    "📱 Pyrofork 用户登录", callback_data="manage_pyrofork"
                )
            ],
        ]
        if is_super_admin(user_id):
            keyboard.insert(
                0,
                [InlineKeyboardButton("👥 管理管理员", callback_data="manage_admins")],
            )
        keyboard.append([InlineKeyboardButton("❌ 关闭", callback_data="close")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        admin_type = "超级管理员" if is_super_admin(user_id) else "管理员"
        text = f"🛠️ *{admin_type}控制面板*\n\n请选择一项操作:"

        if update.callback_query:
            await self._show_panel(update.callback_query, text, reply_markup)
        else:
            # 保存用户的初始命令消息ID，用于后续删除
            if update.message:
                context.user_data["initial_command_message_id"] = (
                    update.message.message_id
                )
                context.user_data["chat_id"] = update.effective_chat.id

            # 发送管理面板消息
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=foldable_text_with_markdown_v2(text),
                parse_mode="MarkdownV2",
                reply_markup=reply_markup,
            )

            # 删除用户的/admin命令消息
            if update.message:
                try:
                    await _schedule_deletion(
                        chat_id=update.effective_chat.id,
                        message_id=update.message.message_id,
                        delay=USER_COMMAND_DELETE_DELAY,
                        context=context,
                    )
                except Exception as e:
                    logger.warning(f"无法安排删除用户命令消息: {e}")

        return MAIN_PANEL

    async def show_user_panel(
        self,
        query: CallbackQuery,
        context: ContextTypes.DEFAULT_TYPE,
        status_message: str | None = None,
    ) -> int:
        user_manager = get_user_manager(context)
        if not user_manager:
            await self._show_panel(
                query, "❌ 用户管理器未初始化", InlineKeyboardMarkup([])
            )
            return ConversationHandler.END
        users = await user_manager.get_whitelisted_users()
        text = f"👤 *用户白名单* (共 {len(users)} 人)\n\n"
        if status_message:
            text = f"{status_message}\n\n" + text
        if users:
            user_lines = []
            for user in users:
                user_id = user["user_id"]
                username = user.get("username")
                first_name = user.get("first_name")
                last_name = user.get("last_name")

                # 构建显示名称
                display_name = ""
                if first_name or last_name:
                    display_name = f"{first_name or ''} {last_name or ''}".strip()

                if username and display_name:
                    user_lines.append(f"• `{user_id}` - {display_name} (@{username})")
                elif username:
                    user_lines.append(f"• `{user_id}` - @{username}")
                elif display_name:
                    user_lines.append(f"• `{user_id}` - {display_name}")
                else:
                    user_lines.append(f"• `{user_id}`")

            text += "\n".join(user_lines)
        else:
            text += "📭 暂无白名单用户"
        keyboard = [
            [
                InlineKeyboardButton("➕ 添加用户", callback_data="user_add"),
                InlineKeyboardButton("➖ 移除用户", callback_data="user_remove"),
            ],
            [
                InlineKeyboardButton("🔄 刷新", callback_data="refresh_users"),
                InlineKeyboardButton("🔙 返回", callback_data="back_to_main"),
            ],
        ]
        await self._show_panel(query, text, InlineKeyboardMarkup(keyboard))
        return USER_PANEL

    async def show_group_panel(
        self,
        query: CallbackQuery,
        context: ContextTypes.DEFAULT_TYPE,
        status_message: str | None = None,
    ) -> int:
        user_manager = get_user_manager(context)
        if not user_manager:
            await self._show_panel(
                query, "❌ 用户管理器未初始化", InlineKeyboardMarkup([])
            )
            return ConversationHandler.END
        groups = await user_manager.get_whitelisted_groups()
        text = f"👨‍👩‍👧‍👦 *群组白名单* (共 {len(groups)} 个)\n\n"
        if status_message:
            text = f"{status_message}\n\n" + text
        # 修正排序与展示
        if groups:
            group_lines = []
            for g in sorted(groups, key=lambda g: g["group_id"]):
                group_id = g["group_id"]
                group_name = g.get("group_name")

                if group_name == "📜 配置文件白名单":
                    try:
                        chat = await context.bot.get_chat(group_id)
                        group_name = f"{chat.title} (配置文件)"
                    except Exception:
                        # 无法获取（可能机器人不在群里），保持原样
                        pass

                if group_name:
                    group_lines.append(f"• `{group_id}` - {group_name}")
                else:
                    group_lines.append(f"• `{group_id}`")

            text += "\n".join(group_lines)
        else:
            text += "📭 暂无白名单群组"
        keyboard = [
            [
                InlineKeyboardButton("➕ 添加群组", callback_data="group_add"),
                InlineKeyboardButton("➖ 移除群组", callback_data="group_remove"),
            ],
            [
                InlineKeyboardButton("🔄 刷新", callback_data="refresh_groups"),
                InlineKeyboardButton("🔙 返回", callback_data="back_to_main"),
            ],
        ]
        await self._show_panel(query, text, InlineKeyboardMarkup(keyboard))
        return GROUP_PANEL

    async def show_admin_panel(
        self,
        query: CallbackQuery,
        context: ContextTypes.DEFAULT_TYPE,
        status_message: str | None = None,
    ) -> int:
        user_manager = get_user_manager(context)
        if not user_manager:
            await self._show_panel(
                query, "❌ 用户管理器未初始化", InlineKeyboardMarkup([])
            )
            return ConversationHandler.END
        admin_ids = await user_manager.get_all_admins()
        # 转换为兼容格式
        admins = [{"user_id": admin_id} for admin_id in admin_ids]
        text = f"👥 *管理员列表* (共 {len(admins)} 人)\n\n"
        if status_message:
            text = f"{status_message}\n\n" + text
        # 修正排序与展示
        text += (
            "\n".join(
                [
                    f"• `{a['user_id']}`"
                    for a in sorted(admins, key=lambda a: a["user_id"])
                ]
            )
            if admins
            else "📭 暂无管理员"
        )
        keyboard = [
            [
                InlineKeyboardButton("➕ 添加管理员", callback_data="admin_add"),
                InlineKeyboardButton("➖ 移除管理员", callback_data="admin_remove"),
            ],
            [
                InlineKeyboardButton("🔄 刷新", callback_data="refresh_admins"),
                InlineKeyboardButton("🔙 返回", callback_data="back_to_main"),
            ],
        ]
        await self._show_panel(query, text, InlineKeyboardMarkup(keyboard))
        return ADMIN_PANEL

    async def prompt_for_input(
        self,
        query: CallbackQuery,
        context: ContextTypes.DEFAULT_TYPE,
        prompt_text: str,
        next_state: int,
    ) -> int:
        context.user_data["admin_query"] = query
        cancel_keyboard = [
            [InlineKeyboardButton("❌ 取消", callback_data="cancel_input")]
        ]
        await self._show_panel(
            query,
            f"📝 {prompt_text}\n\n发送 /cancel 可取消。",
            InlineKeyboardMarkup(cancel_keyboard),
        )
        return next_state

    async def _handle_modification(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        action_func,
        success_msg,
        failure_msg,
        item_type,
    ):
        # 保存用户命令消息以便稍后删除
        user_message = update.message

        if user_message:
            await _schedule_deletion(
                chat_id=user_message.chat_id,
                message_id=user_message.message_id,
                delay=USER_COMMAND_DELETE_DELAY,
                context=context,
            )

        if not user_message or not user_message.text:
            return ConversationHandler.END

        ids_to_process = re.split(r"[\s\n,]+", user_message.text.strip())
        processed, failed = [], []

        for item_id_str in ids_to_process:
            if not item_id_str:
                continue
            try:
                item_id = int(item_id_str)
                if await action_func(item_id):
                    processed.append(item_id_str)
                else:
                    failed.append(item_id_str)
            except ValueError:
                failed.append(item_id_str)
            except Exception as e:
                logger.error(f"处理 {item_type} {item_id_str} 时出错: {e}")
                failed.append(item_id_str)

        status_text = ""
        if processed:
            status_text += f"✅ {success_msg} {len(processed)} 个{item_type}: `{', '.join(processed)}`\n"
        if failed:
            status_text += f"❌ {failure_msg} {len(failed)} 个{item_type} (无效或状态未变): `{', '.join(failed)}`"

        # 显示操作结果，然后自动关闭面板
        query = context.user_data.get("admin_query") if context.user_data else None
        if query and status_text.strip():
            # 编辑消息显示操作结果
            await query.edit_message_text(
                foldable_text_with_markdown_v2(
                    f"操作完成:\n\n{status_text.strip()}\n\n⏰ 面板将在3秒后自动关闭..."
                ),
                parse_mode="MarkdownV2",
            )

            # 3秒后自动删除面板
            await _schedule_deletion(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                delay=INFO_MESSAGE_DELETE_DELAY,
                context=context,
            )

            # 删除用户的初始命令消息（如果存在）
            initial_msg_id = context.user_data.get("initial_command_message_id")
            chat_id = context.user_data.get("chat_id")
            if initial_msg_id and chat_id:
                await _schedule_deletion(
                    chat_id=chat_id,
                    message_id=initial_msg_id,
                    delay=INFO_MESSAGE_DELETE_DELAY,  # 也延迟3秒
                    context=context,
                )

        return ConversationHandler.END

    async def handle_add_user(self, update, context):
        user_manager = get_user_manager(context)
        if not user_manager:
            return ConversationHandler.END

        async def add_func(user_id):
            return await user_manager.add_to_whitelist(
                user_id, update.effective_user.id
            )

        return await self._handle_modification(
            update, context, add_func, "成功添加", "添加失败", "用户"
        )

    async def handle_remove_user(self, update, context):
        user_manager = get_user_manager(context)
        if not user_manager:
            return ConversationHandler.END

        async def remove_func(user_id):
            return await user_manager.remove_from_whitelist(user_id)

        return await self._handle_modification(
            update, context, remove_func, "成功移除", "移除失败", "用户"
        )

    async def handle_add_group(self, update, context):
        user_manager = get_user_manager(context)
        if not user_manager:
            return ConversationHandler.END

        async def add_func(group_id):
            return await user_manager.add_group_to_whitelist(
                group_id, f"Group {group_id}", update.effective_user.id
            )

        return await self._handle_modification(
            update, context, add_func, "成功添加", "添加失败", "群组"
        )

    async def handle_remove_group(self, update, context):
        user_manager = get_user_manager(context)
        if not user_manager:
            return ConversationHandler.END

        async def remove_func(group_id):
            return await user_manager.remove_group_from_whitelist(group_id)

        return await self._handle_modification(
            update, context, remove_func, "成功移除", "移除失败", "群组"
        )

    async def handle_add_admin(self, update, context):
        user_manager = get_user_manager(context)
        if not user_manager:
            return ConversationHandler.END

        async def add_func(admin_id):
            return await user_manager.add_admin(admin_id, update.effective_user.id)

        return await self._handle_modification(
            update, context, add_func, "成功添加", "添加失败", "管理员"
        )

    async def handle_remove_admin(self, update, context):
        user_manager = get_user_manager(context)
        if not user_manager:
            return ConversationHandler.END

        async def remove_func(admin_id):
            return await user_manager.remove_admin(admin_id)

        return await self._handle_modification(
            update, context, remove_func, "成功移除", "移除失败", "管理员"
        )

    # ============ Pyrofork 管理面板 ============

    async def _display_pyrofork_panel(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """内部方法：显示 Pyrofork 面板（支持 callback 和 message 两种场景）"""
        # 获取 Redis 客户端
        redis_client = (
            context.bot_data.get("cache_manager").redis_client
            if context.bot_data.get("cache_manager")
            else None
        )
        if not redis_client:
            if update.callback_query:
                await update.callback_query.answer(
                    "❌ Redis 客户端未初始化", show_alert=True
                )
            return MAIN_PANEL

        # 获取登录状态
        bot_id = context.bot_data.get("bot_id", 0)
        pyrofork_client = get_pyrofork_client()
        status = await get_pyrofork_login_status(
            redis_client, pyrofork_client=pyrofork_client, bot_id=bot_id
        )

        # 构建状态文本
        text = "📱 *Pyrofork 用户登录管理*\n\n"
        text += "━━━━━━ 当前状态 ━━━━━━\n"
        text += (
            f"API 配置: {'✅ 已配置' if status['api_configured'] else '❌ 未配置'}\n"
        )
        text += f"登录状态: {'✅ 已登录' if status['is_logged_in'] else '❌ 未登录'}\n"

        if status["phone_number"]:
            phone = status["phone_number"]
            masked_phone = f"{phone[:3]}****{phone[-4:]}" if len(phone) > 7 else phone
            text += f"手机号: {masked_phone}\n"

        if status["login_time"]:
            text += f"登录时间: {status['login_time'].strftime('%Y-%m-%d %H:%M')}\n"

        text += "\n━━━━━━ 操作菜单 ━━━━━━"

        # 构建键盘
        keyboard = []
        if not status["api_configured"]:
            # API 未配置: 只显示配置按钮
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "⚙️ 配置 API", callback_data="pyrofork_config_api"
                    )
                ]
            )
        else:
            # API 已配置: 显示登录/登出按钮
            if not status["is_logged_in"]:
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            "📞 手机号登录", callback_data="pyrofork_phone_login"
                        )
                    ]
                )
            else:
                keyboard.append(
                    [InlineKeyboardButton("🚪 登出", callback_data="pyrofork_logout")]
                )

            # 新增: 清除 API 配置按钮
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "🗑️ 清除 API 配置", callback_data="pyrofork_clear_api"
                    )
                ]
            )

        # 返回按钮
        keyboard.append(
            [InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]
        )

        reply_markup = InlineKeyboardMarkup(keyboard)

        # 根据是否有 callback_query 来决定是编辑还是发送新消息
        if update.callback_query:
            await self._show_panel(update.callback_query, text, reply_markup)
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=foldable_text_with_markdown_v2(text),
                parse_mode="MarkdownV2",
                reply_markup=reply_markup,
            )

        return PYROFORK_PANEL

    async def show_pyrofork_panel(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """显示 Pyrofork 登录状态和管理面板（从 callback 调用）"""
        query = update.callback_query
        if not query:
            return MAIN_PANEL

        await query.answer()
        return await self._display_pyrofork_panel(update, context)

    async def start_api_config(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """开始配置 API ID"""
        query = update.callback_query
        await query.answer()

        text = (
            "⚙️ *配置 Telegram API*\n\n"
            "步骤 1/2: 请输入 API ID\n\n"
            "📝 如何获取:\n"
            "1. 访问 https://my.telegram.org/apps\n"
            "2. 使用你的手机号登录\n"
            "3. 创建应用并获取 API ID\n\n"
            "⚠️ 请直接输入纯数字，例如: `12345678`\n\n"
            "💡 输入 /cancel 取消操作"
        )

        await query.edit_message_text(
            foldable_text_with_markdown_v2(text), parse_mode="MarkdownV2"
        )

        return AWAITING_API_ID

    async def handle_api_id(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """处理 API ID 输入"""
        user_message = update.message

        # 删除用户消息
        await _schedule_deletion(
            chat_id=user_message.chat_id,
            message_id=user_message.message_id,
            delay=USER_COMMAND_DELETE_DELAY,
            context=context,
        )

        try:
            api_id = int(user_message.text.strip())
            # 临时保存到 context
            context.user_data["temp_api_id"] = api_id

            text = (
                "⚙️ *配置 Telegram API*\n\n"
                f"✅ API ID 已记录: `{api_id}`\n\n"
                "步骤 2/2: 请输入 API Hash\n\n"
                "API Hash 是一个 32 位的十六进制字符串\n"
                "例如: `a1b2c3d4e5f67890abcdef1234567890`\n\n"
                "💡 输入 /cancel 取消操作"
            )

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=foldable_text_with_markdown_v2(text),
                parse_mode="MarkdownV2",
            )

            return AWAITING_API_HASH

        except ValueError:
            await send_error(
                context, update.effective_chat.id, "❌ API ID 必须是纯数字，请重新输入"
            )
            return AWAITING_API_ID

    async def handle_api_hash(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """处理 API Hash 输入"""
        user_message = update.message

        # 删除用户消息（包含敏感信息）
        await _schedule_deletion(
            chat_id=user_message.chat_id,
            message_id=user_message.message_id,
            delay=USER_COMMAND_DELETE_DELAY,
            context=context,
        )

        api_hash = user_message.text.strip()

        # 简单验证（32位十六进制）
        if len(api_hash) != 32 or not all(
            c in "0123456789abcdefABCDEF" for c in api_hash
        ):
            await send_error(
                context,
                update.effective_chat.id,
                "❌ API Hash 格式不正确，请输入 32 位十六进制字符串",
            )
            return AWAITING_API_HASH

        # 获取之前保存的 API ID
        api_id = context.user_data.get("temp_api_id")
        if not api_id:
            await send_error(
                context, update.effective_chat.id, "❌ 会话超时，请重新开始配置"
            )
            return await self.show_main_panel(update, context)

        # 保存到 Redis
        redis_client = context.bot_data.get("cache_manager").redis_client
        bot_id = context.bot_data.get("bot_id", 0)
        success = await save_pyrofork_credentials(
            redis_client, api_id, api_hash, bot_id=bot_id
        )

        # 清除临时数据
        context.user_data.pop("temp_api_id", None)

        if success:
            # 配置变更后重新初始化 Pyrofork 客户端
            try:
                logger.info("API 配置已更新,正在重新初始化 Pyrofork 客户端...")
                await stop_pyrofork_client()
                await initialize_pyrofork_client(
                    bot_token=config.bot_token,
                    redis_client=redis_client,
                    api_id=config.telegram_api_id or None,
                    api_hash=config.telegram_api_hash or None,
                    bot_id=bot_id,
                )
                logger.info("✅ Pyrofork 客户端已重新初始化")
            except Exception as e:
                logger.error(f"重新初始化 Pyrofork 客户端失败: {e}")

        if success:
            await send_success(
                context,
                update.effective_chat.id,
                "✅ API 配置成功！现在可以使用手机号登录了",
            )
            # 直接调用内部方法显示 Pyrofork 面板
            return await self._display_pyrofork_panel(update, context)
        else:
            await send_error(context, update.effective_chat.id, "❌ 保存 API 配置失败")
            return await self.show_main_panel(update, context)

    async def start_phone_login(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """开始手机号登录流程"""
        query = update.callback_query
        await query.answer()

        text = (
            "📞 *手机号登录*\n\n"
            "请输入你的手机号（国际格式）\n\n"
            "格式示例:\n"
            "- 中国: `+8613812341234`\n"
            "- 美国: `+11234567890`\n"
            "- 其他国家: `+国家代码手机号`\n\n"
            "⚠️ 必须包含国家代码（前面加 +）\n\n"
            "💡 输入 /cancel 取消操作"
        )

        await query.edit_message_text(
            foldable_text_with_markdown_v2(text), parse_mode="MarkdownV2"
        )

        return AWAITING_PHONE_NUMBER

    async def handle_phone_number(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """处理手机号输入"""
        user_message = update.message

        # 删除用户消息
        await _schedule_deletion(
            chat_id=user_message.chat_id,
            message_id=user_message.message_id,
            delay=USER_COMMAND_DELETE_DELAY,
            context=context,
        )

        phone_number = user_message.text.strip()

        # 简单验证手机号格式
        if not phone_number.startswith("+") or len(phone_number) < 10:
            await send_error(
                context,
                update.effective_chat.id,
                "❌ 手机号格式不正确，必须使用国际格式（如 +8613812341234）",
            )
            return AWAITING_PHONE_NUMBER

        # 保存手机号到 context
        context.user_data["phone_number"] = phone_number

        # 发送验证码
        redis_client = context.bot_data.get("cache_manager").redis_client
        bot_id = context.bot_data.get("bot_id", 0)
        result = await start_phone_login(
            phone_number, update.effective_user.id, redis_client, bot_id=bot_id
        )

        if result["success"]:
            text = (
                "📞 *验证码已发送*\n\n"
                f"{result['message']}\n\n"
                "请输入收到的验证码\n\n"
                "⚠️ 验证码有效期 5 分钟\n\n"
                "💡 输入 /cancel 取消操作"
            )

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=foldable_text_with_markdown_v2(text),
                parse_mode="MarkdownV2",
            )

            return AWAITING_PHONE_CODE
        else:
            await send_error(
                context, update.effective_chat.id, f"❌ {result['message']}"
            )
            return AWAITING_PHONE_NUMBER

    async def handle_phone_code(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """处理验证码输入"""
        user_message = update.message

        # 删除用户消息（包含验证码）
        await _schedule_deletion(
            chat_id=user_message.chat_id,
            message_id=user_message.message_id,
            delay=USER_COMMAND_DELETE_DELAY,
            context=context,
        )

        phone_code = user_message.text.strip()
        phone_number = context.user_data.get("phone_number")

        if not phone_number:
            await send_error(
                context, update.effective_chat.id, "❌ 会话超时，请重新开始登录"
            )
            return await self.show_main_panel(update, context)

        # 保存 phone_code 以便 2FA 时使用
        context.user_data["phone_code"] = phone_code

        # 完成登录
        redis_client = context.bot_data.get("cache_manager").redis_client
        bot_id = context.bot_data.get("bot_id", 0)
        result = await complete_phone_login(
            phone_number,
            phone_code,
            update.effective_user.id,
            redis_client,
            bot_id=bot_id,
        )

        if result["success"]:
            # 清除临时数据
            context.user_data.pop("phone_number", None)
            context.user_data.pop("phone_code", None)

            await send_success(context, update.effective_chat.id, "✅ 登录成功！")

            # 直接调用内部方法显示 Pyrofork 面板
            return await self._display_pyrofork_panel(update, context)

        elif result.get("requires_password"):
            # 需要双重验证密码
            text = (
                "🔐 *双重验证*\n\n"
                f"{result['message']}\n\n"
                "请输入你的双重验证密码\n\n"
                "💡 输入 /cancel 取消操作"
            )

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=foldable_text_with_markdown_v2(text),
                parse_mode="MarkdownV2",
            )

            return AWAITING_2FA_PASSWORD
        else:
            await send_error(
                context, update.effective_chat.id, f"❌ {result['message']}"
            )
            return AWAITING_PHONE_CODE

    async def handle_2fa_password(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """处理双重验证密码输入"""
        user_message = update.message

        # 删除用户消息（包含密码）
        await _schedule_deletion(
            chat_id=user_message.chat_id,
            message_id=user_message.message_id,
            delay=USER_COMMAND_DELETE_DELAY,
            context=context,
        )

        # 获取密码和手机号
        password = user_message.text.strip()
        phone_number = context.user_data.get("phone_number")
        phone_code = context.user_data.get("phone_code")

        if not phone_number or not phone_code:
            await send_error(
                context, update.effective_chat.id, "❌ 会话超时，请重新开始登录"
            )
            return await self.show_main_panel(update, context)

        # 使用密码完成登录
        redis_client = context.bot_data.get("cache_manager").redis_client
        bot_id = context.bot_data.get("bot_id", 0)
        result = await complete_phone_login(
            phone_number,
            phone_code,
            update.effective_user.id,
            redis_client,
            password=password,
            bot_id=bot_id,
        )

        if result["success"]:
            # 清除临时数据
            context.user_data.pop("phone_number", None)
            context.user_data.pop("phone_code", None)

            await send_success(context, update.effective_chat.id, "✅ 登录成功！")
            # 显示 Pyrogram 面板
            return await self._display_pyrofork_panel(update, context)
        else:
            # 密码错误，允许重试
            await send_error(
                context, update.effective_chat.id, f"❌ {result['message']}"
            )
            return AWAITING_2FA_PASSWORD

    async def handle_pyrofork_logout(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """处理 Pyrofork 登出"""
        query = update.callback_query

        redis_client = context.bot_data.get("cache_manager").redis_client
        bot_id = context.bot_data.get("bot_id", 0)
        success = await logout_pyrofork_user(redis_client, bot_id=bot_id)

        # 只调用一次 answer,带上结果消息
        if success:
            await query.answer("✅ 已登出", show_alert=True)
        else:
            await query.answer("❌ 登出失败", show_alert=True)

        return await self.show_pyrofork_panel(update, context)

    async def handle_clear_api_config(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """处理清除 API 配置的回调"""
        query = update.callback_query
        await query.answer()

        redis_client = context.bot_data.get("cache_manager").redis_client
        if not redis_client:
            await query.answer("❌ Redis 客户端未初始化", show_alert=True)
            return PYROFORK_PANEL

        # 导入删除函数
        from utils.pyrofork import (
            delete_pyrofork_credentials,
            logout_pyrofork_user,
            get_pyrofork_login_status,
        )

        bot_id = context.bot_data.get("bot_id", 0)

        # 检查登录状态
        status = await get_pyrofork_login_status(redis_client, bot_id=bot_id)

        # 如果已登录,先登出
        if status["is_logged_in"]:
            await logout_pyrofork_user(redis_client, bot_id=bot_id)

        # 删除 API 凭证
        success = await delete_pyrofork_credentials(redis_client, bot_id=bot_id)

        if success:
            await query.message.edit_text(
                "✅ API 配置已清除\n\n正在刷新面板...", parse_mode="Markdown"
            )
        else:
            await query.message.edit_text(
                "❌ 清除 API 配置失败\n\n请稍后重试", parse_mode="Markdown"
            )

        # 延迟后刷新面板
        await asyncio.sleep(1)
        return await self._display_pyrofork_panel(update, context)

    async def close_panel(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        query = update.callback_query
        if query:
            await query.message.delete()

        # 删除用户的初始命令消息（如果存在）
        try:
            if context.user_data:
                initial_msg_id = context.user_data.get("initial_command_message_id")
                chat_id = context.user_data.get("chat_id")
                if initial_msg_id and chat_id:
                    await context.bot.delete_message(
                        chat_id=chat_id, message_id=initial_msg_id
                    )
        except Exception as e:
            logger.warning(f"无法删除初始命令消息: {e}")

        return ConversationHandler.END

    async def cancel_and_back(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Goes back to the correct panel when /cancel is used."""
        if update.message:
            await _schedule_deletion(
                chat_id=update.message.chat_id,
                message_id=update.message.message_id,
                delay=USER_COMMAND_DELETE_DELAY,
                context=context,
            )

        if not context.user_data:
            return ConversationHandler.END

        query = context.user_data.get("admin_query")
        if not query:
            return ConversationHandler.END

        current_panel = context.user_data.get("current_panel")
        if current_panel == "user" and query:
            return await self.show_user_panel(query, context)
        if current_panel == "group" and query:
            return await self.show_group_panel(query, context)
        if current_panel == "admin" and query:
            return await self.show_admin_panel(query, context)

        # Fallback to main panel if something is weird
        return await self.show_main_panel(update, context)

    async def cancel_input(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """处理按钮取消操作"""
        query = update.callback_query
        if not query:
            return ConversationHandler.END

        # 获取当前面板类型并返回对应面板
        current_panel = (
            context.user_data.get("current_panel") if context.user_data else None
        )

        if current_panel == "user":
            return await self.show_user_panel(query, context)
        elif current_panel == "group":
            return await self.show_group_panel(query, context)
        elif current_panel == "admin":
            return await self.show_admin_panel(query, context)
        else:
            # 默认返回主面板
            return await self.show_main_panel(update, context)

    # --- 刷新功能处理 ---
    async def _refresh_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """刷新用户白名单面板"""
        return await self.show_user_panel(update.callback_query, context)

    async def _refresh_groups(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """刷新群组白名单面板"""
        return await self.show_group_panel(update.callback_query, context)

    async def _refresh_admins(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """刷新管理员面板"""
        return await self.show_admin_panel(update.callback_query, context)

    # --- Callback Handlers for Conversation ---
    async def _to_user_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data["current_panel"] = "user"
        return await self.show_user_panel(update.callback_query, context)

    async def _to_group_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data["current_panel"] = "group"
        return await self.show_group_panel(update.callback_query, context)

    async def _to_admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data["current_panel"] = "admin"
        return await self.show_admin_panel(update.callback_query, context)

    async def _prompt_user_add(self, update, context):
        return await self.prompt_for_input(
            update.callback_query,
            context,
            "请输入要添加的用户ID",
            AWAITING_USER_ID_TO_ADD,
        )

    async def _prompt_user_remove(self, update, context):
        return await self.prompt_for_input(
            update.callback_query,
            context,
            "请输入要移除的用户ID",
            AWAITING_USER_ID_TO_REMOVE,
        )

    async def _prompt_group_add(self, update, context):
        return await self.prompt_for_input(
            update.callback_query,
            context,
            "请输入要添加的群组ID",
            AWAITING_GROUP_ID_TO_ADD,
        )

    async def _prompt_group_remove(self, update, context):
        return await self.prompt_for_input(
            update.callback_query,
            context,
            "请输入要移除的群组ID",
            AWAITING_GROUP_ID_TO_REMOVE,
        )

    async def _prompt_admin_add(self, update, context):
        return await self.prompt_for_input(
            update.callback_query,
            context,
            "请输入要添加的管理员ID",
            AWAITING_ADMIN_ID_TO_ADD,
        )

    async def _prompt_admin_remove(self, update, context):
        return await self.prompt_for_input(
            update.callback_query,
            context,
            "请输入要移除的管理员ID",
            AWAITING_ADMIN_ID_TO_REMOVE,
        )

    def get_conversation_handler(self) -> ConversationHandler:
        return ConversationHandler(
            entry_points=[CommandHandler("admin", self.show_main_panel)],
            states={
                MAIN_PANEL: [
                    CallbackQueryHandler(self._to_user_panel, pattern="^manage_users$"),
                    CallbackQueryHandler(
                        self._to_group_panel, pattern="^manage_groups$"
                    ),
                    CallbackQueryHandler(
                        self._to_admin_panel, pattern="^manage_admins$"
                    ),
                    CallbackQueryHandler(
                        self.show_pyrofork_panel, pattern="^manage_pyrofork$"
                    ),
                    CallbackQueryHandler(self.close_panel, pattern="^close$"),
                ],
                USER_PANEL: [
                    CallbackQueryHandler(self._prompt_user_add, pattern="^user_add$"),
                    CallbackQueryHandler(
                        self._prompt_user_remove, pattern="^user_remove$"
                    ),
                    CallbackQueryHandler(
                        self._refresh_users, pattern="^refresh_users$"
                    ),
                    CallbackQueryHandler(
                        self.show_main_panel, pattern="^back_to_main$"
                    ),
                ],
                GROUP_PANEL: [
                    CallbackQueryHandler(self._prompt_group_add, pattern="^group_add$"),
                    CallbackQueryHandler(
                        self._prompt_group_remove, pattern="^group_remove$"
                    ),
                    CallbackQueryHandler(
                        self._refresh_groups, pattern="^refresh_groups$"
                    ),
                    CallbackQueryHandler(
                        self.show_main_panel, pattern="^back_to_main$"
                    ),
                ],
                ADMIN_PANEL: [
                    CallbackQueryHandler(self._prompt_admin_add, pattern="^admin_add$"),
                    CallbackQueryHandler(
                        self._prompt_admin_remove, pattern="^admin_remove$"
                    ),
                    CallbackQueryHandler(
                        self._refresh_admins, pattern="^refresh_admins$"
                    ),
                    CallbackQueryHandler(
                        self.show_main_panel, pattern="^back_to_main$"
                    ),
                ],
                PYROFORK_PANEL: [
                    CallbackQueryHandler(
                        self.start_api_config, pattern="^pyrofork_config_api$"
                    ),
                    CallbackQueryHandler(
                        self.start_phone_login, pattern="^pyrofork_phone_login$"
                    ),
                    CallbackQueryHandler(
                        self.handle_pyrofork_logout, pattern="^pyrofork_logout$"
                    ),
                    # 新增: 清除 API 配置回调
                    CallbackQueryHandler(
                        self.handle_clear_api_config, pattern="^pyrofork_clear_api$"
                    ),
                    CallbackQueryHandler(
                        self.show_main_panel, pattern="^back_to_main$"
                    ),
                ],
                AWAITING_USER_ID_TO_ADD: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND, self.handle_add_user
                    ),
                    CallbackQueryHandler(self.cancel_input, pattern="^cancel_input$"),
                ],
                AWAITING_USER_ID_TO_REMOVE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND, self.handle_remove_user
                    ),
                    CallbackQueryHandler(self.cancel_input, pattern="^cancel_input$"),
                ],
                AWAITING_GROUP_ID_TO_ADD: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND, self.handle_add_group
                    ),
                    CallbackQueryHandler(self.cancel_input, pattern="^cancel_input$"),
                ],
                AWAITING_GROUP_ID_TO_REMOVE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND, self.handle_remove_group
                    ),
                    CallbackQueryHandler(self.cancel_input, pattern="^cancel_input$"),
                ],
                AWAITING_ADMIN_ID_TO_ADD: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND, self.handle_add_admin
                    ),
                    CallbackQueryHandler(self.cancel_input, pattern="^cancel_input$"),
                ],
                AWAITING_ADMIN_ID_TO_REMOVE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND, self.handle_remove_admin
                    ),
                    CallbackQueryHandler(self.cancel_input, pattern="^cancel_input$"),
                ],
                AWAITING_API_ID: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_api_id),
                ],
                AWAITING_API_HASH: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND, self.handle_api_hash
                    ),
                ],
                AWAITING_PHONE_NUMBER: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND, self.handle_phone_number
                    ),
                ],
                AWAITING_PHONE_CODE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND, self.handle_phone_code
                    ),
                ],
                AWAITING_2FA_PASSWORD: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND, self.handle_2fa_password
                    ),
                ],
            },
            fallbacks=[CommandHandler("cancel", self.cancel_and_back)],
            per_message=False,
        )


# 用于命令菜单的admin命令处理器（实际处理由ConversationHandler完成）
async def admin_command_placeholder(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """管理员面板命令占位符 - 此函数仅用于命令菜单注册，实际处理由ConversationHandler完成"""
    # 这个函数不会被调用，因为ConversationHandler会先拦截/admin命令
    pass


admin_panel_handler = AdminPanelHandler()

# Register commands (注意：admin命令不在这里注册，因为它由ConversationHandler处理)
command_factory.register_command(
    "add", add_command, permission=Permission.ADMIN, description="添加用户到白名单"
)
command_factory.register_command(
    "addgroup",
    addgroup_command,
    permission=Permission.ADMIN,
    description="添加群组到白名单",
)
# admin命令由ConversationHandler处理，不需要在这里注册
# command_factory.register_command("admin", admin_command_placeholder, permission=Permission.ADMIN, description="打开管理员面板")
