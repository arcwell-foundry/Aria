"""LLM usage logging to Supabase for cost tracking and analytics."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

PRICING = {
    "anthropic/claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "anthropic/claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
}


class UsageLogger:
    """Logs LLM usage metrics to Supabase for cost tracking."""

    def __init__(self, supabase_client):
        self.db = supabase_client

    async def log(
        self,
        tenant_id: str = "",
        user_id: str = "",
        agent_id: str = "general",
        task_type: str = "general",
        model: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
        status: str = "success",
        error_message: str = None,
        goal_id: str = None,
        cached_tokens: int = 0,
    ):
        """Log an LLM usage event to the database.

        Args:
            tenant_id: Tenant/company UUID for multi-tenant isolation.
            user_id: User UUID who initiated the request.
            agent_id: Agent that made the LLM call (e.g., "orchestrator", "scribe").
            task_type: Category of task (e.g., "chat_response", "email_draft").
            model: Model identifier (e.g., "anthropic/claude-sonnet-4-20250514").
            input_tokens: Number of input/prompt tokens consumed.
            output_tokens: Number of output/completion tokens generated.
            latency_ms: Request latency in milliseconds.
            status: "success" or "error".
            error_message: Error details if status is "error".
            goal_id: Associated goal UUID if part of a goal execution.
            cached_tokens: Number of tokens served from cache (if applicable).
        """
        try:
            provider = model.split("/")[0] if "/" in model else "anthropic"
            rates = PRICING.get(model, {"input": 3.00, "output": 15.00})
            input_cost = (input_tokens / 1_000_000) * rates["input"]
            output_cost = (output_tokens / 1_000_000) * rates["output"]

            self.db.table("llm_usage").insert({
                "tenant_id": tenant_id or None,
                "user_id": user_id or None,
                "agent_id": agent_id,
                "task_type": task_type,
                "goal_id": goal_id or None,
                "model": model,
                "provider": provider,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cached_tokens": cached_tokens,
                "input_cost_usd": float(input_cost),
                "output_cost_usd": float(output_cost),
                "total_cost_usd": float(input_cost + output_cost),
                "latency_ms": latency_ms,
                "status": status,
                "error_message": error_message,
            }).execute()
        except Exception as e:
            logger.warning(f"Failed to log LLM usage: {e}")
