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
# STATION ALIASES  (OFFICIAL LIST — code + full name + common variants)
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

# Official CODE - Full Name list (prompt me bhi use hota hai)
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
# GEMINI
# ==============================================
def call_gemini(msg):
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY missing!")
        return None

    station_legend = "\n".join(f'{c} = {STATION_OFFICIAL[c]}' for c in ALL_STATIONS)

    prompt = f"""You are an expert Indian Railway PRS & UTS data extraction engine, working like a human accountant who has read thousands of railway earning reports.
Samajhne ka tareeka bilkul natural hai — jaise ek insaan padhta hai. Terha-merha text, broken lines, mixed English/Hindi, WhatsApp forward — sab samajh aa jata hai.
Extract numbers into STRICT JSON only. No explanation, no markdown.

=== OFFICIAL STATIONS (CODE = Full Name) ===
{station_legend}

STATION RULES:
1. Message me FULL NAME ho ya CODE — dono same station hain. Hamesha CODE se key banao.
   "Borhat" → "BFD" | "New Tinsukia" → "NTSK" | "Amguri Jn" → "AGI" | "Sibsagar Town" → "SRTN"
2. ROING aur TEZU sirf PRS stations hain — inke UTS data ko ignore karo.

=== GARBLED / SQUISHED TEXT (WhatsApp paste) ===
- "MR=14AMOUNT=40620" → MR=14 AND MR AMT=40620 (do NOT merge into 1440620)
- "P/TKT =319AOUNT =3190" → PF=319 (baad wala amount ignore)
- "T/jenny=992" / "J/TKT" = journey tickets — agar total "T/TKT" alag diya hai to total hi use karo
- "Pass:-7" me ":-7" ka matlab hai value 7 (dash sirf separator hai). "Cash:-385" = 385.

=== SHORT / TERSE MESSAGES (VERY IMPORTANT) ===
Kabhi-kabhi message bahut chhota hota hai, sirf kuch lines:
  "Borhat uts
  Pass:-7
  Tkt:-5
  Cash:-385
  Ecash:-190"
Iska matlab samjho:
- "UTS" likha hai aur PRS nahi → YE SARA DATA UTS KA HAI
- Tkt / T/TKT → "TKT"
- Pass → "PASS"
- Cash (ya Netcash) → "NET"  (UTS ka net cash)
- Ecash / E-CASH / E/CASH / UPI / QR → "UPI"  (digital collection)
- PRS me "Cash" aaye to wo NET hi hai; digi cash alag se likha ho to wo UPI.

=== STRICT PRS MAPPING ===
- "NET" = SIRF Netcash value. Digi Cash / QR / UPI kabhi NET me add MAT karo.
- Digital cash (Digi Cash, QR, UPI, PhonePe, GPay, Card) → "UPI". Sirf POS → "POS".
- "REF" = SUM of ALL refunds (RFD + Cash Refund + Digi Refund + UPI Refund + POS Refund). Ek number.
  Example: RFD 10175 + Digi RFD 23426 → "REF": 33601
- T/TKT → TKT ; T/Pass → PASS ; C/TKT → C/TKT ; C/Pass → C/PASS ; Vch → VCH
- J/AMOUNT (journey total) → IGNORE, kisi column me nahi jata

=== STRICT UTS MAPPING ===
- "NET" = SIRF Netcash. UPI/digital cash NET me add MAT karo.
  EXAMPLE: "NETCASH 22290" + "UPI CASH 4360" → NET=22290, UPI=4360. NET=26650 KABHI MAT DO.
- Ecash / E/CASH / ECASH / UPI CASH / QR → "UPI"
- REF = sum of all refunds (NIL wale skip)
- T/TKT = total tickets ; T/Pass = PASS
- PF (platform) labels: "P/TKT", "PF", "PLT", "PLATFORM", ya sirf "M"/"m" → sab "PF" count
- MR = MR count, MR AMT = MR amount. "MR=14AMOUNT=40620" → "MR": 14, "MR AMT": 40620. MISS NAHI HONA CHAHIYE.

=== MISSING NUMBERS ===
- "nil", "-", "nahi aya", "not received" → field OMIT karo. 0 mat do, guess mat karo.
- Agar section message me nahi → empty object {{}}

=== NEGATIVE NUMBERS ===
"AMOUNT :- -865" jaisa actual negative → sign preserve karo.

Required JSON format (only fields with actual numbers):
{{
  "prs": {{
    "STATION_CODE": {{"TKT":0, "PASS":0, "C/TKT":0, "C/PASS":0, "REF":0, "NET":0, "VCH":0, "POS":0, "UPI":0}}
  }},
  "uts": {{
    "STATION_CODE": {{"TKT":0, "PASS":0, "NET":0, "UPI":0, "PF":0, "MR":0, "MR AMT":0}}
  }}
}}

=== EXAMPLE 1 (terse UTS message) ===
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
  }}
}}
(NOTICE: "Borhat" → "BFD". "Cash" → NET. "Ecash" → UPI. ":-7" dash sirf separator hai, value 7.)

=== EXAMPLE 2 (refunds added, digi cash NOT in net) ===
Input:
"EARNINGS OF SPK
PRS
TKT:-8 PASS:-9 C/TKT:-1 C/PASS:-3
Ref-560
Digi RF-1055
Net cash me amount ata wo nhi aya
UPI:-11575"

Output:
{{
  "prs": {{
    "SPK": {{"TKT": 8, "PASS": 9, "C/TKT": 1, "C/PASS": 3, "REF": 1615, "UPI": 11575}}
  }},
  "uts": {{}}
}}

=== EXAMPLE 3 (full name + UPI cash separate) ===
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
  }}
}}

=== EXAMPLE 4 (squished garbled UTS) ===
Input:
"Earnings Of NTSK
PRS/NTSK
T/TKT =116 T/Pass =170 C/TKT =11 C/Pass =19
RFD =10175 Netcash =24330 Digi CASH =90325 Digi RFD =23426 Vch=8390
UTS/NTSK
T/jenny=992 T/TKT =1340 T/Pass =1554
P/TKT =319AOUNT =3190
MR=14AMOUNT=40620
E/CASH =70232
J/AMOUNT =354500"

Output:
{{
  "prs": {{
    "NTSK": {{"TKT": 116, "PASS": 170, "C/TKT": 11, "C/PASS": 19, "REF": 33601, "NET": 24330, "UPI": 90325, "VCH": 8390}}
  }},
  "uts": {{
    "NTSK": {{"TKT": 1340, "PASS": 1554, "PF": 319, "MR": 14, "MR AMT": 40620, "UPI": 70232}}
  }}
}}
(NOTICE: "MR=14AMOUNT=40620" → MR=14 AUR MR AMT=40620 dono. "RFD 10175 + Digi RFD 23426" → REF=33601.
"P/TKT =319AOUNT =3190" → PF=319. "T/jenny" ignore. "J/AMOUNT" ignore. "E/CASH" → UPI.)

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

    # 🔧 Agar message UTS ka hai par Gemini data ko PRS me daal diya → move karo
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
# REGEX FALLBACK  (Gemini miss kare to bot khud fix kare)
# ==============================================
def _to_float(s):
    try:
        return float(str(s).replace(",", "").strip())
    except:
        return None

def _find_stations_in_text(msg):
    """Message me kaunse station codes/names hain — set return karta hai."""
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

    # ---------- TERSE UTS: Gemini ne UTS me kuch nahi diya ----------
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
            m = re.search(r'(?<![A-Z])CASH\s*[:=\-]*\s*([\d,]+)', up)   # ECASH ko exclude
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

    # ---------- MR + MR AMT (squished) ----------
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
                    print(f"🔧 Fallback: {st} MR AMT = {v} (regex recover)")
        if not vals.get("PF"):
            m = re.search(r'\b(?:P\s?/\s?TKT|PF|PLT|PLATFORM)\s*[=:]?\s*([\d,]+)', up)
            if m:
                v = _to_float(m.group(1))
                if v is not None:
                    vals["PF"] = v
                    print(f"🔧 Fallback: {st} PF = {v} (regex recover)")
        if not vals.get("PF"):
            m = re.search(r'(?:^|\n)\s*M\s*[=:]\s*([\d,]+)', msg.upper())
            if m:
                v = _to_float(m.group(1))
                if v is not None:
                    vals["PF"] = v
                    print(f"🔧 Fallback: {st} PF = {v} ('M' label recover)")
        uts[st] = vals

    # ---------- PRS: REF total ----------
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
                    data = apply_fallback_fixes(data, text)   # 🔧 regex safety net
                    print("✅ Final Data:", json.dumps(data))
                    update_google_sheet(data)
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
