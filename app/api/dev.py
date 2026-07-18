"""Endpoints for poking at things during development."""

from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.api.deps import get_redis
from app.clients import llm
from app.services import chat

router = APIRouter(prefix="/api")


@router.get("/health")
async def health(r: Redis = Depends(get_redis)):
    return {"status": "OK", "redis": await r.ping()}


@router.get("/playground")
async def playground(message: str):
    return await llm.get_playground(message)


@router.get("/chat_test")
async def chat_test(
    message: str,
    session_id: str = "devtest",
    r: Redis = Depends(get_redis),
):
    """Playground + Redis memory. Same session_id keeps the conversation."""
    return await chat.reply(r, session_id, message)
