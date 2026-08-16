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

# ------------------------------------------------------------------
# NTES client (try to import, show warning if missing)
# ------------------------------------------------------------------
try:
    from ntes import NTESClient
    ntes_client = NTESClient()
    NTES_AVAILABLE = True
except ImportError:
    NTES_AVAILABLE = False
    st.warning("⚠️ 'ntes-client' not installed. Railway features will be disabled. Run: pip install ntes-client")

# ------------------------------------------------------------------
# Streamlit page config
# ------------------------------------------------------------------
st.set_page_config(page_title="AI EQMS Hub Pro", page_icon="🚂", layout="wide", initial_sidebar_state="expanded")

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

# ------------------------------------------------------------------
# Secrets and credentials
# ------------------------------------------------------------------
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
GSPREAD_CREDENTIALS = st.secrets.get("GSPREAD_CREDENTIALS")
WEATHER_API_KEY = st.secrets.get("WEATHER_API_KEY", "7fff411d9ecb183d6053870fc40823c9")
DRIVE_FOLDER_ID = "1H1gf8WqfoTYFT_pU9WfIDLrHg-NpuUSI"
SHEET_ID = "1QcS3ZF3YYxSEykG0KiOUuXbTdBh0DMHdMgoqa9t8yrI"

if not GEMINI_API_KEY or not GSPREAD_CREDENTIALS:
    st.error("❌ Missing credentials! Please check secrets.toml")
    st.stop()

# ------------------------------------------------------------------
# Session state defaults
# ------------------------------------------------------------------
defaults = {
    'messages': [], 'activity_log': [], 'last_uploaded_file': None,
    'last_uploaded_drive_url': None, 'last_uploaded_view_url': None,
    'last_uploaded_print_url': None, 'last_refresh': time.time(),
    'chat_suggestions': [
        "Show me EQ summary", "How many records today?", "Train wise breakup",
        "Pending EQ requests", "Quota status", "PNR status"
    ],
    'theme': 'Auto (System)', 'custom_bg': '#ffffff', 'custom_text': '#000000',
    'current_page': 1, 'pnr_val': '', 'train_val': '', 'from_val': None,
    'to_val': None, 'upload_success': False, 'last_upload_time': None,
    'selected_sheet': "EQ", 'view_mode': "📋 Data Table",
    'select_all': False, 'delete_confirm': False,
    'auto_theme_detected': False, 'sidebar_collapsed': False,
    'quick_filter_train': '', 'show_keyboard_help': False, 'print_trigger': False,
    'sch_start': 0, 'sch_data': None, 'weather_data': None,
    'system_theme': 'Day', 'weather_city': 'Tinsukia',
    'pnr_result': None, 'train_result': None,
    'last_uploaded_drive_id': None,
    'manual_refresh': False,
    'original_file_bytes': None,
    'original_file_mime': None,
    'live_sync': False,
    'last_sheet_sync': None,
}

for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ------------------------------------------------------------------
# Flag hours detection (Memory 15)
# ------------------------------------------------------------------
def is_flag_hours():
    now = now_ist()
    sunrise = now.replace(hour=6, minute=0, second=0, microsecond=0)
    sunset = now.replace(hour=18, minute=30, second=0, microsecond=0)
    return sunrise <= now <= sunset

# ------------------------------------------------------------------
# Date helper functions for Railway tab
# ------------------------------------------------------------------
def get_date_label(offset):
    target = datetime.now() - timedelta(days=offset)
    day = target.day
    suffix = {1:'st', 2:'nd', 3:'rd'}.get(day%10 if day not in [11,12,13] else 0, 'th')
    return f"{day}{suffix} {target.strftime('%b')}"

def get_date_for_offset(offset):
    return (datetime.now() - timedelta(days=offset)).strftime("%d-%b-%Y")

# ------------------------------------------------------------------
# Station map
# ------------------------------------------------------------------
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

# ------------------------------------------------------------------
# Cached resources
# ------------------------------------------------------------------
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

# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------
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

def log_activity(action: str):
    st.session_state.activity_log.append({'timestamp': format_time(), 'action': action})
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

# ------------------------------------------------------------------
# Sheet configuration and loading
# ------------------------------------------------------------------
EQ_HEADINGS = [
    'S/N', 'PNR', 'FROM', 'TO', 'BOARDING', 'T/N', 'CLASS', 'DOJ',
    'PASS NAME', 'PASS PH', 'T/BERTHS', 'PURPOSE', 'ADDRESS',
    'DIARY NO', 'RECOMMENDATION', 'DESIGNATION', 'PHONE NUBER',
    'MP/MLA/MR/MINISTER/VIP/VVIP', 'WARRANT NUMBER', 'PROCEESING DATE+TIME',
    'APPLICATION DATE', 'RAILWAY/ZONE/DIVISION', 'PREFERENCE'
]

SHEET_CONFIG = {
    "EQ": {"start_row": 5, "pnr_col": 1, "train_col": 5, "doj_col": 7, "headings": EQ_HEADINGS},
    "DATA": {"start_row": 4, "pnr_col": 1, "train_col": 5, "doj_col": 7, "headings": EQ_HEADINGS},
    "FINAL": {"start_row": 6, "pnr_col": 7, "train_col": 1, "doj_col": 12, "headings": EQ_HEADINGS},
    "DATA2": {"start_row": 4, "pnr_col": 7, "train_col": 1, "doj_col": 12, "headings": EQ_HEADINGS},
    "EMAIL_DATA": {"start_row": 2, "pnr_col": 7, "train_col": 8, "doj_col": 11, "headings": EQ_HEADINGS},
    "NOTE": {"start_row": 2, "pnr_col": None, "train_col": 0, "doj_col": None, "headings": []}
}

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
        st.session_state.last_sheet_sync = format_datetime()
        return df
    except Exception as e:
        st.error(f"Error loading {sheet_name}: {e}")
        return pd.DataFrame()

# ------------------------------------------------------------------
# Gemini Universal Parser (from Telegram bot)
# ------------------------------------------------------------------
def smart_detect_warrant(text):
    if not text:
        return {'warrant': '', 'found': False}
    text = str(text).upper()
    patterns = [
        r'IC[-_\s]*(\d{2,4})',
        r'WARRANT\s*NO\.?\s*[:#]?\s*([A-Z0-9\-]+)',
        r'WARRANT\s*NUMBER\s*[:#]?\s*([A-Z0-9\-]+)',
        r'W[/\-]?NO\.?\s*[:#]?\s*([A-Z0-9\-]+)',
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
    clean_text = re.sub(r'\s+', ' ', text).strip()

    patterns = [
        r'RAIL\s*BOARD',
        r'OFFICE\s*OF\s*(?:THE\s*)?HON\'BLE\s*MINISTER\s*RAILWAYS',
        r'OFFICE\s*OF\s*(?:THE\s*)?HONOURABLE\s*MINISTER\s*RAILWAYS',
        r'HON\'BLE\s*MINISTER\s*RAILWAYS',
        r'HONOURABLE\s*MINISTER\s*RAILWAYS',
        r'MINISTER\s*RAILWAYS',
        r'MINISTRY\s*OF\s*RAILWAYS',
        r'RAIL\s*MANTRI',
        r'RAIL\s*BHAWAN'
    ]

    for pattern in patterns:
        if re.search(pattern, clean_text):
            return {'isRailBoard': True}

    keywords = ['MINISTER', 'RAILWAYS', 'RAILWAY', 'HONBLE', "HON'BLE", 'RAIL MANTRI', 'OFFICE', 'RAIL', 'BOARD']
    score = 0
    for kw in keywords:
        if kw in clean_text:
            score += 1
    if score >= 4:
        return {'isRailBoard': True}

    if 'OFFICE' in clean_text and 'MINISTER' in clean_text and ('RAILWAYS' in clean_text or 'RAILWAY' in clean_text):
        office_idx = clean_text.find('OFFICE')
        minister_idx = clean_text.find('MINISTER')
        if office_idx != -1 and minister_idx != -1 and abs(office_idx - minister_idx) < 50:
            return {'isRailBoard': True}

    return {'isRailBoard': False}

def smart_detect_diary(text):
    if not text:
        return {'diary': '', 'found': False}
    text = str(text).upper()
    patterns = [
        r'DIARY\s*NO\.?\s*[:#]?\s*([A-Z0-9/\-]+)',
        r'DIARY\s*NUMBER\s*[:#]?\s*([A-Z0-9/\-]+)',
        r'D/?NO\.?\s*[:#]?\s*([A-Z0-9/\-]+)'
    ]
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
    if 'OSD' in text:
        return 'OSD'
    if 'PMO' in text:
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

def process_extracted_records(records):
    cleaned = []
    seen = set()
    for rec in records:
        pnr = clean_pnr(rec.get('PNR', ''))
        if not pnr or pnr in seen:
            continue
        seen.add(pnr)

        full_text = ' '.join([
            str(rec.get('PURPOSE', '')), str(rec.get('ADDRESS', '')),
            str(rec.get('RECOMMENDATION', '')), str(rec.get('DESIGNATION', '')),
            str(rec.get('DIARY_NO', '')), str(rec.get('PASS_NAME', '')),
            str(rec.get('PASS_PH', '')), str(rec.get('PHONE_NUBER', '')),
            str(rec.get('WARRANT_NO', '')), str(rec.get('VIP_STATUS', ''))
        ])

        zone = str(rec.get('RAILWAY_ZONE', '')).strip()
        pref = str(rec.get('PREFERENCE', 'General')).strip()
        vip = str(rec.get('VIP_STATUS', '')).strip().upper()
        diary_val = str(rec.get('DIARY_NO', '')).strip()
        warrant_val = str(rec.get('WARRANT_NO', '')).strip()

        rail_board = smart_detect_rail_board(full_text)
        if rail_board['isRailBoard']:
            zone = 'RAIL BOARD'
            pref = 'RAIL BOARD'
            vip = 'MINISTER'
            diary_val = 'RAIL BOARD'

        if not warrant_val:
            warrant = smart_detect_warrant(full_text)
            if warrant['found']:
                warrant_val = warrant['warrant']

        if not diary_val or diary_val == '-' or diary_val == '':
            diary = smart_detect_diary(full_text)
            if diary['found']:
                diary_val = diary['diary']

        if not vip:
            detected_vip = smart_detect_vip(full_text)
            if detected_vip:
                vip = detected_vip

        if smart_detect_lower_seat(full_text) and (pref == 'General' or pref == '' or pref == '-'):
            pref = 'Lower Seat'

        if not pref or pref == '' or pref == '-':
            pref = 'General'

        doj_raw = str(rec.get('DOJ', '')).strip()
        doj_parsed = parse_date(doj_raw)
        if not doj_parsed or doj_parsed == 'Invalid Date' or doj_parsed == 'NaN-NaN-NaN':
            doj_parsed = ''

        clean_record = {
            'PNR': pnr,
            'T_N': str(rec.get('T_N', '')).strip(),
            'CLASS': str(rec.get('CLASS', '')).strip().upper(),
            'DOJ': doj_parsed,
            'FROM': str(rec.get('FROM', '')).strip().upper(),
            'TO': str(rec.get('TO', '')).strip().upper(),
            'BOARDING': str(rec.get('BOARDING', '')).strip().upper(),
            'PASS_NAME': str(rec.get('PASS_NAME', '')).strip(),
            'PASS_PH': clean_phone(str(rec.get('PASS_PH', ''))),
            'T_BERTHS': int(rec.get('T_BERTHS', 1)) if str(rec.get('T_BERTHS', '')).isdigit() else 1,
            'PURPOSE': str(rec.get('PURPOSE', '')).strip(),
            'ADDRESS': str(rec.get('ADDRESS', '')).strip(),
            'DIARY_NO': diary_val,
            'RECOMMENDATION': str(rec.get('RECOMMENDATION', '')).strip(),
            'DESIGNATION': str(rec.get('DESIGNATION', '')).strip(),
            'VIP_STATUS': vip,
            'APPLICATION_DATE': parse_date(str(rec.get('APPLICATION_DATE', ''))),
            'RAILWAY_ZONE': zone,
            'PREFERENCE': pref,
            'PHONE_NUBER': clean_phone(str(rec.get('PHONE_NUBER', ''))),
            'WARRANT_NO': warrant_val
        }
        cleaned.append(clean_record)

    if not cleaned:
        return {'error': 'No valid records extracted'}
    return {'records': cleaned, 'count': len(cleaned)}

def gemini_universal_parser(input_data, input_type, mime_type, progress_callback=None):
    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}'

    system_prompt = """You are TSKEQ Bot's AI extraction engine. You are an EXPERT at reading messy, handwritten, torn, or low-quality railway forms.

=== YOUR SPECIAL SKILL ===
You can read ANY handwriting - no matter how messy, scribbled, or torn the paper is.
You understand Indian railway form formats perfectly.

=== WHAT YOU ARE READING ===
This is a railway EQ (Emergency Quota) application form. It contains passenger details for train reservation.

=== FIELDS TO EXTRACT (21 fields) ===
1. PNR - 10 digit number (look for 10 digits)
2. T_N (Train Number) - 3 to 5 digits
3. CLASS - SL, 2A, 3A, CC, 1A, 2S, etc.
4. DOJ (Date of Journey) - Convert to DD-MM-YYYY
5. FROM - Station code (3-4 capital letters)
6. TO - Station code (3-4 capital letters)
7. BOARDING - Station code (optional)
8. PASS_NAME - Passenger full name
9. PASS_PH - 10 digit phone number
10. T_BERTHS - Number of berths (default 1)
11. PURPOSE - Purpose of travel
12. ADDRESS - Full address
13. DIARY_NO - Diary number
14. RECOMMENDATION - Recommender's name/designation
15. DESIGNATION - Designation of recommender
16. VIP_STATUS - MP, MLA, MR, MINISTER, VIP, VVIP
17. APPLICATION_DATE - Date of application
18. RAILWAY_ZONE - Zone (NFR, NR, ER, etc.)
19. PREFERENCE - General, MP, MLA, MR, etc.
20. PHONE_NUBER - Recommender's phone
21. WARRANT_NO - Warrant number (IC-240, MP-123, etc.)

=== HANDWRITTEN IMAGE TIPS ===
1. If you see scribbled text, try to recognize patterns:
   - 10 digits together = PNR
   - 3-5 digits = Train number
   - 3-4 capital letters = Station code
   - 10 digits with +91 = Phone number
   - Names are usually in capital letters
   - Dates are in DD/MM/YYYY or DD-MM-YYYY format

2. For messy handwriting:
   - Look at the context of the form
   - Each field has a label next to it
   - Use the label to understand what the value is
   - If a value is unreadable, leave it empty

3. Common patterns to recognize:
   - "PNR:" or "PNR No." followed by 10 digits
   - "Train:" or "T/N:" followed by 3-5 digits
   - "From:" or "F:" followed by station code
   - "To:" or "T:" followed by station code
   - "Date:" or "DOJ:" followed by date
   - "Name:" or "Passenger:" followed by name
   - "Phone:" or "Mob:" followed by 10 digits

=== RAIL BOARD RULE ===
ONLY set DIARY_NO="RAIL BOARD", RAILWAY_ZONE="RAIL BOARD", PREFERENCE="RAIL BOARD", VIP_STATUS="MINISTER" if you see:
- "OFFICE OF THE HON'BLE MINISTER RAILWAYS" OR
- "MINISTER RAILWAYS" OR
- "RAIL MANTRI" OR
- "RAIL BHAWAN"
Otherwise, leave these fields empty.

=== EXTRACTION RULES ===
1. PNR: 10 digits only. Remove any extra characters.
2. Train Number: 3-5 digits. Remove DN/UP suffix.
3. DOJ: Convert to DD-MM-YYYY. "24/25.06.26" -> "24-06-2026"
4. Phone: Remove all non-digits, then take the LAST 10 digits. Example: "+919138328565" -> "9138328565"
5. Berths: Number only. Default 1.
6. Warrant: Look for "IC-240", "MP-123", "WARRANT NO:", "W/No."
7. Diary: Look for "DIARY NO:", "D/No."
8. VIP: Check for MP, MLA, MR, MINISTER, VIP, VVIP
9. Lower Seat: If you see "MEDICAL", "HANDICAP", "SR CITIZEN", "AGE+", set PREFERENCE = "Lower Seat"

=== OUTPUT FORMAT ===
Return ONLY a valid JSON array. Example with 1 record:
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

CRITICAL: Return ONLY the JSON array. No explanations, no extra text. If you can't read something, leave it empty. Better to leave empty than to guess wrong."""

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
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 16384}
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
                return {'error': 'Could not parse Gemini response', 'raw': response_text[:500]}
        else:
            json_str = json_match.group(0)

        json_str = json_str.replace('```json', '').replace('```', '').strip()
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*\]', ']', json_str)
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
        return {'error': f'Parser Error: {e}'}

# ------------------------------------------------------------------
# Drive upload and sheet save (FIXED: 403 handling + original file print)
# ------------------------------------------------------------------
def upload_to_drive(file_bytes, filename, mime_type):
    try:
        drive_service = init_drive()
        # Verify folder access first to catch 403 early
        try:
            drive_service.files().get(fileId=DRIVE_FOLDER_ID, fields="id").execute()
        except Exception as e:
            if "403" in str(e) or "forbidden" in str(e).lower():
                return {'success': False, 'error': '403 Forbidden: Service account cannot access Drive folder. Please share the folder with the service account email and grant Editor role.'}
            raise e
        file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=True)
        file = drive_service.files().create(
            body=file_metadata, media_body=media,
            fields='id,name,webViewLink,size'
        ).execute()
        file_id = file.get('id')
        return {
            'success': True, 'id': file_id, 'name': file.get('name'),
            'url': file.get('webViewLink'), 'size': file.get('size'),
            'view_url': f"https://drive.google.com/file/d/{file_id}/view",
            'print_url': f"https://drive.google.com/file/d/{file_id}/preview",
            'download_url': f"https://drive.google.com/uc?export=download&id={file_id}",
            'embed_url': f"https://drive.google.com/file/d/{file_id}/preview?usp=drive_link"
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

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

# ------------------------------------------------------------------
# Weather API function
# ------------------------------------------------------------------
def get_weather(city_name):
    if not city_name:
        return {'error': 'Please enter a city name'}
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={WEATHER_API_KEY}&units=metric"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {
                'city': data.get('name', city_name),
                'country': data.get('sys', {}).get('country', ''),
                'temp': data.get('main', {}).get('temp', 'N/A'),
                'feels_like': data.get('main', {}).get('feels_like', 'N/A'),
                'humidity': data.get('main', {}).get('humidity', 'N/A'),
                'pressure': data.get('main', {}).get('pressure', 'N/A'),
                'weather': data.get('weather', [{}])[0].get('description', 'N/A'),
                'icon': data.get('weather', [{}])[0].get('icon', ''),
                'wind_speed': data.get('wind', {}).get('speed', 'N/A'),
                'wind_deg': data.get('wind', {}).get('deg', 'N/A'),
                'sunrise': data.get('sys', {}).get('sunrise', 'N/A'),
                'sunset': data.get('sys', {}).get('sunset', 'N/A')
            }
        else:
            return {'error': f'City not found. Please check the name.'}
    except Exception as e:
        return {'error': f'Error fetching weather: {str(e)}'}

# ------------------------------------------------------------------
# NTES-based railway functions (EXACT from Telegram bot)
# ------------------------------------------------------------------
def safe_list(data, key):
    val = data.get(key) if data else None
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]

def safe_str(val, default='N/A'):
    return str(val) if val is not None else default

def format_station_time(time_str):
    if not time_str or time_str in ['N/A', 'Source', 'Dest']:
        return time_str
    time_parts = time_str.split()
    if len(time_parts) >= 2 and any(m in time_parts[1] for m in ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']):
        return time_parts[0]
    return time_str

def get_stn_field(station, possible_keys, default=''):
    if not station or not isinstance(station, dict):
        return default
    for key in possible_keys:
        if key in station:
            return station[key]
    lower_map = {k.lower(): v for k, v in station.items()}
    for key in possible_keys:
        if key.lower() in lower_map:
            return lower_map[key.lower()]
    return default

def normalize_station(s):
    if not s or not isinstance(s, dict):
        return {'SC':'N/A','SN':'N/A','STA':'N/A','STD':'N/A','ETA':'','ETD':'','DAY':''}
    sta = s.get('STA','')
    std = s.get('STD','')
    eta = s.get('ETA','')
    etd = s.get('ETD','')
    day = s.get('Day', s.get('day', ''))
    return {'SC': get_stn_field(s, ['SC','StationCode','StnCode','Code','stationCode','stnCode','StnCd'], 'N/A'),
            'SN': get_stn_field(s, ['SN','StationName','StnName','Name','stationName','stnName'], 'N/A'),
            'STA': sta if sta else (eta if eta else 'N/A'),
            'STD': std if std else (etd if etd else 'N/A'),
            'ETA': eta, 'ETD': etd, 'DAY': safe_str(day, '')}

def find_station_index(stations, current_code, current_name, pos_str):
    if not stations:
        return -1, "none"
    if current_code:
        current_code = current_code.upper().strip()
    if current_name:
        current_name = current_name.upper().strip()
    if current_code:
        for i, s in enumerate(stations):
            if s.get('SC','').upper().strip() == current_code:
                return i, "code_exact"
    if current_code and len(current_code) >= 3:
        for i, s in enumerate(stations):
            sc = s.get('SC','').upper().strip()
            if sc and (current_code in sc or sc in current_code):
                return i, "code_contains"
    if current_name:
        for i, s in enumerate(stations):
            sn = s.get('SN','').upper().strip()
            if sn == current_name:
                return i, "name_exact"
    if current_name:
        for i, s in enumerate(stations):
            sn = s.get('SN','').upper().strip()
            if sn and (current_name in sn or sn in current_name):
                return i, "name_contain"
    if current_name:
        current_words = set(re.findall(r'[A-Z]{3,}', current_name))
        for i, s in enumerate(stations):
            sn = s.get('SN','').upper().strip()
            if current_words.intersection(set(re.findall(r'[A-Z]{3,}', sn))):
                return i, "name_word"
    return -1, "none"

def find_nearest_stoppage(stations, current_code, current_name, pos_str):
    if not stations:
        return -1, "none"
    idx, _ = find_station_index(stations, current_code, current_name, pos_str)
    if idx >= 0:
        return idx, "direct"
    pos_lower = pos_str.lower()
    if 'between' in pos_lower:
        match = re.search(r'between\s+([A-Z]+)\s+and\s+([A-Z]+)', pos_str, re.IGNORECASE)
        if match:
            next_code = match.group(2).upper()
            for i, s in enumerate(stations):
                if s.get('SC','').upper().strip() == next_code:
                    return i, "between"
    patterns = [r'after\s+([A-Z]+)\s+before\s+([A-Z]+)', r'from\s+([A-Z]+)\s+to\s+([A-Z]+)']
    for pattern in patterns:
        match = re.search(pattern, pos_str, re.IGNORECASE)
        if match:
            next_code = match.group(2).upper()
            for i, s in enumerate(stations):
                if s.get('SC','').upper().strip() == next_code:
                    return i, "pattern"
    return -1, "none"

def get_full_schedule(train_number):
    try:
        return [normalize_station(s) for s in safe_list(ntes_client.schedule(train_number), 'stations')
                if (s.get('STA') and s.get('STA') != 'N/A') or (s.get('STD') and s.get('STD') != 'N/A')
                or s.get('STA') == 'Source' or s.get('STD') == 'Dest']
    except:
        return []

def get_pnr_status(pnr):
    if not NTES_AVAILABLE:
        return {"error": "NTES library not installed"}
    try:
        response = ntes_client.pnr_status(pnr)
        if not response:
            return None
        err_msg = response.get('errorMessage', '')
        if err_msg and 'FLUSHED' in str(err_msg).upper():
            return {"error": "FLUSHED_PNR"}
        if not response.get('pnrNumber'):
            return None
        passengers = []
        for p in safe_list(response, 'passengerList'):
            passengers.append({
                'booking_status': safe_str(p.get('bookingStatusDetails'), 'N/A'),
                'current_status': safe_str(p.get('currentStatusDetails'), 'N/A')
            })
        return {
            "pnr": safe_str(response.get('pnrNumber')),
            "train_number": safe_str(response.get('trainNumber')),
            "train_name": safe_str(response.get('trainName')),
            "journey_date": safe_str(response.get('dateOfJourney')),
            "class": safe_str(response.get('journeyClass')),
            "quota": safe_str(response.get('quota')),
            "chart_status": safe_str(response.get('chartStatus'), 'Not Prepared'),
            "boarding_point": safe_str(response.get('boardingPoint')),
            "destination": safe_str(response.get('destinationStation')),
            "passengers": passengers
        }
    except Exception as e:
        return {"error": str(e)}

def get_live_train_status(train_number, date_str=None):
    if not NTES_AVAILABLE:
        return {"error": "NTES library not installed"}
    try:
        if date_str is None:
            date_str = datetime.now().strftime("%d-%b-%Y")
        date_formats = [date_str, date_str.replace('-', ' '), date_str.replace('-', '/')]
        response = None
        for fmt in date_formats:
            try:
                response = ntes_client.live_status(train_number, fmt)
                if response and response.get('CPOS'):
                    break
            except:
                continue
        if not response:
            return {"error": "NO_DATA", "message": "Empty response from NTES"}
        # Debug: log available keys
        resp_keys = list(response.keys()) if isinstance(response, dict) else []
        if not response.get('CPOS'):
            # Try alternative keys that NTES might use
            cpos_alt = response.get('cpos') or response.get('currentPosition') or response.get('CurrentPosition') or response.get('position')
            if cpos_alt:
                response['CPOS'] = cpos_alt
            else:
                return {"error": "NO_DATA", "message": f"No position data. Keys: {resp_keys[:10]}"}
        train_name = safe_str(response.get('TNM'), 'N/A')
        source = safe_str(response.get('SRCN', response.get('DFROM')), 'N/A')
        destination = safe_str(response.get('DSTNN', response.get('DTO')), 'N/A')
        dest_code = safe_str(response.get('DST'), '')
        journey_date = safe_str(response.get('STD'), date_str)
        current_pos = safe_str(response.get('CPOS'), 'N/A')
        delay = safe_str(response.get('LDEL'), '0')
        excpt = safe_str(response.get('EXCP'), '')
        pos_str = str(current_pos)
        pos_lower = pos_str.lower()
        is_completed = any(k in pos_lower for k in ["reached destination", "journey completed", "terminated", "destination reached", "arrived at destination", "train completed", "train reached", "journey ended", "train terminated", "has terminated", "run terminated"])
        is_not_started = any(k in pos_lower for k in ["not started", "yet to start", "scheduled", "at source", "will start", "starts from", "origin", "before departure"])
        if not is_completed and destination != 'N/A':
            dest_upper = destination.upper()
            if any(w in pos_lower for w in ['arrived', 'reached', 'terminated', 'completed', 'ended']):
                dest_words = [w for w in dest_upper.split() if len(w) >= 3]
                for word in dest_words:
                    if word in pos_str.upper():
                        is_completed = True
                        break
        current_code = None
        current_name = None
        m = re.search(r'\(([A-Z]{2,5})\)', pos_str)
        if m:
            current_code = m.group(1).upper()
        if not current_code:
            for pattern in [r'from\s+([A-Z]{2,5})\b', r'at\s+([A-Z]{2,5})\b', r'(?:departed|arrived|left|reached)\s+(?:from\s+|at\s+)?([A-Z]{2,5})\b']:
                m = re.search(pattern, pos_str, re.IGNORECASE)
                if m:
                    current_code = m.group(1).upper()
                    break
        if not current_name:
            for pattern in [r'(?:from|at|departed|arrived|left|reached)\s+([A-Z][A-Z\s]+?)(?:\s*\(|$)', r'(?:has|is)\s+([A-Z][A-Z\s]+?)\s+(?:station|junction|jn)']:
                m = re.search(pattern, pos_str, re.IGNORECASE)
                if m:
                    current_name = re.sub(r'\s+(JUNCTION|JN|ROAD|RD|CITY|CANTT|NAGAR|NG)$', '', m.group(1).strip().upper())
                    break
        live_stations_map = {}
        stations_raw = safe_list(response, 'STNSD')
        if not stations_raw:
            stations_raw = safe_list(response, 'STNS')
        all_live = []
        for s in stations_raw:
            ns = normalize_station(s)
            if ns['SC'] != 'N/A':
                live_stations_map[ns['SC'].upper()] = ns
                all_live.append(ns)
        full_stations = get_full_schedule(train_number)
        merged_stations = []
        for s in full_stations:
            sc = s['SC'].upper()
            if sc in live_stations_map:
                live = live_stations_map[sc]
                merged = s.copy()
                for k in ['ETA','ETD','DAY','STA','STD']:
                    if live.get(k):
                        merged[k] = live[k]
                merged_stations.append(merged)
            else:
                merged_stations.append(s)
        upcoming = []
        mapped_idx = -1
        is_non_stoppage = False
        if is_completed:
            upcoming = []
        elif is_not_started:
            upcoming = merged_stations[:8]
        else:
            if merged_stations:
                curr_idx, match_type = find_station_index(merged_stations, current_code, current_name, pos_str)
                if curr_idx >= 0:
                    if curr_idx + 1 < len(merged_stations):
                        upcoming = merged_stations[curr_idx+1:curr_idx+9]
                    else:
                        is_completed = True
                else:
                    is_non_stoppage = True
                    mapped_idx, map_type = find_nearest_stoppage(merged_stations, current_code, current_name, pos_str)
                    if mapped_idx >= 0:
                        if mapped_idx + 1 < len(merged_stations):
                            upcoming = merged_stations[mapped_idx+1:mapped_idx+9]
                        else:
                            is_completed = True
                    elif all_live and (current_code or current_name):
                        live_idx, _ = find_station_index(all_live, current_code, current_name, pos_str)
                        if live_idx >= 0 and live_idx + 1 < len(all_live):
                            next_code = all_live[live_idx+1].get('SC', '').upper()
                            for i, ms in enumerate(merged_stations):
                                if ms.get('SC','').upper() == next_code:
                                    upcoming = merged_stations[i:i+8]
                                    break
                            if not upcoming:
                                upcoming = all_live[live_idx+1:live_idx+9]
                    if not upcoming:
                        return {"error": "NO_DATA", "message": "Train position unclear for this date"}
            elif all_live:
                curr_idx, _ = find_station_index(all_live, current_code, current_name, pos_str)
                if curr_idx >= 0:
                    upcoming = all_live[curr_idx+1:curr_idx+9]
                else:
                    return {"error": "NO_DATA", "message": "Train position unclear for this date"}
        if not upcoming and not is_completed and merged_stations:
            upcoming = merged_stations[:8]
        return {
            "train_number": train_number,
            "train_name": train_name,
            "current_station": current_pos,
            "source": source,
            "destination": destination,
            "journey_date": journey_date,
            "delay": delay,
            "journey_state": "completed" if is_completed else ("not_started" if is_not_started else "running"),
            "stations": upcoming[:8],
            "excpt": excpt,
            "last_updated": datetime.now().strftime('%d %b %H:%M:%S'),
            "query_date": date_str,
            "current_code": current_code,
            "current_name": current_name,
            "is_non_stoppage": is_non_stoppage,
            "mapped_idx": mapped_idx
        }
    except Exception as e:
        return {"error": "API_ERROR", "message": str(e)}

def search_trains(query):
    if not NTES_AVAILABLE:
        return None
    try:
        response = ntes_client.search(query)
        if not response or not response.get('trains'):
            return None
        trains = [{
            'train_number': safe_str(t.get('train_number')),
            'train_name': safe_str(t.get('train_name')),
            'source': safe_str(t.get('source')),
            'destination': safe_str(t.get('destination'))
        } for t in safe_list(response, 'trains')[:15]]
        return {"query": query, "trains": trains, "last_updated": datetime.now().strftime('%d %b %H:%M:%S')}
    except:
        return None

def get_train_schedule(train_number):
    if not NTES_AVAILABLE:
        return {"error": "NTES_NOT_INSTALLED"}
    try:
        response = ntes_client.schedule(train_number)
        if not response:
            return {"error": "NO_DATA"}
        stations = []
        for s in safe_list(response, 'stations'):
            sta = s.get('STA', '')
            std = s.get('STD', '')
            if (sta and sta != 'N/A') or (std and std != 'N/A') or sta == 'Source' or std == 'Dest':
                stations.append({
                    'code': safe_str(s.get('StationCode')),
                    'name': safe_str(s.get('StationName')),
                    'arrival': sta if sta else 'Source',
                    'departure': std if std else 'Dest',
                    'day': safe_str(s.get('Day'))
                })
        return {
            "train_number": train_number,
            "train_name": safe_str(response.get('TrainName')),
            "source": safe_str(response.get('Source')),
            "destination": safe_str(response.get('Destination')),
            "stations": stations,
            "last_updated": datetime.now().strftime('%d %b %H:%M:%S')
        }
    except Exception as e:
        return {"error": str(e)}

def get_confirmation_prediction(passengers, chart_status):
    if "prepared" in str(chart_status).lower() or not passengers:
        return None
    confirmed = 0
    for p in passengers:
        status = str(p.get('current_status', '')).upper()
        if 'CNF' in status:
            confirmed += 1
        elif 'RAC' in status:
            confirmed += 0.5
        elif 'PQWL' in status or 'WL' in status:
            try:
                if '/' in status:
                    confirmed += 0.7 if int(status.split('/')[-1]) <= 3 else 0.4 if int(status.split('/')[-1]) <= 5 else 0.1
            except:
                confirmed += 0.2
    base = (confirmed / len(passengers)) * 100
    if confirmed / len(passengers) < 0.5:
        base += 10
    return min(100, max(0, round(base)))

def get_status_icon(status, chart_status=None):
    status_upper = str(status).upper()
    if 'CAN' in status_upper:
        return "❌"
    if 'CNF' in status_upper:
        return "✅"
    if 'RAC' in status_upper:
        return "🟡"
    if 'PQWL' in status_upper or 'WL' in status_upper:
        return "🔴" if chart_status and "prepared" in str(chart_status).lower() else "⏱️"
    return "ℹ️"

def get_status_note(status, chart_status):
    status_upper = str(status).upper()
    if 'CAN' in status_upper:
        return "❌ Ticket Cancelled!"
    if 'CNF' in status_upper:
        return "✅ Confirmed!"
    if 'RAC' in status_upper:
        return "🟡 RAC - May get confirmed" if "prepared" in str(chart_status).lower() else "🟡 RAC - Chance of confirmation"
    if 'PQWL' in status_upper:
        if "prepared" in str(chart_status).lower():
            return "🔴 PQWL - Chart ready, waiting"
        try:
            num = int(status.split('/')[-1]) if '/' in status else 0
        except:
            num = 0
        if num <= 3:
            return "⏱️ PQWL - Good chance!"
        elif num <= 5:
            return "⏱️ PQWL - May confirm"
        return "⏱️ PQWL - Low chance"
    if 'WL' in status_upper:
        if "prepared" in str(chart_status).lower():
            return "🔴 WL - Chart ready, waiting"
        try:
            num = int(status.split('/')[-1]) if '/' in status else 0
        except:
            num = 0
        if num <= 5:
            return "⏱️ WL - Good chance!"
        elif num <= 10:
            return "⏱️ WL - May confirm"
        return "⏱️ WL - Low chance"
    return "ℹ️ Check status"

# ------------------------------------------------------------------
# Format functions (EXACT from Telegram bot, adapted for Streamlit markdown)
# ------------------------------------------------------------------
def format_pnr_result(data):
    if data and data.get('error') == "FLUSHED_PNR":
        return "❌ FLUSHED PNR / PNR NOT YET GENERATED\n\nPlease check the PNR number and try again."
    if not data:
        return "❌ PNR not found."
    pnr = data.get('pnr', 'N/A')
    train_no = data.get('train_number', 'N/A')
    train_name = data.get('train_name', 'N/A')
    journey_date = data.get('journey_date', 'N/A')
    class_code = data.get('class', 'N/A')
    quota = data.get('quota', 'N/A')
    chart_status = data.get('chart_status', 'N/A')
    boarding = data.get('boarding_point', 'N/A')
    destination = data.get('destination', 'N/A')
    passengers = data.get('passengers', [])
    is_cancelled = any('CAN' in str(p.get('current_status', '')).upper() for p in passengers)
    chart_prepared = "prepared" in str(chart_status).lower()
    chart_icon = "✅" if chart_prepared else "❌"
    chart_text = "Chart Prepared" if chart_prepared else "Chart Not Prepared"
    msg = f"🎟️ PNR: {pnr}\n🚃 Train Number: {train_no}\n🚇 Train Name: {train_name}\n📍 {boarding} ➡️ {destination}\n🗓️ Journey Date: {journey_date}\n😎 Class & Quota: {class_code} ({quota})\n📋 Chart Status: {chart_text} {chart_icon}\n"
    if not chart_prepared and not is_cancelled:
        pred = get_confirmation_prediction(passengers, chart_status)
        if pred is not None:
            msg += f"🎯 Confirmation: {'🟢' if pred >= 80 else '🟡' if pred >= 50 else '🔴'} {pred}% {'High' if pred >= 80 else 'Medium' if pred >= 50 else 'Low'} Chance\n"
    msg += "\n👫 Passenger List 👫\n"
    circles = ["❶", "❷", "❸", "❹", "❺", "❻", "❼", "❽", "❾", "❿"]
    for i, p in enumerate(passengers, 1):
        booking = p.get('booking_status', 'N/A')
        current = p.get('current_status', 'N/A')
        circle = circles[i-1] if i <= len(circles) else f"{i}️⃣"
        booking_icon = get_status_icon(booking, chart_status)
        current_icon = get_status_icon(current, chart_status)
        note = get_status_note(current, chart_status)
        msg += f"\n{circle}\nBooking Status: {booking} {booking_icon}\nCurrent Status: {current} {current_icon}\nStatus Note: {note}\n"
    msg += f"\n\n📌 Last Updated @ {datetime.now().strftime('%d %b %H:%M:%S')}"
    return msg

def format_live_train_result(data):
    if not data:
        return "❌ Train not found. Please check the train number.", None
    if isinstance(data, dict) and data.get('error'):
        return f"❌ {data.get('error')}", None
    train_no = data.get('train_number', 'N/A')
    query_date = data.get('query_date', datetime.now().strftime("%d-%b-%Y"))
    journey_state = data.get('journey_state', 'running')
    current_offset = 0
    for offset in range(5):
        if query_date == get_date_for_offset(offset):
            current_offset = offset
            break
    date_label = get_date_label(current_offset)
    msg = f"🚂 LIVE TRAIN STATUS - {date_label.upper()}\n\nTrain: {data.get('train_name', 'N/A')} ({train_no})\nFrom: {data.get('source', 'N/A')} → {data.get('destination', 'N/A')}\n📅 Journey Date: {data.get('journey_date', 'N/A')}\n"
    delay = data.get('delay', '0')
    msg += f"⏰ Delay: {'✅ On Time' if str(delay) == '0' else f'⏰ {delay} mins late'}\n📍 Current Status: {data.get('current_station', 'N/A')}\n"
    if data.get('excpt'):
        msg += f"\n⚠️ {data.get('excpt')}\n"
    if journey_state == "completed":
        msg += f"\n🏁 *JOURNEY COMPLETED*\n✅ Train has reached its destination.\n"
    elif journey_state == "not_started":
        msg += f"\n⏳ *JOURNEY NOT STARTED*\n📌 Train is yet to depart from source.\n"
        stations = data.get('stations', [])
        if stations:
            msg += f"\n📋 Scheduled Stations:\n"
            for i, s in enumerate(stations[:8], 1):
                msg += f"   {i}. {s.get('SC', 'N/A')} - {s.get('SN', 'N/A')}\n      Arr: {format_station_time(s.get('STA', 'N/A'))} | Dep: {format_station_time(s.get('STD', 'N/A'))}" + (f" | Day: {s.get('DAY', '')}" if s.get('DAY') else "") + "\n"
        else:
            msg += "\n📋 No schedule available.\n"
    else:
        stations = data.get('stations', [])
        if stations:
            msg += "\n📋 Upcoming Stations:\n"
            for i, s in enumerate(stations, 1):
                arrival = s.get('ETA', '') or s.get('STA', 'N/A')
                departure = s.get('ETD', '') or s.get('STD', 'N/A')
                msg += f"   {i}. {s.get('SC', 'N/A')} - {s.get('SN', 'N/A')}\n      Arr: {format_station_time(arrival)} | Dep: {format_station_time(departure)}" + (f" | Day: {s.get('DAY', '')}" if s.get('DAY') else "") + "\n"
        else:
            msg += "\n📋 No upcoming stations available.\n"
    msg += f"\n📌 Last Updated @ {data.get('last_updated', datetime.now().strftime('%d %b %H:%M:%S'))}"
    return msg

def format_train_search(data):
    if not data:
        return "❌ No trains found. Please try again."
    msg = f"🔍 TRAIN SEARCH RESULTS\n📋 Query: {data.get('query', 'N/A')}\n\n"
    for t in data.get('trains', [])[:10]:
        msg += f"🚂 {t.get('train_number', 'N/A')}\n   Train: {t.get('train_name', 'N/A')}\n   Route: {t.get('source', 'N/A')} → {t.get('destination', 'N/A')}\n\n"
    msg += f"📌 Last Updated @ {data.get('last_updated', datetime.now().strftime('%d %b %H:%M:%S'))}"
    return msg

def format_schedule_result(data, chunk_start=0):
    if not data:
        return "❌ Schedule not found.", None
    if isinstance(data, dict) and data.get('error'):
        return f"❌ {data['error']}", None
    stations = [s for s in data.get('stations', [])
                if (s.get('arrival') and s.get('arrival') != 'N/A')
                or (s.get('departure') and s.get('departure') != 'N/A')
                or s.get('arrival') == 'Source'
                or s.get('departure') == 'Dest']
    total = len(stations)
    CHUNK_SIZE = 20
    start = chunk_start
    end = min(start + CHUNK_SIZE, total)
    msg = f"📋 TRAIN SCHEDULE\n\n🚇 {data.get('train_name', 'N/A')} ({data.get('train_number', 'N/A')})\n📍 From: {data.get('source', 'N/A')} → {data.get('destination', 'N/A')}\n📌 Showing {start+1}-{end} of {total}\n\n"
    for i in range(start, end):
        s = stations[i]
        msg += f"{i+1}. {s.get('code', 'N/A')} - {s.get('name', 'N/A')}\n   🕐 Arr: {s.get('arrival', 'N/A')}  |  🕐 Dep: {s.get('departure', 'N/A')}" + (f"  |  Day: {s.get('day', '')}" if s.get('day') and s.get('day') != 'N/A' else "") + "\n\n"
    msg += f"📌 Last Updated @ {data.get('last_updated', datetime.now().strftime('%d %b %H:%M:%S'))}"
    return msg, (start, end, total)

# ------------------------------------------------------------------
# Theme application (FIXED: Auto theme uses IST hour, middle alignment added)
# ------------------------------------------------------------------
def apply_theme(theme, custom_bg=None, custom_text=None):
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
        number_color = "#0969da"
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
        number_color = "#58a6ff"
    else:
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
        number_color = accent

    css = f"""
    <style>
        .block-container {{ padding-top: 0.5rem !important; padding-bottom: 1rem !important; }}
        .stApp {{ background-color: {bg} !important; }}
        [data-testid="stSidebar"] {{ background-color: {card_bg} !important; border-right: 1px solid {border} !important; }}
        [data-testid="stSidebar"] .stMarkdown p, [data-testid="stSidebar"] .stMarkdown div,
        [data-testid="stSidebar"] label, [data-testid="stSidebar"] .stTextInput label,
        [data-testid="stSidebar"] .stSelectbox label, [data-testid="stSidebar"] .stDateInput label,
        [data-testid="stSidebar"] .stNumberInput label, [data-testid="stSidebar"] .stTextArea label,
        [data-testid="stSidebar"] .stRadio label, [data-testid="stSidebar"] .stCheckbox label {{
            color: {text_color} !important;
        }}
        header[data-testid="stHeader"] {{ background-color: {card_bg} !important; border-bottom: 1px solid {border} !important; }}
        h1, h2, h3, h4, h5, h6, .stMarkdown p, .stMarkdown div, .stMarkdown span,
        .stMarkdown h1, .stMarkdown h2, .stMarkdown h3,
        [data-testid="stMetricLabel"], [data-testid="stMetricValue"], .stCaption {{
            color: {text_color} !important;
        }}
        .stTextInput input, .stNumberInput input, .stDateInput input, .stTextArea textarea,
        .stSelectbox > div > div > div {{
            background-color: {input_bg} !important;
            color: {text_color} !important;
            border: 1px solid {border} !important;
            border-radius: 8px !important;
        }}
        .stButton > button {{
            background-color: {button_bg} !important;
            color: {button_text} !important;
            border: 1px solid {button_border} !important;
            border-radius: 8px !important;
            font-weight: 500 !important;
            transition: all 0.15s ease !important;
        }}
        .stButton > button:hover {{
            background-color: {button_hover_bg} !important;
            color: {button_hover_text} !important;
            border-color: {button_hover_border} !important;
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
            border-radius: 12px !important; padding: 16px !important;
        }}
        .stFileUploader:hover {{ border-color: {accent} !important; }}
        .stFileUploader label {{ color: {text_secondary} !important; }}
        .stDataFrame, [data-testid="stDataFrame"], .stDataEditor, [data-testid="stDataEditor"],
        .stDataFrame table, .stDataEditor table, .stDataFrame th, .stDataEditor th,
        .stDataFrame td, .stDataEditor td, .stDataEditor input, .stDataEditor textarea {{
            background-color: {card_bg} !important;
            color: {text_color} !important;
            border-color: {border} !important;
        }}
        .stDataFrame th, .stDataEditor th {{ border-bottom: 2px solid {border} !important; font-weight: 600 !important; }}
        .stDataFrame td, .stDataEditor td {{ text-align: center !important; vertical-align: middle !important; }}
        .stDataFrame th, .stDataEditor th {{ text-align: center !important; vertical-align: middle !important; }}
        .stExpander {{ background-color: {card_bg} !important; border: 1px solid {border} !important; border-radius: 8px !important; }}
        .streamlit-expanderHeader {{ color: {text_color} !important; font-weight: 600 !important; }}
        .stChatMessage {{ background-color: {card_bg} !important; border: 1px solid {border} !important; border-radius: 12px !important; padding: 12px !important; margin-bottom: 8px !important; }}
        .stChatInput {{ background-color: {input_bg} !important; border: 1px solid {border} !important; border-radius: 12px !important; }}
        .stChatInput input {{ color: {text_color} !important; }}
        [data-testid="stMetric"] {{ background-color: {card_bg} !important; border: 1px solid {border} !important; border-radius: 10px !important; padding: 14px !important; }}
        .stTabs [data-baseweb="tab-list"] {{ background-color: {card_bg} !important; border-bottom: 1px solid {border} !important; }}
        .stTabs [data-baseweb="tab"] {{ color: {text_secondary} !important; }}
        .stTabs [data-baseweb="tab-highlight"] {{ background-color: {accent} !important; }}
        ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
        ::-webkit-scrollbar-track {{ background: {bg}; }}
        ::-webkit-scrollbar-thumb {{ background: {border}; border-radius: 10px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: {accent}; }}
        .action-box {{ background: {card_bg}; border: 1px solid {border}; border-radius: 12px; padding: 18px; margin-bottom: 16px; }}
        .file-card {{ background: {card_bg}; border: 1px solid {border}; border-radius: 12px; padding: 14px; margin: 10px 0; }}
        .file-card-title {{ color: {text_color}; font-weight: 600; font-size: 0.95rem; margin-bottom: 2px; }}
        .file-card-meta {{ color: {text_secondary}; font-size: 0.8rem; margin-bottom: 10px; }}
        .pro-footer {{ color: {text_secondary} !important; border-top: 1px solid {border} !important; text-align: center !important; padding: 18px 0 8px !important; margin-top: 28px !important; font-size: 0.85rem !important; }}
        .sheet-link-btn {{
            display: inline-block !important; padding: 9px 16px !important;
            background: {button_bg} !important; color: {accent} !important;
            border: 1px solid {button_border} !important; border-radius: 8px !important;
            text-decoration: none !important; text-align: center !important; width: 100% !important;
            transition: all 0.15s !important; font-weight: 500 !important; font-size: 0.9rem !important;
        }}
        .sheet-link-btn:hover {{ background: {accent} !important; color: white !important; border-color: {accent} !important; }}
        .status-pill {{ display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 0.78rem; font-weight: 500; }}
        .status-live {{ background: rgba(63, 185, 80, 0.15); color: {success}; border: 1px solid {success}; }}
        .train-count-container {{ display: flex; flex-wrap: wrap; gap: 10px; justify-content: flex-start; margin: 10px 0; }}
        .train-count-card {{
            border: 1px solid {border};
            border-radius: 10px;
            padding: 8px 16px;
            min-width: 80px;
            text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            transition: transform 0.15s ease, box-shadow 0.15s ease;
            background: transparent;
        }}
        .train-count-card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.12); border-color: {accent}; }}
        .train-count-number {{ 
            color: {number_color};
            font-weight: 800;
            font-size: 1.8rem;
            line-height: 1.2;
            letter-spacing: -0.5px;
        }}
        .train-count-badge {{ 
            display: inline-block;
            background: {accent};
            color: white;
            font-size: 0.9rem;
            font-weight: 700;
            padding: 2px 10px;
            border-radius: 20px;
            margin-top: 2px;
        }}
        .train-total-card {{ 
            border: 2px solid {success};
            border-radius: 12px;
            padding: 8px 20px;
            min-width: 120px;
            text-align: center;
            background: transparent;
        }}
        .train-total-number {{ 
            color: {success};
            font-weight: 800;
            font-size: 1.5rem;
            line-height: 1.2;
        }}
        .train-total-label {{ 
            color: {text_secondary};
            font-size: 0.75rem;
            margin-top: 2px;
        }}
        .weather-card {{
            background: {card_bg};
            border: 1px solid {border};
            border-radius: 16px;
            padding: 20px;
            margin: 10px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }}
        .weather-temp {{
            font-size: 3.5rem;
            font-weight: 700;
            color: {number_color};
        }}
        .weather-desc {{
            font-size: 1.2rem;
            color: {text_color};
        }}
        .weather-detail {{
            font-size: 0.95rem;
            color: {text_secondary};
            padding: 4px 0;
        }}
        .result-box {{
            background: {card_bg};
            border: 2px solid {accent};
            border-radius: 12px;
            padding: 20px;
            margin: 15px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}
        .result-box pre {{
            white-space: pre-wrap;
            word-wrap: break-word;
            font-family: inherit;
            font-size: 0.95rem;
            line-height: 1.6;
            margin: 0;
            color: {text_color};
        }}
        .print-only {{ display: none; }}
        @media print {{
            @page {{ margin: 1cm; size: A4 landscape; }}
            body {{ background: white !important; }}
            .no-print, header, footer, .stSidebar, .stButton, .stExpander, .stTabs,
            .stSelectbox, .stTextInput, .stDateInput, .stNumberInput, .stTextArea, .stRadio,
            .stCheckbox, .stFileUploader, .stCaption, .stImage, .stVideo, .stAudio, .stPlotlyChart,
            .action-box, .pro-footer, .status-pill, .sheet-link-btn, .stChatMessage, .stChatInput,
            .train-count-container, .weather-card, .result-box, .marquee-container {{ display: none !important; }}
            .print-only {{ display: block !important; visibility: visible !important; }}
            .print-only table {{ width: 100% !important; border-collapse: collapse !important; font-size: 9pt !important; }}
            .print-only th, .print-only td {{ border: 1px solid #333 !important; padding: 4px !important; font-size: 9pt !important; color: #000 !important; background: #fff !important; text-align: center !important; vertical-align: middle !important; }}
            .print-only th {{ background: #eee !important; font-weight: bold !important; }}
            .print-only tr:nth-child(even) td {{ background: #f9f9f9 !important; }}
        }}
        * {{ transition: background-color 0.2s ease, color 0.2s ease, border-color 0.2s ease; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# ------------------------------------------------------------------
# Marquee / Crawling ticker for EQ data
# ------------------------------------------------------------------
def render_eq_marquee(df):
    if df.empty or len(df) == 0:
        return ""
    pnr_col = next((c for c in df.columns if 'PNR' in str(c).upper()), None)
    train_col = next((c for c in df.columns if 'T/N' in str(c).upper() or 'T_N' in str(c).upper() or 'TRAIN' in str(c).upper()), None)
    from_col = next((c for c in df.columns if 'FROM' in str(c).upper()), None)
    to_col = next((c for c in df.columns if 'TO' in str(c).upper() and 'BOARDING' not in str(c).upper() and 'FROM' not in str(c).upper()), None)
    class_col = next((c for c in df.columns if 'CLASS' in str(c).upper()), None)
    name_col = next((c for c in df.columns if 'PASS_NAME' in str(c).upper() or 'PASS NAME' in str(c).upper()), None)
    rec_col = next((c for c in df.columns if 'RECOMMENDATION' in str(c).upper()), None)

    items = []
    for _, row in df.head(25).iterrows():
        parts = []
        if pnr_col and row.get(pnr_col):
            parts.append(f"🎫 PNR:{row.get(pnr_col,'')}")
        if train_col and row.get(train_col):
            parts.append(f"🚂 Train:{row.get(train_col,'')}")
        if from_col and row.get(from_col):
            parts.append(f"📍 From:{row.get(from_col,'')}")
        if to_col and row.get(to_col):
            parts.append(f"📍 To:{row.get(to_col,'')}")
        if class_col and row.get(class_col):
            parts.append(f"🎓 Class:{row.get(class_col,'')}")
        if name_col and row.get(name_col):
            parts.append(f"👤 Name:{row.get(name_col,'')}")
        if rec_col and row.get(rec_col):
            parts.append(f"📝 Rec:{row.get(rec_col,'')}")
        if parts:
            items.append(" | ".join(parts))

    if not items:
        return ""

    text = "  ⭐  ".join(items)
    return f"""
    <div class="marquee-container no-print" style="overflow: hidden; white-space: nowrap; background: linear-gradient(90deg, #FF9933, #FFFFFF, #138808); 
         padding: 10px 0; border-radius: 8px; margin-bottom: 12px; border: 1px solid #d0d7de;">
        <div style="display: inline-block; padding-left: 100%; animation: marqueeScroll 35s linear infinite; color: #000; font-weight: 700; font-size: 1rem;">
            {text}
        </div>
    </div>
    <style>
    @keyframes marqueeScroll {{
        0% {{ transform: translateX(0); }}
        100% {{ transform: translateX(-100%); }}
    }}
    </style>
    """

# ------------------------------------------------------------------
# PDF, image, WhatsApp helpers
# ------------------------------------------------------------------
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
    if 'Select' in cols:
        cols.remove('Select')
    if len(cols) > 15:
        cols = cols[:15]
    col_width = min(25, 277 / max(len(cols), 1))
    pdf.set_font("Arial", 'B', 7)
    for c in cols:
        safe_c = sanitize_latin(str(c)[:15])
        pdf.cell(col_width, 6, safe_c, border=1, align='C')
    pdf.ln()
    pdf.set_font("Arial", '', 6)
    max_rows = len(df) if full else min(120, len(df))
    for idx, row in df.head(max_rows).iterrows():
        for c in cols:
            val = str(row.get(c, ""))[:20]
            safe_val = sanitize_latin(val)
            pdf.cell(col_width, 5, safe_val, border=1, align='C')
        pdf.ln()
        if pdf.get_y() > 185:
            pdf.add_page()
            pdf.set_font("Arial", 'B', 7)
            for c in cols:
                safe_c = sanitize_latin(str(c)[:15])
                pdf.cell(col_width, 6, safe_c, border=1, align='C')
            pdf.ln()
            pdf.set_font("Arial", '', 6)
    output = pdf.output(dest='S')
    if isinstance(output, bytearray):
        return bytes(output)
    elif isinstance(output, str):
        return output.encode('latin-1')
    else:
        return output

def create_table_image(df, title):
    if df.empty:
        return None
    cols = list(df.columns)
    if '_sheet_row' in cols:
        cols.remove('_sheet_row')
    if 'Select' in cols:
        cols.remove('Select')
    if len(cols) > 10:
        cols = cols[:10]
    data = df[cols].head(50).values
    n_rows = min(len(df), 50)
    n_cols = len(cols)
    fig_height = max(3, 0.5 + 0.45 * n_rows)
    fig_width = max(10, 1.5 * n_cols)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    ax.axis('off')
    table = ax.table(cellText=data, colLabels=cols, loc='center', cellLoc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.6)
    for (i, j), cell in table.get_celld().items():
        if i == 0:
            cell.set_facecolor('#4a90d9')
            cell.set_text_props(color='white', weight='bold', fontsize=10)
        else:
            cell.set_facecolor('#f0f4fa' if i % 2 == 0 else 'white')
            cell.set_text_props(color='#1f2328', fontsize=9)
        cell.set_edgecolor('#cccccc')
        cell.set_height(0.04)
    plt.title(title, fontsize=14, weight='bold', pad=20, color='#1f2328')
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    buf.seek(0)
    plt.close()
    return buf.getvalue()

def build_whatsapp_message(sheet_name, selected_count, pnrs, total_rows, df):
    now_str = format_datetime()
    if not df.empty:
        cols = list(df.columns)
        if '_sheet_row' in cols:
            cols.remove('_sheet_row')
        if 'Select' in cols:
            cols.remove('Select')
        cols = cols[:5]
        table_lines = []
        header = " | ".join([c[:8] for c in cols])
        table_lines.append(header)
        table_lines.append("-" * (len(header) + 4))
        for _, row in df.head(8).iterrows():
            row_vals = [str(row.get(c, ""))[:10] for c in cols]
            table_lines.append(" | ".join(row_vals))
        if len(df) > 8:
            table_lines.append(f"... and {len(df)-8} more rows")
        table_text = "\n".join(table_lines)
    else:
        table_text = "No data"
    if selected_count > 0 and pnrs:
        pnr_text = ", ".join(str(p) for p in pnrs[:10])
        if len(pnrs) > 10:
            pnr_text += f" (+{len(pnrs)-10} more)"
        msg = f"📊 *{sheet_name}* — {selected_count} rows selected\n🕐 {now_str}\n🎫 PNRs: {pnr_text}\n\n```\n{table_text}\n```"
    else:
        msg = f"📊 *{sheet_name}* — Total {total_rows} rows\n🕐 {now_str}\n\n```\n{table_text}\n```"
    msg += f"\n🔗 Sheet: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
    return msg

def get_pnr_status_url(pnr):
    if not pnr or len(str(pnr)) != 10:
        return None
    return f"https://www.confirmtkt.com/pnr-status/{pnr}"

# ------------------------------------------------------------------
# Main function
# ------------------------------------------------------------------
def main():
    # Theme selection (FIXED: Auto uses IST hour)
    theme_options = ['Day', 'Dark', 'Custom', 'Auto (System)']
    if not st.session_state.auto_theme_detected:
        st.session_state.auto_theme_detected = True
        if st.session_state.theme == 'Day':
            st.session_state.theme = 'Auto (System)'

    theme_choice = st.sidebar.selectbox("🎨 Theme", theme_options,
        index=theme_options.index(st.session_state.theme) if st.session_state.theme in theme_options else 0,
        key="theme_select")
    if theme_choice != st.session_state.theme:
        st.session_state.theme = theme_choice
        st.rerun()

    effective_theme = theme_choice
    if theme_choice == 'Auto (System)':
        hour = now_ist().hour
        effective_theme = 'Dark' if (hour < 6 or hour >= 19) else 'Day'

    if effective_theme == 'Custom':
        custom_bg = st.sidebar.color_picker("Background Color", value=st.session_state.custom_bg, key="custom_bg_picker")
        custom_text = st.sidebar.color_picker("Text Color", value=st.session_state.custom_text, key="custom_text_picker")
        if custom_bg != st.session_state.custom_bg or custom_text != st.session_state.custom_text:
            st.session_state.custom_bg = custom_bg
            st.session_state.custom_text = custom_text
            st.rerun()
    else:
        custom_bg = None
        custom_text = None

    apply_theme(effective_theme, custom_bg, custom_text)

    # Auto-refresh for bidirectional sync feel (every 60s)
    st.components.v1.html("""
    <script>
    (function(){
        if(!window._eqmsAutoRefresh){
            window._eqmsAutoRefresh = true;
            setInterval(function(){
                window.location.reload();
            }, 60000);
        }
    })();
    </script>
    """, height=0)

    # Sidebar
    with st.sidebar:
        # FIXED: Flag colors only during flag hours (Memory 15)
        if is_flag_hours():
            st.markdown("""
            <div style="text-align:center; margin-bottom:10px; font-size:1.3rem; line-height:1.8;">
                <span style="color:#FF9933;">🟠 नमस्ते आपका स्वागत है</span><br>
                <span style="color:#FFFFFF;">⚪ हम भारत के लोग</span><br>
                <span style="color:#138808; font-weight:bold;">🟢 जय हिंद</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="text-align:center; margin-bottom:10px; font-size:1.3rem; line-height:1.8; color: inherit;">
                🙏 नमस्ते आपका स्वागत है<br>
                🇮🇳 हम भारत के लोग<br>
                🫡 जय हिंद
            </div>
            """, unsafe_allow_html=True)

        now = now_ist()
        st.caption(f"📅 {format_date()}  •  🕐 {format_time()} IST")

        # Sync status indicator
        sync_status = f"🟢 Live" if st.session_state.last_sheet_sync else "🟡 Waiting"
        st.caption(f"📡 Sheet Sync: {sync_status} | {st.session_state.last_sheet_sync or '—'}")

        # Live sync toggle
        live_sync = st.toggle("🔄 Auto Sync (60s)", value=st.session_state.live_sync, key="live_sync_toggle")
        if live_sync != st.session_state.live_sync:
            st.session_state.live_sync = live_sync
            st.rerun()

        # Weather widget in sidebar
        with st.expander("🌤️ Weather", expanded=True):
            city = st.text_input("🏙️ City", value=st.session_state.weather_city, key="sidebar_weather_city")
            if city != st.session_state.weather_city:
                st.session_state.weather_city = city

            if st.button("🌤️ Get Weather", key="sidebar_weather_btn", use_container_width=True):
                if city:
                    with st.spinner(f"Fetching..."):
                        data = get_weather(city)
                        if data and 'error' not in data:
                            st.session_state.weather_data = data
                            st.rerun()
                        else:
                            st.error(data.get('error', 'Error'))

            if st.session_state.weather_data and 'error' not in st.session_state.weather_data:
                data = st.session_state.weather_data
                st.markdown(f"""
                <div style="text-align:center; padding: 5px 0;">
                    <div style="font-size:1.5rem; font-weight:700;">{data['temp']}°C</div>
                    <div>{data['weather'].title()}</div>
                    <div style="font-size:0.8rem; color:#656d76;">💧 {data['humidity']}%  🌬️ {data['wind_speed']} m/s</div>
                </div>
                """, unsafe_allow_html=True)

        with st.expander("🔄 Sync & Status", expanded=True):
            if st.button("🔄 Sync Now", use_container_width=True, key="sync_now_btn"):
                st.cache_data.clear()
                st.session_state.last_refresh = time.time()
                log_activity("🔄 Manual sync")
                st.rerun()
            st.caption(f"Last sync: {format_time(datetime.fromtimestamp(st.session_state.last_refresh, tz=IST))} IST")

        sheet_link = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
        st.markdown(f'<a href="{sheet_link}" target="_blank" class="sheet-link-btn">📊 Open Google Sheet</a>', unsafe_allow_html=True)

        with st.expander("📤 Upload & Process", expanded=True):
            st.caption("📷 Image • 📄 PDF • 📝 Text • 🎤 Audio")
            mode = st.radio("Type", ["📷 Image / PDF", "📝 Text", "🎤 Voice / Audio"],
                horizontal=True, label_visibility="collapsed", key="upload_mode_radio")
            uploaded = None
            text_data = ""
            audio_data = None
            if mode == "📷 Image / PDF":
                uploaded = st.file_uploader("Image or PDF", type=["png","jpg","jpeg","pdf"],
                    label_visibility="collapsed", key="img_pdf_uploader")
            elif mode == "📝 Text":
                text_data = st.text_area("📝 Paste text", height=150,
                    placeholder="Messy text yahan paste karein...",
                    label_visibility="collapsed", key="text_input_area")
                if text_data:
                    st.caption(f"✓ {len(text_data)} characters ready")
            else:
                st.caption("🎤 Mic se record karein")
                audio_data = st.audio_input("Record", label_visibility="collapsed", key="audio_recorder")
                uploaded = st.file_uploader("Ya file upload", type=["mp3","wav","ogg","m4a"],
                    label_visibility="collapsed", key="audio_file_uploader")
                if audio_data:
                    st.audio(audio_data, format='audio/wav')
                elif uploaded:
                    st.audio(uploaded, format='audio/mp3')

            if st.button("🚀 Process & Save", type="primary", use_container_width=True, key="process_save_btn"):
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
                                            st.session_state.last_uploaded_drive_id = drive_res.get('id')
                                            st.session_state.original_file_bytes = fbytes
                                            st.session_state.original_file_mime = mime
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

        # FIXED: Original file print/view/download options
        if st.session_state.upload_success and st.session_state.last_uploaded_file:
            with st.expander("📄 Last Uploaded File", expanded=True):
                st.markdown(f"""
                <div class="file-card">
                    <div class="file-card-title">📄 {st.session_state.last_uploaded_file}</div>
                    <div class="file-card-meta">Uploaded at {st.session_state.get('last_upload_time', '—')} IST</div>
                </div>
                """, unsafe_allow_html=True)
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    if st.session_state.last_uploaded_view_url:
                        st.link_button("👁️ View", st.session_state.last_uploaded_view_url, use_container_width=True)
                with c2:
                    if st.session_state.last_uploaded_print_url:
                        st.link_button("🖨️ Print File", st.session_state.last_uploaded_print_url, use_container_width=True)
                with c3:
                    if st.session_state.last_uploaded_drive_id:
                        st.link_button("📥 Download", f"https://drive.google.com/uc?export=download&id={st.session_state.last_uploaded_drive_id}", use_container_width=True)
                with c4:
                    if st.session_state.last_uploaded_print_url:
                        st.components.v1.html(f"""
                        <div style="width:100%;">
                            <button onclick="window.open('{st.session_state.last_uploaded_print_url}', '_blank')" style="
                                background: linear-gradient(135deg, #7c3aed, #6d28d9);
                                color: white; border: none; border-radius: 8px;
                                padding: 9px 16px; width: 100%; font-weight: 600;
                                cursor: pointer; font-size: 0.9rem;
                            ">🖨️ Open & Print</button>
                        </div>
                        """, height=50)
                if st.button("🗑️ Clear History", use_container_width=True, key="clear_history_btn"):
                    st.session_state.last_uploaded_file = None
                    st.session_state.last_uploaded_drive_url = None
                    st.session_state.last_uploaded_view_url = None
                    st.session_state.last_uploaded_print_url = None
                    st.session_state.last_uploaded_drive_id = None
                    st.session_state.original_file_bytes = None
                    st.session_state.original_file_mime = None
                    st.session_state.upload_success = False
                    st.rerun()

        with st.expander("📋 Activity Log", expanded=True):
            if st.session_state.activity_log:
                for log in reversed(st.session_state.activity_log[-20:]):
                    st.caption(f"{log.get('timestamp', '')} — {log.get('action', '')}")
            else:
                st.caption("No activity yet")
        st.markdown("---")

        # Sheet selection in sidebar
        st.markdown("### 📑 Sheet Selection")
        sheet_choice = st.selectbox("Select Sheet", list(SHEET_CONFIG.keys()),
            index=list(SHEET_CONFIG.keys()).index(st.session_state.selected_sheet)
            if st.session_state.selected_sheet in SHEET_CONFIG else 0,
            key="sheet_select")
        if sheet_choice != st.session_state.selected_sheet:
            st.session_state.selected_sheet = sheet_choice
            st.session_state.current_page = 1
            st.cache_data.clear()
            st.rerun()

        # Filters
        st.markdown("### 🔍 Filters")
        config = SHEET_CONFIG[sheet_choice]
        pnr_col_idx = config.get("pnr_col")
        train_col_idx = config.get("train_col")
        doj_col_idx = config.get("doj_col")

        pnr_input = st.text_input("PNR (partial)", value=st.session_state.pnr_val, key="pnr_filter_input")
        if pnr_input != st.session_state.pnr_val:
            st.session_state.pnr_val = pnr_input
            st.session_state.current_page = 1
            st.rerun()

        train_input = st.text_input("Train (partial)", value=st.session_state.train_val, key="train_filter_input")
        if train_input != st.session_state.train_val:
            st.session_state.train_val = train_input
            st.session_state.current_page = 1
            st.rerun()

        c1, c2 = st.columns(2)
        with c1:
            from_input = st.date_input("From DOJ", value=st.session_state.from_val,
                key="from_date_input", format="DD-MM-YYYY")
        with c2:
            to_input = st.date_input("To DOJ", value=st.session_state.to_val,
                key="to_date_input", format="DD-MM-YYYY")
        if from_input != st.session_state.from_val:
            st.session_state.from_val = from_input
            st.session_state.current_page = 1
            st.rerun()
        if to_input != st.session_state.to_val:
            st.session_state.to_val = to_input
            st.session_state.current_page = 1
            st.rerun()

        # Print Sheet download in sidebar
        st.markdown("---")
        st.markdown("### 🖨️ Print Sheet")
        print_html_key = f'print_html_{sheet_choice}'
        print_html_val = st.session_state.get(print_html_key, '')
        if print_html_val:
            st.download_button(
                label="🖨️ Download & Print",
                data=print_html_val.encode('utf-8'),
                file_name=f"{sheet_choice}_print_{format_datetime().replace(' ', '_').replace(':', '-')}.html",
                mime="text/html",
                use_container_width=True,
                key=f"sidebar_print_dl_{sheet_choice}"
            )
            st.caption("👆 Download karein, file open karein, auto-print hoga")
        else:
            st.info("📋 Data Table view mein jayein, print button yahan ayega")

    # Load data for selected sheet
    df_raw = load_sheet_data_cached(sheet_choice, SHEET_ID)
    filtered_df = df_raw.copy() if not df_raw.empty else pd.DataFrame()

    # Apply filters
    if not filtered_df.empty:
        config = SHEET_CONFIG[sheet_choice]
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
            except Exception:
                filtered_df['_temp'] = pd.to_datetime(filtered_df[col_name], errors='coerce')
            if st.session_state.from_val:
                filtered_df = filtered_df[filtered_df['_temp'] >= pd.to_datetime(st.session_state.from_val)]
            if st.session_state.to_val:
                filtered_df = filtered_df[filtered_df['_temp'] <= pd.to_datetime(st.session_state.to_val)]
            filtered_df = filtered_df.drop('_temp', axis=1, errors='ignore')

    # View mode selection
    view = st.radio("View Mode", ["📋 Data Table", "📊 Dashboard", "💬 Chat", "🚂 Railway", "🌤️ Weather"],
        index=["📋 Data Table", "📊 Dashboard", "💬 Chat", "🚂 Railway", "🌤️ Weather"].index(st.session_state.view_mode)
        if st.session_state.view_mode in ["📋 Data Table", "📊 Dashboard", "💬 Chat", "🚂 Railway", "🌤️ Weather"] else 0,
        key="view_mode_radio", horizontal=True)
    if view != st.session_state.view_mode:
        st.session_state.view_mode = view
        st.rerun()

    # Top bar
    top_c1, top_c2 = st.columns([4, 1])
    with top_c1:
        st.markdown(f"<h1 style='font-size:22px; font-weight:700; margin:0;'>🚂 AI EQMS Hub Pro — {sheet_choice}</h1>", unsafe_allow_html=True)
    with top_c2:
        st.markdown(f"<div style='padding-top:6px; text-align:right;'><span class='status-pill status-live'>● Live</span> &nbsp; <span style='font-size:13px;'>Sync {format_time(datetime.fromtimestamp(st.session_state.last_refresh, tz=IST))} IST</span></div>", unsafe_allow_html=True)

    st.caption(f"Enterprise Railway EQ Management  •  {format_date()}  •  {format_time()} IST")
    st.markdown("---")

    # Marquee / Crawling ticker (EQ data scrolls left to right)
    if view == "📋 Data Table" and sheet_choice == "EQ" and not filtered_df.empty:
        marquee_html = render_eq_marquee(filtered_df)
        if marquee_html:
            st.markdown(marquee_html, unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # View: Chat
    # ------------------------------------------------------------------
    if view == "💬 Chat":
        st.subheader("💬 Chat with TSKEQ Bot")
        st.caption("Ask about EQ data, trains, quota, PNR or anything else.")
        if prompt := st.chat_input("Type your question...", key="chat_input"):
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
        if st.button("🗑️ Clear Chat", use_container_width=True, key="clear_chat_btn"):
            st.session_state.messages = []
            st.rerun()

    # ------------------------------------------------------------------
    # View: Dashboard
    # ------------------------------------------------------------------
    elif view == "📊 Dashboard":
        st.subheader(f"📊 Analytics Dashboard — {sheet_choice}")
        train_col = None
        for c in filtered_df.columns:
            if 'T/N' in c.upper() or 'T_N' in c.upper() or 'TRAIN' in c.upper():
                train_col = c
                break

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
            if train_col:
                train_counts = filtered_df[train_col].value_counts().reset_index()
                train_counts.columns = ['Train', 'Count']
                fig_bar = px.bar(train_counts.head(15), x='Train', y='Count', title="Top 15 Trains by EQ Count", color='Count', color_continuous_scale='Blues')
                fig_bar.update_layout(height=400, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_bar, use_container_width=True)
            class_col = next((c for c in filtered_df.columns if 'CLASS' in c.upper()), None)
            if class_col:
                class_counts = filtered_df[class_col].value_counts().reset_index()
                class_counts.columns = ['Class', 'Count']
                fig_pie = px.pie(class_counts, names='Class', values='Count', title="Class Distribution", hole=0.4)
                fig_pie.update_layout(height=350, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_pie, use_container_width=True)
            doj_col = next((c for c in filtered_df.columns if 'DOJ' in str(c).upper()), None)
            if doj_col:
                df_temp = filtered_df.copy()
                df_temp['_date'] = pd.to_datetime(df_temp[doj_col], format='%d-%m-%Y', errors='coerce')
                if df_temp['_date'].isna().all():
                    df_temp['_date'] = pd.to_datetime(df_temp[doj_col], errors='coerce')
                daily = df_temp.groupby('_date').size().reset_index(name='count')
                if not daily.empty:
                    fig_line = px.line(daily, x='_date', y='count', title="Daily Trend", markers=True, labels={'_date': 'Date', 'count': 'Records'}, color_discrete_sequence=['#ff6b6b'])
                    fig_line.update_layout(height=300, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig_line, use_container_width=True)
            with st.expander("📊 Train-wise EQ Count (Full List)", expanded=False):
                if train_col:
                    train_counts_full = filtered_df[train_col].value_counts().reset_index()
                    train_counts_full.columns = ['Train Number', 'EQ Count']
                    st.dataframe(train_counts_full, use_container_width=True, height=400)
        else:
            st.info("No data for charts. Adjust filters or choose another sheet.")

    # ------------------------------------------------------------------
    # View: Data Table
    # ------------------------------------------------------------------
    elif view == "📋 Data Table":
        st.subheader(f"📋 {sheet_choice}  —  {len(filtered_df)} rows")
        train_col_metric = None
        doj_col = None
        for c in filtered_df.columns:
            if 'T/N' in c.upper() or 'T_N' in c.upper() or 'TRAIN' in c.upper():
                train_col_metric = c
            if 'DOJ' in c.upper():
                doj_col = c

        if sheet_choice != "NOTE":
            if not filtered_df.empty:
                if train_col_metric:
                    train_counts_series = filtered_df[train_col_metric].value_counts()
                    st.markdown("**🚆 Train-wise Count**")
                    cards_html = '<div class="train-count-container">'
                    total_eq = len(filtered_df)
                    cards_html += f'<div class="train-total-card"><div class="train-total-number">Total EQ: {total_eq}</div></div>'
                    for train_num, cnt in train_counts_series.items():
                        cards_html += f'<div class="train-count-card"><div class="train-count-number">{train_num}</div><div class="train-count-badge">{cnt}</div></div>'
                    cards_html += '</div>'
                    st.markdown(cards_html, unsafe_allow_html=True)
                    st.markdown("---")
                else:
                    st.metric("Total Records", len(filtered_df))
                    st.markdown("---")

        if st.button("🔄 Refresh Data", use_container_width=False, key="refresh_data_btn"):
            st.cache_data.clear()
            st.session_state.last_refresh = time.time()
            log_activity("🔄 Manual refresh from main")
            st.rerun()

        if filtered_df.empty:
            st.info("No data to show. Clear filters or select another sheet.")
        else:
            page_size = st.selectbox("Rows per page", [15, 25, 50, 100], index=1, key="page_size_select")
            total_pages = max(1, math.ceil(len(filtered_df) / page_size))
            if st.session_state.current_page > total_pages:
                st.session_state.current_page = total_pages
            if st.session_state.current_page < 1:
                st.session_state.current_page = 1

            nav1, nav2, nav3 = st.columns([1, 2, 1])
            with nav1:
                if st.button("◀ Previous", use_container_width=True, disabled=st.session_state.current_page <= 1, key="prev_page_btn"):
                    st.session_state.current_page -= 1
                    st.rerun()
            with nav2:
                st.markdown(f"<div style='text-align:center; padding-top:6px;'><b>Page {st.session_state.current_page} of {total_pages}</b></div>", unsafe_allow_html=True)
            with nav3:
                if st.button("Next ▶", use_container_width=True, disabled=st.session_state.current_page >= total_pages, key="next_page_btn"):
                    st.session_state.current_page += 1
                    st.rerun()

            page = st.session_state.current_page - 1
            start_idx = page * page_size
            end_idx = min(start_idx + page_size, len(filtered_df))
            page_df = filtered_df.iloc[start_idx:end_idx].copy()
            sheet_rows = page_df['_sheet_row'].tolist() if '_sheet_row' in page_df.columns else []
            display_df = page_df.drop(columns=['_sheet_row'], errors='ignore')
            display_df.insert(0, "Select", False)

            # FIX: Print table uses ALL filtered data (not just current page)
            print_df_full = filtered_df.copy()
            if '_sheet_row' in print_df_full.columns:
                print_df_full = print_df_full.drop(columns=['_sheet_row'])
            if 'Select' in print_df_full.columns:
                print_df_full = print_df_full.drop(columns=['Select'])

            # Generate print-ready HTML file for download
            if not print_df_full.empty:
                html_table = print_df_full.to_html(index=False, border=1, classes='print-table', justify='center')
                print_html = f"""<!DOCTYPE html><html><head><title>{sheet_choice} Sheet - AI EQMS Hub Pro</title><style>body{{font-family:Arial,sans-serif;margin:20px;}}h2{{text-align:center;margin-bottom:5px;}}.meta{{text-align:center;font-size:10pt;color:#666;margin-bottom:15px;}}table{{width:100%;border-collapse:collapse;font-size:9pt;}}th,td{{border:1px solid #333;padding:5px;text-align:center;vertical-align:middle;}}th{{background:#f0f0f0;font-weight:bold;}}tr:nth-child(even){{background:#f9f9f9;}}.footer{{text-align:center;font-size:9pt;color:#666;margin-top:15px;}}@media print{{body{{margin:0;}}}}</style></head><body><h2>{sheet_choice} Sheet Data</h2><div class="meta">Total Rows: {len(print_df_full)} | Generated: {format_datetime()} IST</div>{html_table}<div class="footer">AI EQMS Hub Pro • {format_date()}</div><script>window.onload=function(){{setTimeout(function(){{window.print();}},500);}};</script></body></html>"""
                st.session_state[f'print_html_{sheet_choice}'] = print_html
            else:
                st.session_state[f'print_html_{sheet_choice}'] = '' 

            edited_page = st.data_editor(display_df, use_container_width=True, height=400,
                column_config={"Select": st.column_config.CheckboxColumn("Select", width="small")},
                key=f"editor_{sheet_choice}_{st.session_state.current_page}_{page_size}")

            select_all = st.checkbox("Select All on Page", value=st.session_state.select_all, key="select_all_cb")
            if select_all != st.session_state.select_all:
                st.session_state.select_all = select_all
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

            st.markdown('<div class="action-box no-print">', unsafe_allow_html=True)
            st.markdown("**⚡ Quick Actions**")
            a1, a2, a3, a4 = st.columns(4)
            with a1:
                if st.button("💾 Save Edits", use_container_width=True, key="save_edits_btn"):
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
                if st.button("➕ Add Row", use_container_width=True, key="add_row_btn"):
                    try:
                        gc = init_sheets()
                        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                        all_data = sheet.get_all_values()
                        config = SHEET_CONFIG[sheet_choice]
                        start_row = config["start_row"]
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
                    if st.button("🗑️ Delete", use_container_width=True, key="delete_btn"):
                        if not st.session_state.delete_confirm:
                            st.session_state.delete_confirm = True
                            st.warning("Confirm delete by clicking again.")
                            st.rerun()
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
                    st.button("🗑️ Delete", disabled=True, use_container_width=True, key="delete_disabled_btn")
                    st.session_state.delete_confirm = False
            with a4:
                msg = build_whatsapp_message(sheet_choice, len(selected_indices), selected_pnrs, len(filtered_df), filtered_df)
                encoded = urllib.parse.quote(msg)
                wa_url = f"https://api.whatsapp.com/send?text={encoded}"
                st.link_button("📤 WhatsApp Text", wa_url, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

            # WhatsApp Image Share
            st.markdown('<div class="no-print">', unsafe_allow_html=True)
            st.markdown("**📱 WhatsApp Image Share**")
            wa_col1, wa_col2, wa_col3 = st.columns(3)
            with wa_col1:
                if not filtered_df.empty:
                    img_bytes = create_table_image(filtered_df, f"{sheet_choice} Data")
                    if img_bytes:
                        st.download_button("🖼️ Download Table Image", data=img_bytes,
                            file_name=f"{sheet_choice}_table.png", mime="image/png",
                            use_container_width=True, key="wa_img_download")
            with wa_col2:
                if selected_indices and not filtered_df.empty:
                    sel_img_bytes = create_table_image(filtered_df.iloc[selected_indices], f"{sheet_choice} Selected")
                    if sel_img_bytes:
                        st.download_button("🖼️ Download Selected Image", data=sel_img_bytes,
                            file_name=f"{sheet_choice}_selected.png", mime="image/png",
                            use_container_width=True, key="wa_sel_img_download")
                else:
                    st.info("Select rows to generate image")
            with wa_col3:
                if not filtered_df.empty:
                    img_bytes = create_table_image(filtered_df, f"{sheet_choice} Data")
                    if img_bytes:
                        img_b64 = base64.b64encode(img_bytes).decode()
                        copy_js = f"""
                        <div style="width:100%;">
                            <button onclick="copyImageToClipboard()" style="
                                background: #25D366; color: white; border: none; border-radius: 8px;
                                padding: 9px 16px; width: 100%; font-weight: 600;
                                cursor: pointer; font-size: 1rem;
                            ">📋 Copy Sheet Image</button>
                            <script>
                            function copyImageToClipboard() {{
                                var imgData = "{img_b64}";
                                fetch('data:image/png;base64,' + imgData)
                                    .then(res => res.blob())
                                    .then(blob => {{
                                        navigator.clipboard.write([
                                            new ClipboardItem({{ 'image/png': blob }})
                                        ]).then(() => {{
                                            alert('Image copied to clipboard! Paste it into WhatsApp.');
                                        }}).catch(() => {{
                                            alert('Failed to copy. Please use download instead.');
                                        }});
                                    }});
                            }}
                            </script>
                        </div>
                        """
                        st.components.v1.html(copy_js, height=50)
                    else:
                        st.info("Image generation failed")
                else:
                    st.info("No data to copy")
            st.markdown('</div>', unsafe_allow_html=True)

            # Export
            st.markdown('<div class="no-print">', unsafe_allow_html=True)
            st.markdown("**📄 Export**")
            e1, e2, e3, e4 = st.columns(4)
            with e1:
                try:
                    export_df = filtered_df.drop(columns=['_sheet_row'], errors='ignore')
                    pdf_bytes = generate_pdf(export_df, sheet_choice, full=True)
                    st.download_button("📥 PDF (All)", data=pdf_bytes,
                        file_name=f"{sheet_choice}_{now_ist().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf", use_container_width=True, key="pdf_all_download")
                except Exception as e:
                    st.warning(f"PDF error: {e}")
            with e2:
                if selected_indices:
                    export_sel = filtered_df.iloc[selected_indices].drop(columns=['_sheet_row'], errors='ignore')
                else:
                    export_sel = filtered_df.drop(columns=['_sheet_row'], errors='ignore')
                csv_sel = export_sel.to_csv(index=False).encode('utf-8')
                st.download_button("📥 CSV (Selected)" if selected_indices else "📥 CSV (All)", data=csv_sel,
                    file_name=f"{sheet_choice}_{now_ist().strftime('%Y%m%d_%H%M')}_selected.csv",
                    mime="text/csv", use_container_width=True, key="csv_download")
            with e3:
                export_df = filtered_df.drop(columns=['_sheet_row'], errors='ignore')
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                    export_df.to_excel(writer, sheet_name=sheet_choice, index=False)
                excel_data = excel_buffer.getvalue()
                st.download_button("📥 Excel", data=excel_data,
                    file_name=f"{sheet_choice}_{now_ist().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True, key="excel_download")
            with e4:
                csv_full = filtered_df.drop(columns=['_sheet_row'], errors='ignore').to_csv(index=False).encode('utf-8')
                st.download_button("📋 Copy CSV", data=csv_full, file_name="table.csv",
                    mime="text/csv", use_container_width=True, key="copy_csv_download")
            st.markdown('</div>', unsafe_allow_html=True)

            # Extra Features
            st.markdown('<div class="no-print">', unsafe_allow_html=True)
            with st.expander("🔧 Extra Features", expanded=False):
                feat1, feat2 = st.columns(2)
                with feat1:
                    st.markdown("**🎫 PNR Status Check**")
                    pnr_check = st.text_input("Enter PNR", max_chars=10, key="pnr_status_input")
                    if pnr_check and len(pnr_check) == 10:
                        pnr_url = get_pnr_status_url(pnr_check)
                        st.link_button("🔍 Check PNR Status", pnr_url, use_container_width=True)
                    st.markdown("**📊 Quick Stats**")
                    if not filtered_df.empty and pnr_col:
                        valid_pnrs = filtered_df[pnr_col].astype(str).str.match(r'\d{10}').sum()
                        st.caption(f"✅ Valid PNRs: {valid_pnrs}")
                    if not filtered_df.empty and doj_col is not None:
                        upcoming = sum(1 for _, r in filtered_df.iterrows() if not is_expired(r.get(doj_col, '')))
                        st.caption(f"📅 Upcoming DOJ: {upcoming}")
                with feat2:
                    st.markdown("**🚆 Train Analysis**")
                    if train_col_metric and not filtered_df.empty:
                        most_common = filtered_df[train_col_metric].mode()
                        if not most_common.empty:
                            st.caption(f"🔥 Most frequent train: {most_common.iloc[0]}")
                        if pnr_col:
                            dupes = filtered_df[pnr_col].value_counts()
                            dupes = dupes[dupes > 1]
                            if not dupes.empty:
                                st.warning(f"⚠️ {len(dupes)} duplicate PNR(s) found!")
                            else:
                                st.success("✅ No duplicate PNRs")
                    st.markdown("**⌨️ Shortcuts**")
                    st.caption("Ctrl+R: Refresh | Ctrl+P: Print")
            st.markdown('</div>', unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # View: Railway Features (EXACT bot formatting)
    # ------------------------------------------------------------------
    elif view == "🚂 Railway":
        st.subheader("🚂 Indian Railways - Real‑time Info")
        if not NTES_AVAILABLE:
            st.error("❌ 'ntes-client' library not installed. Please run: `pip install ntes-client`")
            st.stop()

        # Debug: Show NTES client status
        with st.expander("🔧 NTES Debug Info", expanded=False):
            st.caption("Agar data nahi a raha, yahan check karein")
            try:
                test_train = st.text_input("Test Train Number", value="12309", key="ntes_test_train")
                if st.button("Test NTES Connection", key="ntes_test_btn"):
                    with st.spinner("Testing..."):
                        try:
                            test_resp = ntes_client.schedule(test_train)
                            st.json(test_resp if test_resp else {"status": "No response"})
                        except Exception as e:
                            st.error(f"NTES Error: {str(e)}")
            except Exception as e:
                st.error(f"Debug init error: {e}")

        tab1, tab2, tab3 = st.tabs(["🔍 PNR Status", "🚂 Live Train", "📋 Train Schedule"])

        # PNR Tab
        with tab1:
            st.markdown("### PNR Status Check")
            pnr_input = st.text_input("Enter 10-digit PNR", max_chars=10, key="rail_pnr")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Check PNR", key="pnr_check", use_container_width=True):
                    if not pnr_input or len(pnr_input) != 10 or not pnr_input.isdigit():
                        st.error("Please enter a valid 10-digit PNR.")
                    else:
                        with st.spinner("Fetching PNR details..."):
                            data = get_pnr_status(pnr_input)
                            if data and isinstance(data, dict) and data.get('error'):
                                st.error(f"❌ {data.get('error')}")
                            elif data:
                                st.markdown(format_pnr_result(data))
                            else:
                                st.error("❌ PNR not found or flushed.")
            with col2:
                if st.button("🔄 Refresh PNR", key="refresh_pnr", use_container_width=True):
                    if pnr_input and len(pnr_input) == 10 and pnr_input.isdigit():
                        with st.spinner("Refreshing PNR..."):
                            data = get_pnr_status(pnr_input)
                            if data and isinstance(data, dict) and data.get('error'):
                                st.error(f"❌ {data.get('error')}")
                            elif data:
                                st.markdown(format_pnr_result(data))
                            else:
                                st.error("❌ PNR not found or flushed.")
                    else:
                        st.warning("Please enter a valid PNR first.")

        # Live Train Tab
        with tab2:
            st.markdown("### Live Train Status")
            train_no = st.text_input("Enter Train Number (3-5 digits)", key="rail_train")
            date_options = [f"{get_date_label(i)} ({get_date_for_offset(i)})" for i in range(5)]
            date_choice = st.selectbox("Select Date", date_options, index=0, key="rail_date")
            offset = 0
            for i in range(5):
                if get_date_label(i) in date_choice:
                    offset = i
                    break
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Get Live Status", key="train_live", use_container_width=True):
                    if not train_no or not train_no.isdigit() or not (3 <= len(train_no) <= 5):
                        st.error("Please enter a valid train number (3-5 digits).")
                    else:
                        with st.spinner("Fetching live status..."):
                            date_str = get_date_for_offset(offset)
                            data = get_live_train_status(train_no, date_str)
                            if data and isinstance(data, dict) and data.get('error'):
                                st.error(f"❌ {data.get('error')}")
                                if 'raw' in data:
                                    with st.expander("🔍 Raw Response"):
                                        st.code(data.get('raw', ''))
                            elif data:
                                st.markdown(format_live_train_result(data))
                            else:
                                st.error("❌ No data available from NTES.")
            with col2:
                if st.button("🔄 Refresh Live Status", key="refresh_live", use_container_width=True):
                    if train_no and train_no.isdigit() and (3 <= len(train_no) <= 5):
                        with st.spinner("Refreshing live status..."):
                            date_str = get_date_for_offset(offset)
                            data = get_live_train_status(train_no, date_str)
                            if data and isinstance(data, dict) and data.get('error'):
                                st.error(f"❌ {data.get('error')}")
                                if 'raw' in data:
                                    with st.expander("🔍 Raw Response"):
                                        st.code(data.get('raw', ''))
                            elif data:
                                st.markdown(format_live_train_result(data))
                            else:
                                st.error("❌ No data available from NTES.")
                    else:
                        st.warning("Please enter a valid train number first.")

        # Schedule Tab
        with tab3:
            st.markdown("### Train Schedule / Route")
            train_no_sch = st.text_input("Enter Train Number (3-5 digits)", key="rail_sch")
            if 'sch_start' not in st.session_state:
                st.session_state.sch_start = 0
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Get Schedule", key="train_sch", use_container_width=True):
                    if not train_no_sch or not train_no_sch.isdigit() or not (3 <= len(train_no_sch) <= 5):
                        st.error("Please enter a valid train number.")
                    else:
                        with st.spinner("Fetching schedule..."):
                            data = get_train_schedule(train_no_sch)
                            if data and isinstance(data, dict) and data.get('error'):
                                st.error(f"❌ {data.get('error')}")
                            elif data:
                                st.session_state.sch_data = data
                                st.session_state.sch_start = 0
                                st.rerun()
                            else:
                                st.error("❌ Schedule not found.")
            with col2:
                if st.button("🔄 Refresh Schedule", key="refresh_sch", use_container_width=True):
                    if train_no_sch and train_no_sch.isdigit() and (3 <= len(train_no_sch) <= 5):
                        with st.spinner("Refreshing schedule..."):
                            data = get_train_schedule(train_no_sch)
                            if data and isinstance(data, dict) and data.get('error'):
                                st.error(f"❌ {data.get('error')}")
                            elif data:
                                st.session_state.sch_data = data
                                st.session_state.sch_start = 0
                                st.rerun()
                            else:
                                st.error("❌ Schedule not found.")
                    else:
                        st.warning("Please enter a valid train number first.")

            if 'sch_data' in st.session_state and st.session_state.sch_data:
                data = st.session_state.sch_data
                if isinstance(data, dict):
                    stations = data.get('stations', [])
                    total = len(stations)
                    chunk = 20
                    start = st.session_state.sch_start
                    end = min(start + chunk, total)
                    if start >= total and total > 0:
                        start = max(0, total - chunk)
                        end = total
                        st.session_state.sch_start = start
                    msg, nav_info = format_schedule_result(data, start)
                    st.markdown(msg)
                    if total > 0 and nav_info:
                        start, end, total = nav_info
                        col1, col2, col3 = st.columns([1,2,1])
                        with col1:
                            if start > 0:
                                if st.button("◀ Previous", key="sch_prev"):
                                    st.session_state.sch_start = max(0, start - chunk)
                                    st.rerun()
                        with col2:
                            st.write(f"Showing {start+1}-{end} of {total}")
                        with col3:
                            if end < total:
                                if st.button("Next ▶", key="sch_next"):
                                    st.session_state.sch_start = end
                                    st.rerun()
                else:
                    st.info("No schedule data available.")

    # ------------------------------------------------------------------
    # View: Weather
    # ------------------------------------------------------------------
    elif view == "🌤️ Weather":
        st.subheader("🌤️ Weather Information")

        city = st.text_input("🏙️ Enter City Name", value=st.session_state.weather_city, 
                            placeholder="e.g., Tinsukia, New Delhi, Mumbai", key="weather_city_input")
        if city != st.session_state.weather_city:
            st.session_state.weather_city = city

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🌤️ Get Weather", key="weather_btn", use_container_width=True):
                if city:
                    with st.spinner(f"Fetching weather for {city}..."):
                        data = get_weather(city)
                        if data and 'error' not in data:
                            st.session_state.weather_data = data
                            st.rerun()
                        else:
                            st.error(data.get('error', 'Error fetching weather'))
                else:
                    st.warning("Please enter a city name.")
        with col2:
            if st.button("🔄 Refresh", key="refresh_weather", use_container_width=True):
                if city:
                    with st.spinner(f"Refreshing weather for {city}..."):
                        data = get_weather(city)
                        if data and 'error' not in data:
                            st.session_state.weather_data = data
                            st.rerun()
                        else:
                            st.error(data.get('error', 'Error fetching weather'))
                else:
                    st.warning("Please enter a city name.")

        if st.session_state.weather_data and 'error' not in st.session_state.weather_data:
            data = st.session_state.weather_data

            st.markdown(f"""
            <div class="weather-card">
                <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap;">
                    <div>
                        <h2 style="margin: 0; font-size: 1.8rem;">{data['city']}, {data['country']}</h2>
                        <div class="weather-desc">{data['weather'].title()}</div>
                    </div>
                    <div style="text-align: center;">
                        <div class="weather-temp">{data['temp']}°C</div>
                        <div style="font-size: 0.9rem; color: #656d76;">Feels like {data['feels_like']}°C</div>
                    </div>
                </div>
                <hr style="margin: 12px 0; border-color: #d0d7de;">
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px;">
                    <div class="weather-detail">💧 Humidity: {data['humidity']}%</div>
                    <div class="weather-detail">🌬️ Wind: {data['wind_speed']} m/s</div>
                    <div class="weather-detail">📊 Pressure: {data['pressure']} hPa</div>
                </div>
            """, unsafe_allow_html=True)

            if data.get('sunrise') and data.get('sunrise') != 'N/A':
                try:
                    sunrise = datetime.fromtimestamp(data['sunrise']).strftime('%H:%M')
                    sunset = datetime.fromtimestamp(data['sunset']).strftime('%H:%M')
                    st.markdown(f"""
                    <div style="display: flex; gap: 20px; margin-top: 8px;">
                        <span>🌅 Sunrise: {sunrise}</span>
                        <span>🌇 Sunset: {sunset}</span>
                    </div>
                    """, unsafe_allow_html=True)
                except:
                    pass

            if data.get('icon'):
                icon_url = f"https://openweathermap.org/img/wn/{data['icon']}@4x.png"
                st.image(icon_url, caption=data['weather'].title(), width=100)

            st.markdown(f'<div style="font-size: 0.8rem; color: #656d76; margin-top: 10px;">🔄 Updated: {format_datetime()}</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        elif st.session_state.weather_data and 'error' in st.session_state.weather_data:
            st.error(st.session_state.weather_data['error'])

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------
    st.markdown("""
    <div class='pro-footer no-print'>
        🚂 AI EQMS Hub Pro • Created by Sharique<br>
        © 2026 All Rights Reserved
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
