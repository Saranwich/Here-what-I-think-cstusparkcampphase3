"""หน้าแผนที่ให้ทีมออกแบบเปิดดู — อ่านอย่างเดียว ไม่มีอะไรเขียนกลับ

หน้าเว็บเป็นไฟล์เดียวใน static/ ที่ไปเรียก /api/dashboard/reports เอาเอง
ไฟล์นี้จึงมีแค่ 3 ทาง: หน้าเว็บ, ข้อมูล, และรูป
"""

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.deps import get_db
from app.clients import media, storage
from app.core.config import BASE_DIR

router = APIRouter()

PAGE = BASE_DIR / "app" / "static" / "dashboard.html"


@router.get("/dashboard")
async def page() -> FileResponse:
    return FileResponse(PAGE)


@router.get("/api/dashboard/reports")
async def reports(pool: asyncpg.Pool = Depends(get_db)) -> list[dict]:
    """ทุกใบที่เก็บไว้ พร้อมพิกัดและรายการรูป

    ส่งใบที่ไม่มีพิกัดมาด้วย **ตั้งใจ** — ใบพวกนั้นปักหมุดเองไม่ได้ ต้องให้ทีม
    มาปักมือทีหลัง ถ้ากรองทิ้งตรงนี้มันจะหายไปจากสายตาทุกคนตลอดกาล
    """
    return await storage.list_reports(pool)


@router.get("/api/dashboard/image/{image_id}")
async def image(image_id: int, pool: asyncpg.Pool = Depends(get_db)) -> FileResponse:
    """รูปของใบนั้น อ้างด้วย id ของรูป ไม่ใช่ path — ข้างนอกไม่ต้องรู้ว่าไฟล์อยู่ไหน"""
    key = await storage.image_key(pool, image_id)
    if key is None:
        raise HTTPException(status_code=404, detail="ไม่มีรูปนี้")

    path = media.local_file(key)
    if path is None:
        # แถวมีแต่ไฟล์หาย — เกิดได้ถ้าย้ายเครื่องแล้วสำรองมาแต่ฐานข้อมูล
        raise HTTPException(status_code=404, detail="มีรูปในระบบแต่หาไฟล์ไม่เจอ")

    return FileResponse(path, media_type="image/jpeg")
