from openai import OpenAI
from app.core.config import OPENAI_API_ENDPOINT, API_KEY

client = OpenAI(
    api_key=API_KEY,
    base_url=OPENAI_API_ENDPOINT
    )

completion = client.chat.completions.create(
    model="qwen3.8-max-preview", #กำหนดชื่อ model แนะนำให้ใช้ qwen3.8-max-preview
    messages=[ 
        {"role": "user", "content": "Hello! Tell me a fun fact about AI."} #กำหนด prompt
    ],

    extra_body={
        "reasoning_effort": "high",  #กำหนด effort ของโมเดล แนะนำให้ใช้เป็น "high"
    }

)

print(completion.choices[0].message.content)