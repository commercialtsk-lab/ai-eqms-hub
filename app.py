import streamlit as st
import pandas as pd
import json
import re
import base64
from datetime import datetime, timedelta
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image
import io
import requests

# ==================== PAGE CONFIG ====================
st.set_page_config(
    page_title="AI EQMS Hub",
    page_icon="🚂",
    layout="wide"
)

# ==================== CREDENTIALS ====================
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
GSPREAD_CREDENTIALS = st.secrets.get("GSPREAD_CREDENTIALS")

if not GEMINI_API_KEY:
    st.error("❌ GEMINI_API_KEY not found in secrets!")
    st.stop()

if not GSPREAD_CREDENTIALS:
    st.error("❌ GSPREAD_CREDENTIALS not found in secrets!")
    st.stop()

SHEET_ID = "1QcS3ZF3YYxSEykG0KiOUuXbTdBh0DMHdMgoqa9t8yrI"
SHEET_NAME = "EQ"
NOTE_SHEET_NAME = "NOTE"

# ==================== CONSTANTS ====================
HEADINGS = [
    'S/N', 'PNR', 'FROM', 'TO', 'BOARDING', 'T/N', 'CLASS', 'DOJ',
    'PASS NAME', 'PASS PH', 'T/BERTHS', 'PURPOSE', 'ADDRESS',
    'DIARY NO', 'RECOMMENDATION', 'DESIGNATION', 'PHONE NUBER',
    'MP/MLA/MR/MINISTER/VIP/VVIP', 'WARRANT NUMBER', 'PROCEESING DATE+TIME',
    'APPLICATION DATE', 'RAILWAY/ZONE/DIVISION', 'PREFERENCE'
]

PRIORITY_ORDER = {
    'MR': 5, 'MINISTER': 5, 'OSD': 5, 'PMO': 5, 'RAIL BOARD': 5,
    'MP': 4, 'MLA': 3, 'VIP': 2, 'VVIP': 2, 'GENERAL': 1, '': 1, 'N/A': 1
}

STATION_MAP = {
    'MXN': 'Mariani Junction', 'KOJ': 'Kokrajhar', 'DBRG': 'Dibrugarh',
    'NTSK': 'New Tinsukia', 'MFP': 'Muzaffarpur', 'KIR': 'Katihar Junction',
    'DEL': 'Delhi', 'NDLS': 'New Delhi', 'HWH': 'Howrah',
    'SDAH': 'Sealdah', 'GHY': 'Guwahati', 'NJP': 'New Jalpaiguri',
    'NBQ': 'New Bongaigaon', 'TBM': 'Tambaram', 'YPR': 'Yesvantpur',
    'SMVB': 'SMVT Bengaluru', 'LKO': 'Lucknow', 'PRYJ': 'Prayagraj',
    'DNR': 'Danapur', 'RE': 'Rewari', 'AY': 'Ayodhya',
    'FKG': 'Furkating', 'KYQ': 'Kamakhya', 'MLDT': 'Malda Town',
    'NNA': 'Naugachia', 'JTI': 'Jatinga', 'CLG': 'Kahalgaon',
    'ROK': 'Rohtak', 'BGP': 'Bhagalpur', 'JMP': 'Jamalpur',
    'JYG': 'Jaynagar', 'BJU': 'Barauni', 'SPJ': 'Samastipur',
    'HJP': 'Hajipur', 'PPTA': 'Patliputra', 'PNBE': 'Patna',
    'ARA': 'Ara', 'BXR': 'Buxar', 'DDU': 'Pt. Deen Dayal Upadhyaya',
    'BSB': 'Varanasi', 'CNB': 'Kanpur Central', 'TDL': 'Tundla',
    'ALJN': 'Aligarh', 'GZB': 'Ghaziabad', 'BKN': 'Bikaner',
    'BME': 'Barmer', 'JU': 'Jodhpur', 'AII': 'Ajmer',
    'JP': 'Jaipur', 'UDZ': 'Udaipur', 'BPL': 'Bhopal',
    'INDB': 'Indore', 'JBP': 'Jabalpur', 'RTM': 'Ratlam',
    'UJN': 'Ujjain', 'BRC': 'Vadodara', 'ADI': 'Ahmedabad',
    'ST': 'Surat', 'BL': 'Valsad', 'PUNE': 'Pune',
    'BCT': 'Mumbai Central', 'CSTM': 'Mumbai CSMT', 'TVC': 'Thiruvananthapuram',
    'ERS': 'Ernakulam', 'MAQ': 'Mangalore', 'SBC': 'Bengaluru City',
    'MAS': 'Chennai Central', 'MS': 'Chennai Egmore', 'BBS': 'Bhubaneswar',
    'VSKP': 'Visakhapatnam', 'HYB': 'Hyderabad', 'SC': 'Secunderabad',
    'BZA': 'Vijayawada', 'GNT': 'Guntur', 'AGC': 'Agra Cantt',
    'AF': 'Agra Fort', 'MTJ': 'Mathura', 'GWL': 'Gwalior',
    'JHS': 'Jhansi', 'BHUJ': 'Bhuj', 'GIMB': 'Gandhidham',
}

# ==================== INITIALIZE SERVICES ====================
@st.cache_resource
def init_gemini():
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel('gemini-2.5-flash')

@st.cache_resource
def init_sheets():
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(GSPREAD_CREDENTIALS, scope)
    return gspread.authorize(creds)

# ==================== HELPER FUNCTIONS ====================
def clean_pnr(pnr):
    if not pnr:
        return ''
    digits = re.sub(r'\D', '', str(pnr))
    return digits if len(digits) == 10 else (digits[-10:] if len(digits) > 10 else '')

def clean_phone(phone):
    if not phone:
        return ''
    digits = re.sub(r'\D', '', str(phone))
    return digits[-10:] if len(digits) >= 10 else ''

def parse_date(date_str):
    if not date_str:
        return ''
    date_str = str(date_str).strip()
    
    if isinstance(date_str, datetime):
        return date_str.strftime("%d-%m-%Y")
    
    match = re.search(r'(\d{1,2})[\/.\-](\d{1,2})[\/.\-](\d{2,4})', date_str)
    if match:
        day, month, year = match.groups()
        day = day.zfill(2)
        month = month.zfill(2)
        if len(year) == 2:
            year = '20' + year
        if int(month) > 12 and int(day) <= 12:
            day, month = month, day
        return f"{day}-{month}-{year}"
    
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%d-%m-%Y")
    except:
        pass
    
    return date_str

def get_station(code):
    if not code:
        return ''
    code = str(code).upper().strip()
    return f"{code} ({STATION_MAP[code]})" if code in STATION_MAP else code

def get_priority(vip_status):
    if not vip_status:
        return 1
    v = str(vip_status).upper().strip()
    if v in PRIORITY_ORDER:
        return PRIORITY_ORDER[v]
    if 'MR' in v or 'MINISTER' in v or 'RAIL BOARD' in v:
        return 5
    if 'MP' in v and 'PMO' not in v:
        return 4
    if 'MLA' in v:
        return 3
    if 'VVIP' in v:
        return 2
    if 'VIP' in v:
        return 1
    return 1

def extract_berth(name_field):
    if not name_field:
        return {'name': '', 'berths': 1}
    name = str(name_field).strip()
    match = re.search(r'^(.+?)(?:\s*\+\s*(\d+))?\s*$', name)
    if match:
        extra = int(match[2]) if match[2] else 0
        return {'name': match[1].strip(), 'berths': 1 + extra}
    return {'name': name, 'berths': 1}

def match_train_number(input_train, note_train):
    if not input_train or not note_train:
        return False
    input_t = str(input_train).strip().upper()
    note_t = str(note_train).strip().upper()
    if input_t == note_t:
        return True
    input_clean = re.sub(r'\s*(DN|UP)$', '', input_t).strip()
    note_clean = re.sub(r'\s*(DN|UP)$', '', note_t).strip()
    return input_clean == note_clean or input_clean == note_t or input_t == note_clean

# ==================== SMART DETECTION FUNCTIONS ====================
def smart_detect_warrant(text):
    if not text:
        return {'warrant': '', 'found': False}
    text = str(text).upper()
    patterns = [
        r'IC[-_\s]*(\d{2,4})',
        r'WARRANT\s*NO\.?\s*[:#]?\s*([A-Z0-9\-]+)',
        r'WARRANT\s*NUMBER\s*[:#]?\s*([A-Z0-9\-]+)',
        r'W[\/\-]?NO\.?\s*[:#]?\s*([A-Z0-9\-]+)',
        r'MP[-_\s]*(\d{2,4})',
        r'MLA[-_\s]*(\d{2,4})'
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            warrant = match.group(1) if len(match.groups()) > 0 else match.group(0)
            if warrant and len(warrant) >= 2:
                return {'warrant': warrant.strip().upper(), 'found': True}
    return {'warrant': '', 'found': False}

def smart_detect_rail_board(text):
    if not text:
        return {'isRailBoard': False}
    text = str(text).upper().replace('\\s+', ' ')
    patterns = [
        r'RAIL\s*BOARD',
        r'OFFICE\s*OF\s*(?:THE\s*)?HON\'?BLE\s*MINISTER\s*RAILWAYS',
        r'OFFICE\s*OF\s*(?:THE\s*)?HONOURABLE\s*MINISTER\s*RAILWAYS',
        r'MINISTER\s*RAILWAYS',
        r'MINISTRY\s*OF\s*RAILWAYS',
        r'RAIL\s*MANTRI',
        r'RAIL\s*BHAWAN'
    ]
    for pattern in patterns:
        if re.search(pattern, text):
            return {'isRailBoard': True}
    
    keywords = ['MINISTER', 'RAILWAYS', 'RAILWAY', 'HONBLE', "HON'BLE", 'RAIL MANTRI', 'OFFICE', 'RAIL', 'BOARD']
    score = sum(1 for kw in keywords if kw in text)
    if score >= 4:
        return {'isRailBoard': True}
    
    if 'OFFICE' in text and 'MINISTER' in text and ('RAILWAYS' in text or 'RAILWAY' in text):
        if text.find('OFFICE') < 50:
            return {'isRailBoard': True}
    
    return {'isRailBoard': False}

def smart_detect_diary(text):
    if not text:
        return {'diary': '', 'found': False}
    text = str(text).upper()
    patterns = [
        r'DIARY\s*NO\.?\s*[:#]?\s*([A-Z0-9\/\-]+)',
        r'DIARY\s*NUMBER\s*[:#]?\s*([A-Z0-9\/\-]+)',
        r'D\/?NO\.?\s*[:#]?\s*([A-Z0-9\/\-]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return {'diary': match.group(1).strip(), 'found': True}
    return {'diary': '', 'found': False}

def smart_detect_vip(text):
    if not text:
        return ''
    text = str(text).upper()
    if 'MINISTER' in text:
        return 'MINISTER'
    if re.search(r'\bMR\b', text):
        return 'MR'
    if re.search(r'\bMP\b', text) and 'PMO' not in text:
        return 'MP'
    if re.search(r'\bMLA\b', text):
        return 'MLA'
    if re.search(r'\bOSD\b', text):
        return 'OSD'
    if re.search(r'\bPMO\b', text):
        return 'PMO'
    if 'VVIP' in text:
        return 'VVIP'
    if 'VIP' in text:
        return 'VIP'
    return ''

def smart_detect_lower_seat(text):
    if not text:
        return False
    text = str(text).upper()
    keywords = ['AGE+', 'AGE +', 'MEDICAL', 'HANDICAP', 'SR CITIZEN', 'SENIOR', 'DISABLED']
    return any(kw in text for kw in keywords)

# ==================== SHEET FUNCTIONS ====================
def get_note_sheet_data(sheet):
    try:
        all_data = sheet.get_all_values()
        if len(all_data) < 2:
            return []
        result = []
        for row in all_data[1:]:
            if row and row[0]:
                result.append({
                    'train': str(row[0]).strip(),
                    'class': str(row[1] if len(row) > 1 else '').strip().upper(),
                    'quota': int(row[2]) if len(row) > 2 and row[2] else 0,
                    'time': str(row[3] if len(row) > 3 else '').strip(),
                    'day': str(row[4] if len(row) > 4 else '').strip().upper(),
                    'from': str(row[5] if len(row) > 5 else '').strip(),
                    'to': str(row[6] if len(row) > 6 else '').strip(),
                    'designation': str(row[7] if len(row) > 7 else '').strip(),
                    'phone': str(row[8] if len(row) > 8 else '').strip()
                })
        return result
    except:
        return []

def get_quota_status(train_num, class_type, doj, note_sheet):
    notes = get_note_sheet_data(note_sheet)
    t = str(train_num).strip()
    c = str(class_type or '').strip().upper()
    
    note_entry = None
    for n in notes:
        if match_train_number(n['train'], t) and n['class'] == c:
            note_entry = n
            break
    
    if not note_entry:
        return {'total': 0, 'used': 0, 'available': 0, 'time': '', 'day': '', 'valid': False}
    
    # Calculate used quota from EQ sheet
    used = 0
    try:
        eq_sheet = init_sheets().open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        eq_data = eq_sheet.get_all_values()
        for row in eq_data[4:]:
            if len(row) > 10:
                row_train = str(row[5] if len(row) > 5 else '').strip()
                row_class = str(row[6] if len(row) > 6 else '').strip().upper()
                row_doj = str(row[7] if len(row) > 7 else '').strip()
                if match_train_number(row_train, t) and row_class == c:
                    if not doj or row_doj == doj or row_doj == parse_date(doj):
                        used += int(row[10]) if row[10] else 1
    except:
        pass
    
    total = note_entry['quota']
    return {
        'total': total,
        'used': used,
        'available': total - used,
        'time': note_entry['time'],
        'day': note_entry['day'],
        'valid': True,
        'designation': note_entry['designation'],
        'phone': note_entry['phone'],
        'from': note_entry['from'],
        'to': note_entry['to']
    }

# ==================== GEMINI SYSTEM PROMPT ====================
def get_system_prompt():
    return """You are an expert at reading railway EQ (Emergency Quota) application forms.

Extract these fields and return ONLY a valid JSON array:

PNR (10 digits), T_N (Train Number 3-5 digits), CLASS (SL/2A/3A/CC/1A/2S),
DOJ (DD-MM-YYYY), FROM, TO, BOARDING, PASS_NAME,
PASS_PH (10 digits), T_BERTHS (number), PURPOSE, ADDRESS,
DIARY_NO, RECOMMENDATION, DESIGNATION, VIP_STATUS,
APPLICATION_DATE, RAILWAY_ZONE, PREFERENCE, PHONE_NUBER, WARRANT_NO

Example:
[
  {
    "PNR": "9085176759",
    "T_N": "15909",
    "CLASS": "SL",
    "DOJ": "28-06-2026",
    "FROM": "NTSK",
    "TO": "DLI",
    "BOARDING": "",
    "PASS_NAME": "SHARIQUE",
    "PASS_PH": "9876543210",
    "T_BERTHS": 1,
    "PURPOSE": "",
    "ADDRESS": "",
    "DIARY_NO": "",
    "RECOMMENDATION": "",
    "DESIGNATION": "",
    "VIP_STATUS": "",
    "APPLICATION_DATE": "",
    "RAILWAY_ZONE": "",
    "PREFERENCE": "General",
    "PHONE_NUBER": "",
    "WARRANT_NO": ""
  }
]

Return ONLY JSON. No explanations."""

# ==================== PROCESS EXTRACTED RECORDS ====================
def process_extracted_records(records):
    if not records:
        return {'records': [], 'count': 0}
    if not isinstance(records, list):
        records = [records]
    
    processed = []
    seen_pnrs = set()
    
    for rec in records:
        pnr = clean_pnr(rec.get('PNR', ''))
        if not pnr or pnr in seen_pnrs:
            continue
        seen_pnrs.add(pnr)
        
        full_text = ' '.join([
            str(rec.get('PURPOSE', '')),
            str(rec.get('ADDRESS', '')),
            str(rec.get('RECOMMENDATION', '')),
            str(rec.get('DESIGNATION', '')),
            str(rec.get('DIARY_NO', '')),
            str(rec.get('PASS_NAME', '')),
            str(rec.get('PASS_PH', '')),
            str(rec.get('PHONE_NUBER', '')),
            str(rec.get('WARRANT_NO', '')),
            str(rec.get('VIP_STATUS', ''))
        ])
        
        rail_board = smart_detect_rail_board(full_text)
        if rail_board['isRailBoard']:
            rec['DIARY_NO'] = 'RAIL BOARD'
            rec['RAILWAY_ZONE'] = 'RAIL BOARD'
            rec['PREFERENCE'] = 'RAIL BOARD'
            rec['VIP_STATUS'] = 'MINISTER'
        
        if not rec.get('WARRANT_NO'):
            warrant = smart_detect_warrant(full_text)
            if warrant['found']:
                rec['WARRANT_NO'] = warrant['warrant']
        
        if not rec.get('DIARY_NO') or rec.get('DIARY_NO') == '-':
            diary = smart_detect_diary(full_text)
            if diary['found']:
                rec['DIARY_NO'] = diary['diary']
        
        if not rec.get('VIP_STATUS'):
            vip = smart_detect_vip(full_text)
            if vip:
                rec['VIP_STATUS'] = vip
        
        if rec.get('PREFERENCE') == 'General' or not rec.get('PREFERENCE'):
            if smart_detect_lower_seat(full_text):
                rec['PREFERENCE'] = 'Lower Seat'
        
        if rec.get('PASS_PH'):
            rec['PASS_PH'] = clean_phone(rec['PASS_PH'])
        if rec.get('PHONE_NUBER'):
            rec['PHONE_NUBER'] = clean_phone(rec['PHONE_NUBER'])
        if rec.get('DOJ'):
            rec['DOJ'] = parse_date(rec['DOJ'])
        if rec.get('APPLICATION_DATE'):
            rec['APPLICATION_DATE'] = parse_date(rec['APPLICATION_DATE'])
        if rec.get('T_N'):
            rec['T_N'] = re.sub(r'\s*(DN|UP)$', '', rec['T_N']).strip()
        
        rec.setdefault('PREFERENCE', 'General')
        rec.setdefault('T_BERTHS', 1)
        rec.setdefault('CLASS', '')
        
        processed.append(rec)
    
    return {'records': processed, 'count': len(processed)}

# ==================== SAVE TO GOOGLE SHEETS ====================
def save_to_sheet(sheet, records):
    existing = []
    try:
        all_values = sheet.get_all_values()
        for row in all_values[4:]:
            if row and len(row) > 1:
                pnr = clean_pnr(row[1])
                if pnr:
                    existing.append(pnr)
    except:
        pass
    
    saved = 0
    skipped = 0
    skip_reasons = []
    current_count = len(sheet.get_all_values()) - 4
    
    for rec in records:
        pnr = clean_pnr(rec.get('PNR', ''))
        
        if not pnr:
            skipped += 1
            skip_reasons.append("No PNR found")
            continue
        
        if pnr in existing:
            skipped += 1
            skip_reasons.append(f"PNR {pnr} already exists")
            continue
        
        current_count += 1
        now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        
        berth_info = extract_berth(rec.get('PASS_NAME', ''))
        pass_name = re.sub(r'\s*\+\s*\d+\s*$', '', str(rec.get('PASS_NAME', '')).strip()) or berth_info['name']
        
        row_data = [
            current_count,
            pnr,
            get_station(rec.get('FROM', '')),
            get_station(rec.get('TO', '')),
            get_station(rec.get('BOARDING', '')),
            rec.get('T_N', '').strip(),
            rec.get('CLASS', '').upper(),
            rec.get('DOJ', ''),
            pass_name,
            rec.get('PASS_PH', ''),
            int(rec.get('T_BERTHS', 1)),
            rec.get('PURPOSE', '').strip(),
            rec.get('ADDRESS', '').strip(),
            rec.get('DIARY_NO', '').strip(),
            rec.get('RECOMMENDATION', '').strip(),
            rec.get('DESIGNATION', '').strip(),
            rec.get('PHONE_NUBER', ''),
            rec.get('VIP_STATUS', '').upper(),
            rec.get('WARRANT_NO', '').strip(),
            now,
            rec.get('APPLICATION_DATE', ''),
            rec.get('RAILWAY_ZONE', '').upper(),
            rec.get('PREFERENCE', 'General')
        ]
        
        sheet.append_row(row_data)
        existing.append(pnr)
        saved += 1
    
    return {'saved': saved, 'skipped': skipped, 'skip_reasons': skip_reasons}

# ==================== QUOTA STATUS FUNCTIONS ====================
def get_all_quota_status(note_sheet):
    notes = get_note_sheet_data(note_sheet)
    result = []
    for n in notes:
        status = get_quota_status(n['train'], n['class'], None, note_sheet)
        result.append({
            'train': n['train'],
            'class': n['class'],
            'total': status['total'],
            'used': status['used'],
            'available': status['available'],
            'time': n['time'],
            'day': n['day'],
            'valid': status['valid'],
            'designation': n['designation'],
            'phone': n['phone'],
            'from': n['from'],
            'to': n['to']
        })
    return result

def get_eq_records_by_train(train_num, doj, eq_sheet):
    try:
        all_data = eq_sheet.get_all_values()
        if len(all_data) < 5:
            return []
        
        records = []
        t = str(train_num).strip()
        
        for row in all_data[4:]:
            if len(row) > 7:
                row_train = str(row[5] if len(row) > 5 else '').strip()
                row_doj = str(row[7] if len(row) > 7 else '').strip()
                if match_train_number(row_train, t):
                    if not doj or row_doj == doj or row_doj == parse_date(doj):
                        records.append({
                            'sno': row[0] if len(row) > 0 else '',
                            'pnr': row[1] if len(row) > 1 else '',
                            'from': row[2] if len(row) > 2 else '',
                            'to': row[3] if len(row) > 3 else '',
                            'boarding': row[4] if len(row) > 4 else '',
                            'train': row[5] if len(row) > 5 else '',
                            'class': row[6] if len(row) > 6 else '',
                            'doj': row[7] if len(row) > 7 else '',
                            'name': row[8] if len(row) > 8 else '',
                            'phone': row[9] if len(row) > 9 else '',
                            'berths': int(row[10]) if len(row) > 10 and row[10] else 1,
                            'vip': row[17] if len(row) > 17 else '',
                            'priority': get_priority(row[17] if len(row) > 17 else '')
                        })
        
        records.sort(key=lambda x: x['priority'], reverse=True)
        return records
    except:
        return []

def get_all_eq_records(eq_sheet):
    try:
        all_data = eq_sheet.get_all_values()
        if len(all_data) < 5:
            return []
        
        records = []
        for row in all_data[4:]:
            if len(row) > 1:
                records.append({
                    'sno': row[0] if len(row) > 0 else '',
                    'pnr': row[1] if len(row) > 1 else '',
                    'from': row[2] if len(row) > 2 else '',
                    'to': row[3] if len(row) > 3 else '',
                    'boarding': row[4] if len(row) > 4 else '',
                    'train': row[5] if len(row) > 5 else '',
                    'class': row[6] if len(row) > 6 else '',
                    'doj': row[7] if len(row) > 7 else '',
                    'name': row[8] if len(row) > 8 else '',
                    'phone': row[9] if len(row) > 9 else '',
                    'berths': int(row[10]) if len(row) > 10 and row[10] else 1,
                    'vip': row[17] if len(row) > 17 else '',
                    'priority': get_priority(row[17] if len(row) > 17 else '')
                })
        return records
    except:
        return []

# ==================== SIDEBAR NAVIGATION ====================
st.sidebar.title("⚡ EQ Master Bot Hub")
menu = st.sidebar.radio(
    "Select View",
    ["📊 Sheets View", "🤖 AI Upload", "📋 EQ Report", "📊 Quota Status"]
)

try:
    gc = init_sheets()
    eq_sheet = gc.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
    note_sheet = gc.open_by_key(SHEET_ID).worksheet(NOTE_SHEET_NAME)
except Exception as e:
    st.error(f"❌ Google Sheets connection error: {str(e)}")
    st.stop()

# ===== MENU 1: SHEETS VIEW =====
if menu == "📊 Sheets View":
    st.title("📊 Google Sheets Data")
    
    sheet_names = ["EQ", "EMAIL_DATA", "NOTE", "DATA", "FINAL", "DATA2"]
    tabs = st.tabs(sheet_names)
    
    for i, tab in enumerate(tabs):
        with tab:
            try:
                ws = gc.open_by_key(SHEET_ID).worksheet(sheet_names[i])
                data = ws.get_all_values()
                
                if data and len(data) > 1:
                    # Make headers unique
                    seen = {}
                    headers = []
                    for h in data[0]:
                        h_str = str(h).strip()
                        if h_str in seen:
                            seen[h_str] += 1
                            headers.append(f"{h_str}_{seen[h_str]}")
                        else:
                            seen[h_str] = 0
                            headers.append(h_str if h_str else "Unnamed")
                    
                    df = pd.DataFrame(data[1:], columns=headers)
                    st.dataframe(df, use_container_width=True, height=400)
                    
                    col1, col2, col3 = st.columns(3)
                    col1.metric("📊 Total Rows", len(df))
                    col2.metric("📋 Columns", len(df.columns))
                    col3.metric("🕐 Updated", datetime.now().strftime("%H:%M"))
                else:
                    st.warning(f"⚠️ Sheet '{sheet_names[i]}' is empty")
            except Exception as e:
                st.error(f"❌ Error loading {sheet_names[i]}: {str(e)}")

# ===== MENU 2: AI UPLOAD =====
elif menu == "🤖 AI Upload":
    st.title("🤖 AI-Powered Data Upload")
    
    upload_type = st.radio("Select upload type:", ["📷 Image", "📄 PDF", "📝 Text", "🎵 Audio"], horizontal=True)
    
    uploaded_file = None
    text_input = None
    
    if upload_type in ["📷 Image", "📄 PDF", "🎵 Audio"]:
        types = {
            "📷 Image": ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'],
            "📄 PDF": ['pdf'],
            "🎵 Audio": ['mp3', 'wav', 'ogg', 'm4a']
        }
        uploaded_file = st.file_uploader(f"Upload {upload_type}", type=types.get(upload_type, []))
    else:
        text_input = st.text_area("Enter text data:", height=150)
    
    if st.button("🚀 Process & Save", use_container_width=True, type="primary"):
        with st.spinner("🔄 Processing with Gemini AI..."):
            try:
                model = init_gemini()
                
                if uploaded_file:
                    file_bytes = uploaded_file.read()
                    file_base64 = base64.b64encode(file_bytes).decode('utf-8')
                    
                    if upload_type == "📷 Image":
                        response = model.generate_content([
                            get_system_prompt(),
                            {"mime_type": "image/jpeg", "data": file_base64}
                        ])
                        st.image(uploaded_file, caption="Uploaded Image", width=300)
                    elif upload_type == "📄 PDF":
                        response = model.generate_content([
                            get_system_prompt(),
                            {"mime_type": "application/pdf", "data": file_base64}
                        ])
                        st.success(f"✅ PDF processed: {uploaded_file.name}")
                    else:
                        response = model.generate_content([
                            get_system_prompt(),
                            {"mime_type": "audio/mpeg", "data": file_base64}
                        ])
                        st.success(f"✅ Audio processed: {uploaded_file.name}")
                elif text_input:
                    response = model.generate_content(get_system_prompt() + f"\n\nINPUT DATA:\n{text_input}")
                else:
                    st.warning("⚠️ Please upload a file or enter text")
                    st.stop()
                
                # Parse JSON
                match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', response.text)
                if match:
                    json_str = match.group().replace("'", '"')
                    records = json.loads(json_str)
                    if isinstance(records, dict):
                        records = [records]
                    
                    result = process_extracted_records(records)
                    
                    if result['count'] > 0:
                        st.success(f"✅ Extracted {result['count']} records!")
                        df = pd.DataFrame(result['records'])
                        st.dataframe(df, use_container_width=True)
                        
                        # Save to sheets
                        save_result = save_to_sheet(eq_sheet, result['records'])
                        
                        if save_result['saved'] > 0:
                            st.success(f"✅ Saved {save_result['saved']} new records to Google Sheets!")
                        else:
                            st.warning("⚠️ No new records saved (duplicates)")
                        
                        if save_result['skipped'] > 0:
                            with st.expander(f"⚠️ Skipped {save_result['skipped']} records"):
                                for reason in save_result['skip_reasons']:
                                    st.text(f"  - {reason}")
                    else:
                        st.warning("⚠️ No valid records extracted")
                else:
                    st.error("❌ Could not parse JSON from response")
                    with st.expander("Raw Response"):
                        st.text(response.text[:500])
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")

# ===== MENU 3: EQ REPORT =====
elif menu == "📋 EQ Report":
    st.title("📋 EQ Report")
    
    all_records = get_all_eq_records(eq_sheet)
    
    if all_records:
        st.write(f"📊 Total Records: {len(all_records)}")
        
        # Search by train
        train_search = st.text_input("🔍 Search by Train Number:", placeholder="e.g., 15909")
        
        if train_search:
            filtered = [r for r in all_records if match_train_number(r['train'], train_search)]
        else:
            filtered = all_records
        
        if filtered:
            df = pd.DataFrame(filtered)
            st.dataframe(df, use_container_width=True)
            
            # Download option
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download as CSV",
                data=csv,
                file_name=f"eq_report_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        else:
            st.info("No records found for this train number")
    else:
        st.info("No EQ records found")

# ===== MENU 4: QUOTA STATUS =====
elif menu == "📊 Quota Status":
    st.title("📊 Quota Status")
    
    quota_data = get_all_quota_status(note_sheet)
    
    if quota_data:
        df = pd.DataFrame(quota_data)
        st.dataframe(df, use_container_width=True)
        
        # Summary
        total_quota = sum(q['total'] for q in quota_data)
        total_used = sum(q['used'] for q in quota_data)
        total_available = sum(q['available'] for q in quota_data)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("📊 Total Quota", total_quota)
        col2.metric("📈 Used", total_used)
        col3.metric("✅ Available", total_available)
    else:
        st.info("No quota data found in NOTE sheet")

# ==================== FOOTER ====================
st.markdown("---")
st.caption("🚂 EQ Master Bot Hub | Powered by Gemini 2.5 Flash | Google Sheets Connected")
