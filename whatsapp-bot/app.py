import os
import re
import json
import time
import base64
import requests
import gspread
from gspread.utils import rowcol_to_a1
from google.oauth2.service_account import Credentials
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==============================================
# ENVIRONMENT VARIABLES (RENDER ENV)
# ==============================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SHEET_NAME = os.environ.get("SHEET_NAME", "UTS&PRS")

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "") or os.environ.get("SECRET_TOKEN", "")
WHATSAPP_TOKEN = (os.environ.get("WHATSAPP_TOKEN") or os.environ.get("META_TOKEN")
                  or os.environ.get("BOT_TOKEN") or "")
PHONE_NUMBER_ID = (os.environ.get("PHONE_NUMBER_ID") or os.environ.get("WHATSAPP_PHONE_NUMBER_ID") or "")

GOOGLE_CREDENTIALS_B64 = os.environ.get("GOOGLE_CREDENTIALS_B64", "")
GOOGLE_CREDENTIALS_STR = os.environ.get("GOOGLE_CREDENTIALS", "")

GEMINI_MODEL = "gemini-2.5-flash"

ALL_STATIONS = [
    "DBRT","DBRG","NTSK","TSK","MXN","JTTN","SRTN","SLGR","GLGT","MRHT",
    "NAM","NHK","FKG","AGI","DJG","LEDO","MRG","DBY","MJN","TTB","BOJ",
    "BFD","SPK","CHB","SPTR","DMC","MZS","NLP","LBI","BGND","LMY","SRPN",
    "SMCP","TQM","GOM","BDLN","CKW","LHL","DKM","PNT","TII","LXA","SFR",
    "SLX","NMT","ROING","TEZU","CGF","DMGN","TNGN","NSBG","KOWN","NCH",
    "CMA","KXL","BBGN","BLMR","NMGY","KRHT"
]

PRS_COLS = {
    "TKT": 4, "PASS": 5, "C/TKT": 6, "C/PASS": 7,
    "REF": 8, "NET": 9, "VCH": 10, "POS": 11, "UPI": 12
}

UTS_COLS_NU = {
    "PF": 14, "TKT": 16, "PASS": 17, "NET": 18,
    "MR": 19, "MR AMT": 20, "UPI": 21
}

# ==============================================
# META RETRY PROTECTION: ek message = 1 Gemini call
# ==============================================
PROCESSED_MSG_IDS = {}

def already_processed(msg_id):
    now = time.time()
    # purane entries (10 min se zyada purane) saaf karo
    for k in [k for k, t in PROCESSED_MSG_IDS.items() if now - t > 600]:
        del PROCESSED_MSG_IDS[k]
    if msg_id in PROCESSED_MSG_IDS:
        return True
    PROCESSED_MSG_IDS[msg_id] = now
    return False

# ==============================================
# CREDENTIALS LOADING (RENDER-SAFE)
# ==============================================
def _fix_newlines_inside_strings(s: str) -> str:
    out, in_str, esc = [], False, False
    for ch in s:
        if esc:
            out.append(ch); esc = False
        elif ch == "\\":
            out.append(ch); esc = True
        elif ch == '"':
            out.append(ch); in_str = not in_str
        elif ch == "\n" and in_str:
            out.append("\\n")
        else:
            out.append(ch)
    return "".join(out)

def load_credentials_dict():
    if GOOGLE_CREDENTIALS_B64:
        try:
            d = json.loads(base64.b64decode(GOOGLE_CREDENTIALS_B64).decode("utf-8"))
            print("✅ Credentials loaded via GOOGLE_CREDENTIALS_B64")
            return d
        except Exception as e:
            print(f"❌ GOOGLE_CREDENTIALS_B64 decode failed: {e}")
            return None

    raw = (GOOGLE_CREDENTIALS_STR or "").strip()
    if not raw:
        print("❌ No Google credentials in env vars!")
        return None

    candidates = [raw]
    if len(raw) > 1 and raw[0] in "'\"" and raw[-1] == raw[0]:
        candidates.append(raw[1:-1])

    for cand in candidates:
        try:
            d = json.loads(cand)
            print("✅ Credentials loaded via GOOGLE_CREDENTIALS")
            return d
        except json.JSONDecodeError:
            pass
        try:
            d = json.loads(_fix_newlines_inside_strings(cand))
            print("✅ Credentials loaded via GOOGLE_CREDENTIALS (newline-fixed)")
            return d
        except json.JSONDecodeError:
            pass

    print("❌ GOOGLE_CREDENTIALS JSON parse failed.")
    return None

# ==============================================
# GOOGLE SHEETS CONNECTION (CACHED)
# ==============================================
_SHEET = None
_STATION_MAP = None

def get_sheet():
    global _SHEET
    if _SHEET:
        return _SHEET
    creds_dict = load_credentials_dict()
    if not creds_dict:
        return None
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets",
                  "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open(SHEET_NAME)
        try:
            _SHEET = sh.worksheet(SHEET_NAME)
        except gspread.WorksheetNotFound:
            _SHEET = sh.sheet1
        print(f"✅ Google Sheet connected: '{sh.title}' / tab: '{_SHEET.title}'")
        return _SHEET
    except Exception as e:
        print(f"❌ Google Sheet Connection Error: {e}")
        return None

def get_station_map(sheet):
    global _STATION_MAP
    if _STATION_MAP:
        return _STATION_MAP
    m = {}
    for idx, val in enumerate(sheet.col_values(2), start=1):
        if 3 <= idx <= 30 and val:
            m.setdefault(str(val).upper().strip(), {"row": idx, "nameCol": "B"})
    for idx, val in enumerate(sheet.col_values(13), start=1):
        if 31 <= idx <= 47 and val:
            m.setdefault(str(val).upper().strip(), {"row": idx, "nameCol": "M"})
    for idx, val in enumerate(sheet.col_values(3), start=1):
        if 32 <= idx <= 48 and val:
            m.setdefault(str(val).upper().strip(), {"row": idx, "nameCol": "C"})
    _STATION_MAP = m
    print(f"✅ Station map ready: {len(m)} stations")
    return m

# ==============================================
# PF & DIGITAL CASH EXTRACTION
# ==============================================
def extract_pf_from_message(msg):
    if not msg:
        return None
    clean_msg = re.sub(r'PLATFORM\s*(?:TKT|AMT|AMOUNT)?', ' ', msg, flags=re.IGNORECASE)
    if re.search(r'\b(?:P/TKT|PF)\b[^\n]*?(?:NIL|NIL\.)', clean_msg, flags=re.IGNORECASE):
        return 0
    m = re.search(r'\b(?:P/TKT|PF\s*(?:TKT|QTY|QUANTITY|NO\.?|COUNT)?)\s*\.?\s*[-:=]?\s*(\d+)', clean_msg, flags=re.IGNORECASE)
    if m:
        return int(m.group(1))
    m2 = re.search(r'\bPF\s*(?:AMT|AMOUNT)\s*\.?\s*[-:=]?\s*(\d+)', clean_msg, flags=re.IGNORECASE)
    if m2:
        return int(m2.group(1))
    m3 = re.search(r'\bPF\b\s*\.?\s*[-:=]?\s*(\d+)', clean_msg, flags=re.IGNORECASE)
    if m3:
        return int(m3.group(1))
    return None

def message_has_digital_cash(msg):
    return bool(re.search(r'(?:E/CASH|D/CASH|ECASH|DCASH|E-CASH|E\s*CASH|DIGI\s*CASH|E\s*cas)', msg or "", re.IGNORECASE))

def extract_digital_cash_from_message(msg):
    if not msg:
        return 0.0
    total = 0.0
    matches = re.finditer(r'(?:E/CASH|D/CASH|ECASH|DCASH|E-CASH|E\s*CASH|DIGI\s*CASH|E\s*cas)\s*[-:=]?\s*([\d,]+(?:\.\d+)?)', msg, re.IGNORECASE)
    for m in matches:
        try:
            total += float(m.group(1).replace(',', ''))
        except ValueError:
            pass
    return total

def split_message_by_station(msg):
    blocks = {}
    if not msg:
        return blocks
    header_regex = re.compile(r'(?:REVENUE\s+OF|EARNINGS\s+OF|UTS\s+OF|PRS\s+OF)\s+(?:UTS/|PRS/)?([A-Z]{2,6})', re.IGNORECASE)
    matches = []
    for m in header_regex.finditer(msg):
        st = m.group(1).upper()
        if st in ALL_STATIONS:
            matches.append({"station": st, "index": m.start()})
    bare_regex = re.compile(r'\b(?:UTS|PRS)/([A-Z]{2,6})\b', re.IGNORECASE)
    for m in bare_regex.finditer(msg):
        st = m.group(1).upper()
        if st in ALL_STATIONS:
            if not any(abs(x["index"] - m.start()) < 5 for x in matches):
                matches.append({"station": st, "index": m.start()})
    first_line = msg.split('\n')[0].strip().upper()
    if first_line in ALL_STATIONS and not matches:
        matches.append({"station": first_line, "index": 0})
    matches.sort(key=lambda x: x["index"])
    for i in range(len(matches)):
        start = matches[i]["index"]
        end = matches[i+1]["index"] if i + 1 < len(matches) else len(msg)
        st = matches[i]["station"]
        blocks[st] = blocks.get(st, "") + "\n" + msg[start:end]
    return blocks

# ==============================================
# GEMINI API CALL (EXACTLY 1 CALL PER MESSAGE)
# ==============================================
def call_gemini(msg):
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY missing!")
        return None

    prompt = f"""You are an expert railway data extraction assistant. Extract numbers into strict JSON.
ALL VALID STATION CODES: {', '.join(ALL_STATIONS)}

RULES:
- Map PRS & UTS fields correctly.
- NET = amount as stated. Never subtract digital payments.
- PF = exact count from explicit line. Ignore PLATFORM TKT.
- Use ONLY station codes from the list above, in UPPERCASE.

Return ONLY valid JSON (no markdown):
{{
  "prs": {{"STATION": {{"TKT":0, "PASS":0, "C/TKT":0, "C/PASS":0, "REF":0, "NET":0, "VCH":0, "POS":0, "UPI":0}}}},
  "uts": {{"STATION": {{"TKT":0, "PASS":0, "NET":0, "UPI":0, "PF":0, "MR":0, "MR AMT":0}}}}
}}

MESSAGE:
{msg}
JSON ONLY:"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096}
    }
    try:
        res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=25)
        if res.status_code == 200:
            txt = res.json()['candidates'][0]['content']['parts'][0]['text']
            txt = re.sub(r'```json\n?', '', txt, flags=re.IGNORECASE)
            txt = re.sub(r'```\n?', '', txt).strip()
            match = re.search(r'\{[\s\S]*\}', txt)
            if match:
                parsed = json.loads(match.group(0))
                parsed["prs"] = parsed.get("prs") or {}
                parsed["uts"] = parsed.get("uts") or {}
                return parsed
            print("⚠️ Gemini: no JSON block in response")
        else:
            print(f"❌ Gemini HTTP {res.status_code}: {res.text[:300]}")
    except Exception as e:
        print(f"❌ Gemini API Error: {e}")
    return None

def apply_post_processing(data, msg):
    if not data:
        return data
    station_blocks = split_message_by_station(msg)
    for st, uts_dict in list(data.get("uts", {}).items()):
        block = station_blocks.get(st)
        if block:
            pf_val = extract_pf_from_message(block)
            data["uts"][st]["PF"] = pf_val if pf_val is not None else 0
            if message_has_digital_cash(block):
                dc = extract_digital_cash_from_message(block)
                cur_upi = float(data["uts"][st].get("UPI", 0) or 0)
                if dc > 0 and cur_upi < dc:
                    data["uts"][st]["UPI"] = cur_upi + dc
    for st, prs_dict in list(data.get("prs", {}).items()):
        block = station_blocks.get(st)
        if block and message_has_digital_cash(block):
            dc = extract_digital_cash_from_message(block)
            cur_upi = float(data["prs"][st].get("UPI", 0) or 0)
            if dc > 0 and cur_upi < dc:
                data["prs"][st]["UPI"] = cur_upi + dc
    return data

# ==============================================
# UPDATE GOOGLE SHEET (1 READ + 1 BATCH WRITE)
# ==============================================
def update_google_sheet(data):
    sheet = get_sheet()
    if not sheet:
        print("❌ Could not connect to Google Sheet.")
        return False
    smap = get_station_map(sheet)
    try:
        matrix = sheet.get("A1:U60")
    except Exception as e:
        print(f"❌ Sheet read error: {e}")
        return False

    def current(r, c):
        try:
            v = matrix[r - 1][c - 1]
        except IndexError:
            return 0.0
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    updates = []
    def queue(r, c, val):
        updates.append({"range": rowcol_to_a1(r, c), "values": [[val]]})

    for st, prs_vals in data.get("prs", {}).items():
        info = smap.get(str(st).upper().strip())
        if not info:
            print(f"⚠️ Station {st} not found in sheet!")
            continue
        row = info["row"]
        for fld, val in (prs_vals or {}).items():
            try:
                v = float(val)
            except (TypeError, ValueError):
                continue
            if v > 0 and fld in PRS_COLS:
                col = PRS_COLS[fld]
                new_val = current(row, col) + v
                queue(row, col, new_val)
                print(f"✅ Updated PRS {st} {fld}: +{v} -> Total: {new_val}")

    for st, uts_vals in data.get("uts", {}).items():
        info = smap.get(str(st).upper().strip())
        if not info:
            print(f"⚠️ Station {st} not found in sheet!")
            continue
        row = info["row"]
        for fld, val in (uts_vals or {}).items():
            if fld == "PF" and not val:
                continue
            try:
                v = float(val)
            except (TypeError, ValueError):
                continue
            if v > 0:
                if info["nameCol"] == "C":
                    col = {"TKT": 4, "PASS": 5, "NET": 9, "UPI": 12,
                           "PF": 8, "MR": 9, "MR AMT": 10}.get(fld)
                else:
                    col = UTS_COLS_NU.get(fld)
                if col:
                    new_val = current(row, col) + v
                    queue(row, col, new_val)
                    print(f"✅ Updated UTS {st} {fld}: +{v} -> Total: {new_val}")

    if not updates:
        print("⚠️ Sheet update skipped: zero updates queued.")
        return True
    try:
        sheet.batch_update(updates)
        print(f"✅ Sheet batch update done ({len(updates)} cells)")
        return True
    except Exception as e:
        print(f"❌ Sheet batch update error: {e}")
        return False

# ==============================================
# WHATSAPP REPLY (CONFIRMATION)
# ==============================================
def send_whatsapp_reply(to_number, text):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        return
    try:
        url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
        headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
        payload = {"messaging_product": "whatsapp", "to": to_number, "type": "text",
                   "text": {"body": text}}
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        if r.status_code != 200:
            print(f"⚠️ WhatsApp reply failed: {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"⚠️ WhatsApp reply error: {e}")

# ==============================================
# WEBHOOK ENDPOINT
# ==============================================
@app.route("/", methods=["GET"])
def home():
    return "Bot is running ✅", 200

@app.route("/webhook", methods=["GET"])
def webhook_verify():
    # Meta webhook verification
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and challenge:
        if token == VERIFY_TOKEN:
            print("✅ Meta webhook verified successfully")
            return challenge, 200
        print(f"❌ Webhook verify FAILED. Env VERIFY_TOKEN: '{VERIFY_TOKEN}', Meta bheja: '{token}'")
        return "Verification token mismatch", 403
    return "Webhook Live and Running!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(silent=True) or {}
    found_any = False

    try:
        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                val = change.get("value", {})
                # statuses (sent/delivered/read) skip karo
                for m in val.get("messages", []):
                    found_any = True
                    if m.get("type") != "text":
                        continue
                    msg_id = m.get("id", "")
                    from_number = m.get("from", "")
                    incoming_msg = (m.get("text", {}) or {}).get("body", "").strip()
                    if not incoming_msg:
                        continue

                    # META RETRY? -> already processed -> sirf 200, NO gemini call
                    if already_processed(msg_id):
                        print(f"⏭️ Duplicate message {msg_id}, skipped (no Gemini call)")
                        continue

                    print(f"📩 New message from {from_number}: {incoming_msg[:80]}...")
                    data = call_gemini(incoming_msg)  # SIRF 1 CALL

                    if not data:
                        send_whatsapp_reply(from_number, "❌ Data samajh nahi aaya. Format check karke dobara bhejo.")
                        continue

                    data = apply_post_processing(data, incoming_msg)
                    print("Successfully Extracted Data:", json.dumps(data))

                    ok = update_google_sheet(data)
                    if ok:
                        stns = ", ".join(sorted(set(list(data.get("prs", {})) + list(data.get("uts", {})))))
                        send_whatsapp_reply(from_number, f"✅ Sheet update ho gaya: {stns}")
                    else:
                        send_whatsapp_reply(from_number, "❌ Sheet update failed. Baad me try karo.")
    except Exception as e:
        print(f"❌ Webhook processing error: {e}")

    # Meta ko hamesha 200 bhejo taaki retry storm na ho
    if not found_any:
        print("ℹ️ POST received but no messages array (status update etc.)")
    return jsonify({"status": "ok"}), 200

# ==============================================
# TEST ENDPOINTS (debugging ke liye)
# ==============================================
@app.route("/test-sheet", methods=["GET"])
def test_sheet():
    sheet = get_sheet()
    if not sheet:
        return jsonify({"ok": False, "error": "Sheet connection failed. Upar wale logs dekho."}), 200
    smap = get_station_map(sheet)
    sample = {k: v for k, v in list(smap.items())[:5]}
    return jsonify({"ok": True, "sheet": sheet.title, "stations_found": len(smap), "sample": sample}), 200

@app.route("/test-gemini", methods=["GET"])
def test_gemini():
    q = request.args.get("msg", "PRS OF DBRG TKT 10 PASS 12 NET 5000")
    data = call_gemini(q)
    return jsonify({"ok": data is not None, "result": data}), 200

# ==============================================
# STARTUP SELF-CHECK
# ==============================================
def startup_check():
    print("========== STARTUP CHECK ==========")
    print(f"SHEET_NAME: {SHEET_NAME}")
    print(f"VERIFY_TOKEN set: {bool(VERIFY_TOKEN)}")
    print(f"WHATSAPP_TOKEN set: {bool(WHATSAPP_TOKEN)}")
    print(f"PHONE_NUMBER_ID set: {bool(PHONE_NUMBER_ID)}")
    print(f"GEMINI_API_KEY set: {bool(GEMINI_API_KEY)}")
    print(f"GOOGLE_CREDENTIALS_B64 set: {bool(GOOGLE_CREDENTIALS_B64)}")
    get_sheet()
    print("===================================")

startup_check()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
    
