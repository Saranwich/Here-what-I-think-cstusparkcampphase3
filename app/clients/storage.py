"""ที่เก็บรายงานที่คุยจบแล้ว — ของถาวร ห้ามหาย

อยู่ใน Postgres + PostGIS ตารางอยู่ที่ `schema.sql` รากโปรเจกต์ รันมือครั้งเดียว
คนเรียกส่ง dict ธรรมดาเข้ามา ได้ id กลับไป ไม่ต้องรู้ว่าข้างล่างเป็นอะไร

geom มาจาก ST_MakePoint(longitude, latitude) — **longitude มาก่อน** ไม่ใช่ latitude
แถวที่ไม่มี geom จะไม่ขึ้นเป็นหมุดบนแผนที่ แต่ยังใช้นับสถิติได้ ทีมปักมือทีหลังได้
"""

import logging

import asyncpg

log = logging.getLogger(__name__)

# ช่องที่ลงตารางได้ ไล่ชื่อเองทีละช่อง **ห้ามยัด dict ทั้งก้อนเข้า INSERT**
#
# เพราะ _sanitize() ใน services/survey.py ปล่อยช่องที่ไม่รู้จักผ่านมาได้ (มันกรอง
# แค่ "ค่า" ที่นอกรายการ ไม่ได้กรอง "ชื่อช่อง") วันที่โมเดลกุชื่อช่องขึ้นมาเอง
# รายชื่อนี้คือด่านที่จับได้
COLUMNS = (
    "session_id",
    "source",
    "category",
    "notes",
    "title",
    "severity",
    "affect_desc",
    "affect_tags",
    "frequency",
    "time_of_day",
    "cause_said",
    "occurred_said",
    "location_text",
    "no_location",
    "no_photo",
)

# ช่องที่ไม่ได้ลงคอลัมน์ตรง ๆ แต่รู้จัก — พิกัดกลายเป็น geom รูปแยกไปอีกตาราง
_HANDLED = {"latitude", "longitude", "image_keys"}

_SELECT = ", ".join(("r.id", *(f"r.{name}" for name in COLUMNS), "r.created_at"))

_IMAGE_KEYS = """
    COALESCE(
        array_agg(i.image_key ORDER BY i.id) FILTER (WHERE i.image_key IS NOT NULL),
        '{}'
    ) AS image_keys
"""


async def save_report(pool: asyncpg.Pool, report: dict) -> int:
    """เก็บรายงาน 1 ใบพร้อมรูปของมัน คืน id กลับไป

    ใบกับรูปลงในธุรกรรมเดียวกัน — ได้ทั้งคู่หรือไม่ได้เลย ไม่มีใบที่รูปหลุดหาย
    """
    unknown = set(report) - set(COLUMNS) - _HANDLED
    if unknown:
        # ทิ้งเฉพาะช่องที่ไม่รู้จัก ไม่ทิ้งทั้งใบ — เรื่องที่ชาวบ้านเล่ามาสำคัญกว่า
        # ช่องที่โมเดลกุขึ้นมา แต่ต้องได้ยินเสียงมัน ไม่ใช่หายไปเงียบ ๆ
        log.warning("ช่องที่ไม่มีในตาราง ไม่ได้เก็บ: %s", sorted(unknown))

    names = [name for name in COLUMNS if name in report]
    values = [report[name] for name in names]

    columns = ", ".join(names)
    holders = ", ".join(f"${i}" for i in range(1, len(names) + 1))

    latitude = report.get("latitude")
    longitude = report.get("longitude")
    if latitude is not None and longitude is not None:
        columns += ", geom"
        holders += f", ST_MakePoint(${len(names) + 1}, ${len(names) + 2})::geography"
        values += [longitude, latitude]

    async with pool.acquire() as conn, conn.transaction():
        report_id = await conn.fetchval(
            f"INSERT INTO reports ({columns}) VALUES ({holders}) RETURNING id",
            *values,
        )
        for image_key in report.get("image_keys") or []:
            await conn.execute(
                "INSERT INTO report_images (report_id, image_key) VALUES ($1, $2)",
                report_id,
                image_key,
            )

    return report_id


async def list_reports(pool: asyncpg.Pool) -> list[dict]:
    """อ่านทั้งหมด — ไว้ส่องตอน dev ของจริงคงมี filter ทีหลัง"""
    rows = await pool.fetch(f"""
        SELECT {_SELECT},
               ST_Y(r.geom::geometry) AS latitude,
               ST_X(r.geom::geometry) AS longitude,
               {_IMAGE_KEYS}
          FROM reports r
          LEFT JOIN report_images i ON i.report_id = r.id
      GROUP BY r.id
      ORDER BY r.id
    """)
    return [dict(row) for row in rows]


async def last_location(pool: asyncpg.Pool, session_id: str) -> dict | None:
    """ตำแหน่งล่าสุดที่คนนี้เคยแจ้งไว้ คืน None ถ้าไม่เคยมี

    ถามจากที่เก็บหลัก ไม่เอาไปกองไว้ใน Redis เพราะ Redis อยู่บน RAM
    คนใช้เยอะ ๆ แล้วจะบวม ส่วนตรงนี้ index reports_session_idx ตอบให้อยู่แล้ว
    """
    row = await pool.fetchrow(
        """
        SELECT ST_Y(geom::geometry) AS latitude,
               ST_X(geom::geometry) AS longitude,
               location_text
          FROM reports
         WHERE session_id = $1 AND geom IS NOT NULL
      ORDER BY created_at DESC
         LIMIT 1
        """,
        session_id,
    )
    return dict(row) if row else None
