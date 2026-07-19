import json

from openai import AsyncOpenAI
from app.core.config import OPENAI_API_ENDPOINT, API_KEY

client = AsyncOpenAI(
    api_key=API_KEY,
    base_url=OPENAI_API_ENDPOINT
    )

async def get_playground(message: str) -> str:

    completion = await client.chat.completions.create(

        model="qwen3.8-max-preview", #กำหนดชื่อ model แนะนำให้ใช้ qwen3.8-max-preview

        messages=[
        {"role": "user", "content": message} #กำหนด prompt
        ],

        extra_body={
            "reasoning_effort": "high",  #กำหนด effort ของโมเดล แนะนำให้ใช้เป็น "high"
        }

    )

    return completion.choices[0].message.content


async def chat(messages: list[dict]) -> str:
    """Same model as the playground, but takes a full message history."""

    completion = await client.chat.completions.create(
        model="qwen3.8-max-preview",
        messages=messages,
        extra_body={
            "reasoning_effort": "high",
        },
    )

    return completion.choices[0].message.content


async def chat_tools(messages: list[dict], tools: list[dict]) -> dict:
    """Chat, letting the model call our tools.

    Returns a plain dict so nothing outside this file has to know what an
    OpenAI object looks like:

        {"content": "...", "tool_calls": [{"id", "name", "arguments": {...}}]}
    """

    completion = await client.chat.completions.create(
        model="qwen3.8-max-preview",
        messages=messages,
        tools=tools,
        extra_body={
            "reasoning_effort": "high",
        },
    )

    message = completion.choices[0].message
    return {
        "content": message.content or "",
        "tool_calls": [
            {
                "id": call.id,
                "name": call.function.name,
                "arguments": json.loads(call.function.arguments or "{}"),
            }
            for call in (message.tool_calls or [])
        ],
    }


def tool_exchange(tool_calls: list[dict], result: str) -> list[dict]:
    """The two messages the model expects back after it called a tool:
    what it asked for, and what it got. Same `result` for every call."""

    asked = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call["id"],
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                },
            }
            for call in tool_calls
        ],
    }
    got = [
        {"role": "tool", "tool_call_id": call["id"], "content": result}
        for call in tool_calls
    ]
    return [asked] + got