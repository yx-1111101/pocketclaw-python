# LLM Proxy Usage Statistics

This module provides usage tracking and cost calculation for the LLM proxy service.

## Features

- Log all proxy requests to Supabase
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
- `usage`: JSONB containing token counts and cost
- `created_at`: Record creation time

### llm_usage
Stores pricing information for LLM models.

Columns:
- `id`: Primary key
- `model`: Model name (unique)
- `pricing`: JSONB with input/output prices per 1M tokens
- `updated_at`: Last update time
- `created_at`: Record creation time

## Setup

1. Create the database tables:
```bash
psql -h <host> -U <user> -d <database> -f llm_proxy/sql/create_tables.sql
```

2. Load pricing data:
```bash
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_KEY="your-service-role-key"
python llm_proxy/load_pricing.py [path/to/pricing.yaml]
```

Default pricing file: `/home/xuyz20/model_router/config/pricing.yaml`

## Usage

The usage tracking is automatically integrated into the proxy. Every request to `/llm/chat/completions` will:

1. Call the LLM provider
2. Extract usage information from the response
3. Look up pricing for the model
4. Calculate cost
5. Log to `llm_proxy_log` table

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
