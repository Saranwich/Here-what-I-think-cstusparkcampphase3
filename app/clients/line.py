"""ส่งข้อความกลับ LINE

นาฬิกา 2 เรือนที่ต้องจำ (ดู local/plan.md)
  2 วินาที  = ต้องตอบ 200 กลับ LINE ให้ทัน — เรื่องนั้นจัดการที่ api/line.py
  1 นาที    = อายุ reply token ทันใช้ reply (ฟรี) ไม่ทันต้อง push (กินโควตา)
"""

import logging

from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    AsyncMessagingApiBlob,
    Configuration,
    LocationAction,
    PushMessageRequest,
    QuickReply,
    QuickReplyItem,
    ReplyMessageRequest,
    ShowLoadingAnimationRequest,
    TextMessage,
)

from app.core.config import LINE_CHANNEL_ACCESS_TOKEN

log = logging.getLogger(__name__)

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)

# ปุ่มแชร์ตำแหน่ง โผล่ตอนบอทกำลังถามหาตำแหน่ง กดง่ายกว่าพิมพ์เยอะ
_LOCATION_BUTTON = QuickReply(
    items=[QuickReplyItem(action=LocationAction(label="ส่งตำแหน่ง"))]
)


def _message(text: str, ask_location: bool) -> TextMessage:
    return TextMessage(
        text=text,
        quickReply=_LOCATION_BUTTON if ask_location else None,
    )


async def reply(reply_token: str, text: str, ask_location: bool = False) -> None:
    async with AsyncApiClient(configuration) as api_client:
        await AsyncMessagingApi(api_client).reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[_message(text, ask_location)],
            )
        )


async def push(to: str, text: str, ask_location: bool = False) -> None:
    """ใช้ตอน reply token หมดอายุแล้ว — อันนี้กินโควตารายเดือนของ OA"""
    async with AsyncApiClient(configuration) as api_client:
        await AsyncMessagingApi(api_client).push_message(
            PushMessageRequest(
                to=to,
                messages=[_message(text, ask_location)],
            )
        )


async def send(
    reply_token: str, to: str, text: str, ask_location: bool = False
) -> None:
    """ลอง reply ก่อนเพราะฟรี ไม่ได้ค่อย push

    reply พังได้หลายทาง (token หมดอายุ / ถูกใช้ไปแล้ว) ซึ่งเรารู้ตอนยิงเท่านั้น
    เลยดักตรงนี้แล้วเปลี่ยนไปใช้ push แทน ดีกว่าเงียบหายไปเฉย ๆ
    """
    try:
        await reply(reply_token, text, ask_location)
    except Exception:
        log.warning("reply ไม่สำเร็จ เปลี่ยนไปใช้ push", exc_info=True)
        await push(to, text, ask_location)


async def download_image(message_id: str) -> bytes:
    """โหลดรูปที่ชาวบ้านส่งมา — LINE เก็บไว้ให้ชั่วคราว ต้องรีบมาเอา"""
    async with AsyncApiClient(configuration) as api_client:
        return await AsyncMessagingApiBlob(api_client).get_message_content(message_id)


async def show_loading(chat_id: str, seconds: int = 20) -> None:
    """จุดสามจุดกระพริบระหว่างรอ AI คิด — ได้เฉพาะแชท 1:1 กลุ่มใช้ไม่ได้

    ล้มเหลวได้โดยไม่เป็นไร มันเป็นแค่ของประดับ ห้ามทำให้ข้อความจริงไม่ถูกส่ง
    """
    try:
        async with AsyncApiClient(configuration) as api_client:
            await AsyncMessagingApi(api_client).show_loading_animation(
                ShowLoadingAnimationRequest(chatId=chat_id, loadingSeconds=seconds)
            )
    except Exception:
        log.debug("แสดง loading ไม่ได้ ข้ามไป", exc_info=True)
