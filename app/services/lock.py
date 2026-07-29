"""หนึ่งบทสนทนา ทำได้ทีละตา ตาที่มาทีหลังต่อคิวรอ

ทำไมต้องมี: ช่องทางแชทยิงเข้ามาแยกกันทุกข้อความ ส่งรูปรวด 3 ใบ = งาน 3 ชิ้น
วิ่งพร้อมกันบนบทสนทนาเดียวกัน ทั้งสามอ่านใบเจอว่า "ครบแล้ว" ในเวลาไล่เลี่ยกัน
เพราะยังไม่มีใครลบใบทิ้ง แล้วต่างคนต่างเก็บลงที่เก็บถาวร

**เจอของจริงแล้ว 29 ก.ค.** ส่งรูป 3 ใบรวด ได้รายงาน 2 ใบที่เป็นเรื่องเดียวกัน
หมุดซ้อนกันบนแผนที่ รูปชุดเดียวถูกผูกซ้ำสองรอบ และความจำโดนล้างสองครั้ง
บทสนทนาก่อนหน้าหายไปด้วย

lock อยู่ใน Redis ไม่ได้อยู่ในหน่วยความจำของ process — ขึ้นหลาย process
เมื่อไหร่ก็ยังกันได้เหมือนเดิม
"""

import logging
from contextlib import asynccontextmanager

from redis.asyncio import Redis
from redis.exceptions import LockError

log = logging.getLogger(__name__)

HOLD_SECONDS = 90   # ถือได้นานสุดเท่านี้ เผื่อ process ตายคาไว้ lock จะได้ไม่ค้างตลอดกาล
WAIT_SECONDS = 45   # รอคิวได้นานสุดเท่านี้ นานกว่านี้ token ตอบกลับก็หมดอายุพอดี


class Busy(Exception):
    """บทสนทนานี้มีตาอื่นทำอยู่ และรอไม่ไหวแล้ว"""


def _key(session_id: str) -> str:
    return f"turn:{session_id}"


@asynccontextmanager
async def one_at_a_time(r: Redis, session_id: str, wait: float = WAIT_SECONDS):
    """กันไม่ให้บทสนทนาเดียวกันถูกประมวลผลซ้อนกัน

    `wait=0` = ลองครั้งเดียว ไม่ว่างก็ยอมแพ้ทันที (ใช้กับงานเบื้องหลังที่รอได้
    ไม่ต้องรีบ ปล่อยให้เจ้าของตาจัดการไป แล้วค่อยมาใหม่รอบหน้า)
    """
    lock = r.lock(_key(session_id), timeout=HOLD_SECONDS, blocking_timeout=wait)

    if not await lock.acquire():
        raise Busy(session_id)

    try:
        yield
    finally:
        try:
            await lock.release()
        except LockError:
            # ถือเกิน HOLD_SECONDS จน lock หมดอายุไปเอง แปลว่าตานี้ช้าผิดปกติ
            # และอาจมีตาอื่นเข้ามาทับไปแล้ว ต้องรู้ ไม่ใช่ปล่อยผ่าน
            log.warning("ตานี้ใช้เวลานานเกิน lock หมดอายุก่อน session=%s", session_id)
