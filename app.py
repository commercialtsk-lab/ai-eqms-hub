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
from datetime import datetime
from zoneinfo import ZoneInfo
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from fpdf import FPDF
import plotly.express as px
import plotly.graph_objects as go
import matplotlib.pyplot as plt
from matplotlib.table import Table as MplTable
import numpy as np
import streamlit.components.v1 as components

# ========== PAGE CONFIG ==========
st.set_page_config(
    page_title="AI EQMS Hub Pro",
    page_icon="🚂",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== TIMEZONE (IST) ==========
IST = ZoneInfo("Asia/Kolkata")

def now_ist():
    return datetime.now(IST)

def format_time(dt=None):
    if dt is None:
        dt = now_ist()
    return dt.strftime("%H:%M:%S")

def format_date(dt=None):
    if dt is None:
        dt = now_ist()
    return dt.strftime("%d-%m-%Y")

def format_datetime(dt=None):
    if dt is None:
        dt = now_ist()
    return dt.strftime("%d-%m-%Y %H:%M:%S")

# ========== THEME PERSISTENCE (Query Params + System Auto) ==========
def get_persisted_theme():
    qp = st.query_params
    theme = qp.get("theme", "Day")
    if isinstance(theme, list):
        theme = theme[0]
    custom_bg = qp.get("custom_bg", "#ffffff")
    if isinstance(custom_bg, list):
        custom_bg = custom_bg[0]
    custom_text = qp.get("custom_text", "#000000")
    if isinstance(custom_text, list):
        custom_text = custom_text[0]
    return theme, custom_bg, custom_text

def set_persisted_theme(theme, custom_bg=None, custom_text=None):
    st.query_params["theme"] = theme
    if custom_bg:
        st.query_params["custom_bg"] = custom_bg
    if custom_text:
        st.query_params["custom_text"] = custom_text

def resolve_system_theme():
    hour = now_ist().hour
    return "Day" if 6 <= hour < 18 else "Dark"

# ========== CREDENTIALS ==========
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
GSPREAD_CREDENTIALS = st.secrets.get("GSPREAD_CREDENTIALS")

if not GEMINI_API_KEY or not GSPREAD_CREDENTIALS:
    st.error("❌ Missing credentials! Please check secrets.toml")
    st.stop()

SHEET_ID = "1QcS3ZF3YYxSEykG0KiOUuXbTdBh0DMHdMgoqa9t8yrI"
DRIVE_FOLDER_ID = "1H1gf8WqfoTYFT_pU9WfIDLrHg-NpuUSI"

# ========== SESSION STATE ==========
persisted_theme, persisted_bg, persisted_text = get_persisted_theme()

if persisted_theme == "System":
    effective_theme = resolve_system_theme()
else:
    effective_theme = persisted_theme

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
    'theme': persisted_theme,
    'custom_bg': persisted_bg,
    'custom_text': persisted_text,
    'current_page': 1,
    'pnr_val': '',
    'train_val': '',
    'from_val': None,
    'to_val': None,
    'upload_success': False,
    'last_upload_time': None,
    'selected_sheet': "EQ",
    'view_mode': "📋 Data Table",
    'select_all': False,
    'delete_confirm': False,
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
        today = now_ist().replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
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
    month = now_ist().month
    if month in [5, 6, 7]:
        return 18, 45
    elif month in [11, 12, 1]:
        return 17, 15
    elif month in [2, 3, 10]:
        return 18, 0
    else:
        return 18, 30

def is_flag_time():
    now = now_ist()
    sunset_h, sunset_m = get_sunset_time()
    start = now.replace(hour=6, minute=0, second=0, microsecond=0)
    end = now.replace(hour=sunset_h, minute=sunset_m, second=0, microsecond=0)
    return start <= now <= end

def log_activity(action: str):
    st.session_state.activity_log.append({
        'timestamp': format_time(),
        'action': action
    })
    if len(st.session_state.activity_log) > 50:
        st.session_state.activity_log = st.session_state.activity_log[-50:]

def sanitize_latin(text):
    if not text:
        return ''
    replacements = {
        '•': '-', '·': '-', '\u2018': "'", '\u2019': "'",
        '\u201c': '"', '\u201d': '"', '\u2013': '-', '\u2014': '-',
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode('latin-1', 'ignore').decode('latin-1')

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
@st.cache_data(ttl=10, show_spinner=False)
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
        for row in data_rows:
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
1. DIARY_NO: Look for "No." or "Diary No." pattern. Preserve as-is. Do NOT overwrite with RAIL BOARD unless explicitly stated.
2. PREFERENCE: If you see "Lower Berth", "Lower Seat", "Coupe", set PREFERENCE = "Lower Seat".
3. RAIL BOARD: If you see "Office of the Hon'ble Minister Railways", set DIARY_NO="RAIL BOARD", RAILWAY_ZONE="RAIL BOARD".
4. DOJ: If you see "24/25.06.26", return the FIRST date: "24-06-2026".
5. Multiple entries: If a table has multiple rows, extract ALL valid entries.

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
            now = format_datetime()
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

# ========== THEME (with persistence + System Auto) ==========
def apply_theme(theme, custom_bg=None, custom_text=None):
    if theme == 'System':
        theme = resolve_system_theme()

    if theme == 'Day':
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
        button_bg = "#f6f8fa"
        button_text = "#1f2328"
        button_border = "#d0d7de"
        button_hover_bg = accent
        button_hover_text = "white"
        button_hover_border = accent
    elif theme == 'Dark':
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
        button_bg = "#21262d"
        button_text = "#e6edf3"
        button_border = "#30363d"
        button_hover_bg = accent
        button_hover_text = "white"
        button_hover_border = accent
    else:  # Custom
        bg = custom_bg if custom_bg else "#ffffff"
        card_bg = bg
        text_color = custom_text if custom_text else "#000000"
        text_secondary = text_color
        border = "#d0d7de"
        input_bg = bg
        accent = "#0969da"
        accent_hover = "#0550ae"
        success = "#1a7f37"
        danger = "#cf222e"
        button_bg = bg
        button_text = text_color
        button_border = border
        button_hover_bg = accent
        button_hover_text = "white"
        button_hover_border = accent

    css = f"""
    <style>
        .block-container {{ padding-top: 0.5rem !important; padding-bottom: 1rem !important; }}
        .stApp {{ background-color: {bg} !important; }}
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
        [data-testid="stSidebar"] .stRadio label,
        [data-testid="stSidebar"] .stCheckbox label {{
            color: {text_color} !important;
        }}
        header[data-testid="stHeader"] {{
            background-color: {card_bg} !important;
            border-bottom: 1px solid {border} !important;
        }}
        h1, h2, h3, h4, h5, h6,
        .stMarkdown p, .stMarkdown div, .stMarkdown span,
        .stMarkdown h1, .stMarkdown h2, .stMarkdown h3,
        [data-testid="stMetricLabel"],
        [data-testid="stMetricValue"],
        .stCaption {{
            color: {text_color} !important;
            font-size: 1rem !important;
        }}
        .stTextInput input, .stNumberInput input,
        .stDateInput input, .stTextArea textarea,
        .stSelectbox > div > div > div {{
            background-color: {input_bg} !important;
            color: {text_color} !important;
            border: 1px solid {border} !important;
            border-radius: 8px !important;
            font-size: 1rem !important;
        }}
        .stButton > button {{
            background-color: {button_bg} !important;
            color: {button_text} !important;
            border: 1px solid {button_border} !important;
            border-radius: 8px !important;
            font-weight: 500 !important;
            font-size: 0.95rem !important;
            transition: all 0.15s ease !important;
        }}
        .stButton > button:hover {{
            background-color: {button_hover_bg} !important;
            color: {button_hover_text} !important;
            border-color: {button_hover_border} !important;
            transform: translateY(-1px) !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15) !important;
        }}
        .stButton > button:disabled {{ opacity: 0.45 !important; cursor: not-allowed !important; }}
        .stButton > button[kind="primary"] {{
            background-color: {accent} !important;
            color: white !important;
            border-color: {accent} !important;
        }}
        .stButton > button[kind="primary"]:hover {{
            background-color: {accent_hover} !important;
            border-color: {accent_hover} !important;
        }}
        .stFileUploader {{
            background-color: {input_bg} !important;
            border: 2px dashed {border} !important;
            border-radius: 12px !important;
            padding: 16px !important;
        }}
        .stFileUploader:hover {{ border-color: {accent} !important; }}
        .stFileUploader label {{ color: {text_secondary} !important; }}
        .stDataFrame, [data-testid="stDataFrame"],
        .stDataFrame table, [data-testid="stDataFrame"] table,
        .stDataFrame thead, [data-testid="stDataFrame"] thead,
        .stDataFrame tbody, [data-testid="stDataFrame"] tbody,
        .stDataFrame th, [data-testid="stDataFrame"] th,
        .stDataFrame td, [data-testid="stDataFrame"] td,
        .stDataEditor, [data-testid="stDataEditor"],
        .stDataEditor table, [data-testid="stDataEditor"] table,
        .stDataEditor thead, [data-testid="stDataEditor"] thead,
        .stDataEditor tbody, [data-testid="stDataEditor"] tbody,
        .stDataEditor th, [data-testid="stDataEditor"] th,
        .stDataEditor td, [data-testid="stDataEditor"] td,
        .stDataEditor input, .stDataEditor textarea {{
            background-color: {card_bg} !important;
            color: {text_color} !important;
            border-color: {border} !important;
            font-size: 0.9rem !important;
        }}
        .stDataFrame th, [data-testid="stDataFrame"] th,
        .stDataEditor th, [data-testid="stDataEditor"] th {{
            border-bottom: 2px solid {border} !important;
            font-weight: 600 !important;
        }}
        .stExpander {{
            background-color: {card_bg} !important;
            border: 1px solid {border} !important;
            border-radius: 8px !important;
        }}
        .streamlit-expanderHeader {{
            color: {text_color} !important;
            font-weight: 600 !important;
            font-size: 1rem !important;
        }}
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
        .stChatInput input {{ color: {text_color} !important; }}
        [data-testid="stMetric"] {{
            background-color: {card_bg} !important;
            border: 1px solid {border} !important;
            border-radius: 10px !important;
            padding: 14px !important;
        }}
        .stTabs [data-baseweb="tab-list"] {{
            background-color: {card_bg} !important;
            border-bottom: 1px solid {border} !important;
        }}
        .stTabs [data-baseweb="tab"] {{ color: {text_secondary} !important; }}
        .stTabs [data-baseweb="tab-highlight"] {{ background-color: {accent} !important; }}
        ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
        ::-webkit-scrollbar-track {{ background: {bg}; }}
        ::-webkit-scrollbar-thumb {{ background: {border}; border-radius: 10px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: {accent}; }}
        .action-box {{
            background: {card_bg};
            border: 1px solid {border};
            border-radius: 12px;
            padding: 18px;
            margin-bottom: 16px;
        }}
        .file-card {{
            background: {card_bg};
            border: 1px solid {border};
            border-radius: 12px;
            padding: 14px;
            margin: 10px 0;
        }}
        .file-card-title {{
            color: {text_color};
            font-weight: 600;
            font-size: 0.95rem;
            margin-bottom: 2px;
        }}
        .file-card-meta {{
            color: {text_secondary};
            font-size: 0.8rem;
            margin-bottom: 10px;
        }}
        .pro-footer {{
            color: {text_secondary} !important;
            border-top: 1px solid {border} !important;
            text-align: center !important;
            padding: 18px 0 8px !important;
            margin-top: 28px !important;
            font-size: 0.85rem !important;
        }}
        .sheet-link-btn {{
            display: inline-block !important;
            padding: 9px 16px !important;
            background: {button_bg} !important;
            color: {accent} !important;
            border: 1px solid {button_border} !important;
            border-radius: 8px !important;
            text-decoration: none !important;
            text-align: center !important;
            width: 100% !important;
            transition: all 0.15s !important;
            font-weight: 500 !important;
            font-size: 0.9rem !important;
        }}
        .sheet-link-btn:hover {{
            background: {accent} !important;
            color: white !important;
            border-color: {accent} !important;
        }}
        .status-pill {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 20px;
            font-size: 0.78rem;
            font-weight: 500;
        }}
        .status-live {{
            background: rgba(63, 185, 80, 0.15);
            color: {success};
            border: 1px solid {success};
        }}
        .top-bar {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            align-items: center;
            margin-bottom: 8px;
        }}
        .train-count-box {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px 12px;
            padding: 14px 18px;
            background: {card_bg};
            border-radius: 12px;
            border: 1px solid {border};
            margin: 10px 0 18px 0;
            align-items: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        }}
        .train-count-item {{
            background: {input_bg};
            padding: 6px 16px;
            border-radius: 20px;
            border: 1px solid {border};
            font-weight: 600;
            font-size: 0.95rem;
            white-space: nowrap;
            transition: all 0.2s ease;
        }}
        .train-count-item:hover {{
            border-color: {accent};
            transform: translateY(-2px);
            box-shadow: 0 2px 8px rgba(9,105,218,0.15);
        }}
        .train-count-total {{
            font-weight: 700;
            font-size: 1.05rem;
            margin-left: auto;
            padding: 6px 18px;
            background: linear-gradient(135deg, {accent}, {accent_hover});
            color: white;
            border-radius: 20px;
            box-shadow: 0 2px 8px rgba(9,105,218,0.25);
        }}
        .print-table {{
            display: none;
        }}
        .tooltip-container {{
            position: relative;
            display: inline-block;
        }}
        .tooltip-container .tooltip-text {{
            visibility: hidden;
            width: 200px;
            background-color: {card_bg};
            color: {text_color};
            text-align: center;
            border-radius: 8px;
            padding: 8px;
            position: absolute;
            z-index: 1000;
            bottom: 125%;
            left: 50%;
            margin-left: -100px;
            opacity: 0;
            transition: opacity 0.3s;
            font-size: 0.8rem;
            border: 1px solid {border};
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}
        .tooltip-container:hover .tooltip-text {{
            visibility: visible;
            opacity: 1;
        }}
        * {{
            transition: background-color 0.2s ease, color 0.2s ease, border-color 0.2s ease;
        }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# ========== PDF GENERATION ==========
def generate_pdf(df, title, full=True):
    pdf = FPDF('L', 'mm', 'A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, f"AI EQMS Hub Pro - {title}", ln=True, align='C')
    pdf.set_font("Arial", '', 8)
    pdf.cell(0, 6, f"Generated: {format_datetime()} IST | Rows: {len(df)}", ln=True, align='C')
    pdf.ln(3)

    cols = list(df.columns)
    if '_sheet_row' in cols:
        cols.remove('_sheet_row')
    if len(cols) > 15:
        cols = cols[:15]

    col_width = min(25, 277 / max(len(cols), 1))

    pdf.set_font("Arial", 'B', 7)
    for c in cols:
        safe_c = sanitize_latin(str(c)[:15])
        pdf.cell(col_width, 6, safe_c, border=1)
    pdf.ln()

    pdf.set_font("Arial", '', 6)
    max_rows = len(df) if full else min(120, len(df))
    for idx, row in df.head(max_rows).iterrows():
        for c in cols:
            val = str(row.get(c, ""))[:20]
            safe_val = sanitize_latin(val)
            pdf.cell(col_width, 5, safe_val, border=1)
        pdf.ln()
        if pdf.get_y() > 185:
            pdf.add_page()
            pdf.set_font("Arial", 'B', 7)
            for c in cols:
                safe_c = sanitize_latin(str(c)[:15])
                pdf.cell(col_width, 6, safe_c, border=1)
            pdf.ln()
            pdf.set_font("Arial", '', 6)

    output = pdf.output(dest='S')
    if isinstance(output, bytearray):
        return bytes(output)
    elif isinstance(output, str):
        return output.encode('latin-1')
    else:
        return output

# ========== TABLE AS IMAGE (using matplotlib) ==========
def create_table_image(df, title):
    if df.empty:
        return None
    fig, ax = plt.subplots(figsize=(14, 0.5 + 0.45 * min(len(df), 30)))
    ax.axis('off')
    cols = list(df.columns)
    if '_sheet_row' in cols:
        cols.remove('_sheet_row')
    if len(cols) > 8:
        cols = cols[:8]
    data = df[cols].head(50).values
    table = ax.table(cellText=data, colLabels=cols, loc='center', cellLoc='left')
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.6)
    for (i, j), cell in table.get_celld().items():
        if i == 0:
            cell.set_facecolor('#4a90d9')
            cell.set_text_props(color='white', weight='bold')
        else:
            cell.set_facecolor('#f0f4fa' if i % 2 == 0 else 'white')
            cell.set_text_props(color='black')
        cell.set_edgecolor('#cccccc')
    plt.title(title, fontsize=16, weight='bold', pad=20)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    return buf.getvalue()

# ========== WHATSAPP SHARE ==========
def build_whatsapp_message(sheet_name, selected_count, pnrs, total_rows, df):
    now_str = format_datetime()
    if not df.empty:
        cols = list(df.columns)
        if '_sheet_row' in cols:
            cols.remove('_sheet_row')
        cols = cols[:7]
        table_lines = []
        table_lines.append(" | ".join(cols))
        table_lines.append("-" * 40)
        for _, row in df.head(5).iterrows():
            row_vals = [str(row.get(c, ""))[:12] for c in cols]
            table_lines.append(" | ".join(row_vals))
        if len(df) > 5:
            table_lines.append(f"... and {len(df)-5} more rows")
        table_text = "\n".join(table_lines)
    else:
        table_text = "No data"

    if selected_count > 0 and pnrs:
        pnr_text = ", ".join(str(p) for p in pnrs[:15])
        if len(pnrs) > 15:
            pnr_text += f" (+{len(pnrs)-15} more)"
        msg = f"📊 *{sheet_name}* — {selected_count} rows selected\n🕐 {now_str}\n🎫 PNRs: {pnr_text}\n\n```\n{table_text}\n```"
    else:
        msg = f"📊 *{sheet_name}* — Total {total_rows} rows\n🕐 {now_str}\n\n```\n{table_text}\n```"
    msg += f"\n🔗 Sheet: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
    return msg

# ========== WHATSAPP IMAGE COPY TO CLIPBOARD ==========
def render_whatsapp_image_share(df, sheet_name):
    if df.empty:
        st.info("No data to generate image")
        return
    with st.spinner("Generating table image..."):
        img_bytes = create_table_image(df, f"{sheet_name} Report")
    if not img_bytes:
        st.warning("Could not generate image")
        return
    b64_img = base64.b64encode(img_bytes).decode()
    st.markdown("**📱 WhatsApp Image Share**")
    st.image(img_bytes, caption="Preview — this image will be copied to clipboard", use_container_width=True)
    copy_html = f"""
    <div style="margin: 10px 0;">
        <button id="waCopyBtn" style="background: linear-gradient(135deg, #25D366, #128C7E);color: white;border: none;border-radius: 10px;padding: 12px 24px;width: 100%;font-weight: 600;cursor: pointer;font-size: 1rem;transition: all 0.2s ease;box-shadow: 0 4px 12px rgba(37,211,102,0.3);"
        onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 6px 16px rgba(37,211,102,0.4')" 
        onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 4px 12px rgba(37,211,102,0.3)'"
        onclick="copyImageToClipboard()">📋 Copy Image to Clipboard</button>
        <p id="waCopyStatus" style="text-align:center; margin-top:8px; font-size:0.9rem; color:#666; min-height:20px;"></p>
    </div>
    <script>
    async function copyImageToClipboard() {{
        try {{
            const btn = document.getElementById('waCopyBtn');
            const status = document.getElementById('waCopyStatus');
            btn.disabled = true;
            btn.innerText = '⏳ Copying...';
            status.innerText = '';
            const response = await fetch('data:image/png;base64,{b64_img}');
            const blob = await response.blob();
            await navigator.clipboard.write([new ClipboardItem({{'image/png': blob}})]);
            status.innerText = '✅ Copied! Now open WhatsApp Web/App and press Ctrl+V to paste';
            status.style.color = '#1a7f37';
            status.style.fontWeight = '600';
            btn.innerText = '✅ Copied Successfully!';
            btn.style.background = 'linear-gradient(135deg, #1a7f37, #2ea043)';
            setTimeout(() => {{
                btn.disabled = false;
                btn.innerText = '📋 Copy Image to Clipboard';
                btn.style.background = 'linear-gradient(135deg, #25D366, #128C7E)';
                status.innerText = '';
            }}, 4000);
        }} catch(err) {{
            const status = document.getElementById('waCopyStatus');
            status.innerText = '❌ Auto-copy failed. Right-click the image above → Copy Image, then paste in WhatsApp.';
            status.style.color = '#cf222e';
            document.getElementById('waCopyBtn').disabled = false;
            document.getElementById('waCopyBtn').innerText = '📋 Copy Image to Clipboard';
        }}
    }}
    </script>
    """
    components.html(copy_html, height=130)
    msg = build_whatsapp_message(sheet_name, 0, [], len(df), df)
    encoded = urllib.parse.quote(msg)
    wa_url = f"https://api.whatsapp.com/send?text={encoded}"
    st.link_button("📤 Open WhatsApp (Text Only)", wa_url, use_container_width=True, help="Opens WhatsApp with a text summary of the sheet data")

# ========== FUNCTION TO GENERATE HTML TABLE FOR PRINT ==========
def generate_print_html(df, title):
    if df.empty:
        return "<p>No data</p>"
    cols = list(df.columns)
    if '_sheet_row' in cols:
        cols.remove('_sheet_row')
    html = f"""
    <html>
    <head>
        <title>{title} - Print</title>
        <style>
            @media print {{
                body {{ margin: 0; padding: 10px; }}
                .no-print {{ display: none; }}
            }}
            body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 20px; background: white; color: #333; }}
            h1 {{ color: #1a1a1a; font-size: 22px; margin-bottom: 4px; }}
            .meta {{ color: #666; font-size: 12px; margin-bottom: 16px; }}
            table {{ border-collapse: collapse; width: 100%; font-size: 11px; }}
            th, td {{ border: 1px solid #bbb; padding: 6px 8px; text-align: left; }}
            th {{ background-color: #2563eb; color: white; font-weight: 600; }}
            tr:nth-child(even) {{ background-color: #f8fafc; }}
            tr:hover {{ background-color: #eff6ff; }}
            .total {{ margin-top: 20px; font-weight: bold; font-size: 14px; color: #1a1a1a; }}
            .footer {{ margin-top: 30px; color: #888; font-size: 11px; border-top: 1px solid #ddd; padding-top: 10px; }}
            .print-btn {{ background: #2563eb; color: white; border: none; padding: 10px 24px; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 600; margin-bottom: 20px; }}
            .print-btn:hover {{ background: #1d4ed8; }}
        </style>
    </head>
    <body>
        <button class="print-btn no-print" onclick="window.print()">🖨️ Print This Page</button>
        <h1>{title}</h1>
        <p class="meta">Generated: {format_datetime()} IST | Rows: {len(df)}</p>
        <table>
            <thead><tr>
    """
    for c in cols:
        html += f"<th>{c}</th>"
    html += "</tr></thead><tbody>"
    for _, row in df.iterrows():
        html += "<tr>"
        for c in cols:
            val = str(row.get(c, ""))
            html += f"<td>{val}</td>"
        html += "</tr>"
    html += f"""
            </tbody>
        </table>
        <p class="total">Total Rows: {len(df)}</p>
        <p class="footer">AI EQMS Hub Pro • Generated by TSKEQ Bot</p>
    </body>
    </html>
    """
    return html

# ========== MAIN APP ==========
def main():
    # Theme selection with persistence
    theme_options = ['Day', 'Dark', 'Custom', 'System']
    theme_choice = st.sidebar.selectbox(
        "🎨 Theme", 
        theme_options, 
        index=theme_options.index(st.session_state.theme) if st.session_state.theme in theme_options else 0,
        help="Choose app theme. System auto-switches Day/Dark based on time (6AM-6PM)"
    )
    if theme_choice != st.session_state.theme:
        st.session_state.theme = theme_choice
        set_persisted_theme(theme_choice)
        st.rerun()

    if theme_choice == 'Custom':
        custom_bg = st.sidebar.color_picker(
            "Background Color", 
            value=st.session_state.custom_bg,
            help="Pick custom background color"
        )
        custom_text = st.sidebar.color_picker(
            "Text Color", 
            value=st.session_state.custom_text,
            help="Pick custom text color"
        )
        if custom_bg != st.session_state.custom_bg or custom_text != st.session_state.custom_text:
            st.session_state.custom_bg = custom_bg
            st.session_state.custom_text = custom_text
            set_persisted_theme(theme_choice, custom_bg, custom_text)
            st.rerun()
    else:
        custom_bg = None
        custom_text = None

    apply_theme(theme_choice, custom_bg, custom_text)

    # ---- SIDEBAR ----
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center; margin-bottom:10px; font-size:1.3rem; line-height:1.8;">
            <span style="color:#FF9933;">🟠 नमस्ते आपका स्वागत है</span><br>
            <span style="color:#FFFFFF;">⚪ हम भारत के लोग</span><br>
            <span style="color:#138808; font-weight:bold;">🟢 जय हिंद</span>
        </div>
        """, unsafe_allow_html=True)

        now = now_ist()
        st.caption(f"📅 {format_date()}  •  🕐 {format_time()} IST")

        with st.expander("🔄 Sync & Status", expanded=True):
            auto_refresh = st.checkbox(
                "Auto Sync (every 10s)", 
                value=True,
                help="Automatically refresh data every 10 seconds"
            )
            if auto_refresh:
                elapsed = time.time() - st.session_state.last_refresh
                if elapsed > 10:
                    st.session_state.last_refresh = time.time()
                    st.cache_data.clear()
                    st.rerun()
                else:
                    remaining = 10 - int(elapsed)
                    st.caption(f"⏳ Next sync in {remaining}s")
            if st.button(
                "🔄 Sync Now", 
                use_container_width=True,
                help="Force refresh all sheet data from Google Sheets"
            ):
                st.cache_data.clear()
                st.session_state.last_refresh = time.time()
                log_activity("🔄 Manual sync")
                st.rerun()
            st.caption(f"Last sync: {format_time(datetime.fromtimestamp(st.session_state.last_refresh, tz=IST))} IST")

        sheet_link = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
        st.markdown(f'<a href="{sheet_link}" target="_blank" class="sheet-link-btn">📊 Open Google Sheet</a>', unsafe_allow_html=True)

        # ===== UPLOAD SECTION =====
        with st.expander("📤 Upload & Process", expanded=True):
            st.caption("📷 Image • 📄 PDF • 📝 Text • 🎤 Audio")
            mode = st.radio(
                "Type", 
                ["📷 Image / PDF", "📝 Text", "🎤 Voice / Audio"], 
                horizontal=True, 
                label_visibility="collapsed",
                help="Select input type for processing"
            )

            uploaded = None
            text_data = ""
            audio_data = None

            if mode == "📷 Image / PDF":
                uploaded = st.file_uploader("Image or PDF", type=["png","jpg","jpeg","pdf"], label_visibility="collapsed")
            elif mode == "📝 Text":
                text_data = st.text_area(
                    "📝 Paste text", 
                    height=150, 
                    placeholder="Messy text yahan paste karein...", 
                    label_visibility="collapsed"
                )
                if text_data:
                    st.caption(f"✓ {len(text_data)} characters ready")
            else:
                st.caption("🎤 Mic se record karein")
                audio_data = st.audio_input("Record", label_visibility="collapsed")
                uploaded = st.file_uploader("Ya file upload", type=["mp3","wav","ogg","m4a"], label_visibility="collapsed")
                if audio_data:
                    st.audio(audio_data, format='audio/wav')
                elif uploaded:
                    st.audio(uploaded, format='audio/mp3')

            if st.button(
                "🚀 Process & Save", 
                type="primary", 
                use_container_width=True,
                help="Extract data using Gemini AI and save to EQ sheet + Google Drive"
            ):
                if mode == "📝 Text" and not text_data.strip():
                    st.warning("Text daalein")
                elif mode != "📝 Text" and not uploaded and not audio_data:
                    st.warning("File select karein")
                else:
                    prog = st.progress(0)
                    status = st.empty()
                    def upd(v, m):
                        prog.progress(v)
                        status.text(m)
                    try:
                        if mode == "📝 Text":
                            res = gemini_universal_parser(text_data, "text", None, upd)
                            fname = f"text_{now_ist().strftime('%H%M%S')}.txt"
                            fbytes = text_data.encode()
                            mime = "text/plain"
                        elif audio_data:
                            fbytes = audio_data.getvalue()
                            b64 = base64.b64encode(fbytes).decode()
                            res = gemini_universal_parser(b64, "audio", "audio/wav", upd)
                            fname = f"voice_{now_ist().strftime('%H%M%S')}.wav"
                            mime = "audio/wav"
                        else:
                            fbytes = uploaded.read()
                            b64 = base64.b64encode(fbytes).decode()
                            ftype = "pdf" if uploaded.type == "application/pdf" else "audio" if uploaded.type.startswith("audio") else "image"
                            res = gemini_universal_parser(b64, ftype, uploaded.type, upd)
                            fname = uploaded.name
                            mime = uploaded.type

                        if "error" in res:
                            st.error(res["error"])
                            log_activity(f"❌ Parse failed: {res['error'][:50]}")
                        else:
                            st.success(f"✅ Extracted {res['count']} record(s)")
                            if res.get('records'):
                                with st.expander("🔍 Preview extracted data"):
                                    st.dataframe(pd.DataFrame(res['records']), use_container_width=True)

                            try:
                                gc = init_sheets()
                                eq_sheet = gc.open_by_key(SHEET_ID).worksheet("EQ")
                                save_res = save_to_sheet(eq_sheet, res['records'])

                                if "error" in save_res:
                                    st.error(f"❌ Save error: {save_res['error']}")
                                    log_activity(f"❌ Save error: {save_res['error'][:40]}")
                                else:
                                    st.success(f"✅ Saved {save_res['saved']} new • {save_res['skipped']} skipped")

                                    if uploaded or audio_data:
                                        drive_res = upload_to_drive(fbytes, fname, mime)
                                        if drive_res['success']:
                                            st.success(f"📁 Drive: {drive_res['name']}")
                                            st.session_state.last_uploaded_file = fname
                                            st.session_state.last_uploaded_drive_url = drive_res.get('url')
                                            st.session_state.last_uploaded_view_url = drive_res.get('view_url')
                                            st.session_state.last_uploaded_print_url = drive_res.get('print_url')
                                            st.session_state.upload_success = True
                                            st.session_state.last_upload_time = format_time()
                                            log_activity(f"✅ {fname} → {save_res['saved']} records")
                                        else:
                                            st.error(f"❌ Drive: {drive_res['error']}")
                                            log_activity(f"❌ Drive failed: {drive_res['error'][:40]}")
                                    else:
                                        st.session_state.upload_success = True
                                        st.session_state.last_upload_time = format_time()
                                        log_activity(f"✅ Text input → {save_res['saved']} records")

                                    st.cache_data.clear()
                                    st.session_state.last_refresh = time.time()
                                    time.sleep(0.3)
                                    st.rerun()
                            except Exception as e:
                                st.error(f"❌ Sheet error: {e}")
                                log_activity(f"❌ Sheet: {str(e)[:40]}")
                    except Exception as e:
                        st.error(f"❌ Processing error: {e}")
                        log_activity(f"❌ Process: {str(e)[:40]}")
                    finally:
                        prog.empty()
                        status.empty()

        # ---- Last uploaded file ----
        if st.session_state.upload_success and st.session_state.last_uploaded_file:
            with st.expander("📄 Last Uploaded File", expanded=True):
                st.markdown(f"""
                <div class="file-card">
                    <div class="file-card-title">📄 {st.session_state.last_uploaded_file}</div>
                    <div class="file-card-meta">Uploaded at {st.session_state.get('last_upload_time', '—')} IST</div>
                </div>
                """, unsafe_allow_html=True)
                c1, c2 = st.columns(2)
                with c1:
                    if st.session_state.last_uploaded_view_url:
                        st.link_button("👁️ View", st.session_state.last_uploaded_view_url, use_container_width=True)
                with c2:
                    if st.session_state.last_uploaded_print_url:
                        st.link_button("🖨️ Print File (Drive)", st.session_state.last_uploaded_print_url, use_container_width=True)
                if st.button(
                    "🗑️ Clear History", 
                    use_container_width=True,
                    help="Clear the last uploaded file history from sidebar"
                ):
                    st.session_state.last_uploaded_file = None
                    st.session_state.last_uploaded_drive_url = None
                    st.session_state.last_uploaded_view_url = None
                    st.session_state.last_uploaded_print_url = None
                    st.session_state.upload_success = False
                    st.rerun()

        # ---- Activity Log ----
        with st.expander("📋 Activity Log", expanded=True):
            if st.session_state.activity_log:
                for log in reversed(st.session_state.activity_log[-20:]):
                    st.caption(f"{log.get('timestamp', '')} — {log.get('action', '')}")
            else:
                st.caption("No activity yet")

        st.markdown("---")

        with st.expander("📑 Sheet & Filters", expanded=True):
            sheet_choice = st.selectbox(
                "Select Sheet",
                list(SHEET_CONFIG.keys()),
                index=list(SHEET_CONFIG.keys()).index(st.session_state.selected_sheet)
                if st.session_state.selected_sheet in SHEET_CONFIG else 0,
                help="Choose which Google Sheet to view and edit"
            )
            st.session_state.selected_sheet = sheet_choice
            config = SHEET_CONFIG[sheet_choice]
            start_row = config["start_row"]

            def update_pnr():
                st.session_state.pnr_val = st.session_state._pnr_input
                st.session_state.current_page = 1
            def update_train():
                st.session_state.train_val = st.session_state._train_input
                st.session_state.current_page = 1
            def update_from():
                st.session_state.from_val = st.session_state._from_input
                st.session_state.current_page = 1
            def update_to():
                st.session_state.to_val = st.session_state._to_input
                st.session_state.current_page = 1

            pnr_input = st.text_input(
                "PNR (partial)",
                value=st.session_state.pnr_val,
                key="_pnr_input",
                on_change=update_pnr,
                help="Filter by PNR number (partial match supported)"
            )
            train_input = st.text_input(
                "Train (partial)",
                value=st.session_state.train_val,
                key="_train_input",
                on_change=update_train,
                help="Filter by train number (partial match supported)"
            )

            c1, c2 = st.columns(2)
            with c1:
                from_input = st.date_input(
                    "From DOJ",
                    value=st.session_state.from_val,
                    key="_from_input",
                    on_change=update_from,
                    format="DD-MM-YYYY",
                    help="Start date for DOJ filter"
                )
            with c2:
                to_input = st.date_input(
                    "To DOJ",
                    value=st.session_state.to_val,
                    key="_to_input",
                    on_change=update_to,
                    format="DD-MM-YYYY",
                    help="End date for DOJ filter"
                )

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

        # ----- Quick Filter by Train (dropdown) -----
        train_col = None
        for c in filtered_df.columns:
            if 'T/N' in c.upper() or 'TRAIN' in c.upper():
                train_col = c
                break
        if train_col and not filtered_df.empty:
            train_options = sorted(filtered_df[train_col].dropna().unique())
            if train_options:
                selected_train = st.selectbox(
                    "🚆 Quick Filter by Train", 
                    [""] + train_options, 
                    key="quick_train_select",
                    help="Quickly filter to a specific train number"
                )
                if selected_train:
                    filtered_df = filtered_df[filtered_df[train_col] == selected_train]
                    st.session_state.train_val = selected_train

        # Radio buttons – instant switching
        def set_view_mode():
            st.session_state.view_mode = st.session_state._view_radio
        view = st.radio(
            "View Mode",
            ["📋 Data Table", "📊 Dashboard", "💬 Chat"],
            index=["📋 Data Table", "📊 Dashboard", "💬 Chat"].index(st.session_state.view_mode)
            if st.session_state.view_mode in ["📋 Data Table", "📊 Dashboard", "💬 Chat"] else 0,
            key="_view_radio",
            on_change=set_view_mode,
            help="Switch between data table, analytics dashboard, or AI chat"
        )

    # ========== MAIN AREA ==========
    top_c1, top_c2 = st.columns([4, 1])
    with top_c1:
        st.markdown(
            "<h1 style='font-size:24px; font-weight:700; margin:0;'>🚂 AI EQMS Hub Pro</h1>",
            unsafe_allow_html=True
        )
    with top_c2:
        st.markdown(
            f"<div style='padding-top:6px; text-align:right;'>"
            f"<span class='status-pill status-live'>● Live</span> &nbsp; "
            f"<span style='font-size:14px;'>Sync {format_time(datetime.fromtimestamp(st.session_state.last_refresh, tz=IST))} IST</span>"
            f"</div>",
            unsafe_allow_html=True
        )

    st.caption(f"Enterprise Railway EQ Management  •  {format_date()}  •  {format_time()} IST")
    st.markdown("---")

    # ========== CHAT ==========
    if view == "💬 Chat":
        st.subheader("💬 Chat with TSKEQ Bot")
        st.caption("Ask about EQ data, trains, quota, PNR or anything else.")

        if prompt := st.chat_input("Type your question..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    response = chat_with_gemini(prompt, st.session_state.messages)
                    st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
            st.rerun()

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        st.markdown("**Quick questions**")
        sugg_cols = st.columns(3)
        for i, suggestion in enumerate(st.session_state.chat_suggestions):
            with sugg_cols[i % 3]:
                if st.button(suggestion, key=f"sugg_{i}", use_container_width=True):
                    st.session_state.messages.append({"role": "user", "content": suggestion})
                    with st.spinner("Thinking..."):
                        response = chat_with_gemini(suggestion, st.session_state.messages)
                        st.session_state.messages.append({"role": "assistant", "content": response})
                    st.rerun()

        if st.button(
            "🗑️ Clear Chat", 
            use_container_width=True,
            help="Clear all chat messages"
        ):
            st.session_state.messages = []
            st.rerun()

    # ========== DASHBOARD ==========
    elif view == "📊 Dashboard":
        st.subheader("📊 Analytics Dashboard")

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            total_records = len(filtered_df) if not filtered_df.empty else 0
            st.metric("Total Records", total_records)
        with m2:
            unique_trains = filtered_df[train_col].nunique() if train_col else 0
            st.metric("Unique Trains", unique_trains)
        with m3:
            berth_col = next((c for c in filtered_df.columns if 'BERTH' in str(c).upper() or 'T/BERTHS' in str(c).upper()), None)
            total_berths = 0
            if berth_col and berth_col in filtered_df:
                total_berths = pd.to_numeric(filtered_df[berth_col], errors='coerce').sum()
            st.metric("Total Berths", int(total_berths) if total_berths else 0)
        with m4:
            expired = 0
            doj_col = next((c for c in filtered_df.columns if 'DOJ' in str(c).upper()), None)
            if doj_col and doj_col in filtered_df:
                expired = sum(1 for _, r in filtered_df.iterrows() if is_expired(r.get(doj_col, '')))
            st.metric("Expired DOJ", expired)

        st.markdown("---")

        if not filtered_df.empty:
            # Train‑wise bar chart
            if train_col:
                train_counts = filtered_df[train_col].value_counts().reset_index()
                train_counts.columns = ['Train', 'Count']
                fig_bar = px.bar(train_counts.head(15), x='Train', y='Count', title="Top 15 Trains by EQ Count",
                                 color='Count', color_continuous_scale='Blues')
                fig_bar.update_layout(height=400, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_bar, use_container_width=True)

            # Pie chart for class distribution (if available)
            class_col = next((c for c in filtered_df.columns if 'CLASS' in c.upper()), None)
            if class_col:
                class_counts = filtered_df[class_col].value_counts().reset_index()
                class_counts.columns = ['Class', 'Count']
                fig_pie = px.pie(class_counts, names='Class', values='Count', title="Class Distribution", hole=0.4)
                fig_pie.update_layout(height=350, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_pie, use_container_width=True)

            # DOJ trend
            if doj_col:
                df_temp = filtered_df.copy()
                df_temp['_date'] = pd.to_datetime(df_temp[doj_col], format='%d-%m-%Y', errors='coerce')
                if df_temp['_date'].isna().all():
                    df_temp['_date'] = pd.to_datetime(df_temp[doj_col], errors='coerce')
                daily = df_temp.groupby('_date').size().reset_index(name='count')
                if not daily.empty:
                    fig_line = px.line(daily, x='_date', y='count', title="Daily Trend", markers=True,
                                       labels={'_date': 'Date', 'count': 'Records'},
                                       color_discrete_sequence=['#ff6b6b'])
                    fig_line.update_layout(height=300, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig_line, use_container_width=True)

            # Train-wise count table
            with st.expander("📊 Train-wise EQ Count (Full List)", expanded=False):
                if train_col:
                    train_counts_full = filtered_df[train_col].value_counts().reset_index()
                    train_counts_full.columns = ['Train Number', 'EQ Count']
                    st.dataframe(train_counts_full, use_container_width=True, height=400)

        else:
            st.info("No data for charts. Adjust filters or choose another sheet.")

    # ========== DATA TABLE ==========
    else:
        st.subheader(f"📋 {sheet_choice}  —  {len(filtered_df)} rows")

        # ---------- STATS ROW ----------
        if not filtered_df.empty:
            col_stats = st.columns(4)
            with col_stats[0]:
                st.metric("Total", len(filtered_df))
            with col_stats[1]:
                expired_count = sum(1 for _, r in filtered_df.iterrows() if is_expired(r.get('DOJ', '')))
                st.metric("Expired", expired_count, delta=-expired_count if expired_count > 0 else None)
            with col_stats[2]:
                train_col = next((c for c in filtered_df.columns if 'T/N' in str(c).upper()), None)
                unique_trains = filtered_df[train_col].nunique() if train_col else 0
                st.metric("Unique Trains", unique_trains)
            with col_stats[3]:
                berth_col = next((c for c in filtered_df.columns if 'T/BERTHS' in str(c).upper()), None)
                total_berths = 0
                if berth_col:
                    total_berths = pd.to_numeric(filtered_df[berth_col], errors='coerce').sum()
                st.metric("Total Berths", int(total_berths) if total_berths else 0)

            # ----- Train counts as chip boxes (HAR TRAIN KA ALAG BOX) -----
            if train_col and not filtered_df.empty:
                train_counts_series = filtered_df[train_col].value_counts()
                chips = []
                for train, count in train_counts_series.items():
                    chips.append(f'<span class="train-count-item" title="Train {train}: {count} EQ requests">{train}: {count}</span>')
                chips_html = "".join(chips)
                total_eq = len(filtered_df)
                st.markdown(f"""
                <div class="train-count-box">
                    🚆 Train Counts: {chips_html}
                    <span class="train-count-total" title="Total EQ requests across all trains">Total EQ: {total_eq}</span>
                </div>
                """, unsafe_allow_html=True)
            st.markdown("---")

        # Refresh button
        if st.button(
            "🔄 Refresh Data", 
            use_container_width=False,
            help="Reload current sheet data from Google Sheets"
        ):
            st.cache_data.clear()
            st.session_state.last_refresh = time.time()
            log_activity("🔄 Manual refresh from main")
            st.rerun()

        if filtered_df.empty:
            st.info("No data to show. Clear filters or select another sheet.")
        else:
            page_size = st.selectbox(
                "Rows per page", 
                [15, 25, 50, 100], 
                index=1, 
                key="page_size",
                help="Number of rows to display per page"
            )
            total_pages = max(1, math.ceil(len(filtered_df) / page_size))

            if st.session_state.current_page > total_pages:
                st.session_state.current_page = total_pages
            if st.session_state.current_page < 1:
                st.session_state.current_page = 1

            nav1, nav2, nav3 = st.columns([1, 2, 1])
            with nav1:
                if st.button("◀ Previous", use_container_width=True, disabled=st.session_state.current_page <= 1):
                    st.session_state.current_page -= 1
                    st.rerun()
            with nav2:
                st.markdown(f"<div style='text-align:center; padding-top:6px;'><b>Page {st.session_state.current_page} of {total_pages}</b></div>", unsafe_allow_html=True)
            with nav3:
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

            # Data editor
            edited_page = st.data_editor(
                display_df,
                use_container_width=True,
                height=400,
                column_config={
                    "Select": st.column_config.CheckboxColumn("Select", width="small")
                },
                key=f"editor_{sheet_choice}_{st.session_state.current_page}"
            )

            select_all = st.checkbox("Select All", value=st.session_state.select_all, key="select_all_checkbox")
            if select_all != st.session_state.select_all:
                st.session_state.select_all = select_all
                if select_all:
                    edited_page['Select'] = True
                else:
                    edited_page['Select'] = False
                st.rerun()

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

            pnr_col = next((c for c in edited_page.columns if 'PNR' in str(c).upper()), None)
            selected_pnrs = edited_page.loc[selected_indices, pnr_col].tolist() if pnr_col and selected_indices else []

            st.markdown('<div class="action-box">', unsafe_allow_html=True)
            st.markdown("**⚡ Quick Actions**")

            a1, a2, a3, a4, a5 = st.columns(5)

            with a1:
                if st.button(
                    "💾 Save Edits", 
                    use_container_width=True,
                    help="Save any changes made in the data editor back to Google Sheets"
                ):
                    try:
                        gc = init_sheets()
                        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                        data_to_update = edited_page.drop(columns=["Select"], errors='ignore')
                        data_list = data_to_update.values.tolist()

                        if data_list and sheet_rows:
                            for i, row_data in enumerate(data_list):
                                sheet_row_num = sheet_rows[i]
                                row_data = [str(x) if pd.notna(x) else '' for x in row_data]
                                num_cols = len(row_data)
                                col_letter = col_index_to_letter(num_cols)
                                range_name = f"A{sheet_row_num}:{col_letter}{sheet_row_num}"
                                sheet.update(range_name, [row_data])
                            st.toast("✅ Saved!", icon="💾")
                            log_activity(f"💾 Saved {len(data_list)} rows in {sheet_choice}")
                            st.cache_data.clear()
                            st.session_state.last_refresh = time.time()
                            time.sleep(0.3)
                            st.rerun()
                        else:
                            st.warning("Nothing to save")
                    except Exception as e:
                        if "429" in str(e):
                            st.error("Write quota exceeded. Wait 1 minute.")
                        else:
                            st.error(f"Save error: {e}")
                        log_activity(f"❌ Save: {str(e)[:40]}")

            with a2:
                if st.button(
                    "➕ Add Row", 
                    use_container_width=True,
                    help="Append a new blank row at the end of the sheet"
                ):
                    try:
                        gc = init_sheets()
                        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                        all_data = sheet.get_all_values()
                        num_cols = len(all_data[0]) if all_data else 1
                        blank_row = [''] * num_cols
                        if len(all_data) >= start_row:
                            blank_row[0] = len(all_data) - start_row + 2
                        sheet.append_row(blank_row)
                        st.toast("✅ Row added", icon="➕")
                        log_activity(f"➕ Added row in {sheet_choice}")
                        st.cache_data.clear()
                        st.session_state.last_refresh = time.time()
                        time.sleep(0.3)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Add error: {e}")
                        log_activity(f"❌ Add: {str(e)[:40]}")

            with a3:
                if selected_sheet_rows:
                    if st.button(
                        "🗑️ Delete", 
                        use_container_width=True,
                        help="Delete selected rows from the sheet. Click once to confirm, twice to execute."
                    ):
                        if not st.session_state.delete_confirm:
                            st.session_state.delete_confirm = True
                            st.warning("Confirm delete by clicking again.")
                        else:
                            try:
                                gc = init_sheets()
                                sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                                for row_num in sorted(selected_sheet_rows, reverse=True):
                                    sheet.delete_rows(row_num)
                                st.toast(f"✅ Deleted {len(selected_sheet_rows)}", icon="🗑️")
                                log_activity(f"🗑️ Deleted {len(selected_sheet_rows)} from {sheet_choice}")
                                st.session_state.delete_confirm = False
                                st.cache_data.clear()
                                st.session_state.last_refresh = time.time()
                                time.sleep(0.3)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Delete error: {e}")
                                log_activity(f"❌ Delete: {str(e)[:40]}")
                else:
                    st.button(
                        "🗑️ Delete", 
                        disabled=True, 
                        use_container_width=True,
                        help="Select rows to enable deletion"
                    )
                    st.session_state.delete_confirm = False

            with a4:
                # WhatsApp share: text + image download + PDF download
                msg = build_whatsapp_message(sheet_choice, len(selected_indices), selected_pnrs, len(filtered_df), filtered_df)
                encoded = urllib.parse.quote(msg)
                wa_url = f"https://api.whatsapp.com/send?text={encoded}"
                st.link_button(
                    "📤 WhatsApp Text", 
                    wa_url, 
                    use_container_width=True,
                    help="Share selected data as text message on WhatsApp"
                )

                # Image download
                if not filtered_df.empty:
                    img_bytes = create_table_image(filtered_df, f"{sheet_choice} Table")
                    if img_bytes:
                        st.download_button(
                            "🖼️ Download Table as Image",
                            data=img_bytes,
                            file_name=f"{sheet_choice}_table.png",
                            mime="image/png",
                            use_container_width=True,
                            help="Download PNG and then share on WhatsApp"
                        )

                # PDF download
                try:
                    export_df = filtered_df.drop(columns=['_sheet_row'], errors='ignore')
                    pdf_bytes = generate_pdf(export_df, sheet_choice, full=True)
                    st.download_button(
                        "📥 Download PDF",
                        data=pdf_bytes,
                        file_name=f"{sheet_choice}_{now_ist().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        help="Download full data as PDF document"
                    )
                except:
                    pass

            with a5:
                # PRINT – new tab with clean HTML table and auto print
                if not filtered_df.empty:
                    html_content = generate_print_html(filtered_df, f"{sheet_choice} Report")
                    b64_html = base64.b64encode(html_content.encode('utf-8')).decode('utf-8')
                    st.markdown(f"""
                    <div style="width:100%;">
                        <button onclick="printTable()" style="
                            background: linear-gradient(135deg, #7c3aed, #6d28d9);
                            color: white;
                            border: none;
                            border-radius: 8px;
                            padding: 9px 16px;
                            width: 100%;
                            font-weight: 600;
                            cursor: pointer;
                            font-size: 1rem;
                            transition: all 0.2s ease;
                        " onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 4px 12px rgba(124,58,237,0.3)'"
                        onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='none'"
                        title="Open print-friendly page in new tab with auto-print">🖨️ PRINT</button>
                    </div>
                    <script>
                    function printTable() {{
                        var win = window.open('', '_blank');
                        win.document.write(atob('{b64_html}'));
                        win.document.close();
                        win.onload = function() {{
                            win.print();
                            win.onafterprint = function() {{ win.close(); }};
                        }};
                    }}
                    </script>
                    """, unsafe_allow_html=True)
                else:
                    st.button(
                        "🖨️ PRINT", 
                        disabled=True, 
                        use_container_width=True,
                        help="Select data to enable printing"
                    )

            st.markdown('</div>', unsafe_allow_html=True)

            # ===== WHATSAPP IMAGE SHARE SECTION =====
            if not filtered_df.empty:
                st.markdown("---")
                render_whatsapp_image_share(filtered_df, sheet_choice)

            # ===== EXPORT =====
            st.markdown("**📄 Export**")
            e1, e2, e3, e4 = st.columns(4)
            with e1:
                try:
                    export_df = filtered_df.drop(columns=['_sheet_row'], errors='ignore')
                    pdf_bytes = generate_pdf(export_df, sheet_choice, full=True)
                    st.download_button(
                        "📥 PDF (All)",
                        data=pdf_bytes,
                        file_name=f"{sheet_choice}_{now_ist().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        help="Download all filtered data as PDF"
                    )
                except Exception as e:
                    st.warning(f"PDF error: {e}")

            with e2:
                if selected_indices:
                    export_sel = filtered_df.iloc[selected_indices].drop(columns=['_sheet_row'], errors='ignore')
                else:
                    export_sel = filtered_df.drop(columns=['_sheet_row'], errors='ignore')
                csv_sel = export_sel.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 CSV (Selected)" if selected_indices else "📥 CSV (All)",
                    data=csv_sel,
                    file_name=f"{sheet_choice}_{now_ist().strftime('%Y%m%d_%H%M')}_selected.csv",
                    mime="text/csv",
                    use_container_width=True,
                    help="Download data as CSV file"
                )

            with e3:
                export_df = filtered_df.drop(columns=['_sheet_row'], errors='ignore')
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                    export_df.to_excel(writer, sheet_name=sheet_choice, index=False)
                excel_data = excel_buffer.getvalue()
                st.download_button(
                    "📥 Excel",
                    data=excel_data,
                    file_name=f"{sheet_choice}_{now_ist().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    help="Download data as Excel file"
                )

            with e4:
                csv_full = filtered_df.drop(columns=['_sheet_row'], errors='ignore').to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📋 Copy CSV",
                    data=csv_full,
                    file_name="table.csv",
                    mime="text/csv",
                    use_container_width=True,
                    help="Download CSV and then you can copy its content"
                )

    st.markdown("""
    <div class='pro-footer'>
        🚂 AI EQMS Hub Pro • Created by Sharique<br>
        © 2026 All Rights Reserved
    </div>
    """)


if __name__ == "__main__":
    main()
