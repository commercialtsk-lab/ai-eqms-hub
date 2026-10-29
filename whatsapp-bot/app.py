import os
import json
import re
import time
import requests
from flask import Flask
from pywa import WhatsApp
import gspread
from google.oauth2.service_account import Credentials

# ==============================================
# 1. APP SETUP
# ==============================================
app = Flask(__name__)

# ==============================================
# 2. CONFIGURATION
# ==============================================
CONFIG_SHEET_NAME = os.environ.get('GOOGLE_SHEET_NAME', 'UTS&PRS')
GEMINI_MODEL = "gemini-2.5-flash"

gemini_keys_str = os.environ.get('GEMINI_KEYS', '')
GEMINI_API_KEYS = [k.strip() for k in gemini_keys_str.split(',')] if gemini_keys_str else [os.environ.get('GEMINI_KEY', '')]

ALL_STATIONS = [
    "DBRT","DBRG","NTSK","TSK","MXN","JTTN","SRTN","SLGR","GLGT","MRHT",
    "NAM","NHK","FKG","AGI","DJG","LEDO","MRG","DBY","MJN","TTB","BOJ",
    "BFD","SPK","CHB","SPTR","DMC","MZS","NLP","LBI","BGND","LMY","SRPN",
    "SMCP","TQM","GOM","BDLN","CKW","LHL","DKM","PNT","TII","LXA","SFR",
    "SLX","NMT","ROING","TEZU","CGF","DMGN","TNGN","NSBG","KOWN","NCH",
    "CMA","KXL","BBGN","BLMR","NMGY","KRHT"
]

PRS_COLS = { 
    "TKT":4, "PASS":5, "C/TKT":6, "C/PASS":7, 
    "REF":8, "NET":9, "VCH":10, "POS":11, "UPI":12 
}

UTS_COLS_NU = { 
    "PF":14, "TKT":16, "PASS":17, "NET":18, 
    "MR":19, "MR AMT":20, "UPI":21 
}

key_last_used = {}
key_rate_limit = {}

# ==============================================
# 3. WHATSAPP & GOOGLE SHEETS SETUP
# ==============================================
wa = WhatsApp(
    phone_id=os.environ.get('PHONE_ID'),
    token=os.environ.get('META_TOKEN'),
    server=app,
    verify_token=os.environ.get('VERIFY_TOKEN')
)

# --- GOOGLE CREDENTIALS FIX ---
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

# Render ke Secret File ka path check karein
creds_path = '/etc/secrets/creds.json'

if os.path.exists(creds_path):
    creds = Credentials.from_service_account_file(creds_path, scopes=scope)
elif os.path.exists('creds.json'):
    creds = Credentials.from_service_account_file('creds.json', scopes=scope)
else:
    # Fallback: Environment variable se JSON load karein
    creds_json = os.environ.get('GOOGLE_CREDS_JSON')
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    else:
        raise ValueError("Credentials not found. Please add Secret File or GOOGLE_CREDS_JSON env variable.")

gc = gspread.authorize(creds)

# ==============================================
# 4. EXTRACTION LOGIC
# ==============================================
def extract_pf_quantity(value, context):
    if value is None: return 0
    s = str(value).strip()
    if s == "" or re.match(r'^(nil|null|0)$', s, re.I): return 0
    nums = re.findall(r'\d+', s)
    if not nums: return 0
    first_num = int(nums[0])
    if context and re.search(r'(TKT|QTY|QUANTITY|NO\.?|COUNT)', context, re.I): return first_num
    if context and re.search(r'(AMOUNT|AMT)', context, re.I): return round(first_num / 10)
    if first_num >= 10: return round(first_num / 10)
    return first_num

def extract_pf_from_message(msg):
    if not msg: return None
    clean_msg = re.sub(r'PLATFORM\s*(?:TKT|AMT|AMOUNT)?', ' ', msg, flags=re.I)
    if re.search(r'\b(?:P\/TKT|PF)\b[^\n]*?(?:NIL|NIL\.)', clean_msg, re.I): return 0
    m = re.search(r'\b(?:P\/TKT|PF\s*(?:TKT|QTY|QUANTITY|NO\.?|COUNT))\s*\.?\s*[-:=]?\s*(\d+)', clean_msg, re.I)
    if m: return int(m.group(1))
    m2 = re.search(r'\bPF\s*(?:AMT|AMOUNT)\s*\.?\s*[-:=]?\s*(\d+)', clean_msg, re.I)
    if m2: return round(int(m2.group(1)) / 10)
    m3 = re.search(r'\bPF\b\s*\.?\s*[-:=]?\s*(\d+)', clean_msg, re.I)
    if m3:
        n = int(m3.group(1))
        return round(n / 10) if n >= 10 else n
    return None

def message_has_digital_cash(msg):
    return bool(re.search(r'(?:E\/CASH|D\/CASH|ECASH|DCASH|E-CASH|E\s*CASH|DIGI\s*CASH)', msg or "", re.I))

def extract_digital_cash(msg):
    if not msg: return 0
    total = 0
    matches = re.findall(r'(?:E\/CASH|D\/CASH|ECASH|DCASH|E-CASH|E\s*CASH|DIGI\s*CASH)\s*[-:=]?\s*([\d,]+(?:\.\d+)?)', msg, re.I)
    for m in matches:
        try: total += float(m.replace(',', ''))
        except: pass
    return total

def split_message_by_station(msg):
    blocks = {}
    if not msg: return blocks
    matches = []
    for m in re.finditer(r'(?:REVENUE\s+OF|EARNINGS\s+OF|REVENUE\s+of|Earnings\s+Of|UTS\s+OF|PRS\s+OF|UTS\s+of|PRS\s+of)\s+(?:UTS\/|PRS\/)?([A-Z]{2,6})', msg, re.I):
        st = m.group(1).upper()
        if st in ALL_STATIONS: matches.append({'station': st, 'index': m.start()})
    for m in re.finditer(r'\b(?:UTS|PRS)\/([A-Z]{2,6})\b', msg, re.I):
        st = m.group(1).upper()
        if st in ALL_STATIONS and not any(abs(x['index'] - m.start()) < 5 for x in matches):
            matches.append({'station': st, 'index': m.start()})
    first_line = msg.split("\n")[0].strip().upper()
    if first_line in ALL_STATIONS and not matches:
        matches.append({'station': first_line, 'index': 0})
    matches.sort(key=lambda x: x['index'])
    for i in range(len(matches)):
        start = matches[i]['index']
        end = matches[i+1]['index'] if i+1 < len(matches) else len(msg)
        block = msg[start:end]
        st = matches[i]['station']
        blocks[st] = blocks.get(st, "") + "\n" + block
    return blocks

def get_station_row(sheet, station):
    if not station: return None
    station = station.upper().strip()
    for r in range(3, 31):
        val = sheet.cell(r, 2).value
        if val and str(val).upper().strip() == station: return {'row': r, 'name_col': 'B'}
    for r in range(31, 48):
        val = sheet.cell(r, 13).value
        if val and str(val).upper().strip() == station: return {'row': r, 'name_col': 'M'}
    for r in range(32, 48):
        val = sheet.cell(r, 3).value
        if val and str(val).upper().strip() == station: return {'row': r, 'name_col': 'C'}
    return None

# ==============================================
# 5. GEMINI API CALLS
# ==============================================
def get_working_key():
    now = time.time()
    for key in GEMINI_API_KEYS:
        if not key: continue
        if now < key_rate_limit.get(key, 0): continue
        if now - key_last_used.get(key, 0) >= 2:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
                res = requests.post(url, json={"contents":[{"parts":[{"text":"ok"}]}], "generationConfig":{"maxOutputTokens":1}}, timeout=5)
                if res.status_code == 200:
                    key_last_used[key] = now
                    key_rate_limit[key] = now + 2
                    return key
                elif res.status_code == 429:
                    key_rate_limit[key] = now + 60
            except: pass
    time.sleep(3)
    return get_working_key()

def call_gemini(msg):
    prompt = f"""You are a railway data entry expert. Extract numbers from this message EXACTLY as specified.
STATIONS: {", ".join(ALL_STATIONS)}
FIELD MAPPING (PRS): TKT, PASS, C/TKT, C/PASS, REF, NET, VCH, POS, UPI
FIELD MAPPING (UTS): TKT, PASS, NET, UPI, PF, MR, MR AMT
RULES:
1. IGNORE PLATFORM TKT.
2. If no "PF" line → PF = 0.
3. "PF TKT-82" → PF = 82.
4. "PF-60" → PF = 6.
5. NET = exact amount. Do NOT subtract anything.
6. Multi-station: separate entries.
Return ONLY JSON: {{"prs": {{"STATION": {{"TKT":0, "PASS":0, "C/TKT":0, "C/PASS":0, "REF":0, "NET":0, "VCH":0, "POS":0, "UPI":0}}}}, "uts": {{"STATION": {{"TKT":0, "PASS":0, "NET":0, "UPI":0, "PF":0, "MR":0, "MR AMT":0}}}}}}
MESSAGE: {msg}
JSON ONLY:"""
    key = get_working_key()
    if not key: return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
        res = requests.post(url, json={"contents":[{"parts":[{"text":prompt}]}], "generationConfig":{"temperature":0.1, "maxOutputTokens":4096}}, timeout=30)
        if res.status_code == 200:
            txt = res.json()['candidates'][0]['content']['parts'][0]['text']
            txt = re.sub(r'```json\n?', '', txt, flags=re.I)
            txt = re.sub(r'```\n?', '', txt).strip()
            match = re.search(r'\{[\s\S]*\}', txt)
            if match: txt = match.group(0)
            parsed = json.loads(txt)
            parsed['prs'] = parsed.get('prs', {})
            parsed['uts'] = parsed.get('uts', {})
            return parsed
    except Exception as e:
        print("Gemini Error:", e)
    return None

# ==============================================
# 6. POST PROCESSING & SHEET UPDATE
# ==============================================
def apply_post_processing(data, msg):
    if not data: return data
    station_blocks = split_message_by_station(msg)
    for st in data.get('uts', {}):
        block = station_blocks.get(st)
        if not block:
            data['uts'][st]['PF'] = extract_pf_quantity(data['uts'][st].get('PF'), None)
        else:
            pf_from_block = extract_pf_from_message(block)
            data['uts'][st]['PF'] = 0 if pf_from_block is None else pf_from_block
    for st in data.get('uts', {}):
        block = station_blocks.get(st)
        if block and message_has_digital_cash(block):
            dc = extract_digital_cash(block)
            cur = float(data['uts'][st].get('UPI', 0) or 0)
            if dc > 0 and cur < dc: data['uts'][st]['UPI'] = cur + dc
    for st in data.get('prs', {}):
        block = station_blocks.get(st)
        if block and message_has_digital_cash(block):
            dc = extract_digital_cash(block)
            cur = float(data['prs'][st].get('UPI', 0) or 0)
            if dc > 0 and cur < dc: data['prs'][st]['UPI'] = cur + dc
    return data

def update_sheet(data):
    if not data: return "❌ No data"
    try: sheet = gc.open(CONFIG_SHEET_NAME).sheet1
    except: return "❌ Sheet not found"
    station_order = list(set(list(data.get('prs', {}).keys()) + list(data.get('uts', {}).keys())))
    for st in station_order:
        info = get_station_row(sheet, st)
        if not info: continue
        if st in data.get('prs', {}):
            for fld, val in data['prs'][st].items():
                val = float(val or 0)
                if val > 0 and fld in PRS_COLS:
                    col = PRS_COLS[fld]
                    curr = sheet.cell(info['row'], col).value
                    curr = float(curr) if curr and str(curr).replace('.','',1).isdigit() else 0
                    sheet.update_cell(info['row'], col, curr + val)
        if st in data.get('uts', {}):
            for fld, val in data['uts'][st].items():
                val = float(val or 0)
                if fld == "PF" and val == 0: continue
                if val > 0:
                    col = None
                    if info['name_col'] == 'C':
                        col_map = {"TKT":4, "PASS":5, "NET":9, "UPI":12, "PF":8, "MR":9, "MR AMT":10}
                        col = col_map.get(fld)
                    else: col = UTS_COLS_NU.get(fld)
                    if col:
                        curr = sheet.cell(info['row'], col).value
                        curr = float(curr) if curr and str(curr).replace('.','',1).isdigit() else 0
                        sheet.update_cell(info['row'], col, curr + val)
    return "Updated"

# ==============================================
# 7. WHATSAPP MESSAGE HANDLER (NO REPLY)
# ==============================================
@wa.on_message()
def handle_message(client_wa, msg):
    if msg.type != 'text': return
    
    incoming_text = msg.text
    try:
        data = call_gemini(incoming_text)
        
        if not data or (len(data.get('prs', {})) == 0 and len(data.get('uts', {})) == 0):
            return
            
        data = apply_post_processing(data, incoming_text)
        update_sheet(data)
        
    except Exception as e:
        print(f"Error: {e}")

# ==============================================
# 8. MAIN
# ==============================================
if __name__ == '__main__':
    app.run(port=5000)
