import os
import re
import math
import json
import time
import base64
import threading
import contextlib
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

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_THINKING = int(os.environ.get("GEMINI_THINKING", "1024"))

SHEET_LOCK_FILE = "/tmp/sheet_update.lock"
OSOP_LOCK_FILE = "/tmp/osop_update.lock"
IWOW_LOCK_FILE = "/tmp/iwow_update.lock"
IWOW_GRACE_HOUR = int(os.environ.get("IWOW_GRACE_HOUR", "2"))
# Same entry dobara aaye (forward / Meta retry / chat me do baar paste) to is sandarbh me bhi rok lo
IWOW_RECENT_FILE = os.environ.get("IWOW_RECENT_FILE", "/tmp/iwow_recent.json")
IWOW_DEDUPE_MINUTES = int(os.environ.get("IWOW_DEDUPE_MINUTES", "120"))
# IWOW me "row khaali hai" tay karne wale columns (B to-stn, E commodity, F wagons, K/L placement time/date)
IWOW_CORE_COLS = (2, 5, 6, 11, 12)

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

FIELD_ALIASES = {
    "TICKET": "TKT", "TICKETS": "TKT", "TKTS": "TKT", "TCKT": "TKT",
    "PSG": "PASS", "PSGR": "PASS", "PASSENGER": "PASS", "PASSENGERS": "PASS",
    "CTKT": "C/TKT", "C TKT": "C/TKT", "CPASS": "C/PASS", "C PASS": "C/PASS",
    "MRAMT": "MR AMT", "MR_AMT": "MR AMT",
    "REFUND": "REF", "RFD": "REF",
    "ECASH": "UPI", "E CASH": "UPI", "UPI QR": "UPI", "QR": "UPI",
    "NET CASH": "NET", "CASH": "NET",
    "PLATFORM": "PF",
}

# ==============================================
# COMMODITY ABBREVIATION
# ==============================================
def abbreviate_commodity(comm):
    """RICE(FCI)→FCI/R, WHEAT(FCI)→FCI/W, RICE(PUB)→PUB/R, WHEAT(PUB)→PUB/W."""
    if not comm:
        return ""
    c = str(comm).upper().strip()
    c = re.sub(r'\s+', ' ', c)

    if re.fullmatch(r'(FCI|PUB)/[RW]', c):
        return c
    if "CONTAINER" in c or c in ("CONT", "CNTR"):
        return "CONTAINER"
    if "NAPHTHA" in c or "NAPTHA" in c:
        return "NAPHTHA"

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

def _is_container(commodity, wtype):
    tokens = set(re.split(r'[^A-Z0-9]+', str(wtype or "").upper()))
    return "CONTAINER" in str(commodity or "").upper() or "CONTAINER" in str(wtype or "").upper() \
        or bool(tokens & CONTAINER_WAGON_CODES)

def iwow_free_time(wagons, commodity="", wtype=""):
    """
    46 ya usse zyada wagons -> 11 HRS (sabse pehle).
    Naphtha 8, Container 3, <=20 -> 5, <=30 -> 7, baaki (31-45) -> 9.
    """
    try:
        w = int(float(wagons)) if wagons not in (None, "") else 42
    except Exception:
        w = 42
    if w >= 46:
        return "11 HRS"
    c = str(commodity or "").upper()
    if "NAPHTHA" in c or "NAPTHA" in c:
        return "8 HRS"
    if _is_container(c, wtype):
        return "3 HRS"
    if w <= 20:
        return "5 HRS"
    if w <= 30:
        return "7 HRS"
    return "9 HRS"

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
    _alias_index.setdefault(_norm_station(_code), _code)
    for _a in _aliases:
        _alias_index.setdefault(_norm_station(_a), _code)
        _alias_index.setdefault(_norm_station(_a).replace(' ', ''), _code)
for _code, _nm in STATION_OFFICIAL.items():
    _alias_index.setdefault(_norm_station(_nm), _code)
    _alias_index.setdefault(_norm_station(_nm).replace(' ', ''), _code)

def resolve_station(name, quiet=False):
    if not name:
        return None
    original = str(name).upper().strip()
    n = re.sub(r'[^A-Z0-9 ]', ' ', original)
    n = re.sub(r'\s+', ' ', n).strip()
    if not n:
        return None

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

    # fuzzy — sirf tab jab exactly ek station match ho
    n2_clean = n2.replace(' ', '')
    if len(n2_clean) >= 5:
        hits = set()
        for code, aliases in STATION_ALIASES.items():
            for alias in aliases:
                a_clean = alias.replace(' ', '')
                if len(a_clean) >= 4 and (n2_clean in a_clean or a_clean in n2_clean):
                    hits.add(code)
        if len(hits) == 1:
            return next(iter(hits))

    if not quiet:
        print(f"⚠️ Could not resolve station: '{original}'")
    return None

# ==============================================
# META RETRY PROTECTION
# ==============================================
PROCESSED_MSG_IDS = {}
_PROC_LOCK = threading.Lock()

def already_processed(msg_id):
    if not msg_id:
        return False
    now = time.time()
    with _PROC_LOCK:
        for k in [k for k, t in PROCESSED_MSG_IDS.items() if now - t > 600]:
            del PROCESSED_MSG_IDS[k]
        if msg_id in PROCESSED_MSG_IDS:
            return True
        PROCESSED_MSG_IDS[msg_id] = now
        return False

@contextlib.contextmanager
def file_lock(path):
    f = open(path, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(f, fcntl.LOCK_UN)
        finally:
            f.close()

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
                    return d
                except json.JSONDecodeError:
                    pass
        errors.append("RAW JSON failed")

    print(f"❌ Credentials load failed: {' | '.join(errors) if errors else 'No credentials found'}")
    return None

# ==============================================
# GOOGLE SHEETS
# ==============================================
_GC = None
_GC_TIME = 0.0
_GC_LOCK = threading.Lock()

def _get_gc(force=False):
    """gspread client 45 min cache — har message pe naya login nahi."""
    global _GC, _GC_TIME
    with _GC_LOCK:
        if not force and _GC is not None and time.time() - _GC_TIME < 2700:
            return _GC
        creds_dict = load_credentials_dict()
        if not creds_dict:
            return None
        scopes = ["https://www.googleapis.com/auth/spreadsheets",
                  "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        _GC = gspread.authorize(creds)
        _GC_TIME = time.time()
        return _GC

def gs_retry(fn, *args, **kwargs):
    """Sheets API 429/5xx par retry."""
    last = None
    for attempt in range(5):
        try:
            return fn(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            last = e
            code = getattr(getattr(e, "response", None), "status_code", 0)
            if code in (429, 500, 502, 503, 504):
                time.sleep(min(2 ** attempt, 20) + random.random())
                continue
            raise
        except requests.RequestException as e:
            last = e
            time.sleep(min(2 ** attempt, 10) + random.random())
    raise last

def get_spreadsheet():
    try:
        gc = _get_gc()
        if not gc:
            return None
        try:
            sh = gs_retry(gc.open, SHEET_NAME)
        except Exception:
            gc = _get_gc(force=True)      # token/client purana ho gaya ho to naya
            if not gc:
                return None
            sh = gs_retry(gc.open, SHEET_NAME)
        return sh
    except Exception as e:
        print(f"❌ Google Sheet Connection Error: {e}")
        return None

def get_sheet():
    sh = get_spreadsheet()
    if not sh:
        return None
    try:
        sheet = sh.worksheet("UTS&PRS")
    except gspread.WorksheetNotFound:
        print("⚠️ 'UTS&PRS' tab nahi mili → sheet1 use kar rahe hain")
        sheet = sh.sheet1
    return sheet

def get_station_map(sheet, all_values=None):
    """
    Stations B7:B36 me (primary). Purani ranges (M, C) backward-compat ke liye.
    Map me raw cell text aur resolved station code dono keys hain.
    """
    m = {}
    if all_values is None:
        try:
            all_values = gs_retry(sheet.get_all_values)
        except Exception as e:
            print(f"❌ Error reading sheet: {e}")
            return m

    def add(val, row, col):
        raw = str(val).upper().strip()
        if not raw:
            return
        info = {"row": row, "nameCol": col}
        m.setdefault(raw, info)
        code = resolve_station(raw, quiet=True)
        if code:
            m.setdefault(code, info)

    for i in range(6, min(36, len(all_values))):          # row 7..36
        add(all_values[i][1] if len(all_values[i]) > 1 else "", i + 1, "B")
    for i in range(30, min(47, len(all_values))):
        add(all_values[i][12] if len(all_values[i]) > 12 else "", i + 1, "M")
    for i in range(31, min(48, len(all_values))):
        add(all_values[i][2] if len(all_values[i]) > 2 else "", i + 1, "C")

    print(f"✅ Station map ready: {len(m)} keys")
    return m

# ==============================================
# DATE / TIME PARSERS
# ==============================================
def ist_now():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow() + timedelta(hours=5, minutes=30)

def parse_date_flexible(s):
    if s is None or isinstance(s, bool):
        return None
    if isinstance(s, (int, float)):          # Sheets serial date (UNFORMATTED_VALUE)
        if 20000 < s < 80000:
            return (datetime(1899, 12, 30) + timedelta(days=int(s))).date()
        return None
    s = str(s).strip()
    if not s:
        return None
    s = re.sub(r'(?<=\d)(st|nd|rd|th)\b', '', s, flags=re.I)
    formats = (
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
        "%Y-%m-%d", "%Y/%m/%d",
        "%d %b %Y", "%d %B %Y", "%d %b %y", "%d %B %y",
        "%d %m %Y", "%d %m %y",
        "%d-%b-%Y", "%d-%b-%y", "%d/%b/%Y", "%d-%B-%Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    # saal ke bina (04/11, 4-11, 4 Nov) -> current saal (pehle ye 1900 ban jata tha)
    year = ist_now().year
    for fmt in ("%d/%m", "%d-%m", "%d.%m", "%d %b", "%d %B"):
        try:
            return datetime.strptime(f"{s} {year}", fmt + " %Y").date()
        except ValueError:
            pass
    try:
        from dateutil import parser as _dp
        return _dp.parse(s, dayfirst=True).date()
    except Exception:
        return None

def parse_time_flexible(s):
    """Tolerant — 12:50, 12/50, 12.50, 1250, 12:50 HRS, 2:30 pm."""
    if s is None:
        return None
    if isinstance(s, dt_time):
        return s
    if isinstance(s, bool):
        return None
    if isinstance(s, float) and 0 <= s < 1:   # Sheets time fraction (UNFORMATTED_VALUE)
        mins = int(round(s * 1440)) % 1440
        return dt_time(mins // 60, mins % 60)
    s = str(s).strip().upper()
    if not s:
        return None
    ampm = None
    m_ap = re.search(r'(?<![A-Z])([AP])\.?M\b\.?', s)
    if m_ap:
        ampm = m_ap.group(1) + "M"
    s = re.sub(r'(?<![A-Z])[AP]\.?M\b\.?', '', s)
    s = re.sub(r'\b(HRS|HR|HOURS|HOUR)\b', '', s).strip()
    s = re.sub(r'[/\.\-]', ':', s).replace(' ', '')
    s = re.sub(r':+', ':', s)

    hh = mm = None
    m = re.fullmatch(r'(\d{1,2}):(\d{1,2})(?::\d{1,2})?', s)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
    else:
        m = re.fullmatch(r'(\d{3,4})', s)
        if m:
            v = m.group(1).zfill(4)
            hh, mm = int(v[:2]), int(v[2:])
        else:
            m = re.search(r'(\d{1,2}):(\d{1,2})', s)
            if m:
                hh, mm = int(m.group(1)), int(m.group(2))
    if hh is None:
        return None
    if ampm == "PM" and hh < 12:
        hh += 12
    if ampm == "AM" and hh == 12:
        hh = 0
    if 0 <= hh <= 23 and 0 <= mm <= 59:
        return dt_time(hh, mm)
    return None

# ==============================================
# NUMBER / REGEX HELPERS
# ==============================================
def _to_float(s):
    try:
        return float(str(s).replace(",", "").strip())
    except Exception:
        return None

def _clean_num(v):
    """'1,200', 'Rs 500/-', 12.0 -> number. Nil/blank -> None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        f = float(v)
    else:
        s = str(v).strip().replace(",", "").replace("₹", "")
        s = re.sub(r'(?i)\brs\.?', '', s)
        m = re.search(r'-?\d+(?:\.\d+)?', s)
        if not m:
            return None
        f = float(m.group())
    if f != f:
        return None
    return int(f) if f.is_integer() else round(f, 2)

_ALIAS_LIST = sorted(
    ((re.sub(r'[^A-Z0-9]+', ' ', a.upper()).strip(), code)
     for code, als in STATION_ALIASES.items() for a in als),
    key=lambda x: -len(x[0]))

def _find_stations_in_text(msg):
    """Lambe naam pehle match hote hain, taaki 'DIBRUGARH TOWN' me 'DIBRUGARH' alag na aaye."""
    up = " " + re.sub(r'[^A-Z0-9]+', ' ', str(msg or "").upper()) + " "
    found = set()
    for alias, code in _ALIAS_LIST:
        a = f" {alias} "
        if a in up:
            found.add(code)
            up = up.replace(a, " ")
    return found

def _norm_field(k):
    k = re.sub(r'\s+', ' ', str(k).upper().strip())
    return FIELD_ALIASES.get(k, k)

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
    text = (text or "").replace("\u200e", "").replace("\u200f", "").replace("\u202f", " ").replace("\u00a0", " ")
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
# GEMINI — natural, trusting
# ==============================================
PROMPT_TEMPLATE = r"""You are an expert Indian Railway data extraction engine for the Tinsukia Division.
You read WhatsApp messages like a seasoned railway accountant — messy formats, broken lines, Hinglish, typos, garbled paste, squished text, copied/forwarded chat text, random spacing, mixed labels, missing separators. You understand naturally. Trust your own judgement and extract EVERYTHING that is really present. Never invent numbers that are not in the message.

Return ONE JSON object with these keys (all present, empty if nothing found):
  "prs"   : { "<STATION_CODE>": { "TKT":num, "PASS":num, "C/TKT":num, "C/PASS":num, "REF":num, "NET":num, "VCH":num, "POS":num, "UPI":num } }
  "uts"   : { "<STATION_CODE>": { "PF":num, "TKT":num, "PASS":num, "NET":num, "MR":num, "MR AMT":num, "UPI":num } }
  "osop"  : [ { "station":"CODE", "date":"as written", "amount":num, "unit":num or omit } ]
  "goods" : [ { "from_stn":"CODE", "to_stn":"CODE", "wagons":num, "placement_time":"HH:MM", "placement_date":"as written", "commodity":"ABBREVIATED UPPERCASE", "line":"number or comma list", "party":"UPPERCASE", "wagon_type":"optional", "weight":num or omit, "freight":num or omit } ]

=== CONTEXT ===
__CTX__
STATION HINT (use ONLY if the message text itself names no station): __HINT__
The message may begin with chat-export noise like "[04/11, 7:03 pm] Name:" — ignore it. Sender names/designations (Sr CTC, SM, SS, Pradip Mishra) are NOT data.
One message can contain several things at once (PRS + UTS + OSOP + goods, or several stations). Extract all of them.

=== OFFICIAL STATIONS (CODE = Full Name) ===
__LEGEND__
Always output the CODE, never the full name. Fix spelling mistakes and short forms yourself (Kown/Khowang → KOWN, Krht → KRHT).

=== PRS / UTS READING GUIDE ===
- Normally ONE station's daily revenue report. Station key = CODE (from text like "REVENUE OF BFD", "Kown 4/11/26", "Krht uts of ..." or from STATION HINT). Multi-station bundles are possible → one key per station.
- Lines under a "UTS" heading → "uts". Lines under a "PRS" heading → "prs". If the message has NO UTS/PRS label at all (small stations) → treat as UTS.
- Field meanings (people write them in many ways):
    TKT   : TKT / Tkts / Tckt / Ticket / T / J/TKT
    PASS  : PASS / Psg / Psgr / Passenger / P (when it sits beside T) / J/Pass
    NET   : NET CASH / Net / Cash / Cash amount / J/Amount  — the cash collection amount (never the grand total)
    UPI   : E CASH / Ecash / E-cash / E cas / UPI / UPI QR / QR / Digital / Paytm / PhonePe
    REF   : REFUND / RFD / Digi ref / Digital refund / Digi refund / Digital RFD — SUM OF ALL refund-type amounts found anywhere in the message. If multiple refund lines exist (e.g. REFUND 500 + Digi ref 200 + RFD 100), put the TOTAL (800) in REF. Never take only the first one.
    C/TKT, C/PASS : cancelled tickets / cancelled passengers (PRS)
    PF    : platform tickets (PF / P/TKT / PLT / PLATFORM / "M")
    MR / MR AMT : MR count / MR amount (both captured)
- "Ttl" / "Total" / "Grand total" lines are totals → IGNORE (never put them in NET or anywhere).
- Nil / Nill / NIL / - / blank / "nill .." → omit that key.
- Date lines like "DATE. 04/11/2026" → ignore (not a field).
- Numbers must be plain numbers (remove commas, Rs, /-).
- Missing → omit key.
- If a label is unusual or misspelt, decide by meaning and position, like a human accountant would.

PRS/UTS EXAMPLES:
Input: "REVENUE OF BFD\nDATE.     04/11/2026\nUTS\nTKT                  200\nPASS.               333\nNET CASH.    10485\nE CASH.          1230\n\nPRS\nTKT                 9\nPASS.              20\nNET CASH.    28060\nUPI QR .          10025\nREFUND.          Nill\nC/TKT.              Nill\nC/PASS.            Nill\nDigi ref:-            nill  .."
Output: {"prs":{"BFD":{"TKT":9,"PASS":20,"NET":28060,"UPI":10025}},"uts":{"BFD":{"TKT":200,"PASS":333,"NET":10485,"UPI":1230}},"osop":[],"goods":[]}

Input: "Kown 4/11/26\nPsg-9\nTckt-7\nCash-20\nEcash-400"
Output: {"prs":{},"uts":{"KOWN":{"TKT":7,"PASS":9,"NET":20,"UPI":400}},"osop":[],"goods":[]}

Input: "Krht uts of 4.11.2026\nT 36\nP 58\nCash 1390\nE cas 340\nTtl 1730 only"
Output: {"prs":{},"uts":{"KRHT":{"TKT":36,"PASS":58,"NET":1390,"UPI":340}},"osop":[],"goods":[]}

=== OSOP ===
OSOP lines give, for a station and a date, a rupee amount (and only sometimes a unit/count). Put them in "osop": station CODE, date as written (omit if not written), amount = the rupee amount. Put "unit" ONLY if the message explicitly writes a unit/count — never calculate it, the system does that.

=== INWARD GOODS / IWOW ===
Extract every goods placement into "goods" array.

Fields:
- from_stn / to_stn: station codes (to_stn = station where wagons were placed/received; if the text names none use STATION HINT)
- wagons: number of wagons
- placement_time: HH:MM 24-hour (convert "2:30 pm", "1430 hrs", "14.30" etc.)
- placement_date: date as written (omit if not written)
- commodity: ABBREVIATED uppercase (see below)
- line: just the digit; if multiple lines mentioned together → "10,12"
- party: uppercase (consignee / firm / party name if written, else "")
- wagon_type: wagon code if written (BCNL, BCNA, BCN, BOXN, BTPN, BLC ...)
- weight / freight: optional
Do NOT calculate free time — the system does it.

COMMODITY ABBREVIATION RULES (IMPORTANT — apply always):
- RICE (FCI) / FCI RICE / RICE FCI  → "FCI/R"
- WHEAT (FCI) / FCI WHEAT / WHEAT FCI → "FCI/W"
- RICE (PUB) / PUB RICE / RICE PUB → "PUB/R"
- WHEAT (PUB) / PUB WHEAT / WHEAT PUB → "PUB/W"
- RICE alone → "RICE"
- WHEAT alone → "WHEAT"
- FCI alone (no RICE/WHEAT) → "FCI"
- PUB alone → "PUB"
- CONTAINER / container wagons → "CONTAINER"
- CEMENT → "CEMENT", COAL → "COAL", NAPHTHA → "NAPHTHA", FERT → "FERT"
- Others → keep as UPPERCASE

MULTI-LINE WAGONS:
If the message reports wagons on multiple line numbers with DIFFERENT counts each → create one goods entry per line.

=== VERY IMPORTANT: SAME COMMODITY + SAME TIME ACROSS LINES → MERGE ===
If the message reports the SAME commodity, SAME from_stn, SAME to_stn, SAME placement time+date across multiple line numbers → produce ONE entry with:
- wagons = SUM of all those lines
- line = comma-joined line numbers, e.g. "10,12"

But if commodities DIFFER, keep them as separate entries.

EXAMPLE 1 (merge case):
Input:
"55 BCNL RICE(FCI) WAGONS EX-KNNN TO NTSK PLACED ON L/NO-10 AND 
03 BCNL RICE(FCI) WAGONS EX-KNNN TO NTSK PLACED ON L/NO-12 
AT 12:50 HRS ON DATE-04/11/26"

Expected output — ONE entry:
[
  {
    "from_stn": "KNNN",
    "to_stn": "NTSK",
    "wagons": 58,
    "placement_time": "12:50",
    "placement_date": "04/11/26",
    "commodity": "FCI/R",
    "line": "10,12",
    "party": "",
    "wagon_type": "BCNL"
  }
]

EXAMPLE 2 (different commodities → separate):
Input:
"20 BCNL RICE(FCI) WAGONS EX-KNNN TO NTSK PLACED ON L/NO-10
10 BCNA WHEAT(FCI) WAGONS EX-KNNN TO NTSK PLACED ON L/NO-12
AT 12:50 HRS ON DATE-04/11/26"

Expected — TWO entries:
[
  {"from_stn":"KNNN","to_stn":"NTSK","wagons":20,"placement_time":"12:50","placement_date":"04/11/26","commodity":"FCI/R","line":"10","party":"","wagon_type":"BCNL"},
  {"from_stn":"KNNN","to_stn":"NTSK","wagons":10,"placement_time":"12:50","placement_date":"04/11/26","commodity":"FCI/W","line":"12","party":"","wagon_type":"BCNA"}
]

MESSAGE:
\"\"\"__MSG__\"\"\"

JSON only, no markdown:""".replace('\\"\\"\\"', '"""')

def _gemini_post(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    gen = {"temperature": 0, "maxOutputTokens": 8192, "responseMimeType": "application/json"}
    if "2.5" in GEMINI_MODEL:
        gen["thinkingConfig"] = {"thinkingBudget": GEMINI_THINKING}
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen}

    for attempt in range(4):
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=90)
            if res.status_code == 200:
                return res.json()
            print(f"❌ Gemini HTTP {res.status_code}: {res.text[:250]}")
            if res.status_code not in (429, 500, 502, 503, 504):
                return None
        except Exception as e:
            print(f"❌ Gemini Error: {e}")
        time.sleep(min(2 ** attempt, 12) + random.random())
    return None

def _parse_gemini_json(txt):
    txt = re.sub(r'```json\n?', '', txt or "", flags=re.IGNORECASE)
    txt = re.sub(r'```\n?', '', txt).strip()
    match = re.search(r'\{[\s\S]*\}', txt)
    if not match:
        return None
    parsed = json.loads(match.group(0))
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

def call_gemini(msg, sender="", ts="", hint=None):
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY missing!")
        return None

    station_legend = "\n".join(f'{c} = {STATION_OFFICIAL[c]}' for c in ALL_STATIONS)
    hint_line = (f"{hint} ({STATION_OFFICIAL.get(hint, '')})" if hint else "none")
    ctx_line = (f"Sender name: {sender or 'unknown'} | Message time: {ts or 'unknown'} | "
                f"Now (IST): {ist_now().strftime('%d/%m/%Y %H:%M')}")

    prompt = (PROMPT_TEMPLATE
              .replace("__CTX__", ctx_line)
              .replace("__HINT__", hint_line)
              .replace("__LEGEND__", station_legend)
              .replace("__MSG__", msg))

    for attempt in range(2):          # JSON kharab aaye to ek baar aur
        resp = _gemini_post(prompt)
        if not resp:
            return None
        try:
            parts = resp["candidates"][0]["content"]["parts"]
            txt = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            parsed = _parse_gemini_json(txt)
            if parsed is not None:
                return parsed
            print("⚠️ Gemini returned no JSON")
        except Exception as e:
            print(f"⚠️ Gemini parse error: {e}")
        time.sleep(1.5)
    return None

# ==============================================
# POST-PROCESSING (sirf safai — Gemini ke data ko overwrite nahi karta)
# ==============================================
def _clean_fields(vals):
    out = {}
    if not isinstance(vals, dict):
        return out
    for k, v in vals.items():
        f = _norm_field(k)
        n = _clean_num(v)
        if n is None:
            continue
        if f == "REF" and f in out:
            out[f] = out[f] + n          # alag-alag refund lines ka total
        else:
            out[f] = n
    return out

def _norm_line(ln):
    if ln is None:
        return ""
    nums = re.findall(r'\d+', str(ln))
    if not nums:
        return str(ln).strip().upper()
    try:
        nums = sorted(set(nums), key=int)
    except Exception:
        pass
    return ",".join(nums)

def apply_post_processing(data, msg, hint=None):
    if not data:
        return data

    def _fix_station_dict(d):
        out = {}
        items = list((d or {}).items())
        for st, vals in items:
            code = resolve_station(st)
            if not code and hint and len(items) == 1:
                code = hint
                print(f"ℹ️ Station '{st}' unresolved → hint {hint} use kiya")
            if not code:
                continue
            cleaned = _clean_fields(vals)
            if code in out:
                for k, v in cleaned.items():
                    out[code][k] = out[code].get(k, 0) + v if k == "REF" else v
            else:
                out[code] = cleaned
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

    new_goods = []
    for e in data.get("goods", []):
        if not isinstance(e, dict):
            continue
        frm = str(e.get("from_stn") or "").strip()
        to = str(e.get("to_stn") or "").strip()
        e["from_stn"] = (resolve_station(frm) or frm.upper()) if frm else ""
        e["to_stn"] = (resolve_station(to) or to.upper()) if to else (hint or "")

        e["commodity"] = abbreviate_commodity(e.get("commodity"))
        wtype = str(e.get("wagon_type") or "").upper().strip()
        e["wagon_type"] = wtype
        if _is_container("", wtype):
            e["commodity"] = "CONTAINER"

        wg = _clean_num(e.get("wagons"))
        e["wagons"] = int(wg) if wg is not None else None

        ln = e.get("line")
        if ln is not None:
            e["line"] = _norm_line(ln)
        new_goods.append(e)
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
        t = parse_time_flexible(e.get("placement_time"))
        d = parse_date_flexible(e.get("placement_date"))
        key = (
            str(e.get("from_stn") or "").upper().strip(),
            str(e.get("to_stn") or "").upper().strip(),
            abbreviate_commodity(e.get("commodity")),
            t.strftime("%H:%M") if t else str(e.get("placement_time") or "").strip(),
            d.isoformat() if d else str(e.get("placement_date") or "").strip(),
            str(e.get("party") or "").upper().strip(),
        )
        if key not in merged:
            merged[key] = dict(e)
            order.append(key)
        else:
            ex = merged[key]
            a, b = _clean_num(ex.get("wagons")), _clean_num(e.get("wagons"))
            if a is not None or b is not None:
                ex["wagons"] = int((a or 0) + (b or 0))
            ex["line"] = _norm_line(",".join(str(x) for x in (ex.get("line"), e.get("line")) if x not in (None, "")))
            if not ex.get("wagon_type") and e.get("wagon_type"):
                ex["wagon_type"] = e["wagon_type"]
    return [merged[k] for k in order]

# ==============================================
# REGEX FALLBACK — UTS / PRS
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
    """Gemini fail ho to simple 'label number' lines se UTS/PRS."""
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
# REGEX FALLBACK — GOODS (sirf jab Gemini kuch na de)
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

    pattern = re.compile(
        r'(\d+)\s*(?:([A-Z0-9]{2,6})\s*)?'
        r'(?:RICE\s*\([A-Z]+\)|WHEAT\s*\([A-Z]+\)|RICE|WHEAT|[A-Z]{3,})?\s*'
        r'WAGONS?\s+EX\s*[-:]?\s*([A-Z]{2,6})\s+TO\s+([A-Z]{2,6})\s*'
        r'(?:.*?L\s*/\s*NO\s*[-:=]?\s*(\d+))?',
        re.IGNORECASE
    )

    entries = []
    for m in pattern.finditer(up):
        wagons = int(m.group(1))
        wtype = m.group(2) or ""
        from_raw, to_raw = m.group(3), m.group(4)
        line = m.group(5) or ""

        ctx = up[max(0, m.start() - 3):m.end()]
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
            "party": "",
            "wagon_type": wtype if re.fullmatch(r'B[A-Z]{2,5}', wtype) else "",
        })

    if entries:
        entries = _merge_goods(entries)
        print(f"🔧 Regex goods parsed → {len(entries)} entries")
    return entries

_REFUND_RE = re.compile(
    r'(?:DIGI(?:TAL)?\s*(?:REF\w*|RFD)|\bRFD|\bREFUND)[ \t=:\-\./]*([\d,]+(?:\.\d+)?)')

def apply_fallback_fixes(data, msg):
    """Gemini ka data primary hai; yahan sirf kami hone par madad."""
    if data is None:
        data = {"prs": {}, "uts": {}, "osop": [], "goods": []}

    up = msg.upper()

    # ---- Refund safety-net: sirf single-station PRS me, aur sirf jab Gemini ka REF kam/missing ho ----
    nums = [n for n in (_to_float(a) for a in _REFUND_RE.findall(up)) if n]
    if nums:
        total = sum(nums)
        total = int(total) if float(total).is_integer() else total
        prs = data.get("prs") or {}
        if len(prs) == 1:
            st = next(iter(prs))
            cur = prs[st].get("REF") if isinstance(prs[st], dict) else None
            if cur is None or cur < total:
                prs[st]["REF"] = total
                print(f"💰 PRS {st} REF corrected → {total}")
        elif not prs and re.search(r'\bPRS\b', up):
            found = _find_stations_in_text(msg)
            if len(found) == 1:
                prs[next(iter(found))] = {"REF": total}
                data["prs"] = prs

    # ---- OSOP fallback ----
    osop = data.get("osop") or []
    if "OSOP" in up and not osop:
        lines = msg.splitlines()
        for i, line in enumerate(lines):
            if re.search(r'\bOSOP\b', line, re.IGNORECASE):
                window = "\n".join(lines[i:i + 8])
                st_m = re.search(r'OSOP\s*[:\-]?\s*([A-Za-z][A-Za-z0-9 .]+)', window, re.IGNORECASE)
                if not st_m:
                    continue
                code = resolve_station(st_m.group(1))
                if not code:
                    continue
                date_m = re.search(r'(\d{1,4}[-/\.]\d{1,2}[-/\.]\d{1,4})', window)
                unit_m = re.search(r'(?:unit|u)\s*[:=\-]?\s*(\d+)', window, re.IGNORECASE)
                amt_m = re.search(r'(?:amt|amount|rs\.?)\s*[:=\-]?\s*([\d,]+)', window, re.IGNORECASE)
                if date_m and amt_m:
                    entry = {"station": code, "date": date_m.group(1), "amount": _to_float(amt_m.group(1))}
                    if unit_m:
                        entry["unit"] = int(unit_m.group(1))
                    osop.append(entry)
        data["osop"] = osop

    # ---- Goods: Gemini primary (merge karke), regex sirf fallback ----
    gem_goods = data.get("goods") or []
    if gem_goods:
        data["goods"] = _merge_goods(gem_goods)
    else:
        data["goods"] = _parse_goods_regex(msg)
    return data

# ==============================================
# UPDATE SHEET (PRS / UTS)
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

def update_google_sheet(data):
    with file_lock(SHEET_LOCK_FILE):
        sheet = get_sheet()
        if not sheet:
            return False

        try:
            matrix = gs_retry(sheet.get_all_values)
        except Exception as e:
            print(f"❌ Sheet read error: {e}")
            return False

        smap = get_station_map(sheet, matrix)

        def get_current(r, c):
            try:
                return matrix[r - 1][c - 1]
            except Exception:
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
                v = _to_float(val)
                if v is None or fld not in PRS_COLS or not _is_field_allowed(v, fld):
                    continue
                col = PRS_COLS[fld]
                if is_cell_empty(get_current(row, col)):
                    queue(row, col, v)
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
                v = _to_float(val)
                if v is None or not _is_field_allowed(v, fld):
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
                    print(f"⏭️ UTS {st} {fld}: cell already filled")

        if updates:
            try:
                gs_retry(sheet.batch_update, updates)
                print(f"✅ Batch update successful ({len(updates)} cells)")
            except Exception as e:
                print(f"❌ Batch update failed: {e}")
                return False
    return True

# ==============================================
# OSOP UPDATE
# ==============================================
def osop_units(amount):
    """
    Amount ko 100 ke units me, 50 par round-off:
    1-150 -> 1, 151-250 -> 2, 251-350 -> 3 ... (kam se kam 1).
    """
    a = _clean_num(amount)
    if a is None or a <= 0:
        return None
    return max(1, math.ceil((a - 50) / 100))

def update_osop_sheet(entries):
    if not entries:
        return True

    with file_lock(OSOP_LOCK_FILE):
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
                matrix = gs_retry(ws.get_all_values)
            except Exception as ex:
                print(f"❌ OSOP read error: {ex}")
                continue

            if len(matrix) < 6:
                continue

            def get_current(r, c):
                try:
                    return matrix[r - 1][c - 1]
                except Exception:
                    return ""

            row5 = matrix[4] if len(matrix) > 4 else []
            date_cols = {}
            c = 3
            max_cols = max(len(row5), 40)
            while c <= max_cols:
                raw = row5[c - 1] if c - 1 < len(row5) else ""
                if not str(raw).strip() and c < len(row5):
                    raw = row5[c]
                d = parse_date_flexible(raw)
                if d:
                    date_cols[d] = (c, c + 1)
                c += 2

            if not date_cols:
                print("⚠️ OSOP: row 5 me date columns nahi mile")
                continue

            station_rows = {}
            for r in range(6, len(matrix) + 1):
                cell = matrix[r - 1][1] if len(matrix[r - 1]) > 1 else ""
                if not str(cell).strip():
                    continue
                code = resolve_station(cell, quiet=True)
                if code:
                    station_rows.setdefault(code, []).append(r)

            code = e.get("station")
            if code not in station_rows:
                print(f"⚠️ OSOP: station '{code}' sheet me nahi mila")
                continue

            rows = station_rows[code]
            d = parse_date_flexible(e.get("date")) or ist_now().date()
            if d not in date_cols:
                print(f"⚠️ OSOP: date {d} sheet me nahi mili")
                continue

            camt, cunit = date_cols[d]

            amt = _clean_num(e.get("amount"))

            # same station + date + same amount pehle se likha hai to dobara nahi
            dup = False
            if amt is not None:
                for r in rows:
                    cur = _clean_num(get_current(r, camt))
                    if cur is not None and abs(cur - amt) < 0.005:
                        dup = True
                        break
            if dup:
                print(f"⏭️ OSOP {code} {d}: duplicate (amount {amt} already hai)")
                continue

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

            if amt is not None and amt != 0:
                if is_cell_empty(get_current(row, camt)):
                    updates.append({"range": rowcol_to_a1(row, camt), "values": [[amt]]})

            unit = _clean_num(e.get("unit"))
            if unit is None:
                unit = osop_units(amt)
            if unit is not None:
                if is_cell_empty(get_current(row, cunit)):
                    updates.append({"range": rowcol_to_a1(row, cunit), "values": [[unit]]})

            if updates:
                try:
                    gs_retry(ws.batch_update, updates)
                    print(f"✅ OSOP {code} {d}: written row {row}")
                except Exception as ex:
                    print(f"❌ OSOP write failed: {ex}")
    return True

# ==============================================
# IWOW UPDATE
# ==============================================
def _norm_str(v):
    return str(v or "").strip().upper()

def _iwow_key(to, commodity, wagons, ptime, pdate):
    """
    Duplicate pehchaan: station + commodity + wagons + placement time + date.
    Line / party / from / wagon type key me nahi hain (Gemini har baar alag likh sakta hai).
    """
    w = _clean_num(wagons)
    return (_norm_str(to), _norm_str(abbreviate_commodity(commodity)),
            int(w) if w is not None else "",
            ptime.strftime("%H:%M") if ptime else "",
            pdate.isoformat() if pdate else "")

def _key_str(key):
    return "|".join(str(x) for x in key)

def _load_recent():
    try:
        with open(IWOW_RECENT_FILE) as f:
            d = json.load(f)
    except Exception:
        return {}
    cutoff = time.time() - IWOW_DEDUPE_MINUTES * 60
    return {k: t for k, t in d.items() if isinstance(t, (int, float)) and t >= cutoff}

def _save_recent(d):
    try:
        tmp = IWOW_RECENT_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(d, f)
        os.replace(tmp, IWOW_RECENT_FILE)
    except Exception as e:
        print(f"⚠️ recent-log save failed: {e}")

def update_iwow_sheet(entries):
    if not entries:
        return True

    with file_lock(IWOW_LOCK_FILE):
        sh = get_spreadsheet()
        if not sh:
            return False

        try:
            ws = sh.worksheet("IWOW")
        except gspread.WorksheetNotFound:
            print("❌ 'IWOW' worksheet nahi mili")
            return False

        try:
            try:
                # unformatted: date/time ka display format ya locale kuch bhi ho, compare sahi rahega
                matrix = gs_retry(ws.get_all_values, value_render_option="UNFORMATTED_VALUE")
            except TypeError:
                matrix = gs_retry(ws.get_all_values)
        except Exception as e:
            print(f"❌ IWOW read error: {e}")
            return False

        def cell(r, c):
            try:
                return matrix[r - 1][c - 1]
            except Exception:
                return ""

        def row_is_free(r):
            return all(is_cell_empty(cell(r, c)) for c in IWOW_CORE_COLS)

        # pehli bilkul khaali row (kisi maujooda data par kabhi overwrite nahi)
        current_row = 4
        while current_row <= len(matrix) and not row_is_free(current_row):
            current_row += 1

        now = ist_now()
        today = now.date()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)
        grace_cutoff = dt_time(IWOW_GRACE_HOUR, 0)

        print(f"🕐 IWOW now (IST): {now.strftime('%Y-%m-%d %H:%M')} | grace_cutoff={grace_cutoff} | first free row={current_row}")

        # sheet me pehle se maujood entries
        existing = set()
        for r in range(4, len(matrix) + 1):
            if is_cell_empty(cell(r, 2)):
                continue
            existing.add(_iwow_key(cell(r, 2), cell(r, 5), cell(r, 6),
                                   parse_time_flexible(cell(r, 11)), parse_date_flexible(cell(r, 12))))
        recent = _load_recent()
        pending = []
        updates = []

        for e in entries:
            if not isinstance(e, dict):
                continue

            from_stn = _norm_str(e.get("from_stn"))
            to_stn = _norm_str(e.get("to_stn"))
            wagons = _clean_num(e.get("wagons"))
            ptime = parse_time_flexible(e.get("placement_time"))
            pdate = parse_date_flexible(e.get("placement_date"))
            commodity = abbreviate_commodity(e.get("commodity"))
            line = _norm_line(e.get("line"))
            party = _norm_str(e.get("party"))
            wtype = _norm_str(e.get("wagon_type"))

            if not to_stn:
                print("⏭️ Missing to_stn → skip")
                continue

            # date likhi na ho to: time aage ka ho to kal ka, warna aaj ka
            if not pdate:
                if ptime and datetime.combine(today, ptime) > now + timedelta(minutes=5):
                    pdate = yesterday
                else:
                    pdate = today

            print(f"🔎 {from_stn}→{to_stn} | date={pdate} time={ptime} wagons={wagons} line={line} commodity={commodity}")

            accept = False
            reason = ""

            if pdate == today:
                if ptime and datetime.combine(pdate, ptime) > now + timedelta(minutes=5):
                    reason = f"future time {ptime.strftime('%H:%M')} (now {now.strftime('%H:%M')})"
                else:
                    accept = True
            elif pdate == yesterday:
                if ptime and ptime >= dt_time(22, 0) and now.time() < grace_cutoff:
                    accept = True
                elif not ptime:
                    reason = "yesterday without time"
                elif ptime < dt_time(22, 0):
                    reason = f"yesterday pre-22:00 ({ptime.strftime('%H:%M')})"
                else:
                    reason = f"yesterday 22:00+ but grace passed (now {now.strftime('%H:%M')})"
            elif pdate == tomorrow:
                if ptime and datetime.combine(pdate, ptime) <= now + timedelta(minutes=30):
                    accept = True
                else:
                    reason = "tomorrow pre-report"
            else:
                reason = f"date out of range ({pdate})"

            if not accept:
                print(f"⏭️ Rejected ({reason})")
                continue

            if _is_container(commodity, wtype):
                commodity = "CONTAINER"
                if not wtype:
                    wtype = "CONTAINER"

            key = _iwow_key(to_stn, commodity, wagons, ptime, pdate)
            ks = _key_str(key)
            if key in existing:
                print(f"⏭️ Duplicate — sheet me pehle se hai ({ks})")
                continue
            if ks in recent:
                print(f"⏭️ Duplicate — abhi hi process ho chuka ({ks})")
                continue
            existing.add(key)

            ftime = iwow_free_time(wagons, commodity, wtype)

            if not wtype:
                if "NAPHTHA" in commodity:
                    wtype = "BTPN"
                elif "COAL" in commodity:
                    wtype = "BOXN"
                else:
                    wtype = "BCN"

            arrival_time_str = ""
            arrival_date_str = pdate.strftime("%d-%m-%Y")
            ptime_str = ptime.strftime("%H:%M") if ptime else ""
            pdate_str = pdate.strftime("%d-%m-%Y")

            if ptime:
                delta = random.choice([25, 30, 35, 40])
                arrival_dt = datetime.combine(pdate, ptime) - timedelta(minutes=delta)
                arrival_time_str = arrival_dt.strftime("%H:%M")
                arrival_date_str = arrival_dt.strftime("%d-%m-%Y")

            # agli bilkul khaali row par hi likho
            while current_row <= len(matrix) and not row_is_free(current_row):
                current_row += 1

            def q(col, val):
                if val is not None and str(val).strip() != "":
                    updates.append({"range": rowcol_to_a1(current_row, col), "values": [[val]]})

            q(2, to_stn); q(3, line); q(4, wtype); q(5, commodity)
            q(6, wagons); q(8, wagons)
            q(9, arrival_time_str); q(10, arrival_date_str)
            q(11, ptime_str); q(12, pdate_str)
            q(18, ftime); q(21, from_stn); q(23, party)

            pending.append(ks)
            print(f"✅ IWOW row {current_row}: {from_stn}→{to_stn} | wagons={wagons} | line={line} | {commodity} | free={ftime}")
            current_row += 1

        if updates:
            try:
                need = current_row + 2
                if need > ws.row_count:           # grid se bahar likhne par error aata hai
                    gs_retry(ws.add_rows, need - ws.row_count + 20)
                gs_retry(ws.batch_update, updates)
                print(f"✅ IWOW batch update successful ({len(updates)} cells)")
            except Exception as e:
                print(f"❌ IWOW batch update failed: {e}")
                return False
            now_ts = time.time()
            for ks in pending:
                recent[ks] = now_ts
            _save_recent(recent)
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

    if not _has_content(data):
        print("⚠️ Gemini empty/failed → regex fallback try")
        fb = _parse_kv_fallback(body, hint)
        if fb:
            data = fb

    data = apply_post_processing(data or {"prs": {}, "uts": {}, "osop": [], "goods": []}, body, hint)
    data = apply_fallback_fixes(data, body)

    if not _has_content(data):
        print("❌ Extraction failed — kuch nahi mila")
        return
    print("✅ Final Data:", json.dumps(data, default=str))

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
    if mode == "subscribe" and challenge and VERIFY_TOKEN and token == VERIFY_TOKEN:
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
                    if already_processed(m.get("id", "")):
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
    print(f"CREDENTIALS     : {bool(GOOGLE_CREDENTIALS_STR or GOOGLE_CREDENTIALS_B64)}")
    print(f"IWOW_GRACE_HOUR : {IWOW_GRACE_HOUR}:00 IST")
    print(f"IST_NOW         : {ist_now().strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        s = get_sheet()
        if s:
            print(f"✅ Google Sheet connected: tab '{s.title}'")
    except Exception as e:
        print(f"⚠️ Startup sheet check failed: {e}")
    print("===================================")

startup_check()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
