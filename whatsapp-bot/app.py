import os
import re
import json
import time
import base64
import threading
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
GEMINI_VERIFY = os.environ.get("GEMINI_VERIFY", "1") == "1"   # 2nd pass: Gemini apna hi extract check kare

OSOP_LOCK_FILE = "/tmp/osop_update.lock"
IWOW_LOCK_FILE = "/tmp/iwow_update.lock"
IWOW_GRACE_HOUR = int(os.environ.get("IWOW_GRACE_HOUR", "6"))

# Optional IWOW extra columns (0 = disabled). Column number daalo (A=1, B=2 ...)
IWOW_WEIGHT_COL = int(os.environ.get("IWOW_WEIGHT_COL", "0"))
IWOW_FREIGHT_COL = int(os.environ.get("IWOW_FREIGHT_COL", "0"))
IWOW_REMARK_COL = int(os.environ.get("IWOW_REMARK_COL", "0"))

PROCESS_LOCK = threading.Lock()   # ek time pe ek hi message sheet update kare

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
    "BGND": ["BGND", "BAGINADI", "BOGINADI"],
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
    "LXA": ["LXA", "LAKSWA", "LAKUA"],
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
    "FCGC": ["FCGC", "FCI SIDING"],
    "KNNN": ["KNNN", "KANNN", "KANUN"]
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
    "PNT": "Panitola", "TII": "Tingrai", "LXA": "Lakua",
    "SFR": "Safrai", "SLX": "Seleng Hat", "NMT": "Namtiali",
    "ROING": "Roing", "TEZU": "Tezu", "CGF": "Chariali",
    "DMGN": "Dhamalgaon Jn", "TNGN": "Tangani", "NSBG": "New Sisiborgaon",
    "KOWN": "Khowang", "NCH": "Nakachari", "CMA": "Cinnamara",
    "KXL": "Kamarbandha Ali", "BBGN": "Barua Bamungaon", "BLMR": "Bhalukmara",
    "NMGY": "Numaligarh", "KRHT": "Kharahat", "CCIB": "CCIB",
    "MRLB": "Mal Bazar", "BLZ": "Badarpur Jn", "FCGC": "FCI Siding",
    "KNNN": "Kanun"
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

PRS_ONLY_FIELDS = {"C/TKT", "C/PASS", "VCH", "POS", "REF"}

CONTAINER_WAGON_CODES = {"BLC", "BFKN", "BLL", "BLH", "BLCN", "BLCA", "BLLA", "CFN", "CONTR", "CONT"}

# ==============================================
# COMMODITY ABBREVIATION
# ==============================================
def abbreviate_commodity(comm):
    """RICE(FCI)→FCI/R, WHEAT(FCI)→FCI/W, RICE(PUB)→PUB/R, WHEAT(PUB)→PUB/W."""
    if not comm:
        return ""
    c = str(comm).upper().strip()
    c = re.sub(r'\s+', ' ', c)

    if "CONTAINER" in c or c in ("CONT", "CNTR"):
        return "CONTAINER"

    has_fci = "FCI" in c or "FOOD CORPORATION" in c
    has_pub = "PUB" in c or "PUBLIC" in c
    has_rice = "RICE" in c
    has_wheat = "WHEAT" in c

    if has_rice and has_fci:
        return "FCI/R"
    if has_wheat and has_fci:
        return "FCI/W"
    if has_rice and has_pub:
        return "PUB/R"
    if has_wheat and has_pub:
        return "PUB/W"
    if has_rice:
        return "RICE"
    if has_wheat:
        return "WHEAT"
    if has_fci:
        return "FCI"
    if has_pub:
        return "PUB"
    return c

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

def resolve_station(name, quiet=False):
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

    if not quiet:
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
    """
    Stations B7:B36 me expected hain. Sheet me code ho ya poora naam,
    dono se station code (jaise BFD) pe map ho jata hai.
    """
    m = {}
    try:
        all_values = sheet.get_all_values()
    except Exception as e:
        print(f"❌ Error reading sheet: {e}")
        return m

    def add(raw, row, name_col):
        key = str(raw).upper().strip()
        if not key:
            return
        info = {"row": row, "nameCol": name_col}
        m.setdefault(key, info)
        code = resolve_station(key, quiet=True)
        if code:
            m.setdefault(code, info)

    # PRIMARY: B7:B36
    for i in range(6, min(36, len(all_values))):
        val = all_values[i][1] if len(all_values[i]) > 1 else ""
        if val:
            add(val, i + 1, "B")

    for i in range(30, min(47, len(all_values))):
        val = all_values[i][12] if len(all_values[i]) > 12 else ""
        if val:
            add(val, i + 1, "M")

    for i in range(31, min(48, len(all_values))):
        val = all_values[i][2] if len(all_values[i]) > 2 else ""
        if val:
            add(val, i + 1, "C")

    print(f"✅ Station map ready: {len(m)} keys (B7:B36 primary)")
    return m

# ==============================================
# DATE / TIME PARSERS
# ==============================================
_YEARLESS_FORMATS = ("%d/%m", "%d-%m", "%d.%m")

def parse_date_flexible(s):
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    s = re.sub(r'(?<=\d)(st|nd|rd|th)\b', '', s, flags=re.IGNORECASE)
    s = s.strip(" .,:;-")
    if not s:
        return None

    formats = (
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
        "%Y-%m-%d", "%Y/%m/%d",
        "%d %b %Y", "%d %B %Y", "%d %b %y", "%d %B %y",
        "%d-%b-%Y", "%d-%b-%y",
        "%d %m %Y", "%d %m %y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass

    # Bina saal wali date (4/11, 4-11, 4.11) → is saal ki
    year = ist_now().year
    for fmt in _YEARLESS_FORMATS:
        try:
            return datetime.strptime(f"{s} {year}", f"{fmt} %Y").date()
        except ValueError:
            pass
    for fmt in ("%d %b", "%d %B"):
        try:
            return datetime.strptime(f"{s} {year}", f"{fmt} %Y").date()
        except ValueError:
            pass

    try:
        from dateutil import parser as _dp
        return _dp.parse(s, dayfirst=True).date()
    except Exception:
        return None

def parse_time_flexible(s):
    """Tolerant time parser — handles 12:50, 12/50, 12.50, 1250, 12:50 HRS."""
    if s is None:
        return None
    s = str(s).strip().upper()
    if not s:
        return None
    s = re.sub(r'\b(HRS|HR|HOURS|HOUR)\b', '', s).strip()
    s = re.sub(r'[/\.\-]', ':', s).replace(' ', '')
    s = re.sub(r':+', ':', s)

    for fmt in ("%H:%M", "%H%M"):
        try:
            return datetime.strptime(s, fmt).time()
        except Exception:
            pass
    m = re.search(r'(\d{1,2}):(\d{1,2})', s)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return dt_time(hh, mm)
    return None

def ist_now():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow() + timedelta(hours=5, minutes=30)

# ==============================================
# SMALL HELPERS
# ==============================================
def _to_float(s):
    try:
        return float(str(s).replace(",", "").strip())
    except:
        return None

def _int_if_whole(v):
    f = _to_float(v)
    if f is None:
        return v
    return int(f) if f == int(f) else f

def _clean_party(p):
    p = re.sub(r'\s+', ' ', str(p or '')).strip().upper()
    p = re.sub(r'^M\s*/\s*S\.?\s*', 'M/S ', p)
    p = re.sub(r'[\s.,;:\-]+$', '', p)
    return p

def _find_stations_in_text(msg):
    up = str(msg or "").upper()
    found = set()
    for code, aliases in STATION_ALIASES.items():
        for a in aliases:
            if re.search(r'\b' + re.escape(a) + r'\b', up):
                found.add(code)
                break
    return found

# ==============================================
# WHATSAPP CHAT SPLITTER
# ==============================================
_CHAT_HEADER_RE = re.compile(
    r'^[ \t]*(?:'
    r'\[(?P<ts1>\d{1,2}[/.\-]\d{1,2}(?:[/.\-]\d{2,4})?,?\s*\d{1,2}[:.]\d{2}(?::\d{2})?\s*(?:[APap]\.?[Mm]\.?)?)\]'
    r'|(?P<ts2>\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4},?\s+\d{1,2}[:.]\d{2}(?::\d{2})?\s*(?:[APap]\.?[Mm]\.?)?)\s+-'
    r')\s*(?P<sender>[^:\n]{1,80}?):[ \t]*',
    re.MULTILINE)

def split_chat_messages(text):
    text = (text or "").replace("\u200e", "").replace("\u200f", "").replace("\u202f", " ")
    matches = list(_CHAT_HEADER_RE.finditer(text))
    if not matches:
        return [{"sender": "", "ts": "", "body": text.strip()}]

    blocks = []
    pre = text[:matches[0].start()].strip()
    if pre:
        blocks.append({"sender": "", "ts": "", "body": pre})
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end].strip()
        if body:
            blocks.append({
                "sender": m.group("sender").strip(),
                "ts": (m.group("ts1") or m.group("ts2") or "").strip(),
                "body": body,
            })
    return blocks

def guess_station_hint(body, sender=""):
    """Message me station ka naam ho to wahi, warna sender ke naam se (jaise 'SM KOWN')."""
    found = _find_stations_in_text(body)
    if len(found) == 1:
        return next(iter(found))
    if not found:
        s = _find_stations_in_text(sender)
        if len(s) == 1:
            return next(iter(s))
    return None

# ==============================================
# GEMINI — RULES (ek hi jagah, extract + verify dono use karte hain)
# ==============================================
RULES_TEXT = r"""
=== OUTPUT SCHEMA (ONE JSON object, all 4 keys always present) ===
  "prs"   : { "<STATION_CODE>": { "TKT":num, "PASS":num, "C/TKT":num, "C/PASS":num, "REF":num, "NET":num, "VCH":num, "POS":num, "UPI":num } }
  "uts"   : { "<STATION_CODE>": { "PF":num, "TKT":num, "PASS":num, "NET":num, "MR":num, "MR AMT":num, "UPI":num } }
  "osop"  : [ { "station":"CODE", "date":"as written", "amount":num, "unit":num or omit } ]
  "goods" : [ { "from_stn":"CODE", "to_stn":"CODE", "wagons":num, "placement_time":"HH:MM", "placement_date":"as written", "commodity":"ABBREVIATED UPPERCASE", "line":"number or comma list", "party":"UPPERCASE", "wagon_type":"optional", "free_time":"optional", "weight":num or omit, "freight":num or omit, "remarks":"optional short text" } ]

A single message can contain several kinds of data (e.g. PRS + UTS + goods). Extract ALL of it.

=== PRS / UTS READING GUIDE ===
- Normally ONE station's daily revenue report. Station key = CODE (from text like "REVENUE OF BFD", "Kown 4/11/26", "Krht uts of ..." or from STATION HINT). Multi-station bundles are possible -> one key per station.
- Lines under a "UTS" heading -> "uts". Lines under a "PRS" heading -> "prs". If the message has NO UTS/PRS label at all (small stations) -> treat as UTS.
- Field meanings (people write them in many ways):
    TKT   : TKT / Tkts / Tckt / Ticket / T / J/TKT
    PASS  : PASS / Psg / Psgr / Passenger / P (when it sits beside T) / J/Pass
    NET   : NET CASH / Net / Cash / Cash amount / J/Amount  - the cash collection amount (never the grand total)
    UPI   : E CASH / Ecash / E-cash / E cas / UPI / UPI QR / QR / Digital / Paytm / PhonePe
    REF   : REFUND / RFD / Digi ref / Digital refund / Digi refund / Digital RFD - SUM OF ALL refund-type AMOUNTS of that station. Example: REFUND 500 + Digi ref 200 + RFD 100 -> REF = 800. (A "ref no / reference number" is NOT an amount.)
    C/TKT, C/PASS : cancelled tickets / cancelled passengers (PRS)
    VCH, POS : voucher / POS machine figures if given (PRS)
    PF    : platform tickets (PF / P/TKT / PLT / PLATFORM / "M")
    MR / MR AMT : MR count / MR amount (both captured)
- "Ttl" / "Total" / "Grand total" lines are totals -> IGNORE (never put them in NET or anywhere).
- Nil / Nill / NIL / - / blank / "nill .." -> omit that key.
- Date lines like "DATE. 04/11/2026" -> ignore (not a field).
- Numbers must be plain numbers (remove commas, Rs, /-).
- Missing -> omit key.

PRS/UTS EXAMPLES:
Input: "REVENUE OF BFD\nDATE.     04/11/2026\nUTS\nTKT                  200\nPASS.               333\nNET CASH.    10485\nE CASH.          1230\n\nPRS\nTKT                 9\nPASS.              20\nNET CASH.    28060\nUPI QR .          10025\nREFUND.          Nill\nC/TKT.              Nill\nC/PASS.            Nill\nDigi ref:-            nill  .."
Output: {"prs":{"BFD":{"TKT":9,"PASS":20,"NET":28060,"UPI":10025}},"uts":{"BFD":{"TKT":200,"PASS":333,"NET":10485,"UPI":1230}},"osop":[],"goods":[]}

Input: "Kown 4/11/26\nPsg-9\nTckt-7\nCash-20\nEcash-400"
Output: {"prs":{},"uts":{"KOWN":{"TKT":7,"PASS":9,"NET":20,"UPI":400}},"osop":[],"goods":[]}

Input: "Krht uts of 4.11.2026\nT 36\nP 58\nCash 1390\nE cas 340\nTtl 1730 only"
Output: {"prs":{},"uts":{"KRHT":{"TKT":36,"PASS":58,"NET":1390,"UPI":340}},"osop":[],"goods":[]}

=== OSOP (One Station One Product) ===
- Message mentions OSOP / Osop / O.S.O.P / One Station One Product sale.
- Each entry: station CODE, date as written (if "today/aaj" use today's date DD/MM/YY), amount = sale amount in Rs, unit = number of units/pieces sold (omit if not given).
- Several stations in one message -> several entries. Nil/zero -> skip that station.
OSOP EXAMPLES:
Input: "OSOP BFD 04/11/26 Sale Rs 1500 units 15"
Output: {"prs":{},"uts":{},"osop":[{"station":"BFD","date":"04/11/26","amount":1500,"unit":15}],"goods":[]}
Input: "Osop 04.11.2026\nKRHT 800/8\nKOWN 300/3"
Output: {"prs":{},"uts":{},"osop":[{"station":"KRHT","date":"04.11.2026","amount":800,"unit":8},{"station":"KOWN","date":"04.11.2026","amount":300,"unit":3}],"goods":[]}

=== INWARD GOODS / IWOW ===
Understand ANY style: "<STN> GOODS POSITION", "INWARD", "IWOW", "rake placed", "wagons placed", "Ex-XXX to YYY", "from X", bullets, numbering, tables, Hinglish ("aaj", "kal", "lagaya", "placed hua"), abbreviations, typos, several rakes in one message. Extract every INWARD placement into "goods". (Outward / loading / empty-return details are NOT inward goods -> skip them.)

Fields:
- from_stn / to_stn: station CODES. Words like Ex / ex- / from / X-station = origin. to / at / placed at / for / destination = to_stn. If the heading says "<STN> GOODS POSITION" (or the message is clearly about one station) and no other destination is given, to_stn = that station.
- wagons: number of wagons ("55 BCNL wagons", "rake of 42", "42 W", "BOXN-42" -> 42).
- wagon_type: wagon code exactly as written (BCNL, BCNA, BCN, BOXN, BTPN, BRN, BLC...). Leave empty if not written. Do not guess.
- placement_time: 24-hour HH:MM (9 PM -> 21:00, 2100 hrs -> 21:00, 9.30pm -> 21:30, 12/50 -> 12:50).
- placement_date: as written. "today/aaj" -> today's date, "yesterday/kal(past)" -> yesterday (use the Now context). If no date is written, leave "".
- commodity: ABBREVIATED uppercase (rules below).
- line: line/siding number digits only (L/1, L/NO-10, line no 3, Line-4 -> 1, 10, 3, 4).
- party: the consignee / party / firm / receiver / siding owner in UPPERCASE, full name with Ltd/Pvt/Corporation etc. Look after: Party-, Party:, M/s, Consignee, Rcvr, Receiver, Firm, Indentor, Siding, "for". Never a station name or commodity. If the party is stated once for several rakes, copy it into EVERY rake entry.
- free_time: only if explicitly written (e.g. "free time 9 hrs"), else "".
- weight (tonnes) / freight (Rs): only if written.
- remarks: any other useful note in a few words (e.g. "short placed", "unloading started", "detention"), else "".

COMMODITY ABBREVIATION RULES (apply always):
- RICE (FCI) / FCI RICE / RICE FCI  -> "FCI/R"
- WHEAT (FCI) / FCI WHEAT / WHEAT FCI -> "FCI/W"
- RICE (PUB) / PUB RICE / RICE PUB -> "PUB/R"
- WHEAT (PUB) / PUB WHEAT / WHEAT PUB -> "PUB/W"
- RICE alone -> "RICE", WHEAT alone -> "WHEAT", FCI alone -> "FCI", PUB alone -> "PUB"
- CONTAINER / container wagons -> "CONTAINER"
- CEMENT -> "CEMENT", COAL -> "COAL", NAPHTHA -> "NAPHTHA", FERT / fertiliser / urea -> "FERT"
- Others -> keep as UPPERCASE

MULTI-LINE WAGONS:
If wagons are reported on multiple line numbers with DIFFERENT commodities -> one goods entry per commodity/line.
VERY IMPORTANT - SAME commodity + SAME from_stn + SAME to_stn + SAME placement time+date across several lines -> ONE entry: wagons = SUM, line = comma-joined ("10,12").

GOODS EXAMPLES:
Input: "55 BCNL RICE(FCI) WAGONS EX-KNNN TO NTSK PLACED ON L/NO-10 AND \n03 BCNL RICE(FCI) WAGONS EX-KNNN TO NTSK PLACED ON L/NO-12 \nAT 12:50 HRS ON DATE-04/11/26"
Output: {"prs":{},"uts":{},"osop":[],"goods":[{"from_stn":"KNNN","to_stn":"NTSK","wagons":58,"placement_time":"12:50","placement_date":"04/11/26","commodity":"FCI/R","line":"10,12","party":"","wagon_type":"BCNL"}]}

Input: "20 BCNL RICE(FCI) WAGONS EX-KNNN TO NTSK PLACED ON L/NO-10\n10 BCNA WHEAT(FCI) WAGONS EX-KNNN TO NTSK PLACED ON L/NO-12\nAT 12:50 HRS ON DATE-04/11/26"
Output: {"prs":{},"uts":{},"osop":[],"goods":[{"from_stn":"KNNN","to_stn":"NTSK","wagons":20,"placement_time":"12:50","placement_date":"04/11/26","commodity":"FCI/R","line":"10","party":"","wagon_type":"BCNL"},{"from_stn":"KNNN","to_stn":"NTSK","wagons":10,"placement_time":"12:50","placement_date":"04/11/26","commodity":"FCI/W","line":"12","party":"","wagon_type":"BCNA"}]}

Input: "JTTN GOODS POSITION:\n11 wagons Ex-CCIB to JTTN (Cement) placed at 21:00 hrs on 01.11.26 on L/1.\n\nParty- M/s. Cement Corporation Ltd."
Output: {"prs":{},"uts":{},"osop":[],"goods":[{"from_stn":"CCIB","to_stn":"JTTN","wagons":11,"placement_time":"21:00","placement_date":"01.11.26","commodity":"CEMENT","line":"1","party":"M/S CEMENT CORPORATION LTD","wagon_type":""}]}

Input: "Aaj NTSK me 2 rake aaya. 1) 40 BTPN naphtha ex DBRT 0600 hrs L-3  2) 21 BCNA urea ex NLP 1430 hrs L-4. Party IOCL / IFFCO resp."
Output: {"prs":{},"uts":{},"osop":[],"goods":[{"from_stn":"DBRT","to_stn":"NTSK","wagons":40,"placement_time":"06:00","placement_date":"<today DD/MM/YY>","commodity":"NAPHTHA","line":"3","party":"IOCL","wagon_type":"BTPN"},{"from_stn":"NLP","to_stn":"NTSK","wagons":21,"placement_time":"14:30","placement_date":"<today DD/MM/YY>","commodity":"FERT","line":"4","party":"IFFCO","wagon_type":"BCNA"}]}

GENERAL:
- Trust your own judgement like a seasoned railway accountant. Never invent numbers, dates, times or names that are not in the message.
- Ignore greetings, signatures, officer names/designations, chat-export headers like "[04/11, 7:03 pm] Name:".
- Return empty containers for sections that are not present.
"""

# ==============================================
# GEMINI CORE
# ==============================================
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
        }
    }
    for attempt in range(tries):
        try:
            res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=45)
            if res.status_code == 200:
                txt = res.json()['candidates'][0]['content']['parts'][0]['text']
                txt = re.sub(r'```json\n?', '', txt, flags=re.IGNORECASE)
                txt = re.sub(r'```\n?', '', txt).strip()
                match = re.search(r'\{[\s\S]*\}', txt)
                if match:
                    return json.loads(match.group(0))
                print("⚠️ Gemini returned no JSON")
            else:
                print(f"❌ Gemini HTTP {res.status_code}: {res.text[:250]}")
        except Exception as e:
            print(f"❌ Gemini Error: {e}")
        time.sleep(1.5)
    return None

def _normalize_parsed(parsed):
    if not isinstance(parsed, dict):
        return None
    for k in ("prs", "uts"):
        v = parsed.get(k)
        parsed[k] = v if isinstance(v, dict) else {}
    for k in ("osop", "goods"):
        v = parsed.get(k) or []
        if isinstance(v, dict):
            v = [v]
        parsed[k] = v if isinstance(v, list) else []
    return parsed

def _station_legend():
    return "\n".join(f'{c} = {STATION_OFFICIAL[c]}' for c in ALL_STATIONS)

def _context_block(sender, ts, hint):
    hint_line = (f"{hint} ({STATION_OFFICIAL.get(hint, '')})" if hint else "none")
    now = ist_now()
    yesterday = now - timedelta(days=1)
    return (
        "=== CONTEXT ===\n"
        f"Sender name: {sender or 'unknown'} | Message time: {ts or 'unknown'}\n"
        f"Now (IST): {now.strftime('%d/%m/%Y %H:%M')} | Today = {now.strftime('%d/%m/%y')} | Yesterday = {yesterday.strftime('%d/%m/%y')}\n"
        f"STATION HINT (use ONLY if the message text itself names no station): {hint_line}\n"
        "The message may begin with chat-export noise like \"[04/11, 7:03 pm] Name:\" - ignore it. "
        "Sender names/designations (Sr CTC, SM, SS, Pradip Mishra) are NOT data.\n"
    )

def call_gemini(msg, sender="", ts="", hint=None):
    prompt = (
        "You are an expert Indian Railway data extraction engine for the Tinsukia Division (NF Railway).\n"
        "You read WhatsApp messages like a seasoned railway accountant - messy formats, broken lines, Hinglish, typos, "
        "garbled paste, squished text, copied/forwarded chat text, several different reports in one message. "
        "You understand them naturally.\n\n"
        + _context_block(sender, ts, hint)
        + "\n=== OFFICIAL STATIONS (CODE = Full Name) ===\n" + _station_legend() + "\n"
        + RULES_TEXT
        + "\nMESSAGE:\n\"\"\"" + msg + "\"\"\"\n\nJSON only, no markdown:"
    )
    return _normalize_parsed(gemini_json(prompt))

def gemini_verify(msg, data, sender="", ts="", hint=None):
    """Gemini apna extract original message se dobara check kare. Fail ho to original data hi chalega."""
    if not GEMINI_VERIFY or not data:
        return data
    try:
        prompt = (
            "You are a meticulous auditor for Indian Railway WhatsApp data extraction.\n"
            "Below are the ORIGINAL MESSAGE and the EXTRACTED JSON. Re-read the message carefully and verify every "
            "station, number, date, time, line, wagon count, commodity and party name against it.\n"
            "- Fix ONLY what is clearly wrong or clearly missing. Do not invent anything.\n"
            "- Keep the same schema and follow the same rules (given below), including merge rules and abbreviations.\n"
            "- Return the FULL corrected JSON (all 4 keys).\n\n"
            + _context_block(sender, ts, hint)
            + "\n=== OFFICIAL STATIONS ===\n" + _station_legend() + "\n"
            + RULES_TEXT
            + "\nORIGINAL MESSAGE:\n\"\"\"" + msg + "\"\"\"\n\nEXTRACTED JSON:\n" + json.dumps(data, ensure_ascii=False)
            + "\n\nCorrected JSON only, no markdown:"
        )
        fixed = _normalize_parsed(gemini_json(prompt, tries=1))
        if not fixed:
            return data

        # Safety guards — verifier ne kuch ud-a diya to purana data rakho
        if (data.get("prs") or data.get("uts")) and not (fixed.get("prs") or fixed.get("uts")):
            print("⚠️ Verify dropped PRS/UTS → original rakha")
            return data
        if data.get("goods") and not fixed.get("goods"):
            print("⚠️ Verify dropped goods → original rakha")
            return data
        if data.get("osop") and not fixed.get("osop"):
            print("⚠️ Verify dropped OSOP → original rakha")
            return data

        if json.dumps(fixed, sort_keys=True) != json.dumps(data, sort_keys=True):
            print("🔍 Verify ne data sudhara")
        return fixed
    except Exception as e:
        print(f"⚠️ Verify error: {e}")
        return data

# ==============================================
# POST PROCESSING
# ==============================================
def apply_post_processing(data, msg, hint=None):
    if not data:
        return data

    def _fix_station_dict(d):
        out = {}
        items = [(k, v) for k, v in (d or {}).items() if isinstance(v, dict)]
        for st, vals in items:
            code = resolve_station(st)
            if not code and hint and len(items) == 1:
                code = hint
                print(f"ℹ️ Station '{st}' unresolved → hint {hint} use kiya")
            if code:
                out.setdefault(code, vals)
        return out

    data["prs"] = _fix_station_dict(data.get("prs"))
    data["uts"] = _fix_station_dict(data.get("uts"))

    new_osop = []
    for e in data.get("osop", []):
        if not isinstance(e, dict):
            continue
        code = resolve_station(e.get("station")) or hint
        if code:
            e["station"] = code
            new_osop.append(e)
    data["osop"] = new_osop

    now = ist_now()
    new_goods = []
    for e in data.get("goods", []):
        if not isinstance(e, dict):
            continue
        if e.get("from_stn"):
            e["from_stn"] = resolve_station(e["from_stn"]) or str(e["from_stn"]).upper()
        if e.get("to_stn"):
            e["to_stn"] = resolve_station(e["to_stn"]) or str(e["to_stn"]).upper()
        elif hint:
            e["to_stn"] = hint

        e["commodity"] = abbreviate_commodity(e.get("commodity"))
        e["party"] = _clean_party(e.get("party"))
        e["wagons"] = _int_if_whole(e.get("wagons"))

        wtype = str(e.get("wagon_type") or "").upper()
        if wtype in CONTAINER_WAGON_CODES or "CONTAINER" in wtype:
            e["commodity"] = "CONTAINER"

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

    # Party / date ek hi baar likhi ho to baaki rakes me bhi lagao
    parties = {e["party"] for e in new_goods if e.get("party")}
    if len(parties) == 1:
        only = next(iter(parties))
        for e in new_goods:
            if not e.get("party"):
                e["party"] = only
    dates = {str(e.get("placement_date")).strip() for e in new_goods if str(e.get("placement_date") or "").strip()}
    if len(dates) == 1:
        only_d = next(iter(dates))
        for e in new_goods:
            if not str(e.get("placement_date") or "").strip():
                e["placement_date"] = only_d

    # Date likhi hi nahi → aaj ki (time abhi se aage ho to kal ki yaani peechli raat ka)
    for e in new_goods:
        if not parse_date_flexible(e.get("placement_date")):
            d = now.date()
            pt = parse_time_flexible(e.get("placement_time"))
            if pt and datetime.combine(d, pt) > now + timedelta(minutes=5):
                d = d - timedelta(days=1)
            e["placement_date"] = d.strftime("%d/%m/%Y")
            print(f"ℹ️ Goods date missing → {e['placement_date']} lagayi")

    data["goods"] = new_goods

    # ---- UTS/PRS label correction ----
    up = msg.upper()
    has_uts = bool(re.search(r'\bUTS\b', up))
    has_prs = bool(re.search(r'\bPRS\b', up))
    only_uts_label = has_uts and not has_prs
    no_label = (not has_uts) and (not has_prs)

    if (only_uts_label or no_label) and data["prs"] and not data["goods"] and not data["osop"]:
        for st in list(data["prs"].keys()):
            vals = data["prs"][st]
            if isinstance(vals, dict) and not any(k in vals for k in PRS_ONLY_FIELDS):
                existing = data["uts"].get(st) or {}
                merged = dict(vals)
                merged.update(existing)
                data["uts"][st] = merged
                del data["prs"][st]
                print(f"ℹ️ {st}: label na hone se PRS → UTS me move kiya")

    return data

# ==============================================
# MERGE GOODS (same commodity + time + stations)
# ==============================================
def _merge_goods(entries):
    if not entries:
        return entries
    merged = {}
    order = []
    for e in entries:
        key = (
            str(e.get("from_stn") or "").upper().strip(),
            str(e.get("to_stn") or "").upper().strip(),
            abbreviate_commodity(e.get("commodity")),
            str(e.get("placement_time") or "").strip(),
            str(e.get("placement_date") or "").strip(),
            str(e.get("party") or "").upper().strip(),
        )
        if key not in merged:
            merged[key] = dict(e)
            order.append(key)
        else:
            existing = merged[key]
            try:
                existing["wagons"] = float(existing.get("wagons") or 0) + float(e.get("wagons") or 0)
                if existing["wagons"] == int(existing["wagons"]):
                    existing["wagons"] = int(existing["wagons"])
            except Exception:
                pass
            lines = []
            for ln in (existing.get("line"), e.get("line")):
                if ln is None:
                    continue
                for part in re.split(r'[,\s]+', str(ln).strip()):
                    if part and part not in lines:
                        lines.append(part)
            if lines:
                try:
                    lines_sorted = sorted(set(lines), key=lambda x: int(x) if x.isdigit() else 999)
                except Exception:
                    lines_sorted = sorted(set(lines))
                existing["line"] = ",".join(lines_sorted)
            if not existing.get("wagon_type") and e.get("wagon_type"):
                existing["wagon_type"] = e["wagon_type"]
    return [merged[k] for k in order]

# ==============================================
# REGEX FALLBACK — UTS / PRS (sirf jab Gemini fail ho)
# ==============================================
_FIELD_PATTERNS = [
    ("MR AMT", r'^MR\s*(AMT|AMOUNT)$'),
    ("MR",     r'^MR$'),
    ("C/TKT",  r'^(C/?\s*TKT|CTKT|CANCEL\w*\s*(TKT|TCKT|TICKET)\w*)$'),
    ("C/PASS", r'^(C/?\s*PASS|CPASS|CANCEL\w*\s*(PASS|PSG)\w*)$'),
    ("REF",    r'^(REF|RFD|REFUND|DIGI\s*REF\w*|DIGITAL\s*REF\w*)'),
    ("UPI",    r'^(E\s*CAS\w*|ECAS\w*|UPI.*|QR.*|DIGITAL.*|PAYTM|PHONEPE)$'),
    ("NET",    r'^(NET\s*CASH|NET|CASH|NET\s*AMOUNT|J/AMOUNT)$'),
    ("PASS",   r'^(PASS|PASSENGERS?|PSGR?|P|J/PASS)$'),
    ("TKT",    r'^(TKTS?|TCKTS?|TICKETS?|T|J/TKT)$'),
    ("PF",     r'^(PF|PLATFORM|PLT|P/TKT)$'),
]

_KV_LINE_RE = re.compile(
    r'^\s*([A-Za-z/][A-Za-z/ .&]*?)\s*[-:=.\s]*\s*(-?[\d,]+(?:\.\d+)?)\s*(?:/-|RS\.?)?\s*\.?\s*$',
    re.IGNORECASE)

def _label_to_field(label):
    lab = re.sub(r'[^A-Z/ ]', '', str(label).upper())
    lab = re.sub(r'\s+', ' ', lab).strip()
    for fld, pat in _FIELD_PATTERNS:
        if re.match(pat, lab):
            return fld
    return None

def _parse_kv_fallback(body, hint=None):
    """Simple 'label  number' lines se UTS/PRS nikalta hai."""
    code = hint
    if not code:
        found = _find_stations_in_text(body)
        if len(found) == 1:
            code = next(iter(found))
    if not code:
        return None

    section = None
    vals = {"prs": {}, "uts": {}}
    for line in body.splitlines():
        m = _KV_LINE_RE.match(line)
        if not m:
            if re.search(r'\bUTS\b', line, re.IGNORECASE):
                section = "uts"
            elif re.search(r'\bPRS\b', line, re.IGNORECASE):
                section = "prs"
            continue
        fld = _label_to_field(m.group(1))
        num = _to_float(m.group(2))
        if not fld or num is None:
            continue
        sec = section or "uts"
        if fld == "REF":
            vals[sec]["REF"] = vals[sec].get("REF", 0) + num
        else:
            vals[sec].setdefault(fld, num)

    out = {"prs": {}, "uts": {}, "osop": [], "goods": []}
    if vals["prs"]:
        out["prs"][code] = vals["prs"]
    if vals["uts"]:
        out["uts"][code] = vals["uts"]
    if not out["prs"] and not out["uts"]:
        return None
    print(f"🔧 Regex KV fallback used for {code}: {out}")
    return out

# ==============================================
# REGEX FALLBACK — GOODS (sirf jab Gemini goods na nikaal paye)
# ==============================================
def _parse_goods_regex(msg):
    up = msg.upper().replace("\n", " ")
    up = re.sub(r'\s+', ' ', up)

    pdate_m = re.search(r'(?:ON\s+DATE|DATE)\s*[-:=]?\s*(\d{1,4}[-/\.]\d{1,2}[-/\.]\d{2,4})', up)
    if not pdate_m:
        pdate_m = re.search(r'(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4})', up)
    shared_date = pdate_m.group(1) if pdate_m else ""

    ptime_m = re.search(r'(?:AT|PLACED\s+AT|P/?TIME)\s*[-:=]?\s*(\d{1,2}\s*[:/\.]\s*\d{1,2})\s*(?:HRS|HR)?', up)
    shared_time = ptime_m.group(1) if ptime_m else ""

    party_m = re.search(r'PARTY\s*[-:=]\s*(.+?)(?:\s{2,}|$)', up)
    shared_party = _clean_party(party_m.group(1)) if party_m else ""

    pattern = re.compile(
        r'(\d+)\s*(?:[A-Z0-9]{2,6}\s*)?'
        r'(?:RICE\s*\([A-Z]+\)|WHEAT\s*\([A-Z]+\)|RICE|WHEAT|[A-Z]{3,})?\s*'
        r'WAGONS?\s+EX\s*[-:]?\s*([A-Z]{2,6})\s+TO\s+([A-Z]{2,6})\s*'
        r'(?:.*?L\s*/\s*NO\s*[-:=]?\s*(\d+))?',
        re.IGNORECASE
    )

    entries = []
    for m in pattern.finditer(up):
        wagons = int(m.group(1))
        from_raw = m.group(2)
        to_raw = m.group(3)
        line = m.group(4) or ""

        ctx_start = max(0, m.start() - 3)
        ctx = up[ctx_start:m.end()]
        comm_match = re.search(r'(RICE|WHEAT)\s*\(\s*([A-Z]+)\s*\)', ctx)
        if comm_match:
            commodity = f"{comm_match.group(1)}({comm_match.group(2)})"
        else:
            c = re.search(r'\b(RICE|WHEAT|CEMENT|COAL|NAPHTHA|CONTAINER|FERT)\b', ctx)
            commodity = c.group(1) if c else ""

        entries.append({
            "from_stn": resolve_station(from_raw) or from_raw,
            "to_stn": resolve_station(to_raw) or to_raw,
            "wagons": wagons,
            "placement_time": shared_time,
            "placement_date": shared_date,
            "commodity": abbreviate_commodity(commodity),
            "line": line,
            "party": shared_party
        })

    if entries:
        print(f"🔧 Regex goods parsed: {len(entries)} raw entries → merging...")
        entries = _merge_goods(entries)
        print(f"🔧 After merge: {len(entries)} entries")
    return entries

def apply_fallback_fixes(data, msg):
    if not data:
        return data

    up = msg.upper()
    prs = data.get("prs") or {}

    # ---- REF safety net: sirf jab Gemini ne REF diya hi nahi, aur ek hi PRS station ho ----
    if len(prs) == 1:
        st, vals = next(iter(prs.items()))
        if isinstance(vals, dict) and not vals.get("REF"):
            amounts = re.findall(
                r'\b(?:RFD|REFUND|DIGI\s*REF\w*|DIGITAL\s*REF\w*|DIGI\s*REFUND|DIGITAL\s*RFD)\s*[.=:\-\s]*\s*(?:RS\.?\s*)?([\d,]+(?:\.\d+)?)\b(?!\s*/)',
                up
            )
            nums = [n for n in (_to_float(a) for a in amounts) if n]
            if nums:
                vals["REF"] = sum(nums)
                prs[st] = vals
                print(f"💰 PRS {st} REF regex se: {vals['REF']}")
    data["prs"] = prs

    # OSOP fallback
    osop = data.get("osop") or []
    if "OSOP" in up and not osop:
        lines = msg.splitlines()
        for i, line in enumerate(lines):
            if re.search(r'\bOSOP\b', line, re.IGNORECASE):
                window = "\n".join(lines[i:i+8])
                st_m = re.search(r'OSOP\s*[:\-]?\s*([A-Za-z][A-Za-z0-9 .]+)', window, re.IGNORECASE)
                if not st_m:
                    continue
                code = resolve_station(st_m.group(1))
                if not code:
                    continue
                date_m = re.search(r'(\d{1,4}[-/\.]\d{1,2}[-/\.]\d{1,4})', window)
                unit_m = re.search(r'(?:unit|u)\s*[:=\-]?\s*(\d+)', window, re.IGNORECASE)
                amt_m  = re.search(r'(?:amt|amount|rs\.?)\s*[:=\-]?\s*([\d,]+)', window, re.IGNORECASE)
                if date_m and amt_m:
                    entry = {"station": code, "date": date_m.group(1),
                             "amount": _to_float(amt_m.group(1))}
                    if unit_m:
                        entry["unit"] = int(unit_m.group(1))
                    osop.append(entry)
        data["osop"] = osop

    # GOODS: Gemini pehle. Regex tabhi jab Gemini ne kuch nahi diya
    gemini_goods = data.get("goods") or []
    if gemini_goods:
        data["goods"] = _merge_goods(gemini_goods)
        print(f"✅ Goods from Gemini (merged): {len(data['goods'])} entries")
    else:
        regex_goods = _parse_goods_regex(msg)
        if regex_goods:
            data["goods"] = regex_goods
            print(f"✅ Goods from regex fallback: {len(regex_goods)} entries")

    return data

# ==============================================
# UPDATE SHEET (UTS & PRS)
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
        if not info:
            print(f"⚠️ PRS: '{st}' sheet me nahi mila")
            continue
        if not _has_any_nonzero(vals):
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
                queue(row, col, int(v) if v == int(v) else v)
                print(f"✅ PRS {st} {fld}: wrote {v}")
            else:
                print(f"⏭️ PRS {st} {fld}: cell already filled")

    for st, vals in data.get("uts", {}).items():
        info = smap.get(st)
        if not info:
            print(f"⚠️ UTS: '{st}' sheet me nahi mila")
            continue
        if not _has_any_nonzero(vals):
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
                queue(row, col, int(v) if v == int(v) else v)
                print(f"✅ UTS {st} {fld}: wrote {v}")
            else:
                print(f"⏭️ UTS {st} {fld}: cell already filled")

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
                print("⚠️ OSOP: row 5 me dates nahi mili")
                continue

            station_rows = {}
            for r in range(6, len(matrix) + 1):
                if r-1 >= len(matrix):
                    break
                cell = matrix[r-1][1] if len(matrix[r-1]) > 1 else ""
                if not str(cell).strip():
                    continue
                code = resolve_station(cell, quiet=True)
                if code:
                    station_rows.setdefault(code, []).append(r)

            code = e.get("station")
            if code not in station_rows:
                print(f"⚠️ OSOP: '{code}' sheet me nahi mila")
                continue

            rows = station_rows[code]
            d = parse_date_flexible(e.get("date"))
            if not d or d not in date_cols:
                print(f"⚠️ OSOP: date {e.get('date')} sheet columns me nahi mili")
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
                print(f"⏭️ OSOP {code} {d}: cells already filled")
                continue

            row = chosen_row
            updates = []

            amt = _to_float(e.get("amount")) if e.get("amount") is not None else None
            if amt is not None and amt != 0:
                if is_cell_empty(get_current(row, camt)):
                    updates.append({"range": rowcol_to_a1(row, camt), "values": [[_int_if_whole(amt)]]})

            unit = e.get("unit")
            if unit is None or str(unit).strip() == "":
                if amt is not None:
                    unit = int(amt // 100)
            if unit is not None and str(unit).strip() != "":
                if is_cell_empty(get_current(row, cunit)):
                    updates.append({"range": rowcol_to_a1(row, cunit), "values": [[_int_if_whole(unit)]]})

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

def calc_free_time(wagons_num, commodity="", given=""):
    """Free time rule:
       NAPHTHA = 8 HRS | CONTAINER = 3 HRS
       <=20 wagons = 5 | 21-30 = 7 | 31-44 = 9 | 45+ = 11 HRS
    """
    comm = str(commodity or "").upper()
    if "NAPHTHA" in comm or "NAPTHA" in comm:
        return "8 HRS"
    g = str(given or "").strip().upper()
    if g:
        if re.fullmatch(r'\d+(\.\d+)?', g):
            return f"{int(float(g))} HRS"
        return g
    if "CONTAINER" in comm:
        return "3 HRS"
    if wagons_num >= 45:
        return "11 HRS"
    if wagons_num > 30:
        return "9 HRS"
    if wagons_num > 20:
        return "7 HRS"
    return "5 HRS"

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
        batch_seen = set()

        for e in entries:
            if not isinstance(e, dict):
                continue

            from_stn  = _norm_str(e.get("from_stn"))
            to_stn    = _norm_str(e.get("to_stn"))
            wagons    = _int_if_whole(e.get("wagons"))
            ptime     = parse_time_flexible(e.get("placement_time"))
            pdate     = parse_date_flexible(e.get("placement_date"))
            commodity = abbreviate_commodity(e.get("commodity"))
            line      = _norm_str(e.get("line"))
            party     = _clean_party(e.get("party"))
            wtype     = _norm_str(e.get("wagon_type"))
            ftime     = _norm_str(e.get("free_time"))

            if not to_stn or not pdate:
                print(f"⏭️ Missing to_stn/date → skip")
                continue

            print(f"🔎 {from_stn}→{to_stn} | date={pdate} time={ptime} wagons={wagons} line={line} commodity={commodity} party={party}")

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

            dup_key = (to_stn, pdate_str_check, ptime_str_check, wagons_str_check, from_stn, commodity, line, party)
            if dup_key in batch_seen:
                print(f"⏭️ Duplicate in same message (line {line})")
                continue

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
                existing_party     = _clean_party(row[22]) if len(row) > 22 else ""

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

            batch_seen.add(dup_key)

            if wtype in CONTAINER_WAGON_CODES or "CONTAINER" in wtype:
                commodity = "CONTAINER"
            elif "CONTAINER" in commodity:
                if not wtype:
                    wtype = "CONTAINER"

            try:
                wagons_num = int(float(wagons)) if wagons else 42
            except Exception:
                wagons_num = 42

            # ---- Free time (45+ wagons = 11 HRS) ----
            ftime = calc_free_time(wagons_num, commodity, ftime)

            # ---- Wagon type default ----
            if not wtype:
                if "NAPHTHA" in commodity or "NAPTHA" in commodity:
                    wtype = "BTPN"
                elif "CONTAINER" in commodity:
                    wtype = "CONTAINER"
                elif "CEMENT" in commodity:
                    wtype = "BCN"
                elif "COAL" in commodity:
                    wtype = "BOXN"
                else:
                    wtype = "BCN"

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
                if col and val is not None and str(val).strip() != "":
                    updates.append({"range": rowcol_to_a1(current_row, col), "values": [[val]]})

            q(2, to_stn); q(3, line); q(4, wtype); q(5, commodity)
            q(6, wagons); q(8, wagons)
            q(9, arrival_time_str); q(10, arrival_date_str)
            q(11, ptime_str); q(12, pdate_str)
            q(18, ftime); q(21, from_stn); q(23, party)

            # Optional extra columns (env se set karo)
            q(IWOW_WEIGHT_COL, e.get("weight"))
            q(IWOW_FREIGHT_COL, e.get("freight"))
            q(IWOW_REMARK_COL, e.get("remarks"))

            print(f"✅ IWOW row {current_row}: {from_stn}→{to_stn} | wagons={wagons} | line={line} | {commodity} | free={ftime} | party={party}")
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
# MESSAGE PIPELINE
# ==============================================
def _has_content(data):
    return bool(data and (data.get("prs") or data.get("uts") or data.get("osop") or data.get("goods")))

def process_block(body, sender="", ts=""):
    print(f"\n📩 Block | sender='{sender}' | ts='{ts}'\n{body[:400]}")
    hint = guess_station_hint(body, sender)
    print(f"📍 Station hint: {hint}")

    data = call_gemini(body, sender, ts, hint)

    if _has_content(data):
        data = gemini_verify(body, data, sender, ts, hint)
    else:
        print("⚠️ Gemini empty/failed → regex fallback try")
        fb = _parse_kv_fallback(body, hint)
        if fb:
            data = fb

    if not data:
        print("❌ Extraction failed")
        return

    data = apply_post_processing(data, body, hint)
    data = apply_fallback_fixes(data, body)
    print("✅ Final Data:", json.dumps(data, ensure_ascii=False))

    if data.get("prs") or data.get("uts"):
        update_google_sheet(data)

    if data.get("osop"):
        update_osop_sheet(data["osop"])

    if data.get("goods"):
        update_iwow_sheet(data["goods"])

def process_incoming(text):
    with PROCESS_LOCK:
        try:
            blocks = split_chat_messages(text)
            print(f"📦 {len(blocks)} message block(s) mile")
            for b in blocks:
                try:
                    process_block(b["body"], b["sender"], b["ts"])
                except Exception as e:
                    print(f"❌ Block error: {e}")
        except Exception as e:
            print(f"❌ process_incoming error: {e}")

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

                    # Meta ko turant 200 chahiye → processing background me
                    threading.Thread(target=process_incoming, args=(text,), daemon=True).start()
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
    print(f"GEMINI_VERIFY   : {GEMINI_VERIFY}")
    print(f"CREDENTIALS     : {bool(GOOGLE_CREDENTIALS_STR or GOOGLE_CREDENTIALS_B64)}")
    print(f"IWOW_GRACE_HOUR : {IWOW_GRACE_HOUR}:00 IST")
    print(f"IST_NOW         : {ist_now().strftime('%Y-%m-%d %H:%M:%S')}")
    get_sheet()
    print("===================================")

startup_check()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
