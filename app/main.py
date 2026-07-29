import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import dev, line
from app.clients import redis as redis_client
from app.services import sweeper


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    app.state.redis = redis_client.create_client()
    await app.state.redis.ping()
    # ตาข่ายรองรับ เก็บใบที่ใกล้หมดอายุก่อนหาย — ดูเหตุผลใน services/sweeper.py
    sweep = asyncio.create_task(sweeper.run_forever(app.state.redis))
    print("app opened")
    try:
        yield
    finally:
        # --- shutdown ---
        sweep.cancel()
        await app.state.redis.aclose()
        print("app closed")


app = FastAPI(lifespan=lifespan)

app.include_router(line.router)
app.include_router(dev.router)
