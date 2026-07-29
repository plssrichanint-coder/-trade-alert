# ☁️ Cloud Alert — แจ้งเตือนสัญญาณ 24 ชม. ฟรี (GitHub Actions)

รันบน GitHub (ฟรี) เช็คทอง/BTC H4 ทุก 30 นาที → flip เมื่อไหร่เด้ง Telegram
**ไม่ต้องเปิดคอม ไม่ต้องเปิด MT5** (ใช้ข้อมูล yfinance)

## ไฟล์ในโฟลเดอร์นี้
- `alert_cloud.py` — สคริปต์หลัก (สมอง SuperTrend v2 เดียวกับ EA)
- `requirements.txt` — yfinance, pandas
- `alert_state.json` — จำสัญญาณล่าสุด (กันเตือนซ้ำ)
- `.github/workflows/alert.yml` — ตัวตั้งเวลา GitHub Actions

---

## วิธี deploy (ทำครั้งเดียว ~10 นาที)

### 1) สร้าง repo ใหม่บน GitHub
- ไป https://github.com/new → ตั้งชื่อ เช่น `trade-alert` → **Public** (ฟรีไม่จำกัดนาที) → Create

### 2) อัปโหลดไฟล์ในโฟลเดอร์นี้เข้า repo
วิธีง่าย (ไม่ต้องใช้ git):
- ในหน้า repo → **Add file → Upload files**
- ลากไฟล์ทั้งหมดในโฟลเดอร์ `cloud_alert` เข้าไป (รวมโฟลเดอร์ `.github` ด้วย)
- Commit

> ถ้าลาก `.github` ไม่ติด: กด **Add file → Create new file** แล้วพิมพ์ path
> `.github/workflows/alert.yml` แล้ววางเนื้อหาไฟล์ alert.yml

### 3) ใส่ Secret (token + chat_id ปลอดภัย ไม่โผล่ในโค้ด)
- ในหน้า repo → **Settings → Secrets and variables → Actions → New repository secret**
- สร้าง 2 อัน:
  | Name | Secret |
  |---|---|
  | `TG_BOT_TOKEN` | โทเคนบอทจาก BotFather |
  | `TG_CHAT_ID` | `-5441532822` (กลุ่ม Test) |

### 4) เปิด Actions
- แท็บ **Actions** → ถ้าถามให้ยืนยัน กด **I understand... enable**
- เลือก workflow **Trade Signal Alert** → กด **Run workflow** (ทดสอบรันเลย 1 ครั้ง)
- ดู log: ควรเห็น `XAU ... WAIT/BUY/SELL` และ `BTC ...`

เสร็จ! จากนี้ GitHub รันให้เองทุก 30 นาที ตลอด 24 ชม.

---

## ⚠️ หมายเหตุ
- **ข้อมูล yfinance ≈ ทองโลก(GC=F)/BTC-USD** ไม่ใช่ราคา broker เป๊ะ — ทิศ/จุด flip ตรงกัน พอเด้งค่อยไปเทรดใน MT5 จริง
- **กันเตือนซ้ำกับตัว local:** ถ้าใช้ cloud แล้ว ให้ตั้ง `telegram_config.json` (ตัวในคอม) เป็น `"enabled": false` จะได้ไม่เด้ง 2 ทาง
- GitHub ปิด schedule อัตโนมัติถ้า repo เงียบเกิน 60 วัน — ปกติมีสัญญาณ ~2 สัปดาห์/ครั้ง (commit state) ทำให้ไม่เงียบ; ถ้าโดนปิดจริง เข้า Actions กด enable ใหม่
- เวลา cron เป็น UTC + GitHub อาจดีเลย์ 5–15 นาที — H4 ไม่กระทบ
