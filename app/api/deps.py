"""Shared FastAPI dependencies."""

import asyncpg
from fastapi import Request
from redis.asyncio import Redis


def get_redis(request: Request) -> Redis:
    """The Redis client created in the lifespan."""
    return request.app.state.redis


def get_db(request: Request) -> asyncpg.Pool:
    """The Postgres pool created in the lifespan."""
    return request.app.state.db
