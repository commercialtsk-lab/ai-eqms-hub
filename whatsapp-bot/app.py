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
# STATION ALIASES
# ==============================================
STATION_ALIASES = {
    "DBRT": ["DBRT", "DIBRUGARH TOWN", "DIBRUGARHTOWN"],
    "DBRG": ["DBRG", "DIBRUGARH", "DIBRU GARH"],
    "NTSK": ["NTSK", "NEW TINSUKIA", "NEWTINSUKIA", "NEW TINSUKIA JN", "NEW TINSUKIA JUNCTION"],
    "TSK": ["TSK", "TINSUKIA", "TIN SUKIA"],
    "MXN": ["MXN", "MARIANI", "MARIANI JN"],
    "JTTN": ["JTTN", "JORHAT TOWN", "JORHATTOWN", "JORHAT"],
    "SRTN": ["SRTN", "SIVASAGAR", "SIVASAGAR TOWN", "SIBSAGAR", "SIVASAGARTOWN"],
    "SLGR": ["SLGR", "SIMALUGURI", "SIMALUGURI JN"],
    "GLGT": ["GLGT", "GOLAGHAT", "GOLAGHAT TOWN"],
    "MRHT": ["MRHT", "MORANHAT", "MORAN HAT"],
    "NAM": ["NAM", "NAMRUP"],
    "NHK": ["NHK", "NAHARKATIYA", "NAHARKATIA"],
    "FKG": ["FKG", "FURKATING", "FURKATING JN"],
    "AGI": ["AGI", "AMGURI", "AMGURI JN", "AMGURI JUNCTION", "AMGURI TOWN"],
    "DJG": ["DJG", "DULIAJAN"],
    "LEDO": ["LEDO"],
    "MRG": ["MRG", "MARGHERITA"],
    "DBY": ["DBY", "DIGBOI"],
    "MJN": ["MJN", "MAKUM", "MAKUM JN"],
    "TTB": ["TTB", "TINSUKIA TOWN"],
    "BOJ": ["BOJ", "BORHAT"],
    "BFD": ["BFD", "BORDUBI ROAD"],
    "SPK": ["SPK", "SAPEKHATI", "SAPEKHATI JN"],
    "CHB": ["CHB", "CHABUA"],
    "SPTR": ["SPTR", "SILAPATHAR"],
    "DMC": ["DMC", "DHEMAJI"],
    "MZS": ["MZS", "MURKONGSELEK", "MURKONG SELEK", "MURKONGSELEK"],
    "NLP": ["NLP", "NORTH LAKHIMPUR", "N LAKHIMPUR", "NORTHLAKHIMPUR"],
    "LBI": ["LBI", "LAKHIMPUR"],
    "BGND": ["BGND", "BAGINADI"],
    "LMY": ["LMY", "LAIMEKURI"],
    "SRPN": ["SRPN", "SORBHOG"],
    "SMCP": ["SMCP", "SIMALUGURI"],
    "TQM": ["TQM", "TEZPUR"],
    "GOM": ["GOM", "GOHPUR"],
    "BDLN": ["BDLN", "BORDALAN"],
    "CKW": ["CKW", "CHAKARBHETI"],
    "LHL": ["LHL", "LAHOLAL"],
    "DKM": ["DKM", "DHEKIAJULI"],
    "PNT": ["PNT", "PANITOLA"],
    "TII": ["TII", "TINGRAI"],
    "LXA": ["LXA", "LAKWA"],
    "SFR": ["SFR", "SAFRAI"],
    "SLX": ["SLX", "SILAPATHAR"],
    "NMT": ["NMT", "NAMTI"],
    "ROING": ["ROING"],
    "TEZU": ["TEZU"],
    "CGF": ["CGF", "CHAGALAM"],
    "DMGN": ["DMGN", "DANGORI"],
    "TNGN": ["TNGN", "TANGANI"],
    "NSBG": ["NSBG"],
    "KOWN": ["KOWN"],
    "NCH": ["NCH"],
    "CMA": ["CMA", "CHUMUKEDIMA"],
    "KXL": ["KXL"],
    "BBGN": ["BBGN", "BOKAJAN"],
    "BLMR": ["BLMR", "BALIMARA"],
    "NMGY": ["NMGY"],
    "KRHT": ["KRHT", "KARIMGANJ"]
}

ALL_STATIONS = list(STATION_ALIASES.keys())

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
# STRICT STATION RESOLVER
# ==============================================
def resolve_station(name):
    if not name:
        return None
    original = str(name).upper().strip()
    name = re.sub(r'[^A-Z0-9 ]', '', original)
    name_clean = name.replace(" ", "")

    if name in STATION_ALIASES:
        return name
    if name_clean in STATION_ALIASES:
        return name_clean

    for code, aliases in STATION_ALIASES.items():
        for alias in aliases:
            if name == alias or name_clean == alias.replace(" ", ""):
                return code

    for code, aliases in STATION_ALIASES.items():
        for alias in aliases:
            if len(name) >= 4 and (name in alias or alias in name):
                return code

    print(f"⚠️ Could not resolve station: '{original}'")
    return None

# ==============================================
# GEMINI (Deployment-safe)
# ==============================================
def call_gemini(msg):
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY missing!")
        return None

    station_list = ", ".join(ALL_STATIONS)

    prompt = (
        "You are an expert Indian Railway PRS & UTS EARNINGS extraction engine.\n"
        "Read the ENTIRE message naturally, then extract numbers into STRICT JSON.\n"
        "Return ONLY pure JSON. No explanation, no markdown.\n\n"
        "VALID STATION CODES (use ONLY these):\n"
        + station_list + "\n\n"
        "==========================================================\n"
        "STEP 1 — DETECT SECTION\n"
        "==========================================================\n"
        "Message may have TWO sections labelled:\n"
        "- 'PRS EARNINGS' / 'PRS' -> PRS section\n"
        "- 'UTS EARNINGS' / 'UTS' -> UTS section\n"
        "Extract each section SEPARATELY. A station may appear in BOTH.\n"
        "A message may mention MULTIPLE stations -> extract ALL.\n"
        "Station names may be written any way:\n"
        "- 'AMGURI JN', 'AMGURI', 'AMGURI JUNCTION', 'AGI' -> AGI\n"
        "- 'NEW TINSUKIA', 'NTSK' -> NTSK\n"
        "ALWAYS output the SHORT CODE.\n\n"
        "==========================================================\n"
        "STEP 2 — PRS MAPPING (STRICT)\n"
        "==========================================================\n"
        "- TKT / Tickets / No of Tickets                 -> TKT\n"
        "- PASS / Passenger / Pax                        -> PASS\n"
        "- C/TKT / C TKT / Cancel Ticket / CST            -> C/TKT (only if NUMBER present)\n"
        "- C/PASS / C PASS / Cancel Passenger            -> C/PASS (only if NUMBER present)\n"
        "- N/I / NI / N I                                -> IGNORE (do not map anywhere)\n"
        "- N/I AMOUNT / N I AMOUNT                       -> IGNORE\n"
        "- NETCASH / NET CASH / NET AMOUNT / AMOUNT / TOTAL / CASH -> NET\n"
        "  ⚠️ NET = NETCASH value ONLY. NEVER add UPI/DIGI/POS to NET.\n"
        "- REFUND / REF / REFUND AMOUNT / CASH REFUND    -> REF\n"
        "- DIGI REFUND / DIGI RF / DIGITAL REFUND        -> REF\n"
        "- POS REFUND / POS RF                           -> REF\n"
        "- UPI REFUND / QR REFUND                        -> REF\n"
        "  ⚠️ ALL refunds (REFUND + DIGI REFUND + POS REFUND + UPI REFUND) -> SUM them ALL into REF.\n"
        "  Example: REFUND 560 + DIGI REFUND 1055 = REF 1615.\n"
        "- DIGI CASH / DIGI / DIGITAL CASH / QR CASH / ONLINE CASH -> UPI\n"
        "- UPI / QR / PhonePe / GPay / Paytm / Card / E-Cash       -> UPI\n"
        "- POS (only when NUMBER present)                -> POS\n"
        "- VCH / VOUCHER                                 -> VCH\n\n"
        "==========================================================\n"
        "STEP 3 — UTS MAPPING (STRICT)\n"
        "==========================================================\n"
        "- TKT / Tickets                                 -> TKT\n"
        "- JOURNEY TKT / J TKT                           -> IGNORE (do NOT map to TKT)\n"
        "  ⚠️ If both 'TKT' and 'JOURNEY TKT' appear, use ONLY 'TKT' value.\n"
        "- PASS / Passenger / Pax                        -> PASS\n"
        "- NETCASH / NET CASH / AMOUNT / NET AMOUNT / TOTAL -> NET\n"
        "  ⚠️ NET = NETCASH value ONLY. NEVER add UPI to NET.\n"
        "  ⚠️ If NETCASH=22290 and UPI=4360, then NET=22290 and UPI=4360. NEVER NET=26650.\n"
        "- UPI / QR / DIGI CASH / DIGITAL CASH / UPI CASH / ONLINE -> UPI\n"
        "- REFUND / DIGI REFUND / UPI REFUND / QR REFUND -> REF (SUM ALL refunds)\n"
        "- PF / P/TKT / PLATFORM TICKET                  -> PF\n"
        "- MR / MR AMT                                   -> MR / MR AMT\n"
        "- CST / VOUCHER / RTC / N/I / N/I AMOUNT / N/I PASS -> IGNORE (unless NUMBER clearly maps)\n\n"
        "==========================================================\n"
        "STEP 4 — CRITICAL RULES (NEVER BREAK)\n"
        "==========================================================\n"
        "1. NET = NETCASH value ONLY. NEVER add UPI/DIGI/POS to NET.\n"
        "2. ALL refunds (REFUND + DIGI REFUND + POS REFUND + UPI REFUND) -> SUM into REF.\n"
        "3. DIGI CASH / DIGITAL CASH / QR CASH -> UPI, NOT NET.\n"
        "4. UPI CASH -> UPI, NOT NET.\n"
        "5. If a field is mentioned BUT NO NUMBER is given (e.g. 'POS----NIL', 'VOUCHER-----NIL', 'N/I----NIL'), OMIT it completely. Do NOT put 0.\n"
        "6. Negative numbers are preserved with sign (e.g. -865 stays -865).\n"
        "7. If a field has no numeric value, OMIT it.\n"
        "8. 'NIL' / 'nil' / '-' / 'NA' / 'not available' = missing -> OMIT.\n"
        "9. Do NOT invent numbers. Do NOT add fields together unless rule explicitly says so (only REF refunds get summed).\n"
        "10. 'RS 4000/-' -> 4000. Strip 'RS', '/-', commas.\n"
        "11. Empty PRS or UTS section -> output {} for that section.\n"
        "12. Return ONLY pure JSON.\n\n"
        "==========================================================\n"
        "STEP 5 — EXAMPLE\n"
        "==========================================================\n"
        "Input:\n"
        "AMGURI JN PRS EARNINGS FOR 30/10/26\n"
        "TKT-----16\n"
        "PASS-----21\n"
        "NETCASH---RS 4000/-\n"
        "REFUND----RS 560/-\n"
        "DIGI CASH-----RS 36390 /-\n"
        "DIGI REFUND---RS 1055 /-\n"
        "POS----NIL\n"
        "POS REFUND---NIL\n"
        "CST --NIL\n"
        "VOUCHER------NIL\n"
        "C/TKT-----03\n"
        "C/PASS----------03\n"
        "N/I----NIL\n"
        "N/I AMOUNT--RS NIL\n\n"
        "AMGURI JN UTS EARNINGS FOR 30/10/26\n"
        "TKT--281\n"
        "JOURNEY TKT---278\n"
        "PASS----458\n"
        "NETCASH---RS 22290/-\n"
        "UPI CASH-----RS 4360 /-\n"
        "REFUND ---RS NIL/-\n"
        "UPI REFUND---RS NIL/-\n\n"
        "Correct Output:\n"
        "{\"prs\":{\"AGI\":{\"TKT\":16,\"PASS\":21,\"NET\":4000,\"REF\":1615,\"UPI\":36390,\"C/TKT\":3,\"C/PASS\":3}},"
        "\"uts\":{\"AGI\":{\"TKT\":281,\"PASS\":458,\"NET\":22290,\"UPI\":4360}}}\n\n"
        "Explanation:\n"
        "- PRS NET = 4000 (NETCASH only, NOT 4000+36390)\n"
        "- PRS UPI = 36390 (DIGI CASH -> UPI)\n"
        "- PRS REF = 560 + 1055 = 1615\n"
        "- UTS TKT = 281 (JOURNEY TKT 278 IGNORED)\n"
        "- UTS NET = 22290 (NETCASH only, NOT 22290+4360)\n"
        "- UTS UPI = 4360 (UPI CASH -> UPI)\n\n"
        "==========================================================\n"
        "STEP 6 — JSON FORMAT\n"
        "==========================================================\n"
        "Required format (only include fields with actual numbers):\n"
        "{\"prs\":{\"STATION\":{\"TKT\":0,\"PASS\":0,\"C/TKT\":0,\"C/PASS\":0,\"REF\":0,\"NET\":0,\"VCH\":0,\"POS\":0,\"UPI\":0}},"
        "\"uts\":{\"STATION\":{\"TKT\":0,\"PASS\":0,\"NET\":0,\"UPI\":0,\"PF\":0,\"MR\":0,\"MR AMT\":0}}}\n\n"
        "MESSAGE:\n"
        + msg +
        "\n\nJSON ONLY:"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 2048
        }
    }
    try:
        res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=60)
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
                print(f"⚠️ Duplicate PRS station '{code}' → keeping first")
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
                print(f"⚠️ Duplicate UTS station '{code}' → keeping first")
        else:
            print(f"❌ UTS Station skipped: {st}")
    data["uts"] = new_uts

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
            print(f"⏭️ Cell {rowcol_to_a1(r,c)} already queued, skipping")
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
            print(f"⏭️ PRS {st}: all values 0/missing → SKIPPED")
            continue

        row = info["row"]
        for fld, val in (vals or {}).items():
            try:
                v = float(val)
            except:
                continue

            if fld
