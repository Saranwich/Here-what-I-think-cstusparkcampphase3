"""บทสนทนาต้นฉบับ — ของดิบที่ AI สกัดมาเป็นรายงาน

ทำไมต้องเก็บ: รายงานที่ลง DB คือสิ่งที่ AI *สรุป* ให้ ถ้าวันหลังเราปรับวิธีสกัด
หรืออยากได้ช่องใหม่ย้อนหลัง ต้องมีต้นฉบับให้สกัดใหม่ ไม่งั้นข้อมูลที่เก็บไปแล้ว
กู้คืนไม่ได้ถาวร

ตอนนี้เขียนลงไฟล์ใน local/ ของจริงจะขึ้น S3 — วันย้ายแก้แค่ในไฟล์นี้

    s3://<bucket>/transcripts/YYYY/MM/<report_id>.json

(save เป็น async ตั้งแต่ตอนนี้ เพราะ boto3/aioboto3 เป็น I/O จริง คนเรียกจะได้ไม่ต้องแก้)
"""

import json
from datetime import datetime, timezone

from app.core.config import BASE_DIR

TRANSCRIPT_DIR = BASE_DIR / "local" / "transcripts"


async def save(session_id: str, report_id: int, messages: list[dict]) -> str:
    """เก็บบทสนทนา 1 ชุด คืน key ที่เก็บไว้ (ทีหลังจะเป็น S3 key)"""
    now = datetime.now(timezone.utc)
    key = f"transcripts/{now:%Y/%m}/{report_id}.json"

    path = TRANSCRIPT_DIR / f"{now:%Y-%m}" / f"{report_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(
            {
                "report_id": report_id,
                "session_id": session_id,
                "saved_at": now.isoformat(),
                "messages": messages,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return key
