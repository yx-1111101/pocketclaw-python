# LLM Proxy Usage Statistics

This module provides usage tracking and cost calculation for the LLM proxy service.

## Features

- Log all proxy requests to MySQL
- Track token usage (prompt, completion, total)
- Calculate costs based on model pricing
- Support for multiple LLM providers (OpenAI, Anthropic, etc.)

## Database Tables

### llm_proxy_log
Logs all LLM proxy requests with usage statistics.

Columns:
- `id`: Primary key
- `user_id`: User identifier (nullable)
- `device_id`: Device identifier
- `timestamp`: Request timestamp
- `model`: Model name used
- `provider`: Provider name
- `request_type`: Request type (e.g. `openai`)
- `token_usage`: JSON containing token counts
- `cost_original`: Cost in original currency
- `cost_currency`: Currency code (e.g. `USD`)
- `cost_cny`: Cost in CNY
- `created_at`: Record creation time

### llm_usage
Aggregated usage statistics per user/device/model.

Columns:
- `user_id`, `device_id`, `model`, `provider`, `request_type`: Composite primary key
- `request_count`: Total number of requests
- `prompt_tokens`, `completion_tokens`, `total_tokens`: Accumulated token counts
- `total_cost`: Accumulated cost in CNY
- `first_used_at`, `last_used_at`: Usage timestamps

### llm_pricing
Pricing information for LLM models.

Columns:
- `model`, `provider`, `request_type`: Composite primary key
- `currency_type`: Currency (e.g. `USD`)
- `input_price`, `output_price`: Price per 1M tokens
- `updated_at`, `created_at`: Timestamps

## Setup

1. Create the database tables:
```bash
mysql -h <host> -u <user> -p <database> < sql/create_tables.sql
```

2. Load pricing data:
```bash
export MYSQL_HOST="localhost"
export MYSQL_PORT="3306"
export MYSQL_USER="root"
export MYSQL_PASSWORD="your-password"
export MYSQL_DB="openfriday"
python llm_proxy/load_pricing.py [path/to/pricing.yaml]
```

## Usage

The usage tracking is automatically integrated into the proxy. Every request to `/llm/chat/completions` will:

1. Call the LLM provider
2. Extract usage information from the response
3. Look up pricing for the model
4. Calculate cost
5. Log to `llm_proxy_log` table and upsert aggregated stats into `llm_usage`

## Adding New Providers

To add support for a new LLM provider's usage format:

1. Create a new extractor class in `usage_stats.py`:
```python
class NewProviderUsageExtractor:
    def extract_usage(self, response: Dict[str, Any]) -> Dict[str, Any]:
        # Extract tokens from provider-specific response format
        return {
            "prompt_tokens": ...,
            "completion_tokens": ...,
            "total_tokens": ...,
        }
```

2. Register it in `UsageCalculator.__init__`:
```python
self._extractors["newprovider"] = NewProviderUsageExtractor()
```

3. Update the router to use the correct extractor based on provider format.

## Cost Calculation

Costs are calculated as:
```
input_cost = (prompt_tokens / 1,000,000) × input_price
output_cost = (completion_tokens / 1,000,000) × output_price
total_cost = input_cost + output_cost
```

Prices are stored per 1M tokens in USD.
