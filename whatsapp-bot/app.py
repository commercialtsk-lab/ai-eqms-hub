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
from concurrent.futures import ThreadPoolExecutor
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
GEMINI_THINK_FAST = int(os.environ.get("GEMINI_THINK_FAST", "0"))
GEMINI_THINK_DEEP = int(os.environ.get("GEMINI_THINK_DEEP", "2048"))
GEMINI_PARALLEL = int(os.environ.get("GEMINI_PARALLEL", "4"))
COVERAGE_MIN = float(os.environ.get("COVERAGE_MIN", "0.55"))  # slightly more tolerant
SEND_REPLY = os.environ.get("SEND_REPLY", "1") != "0"

SHEET_LOCK_FILE = "/tmp/sheet_update.lock"
OSOP_LOCK_FILE = "/tmp/osop_update.lock"
IWOW_LOCK_FILE = "/tmp/iwow_update.lock"
IWOW_GRACE_HOUR = int(os.environ.get("IWOW_GRACE_HOUR", "2"))
IWOW_RECENT_FILE = os.environ.get("IWOW_RECENT_FILE", "/tmp/iwow_recent.json")
IWOW_DEDUPE_MINUTES = int(os.environ.get("IWOW_DEDUPE_MINUTES", "120"))
IWOW_CORE_COLS = (2, 5, 6, 11, 12)

PROCESS_LOCK = threading.Lock()

# ==============================================
# STATION ALIASES (unchanged + robust)
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
# COMMODITY / FREE TIME (unchanged)
# ==============================================
def abbreviate_commodity(comm):
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
    if has_rice and has_fci: return "FCI/R"
    if has_wheat and has_fci: return "FCI/W"
    if has_rice and has_pub: return "PUB/R"
    if has_wheat and has_pub: return "PUB/W"
    if has_rice: return "RICE"
    if has_wheat: return "WHEAT"
    if has_fci: return "FCI"
    if has_pub: return "PUB"
    return c

def _is_container(commodity, wtype):
    tokens = set(re.split(r'[^A-Z0-9]+', str(wtype or "").upper()))
    return "CONTAINER" in str(commodity or "").upper() or "CONTAINER" in str(wtype or "").upper() \
        or bool(tokens & CONTAINER_WAGON_CODES)

def iwow_free_time(wagons, commodity="", wtype=""):
    try:
        w = int(float(wagons)) if wagons not in (None, "") else 42
    except Exception:
        w = 42
    if w >= 46: return "11 HRS"
    c = str(commodity or "").upper()
    if "NAPHTHA" in c or "NAPTHA" in c: return "8 HRS"
    if _is_container(c, wtype): return "3 HRS"
    if w <= 20: return "5 HRS"
    if w <= 30: return "7 HRS"
    return "9 HRS"

# ==============================================
# STATION RESOLUTION
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
# META RETRY PROTECTION + LOCKS
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
# CREDENTIALS + SHEETS
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

_GC = None
_GC_TIME = 0.0
_GC_LOCK = threading.RLock()

def _get_gc(force=False):
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

_SH = None
_SH_TIME = 0.0
_WS_CACHE = {}

def reset_caches():
    global _GC, _SH, _SH_TIME
    with _GC_LOCK:
        _GC = None
        _SH = None
        _SH_TIME = 0.0
        _WS_CACHE.clear()

def get_spreadsheet():
    global _SH, _SH_TIME
    try:
        with _GC_LOCK:
            if _SH is not None and time.time() - _SH_TIME < 2700:
                return _SH
            gc = _get_gc()
            if not gc:
                return None
            try:
                sh = gs_retry(gc.open, SHEET_NAME)
            except Exception:
                gc = _get_gc(force=True)
                if not gc:
                    return None
                sh = gs_retry(gc.open, SHEET_NAME)
            _SH, _SH_TIME = sh, time.time()
            _WS_CACHE.clear()
            return sh
    except Exception as e:
        print(f"❌ Google Sheet Connection Error: {e}")
        return None

def get_ws(sh, name):
    w = _WS_CACHE.get(name)
    if w is None:
        w = gs_retry(sh.worksheet, name)
        _WS_CACHE[name] = w
    return w

def get_sheet():
    sh = get_spreadsheet()
    if not sh:
        return None
    try:
        return get_ws(sh, "UTS&PRS")
    except gspread.WorksheetNotFound:
        print("⚠️ 'UTS&PRS' tab nahi mili → sheet1 use kar rahe hain")
        return sh.sheet1
    except Exception as e:
        print(f"❌ Worksheet error: {e}")
        reset_caches()
        return None

def get_station_map(sheet, all_values=None):
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
    for i in range(6, min(36, len(all_values))):
        add(all_values[i][1] if len(all_values[i]) > 1 else "", i + 1, "B")
    for i in range(30, min(47, len(all_values))):
        add(all_values[i][12] if len(all_values[i]) > 12 else "", i + 1, "M")
    for i in range(31, min(48, len(all_values))):
        add(all_values[i][2] if len(all_values[i]) > 2 else "", i + 1, "C")
    print(f"✅ Station map ready: {len(m)} keys")
    return m

# ==============================================
# DATE / TIME / NUMBER HELPERS
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
    if isinstance(s, (int, float)):
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
    if s is None:
        return None
    if isinstance(s, dt_time):
        return s
    if isinstance(s, bool):
        return None
    if isinstance(s, float) and 0 <= s < 1:
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

def _to_float(s):
    try:
        return float(str(s).replace(",", "").strip())
    except Exception:
        return None

def _clean_num(v):
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
# MESSAGE NORMALIZATION (new – handles garbled paste)
# ==============================================
def normalize_message(text):
    """Make squished / messy WhatsApp text easier for both Gemini and regex."""
    if not text:
        return ""
    text = (text
            .replace("\u200e", "").replace("\u200f", "")
            .replace("\u202f", " ").replace("\u00a0", " ")
            .replace("\r\n", "\n").replace("\r", "\n"))
    # Un-squash common patterns: 272AOUNT → 272 AOUNT, 13AMOUNT → 13 AMOUNT
    text = re.sub(r'(\d)([A-Za-z])', r'\1 \2', text)
    text = re.sub(r'([A-Za-z])(\d)', r'\1 \2', text)
    # Common OCR / typing noise
    text = re.sub(r'\bAOUNT\b', 'AMOUNT', text, flags=re.I)
    text = re.sub(r'\bAMONT\b', 'AMOUNT', text, flags=re.I)
    text = re.sub(r'\bJENNY\b', 'JENNY', text, flags=re.I)
    # Collapse multiple spaces but keep newlines
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

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
    text = normalize_message(text or "")
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
    # Strong heading patterns first
    for pat in [
        r'(?:EARNINGS?|REVENUE|REPORT|DATA)\s+(?:OF\s+)?([A-Z]{2,6})\b',
        r'\b(?:PRS|UTS)\s*/\s*([A-Z]{2,6})\b',
        r'\b(?:PRS|UTS)\s*[:\-]?\s*([A-Z]{2,6})\b',
    ]:
        m = re.search(pat, body, re.I)
        if m:
            code = resolve_station(m.group(1), quiet=True)
            if code:
                return code
    found = _find_stations_in_text(body)
    if len(found) == 1:
        return next(iter(found))
    if not found:
        s = _find_stations_in_text(sender)
        if len(s) == 1:
            return next(iter(s))
    return None

# ==============================================
# GEMINI PROMPT (slightly clarified for natural understanding)
# ==============================================
PROMPT_TEMPLATE = r"""You are an expert Indian Railway data extraction engine for the Tinsukia Division.
You read WhatsApp messages like a seasoned railway accountant — messy formats, broken lines, Hinglish, typos, garbled paste, squished text, merged words ("272AOUNT"), copied/forwarded chat text, random spacing, mixed labels, missing separators. You understand naturally, the way a human who has done this job for years does. Trust your own judgement and extract EVERYTHING that is really present. Never invent numbers that are not in the message.

Return ONE JSON object with these keys (all present, empty if nothing found):
  "prs"   : { "<STATION_CODE>": { "TKT":num, "PASS":num, "C/TKT":num, "C/PASS":num, "REF":num, "NET":num, "VCH":num, "POS":num, "UPI":num } }
  "uts"   : { "<STATION_CODE>": { "PF":num, "TKT":num, "PASS":num, "NET":num, "MR":num, "MR AMT":num, "UPI":num } }
  "osop"  : [ { "station":"CODE", "date":"as written", "amount":num, "unit":num or omit } ]
  "goods" : [ { "from_stn":"CODE", "to_stn":"CODE", "wagons":num, "placement_time":"HH:MM", "placement_date":"as written", "commodity":"ABBREVIATED UPPERCASE", "line":"number or comma list", "party":"UPPERCASE", "wagon_type":"optional", "weight":num or omit, "freight":num or omit } ]

=== CONTEXT ===
__CTX__
STATION HINT (use ONLY if the message text itself names no station): __HINT__
The message may begin with chat-export noise like "[04/11, 7:03 pm] Name:" — ignore it. Sender names/designations (Sr CTC, SM, SS, Pradip Mishra) are NOT data.
One message can contain several things at once (PRS + UTS + OSOP + goods, or several stations, or several forwarded reports pasted one after another). Extract all of them.

=== OFFICIAL STATIONS (CODE = Full Name) ===
__LEGEND__
Always output the CODE, never the full name. Fix spelling mistakes and short forms yourself (Kown/Khowang → KOWN, Krht → KRHT). Headings like "Earnings Of NTSK", "REVENUE OF BFD", "PRS/NTSK", "UTS/NTSK" tell you the station and the section.

=== PRS / UTS READING GUIDE ===
- Normally ONE station's daily revenue report. Station key = CODE (from the text or from STATION HINT). Multi-station bundles are possible → one key per station.
- Lines under a "UTS" heading → "uts". Lines under a "PRS" heading → "prs". Headings can look like "PRS", "PRS/NTSK", "PRS :", "UTS REPORT". If the message has NO UTS/PRS label at all (small stations) → treat as UTS.
- Field meanings (people write them in many ways; a leading "T/" means Total, e.g. T/TKT = total tickets):
    TKT   : TKT / Tkts / Tckt / Ticket / T / T/TKT / J/TKT
    PASS  : PASS / Psg / Psgr / Passenger / P (when it sits beside T) / T/Pass / J/Pass
    NET   : NET CASH / Netcash / Net / Cash / Cash amount / J/Amount  — the cash collection amount (never the grand total)
    UPI   : E CASH / E/CASH / Ecash / E-cash / E cas / Digi cash / Digital cash / UPI / UPI QR / QR / Digital / Paytm / PhonePe
    REF   : REFUND / RFD / Digi ref / Digital refund / Digi refund / Digi RFD / Digital RFD — SUM OF ALL refund-type amounts found anywhere in the message. If multiple refund lines exist (e.g. REFUND 500 + Digi ref 200 + RFD 100), put the TOTAL (800) in REF. Never take only the first one.
    C/TKT, C/PASS : cancelled tickets / cancelled passengers (PRS)
    VCH, POS : vouchers / POS-machine amount (PRS)
    PF    : platform tickets COUNT (PF / P/TKT / PLT / PLATFORM / "M"). A platform AMOUNT next to it has no column → ignore it.
    MR / MR AMT : MR count / MR amount (both captured). "MR=13AMOUNT=37960" → MR 13, MR AMT 37960.
- "Jenny" / "JTBS" lines (e.g. "T/jenny 1132") are only a sub-count of tickets already included in the total → ignore them, never add them to TKT.
- "Ttl" / "Total" / "Grand total" lines are totals → IGNORE (never put them in NET or anywhere).
- Nil / Nill / NIL / - / blank / "nill .." → omit that key.
- Date lines like "DATE. 04/11/2026" or "Date:06/11/26" → ignore (not a field).
- Numbers must be plain numbers (remove commas, Rs, /-, spaces).
- Missing → omit key. If a label is unusual or misspelt, decide by meaning and position, like a human accountant would. A number must go to exactly one field.

PRS/UTS EXAMPLES:
Input: "REVENUE OF BFD\nDATE.     04/11/2026\nUTS\nTKT                  200\nPASS.               333\nNET CASH.    10485\nE CASH.          1230\n\nPRS\nTKT                 9\nPASS.              20\nNET CASH.    28060\nUPI QR .          10025\nREFUND.          Nill\nC/TKT.              Nill\nC/PASS.            Nill\nDigi ref:-            nill  .."
Output: {"prs":{"BFD":{"TKT":9,"PASS":20,"NET":28060,"UPI":10025}},"uts":{"BFD":{"TKT":200,"PASS":333,"NET":10485,"UPI":1230}},"osop":[],"goods":[]}

Input: "Kown 4/11/26\nPsg-9\nTckt-7\nCash-20\nEcash-400"
Output: {"prs":{},"uts":{"KOWN":{"TKT":7,"PASS":9,"NET":20,"UPI":400}},"osop":[],"goods":[]}

Input: "Krht uts of 4.11.2026\nT 36\nP 58\nCash 1390\nE cas 340\nTtl 1730 only"
Output: {"prs":{},"uts":{"KRHT":{"TKT":36,"PASS":58,"NET":1390,"UPI":340}},"osop":[],"goods":[]}

Input: "Earnings Of NTSK \nDate:06/11/26\nPRS/NTSK \nT/TKT =81\nT/Pass =78\nC/TKT =04\nC/Pass =09\nRFD =6020\nNetcash =31580\nDigi CASH =56950\nDigi RFD =Nil\nVch=Nil\n\nUTS/NTSK \nT/jenny1132\nT/TKT =1429\nT/Pass =1651\nP/TKT =272AOUNT =2720\nMR=13AMOUNT=37960\nE/CASH =52145\nJ/AMOUNT =338765 "
Output: {"prs":{"NTSK":{"TKT":81,"PASS":78,"C/TKT":4,"C/PASS":9,"REF":6020,"NET":31580,"UPI":56950}},"uts":{"NTSK":{"TKT":1429,"PASS":1651,"PF":272,"MR":13,"MR AMT":37960,"UPI":52145,"NET":338765}},"osop":[],"goods":[]}

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

MESSAGE (between the tags):
<message>
__MSG__
</message>

JSON only, no markdown:"""

_GEMINI_SEM = threading.Semaphore(GEMINI_PARALLEL)

def _gemini_post(prompt, thinking=0):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    gen = {"temperature": 0, "maxOutputTokens": 8192, "responseMimeType": "application/json"}
    if "2.5" in GEMINI_MODEL:
        gen["thinkingConfig"] = {"thinkingBudget": thinking}
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen}
    err = ""
    for attempt in range(5):
        try:
            with _GEMINI_SEM:
                res = requests.post(url, json=payload, headers=headers, timeout=90)
            if res.status_code == 200:
                return res.json(), ""
            err = f"HTTP {res.status_code}: {res.text[:160]}"
            print(f"❌ Gemini {err}")
            if res.status_code not in (429, 500, 502, 503, 504):
                return None, err
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            print(f"❌ Gemini Error: {err}")
        time.sleep(min(2 ** attempt, 16) + random.random())
    return None, err

def _parse_gemini_json(txt):
    txt = re.sub(r'```json\n?', '', txt or "", flags=re.IGNORECASE)
    txt = re.sub(r'```\n?', '', txt).strip()
    match = re.search(r'\{[\s\S]*\}', txt)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
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

def call_gemini(msg, sender="", ts="", hint=None, thinking=0):
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY missing!")
        return None, "GEMINI_API_KEY set nahi hai"
    station_legend = "\n".join(f'{c} = {STATION_OFFICIAL[c]}' for c in ALL_STATIONS)
    hint_line = (f"{hint} ({STATION_OFFICIAL.get(hint, '')})" if hint else "none")
    ctx_line = (f"Sender name: {sender or 'unknown'} | Message time: {ts or 'unknown'} | "
                f"Now (IST): {ist_now().strftime('%d/%m/%Y %H:%M')}")
    prompt = (PROMPT_TEMPLATE
              .replace("__CTX__", ctx_line)
              .replace("__HINT__", hint_line)
              .replace("__LEGEND__", station_legend)
              .replace("__MSG__", msg))
    err = ""
    for attempt in range(2):
        resp, err = _gemini_post(prompt, thinking)
        if not resp:
            return None, err
        try:
            parts = resp["candidates"][0]["content"]["parts"]
            txt = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            parsed = _parse_gemini_json(txt)
            if parsed is not None:
                return parsed, ""
            err = "Gemini ne JSON nahi diya"
            print(f"⚠️ {err}")
        except Exception as e:
            err = f"Gemini response parse error: {e}"
            print(f"⚠️ {err}")
        time.sleep(1.0)
    return None, err

# ==============================================
# POST-PROCESSING + FALLBACKS
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
            out[f] = out[f] + n
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
    # UTS/PRS label correction
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

# Regex fallback (already excellent for this message)
_FIELD_PATTERNS = [
    ("C/TKT",  r'^(C\s*/?\s*(TKT|TCKT|TICKET)S?|CANCEL\w*\s*(TKT|TCKT|TICKET)\w*)$'),
    ("C/PASS", r'^(C\s*/?\s*(PASS|PSG|PSGR)\w*|CANCEL\w*\s*(PASS|PSG)\w*)$'),
    ("REF",    r'^(REF|RFD|REFUND|DIGI(TAL)?\s*(REF\w*|RFD))$'),
    ("VCH",    r'^(VCH|VOUCHERS?)$'),
    ("POS",    r'^POS$'),
    ("MR AMT", r'^MR\s*(AMT|AMOUNT)$'),
    ("MR",     r'^MR$'),
    ("UPI",    r'^(E\s*/?\s*CAS\w*|ECAS\w*|DIGI(TAL)?\s*CASH|UPI.*|QR.*|DIGITAL.*|PAYTM|PHONEPE)$'),
    ("NET",    r'^(NET\s*CASH|NETCASH|NET|CASH|NET\s*AMOUNT|J\s*/?\s*(AMOUNT|AMT))$'),
    ("PF",     r'^(PF|PLATFORM|PLT|P\s*/?\s*TKT|PF\s*/?\s*TKT)$'),
    ("PASS",   r'^(T\s*/?\s*(PASS|PSG|PSGR)\w*|PASS\w*|PSGR?|P|J\s*/?\s*PASS)$'),
    ("TKT",    r'^(T\s*/?\s*(TKT|TCKT|TICKET)S?|TKTS?|TCKTS?|TICKETS?|T|J\s*/?\s*TKT)$'),
]

_KV_PAIR_RE = re.compile(r'([A-Za-z][A-Za-z/ .&]*?)\s*[=:\-]*\s*(-?\d[\d,]*(?:\.\d+)?)')

def _clean_label(label):
    lab = re.sub(r'[^A-Z/ ]', '', str(label).upper())
    return re.sub(r'\s+', ' ', lab).strip()

def _label_to_field(label):
    lab = _clean_label(label)
    for fld, pat in _FIELD_PATTERNS:
        if re.match(pat, lab):
            return fld
    return None

def _is_amount_word(label):
    return bool(re.fullmatch(r'AM?O?U?N?T', _clean_label(label)))

def _line_fields(line):
    out = []
    prev = None
    for m in _KV_PAIR_RE.finditer(line):
        label, raw = m.group(1), m.group(2)
        num = _to_float(raw)
        if num is None:
            continue
        if _is_amount_word(label):
            if prev == "MR":
                out.append(("MR AMT", num))
            prev = None
            continue
        fld = _label_to_field(label)
        if fld:
            out.append((fld, num))
        prev = fld
    return out

def _parse_kv_fallback(body, hint=None):
    cur = hint
    section = None
    res = {"prs": {}, "uts": {}}
    for line in str(body or "").splitlines():
        L = line.strip()
        if not L:
            continue
        sec_m = re.search(r'\b(UTS|PRS)\b', L, re.IGNORECASE)
        stns = _find_stations_in_text(L)
        fields = _line_fields(L)
        if sec_m:
            section = sec_m.group(1).lower()
        if len(stns) == 1 and not fields:
            new = next(iter(stns))
            if new != cur and not sec_m:
                section = None
            cur = new
        if fields and cur is None and len(stns) == 1:
            cur = next(iter(stns))
        if not fields or not cur:
            continue
        for fld, num in fields:
            kind = "prs" if fld in PRS_ONLY_FIELDS else (section or "uts")
            d = res[kind].setdefault(cur, {})
            if fld == "REF":
                d["REF"] = d.get("REF", 0) + num
            else:
                d.setdefault(fld, num)
    out = {"prs": {}, "uts": {}, "osop": [], "goods": []}
    for kind in ("prs", "uts"):
        for st, f in res[kind].items():
            if f:
                out[kind][st] = f
    if not out["prs"] and not out["uts"]:
        return None
    print(f"🔧 Regex KV fallback: {out}")
    return out

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
    if data is None:
        data = {"prs": {}, "uts": {}, "osop": [], "goods": []}
    up = msg.upper()
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
    gem_goods = data.get("goods") or []
    if gem_goods:
        data["goods"] = _merge_goods(gem_goods)
    else:
        data["goods"] = _parse_goods_regex(msg)
    return data

# ==============================================
# SHEET UPDATE FUNCTIONS (unchanged logic, clearer reporting)
# ==============================================
def is_cell_empty(value):
    if value is None:
        return True
    s = str(value).strip().replace(",", "").replace(" ", "").replace("₹", "")
    if s in ("", "-", "0", "0.0", "0.00"):
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

def _fmt_num(v):
    n = _clean_num(v)
    return str(n) if n is not None else str(v)

def update_google_sheet(data):
    lines = []
    with file_lock(SHEET_LOCK_FILE):
        sheet = get_sheet()
        if not sheet:
            return False, ["❌ Google Sheet connect nahi ho payi (credentials/sheet name check karein)"]
        try:
            matrix = gs_retry(sheet.get_all_values)
        except Exception as e:
            print(f"❌ Sheet read error: {e}")
            reset_caches()
            return False, [f"❌ Sheet read error: {e}"]
        smap = get_station_map(sheet, matrix)
        def get_current(r, c):
            try:
                return matrix[r - 1][c - 1]
            except Exception:
                return ""
        updates = []
        queued = set()
        written, same = {}, {}
        def queue(r, c, val):
            key = (r, c)
            if key in queued:
                return False
            queued.add(key)
            updates.append({"range": rowcol_to_a1(r, c), "values": [[val]]})
            return True
        for kind, cols in (("prs", PRS_COLS), ("uts", UTS_COLS_NU)):
            for st, vals in data.get(kind, {}).items():
                info = smap.get(st)
                if not info:
                    lines.append(f"❌ {kind.upper()} {st}: sheet me station ki row nahi mili (B7:B36 me naam/code check karein)")
                    continue
                if not _has_any_nonzero(vals):
                    continue
                row = info["row"]
                for fld, val in (vals or {}).items():
                    v = _to_float(val)
                    if v is None or not _is_field_allowed(v, fld):
                        continue
                    if kind == "uts" and info["nameCol"] == "C":
                        col = {"TKT": 4, "PASS": 5, "NET": 9, "UPI": 12, "PF": 8, "MR": 19, "MR AMT": 20}.get(fld)
                    else:
                        col = cols.get(fld)
                    if not col:
                        continue
                    cur = get_current(row, col)
                    tag = (kind.upper(), st)
                    if is_cell_empty(cur):
                        if queue(row, col, v):
                            written.setdefault(tag, []).append(fld)
                            print(f"✅ {kind.upper()} {st} {fld}: wrote {v}")
                    else:
                        cv = _clean_num(cur)
                        if cv is not None and abs(cv - v) < 0.005:
                            same.setdefault(tag, []).append(fld)
                        else:
                            lines.append(f"⚠️ {kind.upper()} {st} {fld}: sheet me {cur} pehle se hai, naya {_fmt_num(v)} — overwrite nahi kiya")
                            print(f"⏭️ {kind.upper()} {st} {fld}: cell already filled ({cur})")
        if updates:
            try:
                gs_retry(sheet.batch_update, updates)
                print(f"✅ Batch update successful ({len(updates)} cells)")
            except Exception as e:
                print(f"❌ Batch update failed: {e}")
                reset_caches()
                return False, [f"❌ Sheet write fail: {e}"]
        out = []
        for (kind, st), flds in written.items():
            out.append(f"✅ {st} {kind}: {', '.join(flds)}")
        for (kind, st), flds in same.items():
            out.append(f"↩️ {st} {kind}: pehle se bhara (same value) — {', '.join(flds)}")
        return True, out + lines

def osop_units(amount):
    a = _clean_num(amount)
    if a is None or a <= 0:
        return None
    return max(1, math.ceil((a - 50) / 100))

def update_osop_sheet(entries):
    lines = []
    if not entries:
        return True, lines
    with file_lock(OSOP_LOCK_FILE):
        sh = get_spreadsheet()
        if not sh:
            return False, ["❌ OSOP: Google Sheet connect nahi ho payi"]
        try:
            ws = get_ws(sh, "OSOP")
        except gspread.WorksheetNotFound:
            print("❌ 'OSOP' worksheet nahi mili")
            return False, ["❌ 'OSOP' tab sheet me nahi mili"]
        except Exception as ex:
            reset_caches()
            return False, [f"❌ OSOP tab error: {ex}"]
        try:
            matrix = [list(r) for r in gs_retry(ws.get_all_values)]
        except Exception as ex:
            print(f"❌ OSOP read error: {ex}")
            reset_caches()
            return False, [f"❌ OSOP read error: {ex}"]
        if len(matrix) < 6:
            return False, ["❌ OSOP tab me header/station rows nahi mili"]
        def get_current(r, c):
            try:
                return matrix[r - 1][c - 1]
            except Exception:
                return ""
        def set_local(r, c, v):
            while len(matrix) < r:
                matrix.append([])
            row = matrix[r - 1]
            while len(row) < c:
                row.append("")
            row[c - 1] = v
        row5 = matrix[4]
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
            return False, ["❌ OSOP: row 5 me date columns nahi mile"]
        station_rows = {}
        for r in range(6, len(matrix) + 1):
            cell = matrix[r - 1][1] if len(matrix[r - 1]) > 1 else ""
            if not str(cell).strip():
                continue
            code = resolve_station(cell, quiet=True)
            if code:
                station_rows.setdefault(code, []).append(r)
        updates = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            code = e.get("station")
            d = parse_date_flexible(e.get("date")) or ist_now().date()
            label = f"OSOP {code} {d.strftime('%d/%m')}"
            if code not in station_rows:
                lines.append(f"❌ {label}: sheet me station nahi mila")
                continue
            if d not in date_cols:
                lines.append(f"❌ {label}: row 5 me ye date nahi hai")
                continue
            rows = station_rows[code]
            camt, cunit = date_cols[d]
            amt = _clean_num(e.get("amount"))
            dup = False
            if amt is not None:
                for r in rows:
                    cur = _clean_num(get_current(r, camt))
                    if cur is not None and abs(cur - amt) < 0.005:
                        dup = True
                        break
            if dup:
                lines.append(f"↩️ {label}: {amt} pehle se likha hai")
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
                lines.append(f"⚠️ {label}: cells pehle se bhare hain — overwrite nahi kiya")
                continue
            row = chosen_row
            unit = _clean_num(e.get("unit"))
            if unit is None:
                unit = osop_units(amt)
            wrote = []
            if amt is not None and amt != 0 and is_cell_empty(get_current(row, camt)):
                updates.append({"range": rowcol_to_a1(row, camt), "values": [[amt]]})
                set_local(row, camt, amt)
                wrote.append(f"₹{amt}")
            if unit is not None and is_cell_empty(get_current(row, cunit)):
                updates.append({"range": rowcol_to_a1(row, cunit), "values": [[unit]]})
                set_local(row, cunit, unit)
                wrote.append(f"unit {unit}")
            if wrote:
                lines.append(f"✅ {label}: {', '.join(wrote)}")
                print(f"✅ OSOP {code} {d}: row {row} {wrote}")
        if updates:
            try:
                gs_retry(ws.batch_update, updates)
            except Exception as ex:
                print(f"❌ OSOP write failed: {ex}")
                reset_caches()
                return False, lines + [f"❌ OSOP write fail: {ex}"]
    return True, lines

def _norm_str(v):
    return str(v or "").strip().upper()

def _iwow_key(to, commodity, wagons, ptime, pdate):
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
    lines = []
    if not entries:
        return True, lines
    with file_lock(IWOW_LOCK_FILE):
        sh = get_spreadsheet()
        if not sh:
            return False, ["❌ IWOW: Google Sheet connect nahi ho payi"]
        try:
            ws = get_ws(sh, "IWOW")
        except gspread.WorksheetNotFound:
            print("❌ 'IWOW' worksheet nahi mili")
            return False, ["❌ 'IWOW' tab sheet me nahi mili"]
        except Exception as ex:
            reset_caches()
            return False, [f"❌ IWOW tab error: {ex}"]
        try:
            try:
                matrix = gs_retry(ws.get_all_values, value_render_option="UNFORMATTED_VALUE")
            except TypeError:
                matrix = gs_retry(ws.get_all_values)
        except Exception as e:
            print(f"❌ IWOW read error: {e}")
            reset_caches()
            return False, [f"❌ IWOW read error: {e}"]
        def cell(r, c):
            try:
                return matrix[r - 1][c - 1]
            except Exception:
                return ""
        def row_is_free(r):
            return all(is_cell_empty(cell(r, c)) for c in IWOW_CORE_COLS)
        current_row = 4
        while current_row <= len(matrix) and not row_is_free(current_row):
            current_row += 1
        now = ist_now()
        today = now.date()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)
        grace_cutoff = dt_time(IWOW_GRACE_HOUR, 0)
        print(f"🕐 IWOW now (IST): {now.strftime('%Y-%m-%d %H:%M')} | grace_cutoff={grace_cutoff} | first free row={current_row}")
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
            label = f"IWOW {from_stn or '?'}→{to_stn or '?'} {wagons if wagons is not None else '?'}W {commodity}".strip()
            if not to_stn:
                lines.append(f"⏭️ {label}: station (to_stn) samajh nahi aaya")
                continue
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
                    reason = f"placement time {ptime.strftime('%H:%M')} abhi (IST {now.strftime('%H:%M')}) se aage ka hai"
                else:
                    accept = True
            elif pdate == yesterday:
                if ptime and ptime >= dt_time(22, 0) and now.time() < grace_cutoff:
                    accept = True
                elif not ptime:
                    reason = "kal ki date bina time ke"
                elif ptime < dt_time(22, 0):
                    reason = f"kal ki date, time {ptime.strftime('%H:%M')} (22:00 se pehle)"
                else:
                    reason = f"kal raat ka data, par grace time ({IWOW_GRACE_HOUR}:00 IST) nikal gaya"
            elif pdate == tomorrow:
                if ptime and datetime.combine(pdate, ptime) <= now + timedelta(minutes=30):
                    accept = True
                else:
                    reason = "agli date ka pre-report"
            else:
                reason = f"date range se bahar ({pdate.strftime('%d/%m/%Y')})"
            if not accept:
                print(f"⏭️ Rejected ({reason})")
                lines.append(f"⏭️ {label}: {reason}")
                continue
            if _is_container(commodity, wtype):
                commodity = "CONTAINER"
                if not wtype:
                    wtype = "CONTAINER"
            key = _iwow_key(to_stn, commodity, wagons, ptime, pdate)
            ks = _key_str(key)
            if key in existing:
                print(f"⏭️ Duplicate — sheet me pehle se hai ({ks})")
                lines.append(f"↩️ {label}: sheet me pehle se hai (duplicate nahi likha)")
                continue
            if ks in recent:
                print(f"⏭️ Duplicate — abhi hi process ho chuka ({ks})")
                lines.append(f"↩️ {label}: abhi hi process ho chuka (duplicate nahi likha)")
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
            lines.append(f"✅ {label} line {line or '-'} → row {current_row} (free {ftime})")
            print(f"✅ IWOW row {current_row}: {from_stn}→{to_stn} | wagons={wagons} | line={line} | {commodity} | free={ftime}")
            current_row += 1
        if updates:
            try:
                need = current_row + 2
                if need > ws.row_count:
                    gs_retry(ws.add_rows, need - ws.row_count + 20)
                gs_retry(ws.batch_update, updates)
                print(f"✅ IWOW batch update successful ({len(updates)} cells)")
            except Exception as e:
                print(f"❌ IWOW batch update failed: {e}")
                reset_caches()
                return False, [l for l in lines if not l.startswith("✅")] + [f"❌ IWOW write fail: {e}"]
            now_ts = time.time()
            for ks in pending:
                recent[ks] = now_ts
            _save_recent(recent)
    return True, lines

# ==============================================
# MESSAGE PIPELINE (improved merge of Gemini + regex)
# ==============================================
def _empty_data():
    return {"prs": {}, "uts": {}, "osop": [], "goods": []}

def _has_content(data):
    return bool(data and (data.get("prs") or data.get("uts") or data.get("osop") or data.get("goods")))

def merge_data(dst, src):
    for kind in ("prs", "uts"):
        for st, f in (src.get(kind) or {}).items():
            dst[kind].setdefault(st, {}).update(f)
    dst["osop"].extend(src.get("osop") or [])
    dst["goods"].extend(src.get("goods") or [])
    return dst

_DATE_RE = re.compile(r'\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b')
_TIME_RE = re.compile(r'\b\d{1,2}[:.]\d{2}\s*(?:[APap]\.?[Mm]\.?|hrs?|HRS?)?\b')

def _data_numbers(d):
    nums = []
    for kind in ("prs", "uts"):
        for f in (d.get(kind) or {}).values():
            nums.extend(v for v in f.values() if isinstance(v, (int, float)))
    for o in d.get("osop") or []:
        for k in ("amount", "unit"):
            n = _clean_num(o.get(k))
            if n is not None:
                nums.append(n)
    for g in d.get("goods") or []:
        for k in ("wagons", "weight", "freight"):
            n = _clean_num(g.get(k))
            if n is not None:
                nums.append(n)
    return nums

def _big_numbers(body):
    text = _DATE_RE.sub(" ", str(body or ""))
    text = _TIME_RE.sub(" ", text)
    toks = []
    for t in re.findall(r'\d[\d,]*(?:\.\d+)?', text):
        v = _to_float(t)
        if v is not None and len(re.sub(r'\D', '', t.split('.')[0])) >= 3:
            toks.append(v)
    return toks

def _looks_like_data(body):
    return bool(_big_numbers(body)) or bool(re.search(r'\b(WAGONS?|OSOP|UTS|PRS)\b', str(body or ""), re.I))

def coverage(d, body):
    toks = _big_numbers(body)
    if not toks:
        return 1.0
    have = _data_numbers(d)
    hit = sum(1 for t in toks if any(abs(t - h) < 0.005 for h in have))
    return hit / len(toks)

def _prepare(data, body, hint):
    d = apply_post_processing(data or _empty_data(), body, hint)
    return apply_fallback_fixes(d, body)

def _field_count(d):
    n = 0
    for kind in ("prs", "uts"):
        for f in (d.get(kind) or {}).values():
            n += len(f)
    n += len(d.get("osop") or [])
    n += len(d.get("goods") or [])
    return n

def extract_block(body, sender="", ts=""):
    print(f"\n📩 Block | sender='{sender}' | ts='{ts}'\n{body[:400]}")
    body = normalize_message(body)
    hint = guess_station_hint(body, sender)
    print(f"📍 Station hint: {hint}")
    notes = []

    raw1, err1 = call_gemini(body, sender, ts, hint, GEMINI_THINK_FAST)
    best = _prepare(raw1, body, hint) if raw1 else _empty_data()
    best_cov = coverage(best, body) if _has_content(best) else 0.0
    source = "gemini"
    if err1:
        notes.append(f"Gemini: {err1}")

    looks = _looks_like_data(body)
    if looks and best_cov < COVERAGE_MIN:
        print(f"🔁 Coverage {best_cov:.2f} kam — deep thinking se dobara")
        raw2, err2 = call_gemini(body, sender, ts, hint, GEMINI_THINK_DEEP)
        if raw2:
            d2 = _prepare(raw2, body, hint)
            c2 = coverage(d2, body) if _has_content(d2) else 0.0
            if c2 > best_cov or (c2 == best_cov and _field_count(d2) > _field_count(best)):
                best, best_cov, source = d2, c2, "gemini-deep"
        elif err2 and not err1:
            notes.append(f"Gemini: {err2}")

    # Always compute regex and take the richer / higher-coverage result (or fill gaps)
    fb = _parse_kv_fallback(body, hint)
    if fb:
        d3 = _prepare(fb, body, hint)
        c3 = coverage(d3, body) if _has_content(d3) else 0.0
        if c3 > best_cov or (c3 >= best_cov - 0.05 and _field_count(d3) > _field_count(best)):
            best, best_cov, source = d3, c3, "regex"
            notes.append("Regex fallback used / preferred (higher coverage or more fields)")
        else:
            # Merge any missing fields from regex into Gemini result
            for kind in ("prs", "uts"):
                for st, fields in (d3.get(kind) or {}).items():
                    if st not in best[kind]:
                        best[kind][st] = fields
                    else:
                        for k, v in fields.items():
                            if k not in best[kind][st]:
                                best[kind][st][k] = v

    if not _has_content(best):
        best = _prepare(None, body, hint)
    print(f"✅ Final ({source}, coverage {best_cov:.2f}, fields {_field_count(best)}):", json.dumps(best, default=str))
    return best, notes

def process_incoming(text):
    blocks = [b for b in split_chat_messages(text) if re.search(r'\d', b["body"])]
    print(f"📦 {len(blocks)} message block(s) mile")
    if not blocks:
        return "⚠️ Message me koi data (number) nahi mila."
    def work(b):
        try:
            return extract_block(b["body"], b["sender"], b["ts"])
        except Exception as e:
            print(f"❌ Block error: {e}")
            return _empty_data(), [f"Block error: {e}"]
    if len(blocks) == 1:
        results = [work(blocks[0])]
    else:
        with ThreadPoolExecutor(max_workers=min(GEMINI_PARALLEL, len(blocks))) as ex:
            results = list(ex.map(work, blocks))
    agg = _empty_data()
    notes = []
    for data, n in results:
        merge_data(agg, data)
        notes.extend(n)
    if not _has_content(agg):
        msg = "⚠️ Data samajh nahi aaya. Message check karke dobara bhejiye."
        if notes:
            msg += "\n" + "\n".join(f"ℹ️ {n}" for n in dict.fromkeys(notes))
        return msg
    lines = []
    with PROCESS_LOCK:
        for fn, payload, name in ((update_google_sheet, agg if (agg["prs"] or agg["uts"]) else None, "UTS/PRS"),
                                  (update_osop_sheet, agg["osop"], "OSOP"),
                                  (update_iwow_sheet, agg["goods"], "IWOW")):
            if not payload:
                continue
            try:
                ok, rep = fn(payload)
                lines.extend(rep)
            except Exception as e:
                print(f"❌ {name} write crashed: {e}")
                reset_caches()
                lines.append(f"❌ {name} update fail: {e}")
    lines.extend(f"ℹ️ {n}" for n in dict.fromkeys(notes))
    return "\n".join(lines) if lines else "⚠️ Kuch update nahi hua."

# ==============================================
# WHATSAPP + WEBHOOK
# ==============================================
def send_whatsapp(to, text):
    if not (SEND_REPLY and WHATSAPP_TOKEN and PHONE_NUMBER_ID and to):
        return False
    try:
        url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
        headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
        payload = {"messaging_product": "whatsapp", "to": to, "type": "text",
                   "text": {"body": str(text)[:3800]}}
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        if r.status_code >= 300:
            print(f"❌ WhatsApp reply error {r.status_code}: {r.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"❌ WhatsApp reply exception: {e}")
        return False

def handle_message(text, reply_to=None):
    try:
        summary = process_incoming(text)
    except Exception as e:
        print(f"❌ process_incoming error: {e}")
        summary = f"❌ Processing me error aaya: {e}"
    print("📝 Summary:\n" + summary)
    if reply_to:
        send_whatsapp(reply_to, summary)
    return summary

@app.route("/", methods=["GET"])
def home():
    return "Bot is running ✅", 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time_ist": ist_now().strftime("%d/%m/%Y %H:%M")}), 200

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
                    threading.Thread(target=handle_message, args=(text, m.get("from")),
                                     daemon=True).start()
    except Exception as e:
        print(f"❌ Webhook Error: {e}")
    return jsonify({"status": "ok"}), 200

def startup_check():
    print("========== STARTUP CHECK ==========")
    print(f"SHEET_NAME      : {SHEET_NAME}")
    print(f"GEMINI_API_KEY  : {bool(GEMINI_API_KEY)}  model={GEMINI_MODEL}")
    print(f"CREDENTIALS     : {bool(GOOGLE_CREDENTIALS_STR or GOOGLE_CREDENTIALS_B64)}")
    print(f"IWOW_GRACE_HOUR : {IWOW_GRACE_HOUR}:00 IST")
    print(f"WA REPLY        : {SEND_REPLY and bool(WHATSAPP_TOKEN and PHONE_NUMBER_ID)}")
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
