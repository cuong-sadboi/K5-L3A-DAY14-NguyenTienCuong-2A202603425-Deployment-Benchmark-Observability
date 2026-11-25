"""Kết nối Redis dùng chung cho rate limiter và cost guard."""
import logging
from typing import Optional

import redis

from app.config import settings

logger = logging.getLogger("app.redis_client")

_client: Optional[redis.Redis] = None


def get_redis() -> Optional[redis.Redis]:
    """Return a lazily initialized Redis client without pinging on import."""
    global _client
    if _client is not None:
        return _client
    if not settings.redis_url:
        return None
    try:
        _client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1.5,
            socket_timeout=1.5,
        )
    except Exception as exc:
        logger.warning("redis_client_init_failed", extra={"error": str(exc)})
        _client = None
    return _client


r = get_redis()


def redis_healthy() -> bool:
    """Check Redis connectivity for GET /ready."""
    client = get_redis()
    if client is None:
        return False
    try:
        return bool(client.ping())
    except Exception:
        return False


def close_redis() -> None:
    """Close the shared Redis client during application shutdown."""
    global _client, r
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
        _client = None
        r = None
