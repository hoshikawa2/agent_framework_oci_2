from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from typing import Any

logger = logging.getLogger("agent_framework.analytics.tim_sequence")

# In-process fallback. This is not cross-process/global, but keeps telemetry alive
# when Redis is unavailable, matching the framework principle that observability
# must not break business execution.
_memory_lock = asyncio.Lock()
_memory_counters: dict[str, int] = defaultdict(int)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def sequence_enabled() -> bool:
    return _env_bool("PUBSUB_SEQUENCE_ENABLED", True)


def _redis_url() -> str | None:
    return os.getenv("PUBSUB_SEQUENCE_REDIS_URL") or os.getenv("REDIS_URL")


def _ttl_seconds() -> int:
    raw = os.getenv("PUBSUB_SEQUENCE_TTL_SECONDS") or os.getenv("SESSION_TTL_SECONDS") or "86400"
    try:
        return max(0, int(raw))
    except Exception:
        return 86400


def _fallback_enabled() -> bool:
    return _env_bool("PUBSUB_SEQUENCE_MEMORY_FALLBACK", True)


def _key_prefix() -> str:
    return os.getenv("PUBSUB_SEQUENCE_KEY_PREFIX") or "observer:sequence"


def _safe_part(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip()
    return text.replace(" ", "_").replace("/", "_").replace("\\", "_")


def build_sequence_key(agent_id: str | None, session_id: str) -> str:
    agent = _safe_part(agent_id or os.getenv("AGENT_NAME"), "agent")
    session = _safe_part(session_id, "unknown_session")
    return f"{_key_prefix()}:{agent}:{session}"


async def _next_sequence_redis(key: str, ttl_seconds: int) -> int | None:
    url = _redis_url()
    if not url:
        return None
    try:
        import redis.asyncio as redis_async  # type: ignore

        client = redis_async.Redis.from_url(url, decode_responses=True)
        try:
            value = await client.incr(key)
            if ttl_seconds > 0 and value == 1:
                await client.expire(key, ttl_seconds)
            return int(value)
        finally:
            try:
                await client.aclose()
            except AttributeError:  # redis-py older compatibility
                await client.close()
    except Exception:
        logger.exception("tim_sequence.redis_failed key=%s", key)
        return None


async def _next_sequence_memory(key: str) -> int:
    async with _memory_lock:
        _memory_counters[key] += 1
        return _memory_counters[key]


async def next_sequence(agent_id: str | None, session_id: str | None) -> int | None:
    """Return the next per-agent/per-session observer sequence.

    Redis is used first because INCR is atomic across workers/pods. If Redis is
    unavailable and PUBSUB_SEQUENCE_MEMORY_FALLBACK=true, an in-process counter is
    used as a best-effort fallback. If session_id is absent, None is returned so
    the payload remains valid without sequence.
    """
    if not sequence_enabled() or not session_id:
        return None

    key = build_sequence_key(agent_id, session_id)
    value = await _next_sequence_redis(key, _ttl_seconds())
    if value is not None:
        return value
    if _fallback_enabled():
        return await _next_sequence_memory(key)
    return None


async def ensure_sequence(payload: dict[str, Any]) -> dict[str, Any]:
    """Inject sequence if missing, preserving explicit values from metadata/body."""
    if not isinstance(payload, dict):
        return payload
    if payload.get("sequence") is not None:
        return payload
    session_id = payload.get("sessionId") or payload.get("session_id")
    agent_id = payload.get("agentId") or payload.get("agent_id") or os.getenv("AGENT_NAME")
    seq = await next_sequence(agent_id, session_id)
    if seq is not None:
        payload["sequence"] = seq
    return payload
