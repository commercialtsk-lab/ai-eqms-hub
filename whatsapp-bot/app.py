import os
import re
import json
import time
import base64
import requests
import gspread
import fcntl
import random
from datetime import datetime, timedelta, time as dt_time
from gspread.utils import rowcol_to_a1
from google.oauth2.service_account import Credentials
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==============================================
# ENVIRONMENT
# ==============================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SHEET_NAME = os.environ.get("GOOGLE_SHEET_NAME", "") or os.environ.get("SHEET_NAME", "Commercial Position TSK Div NEW")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "") or os.environ.get("SECRET_TOKEN", "")
WHATSAPP_TOKEN = (os.environ.get("META_TOKEN") or os.environ.get("WHATSAPP_TOKEN") or os.environ.get("BOT_TOKEN") or "")
PHONE_NUMBER_ID = (os.environ.get("PHONE_NUMBER_ID") or os.environ.get("WHATSAPP_PHONE_NUMBER_ID") or "")
GOOGLE_CREDENTIALS_B64 = os.environ.get("GOOGLE_CREDENTIALS_B64", "")
GOOGLE_CREDENTIALS_STR = os.environ.get("GOOGLE_CREDENTIALS", "")
GEMINI_MODEL = "gemini-2.5-flash"
OSOP_LOCK_FILE = "/tmp/osop_update.lock"
IWOW_LOCK_FILE = "/tmp/iwow_update.lock"

# ==============================================
# STATION ALIASES
# ==============================================
STATION_ALIASES = {
    "DBRT": ["DBRT", "DIBRUGARH TOWN"], "DBRG": ["DBRG", "DIBRUGARH", "DIBRUGARH JN"],
    "NTSK": ["NTSK", "NEW TINSUKIA", "NEW TINSUKIA JN", "NEWTINSUKIA"], "TSK": ["TSK", "TINSUKIA", "TINSUKIA JN"],
    "MXN": ["MXN", "MARIANI", "MARIANI JN"], "JTTN": ["JTTN", "JORHAT TOWN", "JORHAT"],
    "SRTN": ["SRTN", "SIBSAGAR TOWN", "SIVASAGAR TOWN", "SIBSAGAR", "SIVASAGAR"],
    "SLGR": ["SLGR", "SIMALUGURI", "SIMALUGURI JN"], "GLGT": ["GLGT", "GOLAGHAT"],
    "MRHT": ["MRHT", "MORANHAT"], "NAM": ["NAM", "NAMRUP"], "NHK": ["NHK", "NAHARKATIYA", "NAHARKATIA"],
    "FKG": ["FKG", "FURKATING"], "AGI": ["AGI", "AMGURI"], "DJG": ["DJG", "DULIAJAN"],
    "LEDO": ["LEDO"], "MRG": ["MRG", "MARGHERITA"], "DBY": ["DBY", "DIGBOI"],
    "MJN": ["MJN", "MAKUM", "MAKUM JN"], "TTB": ["TTB", "TITABAR"], "BOJ": ["BOJ", "BHOJO"],
    "BFD": ["BFD", "BORHAT"], "SPK": ["SPK", "SAPEKHATI"], "CHB": ["CHB", "CHABUA"],
    "SPTR": ["SPTR", "SILAPATHAR"], "DMC": ["DMC", "DHEMAJI"], "MZS": ["MZS", "MURKONGSELEK"],
    "NLP": ["NLP", "NORTH LAKHIMPUR"], "LBI": ["LBI", "LILABARI"], "GOM": ["GOM", "GOGAMUKH"],
    "DKM": ["DKM", "DIKOM"], "LXA": ["LXA", "LAKSWA", "LAKWA", "LAKUA"],
    "BLMR": ["BLMR", "BHALUKMARA"], "CCIB": ["CCIB"], "ROING": ["ROING"], "TEZU": ["TEZU"]
}

ALL_STATIONS = list(STATION_ALIASES.keys())
STATION_OFFICIAL = {k: (v[0] if isinstance(v, list) else v) for k, v in STATION_ALIASES.items()}

PRS_COLS = {"TKT": 4, "PASS": 5, "C/TKT": 6, "C/PASS": 7, "REF": 8, "NET": 9, "VCH": 10, "POS": 11, "UPI": 12}
UTS_COLS_NU = {"PF": 14, "TKT": 16, "PASS": 17, "NET": 18, "MR": 19, "MR AMT": 20, "UPI": 21}
NEGATIVE_ALLOWED_FIELDS = {"NET"}

# ==============================================
# HELPERS
# ==============================================
SUFFIX_RE = re.compile(r'\b(STATION|STN|JUNCTION|JN|RAILWAY|RLY)\b')

def _norm_station(s):
    s = re.sub(r'[^A-Z0-9 ]', ' ', str(s).upper())
    s = re.sub(r'\s+', ' ', s).strip()
    s = SUFFIX_RE.sub(' ', s)
    return re.sub(r'\s+', ' ', s).strip()

_alias_index = {}
for _code, _aliases in STATION_ALIASES.items():
    for _a in _aliases:
        _alias_index[_norm_station(_a)] = _code
        _alias_index[_norm_station(_a).replace(' ', '')] = _code

def resolve_station(name):
    if not name: return None
    original = str(name).upper().strip()
    n = re.sub(r'[^A-Z0-9 ]', ' ', original)
    n = re.sub(r'\s+', ' ', n).strip()
    if n in STATION_ALIASES: return n
    if n.replace(' ', '') in STATION_ALIASES: return n.replace(' ', '')
    n2 = _norm_station(n)
    if n2 in STATION_ALIASES: return n2
    if n2 in _alias_index: return _alias_index[n2]
    if n2.replace(' ', '') in _alias_index: return _alias_index[n2.replace(' ', '')]
    return None

PROCESSED_MSG_IDS = {}
def already_processed(msg_id):
    now = time.time()
    for k in [k for k, t in PROCESSED_MSG_IDS.items() if now - t > 600]:
        del PROCESSED_MSG_IDS[k]
    if msg_id in PROCESSED_MSG_IDS: return True
    PROCESSED_MSG_IDS[msg_id] = now
    return False

def _fix_newlines_inside_strings(s: str) -> str:
    out, in_str, esc = [], False, False
    for ch in s:
        if esc: out.append(ch); esc = False
        elif ch == "\\": out.append(ch); esc = True
        elif ch == '"': out.append(ch); in_str = not in_str
        elif ch == "\n" and in_str: out.append("\\n")
        else: out.append(ch)
    return "".join(out)

def load_credentials_dict():
    if GOOGLE_CREDENTIALS_B64:
        try:
            s = GOOGLE_CREDENTIALS_B64.strip().strip("'\"")
            s = re.sub(r"\s+", "", s)
            s += "=" * (-len(s) % 4)
            try: d = json.loads(base64.b64decode(s).decode("utf-8"))
            except: d = json.loads(base64.urlsafe_b64decode(s).decode("utf-8"))
            if "private_key" in d: d["private_key"] = d["private_key"].replace("\\n", "\n")
            return d
        except: pass
    raw = (GOOGLE_CREDENTIALS_STR or "").strip()
    if raw:
        for cand in [raw, raw.strip("'\"")]:
            for fixed in (cand, _fix_newlines_inside_strings(cand)):
                try:
                    d = json.loads(fixed)
                    if "private_key" in d: d["private_key"] = d["private_key"].replace("\\n", "\n")
                    return d
                except: pass
    return None

def get_spreadsheet():
    creds_dict = load_credentials_dict()
    if not creds_dict: return None
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds).open(SHEET_NAME)
    except Exception as e:
        print(f"❌ Sheet Error: {e}")
        return None

def get_sheet():
    sh = get_spreadsheet()
    if not sh: return None
    try: return sh.worksheet("UTS&PRS")
    except: return sh.sheet1

def parse_date_flexible(s):
    if not s: return None
    s = str(s).strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%y", "%Y-%m-%d"):
        try: return datetime.strptime(s, fmt).date()
        except: pass
    try:
        from dateutil import parser as _dp
        return _dp.parse(s, dayfirst=True).date()
    except: return None

def parse_time_flexible(s):
    if not s: return None
    s = str(s).strip().upper().replace("HRS", "").replace("HR", "").strip()
    for fmt in ("%H:%M", "%H.%M", "%H%M"):
        try: return datetime.strptime(s, fmt).time()
        except: pass
    m = re.search(r'(\d{1,2})[:\.](\d{2})', s)
    if m:
        try: return datetime.strptime(f"{int(m.group(1)):02d}:{m.group(2)}", "%H:%M").time()
        except: pass
    return None

def is_cell_empty(value):
    if value is None: return True
    s = str(value).strip().replace(",", "").replace(" ", "")
    return s == "" or s == "-" or s.lower() in ("nil", "none", "null", "n/a", "na")

def _to_float(s):
    try: return float(str(s).replace(",", "").strip())
    except: return None

# ==============================================
# GEMINI
# ==============================================
def call_gemini(msg):
    if not GEMINI_API_KEY: return None
    station_legend = "\n".join(f"{c} = {STATION_OFFICIAL.get(c,c)}" for c in ALL_STATIONS)
    prompt = f"""You are expert Indian Railway data extractor for PRS, UTS, OSOP and INWARD GOODS.

Extract STRICT JSON only.

Stations: {station_legend}

OSOP: put in "osop" array. Keep date as written. Omit unit if missing.

PRS/UTS: multi station supported.

INWARD GOODS (IWOW):
Any goods/placement/rake/cement/coal/naphtha message → "goods" array.
Fields: from_stn, to_stn, wagons, placement_time, placement_date, commodity (UPPER), line, party (UPPER), wagon_type, free_time.

If wagon_type missing → guess (Cement→BCN, Coal→BOXN, Naphtha→BTPN, Container→CONTAINER).
If free_time missing → leave empty (code will calculate).

Example:
"JTTN GOODS POSITION: 11 wagons Ex-CCIB to JTTN (Cement) placed at 21:00 hrs on 01.11.26 on L/1. Party- M/s. Cement Corporation Ltd."

→ {{"goods":[{{"from_stn":"CCIB","to_stn":"JTTN","wagons":11,"placement_time":"21:00","placement_date":"01.11.26","commodity":"CEMENT","line":"1","party":"M/S CEMENT CORPORATION LTD","wagon_type":"BCN","free_time":""}}]}}

MESSAGE:
{msg}

JSON ONLY:"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    try:
        res = requests.post(url, json={"contents":[{"parts":[{"text":prompt}]}], "generationConfig":{"temperature":0.05,"maxOutputTokens":4096}}, timeout=30)
        if res.status_code == 200:
            txt = res.json()['candidates'][0]['content']['parts'][0]['text']
            txt = re.sub(r'```json\n?|```', '', txt, flags=re.I).strip()
            match = re.search(r'\{[\s\S]*\}', txt)
            if match:
                parsed = json.loads(match.group(0))
                parsed.setdefault("prs", {})
                parsed.setdefault("uts", {})
                parsed.setdefault("osop", [])
                parsed.setdefault("goods", [])
                if not isinstance(parsed["osop"], list): parsed["osop"] = [parsed["osop"]]
                if not isinstance(parsed["goods"], list): parsed["goods"] = [parsed["goods"]]
                return parsed
    except Exception as e:
        print(f"❌ Gemini Error: {e}")
    return None

def apply_post_processing(data, msg):
    if not data: return data
    for key in ("prs", "uts"):
        new = {}
        for st, vals in data.get(key, {}).items():
            code = resolve_station(st)
            if code: new[code] = vals
        data[key] = new
    new_osop = []
    for e in data.get("osop", []):
        if isinstance(e, dict):
            code = resolve_station(e.get("station"))
            if code:
                e["station"] = code
                new_osop.append(e)
    data["osop"] = new_osop
    new_goods = []
    for e in data.get("goods", []):
        if isinstance(e, dict):
            if e.get("from_stn"): e["from_stn"] = resolve_station(e["from_stn"]) or str(e["from_stn"]).upper()
            if e.get("to_stn"): e["to_stn"] = resolve_station(e["to_stn"]) or str(e["to_stn"]).upper()
            new_goods.append(e)
    data["goods"] = new_goods
    return data

def apply_fallback_fixes(data, msg):
    return data

# ==============================================
# PRS / UTS UPDATE
# ==============================================
def update_google_sheet(data):
    sheet = get_sheet()
    if not sheet: return False
    try: matrix = sheet.get_all_values()
    except: return False
    smap = {}
    for i, row in enumerate(matrix):
        if i < 2: continue
        for col_idx, name_col in [(1, "B"), (12, "M"), (2, "C")]:
            if len(row) > col_idx and row[col_idx].strip():
                smap[row[col_idx].upper().strip()] = {"row": i+1, "nameCol": name_col}

    def get_current(r, c):
        try: return matrix[r-1][c-1]
        except: return ""

    updates = []
    def queue(r, c, val):
        updates.append({"range": rowcol_to_a1(r, c), "values": [[val]]})

    for st, vals in data.get("prs", {}).items():
        info = smap.get(st)
        if not info: continue
        row = info["row"]
        for fld, val in (vals or {}).items():
            try: v = float(val)
            except: continue
            if fld not in PRS_COLS or v == 0: continue
            col = PRS_COLS[fld]
            if is_cell_empty(get_current(row, col)):
                queue(row, col, v)

    for st, vals in data.get("uts", {}).items():
        info = smap.get(st)
        if not info: continue
        row = info["row"]
        for fld, val in (vals or {}).items():
            try: v = float(val)
            except: continue
            if v == 0: continue
            col = UTS_COLS_NU.get(fld)
            if not col: continue
            if is_cell_empty(get_current(row, col)):
                queue(row, col, v)

    if updates:
        try:
            sheet.batch_update(updates)
            print(f"✅ PRS/UTS updated {len(updates)} cells")
        except Exception as e:
            print(f"❌ PRS/UTS error: {e}")
    return True

# ==============================================
# OSOP UPDATE
# ==============================================
def update_osop_sheet(entries):
    if not entries: return True
    lock_fd = open(OSOP_LOCK_FILE, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        sh = get_spreadsheet()
        if not sh: return False
        try: ws = sh.worksheet("OSOP")
        except: return False

        for e in entries:
            if not isinstance(e, dict): continue
            try: matrix = ws.get_all_values()
            except: continue
            if len(matrix) < 6: continue

            def get_current(r, c):
                try: return matrix[r-1][c-1]
                except: return ""

            row5 = matrix[4] if len(matrix) > 4 else []
            date_cols = {}
            c = 3
            while c <= max(len(row5), 40):
                raw = row5[c-1] if c-1 < len(row5) else ""
                d = parse_date_flexible(raw)
                if d: date_cols[d] = (c, c+1)
                c += 2

            station_rows = {}
            for r in range(6, len(matrix)+1):
                if r-1 >= len(matrix): break
                cell = matrix[r-1][1] if len(matrix[r-1]) > 1 else ""
                if cell.strip():
                    code = resolve_station(cell)
                    if code: station_rows.setdefault(code, []).append(r)

            code = e.get("station")
            if code not in station_rows: continue
            d = parse_date_flexible(e.get("date"))
            if not d or d not in date_cols: continue
            camt, cunit = date_cols[d]
            rows = station_rows[code]

            chosen = None
            for r in rows:
                if is_cell_empty(get_current(r, camt)) and is_cell_empty(get_current(r, cunit)):
                    chosen = r; break
            if not chosen:
                for r in rows:
                    if is_cell_empty(get_current(r, camt)):
                        chosen = r; break
            if not chosen: continue

            updates = []
            amt = _to_float(e.get("amount"))
            if amt and is_cell_empty(get_current(chosen, camt)):
                updates.append({"range": rowcol_to_a1(chosen, camt), "values": [[amt]]})
            unit = e.get("unit")
            if unit is None and amt: unit = int(amt // 100)
            if unit is not None and is_cell_empty(get_current(chosen, cunit)):
                updates.append({"range": rowcol_to_a1(chosen, cunit), "values": [[unit]]})
            if updates:
                try:
                    ws.batch_update(updates)
                    print(f"✅ OSOP {code} → row {chosen}")
                except: pass
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
    return True

# ==============================================
# IWOW UPDATE - FINAL RULES
# ==============================================
def update_iwow_sheet(entries):
    if not entries: return True
    lock_fd = open(IWOW_LOCK_FILE, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        sh = get_spreadsheet()
        if not sh: return False
        try: ws = sh.worksheet("IWOW")
        except:
            print("❌ IWOW sheet nahi mili")
            return False

        try: matrix = ws.get_all_values()
        except: return False

        # First empty row from row 4
        start_row = 4
        for r in range(4, len(matrix) + 40):
            bval = matrix[r-1][1].strip() if r-1 < len(matrix) and len(matrix[r-1]) > 1 else ""
            if not bval:
                start_row = r
                break
        else:
            start_row = len(matrix) + 1

        now = datetime.now()
        today = now.date()
        yesterday = today - timedelta(days=1)
        updates = []
        current_row = start_row

        for e in entries:
            if not isinstance(e, dict): continue

            from_stn = str(e.get("from_stn") or "").upper().strip()
            to_stn   = str(e.get("to_stn") or "").upper().strip()
            wagons   = e.get("wagons")
            ptime    = parse_time_flexible(e.get("placement_time"))
            pdate    = parse_date_flexible(e.get("placement_date"))
            commodity = str(e.get("commodity") or "").upper().strip()
            line     = str(e.get("line") or "").strip()
            party    = str(e.get("party") or "").upper().strip()
            wtype    = str(e.get("wagon_type") or "").upper().strip()
            ftime    = str(e.get("free_time") or "").upper().strip()

            if not to_stn or not pdate: continue

            # ========== DATE + TIME RULE (Final) ==========
            # 1. Today → full accept (except future)
            # 2. Yesterday → only if time >= 22:00
            if ptime:
                placement_dt = datetime.combine(pdate, ptime)
                if placement_dt > now + timedelta(minutes=5):
                    print(f"⏭️ Future time reject: {placement_dt}")
                    continue

            if pdate == today:
                pass  # full accept
            elif pdate == yesterday:
                if not ptime or ptime < dt_time(22, 0):
                    print(f"⏭️ Yesterday data before 22:00 → reject")
                    continue
            else:
                print(f"⏭️ Date too old → reject")
                continue

            # ========== DUPLICATE CHECK ==========
            is_duplicate = False
            pdate_str_check = pdate.strftime("%d-%m-%Y")
            ptime_str_check = ptime.strftime("%H:%M") if ptime else ""
            for r in range(3, min(len(matrix), current_row + 5)):
                try:
                    existing_to = str(matrix[r][1]).strip().upper() if len(matrix[r]) > 1 else ""
                    existing_date = str(matrix[r][11]).strip() if len(matrix[r]) > 11 else ""
                    existing_time = str(matrix[r][10]).strip() if len(matrix[r]) > 10 else ""
                    existing_wagons = str(matrix[r][5]).strip() if len(matrix[r]) > 5 else ""
                    if (existing_to == to_stn and 
                        existing_date == pdate_str_check and 
                        existing_time == ptime_str_check and
                        existing_wagons == str(wagons or "")):
                        is_duplicate = True
                        break
                except: pass
            if is_duplicate:
                print(f"⏭️ Duplicate skipped: {to_stn} {pdate_str_check} {ptime_str_check}")
                continue

            # ========== FREE TIME + WAGON TYPE ==========
            try: wagons_num = int(float(wagons)) if wagons else 42
            except: wagons_num = 42

            if "NAPHTHA" in commodity or "NAPTHA" in commodity:
                ftime = "8 HRS"
                if not wtype: wtype = "BTPN"
            elif "CONTAINER" in commodity or "CONT" in commodity:
                wtype = "CONTAINER"
                if not ftime: ftime = "3 HRS"
            else:
                if not ftime:
                    if wagons_num <= 20:
                        ftime = "5 HRS"
                    elif wagons_num <= 30:
                        ftime = "7 HRS"
                    else:
                        ftime = "9 HRS"
                if not wtype:
                    if "CEMENT" in commodity: wtype = "BCN"
                    elif "COAL" in commodity: wtype = "BOXN"
                    elif any(x in commodity for x in ["FOOD", "GRAIN", "RICE", "WHEAT"]): wtype = "BCN"
                    elif "FERT" in commodity: wtype = "BCN"
                    else: wtype = "BCN"

            # Arrival time
            arrival_time_str = ""
            arrival_date_str = pdate.strftime("%d-%m-%Y")
            ptime_str = ptime.strftime("%H:%M") if ptime else ""
            pdate_str = pdate.strftime("%d-%m-%Y")

            if ptime:
                delta = random.choice([25, 30, 35, 40])
                placement_dt = datetime.combine(pdate, ptime)
                arrival_dt = placement_dt - timedelta(minutes=delta)
                arrival_time_str = arrival_dt.strftime("%H:%M")
                arrival_date_str = arrival_dt.strftime("%d-%m-%Y")

            def q(col, val):
                if val is not None and str(val).strip():
                    updates.append({"range": rowcol_to_a1(current_row, col), "values": [[val]]})

            q(2, to_stn)            # B
            q(3, line)              # C
            q(4, wtype)             # D
            q(5, commodity)         # E
            q(6, wagons)            # F
            q(8, wagons)            # H
            q(9, arrival_time_str)  # I
            q(10, arrival_date_str) # J
            q(11, ptime_str)        # K
            q(12, pdate_str)        # L
            q(18, ftime)            # R
            q(21, from_stn)         # U
            q(23, party)            # W

            print(f"✅ IWOW row {current_row}: {from_stn}→{to_stn} | {wagons} | {commodity} | {ftime} | {wtype}")
            current_row += 1

        if updates:
            try:
                ws.batch_update(updates)
                print(f"✅ IWOW updated {len(updates)} cells")
            except Exception as e:
                print(f"❌ IWOW error: {e}")
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
    return True

# ==============================================
# WEBHOOK
# ==============================================
@app.route("/", methods=["GET"])
def home():
    return "Bot is running ✅", 200

@app.route("/webhook", methods=["GET"])
def webhook_verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "Forbidden", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(silent=True) or {}
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                for m in change.get("value", {}).get("messages", []):
                    if m.get("type") != "text": continue
                    msg_id = m.get("id", "")
                    if already_processed(msg_id): continue
                    text = (m.get("text") or {}).get("body", "").strip()
                    if not text: continue
                    print(f"\n📩 {text[:300]}...")
                    data = call_gemini(text)
                    if not data: continue
                    data = apply_post_processing(data, text)
                    data = apply_fallback_fixes(data, text)
                    print("✅ Data:", json.dumps(data, ensure_ascii=False)[:500])
                    update_google_sheet(data)
                    if data.get("osop"): update_osop_sheet(data["osop"])
                    if data.get("goods"): update_iwow_sheet(data["goods"])
    except Exception as e:
        print(f"❌ Webhook Error: {e}")
    return jsonify({"status": "ok"}), 200

def startup_check():
    print("========== STARTUP ==========")
    print(f"SHEET: {SHEET_NAME}")
    print(f"GEMINI: {bool(GEMINI_API_KEY)}")
    get_sheet()
    print("=============================")

startup_check()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
