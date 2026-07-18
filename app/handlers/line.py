"""LINE webhook: verify the signature, answer text messages with the AI."""

from fastapi import HTTPException
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from redis.asyncio import Redis

from app.config import LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET
from app.handlers import ai

parser = WebhookParser(LINE_CHANNEL_SECRET)
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)


def session_id(event: MessageEvent) -> str:
    """One memory per chat: a group/room shares it, a 1:1 chat is per user."""
    source = event.source
    return (
        getattr(source, "group_id", None)
        or getattr(source, "room_id", None)
        or source.user_id
    )


async def handle(body: str, signature: str, r: Redis) -> None:
    try:
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    async with AsyncApiClient(configuration) as api_client:
        line_api = AsyncMessagingApi(api_client)

        for event in events:
            if not isinstance(event, MessageEvent):
                continue
            if not isinstance(event.message, TextMessageContent):
                continue

            answer = await ai.reply(r, session_id(event), event.message.text)

            await line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=answer)],
                )
            )
