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
# STATION ALIASES  (code bhi, full name bhi, "JN" suffix ke sath bhi)
# ==============================================
STATION_ALIASES = {
    "DBRT": ["DBRT", "DIBRUGARH TOWN", "DIBRUGARHTOWN"],
    "DBRG": ["DBRG", "DIBRUGARH", "DIBRU GARH", "DIBRUGARH JN"],
    "NTSK": ["NTSK", "NEW TINSUKIA", "NEWTINSUKIA", "NEW TINSUKIA JN", "NEW TINSUKIA JUNCTION"],
    "TSK": ["TSK", "TINSUKIA", "TIN SUKIA", "TINSUKIA JN"],
    "MXN": ["MXN", "MARIANI", "MARIANI JN", "MARIANI JUNCTION"],
    "JTTN": ["JTTN", "JORHAT TOWN", "JORHATTOWN", "JORHAT"],
    "SRTN": ["SRTN", "SIVASAGAR", "SIVASAGAR TOWN", "SIBSAGAR", "SIVASAGARTOWN"],
    "SLGR": ["SLGR", "SIMALUGURI", "SIMALUGURI JN", "SIMALUGURI JUNCTION"],
    "GLGT": ["GLGT", "GOLAGHAT", "GOLAGHAT TOWN"],
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
    "TTB": ["TTB", "TINSUKIA TOWN"],
    "BOJ": ["BOJ", "BORHAT"],
    "BFD": ["BFD", "BORDUBI ROAD"],
    "SPK": ["SPK", "SAPEKHATI"],
    "CHB": ["CHB", "CHABUA"],
    "SPTR": ["SPTR", "SILAPATHAR"],
    "DMC": ["DMC", "DHEMAJI"],
    "MZS": ["MZS", "MURKONGSELEK", "MURKONG SELEK"],
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
# STATION RESOLUTION HELPERS  (FULL NAME / JN / STATION sab handle karta hai)
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
    """
    Code ho ya full name, 'Jn'/'Station'/'Junction' ke sath ho — sab official code me resolve hota hai.
    'AMGURI JN' -> AGI, 'Tinsukia' -> TSK, 'New Tinsukia Jn' -> NTSK
    """
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

    # substring fallback (len>=4)
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

    prompt = f"""You are an expert Indian Railway PRS & UTS data extraction engine.
Extract numbers into STRICT JSON only. No explanation, no markdown.

VALID STATION CODES (use ONLY these exact short codes):
{', '.join(ALL_STATIONS)}

=== UNDERSTAND THE MESSAGE NATURALLY ===
Messages can be in ANY format (WhatsApp, typed, mixed English/Hindi, broken lines, typos).
Read the entire message and extract each numeric field for the mentioned station(s).
A single message may contain both UTS and PRS sections — extract both separately.
A single message may mention multiple stations — extract ALL of them.

=== STATION RULES (100% MANDATORY — READ CAREFULLY) ===
1. ALWAYS output the OFFICIAL SHORT CODE as the key — even if the message uses the FULL STATION NAME.
2. Full name ho ya code, dono ko same station samjho:
   "AMGURI JN", "AMGURI", "Amguri Junction", "AGI" → ALL mean "AGI"
   "TINSUKIA" → "TSK" | "NEW TINSUKIA" → "NTSK" | "DIBRUGARH TOWN" → "DBRT" | "DIBRUGARH" → "DBRG"
   "FURKATING JN" → "FKG" | "MARIANI" → "MXN" | "NORTH LAKHIMPUR" → "NLP" | "TEZU" → "TEZU"
3. Agar station clearly identifiable nahi hai, us station ko skip karo.

=== STRICT PRS MAPPING (100% MANDATORY) ===
- "NET" = SIRF "NETCASH" / "NET CASH" / "Net cash" ki value. KABHI BHI Digi Cash / QR / UPI / digital cash NET me ADD MAT KARO.
- ALL digital cash amounts (DIGI CASH, Digi Cash, QR, UPI CASH, UPI, PhonePe, GPay, Paytm, Card, online payment) → "UPI" field me jaate hain. NET me NAHI.
- POS = sirf tab jab message me explicitly "POS" likha ho. POS cash ko POS column me rakho (UPI me nahi).
- "REF" = SUM of ALL refund amounts in the message. Cash Refund + Digi Refund + UPI Refund + POS Refund — SAB KO ADD KARO aur ek hi REF number do.
  Example: REFUND 560 + DIGI REFUND 1055 → "REF": 1615
- TKT / Tickets → TKT ; PASS / Passenger → PASS
- C/TKT / Cancelled Ticket → C/TKT ; C/PASS / Cancelled Passenger → C/PASS
- VOUCHER / VCH → VCH
- N/I, CST, POS REFUND (as separate refund) → refunds ke total me include karo (POS refund REF me jata hai)

=== STRICT UTS MAPPING (100% MANDATORY) ===
- "NET" = SIRF "NETCASH" value. UPI CASH ya digital cash NET me ADD MAT KARO.
  VERY IMPORTANT EXAMPLE: "NETCASH 22290" aur "UPI CASH 4360" → NET=22290, UPI=4360.
  NET=26650 KABHI MAT DO (ye UPI add karne se aata hai — GALAT HAI).
- UPI CASH / QR / digital → UPI
- REF = sum of all refunds (UPI REFUND + REFUND etc. — jo NIL ho usko skip karo)
- TKT = total tickets. Agar "TKT 281" aur "JOURNEY TKT 278" dono hain → TKT = 281 (total wala).
- PASS = total passengers ; PF = platform tickets ; MR = miscellaneous receipt count ; MR AMT = MR amount

=== CRITICAL RULES FOR MISSING NUMBERS ===
1. Field mentioned but NO NUMBER (e.g. "amount nahi aya", "nil", "-", "not received") → OMIT that field completely. Do NOT put 0.
2. Only include a field if a NUMERIC VALUE is literally written.
3. Do NOT guess. Do NOT invent numbers.
4. Agar ek section (PRS/UTS) message me nahi hai → empty object {{}}

=== NEGATIVE NUMBERS ===
Negative number dikhe (e.g. "AMOUNT :- -865") → negative sign preserve karo. Positive mat karo.

Required JSON format (only include fields that have actual numbers):
{{
  "prs": {{
    "STATION_CODE": {{"TKT":0, "PASS":0, "C/TKT":0, "C/PASS":0, "REF":0, "NET":0, "VCH":0, "POS":0, "UPI":0}}
  }},
  "uts": {{
    "STATION_CODE": {{"TKT":0, "PASS":0, "NET":0, "UPI":0, "PF":0, "MR":0, "MR AMT":0}}
  }}
}}

=== EXAMPLE 1 (refunds added, digi cash NOT added to net) ===
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
(NOTICE: REF = 560 + 1055 = 1615. NET omitted kyunki number nahi tha.)

=== EXAMPLE 2 (full name station + digi cash NOT in net) ===
Input:
"AMGURI JN PRS EARNINGS FOR 30/10/26
TKT-----16
PASS-----21
NETCASH---RS 4000/-
REFUND----RS 560/-
DIGI CASH-----RS 36390/-
DIGI REFUND---RS 1055/-
POS----NIL
VOUCHER------NIL
C/TKT-----03
C/PASS----------03

AMGURI JN UTS EARNINGS FOR 30/10/26
TKT--281
PASS----458
NETCASH---RS 22290/-
UPI CASH-----RS 4360/-
REFUND ---RS NIL/-"

Output:
{{
  "prs": {{
    "AGI": {{"TKT": 16, "PASS": 21, "NET": 4000, "REF": 1615, "UPI": 36390, "C/TKT": 3, "C/PASS": 3}}
  }},
  "uts": {{
    "AGI": {{"TKT": 281, "PASS": 458, "NET": 22290, "UPI": 4360}}
  }}
}}
(NOTICE: "AMGURI JN" → "AGI". PRS NET=4000 sirf netcash, DIGI CASH 36390 → UPI. REF=560+1055=1615. UTS NET=22290 sirf netcash, UPI=4360 — 26650 BILKUL NAHI.)

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
                # ⚠️ NOTE: NET aur MR yaha same column 9 par hain — apne sheet layout verify kar lena
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
