"""ใบรายงานที่ยังกรอกไม่เสร็จ — 1 session มีได้หลายใบ แยกกันด้วยชื่อเรื่อง

Redis Hash: key เดียว `survey:{session_id}` ช่องย่อยหนึ่งช่อง = หนึ่งใบ
    survey:U_alice
        "น้ำท่วมซอย 5"   {"category": "flood", "notes": "...", "_seq": 0}
        "หมาจรจัด"        {"category": "other", "notes": "...", "_seq": 1}

ที่เลือกยัดทั้งใบเป็น JSON ในช่องเดียว แทนที่จะแตกเป็นคนละ key
เพราะ TTL ผูกกับ key ไม่ได้ผูกกับช่อง — key เดียวจึงหมดอายุพร้อมกันทั้งชุด
ไม่มีใบไหนค้างเป็นขยะอยู่คนเดียวหลังบทสนทนาจบ

`_seq` คือลำดับที่ใบนั้นถูกเปิด ไว้ให้คนเรียกรู้ว่าเรื่องไหนมาก่อน

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


async def load_all(r: Redis, session_id: str) -> dict[str, dict]:
    """ทุกใบที่ยังเปิดอยู่ของ session นี้ — {ชื่อเรื่อง: ใบ}"""
    raw = await r.hgetall(_key(session_id))
    return {topic: json.loads(value) for topic, value in raw.items()}


async def load(r: Redis, session_id: str, topic: str) -> dict:
    raw = await r.hget(_key(session_id), topic)
    return json.loads(raw) if raw else {}


async def merge(r: Redis, session_id: str, topic: str, fields: dict) -> None:
    """เติมเฉพาะช่องที่มีค่าจริง — AI ส่ง null มาต้องไม่ไปลบของเดิม

    ใบใหม่จะได้ `_seq` ต่อจากใบที่มากที่สุดในตอนนั้น ไม่ใช่จำนวนใบที่มีอยู่
    เพราะพอปิดใบไปแล้วจำนวนจะลดลง แล้วใบใหม่จะได้เลขซ้ำกับใบที่ยังเปิดอยู่
    """
    filled = {
        field: value
        for field, value in fields.items()
        if value not in (None, "")
    }
    if not filled:
        return

    key = _key(session_id)
    current = await load_all(r, session_id)
    report = current.get(topic)

    if report is None:
        seq = max((rep.get("_seq", 0) for rep in current.values()), default=-1) + 1
        report = {"_seq": seq}

    report.update(filled)

    async with r.pipeline() as pipe:
        pipe.hset(key, topic, json.dumps(report, ensure_ascii=False))
        pipe.expire(key, TTL_SECONDS)
        await pipe.execute()


async def drop(r: Redis, session_id: str, topic: str, fields: list[str]) -> None:
    """เอาบางช่องออกจากใบ — ใช้ตอนชาวบ้านบอกว่าตำแหน่งที่ส่งมาผิดจุด

    merge เติมได้อย่างเดียวโดยตั้งใจ (กัน AI ส่ง null มาลบของเดิม)
    การลบจึงต้องเป็นคำสั่งแยกที่โค้ดเราตั้งใจเรียกเท่านั้น
    """
    report = await load(r, session_id, topic)
    if not report:
        return

    for field in fields:
        report.pop(field, None)

    key = _key(session_id)
    async with r.pipeline() as pipe:
        pipe.hset(key, topic, json.dumps(report, ensure_ascii=False))
        pipe.expire(key, TTL_SECONDS)
        await pipe.execute()


async def remove(r: Redis, session_id: str, topic: str) -> None:
    """เอาใบนั้นออกไปทั้งใบ — ใช้ตอนใบครบแล้วและย้ายไปที่เก็บถาวรเรียบร้อย"""
    await r.hdel(_key(session_id), topic)


async def clear(r: Redis, session_id: str) -> None:
    await r.delete(_key(session_id))


# ---- ป้ายเล็ก ๆ ว่า "เพิ่งคุยจบไป" --------------------------------------
# กันไม่ให้พิมพ์ "ครับ" ท้ายบทแล้วบอทเปิดใบใหม่ทันทีแล้วเริ่มสัมภาษณ์ใหม่


async def mark_done(r: Redis, session_id: str, report_id: int) -> None:
    await r.set(_done_key(session_id), report_id, ex=DONE_TTL_SECONDS)


async def just_finished(r: Redis, session_id: str) -> bool:
    return await r.exists(_done_key(session_id)) == 1


async def finished_id(r: Redis, session_id: str) -> int | None:
    """เลขใบที่เพิ่งปิดไป คืน None ถ้าไม่มี — ของที่ตามมาทีหลังจะได้ตามไปเกาะถูกใบ"""
    value = await r.get(_done_key(session_id))
    return int(value) if value is not None else None


async def clear_done(r: Redis, session_id: str) -> None:
    await r.delete(_done_key(session_id))
