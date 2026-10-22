# MataQorLab Master Product & Engineering Roadmap

> สถานะเอกสาร: Active roadmap
> ตรวจทานครั้งล่าสุด: 5 สิงหาคม 2026
> ขอบเขต: ประวัติสิ่งที่พัฒนาแล้ว งานแก้บั๊กและเพิ่มความเสถียร งานยกระดับระบบเดิม และเส้นทางสู่ Enterprise Grade
> เอกสารอ้างอิงสถานะเชิงลึก: [`README.md`](README.md)

เอกสารนี้เป็น Product/Engineering roadmap เท่านั้น ไม่ผูกกับดีล รูปแบบตัวแทนขาย vendor pool หรือข้อตกลงเชิงพาณิชย์รายใดรายหนึ่ง ERP ถูกมองเป็น Source/Connector category หนึ่งของแพลตฟอร์ม และทุกความสามารถต้องออกแบบให้ใช้ซ้ำกับหลายระบบ หลาย Vendor และหลายองค์กรได้

## 1. เป้าหมายของระบบ

MataQorLab คือ AI Analytical Intelligence Platform สำหรับเปลี่ยนข้อมูลธุรกิจจากไฟล์ ERP ฐานข้อมูล SQL และ REST API ให้เป็นข้อมูลที่ผ่านการเตรียม นิยาม Metric ที่ตรวจสอบได้ บทวิเคราะห์จากหลักฐาน Dashboard และการแจ้งเตือนอัตโนมัติ

หลักการที่ห้ามเปลี่ยนเมื่อพัฒนาต่อ:

1. Backend คำนวณก่อน และ LLM มีหน้าที่อธิบายผล ไม่สร้างตัวเลขธุรกิจเอง
2. ทุกผลลัพธ์สำคัญต้องย้อนกลับไปยัง Source, Mapping, Cleaning recipe, Formula, Filter และช่วงเวลาได้
3. การเปลี่ยนข้อมูลหรือเปิด Automation ต้องมีผู้ใช้อนุมัติและมี Audit
4. Source ที่หาย ว่าง หรือสิทธิ์ไม่ถูกต้องต้อง Fail closed และห้ามเขียนข้อมูลว่างทับงานเดิม
5. Tenant, Organization และ Workspace ต้องแยกข้อมูลกันทั้ง Backend, Database, Storage และ UI
6. Enterprise Grade หมายถึงระบบที่ตรวจสอบ กู้คืน และปฏิบัติการได้จริง ไม่ใช่เพียงมีฟีเจอร์ Enterprise ในหน้าจอ

## 2. วิธีอ่านสถานะ

| สัญลักษณ์ | ความหมาย |
|---|---|
| ✅ | พัฒนาแล้วและมีการทดสอบระดับหนึ่ง |
| 🟡 | พัฒนาแกนหลักแล้ว แต่ยังต้อง Hardening หรือทดสอบกับ Production |
| 🔴 | ยังไม่พัฒนา หรือมีเพียง UI/Contract |
| 🔍 | ต้องตรวจยืนยันซ้ำใน Environment จริง |

## 3. Baseline ที่ตรวจยืนยันล่าสุด

### 3.1 Repository และการทดสอบ

- Working tree อยู่ระหว่างพัฒนา Dashboard V4 และ Production hardening จึงยังไม่ควรใช้สถานะ Git เป็น Release evidence จนกว่าจะ Commit และให้ CI ผ่าน
- Backend: **369 tests passed** เมื่อ 5 สิงหาคม 2026
- Frontend: **115 tests passed** เมื่อ 5 สิงหาคม 2026
- Frontend unit tests มี 20 test files
- Backend มี 50 test modules
- Playwright มี 22 flows แต่รวมอยู่ใน spec เดียว และหลาย flow ใช้ Auth bypass หรือ mock API จึงยังไม่ใช่ Production integration coverage
- CI ตรวจ Frontend tests, ESLint, TypeScript, Next.js build, Playwright, Backend pytest/import smoke, dependency/secret scan, CodeQL SAST, container build/vulnerability scan และมี Staging Supabase gate แบบสั่งรัน

### 3.2 Live Supabase ที่ตรวจล่าสุด

- Live project อยู่ในสถานะ `ACTIVE_HEALTHY`
- Migration สำคัญที่ Apply แล้วรวมถึง:
  - `customer_experience_platform`
  - `smart_alert_evaluator`
  - `weekly_chat_delivery`
  - `etl_mapping_contract_hardening`
  - `etl_mapping_contract_hardening_anon_revoke`
- Security Advisor: 11 INFO และ 1 WARN
- WARN ที่ยังเปิดอยู่: `Leaked Password Protection Disabled`
- Performance Advisor: 58 INFO ประเภท unused index และไม่มี WARN
- Unused indexes ต้องประเมินใหม่หลังมี Workload จริง ห้ามลบเพียงเพราะยังไม่ถูกใช้ในช่วง Development

### 3.3 ข้อจำกัดของ Baseline

ผล Unit test ที่ผ่านไม่ได้ยืนยันว่า External service, SMTP, Stripe, ERP, OAuth, SAML, SCIM, Production worker, DNS และ Network policy ทำงานครบ จึงต้องมี Staging integration test และ Production smoke test แยกต่างหาก

## 4. สิ่งที่พัฒนาแล้วจนถึงปัจจุบัน

### 4.1 Product foundation

| Module | สถานะ | สิ่งที่มีแล้ว |
|---|---:|---|
| Public website และ Auth UI | ✅ | Landing, Pricing, Login, Register, Reset password, Thai/English และ Individual/Business separation |
| Authenticated app shell | ✅ | Sidebar รวม, deep links, protected routes, theme และ responsive layout |
| Plan และ Quota | ✅ | Free/Plus/Pro/Enterprise, server-owned entitlement, token/storage quota |
| Enterprise pricing | 🟡 | 99 USD/องค์กร/เดือน รวม 2 seats และ 39 USD/seat เพิ่ม พร้อม Stripe checkout/webhook code; ยังต้องทดสอบ Live payment ครบ lifecycle |
| Organization/Workspace | ✅ | Membership, roles, tenant constraints และ governed company memory |
| Customer Center | 🟡 | Onboarding, Data Health, Lineage, Collaboration, Alerts, Invitations, Integration/Embed contracts; provider integrations บางตัวยังไม่ใช่ของจริง |

### 4.2 Data sources และ ingestion

| Module | สถานะ | สิ่งที่มีแล้ว |
|---|---:|---|
| File sources | ✅ | CSV, Excel, JSON, Parquet, header detection และ large-data ingest |
| SQL sources | 🟡 | UI รองรับ 11 providers, test-before-save, read-only query path และ streaming; optional drivers ยังไม่ได้ติดตั้งครบทุก provider ใน default image |
| REST API | ✅ | Method, headers, body, pagination, nested JSON path discovery และ raw sync |
| Cloud spreadsheets | 🟡 | Google/Microsoft share/download link refresh; private OAuth connector ยังไม่เสร็จ |
| ERP connector | 🔴 | ยังไม่มี Connector SDK หรือ ERP-specific adapter ที่ผ่าน production-like integration test |
| Raw storage | ✅ | File upload และ DB/API sync เก็บ Raw ใน `business-data`; Cloud refresh ตั้งใจไม่คัดลอกต้นฉบับและเก็บผล Parquet |
| Unified storage quota | ✅ | Backend-only quota enforcement ครอบคลุมไฟล์ ข้อมูลระบบ ETL Chat Memory และ Visualization |

### 4.3 ETL, Mapping และ Data Contract

| Module | สถานะ | สิ่งที่มีแล้ว |
|---|---:|---|
| Mandatory preparation gate | ✅ | ห้ามเริ่มวิเคราะห์ Source ใหม่ก่อนยืนยัน ETL/Mapping และ Backend ตรวจซ้ำด้วย 422 |
| Adaptive Data Setup Copilot | ✅ | Source พร้อม/ไม่มี Prompt → Quick Scan → Structure → Mapping → Cleaning Preview → Adaptive Business Context → Review → Background Publish; บันทึกเฉพาะ metadata, มี progress/retry และ Apply `adaptive_data_setup_copilot` บน Live เป็น migration `20260805111750` แล้ว |
| Cleaning profiles | ✅ | Standard, Financial, Careful และ Deep Clean |
| User-approved ETL | ✅ | Preview, toggle rules, explicit imputation approval และ fail-closed critical fields |
| Versioned recipes | ✅ | Recipe version, publish, run history, quality alerts และ immutable Parquet output |
| Incremental scheduling | 🟡 | Cursor, cron/on-upload/manual, lease และ stable output identity; ต้องทดสอบกับ ERP cursor/late-arriving data จริง |
| Mapping memory | ✅ | Dataset-scoped mapping, owner RLS และ deterministic suggestions |
| Data Contract v2 | ✅ | Purpose, grain, primary metric และ natural keys เป็นหน้าหลัก; governance/causal controls อยู่ Advanced |
| Data reconciliation | 🔴 | ยังไม่มีหน้ากระทบยอด Source total กับ Published total แบบเป็นทางการ |

### 4.4 Analytics และ AI

| Module | สถานะ | สิ่งที่มีแล้ว |
|---|---:|---|
| Compute-first analytics | ✅ | pandas, DuckDB, deterministic SQL templates และ domain metrics |
| Semantic Metrics | ✅ | Revenue, Cost, Profit, Margin, Orders, Customers, AOV และ metric definition ต่อ Dataset |
| Structured findings | ✅ | Evidence, formula, SQL, columns, filters, period และ hashes |
| Numeric verification | ✅ | ตรวจตัวเลขในคำตอบและ correction retry ก่อนส่งผู้ใช้ |
| Decision assurance | ✅ | Claim/Evidence Graph, Confidence Matrix, evidence requests, event timeline และ causal eligibility |
| Forecast/scenario baseline | 🟡 | Deterministic monthly baseline และ sensitivity scenario; ยังไม่มี model lifecycle/backtesting แบบ ML product |
| Fact-safe memory | ✅ | เก็บ user-authored preferences และ verified facts ไม่เลื่อน generated prose เป็น fact |
| Governed company memory | ✅ | Typed/versioned records, approval, audit, expiry, archive และ rollback |
| Analytical benchmark | 🟡 | มี offline corpus; ต้องขยายเป็น Golden business datasets แยกตาม Domain/ERP |

### 4.5 Chat และ Visualization

| Module | สถานะ | สิ่งที่มีแล้ว |
|---|---:|---|
| Analytical Chat | ✅ | SSE streaming, intent routing, response modes, dataset/web/mixed analysis และ persistent transcript |
| Chat source context | ✅ | Conversation-scoped file/API/SQL context, mapping/cleaning metadata และ refresh recovery |
| Web evidence | ✅ | Multi-query search, source cards, citation verification และ persistence |
| Visualization proposal | ✅ | Chat ไม่วาดกราฟ snapshot โดยตรง แต่เสนอและสร้างรายงานใน Visualization workspace |
| Visualization intelligence | ✅ v1.1 | Semantic profile, intent detection, candidate scoring, evidence-backed Decision Insights และ enforceable Chart Guardrails ก่อน Render |
| Adaptive dashboard | ✅ V4 | Section-based Generative Presentation DSL, multi-widget, Story/Evidence, Design candidates, filters, drag/reorder/resize, customization และ full-source compute |
| Dashboard durability | 🟡 | แก้ source binding, zero-row false success และ destructive fallback แล้ว; ต้องเพิ่ม real-browser regression สำหรับ refresh/reopen/source replacement |
| Revision/Template/Share | ✅ | Undo/redo, revisions, templates, revocable read-only links และ view limits |
| Export | 🟡 | PNG และ browser print-ready PDF; ยังไม่มี server-side document-grade PDF/PPTX builder |
| Advanced drill-down | 🟡 | มี analytical drill-down บางส่วน แต่ยังไม่ครบทุก widget และ governed source-row flow |

#### 4.5.1 Visualization Intelligence v1 — Semantic → Intent → Candidates (อัปเดต 3 สิงหาคม 2026)

งานลำดับ 1–3 ที่ทำเสร็จแล้ว:

1. **Semantic Understanding:** Dashboard generation ใช้ Column Mapping และการ infer role จากข้อมูลจริงเพื่อแยก Temporal dimension, Categorical dimension, Measure และ Identifier พร้อม confidence, filter eligibility และ aggregation ที่แนะนำ เช่น Revenue ใช้ SUM, Price/Margin ใช้ AVG และ ID ไม่ถูกนำไป SUM
2. **Analysis Intent Detection:** ตรวจเป้าหมายจากคำสั่งไทย/อังกฤษก่อนสร้างกราฟ ครอบคลุม Overview, Trend, Ranking, Comparison, Distribution, Detail และรับรู้ Anomaly/Forecast เพื่อส่งต่อให้โมดูลขั้นสูงในอนาคต
3. **Candidate Generation + Scoring:** สร้าง Widget candidates และ Dashboard compositions หลายชุด แล้วให้คะแนน Semantic fit, Intent coverage, Chart diversity, Cardinality, ความซ้ำซ้อน และ readability ก่อนเลือกชุดที่ดีที่สุด

ทั้ง Auto Dashboard และ AI Dashboard Planner ใช้ Quality scorer ชุดเดียวกัน LLM จึงเป็นเพียง candidate และจะไม่ถูกเลือกเมื่อมี identifier aggregation, non-temporal trend, pie cardinality ไม่เหมาะสม หรือคะแนนต่ำกว่า deterministic candidate อย่างมีนัยสำคัญ Response ส่ง `analysis_intent`, semantic metadata, candidate scores และ selected composition เพื่อรองรับ Audit/Telemetry โดย Frontend แสดง Intent และคะแนนของ Active spec แล้ว

Regression coverage ปัจจุบันตรวจ Semantic type/aggregation, ภาษาไทย, จำนวน candidates/compositions, การห้าม SUM identifier, การลงโทษ line chart ที่ไม่ใช่เวลา และ metadata จาก generation จริง งาน v2 ที่ยังเหลือคือ Domain dashboard templates, user/organization feedback learning, explainable recommendation UI, histogram/scatter/correlation, anomaly/forecast widgets และ quality telemetry จากการใช้งานจริง

#### 4.5.2 Insight-driven Composition + Chart Guardrails (ข้อ 5–6)

Dashboard ที่ Generate ใหม่มีชั้น Decision Insights ซึ่งคำนวณจาก Aggregate results ที่ผ่าน Backend แล้ว ไม่ให้ LLM แต่งตัวเลข ประกอบด้วยตัวขับเคลื่อนหลักและ Contribution, การเปลี่ยนแปลงระหว่างช่วงที่สูงสุด, Potential anomaly candidate ที่ใช้ deterministic robust-change rule และ Recommended next check ที่อ้างกลับไปยัง Widget/Evidence เดิม คำว่า anomaly เป็นสัญญาณให้ตรวจสอบ ไม่ใช่ข้อสรุปเชิงเหตุเป็นผล

ทุก Widget มี `purpose` เช่น Trend, Ranking, Comparison, Distribution หรือ Detail เพื่อบังคับให้ composition ครอบคลุม KPI → Trend → Driver/Mix → จุดที่ควรตรวจ → Detail แทนการเลือกกราฟที่คะแนนสูงแบบซ้ำมุมกัน

Chart Guardrails เปลี่ยนจากการเตือนอย่างเดียวเป็นการบังคับก่อน Query/Render:

- ลบ SUM/AVG บน Identifier แทนการแสดงตัวเลขที่ทำให้เข้าใจผิด
- แปลง Line/Area ที่ไม่มี Temporal dimension เป็น Bar
- แปลง Pie ที่มีมากกว่า 10 หมวดเป็น Bar/Top-N
- ลบกราฟซ้ำและกราฟที่ Dimension มีค่าเดียว
- จำกัดกราฟไม่เกิน 8 ใบต่อ Decision Dashboard และส่ง Guardrail decisions กลับเพื่อ Audit/UI

Frontend แสดง Decision Insight cards, Intent/Quality score และจำนวนรายการที่ Guardrail แก้ไขแล้ว งานต่อคือ Drill-through จาก Insight card ไปยัง Source rows, baseline แบบ seasonal สำหรับ anomaly, user acknowledgement/feedback และ telemetry ว่า Insight ใดนำไปสู่ action จริง

#### 4.5.3 Dashboard Schema V4 — Governed Generative Presentation (อัปเดต 5 สิงหาคม 2026)

V4 เปลี่ยน Dashboard จากรายการ Widget แบบแบนเป็น Presentation DSL ที่ยังตรวจสอบและแก้ไขได้ โดย Spec ประกอบด้วย `presentation`, `sections`, `story`, `filters`, `kpis` และ `widgets` ระบบยังเก็บ Flat widgets เพื่อให้ Compute, Filter, Editor และรายงาน V3 เดิมทำงานต่อได้ รายงาน V2/V3 จะถูก Upgrade เป็น V4 อัตโนมัติเมื่อ Generate/Save โดยไม่ต้องทำ Database migration เพราะ `dashboard_spec` เป็น versioned JSONB

ความสามารถที่เสร็จแล้ว:

- Component Registry สำหรับ Section layouts: Hero, Featured, Balanced, Dense และ Detail โดยไม่เปิดให้ LLM ส่ง HTML/React/CSS
- Presentation variants 3 แบบ: Executive Story, Analytical Deep Dive และ Operational Monitoring
- Design candidates 3 ชุดพร้อม Semantic score, Presentation score และ Overall quality judge; ผู้ใช้ Preview และเลือกในโหมด Customize ได้
- Evidence-grounded Story มี Headline, Summary, Chapters และ Evidence IDs จาก Query context, KPI formula/value, Widget aggregates และ Decision Insights เท่านั้น
- Evidence drawer ให้ผู้ใช้ตรวจสูตร จำนวนจุด Aggregate จำนวนแถว/Filter scope และที่มาของ Narrative
- Section editor เปลี่ยนชื่อ/รูปแบบ Section, เปลี่ยน Variant, ลาก/เพิ่ม/ลบ/ย่อขยาย Widget และบันทึก V4 ได้
- เพิ่ม Pareto component สำหรับ Contribution/Cumulative share เมื่อ Pie ไม่เหมาะ พร้อม Guardrails และ full-source aggregate เดิม
- AI Planner ต้องส่ง V4 DSL และ Story blueprint แต่ไม่มีสิทธิ์แต่ง Narrative facts; Runtime Story สร้างจาก verified evidence หลัง Compute
- Shared Dashboard ล้าง Source identity และตัด Table evidence เมื่อ Share ไม่อนุญาต Detail rows

V4 นี้ตั้งใจเป็น **อิสระภายในระบบที่กำกับได้** ไม่ใช่ Arbitrary HTML จึงรักษา Filter, Refresh, Theme, Export, Accessibility, Audit และ Numeric correctness ได้ งานหลัง V4 คือเพิ่ม Histogram/Scatter/Heatmap/Waterfall, Section drag ข้ามกลุ่ม, narrative localization ที่ละเอียดขึ้น, feedback learning และ visual regression บนอุปกรณ์จริง

### 4.6 Automation และ delivery

| Module | สถานะ | สิ่งที่มีแล้ว |
|---|---:|---|
| ETL scheduler | ✅ | FastAPI lifespan loop, atomic lease, cron, on-upload, run now, pause และ history |
| Dedicated worker deployment | 🔴 | Production ยังต้องแยก worker ออกจาก Web API เพื่อไม่ให้ restart กระทบงาน |
| Guardrails | ✅ | Freshness, complete period, fingerprint, KPI/row change, cooldown, severity และ recipient opt-in |
| Scheduled email | 🟡 | SMTP delivery, deterministic fallback และ telemetry มีแล้ว; ยังต้องตั้ง Production SMTP และทดสอบจริง |
| Weekly AI to Chat | ✅ | เลือกวันจันทร์–อาทิตย์, หนึ่ง active destination ต่อ Dataset และ exact-once fingerprint |
| Smart Alerts | 🟡 | Evaluator, lease, baseline, cooldown, in-app/email/webhook evidence มีแล้ว; Production flag ยังปิดโดย default |
| Slack/Teams delivery | 🟡 | Fixed server webhook สำหรับทดสอบมีแล้ว; OAuth installation ต่อ Organization ยังไม่เสร็จ |
| Dead-letter/replay console | 🔴 | ยังไม่มีหน้ารวมงานล้มเหลวและสั่ง Replay แบบปลอดภัย |

### 4.7 Security, billing และ operations

| Module | สถานะ | สิ่งที่มีแล้ว |
|---|---:|---|
| RLS/Storage hardening | ✅ | Owner/tenant policies, explicit grants, backend-only privileged RPC และ protected upload paths |
| Column security | ✅ | Browser แก้ profile ได้เฉพาะ field ที่อนุญาต; plan/quota เป็น server-owned |
| Stripe billing | 🟡 | Signed webhook, seat pricing, idempotent organization provisioning และ invoice history; ยังต้อง Live lifecycle test |
| SAML/SCIM | 🔴 | มี configuration contract/UI แต่ยังไม่มี production SAML ACS/metadata และ SCIM provisioning endpoints |
| MFA | 🔴 | ยังไม่มี end-user enrollment/challenge/enforcement flow ครบวงจร |
| Internal Admin | 🔴 | ยังไม่มี Enterprise-grade `/internal-admin` |
| Observability | 🟡 | Health/readiness, request ID, timing และ delivery telemetry มีแล้ว; ยังไม่มี centralized traces/metrics/logs และ alerting ครบ |
| Backup/restore | 🔴 | ยังไม่มีหลักฐาน Restore drill ของ Database และ Storage |

## 5. บั๊กที่แก้แล้วและต้องล็อกด้วย Regression Tests

รายการนี้ไม่ถือว่าเป็นบั๊กเปิด แต่เป็นพื้นที่ที่เคยเกิด Regression และต้องห้ามกลับมาอีก:

1. บันทึก Visualization แล้ว Source, กราฟ, Filter หรือจำนวนแถวหายหลัง Refresh/Reopen
2. รายงานแสดงสร้างสำเร็จทั้งที่ Full-source generation ได้ 0 แถว
3. Failed refresh เขียน empty schema ทับ widgets/filters เดิม
4. Chat Source context หายเมื่อสลับห้องหรือ Refresh
5. Mapping/ETL gate ถูกข้ามจาก stale client
6. LLM เสนอ field ที่ไม่มีอยู่จริงหรือสร้างกราฟจาก preview แทน full dataset
7. Python 3.11 container เริ่มไม่ได้จาก syntax ที่รองรับเฉพาะ Python ใหม่กว่า
8. Docker dependency volume เก่าไม่ตรงกับ lockfile
9. Token quota ถูกนับซ้ำระหว่าง legacy trigger และ Backend
10. Scheduled delivery หรือ Chat delivery ส่งซ้ำเมื่อ Worker retry

ทุกข้อข้างต้นต้องมี Unit + Integration หรือ Browser regression ที่จำลอง Restart/Refresh/Retry ไม่ใช่ตรวจเฉพาะ happy path

### 5.1 Open Bug Register เริ่มต้น

ณ วันที่ตรวจ เรายังไม่มีรายการบั๊ก Functional ที่เปิดอยู่พร้อมขั้นตอนทำซ้ำใน Repository กลาง การที่ Unit tests ผ่านไม่ได้แปลว่าไม่มีบั๊กจาก Browser, Environment หรือข้อมูลจริง ดังนั้นบั๊กที่พบระหว่างใช้งานต้องเพิ่มในตารางนี้ทันที ห้ามเก็บไว้เฉพาะในแชท

| ID | Severity | สถานะ | อาการ/ขอบเขต | Evidence ที่ต้องมี |
|---|---:|---|---|---|
| SEC-001 | P0 | Confirmed | Supabase Leaked Password Protection ยังปิด | Advisor result และภาพ/ค่าหลังแก้ |
| OPS-001 | P0 | Confirmed | Production SMTP/Stripe/Worker ยังไม่ได้ตั้งและทดสอบจริง | Smoke-test run IDs และ provider events |
| REL-001 | P0 | Verified/Closed | Real E2E ครบ Next.js → FastAPI → Supabase/Storage ตามการทดสอบล่าสุด | เก็บ CI run และ test evidence ทุก Release |
| REL-002 | P1 | Hardening in progress | Critical Source/Save/Scheduler/Billing paths ใช้ structured event/error taxonomy แล้ว; ยังต้อง audit module รอง | JSON events, incident IDs และ regression tests |
| BUG-001 | P1 | Verified/Closed | ใช้ Filter ใน Adaptive Dashboard แล้วกราฟ/ข้อมูลว่างจนต้อง Refresh | Backend + Playwright filter/save/reopen regression ผ่าน |
| BUG-002 | P1 | Verified/Closed | Export PNG/PDF ล้มด้วย `SecurityError: Cannot access rules` เมื่อมี cross-origin stylesheet | `skipFonts`, unit regression และ Browser retest ผ่าน |

บั๊กใหม่ให้ตั้งรหัส `BUG-###` พร้อม Environment, User/Organization, Source identity, Dataset key, Request/Run ID, เวลา, ขั้นตอนทำซ้ำ, Expected/Actual, Screenshot/Log และ Regression test ที่จะป้องกันไม่ให้กลับมาอีก

## 6. จุดเสี่ยงเชิงเทคนิคที่พบในการตรวจรอบนี้

### P0 — ต้องจัดการก่อน Controlled Production Beta

1. **E2E ต้องคงหลักฐานต่อเนื่อง**: Flow จริงผ่านแล้ว แต่ต้องรันซ้ำบน Staging ทุก Release และเก็บ run/evidence ไม่ให้กลายเป็นการทดสอบครั้งเดียว
2. **Staging release gate ยังไม่ครบ**: มี Supabase schema lint และ read-only Data API/Storage/Auth/RLS smoke แล้ว แต่ยังขาด migration upgrade/fresh-install, Stripe webhook และ SMTP/worker smoke
3. **Dedicated Worker รอ deploy จริง**: API และ Worker แยก lifecycle ในโค้ด/Compose แล้ว แต่ Production ต้อง deploy เป็นคนละ service และเก็บ heartbeat/restart evidence
4. **Leaked Password Protection ยังปิด**: เป็น Security Advisor WARN ที่ยืนยันแล้ว
5. **ไม่มี Restore evidence**: Database backup ไม่เพียงพอสำหรับ Storage objects ต้องมี Storage backup/restore runbook แยก
6. **Production credentials ยังไม่ครบ**: SMTP, Stripe Live, HTTPS frontend/API, Slack/Teams และ OAuth provider credentials
7. **Error observability ยังต้องขยาย**: Critical Source/Save/Scheduler/Billing paths มี correlation ID, structured event และ error taxonomy แล้ว แต่ module รองยังต้อง audit ต่อ

### P1 — ต้องแก้ระหว่าง Production Hardening

1. Backend pin direct dependencies แล้ว; ระยะถัดไปควรเพิ่ม transitive lock/constraints และกระบวนการอัปเดตเป็นรอบ
2. ไฟล์สำคัญมีขนาดใหญ่ เช่น `routes.py`, `visualizations.py`, `Chat.tsx`, `ChatMessageList.tsx` และ `ChatModals.tsx` ทำให้แก้บั๊กแล้วกระทบหลาย flow
3. Critical paths ย้ายจาก `print`/silent fallback ไป structured logging แล้ว แต่ `except Exception` ใน module รองยังต้องแยก intentional fallback ออกจาก failure ที่ต้องหยุดงาน
4. ไม่มี Code coverage threshold และ Mutation/contract tests สำหรับ calculation-critical code
5. Optional database drivers ยังไม่อยู่ใน Production image ครบทุก Provider ที่ UI ประกาศรองรับ
6. Frontend/Backend API types ยังไม่มี generated contract กลางจาก OpenAPI
7. มี error taxonomy และ customer-facing incident ID กลางแล้ว; ระยะถัดไปคือเชื่อมเข้ากับ error tracking/tracing และ support console

### P2 — Technical debt ระยะกลาง

1. แยก domain modules และ route groups ให้เล็กลง
2. แยก Dashboard renderer, editor state, persistence และ source resolver ออกจากกันชัดเจน
3. สร้าง Connector SDK และ contract tests กลาง
4. ย้าย cache/local agent state ที่จำเป็นต่อหลาย instance ไป shared backend
5. เพิ่ม performance budgets สำหรับไฟล์ 500 MB, SQL 10M rows และ dashboard cardinality สูง

## 7. Roadmap การพัฒนาจากปัจจุบันถึง Enterprise Grade

ช่วงเวลาเป็นประมาณการสำหรับการโฟกัสเต็มเวลา โดยต้องปรับตามขอบเขต ERP, จำนวนคนในทีม และผลของ Stability audit ห้ามใช้วันที่เป็นคำสัญญากับลูกค้าก่อนผ่าน Release Gate

### Phase 0 — Stability Freeze

**ระยะเวลา:** 1–2 สัปดาห์
**เป้าหมาย:** หยุดเพิ่มฟีเจอร์กว้าง ๆ และทำให้ Flow ที่มีอยู่เชื่อถือได้

- สร้าง Bug intake template: Environment, User/Org, Source, Dataset key, Request ID, Steps, Expected, Actual และ evidence
- เพิ่ม Regression tests สำหรับ 10 จุดที่เคยพังในหัวข้อ 5
- แยก P0/P1/P2 bug และกำหนด Owner/สถานะ/วันที่ตรวจซ้ำ
- เพิ่ม real integration tests สำหรับ Supabase Auth, RLS, Storage และ migrations บน Staging
- เพิ่ม flow จริง Upload/API/SQL → Adaptive Setup → Background Publish → Chat → Visualization → Save → Refresh → Reopen
- เพิ่ม flow จริง API/SQL Sync → ETL → Publish → Scheduled run
- ตรวจ broad exception ทุกจุดที่เกี่ยวกับ Source, Save, Billing และ Scheduler; ห้ามกลืน error โดยไม่มี structured event
- Pin Python dependencies และเพิ่ม lock/constraints strategy
- เพิ่ม `typecheck`, coverage report, dependency scan, secret scan และ container build ใน CI
- เปิด Leaked Password Protection และ Run Security/Performance Advisor ซ้ำ

**Release Gate:**

- P0 bug เปิดอยู่เป็นศูนย์
- Unit/Integration/E2E ผ่านบน clean environment
- Refresh/Retry/Restart ไม่ทำให้ข้อมูลหรือ layout หาย
- ไม่มี Critical/High security finding
- Migration ใหม่ทดสอบทั้ง upgrade และ fresh install

### Phase 1 — Production-ready Foundation

**ระยะเวลา:** สัปดาห์ 2–4
**เป้าหมาย:** ทำ Environment และ Operations ให้พร้อมสำหรับการทดสอบระบบจริงแบบควบคุม โดยไม่ผูกกับลูกค้าหรือ Vendor รายใด

- แยก Development, Staging และ Production Supabase projects
- Deploy Web, API และ Worker เป็นคนละ service/process
- Worker มี heartbeat, lease metrics, graceful shutdown และ missed-run recovery
- ตั้ง SMTP จริงและทดสอบ Invitation, Scheduled report, failure และ open telemetry
- ตั้ง Stripe Test/Live แยกกันและทดสอบ Checkout, Invoice paid/failed, seat change, cancellation และ duplicate event
- ใช้ centralized structured logs พร้อม request/job/run/correlation IDs
- เพิ่ม Error tracking และ OpenTelemetry traces/metrics/logs
- สร้าง Database + Storage backup policy และทำ Restore drill
- สร้าง incident response, rollback และ credential rotation runbooks
- กำหนด internal SLO หลังมี baseline จริง โดยยังไม่ประกาศ SLA ต่อสาธารณะ

**Release Gate:**

- Production-like staging ทำงานต่อเนื่องอย่างน้อย 7 วัน
- Scheduled job ไม่ส่งซ้ำและกู้จาก worker restart ได้
- Restore drill ผ่านและบันทึก RPO/RTO ที่วัดจริง
- Stripe/SMTP smoke tests ผ่าน
- Security Advisor ไม่มี WARN ที่ยังไม่ได้รับการยอมรับอย่างเป็นลายลักษณ์อักษร

### Phase 2 — ERP & Connector Compatibility Layer

**ระยะเวลา:** สัปดาห์ 4–8
**เป้าหมาย:** สร้างมาตรฐาน Connector กลางและพิสูจน์ว่าสามารถเชื่อม ERP/API/Database แบบ Read-only ได้โดยไม่เขียน Logic ผูกกับ Vendor รายเดียว

- กำหนด Connector Contract: auth, schema discovery, preview, full sync, cursor sync, retry, pagination, rate limit, health และ lineage
- สร้าง Reference ERP adapter ตัวแรกจาก API หรือ Read-only database เพื่อทดสอบ Connector Contract
- สร้าง Google/Microsoft private-file OAuth ด้วย Authorization Code + PKCE โดย FastAPI แลกและ Refresh token ฝั่ง Server เท่านั้น
- เพิ่ม Google Picker/Drive file selection ด้วย scope ขั้นต่ำ `openid`, `email`, `drive.file` และ offline access
- เพิ่ม Microsoft file selection ด้วย `openid`, `profile`, `email`, `offline_access`, `Files.Read`; ขอ `Files.Read.All`/`Sites.Read.All` เมื่อ Use case จำเป็นและได้รับอนุมัติเท่านั้น
- เพิ่ม Cloud OAuth endpoints สำหรับ authorize, callback, account list, disconnect, provider file list และสร้าง Cloud Dataset จาก Picker
- เก็บ Provider secret/refresh token แบบเข้ารหัส ห้ามส่งให้ Browser หรือเก็บใน `NEXT_PUBLIC_*`
- เข้ารหัส credentials ฝั่ง Server และรองรับ rotation/revocation
- เพิ่ม schema drift, deleted/late-arriving record และ backfill handling
- สร้าง Data Reconciliation: Source rows/totals เทียบ Raw, Cleaned และ Published
- สร้าง Golden Dataset และ Golden KPI 3–5 ตัวร่วมกับเจ้าของข้อมูลหรือ Domain reviewer
- ทดสอบ timezone, fiscal period, currency, VAT, discount, cancellation และ returns
- Run Shadow reporting เทียบรายงาน ERP เดิมอย่างน้อยสองรอบ
- ห้าม Write-back เข้า ERP ใน Release นี้

**Release Gate:**

- Golden KPI mismatch เป็นศูนย์ตามนิยาม Metric และ Test fixture ที่อนุมัติ
- Incremental sync ไม่ตกหล่นและไม่สร้างข้อมูลซ้ำ
- Schema drift แจ้งเตือนและหยุดอย่างปลอดภัย
- Mapping, Metric และรายงานผ่าน Acceptance test ที่บันทึกเป็นหลักฐาน

### Phase 3 — Controlled Production Beta

**ระยะเวลา:** สัปดาห์ 8–12
**เป้าหมาย:** ทดสอบกับ Controlled tenants โดยมี Operations รองรับครบวงจร

- Guided onboarding จาก Source ถึง Dashboard แรก
- Executive dashboard และ Explain This Number ที่ครบ Formula/Source/Filter/Freshness
- Dashboard drill-down ถึง governed source rows
- Data Health actions สำหรับ stale source, failed refresh และ schema drift
- Smart Alert และ Scheduled Chat/Email พร้อม replay/failed-job console
- Organization roles, invitations, seats และ billing self-service ครบ
- Internal Admin MVP สำหรับค้นผู้ใช้/องค์กร ดูสถานะ Usage/Jobs และ Audit
- Data export, account deletion และ retention workflow
- Support runbook, status communication และ customer incident IDs
- Accessibility, Thai/English copy และ mobile regression

**Release Gate:**

- Beta tenants ผ่าน cross-tenant isolation tests
- Support สามารถวินิจฉัย failed sync/job จาก Request/Run ID ได้
- ไม่มีข้อมูลหายจาก refresh, retry หรือ deploy
- มี Usage/Cost dashboard ต่อ Organization
- Production-like tenant อย่างน้อยหนึ่งชุดใช้งานรอบรายงานครบวงจรสำเร็จ

### Phase 4 — Enterprise Beta

**ระยะเวลา:** เดือน 3–5
**เป้าหมาย:** รองรับ IT/Admin ขององค์กรและการตรวจสอบความปลอดภัย

- MFA enrollment, challenge, recovery และ Backend/RLS enforcement
- SAML SSO: metadata, ACS, certificate rotation, domain verification และ IdP tests
- SCIM: Users/Groups provisioning, deprovisioning, idempotency และ audit
- Slack/Teams OAuth ต่อ Organization พร้อม encrypted token storage
- Role matrix แบบ least privilege และ periodic access review
- Session revocation, device/session view และ step-up authentication
- Internal Admin Production Operations: suspend/reactivate, feature flags, quota/job/email/billing monitoring
- Approval workflow สำหรับ privileged actions
- Consent-based, time-limited impersonation พร้อมเหตุผลและ audit
- OWASP ASVS 5.0 Level 2 verification และ external penetration test
- DPA, subprocessor list, retention/deletion policy, incident policy และ PDPA/legal review โดยผู้เชี่ยวชาญ
- Full server-side PDF Report Builder; PPTX ทำเมื่อมี customer requirement ที่ยืนยันแล้ว

**Release Gate:**

- MFA/SSO/SCIM happy path และ revocation path ผ่าน
- Privilege escalation และ cross-tenant tests ผ่าน
- ทุก privileged action มี immutable audit
- High/Critical findings จาก security review ถูกปิด
- Backup/restore และ incident tabletop drill ผ่าน

### Phase 5 — Enterprise General Availability

**ระยะเวลา:** เดือน 5–8
**เป้าหมาย:** รองรับหลายองค์กรด้วยกระบวนการมาตรฐานโดยไม่ต้องแก้โค้ดเฉพาะ Vendor หรือลูกค้าแต่ละราย

- Connector SDK พร้อม versioned interface และ certification tests
- ERP connector แรกเป็น Productized connector ไม่ใช่ custom script
- Embedded/white-label analytics พร้อม tenant-scoped token และ branding policy
- Standard tenant/embed provisioning และ usage reconciliation ที่ไม่ผูกกับ Vendor รายเดียว
- Billing dunning, proration, tax/VAT decision, credit/refund controls และ seat reconciliation
- Customer-facing audit export, status page และ support SLA process
- Capacity/load tests ตาม dataset/concurrency tiers
- Disaster recovery plan พร้อมรอบทดสอบตามกำหนด
- SLO ผ่านต่อเนื่องอย่างน้อย 30 วันก่อนประกาศ SLA
- Documentation สำหรับ Admin, Analyst, Security และ API/Connector developer

**Release Gate:**

- Onboard องค์กรใหม่ได้โดยไม่แก้โค้ดเฉพาะราย
- Operational metrics และ alerting ครบทุก critical path
- Support/billing/security runbook ใช้งานได้โดยคนอื่นนอกจากผู้พัฒนาหลัก
- Enterprise checklist ได้รับการ sign-off

### Phase 6 — Scale, Ecosystem และ ML

**ระยะเวลา:** เดือน 8–12+
**เป้าหมาย:** ขยาย Connector และเพิ่ม Intelligence ที่พิสูจน์คุณค่าได้

- Connector marketplace สำหรับ ERP, CRM, E-commerce, Ads และ Accounting
- Forecasting ที่มี backtesting, baseline comparison และ model monitoring
- Anomaly detection ที่แยก seasonal/business rule จาก model anomaly
- Customer/product segmentation พร้อม explainability
- Model registry, dataset/model version, drift และ approval lifecycle
- Cost-aware workload routing และ priority queues เมื่อปริมาณงานเกินความสามารถของ DB lease worker
- Multi-region/data residency ทำเมื่อมีสัญญาลูกค้าหรือข้อกำหนดจริง
- Write-back/closed-loop action ทำเฉพาะหลังผ่าน approval, authorization และ rollback design

### 7.1 งานคงค้างที่ย้ายมาจาก README และ Phase เจ้าของงาน

ตารางนี้เป็นดัชนีรวมของงานอนาคตที่เคยกระจายอยู่ใน `README.md` หลังการย้าย README จะเก็บเฉพาะวิธีติดตั้ง การตั้งค่า และสถานะสิ่งที่พัฒนาแล้ว ส่วนรายการด้านล่างต้องติดตามจากเอกสารนี้เท่านั้น

| งานเดิมจาก README | สถานะปัจจุบัน | Phase หลัก | Release Gate |
|---|---|---:|---|
| Production SMTP สำหรับ Invitation/Notification/Scheduled report | Code มีแล้ว ยังไม่ตั้ง Production | Phase 1 | ส่งจริงและบันทึก delivered/failed/open evidence ได้ |
| Dedicated ETL/Smart Alert worker | Loop/lease มีแล้วแต่ผูกกับ Web lifecycle | Phase 1 | Restart Web ไม่หยุด/ส่งงานซ้ำ และ Worker มี heartbeat |
| Stripe Live configuration และ subscription lifecycle | Checkout/Webhook code มีแล้ว | Phase 1 | Checkout, paid/failed invoice, seat change, cancel และ duplicate event ผ่าน |
| Google/Microsoft private-file OAuth | รองรับเพียง public/share link | Phase 2 | PKCE, encrypted token, picker, refresh, disconnect และ revoke ผ่าน |
| Guided onboarding และ sample/empty-state journey | Customer Center foundation มีแล้ว | Phase 3 | Source → Mapping → verified Dashboard สำเร็จใน Flow เดียว |
| Customer Organization Center self-service | Tenancy/roles/seat foundation มีแล้ว | Phase 3 | Invite, role, workspace, seat และ billing flow ผ่าน |
| Explain This Number | Lineage/audit foundation มีแล้ว | Phase 3 | KPI/Chart ย้อนถึง Formula, Source, Filter, Freshness และ drivers ได้ |
| Smart Alerts Center | Evaluator/Test action มีแล้ว | Phase 1 และ 3 | Dedicated worker, delivery, history, mute, cooldown และ replay ผ่าน |
| Collaboration | Data contract/API foundation มีแล้ว | Phase 3 | Comment, mention, assignment, approval และ context audit ผ่าน |
| Executive View | Dashboard/share foundation มีแล้ว | Phase 3 | Mobile read-only daily/weekly view ผ่าน accessibility/regression |
| Dashboard drill-down | มี analytical drill-down บางส่วน | Phase 3 | ทุก widget ที่ประกาศรองรับเปิด contributor/source rows แบบ governed ได้ |
| Embedded/white-label analytics | Embed contract foundation มีแล้ว | Phase 5 | Tenant token, domain allowlist, branding, revoke และ audit ผ่าน |
| Connector marketplace | ยังไม่มี SDK/marketplace | Phase 6 | Connector SDK/certification และ connectors ที่ผ่าน conformance tests |
| Data Health remediation | แสดง health projection ได้บางส่วน | Phase 3 | stale/failed/drift/missing/anomaly มีเหตุผลและ action แก้ไข |
| Slack/Teams OAuth installation | มี fixed server webhook สำหรับทดสอบ | Phase 4 | Organization install, encrypted token, revoke, retry และ audit ผ่าน |
| SAML SSO | มี UI/configuration contract | Phase 4 | Metadata/ACS/certificate rotation/domain verification/IdP tests ผ่าน |
| SCIM provisioning | มี UI/configuration contract | Phase 4 | Users/Groups provision/deprovision/idempotency/audit ผ่าน |
| Internal Admin MVP | ยังไม่มี route ที่เปิดใช้งาน | Phase 3 | Staff auth, search/view, tester override, account status และ audit ผ่าน |
| Internal Admin Production Operations | ยังไม่มี | Phase 4 | Billing/support/suspend/feature flags/usage/jobs/errors/email monitoring ผ่าน |
| Enterprise-grade Admin Support | ยังไม่มี | Phase 4 | Approval, refund scope, consent impersonation, ticket reason, revoke และ security review ผ่าน |
| Security/incident/backup/access review | ทำบางส่วน | Phase 1 และ 4 | Advisor/ASVS, incident runbook, restore drill และ staff access review ผ่าน |

Cloud OAuth server-only configuration ที่ต้องเพิ่มเมื่อเริ่ม Phase 2:

```env
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=https://api.example.com/api/v1/cloud-oauth/google/callback

MICROSOFT_OAUTH_CLIENT_ID=
MICROSOFT_OAUTH_CLIENT_SECRET=
MICROSOFT_OAUTH_TENANT=common
MICROSOFT_OAUTH_REDIRECT_URI=https://api.example.com/api/v1/cloud-oauth/microsoft/callback

CLOUD_TOKEN_ENCRYPTION_KEY=
```

Planned Cloud OAuth API contract:

```text
GET  /api/v1/cloud-oauth/{provider}/authorize
GET  /api/v1/cloud-oauth/{provider}/callback
GET  /api/v1/cloud-oauth/accounts
POST /api/v1/cloud-oauth/{provider}/disconnect
GET  /api/v1/cloud-oauth/google/files
GET  /api/v1/cloud-oauth/microsoft/files
POST /api/v1/cloud-datasets/from-picker
```

Phase 1 Production configuration checklist ที่ย้ายมาจาก README:

```env
# Scheduled email/invitations/notifications
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_FROM_NAME=MataQorLab
SMTP_USE_TLS=true
DELIVERY_PUBLIC_BASE_URL=https://api.example.com

# Enterprise billing
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
FRONTEND_URL=https://app.example.com

# Enable only after its migration exists in the target database
SMART_ALERT_SCHEDULER_ENABLED=true
```

- `SMTP_FROM_EMAIL` ต้องเป็น Sender ที่ Provider ยืนยันแล้ว และ Secret ต้องอยู่ฝั่ง Server เท่านั้น
- Stripe webhook ต้องชี้ไปที่ `/api/v1/stripe/webhook` และรับอย่างน้อย `checkout.session.completed`, `invoice.payment_succeeded` และ `customer.subscription.deleted`
- หลังแก้ Environment variables ต้อง Restart/Redeploy FastAPI และบันทึก Smoke-test evidence
- Smart Alert flag ต้องเปิดเฉพาะ Environment ที่ Apply `smart_alert_evaluator.sql` แล้ว
- Production ต้องมี ETL/Alert worker อย่างน้อยหนึ่ง Process ที่รันต่อเนื่อง แยกจาก Web API ตาม Phase 1

## 8. Master Backlog แยกตาม Workstream

### 8.1 Reliability และ Bug Management

- [x] สร้าง Bug registry กลาง, Severity definition, intake template และ postmortem template
- [x] เพิ่ม correlation ID ตั้งแต่ Browser → API → Job logs พร้อม incident response ที่ไม่เปิดเผย internal error
- [ ] เพิ่ม replayable fixtures สำหรับไฟล์/API/SQL/ERP
- [ ] ทดสอบ network timeout, partial upload, duplicate event และ stale session
- [ ] ทดสอบ browser refresh/back/forward และหลาย tab
- [ ] เพิ่ม chaos tests สำหรับ worker kill และ dependency outage
- [x] กำหนด P0 response process และ postmortem template

### 8.2 Architecture และ Code Health

- [ ] แยก `backend/app/api/routes.py` ตาม domain
- [ ] แยก `visualizations.py` เป็น source, planner, compute, persistence และ sharing services
- [ ] แยก Chat view/message/modal state เพื่อลดไฟล์ขนาดใหญ่
- [x] แทน `print` ด้วย structured logger ใน critical Source/Visualization/Scheduler/Billing paths พร้อม regression guard
- [ ] Audit broad exception ใน module รองทั้งหมด (critical paths และ error taxonomy เสร็จแล้ว)
- [ ] สร้าง OpenAPI-generated TypeScript client หรือ contract checks
- [x] Pin Python direct dependencies และเพิ่ม npm/pip dependency audit, secret scan, Dependabot และ container build gate
- [ ] เพิ่ม Architecture Decision Records สำหรับ worker, secrets, observability และ connectors

### 8.3 Data Platform และ ERP

- [ ] Connector SDK และ conformance suite
- [ ] Reference ERP adapter ตัวแรกสำหรับ Connector conformance tests
- [ ] Google/Microsoft private-file OAuth Authorization Code + PKCE
- [ ] Encrypted provider token store, rotation, revoke และ disconnect audit
- [ ] Google/Microsoft file picker และ least-privilege scope review
- [ ] Credential encryption/rotation/revocation
- [ ] Schema drift และ reconciliation
- [ ] Backfill, late data, delete/tombstone และ replay
- [ ] Data retention/archive และ raw snapshot lifecycle
- [ ] Install/package optional SQL drivers ตาม provider ที่เปิดรองรับใน Production
- [ ] Query cost/resource guards ต่อ Organization

### 8.4 ETL, Mapping และ Quality

- [ ] Recipe diff/rollback UX
- [ ] Mapping confidence พร้อมเหตุผลจาก schema/sample
- [ ] Quarantine สำหรับ invalid rows
- [ ] Reconciliation report ก่อน Publish
- [ ] Quality rule templates ตามอุตสาหกรรม
- [ ] Contract compatibility check เมื่อ schema เปลี่ยน
- [ ] Fiscal calendar, timezone, currency และ return-policy test packs

### 8.5 Analytics, Semantic Layer และ AI

- [x] Chat Interaction V1: message-level copy/read-aloud/reuse prompt, safe retry-edit action, contextual follow-up chips, auto-growing composer, Escape-to-stop และ jump-to-latest
- [x] Conversation branching/versioning สำหรับ Edit/Regenerate แบบ GPT โดยเก็บแต่ละ branch แยก มีตัวเลือกสลับเวอร์ชัน และไม่ทำลาย audit/history เดิม; Apply `chat_conversation_branching` และ FK-index follow-up บน Live แล้ว
- [x] Inline failed-message retry พร้อมเริ่ม stream ใหม่จากบริบทเดิม และ idempotent persistence ด้วย `client_request_id` + unique constraint; Apply บน Live แล้ว
- [ ] Semantic metric approval/version/deprecation workflow
- [ ] Governed multi-table join model และ grain validation
- [ ] Golden datasets ตาม domain
- [ ] Hallucination/numeric/citation benchmark ใน CI
- [ ] LLM provider outage/fallback tests
- [ ] Cost budget และ quality telemetry ต่อ plan/org
- [ ] Forecast backtesting ก่อนเปิด ML forecast
- [ ] Model/data drift และ human approval สำหรับ ML

### 8.6 Visualization และ Reporting

- [x] Dashboard Schema V4, V3 auto-upgrade, Component Registry และ section-based renderer/editor
- [x] Dashboard V4 i18n ไทย/อังกฤษผ่าน locale catalog กลาง พร้อมแปลชื่อ Section จาก stable section key และ fallback สำหรับ Dashboard เดิม
- [x] Evidence-grounded Story, Design candidates และ Semantic/Presentation quality judge
- [x] Executive/Analytical/Operational variants และ Pareto component
- [x] Insight-driven composition: KPI/Trend/Driver/Movement/Action/Detail จาก verified aggregates
- [x] Enforceable chart guardrails พร้อม correction/removal decisions
- [x] Real-browser save/reopen/filter/source regression
- [ ] Domain dashboard templates สำหรับ Sales/Finance/Inventory/Customer/Operations
- [ ] Feedback learning จาก useful/not useful, delete, replace และ reorder แยก User/Organization
- [ ] Explainable recommendation UI แสดงเหตุผลและทางเลือกของ Candidate
- [ ] Histogram, scatter/correlation, anomaly และ forecast widgets พร้อม deterministic validation
- [ ] Visualization quality telemetry: candidate score, acceptance, edit/delete rate และ time-to-useful-dashboard
- [ ] Drill-down และ governed row inspection ครบทุก chart ที่รองรับ
- [ ] High-cardinality sampling/Top-N UX และ performance budget
- [ ] Mobile executive view และ accessibility
- [ ] Server-side PDF builder
- [ ] PPTX builder เมื่อมี validated demand
- [ ] Scheduled report attachment และ delivery history
- [ ] Embed SDK, domain allowlist และ tenant tokens

### 8.7 Automation และ Notifications

- [x] Dedicated ETL/Alert worker service แยกจาก FastAPI lifecycle พร้อม graceful shutdown
- [ ] Worker backlog/lease metrics (structured heartbeat และ job lifecycle events เสร็จแล้ว)
- [ ] Dead-letter/replay console
- [ ] DST/timezone/missed-run/catch-up tests
- [ ] SMTP production setup
- [ ] Slack/Teams OAuth delivery
- [ ] Per-channel retry/idempotency/rate limits
- [ ] User notification preferences และ unsubscribe/compliance flow

### 8.8 Enterprise Identity และ Governance

- [ ] End-user MFA และ AAL enforcement
- [ ] SAML SSO
- [ ] SCIM Users/Groups
- [ ] Domain verification
- [ ] Role/permission matrix และ access review
- [ ] Session/device management และ revoke
- [ ] Step-up authentication
- [ ] Immutable audit export
- [ ] Retention/legal hold/data deletion workflow

### 8.9 Security และ Privacy

- [ ] เปิด Leaked Password Protection
- [ ] ตรวจ RLS, Grants, Functions, Views และ Storage ทุก migration
- [ ] เตรียม explicit grants สำหรับ Supabase Data API behavior ใหม่
- [x] เพิ่ม CodeQL SAST และ Trivy scan สำหรับ API/Worker และ Web images โดย fail เมื่อพบ Critical/High ที่มีวิธีแก้
- [ ] Rate limit/CAPTCHA/abuse controls สำหรับ Auth และ public endpoints
- [ ] OWASP ASVS 5.0 L2 checklist
- [ ] External penetration test
- [ ] Incident response และ breach notification process
- [ ] DPA/subprocessor/data processing inventory
- [ ] Database และ Storage restore drills

### 8.10 Billing และ Subscription Operations

- [ ] Stripe Live end-to-end tests
- [ ] Async webhook processing และ event replay dashboard
- [ ] Payment failure/dunning/grace period
- [ ] Upgrade/downgrade/proration/cancellation behavior
- [ ] Seat reconciliation ระหว่าง Stripe และ Organization members
- [ ] Invoice, tax/VAT และ refund policy

### 8.11 Internal Admin และ Support

Design spec (routes, staff gate, entitlements vs flags, v1 exclusions):
[`README.md` — Platform Admin Console](README.md#platform-admin-console-planned--หน้าหลังบ้าน-admin-ยังไม่พัฒนา)

- [ ] Staff identity, MFA และ least-privilege roles
- [ ] Search/view users, organizations, plans และ seats
- [ ] Usage, quota, ETL/job/error/email/Stripe monitoring
- [ ] Suspend/reactivate และ feature flags
- [ ] Immutable admin audit
- [ ] Two-person approval สำหรับ high-risk actions
- [ ] Time-limited consent-based impersonation
- [ ] Support ticket/reason linkage และ customer-visible staff identity

### 8.12 Observability และ SRE

- [ ] OpenTelemetry traces, metrics และ logs
- [ ] Error tracking พร้อม source maps และ release version
- [ ] Dashboards: API, Worker, ETL, Source, LLM, Delivery, Stripe และ Auth
- [ ] Alert routing และ on-call ownership
- [ ] Define/measure SLI ก่อนตั้ง SLO/SLA
- [ ] Capacity planning และ load tests
- [ ] Backup inventory, RPO/RTO และ restore evidence
- [ ] Status page และ maintenance communication

## 9. Test Matrix ที่ต้องมี

| Layer | ปัจจุบัน | เป้าหมาย Enterprise |
|---|---|---|
| Unit | แข็งแรงระดับหนึ่ง | Coverage สำหรับ critical calculation และ authorization พร้อม threshold |
| API integration | มีหลาย service tests | ใช้ Staging Supabase/Storage/Stripe fixtures และตรวจ grants/RLS จริง |
| Browser E2E | 22 mocked/bypass flows | Real auth + API + Storage flows แยก smoke/regression/enterprise |
| Migration | ตรวจเป็นราย migration บางส่วน | Fresh install, upgrade, rollback strategy, advisor และ cross-tenant tests ใน CI |
| Data correctness | Structured findings/verifier tests | Golden ERP datasets และ reconciliation signed off |
| Scheduler | Unit tests สำหรับ lease/idempotency | Dedicated worker restart, concurrency, DST, missed run และ provider outage |
| Security | RLS/advisor hardening | ASVS L2, SAST/DAST, dependency/container scan และ pentest |
| Recovery | ยังไม่มี evidence | Database + Storage restore drill ตามรอบ |
| Performance | มี row limits/cache | Dataset tiers, concurrency, P95/P99, memory/cost budgets |

## 10. Enterprise Definition of Done

MataQorLab จะเรียกว่า Enterprise Grade ได้เมื่อครบทุกข้อ ไม่ใช่เพียงเปิด Enterprise plan:

1. **Correctness:** Golden KPI และ reconciliation ผ่านตามนิยามที่ Data owner อนุมัติ
2. **Isolation:** ไม่มี cross-tenant access ใน API, RLS, Storage, Share, Memory, Billing และ Jobs
3. **Identity:** MFA, SSO/SCIM ตามแพ็กเกจ, session revoke และ least privilege ทำงานจริง
4. **Auditability:** Action สำคัญทุกชนิดมี actor, reason, target, timestamp, before/after และ immutable audit
5. **Reliability:** Worker retry/restart/idempotency ผ่าน และไม่มี duplicate delivery/data loss
6. **Observability:** ทุก critical path มี logs, metrics, traces, dashboards และ actionable alerts
7. **Recovery:** Database และ Storage restore ผ่านตาม RPO/RTO ที่ประกาศ
8. **Security:** ไม่มี Critical/High finding ที่ไม่ถูกแก้หรือยอมรับความเสี่ยงอย่างเป็นทางการ
9. **Privacy:** Retention, export, deletion, consent, DPA และ incident process ใช้งานได้
10. **Operations:** ทีม Support/Admin แก้ปัญหาได้โดยไม่ใช้ service-role key หรือแก้ฐานข้อมูลตรง
11. **Delivery:** Deployment, migration และ rollback ทำซ้ำได้จาก CI/CD
12. **Documentation:** Customer Admin, Analyst, Security, Support และ Connector docs ครบ

## 11. Product และ Engineering Metrics

### Correctness

- Golden KPI mismatch rate
- Numeric correction rate
- Reconciliation difference
- Percentage of findings with complete provenance

### Reliability

- Source sync success rate
- ETL/Scheduled delivery success rate
- Duplicate job/delivery count
- Worker backlog และ lease recovery time
- Data-loss/failed-restore incidents

### Performance และ Cost

- P50/P95/P99 API และ analysis latency
- Rows/bytes ต่อ run
- Memory/CPU ต่อ dataset tier
- LLM tokens/cost ต่อ answer และ Organization
- Storage growth และ retention savings

### Product

- Time to first verified dashboard
- Mapping/Contract completion rate
- Weekly active organizations
- Scheduled report open/action rate
- Alert-to-action rate
- Organization activation และ retention

### Security และ Operations

- Open security findings by severity
- Mean time to detect/acknowledge/restore
- Privileged actions without complete audit ซึ่งต้องเท่ากับศูนย์
- Restore drill pass rate
- Support cases ที่วินิจฉัยได้จาก Request/Run ID

## 12. ลำดับงานแนะนำตั้งแต่วันนี้

### สัปดาห์ที่ 1

1. Freeze ฟีเจอร์ใหม่ที่ไม่เกี่ยวกับ Stability หรือ Enterprise release gates
2. สร้าง Bug registry และนำบั๊กที่พบจริงทั้งหมดเข้าระบบ
3. เพิ่ม real E2E สำหรับ Upload/Mapping/Chat/Visualization persistence
4. Audit silent failures และ structured logging ใน Source/Save/Scheduler/Billing paths
5. Pin Python dependencies และยกระดับ CI
6. เปิด Leaked Password Protection และตรวจ Supabase Advisor ซ้ำ

### สัปดาห์ที่ 2

1. แยก Staging/Production environments
2. Deploy dedicated worker
3. ตั้ง SMTP/Stripe test environment
4. เพิ่ม observability และ worker/source dashboards
5. ทำ Database + Storage restore drill
6. ปิด P0 bugs และรัน Stability release gate

### หลัง Stability Gate

1. เลือก Reference ERP schema/sandbox สำหรับ conformance tests และกำหนด Golden KPI
2. สร้าง Connector Contract และ Reference ERP adapter ตัวแรก
3. ทำ reconciliation + incremental sync
4. รัน Controlled Beta และ Shadow reporting ด้วยขอบเขตที่จำกัด
5. พัฒนา Enterprise Identity/Admin ตาม Product security requirements และการใช้งานที่ยืนยันได้

## 13. สิ่งที่ยังไม่ควรเร่งก่อน Stability ผ่าน

- TensorFlow หรือ Deep Learning
- Connector marketplace จำนวนมาก
- Write-back เข้า ERP
- Multi-region architecture
- PPTX Builder หากยังไม่มีลูกค้ายืนยันความต้องการ
- Chart catalog จำนวนมากโดยยังไม่มี regression/performance tests
- Custom logic เฉพาะลูกค้าที่ไม่สามารถย้ายเข้า Connector/Semantic contract กลางได้

## 14. หลักการอัปเดต Roadmap

- อัปเดตเอกสารนี้ทุกสัปดาห์หรือทุก Release
- ทุกงานต้องระบุ Status, Priority, Owner, Target phase, Acceptance criteria และ Evidence
- ห้ามย้ายงานเป็น Done จากการมี UI อย่างเดียว ต้องผ่าน Backend enforcement และ tests ที่เหมาะสม
- บั๊ก Production ต้องเชื่อมกับ Postmortem และ Regression test
- Feature ใหม่ที่เพิ่ม Surface area ต้องเพิ่ม Observability, Security, Documentation และ Runbook พร้อมกัน
- README ใช้บอกวิธีใช้และสถานะฟีเจอร์ ส่วนเอกสารนี้เป็นแหล่งอ้างอิง Roadmap และ Release Gate หลัก

## 15. External Standards และ Platform Notes

- Supabase Production Checklist: <https://supabase.com/docs/guides/deployment/going-into-prod>
- Supabase Security configuration: <https://supabase.com/docs/guides/security/product-security>
- Supabase Database backups: <https://supabase.com/docs/guides/platform/backups>
- Supabase Data API explicit grants change: <https://supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically>
- OWASP ASVS 5.0: <https://owasp.org/www-project-application-security-verification-standard/>
- OpenTelemetry: <https://opentelemetry.io/docs/>
- Stripe Webhook best practices: <https://docs.stripe.com/webhooks>

หมายเหตุ Supabase: ตั้งแต่ 30 ตุลาคม 2026 ตารางใหม่ใน `public` ของโปรเจกต์เดิมจะไม่ถูกเปิดผ่าน Data API อัตโนมัติ จึงต้องคง explicit `GRANT` และ RLS ไว้ใน migration พร้อมทดสอบสิทธิ์ `anon`, `authenticated` และ `service_role` ตาม access model จริง
