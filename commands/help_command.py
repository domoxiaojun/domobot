# type: ignore
import logging

from telegram import Update
from telegram.ext import ContextTypes

from utils.command_factory import command_factory
from utils.formatter import foldable_text_with_markdown_v2
from utils.message_manager import delete_user_command, send_help

# 导入权限相关模块
from utils.permissions import Permission, get_user_permission

logger = logging.getLogger(__name__)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """显示机器人帮助信息"""

    # 添加 null 检查
    if not update.message:
        return

    user_permission = await get_user_permission(update, context)

    help_text = """🤖 *多功能价格查询机器人*

✨ *主要功能:*

💱 *汇率查询*
- `/rate`: 查看汇率查询帮助。
- `/rate USD`: 100美元(USD)兑换人民币(CNY)。
- `/rate USD JPY 50`: 50美元(USD)兑换日元(JPY)。
- `/rate USD 1+1`: 计算表达式并将结果从美元(USD)兑换为人民币(CNY)。

🎮 *Steam 价格查询*
- `/steam <游戏名>`: 查询Steam游戏在默认地区的价格。
- `/steam <游戏名> [国家代码]`: 在指定的一个或多个国家/地区查询游戏价格。
- `/steamb <捆绑包名/ID>`: 查询Steam捆绑包的价格和内容。

📺 *流媒体服务价格*
- `/nf [国家代码]`: 查询Netflix订阅价格 (默认查询热门地区)。
- `/ds [国家代码]`: 查询Disney+订阅价格 (默认查询热门地区)。
- `/sp [国家代码]`: 查询Spotify Premium价格 (默认查询热门地区)。

📱 *应用与服务价格*
- `/app <应用名>`: 搜索App Store应用。
- `/gp <应用名>`: 搜索Google Play应用。
- `/aps <服务> [国家代码]`: 查询Apple服务价格 (服务: `iCloud`, `AppleOne`, `AppleMusic`)。

🌍 *支持的国家/地区示例:*
`US`(美国), `CN`(中国), `TR`(土耳其), `NG`(尼日利亚), `IN`(印度), `MY`(马来西亚), `JP`(日本), `GB`(英国), `DE`(德国) 等。

💡 *使用技巧:*
- 大部分命令支持中文国家名，如"美国"、"土耳其"。
- 不指定国家时，通常会查询多个热门或低价区。
- 所有价格会自动转换为人民币(CNY)以供参考。
- 数据具有智能缓存，提高响应速度且减少API调用。
- 支持数学表达式计算，如 `/rate USD 1+1*2`。

⚡ *快速开始:*
- `/nf`: 查看Netflix全球价格排名。
- `/steam 赛博朋克`: 查询《赛博朋克2077》的价格。
- `/rate`: 查看汇率转换的详细帮助。
- `/info`: 获取对话、用户和消息的详细信息。

🔄 *消息管理:*
- 所有回复消息会自动删除以保持群聊整洁。
- 支持按钮交互，避免重复输入命令。"""

    admin_help_text = """

🔧 *管理员功能:*

📋 *核心管理*
- `/admin`: 打开交互式管理面板 (用户/群组/管理员管理)。
- `/add <用户ID>`: (或回复消息) 添加用户到白名单。
- `/addgroup`: (在群组中) 添加当前群组到白名单。


🧹 *缓存管理*
- `/rate_cleancache`: 清理汇率缓存。
- `/nf_cleancache`: 清理Netflix缓存。
- `/ds_cleancache`: 清理Disney+缓存。
- `/sp_cleancache`: 清理Spotify缓存。
- `/gp_cleancache`: 清理Google Play缓存。
- `/gp_clearitem <包名> [国家...]`: 清理Google Play指定包名缓存（含MySQL）。
- `/app_cleancache`: 清理App Store缓存。
- `/app_clearitem <AppID> [国家...]`: 清理App Store指定AppID缓存（含MySQL）。
- `/steamcc`: 清理Steam相关缓存。
- `/steam_clearitem <AppID|bundle_ID> [国家...]`: 清理Steam指定条目缓存（含MySQL）。
- `/aps_cleancache`: 清理Apple服务缓存。

💡 *管理技巧:*
- 管理面板支持批量操作和实时刷新。
- 所有缓存清理操作都会显示清理结果。"""

    super_admin_help_text = """

🔐 *超级管理员功能:*

👥 *高级管理*
- 管理面板中的"管理管理员"功能 (添加/移除管理员)。
- 完整的系统控制权限 (所有管理员功能)。
- 访问所有系统状态和日志数据。

⚙️ *系统控制*
- 完整的日志管理权限 (归档/清理/维护)。
- 定时任务调度管理。
- 自定义脚本加载控制。

🛡️ *安全管理*
- 管理员权限分配和撤销。
- 系统安全策略配置。
- 全局白名单管理权限。"""

    if user_permission.value >= Permission.ADMIN.value:
        help_text += admin_help_text

    if user_permission.value >= Permission.SUPER_ADMIN.value:
        help_text += super_admin_help_text

    help_text += """

📞 *联系我们:*
如需申请使用权限或遇到问题，请联系机器人管理员。"""

    await send_help(
        context,
        update.message.chat_id,
        foldable_text_with_markdown_v2(help_text),
        parse_mode="MarkdownV2",
    )
    await delete_user_command(
        context, update.message.chat_id, update.message.message_id
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理/start命令"""
    # 添加 null 检查
    if not update.message or not update.effective_user:
        return

    user = update.effective_user

    welcome_text = f"""👋 *欢迎使用多功能价格查询机器人!*

你好 {user.first_name}!

🎯 *这个机器人可以帮你:*
- 💱 查询实时汇率并进行货币转换
- 🎮 查询Steam游戏在全球各国的价格
- 📺 查询Netflix、Disney+等流媒体订阅价格
- 📱 查询App Store和Google Play应用价格
- 🍎 查询Apple各项服务的全球定价

💡 *快速开始:*
发送 `/help` 查看详细使用指南

🚀 *试试这些命令:*
- `/nf`: 查看Netflix全球价格
- `/steam 赛博朋克`: 查询游戏价格
- `/rate USD CNY 100`: 汇率转换

🌟 *功能亮点:*
✅ 支持40+国家和地区查询
✅ 实时汇率自动转换为人民币
✅ 智能缓存，查询速度快
✅ 支持中文国家名称输入

开始探索吧! 🎉"""

    await send_help(
        context,
        update.message.chat_id,
        foldable_text_with_markdown_v2(welcome_text),
        parse_mode="MarkdownV2",
    )
    await delete_user_command(
        context, update.message.chat_id, update.message.message_id
    )


# Register commands
command_factory.register_command(
    "start",
    start_command,
    permission=Permission.USER,
    description="开始使用机器人",
    use_retry=False,
    use_rate_limit=False,
)
command_factory.register_command(
    "help",
    help_command,
    permission=Permission.USER,
    description="显示帮助信息",
    use_retry=False,
    use_rate_limit=False,
)
