"""Cost guard (tiêu chí 8) tracking daily and monthly LLM spend in Redis."""
import logging
from datetime import datetime, timezone

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import get_redis

logger = logging.getLogger("app.cost_guard")

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

DAILY_TTL_SECONDS = 2 * 86400
MONTHLY_TTL_SECONDS = 32 * 86400


def _budget_keys() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return (
        f"cost:daily:{now.strftime('%Y-%m-%d')}",
        f"cost:monthly:{now.strftime('%Y-%m')}",
    )


def check_budget() -> None:
    """Verify spend is below daily and monthly limits before calling the LLM."""
    client = get_redis()
    if client is None:
        raise HTTPException(status_code=503, detail="Cost guard storage unavailable")

    daily_key, monthly_key = _budget_keys()
    try:
        daily_raw, monthly_raw = client.mget(daily_key, monthly_key)
    except redis.RedisError as exc:
        raise HTTPException(status_code=503, detail="Cost guard storage unavailable") from exc

    daily_spent = float(daily_raw or 0.0)
    monthly_spent = float(monthly_raw or 0.0)
    if daily_spent >= settings.daily_budget_usd or monthly_spent >= settings.monthly_budget_usd:
        raise HTTPException(status_code=402, detail="Budget limit exceeded")


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Add request token cost to daily and monthly Redis counters."""
    cost = (input_tokens / 1000.0) * PRICE_INPUT_PER_1K + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    client = get_redis()
    if client is None:
        logger.warning("cost_record_skipped_no_redis", extra={"cost_usd": cost})
        return cost

    daily_key, monthly_key = _budget_keys()
    try:
        pipe = client.pipeline()
        pipe.incrbyfloat(daily_key, cost)
        pipe.expire(daily_key, DAILY_TTL_SECONDS)
        pipe.incrbyfloat(monthly_key, cost)
        pipe.expire(monthly_key, MONTHLY_TTL_SECONDS)
        pipe.execute()
    except redis.RedisError as exc:
        logger.error("cost_record_failed", extra={"error": str(exc), "cost_usd": cost})
    return cost
