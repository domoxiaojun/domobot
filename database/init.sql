-- Telegram Bot 数据库初始化脚本
-- 使用现有变量名保持兼容性

-- 创建数据库（如果需要）
-- CREATE DATABASE IF NOT EXISTS bot DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- USE bot;

-- 用户表（保持现有字段名）
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,  -- 使用 telegram_id 作为主键
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_username (username),
    INDEX idx_last_seen (last_seen)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 管理员权限表（与现有 admin_permissions 对应）
CREATE TABLE IF NOT EXISTS admin_permissions (
    user_id BIGINT PRIMARY KEY,
    granted_by BIGINT NOT NULL,
    granted_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_granted_by (granted_by),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 超级管理员表（从配置中的 SUPER_ADMIN_ID 初始化）
CREATE TABLE IF NOT EXISTS super_admins (
    user_id BIGINT PRIMARY KEY,
    added_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 用户白名单表（与现有 user_whitelist 对应）
CREATE TABLE IF NOT EXISTS user_whitelist (
    user_id BIGINT PRIMARY KEY,
    added_by BIGINT NOT NULL,
    added_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_added_by (added_by),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 群组白名单表（与现有 group_whitelist 对应）
CREATE TABLE IF NOT EXISTS group_whitelist (
    group_id BIGINT PRIMARY KEY,
    group_name VARCHAR(255),
    added_by BIGINT NOT NULL,
    added_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_added_by (added_by)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 管理员操作日志表（可选，用于审计）
CREATE TABLE IF NOT EXISTS admin_logs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    admin_id BIGINT NOT NULL,
    action VARCHAR(100) NOT NULL,
    target_type VARCHAR(50),  -- 'user', 'group', 'cache', etc.
    target_id BIGINT,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_admin_id (admin_id),
    INDEX idx_action (action),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 命令使用统计表（可选，用于分析）
CREATE TABLE IF NOT EXISTS command_stats (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    command VARCHAR(50) NOT NULL,
    user_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    chat_type VARCHAR(20),  -- 'private', 'group', 'supergroup'
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_command (command),
    INDEX idx_user_id (user_id),
    INDEX idx_executed_at (executed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 创建视图：活跃管理员（包括超级管理员）
CREATE OR REPLACE VIEW active_admins AS
SELECT u.user_id, u.username, u.first_name, u.last_name, 
       CASE WHEN sa.user_id IS NOT NULL THEN 'super_admin' ELSE 'admin' END as admin_type
FROM users u
LEFT JOIN admin_permissions ap ON u.user_id = ap.user_id
LEFT JOIN super_admins sa ON u.user_id = sa.user_id
WHERE ap.user_id IS NOT NULL OR sa.user_id IS NOT NULL;

-- 创建存储过程：检查用户权限
DELIMITER //
CREATE PROCEDURE check_user_permission(IN p_user_id BIGINT)
BEGIN
    SELECT 
        u.user_id,
        u.username,
        CASE 
            WHEN sa.user_id IS NOT NULL THEN 'SUPER_ADMIN'
            WHEN ap.user_id IS NOT NULL THEN 'ADMIN'
            WHEN uw.user_id IS NOT NULL THEN 'WHITELISTED'
            ELSE 'USER'
        END as permission_level
    FROM users u
    LEFT JOIN super_admins sa ON u.user_id = sa.user_id
    LEFT JOIN admin_permissions ap ON u.user_id = ap.user_id
    LEFT JOIN user_whitelist uw ON u.user_id = uw.user_id
    WHERE u.user_id = p_user_id;
END//
DELIMITER ;