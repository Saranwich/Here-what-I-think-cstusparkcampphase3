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

# ผลกระทบต่อ "ชีวิตเขา" ไม่ใช่ "ปัญหาคืออะไร" — อย่างหลังคือ category
# ถ้าปนกันเมื่อไหร่ tag จะกลายเป็นสำเนา category แล้วกรองอะไรไม่ได้เลย
AFFECT_TAGS = ["health", "safety", "mobility", "property", "income", "daily_life"]
FREQUENCIES = ["once", "occasional", "recurring"]
TIMES_OF_DAY = ["morning", "afternoon", "evening", "night"]

MIN_NOTES_CHARS = 20        # กัน AI เติม notes สั้น ๆ แล้วปิดเคสทั้งที่ยังไม่ได้อะไร
MAX_LOCATION_ASKS = 2       # ขอพิกัด 2 หนแล้วพอ ไม่ตื๊อ
MAX_PHOTO_ASKS = 1          # รูปขอครั้งเดียว ไม่ได้ก็ไม่เป็นไร มันเป็นของแถม

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
                        "**ช่องหลัก ส่งมาทุกครั้งที่เขาเล่าอะไรก็ตาม** "
                        "เล่าเรื่องของเขาให้ครบในช่องเดียวนี้ ใครเดือดร้อน ตอนไหน ยังไง "
                        "ช่องอื่น (cause_said, affect_desc, occurred_said) เป็นการ"
                        "**แยกชิ้นออกมาจากเรื่องนี้อีกที ไม่ใช่ตัวแทน** "
                        "กรอกช่องอื่นแล้วเว้นช่องนี้ว่าง = เรื่องของเขาหายไปทั้งเรื่อง "
                        "ห้ามเขียนซ้ำกับ category เฉย ๆ เช่น 'น้ำท่วม' ใช้ไม่ได้"
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
                "cause_said": {
                    "type": "string",
                    "description": (
                        "สาเหตุตามที่ชาวบ้าน**คิดเองหรือบอกมาเอง** "
                        "เช่น 'ท่อตัน' 'เขาถมถนนสูงกว่าบ้าน' 'คลองไม่ได้ขุดมาสิบปี' "
                        "นี่คือความเชื่อของเขา ไม่ใช่ข้อเท็จจริงที่ตรวจแล้ว "
                        "ห้ามเดาแทน ห้ามวิเคราะห์ให้ ถ้าเขาไม่ได้พูดถึงสาเหตุ ห้ามส่งช่องนี้"
                    ),
                },
                "affect_desc": {
                    "type": "string",
                    "description": (
                        "ผลกระทบตามคำของเขาเอง ให้ใกล้คำพูดเดิมที่สุด "
                        "เช่น 'ต้องอุ้มลูกลุยน้ำไปส่งโรงเรียน' 'ไม่กล้าออกจากบ้านช่วงบ่าย' "
                        "'ต้องเดินอ้อมไกลขึ้นสิบนาที'"
                    ),
                },
                "affect_tags": {
                    "type": "array",
                    "items": {"type": "string", "enum": AFFECT_TAGS},
                    "description": (
                        "มันทำอะไรกับชีวิตเขา ติดได้หลายอัน "
                        "health = สุขภาพ ป่วย เป็นลม ผื่น หายใจไม่ออก / "
                        "safety = อันตราย ลื่นล้ม ไฟช็อต รถชน / "
                        "mobility = ไปไหนลำบาก เดินอ้อม ออกจากบ้านไม่ได้ / "
                        "property = ของเสียหาย บ้าน รถ ของที่ขาย / "
                        "income = ขาดรายได้ ขายของไม่ได้ ไปทำงานสาย / "
                        "daily_life = ใช้ชีวิตปกติไม่ได้ นอนไม่หลับ ทำกับข้าวไม่ได้ "
                        "**ห้ามใส่ว่ามันเป็นปัญหาอะไร** อันนั้นคือ category คนละเรื่องกัน"
                    ),
                },
                "occurred_said": {
                    "type": "string",
                    "description": (
                        "เกิดตอนไหน ตามคำที่เขาพูด เช่น 'ทุกครั้งที่ฝนตก' "
                        "'บ่ายสองทุกวัน' 'เมื่อวานตอนเย็น' "
                        "**ห้ามแปลงเป็นวันที่หรือเวลาเป็นตัวเลข** เก็บคำเขาไว้ตรง ๆ"
                    ),
                },
                "frequency": {
                    "type": "string",
                    "enum": FREQUENCIES,
                    "description": (
                        "เกิดบ่อยแค่ไหน — once = ครั้งเดียว เพิ่งเจอครั้งแรก / "
                        "occasional = นาน ๆ ที / recurring = เกิดประจำ ซ้ำ ๆ"
                    ),
                },
                "time_of_day": {
                    "type": "array",
                    "items": {"type": "string", "enum": TIMES_OF_DAY},
                    "description": (
                        "ช่วงเวลาที่เกิด ติดได้หลายช่วง "
                        "morning = เช้า / afternoon = สาย-บ่าย / "
                        "evening = เย็น / night = กลางคืน"
                    ),
                },
                "use_last_location": {
                    "type": "boolean",
                    "description": (
                        "ใส่ true เมื่อชาวบ้านบอกว่าเป็น 'ที่เดิม' หรือที่เดียวกับที่เคยแจ้งไว้ "
                        "ระบบจะไปหยิบตำแหน่งเก่ามาให้เอง ใช้ได้เฉพาะตอนที่ระบบแจ้งว่ามีตำแหน่งเก่าอยู่"
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
- **ห้ามพูดว่า "จดให้แล้ว" "บันทึกเรียบร้อย" "รับเรื่องแล้ว" หรือคำทำนองนี้**
  มันฟังดูเหมือนเสมียนรับเรื่องแล้วเงียบหาย ให้พูดถึง**ปลายทาง**แทน
  เช่น "เรื่องนี้จะไปถึงทีมที่ออกแบบปรับปรุงพื้นที่แถวนั้นค่ะ"
  หรือ "เดี๋ยวจุดนี้จะไปขึ้นบนแผนที่ที่ทีมเขาใช้ดูค่ะ"

**ข้อห้ามสำคัญ** เราเก็บข้อมูลอย่างเดียว ไม่ได้เป็นคนไปแก้:
- ห้ามสัญญาว่าจะส่งคนไปช่วย ไปซ่อม หรือจะแก้ให้
- ห้ามบอกว่า "เดี๋ยวจะรีบดำเนินการ" หรือ "แจ้งหน่วยงานให้แล้ว"
- พูดได้แค่ว่าเรื่องนี้จะถูกส่งต่อให้ทีมที่ออกแบบปรับปรุงพื้นที่
- ถ้าเจอเรื่องฉุกเฉินที่ต้องการความช่วยเหลือทันที ให้บอกตรง ๆ ว่าช่องทางนี้
  ไม่ใช่สายด่วน แนะนำให้ติดต่อหน่วยงานฉุกเฉิน แล้วค่อยถามว่าจะเล่าเรื่องนี้ไว้ไหม

เรื่องความหนักเบา:
- **ห้ามถามว่าหนักแค่ไหน หรือให้เขาให้คะแนน** คุณประเมินเองจากที่เขาเล่า

เรื่องสาเหตุ ผลกระทบ และเวลาที่เกิด:
- **ส่วนใหญ่เขาเล่ามาเองอยู่แล้ว หน้าที่คุณคือแกะออกมา ไม่ใช่ตั้งคำถามเพิ่ม**
  เช่น "วันนี้ฝนตกแล้วน้ำท่วม ท่วมบ่อยเกือบตลอด ต้องอุ้มลูกลุยน้ำไปส่งโรงเรียน"
  ประโยคเดียวนี้มีครบทั้งเวลา ความถี่ และผลกระทบ โดยไม่มีใครถามสักคำ
- ถ้าเขาเล่ามาสั้นจนไม่มีอะไรให้แกะ **ถามเพิ่มได้แค่ 1 คำถามต่อ 1 เรื่อง**
  เลือกถามอันที่ขาดแล้วน่าเสียดายที่สุดอันเดียว แล้วพอ
- **ห้ามไล่ถามให้ครบทุกช่อง** นี่ไม่ใช่แบบสอบถาม ช่องไหนเขาไม่พูดถึงก็ปล่อยว่างไว้
  ใบที่ข้อมูลไม่ครบแต่เขายังอยากคุย ดีกว่าใบที่ครบแต่เขาเลิกคุยไปกลางทาง
- ห้ามเดาแทนเขาทุกกรณี ทุกช่องต้องมาจากสิ่งที่เขาพูดจริง ๆ

เรื่องตำแหน่ง:
- **ฟังให้รู้ก่อนว่าเขาเจอเรื่องอะไร แล้วค่อยขอตำแหน่ง**
  ห้ามขอตั้งแต่ประโยคแรกที่เขาทักมา คนเพิ่งทักว่า "สวัสดี" แล้วโดนขอพิกัดเลยจะตกใจ
- พอรู้เรื่องแล้วค่อยชวนให้กดแชร์ตำแหน่ง เพราะข้อมูลต้องขึ้นเป็นหมุดบนแผนที่
- ถ้าเขาบอกว่าส่งไม่ได้หรือไม่สะดวก ให้ถามอีกครั้งเดียวว่าพิมพ์บอกจุดสังเกตแทนได้ไหม
  เช่น ชื่อซอย ป้ายรถเมล์ ตลาด โรงเรียนใกล้ ๆ
- ถ้ายังไม่ได้อีก ปล่อยไป อย่าตื๊อ

เรื่องรูป:
- **คุณดูรูปไม่ได้** ถ้าระบบบอกว่ามีรูปส่งมา แปลว่ารูปถูกแนบไว้กับเรื่องของเขาแล้ว
  ทีมออกแบบจะเห็นตอนเปิดอ่านเรื่องนี้ — **ยังไม่มีใครดู ห้ามบอกเขาว่ามีคนดูแล้ว**
- ให้ขอบคุณสั้น ๆ แล้วชวนเล่าว่าตรงนั้นเกิดอะไรขึ้น
- **ห้ามทำเป็นว่าเห็นรูป ห้ามบรรยายว่ามีอะไรอยู่ในนั้น** เพราะคุณไม่เห็นจริง ๆ
- **ตอนถามต่อ ห้ามอ้างถึงสิ่งที่เขาเพิ่งส่งมา ให้ถามถึงสถานที่จริงแทน**
  ถามว่า "ตรงนั้นเป็นยังไง" ได้ ถามว่าสิ่งที่ส่งมามีอะไรไม่ได้ เพราะคุณไม่รู้
- ห้ามเอาสิ่งที่เดาจากรูปไปใส่ใน record_report
- **ตอนขอรูป ขอครั้งเดียวพอ** บอกเหตุผลสั้น ๆ ว่ารูปช่วยให้ทีมออกแบบเห็นสภาพจริง
  ของตรงนั้นได้ ซึ่งคำบรรยายบอกได้ไม่หมด
- ชวนแบบสบาย ๆ ให้เขาปฏิเสธได้ง่าย เช่น "ถ้าสะดวกถ่ายรูปตรงนั้นมาให้ดูหน่อยได้ไหมคะ
  ไม่มีก็ไม่เป็นไรนะคะ"
- **ถ้าเขาบอกว่าไม่มี ไม่สะดวก หรือถ่ายไม่ได้ ปล่อยทันที ห้ามขอซ้ำ ห้ามคะยั้นคะยอ**
  บางเรื่องเกิดไปแล้ว บางเรื่องเป็นตอนกลางคืน ถ่ายไม่ได้เป็นเรื่องปกติมาก

เรื่องข้อมูลที่ระบบส่งมาให้ในวงเล็บ [ระบบ: ...]:
- นั่นคือของจริงจากแอป ไม่ใช่คำพูดของชาวบ้าน เชื่อได้เลย
- ห้ามพูดถึงวงเล็บนั้นตรง ๆ กับชาวบ้าน ให้คุยเหมือนคนปกติ

กติกา:
- ทุกครั้งที่ได้ข้อมูลใหม่ ให้เรียก record_report ทันที การพิมพ์ว่าจดแล้วไม่มีผล
- ระบบจะบอกกลับมาเองว่ายังขาดอะไร ให้ถามตามนั้น
- ห้ามบอกเขาว่าเรื่องนี้จะถูกส่งต่อแล้ว จนกว่าระบบจะบอกว่าข้อมูลครบ"""

# ต่อท้าย prompt เฉพาะตาที่เพิ่งปิดใบไปหมาด ๆ
JUST_FINISHED_NOTE = """

**ตอนนี้เพิ่งบันทึกเรื่องของเขาไปเมื่อกี้**
ถ้าข้อความล่าสุดเป็นแค่คำตอบรับ เช่น "ครับ" "ค่ะ" "ขอบคุณ" "โอเค" หรือสติกเกอร์
ให้ตอบสั้น ๆ อย่างเป็นมิตรแล้วจบ **ห้ามเริ่มถามเรื่องใหม่ ห้ามขอตำแหน่ง**
เริ่มเก็บเรื่องใหม่เฉพาะตอนที่เขาเล่าเรื่องใหม่จริง ๆ เท่านั้น"""

# ต่อท้าย prompt เมื่อคนนี้เคยแชร์ตำแหน่งไว้แล้วในใบก่อน ๆ
LAST_LOCATION_NOTE = """

**คนนี้เคยแชร์ตำแหน่งไว้แล้ว: {where}**
ตอนถามหาตำแหน่ง ให้ถามว่าเป็นที่เดิมหรือคนละที่ อย่าให้เขาแชร์ซ้ำโดยไม่จำเป็น
ถ้าเขาบอกว่าที่เดิม / ที่เดียวกับเมื่อกี้ / ตรงนั้นแหละ
ให้เรียก record_report พร้อม use_last_location=true ระบบจะหยิบตำแหน่งเก่ามาให้เอง
**ห้ามบอกว่าจำไม่ได้ หรือขอให้แชร์ใหม่ทั้งที่เขาบอกว่าที่เดิม**"""


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


def has_image(report: dict) -> bool:
    return bool(report.get("image_keys"))


def next_goal(report: dict) -> str | None:
    """ยังต้องถามอะไรต่อ — คืน None แปลว่าพอแล้ว ปิดใบได้

    ตำแหน่งไม่ใช่ช่องบังคับ แต่ปลายทางคือหมุดบนแผนที่ เลยขอ MAX_LOCATION_ASKS หน
    ถ้าเขาไม่ให้จริง ๆ ก็ปล่อย ดีกว่าตื๊อจนเขาเลิกคุย

    รูปขอทีหลังตำแหน่ง เพราะตำแหน่งมีค่ากว่า (ไม่มีพิกัด = ไม่ขึ้นหมุด)
    ถ้ายิงขอพร้อมกันจะแย่งความสนใจกันเอง แล้วอาจไม่ได้สักอย่าง
    """
    left = missing(report)
    if left:
        return left[0]

    if not has_location(report) and report.get("_location_asks", 0) < MAX_LOCATION_ASKS:
        return "location"

    if not has_image(report) and report.get("_photo_asks", 0) < MAX_PHOTO_ASKS:
        return "photo"

    return None


def is_complete(report: dict) -> bool:
    return next_goal(report) is None


def _status(report: dict) -> str:
    """ข้อความที่ยัดกลับไปให้ AI หลังมันเรียก tool — โค้ดเราสั่งงาน AI ตรงนี้"""
    goal = next_goal(report)

    if goal is None:
        return (
            "[ระบบ] ข้อมูลครบแล้ว ปิดท้ายสั้น ๆ 1-2 ประโยค "
            "ทวนเรื่องของเขาด้วยคำของเขาเอง แล้วบอกว่าเรื่องนี้จะไปถึงทีม"
            "ที่ออกแบบปรับปรุงพื้นที่ แล้วขอบคุณที่สละเวลาเล่า "
            "**ห้ามพูดถึงการจด การบันทึก หรือการรับเรื่อง** มันฟังดูเหมือนเสมียน "
            "ให้พูดถึงปลายทางว่าเรื่องของเขาจะไปอยู่ที่ไหนแทน "
            "ห้ามสัญญาว่าจะไปแก้ให้ และห้ามถามอะไรอีก"
        )

    if goal == "location":
        return "[ระบบ] เก็บลงระบบแล้ว ยังไม่มีตำแหน่ง — ขอตำแหน่งที่เกิดเรื่อง"

    if goal == "photo":
        return (
            "[ระบบ] เก็บลงระบบแล้ว ยังไม่มีรูป — ชวนถ่ายรูปตรงนั้นมาให้ดูสักรูป "
            "ขอครั้งเดียว บอกเหตุผลสั้น ๆ และทำให้ปฏิเสธง่าย"
        )

    return f"[ระบบ] เก็บลงระบบแล้ว ยังขาด: {FIELD_NAMES[goal]} — ถามต่อเรื่องเดียว"


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
            r, session_id, {"image_keys": current.get("image_keys", []) + [image_key]}
        )

    history = await memory.load(r, session_id)
    report = await draft.load(r, session_id)

    # เพิ่งปิดใบไปหมาด ๆ — อย่าเพิ่งรีบเปิดใบใหม่ใส่เขา
    prompt = SYSTEM_PROMPT
    if not report and await draft.just_finished(r, session_id):
        prompt += JUST_FINISHED_NOTE

    # เคยแจ้งตำแหน่งไว้ในใบก่อน ๆ มั้ย — ถามจากที่เก็บหลัก ไม่ได้กองไว้ใน Redis
    remembered = None if has_location(report) else await storage.last_location(session_id)
    if remembered:
        prompt += LAST_LOCATION_NOTE.format(
            where=remembered.get("location_text") or "ตำแหน่งที่เคยแชร์ไว้"
        )

    said = _with_markers(message, latitude, longitude, image_key)
    messages = (
        [{"role": "system", "content": prompt}]
        + history
        + [{"role": "user", "content": said}]
    )

    for _ in range(MAX_TOOL_ROUNDS):
        answer = await llm.chat_tools(messages, [RECORD_TOOL])

        if not answer["tool_calls"]:
            break

        for call in answer["tool_calls"]:
            if call["name"] != "record_report":
                continue

            arguments = dict(call["arguments"])
            reuse = arguments.pop("use_last_location", False)

            await draft.merge(r, session_id, _allowed(_sanitize(arguments), report))

            if reuse and remembered:
                # ตำแหน่งเก่าเป็นของจากปุ่มแชร์ เชื่อถือได้เท่าเดิม ล็อกไว้เหมือนกัน
                await draft.merge(
                    r, session_id, remembered | {"_location_locked": True}
                )

        report = await draft.load(r, session_id)
        if report:
            # เล่าเรื่องใหม่มาแล้ว ป้าย "เพิ่งคุยจบ" หมดหน้าที่
            await draft.clear_done(r, session_id)
        messages += llm.tool_exchange(answer["tool_calls"], _status(report))
    else:
        # วนครบแล้วยังไม่ยอมพูด — บังคับให้พูดโดยไม่ให้ tool
        answer = {"content": await llm.chat(messages), "tool_calls": []}

    text = answer["content"].strip() or "ขอโทษครับ ช่วยเล่าอีกครั้งได้ไหม"

    # ตัดสินด้วยค่า "ก่อนบวก" เสมอ — ตาที่เราเพิ่งถามหาตำแหน่ง ต้องปล่อยให้เขา
    # ได้ตอบก่อน 1 ตา ถ้าบวกแล้วเช็คทันทีจะกลายเป็นถามแล้วปิดใบในตาเดียวกัน
    goal = next_goal(report)
    asking_location = goal == "location"
    asking_photo = goal == "photo"
    done = is_complete(report)

    if asking_location:
        await draft.merge(
            r, session_id, {"_location_asks": report.get("_location_asks", 0) + 1}
        )

    if asking_photo:
        await draft.merge(
            r, session_id, {"_photo_asks": report.get("_photo_asks", 0) + 1}
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
        await draft.mark_done(r, session_id, report_id)
    else:
        await memory.append(r, session_id, "user", message)
        await memory.append(r, session_id, "assistant", text)

    return {
        "reply": text,
        "report": _public(report),
        "report_id": report_id,
        # บอกคนเรียกว่าตานี้เรากำลังขออะไรอยู่ ฝั่งแชทจะได้เอาไปขึ้นปุ่มให้กด
        # (ไฟล์นี้ไม่รู้ว่าปุ่มหน้าตายังไง และไม่ควรรู้)
        "asking_location": asking_location,
        "asking_photo": asking_photo,
    }


# ช่องที่มีคำศัพท์ตายตัว — ค่านอกรายการถือว่าไม่มี
_VOCAB = {
    "category": CATEGORIES,
    "severity": SEVERITIES,
    "frequency": FREQUENCIES,
}
_LIST_VOCAB = {
    "affect_tags": AFFECT_TAGS,
    "time_of_day": TIMES_OF_DAY,
}


def _sanitize(arguments: dict) -> dict:
    """เจอค่านอกรายการ ทิ้งเฉพาะค่านั้น ไม่ทิ้งทั้งใบ

    วันหนึ่งโมเดลจะส่ง "urgent" มาแทน "high" แน่ ๆ ตอนนั้นเราต้องยังได้เรื่อง
    ที่ชาวบ้านอุตส่าห์เล่ามาเก็บไว้ **ห้ามให้ค่าผิดช่องเดียวฆ่าทั้งรายงาน**
    """
    clean = {}

    for field, value in arguments.items():
        if field in _VOCAB:
            if value in _VOCAB[field]:
                clean[field] = value
        elif field in _LIST_VOCAB:
            kept = [v for v in value or [] if v in _LIST_VOCAB[field]]
            if kept:
                clean[field] = kept
        else:
            clean[field] = value

    return clean


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
