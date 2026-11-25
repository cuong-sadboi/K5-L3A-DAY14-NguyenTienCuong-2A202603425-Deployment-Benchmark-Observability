"""Rate limiting (tiêu chí 7) using a Redis sliding window."""
import math
import time
import uuid

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import get_redis

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """Enforce RATE_LIMIT_PER_MINUTE per API key using a Redis sorted set."""
    client = get_redis()
    if client is None:
        raise HTTPException(status_code=503, detail="Rate limiter storage unavailable")

    redis_key = f"rate_limit:{key}"
    now = time.time()
    window_start = now - WINDOW_SECONDS

    try:
        pipe = client.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        _, count = pipe.execute()

        if count >= settings.rate_limit_per_minute:
            oldest = client.zrange(redis_key, 0, 0, withscores=True)
            retry_after = WINDOW_SECONDS
            if oldest:
                retry_after = max(1, math.ceil(WINDOW_SECONDS - (now - float(oldest[0][1]))))
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

        member = f"{now}:{uuid.uuid4().hex}"
        pipe = client.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, WINDOW_SECONDS + 5)
        pipe.execute()
    except HTTPException:
        raise
    except redis.RedisError as exc:
        raise HTTPException(status_code=503, detail="Rate limiter storage unavailable") from exc
