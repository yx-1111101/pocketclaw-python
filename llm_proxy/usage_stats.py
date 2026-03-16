"""Usage statistics calculation for LLM proxy."""
from typing import Dict, Any, Optional, Protocol, Tuple


class UsageExtractor(Protocol):
    """Protocol for extracting usage from LLM API responses."""

    def extract_usage(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract usage information from API response."""
        ...


class OpenAIUsageExtractor:
    """Extract usage from OpenAI-compatible API responses."""

    def extract_usage(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract usage from OpenAI response format."""
        usage = response.get("usage", {})
        return {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }


class AnthropicUsageExtractor:
    """Extract usage from Anthropic API responses."""

    def extract_usage(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract usage from Anthropic response format."""
        usage = response.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        return {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }


class UsageCalculator:
    """Calculate cost based on usage and pricing."""

    def __init__(self):
        self._extractors: Dict[str, UsageExtractor] = {
            "openai": OpenAIUsageExtractor(),
            "anthropic": AnthropicUsageExtractor(),
        }

    def get_extractor(self, request_type: str) -> UsageExtractor:
        """Get the appropriate usage extractor for an API request type (e.g. 'openai', 'anthropic')."""
        return self._extractors.get(request_type, OpenAIUsageExtractor())

    def calculate_cost(
        self,
        usage: Dict[str, Any],
        pricing: Optional[Dict[str, Any]],
    ) -> Tuple[float, str]:
        """Calculate cost from usage and a llm_pricing row.

        Returns (cost_original, currency_type) where cost_original is in the
        pricing table's native currency (e.g. USD or CNY) per 1M tokens.
        """
        if not pricing:
            return 0.0, "USD"

        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        input_price = float(pricing.get("input_price", 0.0))
        output_price = float(pricing.get("output_price", 0.0))
        currency = pricing.get("currency_type", "USD").upper()

        cost = (prompt_tokens / 1_000_000) * input_price + \
               (completion_tokens / 1_000_000) * output_price

        return cost, currency


# Global calculator instance
calculator = UsageCalculator()
