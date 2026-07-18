"""LINE webhook: verify the signature, unwrap events, hand them to the brain."""

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from redis.asyncio import Redis

from app.api.deps import get_redis
from app.clients import line as line_client
from app.core.config import LINE_CHANNEL_SECRET
from app.services import chat

router = APIRouter()

parser = WebhookParser(LINE_CHANNEL_SECRET)


def session_id(event: MessageEvent) -> str:
    """One memory per chat: a group/room shares it, a 1:1 chat is per user."""
    source = event.source
    return (
        getattr(source, "group_id", None)
        or getattr(source, "room_id", None)
        or source.user_id
    )


@router.post("/callback")
async def callback(
    request: Request,
    x_line_signature: str = Header(...),
    r: Redis = Depends(get_redis),
):
    # The signature is over the raw bytes, so read the body before parsing.
    body = (await request.body()).decode()

    try:
        events = parser.parse(body, x_line_signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        if not isinstance(event, MessageEvent):
            continue
        if not isinstance(event.message, TextMessageContent):
            continue

        answer = await chat.reply(r, session_id(event), event.message.text)
        await line_client.reply(event.reply_token, answer)

    return "OK"
