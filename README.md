# FOOTBALL AI INTELLIGENCE — Starter Web Application

**สถานะ:** เว็บวิเคราะห์ฟุตบอลเวอร์ชันที่รันได้จริง (MVP) พร้อม Python API,
เว็บไซต์ภาษาไทย และชุดทดสอบพื้นฐาน **ยังไม่ใช่ระบบทำนายบอลสมบูรณ์หรือแม่นยำสูงที่พิสูจน์แล้ว**

## สิ่งที่ทำงานแล้ว

- เว็บไซต์ภาษาไทย รองรับ PC / มือถือ มีหน้า บอลวันนี้, วิเคราะห์, ประสิทธิภาพ AI, วิธีใช้งาน
- Python FastAPI + SQLite ในเครื่อง ไม่จำเป็นต้องใช้ API key เพื่อเริ่ม
- นำเข้าผลการแข่งขัน CSV แบบ Football-Data.co.uk (ต้องดาวน์โหลดจากแหล่งที่ได้รับอนุญาต)
- โมเดล Poisson แบบถ่วงเวลา + shrinkage ใช้ข้อมูลเฉพาะแมตช์ก่อนวันวิเคราะห์
- วิเคราะห์ 1X2, BTTS, สูง–ต่ำ, สกอร์ยอดนิยม และครึ่งแรกเมื่อมีข้อมูล
- คำนวณ expected value สำหรับ Asian Handicap และสูง–ต่ำทุกเส้นที่เป็น 0.25
- สรุป performance แบบ walk-forward: accuracy, Brier Score, Log Loss
- นำเข้าตารางแข่งขันจาก CSV ที่มีข้อมูลจริง/มีสิทธิ์ใช้ (ไม่แต่งคู่แข่งขันเอง)
- โหมดข้อมูลจำลอง **DEMO** ที่ต้องเปิดใช้เองโดยสมัครใจ และมีป้ายเตือนในเว็บ
- ไฟล์ Supabase schema SQL + RLS สำหรับวางแผนย้ายสู่ production

## เปิดเว็บบน Windows (วิธีง่ายที่สุด)

1. แตก ZIP ลงโฟลเดอร์ เช่น `D:\FootballAI` แล้วติดตั้ง Python 3.12+ จาก python.org
2. ดับเบิลคลิก `start_windows.bat` เพื่อสร้าง virtualenv และติดตั้ง dependencies
3. เข้า <http://127.0.0.1:8000> ถ้าหน้าเบราว์เซอร์ยังไม่เปิดขึ้น
4. **เริ่มต้นจะยังไม่มีข้อมูลบอลจริง** ต้องนำเข้า CSV ก่อน

หากใช้ VS Code terminal บน Windows:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r api\requirements.txt
$env:PYTHONPATH = "api"
python -m uvicorn football_ai.api:app --port 8000
```

บน macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r api/requirements.txt
PYTHONPATH=api uvicorn football_ai.api:app --port 8000
```

## นำเข้าข้อมูลฟุตบอลจริง

ข้อมูลผลย้อนหลังจาก OpenFootball สามารถอัปเดตด้วยคำสั่ง `.venv\Scripts\python.exe scripts\import_openfootball.py`
ครอบคลุมลีกสูงสุดของอังกฤษ เยอรมนี สเปน อิตาลี และฝรั่งเศส ตามฤดูกาลที่ระบุในสคริปต์
ตรวจสอบวันที่ผลล่าสุดบนหน้าวิเคราะห์ เพราะแหล่งข้อมูลอาจอัปเดตช้ากว่าการแข่งขันจริง

ดาวน์โหลด CSV ผลย้อนหลังของลีกต่าง ๆ จาก <https://www.football-data.co.uk/data.php>
ตามเงื่อนไขของแหล่งข้อมูล เช่น `E0.csv` สำหรับพรีเมียร์ลีก
ต้องมี Date, HomeTeam, AwayTeam, FTHG, FTAG และ Div (ถ้ามี)

บน Windows PowerShell (ขณะอยู่ในโฟลเดอร์โปรเจกต์):

```powershell
$env:PYTHONPATH = "api"
python scripts/import_csv.py "D:\Downloads\E0.csv"
```

ควรนำเข้าหลายฤดูกาลต่อเนื่องกัน แล้วรีเฟรชหน้าเว็บ

**หมายเหตุ:** โปรแกรมไม่ดาวน์โหลดข้อมูลเว็บฟุตบอลอัตโนมัติ เพราะต้องตรวจสอบ
ความเหมาะสมของการเข้าถึง สิทธิ์การใช้งาน และ API ของแต่ละผู้ให้บริการก่อน

## โหมดทดลอง UI ด้วยข้อมูลสมมติ (ห้ามตีความเป็นคำทำนายจริง)

```powershell
$env:PYTHONPATH = "api"
python scripts/create_demo.py
```

โหมดนี้สร้างทีมชื่อ Demo Atlas/Orion ฯลฯ ไม่ใช่ทีมฟุตบอลจริง
หากต้องกลับไปใช้ข้อมูลจริง แนะนำลบฐานข้อมูล local `.sqlite`
แล้วนำเข้าข้อมูลจริงใหม่ในฐานข้อมูลสะอาด

## นำเข้าตารางแข่งขันล่วงหน้า

### วิเคราะห์คู่ที่กำลังแข่ง

ค่าเริ่มต้นใช้ฟีด [Football Mania LiveScore MCP](https://football-mania.com/data-policy) สำหรับการใช้งานส่วนตัวหรือไม่เชิงพาณิชย์ โดยตรวจข้อมูลทุก 60 วินาทีขณะเปิดหน้าบอลวันนี้
เมื่อตั้ง `API_FOOTBALL_KEY` ใน `.env` หรือใน environment ของเซิร์ฟเวอร์แล้วเริ่ม FastAPI ใหม่ ระบบจะใช้ API-Football และดึงข้อมูลทุก 15 นาที
ระบบใช้คำขอร่วมกันต่อโปรเซส ควรตรวจโควตาของแพ็กเกจตามระยะเวลาที่เปิดใช้
รายการแข่งขันขึ้นกับความครอบคลุมของ API-Football ส่วนลิงก์ 365Scores ใช้เปิดดูรายการอ้างอิง
โมเดลประเมินผลเมื่อจบ 90 นาทีจากสกอร์และนาทีปัจจุบัน โดยตั้งอัตรายิงประตูเริ่มต้นเท่ากันสำหรับทั้งสองทีม

### นำเข้าจาก CSV

ต้องมีแหล่งตารางแข่งที่ได้รับอนุญาต และสร้าง CSV ที่มี header:

```csv
league,kickoff,home,away
E0,2027-02-20T15:00:00+00:00,TeamNameA,TeamNameB
```

*บรรทัดตัวอย่างด้านบนเป็นเพียงรูปแบบข้อมูล ไม่ใช่ตารางแข่งจริง*

จากนั้นตั้งค่าเซิร์ฟเวอร์ `FOOTBALL_ADMIN_TOKEN` เป็นสตริงยาวแบบสุ่ม (ห้ามใส่ในเว็บ/config.js) แล้ว import ผ่าน API:

```bash
curl -X POST http://127.0.0.1:8000/api/admin/import-fixtures \
  -H "X-Admin-Token: YOUR_SERVER_ADMIN_TOKEN" -F "file=@my_authorized_fixtures.csv"
```

ข้อมูลที่นำเข้าจะขึ้นที่หน้าแรก ไม่สร้างแมตช์ปลอม

## Cloudflare + Supabase

- **Static website:** สามารถ deploy **โฟลเดอร์ `web/`** ไป Cloudflare Pages โดยไม่ต้องมี build command
- **Backend API:** ต้องโฮสต์ FastAPI แยกต่างหากบนเซิร์ฟเวอร์ Python (Cloudflare Pages อย่างเดียวไม่สามารถรันโมเดล Python นี้ได้)
- ที่ไฟล์ `web/config.js` ตั้ง `window.FOOTBALL_API_URL = 'https://your-python-api-host'`
- เซิร์ฟเวอร์ API ต้องตั้ง `CORS_ORIGINS=https://your-cloudflare-domain.pages.dev`
- **Supabase:** ไฟล์ `supabase/schema.sql` เป็น SQL โครงสร้างและ RLS ที่ยังไม่เชื่อมกับ runtime
  และยังไม่ถูกใช้งานโดยอัตโนมัติ ต้องพัฒนา data adapter/credentials เพิ่มหากเลือกใช้ Supabase เป็น production database
- `SUPABASE_SECRET_KEY` เป็นความลับฝั่งเซิร์ฟเวอร์เท่านั้น ห้ามใส่ในเว็บ

## ทดสอบ

```bash
PYTHONPATH=api python -m pytest api/tests -q
node --check web/app.js
```

API docs: <http://127.0.0.1:8000/api/docs>

## สิ่งที่ยังต้องพัฒนาเพื่อใช้งานจริงระดับ production

ข้อมูลบอลสดและราคา, provider API/quotas, โมเดลที่ผ่านการเทียบกับตลาด,
calibration, xG/lineups, model registry/rollback, ระบบยืนยันเวลาตารางแข่ง,
Supabase persistence, monitoring, login/users, และการ deploy Python API

อ่าน `docs/ACCURACY_ROADMAP.md` สำหรับแนวทางเพิ่มความแม่นยำให้พิสูจน์ได้จริง

**คำเตือน:** ผลจากโมเดลเป็นการประมาณทางสถิติ ไม่ใช่การรับประกันผลฟุตบอลหรือผลตอบแทนจากการเดิมพัน ไม่มีระบบล็อกอินเว็บพนัน/แทงบอลอัตโนมัติ
