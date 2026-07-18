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