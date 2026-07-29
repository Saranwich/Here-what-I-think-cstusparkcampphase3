"""Connection pool to Postgres. Knows nothing about what gets stored in it.

ตารางอยู่ใน schema.sql ที่รากโปรเจกต์ รันมือ ไม่ได้สร้างให้ตอนเปิดแอป
"""

import asyncpg

from app.core.config import DATABASE_URL


async def create_pool() -> asyncpg.Pool:
    """ต่อครั้งเดียวตอนเปิดแอป แล้วส่งต่อผ่าน Depends(get_db)

    คนใช้พร้อมกันไม่กี่คน 5 สายพอเหลือเฟือ ตั้งไว้เองเพราะ default ของ asyncpg
    คือ 10 สายค้างไว้ตลอด ซึ่งเปลืองเปล่า ๆ กับงานขนาดนี้
    """
    return await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
