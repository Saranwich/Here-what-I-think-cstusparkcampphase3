"""Redis-backed chat memory: one list of messages per session."""

import json

from redis.asyncio import Redis

MAX_MESSAGES = 20        # keep the last N messages (user + assistant)
TTL_SECONDS = 60 * 60    # forget a session after 1h of silence


def _key(session_id: str) -> str:
    return f"chat:{session_id}"


async def load(r: Redis, session_id: str) -> list[dict]:
    raw = await r.lrange(_key(session_id), 0, -1)
    return [json.loads(m) for m in raw]


async def append(r: Redis, session_id: str, role: str, content: str) -> None:
    key = _key(session_id)
    async with r.pipeline() as pipe:
        pipe.rpush(key, json.dumps({"role": role, "content": content}))
        pipe.ltrim(key, -MAX_MESSAGES, -1)
        pipe.expire(key, TTL_SECONDS)
        await pipe.execute()


async def clear(r: Redis, session_id: str) -> None:
    await r.delete(_key(session_id))
