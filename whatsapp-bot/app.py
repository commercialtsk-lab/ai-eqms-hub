import os
import re
import json
import time
import base64
import threading
import requests
import gspread
import fcntl
from datetime import datetime, timedelta, time as dt_time
from gspread.utils import rowcol_to_a1
from google.oauth2.service_account import Credentials
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==============================================
# ENVIRONMENT VARIABLES
# ==============================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SHEET_NAME = os.environ.get("GOOGLE_SHEET_NAME", "") or os.environ.get("SHEET_NAME", "Commercial Position TSK Div NEW")

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "") or os.environ.get("SECRET_TOKEN", "")
WHATSAPP_TOKEN = (os.environ.get("META_TOKEN") or os.environ.get("WHATSAPP_TOKEN")
                  or os.environ.get("BOT_TOKEN") or "")
PHONE_NUMBER_ID = (os.environ.get("PHONE_NUMBER_ID") or os.environ.get("WHATSAPP_PHONE_NUMBER_ID") or "")

GOOGLE_CREDENTIALS_B64 = os.environ.get("GOOGLE_CREDENTIALS_B64", "")
GOOGLE_CREDENTIALS_STR = os.environ.get("GOOGLE_CREDENTIALS", "")

GEMINI_MODEL = "gemini-2.5-flash"
OSOP_LOCK_FILE = "/tmp/osop_update.lock"
IWOW_LOCK_FILE = "/tmp/iwow_update.lock"
PRS_LOCK_FILE = "/tmp/prs_update.lock"

# ---- Inward goods settings ----
IWOW_SHEET_NAME = "IWOW"
OSOP_SHEET_NAME = "OSOP"
IST_OFFSET = timedelta(hours=5, minutes=30)
BACKDATE_CUTOFF = dt_time(2, 0)         # is time se pehle process ho to purani date allowed
BACKDATE_MAX_GAP = timedelta(hours=2)   # placement itna hi pehle ka ho

GOODS_HEADERS = ["DATE", "TIME", "FROM", "TO", "WAGONS", "WAGON TYPE",
                 "COMMODITY", "LINE", "PARTY", "FREE TIME (HRS)", "FREE TIME UPTO"]

WAGON_TYPE_GUESS = {
    "CEMENT": "BCN", "CLINKER": "BOXN", "COAL": "BOXN", "NAPHTHA": "BTPN",
    "PETROL": "BTPN", "DIESEL": "BTPN", "HSD": "BTPN", "SKO": "BTPN", "OIL": "BTPN",
    "FERTILIZER": "BCNA", "FERTILISER": "BCNA", "UREA": "BCNA", "DAP": "BCNA",
    "RICE": "BCN", "FOODGRAIN": "BCN", "WHEAT": "BCN", "SUGAR": "BCN",
    "STEEL": "BOXN", "IRON": "BOXN", "STONE": "BOXN", "BALLAST": "BOXN",
    "SAND": "BOXN", "LPG": "BTPGLN", "CONTAINER": "BLC", "PETCOKE": "BOXN",
    "FLYASH": "BCFC", "FLY ASH": "BCFC", "LIMESTONE": "BOXN", "GYPSUM": "BOXN",
}

# ==============================================
# STATION ALIASES
# ==============================================
STATION_ALIASES = {
    "DBRT": ["DBRT", "DIBRUGARH TOWN"],
    "DBRG": ["DBRG", "DIBRUGARH", "DIBRUGARH JN"],
    "NTSK": ["NTSK", "NEW TINSUKIA", "NEW TINSUKIA JN", "NEWTINSUKIA", "NEW TINSUKIA JUNCTION"],
    "TSK": ["TSK", "TINSUKIA", "TINSUKIA JN", "TIN SUKIA", "TINSUKIA TOWN"],
    "MXN": ["MXN", "MARIANI", "MARIANI JN"],
    "JTTN": ["JTTN", "JORHAT TOWN", "JORHAT"],
    "SRTN": ["SRTN", "SIBSAGAR TOWN", "SIVASAGAR TOWN", "SIBSAGAR", "SIVASAGAR", "SIVSAGAR TOWN"],
    "SLGR": ["SLGR", "SIMALUGURI", "SIMALUGURI JN"],
    "GLGT": ["GLGT", "GOLAGHAT"],
    "MRHT": ["MRHT", "MORANHAT", "MORAN HAT"],
    "NAM": ["NAM", "NAMRUP"],
    "NHK": ["NHK", "NAHARKATIYA", "NAHARKATIA"],
    "FKG": ["FKG", "FURKATING", "FURKATING JN"],
    "AGI": ["AGI", "AMGURI", "AMGURI JN", "AMGURI JUNCTION"],
    "DJG": ["DJG", "DULIAJAN"],
    "LEDO": ["LEDO"],
    "MRG": ["MRG", "MARGHERITA"],
    "DBY": ["DBY", "DIGBOI"],
    "MJN": ["MJN", "MAKUM", "MAKUM JN"],
    "TTB": ["TTB", "TITABAR"],
    "BOJ": ["BOJ", "BHOJO"],
    "BFD": ["BFD", "BORHAT"],
    "SPK": ["SPK", "SAPEKHATI"],
    "CHB": ["CHB", "CHABUA"],
    "SPTR": ["SPTR", "SILAPATHAR"],
    "DMC": ["DMC", "DHEMAJI"],
    "MZS": ["MZS", "MURKONGSELEK", "MURKONG SELEK"],
    "NLP": ["NLP", "NORTH LAKHIMPUR", "N LAKHIMPUR", "NORTHLAKHIMPUR"],
    "LBI": ["LBI", "LILABARI"],
    "BGND": ["BGND", "BAGINADI"],
    "LMY": ["LMY", "LAIMEKURI"],
    "SRPN": ["SRPN", "SRIPANI"],
    "SMCP": ["SMCP", "SIMEN CHAPARI", "SIMENCHAPARI"],
    "TQM": ["TQM", "TELAM"],
    "GOM": ["GOM", "GOGAMUKH"],
    "BDLN": ["BDLN", "BORDOLONI"],
    "CKW": ["CKW", "CHALKHOA"],
    "LHL": ["LHL", "LAHOAL"],
    "DKM": ["DKM", "DIKOM"],
    "PNT": ["PNT", "PANITOLA"],
    "TII": ["TII", "TINGRAI"],
    "LXA": ["LXA", "LAKSWA", "LAKWA", "LAKUA"],
    "SFR": ["SFR", "SAFRAI"],
    "SLX": ["SLX", "SELENG HAT", "SELENGHAT"],
    "NMT": ["NMT", "NAMTIALI"],
    "ROING": ["ROING"],
    "TEZU": ["TEZU"],
    "CGF": ["CGF", "CHARIALI"],
    "DMGN": ["DMGN", "DHAMALGAON", "DHAMALGAON JN"],
    "TNGN": ["TNGN", "TANGANI"],
    "NSBG": ["NSBG", "NEW SISIBORGAON", "SISIBORGAON"],
    "KOWN": ["KOWN", "KHOWANG"],
    "NCH": ["NCH", "NAKACHARI"],
    "CMA": ["CMA", "CINNAMARA"],
    "KXL": ["KXL", "KAMARBANDHA ALI", "KAMARBANDHAALI"],
    "BBGN": ["BBGN", "BARUA BAMUNGAON", "BARUABAMUNGAON"],
    "BLMR": ["BLMR", "BHALUKMARA"],
    "NMGY": ["NMGY", "NUMALIGARH"],
    "KRHT": ["KRHT", "KHARAHAT"],
    "CCIB": ["CCIB", "CHANDI CHOWK", "CHANDICHOWKI"]
}

ALL_STATIONS = list(STATION_ALIASES.keys())

STATION_OFFICIAL = {
    "DBRT": "Dibrugarh Town", "DBRG": "Dibrugarh", "NTSK": "New Tinsukia Jn",
    "TSK": "Tinsukia Jn", "MXN": "Mariani Jn", "JTTN": "Jorhat Town",
    "SRTN": "Sibsagar Town", "SLGR": "Simaluguri Jn", "GLGT": "Golaghat",
    "MRHT": "Moranhat", "NAM": "Namrup", "NHK": "Naharkatiya",
    "FKG": "Furkating Jn", "AGI": "Amguri", "DJG": "Duliajan",
    "LEDO": "Ledo", "MRG": "Margherita", "DBY": "Digboi",
    "MJN": "Makum Jn", "TTB": "Titabar", "BOJ": "Bhojo",
    "BFD": "Borhat", "SPK": "Sapekhati", "CHB": "Chabua",
    "SPTR": "Silapathar", "DMC": "Dhemaji", "MZS": "Murkongselek",
    "NLP": "North Lakhimpur", "LBI": "Lilabari", "BGND": "Baginadi",
    "LMY": "Laimekuri", "SRPN": "Sripani", "SMCP": "Simen Chapari",
    "TQM": "Telam", "GOM": "Gogamukh", "BDLN": "Bordoloni",
    "CKW": "Chalkhoa", "LHL": "Lahoal", "DKM": "Dikom",
    "PNT": "Panitola", "TII": "Tingrai", "LXA": "Lakswa",
    "SFR": "Safrai", "SLX": "Seleng Hat", "NMT": "Namtiali",
    "ROING": "Roing", "TEZU": "Tezu", "CGF": "Chariali",
    "DMGN": "Dhamalgaon Jn", "TNGN": "Tangani", "NSBG": "New Sisiborgaon",
    "KOWN": "Khowang", "NCH": "Nakachari", "CMA": "Cinnamara",
    "KXL": "Kamarbandha Ali", "BBGN": "Barua Bamungaon", "BLMR": "Bhalukmara",
    "NMGY": "Numaligarh", "KRHT": "Kharahat", "CCIB": "CCIB"
}

PRS_COLS = {
    "TKT": 4, "PASS": 5, "C/TKT": 6, "C/PASS": 7,
    "REF": 8, "NET": 9, "VCH": 10, "POS": 11, "UPI": 12
}

UTS_COLS_NU = {
    "PF": 14, "TKT": 16, "PASS": 17, "NET": 18,
    "MR": 19, "MR AMT": 20, "UPI": 21
}

NEGATIVE_ALLOWED_FIELDS = {"NET"}

# ==============================================
# STATION RESOLUTION HELPERS
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
    if not name:
        return None
    original = str(name).upper().strip()
    n = re.sub(r'[^A-Z0-9 ]', ' ', original)
    n = re.sub(r'\s+', ' ', n).strip()

    if n in STATION_ALIASES:
        return n
    if n.replace(' ', '') in STATION_ALIASES:
        return n.replace(' ', '')

    n2 = _norm_station(n)
    if n2 in STATION_ALIASES:
        return n2
    if n2 in _alias_index:
        return _alias_index[n2]
    if n2.replace(' ', '') in _alias_index:
        return _alias_index[n2.replace(' ', '')]

    n2_clean = n2.replace(' ', '')
    for code, aliases in STATION_ALIASES.items():
        for alias in aliases:
            a_clean = alias.replace(' ', '')
            if len(n2_clean) >= 4 and (n2_clean in a_clean or a_clean in n2_clean):
                return code

    print(f"⚠️ Could not resolve station: '{original}'")
    return None

# ==============================================
# META RETRY PROTECTION
# ==============================================
PROCESSED_MSG_IDS = {}

def already_processed(msg_id):
    now = time.time()
    for k in [k for k, t in PROCESSED_MSG_IDS.items() if now - t > 600]:
        del PROCESSED_MSG_IDS[k]
    if msg_id in PROCESSED_MSG_IDS:
        return True
    PROCESSED_MSG_IDS[msg_id] = now
    return False

# ==============================================
# CREDENTIALS
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
    errors = []

    if GOOGLE_CREDENTIALS_B64:
        try:
            s = GOOGLE_CREDENTIALS_B64.strip().strip("'\"")
            s = re.sub(r"\s+", "", s)
            s += "=" * (-len(s) % 4)
            try:
                d = json.loads(base64.b64decode(s).decode("utf-8"))
            except Exception:
                d = json.loads(base64.urlsafe_b64decode(s).decode("utf-8"))
            if "private_key" in d:
                d["private_key"] = d["private_key"].replace("\\n", "\n")
            print("✅ Credentials loaded via GOOGLE_CREDENTIALS_B64")
            return d
        except Exception as e:
            errors.append(f"B64 failed: {e}")

    raw = (GOOGLE_CREDENTIALS_STR or "").strip()
    if raw:
        candidates = [raw]
        if len(raw) > 1 and raw[0] in "'\"" and raw[-1] == raw[0]:
            candidates.append(raw[1:-1])
        for cand in candidates:
            for fixed in (cand, _fix_newlines_inside_strings(cand)):
                try:
                    d = json.loads(fixed)
                    if "private_key" in d:
                        d["private_key"] = d["private_key"].replace("\\n", "\n")
                    print("✅ Credentials loaded via GOOGLE_CREDENTIALS (raw JSON)")
                    return d
                except json.JSONDecodeError:
                    pass
        errors.append("RAW JSON failed")

    print(f"❌ Credentials load failed: {' | '.join(errors) if errors else 'No credentials found'}")
    return None

# ==============================================
# GOOGLE SHEETS  (NO CACHE)
# ==============================================
def get_spreadsheet():
    creds_dict = load_credentials_dict()
    if not creds_dict:
        return None
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets",
                  "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open(SHEET_NAME)
        print(f"✅ Spreadsheet connected: '{sh.title}'")
        return sh
    except Exception as e:
        print(f"❌ Google Sheet Connection Error: {e}")
        return None

def get_sheet(sh=None):
    sh = sh or get_spreadsheet()
    if not sh:
        return None
    try:
        try:
            sheet = sh.worksheet("UTS&PRS")
        except gspread.WorksheetNotFound:
            print("⚠️ 'UTS&PRS' tab nahi mili → sheet1 use kar rahe hain")
            sheet = sh.sheet1
        print(f"✅ Tab: '{sheet.title}'")
        return sheet
    except Exception as e:
        print(f"❌ Worksheet Error: {e}")
        return None

def get_station_map(sheet):
    m = {}
    try:
        all_values = sheet.get_all_values()
    except Exception as e:
        print(f"❌ Error reading sheet: {e}")
        return m

    for i in range(2, min(30, len(all_values))):
        val = all_values[i][1] if len(all_values[i]) > 1 else ""
        if val:
            m.setdefault(str(val).upper().strip(), {"row": i + 1, "nameCol": "B"})

    for i in range(30, min(47, len(all_values))):
        val = all_values[i][12] if len(all_values[i]) > 12 else ""
        if val:
            m.setdefault(str(val).upper().strip(), {"row": i + 1, "nameCol": "M"})

    for i in range(31, min(48, len(all_values))):
        val = all_values[i][2] if len(all_values[i]) > 2 else ""
        if val:
            m.setdefault(str(val).upper().strip(), {"row": i + 1, "nameCol": "C"})

    print(f"✅ Station map ready: {len(m)} stations")
    return m

# ==============================================
# DATE / TIME PARSER
# ==============================================
def now_ist():
    return datetime.utcnow() + IST_OFFSET

def parse_date_flexible(s):
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    s = re.sub(r'(?<=\d)(st|nd|rd|th)\b', '', s, flags=re.IGNORECASE)
    formats = (
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
        "%Y-%m-%d", "%Y/%m/%d",
        "%d %b %Y", "%d %B %Y", "%d %b %y", "%d %B %y",
        "%d-%b-%Y", "%d-%b-%y", "%d %m %Y", "%d %m %y",
        "%d/%m", "%d-%m", "%d.%m", "%d %b", "%d %B",
    )
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    try:
        from dateutil import parser as _dp
        return _dp.parse(s, dayfirst=True).date()
    except Exception:
        return None

def parse_time_flexible(s):
    if not s:
        return None
    s = str(s).strip().upper()
    s = re.sub(r'\s*(HRS|HRS\.|HR|HOURS|HOUR|H)\b\.?', '', s).strip()

    m = re.search(r'(\d{1,2})\s*(?:[:\.]\s*(\d{2}))?\s*(AM|PM|A\.M\.|P\.M\.)', s)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2) or 0)
        ap = m.group(3).replace(".", "")
        if ap == "PM" and h < 12:
            h += 12
        if ap == "AM" and h == 12:
            h = 0
        if 0 <= h < 24 and 0 <= mi < 60:
            return dt_time(h, mi)

    for fmt in ("%H:%M", "%H.%M", "%H%M"):
        try:
            return datetime.strptime(s, fmt).time()
        except Exception:
            pass
    m = re.search(r'(\d{1,2})[:\.](\d{2})', s)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)}:{m.group(2)}", "%H:%M").time()
        except Exception:
            pass
    m = re.fullmatch(r'(\d{3,4})', s)
    if m:
        v = m.group(1).zfill(4)
        try:
            return datetime.strptime(v, "%H%M").time()
        except Exception:
            pass
    return None

# ==============================================
# GEMINI CORE
# ==============================================
def _extract_json(txt):
    txt = re.sub(r'```json\n?', '', txt, flags=re.IGNORECASE)
    txt = re.sub(r'```\n?', '', txt).strip()
    try:
        return json.loads(txt)
    except Exception:
        pass
    match = re.search(r'\{[\s\S]*\}', txt)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return None

def gemini_json(prompt, tries=2):
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY missing!")
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    for attempt in range(tries):
        try:
            res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=40)
            if res.status_code == 200:
                txt = res.json()['candidates'][0]['content']['parts'][0]['text']
                parsed = _extract_json(txt)
                if parsed is not None:
                    return parsed
                print("⚠️ Gemini returned no valid JSON")
            else:
                print(f"❌ Gemini HTTP {res.status_code}: {res.text[:250]}")
        except Exception as e:
            print(f"❌ Gemini Error: {e}")
        time.sleep(1.5)
    return None

# ---------- PRS / UTS / OSOP extraction ----------
def call_gemini(msg):
    station_legend = "\n".join(f'{c} = {STATION_OFFICIAL[c]}' for c in ALL_STATIONS)
    prompt = f"""You are an expert Indian Railway data extraction engine for PRS, UTS and OSOP.
Extract into STRICT JSON only.

=== OFFICIAL STATIONS ===
{station_legend}

=== OSOP ===
If message has OSOP/Osop -> put in "osop" array, each item: {{"station": code, "date": "...", "unit": "..."}}.
Keep date string exactly as written. Omit unit if not given.

=== PRS ===
"prs": {{ "<STATION CODE>": {{"TKT":n,"PASS":n,"C/TKT":n,"C/PASS":n,"REF":n,"NET":n,"VCH":n,"POS":n,"UPI":n}} }}

=== UTS ===
"uts": {{ "<STATION CODE>": {{"PF":n,"TKT":n,"PASS":n,"NET":n,"MR":n,"MR AMT":n,"UPI":n}} }}

Multi-station bundle supported. Map fields correctly. Omit nil/nill/missing values.
Output shape: {{"prs":{{}},"uts":{{}},"osop":[]}}

MESSAGE:
{msg}

JSON ONLY:"""
    parsed = gemini_json(prompt)
    if not isinstance(parsed, dict):
        return None
    parsed["prs"] = parsed.get("prs") or {}
    parsed["uts"] = parsed.get("uts") or {}
    parsed["osop"] = parsed.get("osop") or []
    if not isinstance(parsed["osop"], list):
        parsed["osop"] = [parsed["osop"]]
    return parsed

def apply_post_processing(data, msg):
    if not data:
        return data

    for key in ("prs", "uts"):
        fixed = {}
        for st, vals in (data.get(key) or {}).items():
            code = resolve_station(st)
            if code:
                fixed.setdefault(code, vals)
            else:
                print(f"❌ {key.upper()} station skipped: {st}")
        data[key] = fixed

    new_osop = []
    for e in data.get("osop", []):
        if not isinstance(e, dict):
            continue
        code = resolve_station(e.get("station"))
        if code:
            e["station"] = code
            new_osop.append(e)
    data["osop"] = new_osop
    return data

# ==============================================
# PRS / UTS SHEET UPDATE
# ==============================================
def is_cell_empty(value):
    if value is None:
        return True
    s = str(value).strip().replace(",", "").replace(" ", "")
    if s == "" or s == "-":
        return True
    if s.lower() in ("nil", "none", "null", "n/a", "na"):
        return True
    return False

def _has_any_nonzero(vals):
    if not vals:
        return False
    for v in vals.values():
        try:
            if float(v) != 0:
                return True
        except Exception:
            continue
    return False

def _is_field_allowed(v, fld):
    if v == 0:
        return False
    if fld in NEGATIVE_ALLOWED_FIELDS:
        return True
    return v > 0

def update_google_sheet(data, sh=None):
    """PRS/UTS update. Returns number of cells written."""
    sheet = get_sheet(sh)
    if not sheet:
        return 0
    try:
        matrix = sheet.get_all_values()
    except Exception as e:
        print(f"❌ Sheet read error: {e}")
        return 0

    smap = get_station_map(sheet)

    def get_current(r, c):
        try:
            return matrix[r - 1][c - 1]
        except Exception:
            return ""

    updates, queued = [], set()

    def queue(r, c, val):
        if (r, c) in queued:
            return
        queued.add((r, c))
        updates.append({"range": rowcol_to_a1(r, c), "values": [[val]]})

    for section, cols in (("prs", PRS_COLS), ("uts", UTS_COLS_NU)):
        for st, vals in (data.get(section) or {}).items():
            info = smap.get(st)
            if not info or not _has_any_nonzero(vals):
                continue
            row = info["row"]
            for fld, val in (vals or {}).items():
                try:
                    v = float(val)
                except Exception:
                    continue
                fld = str(fld).upper().strip()
                if fld not in cols or not _is_field_allowed(v, fld):
                    continue
                col = cols[fld]
                if is_cell_empty(get_current(row, col)):
                    queue(row, col, int(v) if v == int(v) else v)
                    print(f"✅ {section.upper()} {st} {fld}: wrote {v}")

    if updates:
        with open(PRS_LOCK_FILE, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                sheet.batch_update(updates, value_input_option="USER_ENTERED")
            except Exception as e:
                print(f"❌ Batch update error: {e}")
                return 0
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
    return len(updates)

# ==============================================
# OSOP SHEET UPDATE  (simple log tab - apne layout ke hisaab se badlo)
# ==============================================
def update_osop_sheet(osop_list, sh=None):
    added = []
    if not osop_list:
        return added
    sh = sh or get_spreadsheet()
    if not sh:
        return added
    try:
        try:
            ws = sh.worksheet(OSOP_SHEET_NAME)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=OSOP_SHEET_NAME, rows=500, cols=4)
            ws.append_row(["DATE", "STATION", "STATION NAME", "UNIT"], value_input_option="USER_ENTERED")
        with open(OSOP_LOCK_FILE, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                existing = {(str(r[0]).strip(), str(r[1]).strip().upper())
                            for r in ws.get_all_values()[1:] if len(r) > 1}
                rows = []
                for e in osop_list:
                    key = (str(e.get("date", "")).strip(), e["station"])
                    if key in existing:
                        continue
                    existing.add(key)
                    rows.append([key[0], e["station"], STATION_OFFICIAL.get(e["station"], ""), e.get("unit", "")])
                    added.append(f"{e['station']} {key[0]}")
                if rows:
                    ws.append_rows(rows, value_input_option="USER_ENTERED")
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
    except Exception as e:
        print(f"❌ OSOP error: {e}")
    return added

# ==============================================
# INWARD GOODS (IWOW)  --  GEMINI EXTRACTION
# ==============================================
GOODS_HINT_RE = re.compile(
    r'goods|inward|iwow|wagon|wgn|wag\b|rake|placed|placement|\bex[-\s]|arrived|'
    r'\b(BCN|BCNA|BCNHL|BOXN|BTPN|BTPGLN|BCFC|BOST|BLC)\b|cement|coal|naphtha|clinker|'
    r'fertili[sz]er|urea|petcoke|ballast|diesel|petrol|\bHSD\b|\bparty\b|\bM/S\b',
    re.IGNORECASE)

def looks_like_goods(msg):
    return bool(GOODS_HINT_RE.search(msg or ""))

def extract_goods_gemini(msg):
    now = now_ist()
    station_legend = "\n".join(f'{c} = {STATION_OFFICIAL[c]}' for c in ALL_STATIONS)
    prompt = f"""You are an expert Indian Railways (NF Railway, Tinsukia Division) goods-traffic data extraction engine.
The input is a WhatsApp message about INWARD GOODS / IWOW / goods position / rake or wagon placement.
It can be in ANY style: English, Hindi, Hinglish, abbreviations, short-hand, bullet lists, tables,
several rakes in one message, typos, mixed date/time formats. Understand the MEANING and extract every placement.

Today (IST) is {now.strftime('%d.%m.%Y')} and current time is {now.strftime('%H:%M')}.

=== STATION CODES ===
{station_legend}
Output station CODES only (e.g. Jorhat Town -> JTTN). If a station is not in the list, give the best short code or the name in UPPERCASE.

=== OUTPUT (STRICT JSON ONLY) ===
{{"goods":[{{
  "from_stn": "originating station code (words like Ex, ex-, from, X, via-origin, loaded at, despatched from). Empty string if absent",
  "to_stn": "destination / placement station code (words like to, at, placed at, for, destination). If the message heading says '<STATION> GOODS POSITION' and no other destination, use that station",
  "wagons": integer number of wagons (words like wagons, wgns, wags, BOXN-42, 'rake of 42', '42 BCN'),
  "wagon_type": "BCN / BCNA / BOXN / BTPN / BTPGLN / BCFC etc. as given. If not given, guess from commodity (cement->BCN, coal/stone/ballast->BOXN, oil/naphtha/petrol/diesel->BTPN, fertiliser/urea->BCNA)",
  "placement_time": "24 hour HH:MM (convert 9 PM -> 21:00, 2100 hrs -> 21:00, 9.30pm -> 21:30). Empty if absent",
  "placement_date": "DD.MM.YY exactly as written if written. If message says today/aaj use today's date; yesterday/kal(past) use yesterday's date. Empty if absent",
  "commodity": "UPPERCASE commodity (CEMENT, COAL, NAPHTHA, FERTILIZER ...)",
  "line": "line/siding number digits only (L/1, line no 2, Line-3, L1, siding 4 -> '1','2','3','1','4'). Empty if absent",
  "party": "full consignee / party / firm / siding owner name in UPPERCASE (after Party-, Consignee, M/s, Rcvr, Firm, Siding). Keep M/S prefix",
  "free_time": "free time hours as integer if explicitly given, otherwise empty string"
}}]}}

=== RULES ===
- One object per rake / placement. If a message lists several rakes or several lines, return several objects.
- If common info (date, party, destination) is stated once at the top or bottom and applies to all rakes, copy it into every object.
- Never invent wagons, dates or times that are not in the message. Use empty string for unknown fields.
- Ignore greetings, signatures, officer names, and unrelated text.
- Ignore entries that are clearly NIL / no placement.
- Return {{"goods":[]}} if there is no inward goods data.

=== EXAMPLES ===
Input: "JTTN GOODS POSITION:\\n11 wagons Ex-CCIB to JTTN (Cement) placed at 21:00 hrs on 01.11.26 on L/1.\\n\\nParty- M/s. Cement Corporation Ltd."
Output: {{"goods":[{{"from_stn":"CCIB","to_stn":"JTTN","wagons":11,"wagon_type":"BCN","placement_time":"21:00","placement_date":"01.11.26","commodity":"CEMENT","line":"1","party":"M/S CEMENT CORPORATION LTD","free_time":""}}]}}

Input: "Inward: 42 BOXN coal from Margherita placed Tinsukia 9.30 pm today line 2 party Coal India Ltd"
Output: {{"goods":[{{"from_stn":"MRG","to_stn":"TSK","wagons":42,"wagon_type":"BOXN","placement_time":"21:30","placement_date":"{now.strftime('%d.%m.%y')}","commodity":"COAL","line":"2","party":"COAL INDIA LTD","free_time":""}}]}}

Input: "Aaj NTSK me 2 rake aaya. 1) 40 BTPN naphtha ex DBRT 0600 hrs L-3 IOCL  2) 21 BCNA urea ex NLP 1430 hrs L-4 IFFCO"
Output: {{"goods":[{{"from_stn":"DBRT","to_stn":"NTSK","wagons":40,"wagon_type":"BTPN","placement_time":"06:00","placement_date":"{now.strftime('%d.%m.%y')}","commodity":"NAPHTHA","line":"3","party":"IOCL","free_time":""}},{{"from_stn":"NLP","to_stn":"NTSK","wagons":21,"wagon_type":"BCNA","placement_time":"14:30","placement_date":"{now.strftime('%d.%m.%y')}","commodity":"UREA","line":"4","party":"IFFCO","free_time":""}}]}}

MESSAGE:
{msg}

JSON ONLY:"""
    parsed = gemini_json(prompt)
    if not isinstance(parsed, dict):
        return []
    goods = parsed.get("goods") or []
    if isinstance(goods, dict):
        goods = [goods]
    return [g for g in goods if isinstance(g, dict)]

def parse_goods_regex(msg):
    """Gemini fail ho to backup parser."""
    out = []
    m_to = re.match(r'\s*([A-Za-z ]+?)\s+GOODS', msg, re.IGNORECASE)
    default_to = m_to.group(1).strip() if m_to else ""
    mp_all = re.search(r'party\s*[-:]\s*([^\n]+)', msg, re.IGNORECASE)
    md_all = re.search(r'(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})', msg)

    chunks = re.split(r'(?=\b\d+\s*(?:wagons?|wgns?|wags?)\b)', msg, flags=re.IGNORECASE)
    for ch in chunks:
        mw = re.match(r'\s*(\d+)\s*(?:wagons?|wgns?|wags?)\b', ch, re.IGNORECASE)
        if not mw:
            continue
        mft = re.search(r'ex[-\s]*([A-Za-z ]+?)\s+to\s+([A-Za-z ]+?)\s*(?:\(|placed|on\b|at\b|$)', ch, re.IGNORECASE)
        mc = re.search(r'\(([^)]+)\)', ch)
        mt = re.search(r'(\d{1,2}[:.]?\d{2})\s*(?:hrs|hr|hours)', ch, re.IGNORECASE)
        md = re.search(r'on\s+(\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?)', ch, re.IGNORECASE)
        ml = re.search(r'\bL\s*[/-]?\s*(\d+)|\bline\s*(?:no\.?)?\s*(\d+)', ch, re.IGNORECASE)
        mp = re.search(r'party\s*[-:]\s*([^\n]+)', ch, re.IGNORECASE) or mp_all
        out.append({
            "from_stn": mft.group(1).strip() if mft else "",
            "to_stn": mft.group(2).strip() if mft else default_to,
            "wagons": int(mw.group(1)),
            "placement_time": mt.group(1).replace(".", ":") if mt else "",
            "placement_date": md.group(1) if md else (md_all.group(1) if md_all else ""),
            "commodity": mc.group(1).strip() if mc else "",
            "line": (ml.group(1) or ml.group(2)) if ml else "",
            "party": mp.group(1).strip() if mp else "",
            "wagon_type": "", "free_time": "",
        })
    return out

# ==============================================
# INWARD GOODS  --  NORMALIZE / RULES / SHEET
# ==============================================
def _clean_party(p):
    p = re.sub(r'\s+', ' ', str(p or '')).strip().upper()
    p = re.sub(r'^M\s*/\s*S\.?\s*', 'M/S ', p)
    p = re.sub(r'[.\s]+$', '', p)
    return p

def calc_free_time_hours(wagons):
    # NOTE: apne railway rule ke hisaab se badlo
    w = int(wagons or 0)
    if w <= 0:
        return 0
    if w <= 10:
        return 3
    if w <= 30:
        return 5
    return 7

def _to_int(x):
    try:
        return int(float(str(x).strip()))
    except Exception:
        m = re.search(r'\d+', str(x or ""))
        return int(m.group(0)) if m else None

def _norm_time_str(t):
    tm = parse_time_flexible(t)
    return tm.strftime("%H:%M") if tm else None

def _norm_date_obj(s):
    d = parse_date_flexible(s)
    if d and d.year == 1900:                       # bina year wali date
        try:
            d = d.replace(year=now_ist().year)
        except ValueError:
            return None
    return d

def normalize_goods_entry(e):
    """Raw entry -> sheet-ready dict. Invalid ho to None."""
    if not isinstance(e, dict):
        return None

    now = now_ist()
    d = _norm_date_obj(e.get("placement_date")) or now.date()   # date na ho to aaj ki
    tm = parse_time_flexible(e.get("placement_time")) or now.time().replace(second=0, microsecond=0)
    t = tm.strftime("%H:%M")
    wagons = _to_int(e.get("wagons"))
    to_stn = resolve_station(e.get("to_stn")) or str(e.get("to_stn") or "").upper().strip()
    from_stn = resolve_station(e.get("from_stn")) or str(e.get("from_stn") or "").upper().strip()
    commodity = re.sub(r'\s+', ' ', str(e.get("commodity") or "")).strip().upper()

    if not (wagons and wagons > 0 and to_stn):
        print(f"⚠️ Goods entry invalid/incomplete: {e}")
        return None

    line = re.sub(r'\D', '', str(e.get("line") or ""))
    wtype = str(e.get("wagon_type") or "").upper().strip()
    if not wtype:
        wtype = next((v for k, v in WAGON_TYPE_GUESS.items() if k in commodity), "")

    placed_dt = datetime.combine(d, tm)
    free_hrs = _to_int(e.get("free_time")) or calc_free_time_hours(wagons)
    free_upto = placed_dt + timedelta(hours=free_hrs)

    return {
        "placed_dt": placed_dt,
        "date": d.strftime("%d/%m/%Y"),
        "time": t,
        "from": from_stn,
        "to": to_stn,
        "wagons": wagons,
        "wtype": wtype,
        "commodity": commodity,
        "line": line,
        "party": _clean_party(e.get("party")),
        "free_hrs": free_hrs,
        "free_upto": free_upto.strftime("%d/%m/%Y %H:%M"),
    }

def goods_date_allowed(placed_dt, now=None):
    """(allowed, reason)
    - aaj ki date: full accept
    - future: reject
    - purani date: sirf jab processing 02:00 se pehle ho aur placement max 2 ghante pehle ka ho
    """
    now = now or now_ist()
    if placed_dt.date() == now.date():
        return True, ""
    if placed_dt.date() > now.date():
        return False, "future date"
    if now.time() >= BACKDATE_CUTOFF:
        return False, "purani date (02:00 AM ke baad allowed nahi)"
    if placed_dt > now or (now - placed_dt) > BACKDATE_MAX_GAP:
        return False, "purani date aur 2 ghante se zyada purana"
    return True, ""

def _goods_key(date, time_, frm, to, wagons, commodity, line, party):
    def n(x):
        return re.sub(r'\s+', ' ', str(x or '')).strip().upper()
    d = _norm_date_obj(date)
    tm = _norm_time_str(time_)
    return (
        d.strftime("%d/%m/%Y") if d else n(date),
        tm or n(time_),
        n(frm), n(to),
        str(_to_int(wagons) or n(wagons)),
        n(commodity),
        re.sub(r'\D', '', str(line or '')),
        _clean_party(party),
    )

def _entry_key(g):
    return _goods_key(g["date"], g["time"], g["from"], g["to"],
                      g["wagons"], g["commodity"], g["line"], g["party"])

def _row_key(r):
    r = list(r) + [""] * (11 - len(r))
    # DATE, TIME, FROM, TO, WAGONS, TYPE, COMMODITY, LINE, PARTY
    return _goods_key(r[0], r[1], r[2], r[3], r[4], r[6], r[7], r[8])

def get_iwow_sheet(sh=None):
    sh = sh or get_spreadsheet()
    if not sh:
        return None
    try:
        try:
            ws = sh.worksheet(IWOW_SHEET_NAME)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=IWOW_SHEET_NAME, rows=1000, cols=len(GOODS_HEADERS))
            ws.append_row(GOODS_HEADERS, value_input_option="USER_ENTERED")
            print(f"✅ '{IWOW_SHEET_NAME}' tab bana di")
        return ws
    except Exception as e:
        print(f"❌ IWOW sheet error: {e}")
        return None

def update_goods_sheet(goods_list, msg="", sh=None):
    """Returns (added_list, skipped_list[(label, reason)])"""
    added, skipped = [], []

    entries = []
    for raw in goods_list or []:
        g = normalize_goods_entry(raw)
        if g:
            entries.append(g)
    if not entries and msg:
        print("⚠️ Gemini goods empty -> regex fallback")
        for raw in parse_goods_regex(msg):
            g = normalize_goods_entry(raw)
            if g:
                entries.append(g)
    if not entries:
        return added, [("goods data", "parse nahi hua")]

    ws = get_iwow_sheet(sh)
    if not ws:
        return added, [("goods", "IWOW sheet connect nahi hui")]

    now = now_ist()
    with open(IWOW_LOCK_FILE, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            existing = ws.get_all_values()
            seen = set()
            for r in existing[1:]:
                if any(str(c).strip() for c in r):
                    seen.add(_row_key(r))

            rows_to_add = []
            for g in entries:
                label = f"{g['wagons']}W {g['from']}→{g['to']} {g['commodity']} {g['date']} {g['time']}"

                ok, reason = goods_date_allowed(g["placed_dt"], now)
                if not ok:
                    skipped.append((label, reason))
                    continue

                k = _entry_key(g)
                if k in seen:
                    skipped.append((label, "duplicate (pehle se sheet me hai)"))
                    continue

                seen.add(k)
                rows_to_add.append([
                    g["date"], g["time"], g["from"], g["to"], g["wagons"],
                    g["wtype"], g["commodity"], g["line"], g["party"],
                    g["free_hrs"], g["free_upto"],
                ])
                added.append(label)

            if rows_to_add:
                ws.append_rows(rows_to_add, value_input_option="USER_ENTERED")
                print(f"✅ IWOW: {len(rows_to_add)} entry add hui")
        except Exception as e:
            print(f"❌ IWOW update error: {e}")
            skipped.append(("goods", f"error: {e}"))
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)

    return added, skipped

# ==============================================
# WHATSAPP
# ==============================================
def send_whatsapp(to, text):
    if not (WHATSAPP_TOKEN and PHONE_NUMBER_ID and to):
        print("⚠️ WhatsApp send config missing")
        return
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    body = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text[:4000]}}
    try:
        r = requests.post(url, headers=headers, json=body, timeout=20)
        if r.status_code >= 300:
            print(f"❌ WhatsApp send {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"❌ WhatsApp send error: {e}")

# ==============================================
# MESSAGE PIPELINE
# ==============================================
PRS_UTS_HINT_RE = re.compile(r'\b(PRS|UTS|OSOP|TKT|C/TKT|PASS|UPI|VCH|POS|NET)\b', re.IGNORECASE)

def process_message(sender, msg):
    replies = []
    try:
        goods_like = looks_like_goods(msg)
        other_like = bool(PRS_UTS_HINT_RE.search(msg))
        sh = None

        if goods_like:
            sh = get_spreadsheet()
            goods = extract_goods_gemini(msg)
            added, skipped = update_goods_sheet(goods, msg, sh)
            if added:
                replies.append("✅ Goods added:\n" + "\n".join(f"• {a}" for a in added))
            if skipped:
                replies.append("⚠️ Goods skipped:\n" + "\n".join(f"• {s} – {r}" for s, r in skipped))

        if other_like or not goods_like:
            data = apply_post_processing(call_gemini(msg), msg)
            if data and (data["prs"] or data["uts"] or data["osop"]):
                sh = sh or get_spreadsheet()
                n = update_google_sheet(data, sh) if (data["prs"] or data["uts"]) else 0
                osop_added = update_osop_sheet(data["osop"], sh)
                if n:
                    replies.append(f"✅ PRS/UTS: {n} cell update hui")
                if osop_added:
                    replies.append("✅ OSOP added:\n" + "\n".join(f"• {a}" for a in osop_added))
                if not n and not osop_added:
                    replies.append("ℹ️ PRS/UTS: koi nayi cell update nahi hui (already filled ya zero)")
            elif not goods_like:
                replies.append("❌ Data samajh nahi aaya. Format check karke dobara bhejo.")
    except Exception as e:
        print(f"❌ process_message error: {e}")
        replies.append("❌ Server error aaya, thodi der baad try karo.")

    if replies:
        send_whatsapp(sender, "\n\n".join(replies))

# ==============================================
# WEBHOOK
# ==============================================
@app.route("/", methods=["GET"])
def home():
    return "Bot running ✅", 200

@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge", "")
    if mode == "subscribe" and token and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        body = request.get_json(silent=True) or {}
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for m in value.get("messages", []) or []:
                    if m.get("type") != "text":
                        continue
                    msg_id = m.get("id")
                    if msg_id and already_processed(msg_id):
                        continue
                    text = (m.get("text") or {}).get("body", "").strip()
                    sender = m.get("from")
                    if text:
                        threading.Thread(target=process_message, args=(sender, text), daemon=True).start()
    except Exception as e:
        print(f"❌ Webhook error: {e}")
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
