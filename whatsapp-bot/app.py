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
IWOW_GRACE_HOUR = int(os.environ.get("IWOW_GRACE_HOUR", "6"))

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
    "SRTN": ["SRTN", "SIBSAGAR TOWN", "SIVASAGAR TOWN", "SIBSAGAR", "SIVASAGAR"],
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
    "LXA": ["LXA", "LAKSWA"],
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
    "CCIB": ["CCIB", "CHANDI CHOWK", "CHANDICHOWKI"],
    "MRLB": ["MRLB", "MAL BAZAR", "MALBAZAR", "MAL JUNCTION", "MAL JN"],
    "BLZ":  ["BLZ", "BADARPUR", "BADARPUR JN"],
    "FCGC": ["FCGC", "FCI", "FCI SIDING", "FOOD CORPORATION"]
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
    "NMGY": "Numaligarh", "KRHT": "Kharahat", "CCIB": "CCIB",
    "MRLB": "Mal Bazar", "BLZ": "Badarpur Jn", "FCGC": "FCI Siding"
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

CONTAINER_WAGON_CODES = {"BLC", "BFKN", "BLL", "BLH", "BLCN", "BLCA", "BLLA", "CFN", "CONTR", "CONT"}

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
# GOOGLE SHEETS
# ==============================================
def get_sheet():
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
            sheet = sh.worksheet("UTS&PRS")
        except gspread.WorksheetNotFound:
            print("⚠️ 'UTS&PRS' tab nahi mili → sheet1 use kar rahe hain")
            sheet = sh.sheet1
        print(f"✅ Google Sheet connected: '{sh.title}' / tab: '{sheet.title}'")
        return sheet
    except Exception as e:
        print(f"❌ Google Sheet Connection Error: {e}")
        return None

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
# DATE / TIME PARSERS
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

def parse_time_flexible(s):
    if s is None:
        return None
    s = str(s).strip().upper()
    if not s:
        return None
    s = re.sub(r'\b(HRS|HR|HOURS|HOUR)\b', '', s).strip()
    s = s.replace('.', ':').replace(' ', '')
    for fmt in ("%H:%M", "%H%M"):
        try:
            return datetime.strptime(s, fmt).time()
        except Exception:
            pass
    m = re.search(r'(\d{1,2}):(\d{2})', s)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)}:{m.group(2)}", "%H:%M").time()
        except Exception:
            pass
    return None

def ist_now():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow() + timedelta(hours=5, minutes=30)

# ==============================================
# GEMINI — fully natural prompt
# ==============================================
def call_gemini(msg):
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY missing!")
        return None

    station_legend = "\n".join(f'{c} = {STATION_OFFICIAL[c]}' for c in ALL_STATIONS)

    prompt = f"""You are an expert Indian Railway data extraction engine for the Tinsukia Division.
You read WhatsApp messages like a seasoned railway accountant — messy formats, broken lines, Hinglish, typos, garbled paste, squished text. You understand naturally. Trust your own judgement.

Return ONE JSON object with these keys (all present, empty if nothing found):
  "prs"   : {{ "<STATION_CODE>": {{ "TKT":num, "PASS":num, "C/TKT":num, "C/PASS":num, "REF":num, "NET":num, "VCH":num, "POS":num, "UPI":num }} }}
  "uts"   : {{ "<STATION_CODE>": {{ "PF":num, "TKT":num, "PASS":num, "NET":num, "MR":num, "MR AMT":num, "UPI":num }} }}
  "osop"  : [ {{ "station":"CODE", "date":"as written", "amount":num, "unit":num or omit }} ]
  "goods" : [ {{ "from_stn":"CODE", "to_stn":"CODE", "wagons":num, "placement_time":"HH:MM", "placement_date":"as written", "commodity":"UPPERCASE", "line":"just number or comma list", "party":"FULL NAME UPPERCASE", "wagon_type":"optional", "weight":num or omit, "freight":num or omit }} ]

=== OFFICIAL STATIONS (CODE = Full Name) ===
{station_legend}

Rules of thumb (apply with judgement — don't over-apply):
- Station full name OR code → always use the CODE as key.
- PRS NET = net cash only (never add UPI/digi cash).
- REF = SUM of all refunds (cash + digi + pos + upi refunds).
- UTS NET = net cash. UPI cash separate. J/Amount / journey amount → NET.
- UTS J/TKT / journey tickets → TKT ; J/Pass → PASS (when T/TKT or T/Pass absent).
- MR + MR AMT both → always capture both.
- PF / P/TKT / PLT / PLATFORM / "M" → all map to PF.
- Missing values (nil, -, "nahi aya") → omit the key. Don't insert 0.
- Negative numbers → keep sign.

=== INWARD GOODS / IWOW ===
Any message about goods placement / rake / wagons / inward / container / cement / coal / naphtha / freight / M/s. → extract into "goods" array.
Fields per goods entry:
- "from_stn" / "to_stn": station codes
- "wagons": number of wagons (parse "14 wagons" / "Load - 14 wagons" / "Rake - 60")
- "placement_time": HH:MM 24-hour
- "placement_date": date exactly as written
- "commodity": UPPERCASE. If the message mentions container, container wagon type, or the container is being loaded → commodity = "CONTAINER".
- "line": just the digit. **If the message splits wagons across multiple lines (LINE NO 4 - 05 WAGONS, LINE NO 5 - 02 WAGONS etc.), create ONE goods entry PER LINE with the respective wagons count.** If a single line mentions multiple lines together (L/4,5,6), use "4,5,6".
- "party": full UPPERCASE
- "wagon_type": optional — if any container wagon code (BLC, BFKN, BLL, BLH, BLCN, CFN) mentioned, use it
- "weight": optional number
- "freight": optional number

=== MULTI-LINE EXAMPLE (very important — CRACK THIS FORMAT) ===
Input:
"FCGC GOODS POSITION.
21 WAGONS EX -BLZ TO FCGC (RICE) PLACED AT  05:15 HRS  ON DATE 03/11/26 
LINE NO 4- 05 WAGONS
LINE NO 5- 02 WAGONS 
LINE NO 6 - 14 WAGONS
M/S- FOOD CORPORATION OF INDIA ASSAM
(RAKE DEMAND)"

Expected goods (3 entries — one per LINE NO):
[
  {{
    "from_stn": "BLZ",
    "to_stn": "FCGC",
    "wagons": 5,
    "placement_time": "05:15",
    "placement_date": "03/11/26",
    "commodity": "RICE",
    "line": "4",
    "party": "M/S FOOD CORPORATION OF INDIA ASSAM"
  }},
  {{
    "from_stn": "BLZ",
    "to_stn": "FCGC",
    "wagons": 2,
    "placement_time": "05:15",
    "placement_date": "03/11/26",
    "commodity": "RICE",
    "line": "5",
    "party": "M/S FOOD CORPORATION OF INDIA ASSAM"
  }},
  {{
    "from_stn": "BLZ",
    "to_stn": "FCGC",
    "wagons": 14,
    "placement_time": "05:15",
    "placement_date": "03/11/26",
    "commodity": "RICE",
    "line": "6",
    "party": "M/S FOOD CORPORATION OF INDIA ASSAM"
  }}
]
(Total wagons across lines = 5+2+14 = 21, which matches the "21 WAGONS" header. Always preserve per-line wagon split if lines are given separately.)

=== SINGLE LINE EXAMPLE ===
Input:
"DT - 02/11/26
EX MRLB  TO SPTR
LINE NO- 4
Load - 14wagons (Rake demand)
Commodity - Cement
Weight -896
Freight - 2716325
P/TIME- 21:30 HRS
PARTY -M/S ACC"
Expected:
{{
  "from_stn": "MRLB",
  "to_stn": "SPTR",
  "wagons": 14,
  "placement_time": "21:30",
  "placement_date": "02/11/26",
  "commodity": "CEMENT",
  "line": "4",
  "party": "M/S ACC",
  "weight": 896,
  "freight": 2716325
}}

=== FEW-SHOT EXAMPLES (PRS/UTS) ===

Example A — terse UTS:
Input:
"Borhat uts
Pass:-7
Tkt:-5
Cash:-385
Ecash:-190"
Output:
{{"prs": {{}}, "uts": {{"BFD": {{"TKT": 5, "PASS": 7, "NET": 385, "UPI": 190}}}}, "osop": [], "goods": []}}

Example B — J/Amount is UTS NET:
Input:
"MXN STN ON 02/11/2026
PRS
T/TKT -98
T/Pass -205
Net Cash -146315
RFD -905
UPI -35460
VCH -31220
C/TKT -2
C/Pass -2
UTS
PF TKT -69
J/TKT -686
J/Pass -881
J/Amount -83970
Ecash -33905
MR -22
MR Amount-44610
VCH -8896
RFD -9526"
Output:
{{
  "prs": {{"MXN": {{"TKT": 98, "PASS": 205, "NET": 146315, "REF": 905, "UPI": 35460, "VCH": 31220, "C/TKT": 2, "C/PASS": 2}}}},
  "uts": {{"MXN": {{"PF": 69, "TKT": 686, "PASS": 881, "NET": 83970, "UPI": 33905, "MR": 22, "MR AMT": 44610}}}},
  "osop": [], "goods": []
}}

Example C — OSOP:
Input:
"Osop dmc
26-10-26
Unit 5
Amt 600
Osop nhk
26-10-26
Amt 600"
Output:
{{"prs": {{}}, "uts": {{}}, "osop": [
  {{"station": "DMC", "date": "26-10-26", "unit": 5, "amount": 600}},
  {{"station": "NHK", "date": "26-10-26", "amount": 600}}
], "goods": []}}

MESSAGE:
\"\"\"{msg}\"\"\"

JSON only, no markdown:"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096}
    }
    try:
        res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=45)
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
                parsed["goods"] = parsed.get("goods") or []
                if not isinstance(parsed["osop"], list):
                    parsed["osop"] = [parsed["osop"]]
                if not isinstance(parsed["goods"], list):
                    parsed["goods"] = [parsed["goods"]]
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
            new_prs.setdefault(code, vals)
    data["prs"] = new_prs

    new_uts = {}
    for st, vals in data.get("uts", {}).items():
        code = resolve_station(st)
        if code:
            new_uts.setdefault(code, vals)
    data["uts"] = new_uts

    new_osop = []
    for e in data.get("osop", []):
        if not isinstance(e, dict):
            continue
        code = resolve_station(e.get("station"))
        if code:
            e["station"] = code
            new_osop.append(e)
    data["osop"] = new_osop

    new_goods = []
    for e in data.get("goods", []):
        if not isinstance(e, dict):
            continue
        if e.get("from_stn"):
            e["from_stn"] = resolve_station(e["from_stn"]) or str(e["from_stn"]).upper()
        if e.get("to_stn"):
            e["to_stn"] = resolve_station(e["to_stn"]) or str(e["to_stn"]).upper()

        comm = str(e.get("commodity") or "").upper()
        wtype = str(e.get("wagon_type") or "").upper()
        if ("CONTAINER" in comm or "CONT" in comm or
                wtype in CONTAINER_WAGON_CODES or "CONTAINER" in wtype):
            e["commodity"] = "CONTAINER"

        # Normalise line field — keep as-is if it's a comma list, else string digit
        ln = e.get("line")
        if ln is not None:
            ln_str = str(ln).strip()
            if "," in ln_str:
                nums = re.findall(r'\d+', ln_str)
                e["line"] = ",".join(nums) if nums else ln_str
            else:
                m = re.search(r'\d+', ln_str)
                e["line"] = m.group(0) if m else ln_str

        new_goods.append(e)
    data["goods"] = new_goods

    up = msg.upper()
    if "UTS" in up and "PRS" not in up.replace("UTS", ""):
        if not data["uts"] and len(data["prs"]) == 1:
            st, vals = next(iter(data["prs"].items()))
            if isinstance(vals, dict) and not any(k in vals for k in ("C/TKT", "C/PASS", "VCH", "POS", "REF")):
                data["uts"] = {st: vals}
                data["prs"] = {}

    return data

# ==============================================
# REGEX FALLBACK
# ==============================================
def _to_float(s):
    try:
        return float(str(s).replace(",", "").strip())
    except:
        return None

def _find_stations_in_text(msg):
    up = msg.upper()
    found = set()
    for code, aliases in STATION_ALIASES.items():
        for a in aliases:
            if re.search(r'\b' + re.escape(a) + r'\b', up):
                found.add(code)
                break
    return found

def _parse_multi_line_goods(msg):
    """
    Detects messages where wagons are split across multiple LINE NO lines:
      LINE NO 4 - 05 WAGONS
      LINE NO 5 - 02 WAGONS
      LINE NO 6 - 14 WAGONS
    Returns a list of goods entries (one per line), or [] if pattern not found.
    """
    up = msg.upper()

    # Header info
    from_m = re.search(r'\bEX\s*[-:/]?\s*([A-Z]{2,6})\b', up)
    to_m   = re.search(r'\bTO\s+([A-Z]{2,6})\b', up)
    if not from_m or not to_m:
        return []
    from_stn = resolve_station(from_m.group(1))
    to_stn   = resolve_station(to_m.group(1))
    if not from_stn or not to_stn:
        return []

    # Every "LINE NO <n> ... <x> WAGON[S]" line
    line_hits = re.findall(
        r'LINE\s*(?:NO\.?|NUMBER|NUM)?\s*[-:=]?\s*(\d+)\s*[-–:=]?\s*(\d+)\s*WAGON',
        up
    )
    if len(line_hits) < 2:
        return []

    comm_m  = re.search(r'\(([A-Z][A-Z\s]+)\)', up)
    if not comm_m:
        comm_m = re.search(r'COMMODITY\s*[-:=]?\s*([A-Z][A-Z\s]+)', up)
    commodity = comm_m.group(1).strip() if comm_m else ""

    ptime_m = re.search(r'PLACED\s+AT\s+(\d{1,2}[:.]\d{2})', up)
    if not ptime_m:
        ptime_m = re.search(r'P/?TIME\s*[-:=]?\s*(\d{1,2}[:.]\d{2})', up)
    ptime = ptime_m.group(1) if ptime_m else ""

    pdate_m = re.search(r'(?:ON\s+DATE|DT|DATE)\s*[-:=]?\s*(\d{1,4}[-/\.]\d{1,2}[-/\.]\d{1,4})', up)
    if not pdate_m:
        pdate_m = re.search(r'(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4})', up)
    pdate = pdate_m.group(1) if pdate_m else ""

    party_m = re.search(r'M/S\s*[-:=]?\s*([A-Z][A-Z0-9 ./&()\-]+)', msg.upper())
    party = party_m.group(1).strip() if party_m else ""

    out = []
    for line_no, wagons in line_hits:
        out.append({
            "from_stn": from_stn,
            "to_stn": to_stn,
            "wagons": int(wagons),
            "placement_time": ptime,
            "placement_date": pdate,
            "commodity": commodity,
            "line": line_no,
            "party": party
        })
    print(f"🔧 Multi-line goods parsed: {len(out)} entries")
    return out

def apply_fallback_fixes(data, msg):
    if not data:
        return data

    up = msg.upper()
    uts = data.get("uts") or {}
    prs = data.get("prs") or {}

    # Terse UTS
    if not uts and "UTS" in up and "NETCASH" not in up.replace(" ", "") and "DIGI" not in up:
        found = _find_stations_in_text(msg)
        if len(found) == 1:
            st = next(iter(found))
            vals = {}
            m = re.search(r'(?:T\s?/\s?TKT|TKT|TICKETS?)\s*[:=\-]*\s*([\d,]+)', up)
            if m: vals["TKT"] = _to_float(m.group(1))
            m = re.search(r'(?:T\s?/\s?PASS|PASS|PAX)\s*[:=\-]*\s*([\d,]+)', up)
            if m: vals["PASS"] = _to_float(m.group(1))
            m = re.search(r'(?<![A-Z])CASH\s*[:=\-]*\s*([\d,]+)', up)
            if m: vals["NET"] = _to_float(m.group(1))
            m = re.search(r'E\s?[-/]?\s?CASH\s*[:=\-]*\s*([\d,]+)', up)
            if m: vals["UPI"] = _to_float(m.group(1))
            vals = {k: v for k, v in vals.items() if v is not None}
            if vals:
                uts[st] = vals
                data["uts"] = uts

    # MR + MR AMT
    if len(uts) == 1:
        st, vals = next(iter(uts.items()))
        vals = vals if isinstance(vals, dict) else {}
        if not vals.get("MR AMT"):
            m = re.search(r'\bMR\s*[=:]?\s*([\d,]+)\s*(?:A\s?M?O?U?N?T|AMT|AOUNT|AMNT)\s*[=:]?\s*([\d,]+)', up)
            if m:
                if not vals.get("MR"):
                    v = _to_float(m.group(1))
                    if v is not None: vals["MR"] = v
                v = _to_float(m.group(2))
                if v is not None: vals["MR AMT"] = v
        if not vals.get("PF"):
            m = re.search(r'\b(?:P\s?/\s?TKT|PF|PLT|PLATFORM)\s*[=:]?\s*([\d,]+)', up)
            if m:
                v = _to_float(m.group(1))
                if v is not None: vals["PF"] = v
        uts[st] = vals

    # UTS NET from J/Amount
    if len(uts) == 1:
        st, vals = next(iter(uts.items()))
        vals = vals if isinstance(vals, dict) else {}
        if not vals.get("NET"):
            m = re.search(r'J\s*/?\s*(?:AMOUNT|AMT)\s*[-:=]?\s*([\d,]+)', up)
            if m:
                v = _to_float(m.group(1))
                if v is not None: vals["NET"] = v
        if not vals.get("TKT"):
            m = re.search(r'J\s*/?\s*TKT\s*[-:=]?\s*([\d,]+)', up)
            if m:
                v = _to_float(m.group(1))
                if v is not None: vals["TKT"] = v
        if not vals.get("PASS"):
            m = re.search(r'J\s*/?\s*(?:PASS|PAX)\s*[-:=]?\s*([\d,]+)', up)
            if m:
                v = _to_float(m.group(1))
                if v is not None: vals["PASS"] = v
        uts[st] = vals

    # PRS REF total
    if len(prs) == 1:
        st, vals = next(iter(prs.items()))
        vals = vals if isinstance(vals, dict) else {}
        if not vals.get("REF"):
            amounts = re.findall(r'\b(?:RFD|REFUND|REF)\s*[=:]?\s*([\d,]+)', up)
            nums = [n for n in (_to_float(a) for a in amounts) if n is not None]
            if nums: vals["REF"] = sum(nums)
        prs[st] = vals

    # OSOP fallback
    osop = data.get("osop") or []
    if "OSOP" in up and not osop:
        lines = msg.splitlines()
        for i, line in enumerate(lines):
            if re.search(r'\bOSOP\b', line, re.IGNORECASE):
                window = "\n".join(lines[i:i+8])
                st_m = re.search(r'OSOP\s*[:\-]?\s*([A-Za-z][A-Za-z0-9 .]+)', window, re.IGNORECASE)
                if not st_m: continue
                code = resolve_station(st_m.group(1))
                if not code: continue
                date_m = re.search(r'(\d{1,4}[-/\.]\d{1,2}[-/\.]\d{1,4})', window)
                unit_m = re.search(r'(?:unit|u)\s*[:=\-]?\s*(\d+)', window, re.IGNORECASE)
                amt_m  = re.search(r'(?:amt|amount|rs\.?)\s*[:=\-]?\s*([\d,]+)', window, re.IGNORECASE)
                if date_m and amt_m:
                    entry = {"station": code, "date": date_m.group(1),
                             "amount": _to_float(amt_m.group(1))}
                    if unit_m: entry["unit"] = int(unit_m.group(1))
                    osop.append(entry)
        data["osop"] = osop

    # 🔧 Multi-line goods detection — overrides Gemini if lines are split
    multi = _parse_multi_line_goods(msg)
    if multi:
        data["goods"] = multi
        print(f"🔧 Multi-line goods override applied ({len(multi)} entries)")

    return data

# ==============================================
# UPDATE SHEET
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

    lock_fd = open(OSOP_LOCK_FILE, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

        sh = get_spreadsheet()
        if not sh:
            return False

        try:
            ws = sh.worksheet("OSOP")
        except gspread.WorksheetNotFound:
            print("❌ 'OSOP' worksheet nahi mili")
            return False

        for e in entries:
            if not isinstance(e, dict):
                continue

            try:
                matrix = ws.get_all_values()
            except Exception:
                continue

            if len(matrix) < 6:
                continue

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
                c += 2

            if not date_cols:
                continue

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

            code = e.get("station")
            if code not in station_rows:
                continue

            rows = station_rows[code]
            d = parse_date_flexible(e.get("date"))
            if not d or d not in date_cols:
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
                continue

            row = chosen_row
            updates = []

            amt = _to_float(e.get("amount")) if e.get("amount") is not None else None
            if amt is not None and amt != 0:
                if is_cell_empty(get_current(row, camt)):
                    updates.append({"range": rowcol_to_a1(row, camt), "values": [[amt]]})

            unit = e.get("unit")
            if unit is None or str(unit).strip() == "":
                if amt is not None:
                    unit = int(amt // 100)
            if unit is not None and str(unit).strip() != "":
                if is_cell_empty(get_current(row, cunit)):
                    updates.append({"range": rowcol_to_a1(row, cunit), "values": [[unit]]})

            if updates:
                try:
                    ws.batch_update(updates)
                    print(f"✅ OSOP {code} {d}: written row {row}")
                except Exception as ex:
                    print(f"❌ OSOP write failed: {ex}")

    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()

    return True

# ==============================================
# IWOW UPDATE
# ==============================================
def _norm_str(v):
    return str(v or "").strip().upper()

def update_iwow_sheet(entries):
    if not entries:
        return True

    lock_fd = open(IWOW_LOCK_FILE, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

        sh = get_spreadsheet()
        if not sh:
            return False

        try:
            ws = sh.worksheet("IWOW")
        except gspread.WorksheetNotFound:
            print("❌ 'IWOW' worksheet nahi mili")
            return False

        try:
            matrix = ws.get_all_values()
        except Exception as e:
            print(f"❌ IWOW read error: {e}")
            return False

        start_row = 4
        for r in range(4, len(matrix) + 50):
            bval = ""
            if r - 1 < len(matrix) and len(matrix[r - 1]) > 1:
                bval = str(matrix[r - 1][1]).strip()
            if not bval:
                start_row = r
                break
        else:
            start_row = len(matrix) + 1

        now = ist_now()
        today = now.date()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)
        grace_cutoff = dt_time(IWOW_GRACE_HOUR, 0)

        print(f"🕐 IWOW now (IST): {now.strftime('%Y-%m-%d %H:%M')} | today={today} | yesterday={yesterday} | grace_cutoff={grace_cutoff}")

        updates = []
        current_row = start_row

        for e in entries:
            if not isinstance(e, dict):
                continue

            from_stn  = _norm_str(e.get("from_stn"))
            to_stn    = _norm_str(e.get("to_stn"))
            wagons    = e.get("wagons")
            ptime     = parse_time_flexible(e.get("placement_time"))
            pdate     = parse_date_flexible(e.get("placement_date"))
            commodity = _norm_str(e.get("commodity"))
            line      = _norm_str(e.get("line"))
            party     = _norm_str(e.get("party"))
            wtype     = _norm_str(e.get("wagon_type"))
            ftime     = _norm_str(e.get("free_time"))

            if not to_stn or not pdate:
                print(f"⏭️ Missing to_stn/date → skip")
                continue

            print(f"🔎 {from_stn}→{to_stn} | date={pdate} time={ptime} wagons={wagons} line={line}")

            # ==========================================
            # DATE ACCEPTANCE — 24-hour clock in IST
            #  • Today: any past time (reject only future >5 min)
            #  • Yesterday: only if placement >= 22:00 AND now < grace_cutoff (06:00)
            #    → "forgot 22:00, remembered 2 AM" grace window
            #  • Tomorrow: only if within 30 min (edge)
            #  • Anything else: reject
            # ==========================================
            accept = False
            reason = ""

            if pdate == today:
                if ptime:
                    placement_dt = datetime.combine(pdate, ptime)
                    if placement_dt > now + timedelta(minutes=5):
                        reason = f"future time {placement_dt.strftime('%H:%M')} (now {now.strftime('%H:%M')})"
                    else:
                        accept = True
                else:
                    accept = True

            elif pdate == yesterday:
                if ptime and ptime >= dt_time(22, 0) and now.time() < grace_cutoff:
                    accept = True
                    reason = f"yesterday 22:00+ within grace (now {now.strftime('%H:%M')})"
                else:
                    if not ptime:
                        reason = "yesterday without time"
                    elif ptime < dt_time(22, 0):
                        reason = f"yesterday pre-22:00 ({ptime.strftime('%H:%M')})"
                    else:
                        reason = f"yesterday 22:00+ but grace passed (now {now.strftime('%H:%M')})"

            elif pdate == tomorrow:
                if ptime:
                    placement_dt = datetime.combine(pdate, ptime)
                    if placement_dt <= now + timedelta(minutes=30):
                        accept = True
                    else:
                        reason = "tomorrow pre-report"
                else:
                    reason = "tomorrow pre-report"

            else:
                reason = f"date out of range ({pdate})"

            if not accept:
                print(f"⏭️ Rejected ({reason})")
                continue

            pdate_str_check  = pdate.strftime("%d-%m-%Y")
            ptime_str_check  = ptime.strftime("%H:%M") if ptime else ""
            wagons_str_check = str(wagons or "").strip()

            # Duplicate check includes `line` so multi-line entries each get their own row
            is_duplicate = False
            for r in range(3, len(matrix)):
                row = matrix[r]
                existing_to        = _norm_str(row[1])   if len(row) > 1  else ""
                existing_line      = _norm_str(row[2])   if len(row) > 2  else ""
                existing_commodity = _norm_str(row[4])   if len(row) > 4  else ""
                existing_wagons    = str(row[5]).strip() if len(row) > 5  else ""
                existing_time      = str(row[10]).strip() if len(row) > 10 else ""
                existing_date      = str(row[11]).strip() if len(row) > 11 else ""
                existing_from      = _norm_str(row[20])  if len(row) > 20 else ""
                existing_party     = _norm_str(row[22])  if len(row) > 22 else ""

                if (existing_to        == to_stn and
                    existing_date      == pdate_str_check and
                    existing_time      == ptime_str_check and
                    existing_wagons    == wagons_str_check and
                    existing_from      == from_stn and
                    existing_commodity == commodity and
                    existing_line      == line and
                    existing_party     == party):
                    is_duplicate = True
                    break

            if is_duplicate:
                print(f"⏭️ Duplicate (line {line})")
                continue

            if wtype in CONTAINER_WAGON_CODES or "CONTAINER" in wtype:
                commodity = "CONTAINER"
            elif "CONTAINER" in commodity or "CONT" in commodity:
                commodity = "CONTAINER"
                if not wtype:
                    wtype = "CONTAINER"

            try:
                wagons_num = int(float(wagons)) if wagons else 42
            except Exception:
                wagons_num = 42

            if "NAPHTHA" in commodity or "NAPTHA" in commodity:
                ftime = "8 HRS"
                if not wtype: wtype = "BTPN"
            elif "CONTAINER" in commodity:
                if not ftime: ftime = "3 HRS"
                if not wtype: wtype = "CONTAINER"
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

            arrival_time_str = ""
            arrival_date_str = pdate.strftime("%d-%m-%Y")
            ptime_str        = ptime.strftime("%H:%M") if ptime else ""
            pdate_str        = pdate.strftime("%d-%m-%Y")

            if ptime:
                delta = random.choice([25, 30, 35, 40])
                placement_dt = datetime.combine(pdate, ptime)
                arrival_dt = placement_dt - timedelta(minutes=delta)
                arrival_time_str = arrival_dt.strftime("%H:%M")
                arrival_date_str = arrival_dt.strftime("%d-%m-%Y")

            def q(col, val):
                if val is not None and str(val).strip() != "":
                    updates.append({"range": rowcol_to_a1(current_row, col), "values": [[val]]})

            q(2, to_stn); q(3, line); q(4, wtype); q(5, commodity)
            q(6, wagons); q(8, wagons)
            q(9, arrival_time_str); q(10, arrival_date_str)
            q(11, ptime_str); q(12, pdate_str)
            q(18, ftime); q(21, from_stn); q(23, party)

            print(f"✅ IWOW row {current_row}: {from_stn}→{to_stn} | wagons={wagons} | line={line} | {commodity}")
            current_row += 1

        if updates:
            try:
                ws.batch_update(updates)
                print(f"✅ IWOW batch update successful ({len(updates)} cells)")
            except Exception as e:
                print(f"❌ IWOW batch update failed: {e}")
                return False

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

                    if data.get("goods"):
                        update_iwow_sheet(data["goods"])
    except Exception as e:
        print(f"❌ Webhook Error: {e}")

    return jsonify({"status": "ok"}), 200

# ==============================================
# STARTUP
# ==============================================
def startup_check():
    print("========== STARTUP CHECK ==========")
    print(f"SHEET_NAME      : {SHEET_NAME}")
    print(f"GEMINI_API_KEY  : {bool(GEMINI_API_KEY)}")
    print(f"CREDENTIALS     : {bool(GOOGLE_CREDENTIALS_STR or GOOGLE_CREDENTIALS_B64)}")
    print(f"IWOW_GRACE_HOUR : {IWOW_GRACE_HOUR}:00 IST")
    print(f"IST_NOW         : {ist_now().strftime('%Y-%m-%d %H:%M:%S')}")
    get_sheet()
    print("===================================")

startup_check()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
