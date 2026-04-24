-- ==========================
-- Migration: Gateway Management
-- ==========================
USE openfriday;

-- ── devices 表新增列 ──────────────────────────────────────────────
ALTER TABLE devices
    ADD COLUMN IF NOT EXISTS source_type VARCHAR(50) NULL DEFAULT 'legacy',
    ADD COLUMN IF NOT EXISTS runtime VARCHAR(255) NULL,
    ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMP NULL;

-- ── device_bindings 表新增列 ──────────────────────────────────────
ALTER TABLE device_bindings
    ADD COLUMN IF NOT EXISTS display_name VARCHAR(255) NULL;

-- ── 新建 pairing_credentials 表 ──────────────────────────────────
CREATE TABLE IF NOT EXISTS pairing_credentials (
    id BIGINT NOT NULL AUTO_INCREMENT,
    device_id VARCHAR(255) NOT NULL,
    credential_code VARCHAR(16) NOT NULL,
    credential_hash VARCHAR(255) NOT NULL,
    runtime VARCHAR(255) NULL,
    expires_at TIMESTAMP NOT NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 5,
    used TINYINT(1) NOT NULL DEFAULT 0,
    invalidated TINYINT(1) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- pairing_credentials indexes
SET @tbl := 'pairing_credentials';
SET @idx := 'idx_pairing_credentials_device_id';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx)=0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(device_id)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx := 'idx_pairing_credentials_credential_hash';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx)=0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(credential_hash)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx := 'idx_pairing_credentials_expires_at';
SET @sql := IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=@tbl AND INDEX_NAME=@idx)=0,
    CONCAT('CREATE INDEX ', @idx, ' ON ', @tbl, '(expires_at)'),
    'SELECT "Index exists, skipped"');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
