import streamlit as st
import pandas as pd
import json
import re
import base64
import io
import time
import requests
from datetime import datetime
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.service_account import Credentials as GDriveCredentials
from fpdf import FPDF
import plotly.express as px
import plotly.graph_objects as go

# ========== PAGE CONFIG ==========
st.set_page_config(
    page_title="AI EQMS Hub Pro", 
    page_icon="🚂", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# ========== CREDENTIALS ==========
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
GSPREAD_CREDENTIALS = st.secrets.get("GSPREAD_CREDENTIALS")
if not GEMINI_API_KEY or not GSPREAD_CREDENTIALS:
    st.error("❌ Missing credentials!")
    st.stop()

SHEET_ID = "1QcS3ZF3YYxSEykG0KiOUuXbTdBh0DMHdMgoqa9t8yrI"
DRIVE_FOLDER_ID = "1H1gf8WqfoTYFT_pU9WfIDLrHg-NpuUSI"

# ========== SESSION STATE ==========
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'activity_log' not in st.session_state:
    st.session_state.activity_log = []
if 'sidebar_collapsed' not in st.session_state:
    st.session_state.sidebar_collapsed = False
if 'last_uploaded_file' not in st.session_state:
    st.session_state.last_uploaded_file = None
if 'last_uploaded_drive_url' not in st.session_state:
    st.session_state.last_uploaded_drive_url = None
if 'chat_suggestions' not in st.session_state:
    st.session_state.chat_suggestions = [
        "Show me EQ summary", 
        "How many records today?", 
        "Train wise breakup", 
        "Pending EQ requests", 
        "Quota status",
        "PNR status"
    ]

# ========== SERVICES ==========
@st.cache_resource
def init_gemini():
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel('gemini-2.5-flash')

@st.cache_resource
def init_sheets():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(GSPREAD_CREDENTIALS, scope)
    return gspread.authorize(creds)

@st.cache_resource
def init_drive():
    creds_dict = dict(GSPREAD_CREDENTIALS)
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    scopes = ['https://www.googleapis.com/auth/drive.file']
    creds = GDriveCredentials.from_service_account_info(creds_dict, scopes=scopes)
    return build('drive', 'v3', credentials=creds)

# ========== HELPER FUNCTIONS ==========
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
    if isinstance(date_str, datetime):
        return date_str.strftime("%d-%m-%Y")
    date_str = str(date_str).strip()
    match = re.search(r'(\d{1,2})[\/.\-](\d{1,2})[\/.\-](\d{2,4})', date_str)
    if match:
        day, month, year = match.groups()
        day = day.zfill(2); month = month.zfill(2)
        if len(year) == 2: year = '20' + year
        if int(month) > 12 and int(day) <= 12: day, month = month, day
        return f"{day}-{month}-{year}"
    return date_str

def smart_detect_warrant(text):
    if not text:
        return {'warrant': '', 'found': False}
    text = str(text).upper()
    patterns = [
        r'IC[-_\s]*(\d{2,4})',
        r'WARRANT\s*NO\.?\s*[:#]?\s*([A-Z0-9\-]+)',
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
    text = str(text).upper()
    patterns = [r'RAIL\s*BOARD', r'MINISTER\s*RAILWAYS', r'RAIL\s*MANTRI', r'RAIL\s*BHAWAN']
    for pattern in patterns:
        if re.search(pattern, text):
            return {'isRailBoard': True}
    return {'isRailBoard': False}

def smart_detect_diary(text):
    if not text:
        return {'diary': '', 'found': False}
    text = str(text).upper()
    patterns = [r'DIARY\s*NO\.?\s*[:#]?\s*([A-Z0-9\/\-]+)', r'NO\.?\s*[:#]?\s*([A-Z0-9\/\-]+)']
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            diary = match.group(1).strip()
            if len(diary) > 3:
                return {'diary': diary, 'found': True}
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
    return ''

def smart_detect_lower_seat(text):
    if not text:
        return False
    text = str(text).upper()
    keywords = ['LOWER BERTH', 'COUPE', 'WOMAN', 'LOWER SEAT', 'AGE+', 'MEDICAL', 'HANDICAP', 'SR CITIZEN']
    return any(kw in text for kw in keywords)

STATION_MAP = {
    'NTSK': 'New Tinsukia', 'GHY': 'Guwahati', 'NDLS': 'New Delhi',
    'HWH': 'Howrah', 'PNBE': 'Patna', 'BSB': 'Varanasi', 'CNB': 'Kanpur Central',
    'LKO': 'Lucknow', 'DDU': 'Pt. Deen Dayal Upadhyaya', 'GAYA': 'Gaya',
    'MGS': 'Mughalsarai', 'ASN': 'Asansol', 'DHN': 'Dhanbad', 'SC': 'Secunderabad',
    'MAS': 'Chennai Central', 'SBC': 'Bengaluru City', 'CSTM': 'Mumbai CSMT',
    'BCT': 'Mumbai Central', 'PUNE': 'Pune', 'ADI': 'Ahmedabad', 'BRC': 'Vadodara',
    'JP': 'Jaipur', 'AII': 'Ajmer', 'BPL': 'Bhopal', 'INDB': 'Indore',
    'JBP': 'Jabalpur', 'NGP': 'Nagpur', 'HYB': 'Hyderabad', 'BZA': 'Vijayawada',
    'GNT': 'Guntur', 'VSKP': 'Visakhapatnam', 'BBS': 'Bhubaneswar',
    'KGP': 'Kharagpur', 'KOAA': 'Kolkata', 'NJP': 'New Jalpaiguri',
    'NBQ': 'New Bongaigaon', 'KYQ': 'Kamakhya', 'DBRG': 'Dibrugarh',
    'MXN': 'Mariani Junction', 'FKG': 'Furkating', 'JTI': 'Jatinga',
    'MFP': 'Muzaffarpur', 'KIR': 'Katihar Junction', 'DEL': 'Delhi',
    'SDAH': 'Sealdah', 'TBM': 'Tambaram', 'YPR': 'Yesvantpur',
    'SMVB': 'SMVT Bengaluru', 'PRYJ': 'Prayagraj', 'DNR': 'Danapur',
    'RE': 'Rewari', 'AY': 'Ayodhya', 'MLDT': 'Malda Town', 'NNA': 'Naugachia',
    'CLG': 'Kahalgaon', 'ROK': 'Rohtak', 'BGP': 'Bhagalpur', 'JMP': 'Jamalpur',
    'JYG': 'Jaynagar', 'BJU': 'Barauni', 'SPJ': 'Samastipur', 'HJP': 'Hajipur',
    'PPTA': 'Patliputra', 'ARA': 'Ara', 'BXR': 'Buxar', 'TDL': 'Tundla',
    'ALJN': 'Aligarh', 'GZB': 'Ghaziabad', 'BKN': 'Bikaner', 'BME': 'Barmer',
    'JU': 'Jodhpur', 'UDZ': 'Udaipur', 'RTM': 'Ratlam', 'UJN': 'Ujjain',
    'ST': 'Surat', 'BL': 'Valsad', 'TVC': 'Thiruvananthapuram',
    'ERS': 'Ernakulam', 'MAQ': 'Mangalore', 'MS': 'Chennai Egmore',
    'AF': 'Agra Fort', 'MTJ': 'Mathura', 'GWL': 'Gwalior', 'JHS': 'Jhansi',
    'BHUJ': 'Bhuj', 'GIMB': 'Gandhidham', 'ANND': 'Anand', 'ND': 'Nadiad',
    'BH': 'Bharuch', 'NVS': 'Navsari', 'BSR': 'Vasai Road', 'BVI': 'Borivali',
    'DDR': 'Dadar', 'KYN': 'Kalyan', 'NK': 'Nashik Road', 'MMR': 'Manmad',
    'BSL': 'Bhusaval', 'AK': 'Akola', 'BPQ': 'Balharshah', 'SKZR': 'Sirpur Kagaznagar',
    'MCI': 'Manchiryal', 'KZJ': 'Kazipet', 'KCG': 'Kacheguda', 'MBNR': 'Mahbubnagar',
    'TEL': 'Tenali', 'OGL': 'Ongole', 'NLR': 'Nellore', 'GDR': 'Gudur',
    'CGL': 'Chengalpattu', 'VM': 'Villupuram', 'TJ': 'Thanjavur', 'TPJ': 'Tiruchirappalli',
    'MDU': 'Madurai', 'NCJ': 'Nagercoil', 'QLN': 'Kollam', 'ALLP': 'Alappuzha',
    'TCR': 'Thrissur', 'PGT': 'Palakkad', 'CBE': 'Coimbatore', 'SA': 'Salem',
    'JTJ': 'Jolarpettai', 'KPD': 'Katpadi', 'AJJ': 'Arakkonam', 'PER': 'Perambur',
    'KMU': 'Kumbakonam', 'MV': 'Mayiladuthurai', 'CDM': 'Chidambaram',
    'TDPR': 'Tirupadripulyur', 'CTC': 'Cuttack', 'BHC': 'Bhadrak', 'SRC': 'Santragachi',
    'GMO': 'Gomoh', 'KQR': 'Koderma', 'MGS': 'Mughalsarai', 'BBK': 'Barabanki',
    'GD': 'Gonda', 'BST': 'Basti', 'GKP': 'Gorakhpur', 'DEOS': 'Deoria Sadar',
    'DGR': 'Durgapur', 'BWN': 'Bardhaman', 'VZM': 'Vizianagaram', 'SLO': 'Samalkot',
    'RJY': 'Rajahmundry', 'WADI': 'Wadi', 'YG': 'Yadgir', 'RC': 'Raichur',
    'GTL': 'Guntakal', 'DHNE': 'Dhone', 'KRNT': 'Kurnool City', 'GWD': 'Gadwal',
    'PNU': 'Palanpur', 'ABR': 'Abu Road', 'FA': 'Falna', 'MJ': 'Marwar Junction',
    'AWR': 'Alwar', 'SUR': 'Solapur', 'GR': 'Gulbarga'
}
def get_station(code):
    if not code:
        return ''
    code = code.upper().strip()
    return f"{code} ({STATION_MAP[code]})" if code in STATION_MAP else code

def gemini_universal_parser(input_data, input_type, mime_type, progress_callback=None):
    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}'
    
    system_prompt = """
You are TSKEQ Bot's AI extraction engine. You are an EXPERT at reading messy, handwritten, torn, or low-quality railway forms.

=== FIELDS TO EXTRACT (21 fields) ===
PNR, T_N (Train Number), CLASS, DOJ (DD-MM-YYYY), FROM, TO, BOARDING, PASS_NAME, PASS_PH (10 digits), T_BERTHS, PURPOSE, ADDRESS, DIARY_NO, RECOMMENDATION, DESIGNATION, VIP_STATUS, APPLICATION_DATE, RAILWAY_ZONE, PREFERENCE, PHONE_NUBER, WARRANT_NO

=== SPECIAL RULES ===
1. DIARY_NO: Look for "No." or "Diary No." pattern.
2. PREFERENCE: If you see "Lower Berth", "Lower Seat", "Coupe", set PREFERENCE = "Lower Seat".
3. RAIL BOARD: If you see "Office of the Hon'ble Minister Railways", set DIARY_NO="RAIL BOARD", RAILWAY_ZONE="RAIL BOARD".

=== OUTPUT FORMAT ===
Return ONLY a valid JSON array. No explanations.
[
  {
    "PNR": "6307598699",
    "T_N": "20503",
    "CLASS": "1A",
    "DOJ": "12-08-2026",
    "FROM": "HJP",
    "TO": "LKO",
    "BOARDING": "",
    "PASS_NAME": "INDU DUBEY",
    "PASS_PH": "9771425900",
    "T_BERTHS": 1,
    "PURPOSE": "",
    "ADDRESS": "",
    "DIARY_NO": "ECR/CRM/PCCM Cell/EQ/01/2026",
    "RECOMMENDATION": "MRITYUNJAY KUMAR",
    "DESIGNATION": "Secy to PCCM",
    "VIP_STATUS": "",
    "APPLICATION_DATE": "10-08-2026",
    "RAILWAY_ZONE": "ECR",
    "PREFERENCE": "Lower Seat",
    "PHONE_NUBER": "9771425962",
    "WARRANT_NO": ""
  }
]
CRITICAL: Return ONLY the JSON array.
"""
    parts = []
    if input_type in ['image', 'pdf']:
        mime = mime_type or ("image/jpeg" if input_type == 'image' else "application/pdf")
        parts.append({"inline_data": {"mime_type": mime, "data": input_data}})
        parts.append({"text": system_prompt})
    elif input_type == 'audio':
        parts.append({"inline_data": {"mime_type": mime_type or "audio/ogg", "data": input_data}})
        parts.append({"text": system_prompt})
    elif input_type == 'text':
        parts.append({"text": system_prompt + "\n\nINPUT DATA:\n" + input_data})
    else:
        return {'error': 'Unsupported type'}

    if progress_callback:
        progress_callback(30, "Sending to Gemini...")
    
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 16384}
    }
    try:
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, timeout=120)
        if response.status_code != 200:
            return {'error': f'Gemini API Error: {response.status_code}'}
        data = response.json()
        if not data.get('candidates') or not data['candidates'][0].get('content', {}).get('parts'):
            return {'error': 'Empty response from Gemini'}
        response_text = data['candidates'][0]['content']['parts'][0]['text']
        
        if progress_callback:
            progress_callback(60, "Parsing Gemini response...")
        
        json_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', response_text)
        if not json_match:
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
            if json_match:
                json_str = json_match.group(1)
            else:
                if progress_callback:
                    progress_callback(80, "Using fallback extraction...")
                return extract_data_manually(response_text, input_data)
        else:
            json_str = json_match.group(0)
        
        json_str = json_str.replace('```json', '').replace('```', '').strip()
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        json_str = re.sub(r'([a-zA-Z0-9_]+)\s*:', r'"\1":', json_str)
        json_str = json_str.replace("'", '"')
        records = json.loads(json_str)
        if isinstance(records, dict):
            records = [records]
        
        if progress_callback:
            progress_callback(90, "Processing records...")
        
        result = process_extracted_records(records)
        if progress_callback:
            progress_callback(100, "Complete!")
        return result
    except Exception as e:
        return {'error': f'Parser Error: {e}', 'raw': response_text[:500] if 'response_text' in locals() else ''}

def extract_data_manually(response_text, input_data):
    records = []
    text = response_text + ' ' + str(input_data or '')
    text = re.sub(r'\s+', ' ', text).strip()
    pnr_matches = re.findall(r'\b\d{10}\b', text)
    if not pnr_matches:
        return {'error': 'No PNR found'}
    train_matches = re.findall(r'\b\d{3,5}\b', text)
    trains = [t for t in train_matches if len(t) != 10]
    date_matches = re.findall(r'\d{1,2}[\/.\-]\d{1,2}[\/.\-]\d{2,4}', text)
    station_matches = re.findall(r'\b[A-Z]{3,4}\b', text)
    name_matches = re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', text)
    names = [n for n in name_matches if 3 < len(n) < 40]
    phone_matches = re.findall(r'\b\d{10}\b', text)
    diary_match = re.search(r'No\.?\s*[:#]?\s*([A-Z0-9\/\-]+)', text.upper())
    diary = diary_match.group(1).strip() if diary_match else ''
    app_date = ''
    date_pattern = r'Dated\s*[:#]?\s*(\d{1,2}[\/.\-]\d{1,2}[\/.\-]\d{2,4})'
    date_match = re.search(date_pattern, text, re.IGNORECASE)
    if date_match:
        app_date = date_match.group(1)
    lower_seat = any(kw in text.upper() for kw in ['LOWER BERTH', 'COUPE', 'WOMAN', 'LOWER SEAT'])
    is_rail_board = smart_detect_rail_board(text)['isRailBoard']
    max_records = max(len(pnr_matches), len(trains), len(date_matches), len(station_matches), len(names))
    if max_records == 0:
        return {'error': 'No data extracted'}
    for i in range(min(max_records, 5)):
        rec = {
            'PNR': pnr_matches[i] if i < len(pnr_matches) else '',
            'T_N': trains[i] if i < len(trains) else '',
            'CLASS': '',
            'DOJ': parse_date(date_matches[i]) if i < len(date_matches) else '',
            'FROM': station_matches[i] if i < len(station_matches) else '',
            'TO': station_matches[i+1] if i+1 < len(station_matches) else '',
            'BOARDING': '',
            'PASS_NAME': names[i] if i < len(names) else '',
            'PASS_PH': phone_matches[i] if i < len(phone_matches) else '',
            'T_BERTHS': 1,
            'PURPOSE': '',
            'ADDRESS': '',
            'DIARY_NO': diary if diary else ('RAIL BOARD' if is_rail_board else ''),
            'RECOMMENDATION': '',
            'DESIGNATION': '',
            'VIP_STATUS': 'MINISTER' if is_rail_board else '',
            'APPLICATION_DATE': parse_date(app_date) if app_date else '',
            'RAILWAY_ZONE': 'RAIL BOARD' if is_rail_board else '',
            'PREFERENCE': 'Lower Seat' if lower_seat else ('RAIL BOARD' if is_rail_board else 'General'),
            'PHONE_NUBER': '',
            'WARRANT_NO': ''
        }
        if rec['PNR']:
            records.append(rec)
    return process_extracted_records(records)

def process_extracted_records(records):
    cleaned = []
    seen = set()
    for rec in records:
        pnr = clean_pnr(rec.get('PNR', ''))
        if not pnr or pnr in seen:
            continue
        seen.add(pnr)
        full_text = ' '.join([
            str(rec.get('PURPOSE', '')),
            str(rec.get('ADDRESS', '')),
            str(rec.get('RECOMMENDATION', '')),
            str(rec.get('DESIGNATION', '')),
            str(rec.get('DIARY_NO', '')),
            str(rec.get('PASS_NAME', '')),
            str(rec.get('PASS_PH', '')),
            str(rec.get('PHONE_NUBER', ''))
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
        if not rec.get('DIARY_NO') or rec['DIARY_NO'] == '-':
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
        cleaned.append(rec)
    if not cleaned:
        return {'error': 'No valid records extracted'}
    return {'records': cleaned, 'count': len(cleaned)}

# ========== SHEET LOADER ==========
@st.cache_data(ttl=30)
def load_sheet_data_cached(sheet_name, start_row, sheet_id):
    try:
        gc = init_sheets()
        sheet = gc.open_by_key(sheet_id).worksheet(sheet_name)
        all_data = sheet.get_all_values()
        if len(all_data) < start_row:
            return pd.DataFrame()
        if start_row > 1:
            headers_raw = all_data[start_row-2]
        else:
            headers_raw = all_data[0] if all_data else []
        data_rows = all_data[start_row-1:] if start_row <= len(all_data) else []
        seen = {}
        unique_headers = []
        for h in headers_raw:
            h_str = str(h).strip()
            if not h_str:
                h_str = "Unnamed"
            if h_str in seen:
                seen[h_str] += 1
                unique_headers.append(f"{h_str}_{seen[h_str]}")
            else:
                seen[h_str] = 0
                unique_headers.append(h_str)
        df = pd.DataFrame(data_rows, columns=unique_headers[:len(data_rows[0])] if data_rows else [])
        return df
    except Exception as e:
        st.error(f"Error loading {sheet_name}: {e}")
        return pd.DataFrame()

# ========== SHEET CONFIG ==========
SHEET_CONFIG = {
    "EQ": {"start_row": 5, "pnr_col": 1, "train_col": 5, "doj_col": 7},
    "DATA": {"start_row": 3, "pnr_col": 1, "train_col": 5, "doj_col": 7},
    "FINAL": {"start_row": 6, "pnr_col": 7, "train_col": 1, "doj_col": 12},
    "DATA2": {"start_row": 4, "pnr_col": 7, "train_col": 1, "doj_col": 12},
    "EMAIL_DATA": {"start_row": 2, "pnr_col": 7, "train_col": 8, "doj_col": 11},
    "NOTE": {"start_row": 2, "pnr_col": None, "train_col": 0, "doj_col": None}
}

# ========== UPLOAD & SAVE ==========
def upload_to_drive(file_bytes, filename, mime_type):
    try:
        drive_service = init_drive()
        file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=True)
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id,name,webViewLink,size').execute()
        return {
            'success': True, 
            'id': file.get('id'), 
            'name': file.get('name'), 
            'url': file.get('webViewLink'), 
            'size': file.get('size'),
            'print_url': f"https://drive.google.com/file/d/{file.get('id')}/preview"
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

def save_to_sheet(sheet, records):
    try:
        all_data = sheet.get_all_values()
        existing_pnrs = []
        for row in all_data[4:]:
            if row and len(row) > 1:
                pnr = clean_pnr(row[1])
                if pnr:
                    existing_pnrs.append(pnr)
        saved = 0
        skipped = 0
        for rec in records:
            pnr = clean_pnr(rec.get('PNR', ''))
            if not pnr or pnr in existing_pnrs:
                skipped += 1
                continue
            now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            row = [len(all_data)+1, pnr, rec.get('FROM',''), rec.get('TO',''), rec.get('BOARDING',''),
                   rec.get('T_N',''), rec.get('CLASS',''), rec.get('DOJ',''), rec.get('PASS_NAME',''),
                   rec.get('PASS_PH',''), rec.get('T_BERTHS',1), rec.get('PURPOSE',''), rec.get('ADDRESS',''),
                   rec.get('DIARY_NO',''), rec.get('RECOMMENDATION',''), rec.get('DESIGNATION',''),
                   rec.get('PHONE_NUBER',''), rec.get('VIP_STATUS',''), rec.get('WARRANT_NO',''),
                   now, rec.get('APPLICATION_DATE',''), rec.get('RAILWAY_ZONE',''), rec.get('PREFERENCE','General')]
            sheet.append_row(row)
            existing_pnrs.append(pnr)
            saved += 1
            time.sleep(0.15)
        return {'saved': saved, 'skipped': skipped}
    except Exception as e:
        return {'error': str(e)}

# ========== THEME (DeepSeek Perfect Dark/Light) ==========
def apply_theme(dark_mode):
    if dark_mode:
        bg = "#0d1117"
        card_bg = "#161b22"
        text_color = "#f0f6fc"
        text_secondary = "#8b949e"
        border = "#30363d"
        input_bg = "#0d1117"
        primary_bg = "#58a6ff"
        primary_hover = "#79c0ff"
        primary_text = "#ffffff"
        secondary_bg = "#21262d"
        secondary_text = "#c9d1d9"
        header_bg = "#161b22"
        button_text = "#58a6ff"
        button_hover = "#79c0ff"
    else:
        bg = "#f6f8fa"
        card_bg = "#ffffff"
        text_color = "#24292f"
        text_secondary = "#57606a"
        border = "#d0d7de"
        input_bg = "#f6f8fa"
        primary_bg = "#0969da"
        primary_hover = "#0550ae"
        primary_text = "#ffffff"
        secondary_bg = "#f6f8fa"
        secondary_text = "#24292f"
        header_bg = "#f6f8fa"
        button_text = "#0969da"
        button_hover = "#0550ae"
    
    st.markdown(f"""
    <style>
        /* Full App Background */
        .stApp, .main .block-container, .css-1d391kg, .css-18e3th9,
        .stSidebar, .sidebar-content, .css-1d391kg .sidebar-content {{
            background-color: {bg} !important;
        }}
        
        /* Top header */
        header, .st-emotion-cache-1avcm0n, .st-emotion-cache-6qob1r {{
            background-color: {bg} !important;
        }}
        
        /* All Text */
        body, .stMarkdown, p, div, span, h1, h2, h3, h4, h5, h6,
        label, .stTextInput label, .stSelectbox label, .stDateInput label,
        .stNumberInput label, .stTextArea label, .stCheckbox label,
        .stRadio label, .stSlider label, .stFileUploader label,
        .stDataFrame, .stDataFrame div, .stDataFrame span,
        .stTable, .stTable div, .stTable span,
        .stMetric, .stMetric label, .stMetric div,
        .stChatMessage, .stChatMessage div, .stChatMessage p,
        .stSidebar .sidebar-content, .stSidebar .sidebar-content p,
        .stSidebar .sidebar-content div, .stSidebar .sidebar-content label,
        .stExpander, .stExpander .streamlit-expanderHeader,
        .stSelectbox, .stSelectbox div, .stSelectbox span,
        .stTextInput, .stTextInput div, .stTextInput span,
        .stDateInput, .stDateInput div, .stDateInput span,
        .stNumberInput, .stNumberInput div, .stNumberInput span,
        .stTextArea, .stTextArea div, .stTextArea span,
        .stChatInput, .stChatInput div, .stChatInput span,
        .stChatInput input, .stChatInput textarea,
        .stSelectbox select {{
            color: {text_color} !important;
        }}
        
        /* File Uploader - FIXED Dark Mode */
        .stFileUploader label, .stFileUploader div, .stFileUploader span,
        .stFileUploader .st-ae, .stFileUploader .st-bb,
        .stFileUploader .st-b6, .stFileUploader .st-b7,
        .stFileUploader .st-b8, .stFileUploader .st-b9 {{
            color: {text_color} !important;
        }}
        .stFileUploader {{
            background-color: {input_bg} !important;
            border: 1px dashed {border} !important;
            border-radius: 8px !important;
            padding: 8px !important;
        }}
        .stFileUploader .st-ae {{
            color: {text_color} !important;
        }}
        .stFileUploader .st-b6 {{
            color: {text_color} !important;
        }}
        .stFileUploader .st-b7 {{
            color: {text_color} !important;
        }}
        
        /* Open Google Sheet Button */
        .sheet-link-btn {{
            display: inline-block !important;
            padding: 10px 20px !important;
            background: transparent !important;
            color: {button_text} !important;
            border: 1px solid {border} !important;
            border-radius: 8px !important;
            cursor: pointer !important;
            font-weight: 500 !important;
            text-decoration: none !important;
            text-align: center !important;
            width: 100% !important;
        }}
        .sheet-link-btn:hover {{
            color: {button_hover} !important;
            border-color: {button_hover} !important;
        }}
        
        /* Buttons - DeepSeek Style */
        .stButton button, .stButton button p {{
            background: transparent !important;
            color: {button_text} !important;
            border: none !important;
            border-radius: 0 !important;
            font-weight: 500 !important;
            padding: 4px 12px !important;
            transition: all 0.2s ease !important;
            box-shadow: none !important;
            font-size: 0.9rem !important;
            cursor: pointer !important;
        }}
        .stButton button:hover {{
            background: transparent !important;
            color: {button_hover} !important;
            text-decoration: underline !important;
        }}
        .stButton button:disabled {{
            color: {text_secondary} !important;
            cursor: not-allowed !important;
        }}
        
        /* Action Box */
        .action-box {{
            background: {card_bg};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
        }}
        
        /* Cards & Containers */
        .stMetric, .stExpander, .stDataFrame, .stTable,
        .stChatMessage, .stChatInput, .stSelectbox, .stTextInput,
        .stDateInput, .stNumberInput, .stTextArea {{
            background-color: {card_bg} !important;
            border-color: {border} !important;
        }}
        
        /* Data Editor */
        .stDataFrame thead th {{
            background: {header_bg} !important;
            color: {text_color} !important;
            border-bottom: 2px solid {border} !important;
        }}
        .stDataFrame tbody td {{
            background-color: {card_bg} !important;
            color: {text_color} !important;
            border-color: {border} !important;
        }}
        .stDataFrame tbody tr:hover {{
            background-color: {secondary_bg} !important;
        }}
        
        /* Input Fields */
        .stTextInput input, .stSelectbox select, .stDateInput input,
        .stNumberInput input, .stTextArea textarea {{
            background-color: {input_bg} !important;
            color: {text_color} !important;
            border: 1px solid {border} !important;
            border-radius: 6px !important;
        }}
        
        /* Selectbox */
        .stSelectbox select {{
            background-color: {input_bg} !important;
            color: {text_color} !important;
        }}
        .stSelectbox div {{
            background-color: {input_bg} !important;
            color: {text_color} !important;
        }}
        
        /* Borders */
        .stExpander, .stDataFrame, .stTable, .stMetric,
        .stChatMessage, .stChatInput {{
            border: 1px solid {border} !important;
            border-radius: 8px !important;
        }}
        
        /* Footer */
        .pro-footer {{
            color: {text_secondary} !important;
            border-top: 1px solid {border} !important;
            text-align: center !important;
            padding: 20px 0 10px !important;
            margin-top: 30px !important;
        }}
        
        /* Hide row index */
        .stDataFrame thead tr th:first-child,
        .stDataFrame tbody tr th:first-child,
        .stDataFrame tbody tr td:first-child {{
            display: none !important;
        }}
        .stDataFrame thead tr th:nth-child(2),
        .stDataFrame tbody tr td:nth-child(2) {{
            display: table-cell !important;
        }}
        
        /* Toast */
        .stToast {{
            background: {card_bg} !important;
            border-left: 4px solid {primary_bg} !important;
            color: {text_color} !important;
        }}
        
        /* Progress Bar */
        .stProgress .st-bo {{
            background-color: {primary_bg} !important;
        }}
        
        /* Suggestion Chips */
        .suggestion-chip {{
            display: inline-block;
            background: {secondary_bg};
            border: 1px solid {border};
            border-radius: 20px;
            padding: 6px 14px;
            margin: 4px;
            cursor: pointer;
            color: {text_color};
            font-size: 0.85rem;
        }}
        .suggestion-chip:hover {{
            background: {primary_bg};
            color: white;
        }}
        
        /* Sidebar Toggle */
        .sidebar-toggle {{
            background: transparent !important;
            color: {text_color} !important;
            border: none !important;
            border-radius: 8px !important;
            padding: 8px 16px !important;
            font-weight: 500 !important;
            width: 100% !important;
            cursor: pointer !important;
        }}
        .sidebar-toggle:hover {{
            color: {button_hover} !important;
        }}
        
        /* Scrollbar */
        ::-webkit-scrollbar {{
            width: 6px;
            height: 6px;
        }}
        ::-webkit-scrollbar-track {{
            background: {bg};
        }}
        ::-webkit-scrollbar-thumb {{
            background: {primary_bg};
            border-radius: 10px;
        }}
        ::-webkit-scrollbar-thumb:hover {{
            background: {primary_hover};
        }}
        
        @media print {{
            .stApp, .main .block-container {{
                background-color: white !important;
            }}
            .stMetric, .stButton, .stExpander, .stSidebar, .action-box {{
                display: none !important;
            }}
        }}
    </style>
    """, unsafe_allow_html=True)

# ========== SHARE FUNCTION ==========
def share_data(df, sheet_name, selected_rows=None):
    if selected_rows is not None and len(selected_rows) > 0:
        data = df.iloc[selected_rows]
        msg = f"📊 {sheet_name} – Selected {len(data)} rows\n"
        pnr_col = next((c for c in data.columns if 'PNR' in c.upper()), None)
        if pnr_col:
            pnrs = data[pnr_col].tolist()
            msg += f"PNRs: {', '.join(str(p) for p in pnrs[:10])}{'...' if len(pnrs)>10 else ''}\n"
    else:
        data = df
        msg = f"📊 {sheet_name} – Total {len(data)} rows\n"

    pdf = FPDF('L', 'mm', 'A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, f"{sheet_name} Report", ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 8)
    cols = data.columns.tolist()
    if 'Select' in cols:
        cols.remove('Select')
    col_width = 260 / len(cols) if len(cols) > 0 else 20
    for col in cols:
        pdf.cell(col_width, 7, str(col)[:12].encode('latin-1', 'ignore').decode('latin-1'), border=1, align='C')
    pdf.ln()
    pdf.set_font("Arial", '', 7)
    for _, row in data.head(100).iterrows():
        for col in cols:
            val = str(row[col])[:15] if pd.notna(row[col]) else ''
            val_safe = val.encode('latin-1', 'ignore').decode('latin-1')
            pdf.cell(col_width, 6, val_safe, border=1, align='L')
        pdf.ln()
    pdf_bytes = pdf.output(dest='S').encode('latin-1')
    return msg, pdf_bytes

# ========== DASHBOARD ==========
def show_dashboard(df, sheet_name):
    if df.empty:
        st.info("No data to display charts.")
        return
    try:
        total_records = len(df)
        train_col = next((c for c in df.columns if 'T/N' in c.upper() or 'TRAIN' in c.upper()), None)
        unique_trains = df[train_col].nunique() if train_col and train_col in df else 0
        berth_col = next((c for c in df.columns if 'BERTH' in c.upper() or 'T/BERTHS' in c.upper()), None)
        if berth_col and berth_col in df:
            total_berths = pd.to_numeric(df[berth_col], errors='coerce').sum()
        else:
            total_berths = 0

        col1, col2, col3 = st.columns(3)
        col1.metric("📊 Total Records", total_records)
        col2.metric("🚂 Unique Trains", unique_trains)
        col3.metric("💺 Total Berths", int(total_berths) if total_berths else 0)

        if train_col and train_col in df and df[train_col].notna().any():
            fig_pie = px.pie(df, names=train_col, title=f"Train Distribution ({sheet_name})",
                             hole=0.4, color_discrete_sequence=px.colors.qualitative.Set3)
            fig_pie.update_layout(height=350)
            st.plotly_chart(fig_pie, use_container_width=True)

        if berth_col and berth_col in df:
            berth_vals = pd.to_numeric(df[berth_col], errors='coerce').dropna()
            if not berth_vals.empty:
                fig_hist = px.histogram(berth_vals, nbins=10, title="Berths Distribution",
                                        labels={'value': 'Berths', 'count': 'Frequency'},
                                        color_discrete_sequence=['#2d7d46'])
                fig_hist.update_layout(height=350, bargap=0.2)
                st.plotly_chart(fig_hist, use_container_width=True)

        doj_col = next((c for c in df.columns if 'DOJ' in c.upper()), None)
        if doj_col and doj_col in df:
            df_temp = df.copy()
            df_temp['_date'] = pd.to_datetime(df_temp[doj_col], format='%d-%m-%Y', errors='coerce')
            daily_counts = df_temp.groupby('_date').size().reset_index(name='count')
            if not daily_counts.empty:
                fig_line = px.line(daily_counts, x='_date', y='count', title="Daily Records Trend",
                                   labels={'_date': 'Date', 'count': 'Number of Records'},
                                   markers=True, color_discrete_sequence=['#ff6b6b'])
                fig_line.update_layout(height=350)
                st.plotly_chart(fig_line, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not render dashboard: {str(e)}")

# ========== CHAT WITH GEMINI ==========
def get_sheet_context():
    try:
        gc = init_sheets()
        eq_sheet = gc.open_by_key(SHEET_ID).worksheet("EQ")
        all_data = eq_sheet.get_all_values()
        total = len(all_data) - 4
        summary = f"EQ Sheet has {total} records.\n"
        if total > 0:
            sample = all_data[-5:] if len(all_data) > 5 else all_data[4:]
            summary += "Recent records:\n"
            for row in sample:
                if len(row) > 7:
                    summary += f"PNR: {row[1] if len(row)>1 else ''}, Train: {row[5] if len(row)>5 else ''}, DOJ: {row[7] if len(row)>7 else ''}\n"
        return summary
    except Exception as e:
        return "Sheet data temporarily unavailable."

def chat_with_gemini(user_message, chat_history):
    try:
        model = init_gemini()
        context = get_sheet_context()
        
        system_prompt = f"""You are TSKEQ Bot - a railway EQ assistant. You have access to the EQ sheet data.

Sheet Context:
{context}

Instructions:
1. Answer questions based on the sheet data if relevant.
2. For general railway questions, use your knowledge.
3. Be helpful, concise, and friendly.
4. Use emojis occasionally.

Previous conversation:
"""
        for msg in chat_history[-10:]:
            if msg['role'] == 'user':
                system_prompt += f"User: {msg['content']}\n"
            else:
                system_prompt += f"Assistant: {msg['content']}\n"
        
        system_prompt += f"\nUser: {user_message}\nAssistant:"
        
        response = model.generate_content(system_prompt)
        return response.text
    except Exception as e:
        return f"Error: Could not process your request. Please try again later."

# ========== ACTIVITY LOG ==========
def log_activity(action, details):
    timestamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    st.session_state.activity_log.append({
        'timestamp': timestamp,
        'action': action,
        'details': details
    })
    if len(st.session_state.activity_log) > 100:
        st.session_state.activity_log = st.session_state.activity_log[-100:]

# ========== MAIN APP ==========
dark_mode = st.sidebar.toggle("🌙 Dark Mode", value=False)
apply_theme(dark_mode)

# ---- Sidebar Toggle ----
if st.sidebar.button("☰ Toggle Sidebar", use_container_width=True):
    st.session_state.sidebar_collapsed = not st.session_state.sidebar_collapsed

if not st.session_state.sidebar_collapsed:
    # ---- Open Google Sheet Button ----
    sheet_link = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
    st.sidebar.markdown("---")
    st.sidebar.markdown(f'<a href="{sheet_link}" target="_blank" class="sheet-link-btn">📊 Open Google Sheet</a>', unsafe_allow_html=True)
    st.sidebar.markdown("---")

    st.sidebar.title("⚡ AI EQMS Hub Pro")
    st.sidebar.write(f"📅 {datetime.now().strftime('%d-%m-%Y')}")

    try:
        eq_df = load_sheet_data_cached('EQ', 5, SHEET_ID)
        total_records = len(eq_df) if not eq_df.empty else 0
        st.sidebar.write(f"📊 Total Records: {total_records}")
    except:
        st.sidebar.write("📊 Total Records: ?")

    # ---- File Upload ----
    st.sidebar.subheader("📤 Upload File")
    uploaded_file = st.sidebar.file_uploader("Choose file (Image/PDF/Text)", type=['png','jpg','jpeg','pdf','txt'])

    if st.sidebar.button("🚀 Process & Save", use_container_width=True):
        if uploaded_file:
            file_bytes = uploaded_file.read()
            file_type = 'pdf' if uploaded_file.type == 'application/pdf' else 'image'
            
            progress_text = st.sidebar.empty()
            progress_bar = st.sidebar.progress(0)
            
            def update_progress(value, message):
                progress_bar.progress(value)
                progress_text.text(message)
            
            try:
                with st.spinner("Processing..."):
                    b64 = base64.b64encode(file_bytes).decode('utf-8')
                    
                    parse_result = gemini_universal_parser(b64, file_type, uploaded_file.type, update_progress)
                    
                    if 'error' in parse_result:
                        st.sidebar.error(f"Error: {parse_result['error']}")
                    else:
                        st.sidebar.success(f"✅ Extracted {parse_result['count']} records!")
                        
                        if parse_result['records']:
                            with st.sidebar.expander("📋 Extracted Data Preview"):
                                st.dataframe(pd.DataFrame(parse_result['records']))
                        
                        try:
                            gc = init_sheets()
                            eq_sheet = gc.open_by_key(SHEET_ID).worksheet("EQ")
                            save_res = save_to_sheet(eq_sheet, parse_result['records'])
                            
                            if 'error' in save_res:
                                st.sidebar.error(f"Save error: {save_res['error']}")
                            else:
                                st.sidebar.success(f"✅ Saved {save_res['saved']} new records!")
                                
                                drive_res = upload_to_drive(file_bytes, uploaded_file.name, uploaded_file.type)
                                if drive_res['success']:
                                    st.sidebar.success(f"📁 File uploaded to Drive")
                                    st.session_state.last_uploaded_file = uploaded_file.name
                                    st.session_state.last_uploaded_drive_url = drive_res['print_url']
                                else:
                                    st.sidebar.error(f"Drive upload error: {drive_res['error']}")
                                
                                log_activity("File Upload", f"Uploaded {uploaded_file.name}, extracted {parse_result['count']} records")
                                st.cache_data.clear()
                                st.rerun()
                        except Exception as e:
                            st.sidebar.error(f"Sheet error: {e}")
            except Exception as e:
                st.sidebar.error(f"Processing error: {e}")
            finally:
                progress_bar.empty()
                progress_text.empty()
        else:
            st.sidebar.warning("Please select a file.")

    st.sidebar.markdown("---")

    # ---- Activity Log ----
    with st.sidebar.expander("📋 Activity Log", expanded=False):
        if st.session_state.activity_log:
            for log in st.session_state.activity_log[-10:]:
                st.caption(f"🕐 {log['timestamp']}")
                st.caption(f"📌 {log['action']}: {log['details']}")
                st.divider()
        else:
            st.caption("No activity yet")

    st.sidebar.markdown("---")

    # ---- Sheet Selector ----
    sheet_choice = st.sidebar.selectbox("Select Sheet", list(SHEET_CONFIG.keys()))
    config = SHEET_CONFIG[sheet_choice]
    start_row = config["start_row"]

    # ---- Filters ----
    st.sidebar.subheader("🔍 Filters")
    if 'pnr_val' not in st.session_state:
        st.session_state.pnr_val = ''
    if 'train_val' not in st.session_state:
        st.session_state.train_val = ''
    if 'from_val' not in st.session_state:
        st.session_state.from_val = None
    if 'to_val' not in st.session_state:
        st.session_state.to_val = None

    pnr_input = st.sidebar.text_input("PNR (partial)", value=st.session_state.pnr_val, key="pnr_input_widget")
    train_input = st.sidebar.text_input("Train (partial)", value=st.session_state.train_val, key="train_input_widget")
    from_input = st.sidebar.date_input("From DOJ", value=st.session_state.from_val, key="from_input_widget")
    to_input = st.sidebar.date_input("To DOJ", value=st.session_state.to_val, key="to_input_widget")

    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("Apply Filters", use_container_width=True):
            st.session_state.pnr_val = pnr_input
            st.session_state.train_val = train_input
            st.session_state.from_val = from_input
            st.session_state.to_val = to_input
            log_activity("Filter Applied", f"Sheet: {sheet_choice}")
            st.rerun()
    with col2:
        if st.button("Clear Filters", use_container_width=True):
            st.session_state.pnr_val = ''
            st.session_state.train_val = ''
            st.session_state.from_val = None
            st.session_state.to_val = None
            st.rerun()

    # ---- Load and filter data ----
    df_raw = load_sheet_data_cached(sheet_choice, start_row, SHEET_ID)
    filtered_df = df_raw.copy() if not df_raw.empty else pd.DataFrame()

    if not filtered_df.empty:
        pnr_col_idx = config.get("pnr_col")
        train_col_idx = config.get("train_col")
        doj_col_idx = config.get("doj_col")

        if st.session_state.pnr_val and pnr_col_idx is not None and pnr_col_idx < len(filtered_df.columns):
            col_name = filtered_df.columns[pnr_col_idx]
            filtered_df = filtered_df[filtered_df[col_name].astype(str).str.contains(st.session_state.pnr_val, case=False, na=False)]

        if st.session_state.train_val and train_col_idx is not None and train_col_idx < len(filtered_df.columns):
            col_name = filtered_df.columns[train_col_idx]
            filtered_df = filtered_df[filtered_df[col_name].astype(str).str.contains(st.session_state.train_val, case=False, na=False)]

        if (st.session_state.from_val or st.session_state.to_val) and doj_col_idx is not None and doj_col_idx < len(filtered_df.columns):
            col_name = filtered_df.columns[doj_col_idx]
            try:
                filtered_df['_temp'] = pd.to_datetime(filtered_df[col_name], format='%d-%m-%Y', errors='coerce')
                if filtered_df['_temp'].isna().all():
                    filtered_df['_temp'] = pd.to_datetime(filtered_df[col_name], errors='coerce')
            except:
                filtered_df['_temp'] = pd.to_datetime(filtered_df[col_name], errors='coerce')
            if st.session_state.from_val:
                filtered_df = filtered_df[filtered_df['_temp'] >= pd.to_datetime(st.session_state.from_val)]
            if st.session_state.to_val:
                filtered_df = filtered_df[filtered_df['_temp'] <= pd.to_datetime(st.session_state.to_val)]
            filtered_df = filtered_df.drop('_temp', axis=1)

    # ---- Print ----
    st.sidebar.subheader("🖨️ Print")
    if st.sidebar.button("🖨️ Print Sheet", use_container_width=True):
        print_df = filtered_df.copy()
        if 'Select' in print_df.columns:
            print_df = print_df.drop('Select', axis=1)
        html_table = print_df.to_html(index=False, classes='print-table')
        st.components.v1.html(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 20px; }}
                .print-table {{ width: 100%; border-collapse: collapse; font-size: 10px; }}
                .print-table th {{ background-color: #2d7d46; color: white; font-weight: bold; padding: 6px; border: 1px solid #000; text-align: center; }}
                .print-table td {{ padding: 4px; border: 1px solid #000; text-align: left; }}
                @media print {{ body * {{ visibility: visible; }} }}
            </style>
        </head>
        <body>
            <div id="print-area">
                {html_table}
                <p style="text-align:center; margin-top:20px; font-size:12px;">{sheet_choice} Report • {datetime.now().strftime('%d-%m-%Y %H:%M')}</p>
            </div>
            <script>window.onload = function() {{ window.print(); }};</script>
        </body>
        </html>
        """, height=0, scrolling=False)

    st.sidebar.markdown("---")

    # ---- Navigation ----
    view = st.sidebar.radio("View", ["Data Table", "Dashboard", "💬 Chat with Gemini"])

else:
    st.sidebar.markdown("")
    st.sidebar.markdown("")
    st.sidebar.markdown("")
    view = "Data Table"
    sheet_choice = "EQ"
    config = SHEET_CONFIG["EQ"]
    start_row = config["start_row"]
    df_raw = load_sheet_data_cached("EQ", start_row, SHEET_ID)
    filtered_df = df_raw.copy() if not df_raw.empty else pd.DataFrame()

st.markdown("<div class='pro-title'>🚂 AI EQMS Hub</div>", unsafe_allow_html=True)
st.markdown("<div class='pro-subtitle'>Enterprise Quality Management – Pro Edition</div>", unsafe_allow_html=True)
st.markdown("---")

if view == "💬 Chat with Gemini":
    st.subheader("💬 Chat with TSKEQ Bot")
    
    st.markdown("**💡 Suggested Questions:**")
    cols = st.columns(3)
    for i, suggestion in enumerate(st.session_state.chat_suggestions):
        with cols[i % 3]:
            if st.button(suggestion, key=f"suggestion_{i}", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": suggestion})
                st.rerun()
    st.divider()

    # ---- Chat Messages ----
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ---- Chat Input (Below Suggested Questions) ----
    if prompt := st.chat_input("Ask a question..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response = chat_with_gemini(prompt, st.session_state.messages[-30:])
                st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})

    # ---- Clear Chat (Below Chat Input) ----
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

elif view == "Dashboard":
    st.subheader("📊 Dashboard")
    show_dashboard(filtered_df, sheet_choice)

else:
    st.subheader(f"📋 {sheet_choice} – {len(filtered_df)} rows")
    if filtered_df.empty:
        st.info("No data to display. Try adjusting filters or clearing them.")
    else:
        # ---- Page navigation ----
        page_size = st.selectbox("Rows per page", [15, 25, 50, 100], index=1, key="page_size")
        total_pages = max(1, (len(filtered_df) + page_size - 1) // page_size)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            if st.button("◀ Previous", use_container_width=True):
                current_page = st.session_state.get('current_page', 1)
                if current_page > 1:
                    st.session_state.current_page = current_page - 1
                    st.rerun()
        with col2:
            current_page = st.session_state.get('current_page', 1)
            st.write(f"Page {current_page} of {total_pages}")
        with col3:
            if st.button("Next ▶", use_container_width=True):
                current_page = st.session_state.get('current_page', 1)
                if current_page < total_pages:
                    st.session_state.current_page = current_page + 1
                    st.rerun()
        
        page = st.session_state.get('current_page', 1) - 1
        start_idx = page * page_size
        end_idx = min(start_idx + page_size, len(filtered_df))
        page_df = filtered_df.iloc[start_idx:end_idx]

        if not page_df.empty:
            page_df.insert(0, "Select", False)
            edited_page = st.data_editor(
                page_df,
                use_container_width=True,
                height=400,
                column_config={"Select": st.column_config.CheckboxColumn("Select", width="small")},
                key="data_editor"
            )
            selected_indices = edited_page[edited_page["Select"]].index.tolist()

            # ===== ACTION BUTTONS IN ONE BOX =====
            st.markdown('<div class="action-box">', unsafe_allow_html=True)
            st.subheader("⚡ Actions")
            
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                if st.button("💾 Save Edits", use_container_width=True):
                    try:
                        gc = init_sheets()
                        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                        data_to_update = edited_page.drop("Select", axis=1).values.tolist()
                        if data_to_update:
                            num_cols = len(data_to_update[0])
                            start_row_update = start_row + start_idx
                            end_row_update = start_row_update + len(data_to_update) - 1
                            col_letter = chr(64 + num_cols)
                            range_name = f"A{start_row_update}:{col_letter}{end_row_update}"
                            sheet.update(range_name, data_to_update)
                            st.toast("✅ Changes saved!", icon="💾")
                            log_activity("Edit", f"Saved edits in {sheet_choice}")
                            st.cache_data.clear()
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.warning("No data to save.")
                    except Exception as e:
                        st.error(f"Save error: {e}")
            
            with col2:
                if st.button("➕ Add Row", use_container_width=True):
                    try:
                        gc = init_sheets()
                        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                        all_data = sheet.get_all_values()
                        num_cols = len(all_data[0]) if all_data else 1
                        blank_row = [''] * num_cols
                        if len(all_data) >= start_row:
                            next_sn = len(all_data) - start_row + 2
                            blank_row[0] = next_sn
                        sheet.append_row(blank_row)
                        st.toast("✅ Blank row added!", icon="➕")
                        log_activity("Add Row", f"Added row in {sheet_choice}")
                        st.cache_data.clear()
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Add row error: {e}")
            
            with col3:
                if selected_indices:
                    if st.button("🗑️ Delete Selected", use_container_width=True):
                        actual_rows = [start_row + idx for idx in selected_indices]
                        try:
                            gc = init_sheets()
                            sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                            for row_num in sorted(actual_rows, reverse=True):
                                sheet.delete_rows(row_num)
                            st.toast(f"✅ {len(selected_indices)} rows deleted!", icon="🗑️")
                            log_activity("Delete", f"Deleted {len(selected_indices)} rows from {sheet_choice}")
                            st.cache_data.clear()
                            time.sleep(0.5)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Delete error: {e}")
                else:
                    st.button("🗑️ Delete Selected", disabled=True, use_container_width=True)
            
            with col4:
                if selected_indices:
                    if st.button("📤 Share Selected", use_container_width=True):
                        msg, pdf_bytes = share_data(edited_page, sheet_choice, selected_indices)
                        st.download_button("📥 Download PDF", data=pdf_bytes, file_name=f"{sheet_choice}_selected.pdf", mime="application/pdf")
                        wa_link = f"https://api.whatsapp.com/send?text={msg.replace(' ', '%20')}"
                        st.markdown(f'<a href="{wa_link}" target="_blank"><button style="padding:10px 20px; background:#25D366; color:white; border:none; border-radius:8px; cursor:pointer;">📱 Share via WhatsApp</button></a>', unsafe_allow_html=True)
                        log_activity("Share", f"Shared {len(selected_indices)} rows")
                else:
                    st.button("📤 Share Selected", disabled=True, use_container_width=True)
            
            with col5:
                if st.session_state.last_uploaded_drive_url:
                    if st.button("🖨️ Print File", use_container_width=True):
                        st.markdown(f'<script>window.open("{st.session_state.last_uploaded_drive_url}&print=true", "_blank");</script>', unsafe_allow_html=True)
                else:
                    st.button("🖨️ Print File", disabled=True, use_container_width=True)
            
            st.markdown('</div>', unsafe_allow_html=True)

            # ===== QUICK LINKS =====
            st.subheader("🔗 Quick Links")
            col_indices = {'X': 23, 'Y': 24, 'Z': 25, 'AA': 26}
            for idx, row in filtered_df.iterrows():
                links = []
                for label, col_idx in col_indices.items():
                    if len(filtered_df.columns) > col_idx:
                        col_name = filtered_df.columns[col_idx]
                        val = row[col_name]
                        if isinstance(val, str) and 'HYPERLINK' in val:
                            url_match = re.search(r'HYPERLINK\("([^"]+)"', val)
                            if url_match:
                                url = url_match.group(1)
                                if label == 'X':
                                    links.append(f'<a href="{url}" target="_blank">View</a>')
                                elif label == 'Y':
                                    links.append(f'<a href="{url}&print=true" target="_blank">Print</a>')
                                elif label == 'Z':
                                    links.append('📝 Hover')
                                elif label == 'AA':
                                    links.append(f'<a href="{url}" target="_blank">PNR</a>')
                        elif label == 'Z' and val and not isinstance(val, str):
                            links.append(f'📝 {str(val)[:20]}')
                if links:
                    row_num = idx + 1
                    st.markdown(f"**Row {row_num}:** " + " | ".join(links), unsafe_allow_html=True)

            # ===== EXPORT =====
            st.subheader("📄 Export")
            col1, col2 = st.columns(2)
            with col1:
                try:
                    pdf = FPDF('L', 'mm', 'A4')
                    pdf.add_page()
                    pdf.set_font("Arial", 'B', 14)
                    pdf.cell(0, 10, f"{sheet_choice} Report", ln=True, align='C')
                    pdf.ln(5)
                    pdf.set_font("Arial", 'B', 8)
                    cols = filtered_df.columns.tolist()
                    if 'Select' in cols:
                        cols.remove('Select')
                    col_width = 260 / len(cols) if len(cols) > 0 else 20
                    for col in cols:
                        pdf.cell(col_width, 7, str(col)[:12].encode('latin-1', 'ignore').decode('latin-1'), border=1, align='C')
                    pdf.ln()
                    pdf.set_font("Arial", '', 7)
                    for _, row in filtered_df.head(200).iterrows():
                        for col in cols:
                            val = str(row[col])[:15] if pd.notna(row[col]) else ''
                            val_safe = val.encode('latin-1', 'ignore').decode('latin-1')
                            pdf.cell(col_width, 6, val_safe, border=1, align='L')
                        pdf.ln()
                    pdf_bytes = pdf.output(dest='S').encode('latin-1')
                    st.download_button("📥 Download PDF", data=pdf_bytes, file_name=f"{sheet_choice}.pdf", mime="application/pdf", use_container_width=True)
                except Exception as e:
                    st.warning(f"PDF error: {e}")
            with col2:
                csv = filtered_df.drop('Select', axis=1).to_csv(index=False).encode('utf-8') if 'Select' in filtered_df.columns else filtered_df.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download CSV", data=csv, file_name=f"{sheet_choice}.csv", mime="text/csv", use_container_width=True)

# ===== FOOTER =====
st.markdown("""
<div class='pro-footer'>
    🚂 AI EQMS Hub Pro – Created by Sharique<br>
    © 2026 All Rights Reserved
</div>
""", unsafe_allow_html=True)
