import os
import re
import json
import time
import base64
import requests
import gspread
from datetime import datetime
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
    "KRHT": ["KRHT", "KHARAHAT"]
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
    "NMGY": "Numaligarh", "KRHT": "Kharahat"
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

def get_sheet():
    sh = get_spreadsheet()
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
# DATE PARSER
# ==============================================
def parse_date_flexible(s):
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    formats = (
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
        "%Y-%m-%d", "%Y/%m/%d",
        "%d %b %Y", "%d %B %Y", "%d %b %y", "%d %B %y",
        "%d %m %Y", "%d %m %y",
        "%d/%m", "%d-%m", "%d.%m",
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

# ==============================================
# GEMINI
# ==============================================
def call_gemini(msg):
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY missing!")
        return None

    station_legend = "\n".join(f'{c} = {STATION_OFFICIAL[c]}' for c in ALL_STATIONS)

    prompt = f"""You are an expert Indian Railway PRS & UTS & OSOP data extraction engine.
You work exactly like a human railway accountant. Any format, multi-station bundle, multi-line, missing labels — you understand naturally.

Extract numbers into STRICT JSON only. No explanation, no markdown.

=== OFFICIAL STATIONS ===
{station_legend}

STATION RULES:
1. Full name or code → always use CODE.
   "Sapekhati" / "SPK" → SPK
   "Bhalukmara" / "BLMR" → BLMR
   "New Tinsukia" / "ntsk" → NTSK
   "Sibsagar Town" → SRTN
   "Lakua" → LXA
   "Naharkatia" → NHK
   "Dhemaji" → DMC

=== OSOP SECTION ===
Agar message me OSOP / Osop aaya hai to "osop" array me nikaalo.
date string bilkul waisi rakho jaisi message me hai.
unit nahi diya to key omit karo.

=== PRS & UTS (MULTI-STATION BUNDLE SUPPORT) ===
Message me ek se zyada stations ka data ho sakta hai (copy-paste bundle).
Har station ka data alag-alag nikaalo.

STRICT MAPPING:
PRS:
- TKT / T/TKT → TKT
- PASS / T/PASS → PASS
- C/TKT → C/TKT
- C/PASS → C/PASS
- NET CASH / NETCASH → NET
- UPI / UPI QR / DIGI CASH / E CASH / ECASH → UPI
- REFUND / RFD / DIGI REF → REF (sum of all refunds)
- VOUCHER / VCH → VCH
- POS → POS

UTS:
- TKT → TKT
- PASS → PASS
- NET CASH → NET
- E CASH / UPI → UPI
- PF / P/TKT / PLATFORM → PF
- MR → MR
- MR AMT / AMOUNT (for MR) → MR AMT

MISSING: "nil", "nill", "-", "nahi aya" → field OMIT (0 mat do)

=== EXAMPLES ===

EXAMPLE 1 (your exact bundle style):
Input:
"REVENUE OF SPK
DATE.     02/11/2026
UTS
TKT                  294
PASS.               476
NET CASH.    17720
E CASH.          2110

PRS
TKT                 20
PASS.              58
NET CASH.    40665
UPI QR .          12580
REFUND.          1335
C/TKT.              1
C/PASS.           1
Digi ref:-            nill  ..

BLMR 
Date -02/11/2026
TKT -7
Pass -13
Amount -590/-"

Output:
{{
  "prs": {{
    "SPK": {{"TKT": 20, "PASS": 58, "NET": 40665, "UPI": 12580, "REF": 1335, "C/TKT": 1, "C/PASS": 1}}
  }},
  "uts": {{
    "SPK": {{"TKT": 294, "PASS": 476, "NET": 17720, "UPI": 2110}},
    "BLMR": {{"TKT": 7, "PASS": 13, "NET": 590}}
  }},
  "osop": []
}}

EXAMPLE 2 (OSOP multi):
Input:
"Osop dmc
26-10-26
Unit 5
Amt 600
Osop nhk
26-10-26
Amt 600
Osop ntsk
26-10-26
Amt 450
Osop ntsk
26-10-26
Unit 5
Amt 600"

Output:
{{
  "prs": {{}},
  "uts": {{}},
  "osop": [
    {{"station": "DMC", "date": "26-10-26", "unit": 5, "amount": 600}},
    {{"station": "NHK", "date": "26-10-26", "amount": 600}},
    {{"station": "NTSK", "date": "26-10-26", "amount": 450}},
    {{"station": "NTSK", "date": "26-10-26", "unit": 5, "amount": 600}}
  ]
}}

EXAMPLE 3 (terse UTS):
Input:
"Borhat uts
Pass:-7
Tkt:-5
Cash:-385
Ecash:-190"

Output:
{{
  "prs": {{}},
  "uts": {{
    "BFD": {{"TKT": 5, "PASS": 7, "NET": 385, "UPI": 190}}
  }},
  "osop": []
}}

MESSAGE:
{msg}

JSON ONLY:"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.05, "maxOutputTokens": 4096}
    }
    try:
        res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
        if res.status_code == 200:
            txt = res.json()['candidates'][0]['content']['parts'][0]['text']
            txt = re.sub(r'```json\n?', '', txt, flags=re.IGNORECASE)
            txt = re.sub(r'```\n?', '', txt).strip()
            match = re.search(r'\{[\s\S]*\}', txt)
            if match:
                parsed = json.loads(match.group(0))
                parsed["prs"] = parsed.get("prs") or {}
                parsed["uts"] = parsed.get("uts") or {}
                parsed["osop"] = parsed.get("osop") or []
                if not isinstance(parsed["osop"], list):
                    parsed["osop"] = [parsed["osop"]]
                return parsed
            print("⚠️ Gemini returned no JSON")
        else:
            print(f"❌ Gemini HTTP {res.status_code}: {res.text[:250]}")
    except Exception as e:
        print(f"❌ Gemini Error: {e}")
    return None

def apply_post_processing(data, msg):
    if not data:
        return data

    new_prs = {}
    for st, vals in data.get("prs", {}).items():
        code = resolve_station(st)
        if code:
            if code not in new_prs:
                new_prs[code] = vals
            else:
                print(f"⚠️ Duplicate PRS station '{code}' → keeping first")
        else:
            print(f"❌ Station skipped: {st}")
    data["prs"] = new_prs

    new_uts = {}
    for st, vals in data.get("uts", {}).items():
        code = resolve_station(st)
        if code:
            if code not in new_uts:
                new_uts[code] = vals
            else:
                print(f"⚠️ Duplicate UTS station '{code}' → keeping first")
        else:
            print(f"❌ UTS Station skipped: {st}")
    data["uts"] = new_uts

    new_osop = []
    for e in data.get("osop", []):
        if not isinstance(e, dict):
            continue
        code = resolve_station(e.get("station"))
        if code:
            e["station"] = code
            new_osop.append(e)
        else:
            print(f"❌ OSOP entry skipped: {e}")
    data["osop"] = new_osop

    up = msg.upper()
    if "UTS" in up and "PRS" not in up.replace("UTS", ""):
        if not data["uts"] and len(data["prs"]) == 1:
            st, vals = next(iter(data["prs"].items()))
            if isinstance(vals, dict) and not any(k in vals for k in ("C/TKT", "C/PASS", "VCH", "POS", "REF")):
                data["uts"] = {st: vals}
                data["prs"] = {}
                print(f"🔧 Moved PRS→UTS for {st}")

    return data

# ==============================================
# REGEX FALLBACK
# ==============================================
def _to_float(s):
    try:
        return float(str(s).replace(",", "").strip())
    except:
        return None

def apply_fallback_fixes(data, msg):
    if not data:
        return data

    up = msg.upper()
    osop = data.get("osop") or []

    if "OSOP" in up and not osop:
        lines = msg.splitlines()
        for i, line in enumerate(lines):
            if re.search(r'\bOSOP\b', line, re.IGNORECASE):
                window = "\n".join(lines[i:i+8])
                st_m = re.search(r'OSOP\s*[:\-]?\s*([A-Za-z][A-Za-z0-9 .]+)', window, re.IGNORECASE)
                if not st_m:
                    for j in range(i+1, min(i+4, len(lines))):
                        cand = lines[j].strip()
                        if cand and re.match(r'^[A-Za-z][A-Za-z0-9 .]+$', cand) and not re.search(r'\d{2}', cand):
                            st_m = re.match(r'^([A-Za-z][A-Za-z0-9 .]+)$', cand)
                            if st_m:
                                break
                if not st_m:
                    continue
                code = resolve_station(st_m.group(1))
                if not code:
                    continue

                date_m = re.search(r'(\d{1,4}[-/\.]\d{1,2}[-/\.]\d{1,4})', window)
                unit_m = re.search(r'(?:unit|u)\s*[:=\-]?\s*(\d+)', window, re.IGNORECASE)
                amt_m  = re.search(r'(?:amt|amount|rs\.?)\s*[:=\-]?\s*([\d,]+)', window, re.IGNORECASE)
                if not amt_m:
                    nums = re.findall(r'\b([\d,]{2,})\b', window)
                    if nums:
                        amt_m = type('X', (), {'group': lambda self, n: nums[-1]})()

                if date_m and amt_m:
                    entry = {
                        "station": code,
                        "date": date_m.group(1),
                        "amount": _to_float(amt_m.group(1))
                    }
                    if unit_m:
                        entry["unit"] = int(unit_m.group(1))
                    osop.append(entry)
                    print(f"🔧 OSOP fallback: {entry}")

        data["osop"] = osop

    return data

# ==============================================
# UPDATE SHEETS
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
        except:
            continue
    return False

def _is_field_allowed(v, fld):
    if v == 0:
        return False
    if fld in NEGATIVE_ALLOWED_FIELDS:
        return True
    return v > 0

def update_google_sheet(data):
    sheet = get_sheet()
    if not sheet:
        return False

    try:
        matrix = sheet.get_all_values()
    except Exception as e:
        print(f"❌ Sheet read error: {e}")
        return False

    smap = get_station_map(sheet)

    def get_current(r, c):
        try:
            return matrix[r-1][c-1]
        except:
            return ""

    updates = []
    queued = set()

    def queue(r, c, val):
        key = (r, c)
        if key in queued:
            return
        queued.add(key)
        updates.append({"range": rowcol_to_a1(r, c), "values": [[val]]})

    for st, vals in data.get("prs", {}).items():
        info = smap.get(st)
        if not info or not _has_any_nonzero(vals):
            continue
        row = info["row"]
        for fld, val in (vals or {}).items():
            try:
                v = float(val)
            except:
                continue
            if fld not in PRS_COLS or not _is_field_allowed(v, fld):
                continue
            col = PRS_COLS[fld]
            if is_cell_empty(get_current(row, col)):
                queue(row, col, v)
                print(f"✅ PRS {st} {fld}: wrote {v}")
            else:
                print(f"⏭️ PRS {st} {fld}: SKIPPED (already filled)")

    for st, vals in data.get("uts", {}).items():
        info = smap.get(st)
        if not info or not _has_any_nonzero(vals):
            continue
        row = info["row"]
        for fld, val in (vals or {}).items():
            if fld == "PF" and not val:
                continue
            try:
                v = float(val)
            except:
                continue
            if not _is_field_allowed(v, fld):
                continue
            if info["nameCol"] == "C":
                col = {"TKT": 4, "PASS": 5, "NET": 9, "UPI": 12, "PF": 8, "MR": 19, "MR AMT": 20}.get(fld)
            else:
                col = UTS_COLS_NU.get(fld)
            if not col:
                continue
            if is_cell_empty(get_current(row, col)):
                queue(row, col, v)
                print(f"✅ UTS {st} {fld}: wrote {v}")
            else:
                print(f"⏭️ UTS {st} {fld}: SKIPPED (already filled)")

    if updates:
        try:
            sheet.batch_update(updates)
            print(f"✅ Batch update successful ({len(updates)} cells)")
        except Exception as e:
            print(f"❌ Batch update failed: {e}")
            return False
    return True

# ==============================================
# OSOP UPDATE
# ==============================================
def update_osop_sheet(entries):
    if not entries:
        return True

    sh = get_spreadsheet()
    if not sh:
        return False

    try:
        ws = sh.worksheet("OSOP")
    except gspread.WorksheetNotFound:
        print("❌ 'OSOP' worksheet nahi mili")
        return False

    try:
        matrix = ws.get_all_values()
    except Exception as e:
        print(f"❌ OSOP read error: {e}")
        return False

    if len(matrix) < 6:
        print("❌ OSOP sheet me kam se kam 6 rows chahiye")
        return False

    def get_current(r, c):
        try:
            return matrix[r-1][c-1]
        except:
            return ""

    row5 = matrix[4] if len(matrix) > 4 else []
    date_cols = {}
    c = 3
    max_cols = max(len(row5), 40)
    while c <= max_cols:
        raw = row5[c-1] if c-1 < len(row5) else ""
        if not str(raw).strip() and c < len(row5):
            raw = row5[c]
        d = parse_date_flexible(raw)
        if d:
            date_cols[d] = (c, c + 1)
            print(f"📅 OSOP date '{raw.strip()}' → {rowcol_to_a1(5, c)}:{rowcol_to_a1(5, c+1)}")
        c += 2

    if not date_cols:
        print("❌ OSOP row 5 me koi date nahi mili")
        return False

    station_rows = {}
    for r in range(6, len(matrix) + 1):
        if r-1 >= len(matrix):
            break
        cell = matrix[r-1][1] if len(matrix[r-1]) > 1 else ""
        if not str(cell).strip():
            continue
        code = resolve_station(cell)
        if code:
            station_rows.setdefault(code, []).append(r)
            print(f"📍 OSOP row {r}: '{str(cell).strip()}' → {code}")

    if not station_rows:
        print("❌ OSOP B column me koi station nahi mila")
        return False

    updates = []
    queued = set()

    def queue(r, c, val):
        key = (r, c)
        if key in queued:
            return
        queued.add(key)
        updates.append({"range": rowcol_to_a1(r, c), "values": [[val]]})

    for e in entries:
        if not isinstance(e, dict):
            continue
        code = e.get("station")
        if code not in station_rows:
            print(f"⚠️ OSOP: '{code}' sheet me nahi mila → skip")
            continue

        rows = station_rows[code]
        d = parse_date_flexible(e.get("date"))
        if not d or d not in date_cols:
            print(f"⚠️ OSOP {code}: date '{e.get('date')}' match nahi hua → skip")
            continue

        camt, cunit = date_cols[d]

        chosen_row = None
        for r in rows:
            if is_cell_empty(get_current(r, camt)) and is_cell_empty(get_current(r, cunit)):
                chosen_row = r
                break
        if chosen_row is None:
            for r in rows:
                if is_cell_empty(get_current(r, camt)):
                    chosen_row = r
                    break

        if chosen_row is None:
            print(f"⚠️ OSOP {code} {d}: saari rows filled → skip")
            continue

        row = chosen_row
        print(f"📌 OSOP {code} {d}: using row {row}")

        amt = _to_float(e.get("amount")) if e.get("amount") is not None else None
        if amt is not None and amt != 0:
            if is_cell_empty(get_current(row, camt)):
                queue(row, camt, amt)
                print(f"✅ OSOP {code} {d}: amount {amt} → {rowcol_to_a1(row, camt)}")
            else:
                print(f"⏭️ OSOP {code} {d}: amount already filled → NO OVERWRITE")

        unit = e.get("unit")
        if unit is None or str(unit).strip() == "":
            if amt is not None:
                unit = int(amt // 100)
                print(f"🔧 unit missing → amount//100 = {unit}")
            else:
                unit = None

        if unit is not None and str(unit).strip() != "":
            if is_cell_empty(get_current(row, cunit)):
                queue(row, cunit, unit)
                print(f"✅ OSOP {code} {d}: unit {unit} → {rowcol_to_a1(row, cunit)}")
            else:
                print(f"⏭️ OSOP {code} {d}: unit already filled → NO OVERWRITE")

    if not updates:
        print("⚠️ OSOP: kuch write nahi hua")
        return True

    try:
        ws.batch_update(updates)
        print(f"✅ OSOP batch update successful ({len(updates)} cells)")
        return True
    except Exception as e:
        print(f"❌ OSOP batch update failed: {e}")
        return False

# ==============================================
# WEBHOOK
# ==============================================
@app.route("/", methods=["GET"])
def home():
    return "Bot is running ✅", 200

@app.route("/webhook", methods=["GET"])
def webhook_verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and challenge and token == VERIFY_TOKEN:
        print("✅ Webhook verified")
        return challenge, 200
    return "Forbidden", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(silent=True) or {}
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                for m in change.get("value", {}).get("messages", []):
                    if m.get("type") != "text":
                        continue
                    msg_id = m.get("id", "")
                    if already_processed(msg_id):
                        continue

                    text = (m.get("text") or {}).get("body", "").strip()
                    if not text:
                        continue

                    print(f"\n📩 Incoming:\n{text[:400]}...")
                    data = call_gemini(text)
                    if not data:
                        print("❌ Extraction failed")
                        continue

                    data = apply_post_processing(data, text)
                    data = apply_fallback_fixes(data, text)
                    print("✅ Final Data:", json.dumps(data))

                    update_google_sheet(data)

                    if data.get("osop"):
                        update_osop_sheet(data["osop"])
    except Exception as e:
        print(f"❌ Webhook Error: {e}")

    return jsonify({"status": "ok"}), 200

# ==============================================
# STARTUP
# ==============================================
def startup_check():
    print("========== STARTUP CHECK ==========")
    print(f"SHEET_NAME     : {SHEET_NAME}")
    print(f"GEMINI_API_KEY : {bool(GEMINI_API_KEY)}")
    print(f"CREDENTIALS    : {bool(GOOGLE_CREDENTIALS_STR or GOOGLE_CREDENTIALS_B64)}")
    get_sheet()
    print("===================================")

startup_check()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
