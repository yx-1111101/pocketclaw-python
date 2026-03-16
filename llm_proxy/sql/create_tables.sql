-- ── llm_proxy_log ─────────────────────────────────────────────────────────────
-- Raw log of every proxied LLM request.
CREATE TABLE IF NOT EXISTS llm_proxy_log (
    id            BIGSERIAL     PRIMARY KEY,
    user_id       TEXT,
    device_id     TEXT          NOT NULL,
    timestamp     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    model         TEXT          NOT NULL,
    provider      TEXT          NOT NULL,
    request_type  TEXT          NOT NULL DEFAULT 'openai',
    usage         JSONB         NOT NULL,
    cost_original NUMERIC(18,8) NOT NULL DEFAULT 0,  -- cost in original pricing currency
    cost_currency TEXT          NOT NULL DEFAULT 'USD', -- currency of cost_original
    cost_cny      NUMERIC(18,8) NOT NULL DEFAULT 0,  -- cost converted to CNY
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_proxy_log_device_id    ON llm_proxy_log(device_id);
CREATE INDEX IF NOT EXISTS idx_llm_proxy_log_user_id      ON llm_proxy_log(user_id);
CREATE INDEX IF NOT EXISTS idx_llm_proxy_log_timestamp    ON llm_proxy_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_llm_proxy_log_model        ON llm_proxy_log(model);
CREATE INDEX IF NOT EXISTS idx_llm_proxy_log_provider     ON llm_proxy_log(provider);
CREATE INDEX IF NOT EXISTS idx_llm_proxy_log_request_type ON llm_proxy_log(request_type);

COMMENT ON TABLE  llm_proxy_log                IS 'Raw log of every proxied LLM request';
COMMENT ON COLUMN llm_proxy_log.provider       IS 'LLM API service provider (e.g. zhizengzeng, openai), identified by base_url';
COMMENT ON COLUMN llm_proxy_log.request_type   IS 'API protocol (e.g. openai, anthropic)';
COMMENT ON COLUMN llm_proxy_log.usage          IS 'JSON: prompt_tokens, completion_tokens, total_tokens';
COMMENT ON COLUMN llm_proxy_log.cost_original  IS 'Request cost in the pricing table native currency';
COMMENT ON COLUMN llm_proxy_log.cost_currency  IS 'Currency of cost_original (e.g. USD, CNY)';
COMMENT ON COLUMN llm_proxy_log.cost_cny       IS 'Request cost converted to CNY';


-- ── llm_usage ─────────────────────────────────────────────────────────────────
-- Aggregated token / cost usage per (user, device, model, provider, request_type).
-- Upserted on every request; use for dashboards and quota enforcement.
CREATE TABLE IF NOT EXISTS llm_usage (
    user_id          TEXT         NOT NULL,
    device_id        TEXT         NOT NULL,
    model            TEXT         NOT NULL,
    provider         TEXT         NOT NULL,
    request_type     TEXT         NOT NULL DEFAULT 'openai',
    request_count    BIGINT       NOT NULL DEFAULT 0,
    prompt_tokens    BIGINT       NOT NULL DEFAULT 0,
    completion_tokens BIGINT      NOT NULL DEFAULT 0,
    total_tokens     BIGINT       NOT NULL DEFAULT 0,
    total_cost       NUMERIC(18,8) NOT NULL DEFAULT 0,
    first_used_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_used_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, device_id, model, provider, request_type)
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_user_id      ON llm_usage(user_id);
CREATE INDEX IF NOT EXISTS idx_llm_usage_device_id    ON llm_usage(device_id);
CREATE INDEX IF NOT EXISTS idx_llm_usage_model        ON llm_usage(model);
CREATE INDEX IF NOT EXISTS idx_llm_usage_provider     ON llm_usage(provider);

COMMENT ON TABLE  llm_usage                  IS 'Aggregated usage stats per (user, device, model, provider, request_type)';
COMMENT ON COLUMN llm_usage.provider         IS 'LLM API service provider (e.g. zhizengzeng, openai), identified by base_url';
COMMENT ON COLUMN llm_usage.request_type     IS 'API protocol (e.g. openai, anthropic)';
COMMENT ON COLUMN llm_usage.request_count    IS 'Total number of requests made with this key combination';
COMMENT ON COLUMN llm_usage.total_cost       IS 'Cumulative cost in CNY';


-- ── llm_pricing ───────────────────────────────────────────────────────────────
-- Pricing lookup keyed by (model, provider, request_type).
-- Replaces the old single-column llm_usage pricing table.
CREATE TABLE IF NOT EXISTS llm_pricing (
    model         TEXT          NOT NULL,
    provider      TEXT          NOT NULL,
    request_type  TEXT          NOT NULL DEFAULT 'openai',
    currency_type TEXT          NOT NULL DEFAULT 'USD',  -- currency of input/output prices
    input_price   NUMERIC(18,8) NOT NULL DEFAULT 0,      -- per 1M input tokens
    output_price  NUMERIC(18,8) NOT NULL DEFAULT 0,      -- per 1M output tokens
    updated_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    PRIMARY KEY (model, provider, request_type)
);

COMMENT ON TABLE  llm_pricing                IS 'Per-model pricing keyed by (model, provider, request_type)';
COMMENT ON COLUMN llm_pricing.provider       IS 'LLM API service provider (e.g. zhizengzeng, openai)';
COMMENT ON COLUMN llm_pricing.request_type   IS 'API protocol (e.g. openai, anthropic)';
COMMENT ON COLUMN llm_pricing.currency_type  IS 'Currency of input_price and output_price (e.g. USD, CNY)';
COMMENT ON COLUMN llm_pricing.input_price    IS 'Price per 1M input tokens in currency_type';
COMMENT ON COLUMN llm_pricing.output_price   IS 'Price per 1M output tokens in currency_type';


-- ── llm_credit ────────────────────────────────────────────────────────────────
-- Current balance for each user. Debited on every request by the cost incurred.
-- Top-ups are recorded as positive adjustments; balance must not go below zero.
CREATE TABLE IF NOT EXISTS llm_credit (
    user_id      TEXT          PRIMARY KEY,
    balance      NUMERIC(18,8) NOT NULL DEFAULT 0 CHECK (balance >= 0),
    updated_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    created_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  llm_credit            IS 'Current credit balance per user in USD';
COMMENT ON COLUMN llm_credit.balance    IS 'Remaining balance in USD; debited by request cost, credited by top-ups';
