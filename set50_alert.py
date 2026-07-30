# -*- coding: utf-8 -*-
"""
set50_alert.py — สแกน SET50 หาสัญญาณ SuperTrend v2 (D1) แล้วเด้ง Telegram (cloud 24 ชม.)
- ข้อมูล yfinance (.BK) รายวัน D1  (ไม่ใช้ MT5 = รันบน GitHub Actions Linux ได้)
- สมองเดียวกับ alert_cloud.py: SuperTrend ATR10x3.0 + ADX14 + EMA200 regime (รายวัน)
  ⚠️ ถ้าจูนพารามิเตอร์ ต้องแก้ให้ตรงกับ 3 ไฟล์สูตร (auto_trader/server/alert_cloud) — ดู memory
- เด้งเฉพาะตอน flip ใหม่ (dedup ด้วย set50_state.json ราย ticker ตามวันแท่ง)
- validate 2026-07-30: backtest 6y universe PF 1.41 (มี edge)
token/chat_id จาก ENV: TG_BOT_TOKEN, TG_CHAT_ID (GitHub Secrets)
"""
import os, json, sys, io
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass
import urllib.request, urllib.parse
import pandas as pd
import yfinance as yf

TOKEN = os.environ.get("TG_BOT_TOKEN", "")
CHAT  = os.environ.get("TG_CHAT_ID", "")
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "set50_state.json")

ATR_P, ST_MULT, ADX_P, REGIME_EMA = 10, 3.0, 14, 200

SET50 = [
    "ADVANC", "AOT", "AWC", "BANPU", "BBL", "BDMS", "BEM", "BGRIM", "BH", "BTS",
    "CBG", "CENTEL", "COM7", "CPALL", "CPF", "CPN", "CRC", "DELTA", "EA", "EGCO",
    "GLOBAL", "GPSC", "GULF", "HMPRO", "INTUCH", "IVL", "KBANK", "KCE", "KTB", "KTC",
    "LH", "MINT", "MTC", "OR", "OSP", "PTT", "PTTEP", "PTTGC", "RATCH", "SAWAD",
    "SCB", "SCC", "SCGP", "TIDLOR", "TISCO", "TLI", "TOP", "TRUE", "TU", "WHA",
]


def supertrend(h, l, c, period=ATR_P, mult=ST_MULT):
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


def adx_last(h, l, c, period=ADX_P):
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


def fetch_daily(ticker):
    df = yf.download(ticker + ".BK", period="2y", interval="1d",
                     auto_adjust=True, progress=False)
    if df is None or len(df) == 0:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    r = df[["Open", "High", "Low", "Close"]].dropna()
    r.columns = ["o", "h", "l", "c"]
    return r


def evaluate(r):
    H = [float(x) for x in r["h"]]; L = [float(x) for x in r["l"]]; C = [float(x) for x in r["c"]]
    tr, stl = supertrend(H, L, C); reg = ema_last(C, REGIME_EMA); adx = adx_last(H, L, C)
    cur, prev = tr[-1], tr[-2]; last = C[-1]
    flip_up = cur == 1 and prev == -1; flip_down = cur == -1 and prev == 1
    sig = "BUY" if (flip_up and last > reg) else ("SELL" if (flip_down and last < reg) else "WAIT")
    return dict(sig=sig, last=round(last, 2), sl=round(stl[-1], 2), adx=round(adx, 1),
                bar=str(r.index[-1].date()))


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
    hits = []
    for t in SET50:
        try:
            r = fetch_daily(t)
            if r is None or len(r) < 60:
                print("%-8s ไม่มีข้อมูลพอ" % t); continue
            e = evaluate(r)
            print("%-8s %-4s last=%s SL=%s ADX=%s bar=%s" %
                  (t, e["sig"], e["last"], e["sl"], e["adx"], e["bar"]))
            if e["sig"] in ("BUY", "SELL") and state.get(t) != e["bar"]:
                hits.append((t, e)); state[t] = e["bar"]
        except Exception as ex:
            print("%-8s error: %s" % (t, ex))
    if hits:
        lines = ["📊 <b>SET50 สัญญาณ SuperTrend D1</b> (%s)" % hits[0][1]["bar"], ""]
        for t, e in hits:
            head = "🟢 BUY " if e["sig"] == "BUY" else "🔴 SELL"
            lines.append("%s <b>%s</b> @ %s  (SL %s, ADX %s)" %
                         (head, t, e["last"], e["sl"], e["adx"]))
        lines.append("")
        lines.append("⚠️ สัญญาณเทคนิค D1 (yfinance) — ไปเช็ค/เปิดออเดอร์เองในโบรกจริง ไม่ใช่คำแนะนำการลงทุน")
        if tg_send("\n".join(lines)):
            print("   -> ส่ง alert %d ตัวแล้ว" % len(hits))
        else:
            # ส่งไม่สำเร็จ = อย่าเพิ่ง mark state (ให้ลองใหม่รอบหน้า)
            for t, e in hits:
                if state.get(t) == e["bar"]:
                    del state[t]
    else:
        print("ไม่มี flip ใหม่วันนี้")
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
