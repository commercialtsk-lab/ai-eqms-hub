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
# STATION ALIASES  (OFFICIAL LIST)
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
# DATE PARSER (koi bhi format)
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

    prompt = f"""You are an expert Indian Railway PRS & UTS & OSOP data extraction engine, working like a human accountant who has read thousands of railway reports.
Samajhne ka tareeka bilkul natural hai — jaise ek insaan padhta hai. Terha-merha text, broken lines, mixed English/Hindi, WhatsApp forward — sab samajh aa jata hai.
Extract numbers into STRICT JSON only. No explanation, no markdown.

=== OFFICIAL STATIONS (CODE = Full Name) ===
{station_legend}

STATION RULES:
1. Message me FULL NAME ho ya CODE — dono same station hain. Hamesha CODE se key banao.
   "Borhat" → "BFD" | "New Tinsukia" → "NTSK" | "Amguri Jn" → "AGI" | "Sibsagar Town" → "SRTN"
2. ROING aur TEZU sirf PRS stations hain — inke UTS data ko ignore karo.

=== OSOP SECTION (VERY IMPORTANT — NEW) ===
Agar message me "OSOP" likha hai, to OSOP entries nikal kar "osop" ARRAY me do.
Har entry 4 cheezon ka hota hai:
- "station": OFFICIAL CODE (full name aaye to code banao)
- "date": EXACTLY waise likho jaisa message me likha hai — CONVERT MAT KARO.
  "01/11/2026", "1-11-26", "1 Nov 26", "01.11.2026" — jo bhi ho, same string rakho. Date match karne ka kaam baad me hota hai.
- "unit": unit number (agar message me diya ho). Agar unit NAHI diya → "unit" key OMIT karo.
- "amount": amount number (zaroori hai)

OSOP RULES:
1. Ek message me MULTIPLE entries ho sakti hain — ARRAY me MESSAGE KE ORDER me rakho. Order kabhi mat badlo.
2. Ek station (jaise DBRG) ek message me DO BAR aa sakta hai (do units) — dono entries alag-alag array items banao, order preserve karo.
3. Entry kisi bhi style me ho — "OSOP DBRG, date 01/11/2026, unit 4, Amount 450" ya "DBRG osop 1/11/26 amt 450 unit 4" ya "OSOP - New Tinsukia - 01.11.2026 - 300 (unit 2)" — sab samajh aa jata hai.
4. Amount me "Rs", "/-", "," hata do, sirf number rakho.
5. Agar message me OSOP nahi hai → "osop": [] (empty array) do.

=== GARBLED / SQUISHED TEXT (WhatsApp paste) ===
- "MR=14AMOUNT=40620" → MR=14 AND MR AMT=40620 (do NOT merge into 1440620)
- "P/TKT =319AOUNT =3190" → PF=319 (baad wala amount ignore)
- "T/jenny=992" / "J/TKT" = journey tickets — agar total "T/TKT" alag diya hai to total hi use karo
- "Pass:-7" me ":-7" ka matlab hai value 7 (dash sirf separator hai)

=== SHORT / TERSE MESSAGES ===
  "Borhat uts
  Pass:-7
  Tkt:-5
  Cash:-385
  Ecash:-190"
- "UTS" likha hai aur PRS nahi → YE SARA DATA UTS KA HAI
- Tkt → "TKT" ; Pass → "PASS" ; Cash/Netcash → "NET" ; Ecash/E-CASH/UPI/QR → "UPI"

=== STRICT PRS MAPPING ===
- "NET" = SIRF Netcash value. Digi Cash / QR / UPI kabhi NET me add MAT karo.
- Digital cash (Digi Cash, QR, UPI, PhonePe, GPay, Card) → "UPI". Sirf POS → "POS".
- "REF" = SUM of ALL refunds (RFD + Cash Refund + Digi Refund + UPI Refund + POS Refund). Ek number.
  Example: RFD 10175 + Digi RFD 23426 → "REF": 33601
- T/TKT → TKT ; T/Pass → PASS ; C/TKT → C/TKT ; C/Pass → C/PASS ; Vch → VCH
- J/AMOUNT (journey total) → IGNORE

=== STRICT UTS MAPPING ===
- "NET" = SIRF Netcash. UPI/digital cash NET me add MAT karo.
  EXAMPLE: "NETCASH 22290" + "UPI CASH 4360" → NET=22290, UPI=4360. NET=26650 KABHI MAT DO.
- Ecash / E/CASH / ECASH / UPI CASH / QR → "UPI"
- REF = sum of all refunds (NIL wale skip)
- T/TKT = total tickets ; T/Pass = PASS
- PF labels: "P/TKT", "PF", "PLT", "PLATFORM", ya sirf "M"/"m" → sab "PF" count
- MR = MR count, MR AMT = MR amount. "MR=14AMOUNT=40620" → "MR": 14, "MR AMT": 40620. MISS NAHI HONA CHAHIYE.

=== MISSING NUMBERS ===
- "nil", "-", "nahi aya", "not received" → field OMIT karo. 0 mat do, guess mat karo.

=== NEGATIVE NUMBERS ===
"AMOUNT :- -865" jaisa actual negative → sign preserve karo.

Required JSON format:
{{
  "prs": {{
    "STATION_CODE": {{"TKT":0, "PASS":0, "C/TKT":0, "C/PASS":0, "REF":0, "NET":0, "VCH":0, "POS":0, "UPI":0}}
  }},
  "uts": {{
    "STATION_CODE": {{"TKT":0, "PASS":0, "NET":0, "UPI":0, "PF":0, "MR":0, "MR AMT":0}}
  }},
  "osop": [
    {{"station": "CODE", "date": "as-written", "unit": 0, "amount": 0}}
  ]
}}

=== EXAMPLE A (OSOP — multiple entries, order preserved) ===
Input:
"OSOP DBRG, date 01/11/2026, unit 4, Amount 450
OSOP DBRG date 01/11/2026 amount 620
OSOP New Tinsukia 01/11/26 unit 2 amount 300
OSOP Sibsagar Town, dt 1-11-2026, Rs 520/-"

Output:
{{
  "prs": {{}},
  "uts": {{}},
  "osop": [
    {{"station": "DBRG", "date": "01/11/2026", "unit": 4, "amount": 450}},
    {{"station": "DBRG", "date": "01/11/2026", "amount": 620}},
    {{"station": "NTSK", "date": "01/11/26", "unit": 2, "amount": 300}},
    {{"station": "SRTN", "date": "1-11-2026", "amount": 520}}
  ]
}}
(NOTICE: DBRG ki pehli entry unit 4 ke sath, dusri bina unit — ARRAY ORDER = message order. Date string bilkul waisi jaise likhi thi.)

=== EXAMPLE B (terse UTS) ===
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

=== EXAMPLE C (PRS+UTS normal) ===
Input:
"AMGURI JN PRS EARNINGS
TKT-----16 PASS-----21 NETCASH---RS 4000/-
REFUND----RS 560/- DIGI CASH-----RS 36390/- DIGI REFUND---RS 1055/-
POS----NIL VOUCHER------NIL C/TKT-----03 C/PASS----------03
AMGURI JN UTS EARNINGS
TKT--281 PASS----458 NETCASH---RS 22290/- UPI CASH-----RS 4360/- REFUND ---RS NIL/-"

Output:
{{
  "prs": {{
    "AGI": {{"TKT": 16, "PASS": 21, "NET": 4000, "REF": 1615, "UPI": 36390, "C/TKT": 3, "C/PASS": 3}}
  }},
  "uts": {{
    "AGI": {{"TKT": 281, "PASS": 458, "NET": 22290, "UPI": 4360}}
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
                print(f"⚠️ Duplicate PRS station '{code}' in same message → keeping first")
        else:
            print(f"❌ Station skipped (not resolved): {st}")
    data["prs"] = new_prs

    new_uts = {}
    for st, vals in data.get("uts", {}).items():
        code = resolve_station(st)
        if code:
            if code not in new_uts:
                new_uts[code] = vals
            else:
                print(f"⚠️ Duplicate UTS station '{code}' in same message → keeping first")
        else:
            print(f"❌ UTS Station skipped: {st}")
    data["uts"] = new_uts

    # OSOP stations bhi resolve karo (ORDER preserve — yahi duplicate-row allocation ka basis hai)
    new_osop = []
    for e in data.get("osop", []):
        if not isinstance(e, dict):
            continue
        code = resolve_station(e.get("station"))
        if code:
            e["station"] = code
            new_osop.append(e)
        else:
            print(f"❌ OSOP entry skipped (station not resolved): {e}")
    data["osop"] = new_osop

    # Agar message UTS ka hai par Gemini data PRS me daal de → move karo
    up = msg.upper()
    if "UTS" in up and "PRS" not in up.replace("UTS", ""):
        if not data["uts"] and len(data["prs"]) == 1:
            st, vals = next(iter(data["prs"].items()))
            if isinstance(vals, dict) and not any(k in vals for k in ("C/TKT", "C/PASS", "VCH", "POS", "REF")):
                data["uts"] = {st: vals}
                data["prs"] = {}
                print(f"🔧 Moved PRS→UTS for {st} (message was UTS-only)")

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

def apply_fallback_fixes(data, msg):
    if not data:
        return data

    up = msg.upper()
    uts = data.get("uts") or {}
    prs = data.get("prs") or {}

    # OSOP fallback: "OSOP DBRG date 01/11/2026 unit 4 amount 450" pattern
    osop = data.get("osop") or []
    if "OSOP" in up and not osop:
        pat = re.compile(
            r'OSOP\s+([A-Za-z][A-Za-z .]+?)[,;\s]+(?:date|dt|d)?\s*[:=\-]?\s*'
            r'(\d{1,4}[-/\.]\d{1,2}[-/\.]\d{1,4})[,;\s]+(?:unit|u)?\s*[:=\-]?\s*(\d+)?[,;\s]*'
            r'(?:amount|amt)?\s*[:=\-]?\s*Rs?\s*\.?\s*([\d,]+)',
            re.IGNORECASE
        )
        for m in pat.finditer(msg):
            code = resolve_station(m.group(1))
            if code:
                entry = {"station": code, "date": m.group(2), "amount": _to_float(m.group(4))}
                if m.group(3):
                    entry["unit"] = int(m.group(3))
                osop.append(entry)
                print(f"🔧 OSOP regex fallback: {entry}")
        data["osop"] = osop

    # Terse UTS fallback
    if not uts and "UTS" in up and "NETCASH" not in up.replace(" ", "") and "DIGI" not in up:
        found = _find_stations_in_text(msg)
        if len(found) == 1:
            st = next(iter(found))
            vals = {}
            m = re.search(r'(?:T\s?/\s?TKT|TKT|TICKETS?)\s*[:=\-]*\s*([\d,]+)', up)
            if m:
                vals["TKT"] = _to_float(m.group(1))
            m = re.search(r'(?:T\s?/\s?PASS|PASS|PAX)\s*[:=\-]*\s*([\d,]+)', up)
            if m:
                vals["PASS"] = _to_float(m.group(1))
            m = re.search(r'(?<![A-Z])CASH\s*[:=\-]*\s*([\d,]+)', up)
            if m:
                vals["NET"] = _to_float(m.group(1))
            m = re.search(r'E\s?[-/]?\s?CASH\s*[:=\-]*\s*([\d,]+)', up)
            if m:
                vals["UPI"] = _to_float(m.group(1))
            vals = {k: v for k, v in vals.items() if v is not None}
            if vals:
                uts[st] = vals
                data["uts"] = uts
                print(f"🔧 Terse UTS fallback: {st} → {vals}")

    # MR + MR AMT squished
    if len(uts) == 1:
        st, vals = next(iter(uts.items()))
        vals = vals if isinstance(vals, dict) else {}
        if not vals.get("MR AMT"):
            m = re.search(r'\bMR\s*[=:]?\s*([\d,]+)\s*(?:A\s?M?O?U?N?T|AMT|AOUNT|AMNT)\s*[=:]?\s*([\d,]+)', up)
            if m:
                if not vals.get("MR"):
                    v = _to_float(m.group(1))
                    if v is not None:
                        vals["MR"] = v
                v = _to_float(m.group(2))
                if v is not None:
                    vals["MR AMT"] = v
                    print(f"🔧 Fallback: {st} MR AMT = {v}")
        if not vals.get("PF"):
            m = re.search(r'\b(?:P\s?/\s?TKT|PF|PLT|PLATFORM)\s*[=:]?\s*([\d,]+)', up)
            if m:
                v = _to_float(m.group(1))
                if v is not None:
                    vals["PF"] = v
                    print(f"🔧 Fallback: {st} PF = {v}")
        if not vals.get("PF"):
            m = re.search(r'(?:^|\n)\s*M\s*[=:]\s*([\d,]+)', msg.upper())
            if m:
                v = _to_float(m.group(1))
                if v is not None:
                    vals["PF"] = v
                    print(f"🔧 Fallback: {st} PF = {v} ('M' label)")
        uts[st] = vals

    # PRS: REF total
    if len(prs) == 1:
        st, vals = next(iter(prs.items()))
        vals = vals if isinstance(vals, dict) else {}
        if not vals.get("REF"):
            amounts = re.findall(r'\b(?:RFD|REFUND|REF)\s*[=:]?\s*([\d,]+)', up)
            nums = [n for n in (_to_float(a) for a in amounts) if n is not None]
            if nums:
                vals["REF"] = sum(nums)
                print(f"🔧 Fallback: PRS {st} REF = {vals['REF']} ({len(nums)} refunds)")
        prs[st] = vals

    return data

# ==============================================
# UPDATE SHEET  (STRICT — NO OVERWRITE, NO ADD, NO ZERO)
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
            print(f"⏭️ Cell {rowcol_to_a1(r,c)} already queued, skipping duplicate")
            return
        queued.add(key)
        updates.append({"range": rowcol_to_a1(r, c), "values": [[val]]})

    # -------- PRS --------
    for st, vals in data.get("prs", {}).items():
        info = smap.get(st)
        if not info:
            print(f"⚠️ Station {st} not found in sheet map")
            continue

        if not _has_any_nonzero(vals):
            print(f"⏭️ PRS {st}: all values are 0/missing → SKIPPED (nothing to write)")
            continue

        row = info["row"]
        for fld, val in (vals or {}).items():
            try:
                v = float(val)
            except:
                continue

            if fld not in PRS_COLS:
                continue

            if not _is_field_allowed(v, fld):
                print(f"⏭️ PRS {st} {fld}: value {v} not allowed (0 or wrong sign) → SKIPPED")
                continue

            col = PRS_COLS[fld]
            existing_raw = get_current(row, col)

            if is_cell_empty(existing_raw):
                queue(row, col, v)
                print(f"✅ PRS {st} {fld}: wrote {v} (was empty)")
            else:
                print(f"⏭️ PRS {st} {fld}: SKIPPED (already has → '{existing_raw}')")

    # -------- UTS --------
    for st, vals in data.get("uts", {}).items():
        info = smap.get(st)
        if not info:
            continue

        if not _has_any_nonzero(vals):
            print(f"⏭️ UTS {st}: all values are 0/missing → SKIPPED (nothing to write)")
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
                print(f"⏭️ UTS {st} {fld}: value {v} not allowed (0 or wrong sign) → SKIPPED")
                continue

            if info["nameCol"] == "C":
                col = {"TKT": 4, "PASS": 5, "NET": 9, "UPI": 12, "PF": 8, "MR": 19, "MR AMT": 20}.get(fld)
            else:
                col = UTS_COLS_NU.get(fld)

            if not col:
                continue

            existing_raw = get_current(row, col)
            if is_cell_empty(existing_raw):
                queue(row, col, v)
                print(f"✅ UTS {st} {fld}: wrote {v} (was empty)")
            else:
                print(f"⏭️ UTS {st} {fld}: SKIPPED (already has → '{existing_raw}')")

    if not updates:
        print("⚠️ No cells updated (all already filled or values were 0)")
        return True

    try:
        sheet.batch_update(updates)
        print(f"✅ Batch update successful ({len(updates)} cells)")
        return True
    except Exception as e:
        print(f"❌ Batch update failed: {e}")
        return False

# ==============================================
# OSOP SHEET UPDATE  (NEW)
# ==============================================
# Layout:
#   Row 5    : dates — C5:D5 merged, E5:F5 merged, ... (har date = 2 columns)
#   B6:B20   : stations (full name / code / dono — duplicates allowed, jaise DBRG 2 bar)
#   Data     : amount = date-pair ka LEFT column, unit = RIGHT column
def update_osop_sheet(entries):
    if not entries:
        return True

    sh = get_spreadsheet()
    if not sh:
        return False

    try:
        ws = sh.worksheet("OSOP")
    except gspread.WorksheetNotFound:
        print("❌ 'OSOP' worksheet nahi mili workbook me")
        return False

    try:
        matrix = ws.get_all_values()
    except Exception as e:
        print(f"❌ OSOP read error: {e}")
        return False

    if len(matrix) < 6:
        print("❌ OSOP sheet me data nahi hai (kam se kam 6 rows chahiye)")
        return False

    def get_current(r, c):
        try:
            return matrix[r-1][c-1]
        except:
            return ""

    # ---- Row 5: dates, har 2 column ka pair (left merged cell) ----
    row5 = matrix[4] if len(matrix) > 4 else []
    date_cols = {}   # date_obj -> (amount_col, unit_col)
    c = 3            # C column se start
    max_cols = max(len(row5), 40)
    while c <= max_cols:
        raw = row5[c-1] if c-1 < len(row5) else ""
        if not str(raw).strip() and c < len(row5):
            raw = row5[c]  # merged ho to right cell check
        d = parse_date_flexible(raw)
        if d:
            date_cols[d] = (c, c + 1)
            print(f"📅 OSOP date '{raw.strip()}' → cols {rowcol_to_a1(5, c)}:{rowcol_to_a1(5, c+1)}")
        c += 2

    if not date_cols:
        print("❌ OSOP row 5 me koi date nahi mili")
        return False

    # ---- B6:B20: station rows (code -> rows list, order preserved) ----
    station_rows = {}
    for r in range(6, 21):
        if r-1 >= len(matrix):
            break
        cell = matrix[r-1][1] if len(matrix[r-1]) > 1 else ""
        if not str(cell).strip():
            continue
        code = resolve_station(cell)
        if code:
            station_rows.setdefault(code, []).append(r)
            print(f"📍 OSOP row {r}: '{str(cell).strip()}' → {code}")
        else:
            print(f"⚠️ OSOP row {r}: '{cell}' resolve nahi hua")

    if not station_rows:
        print("❌ OSOP B6:B20 me koi station nahi mila")
        return False

    updates = []
    queued = set()

    def queue(r, c, val):
        key = (r, c)
        if key in queued:
            print(f"⏭️ Cell {rowcol_to_a1(r,c)} already queued")
            return
        queued.add(key)
        updates.append({"range": rowcol_to_a1(r, c), "values": [[val]]})

    # ---- Entries ko rows me baanto (duplicate station: nth entry → nth row) ----
    usage = {code: 0 for code in station_rows}

    for e in entries:
        if not isinstance(e, dict):
            continue
        code = e.get("station")
        if code not in station_rows:
            print(f"⚠️ OSOP: '{e.get('station')}' sheet ke B6:B20 me nahi mila → entry skip")
            continue

        idx = usage.get(code, 0)
        rows = station_rows[code]
        if idx >= len(rows):
            print(f"⚠️ OSOP {code}: sheet me sirf {len(rows)} row(s) — extra entry skip: {e}")
            continue
        row = rows[idx]
        usage[code] = idx + 1

        d = parse_date_flexible(e.get("date"))
        if not d:
            print(f"⚠️ OSOP {code}: date '{e.get('date')}' samajh nahi aayi → entry skip: {e}")
            continue
        if d not in date_cols:
            print(f"⚠️ OSOP {code}: date '{e.get('date')}' ({d}) row 5 me nahi mili → entry skip")
            continue

        camt, cunit = date_cols[d]

        # ---- AMOUNT (left column) ----
        amt = _to_float(e.get("amount")) if e.get("amount") is not None else None
        if amt is not None and amt != 0:
            ex = get_current(row, camt)
            ex_f = _to_float(ex)
            if is_cell_empty(ex):
                queue(row, camt, amt)
                print(f"✅ OSOP {code} {d}: amount {amt} → {rowcol_to_a1(row, camt)}")
            elif ex_f is not None and ex_f == amt:
                print(f"⏭️ OSOP {code} {d}: amount {amt} already present → skip (duplicate)")
            else:
                print(f"⏭️ OSOP {code} {d}: amount cell me already '{ex}' hai → NO OVERWRITE")

        # ---- UNIT (right column) ----
        unit = e.get("unit")
        if unit is None or str(unit).strip() == "":
            # Unit missing → same station ki baki duplicate rows ke units se compare karke infer
            used_units = set()
            for rr in rows:
                if rr == row:
                    continue
                uv = _to_float(get_current(rr, cunit))
                if uv is not None:
                    used_units.add(int(uv))
            if len(used_units) == 1:
                unit = used_units.pop() + 1
                print(f"🔧 OSOP {code} {d}: unit missing → existing units compare karke '{unit}' infer kiya")
            else:
                print(f"⚠️ OSOP {code} {d}: unit missing, sheet me compare ke liye kuch nahi → unit cell blank rahega")

        if unit is not None and str(unit).strip() != "":
            ex = get_current(row, cunit)
            if is_cell_empty(ex):
                queue(row, cunit, unit)
                print(f"✅ OSOP {code} {d}: unit {unit} → {rowcol_to_a1(row, cunit)}")
            else:
                print(f"⏭️ OSOP {code} {d}: unit cell me already '{ex}' hai → NO OVERWRITE")

    if not updates:
        print("⚠️ OSOP: kuch write nahi hua (sab filled ya invalid)")
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

                    # PRS/UTS update
                    update_google_sheet(data)

                    # OSOP update (agar entries hain)
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
