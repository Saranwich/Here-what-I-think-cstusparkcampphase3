"""Shared FastAPI dependencies."""

from fastapi import Request
from redis.asyncio import Redis


def get_redis(request: Request) -> Redis:
    """The Redis client created in the lifespan."""
    return request.app.state.redis
