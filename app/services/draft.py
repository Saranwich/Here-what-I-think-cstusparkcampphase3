"""ใบรายงานที่ยังกรอกไม่เสร็จ — 1 session ต่อ 1 ใบ

Redis Hash: key เดียว `survey:{session_id}` แต่ข้างในมีช่องย่อยหลายช่อง
    survey:U_alice
        incident_type  "flood"
        location_text  "หลังวัดโพธิ์"

ของชั่วคราว หายได้ ตั้ง TTL ไว้เหมือน chat memory
พอกรอกครบค่อยย้ายไปนอนที่ clients/storage.py ซึ่งเป็นของถาวร
"""

import json

from redis.asyncio import Redis

TTL_SECONDS = 60 * 60
DONE_TTL_SECONDS = 30 * 60   # หลังปิดใบ จำไว้ครึ่งชั่วโมงว่าเพิ่งคุยจบไป

# ทุกอย่างในไฟล์นี้เป็นของชั่วคราวที่หายได้ และมี TTL เสมอ
# ของที่ต้องอยู่ยาวห้ามมาไว้ตรงนี้ Redis อยู่บน RAM เดี๋ยวบวม


def _key(session_id: str) -> str:
    return f"survey:{session_id}"


def _done_key(session_id: str) -> str:
    return f"survey:{session_id}:done"


async def load(r: Redis, session_id: str) -> dict:
    raw = await r.hgetall(_key(session_id))
    return {field: json.loads(value) for field, value in raw.items()}


async def merge(r: Redis, session_id: str, fields: dict) -> None:
    """เติมเฉพาะช่องที่มีค่าจริง — AI ส่ง null มาต้องไม่ไปลบของเดิม"""
    filled = {
        field: json.dumps(value, ensure_ascii=False)
        for field, value in fields.items()
        if value not in (None, "")
    }
    if not filled:
        return

    key = _key(session_id)
    async with r.pipeline() as pipe:
        pipe.hset(key, mapping=filled)
        pipe.expire(key, TTL_SECONDS)
        await pipe.execute()


async def clear(r: Redis, session_id: str) -> None:
    await r.delete(_key(session_id))


# ---- ป้ายเล็ก ๆ ว่า "เพิ่งคุยจบไป" --------------------------------------
# กันไม่ให้พิมพ์ "ครับ" ท้ายบทแล้วบอทเปิดใบใหม่ทันทีแล้วเริ่มสัมภาษณ์ใหม่


async def mark_done(r: Redis, session_id: str, report_id: int) -> None:
    await r.set(_done_key(session_id), report_id, ex=DONE_TTL_SECONDS)


async def just_finished(r: Redis, session_id: str) -> bool:
    return await r.exists(_done_key(session_id)) == 1


async def clear_done(r: Redis, session_id: str) -> None:
    await r.delete(_done_key(session_id))
