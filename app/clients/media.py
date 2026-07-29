"""รูปที่ชาวบ้านส่งมา

**รูปไม่เข้าโมเดล** — เปลืองและเสี่ยงข้อมูลส่วนตัวหลุด เราแค่เก็บไฟล์ไว้
แล้วบอก AI ว่า "มีรูปมาแล้วนะ" เป็นข้อความ marker เท่านั้น
คนที่ดูรูปจริงคือทีมออกแบบตอนเปิดแดชบอร์ด

ตอนนี้ลงไฟล์ใน local/ ของจริงจะขึ้น S3 — วันย้ายแก้แค่ในไฟล์นี้

    s3://<bucket>/images/YYYY/MM/<message_id>.jpg
"""

from datetime import datetime, timezone

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
