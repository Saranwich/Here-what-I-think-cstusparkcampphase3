"""LINE webhook: เช็คลายเซ็น แกะกล่อง แล้วโยนงานให้สมอง

**ต้องตอบ 200 กลับ LINE ภายใน 2 วินาที** ไม่งั้นนับเป็น error ฝั่ง LINE
AI คิดนานกว่านั้นแน่ เลยตอบ 200 ทันทีแล้วให้ BackgroundTasks ไปคุยต่อเบื้องหลัง
(reply token ยังมีอายุ 1 นาที ทันสบาย)

ไฟล์นี้คือที่เดียวที่รู้จักกล่องของ LINE — งานแกะทั้งหมดจบตรงนี้
สมองข้างในรับแค่ str กับตัวเลข
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import (
    ImageMessageContent,
    LocationMessageContent,
    MessageEvent,
    TextMessageContent,
)
from redis.asyncio import Redis

from app.api.deps import get_redis
from app.clients import line as line_client
from app.clients import media
from app.core.config import LINE_CHANNEL_SECRET
from app.services import survey

router = APIRouter()

parser = WebhookParser(LINE_CHANNEL_SECRET)


def session_id(event: MessageEvent) -> str:
    """หนึ่งใบต่อหนึ่งห้องแชท — กลุ่มใช้ร่วมกัน แชทเดี่ยวแยกตามคน"""
    source = event.source
    return (
        getattr(source, "group_id", None)
        or getattr(source, "room_id", None)
        or source.user_id
    )


def is_direct(event: MessageEvent) -> bool:
    """แชท 1:1 หรือเปล่า — loading animation ใช้ได้เฉพาะแบบนี้"""
    return getattr(event.source, "group_id", None) is None and (
        getattr(event.source, "room_id", None) is None
    )


def unwrap(event: MessageEvent) -> dict | None:
    """แกะกล่องเป็นของธรรมดา คืน None ถ้าเป็นชนิดที่เรายังไม่รับ (สติกเกอร์ เสียง วิดีโอ)"""
    message = event.message

    if isinstance(message, TextMessageContent):
        return {"said": message.text}

    if isinstance(message, LocationMessageContent):
        # พิกัดไม่เข้าโมเดลตรง ๆ ข้างในจะแปลงเป็น marker ให้เอง
        # ชื่อสถานที่เอาจาก LINE เลย เชื่อถือได้กว่าให้โมเดลสรุปเอง
        return {
            "said": "ส่งตำแหน่งมาให้แล้ว",
            "latitude": message.latitude,
            "longitude": message.longitude,
            "location_text": message.address or message.title,
        }

    if isinstance(message, ImageMessageContent):
        # ตัวรูปยังไม่โหลดตรงนี้ เพราะต้องรีบตอบ 200 ให้ทัน 2 วิ ไปโหลดเบื้องหลัง
        return {"said": "ส่งรูปมาให้", "image_id": message.id}

    return None


@router.post("/callback")
async def callback(
    request: Request,
    background_tasks: BackgroundTasks,
    x_line_signature: str = Header(...),
    r: Redis = Depends(get_redis),
):
    # ลายเซ็นคิดจาก body ดิบ ต้องอ่านก่อนแปลง
    body = (await request.body()).decode()

    try:
        events = parser.parse(body, x_line_signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        if not isinstance(event, MessageEvent):
            continue

        unwrapped = unwrap(event)
        if unwrapped is None:
            continue

        background_tasks.add_task(
            answer,
            r,
            session_id(event),
            event.reply_token,
            is_direct(event),
            unwrapped,
        )

    # ตอบทันที ห้ามรอ AI
    return "OK"


async def answer(
    r: Redis,
    session: str,
    reply_token: str,
    direct: bool,
    incoming: dict,
) -> None:
    """ทำงานหลังตอบ 200 ไปแล้ว — ตรงนี้ช้าได้"""
    if direct:
        await line_client.show_loading(session)

    image_key = None
    if image_id := incoming.get("image_id"):
        # LINE เก็บรูปให้ชั่วคราว ต้องรีบมาเอาก่อนหมดอายุ
        content = await line_client.download_image(image_id)
        image_key = await media.save(image_id, content)

    result = await survey.reply(
        r,
        session,
        incoming["said"],
        latitude=incoming.get("latitude"),
        longitude=incoming.get("longitude"),
        location_text=incoming.get("location_text"),
        image_key=image_key,
    )

    await line_client.send(
        reply_token,
        session,
        result["reply"],
        ask_location=result["asking_location"],
        ask_photo=result["asking_photo"],
    )
