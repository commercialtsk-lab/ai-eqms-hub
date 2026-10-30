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
# STATION ALIASES (short code + full names)
# ==============================================
STATION_ALIASES = {
    "DBRT": ["DBRT", "DIBRUGARH TOWN", "DIBRUGARHTOWN"],
    "DBRG": ["DBRG", "DIBRUGARH", "DIBRU GARH"],
    "NTSK": ["NTSK", "NEW TINSUKIA", "NEWTINSUKIA", "NEW TINSUKIA JN"],
    "TSK": ["TSK", "TINSUKIA", "TIN SUKIA"],
    "MXN": ["MXN", "MARIANI", "MARIANI JN"],
    "JTTN": ["JTTN", "JORHAT TOWN", "JORHATTOWN"],
    "SRTN": ["SRTN", "SIVASAGAR", "SIVASAGAR TOWN", "SIBSAGAR"],
    "SLGR": ["SLGR", "SIMALUGURI", "SIMALUGURI JN"],
    "GLGT": ["GLGT", "GOLAGHAT", "GOLAGHAT TOWN"],
    "MRHT": ["MRHT", "MORANHAT", "MORAN HAT"],
    "NAM": ["NAM", "NAMRUP"],
    "NHK": ["NHK", "NAHARKATIYA", "NAHARKATIA"],
    "FKG": ["FKG", "FURKATING", "FURKATING JN"],
    "AGI": ["AGI", "AMGURI"],
    "DJG": ["DJG", "DULIAJAN"],
    "LEDO": ["LEDO"],
    "MRG": ["MRG", "MARGHERITA"],
    "DBY": ["DBY", "DIGBOI"],
    "MJN": ["MJN", "MAKUM", "MAKUM JN"],
    "TTB": ["TTB", "TINSUKIA TOWN"],
    "BOJ": ["BOJ", "BORHAT"],
    "BFD": ["BFD", "BORDUBI ROAD"],
    "SPK": ["SPK", "SAPEKHATI"],
    "CHB": ["CHB", "CHABUA"],
    "SPTR": ["SPTR", "SILAPATHAR"],
    "DMC": ["DMC", "DHEMAJI"],
    "MZS": ["MZS", "MURKONGSELEK", "MURKONG SELEK"],
    "NLP": ["NLP", "NORTH LAKHIMPUR", "N LAKHIMPUR"],
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
    "NSBG": ["NSBG", "NISBG"],
    "KOWN": ["KOWN", "KOWNO"],
    "NCH": ["NCH", "NACHANI"],
    "CMA": ["CMA", "CHUMUKEDIMA"],
    "KXL": ["KXL", "KOKILA"],
    "BBGN": ["BBGN", "BOKAJAN"],
    "BLMR": ["BLMR", "BALIMARA"],
    "NMGY": ["NMGY", "NAMGONG"],
    "KRHT": ["KRHT", "KARIMGANJ"]
}

ALL_STATIONS = list(STATION_ALIASES.keys())

# ==============================================
# COLUMN MAPS (per block)
# ==============================================
# Block 1 (Col B, rows 3-30)  : PRS + UTS
# Block 2 (Col M, rows 31-47) : UTS only (same cols as B1 UTS)
# Block 3 (Col C, rows 32-47) : UTS only (PRS-style cols)

B1_PRS_COLS = {
    "TKT": 4, "PASS": 5, "C/TKT": 6, "C/PASS": 7,
    "REF": 8, "NET": 9, "VCH": 10, "POS": 11, "UPI": 12
}

B1_UTS_COLS = {
    "PF": 14, "TKT": 16, "PASS": 17, "NET": 18,
    "MR": 19, "MR AMT": 20, "UPI": 21
}

B2_UTS_COLS = {
    "PF": 14, "TKT": 16, "PASS": 17, "NET": 18,
    "MR": 19, "MR AMT": 20, "UPI": 21
}

B3_UTS_COLS = {
    "TKT": 4, "PASS": 5, "PF": 8, "NET": 9,
    "MR": 9, "MR AMT": 10, "UPI": 12
}

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
# CREDENTIALS LOADING
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
_SHEET = None
_STATION_MAP = None

def get_sheet():
    global _SHEET
    if _SHEET:
        return _SHEET
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
            _SHEET = sh.worksheet("UTS&PRS")
        except gspread.WorksheetNotFound:
            print("⚠️ 'UTS&PRS' tab nahi mili, sheet1 use kar rahe hain")
            _SHEET = sh.sheet1
        print(f"✅ Google Sheet connected: '{sh.title}' / tab: '{_SHEET.title}'")
        return _SHEET
    except Exception as e:
        print(f"❌ Google Sheet Connection Error: {e}")
        return None

def get_station_map(sheet):
    """Scan all 3 blocks. Returns {STATION: {row, nameCol, block}}."""
    global _STATION_MAP
    if _STATION_MAP:
        return _STATION_MAP
    m = {}
    try:
        all_values = sheet.get_all_values()
    except Exception as e:
        print(f"❌ Error reading full sheet: {e}")
        _STATION_MAP = m
        return m

    def _clean(v):
        return str(v).upper().strip() if v else ""

    # Block 1: Column B (index 1), rows 3-30 → sheet index 2-29
    for i in range(2, min(30, len(all_values))):
        row = all_values[i]
        val = _clean(row[1] if len(row) > 1 else "")
        if val and val not in m:
            m[val] = {"row": i + 1, "nameCol": "B", "block": "B1"}

    # Block 2: Column M (index 12), rows 31-47 → sheet index 30-46
    for i in range(30, min(47, len(all_values))):
        row = all_values[i]
        val = _clean(row[12] if len(row) > 12 else "")
        if val and val not in m:
            m[val] = {"row": i + 1, "nameCol": "M", "block": "B2"}

    # Block 3: Column C (index 2), rows 32-47 → sheet index 31-46
    for i in range(31, min(48, len(all_values))):
        row = all_values[i]
        val = _clean(row[2] if len(row) > 2 else "")
        if val and val not in m:
            m[val] = {"row": i + 1, "nameCol": "C", "block": "B3"}

    _STATION_MAP = m
    print(f"✅ Station map ready: {len(m)} stations")
    # print(f"   B1: {sum(1 for v in m.values() if v['block']=='B1')} | "
    #       f"B2: {sum(1 for v in m.values() if v['block']=='B2')} | "
    #       f"B3: {sum(1 for v in m.values() if v['block']=='B3')}")
    return m

# ==============================================
# SMART STATION RESOLVER
# ==============================================
def resolve_station(name):
    if not name:
        return None
    name = str(name).upper().strip()
    name = re.sub(r'[^A-Z0-9 ]', '', name)

    if name in STATION_ALIASES:
        return name

    for code, aliases in STATION_ALIASES.items():
        for alias in aliases:
            if name == alias or name in alias or alias in name:
                return code

    clean = name.replace(" ", "")
    for code, aliases in STATION_ALIASES.items():
        for alias in aliases:
            if clean == alias.replace(" ", ""):
                return code
    return None

# ==============================================
# GEMINI CALL (Perfect mapping prompt)
# ==============================================
def call_gemini(msg):
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY missing!")
        return None

    prompt = f"""You are an expert Indian Railway PRS/UTS data extraction system.
Extract data into STRICT JSON only.

VALID STATIONS (use ONLY these short codes):
{', '.join(ALL_STATIONS)}

═══════════════════════════════
PRS FIELD MAPPING
═══════════════════════════════
- TKT      = T/TKT, TKT, TKTs, Total Tickets
- PASS     = T/Pass, PASS, Passengers
- C/TKT    = C/TKT, CANTKT, C/T, Cancelled Tickets
- C/PASS   = C/PASS, CANPASS, C/P, Cancelled Passengers
- NET      = Net Cash, NETCASH, NET CASH, AMT, NET (as stated — NEVER subtract)
- REF      = SUM of all refunds: REFUND + UPIREFUND + UPI RFD + Digi REFUND + Digi REF + e-Refund + POS REF + RFD + any REF
- UPI      = UPI, QR, Digi CASH, E-Cash, E/CASH, D/CASH (all digital)
- VCH      = VOUCHER, VCH, VOU
- POS      = POS

═══════════════════════════════
UTS FIELD MAPPING
═══════════════════════════════
- TKT      = TKT, TKTs, J/TKT, T/jrny — NEVER "PLATFORM TKT"
- PASS     = PASS, J/Pass
- NET      = AMOUNT, J/Amount, J AMOUNT, NET CASH, Cash, Ttl (as stated — NEVER subtract)
- UPI      = UPI, QR, ECASH, E/CASH, D/CASH, E cas, E-Cash, Digi CASH
- PF       = ONLY from explicit PF line:
             * "PF TKT-82" / "PF Tkts-82" / "PF Qty-82" / "P/TKT=267" → use number AS-IS (82, 267) — COUNT
             * "PF-60" / "PF AMT-60" / "PF Amount=60" → divide by 10 → 6 (rupees)
             * "PF NIL" / "PF TKTs - NIL" / "PF. NIL" → 0
             * No PF line at all → 0
- MR       = MR count (e.g. "MR 16=17570" → MR=16, MR AMT=17570)
- MR AMT   = MR amount

═══════════════════════════════
CRITICAL RULES
═══════════════════════════════
1. PLATFORM TKT and PLATFORMAMT are platform tickets — IGNORE COMPLETELY. NOT PF, NOT TKT.
2. "PLATFORM TKT=52" does NOT mean PF=52.
3. No "PF"/"P/TKT" line in UTS → PF = 0.
4. "PF NIL" / "PF TKTs - NIL" / "PF. NIL" → PF = 0.
5. "PF TKT-82" / "P/TKT=267" → 82 / 267 (count, no divide).
6. "PF-60" / "PF AMT-60" → 6 (÷10).
7. NET = amount EXACTLY as stated. NEVER subtract E/CASH, UPI, ECASH, Digi from NET.
8. SUM all refund types into REF for PRS.
9. Ignore nil, null, zero, blank, "-".
10. Multi-station: separate PRS and UTS per station, each PF independent.
11. ONLY include a section if it EXISTS for that station:
    - No PRS → do NOT include under "prs"
    - No UTS → do NOT include under "uts"
12. Station can be short code (MZS) or full name (Murkongselek). Always convert to short code.
13. Spelling mistakes in station names should be corrected intelligently.
14. Return ONLY pure JSON, no markdown, no explanation.

Return format:
{{
  "prs": {{
    "STATION_CODE": {{"TKT":0, "PASS":0, "C/TKT":0, "C/PASS":0, "REF":0, "NET":0, "VCH":0, "POS":0, "UPI":0}}
  }},
  "uts": {{
    "STATION_CODE": {{"TKT":0, "PASS":0, "NET":0, "UPI":0, "PF":0, "MR":0, "MR AMT":0}}
  }}
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
                return parsed
            print("⚠️ Gemini: no JSON block")
        else:
            print(f"❌ Gemini HTTP {res.status_code}: {res.text[:300]}")
    except Exception as e:
        print(f"❌ Gemini API Error: {e}")
    return None

# ==============================================
# POST PROCESSING (station normalize + PF strict)
# ==============================================
def split_message_by_station(msg):
    """Split bulk message into per-station blocks (for PF extraction)."""
    blocks = {}
    if not msg:
        return blocks

    header_re = re.compile(
        r'(?:REVENUE\s+OF|EARNINGS\s+OF|REVENUE\s+of|Earnings\s+Of|UTS\s+OF|PRS\s+OF|UTS\s+of|PRS\s+of)\s+(?:UTS/|PRS/)?([A-Z]{{2,6}})',
        re.IGNORECASE
    )
    matches = []
    for m in header_re.finditer(msg):
        st = m.group(1).upper()
        code = resolve_station(st)
        if code:
            matches.append({"station": code, "index": m.start()})

    bare_re = re.compile(r'\b(?:UTS|PRS)/([A-Z]{2,6})\b', re.IGNORECASE)
    for m in bare_re.finditer(msg):
        st = m.group(1).upper()
        code = resolve_station(st)
        if code:
            close_dup = any(abs(x["index"] - m.start()) < 5 for x in matches)
            if not close_dup:
                matches.append({"station": code, "index": m.start()})

    # First-line standalone station
    first_line = msg.split("\n")[0].strip().upper()
    code = resolve_station(first_line)
    if code and not matches:
        matches.append({"station": code, "index": 0})

    matches.sort(key=lambda x: x["index"])
    for i, mt in enumerate(matches):
        start = mt["index"]
        end = matches[i + 1]["index"] if i + 1 < len(matches) else len(msg)
        block = msg[start:end]
        st = mt["station"]
        blocks[st] = blocks.get(st, "") + "\n" + block
    return blocks

def extract_pf_from_message(text):
    """Returns PF count from explicit PF line, or 0 if NIL, or None if no PF line."""
    if not text:
        return None
    clean = re.sub(r'PLATFORM\s*(?:TKT|AMT|AMOUNT)?', ' ', text, flags=re.IGNORECASE)

    if re.search(r'\b(?:P/TKT|PF)\b[^\n]*?(?:NIL|NIL\.)', clean, re.IGNORECASE):
        return 0

    m = re.search(
        r'\b(?:P/TKT|PF\s*(?:TKT|QTY|QUANTITY|NO\.?|COUNT))\s*\.?\s*[-:=]?\s*(\d+)',
        clean, re.IGNORECASE
    )
    if m:
        return int(m.group(1))

    m2 = re.search(r'\bPF\s*(?:AMT|AMOUNT)\s*\.?\s*[-:=]?\s*(\d+)', clean, re.IGNORECASE)
    if m2:
        return round(int(m2.group(1)) / 10)

    m3 = re.search(r'\bPF\b\s*\.?\s*[-:=]?\s*(\d+)', clean, re.IGNORECASE)
    if m3:
        n = int(m3.group(1))
        return round(n / 10) if n >= 10 else n

    return None

def apply_post_processing(data, msg):
    if not data:
        return data

    # ---- Station code normalize ----
    new_prs = {}
    for st, vals in data.get("prs", {}).items():
        code = resolve_station(st)
        if code:
            # Merge if duplicate
            if code in new_prs:
                for k, v in (vals or {}).items():
                    try:
                        new_prs[code][k] = new_prs[code].get(k, 0) + float(v or 0)
                    except:
                        pass
            else:
                new_prs[code] = dict(vals or {})
    data["prs"] = new_prs

    new_uts = {}
    for st, vals in data.get("uts", {}).items():
        code = resolve_station(st)
        if code:
            if code in new_uts:
                for k, v in (vals or {}).items():
                    try:
                        new_uts[code][k] = new_uts[code].get(k, 0) + float(v or 0)
                    except:
                        pass
            else:
                new_uts[code] = dict(vals or {})
    data["uts"] = new_uts

    # ---- Per-station PF override (strict) ----
    station_blocks = split_message_by_station(msg)
    for st in list(data["uts"].keys()):
        block = station_blocks.get(st)
        if not block:
            # No block → clean AI value
            try:
                v = float(data["uts"][st].get("PF", 0) or 0)
                data["uts"][st]["PF"] = int(v) if v < 10 else round(v / 10)
            except:
                data["uts"][st]["PF"] = 0
            continue
        pf = extract_pf_from_message(block)
        data["uts"][st]["PF"] = 0 if pf is None else pf

    return data

# ==============================================
# UPDATE GOOGLE SHEET (block-aware, manual-safe)
# ==============================================
def update_google_sheet(data):
    sheet = get_sheet()
    if not sheet:
        print("❌ Could not connect to Google Sheet.")
        return False
    smap = get_station_map(sheet)
    try:
        matrix = sheet.get_all_values()
    except Exception as e:
        print(f"❌ Sheet read error: {e}")
        return False

    def current(r, c):
        try:
            v = matrix[r - 1][c - 1]
            return float(str(v).replace(",", ""))
        except:
            return 0.0

    def is_formula(r, c):
        try:
            v = matrix[r - 1][c - 1]
            return isinstance(v, str) and v.startswith("=")
        except:
            return False

    updates = []
    def queue(r, c, val):
        updates.append({"range": rowcol_to_a1(r, c), "values": [[val]]})

    # ---------- PRS ----------
    for st, prs_vals in data.get("prs", {}).items():
        info = smap.get(st)
        if not info:
            print(f"⚠️ Station {st} not found in sheet (PRS)")
            continue
        if info["block"] != "B1":
            print(f"⚠️ {st} is {info['block']} (UTS-only) — PRS data skipped")
            continue
        row = info["row"]
        for fld, val in (prs_vals or {}).items():
            try:
                v = float(val)
            except:
                continue
            if v > 0 and fld in B1_PRS_COLS:
                col = B1_PRS_COLS[fld]
                if is_formula(row, col):
                    print(f"⏭️ Skip formula PRS {st} {fld} @ {rowcol_to_a1(row, col)}")
                    continue
                new_val = current(row, c
