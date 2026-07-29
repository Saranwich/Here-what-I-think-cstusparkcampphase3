"""รูปที่ชาวบ้านส่งมา

**รูปไม่เข้าโมเดล** — เปลืองและเสี่ยงข้อมูลส่วนตัวหลุด เราแค่เก็บไฟล์ไว้
แล้วบอก AI ว่า "มีรูปมาแล้วนะ" เป็นข้อความ marker เท่านั้น
คนที่ดูรูปจริงคือทีมออกแบบตอนเปิดแดชบอร์ด

ตอนนี้ลงไฟล์ใน local/ ของจริงจะขึ้น S3 — วันย้ายแก้แค่ในไฟล์นี้

    s3://<bucket>/images/YYYY/MM/<message_id>.jpg
"""

from datetime import datetime, timezone
from pathlib import Path

from app.core.config import BASE_DIR

STORE_DIR = BASE_DIR / "local"


async def save(message_id: str, content: bytes) -> str:
    """เก็บรูป 1 ใบ คืน key ที่เก็บไว้ (ทีหลังจะเป็น S3 key)

    key ต่อท้าย STORE_DIR แล้วได้ path ของไฟล์เลย ไม่มีกฎแปลงชื่ออะไรคั่นกลาง
    ที่ต้องเป็นแบบนี้เพราะสิ่งที่ลง DB คือ key ล้วน ๆ วันเปิดแดชบอร์ดต้องหาไฟล์
    เจอจาก key อย่างเดียว
    """
    now = datetime.now(timezone.utc)
    key = f"images/{now:%Y/%m}/{message_id}.jpg"

    path = STORE_DIR / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)

    return key


def local_file(key: str) -> Path | None:
    """key -> ไฟล์บนเครื่อง คืน None ถ้าไม่มีไฟล์นั้น

    **ที่เดียวในโปรเจกต์ที่แปลง key เป็น path ได้** วันย้ายขึ้น S3 ฟังก์ชันนี้
    จะกลายเป็นตัวดึงจาก bucket แทน คนเรียกไม่ต้องรู้ว่าไฟล์ไปนอนอยู่ที่ไหนแล้ว
    """
    path = (STORE_DIR / key).resolve()
    if not path.is_relative_to(STORE_DIR.resolve()):
        # key มาจากฐานข้อมูลของเราเอง ไม่ควรมีทางหลุดออกนอกโฟลเดอร์
        # แต่ตรงนี้เป็นทางที่ยิงไฟล์ออกไปข้างนอก ไม่ควรเชื่อใครทั้งนั้น
        return None
    return path if path.is_file() else None
