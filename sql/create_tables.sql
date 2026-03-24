

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

CREATE INDEX idx_users_user_id ON users(user_id);

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

CREATE INDEX idx_devices_device_id ON devices(device_id);
CREATE INDEX idx_devices_status ON devices(status);

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

CREATE INDEX idx_device_bindings_device ON device_bindings(device_id);
CREATE INDEX idx_device_bindings_user ON device_bindings(user_id);

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

CREATE INDEX idx_chat_messages_device ON chat_messages(device_id);
CREATE INDEX idx_chat_messages_created ON chat_messages(created_at);

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

CREATE INDEX idx_llm_proxy_log_device_id ON llm_proxy_log(device_id);
CREATE INDEX idx_llm_proxy_log_user_id ON llm_proxy_log(user_id);
CREATE INDEX idx_llm_proxy_log_timestamp ON llm_proxy_log(timestamp);
CREATE INDEX idx_llm_proxy_log_model ON llm_proxy_log(model);
CREATE INDEX idx_llm_proxy_log_provider ON llm_proxy_log(provider);
CREATE INDEX idx_llm_proxy_log_request_type ON llm_proxy_log(request_type);

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

CREATE INDEX idx_llm_usage_user_id ON llm_usage(user_id);
CREATE INDEX idx_llm_usage_device_id ON llm_usage(device_id);
CREATE INDEX idx_llm_usage_model ON llm_usage(model);
CREATE INDEX idx_llm_usage_provider ON llm_usage(provider);

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