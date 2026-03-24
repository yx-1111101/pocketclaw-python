-- ==========================
-- Database
-- ==========================
CREATE DATABASE IF NOT EXISTS openfriday;
USE openfriday;

-- ==========================
-- Table: users
-- ==========================
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(255) NOT NULL,
    openid VARCHAR(255) NULL,
    phone VARCHAR(255) NULL,
    nickname VARCHAR(255) NULL,
    avatar VARCHAR(255) NULL,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id),
    UNIQUE KEY users_openid_key (openid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Indexes
SET @tbl := 'users';
SET @idx := 'idx_users_openid';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx) = 0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, ' (openid)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ==========================
-- Table: devices
-- ==========================
CREATE TABLE IF NOT EXISTS devices (
    device_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NULL DEFAULT '我的盒子',
    public_url VARCHAR(255) NULL,
    device_secret_hash VARCHAR(255) NULL,
    firmware_version VARCHAR(255) NULL,
    pairing_code_hash VARCHAR(255) NULL,
    pairing_code_expires TIMESTAMP NULL,
    status VARCHAR(50) NULL DEFAULT 'offline',
    last_seen TIMESTAMP NULL,
    provisioned_at TIMESTAMP NULL,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (device_id),
    UNIQUE KEY devices_device_id_key (device_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Indexes
SET @tbl := 'devices';
SET @idx := 'idx_devices_device_id';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx) = 0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(device_id)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx := 'idx_devices_status';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx) = 0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(status)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ==========================
-- Table: device_bindings
-- ==========================
CREATE TABLE IF NOT EXISTS device_bindings (
    id CHAR(36) NOT NULL DEFAULT UUID(),
    user_id VARCHAR(255) NOT NULL,
    device_id VARCHAR(255) NOT NULL,
    role VARCHAR(50) NULL DEFAULT 'owner',
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY device_bindings_user_id_device_id_key (user_id, device_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Indexes
SET @tbl := 'device_bindings';
SET @idx := 'idx_device_bindings_device';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx) = 0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(device_id)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx := 'idx_device_bindings_user';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx) = 0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(user_id)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ==========================
-- Table: chat_messages
-- ==========================
CREATE TABLE IF NOT EXISTS chat_messages (
    id CHAR(36) NOT NULL DEFAULT UUID(),
    device_id CHAR(36) NULL,
    role VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    model VARCHAR(255) NULL,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Indexes
SET @tbl := 'chat_messages';
SET @idx := 'idx_chat_messages_device';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx) = 0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(device_id)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx := 'idx_chat_messages_created';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx) = 0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(created_at)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Repeat this pattern for llm_proxy_log, llm_usage, llm_pricing, llm_credit
-- ... basically check INFORMATION_SCHEMA.STATISTICS for each index before creating
