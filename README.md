# MataQorLab · Analyst App

เว็บแอปวิเคราะห์ข้อมูลธุรกิจด้วย AI ตั้งแต่เชื่อมแหล่งข้อมูล เตรียมข้อมูล และกำหนดความหมายของคอลัมน์ ไปจนถึงถามตอบผ่านแชทและแสดงผลบน Dashboard

โปรเจกต์นี้แสดงการพัฒนาระบบ Full-stack ที่เชื่อม Frontend, API, Data processing, AI และ Background worker เข้าด้วยกัน โดยให้ Backend คำนวณตัวเลขก่อนส่งให้ LLM ช่วยอธิบายผล

> Repository นี้เป็นสำเนาสำหรับ Portfolio แยกจากประวัติ Git เดิม ไม่รวมข้อมูลผู้ใช้ ไฟล์ตั้งค่าจริง หรือคีย์บริการ ต้องตั้งค่าบริการของตัวเองก่อนใช้งาน และยังไม่ได้รัน Build หรือ Test ของสำเนานี้

## ฟีเจอร์หลัก

- **Data connections** — นำเข้าข้อมูลจากไฟล์ CSV, Excel, JSON, Parquet รวมถึง SQL และ REST API
- **Guided data setup** — เตรียมข้อมูลผ่านบทสนทนา ตรวจคุณภาพ และยืนยัน Semantic mapping ก่อนวิเคราะห์
- **AI chat** — ถามตอบเกี่ยวกับข้อมูล พร้อมสตรีมคำตอบและสถานะการทำงานผ่าน Server-Sent Events (SSE)
- **Analytics & visualization** — คำนวณด้วย pandas/DuckDB และนำเสนอผลผ่านกราฟกับ Dashboard
- **Traceable results** — เก็บ Metadata ของการวิเคราะห์ นิยาม Metric และข้อมูลประกอบการตรวจสอบผลลัพธ์
- **User workspace** — ระบบเข้าสู่ระบบ จัดการไฟล์ ประวัติแชท การตั้งค่า และโควตาการใช้งาน
- **Background processing** — Worker แยกจาก API สำหรับงาน ETL ตามเวลาและการส่งรายงาน
- **Billing integration** — โค้ดเชื่อม Stripe สำหรับ Subscription และจัดการสิทธิ์ตามแพ็กเกจ
- **ภาษาและหน้าจอ** — รองรับภาษาไทย/อังกฤษ พร้อม UI สำหรับ Desktop และ Mobile

ฟีเจอร์ที่พึ่งบริการภายนอกต้องมี Configuration และ Database schema ที่เกี่ยวข้อง การมีโค้ด Integration ไม่ได้หมายความว่ามีบริการจริงเปิดให้ทดลองใน Repository นี้

## Tech stack

| ส่วน | เทคโนโลยี |
| --- | --- |
| Frontend | Next.js 16 App Router, React 19, TypeScript |
| UI | Tailwind CSS, Motion, Recharts |
| Backend | Python, FastAPI, Pydantic |
| Data processing | pandas, DuckDB, PyArrow, SQLAlchemy |
| Authentication & data | Supabase Auth, PostgreSQL, Storage |
| AI | OpenAI-compatible API ผ่าน OpenAI Python SDK |
| Payments | Stripe |
| Testing | Vitest, Pytest, Playwright |
| Development & CI | Docker, Docker Compose, GitHub Actions |

## แนวทางออกแบบระบบ

```text
ผู้ใช้ → Next.js → FastAPI → เตรียมข้อมูล / ยืนยัน Mapping
                      │                 │
                      │          pandas / DuckDB
                      │                 │
                      │          ผลคำนวณ + Metadata
                      │                 │
                      │          LLM ช่วยอธิบายผล
                      │                 │
                      └────── SSE → Chat / Dashboard

Next.js / FastAPI ─── Supabase (Auth, Database, Storage)
FastAPI ──────────── Stripe
Background worker ── งานตามเวลา / ETL / ส่งรายงาน
```

- **แยกการคำนวณออกจากการสร้างคำตอบ** — ผลวิเคราะห์มีที่มาจาก Data processing ส่วน LLM ใช้ช่วยตีความและสื่อสาร ไม่ถือคำตอบจาก AI เป็นหลักฐานยืนยันความถูกต้องโดยลำพัง
- **ยืนยันความหมายของข้อมูลก่อนใช้** — Mapping และบริบทของ Dataset เป็นเงื่อนไขก่อนเรียกงานวิเคราะห์
- **แยกงานตามเวลาออกจาก HTTP request** — Worker ใช้ Process แยกจาก API
- **เก็บ Secret ฝั่ง Server** — Service role, LLM key และ Stripe secret อยู่ใน Backend configuration

## โครงสร้างโปรเจกต์

```text
app/                    Next.js routes, layouts และ providers
src/                    Views, components, hooks และ frontend utilities
backend/
  app/                  FastAPI routes, services และ worker
  supabase/             SQL migrations และคำอธิบายการตั้งค่า
  tests/                Backend tests และ fixtures
  requirements.txt      Python dependencies
public/                 Static assets
scripts/                Development และ validation scripts
e2e/                    Playwright tests
docs/                   เอกสาร workflow และ operations
.github/workflows/      CI workflows
```

## รันบนเครื่อง

### 1. เตรียมเครื่องและบริการ

ใช้ Node.js 20+ และ Python 3.11+ ตาม Runtime ที่โปรเจกต์กำหนด พร้อม Supabase project และ API key ของ LLM provider ที่รองรับ OpenAI-compatible API

เตรียม Database schema, Storage และ Auth ของ Supabase ก่อนใช้ฟีเจอร์ที่เกี่ยวข้อง ดู [คำแนะนำ SQL migrations](backend/supabase/README.md) และเงื่อนไขในแต่ละไฟล์ SQL ภายใต้ `backend/supabase/` รายการนี้มี Migration ที่ต่อยอดจาก Schema เดิม จึงไม่ควรถือว่าเป็นคำสั่ง Bootstrap ฐานข้อมูลว่างแบบครบชุด

Stripe, SMTP และบริการเสริมจำเป็นเฉพาะเมื่อใช้งานฟีเจอร์นั้น

### 2. ตั้งค่า Environment

รันจากโฟลเดอร์หลักด้วย PowerShell:

```powershell
Copy-Item .env.example .env.local
Copy-Item backend/.env.example backend/.env
```

| ไฟล์ | ค่าหลักที่ต้องตั้ง |
| --- | --- |
| `.env.local` | `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` |
| `backend/.env` | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `LLM_API_KEY`, `LLM_BASE_URL`, `FRONTEND_URL` |

หากใช้ตัวเชื่อม SQL/API ให้ตั้ง `CONNECTION_SECRET_KEY` สำหรับเข้ารหัสข้อมูลการเชื่อมต่อด้วย ตามคำอธิบายใน `backend/.env.example`

ค่าที่ขึ้นต้นด้วย `NEXT_PUBLIC_` จะถูกเปิดเผยให้ Browser เห็น ห้ามใส่ Service role หรือ Secret key ในตัวแปรกลุ่มนี้

### 3. เริ่ม Backend

เปิด Terminal แรกจากโฟลเดอร์หลัก:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

API documentation: [localhost:8000/docs](http://localhost:8000/docs)

บน macOS/Linux ใช้ `python3` สร้าง Virtual environment และใช้ `.venv/bin/python` แทน `.\.venv\Scripts\python.exe`

### 4. เริ่ม Frontend

เปิด Terminal ที่สองจากโฟลเดอร์หลัก:

```powershell
npm ci
$env:NEXT_DIST_DIR = '.next-local'
npx next dev
```

เปิด [localhost:3000](http://localhost:3000)

บน macOS/Linux ใช้ `npm run dev` ได้โดยตรง ส่วนคำสั่งด้านบนใช้กับ PowerShell เพราะ Script เดิมตั้ง Environment variable ด้วยรูปแบบ Shell ของ Unix

### 5. เริ่ม Worker เมื่อใช้งานตามเวลา

เปิด Terminal เพิ่มจากโฟลเดอร์หลัก:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.worker
```

Worker ต้องใช้ Environment และ Database migrations ที่ตรงกับฟีเจอร์งานตามเวลาที่เปิดใช้งาน

## คำสั่งตรวจสอบ

Frontend — รันจากโฟลเดอร์หลักหลังติดตั้ง Dependencies:

```powershell
npm test
npm run lint
npx tsc --noEmit
npm run build
```

Backend — รันจากโฟลเดอร์หลัก:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

มี Playwright tests ใน `e2e/` และ CI configuration ใน `.github/workflows/` การทดสอบแบบ Mock/Fixture ไม่ได้ยืนยันว่า Auth, Payments หรือบริการภายนอกทำงานครบวงจร ผลผ่านต้องอ้างอิงจากการรันกับ Revision และ Environment ที่ต้องการตรวจจริง

## ขอบเขตของ Portfolio

- ไม่มี Live demo หรือบัญชีทดลองแนบมากับสำเนานี้
- ไม่มีข้อมูลผู้ใช้จริง คีย์บริการ และประวัติ Commit จาก Repository ต้นฉบับ
- สำเนานี้ยังไม่ได้ติดตั้ง Dependencies หรือรันทดสอบระบบจริง จึงไม่ระบุผลผ่านหรือจำนวน Test
- การใช้ Database provider บางประเภทต้องติดตั้ง Driver เพิ่มตามรายการใน `backend/requirements.txt`
- Python analytics sandbox ต้องใช้ Runner ที่แยกจาก API และตั้งค่าก่อนเปิดใช้งาน
- เอกสาร Roadmap และ Operations ที่เหลือใน Repository เป็นบริบทการพัฒนา ไม่ใช่หลักฐานว่าระบบพร้อม Production

## เอกสารเพิ่มเติม

- [Database migrations](backend/supabase/README.md)
- [Conversational setup smoke checks](docs/conversational_setup_smoke.md)
- [Design notes](DESIGN.md)
- [Development roadmap](roadmapmataqorlab.md)

## สิทธิ์การใช้งาน

Repository นี้ยังไม่มีไฟล์ License กำหนดสิทธิ์ใช้งาน การเผยแพร่เพื่อแสดงผลงานไม่ได้ให้สิทธิ์นำไปใช้ แจกจ่าย หรือดัดแปลงโดยอัตโนมัติ หากต้องการนำไปใช้ให้ติดต่อเจ้าของ Repository
