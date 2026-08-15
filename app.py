import streamlit as st
import pandas as pd
import json
import re
import base64
import io
import time
import math
import requests
import urllib.parse
from datetime import datetime, timedelta
from collections import Counter
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from fpdf import FPDF
import plotly.express as px

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
    st.error("❌ Missing credentials! Please check secrets.toml")
    st.stop()

SHEET_ID = "1QcS3ZF3YYxSEykG0KiOUuXbTdBh0DMHdMgoqa9t8yrI"
DRIVE_FOLDER_ID = "1H1gf8WqfoTYFT_pU9WfIDLrHg-NpuUSI"

# ========== SESSION STATE ==========
defaults = {
    'messages': [],
    'activity_log': [],
    'last_uploaded_file': None,
    'last_uploaded_drive_url': None,
    'last_uploaded_view_url': None,
    'last_uploaded_print_url': None,
    'last_refresh': time.time(),
    'chat_suggestions': [
        "Show me EQ summary",
        "How many records today?",
        "Train wise breakup",
        "Pending EQ requests",
        "Quota status",
        "PNR status"
    ],
    'dark_mode': False,
    'current_page': 1,
    'pnr_val': '',
    'train_val': '',
    'from_val': None,
    'to_val': None,
    'upload_success': False,
    'last_upload_time': None,
    'selected_sheet': "EQ",
}

for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ========== HEADINGS ==========
HEADINGS = [
    'S/N', 'PNR', 'FROM', 'TO', 'BOARDING', 'T/N', 'CLASS', 'DOJ',
    'PASS NAME', 'PASS PH', 'T/BERTHS', 'PURPOSE', 'ADDRESS',
    'DIARY NO', 'RECOMMENDATION', 'DESIGNATION', 'PHONE NUBER',
    'MP/MLA/MR/MINISTER/VIP/VVIP', 'WARRANT NUMBER', 'PROCEESING DATE+TIME',
    'APPLICATION DATE', 'RAILWAY/ZONE/DIVISION', 'PREFERENCE',
    'LINK (Click to Open)', 'PRINT (A4 Size)', 'VIEW (Hover Details)', 'PNR STATUS LINK'
]

# ========== STATION MAP ==========
STATION_MAP = {
    'NTSK': 'New Tinsukia', 'GHY': 'Guwahati', 'NDLS': 'New Delhi', 'HWH': 'Howrah',
    'PNBE': 'Patna', 'BSB': 'Varanasi', 'CNB': 'Kanpur Central', 'LKO': 'Lucknow',
    'DDU': 'Pt. Deen Dayal Upadhyaya', 'GAYA': 'Gaya', 'MGS': 'Mughalsarai',
    'ASN': 'Asansol', 'DHN': 'Dhanbad', 'SC': 'Secunderabad', 'MAS': 'Chennai Central',
    'SBC': 'Bengaluru City', 'CSTM': 'Mumbai CSMT', 'BCT': 'Mumbai Central',
    'PUNE': 'Pune', 'ADI': 'Ahmedabad', 'BRC': 'Vadodara', 'JP': 'Jaipur',
    'AII': 'Ajmer', 'BPL': 'Bhopal', 'INDB': 'Indore', 'JBP': 'Jabalpur',
    'NGP': 'Nagpur', 'HYB': 'Hyderabad', 'BZA': 'Vijayawada', 'GNT': 'Guntur',
    'VSKP': 'Visakhapatnam', 'BBS': 'Bhubaneswar', 'KGP': 'Kharagpur',
    'KOAA': 'Kolkata', 'NJP': 'New Jalpaiguri', 'NBQ': 'New Bongaigaon',
    'KYQ': 'Kamakhya', 'DBRG': 'Dibrugarh', 'MXN': 'Mariani Junction',
    'FKG': 'Furkating', 'JTI': 'Jatinga', 'MFP': 'Muzaffarpur',
    'KIR': 'Katihar Junction', 'DEL': 'Delhi', 'SDAH': 'Sealdah',
    'TBM': 'Tambaram', 'YPR': 'Yesvantpur', 'SMVB': 'SMVT Bengaluru',
    'PRYJ': 'Prayagraj', 'DNR': 'Danapur', 'RE': 'Rewari', 'AY': 'Ayodhya',
    'MLDT': 'Malda Town', 'NNA': 'Naugachia', 'CLG': 'Kahalgaon', 'ROK': 'Rohtak',
    'BGP': 'Bhagalpur', 'JMP': 'Jamalpur', 'JYG': 'Jaynagar', 'BJU': 'Barauni',
    'SPJ': 'Samastipur', 'HJP': 'Hajipur', 'PPTA': 'Patliputra', 'ARA': 'Ara',
    'BXR': 'Buxar', 'TDL': 'Tundla', 'ALJN': 'Aligarh', 'GZB': 'Ghaziabad',
    'BKN': 'Bikaner', 'BME': 'Barmer', 'JU': 'Jodhpur', 'UDZ': 'Udaipur',
    'RTM': 'Ratlam', 'UJN': 'Ujjain', 'ST': 'Surat', 'BL': 'Valsad',
    'TVC': 'Thiruvananthapuram', 'ERS': 'Ernakulam', 'MAQ': 'Mangalore',
    'MS': 'Chennai Egmore', 'AF': 'Agra Fort', 'MTJ': 'Mathura', 'GWL': 'Gwalior',
    'JHS': 'Jhansi', 'BHUJ': 'Bhuj', 'GIMB': 'Gandhidham', 'ANND': 'Anand',
    'ND': 'Nadiad', 'BH': 'Bharuch', 'NVS': 'Navsari', 'BSR': 'Vasai Road',
    'BVI': 'Borivali', 'DDR': 'Dadar', 'KYN': 'Kalyan', 'NK': 'Nashik Road',
    'MMR': 'Manmad', 'BSL': 'Bhusaval', 'AK': 'Akola', 'BPQ': 'Balharshah',
    'SKZR': 'Sirpur Kagaznagar', 'MCI': 'Manchiryal', 'KZJ': 'Kazipet',
    'KCG': 'Kacheguda', 'MBNR': 'Mahbubnagar', 'TEL': 'Tenali', 'OGL': 'Ongole',
    'NLR': 'Nellore', 'GDR': 'Gudur', 'CGL': 'Chengalpattu', 'VM': 'Villupuram',
    'TJ': 'Thanjavur', 'TPJ': 'Tiruchirappalli', 'MDU': 'Madurai',
    'NCJ': 'Nagercoil', 'QLN': 'Kollam', 'ALLP': 'Alappuzha', 'TCR': 'Thrissur',
    'PGT': 'Palakkad', 'CBE': 'Coimbatore', 'SA': 'Salem', 'JTJ': 'Jolarpettai',
    'KPD': 'Katpadi', 'AJJ': 'Arakkonam', 'PER': 'Perambur', 'KMU': 'Kumbakonam',
    'MV': 'Mayiladuthurai', 'CDM': 'Chidambaram', 'TDPR': 'Tirupadripulyur',
    'CTC': 'Cuttack', 'BHC': 'Bhadrak', 'SRC': 'Santragachi', 'GMO': 'Gomoh',
    'KQR': 'Koderma', 'BBK': 'Barabanki', 'GD': 'Gonda', 'BST': 'Basti',
    'GKP': 'Gorakhpur', 'DEOS': 'Deoria Sadar', 'DGR': 'Durgapur',
    'BWN': 'Bardhaman', 'VZM': 'Vizianagaram', 'SLO': 'Samalkot',
    'RJY': 'Rajahmundry', 'WADI': 'Wadi', 'YG': 'Yadgir', 'RC': 'Raichur',
    'GTL': 'Guntakal', 'DHNE': 'Dhone', 'KRNT': 'Kurnool City', 'GWD': 'Gadwal',
    'PNU': 'Palanpur', 'ABR': 'Abu Road', 'FA': 'Falna', 'MJ': 'Marwar Junction',
    'AWR': 'Alwar', 'SUR': 'Solapur', 'GR': 'Gulbarga', 'CSMT': 'Mumbai CSMT',
    'AGC': 'Agra Cantt', 'KOJ': 'Kokrajhar'
}

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
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes)
    return build('drive', 'v3', credentials=creds)

# ========== HELPERS ==========
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
    multi_match = re.search(r'(\d{1,2})[\/\.\-](\d{1,2})[\/\.\-](\d{2,4})', date_str)
    if multi_match:
        day, month, year = multi_match.groups()
        day = day.zfill(2)
        month = month.zfill(2)
        if len(year) == 2:
            year = '20' + year
        if int(month) > 12 and int(day) <= 12:
            day, month = month, day
        return f"{day}-{month}-{year}"
    return date_str

def get_station(code):
    if not code:
        return ''
    code = str(code).upper().strip()
    return f"{code} ({STATION_MAP[code]})" if code in STATION_MAP else code

def extract_hyperlink_url(cell_value):
    if not cell_value:
        return None
    val = str(cell_value)
    match = re.search(r'HYPERLINK\("([^"]+)"', val, re.IGNORECASE)
    if match:
        return match.group(1)
    if val.startswith('http'):
        return val
    return None

def is_expired(doj_str):
    if not doj_str:
        return False
    parsed = parse_date(doj_str)
    if not parsed:
        return False
    try:
        doj_dt = datetime.strptime(parsed, "%d-%m-%Y")
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return doj_dt < today
    except Exception:
        return False

def col_index_to_letter(idx):
    result = ""
    while idx > 0:
        idx, remainder = divmod(idx - 1, 26)
        result = chr(65 + remainder) + result
    return result

def get_sunset_time():
    month = datetime.now().month
    if month in [5, 6, 7]:
        return 18, 45
    elif month in [11, 12, 1]:
        return 17, 15
    elif month in [2, 3, 10]:
        return 18, 0
    else:
        return 18, 30

def is_flag_time():
    now = datetime.now()
    sunset_h, sunset_m = get_sunset_time()
    start = now.replace(hour=6, minute=0, second=0, microsecond=0)
    end = now.replace(hour=sunset_h, minute=sunset_m, second=0, microsecond=0)
    return start <= now <= end

def log_activity(action: str):
    st.session_state.activity_log.append({
        'timestamp': datetime.now().strftime("%H:%M:%S"),
        'action': action
    })
    if len(st.session_state.activity_log) > 50:
        st.session_state.activity_log = st.session_state.activity_log[-50:]

# ========== SHEET CONFIG ==========
SHEET_CONFIG = {
    "EQ": {"start_row": 5, "pnr_col": 1, "train_col": 5, "doj_col": 7},
    "DATA": {"start_row": 3, "pnr_col": 1, "train_col": 5, "doj_col": 7},
    "FINAL": {"start_row": 6, "pnr_col": 7, "train_col": 1, "doj_col": 12},
    "DATA2": {"start_row": 4, "pnr_col": 7, "train_col": 1, "doj_col": 12},
    "EMAIL_DATA": {"start_row": 2, "pnr_col": 7, "train_col": 8, "doj_col": 11},
    "NOTE": {"start_row": 2, "pnr_col": None, "train_col": 0, "doj_col": None}
}

# ========== LOAD SHEET DATA ==========
@st.cache_data(ttl=30, show_spinner=False)
def load_sheet_data_cached(sheet_name, sheet_id):
    try:
        gc = init_sheets()
        sheet = gc.open_by_key(sheet_id).worksheet(sheet_name)
        all_data = sheet.get_all_values()
        config = SHEET_CONFIG.get(sheet_name, {"start_row": 1})
        start_row = config["start_row"]
        if len(all_data) < start_row:
            return pd.DataFrame()

        headers_raw = all_data[start_row - 2] if start_row > 1 else (all_data[0] if all_data else [])
        data_rows = all_data[start_row - 1:] if start_row <= len(all_data) else []

        seen = {}
        unique_headers = []
        for h in headers_raw:
            h_str = str(h).strip() or "Unnamed"
            if h_str in seen:
                seen[h_str] += 1
                unique_headers.append(f"{h_str}_{seen[h_str]}")
            else:
                seen[h_str] = 0
                unique_headers.append(h_str)

        if not data_rows:
            return pd.DataFrame()

        max_cols = len(unique_headers)
        padded_rows = []
        for i, row in enumerate(data_rows):
            padded = list(row) + [''] * (max_cols - len(row))
            padded_rows.append(padded[:max_cols])

        df = pd.DataFrame(padded_rows, columns=unique_headers)
        df['_sheet_row'] = list(range(start_row, start_row + len(df)))
        return df
    except Exception as e:
        st.error(f"Error loading {sheet_name}: {e}")
        return pd.DataFrame()

# ========== GEMINI EXTRACTION ==========
def gemini_universal_parser(input_data, input_type, mime_type, progress_callback=None):
    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}'

    system_prompt = """
You are TSKEQ Bot's AI extraction engine. You are an EXPERT at reading messy, handwritten, torn, or low-quality railway forms.

=== FIELDS TO EXTRACT (21 fields) ===
PNR, T_N (Train Number), CLASS, DOJ (DD-MM-YYYY), FROM, TO, BOARDING, PASS_NAME, PASS_PH (10 digits), T_BERTHS, PURPOSE, ADDRESS, DIARY_NO, RECOMMENDATION, DESIGNATION, VIP_STATUS, APPLICATION_DATE, RAILWAY_ZONE, PREFERENCE, PHONE_NUBER, WARRANT_NO

=== SPECIAL RULES ===
1. DIARY_NO: Look for "No." or "Diary No." pattern. Preserve as-is.
2. PREFERENCE: If you see "Lower Berth", "Lower Seat", "Coupe", set PREFERENCE = "Lower Seat".
3. RAIL BOARD: If you see "Office of the Hon'ble Minister Railways", set DIARY_NO="RAIL BOARD", RAILWAY_ZONE="RAIL BOARD".
4. DOJ: Extract date in DD-MM-YYYY format.
5. Multiple entries: Extract ALL valid entries.

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
    date_matches = re.findall(r'\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4}', text)
    station_matches = re.findall(r'\b[A-Z]{3,4}\b', text)
    name_matches = re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', text)
    names = [n for n in name_matches if 3 < len(n) < 40]
    phone_matches = re.findall(r'\b\d{10}\b', text)
    diary_match = re.search(r'No\.?\s*[:#]?\s*([A-Z0-9\/\-]+)', text.upper())
    diary = diary_match.group(1).strip() if diary_match else ''
    app_date = ''
    date_pattern = r'Dated\s*[:#]?\s*(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4})'
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
            rec['T_N'] = re.sub(r'\s*(DN|UP)$', '', str(rec['T_N'])).strip()
        rec.setdefault('PREFERENCE', 'General')
        rec.setdefault('T_BERTHS', 1)
        rec.setdefault('CLASS', '')
        cleaned.append(rec)
    if not cleaned:
        return {'error': 'No valid records extracted'}
    return {'records': cleaned, 'count': len(cleaned)}

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
            warrant = match.group(1) if match.groups() else match.group(0)
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

# ========== DRIVE UPLOAD ==========
def upload_to_drive(file_bytes, filename, mime_type):
    try:
        drive_service = init_drive()
        file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=True)
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,name,webViewLink,size'
        ).execute()
        file_id = file.get('id')
        return {
            'success': True,
            'id': file_id,
            'name': file.get('name'),
            'url': file.get('webViewLink'),
            'size': file.get('size'),
            'view_url': f"https://drive.google.com/file/d/{file_id}/view",
            'print_url': f"https://drive.google.com/file/d/{file_id}/preview",
            'download_url': f"https://drive.google.com/uc?export=download&id={file_id}"
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ========== SAVE TO SHEET ==========
def save_to_sheet(sheet, records):
    try:
        all_data = sheet.get_all_values()
        existing_pnrs = []
        start_row = 5
        for row in all_data[start_row-1:]:
            if row and len(row) > 1:
                pnr = clean_pnr(row[1])
                if pnr:
                    existing_pnrs.append(pnr)
        saved = 0
        skipped = 0
        next_sn = len(all_data) - start_row + 2
        for rec in records:
            pnr = clean_pnr(rec.get('PNR', ''))
            if not pnr or pnr in existing_pnrs:
                skipped += 1
                continue
            now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            row = [
                next_sn, pnr, rec.get('FROM', ''), rec.get('TO', ''), rec.get('BOARDING', ''),
                rec.get('T_N', ''), rec.get('CLASS', ''), rec.get('DOJ', ''), rec.get('PASS_NAME', ''),
                rec.get('PASS_PH', ''), rec.get('T_BERTHS', 1), rec.get('PURPOSE', ''), rec.get('ADDRESS', ''),
                rec.get('DIARY_NO', ''), rec.get('RECOMMENDATION', ''), rec.get('DESIGNATION', ''),
                rec.get('PHONE_NUBER', ''), rec.get('VIP_STATUS', ''), rec.get('WARRANT_NO', ''),
                now, rec.get('APPLICATION_DATE', ''), rec.get('RAILWAY_ZONE', ''), rec.get('PREFERENCE', 'General')
            ]
            sheet.append_row(row)
            existing_pnrs.append(pnr)
            next_sn += 1
            saved += 1
            time.sleep(0.12)
        return {'saved': saved, 'skipped': skipped}
    except Exception as e:
        return {'error': str(e)}

# ========== GEMINI CHAT ==========
def get_sheet_context():
    try:
        gc = init_sheets()
        eq_sheet = gc.open_by_key(SHEET_ID).worksheet("EQ")
        all_data = eq_sheet.get_all_values()
        total = max(0, len(all_data) - 4)
        summary = f"EQ Sheet has {total} records.\n"
        if total > 0:
            sample = all_data[-5:] if len(all_data) > 5 else all_data[4:]
            summary += "Recent records:\n"
            for row in sample:
                if len(row) > 7:
                    summary += f"PNR: {row[1] if len(row)>1 else ''}, Train: {row[5] if len(row)>5 else ''}, DOJ: {row[7] if len(row)>7 else ''}\n"
        return summary
    except Exception:
        return "Sheet data temporarily unavailable."

def chat_with_gemini(user_message, chat_history):
    try:
        model = init_gemini()
        context = get_sheet_context()

        system_prompt = f"""You are TSKEQ Bot - a professional railway EQ assistant. You have access to the EQ sheet data.

Sheet Context:
{context}

Instructions:
1. Answer questions based on the sheet data if relevant.
2. For general railway questions, use your knowledge.
3. Be helpful, concise, and professional yet friendly.
4. Use emojis sparingly and appropriately.
5. Respond naturally as if you are having a conversation.
6. You can discuss any topic - not just railways.

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
        return f"⚠️ Error: Could not process your request. Please try again later. ({str(e)})"

# ========== THEME ==========
def apply_theme(dark_mode: bool):
    st.session_state.dark_mode = dark_mode
    if dark_mode:
        bg = "#0d1117"
        card_bg = "#161b22"
        text_color = "#e6edf3"
        text_secondary = "#8b949e"
        border = "#30363d"
        input_bg = "#0d1117"
        accent = "#58a6ff"
        accent_hover = "#79c0ff"
        success = "#3fb950"
        danger = "#f85149"
        warning = "#d29922"
        chat_user_bg = "#1f2937"
        chat_assistant_bg = "#21262d"
        button_bg = "#21262d"
        button_text = "#e6edf3"
        button_border = "#30363d"
        hover_bg = "#30363d"
    else:
        bg = "#f6f8fa"
        card_bg = "#ffffff"
        text_color = "#1f2328"
        text_secondary = "#656d76"
        border = "#d0d7de"
        input_bg = "#ffffff"
        accent = "#0969da"
        accent_hover = "#0550ae"
        success = "#1a7f37"
        danger = "#cf222e"
        warning = "#9a6700"
        chat_user_bg = "#ddf4ff"
        chat_assistant_bg = "#f6f8fa"
        button_bg = "#f6f8fa"
        button_text = "#1f2328"
        button_border = "#d0d7de"
        hover_bg = "#eaeef2"

    css = f"""
    <style>
        /* Base */
        .stApp {{
            background-color: {bg} !important;
        }}
        [data-testid="stSidebar"] {{
            background-color: {card_bg} !important;
            border-right: 1px solid {border} !important;
        }}
        [data-testid="stSidebar"] .stMarkdown p,
        [data-testid="stSidebar"] .stMarkdown div,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] .stTextInput label,
        [data-testid="stSidebar"] .stSelectbox label,
        [data-testid="stSidebar"] .stDateInput label,
        [data-testid="stSidebar"] .stNumberInput label,
        [data-testid="stSidebar"] .stTextArea label,
        [data-testid="stSidebar"] .stRadio label {{
            color: {text_color} !important;
        }}
        header[data-testid="stHeader"] {{
            background-color: {card_bg} !important;
            border-bottom: 1px solid {border} !important;
        }}

        /* Text */
        h1, h2, h3, h4, h5, h6,
        .stMarkdown p, .stMarkdown div, .stMarkdown span,
        .stMarkdown h1, .stMarkdown h2, .stMarkdown h3,
        [data-testid="stMetricLabel"],
        [data-testid="stMetricValue"],
        .stCaption {{
            color: {text_color} !important;
        }}

        /* Inputs */
        .stTextInput input, .stNumberInput input,
        .stDateInput input, .stTextArea textarea,
        .stSelectbox > div > div > div {{
            background-color: {input_bg} !important;
            color: {text_color} !important;
            border: 1px solid {border} !important;
            border-radius: 8px !important;
        }}

        /* Buttons - high contrast */
        .stButton > button {{
            background-color: {button_bg} !important;
            color: {button_text} !important;
            border: 1px solid {button_border} !important;
            border-radius: 8px !important;
            font-weight: 500 !important;
            transition: all 0.15s ease !important;
        }}
        .stButton > button:hover {{
            background-color: {accent} !important;
            color: white !important;
            border-color: {accent} !important;
        }}
        .stButton > button:disabled {{
            opacity: 0.45 !important;
            cursor: not-allowed !important;
        }}
        .stButton > button[kind="primary"] {{
            background-color: {accent} !important;
            color: white !important;
            border-color: {accent} !important;
        }}
        .stButton > button[kind="primary"]:hover {{
            background-color: {accent_hover} !important;
            border-color: {accent_hover} !important;
        }}

        /* File uploader */
        .stFileUploader {{
            background-color: {input_bg} !important;
            border: 2px dashed {border} !important;
            border-radius: 12px !important;
            padding: 16px !important;
        }}
        .stFileUploader:hover {{
            border-color: {accent} !important;
        }}
        .stFileUploader label {{
            color: {text_secondary} !important;
        }}

        /* Dataframe */
        .stDataFrame, [data-testid="stDataFrame"] {{
            background-color: {card_bg} !important;
            border: 1px solid {border} !important;
            border-radius: 8px !important;
        }}
        .stDataFrame th {{
            background-color: {card_bg} !important;
            color: {text_color} !important;
            border-bottom: 2px solid {border} !important;
            font-weight: 600 !important;
        }}
        .stDataFrame td {{
            background-color: {card_bg} !important;
            color: {text_color} !important;
            border-color: {border} !important;
        }}

        /* Expander */
        .stExpander {{
            background-color: {card_bg} !important;
            border: 1px solid {border} !important;
            border-radius: 8px !important;
        }}
        .streamlit-expanderHeader {{
            color: {text_color} !important;
            font-weight: 600 !important;
        }}

        /* Chat */
        .stChatMessage {{
            background-color: {card_bg} !important;
            border: 1px solid {border} !important;
            border-radius: 12px !important;
            padding: 12px !important;
            margin-bottom: 8px !important;
        }}
        .stChatInput {{
            background-color: {input_bg} !important;
            border: 1px solid {border} !important;
            border-radius: 12px !important;
        }}
        .stChatInput input {{
            color: {text_color} !important;
        }}

        /* Metric cards */
        [data-testid="stMetric"] {{
            background-color: {card_bg} !important;
            border: 1px solid {border} !important;
            border-radius: 10px !important;
            padding: 14px !important;
        }}

        /* Tabs */
        .stTabs [data-baseweb="tab-list"] {{
            background-color: {card_bg} !important;
            border-bottom: 1px solid {border} !important;
        }}
        .stTabs [data-baseweb="tab"] {{
            color: {text_secondary} !important;
        }}
        .stTabs [data-baseweb="tab-highlight"] {{
            background-color: {accent} !important;
        }}

        /* Scrollbar */
        ::-webkit-scrollbar {{
            width: 8px;
            height: 8px;
        }}
        ::-webkit-scrollbar-track {{
            background: {bg};
        }}
        ::-webkit-scrollbar-thumb {{
            background: {border};
            border-radius: 10px;
        }}
        ::-webkit-scrollbar-thumb:hover {{
            background: {accent};
        }}

        /* Custom cards */
        .action-box {{
            background: {card_bg};
            border: 1px solid {border};
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
        }}
        .file-card {{
            background: {card_bg};
            border: 1px solid {border};
            border-radius: 12px;
            padding: 16px;
            margin: 12px 0;
        }}
        .file-card-title {{
            color: {text_color};
            font-weight: 600;
            font-size: 1rem;
            margin-bottom: 4px;
        }}
        .file-card-meta {{
            color: {text_secondary};
            font-size: 0.85rem;
            margin-bottom: 12px;
        }}
        .pro-footer {{
            color: {text_secondary} !important;
            border-top: 1px solid {border} !important;
            text-align: center !important;
            padding: 20px 0 10px !important;
            margin-top: 30px !important;
        }}
        .sheet-link-btn {{
            display: inline-block !important;
            padding: 10px 20px !important;
            background: {button_bg} !important;
            color: {accent} !important;
            border: 1px solid {button_border} !important;
            border-radius: 8px !important;
            text-decoration: none !important;
            text-align: center !important;
            width: 100% !important;
            transition: all 0.15s !important;
            font-weight: 500 !important;
        }}
        .sheet-link-btn:hover {{
            background: {accent} !important;
            color: white !important;
            border-color: {accent} !important;
        }}
        .status-pill {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 500;
        }}
        .status-live {{
            background: rgba(63, 185, 80, 0.15);
            color: {success};
            border: 1px solid {success};
        }}
        * {{
            transition: background-color 0.2s ease, color 0.2s ease, border-color 0.2s ease;
        }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# ========== WHATSAPP SHARE ==========
def build_whatsapp_message(sheet_name, selected_count, pnrs):
    now_str = datetime.now().strftime("%d-%m-%Y %H:%M")
    msg = f"📊 *{sheet_name}* — {selected_count} rows selected\n🕐 {now_str}"
    if pnrs:
        pnr_text = ", ".join(str(p) for p in pnrs[:15])
        if len(pnrs) > 15:
            pnr_text += f" (+{len(pnrs)-15} more)"
        msg += f"\n🎫 PNRs: {pnr_text}"
    msg += f"\n🔗 Sheet: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
    return msg

# ========== MAIN APP ==========
def main():
    # ---- THEME TOGGLE ----
    dark_mode = st.sidebar.toggle("🌙 Dark Mode", value=st.session_state.dark_mode)
    if dark_mode != st.session_state.dark_mode:
        st.session_state.dark_mode = dark_mode
        st.rerun()
    apply_theme(dark_mode)

    # ---- SIDEBAR ----
    with st.sidebar:
        # Greeting
        now = datetime.now()
        hour = now.hour
        if 5 <= hour < 12:
            if is_flag_time():
                st.markdown("""
                <div style="text-align:center; margin-bottom:10px;">
                    <div style="font-size:24px; margin-bottom:4px;">🇮🇳</div>
                    <div style="font-weight:600; color:#FF9933;">🟠 Good Morning</div>
                    <div style="font-weight:600; color:#000000;">⚪ Jai Hind</div>
                    <div style="font-weight:600; color:#138808;">🟢 Vande Mataram</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("☀️ **Good Morning!**")
        elif 12 <= hour < 17:
            st.markdown("🌤️ **Good Afternoon!**")
        elif 17 <= hour < 21:
            st.markdown("🌆 **Good Evening!**")
        else:
            st.markdown("🌙 **Good Night!**")

        st.caption(f"📅 {now.strftime('%d-%m-%Y')}  •  🕐 {now.strftime('%H:%M:%S')}")

        # ---- Auto Refresh ----
        with st.expander("🔄 Sync & Refresh", expanded=True):
            auto_refresh = st.checkbox("Auto Sync every 30s", value=True)
            if auto_refresh:
                if time.time() - st.session_state.last_refresh > 30:
                    st.session_state.last_refresh = time.time()
                    st.cache_data.clear()
                    st.rerun()
            if st.button("🔄 Sync Now", use_container_width=True):
                st.cache_data.clear()
                st.session_state.last_refresh = time.time()
                log_activity("🔄 Manual sync triggered")
                st.rerun()
            st.caption(f"Last sync: {datetime.fromtimestamp(st.session_state.last_refresh).strftime('%H:%M:%S')}")

        st.markdown("---")

        # ---- Sheet Link ----
        sheet_link = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
        st.markdown(f'<a href="{sheet_link}" target="_blank" class="sheet-link-btn">📊 Open Google Sheet</a>', unsafe_allow_html=True)

        # ---- File Upload Section ----
        with st.expander("📤 Upload & Process", expanded=True):
            st.caption("Image • PDF • Text • Audio")
            uploaded_file = st.file_uploader(
                "Choose a file",
                type=['png', 'jpg', 'jpeg', 'pdf', 'txt', 'mp3', 'wav', 'ogg', 'm4a'],
                label_visibility="collapsed"
            )
            caption = st.text_input("📝 Caption (optional)", placeholder="Add notes...", key="upload_caption")

            if st.button("🚀 Process & Save", use_container_width=True, type="primary"):
                if uploaded_file:
                    file_bytes = uploaded_file.read()
                    file_type = 'pdf' if uploaded_file.type == 'application/pdf' else 'image'
                    if uploaded_file.type.startswith('audio/'):
                        file_type = 'audio'
                    elif uploaded_file.type == 'text/plain':
                        file_type = 'text'

                    progress_text = st.empty()
                    progress_bar = st.progress(0)

                    def update_progress(value, message):
                        progress_bar.progress(value)
                        progress_text.text(message)

                    try:
                        with st.spinner("Processing with AI..."):
                            b64 = base64.b64encode(file_bytes).decode('utf-8')

                            if file_type == 'text':
                                parse_result = gemini_universal_parser(
                                    uploaded_file.getvalue().decode('utf-8'), 'text', None, update_progress
                                )
                            else:
                                parse_result = gemini_universal_parser(
                                    b64, file_type, uploaded_file.type, update_progress
                                )

                            if 'error' in parse_result:
                                st.error(f"❌ Error: {parse_result['error']}")
                                log_activity(f"❌ Parse failed: {parse_result['error'][:60]}")
                            else:
                                st.success(f"✅ Extracted {parse_result['count']} record(s)!")

                                if parse_result.get('records'):
                                    with st.expander("📋 Extracted Data Preview", expanded=False):
                                        st.dataframe(pd.DataFrame(parse_result['records']), use_container_width=True)

                                try:
                                    gc = init_sheets()
                                    eq_sheet = gc.open_by_key(SHEET_ID).worksheet("EQ")
                                    save_res = save_to_sheet(eq_sheet, parse_result['records'])

                                    if 'error' in save_res:
                                        st.error(f"❌ Save error: {save_res['error']}")
                                        log_activity(f"❌ Sheet save error: {save_res['error'][:50]}")
                                    else:
                                        st.success(f"✅ Saved {save_res['saved']} new • {save_res['skipped']} skipped")

                                        drive_res = upload_to_drive(file_bytes, uploaded_file.name, uploaded_file.type)
                                        if drive_res['success']:
                                            st.success(f"📁 Uploaded to Drive: {drive_res['name']}")
                                            st.session_state.last_uploaded_file = uploaded_file.name
                                            st.session_state.last_uploaded_drive_url = drive_res.get('url')
                                            st.session_state.last_uploaded_view_url = drive_res.get('view_url')
                                            st.session_state.last_uploaded_print_url = drive_res.get('print_url')
                                            st.session_state.upload_success = True
                                            st.session_state.last_upload_time = datetime.now().strftime("%H:%M:%S")
                                            log_activity(f"✅ {uploaded_file.name} → {save_res['saved']} records saved")
                                        else:
                                            st.error(f"❌ Drive upload error: {drive_res['error']}")
                                            log_activity(f"❌ Drive failed: {drive_res['error'][:50]}")

                                        st.cache_data.clear()
                                        st.session_state.last_refresh = time.time()
                                        time.sleep(0.4)
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Sheet error: {e}")
                                    log_activity(f"❌ Sheet error: {str(e)[:50]}")
                    except Exception as e:
                        st.error(f"❌ Processing error: {e}")
                        log_activity(f"❌ Process error: {str(e)[:50]}")
                    finally:
                        progress_bar.empty()
                        progress_text.empty()
                else:
                    st.warning("⚠️ Please select a file first.")

        # ---- Uploaded File Actions ----
        if st.session_state.upload_success and st.session_state.last_uploaded_file:
            with st.expander("📄 Last Uploaded File", expanded=True):
                st.markdown(f"""
                <div class="file-card">
                    <div class="file-card-title">📄 {st.session_state.last_uploaded_file}</div>
                    <div class="file-card-meta">Uploaded at {st.session_state.get('last_upload_time', 'N/A')}</div>
                </div>
                """, unsafe_allow_html=True)

                c1, c2 = st.columns(2)
                with c1:
                    if st.session_state.last_uploaded_view_url:
                        st.link_button("👁️ View Original", st.session_state.last_uploaded_view_url, use_container_width=True)
                with c2:
                    if st.session_state.last_uploaded_print_url:
                        st.link_button("🖨️ Print Original", st.session_state.last_uploaded_print_url, use_container_width=True)

                if st.button("🗑️ Clear File History", use_container_width=True):
                    st.session_state.last_uploaded_file = None
                    st.session_state.last_uploaded_drive_url = None
                    st.session_state.last_uploaded_view_url = None
                    st.session_state.last_uploaded_print_url = None
                    st.session_state.upload_success = False
                    st.rerun()

        # ---- Activity Log ----
        with st.expander("📋 Activity Log", expanded=False):
            if st.session_state.activity_log:
                for log in reversed(st.session_state.activity_log[-20:]):
                    st.caption(f"🕐 {log.get('timestamp', '')} — {log.get('action', '')}")
            else:
                st.caption("No activity yet")

        st.markdown("---")

        # ---- Sheet Selector & Filters ----
        with st.expander("📑 Sheet & Filters", expanded=True):
            sheet_choice = st.selectbox(
                "Select Sheet",
                list(SHEET_CONFIG.keys()),
                index=list(SHEET_CONFIG.keys()).index(st.session_state.selected_sheet)
                if st.session_state.selected_sheet in SHEET_CONFIG else 0
            )
            st.session_state.selected_sheet = sheet_choice
            config = SHEET_CONFIG[sheet_choice]
            start_row = config["start_row"]

            st.subheader("🔍 Filters")
            pnr_input = st.text_input("🔢 PNR (partial)", value=st.session_state.pnr_val, key="pnr_input_widget")
            train_input = st.text_input("🚂 Train (partial)", value=st.session_state.train_val, key="train_input_widget")

            c1, c2 = st.columns(2)
            with c1:
                from_input = st.date_input("📅 From DOJ", value=st.session_state.from_val, key="from_input_widget")
            with c2:
                to_input = st.date_input("📅 To DOJ", value=st.session_state.to_val, key="to_input_widget")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("Apply Filters", use_container_width=True, type="primary"):
                    st.session_state.pnr_val = pnr_input
                    st.session_state.train_val = train_input
                    st.session_state.from_val = from_input
                    st.session_state.to_val = to_input
                    st.session_state.current_page = 1
                    st.rerun()
            with col2:
                if st.button("Clear Filters", use_container_width=True):
                    st.session_state.pnr_val = ''
                    st.session_state.train_val = ''
                    st.session_state.from_val = None
                    st.session_state.to_val = None
                    st.session_state.current_page = 1
                    st.rerun()

        # ---- Load and filter data ----
        df_raw = load_sheet_data_cached(sheet_choice, SHEET_ID)
        filtered_df = df_raw.copy() if not df_raw.empty else pd.DataFrame()

        if not filtered_df.empty:
            pnr_col_idx = config.get("pnr_col")
            train_col_idx = config.get("train_col")
            doj_col_idx = config.get("doj_col")

            if st.session_state.pnr_val and pnr_col_idx is not None and pnr_col_idx < len(filtered_df.columns):
                col_name = filtered_df.columns[pnr_col_idx]
                filtered_df = filtered_df[
                    filtered_df[col_name].astype(str).str.contains(st.session_state.pnr_val, case=False, na=False)
                ]

            if st.session_state.train_val and train_col_idx is not None and train_col_idx < len(filtered_df.columns):
                col_name = filtered_df.columns[train_col_idx]
                filtered_df = filtered_df[
                    filtered_df[col_name].astype(str).str.contains(st.session_state.train_val, case=False, na=False)
                ]

            if (st.session_state.from_val or st.session_state.to_val) and doj_col_idx is not None and doj_col_idx < len(filtered_df.columns):
                col_name = filtered_df.columns[doj_col_idx]
                try:
                    filtered_df['_temp'] = pd.to_datetime(filtered_df[col_name], format='%d-%m-%Y', errors='coerce')
                    if filtered_df['_temp'].isna().all():
                        filtered_df['_temp'] = pd.to_datetime(filtered_df[col_name], errors='coerce')
                except Exception:
                    filtered_df['_temp'] = pd.to_datetime(filtered_df[col_name], errors='coerce')
                if st.session_state.from_val:
                    filtered_df = filtered_df[filtered_df['_temp'] >= pd.to_datetime(st.session_state.from_val)]
                if st.session_state.to_val:
                    filtered_df = filtered_df[filtered_df['_temp'] <= pd.to_datetime(st.session_state.to_val)]
                filtered_df = filtered_df.drop('_temp', axis=1, errors='ignore')

        # ---- Navigation ----
        view = st.radio(
            "👁️ View Mode",
            ["📋 Data Table", "📊 Dashboard", "💬 Chat with Gemini"],
            horizontal=False
        )

    # ---- MAIN AREA ----
    st.markdown(
        "<h1 style='font-size:30px; font-weight:700; margin-bottom:2px;'>🚂 AI EQMS Hub Pro</h1>",
        unsafe_allow_html=True
    )
    st.markdown(
        f"<p style='color:#656d76; font-size:14px; margin-bottom:12px;'>"
        f"Enterprise Railway EQ Management • "
        f"<span class='status-pill status-live'>● Live</span> • "
        f"Last sync: {datetime.fromtimestamp(st.session_state.last_refresh).strftime('%H:%M:%S')}"
        f"</p>",
        unsafe_allow_html=True
    )
    st.markdown("---")

    # ========== CHAT VIEW ==========
    if view == "💬 Chat with Gemini":
        st.subheader("💬 Chat with TSKEQ Bot")
        st.caption("Ask about EQ data, trains, quota, PNR status, or anything else.")

        st.markdown("**💡 Quick suggestions**")
        sugg_cols = st.columns(3)
        for i, suggestion in enumerate(st.session_state.chat_suggestions):
            with sugg_cols[i % 3]:
                if st.button(suggestion, key=f"suggestion_{i}", use_container_width=True):
                    st.session_state.messages.append({"role": "user", "content": suggestion})
                    st.rerun()

        st.divider()

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if prompt := st.chat_input("Ask a question..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    response = chat_with_gemini(prompt, st.session_state.messages)
                    st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
            st.rerun()

        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    # ========== DASHBOARD VIEW ==========
    elif view == "📊 Dashboard":
        st.subheader("📊 Analytics Dashboard")

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            total_records = len(filtered_df) if not filtered_df.empty else 0
            st.metric("📊 Total Records", total_records)
        with m2:
            train_col = next((c for c in filtered_df.columns if 'T/N' in str(c).upper() or 'TRAIN' in str(c).upper()), None)
            unique_trains = filtered_df[train_col].nunique() if train_col and train_col in filtered_df else 0
            st.metric("🚂 Unique Trains", unique_trains)
        with m3:
            berth_col = next((c for c in filtered_df.columns if 'BERTH' in str(c).upper() or 'T/BERTHS' in str(c).upper()), None)
            if berth_col and berth_col in filtered_df:
                total_berths = pd.to_numeric(filtered_df[berth_col], errors='coerce').sum()
            else:
                total_berths = 0
            st.metric("💺 Total Berths", int(total_berths) if total_berths else 0)
        with m4:
            expired = 0
            doj_col = next((c for c in filtered_df.columns if 'DOJ' in str(c).upper()), None)
            if doj_col and doj_col in filtered_df:
                expired = sum(1 for _, r in filtered_df.iterrows() if is_expired(r.get(doj_col, '')))
            st.metric("⏰ Expired DOJ", expired)

        st.markdown("---")

        if not filtered_df.empty:
            c1, c2 = st.columns(2)

            with c1:
                train_col = next((c for c in filtered_df.columns if 'T/N' in str(c).upper() or 'TRAIN' in str(c).upper()), None)
                if train_col and train_col in filtered_df and filtered_df[train_col].notna().any():
                    train_counts = filtered_df[train_col].value_counts().head(10).reset_index()
                    train_counts.columns = ['Train', 'Count']
                    fig_pie = px.pie(
                        train_counts, names='Train', values='Count',
                        title="🚂 Top 10 Train Distribution",
                        hole=0.45,
                        color_discrete_sequence=px.colors.qualitative.Set3
                    )
                    fig_pie.update_layout(height=380, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                    st.plotly_chart(fig_pie, use_container_width=True)

            with c2:
                berth_col = next((c for c in filtered_df.columns if 'BERTH' in str(c).upper() or 'T/BERTHS' in str(c).upper()), None)
                if berth_col and berth_col in filtered_df:
                    berth_vals = pd.to_numeric(filtered_df[berth_col], errors='coerce').dropna()
                    if not berth_vals.empty:
                        fig_hist = px.histogram(
                            berth_vals, nbins=10, title="💺 Berths Distribution",
                            labels={'value': 'Berths Requested', 'count': 'Frequency'},
                            color_discrete_sequence=['#2d7d46']
                        )
                        fig_hist.update_layout(height=380, bargap=0.2, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                        st.plotly_chart(fig_hist, use_container_width=True)

            doj_col = next((c for c in filtered_df.columns if 'DOJ' in str(c).upper()), None)
            if doj_col and doj_col in filtered_df:
                df_temp = filtered_df.copy()
                df_temp['_date'] = pd.to_datetime(df_temp[doj_col], format='%d-%m-%Y', errors='coerce')
                if df_temp['_date'].isna().all():
                    df_temp['_date'] = pd.to_datetime(df_temp[doj_col], errors='coerce')
                daily_counts = df_temp.groupby('_date').size().reset_index(name='count')
                if not daily_counts.empty:
                    fig_line = px.line(
                        daily_counts, x='_date', y='count', title="📈 Daily Records Trend",
                        labels={'_date': 'Date', 'count': 'Number of Records'},
                        markers=True, color_discrete_sequence=['#ff6b6b']
                    )
                    fig_line.update_layout(height=380, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info("📭 No data available for charts. Try adjusting filters or selecting a different sheet.")

    # ========== DATA TABLE VIEW ==========
    else:
        st.subheader(f"📋 {sheet_choice} — {len(filtered_df)} rows")
        if filtered_df.empty:
            st.info("No data to display. Try adjusting filters or clearing them.")
        else:
            page_size = st.selectbox("Rows per page", [15, 25, 50, 100], index=1, key="page_size")
            total_pages = max(1, math.ceil(len(filtered_df) / page_size))

            if st.session_state.current_page > total_pages:
                st.session_state.current_page = total_pages
            if st.session_state.current_page < 1:
                st.session_state.current_page = 1

            col1, col2, col3 = st.columns([1, 2, 1])
            with col1:
                if st.button("◀ Previous", use_container_width=True, disabled=st.session_state.current_page <= 1):
                    st.session_state.current_page -= 1
                    st.rerun()
            with col2:
                st.write(f"**Page {st.session_state.current_page} of {total_pages}**")
            with col3:
                if st.button("Next ▶", use_container_width=True, disabled=st.session_state.current_page >= total_pages):
                    st.session_state.current_page += 1
                    st.rerun()

            page = st.session_state.current_page - 1
            start_idx = page * page_size
            end_idx = min(start_idx + page_size, len(filtered_df))
            page_df = filtered_df.iloc[start_idx:end_idx].copy()

            sheet_rows = page_df['_sheet_row'].tolist() if '_sheet_row' in page_df.columns else []

            display_df = page_df.drop(columns=['_sheet_row'], errors='ignore')
            display_df.insert(0, "Select", False)

            edited_page = st.data_editor(
                display_df,
                use_container_width=True,
                height=420,
                column_config={
                    "Select": st.column_config.CheckboxColumn("Select", width="small")
                },
                key=f"data_editor_{sheet_choice}_{st.session_state.current_page}",
                disabled=["_sheet_row"] if "_sheet_row" in display_df.columns else None
            )

            selected_mask = edited_page["Select"] if "Select" in edited_page.columns else pd.Series([False] * len(edited_page))
            selected_indices = edited_page[selected_mask].index.tolist()

            selected_sheet_rows = []
            if selected_indices and sheet_rows:
                for idx in selected_indices:
                    try:
                        pos = list(page_df.index).index(idx)
                        selected_sheet_rows.append(sheet_rows[pos])
                    except (ValueError, IndexError):
                        pass

            st.markdown('<div class="action-box">', unsafe_allow_html=True)
            st.subheader("⚡ Actions")

            b1, b2, b3, b4, b5 = st.columns(5)

            with b1:
                if st.button("💾 Save Edits", use_container_width=True):
                    try:
                        gc = init_sheets()
                        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                        data_to_update = edited_page.drop(columns=["Select"], errors='ignore')
                        if '_sheet_row' in data_to_update.columns:
                            data_to_update = data_to_update.drop(columns=['_sheet_row'])
                        data_list = data_to_update.values.tolist()

                        if data_list and sheet_rows:
                            for i, row_data in enumerate(data_list):
                                sheet_row_num = sheet_rows[i]
                                row_data = [str(x) if pd.notna(x) else '' for x in row_data]
                                num_cols = len(row_data)
                                col_letter = col_index_to_letter(num_cols)
                                range_name = f"A{sheet_row_num}:{col_letter}{sheet_row_num}"
                                sheet.update(range_name, [row_data])
                            st.toast("✅ Changes saved!", icon="💾")
                            log_activity(f"💾 Saved edits in {sheet_choice} ({len(data_list)} rows)")
                            st.cache_data.clear()
                            st.session_state.last_refresh = time.time()
                            time.sleep(0.4)
                            st.rerun()
                        else:
                            st.warning("No data to save.")
                    except Exception as e:
                        if "429" in str(e):
                            st.error("❌ Write quota exceeded. Wait a minute and try again.")
                        else:
                            st.error(f"Save error: {e}")
                        log_activity(f"❌ Save error: {str(e)[:50]}")

            with b2:
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
                        log_activity(f"➕ Added blank row in {sheet_choice}")
                        st.cache_data.clear()
                        st.session_state.last_refresh = time.time()
                        time.sleep(0.4)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Add row error: {e}")
                        log_activity(f"❌ Add row error: {str(e)[:50]}")

            with b3:
                if selected_sheet_rows:
                    if st.button("🗑️ Delete Selected", use_container_width=True):
                        try:
                            gc = init_sheets()
                            sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                            for row_num in sorted(selected_sheet_rows, reverse=True):
                                sheet.delete_rows(row_num)
                            st.toast(f"✅ {len(selected_sheet_rows)} rows deleted!", icon="🗑️")
                            log_activity(f"🗑️ Deleted {len(selected_sheet_rows)} rows from {sheet_choice}")
                            st.cache_data.clear()
                            st.session_state.last_refresh = time.time()
                            time.sleep(0.4)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Delete error: {e}")
                            log_activity(f"❌ Delete error: {str(e)[:50]}")
                else:
                    st.button("🗑️ Delete Selected", disabled=True, use_container_width=True)

            with b4:
                if selected_indices:
                    pnr_col = next((c for c in edited_page.columns if 'PNR' in str(c).upper()), None)
                    pnrs = []
                    if pnr_col:
                        pnrs = edited_page.loc[selected_indices, pnr_col].tolist()
                    msg = build_whatsapp_message(sheet_choice, len(selected_indices), pnrs)
                    wa_url = f"https://api.whatsapp.com/send?text={urllib.parse.quote(msg)}"
                    st.link_button("📤 Share WhatsApp", wa_url, use_container_width=True)
                else:
                    st.button("📤 Share WhatsApp", disabled=True, use_container_width=True)

            with b5:
                if st.session_state.last_uploaded_print_url:
                    st.link_button("🖨️ Print File", st.session_state.last_uploaded_print_url, use_container_width=True)
                else:
                    st.button("🖨️ Print File", disabled=True, use_container_width=True)

            st.markdown('</div>', unsafe_allow_html=True)

            # Quick Links for EQ sheet
            if sheet_choice == "EQ" and not filtered_df.empty:
                st.subheader("🔗 Quick Links")
                link_cols = [c for c in filtered_df.columns if any(x in str(c).upper() for x in ['LINK', 'PRINT', 'VIEW', 'PNR STATUS'])]
                if link_cols:
                    with st.expander(f"Show links ({min(20, len(filtered_df))} rows)"):
                        for idx, row in filtered_df.head(20).iterrows():
                            links = []
                            for col in link_cols:
                                val = row.get(col, '')
                                url = extract_hyperlink_url(val)
                                if url:
                                    if 'PRINT' in str(col).upper():
                                        links.append(f'<a href="{url}" target="_blank">🖨️ Print</a>')
                                    elif 'VIEW' in str(col).upper() or 'LINK' in str(col).upper():
                                        links.append(f'<a href="{url}" target="_blank">👁️ View</a>')
                                    elif 'PNR' in str(col).upper():
                                        links.append(f'<a href="{url}" target="_blank">🎫 PNR</a>')
                            if links:
                                st.markdown(f"**Row {idx + 1}:** " + " | ".join(links), unsafe_allow_html=True)
                else:
                    st.caption("No hyperlink columns detected in this sheet.")

            # Export
            st.subheader("📄 Export")
            e1, e2 = st.columns(2)
            with e1:
                try:
                    export_df = filtered_df.drop(columns=['_sheet_row'], errors='ignore')
                    pdf = FPDF('L', 'mm', 'A4')
                    pdf.add_page()
                    pdf.set_font("Arial", 'B', 14)
                    pdf.cell(0, 10, f"{sheet_choice} Report - {datetime.now().strftime('%d-%m-%Y %H:%M')}", ln=True, align='C')
                    pdf.ln(4)
                    pdf.set_font("Arial", 'B', 7)
                    cols = export_df.columns.tolist()
                    if not cols:
                        raise ValueError("No columns")
                    col_width = min(25, 270 / max(len(cols), 1))
                    for col in cols:
                        safe = str(col)[:14].encode('latin-1', 'ignore').decode('latin-1')
                        pdf.cell(col_width, 6, safe, border=1, align='C')
                    pdf.ln()
                    pdf.set_font("Arial", '', 6)
                    for _, row in export_df.head(150).iterrows():
                        for col in cols:
                            val = str(row[col])[:16] if pd.notna(row[col]) else ''
                            val_safe = val.encode('latin-1', 'ignore').decode('latin-1')
                            pdf.cell(col_width, 5, val_safe, border=1, align='L')
                        pdf.ln()
                    pdf_bytes = pdf.output(dest='S').encode('latin-1')
                    st.download_button(
                        "📥 Download PDF",
                        data=pdf_bytes,
                        file_name=f"{sheet_choice}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                except Exception as e:
                    st.warning(f"PDF generation issue: {e}")

            with e2:
                export_df = filtered_df.drop(columns=['_sheet_row'], errors='ignore')
                csv = export_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 Download CSV",
                    data=csv,
                    file_name=f"{sheet_choice}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

    # ---- FOOTER ----
    st.markdown("""
    <div class='pro-footer'>
        🚂 AI EQMS Hub Pro – Created by Sharique<br>
        © 2026 All Rights Reserved • Professional Railway EQ Management System
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
