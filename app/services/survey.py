"""น้องเมือง — สมองของบอทเก็บเสียงคนในชุมชน (UCR / TONKIT Lab)

เราไม่ใช่ศูนย์ช่วยเหลือ ปลายทางของข้อมูลคือหมุดบนแผนที่ให้ทีมออกแบบเมืองใช้
ตัดสินใจว่าควรปรับปรุงตรงไหนก่อน — sensor บอกได้ว่าตรงนี้ 38°C แต่บอกไม่ได้ว่า
ยายที่เดินไปตลาดทุกเช้าเดินไม่ไหวเพราะไม่มีร่มเงา เรารับหน้าที่เก็บส่วนหลัง

หลักการเดียวที่ห้ามพัง: **AI พูดว่า "จดให้แล้วค่ะ" ไม่มีผลอะไรทั้งนั้น**
ต้องเรียก record_report เท่านั้นข้อมูลถึงลง และ **โค้ดไฟล์นี้เป็นคนตัดสิน**
ว่าครบหรือยัง ไม่ใช่ AI

ไฟล์นี้ไม่รู้จักช่องทางแชท และไม่รู้จักเว็บเฟรมเวิร์ก — รับ str คืน dict ธรรมดา
(แม้แต่ในคอมเมนต์ก็เลี่ยงคำต้องห้าม เพราะ grep ในกฎข้อ 2 จับคำ ไม่ได้จับความหมาย)
"""

from redis.asyncio import Redis

from app.clients import llm, storage, transcript
from app.services import draft, memory

# ---------------------------------------------------------------- ช่องที่เก็บ

CATEGORIES = ["heat", "flood", "access", "other"]
SEVERITIES = ["low", "medium", "high"]

MIN_NOTES_CHARS = 20        # กัน AI เติม notes สั้น ๆ แล้วปิดเคสทั้งที่ยังไม่ได้อะไร
MAX_LOCATION_ASKS = 2       # ขอพิกัด 2 หนแล้วพอ ไม่ตื๊อ

FIELD_NAMES = {
    "notes": "เรื่องที่เขาเจอจริง ๆ ว่าเป็นยังไง (ที่มีอยู่ยังสั้นไป)",
    "category": "ว่าเป็นเรื่องร้อน / น้ำท่วม / การเดินทางเข้าถึง หรืออื่น ๆ",
    "location": "ตำแหน่งที่เกิดเรื่อง",
}

RECORD_TOOL = {
    "type": "function",
    "function": {
        "name": "record_report",
        "description": (
            "บันทึกสิ่งที่ได้จากชาวบ้านลงระบบ เรียกทุกครั้งที่รู้อะไรใหม่ "
            "ส่งมาเฉพาะช่องที่รู้จริง ห้ามเดา "
            "การพิมพ์ตอบว่าจดแล้วโดยไม่เรียกเครื่องมือนี้ ข้อมูลจะไม่ถูกบันทึก"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": CATEGORIES,
                    "description": (
                        "heat = ร้อน แดด ไม่มีร่มเงา / "
                        "flood = น้ำท่วม น้ำขัง ระบายไม่ทัน / "
                        "access = ทางเดิน ทางข้าม รถเข็น คนแก่ไปไหนลำบาก / "
                        "other = นอกจากนี้"
                    ),
                },
                "notes": {
                    "type": "string",
                    "description": (
                        "สิ่งที่เขาเจอมาจริง ๆ ตามที่เล่า ใครเดือดร้อน ตอนไหน ยังไง "
                        "ห้ามเขียนซ้ำกับ category เฉย ๆ เช่น 'น้ำท่วม' ใช้ไม่ได้ "
                        "ถ้าเขายังไม่ได้เล่าอะไรเป็นเรื่องเป็นราว ห้ามส่งช่องนี้มา"
                    ),
                },
                "severity": {
                    "type": "string",
                    "enum": SEVERITIES,
                    "description": (
                        "ประเมินเองจากสิ่งที่เขาเล่า **ห้ามถามชาวบ้านว่าหนักแค่ไหน** "
                        "high = กระทบสุขภาพ/ความปลอดภัย หรือเกิดประจำจนใช้ชีวิตไม่ได้ "
                        "medium = เดือดร้อนชัดเจนแต่ยังพอเลี่ยงได้ "
                        "low = รำคาญ ไม่สะดวก"
                    ),
                },
                "title": {
                    "type": "string",
                    "description": "พาดหัวสั้น ๆ ไม่เกิน 10 คำ ไว้ขึ้นบนหมุดแผนที่",
                },
                "location_text": {
                    "type": "string",
                    "description": (
                        "ตำแหน่งตามที่ชาวบ้าน**พิมพ์บอกมาเอง** เช่น 'ป้ายรถเมล์หน้าตลาดสด' "
                        "ห้ามส่งคำอธิบายลอย ๆ อย่าง 'ตำแหน่งที่ผู้ใช้แชร์มา' "
                        "ถ้าเขาไม่ได้พิมพ์บอกสถานที่ ห้ามส่งช่องนี้"
                    ),
                },
                # ไม่มี latitude/longitude ให้โมเดลกรอก — พิกัดมาจากปุ่มแชร์ตำแหน่งทางเดียว
                # เปิดช่องให้มันกรอกเมื่อไหร่ มันจะเดาตัวเลขให้เมื่อนั้น
            },
            "required": [],
        },
    },
}

# --------------------------------------------------------------- ลักษณะการตอบ

SYSTEM_PROMPT = """คุณคือ "น้องเมือง" **ผู้หญิง** เก็บเสียงคนในชุมชนเรื่องสภาพแวดล้อมเมือง
ให้ทีมออกแบบเอาไปตัดสินใจว่าควรปรับปรุงตรงไหนก่อน

ลงท้าย "ค่ะ" กับ "คะ" เท่านั้น **ห้ามใช้ "ครับ" เด็ดขาด** แม้แต่คำเดียว
และห้ามเขียนแบบเผื่อไว้ทั้งสองอย่างเช่น "ครับ/คะ"

สิ่งที่อยากได้คือ **ประสบการณ์จริง** ไม่ใช่ความเห็นลอย ๆ
ใครเดือดร้อน ตรงไหน ตอนไหนของวัน แล้วมันทำให้เขาต้องทำอะไรที่ไม่อยากทำ
เช่น "ต้องเดินอ้อมไกลขึ้น" "ไม่กล้าออกจากบ้านช่วงบ่าย" "อุ้มลูกลุยน้ำไปส่งโรงเรียน"

วิธีคุย:
- พูดไทยแบบเป็นกันเอง เหมือนคนในพื้นที่คุยกัน ไม่ใช้ศัพท์ราชการ
- สั้น ๆ ไม่เกิน 2 ประโยค แล้วถามต่อ **ทีละเรื่องเดียว** ห้ามยิงรัวหลายคำถาม
- ห้ามถามซ้ำสิ่งที่รู้แล้ว และห้ามทวนข้อมูลทั้งหมดทุกรอบ
- ถ้าเขาเล่ามาทีเดียวหลายเรื่อง เก็บให้หมด อย่าทิ้ง
- ถ้าเขาบ่นลอย ๆ เช่น "ร้อนชิบหาย" ให้ชวนเล่าต่อว่าเจอตอนไหน ตรงไหน

**ข้อห้ามสำคัญ** เราเก็บข้อมูลอย่างเดียว ไม่ได้เป็นคนไปแก้:
- ห้ามสัญญาว่าจะส่งคนไปช่วย ไปซ่อม หรือจะแก้ให้
- ห้ามบอกว่า "เดี๋ยวจะรีบดำเนินการ" หรือ "แจ้งหน่วยงานให้แล้ว"
- พูดได้แค่ว่าเรื่องนี้จะถูกส่งต่อให้ทีมที่ออกแบบปรับปรุงพื้นที่
- ถ้าเจอเรื่องฉุกเฉินที่ต้องการความช่วยเหลือทันที ให้บอกตรง ๆ ว่าช่องทางนี้
  ไม่ใช่สายด่วน แนะนำให้ติดต่อหน่วยงานฉุกเฉิน แล้วค่อยถามต่อว่าจะให้บันทึกไว้ไหม

เรื่องความหนักเบา:
- **ห้ามถามว่าหนักแค่ไหน หรือให้เขาให้คะแนน** คุณประเมินเองจากที่เขาเล่า

เรื่องตำแหน่ง:
- ขอให้กดแชร์ตำแหน่งก่อน เพราะข้อมูลนี้ต้องขึ้นเป็นหมุดบนแผนที่
- ถ้าเขาบอกว่าส่งไม่ได้หรือไม่สะดวก ให้ถามอีกครั้งเดียวว่าพิมพ์บอกจุดสังเกตแทนได้ไหม
  เช่น ชื่อซอย ป้ายรถเมล์ ตลาด โรงเรียนใกล้ ๆ
- ถ้ายังไม่ได้อีก ปล่อยไป อย่าตื๊อ

เรื่องรูป:
- **คุณดูรูปไม่ได้** ถ้าระบบบอกว่ามีรูปส่งมา แปลว่าเก็บไว้ให้ทีมออกแบบดูแล้ว
- ให้ขอบคุณสั้น ๆ แล้วชวนเล่าว่าในรูปคืออะไร ตรงไหน
- **ห้ามทำเป็นว่าเห็นรูป ห้ามบรรยายว่าในรูปมีอะไร** เพราะคุณไม่เห็นจริง ๆ
- ห้ามเอาสิ่งที่เดาจากรูปไปใส่ใน record_report

เรื่องข้อมูลที่ระบบส่งมาให้ในวงเล็บ [ระบบ: ...]:
- นั่นคือของจริงจากแอป ไม่ใช่คำพูดของชาวบ้าน เชื่อได้เลย
- ห้ามพูดถึงวงเล็บนั้นตรง ๆ กับชาวบ้าน ให้คุยเหมือนคนปกติ

กติกา:
- ทุกครั้งที่ได้ข้อมูลใหม่ ให้เรียก record_report ทันที การพิมพ์ว่าจดแล้วไม่มีผล
- ระบบจะบอกกลับมาเองว่ายังขาดอะไร ให้ถามตามนั้น
- ห้ามบอกว่าบันทึกเรียบร้อยแล้วเองจนกว่าระบบจะบอกว่าครบ"""


# -------------------------------------------------------------- ตัวตัดสินใจ

def missing(report: dict) -> list[str]:
    """ช่องบังคับที่ยังขาด — มีแค่ 2 ช่อง category กับ notes"""
    left = []

    if not report.get("category"):
        left.append("category")

    # ตัวหนังสือน้อยเกิน = ยังไม่ได้เล่าอะไร ถือว่ายังไม่มี
    if len(str(report.get("notes") or "")) < MIN_NOTES_CHARS:
        left.append("notes")

    return left


def has_location(report: dict) -> bool:
    if report.get("latitude") is not None and report.get("longitude") is not None:
        return True
    return bool(report.get("location_text"))


def next_goal(report: dict) -> str | None:
    """ยังต้องถามอะไรต่อ — คืน None แปลว่าพอแล้ว ปิดใบได้

    ตำแหน่งไม่ใช่ช่องบังคับ แต่ปลายทางคือหมุดบนแผนที่ เลยขอ MAX_LOCATION_ASKS หน
    ถ้าเขาไม่ให้จริง ๆ ก็ปล่อย ดีกว่าตื๊อจนเขาเลิกคุย
    """
    left = missing(report)
    if left:
        return left[0]

    if not has_location(report) and report.get("_location_asks", 0) < MAX_LOCATION_ASKS:
        return "location"

    return None


def is_complete(report: dict) -> bool:
    return next_goal(report) is None


def _status(report: dict) -> str:
    """ข้อความที่ยัดกลับไปให้ AI หลังมันเรียก tool — โค้ดเราสั่งงาน AI ตรงนี้"""
    goal = next_goal(report)

    if goal is None:
        return (
            "บันทึกครบแล้ว สรุปให้เขาฟังสั้น ๆ 1-2 ประโยคว่าเก็บอะไรไว้ "
            "บอกว่าจะส่งต่อให้ทีมที่ดูแลการปรับปรุงพื้นที่ แล้วขอบคุณ "
            "ห้ามสัญญาว่าจะไปแก้ให้ และห้ามถามอะไรอีก"
        )

    if goal == "location":
        return "บันทึกแล้ว ยังไม่มีตำแหน่ง — ขอตำแหน่งที่เกิดเรื่อง"

    return f"บันทึกแล้ว ยังขาด: {FIELD_NAMES[goal]} — ถามต่อเรื่องเดียว"


# ------------------------------------------------------------------ ตัวคุย

MAX_TOOL_ROUNDS = 3   # กันโมเดลวนเรียก tool ไม่หยุด


async def reply(
    r: Redis,
    session_id: str,
    message: str,
    latitude: float | None = None,
    longitude: float | None = None,
    location_text: str | None = None,
    image_key: str | None = None,
    source: str = "user",
) -> dict:
    """คุย 1 ตา คืน {"reply", "report", "report_id", "asking_location"}

    latitude/longitude/location_text มาจากปุ่มแชร์ตำแหน่ง ไม่ได้มาจากการพิมพ์
    image_key คือรูปที่เก็บไว้แล้ว **ตัวรูปไม่เข้าโมเดล** เข้าแค่ marker บอกว่ามีรูป
    source บอกว่ามาจากที่ไหน "user" = ทักมาเอง / "broadcast" = ตอบการ์ดที่เรายิงไป
    """
    if latitude is not None and longitude is not None:
        # ของจากปุ่มแชร์ตำแหน่งเชื่อถือได้กว่าที่โมเดลสรุปเอง เขียนลงตรง ๆ ไม่ผ่านโมเดล
        # แล้วปักธงไว้ว่าช่องนี้ห้ามใครมาทับ
        await draft.merge(
            r,
            session_id,
            {
                "latitude": latitude,
                "longitude": longitude,
                "location_text": location_text,
                "_location_locked": True,
            },
        )

    if image_key:
        current = await draft.load(r, session_id)
        await draft.merge(
            r, session_id, {"images": current.get("images", []) + [image_key]}
        )

    history = await memory.load(r, session_id)
    report = await draft.load(r, session_id)

    said = _with_markers(message, latitude, longitude, image_key)
    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + history
        + [{"role": "user", "content": said}]
    )

    for _ in range(MAX_TOOL_ROUNDS):
        answer = await llm.chat_tools(messages, [RECORD_TOOL])

        if not answer["tool_calls"]:
            break

        for call in answer["tool_calls"]:
            if call["name"] == "record_report":
                await draft.merge(r, session_id, _allowed(call["arguments"], report))

        report = await draft.load(r, session_id)
        messages += llm.tool_exchange(answer["tool_calls"], _status(report))
    else:
        # วนครบแล้วยังไม่ยอมพูด — บังคับให้พูดโดยไม่ให้ tool
        answer = {"content": await llm.chat(messages), "tool_calls": []}

    text = answer["content"].strip() or "ขอโทษครับ ช่วยเล่าอีกครั้งได้ไหม"

    # ตัดสินด้วยค่า "ก่อนบวก" เสมอ — ตาที่เราเพิ่งถามหาตำแหน่ง ต้องปล่อยให้เขา
    # ได้ตอบก่อน 1 ตา ถ้าบวกแล้วเช็คทันทีจะกลายเป็นถามแล้วปิดใบในตาเดียวกัน
    asking_location = next_goal(report) == "location"
    done = is_complete(report)

    if asking_location:
        await draft.merge(
            r, session_id, {"_location_asks": report.get("_location_asks", 0) + 1}
        )

    report_id = None
    if done:
        report_id = await storage.save_report(
            {"session_id": session_id, "source": source, **_public(report)}
        )
        # เก็บต้นฉบับก่อนล้างความจำ — ที่ผ่านมาตรงนี้คือจุดที่ของดิบหายไปตลอดกาล
        await transcript.save(
            session_id,
            report_id,
            history
            + [{"role": "user", "content": message}, {"role": "assistant", "content": text}],
        )
        await draft.clear(r, session_id)
        await memory.clear(r, session_id)
    else:
        await memory.append(r, session_id, "user", message)
        await memory.append(r, session_id, "assistant", text)

    return {
        "reply": text,
        "report": _public(report),
        "report_id": report_id,
        # บอกคนเรียกว่าตานี้เรากำลังขอตำแหน่งอยู่ ฝั่งแชทจะได้เอาไปขึ้นปุ่มให้กด
        # (ไฟล์นี้ไม่รู้ว่าปุ่มหน้าตายังไง และไม่ควรรู้)
        "asking_location": asking_location,
    }


def _allowed(arguments: dict, report: dict) -> dict:
    """กรองสิ่งที่โมเดลส่งมา ก่อนให้เขียนลงใบ

    ถ้าตำแหน่งมาจากปุ่มแชร์แล้ว ห้ามโมเดลเขียนทับ — เคยเจอมันทับ
    "ซอยเพชรเกษม 63 แขวงหลักสอง" ด้วยคำว่า "ตำแหน่งที่ผู้ใช้แชร์มา" ซึ่งไม่มีข้อมูลอะไรเลย
    """
    if not report.get("_location_locked"):
        return arguments
    return {k: v for k, v in arguments.items() if k != "location_text"}


def _public(report: dict) -> dict:
    """ตัดช่องที่เราใช้นับภายในออก ขึ้นต้นด้วย _ = ไม่ลง DB ไม่โผล่ออก API"""
    return {k: v for k, v in report.items() if not k.startswith("_")}


def _with_markers(message: str, latitude, longitude, image_key) -> str:
    """รูป/พิกัดไม่เข้าโมเดล — ยัด marker บอกให้รู้แทน ประหยัดและไม่หลุดข้อมูลส่วนตัว"""
    markers = []

    if latitude is not None and longitude is not None:
        markers.append(f"[ระบบ: ผู้ใช้แชร์ตำแหน่งมาแล้ว {latitude}, {longitude}]")

    if image_key:
        markers.append("[ระบบ: ผู้ใช้ส่งรูปมาให้ 1 รูป เก็บไว้ให้แล้ว คุณดูรูปไม่ได้]")

    return " ".join(markers + [message]).strip()
