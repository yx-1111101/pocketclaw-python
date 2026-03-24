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

-- Users indexes
SET @tbl := 'users';
SET @idx := 'idx_users_openid';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx)=0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(openid)'),
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

-- Devices indexes
SET @tbl := 'devices';
SET @idx := 'idx_devices_device_id';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx)=0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(device_id)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx := 'idx_devices_status';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx)=0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(status)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ==========================
-- Table: device_bindings
-- ==========================
CREATE TABLE IF NOT EXISTS device_bindings (
    id BIGINT NOT NULL AUTO_INCREMENT,
    user_id VARCHAR(255) NOT NULL,
    device_id VARCHAR(255) NOT NULL,
    role VARCHAR(50) NULL DEFAULT 'owner',
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY device_bindings_user_id_device_id_key (user_id, device_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Device_bindings indexes
SET @tbl := 'device_bindings';
SET @idx := 'idx_device_bindings_device';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx)=0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(device_id)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx := 'idx_device_bindings_user';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx)=0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(user_id)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ==========================
-- Table: chat_messages
-- ==========================
CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGINT NOT NULL AUTO_INCREMENT,
    device_id BIGINT NULL,
    role VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    model VARCHAR(255) NULL,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Chat_messages indexes
SET @tbl := 'chat_messages';
SET @idx := 'idx_chat_messages_device';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx)=0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(device_id)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx := 'idx_chat_messages_created';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx)=0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(created_at)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ==========================
-- Table: llm_proxy_log
-- ==========================
CREATE TABLE IF NOT EXISTS llm_proxy_log (
    id BIGINT NOT NULL AUTO_INCREMENT,
    user_id VARCHAR(255) NULL,
    device_id VARCHAR(255) NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    model VARCHAR(255) NOT NULL,
    provider VARCHAR(255) NOT NULL,
    request_type VARCHAR(50) NOT NULL DEFAULT 'openai',
    usage JSON NOT NULL,
    cost_original DECIMAL(18,8) NOT NULL DEFAULT 0,
    cost_currency VARCHAR(10) NOT NULL DEFAULT 'USD',
    cost_cny DECIMAL(18,8) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- llm_proxy_log indexes
SET @tbl := 'llm_proxy_log';
SET @idx := 'idx_llm_proxy_log_device_id';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx)=0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(device_id)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx := 'idx_llm_proxy_log_user_id';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx)=0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(user_id)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx := 'idx_llm_proxy_log_timestamp';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx)=0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(timestamp)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx := 'idx_llm_proxy_log_model';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx)=0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(model)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx := 'idx_llm_proxy_log_provider';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx)=0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(provider)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx := 'idx_llm_proxy_log_request_type';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx)=0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(request_type)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ==========================
-- Table: llm_usage
-- ==========================
CREATE TABLE IF NOT EXISTS llm_usage (
    user_id VARCHAR(255) NOT NULL,
    device_id VARCHAR(255) NOT NULL,
    model VARCHAR(255) NOT NULL,
    provider VARCHAR(255) NOT NULL,
    request_type VARCHAR(50) NOT NULL DEFAULT 'openai',
    request_count BIGINT NOT NULL DEFAULT 0,
    prompt_tokens BIGINT NOT NULL DEFAULT 0,
    completion_tokens BIGINT NOT NULL DEFAULT 0,
    total_tokens BIGINT NOT NULL DEFAULT 0,
    total_cost DECIMAL(18,8) NOT NULL DEFAULT 0,
    first_used_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, device_id, model, provider, request_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- llm_usage indexes
SET @tbl := 'llm_usage';
SET @idx := 'idx_llm_usage_user_id';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx)=0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(user_id)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx := 'idx_llm_usage_device_id';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx)=0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(device_id)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx := 'idx_llm_usage_model';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx)=0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(model)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx := 'idx_llm_usage_provider';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx)=0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(provider)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ==========================
-- Table: llm_pricing
-- ==========================
CREATE TABLE IF NOT EXISTS llm_pricing (
    model VARCHAR(255) NOT NULL,
    provider VARCHAR(255) NOT NULL,
    request_type VARCHAR(50) NOT NULL DEFAULT 'openai',
    currency_type VARCHAR(10) NOT NULL DEFAULT 'USD',
    input_price DECIMAL(18,8) NOT NULL DEFAULT 0,
    output_price DECIMAL(18,8) NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (model, provider, request_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ==========================
-- Table: llm_credit
-- ==========================
CREATE TABLE IF NOT EXISTS llm_credit (
    user_id VARCHAR(255) NOT NULL,
    balance DECIMAL(18,8) NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;