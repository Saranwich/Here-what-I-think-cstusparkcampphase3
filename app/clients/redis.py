"""Connection to Redis. Knows nothing about what gets stored in it."""

from redis.asyncio import Redis

from app.core.config import REDIS_URL


def create_client() -> Redis:
    return Redis.from_url(REDIS_URL, decode_responses=True)
