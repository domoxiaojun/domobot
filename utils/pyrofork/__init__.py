"""
Pyrofork 模块 - 用户信息查询和会话管理

Pyrofork 是 Pyrogram 的活跃社区维护版本，支持最新 Telegram API (Layer 200+)

主要功能：
- 获取高级用户信息（注册日期、DC 位置、Premium 状态）
- 用户会话管理（登录、登出）
- API 凭证管理
- 多数据源整合（MySQL + Redis + Raw API + ID 推测）

模块结构：
├── credentials.py     - API 凭证管理
├── session.py         - 会话和用户信息缓存
├── client.py          - 客户端生命周期管理
├── login.py           - 登录流程管理
├── user_info.py       - 用户信息查询（顶层整合）
├── dc_extractor.py    - DC 位置提取
├── persistence.py     - MySQL 持久化
└── id_estimation.py   - ID 推测算法
"""

# ============ 公共API导出 ============

# 凭证管理 (credentials.py)
from .credentials import (
    save_pyrofork_credentials,
    get_pyrofork_credentials,
    delete_pyrofork_credentials,
)

# 会话管理 (session.py)
from .session import (
    save_session_string,
    get_session_info,
    get_pyrofork_login_status,
    save_user_info_to_cache,
    get_cached_user_info,
)

# 客户端管理 (client.py)
from .client import (
    get_pyrofork_client,
    get_bot_id,
    get_logged_in_username,
    is_user_mode,
    initialize_pyrofork_client,
    stop_pyrofork_client,
)

# 登录流程 (login.py)
from .login import (
    start_phone_login,
    complete_phone_login,
    logout_pyrofork_user,
)

# 用户信息查询 (user_info.py) - 顶层整合模块
from .user_info import (
    get_user_full_info,
    get_user_dc_and_premium,
    get_user_info_via_raw_api,
    DC_LOCATIONS,
)

# DC 位置提取 (dc_extractor.py)
from .dc_extractor import get_dc_from_profile_photo

# MySQL 持久化 (persistence.py)
from .persistence import (
    save_telegram_reg_to_db,
    get_telegram_reg_from_db,
)

# ID 推测算法 (id_estimation.py)
from .id_estimation import (
    estimate_registration_date,
    save_registration_sample,
)

# ============ __all__ 定义 ============

__all__ = [
    # 凭证管理
    "save_pyrofork_credentials",
    "get_pyrofork_credentials",
    "delete_pyrofork_credentials",
    # 会话管理
    "save_session_string",
    "get_session_info",
    "get_pyrofork_login_status",
    "save_user_info_to_cache",
    "get_cached_user_info",
    # 客户端管理
    "get_pyrofork_client",
    "get_bot_id",
    "get_logged_in_username",
    "is_user_mode",
    "initialize_pyrofork_client",
    "stop_pyrofork_client",
    # 登录流程
    "start_phone_login",
    "complete_phone_login",
    "logout_pyrofork_user",
    # 用户信息查询
    "get_user_full_info",
    "get_user_dc_and_premium",
    "get_user_info_via_raw_api",
    "DC_LOCATIONS",
    # DC 位置提取
    "get_dc_from_profile_photo",
    # MySQL 持久化
    "save_telegram_reg_to_db",
    "get_telegram_reg_from_db",
    # ID 推测算法
    "estimate_registration_date",
    "save_registration_sample",
]
