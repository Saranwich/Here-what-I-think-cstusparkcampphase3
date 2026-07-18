from fastapi import Request
from redis.asyncio import Redis

from app.config import REDIS_URL


def create_client() -> Redis:
    return Redis.from_url(REDIS_URL, decode_responses=True)


def get_redis(request: Request) -> Redis:
    """FastAPI dependency: the client created in the lifespan."""
    return request.app.state.redis
