# -*- coding: utf-8 -*-
"""
alert_cloud.py — แจ้งเตือนสัญญาณ SuperTrend v2 ฟรี 24 ชม. บน GitHub Actions
- ข้อมูลจาก yfinance (ทอง GC=F, BTC BTC-USD) resample -> H4  (ไม่ต้องใช้ MT5)
- สมองเดียวกับ server.py / auto_trader: SuperTrend ATR10x3.0 + ADX + EMA300 regime
- เด้งเข้า Telegram เฉพาะตอน flip ใหม่ (dedup ด้วย alert_state.json)
token/chat_id อ่านจาก ENV: TG_BOT_TOKEN, TG_CHAT_ID  (ตั้งเป็น GitHub Secrets)
"""
import os, json, sys, io
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass
import urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
import pandas as pd
import yfinance as yf

TOKEN = os.environ.get("TG_BOT_TOKEN", "")
CHAT  = os.environ.get("TG_CHAT_ID", "")
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alert_state.json")
WATCH = [("XAU ทอง", "GC=F"), ("BTC", "BTC-USD")]
DAILY_HOUR_ICT = 8        # ส่งสรุปรายวันรอบแรกที่รันหลังเวลานี้ (เวลาไทย ICT = UTC+7)
DAILY_KEY = "_daily"      # key ใน state สำหรับ dedup heartbeat (ไม่ชนกับ ticker)


def supertrend(h, l, c, period=10, mult=3.0):
    n = len(c); trend = [1] * n; stl = list(c)
    if n <= period + 2:
        return trend, stl
    tr = [0.0] * n
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr = [0.0] * n; atr[period] = sum(tr[1:period + 1]) / period
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    fup = [0.0] * n; flo = [0.0] * n
    for i in range(period, n):
        hl2 = (h[i] + l[i]) / 2.0; bup = hl2 + mult * atr[i]; blo = hl2 - mult * atr[i]
        if i == period:
            fup[i], flo[i], trend[i] = bup, blo, 1
        else:
            fup[i] = bup if (bup < fup[i - 1] or c[i - 1] > fup[i - 1]) else fup[i - 1]
            flo[i] = blo if (blo > flo[i - 1] or c[i - 1] < flo[i - 1]) else flo[i - 1]
            trend[i] = (-1 if c[i] < flo[i] else 1) if trend[i - 1] == 1 else (1 if c[i] > fup[i] else -1)
        stl[i] = flo[i] if trend[i] == 1 else fup[i]
    return trend, stl


def adx_last(h, l, c, period=14):
    n = len(c)
    if n <= period * 2 + 2:
        return 0.0
    pdm = [0.0] * n; mdm = [0.0] * n; tr = [0.0] * n
    for i in range(1, n):
        up = h[i] - h[i - 1]; dn = l[i - 1] - l[i]
        pdm[i] = up if (up > dn and up > 0) else 0.0
        mdm[i] = dn if (dn > up and dn > 0) else 0.0
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    a = sum(tr[1:period + 1]); pv = sum(pdm[1:period + 1]); mv = sum(mdm[1:period + 1]); dx = []
    for i in range(period + 1, n):
        a = a - a / period + tr[i]; pv = pv - pv / period + pdm[i]; mv = mv - mv / period + mdm[i]
        if a == 0:
            continue
        pdi = 100 * pv / a; mdi = 100 * mv / a; s = pdi + mdi
        dx.append(100 * abs(pdi - mdi) / s if s > 0 else 0.0)
    if len(dx) < period:
        return 0.0
    adx = sum(dx[:period]) / period
    for d in dx[period:]:
        adx = (adx * (period - 1) + d) / period
    return adx


def ema_last(c, period):
    a = 2 / (period + 1); e = c[0]
    for x in c[1:]:
        e = x * a + e * (1 - a)
    return e


def fetch_4h(ticker):
    df = yf.download(ticker, period="250d", interval="1h", auto_adjust=False, progress=False)
    if df is None or len(df) == 0:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    idx = df.index
    df.index = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    o = df["Open"].resample("4h").first(); h = df["High"].resample("4h").max()
    l = df["Low"].resample("4h").min();   c = df["Close"].resample("4h").last()
    r = pd.DataFrame({"o": o, "h": h, "l": l, "c": c}).dropna()
    now = pd.Timestamp.now(tz="UTC")
    r = r[r.index + pd.Timedelta("4h") <= now]     # เฉพาะแท่งที่ปิดสมบูรณ์แล้ว (กัน repaint)
    return r


def evaluate(r):
    H = [float(x) for x in r["h"]]; L = [float(x) for x in r["l"]]; C = [float(x) for x in r["c"]]
    tr, stl = supertrend(H, L, C); reg = ema_last(C, 300); adx = adx_last(H, L, C)
    cur, prev = tr[-1], tr[-2]; last = C[-1]
    flip_up = cur == 1 and prev == -1; flip_down = cur == -1 and prev == 1
    sig = "BUY" if (flip_up and last > reg) else ("SELL" if (flip_down and last < reg) else "WAIT")
    return dict(sig=sig, last=round(last, 2), sl=round(stl[-1], 2), adx=round(adx, 1),
                trend=("up" if cur == 1 else "down"), bar=str(r.index[-1]))


def tg_send(text):
    if not TOKEN or not CHAT:
        print("  (ไม่มี TG_BOT_TOKEN/TG_CHAT_ID -> ข้ามการส่ง)")
        return False
    data = urllib.parse.urlencode({"chat_id": CHAT, "text": text, "parse_mode": "HTML"}).encode()
    try:
        req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % TOKEN, data=data)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception as e:
        print("  TG error:", e)
        return False


def main():
    try:
        with open(STATE, encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = {}
    latest = []   # เก็บผลล่าสุดของแต่ละ symbol ไว้ทำสรุปรายวัน
    for name, ticker in WATCH:
        try:
            r = fetch_4h(ticker)
            if r is None or len(r) < 50:
                print("%-10s ไม่มีข้อมูลพอ" % name); continue
            e = evaluate(r)
            latest.append((name, e))
            print("%-10s %-4s last=%s SL=%s ADX=%s bar=%s" %
                  (name, e["sig"], e["last"], e["sl"], e["adx"], e["bar"]))
            if e["sig"] in ("BUY", "SELL") and state.get(ticker) != e["bar"]:
                head = "🟢 <b>BUY</b>" if e["sig"] == "BUY" else "🔴 <b>SELL</b>"
                msg = ("%s — %s H4\nแท่ง: %s\nราคา: <b>%s</b>\nSL (เส้น ST): %s\nADX: %s\n"
                       "(ข้อมูล yfinance ≈ ทองโลก/BTC — ไปเปิดออเดอร์ใน MT5 จริงเอง)\n"
                       "⚠️ สัญญาณเทคนิค ไม่ใช่คำรับประกัน"
                       % (head, name, e["bar"], e["last"], e["sl"], e["adx"]))
                if tg_send(msg):
                    state[ticker] = e["bar"]; print("   -> ส่ง alert แล้ว")
        except Exception as ex:
            print("%-10s error: %s" % (name, ex))

    # daily_heartbeat(state, latest)  # ตัด heartbeat/bot-alive ออก 2026-08-12 (user ขอ)

    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def daily_heartbeat(state, latest):
    """ยิงสรุปสถานะวันละครั้ง (รอบแรกที่รันหลัง DAILY_HOUR_ICT) แม้เป็น WAIT
    เพื่อยืนยันว่า cloud alert ยังทำงานอยู่ — dedup ด้วยวันที่ (เวลาไทย)."""
    now_ict = datetime.now(timezone.utc) + timedelta(hours=7)
    today = now_ict.strftime("%Y-%m-%d")
    if now_ict.hour < DAILY_HOUR_ICT or state.get(DAILY_KEY) == today:
        return
    if not latest:
        print("  (ยังไม่มีข้อมูล symbol -> ข้ามสรุปรายวัน)"); return
    icon = {"BUY": "🟢", "SELL": "🔴", "WAIT": "⚪"}
    lines = []
    for name, e in latest:
        lines.append("%s <b>%s</b> %s — ราคา %s · ADX %s · เทรนด์ %s"
                     % (icon.get(e["sig"], "⚪"), e["sig"], name, e["last"], e["adx"], e["trend"]))
    msg = ("📊 <b>สรุปสถานะรายวัน</b> (SuperTrend H4)\n🕗 %s ICT\n—\n%s\n—\n"
           "✅ ระบบ alert ทำงานปกติ (ข้อความนี้ยืนยันว่า cloud ยังรันอยู่)\n"
           "จะเด้งเตือน BUY/SELL แยกอีกครั้งเมื่อมีสัญญาณ flip จริง"
           % (now_ict.strftime("%Y-%m-%d %H:%M"), "\n".join(lines)))
    if tg_send(msg):
        state[DAILY_KEY] = today; print("   -> ส่งสรุปรายวันแล้ว")


if __name__ == "__main__":
    main()
