import os
import re
import json
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==============================================
# ENVIRONMENT VARIABLES (RENDER ENV SE FETCH HOGA)
# ==============================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SHEET_NAME = os.environ.get("SHEET_NAME", "UTS&PRS")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

GEMINI_MODEL = "gemini-2.5-flash"

ALL_STATIONS = [
    "DBRT","DBRG","NTSK","TSK","MXN","JTTN","SRTN","SLGR","GLGT","MRHT",
    "NAM","NHK","FKG","AGI","DJG","LEDO","MRG","DBY","MJN","TTB","BOJ",
    "BFD","SPK","CHB","SPTR","DMC","MZS","NLP","LBI","BGND","LMY","SRPN",
    "SMCP","TQM","GOM","BDLN","CKW","LHL","DKM","PNT","TII","LXA","SFR",
    "SLX","NMT","ROING","TEZU","CGF","DMGN","TNGN","NSBG","KOWN","NCH",
    "CMA","KXL","BBGN","BLMR","NMGY","KRHT"
]

# ==============================================
# PF EXTRACTION — STRICT (NO DIVISION BY 10)
# ==============================================
def extract_pf_quantity(value, context):
    if value is None:
        return 0
    str_val = str(value).strip()
    if str_val == "" or re.match(r'^(nil|null|0)$', str_val, re.IGNORECASE):
        return 0
    numbers = re.findall(r'\d+', str_val)
    if not numbers:
        return 0
    first_num = int(numbers[0])
    # Exact quantity direct bitha do, /10 nahi karna hai
    return first_num

def extract_pf_from_message(msg):
    if not msg:
        return None
    clean_msg = re.sub(r'PLATFORM\s*(?:TKT|AMT|AMOUNT)?', ' ', msg, flags=re.IGNORECASE)
    if re.search(r'\b(?:P/TKT|PF)\b[^\n]*?(?:NIL|NIL\.)', clean_msg, flags=re.IGNORECASE):
        return 0
    m = re.search(r'\b(?:P/TKT|PF\s*(?:TKT|QTY|QUANTITY|NO\.?|COUNT)?)\s*\.?\s*[-:=]?\s*(\d+)', clean_msg, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m2 = re.search(r'\bPF\s*(?:AMT|AMOUNT)\s*\.?\s*[-:=]?\s*(\d+)', clean_msg, re.IGNORECASE)
    if m2:
        return int(m2.group(1))
    m3 = re.search(r'\bPF\b\s*\.?\s*[-:=]?\s*(\d+)', clean_msg, re.IGNORECASE)
    if m3:
        return int(m3.group(1))
    return None

# ==============================================
# DIGITAL CASH EXTRACTION
# ==============================================
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

# ==============================================
# SPLIT MESSAGE INTO PER-STATION BLOCKS
# ==============================================
def split_message_by_station(msg):
    blocks = {}
    if not msg:
        return blocks
    header_regex = re.compile(r'(?:REVENUE\s+OF|EARNINGS\s+OF|REVENUE\s+of|Earnings\s+Of|UTS\s+OF|PRS\s+OF|UTS\s+of|PRS\s+of)\s+(?:UTS/|PRS/)?([A-Z]{2,6})', re.IGNORECASE)
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
# DETAILED GEMINI PROMPT (NATURAL & PRECISE)
# ==============================================
def call_gemini(msg):
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY environment variable missing!")
        return None
        
    prompt = f"""You are an expert railway data extraction and parsing assistant. Your task is to accurately read incoming railway earnings and revenue messages (which can be pasted, forwarded, single-station, or multi-station) and extract numeric values into a strict JSON format.

ALL VALID STATION CODES: {', '.join(ALL_STATIONS)}

DETAILED FIELD MAPPING INSTRUCTIONS:

1. PRS SECTION MAPPING:
- TKT: Map from T/TKT, TKT, TKTs, Total Tickets.
- PASS: Map from T/Pass, PASS, Passengers.
- C/TKT: Map from C/TKT, CANTKT, C/T, Cancelled Tickets.
- C/PASS: Map from C/PASS, CANPASS, C/P, Cancelled Passengers.
- NET: Map from Net Cash, NETCASH, AMT, NET, Cash. KEEP AS STATED — do NOT subtract digital payments from net.
- REF: Sum of all refund types including REFUND, UPIREFUND, Digi REFUND, e-Refund, POS REF, RFD, UPI RFD.
- UPI: Map from UPI, QR, Digi CASH, E-Cash, E/CASH, D/CASH.
- VCH: Map from VOUCHER, VCH, VOU.
- POS: Map from POS.

2. UTS SECTION MAPPING:
- TKT: Map from TKT, TKTs, J/TKT, TTL (EXCLUDE "PLATFORM TKT").
- PASS: Map from PASS, J/Pass, PsgF.
- NET: Map from AMOUNT, J/Amount, NET CASH, Cash, Total. KEEP AS STATED — do NOT subtract digital payments.
- UPI: Map from UPI, QR, ECASH, E/CASH, D/CASH, E cas, E-Cash.
- PF: Extract ONLY from explicit platform fee lines like "PF TKT-82", "P/TKT=267", "PF Qty-52", "PF-60", "PF. NIL". Keep count as exact quantity (NO division by 10).
- MR: Map MR count (e.g., "MR 16=17570" → MR=16).
- MR AMT: Map MR amount (e.g., "MR 16=17570" → MR AMT=17570).

CRITICAL EXTRACTION RULES:
1. PLATFORM TKT and PLATFORMAMT must be completely ignored. They are NOT Platform Fees and NOT Tickets.
2. NET must be taken exactly as stated in the message. Never subtract E/CASH, UPI, or digital cash.
3. If a station contains only PRS data, do not include an empty UTS block for it, and vice versa.
4. Handle flexible formatting, typos, varying spacing, and shorthand notations seamlessly.

Return ONLY a valid JSON object matching this exact structure (no markdown fences, no extra text):
{{
  "prs": {{
    "STATION_NAME": {{
      "TKT": 0, "PASS": 0, "C/TKT": 0, "C/PASS": 0, "REF": 0, "NET": 0, "VCH": 0, "POS": 0, "UPI": 0
    }}
  }},
  "uts": {{
    "STATION_NAME": {{
      "TKT": 0, "PASS": 0, "NET": 0, "UPI": 0, "PF": 0, "MR": 0, "MR AMT": 0
    }}
  }}
}}

INCOMING MESSAGE TO PARSE:
{msg}

JSON OUTPUT ONLY:"""

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

# ==============================================
# POST-PROCESSING (RE-VERIFICATION)
# ==============================================
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

    # Sirf ek hi bar Gemini API call hoga
    data = call_gemini(incoming_msg)

    if data:
        data = apply_post_processing(data, incoming_msg)
        print("Successfully Extracted Data:", json.dumps(data))
        return jsonify({"status": "success", "extracted": data}), 200
    else:
        print("⚠️ Gemini returned null.")
        return jsonify({"status": "failed", "message": "Gemini returned null"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
    
