from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import dev, line
from app.clients import redis as redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    app.state.redis = redis_client.create_client()
    await app.state.redis.ping()
    print("app opened")
    try:
        yield
    finally:
        # --- shutdown ---
        await app.state.redis.aclose()
        print("app closed")


app = FastAPI(lifespan=lifespan)

app.include_router(line.router)
app.include_router(dev.router)
