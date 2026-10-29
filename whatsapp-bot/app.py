import os
import re
import math
import json
import requests

# ==============================================
# CONFIGURATION & CONSTANTS
# ==============================================
CONFIG_SHEET_NAME = "UTS&PRS"
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID", "6336489158")

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
# TELEGRAM HELPER
# ==============================================
def send_message(text, chat_id=CHAT_ID):
    if not BOT_TOKEN or not chat_id:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending Telegram message: {e}")

# ==============================================
# PF EXTRACTION — STRICT (explicit PF lines only)
# ==============================================
def extract_pf_quantity(value, context=None):
    if value is None:
        return 0
    val_str = str(value).strip()
    if not val_str or re.match(r'^(nil|null|0)$', val_str, re.IGNORECASE):
        return 0
    numbers = re.findall(r'\d+', val_str)
    if not numbers:
        return 0
    first_number = int(numbers[0])
    if context and re.search(r'(TKT|QTY|QUANTITY|NO\.?|COUNT)', context, re.IGNORECASE):
        return first_number
    if context and re.search(r'(AMOUNT|AMT)', context, re.IGNORECASE):
        return round(first_number / 10)
    if first_number >= 10:
        return round(first_number / 10)
    return first_number

def extract_pf_from_message(msg):
    if not msg:
        return None
    
    clean_msg = re.sub(r'PLATFORM\s*(?:TKT|AMT|AMOUNT)?', ' ', msg, flags=re.IGNORECASE)
    
    if re.search(r'\b(?:P\/TKT|PF)\b[^\n]*?(?:NIL|NIL\.)', clean_msg, re.IGNORECASE):
        return 0
    
    m = re.search(r'\b(?:P\/TKT|PF\s*(?:TKT|QTY|QUANTITY|NO\.?|COUNT))\s*\.?\s*[-:=]?\s*(\d+)', clean_msg, re.IGNORECASE)
    if m:
        return int(m.group(1))
    
    m2 = re.search(r'\bPF\s*(?:AMT|AMOUNT)\s*\.?\s*[-:=]?\s*(\d+)', clean_msg, re.IGNORECASE)
    if m2:
        return round(int(m2.group(1)) / 10)
    
    m3 = re.search(r'\bPF\b\s*\.?\s*[-:=]?\s*(\d+)', clean_msg, re.IGNORECASE)
    if m3:
        n = int(m3.group(1))
        return round(n / 10) if n >= 10 else n
    
    return None

# ==============================================
# DIGITAL CASH
# ==============================================
def message_has_digital_cash(msg):
    return bool(re.search(r'(?:E\/CASH|D\/CASH|ECASH|DCASH|E-CASH|E\s*CASH|DIGI\s*CASH)', msg or "", re.IGNORECASE))

def extract_digital_cash_from_message(msg):
    if not msg:
        return 0.0
    total = 0.0
    pattern = r'(?:E\/CASH|D\/CASH|ECASH|DCASH|E-CASH|E\s*CASH|DIGI\s*CASH)\s*[-:=]?\s*([\d,]+(?:\.\d+)?)'
    for match in re.finditer(pattern, msg, re.IGNORECASE):
        try:
            num = float(match.group(1).replace(',', ''))
            total += num
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
    
    header_regex = r'(?:REVENUE\s+OF|EARNINGS\s+OF|REVENUE\s+of|Earnings\s+Of|UTS\s+OF|PRS\s+OF|UTS\s+of|PRS\s+of)\s+(?:UTS\/|PRS\/)?([A-Z]{2,6})'
    matches = []
    
    for m in re.finditer(header_regex, msg, re.IGNORECASE):
        st = m.group(1).upper()
        if st in ALL_STATIONS:
            matches.append({'station': st, 'index': m.start()})
            
    bare_regex = r'\b(?:UTS|PRS)\/([A-Z]{2,6})\b'
    for m in re.finditer(bare_regex, msg, re.IGNORECASE):
        st = m.group(1).upper()
        if st in ALL_STATIONS:
            close_dup = any(abs(x['index'] - m.start()) < 5 for x in matches)
            if not close_dup:
                matches.append({'station': st, 'index': m.start()})
                
    first_line = msg.split("\n")[0].strip().upper()
    if first_line in ALL_STATIONS and len(matches) == 0:
        matches.append({'station': first_line, 'index': 0})
        
    matches.sort(key=lambda x: x['index'])
    
    for i in range(len(matches)):
        start = matches[i]['index']
        end = matches[i+1]['index'] if i + 1 < len(matches) else len(msg)
        block = msg[start:end]
        st = matches[i]['station']
        blocks[st] = blocks.get(st, "") + "\n" + block
        
    return blocks

# ==============================================
# FIND STATION ROW IN GOOGLE SHEET
# ==============================================
def get_station_row(sheet, station):
    if not station:
        return None
    station = str(station).upper().strip()
    
    col_b_vals = sheet.range("B3:B30")
    for cell in col_b_vals:
        if cell.value and str(cell.value).upper().strip() == station:
            return {"row": cell.row, "nameCol": "B"}
            
    col_m_vals = sheet.range("M31:M47")
    for cell in col_m_vals:
        if cell.value and str(cell.value).upper().strip() == station:
            return {"row": cell.row, "nameCol": "M"}
            
    col_c_vals = sheet.range("C32:C47")
    for cell in col_c_vals:
        if cell.value and str(cell.value).upper().strip() == station:
            return {"row": cell.row, "nameCol": "C"}
            
    return None

# ==============================================
# GEMINI API CALL (Environment Variable Based)
# ==============================================
def call_gemini(msg):
    if not GEMINI_API_KEY:
        print("Gemini API key not found in environment variables!")
        return None

    prompt = f"""You are a railway data entry expert. Extract numbers from this message EXACTLY as specified.

STATIONS: {", ".join(ALL_STATIONS)}

FIELD MAPPING (PRS section):
- TKT = T/TKT, TKT, TKTs (ticket count)
- PASS = T/Pass, PASS (passenger count)
- C/TKT = C/TKT, CANTKT, C/T (cancelled tickets)
- C/PASS = C/PASS, CANPASS, C/P (cancelled passengers)
- NET = Net Cash, NETCASH, AMT, NET. KEEP AS STATED — do NOT subtract anything.
- REF = sum of REFUND + UPIREFUND + Digi REFUND + e-Refund + POS REF + RFD + UPI RFD
- UPI = UPI, QR, Digi CASH, E-Cash, E/CASH, D/CASH (digital)
- VCH = VOUCHER, VCH, VOU
- POS = POS

FIELD MAPPING (UTS section):
- TKT = TKT, TKTs, J/TKT (main UTS ticket count) — NOT "PLATFORM TKT"
- PASS = PASS, J/Pass
- NET = AMOUNT, J/Amount, NET CASH, Cash. KEEP AS STATED — do NOT subtract anything.
- UPI = UPI, QR, ECASH, E/CASH, D/CASH, E cas, E-Cash (digital)
- PF = ONLY from explicit PF line: "PF TKT-82", "P/TKT=267", "PF Qty-52", "PF-60", "PF. NIL"
- MR = MR count (e.g. "MR 16=17570" → MR=16, MR AMT=17570)
- MR AMT = MR amount

⚠️ CRITICAL RULES:
1. PLATFORM TKT and PLATFORMAMT are platform tickets — IGNORE THEM COMPLETELY. They are NOT PF, NOT TKT, NOT anything. Skip them.
2. PLATFORM TKT=52 does NOT mean PF=52. PF must come only from a line that literally says "PF" or "P/TKT".
3. If a station's UTS section has NO "PF" or "P/TKT" line → PF = 0.
4. If a station's UTS section says "PF NIL" or "PF TKTs - NIL" → PF = 0.
5. "PF TKT-82" or "P/TKT=267" → PF = 82 or 267 (count, no division).
6. "PF-60" or "PF AMT-60" → PF = 6 (rupees ÷ 10).
7. NET = amount exactly as stated. NEVER subtract E/CASH, D/CASH, UPI, Digi, or ECASH from NET.
8. SUM all refund types into REF for PRS.
9. Ignore nil, null, zero, blank.
10. Multi-station: separate PRS and UTS entry per station, each with independent PF.

Return ONLY this JSON (no markdown, no extra text):
{{
  "prs": {{"STATION": {{"TKT":0, "PASS":0, "C/TKT":0, "C/PASS":0, "REF":0, "NET":0, "VCH":0, "POS":0, "UPI":0}}}},
  "uts": {{"STATION": {{"TKT":0, "PASS":0, "NET":0, "UPI":0, "PF":0, "MR":0, "MR AMT":0}}}}
}}

MESSAGE:
{msg}

JSON ONLY:"""

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096}
        }
        res = requests.post(url, json=payload, timeout=30)
        if res.status_code == 200:
            txt = res.json()['candidates'][0]['content']['parts'][0]['text']
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
        print(f"Gemini Error: {e}")
    return None

# ==============================================
# POST-PROCESSING — SMART PER-STATION
# ==============================================
def apply_post_processing(data, msg):
    if not data:
        return data
    
    station_blocks = split_message_by_station(msg)
    
    for st in list(data.get("uts", {}).keys()):
        block = station_blocks.get(st)
        if not block:
            cleaned = extract_pf_quantity(data["uts"][st].get("PF"), None)
            data["uts"][st]["PF"] = cleaned
            continue
            
        pf_from_block = extract_pf_from_message(block)
        if pf_from_block is None:
            data["uts"][st]["PF"] = 0
        else:
            data["uts"][st]["PF"] = pf_from_block
            
    for st in list(data.get("uts", {}).keys()):
        block = station_blocks.get(st)
        if block and message_has_digital_cash(block):
            dc = extract_digital_cash_from_message(block)
            cur = float(data["uts"][st].get("UPI", 0))
            if dc > 0 and cur < dc:
                data["uts"][st]["UPI"] = cur + dc

    for st in list(data.get("prs", {}).keys()):
        block = station_blocks.get(st)
        if block and message_has_digital_cash(block):
            dc = extract_digital_cash_from_message(block)
            cur = float(data["prs"][st].get("UPI", 0))
            if dc > 0 and cur < dc:
                data["prs"][st]["UPI"] = cur + dc

    return data

# ==============================================
# UPDATE SHEET — GROUPED PER STATION
# ==============================================
def update_sheet(data, spreadsheet, chat_id=CHAT_ID):
    if not data:
        return "❌ No data"
        
    data["prs"] = data.get("prs", {})
    data["uts"] = data.get("uts", {})
    
    try:
        sheet = spreadsheet.worksheet(CONFIG_SHEET_NAME)
    except Exception:
        return "❌ Sheet not found"
        
    send_message("🧠 **Processing...**", chat_id)
    
    reply_lines = []
    errors = []
    refund_total = 0
    pf_total = 0
    upi_total = 0
    
    station_order = []
    seen = {}
    for st in data["prs"]:
        if st not in seen:
            seen[st] = True
            station_order.append(st)
    for st in data["uts"]:
        if st not in seen:
            seen[st] = True
            station_order.append(st)
            
    for st in station_order:
        info = get_station_row(sheet, st)
        if not info:
            errors.append(st)
            continue
            
        had_data = False
        
        # --- PRS ---
        if st in data["prs"]:
            upd_p = []
            for fld, raw_val in data["prs"][st].items():
                val = float(raw_val or 0)
                if val > 0 and fld in PRS_COLS:
                    col = PRS_COLS[fld]
                    curr_val = sheet.cell(info["row"], col).value
                    try:
                        curr = float(curr_val) if curr_val else 0.0
                    except ValueError:
                        curr = 0.0
                    sheet.update_cell(info["row"], col, curr + val)
                    upd_p.append(f"{fld}: +{int(val) if val.is_integer() else val}")
                    had_data = True
                    if fld == "REF":
                        refund_total += val
                    if fld == "UPI":
                        upi_total += val
            if upd_p:
                reply_lines.append(f"📌 **{st} (PRS)**: {', '.join(upd_p)}")

        # --- UTS ---
        if st in data["uts"]:
            upd_u = []
            for fld, raw_val in data["uts"][st].items():
                val = float(raw_val or 0)
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
                        curr_val = sheet.cell(info["row"], col).value
                        try:
                            curr = float(curr_val) if curr_val else 0.0
                        except ValueError:
                            curr = 0.0
                        sheet.update_cell(info["row"], col, curr + val)
                        upd_u.append(f"{fld}: +{int(val) if val.is_integer() else val}")
                        had_data = True
                        if fld == "PF":
                            pf_total += val
                        if fld == "UPI":
                            upi_total += val
            if upd_u:
                reply_lines.append(f"📌 **{st} (UTS)**: {', '.join(upd_u)}")
                
        if had_data:
            reply_lines.append(f"✅ **{st} complete**")
            
    if not reply_lines and not errors:
        return "🌿 No numbers found."
        
    reply = "✅ **Updated!**\n\n" + "\n".join(reply_lines)
    if refund_total:
        reply += f"\n\n💰 Refunds: ₹{refund_total}"
    if pf_total:
        reply += f"\n🎫 Total PF: {int(pf_total)} PF"
    if upi_total:
        reply += f"\n💳 Digital (UPI): ₹{upi_total}"
    if errors:
        reply += f"\n\n⚠️ Unknown: {', '.join(errors)}"
        
    return reply

# ==============================================
# MAIN PROCESS FUNCTION
# ==============================================
def process_and_update(msg, spreadsheet, chat_id=CHAT_ID):
    print(f"📨 {msg}")
    data = call_gemini(msg)
    if not data:
        return "🌿 Couldn't extract. Send like:\n`MRG TKT-15 PASS-24 AMT-26055 Digi-15435 Digi REF-1020 PF-6`"
        
    data = apply_post_processing(data, msg)
    result_reply = update_sheet(data, spreadsheet, chat_id)
    return result_reply
    
