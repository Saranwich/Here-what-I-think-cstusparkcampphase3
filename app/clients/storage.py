"""ที่เก็บรายงานที่คุยจบแล้ว — ของถาวร ห้ามหาย

ตอนนี้เขียนลงไฟล์ .jsonl บรรทัดละ 1 รายงาน เอาไว้ให้รอดก่อน
วันที่ย้ายไป Postgres + PostGIS จะแก้แค่ในไฟล์นี้ไฟล์เดียว คนเรียกไม่ต้องรู้เรื่อง
(เพราะงั้น save_report ถึงเป็น async ทั้งที่ตอนนี้ยังไม่ต้อง)

    CREATE EXTENSION IF NOT EXISTS postgis;

    CREATE TABLE reports (
        id            bigserial PRIMARY KEY,
        session_id    text        NOT NULL,
        source        text        NOT NULL DEFAULT 'user',   -- user | broadcast
        category      text        NOT NULL,                  -- heat|flood|access|other
        notes         text        NOT NULL,
        severity      text,                                  -- low|medium|high (AI จัดให้)
        title         text,                                  -- พาดหัวบนหมุด
        geom          geography(Point, 4326),                -- latitude/longitude ลงตรงนี้
        location_text text,                                  -- ตอนแชร์ตำแหน่งไม่ได้
        image_keys    text[],                                -- key ของรูปบน S3
        created_at    timestamptz NOT NULL DEFAULT now()
    );

    CREATE INDEX reports_geom_idx ON reports USING GIST (geom);
    CREATE INDEX reports_session_idx ON reports (session_id, created_at DESC);

geom มาจาก ST_MakePoint(longitude, latitude) — longitude มาก่อน ไม่ใช่ latitude
แถวที่ไม่มี geom จะไม่ขึ้นเป็นหมุดบนแผนที่ แต่ยังใช้นับสถิติได้
"""

import json
from datetime import datetime, timezone

from app.core.config import BASE_DIR

REPORTS_FILE = BASE_DIR / "local" / "reports.jsonl"


async def save_report(report: dict) -> int:
    """เก็บรายงาน 1 ใบ คืน id กลับไป (แทน bigserial ของ Postgres)"""
    REPORTS_FILE.parent.mkdir(exist_ok=True)

    row = {
        "id": _next_id(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        **report,
    }

    with REPORTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return row["id"]


async def list_reports() -> list[dict]:
    """อ่านทั้งหมด — ไว้ส่องตอน dev ของจริงคงมี filter ทีหลัง"""
    if not REPORTS_FILE.exists():
        return []
    with REPORTS_FILE.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


async def last_location(session_id: str) -> dict | None:
    """ตำแหน่งล่าสุดที่คนนี้เคยแจ้งไว้ คืน None ถ้าไม่เคยมี

    ถามจากที่เก็บหลัก ไม่เอาไปกองไว้ใน Redis เพราะ Redis อยู่บน RAM
    คนใช้เยอะ ๆ แล้วจะบวม ส่วนตรงนี้ Postgres ตอบได้อยู่แล้วด้วย index

        SELECT ST_Y(geom::geometry) AS latitude,
               ST_X(geom::geometry) AS longitude,
               location_text
          FROM reports
         WHERE session_id = $1 AND geom IS NOT NULL
         ORDER BY created_at DESC
         LIMIT 1;
    """
    for row in reversed(await list_reports()):
        if row.get("session_id") != session_id:
            continue
        if row.get("latitude") is None or row.get("longitude") is None:
            continue
        return {
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "location_text": row.get("location_text"),
        }
    return None


def _next_id() -> int:
    if not REPORTS_FILE.exists():
        return 1
    with REPORTS_FILE.open(encoding="utf-8") as f:
        return sum(1 for line in f if line.strip()) + 1
