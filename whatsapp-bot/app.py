import os
import re
import json
import requests
import gspread
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==============================================
# ENVIRONMENT VARIABLES (RENDER ENV)
# ==============================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SHEET_NAME = os.environ.get("SHEET_NAME", "UTS&PRS")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
GOOGLE_CREDENTIALS_STR = os.environ.get("GOOGLE_CREDENTIALS", "")

GEMINI_MODEL = "gemini-2.5-flash"

ALL_STATIONS = [
    "DBRT","DBRG","NTSK","TSK","MXN","JTTN","SRTN","SLGR","GLGT","MRHT",
    "NAM","NHK","FKG","AGI","DJG","LEDO","MRG","DBY","MJN","TTB","BOJ",
    "BFD","SPK","CHB","SPTR","DMC","MZS","NLP","LBI","BGND","LMY","SRPN",
    "SMCP","TQM","GOM","BDLN","CKW","LHL","DKM","PNT","TII","LXA","SFR",
    "SLX","NMT","ROING","TEZU","CGF","DMGN","TNGN","NSBG","KOWN","NCH",
    "CMA","KXL","BBGN","BLMR","NMGY","KRHT"
]

PRS_COLS = { 
    "TKT": 4, "PASS": 5, "C/TKT": 6, "C/PASS": 7, 
    "REF": 8, "NET": 9, "VCH": 10, "POS": 11, "UPI": 12 
}

UTS_COLS_NU = { 
    "PF": 14, "TKT": 16, "PASS": 17, "NET": 18, 
    "MR": 19, "MR AMT": 20, "UPI": 21 
}

# ==============================================
# GOOGLE SHEETS CONNECTION SETUP (BULLETPROOF)
# ==============================================
def get_sheet_connection():
    try:
        if GOOGLE_CREDENTIALS_STR:
            # Render env variable ko direct creds.json file mein write kar do 
            # taaki escape sequence ya json.loads ka koi error na aaye
            with open("creds.json", "w") as f:
                f.write(GOOGLE_CREDENTIALS_STR)
                
        gc = gspread.service_account(filename="creds.json")
        sheet = gc.open(SHEET_NAME).worksheet(SHEET_NAME)
        return sheet
    except Exception as e:
        print(f"Google Sheet Connection Error: {e}")
        return None

def find_station_row(sheet, station):
    station = station.upper().strip()
    for r in range(3, 31):
        val = sheet.cell(r, 2).value
        if val and str(val).upper().strip() == station:
            return {"row": r, "nameCol": "B"}
    for r in range(31, 48):
        val = sheet.cell(r, 13).value
        if val and str(val).upper().strip() == station:
            return {"row": r, "nameCol": "M"}
    for r in range(32, 48):
        val = sheet.cell(r, 3).value
        if val and str(val).upper().strip() == station:
            return {"row": r, "nameCol": "C"}
    return None

# ==============================================
# PF & DIGITAL CASH EXTRACTION
# ==============================================
def extract_pf_from_message(msg):
    if not msg:
        return None
    clean_msg = re.sub(r'PLATFORM\s*(?:TKT|AMT|AMOUNT)?', ' ', msg, flags=re.IGNORECASE)
    if re.search(r'\b(?:P/TKT|PF)\b[^\n]*?(?:NIL|NIL\.)', clean_msg, flags=re.IGNORECASE):
        return 0
    m = re.search(r'\b(?:P/TKT|PF\s*(?:TKT|QTY|QUANTITY|NO\.?|COUNT)?)\s*\.?\s*[-:=]?\s*(\d+)', clean_msg, flags=re.IGNORECASE)
    if m:
        return int(m.group(1))
    m2 = re.search(r'\bPF\s*(?:AMT|AMOUNT)\s*\.?\s*[-:=]?\s*(\d+)', clean_msg, flags=re.IGNORECASE)
    if m2:
        return int(m2.group(1))
    m3 = re.search(r'\bPF\b\s*\.?\s*[-:=]?\s*(\d+)', clean_msg, flags=re.IGNORECASE)
    if m3:
        return int(m3.group(1))
    return None

def message_has_digital_cash(msg):
    return bool(re.search(r'(?:E/CASH|D/CASH|ECASH|DCASH|E-CASH|E\s*CASH|DIGI\s*CASH|E\s*cas)', msg or "", re.IGNORECASE))

def extract_digital_cash_from_message(msg):
    if not msg:
        return 0.0
    total = 0.0
    matches = re.finditer(r'(?:E/CASH|D/CASH|ECASH|DCASH|E-CASH|E\s*CASH|DIGI\s*CASH|E\s*cas)\s*[-:=]?\s*([\d,]+(?:\.\d+)?)', msg, re.IGNORECASE)
    for m in matches:
        val_str = m.group(1).replace(',', '')
        try:
            total += float(val_str)
        except ValueError:
            pass
    return total

def split_message_by_station(msg):
    blocks = {}
    if not msg:
        return blocks
    header_regex = re.compile(r'(?:REVENUE\s+OF|EARNINGS\s+OF|UTS\s+OF|PRS\s+OF)\s+(?:UTS/|PRS/)?([A-Z]{2,6})', re.IGNORECASE)
    matches = []
    for m in header_regex.finditer(msg):
        st = m.group(1).upper()
        if st in ALL_STATIONS:
            matches.append({"station": st, "index": m.start()})
            
    bare_regex = re.compile(r'\b(?:UTS|PRS)/([A-Z]{2,6})\b', re.IGNORECASE)
    for m in bare_regex.finditer(msg):
        st = m.group(1).upper()
        if st in ALL_STATIONS:
            if not any(abs(x["index"] - m.start()) < 5 for x in matches):
                matches.append({"station": st, "index": m.start()})
                
    first_line = msg.split('\n')[0].strip().upper()
    if first_line in ALL_STATIONS and not matches:
        matches.append({"station": first_line, "index": 0})
        
    matches.sort(key=lambda x: x["index"])
    for i in range(len(matches)):
        start = matches[i]["index"]
        end = matches[i+1]["index"] if i + 1 < len(matches) else len(msg)
        st = matches[i]["station"]
        block = msg[start:end]
        blocks[st] = blocks.get(st, "") + "\n" + block
    return blocks

# ==============================================
# GEMINI API CALL (EXACTLY 1 CALL)
# ==============================================
def call_gemini(msg):
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY missing!")
        return None
        
    prompt = f"""You are an expert railway data extraction assistant. Extract numbers into strict JSON.
ALL VALID STATION CODES: {', '.join(ALL_STATIONS)}

RULES:
- Map PRS & UTS fields correctly.
- NET = amount as stated. Never subtract digital payments.
- PF = exact count from explicit line. Ignore PLATFORM TKT.

Return ONLY valid JSON (no markdown):
{{
  "prs": {{"STATION": {{"TKT":0, "PASS":0, "C/TKT":0, "C/PASS":0, "REF":0, "NET":0, "VCH":0, "POS":0, "UPI":0}}}},
  "uts": {{"STATION": {{"TKT":0, "PASS":0, "NET":0, "UPI":0, "PF":0, "MR":0, "MR AMT":0}}}}
}}

MESSAGE:
{msg}
JSON ONLY:"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096}
    }
    
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=20)
        if res.status_code == 200:
            res_data = res.json()
            txt = res_data['candidates'][0]['content']['parts'][0]['text']
            txt = re.sub(r'```json\n?', '', txt, flags=re.IGNORECASE)
            txt = re.sub(r'```\n?', '', txt).strip()
            match = re.search(r'\{[\s\S]*\}', txt)
            if match:
                txt = match.group(0)
            parsed = json.loads(txt)
            parsed["prs"] = parsed.get("prs", {})
            parsed["uts"] = parsed.get("uts", {})
            return parsed
    except Exception as e:
        print(f"Gemini API Error: {e}")
    return None

def apply_post_processing(data, msg):
    if not data:
        return data
    station_blocks = split_message_by_station(msg)
    
    for st, uts_dict in data.get("uts", {}).items():
        block = station_blocks.get(st)
        if block:
            pf_val = extract_pf_from_message(block)
            data["uts"][st]["PF"] = pf_val if pf_val is not None else 0
            if message_has_digital_cash(block):
                dc = extract_digital_cash_from_message(block)
                cur_upi = float(data["uts"][st].get("UPI", 0))
                if dc > 0 and cur_upi < dc:
                    data["uts"][st]["UPI"] = cur_upi + dc

    for st, prs_dict in data.get("prs", {}).items():
        block = station_blocks.get(st)
        if block and message_has_digital_cash(block):
            dc = extract_digital_cash_from_message(block)
            cur_upi = float(data["prs"][st].get("UPI", 0))
            if dc > 0 and cur_upi < dc:
                data["prs"][st]["UPI"] = cur_upi + dc

    return data

# ==============================================
# UPDATE GOOGLE SHEET FUNCTION
# ==============================================
def update_google_sheet(data):
    sheet = get_sheet_connection()
    if not sheet:
        print("❌ Could not connect to Google Sheet.")
        return False

    for st, prs_vals in data.get("prs", {}).items():
        info = find_station_row(sheet, st)
        if not info:
            print(f"⚠️ Station {st} not found in sheet!")
            continue
        row = info["row"]
        for fld, val in prs_vals.items():
            if val > 0 and fld in PRS_COLS:
                col = PRS_COLS[fld]
                curr_val = sheet.cell(row, col).value
                new_val = (float(curr_val) if curr_val not in ["", None] else 0) + float(val)
                sheet.update_cell(row, col, new_val)
                print(f"✅ Updated PRS {st} {fld}: +{val} -> Total: {new_val}")

    for st, uts_vals in data.get("uts", {}).items():
        info = find_station_row(sheet, st)
        if not info:
            print(f"⚠️ Station {st} not found in sheet!")
            continue
        row = info["row"]
        for fld, val in uts_vals.items():
            if fld == "PF" and val == 0:
                continue
            if val > 0:
                col = None
                if info["nameCol"] == "C":
                    col_map = {"TKT": 4, "PASS": 5, "NET": 9, "UPI": 12, "PF": 8, "MR": 9, "MR AMT": 10}
                    col = col_map.get(fld)
                else:
                    col = UTS_COLS_NU.get(fld)
                
                if col:
                    curr_val = sheet.cell(row, col).value
                    new_val = (float(curr_val) if curr_val not in ["", None] else 0) + float(val)
                    sheet.update_cell(row, col, new_val)
                    print(f"✅ Updated UTS {st} {fld}: +{val} -> Total: {new_val}")
    return True

# ==============================================
# WEBHOOK ENDPOINT
# ==============================================
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return "Webhook Live and Running!", 200

    payload = request.get_json(silent=True) or {}
    incoming_msg = ""
    try:
        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                val = change.get("value", {})
                messages = val.get("messages", [])
                for m in messages:
                    if m.get("type") == "text":
                        incoming_msg += m.get("text", {}).get("body", "") + "\n"
    except Exception as e:
        print("Parsing Error:", e)

    incoming_msg = incoming_msg.strip()
    if not incoming_msg:
        return jsonify({"status": "ignored", "reason": "No text body found"}), 200

    print("Processing incoming message with Gemini...")
    data = call_gemini(incoming_msg)

    if data:
        data = apply_post_processing(data, incoming_msg)
        print("Successfully Extracted Data:", json.dumps(data))
        
        # Google Sheet Update Call
        success = update_google_sheet(data)
        
        return jsonify({"status": "success", "sheet_updated": success, "extracted": data}), 200
    else:
        print("⚠️ Gemini returned null.")
        return jsonify({"status": "failed", "message": "Gemini returned null"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
    
