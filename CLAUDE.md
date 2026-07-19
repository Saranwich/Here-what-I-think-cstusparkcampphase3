# กฎของโปรเจกต์นี้

อ่านก่อนเขียนโค้ด ใช้ทั้งกับคนและกับ AI

## โครงสร้าง

```
app/
  main.py              สร้าง app + lifespan + ต่อ router เท่านั้น
  core/config.py       อ่านค่าจาก .env
  api/                 route — ชั้นเดียวที่รู้จัก FastAPI
  services/            ตรรกะของเรา (สมอง)
  clients/             คุยกับของนอกบ้าน (Redis, AI, LINE)
```

## กฎ

**1. ลูกศรวิ่งทางเดียว — ห้ามย้อน**

```
api/ → services/ → clients/
```

`services/` และ `clients/` ห้าม import อะไรจาก `api/`
`clients/` ห้าม import อะไรจาก `services/`

**2. มีแต่ `api/` ที่รู้จัก FastAPI**

ถ้าเปิดไฟล์ใน `services/` หรือ `clients/` แล้วเจอคำว่า `fastapi`, `Request`, `Depends` แปลว่าวางผิดที่

`Depends` ทุกตัวอยู่ใน `api/deps.py`

**3. `services/` ห้ามรู้จัก LINE**

`services/` รับ-ส่งแค่ `str` และ `dict` ธรรมดา ห้ามมีคำว่า `linebot`, `reply_token`, `event`
งานแกะกล่องของ LINE อยู่ใน `api/line.py` งานยิงกลับอยู่ใน `clients/line.py`

เหตุผล: วันหลังเพิ่ม Discord หรือเว็บ จะได้เพิ่มแค่ไฟล์ใน `api/` โดยไม่ต้องแตะสมอง

**4. `main.py` ห้ามมี route**

มีได้แค่ lifespan กับ `include_router`

**5. ตั้งชื่อไฟล์ตามหน้าที่ ไม่ใช่ตามยี่ห้อ**

`llm.py` ไม่ใช่ `openai.py` — วันหลังเปลี่ยนเจ้าจะได้ไม่ต้องแก้ชื่อทั้งโปรเจกต์

**6. lifespan มี `yield` ได้อันเดียว**

บนสุด = ตอนเปิดแอป / ล่าง `yield` = ตอนปิด / `yield` ต้องอยู่ใน `try` ส่วน setup อยู่นอก
ห้ามใช้ `@app.on_event` มันตกรุ่นแล้ว

**7. ห้ามสร้าง connection เองในไฟล์อื่น**

Redis ต่อครั้งเดียวใน lifespan แล้วส่งต่อผ่าน `Depends(get_redis)`

## วิธีเช็คเร็ว ๆ ว่ายังไม่พัง

```bash
grep -rniE "fastapi|linebot|request" app/services   # ต้องไม่เจอ
grep -rniE "fastapi" app/clients                    # ต้องไม่เจอ
grep -rn "from app.api" app/services app/clients    # ต้องไม่เจอ
grep -rn "from app.services" app/clients            # ต้องไม่เจอ
```

## ยังไม่ทำตอนนี้

pydantic schemas, SQLAlchemy, alembic, Postgres — เอาไว้ทีหลัง ตอนใส่จะเพิ่ม
`schemas/`, `models/`, `repositories/` เข้ามา โดยไม่ต้องรื้อของเดิม

## git

commit ใช้ชื่อเจ้าของ repo เท่านั้น **ห้ามใส่ Co-Authored-By หรือ link ของ AI**
