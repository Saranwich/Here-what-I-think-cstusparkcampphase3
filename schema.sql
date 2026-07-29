-- ตารางของ Postgres — รันมือครั้งเดียวตอนตั้งเครื่องใหม่
--
--     psql "$DATABASE_URL" -f schema.sql
--
-- แอปไม่สร้างตารางให้เองตอนเปิด ตั้งใจให้เป็นแบบนั้น เพราะโค้ดที่แก้ schema ได้
-- ระหว่างรันคือโค้ดที่ทำ schema พังได้ระหว่างรันเหมือนกัน
--
-- ไม่มี IF NOT EXISTS เพราะรันซ้ำควรพังให้เห็น ดีกว่าเงียบแล้วปล่อยให้ตารางเก่า
-- ที่หน้าตาไม่ตรงกับไฟล์นี้อยู่ต่อไป

CREATE EXTENSION IF NOT EXISTS postgis;


CREATE TABLE reports (
    id            bigserial   PRIMARY KEY,
    session_id    text        NOT NULL,               -- LINE user id
    source        text        NOT NULL DEFAULT 'user', -- user | rescued | broadcast
    created_at    timestamptz NOT NULL DEFAULT now(),

    -- สองช่องนี้เท่านั้นที่บังคับ ตรงกับ missing() ใน services/survey.py
    category      text        NOT NULL,               -- heat | flood | access | other
    notes         text        NOT NULL,               -- ฉบับเรียบเรียงให้ทีมอ่าน

    title         text,                               -- พาดหัวบนหมุด
    severity      text,                               -- low | medium | high
    affect_desc   text,
    affect_tags   text[],                             -- health safety mobility property income daily_life
    frequency     text,                               -- once | occasional | recurring
    time_of_day   text[],                             -- morning afternoon evening night

    -- คำพูดของชาวบ้านตรง ๆ รวมภาษาถิ่น **ห้าม normalize** ฉบับเรียบเรียงอยู่ที่ notes แล้ว
    cause_said    text,
    occurred_said text,

    -- geom มาจาก ST_MakePoint(longitude, latitude) — longitude มาก่อน
    -- แถวที่ไม่มี geom ไม่ขึ้นเป็นหมุด แต่ยังนับสถิติได้ ทีมปักมือทีหลังได้
    geom          geography(Point, 4326),
    location_text text,                               -- ที่อยู่แบบพูด ตอนแชร์พิกัดไม่ได้

    -- แยก "เขาปฏิเสธเอง" ออกจาก "คุยค้างแล้วหายไป" — คนละเรื่องกันสำหรับทีมออกแบบ
    no_location   boolean     NOT NULL DEFAULT false,
    no_photo      boolean     NOT NULL DEFAULT false
);

-- ไม่มี CHECK constraint ที่ category / severity / frequency ทั้งที่ใส่ได้
-- เพราะ _sanitize() ใน services/survey.py กรองค่านอกรายการทิ้งก่อนถึงตรงนี้แล้ว
-- ถ้าใส่ CHECK ค่าเพี้ยนช่องเดียวจะทำ INSERT ล้มทั้งแถว = เสียเรื่องที่เขาอุตส่าห์เล่าทั้งใบ
-- ชั้นแอปกรอง ชั้นนี้รับ

CREATE INDEX reports_geom_idx    ON reports USING GIST (geom);
CREATE INDEX reports_session_idx ON reports (session_id, created_at DESC);


CREATE TABLE report_images (
    id         bigserial   PRIMARY KEY,
    report_id  bigint      NOT NULL REFERENCES reports(id) ON DELETE CASCADE,

    -- key ไม่ใช่ path — ห้ามใครนอก clients/media.py เอาไปต่อกับชื่อโฟลเดอร์
    -- นั่นคือทั้งหมดของแผนย้ายขึ้น S3
    image_key  text        NOT NULL,                  -- images/YYYY/MM/xxx.jpg
    descr      text,                                  -- เรื่องที่คุยกันอยู่ตอนรูปมาถึง
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX report_images_report_idx ON report_images (report_id);
