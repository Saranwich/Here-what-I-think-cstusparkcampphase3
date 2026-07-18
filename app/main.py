from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, Request
from redis.asyncio import Redis

from app.handlers import ai, line
from app.services import openai, redis as redis_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    app.state.redis = redis_service.create_client()
    await app.state.redis.ping()
    print("app opened")
    try:
        yield
    finally:
        # --- shutdown ---
        await app.state.redis.aclose()
        print("app closed")


app = FastAPI(lifespan=lifespan)

@app.post("/callback")
async def callback(
    request: Request,
    x_line_signature: str = Header(...),
    r: Redis = Depends(redis_service.get_redis),
):
    # The signature is over the raw bytes, so read the body before parsing.
    body = (await request.body()).decode()
    await line.handle(body, x_line_signature, r)
    return "OK"

@app.get("/api/health")
async def health (r: Redis = Depends(redis_service.get_redis)):
    return {"status": "OK", "redis": await r.ping()}

@app.get("/api/playground")
async def playground(message : str):
    return await openai.get_playground(message)

@app.get("/api/chat_test")
async def chat_test(message: str,session_id: str = "devtest",r: Redis = Depends(redis_service.get_redis),):
    """Playground + Redis memory. Same session_id keeps the conversation."""
    return await ai.reply(r, session_id, message)
