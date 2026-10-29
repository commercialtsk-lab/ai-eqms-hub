import os
import json
import re
import time
import requests
from flask import Flask, request, jsonify
import gspread
from google.oauth2.service_account import Credentials

# ==============================================
# 1. APP SETUP
# ==============================================
app = Flask(__name__)

# ==============================================
# 2. CONFIGURATION
# ==============================================
SPREADSHEET_NAME = "Commercial Position TSK Div NEW"
WORKSHEET_NAME = "UTS&PRS"
GEMINI_MODEL = "gemini-2.5-flash"

gemini_keys_str = os.environ.get('GEMINI_KEYS', '')
GEMINI_API_KEYS = [k.strip() for k in gemini_keys_str.split(',') if k.strip()] if gemini_keys_str else []
single_key = os.environ.get('GEMINI_KEY', '').strip()
if single_key and single_key not in GEMINI_API_KEYS:
    GEMINI_API_KEYS.append(single_key)

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
# 3. GOOGLE SHEETS SETUP
# ==============================================
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

def get_google_credentials():
    creds_dict = {
        "type": "service_account",
        "project_id": "railwaybotnew",
        "private_key_id": "527c52ddb3dd21e8d8431cd8eaf0966e0470436d",
        "private_key": (
            "-----BEGIN PRIVATE KEY-----\n"
            "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDGJnjp28XqPj29\n"
            "9BuVrzb+aVuFZdIHBwz/qHOy6iZ5SGXs7E3W4rETj6utTsAIs23FkBG6gMy/WBoN\n"
            "rI2EBMzHW6mKr1XnaKbtfIBa0TWtJRtyIqujUJoZmvvyCKJAeIDbkcYANHr3Efla\n"
            "LzibAxsRAL1eV04nTxh5jbrOyH4AiAzz5EqTAgDy1SSPPBQGA8M2t+wqf0jf7W9v\n"
            "BRCbgyWbq6+bmyegGgNmB5z0lr7NmWu49WTUczk78sbGFNxk7qjvdS95Y0aJ8GCI\n"
            "gzFKdE1A26ZxnyEplxa5Ja8D9LxLt+5vsBV7XdMRm2tYA94wu4YGZRdvvT8J9Pnl\n"
            "qMDH5q2fAgMBAAECggEAFKj1Ps5Ajqxfq/sUQeFLdsT4cGpjNtgIMG3ZZmRd5OkP\n"
            "YN/AkUZV7TKz1TWaoILzepULbCqQGTvv4iYazpLg4RZlu9qNNpFlpOmwHl1QNJXj\n"
            "tzJLOr4lhcRFlFZMczQSnLzQbBFiEs8SdHyWRn9RO/lw79xi1Ia9iAr8Lnb0FaI/\n"
            "//JQLZUzD74Z3FFsPX7gbgRaDgX/onSwiK5p3gDEVEH7CIPjOZ9K975d+rpoTiC3\n"
            "MW5e6xYbDwEZ7waAACPld12PXK0UxIpNXfiIjksXegiYTWOAyOGkMW4We0K6vWO7\n"
            "WobWOTrELKiUXi1mV9W8YqgHcQRlZBubCYDkf3cBkQKBgQD3L8lLNFvVi2OGheWu\n"
            "iIYzNJAyHjaWMEeqlPnU1z3P9gED6JA6BeywbIRRFDSKsGxnPSeYJ75f+b9iiohh\n"
            "OSJZxKcA2r6p90NHrWHBeg4JV2Mm5KakIGG6PAGni3DVlpiV/txgByArxdOHGO49\n"
            "XMSpciWmq3sPxfoVIoM5OSuWTwKBgQDNNxpcun3CRNOx8HaJ5WZP/frXf+c0IiHz\n"
            "ex4TghXHpnEbvJL2786t+vrsk3+ha8tBO5ZwagGtI+YK4bY3Jjt0pyeeoqws3lbI\n"
            "YoYwmXijPdTZBB7qAVsvWqgjUZT3V+y8Ct3u9ZY5B2FTZLniMcc8eRutWD+r9Yxx\n"
            "fjI2DZDvsQKBgQCz/1U6cT8qSl1H+TrelEX9BZq3FC81wKR/QAqJBc/aHs5wdSqJ\n"
            "RgUsF2lmzSrRj1Tw/KRXdSF5LBlEfZKAEaXE7qGZyrAqfoa8rDHSPLn57WujR79d\n"
            "JsNjZQzjX3Pj5Mzp9POu7aFsnprA9tONVX9T0G5AZwCu5MCOIVqjEdF+mwKBgFbX\n"
            "C5PT4yXTZFX3MOJXrf0JuB17ZYZdL0rOfcK5mKfc2h5npTVT830SKR71p9vSNrfL\n"
            "FHVLlpwDBfTy4N3jkuNhXNW3du6hw82WS7zDJRbHMowHP2G84y5dyarwef5VObu1\n"
            "SYc2a7SEV/4nMLX0ZKBFi53GK2OETEM2qN7QzNVxAoGBAL+4ZjBHiAxW1Nkd3seb\n"
            "LrDik31RW8hAnRDHGN83lHrQyRHfCEKQs7XFyGFNznQhxbTqd/RJP5wC6OcasRDO\n"
            "QX56gghGknWeHMkE2CC/ISDzipgSRmuYQir5v4IXk2XIw9TdXt9/eFQI2GVBd9dl\n"
            "TXDtJ5imgNrUV6j8JvArmcT/\n"
            "-----END PRIVATE KEY-----\n"
        ),
        "client_email": "bot-new@railwaybotnew.iam.gserviceaccount.com",
        "client_id": "110610138242104288410",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/bot-new%40railwaybotnew.iam.gserviceaccount.com",
        "universe_domain": "googleapis.com"
    }
    return Credentials.from_service_account_info(creds_dict, scopes=scope)

creds = get_google_credentials()
gc = gspread.authorize(creds)

# ==============================================
# 4. EXTRACTION & FALLBACK LOGIC
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
    for m in re.finditer(r'(?:REVENUE\s+OF|EARNINGS\s+OF|REVENUE\s+of|Earnings\s+Of|UTS\s+OF|PRS\s+OF|UTS\s+of|PRS\s+of|STN\s*[-:]?)\s*(?:UTS\/|PRS\/)?([A-Z]{2,6})', msg, re.I):
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

# ==============================================
# 5. GEMINI API & SMART FALLBACK EXTRACTION
# ==============================================
def get_working_key():
    if not GEMINI_API_KEYS:
        return None
    now = time.time()
    for key in GEMINI_API_KEYS:
        if not key: continue
        if now < key_rate_limit.get(key, 0): continue
        if now - key_last_used.get(key, 0) >= 1:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
                res = requests.post(url, json={"contents":[{"parts":[{"text":"ok"}]}], "generationConfig":{"maxOutputTokens":1}}, timeout=5)
                if res.status_code == 200:
                    key_last_used[key] = now
                    key_rate_limit[key] = now + 1
                    return key
                elif res.status_code == 429:
                    key_rate_limit[key] = now + 30
            except: pass
    return GEMINI_API_KEYS[0] if GEMINI_API_KEYS else None

def call_gemini_api(msg):
    prompt = f"""You are a railway data entry expert. Extract numbers from this message EXACTLY as specified.
STATIONS: {", ".join(ALL_STATIONS)}
FIELD MAPPING (PRS): TKT, PASS, C/TKT, C/PASS, REF (sum all refunds), NET (AMT), VCH, POS, UPI
FIELD MAPPING (UTS): TKT, PASS, NET (AMT/CASH), UPI (E/CASH), PF, MR, MR AMT
Return ONLY JSON format:
{{"prs": {{"STATION": {{"TKT":0, "PASS":0, "C/TKT":0, "C/PASS":0, "REF":0, "NET":0, "VCH":0, "POS":0, "UPI":0}}}}, "uts": {{"STATION": {{"TKT":0, "PASS":0, "NET":0, "UPI":0, "PF":0, "MR":0, "MR AMT":0}}}}}}
MESSAGE:
{msg}
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
            return {
                'prs': {k.strip().upper(): v for k, v in parsed.get('prs', {}).items()},
                'uts': {k.strip().upper(): v for k, v in parsed.get('uts', {}).items()}
            }
    except Exception as e:
        print("Gemini API Error:", e)
    return None

def call_gemini(msg):
    # 1. Try Gemini API first
    parsed = call_gemini_api(msg)
    if parsed and (parsed.get('prs') or parsed.get('uts')):
        return parsed
        
    print("⚠️ Gemini API returned null. Using Smart Fallback Extractor...")
    
    # 2. Smart Fallback if Gemini fails
    res = {"prs": {}, "uts": {}}
    msg_upper = msg.upper()
    
    found_st = None
    for st in ALL_STATIONS:
        if st in msg_upper:
            found_st = st
            break
            
    if not found_st:
        return res
        
    is_uts = "UTS" in msg_upper or "TTL" in msg_upper or "PSG" in msg_upper or "CASH" in msg_upper
    target_key = "uts" if is_uts else "prs"
    
    fields = {}
    for line in msg.split('\n'):
        parts = re.split(r'[:=-]', line)
        if len(parts) >= 2:
            key_name = parts[0].strip().upper()
            nums = re.findall(r'[\d,]+(?:\.\d+)?', parts[1])
            if nums:
                val = float(nums[0].replace(',', ''))
                if "TTL" in key_name or "TKT" in key_name: fields["TKT"] = val
                elif "PSG" in key_name or "PASS" in key_name: fields["PASS"] = val
                elif "CASH" in key_name and "E" not in key_name: fields["NET"] = val
                elif "AMT" in key_name and "NET" not in fields: fields["NET"] = val
                elif "E/CASH" in key_name or "ECASH" in key_name or "UPI" in key_name: fields["UPI"] = val
                elif "TOTAL" in key_name and "NET" not in fields: fields["NET"] = val

    if is_uts:
        res["uts"][found_st] = {
            "TKT": fields.get("TKT", 0),
            "PASS": fields.get("PASS", 0),
            "NET": fields.get("NET", 0),
            "UPI": fields.get("UPI", 0),
            "PF": 0, "MR": 0, "MR AMT": 0
        }
    else:
        res["prs"][found_st] = {
            "TKT": fields.get("TKT", 0),
            "PASS": fields.get("PASS", 0),
            "C/TKT": 0, "C/PASS": 0, "REF": 0,
            "NET": fields.get("NET", 0),
            "VCH": 0, "POS": 0, "UPI": fields.get("UPI", 0)
        }
        
    return res

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
    try:
        sh = gc.open(SPREADSHEET_NAME)
        sheet = sh.worksheet(WORKSHEET_NAME)
    except Exception as e: 
        print(f"Sheet Access Error: {e}")
        return "❌ Sheet not found"
        
    try:
        all_rows = sheet.get_all_values()
    except Exception as e:
        print(f"Error fetching sheet values: {e}")
        return "❌ Fetch Error"

    def find_station_row(station_code):
        station_code = station_code.upper().strip()
        for idx in range(2, 30):
            if idx < len(all_rows) and len(all_rows[idx]) > 1:
                val = str(all_rows[idx][1]).upper().strip()
                if station_code == val or station_code in val:
                    return {'row': idx + 1, 'name_col': 'B'}
        for idx in range(30, 47):
            if idx < len(all_rows) and len(all_rows[idx]) > 12:
                val = str(all_rows[idx][12]).upper().strip()
                if station_code == val or station_code in val:
                    return {'row': idx + 1, 'name_col': 'M'}
        for idx in range(31, 47):
            if idx < len(all_rows) and len(all_rows[idx]) > 2:
                val = str(all_rows[idx][2]).upper().strip()
                if station_code == val or station_code in val:
                    return {'row': idx + 1, 'name_col': 'C'}
        return None

    prs_data = data.get('prs', {})
    uts_data = data.get('uts', {})
    station_order = list(set(list(prs_data.keys()) + list(uts_data.keys())))

    for st in station_order:
        info = find_station_row(st)
        if not info:
            print(f"⚠️ Station {st} row not found in sheet memory")
            continue
            
        r_idx = info['row']
        
        # --- PRS UPDATE ---
        if st in prs_data:
            for fld, val in prs_data[st].items():
                val = float(val or 0)
                if val > 0 and fld in PRS_COLS:
                    col_idx = PRS_COLS[fld]
                    curr_val_str = all_rows[r_idx - 1][col_idx - 1] if len(all_rows[r_idx - 1]) >= col_idx else "0"
                    curr = float(curr_val_str) if curr_val_str and str(curr_val_str).replace('.','',1).isdigit() else 0
                    new_val = curr + val
                    sheet.update_cell(r_idx, col_idx, new_val)
                    all_rows[r_idx - 1][col_idx - 1] = str(new_val)
                    print(f"✅ Updated PRS {st} {fld}: +{val} -> Total: {new_val}")
                    
        # --- UTS UPDATE ---
        if st in uts_data:
            for fld, val in uts_data[st].items():
                val = float(val or 0)
                if fld == "PF" and val == 0: continue
                if val > 0:
                    col = None
                    if info['name_col'] == 'C':
                        col_map = {"TKT":4, "PASS":5, "NET":9, "UPI":12, "PF":8, "MR":9, "MR AMT":10}
                        col = col_map.get(fld)
                    else: 
                        col = UTS_COLS_NU.get(fld)
                    if col:
                        curr_val_str = all_rows[r_idx - 1][col - 1] if len(all_rows[r_idx - 1]) >= col else "0"
                        curr = float(curr_val_str) if curr_val_str and str(curr_val_str).replace('.','',1).isdigit() else 0
                        new_val = curr + val
                        sheet.update_cell(r_idx, col, new_val)
                        all_rows[r_idx - 1][col - 1] = str(new_val)
                        print(f"✅ Updated UTS {st} {fld}: +{val} -> Total: {new_val}")
                        
    return "Updated"

# ==============================================
# 7. WEBHOOK HANDLER FOR META
# ==============================================
@app.route('/', methods=['GET'])
def home():
    return "Railway Bot Active", 200

@app.route('/webhook', methods=['GET'])
def verify_webhook():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    verify_token = os.environ.get('VERIFY_TOKEN', 'Sharique786')

    if mode and token:
        if mode == 'subscribe' and token == verify_token:
            return challenge, 200
        return 'Forbidden', 403
    return 'Webhook Active', 200

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    data = request.get_json()
    print("Received Webhook Payload:", json.dumps(data))
    try:
        if data.get('entry'):
            for entry in data['entry']:
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    messages = value.get('messages', [])
                    for msg in messages:
                        if msg.get('type') == 'text':
                            text_body = msg['text']['body']
                            print(f"Processing Incoming Text:\n{text_body}")
                            extracted = call_gemini(text_body)
                            print(f"Extracted Data: {json.dumps(extracted)}")
                            if extracted:
                                processed = apply_post_processing(extracted, text_body)
                                res = update_sheet(processed)
                                print(f"Sheet Update Result: {res}")
    except Exception as e:
        print(f"Error handling webhook: {e}")
    return jsonify({'status': 'success'}), 200

# ==============================================
# 8. MAIN
# ==============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
    
