"""Production AI Agent — Part 6 Final Project."""
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import close_redis, redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Format every application log record as a single valid JSON object line."""

    _RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {
        "message",
        "asctime",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _configure_logging() -> logging.Logger:
    app_logger = logging.getLogger("app")
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    app_logger.setLevel(level)
    app_logger.propagate = False
    if not app_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        app_logger.addHandler(handler)
    return logging.getLogger("app.main")


logger = _configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Manage startup logging and graceful Redis cleanup on shutdown."""
    logger.info(
        "startup",
        extra={"environment": settings.environment, "port": settings.port},
    )
    try:
        yield
    finally:
        logger.info("shutdown", extra={"environment": settings.environment})
        close_redis()


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every HTTP request and its latency as structured JSON."""
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
    logger.info(
        "request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration_ms,
        },
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a clean 500 JSON response without leaking stack traces."""
    logger.error(
        "unhandled_error",
        extra={"path": request.url.path, "error": str(exc)},
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: Optional[str] = Field(default=None, max_length=128)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe: always returns 200 while the process is running."""
    return {"status": "ok", "environment": settings.environment}


@app.get("/ready")
def ready():
    """Readiness probe: returns 200 when Redis is reachable, 503 otherwise."""
    if redis_healthy():
        return {"status": "ready", "redis": "ok"}
    return JSONResponse(
        status_code=503,
        content={"status": "not ready", "redis": "unavailable"},
    )


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)) -> dict[str, Any]:
    """Process an authenticated question with rate limiting and cost guard."""
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)
    input_tokens = max(1, len(body.question) // 4)
    output_tokens = max(1, len(answer) // 4)
    cost_usd = record_cost(input_tokens, output_tokens)

    logger.info(
        "ask_completed",
        extra={
            "user_id": body.user_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost_usd, 8),
        },
    )
    return {
        "question": body.question,
        "answer": answer,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost_usd, 8),
        },
    }
