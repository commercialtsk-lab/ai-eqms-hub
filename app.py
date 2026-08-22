# =====================================================================
# AI EQMS Hub Pro - Complete Streamlit Application
# =====================================================================
# Created by: Sharique
# Version: 3.0 (Full)
# Description: Emergency Quota Management System for Indian Railways
# =====================================================================

import os
import streamlit as st
import streamlit.components.v1 as components
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
from plotly.subplots import make_subplots
import matplotlib.pyplot as plt
from matplotlib.table import Table as MplTable
import numpy as np
from PIL import Image, ImageDraw

# =====================================================================
# NTES Client (Indian Railways API)
# =====================================================================
try:
    from ntes import NTESClient
    ntes_client = NTESClient()
    NTES_AVAILABLE = True
except ImportError:
    NTES_AVAILABLE = False

# =====================================================================
# Streamlit Page Configuration
# =====================================================================
st.set_page_config(
    page_title="AI EQMS Hub Pro",
    page_icon="🚂",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =====================================================================
# Time Zone Configuration
# =====================================================================
IST = ZoneInfo("Asia/Kolkata")

def now_ist():
    return datetime.now(IST)

def format_time(dt=None):
    if dt is None: dt = now_ist()
    return dt.strftime("%H:%M:%S")

def format_date(dt=None):
    if dt is None: dt = now_ist()
    return dt.strftime("%d-%m-%Y")

def format_datetime(dt=None):
    if dt is None: dt = now_ist()
    return dt.strftime("%d-%m-%Y %H:%M:%S")

# =====================================================================
# Secrets & Configuration
# =====================================================================
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
GSPREAD_CREDENTIALS = st.secrets.get("GSPREAD_CREDENTIALS")
WEATHER_API_KEY = st.secrets.get("WEATHER_API_KEY", "7fff411d9ecb183d6053870fc40823c9")
DRIVE_FOLDER_ID = "1H1gf8WqfoTYFT_pU9WfIDLrHg-NpuUSI"
SHEET_ID = "1QcS3ZF3YYxSEykG0KiOUuXbTdBh0DMHdMgoqa9t8yrI"

if not GEMINI_API_KEY or not GSPREAD_CREDENTIALS:
    st.error("Missing credentials! Please check secrets.toml")
    st.stop()

# =====================================================================
# Session State Defaults
# =====================================================================
defaults = {
    'messages': [], 'activity_log': [], 'last_uploaded_file': None,
    'last_uploaded_drive_url': None, 'last_uploaded_view_url': None,
    'last_uploaded_print_url': None, 'last_refresh': time.time(),
    'chat_suggestions': ["Show me EQ summary", "How many records today?", "Train wise breakup",
        "Pending EQ requests", "Quota status", "PNR status"],
    'theme': 'Auto (System)', 'custom_bg': '#ffffff', 'custom_text': '#000000',
    'current_page': 1, 'pnr_val': '', 'train_val': '', 'from_val': None,
    'to_val': None, 'upload_success': False, 'last_upload_time': None,
    'selected_sheet': "EQ", 'view_mode': "📋 Data Table",
    'select_all': False, 'delete_confirm': False,
    'sidebar_collapsed': False,
    'text_input_key': 0, 'img_uploader_key': 0,
    'audio_uploader_key': 0, 'audio_recorder_key': 0,
    'quick_filter_train': '', 'show_keyboard_help': False, 'print_trigger': False,
    'sch_start': 0, 'sch_data': None, 'weather_data': None, 'weather_forecast': None,
    'system_theme': 'Day', 'weather_city': 'Tinsukia',
    'pnr_result': None, 'train_result': None, 'search_result': None,
    'last_uploaded_drive_id': None, 'manual_refresh': False,
    'sheet_print_data': None,
    'dashboard_filters': {'pnr': '', 'train': '', 'from_doj': None, 'to_doj': None, 'class_filter': '', 'route_filter': '', 'vip_filter': ''},
    'global_search': '', 'sort_column': None, 'sort_ascending': True, 'column_filters': {},
    'rows_per_page': 25, 'dashboard_sheet': 'EQ', 'adv_filters': {},
    'weather_lat': None, 'weather_lon': None, 'weather_location_name': None,
    'pnr_last_checked': None,
    'class_val': '',  # Added missing class_val
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# =====================================================================
# Helper Functions
# =====================================================================
def get_date_label(offset):
    target = datetime.now() - timedelta(days=offset)
    day = target.day
    suffix = {1:'st', 2:'nd', 3:'rd'}.get(day%10 if day not in [11,12,13] else 0, 'th')
    return f"{day}{suffix} {target.strftime('%b')}"

def get_date_for_offset(offset):
    return (datetime.now() - timedelta(days=offset)).strftime("%d-%b-%Y")

# =====================================================================
# Station Map
# =====================================================================
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

# =====================================================================
# Initialize APIs
# =====================================================================
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

# =====================================================================
# Data Cleaning Functions
# =====================================================================
def clean_pnr(pnr):
    if not pnr: return ''
    digits = re.sub(r'\D', '', str(pnr))
    return digits if len(digits) == 10 else (digits[-10:] if len(digits) > 10 else '')

def clean_phone(phone):
    if not phone: return ''
    digits = re.sub(r'\D', '', str(phone))
    return digits[-10:] if len(digits) >= 10 else ''

def parse_date(date_str):
    if not date_str: return ''
    if isinstance(date_str, datetime): return date_str.strftime("%d-%m-%Y")
    date_str = str(date_str).strip()
    multi_match = re.search(r'(\d{1,2})[\/\.\-](\d{1,2})[\/\.\-](\d{2,4})', date_str)
    if multi_match:
        day, month, year = multi_match.groups()
        day, month = day.zfill(2), month.zfill(2)
        if len(year) == 2: year = '20' + year
        if int(month) > 12 and int(day) <= 12: day, month = month, day
        return f"{day}-{month}-{year}"
    return date_str

def get_station(code):
    if not code: return ''
    code = str(code).upper().strip()
    return f"{code} ({STATION_MAP[code]})" if code in STATION_MAP else code

def is_expired(doj_str):
    if not doj_str: return False
    parsed = parse_date(doj_str)
    if not parsed: return False
    try:
        doj_dt = datetime.strptime(parsed, "%d-%m-%Y")
        today = now_ist().replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        return doj_dt < today
    except Exception: return False

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
    if not text: return ''
    replacements = {'•': '-', '·': '-', '\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"', '\u2013': '-', '\u2014': '-'}
    for k, v in replacements.items(): text = text.replace(k, v)
    return text.encode('latin-1', 'ignore').decode('latin-1')

def find_column(df, keywords):
    """Find column name in df matching any keyword (case-insensitive, stripped, fuzzy)."""
    for col in df.columns:
        col_clean = str(col).strip().upper().replace(' ', '').replace('_', '').replace('/', '').replace('-', '')
        for kw in keywords:
            kw_clean = kw.upper().replace(' ', '').replace('_', '').replace('/', '').replace('-', '')
            if kw_clean in col_clean or col_clean in kw_clean:
                return col
    return None

def column_has_data(df, col):
    """Check if a column exists and has at least one non-empty value."""
    if col is None or col not in df.columns:
        return False
    return df[col].astype(str).str.strip().ne('').any()

# =====================================================================
# Sheet Configuration
# =====================================================================
EQ_HEADINGS = ['S/N', 'PNR', 'FROM', 'TO', 'BOARDING', 'T/N', 'CLASS', 'DOJ',
    'PASS NAME', 'PASS PH', 'T/BERTHS', 'PURPOSE', 'ADDRESS',
    'DIARY NO', 'RECOMMENDATION', 'DESIGNATION', 'PHONE NUBER',
    'MP/MLA/MR/MINISTER/VIP/VVIP', 'WARRANT NUMBER', 'PROCEESING DATE+TIME',
    'APPLICATION DATE', 'RAILWAY/ZONE/DIVISION', 'PREFERENCE']

SHEET_CONFIG = {
    # EQ & DATA: same layout — data rows start at row 5 (EQ) / row 4 (DATA)
    # Cols: A=S/N, B=PNR, C=FROM, D=TO, E=BOARDING, F=T/N, G=CLASS, H=DOJ, I=PASS_NAME, J=PASS_PH,
    #       K=T/BERTHS, L=PURPOSE, M=ADDRESS, N=DIARY_NO, O=RECOMMENDATION, P=DESIGNATION, Q=PHONE,
    #       R=VIP_STATUS, S=WARRANT, T=PROC_DATE, U=APP_DATE, V=ZONE, W=PREFERENCE
    "EQ": {"start_row": 5, "pnr_col": 1, "train_col": 5, "class_col": 6, "from_col": 2, "to_col": 3, "berth_col": 10, "doj_col": 7, "headings": EQ_HEADINGS},
    "DATA": {"start_row": 4, "pnr_col": 1, "train_col": 5, "class_col": 6, "from_col": 2, "to_col": 3, "berth_col": 10, "doj_col": 7, "headings": EQ_HEADINGS},

    # FINAL & DATA2: same layout — data rows start at row 6
    # Cols: A=T/N, B=CLASS, C=FROM, D=TO, E=BOARDING, F=T/BERTHS, G=PASS_NAME, H=PASS_PH, I=PURPOSE,
    #       J=ADDRESS, K=FROM_STN, L=TO_STN, M=DOJ, N=RECOMMENDATION ...
    "FINAL": {"start_row": 6, "pnr_col": 7, "train_col": 1, "class_col": 2, "from_col": 10, "to_col": 11, "berth_col": 5, "doj_col": 12, "headings": EQ_HEADINGS},
    "DATA2": {"start_row": 6, "pnr_col": 7, "train_col": 1, "class_col": 2, "from_col": 10, "to_col": 11, "berth_col": 5, "doj_col": 12, "headings": EQ_HEADINGS},

    # EMAIL_DATA: row 2, columns: I=train, J=from, K=to, L=DOJ, M=class, P=berths (total seats)
    "EMAIL_DATA": {"start_row": 2, "pnr_col": 6, "train_col": 8, "class_col": 12, "from_col": 9, "to_col": 10, "berth_col": 15, "doj_col": 11, "headings": EQ_HEADINGS},
    "NOTE": {"start_row": 2, "pnr_col": None, "train_col": 0, "class_col": None, "from_col": None, "to_col": None, "berth_col": None, "doj_col": None, "headings": []}
}

# =====================================================================
# Load Sheet Data
# =====================================================================
@st.cache_data(ttl=10, show_spinner=False)
def load_sheet_data_cached(sheet_name, sheet_id):
    try:
        gc = init_sheets()
        sheet = gc.open_by_key(sheet_id).worksheet(sheet_name)
        all_data = sheet.get_all_values()
        config = SHEET_CONFIG.get(sheet_name, {"start_row": 1})
        start_row = config["start_row"]
        if len(all_data) < start_row: return pd.DataFrame()
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
        if not data_rows: return pd.DataFrame()
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

# =====================================================================
# Smart Detection Functions
# =====================================================================
def smart_detect_warrant(text):
    if not text: return {'warrant': '', 'found': False}
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
    if not text: return {'isRailBoard': False}
    text = str(text).upper()
    clean_text = re.sub(r'\s+', ' ', text).strip()
    patterns = [
        r'RAIL\s*BOARD', r'OFFICE\s*OF\s*(?:THE\s*)?HON\'BLE\s*MINISTER\s*RAILWAYS',
        r'OFFICE\s*OF\s*(?:THE\s*)?HONOURABLE\s*MINISTER\s*RAILWAYS',
        r'HON\'BLE\s*MINISTER\s*RAILWAYS', r'HONOURABLE\s*MINISTER\s*RAILWAYS',
        r'MINISTER\s*RAILWAYS', r'MINISTRY\s*OF\s*RAILWAYS', r'RAIL\s*MANTRI', r'RAIL\s*BHAWAN'
    ]
    for pattern in patterns:
        if re.search(pattern, clean_text): return {'isRailBoard': True}
    keywords = ['MINISTER', 'RAILWAYS', 'RAILWAY', 'HONBLE', "HON'BLE", 'RAIL MANTRI', 'OFFICE', 'RAIL', 'BOARD']
    score = sum(1 for kw in keywords if kw in clean_text)
    if score >= 4: return {'isRailBoard': True}
    if 'OFFICE' in clean_text and 'MINISTER' in clean_text and ('RAILWAYS' in clean_text or 'RAILWAY' in clean_text):
        office_idx = clean_text.find('OFFICE')
        minister_idx = clean_text.find('MINISTER')
        if office_idx != -1 and minister_idx != -1 and abs(office_idx - minister_idx) < 50:
            return {'isRailBoard': True}
    return {'isRailBoard': False}

def smart_detect_diary(text):
    if not text: return {'diary': '', 'found': False}
    text = str(text).upper()
    patterns = [
        r'DIARY\s*NO\.?\s*[:#]?\s*([A-Z0-9\/\-]+)',
        r'DIARY\s*NUMBER\s*[:#]?\s*([A-Z0-9\/\-]+)',
        r'D\/?NO\.?\s*[:#]?\s*([A-Z0-9\/\-]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            diary = match.group(1).strip()
            if len(diary) > 3: return {'diary': diary, 'found': True}
    return {'diary': '', 'found': False}

def smart_detect_vip(text):
    if not text: return ''
    text = str(text).upper()
    if 'MINISTER' in text: return 'MINISTER'
    if re.search(r'\bMR\b', text): return 'MR'
    if re.search(r'\bMP\b', text) and 'PMO' not in text: return 'MP'
    if re.search(r'\bMLA\b', text): return 'MLA'
    if 'OSD' in text: return 'OSD'
    if 'PMO' in text: return 'PMO'
    if 'VVIP' in text: return 'VVIP'
    if 'VIP' in text: return 'VIP'
    return ''

def smart_detect_lower_seat(text):
    if not text: return False
    text = str(text).upper()
    keywords = ['AGE+', 'AGE +', 'MEDICAL', 'HANDICAP', 'SR CITIZEN', 'SENIOR', 'DISABLED']
    return any(kw in text for kw in keywords)

# =====================================================================
# Process Extracted Records
# =====================================================================
def process_extracted_records(records):
    cleaned = []
    seen = set()
    for rec in records:
        pnr = clean_pnr(rec.get('PNR', ''))
        if not pnr or pnr in seen: continue
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
            if warrant['found']: warrant_val = warrant['warrant']
        if not diary_val or diary_val == '-' or diary_val == '':
            diary = smart_detect_diary(full_text)
            if diary['found']: diary_val = diary['diary']
        if not vip:
            detected_vip = smart_detect_vip(full_text)
            if detected_vip: vip = detected_vip
        if smart_detect_lower_seat(full_text) and (pref == 'General' or pref == '' or pref == '-'):
            pref = 'Lower Seat'
        if not pref or pref == '' or pref == '-': pref = 'General'
        doj_raw = str(rec.get('DOJ', '')).strip()
        doj_parsed = parse_date(doj_raw)
        if not doj_parsed or doj_parsed == 'Invalid Date' or doj_parsed == 'NaN-NaN-NaN': doj_parsed = ''
        cleaned.append({
            'PNR': pnr, 'T_N': str(rec.get('T_N', '')).strip(),
            'CLASS': str(rec.get('CLASS', '')).strip().upper(),
            'DOJ': doj_parsed, 'FROM': str(rec.get('FROM', '')).strip().upper(),
            'TO': str(rec.get('TO', '')).strip().upper(),
            'BOARDING': str(rec.get('BOARDING', '')).strip().upper(),
            'PASS_NAME': str(rec.get('PASS_NAME', '')).strip(),
            'PASS_PH': clean_phone(str(rec.get('PASS_PH', ''))),
            'T_BERTHS': int(rec.get('T_BERTHS', 1)) if str(rec.get('T_BERTHS', '')).isdigit() else 1,
            'PURPOSE': str(rec.get('PURPOSE', '')).strip(),
            'ADDRESS': str(rec.get('ADDRESS', '')).strip(),
            'DIARY_NO': diary_val, 'RECOMMENDATION': str(rec.get('RECOMMENDATION', '')).strip(),
            'DESIGNATION': str(rec.get('DESIGNATION', '')).strip(),
            'VIP_STATUS': vip, 'APPLICATION_DATE': parse_date(str(rec.get('APPLICATION_DATE', ''))),
            'RAILWAY_ZONE': zone, 'PREFERENCE': pref,
            'PHONE_NUBER': clean_phone(str(rec.get('PHONE_NUBER', ''))),
            'WARRANT_NO': warrant_val
        })
    if not cleaned: return {'error': 'No valid records extracted'}
    return {'records': cleaned, 'count': len(cleaned)}

# =====================================================================
# Gemini Parser
# =====================================================================
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
        parts.append({"text": system_prompt + """

INPUT DATA:
""" + input_data})
    else:
        return {'error': 'Unsupported type'}
    if progress_callback: progress_callback(30, "Sending to Gemini...")
    payload = {"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.4, "maxOutputTokens": 16384}}
    try:
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, timeout=120)
        if response.status_code != 200: return {'error': f'Gemini API Error: {response.status_code}'}
        data = response.json()
        if not data.get('candidates') or not data['candidates'][0].get('content', {}).get('parts'):
            return {'error': 'Empty response from Gemini'}
        response_text = data['candidates'][0]['content']['parts'][0]['text']
        if progress_callback: progress_callback(60, "Parsing Gemini response...")
        json_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', response_text)
        if not json_match:
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
            if json_match: json_str = json_match.group(1)
            else:
                if progress_callback: progress_callback(80, "Using fallback extraction...")
                return {'error': 'Could not parse Gemini response', 'raw': response_text[:500]}
        else: json_str = json_match.group(0)
        json_str = json_str.replace('```json', '').replace('```', '').strip()
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*\]', ']', json_str)
        json_str = re.sub(r'([a-zA-Z0-9_]+)\s*:', r'"\1":', json_str)
        json_str = json_str.replace("'", '"')
        records = json.loads(json_str)
        if isinstance(records, dict): records = [records]
        if progress_callback: progress_callback(90, "Processing records...")
        result = process_extracted_records(records)
        if progress_callback: progress_callback(100, "Complete!")
        return result
    except Exception as e:
        return {'error': f'Parser Error: {e}'}

# =====================================================================
# Drive Upload
# =====================================================================
def upload_to_drive(file_bytes, filename, mime_type):
    try:
        drive_service = init_drive()
        file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=True)
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id,name,webViewLink,size').execute()
        file_id = file.get('id')
        return {'success': True, 'id': file_id, 'name': file.get('name'), 'url': file.get('webViewLink'),
                'size': file.get('size'), 'view_url': f"https://drive.google.com/file/d/{file_id}/view",
                'print_url': f"https://drive.google.com/file/d/{file_id}/preview",
                'download_url': f"https://drive.google.com/uc?export=download&id={file_id}"}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# =====================================================================
# Save to Sheet
# =====================================================================
def save_to_sheet(sheet, records):
    try:
        all_data = sheet.get_all_values()
        existing_pnrs = []
        start_row = 5
        for row in all_data[start_row-1:]:
            if row and len(row) > 1:
                pnr = clean_pnr(row[1])
                if pnr: existing_pnrs.append(pnr)
        saved, skipped = 0, 0
        next_sn = len(all_data) - start_row + 2
        for rec in records:
            pnr = clean_pnr(rec.get('PNR', ''))
            if not pnr or pnr in existing_pnrs:
                skipped += 1
                continue
            now = format_datetime()
            row = [next_sn, pnr, rec.get('FROM', ''), rec.get('TO', ''), rec.get('BOARDING', ''),
                rec.get('T_N', ''), rec.get('CLASS', ''), rec.get('DOJ', ''), rec.get('PASS_NAME', ''),
                rec.get('PASS_PH', ''), rec.get('T_BERTHS', 1), rec.get('PURPOSE', ''), rec.get('ADDRESS', ''),
                rec.get('DIARY_NO', ''), rec.get('RECOMMENDATION', ''), rec.get('DESIGNATION', ''),
                rec.get('PHONE_NUBER', ''), rec.get('VIP_STATUS', ''), rec.get('WARRANT_NO', ''),
                now, rec.get('APPLICATION_DATE', ''), rec.get('RAILWAY_ZONE', ''), rec.get('PREFERENCE', 'General')]
            sheet.append_row(row)
            existing_pnrs.append(pnr)
            next_sn += 1
            saved += 1
            time.sleep(0.12)
        return {'saved': saved, 'skipped': skipped}
    except Exception as e:
        return {'error': str(e)}

# =====================================================================
# Get Sheet Context for Chat
# =====================================================================
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

# =====================================================================
# Chat with Gemini
# =====================================================================
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
            if msg['role'] == 'user': system_prompt += f"User: {msg['content']}\n"
            else: system_prompt += f"Assistant: {msg['content']}\n"
        system_prompt += f"\nUser: {user_message}\nAssistant:"
        response = model.generate_content(system_prompt)
        return response.text
    except Exception as e:
        return f"⚠️ Error: Could not process your request. Please try again later. ({str(e)})"

# =====================================================================
# Weather Functions
# =====================================================================
def get_weather(city_name):
    if not city_name: return {'error': 'Please enter a city name'}
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={WEATHER_API_KEY}&units=metric"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {'city': data.get('name', city_name), 'country': data.get('sys', {}).get('country', ''),
                'temp': data.get('main', {}).get('temp', 'N/A'), 'feels_like': data.get('main', {}).get('feels_like', 'N/A'),
                'humidity': data.get('main', {}).get('humidity', 'N/A'), 'pressure': data.get('main', {}).get('pressure', 'N/A'),
                'weather': data.get('weather', [{}])[0].get('description', 'N/A'),
                'icon': data.get('weather', [{}])[0].get('icon', ''),
                'wind_speed': data.get('wind', {}).get('speed', 'N/A'), 'wind_deg': data.get('wind', {}).get('deg', 'N/A'),
                'sunrise': data.get('sys', {}).get('sunrise', 'N/A'), 'sunset': data.get('sys', {}).get('sunset', 'N/A'),
                'lat': data.get('coord', {}).get('lat'), 'lon': data.get('coord', {}).get('lon')}
        else: return {'error': 'City not found. Please check the name.'}
    except Exception as e: return {'error': f'Error fetching weather: {str(e)}'}

def get_weather_forecast(city_name):
    if not city_name: return {'error': 'Please enter a city name'}
    try:
        url = f"https://api.openweathermap.org/data/2.5/forecast?q={city_name}&appid={WEATHER_API_KEY}&units=metric"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            forecast_list = data.get('list', [])
            daily_forecast = {}
            for item in forecast_list:
                date = item.get('dt_txt', '')[:10]
                if date not in daily_forecast:
                    daily_forecast[date] = {'temps': [], 'weather': item['weather'][0]['main'] if item.get('weather') else 'N/A',
                        'icon': item['weather'][0]['icon'] if item.get('weather') else '', 'humidity': item['main']['humidity'],
                        'wind': item['wind']['speed'], 'pressure': item['main']['pressure'],
                        'description': item['weather'][0]['description'] if item.get('weather') else 'N/A'}
                daily_forecast[date]['temps'].append(item['main']['temp'])
            result = []
            for date, info in list(daily_forecast.items())[:5]:
                result.append({'date': date, 'temp': round(sum(info['temps'])/len(info['temps']), 1),
                    'min_temp': round(min(info['temps']), 1), 'max_temp': round(max(info['temps']), 1),
                    'weather': info['weather'], 'description': info['description'].title(),
                    'icon': info['icon'], 'humidity': info['humidity'], 'wind': info['wind'], 'pressure': info['pressure']})
            return {'forecast': result, 'city': data.get('city', {}).get('name', city_name), 'country': data.get('city', {}).get('country', '')}
        else: return {'error': 'City not found. Please check the name.'}
    except Exception as e: return {'error': f'Error fetching forecast: {str(e)}'}

def get_weather_by_coords(lat, lon):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {'city': data.get('name', 'Unknown'), 'country': data.get('sys', {}).get('country', ''),
                'temp': data.get('main', {}).get('temp', 'N/A'), 'feels_like': data.get('main', {}).get('feels_like', 'N/A'),
                'humidity': data.get('main', {}).get('humidity', 'N/A'), 'pressure': data.get('main', {}).get('pressure', 'N/A'),
                'weather': data.get('weather', [{}])[0].get('description', 'N/A'),
                'icon': data.get('weather', [{}])[0].get('icon', ''),
                'wind_speed': data.get('wind', {}).get('speed', 'N/A'), 'wind_deg': data.get('wind', {}).get('deg', 'N/A'),
                'sunrise': data.get('sys', {}).get('sunrise', 'N/A'), 'sunset': data.get('sys', {}).get('sunset', 'N/A'),
                'lat': lat, 'lon': lon}
        else: return {'error': 'Location not found'}
    except Exception as e: return {'error': f'Error: {str(e)}'}

def get_forecast_by_coords(lat, lon):
    try:
        url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            forecast_list = data.get('list', [])
            daily_forecast = {}
            for item in forecast_list:
                date = item.get('dt_txt', '')[:10]
                if date not in daily_forecast:
                    daily_forecast[date] = {'temps': [], 'weather': item['weather'][0]['main'] if item.get('weather') else 'N/A',
                        'icon': item['weather'][0]['icon'] if item.get('weather') else '', 'humidity': item['main']['humidity'],
                        'wind': item['wind']['speed'], 'pressure': item['main']['pressure'],
                        'description': item['weather'][0]['description'] if item.get('weather') else 'N/A'}
                daily_forecast[date]['temps'].append(item['main']['temp'])
            result = []
            for date, info in list(daily_forecast.items())[:5]:
                result.append({'date': date, 'temp': round(sum(info['temps'])/len(info['temps']), 1),
                    'min_temp': round(min(info['temps']), 1), 'max_temp': round(max(info['temps']), 1),
                    'weather': info['weather'], 'description': info['description'].title(),
                    'icon': info['icon'], 'humidity': info['humidity'], 'wind': info['wind'], 'pressure': info['pressure']})
            return {'forecast': result, 'city': data.get('city', {}).get('name', 'Unknown'), 'country': data.get('city', {}).get('country', '')}
        else: return {'error': 'Forecast not available'}
    except Exception as e: return {'error': f'Error: {str(e)}'}

def get_location_from_ip():
    services = [
        {"url": "https://ipapi.co/json/", "parser": lambda d: {'city': d.get('city', ''), 'lat': d.get('latitude'), 'lon': d.get('longitude'), 'country': d.get('country_name', '')}},
        {"url": "https://ip-api.com/json/", "parser": lambda d: {'city': d.get('city', ''), 'lat': d.get('lat'), 'lon': d.get('lon'), 'country': d.get('country', '')} if d.get('status') == 'success' else None},
        {"url": "https://ipinfo.io/json", "parser": lambda d: {'city': d.get('city', '').replace(', India', '').strip(), 'lat': float(d.get('loc','').split(',')[0]) if d.get('loc') else None, 'lon': float(d.get('loc','').split(',')[1]) if d.get('loc') and len(d.get('loc','').split(','))>1 else None, 'country': d.get('country', '')}}
    ]
    for svc in services:
        try:
            resp = requests.get(svc["url"], timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                result = svc["parser"](data)
                if result and result.get('city'):
                    return result
        except Exception: continue
    return None

# =====================================================================
# NTES / Railway Functions
# =====================================================================
def safe_list(data, key):
    val = data.get(key) if data else None
    if val is None: return []
    if isinstance(val, list): return val
    return [val]

def safe_str(val, default='N/A'):
    return str(val) if val is not None else default

def format_station_time(time_str):
    if not time_str or time_str in ['N/A', 'Source', 'Dest']: return time_str
    time_parts = time_str.split()
    if len(time_parts) >= 2 and any(m in time_parts[1] for m in ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']):
        return time_parts[0]
    return time_str

def get_stn_field(station, possible_keys, default=''):
    if not station or not isinstance(station, dict): return default
    for key in possible_keys:
        if key in station: return station[key]
    lower_map = {k.lower(): v for k, v in station.items()}
    for key in possible_keys:
        if key.lower() in lower_map: return lower_map[key.lower()]
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
        'STA': sta if sta else (eta if eta else 'N/A'), 'STD': std if std else (etd if etd else 'N/A'),
        'ETA': eta, 'ETD': etd, 'DAY': safe_str(day, '')}

def find_station_index(stations, current_code, current_name, pos_str):
    if not stations: return -1, "none"
    if current_code: current_code = current_code.upper().strip()
    if current_name: current_name = current_name.upper().strip()
    if current_code:
        for i, s in enumerate(stations):
            if s.get('SC','').upper().strip() == current_code: return i, "code_exact"
    if current_code and len(current_code) >= 3:
        for i, s in enumerate(stations):
            sc = s.get('SC','').upper().strip()
            if sc and (current_code in sc or sc in current_code): return i, "code_contains"
    if current_name:
        for i, s in enumerate(stations):
            sn = s.get('SN','').upper().strip()
            if sn == current_name: return i, "name_exact"
    if current_name:
        for i, s in enumerate(stations):
            sn = s.get('SN','').upper().strip()
            if sn and (current_name in sn or sn in current_name): return i, "name_contain"
    if current_name:
        current_words = set(re.findall(r'[A-Z]{3,}', current_name))
        for i, s in enumerate(stations):
            sn = s.get('SN','').upper().strip()
            if current_words.intersection(set(re.findall(r'[A-Z]{3,}', sn))): return i, "name_word"
    return -1, "none"

def find_nearest_stoppage(stations, current_code, current_name, pos_str):
    if not stations: return -1, "none"
    idx, _ = find_station_index(stations, current_code, current_name, pos_str)
    if idx >= 0: return idx, "direct"
    pos_lower = pos_str.lower()
    if 'between' in pos_lower:
        match = re.search(r'between\s+([A-Z]+)\s+and\s+([A-Z]+)', pos_str, re.IGNORECASE)
        if match:
            next_code = match.group(2).upper()
            for i, s in enumerate(stations):
                if s.get('SC','').upper().strip() == next_code: return i, "between"
    patterns = [r'after\s+([A-Z]+)\s+before\s+([A-Z]+)', r'from\s+([A-Z]+)\s+to\s+([A-Z]+)']
    for pattern in patterns:
        match = re.search(pattern, pos_str, re.IGNORECASE)
        if match:
            next_code = match.group(2).upper()
            for i, s in enumerate(stations):
                if s.get('SC','').upper().strip() == next_code: return i, "pattern"
    return -1, "none"

def get_full_schedule(train_number):
    try:
        return [normalize_station(s) for s in safe_list(ntes_client.schedule(train_number), 'stations')
                if (s.get('STA') and s.get('STA') != 'N/A') or (s.get('STD') and s.get('STD') != 'N/A')
                or s.get('STA') == 'Source' or s.get('STD') == 'Dest']
    except Exception: return []

def get_pnr_status(pnr):
    if not NTES_AVAILABLE: return {"error": "NTES library not installed"}
    try:
        response = ntes_client.pnr_status(pnr)
        if not response: return {"error": "NO_DATA", "message": "Empty response from NTES server"}
        err_msg = response.get('errorMessage', '')
        if err_msg and 'FLUSHED' in str(err_msg).upper(): return {"error": "FLUSHED_PNR"}
        if not response.get('pnrNumber'): return {"error": "NO_DATA", "message": "Invalid PNR or server error"}
        passengers = []
        for p in safe_list(response, 'passengerList'):
            passengers.append({'booking_status': safe_str(p.get('bookingStatusDetails'), 'N/A'),
                'current_status': safe_str(p.get('currentStatusDetails'), 'N/A')})
        return {"pnr": safe_str(response.get('pnrNumber')), "train_number": safe_str(response.get('trainNumber')),
            "train_name": safe_str(response.get('trainName')), "journey_date": safe_str(response.get('dateOfJourney')),
            "class": safe_str(response.get('journeyClass')), "quota": safe_str(response.get('quota')),
            "chart_status": safe_str(response.get('chartStatus'), 'Not Prepared'),
            "boarding_point": safe_str(response.get('boardingPoint')), "destination": safe_str(response.get('destinationStation')),
            "passengers": passengers}
    except requests.exceptions.ConnectTimeout:
        return {"error": "TIMEOUT", "message": "NTES server is not responding."}
    except requests.exceptions.ConnectionError:
        return {"error": "CONNECTION_ERROR", "message": "Cannot connect to NTES server."}
    except Exception as e:
        err_str = str(e)
        if "timeout" in err_str.lower() or "connection" in err_str.lower():
            return {"error": "NETWORK_ERROR", "message": f"Network issue: {err_str[:200]}."}
        return {"error": "API_ERROR", "message": err_str[:200]}

def get_confirmation_prediction(passengers, chart_status):
    if "prepared" in str(chart_status).lower() or not passengers: return None
    confirmed = 0
    for p in passengers:
        status = str(p.get('current_status', '')).upper()
        if 'CNF' in status: confirmed += 1
        elif 'RAC' in status: confirmed += 0.5
        elif 'PQWL' in status or 'WL' in status:
            try:
                if '/' in status: confirmed += 0.7 if int(status.split('/')[-1]) <= 3 else 0.4 if int(status.split('/')[-1]) <= 5 else 0.1
            except: confirmed += 0.2
    base = (confirmed / len(passengers)) * 100
    if confirmed / len(passengers) < 0.5: base += 10
    return min(100, max(0, round(base)))

def get_status_icon(status, chart_status=None):
    status_upper = str(status).upper()
    if 'CAN' in status_upper: return "❌"
    if 'CNF' in status_upper: return "✅"
    if 'RAC' in status_upper: return "🟡"
    if 'PQWL' in status_upper or 'WL' in status_upper:
        return "🔴" if chart_status and "prepared" in str(chart_status).lower() else "⏱️"
    return "ℹ️"

def get_status_note(status, chart_status):
    status_upper = str(status).upper()
    if 'CAN' in status_upper: return "❌ Ticket Cancelled!"
    if 'CNF' in status_upper: return "✅ Confirmed!"
    if 'RAC' in status_upper:
        return "🟡 RAC - May get confirmed" if "prepared" in str(chart_status).lower() else "🟡 RAC - Chance of confirmation"
    if 'PQWL' in status_upper:
        if "prepared" in str(chart_status).lower(): return "🔴 PQWL - Chart ready, waiting"
        try: num = int(status.split('/')[-1]) if '/' in status else 0
        except: num = 0
        if num <= 3: return "⏱️ PQWL - Good chance!"
        elif num <= 5: return "⏱️ PQWL - May confirm"
        return "⏱️ PQWL - Low chance"
    if 'WL' in status_upper:
        if "prepared" in str(chart_status).lower(): return "🔴 WL - Chart ready, waiting"
        try: num = int(status.split('/')[-1]) if '/' in status else 0
        except: num = 0
        if num <= 5: return "⏱️ WL - Good chance!"
        elif num <= 10: return "⏱️ WL - May confirm"
        return "⏱️ WL - Low chance"
    return "ℹ️ Check status"

def format_pnr_result(data):
    if not data: return "❌ PNR not found."
    if isinstance(data, dict) and data.get('error'):
        if data['error'] == "FLUSHED_PNR": return "❌ FLUSHED PNR / PNR NOT YET GENERATED\n\nPlease check the PNR number and try again."
        return f"❌ Error: {data['error']}"
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
    msg += f"\n\n📌 Last Updated @ {now_ist().strftime('%d %b %H:%M:%S')}"
    return msg

def get_live_train_status(train_number, date_str=None):
    if not NTES_AVAILABLE: return {"error": "NTES library not installed"}
    try:
        if date_str is None: date_str = datetime.now().strftime("%d-%b-%Y")
        date_formats = [date_str, date_str.replace('-', ' '), date_str.replace('-', '/')]
        response = None
        for fmt in date_formats:
            try:
                response = ntes_client.live_status(train_number, fmt)
                if response and response.get('CPOS'): break
            except Exception: continue
        if not response or not response.get('CPOS'): return {"error": "NO_DATA", "message": "No live data available for this train/date"}
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
                    if word in pos_str.upper(): is_completed = True; break
        current_code = None
        current_name = None
        m = re.search(r'\(([A-Z]{2,5})\)', pos_str)
        if m: current_code = m.group(1).upper()
        if not current_code:
            for pattern in [r'from\s+([A-Z]{2,5})\b', r'at\s+([A-Z]{2,5})\b', r'(?:departed|arrived|left|reached)\s+(?:from\s+|at\s+)?([A-Z]{2,5})\b']:
                m = re.search(pattern, pos_str, re.IGNORECASE)
                if m: current_code = m.group(1).upper(); break
        if not current_name:
            for pattern in [r'(?:from|at|departed|arrived|left|reached)\s+([A-Z][A-Z\s]+?)(?:\s*\(|$)', r'(?:has|is)\s+([A-Z][A-Z\s]+?)\s+(?:station|junction|jn)']:
                m = re.search(pattern, pos_str, re.IGNORECASE)
                if m: current_name = re.sub(r'\s+(JUNCTION|JN|ROAD|RD|CITY|CANTT|NAGAR|NG)$', '', m.group(1).strip().upper()); break
        live_stations_map = {}
        stations_raw = safe_list(response, 'STNSD')
        if not stations_raw: stations_raw = safe_list(response, 'STNS')
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
                    if live.get(k): merged[k] = live[k]
                merged_stations.append(merged)
            else: merged_stations.append(s)
        upcoming = []
        mapped_idx = -1
        is_non_stoppage = False
        if is_completed: upcoming = []
        elif is_not_started: upcoming = merged_stations[:8]
        else:
            if merged_stations:
                curr_idx, match_type = find_station_index(merged_stations, current_code, current_name, pos_str)
                if curr_idx >= 0:
                    if curr_idx + 1 < len(merged_stations): upcoming = merged_stations[curr_idx+1:curr_idx+9]
                    else: is_completed = True
                else:
                    is_non_stoppage = True
                    mapped_idx, map_type = find_nearest_stoppage(merged_stations, current_code, current_name, pos_str)
                    if mapped_idx >= 0:
                        if mapped_idx + 1 < len(merged_stations): upcoming = merged_stations[mapped_idx+1:mapped_idx+9]
                        else: is_completed = True
                    elif all_live and (current_code or current_name):
                        live_idx, _ = find_station_index(all_live, current_code, current_name, pos_str)
                        if live_idx >= 0 and live_idx + 1 < len(all_live):
                            next_code = all_live[live_idx+1].get('SC', '').upper()
                            for i, ms in enumerate(merged_stations):
                                if ms.get('SC','').upper() == next_code:
                                    upcoming = merged_stations[i:i+8]
                                    break
                            if not upcoming: upcoming = all_live[live_idx+1:live_idx+9]
                    if not upcoming: return {"error": "NO_DATA", "message": "Train position unclear for this date"}
            elif all_live:
                curr_idx, _ = find_station_index(all_live, current_code, current_name, pos_str)
                if curr_idx >= 0: upcoming = all_live[curr_idx+1:curr_idx+9]
                else: return {"error": "NO_DATA", "message": "Train position unclear for this date"}
        if not upcoming and not is_completed and merged_stations: upcoming = merged_stations[:8]
        return {"train_number": train_number, "train_name": train_name, "current_station": current_pos,
            "source": source, "destination": destination, "journey_date": journey_date,
            "delay": delay, "excpt": excpt, "state": "completed" if is_completed else ("not_started" if is_not_started else "running"),
            "stations": upcoming[:8], "last_updated": datetime.now().strftime('%d %b %H:%M:%S'),
            "query_date": date_str, "current_code": current_code, "current_name": current_name,
            "is_non_stoppage": is_non_stoppage, "mapped_idx": mapped_idx}
    except requests.exceptions.ConnectTimeout:
        return {"error": "TIMEOUT", "message": "NTES server is not responding."}
    except requests.exceptions.ConnectionError:
        return {"error": "CONNECTION_ERROR", "message": "Cannot connect to NTES server."}
    except Exception as e:
        err_str = str(e)
        if "timeout" in err_str.lower() or "connection" in err_str.lower():
            return {"error": "NETWORK_ERROR", "message": f"Network issue: {err_str[:200]}."}
        return {"error": "API_ERROR", "message": err_str[:200]}

def format_live_train_result(data):
    if not data: return "❌ Train not found. Please check the train number.", None
    if isinstance(data, dict) and data.get('error'): return f"❌ {data.get('error')}: {data.get('message', 'Unknown error')}", None
    train_no = data.get('train_number', 'N/A')
    query_date = data.get('query_date', datetime.now().strftime("%d-%b-%Y"))
    journey_state = data.get('state', 'running')
    current_offset = 0
    for offset in range(5):
        if query_date == get_date_for_offset(offset): current_offset = offset; break
    date_label = get_date_label(current_offset)
    msg = f"## 🚂 LIVE TRAIN STATUS — {date_label.upper()}\n\n"
    msg += f"**Train:** {data.get('train_name', 'N/A')} ({train_no})\n"
    msg += f"**From:** {data.get('source', 'N/A')} → {data.get('destination', 'N/A')}\n"
    msg += f"**Date:** {data.get('journey_date', 'N/A')}\n"
    delay = data.get('delay', '0')
    msg += f"**Delay:** {'✅ On Time' if str(delay) == '0' else f'⏰ {delay} mins late'}\n"
    msg += f"**Current Status:** {data.get('current_station', 'N/A')}\n"
    if data.get('excpt'): msg += f"\n⚠️ **Exception:** {data.get('excpt')}\n"
    if journey_state == "completed":
        msg += "\n🏁 **JOURNEY COMPLETED**\n✅ Train has reached its destination.\n"
    elif journey_state == "not_started":
        msg += "\n⏳ **JOURNEY NOT STARTED**\n📌 Train is yet to depart from source.\n"
        stations = data.get('stations', [])
        if stations:
            msg += "\n**Scheduled Stations:**\n"
            for i, s in enumerate(stations[:8], 1):
                msg += f"{i}. **{s.get('SC', 'N/A')}** — {s.get('SN', 'N/A')}\n"
                msg += f"   Arr: {format_station_time(s.get('STA', 'N/A'))} | Dep: {format_station_time(s.get('STD', 'N/A'))}"
                if s.get('DAY'): msg += f" | Day: {s.get('DAY', '')}"
                msg += "\n"
        else: msg += "\n📋 No schedule available.\n"
    else:
        stations = data.get('stations', [])
        if stations:
            msg += "\n**Upcoming Stations:**\n"
            for i, s in enumerate(stations, 1):
                arrival = s.get('ETA', '') or s.get('STA', 'N/A')
                departure = s.get('ETD', '') or s.get('STD', 'N/A')
                msg += f"{i}. **{s.get('SC', 'N/A')}** — {s.get('SN', 'N/A')}\n"
                msg += f"   Arr: {format_station_time(arrival)} | Dep: {format_station_time(departure)}"
                if s.get('DAY'): msg += f" | Day: {s.get('DAY', '')}"
                msg += "\n"
        else: msg += "\n📋 No upcoming stations available.\n"
    msg += f"\n_Last updated: {data.get('last_updated', datetime.now().strftime('%d %b %H:%M:%S'))}_"
    return msg, None

def search_trains(query):
    if not NTES_AVAILABLE: return {"error": "NTES library not installed"}
    try:
        response = ntes_client.search(query)
        if not response or not response.get('trains'): return None
        trains = []
        for t in safe_list(response, 'trains')[:15]:
            trains.append({'train_number': safe_str(t.get('train_number')), 'train_name': safe_str(t.get('train_name')),
                'source': safe_str(t.get('source')), 'destination': safe_str(t.get('destination'))})
        return {"query": query, "trains": trains, "last_updated": datetime.now().strftime('%d %b %H:%M:%S')}
    except requests.exceptions.ConnectTimeout: return {"error": "TIMEOUT", "message": "NTES server is not responding."}
    except requests.exceptions.ConnectionError: return {"error": "CONNECTION_ERROR", "message": "Cannot connect to NTES server."}
    except Exception as e:
        err_str = str(e)
        if "timeout" in err_str.lower() or "connection" in err_str.lower(): return {"error": "NETWORK_ERROR", "message": f"Network issue: {err_str[:200]}"}
        return {"error": "API_ERROR", "message": err_str[:200]}

def format_train_search(data):
    if not data: return "❌ No trains found. Please try again."
    if isinstance(data, dict) and data.get('error'): return f"❌ {data['error']}"
    msg = f"## 🔍 TRAIN SEARCH RESULTS\n\n**Query:** {data.get('query', 'N/A')}\n\n"
    for t in data.get('trains', [])[:10]:
        msg += f"🚂 **{t.get('train_number', 'N/A')}** — {t.get('train_name', 'N/A')}\n"
        msg += f"   Route: {t.get('source', 'N/A')} → {t.get('destination', 'N/A')}\n\n"
    msg += f"_Last updated: {data.get('last_updated', datetime.now().strftime('%d %b %H:%M:%S'))}_"
    return msg

def get_train_schedule(train_number):
    if not NTES_AVAILABLE: return {"error": "NTES library not installed"}
    try:
        response = ntes_client.schedule(train_number)
        if not response: return None
        stations = []
        for s in safe_list(response, 'stations'):
            sta = s.get('STA', '')
            std = s.get('STD', '')
            if (sta and sta != 'N/A') or (std and std != 'N/A') or sta == 'Source' or std == 'Dest':
                stations.append({'code': safe_str(s.get('StationCode')), 'name': safe_str(s.get('StationName')),
                    'arrival': sta if sta else 'Source', 'departure': std if std else 'Dest', 'day': safe_str(s.get('Day'))})
        return {"train_number": train_number, "train_name": safe_str(response.get('TrainName')),
            "source": safe_str(response.get('Source')), "destination": safe_str(response.get('Destination')),
            "stations": stations, "last_updated": datetime.now().strftime('%d %b %H:%M:%S')}
    except requests.exceptions.ConnectTimeout: return {"error": "TIMEOUT", "message": "NTES server is not responding."}
    except requests.exceptions.ConnectionError: return {"error": "CONNECTION_ERROR", "message": "Cannot connect to NTES server."}
    except Exception as e:
        err_str = str(e)
        if "timeout" in err_str.lower() or "connection" in err_str.lower(): return {"error": "NETWORK_ERROR", "message": f"Network issue: {err_str[:200]}"}
        return {"error": "API_ERROR", "message": err_str[:200]}

def format_schedule_result(data, start=0, chunk=20):
    if not data: return "❌ Schedule not found.", None
    if isinstance(data, dict) and data.get('error'): return f"❌ {data['error']}", None
    if isinstance(data, dict) and 'stations' not in data: return "❌ Invalid schedule data.", None
    stations = data.get('stations', [])
    total = len(stations)
    end = min(start + chunk, total)
    if start >= total: start = max(0, total - chunk); end = total
    msg = f"**Train:** {data.get('train_number', 'N/A')} - {data.get('train_name', 'N/A')}\n"
    msg += f"**From:** {data.get('source', 'N/A')} → {data.get('destination', 'N/A')}\n"
    msg += f"**Showing {start+1} to {end} of {total}**\n\n"
    for i in range(start, end):
        s = stations[i]
        msg += f"{i+1}. **{s['code']}** - {s['name']}\n"
        msg += f"   🕐 Arr: {s['arrival']}  |  🕐 Dep: {s['departure']}"
        if s.get('day') and s.get('day') != 'N/A': msg += f"  |  Day: {s['day']}"
        msg += "\n\n"
    msg += f"_Last updated: {data.get('last_updated', datetime.now().strftime('%d %b %H:%M:%S'))}_"
    return msg, (start, end, total)

# =====================================================================
# Passport Photo Functions
# =====================================================================
def remove_background(image_data):
    key = str(st.secrets.get("REMOVE_BG_API_KEY", "")).strip()
    if not key: key = str(os.environ.get("REMOVE_BG_API_KEY", "")).strip()
    if not key and "remove_bg_key" in st.session_state: key = str(st.session_state.remove_bg_key).strip()
    if not key: return None
    try:
        r = requests.post("https://api.remove.bg/v1.0/removebg", files={"image_file": ("image.jpg", image_data, "image/jpeg")},
            data={"size": "auto", "format": "png"}, headers={"X-Api-Key": key}, timeout=30)
        return r.content if r.status_code == 200 else None
    except Exception: return None

def add_border(image_data):
    try:
        img = Image.open(io.BytesIO(image_data))
        if img.mode != "RGBA": img = img.convert("RGBA")
        w, h = img.size
        PW, PH = 413, 531
        BS = 8
        new_img = Image.new("RGB", (PW, PH), "white")
        target_w = PW - (BS * 2)
        target_h = PH - (BS * 2)
        scale = min(target_w / w, target_h / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        img_bg = Image.new("RGB", (new_w, new_h), "white")
        if img_resized.mode == "RGBA": img_bg.paste(img_resized, (0, 0), img_resized)
        else: img_bg.paste(img_resized, (0, 0))
        x = (target_w - new_w) // 2 + BS
        y = (target_h - new_h) // 2 + BS
        new_img.paste(img_bg, (x, y))
        draw = ImageDraw.Draw(new_img)
        draw.rectangle([(0, 0), (PW - 1, PH - 1)], outline="black", width=6)
        draw.rectangle([(6, 6), (PW - 7, PH - 7)], outline="black", width=2)
        output = io.BytesIO()
        new_img.save(output, format="PNG", quality=100)
        output.seek(0)
        return output.getvalue()
    except Exception: return None

def process_passport_image(data):
    no_bg = remove_background(data)
    if no_bg is None: return None
    final = add_border(no_bg)
    return final if final else no_bg

# =====================================================================
# Apply Theme
# =====================================================================
def apply_theme(theme, custom_bg=None, custom_text=None):
    if theme == 'Day':
        bg = "#f8fafc"
        card_bg = "rgba(255,255,255,0.85)"
        text_color = "#1e293b"
        text_secondary = "#64748b"
        border = "rgba(255,255,255,0.3)"
        input_bg = "rgba(255,255,255,0.7)"
        accent = "#2563eb"
        accent_hover = "#1d4ed8"
        success = "#16a34a"
        danger = "#dc2626"
        button_bg = "rgba(255,255,255,0.5)"
        button_text = "#1e293b"
        button_border = "rgba(255,255,255,0.5)"
        button_hover_bg = accent
        button_hover_text = "white"
        button_hover_border = accent
        number_color = "#2563eb"
        table_header_bg = "#1e293b"
        table_header_text = "#ffffff"
        table_alt_row = "rgba(248,250,252,0.6)"
        chart_bg = "rgba(0,0,0,0)"
    elif theme == 'Dark':
        bg = "#0f172a"
        card_bg = "rgba(30,41,59,0.85)"
        text_color = "#f1f5f9"
        text_secondary = "#94a3b8"
        border = "rgba(51,65,85,0.5)"
        input_bg = "rgba(15,23,42,0.7)"
        accent = "#60a5fa"
        accent_hover = "#93c5fd"
        success = "#4ade80"
        danger = "#f87171"
        button_bg = "rgba(51,65,85,0.5)"
        button_text = "#f1f5f9"
        button_border = "rgba(71,85,105,0.5)"
        button_hover_bg = accent
        button_hover_text = "white"
        button_hover_border = accent
        number_color = "#60a5fa"
        table_header_bg = "#2563eb"
        table_header_text = "#ffffff"
        table_alt_row = "rgba(30,41,59,0.6)"
        chart_bg = "rgba(0,0,0,0)"
    else:
        bg = custom_bg if custom_bg else "#ffffff"
        def is_dark_color(hex_color):
            try:
                hex_color = hex_color.lstrip('#')
                r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
                brightness = (r * 299 + g * 587 + b * 114) / 1000
                return brightness < 128
            except: return False
        is_dark = is_dark_color(bg)
        card_bg = bg if not is_dark else "rgba(30,41,59,0.85)"
        text_color = custom_text if custom_text else ("#f1f5f9" if is_dark else "#1e293b")
        text_secondary = text_color
        border = "#475569" if is_dark else "#e2e8f0"
        input_bg = bg
        accent = "#60a5fa" if is_dark else "#2563eb"
        accent_hover = "#93c5fd" if is_dark else "#1d4ed8"
        success = "#4ade80" if is_dark else "#16a34a"
        danger = "#f87171" if is_dark else "#dc2626"
        button_bg = bg
        button_text = text_color
        button_border = border
        button_hover_bg = accent
        button_hover_text = "white"
        button_hover_border = accent
        number_color = accent
        table_header_bg = "#2563eb" if is_dark else "#1e293b"
        table_header_text = "#ffffff"
        table_alt_row = "rgba(30,41,59,0.6)" if is_dark else "rgba(248,250,252,0.6)"
        chart_bg = "rgba(0,0,0,0)"

    css = f"""
    <style>
        /* Hide default elements */
        #MainMenu {{visibility: hidden !important;}}
        footer {{visibility: hidden !important;}}
        header {{visibility: hidden !important;}}
        .stDeployButton {{display: none !important;}}
        .viewerBadge_container__1QSob {{display: none !important;}}
        .stActionButton {{display: none !important;}}

        /* Transparent main container */
        .main .block-container {{
            padding-top: 0.5rem !important;
            padding-bottom: 0.5rem !important;
            max-width: 100% !important;
            min-height: 100vh !important;
            background: transparent !important;
        }}
        .stApp, .stAppViewContainer, .stMain, .stMainBlockContainer, .block-container {{
            background: transparent !important;
        }}

        /* Transparent sidebar with blur */
        [data-testid="stSidebar"] {{
            background: {card_bg} !important;
            backdrop-filter: blur(12px) !important;
            border-right: 1px solid {border} !important;
        }}

        /* Glass effect for dataframes, editors, cards, expanders */
        div[data-testid="stDataFrame"], div[data-testid="stDataEditor"],
        .stExpander, .stChatMessage, [data-testid="stMetric"], .action-box, .file-card,
        .stDataFrame, [data-testid="stDataFrame"], .stDataEditor, [data-testid="stDataEditor"],
        [data-testid="stDataFrameResizable"], [data-testid="stDataEditorResizable"],
        .stDataFrame table, .stDataEditor table {{
            background: {card_bg} !important;
            backdrop-filter: blur(8px) !important;
            border: 1px solid {border} !important;
        }}

        /* Transparent inputs */
        .stTextInput input, .stNumberInput input, .stDateInput input, .stTextArea textarea,
        .stSelectbox > div > div > div {{
            background: {input_bg} !important;
            backdrop-filter: blur(4px) !important;
            border: 1px solid {border} !important;
            border-radius: 8px !important;
        }}

        /* Glass buttons */
        .stButton > button {{
            background: {button_bg} !important;
            backdrop-filter: blur(4px) !important;
            color: {button_text} !important;
            border: 1px solid {button_border} !important;
            border-radius: 8px !important;
            font-weight: 500 !important;
            transition: all 0.15s ease !important;
        }}
        .stButton > button:hover {{
            background: {button_hover_bg} !important;
            color: {button_hover_text} !important;
            border-color: {button_hover_border} !important;
        }}
        .stButton > button[kind="primary"] {{
            background: {accent} !important;
            color: white !important;
            border-color: {accent} !important;
        }}
        .stButton > button[kind="primary"]:hover {{
            background: {accent_hover} !important;
            border-color: {accent_hover} !important;
        }}

        /* Header with glass */
        header[data-testid="stHeader"] {{
            background: {card_bg} !important;
            backdrop-filter: blur(12px) !important;
            border-bottom: 1px solid {border} !important;
        }}

        /* Text colors */
        h1, h2, h3, h4, h5, h6, .stMarkdown p, .stMarkdown div, .stMarkdown span,
        .stMarkdown h1, .stMarkdown h2, .stMarkdown h3,
        [data-testid="stMetricLabel"], [data-testid="stMetricValue"], .stCaption,
        label, .stTextInput label, .stSelectbox label, .stDateInput label,
        .stNumberInput label, .stTextArea label, .stRadio label, .stCheckbox label {{
            color: {text_color} !important;
        }}

        /* Table headers and cells */
        .stDataFrame th, .stDataEditor th {{
            background: {table_header_bg} !important;
            color: {table_header_text} !important;
            border-bottom: 2px solid {border} !important;
            font-weight: 600 !important;
        }}
        .stDataFrame tr:nth-child(even) td, .stDataEditor tr:nth-child(even) td {{
            background: {table_alt_row} !important;
        }}
        .stDataFrame td, .stDataEditor td {{
            text-align: center !important;
            border: 1px solid {border} !important;
            color: {text_color} !important;
        }}

        /* Scrollbar */
        ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
        ::-webkit-scrollbar-track {{ background: rgba(0,0,0,0.1); border-radius: 4px; }}
        ::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.3); border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: {accent}; }}

        /* Status pill */
        .status-pill {{ display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 0.78rem; font-weight: 500; }}
        .status-live {{ background: rgba(63, 185, 80, 0.15); color: {success}; border: 1px solid {success}; animation: live-pulse 2s ease-in-out infinite; }}
        @keyframes live-pulse {{ 0%,100%{{box-shadow:0 0 0 0 rgba(63,185,80,0.4);}} 50%{{box-shadow:0 0 0 8px rgba(63,185,80,0);}} }}

        /* Train count cards */
        .train-count-container {{ display: flex; flex-wrap: wrap; gap: 10px; justify-content: flex-start; margin: 10px 0; }}
        .train-count-card {{
            border: 1px solid {border}; border-radius: 10px; padding: 8px 16px;
            min-width: 80px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            transition: transform 0.15s ease, box-shadow 0.15s ease; background: {card_bg};
            backdrop-filter: blur(4px);
        }}
        .train-count-number {{ color: {number_color}; font-weight: 800; font-size: 1.8rem; }}
        .train-count-badge {{ display: inline-block; background: {accent}; color: white; font-size: 0.9rem; font-weight: 700; padding: 2px 10px; border-radius: 20px; }}
        .train-total-card {{
            border: 2px solid {success}; border-radius: 12px; padding: 8px 20px;
            min-width: 120px; text-align: center; background: {card_bg};
            backdrop-filter: blur(4px);
        }}
        .train-total-number {{ color: {success}; font-weight: 800; font-size: 1.5rem; }}
        .train-total-label {{ color: {text_secondary}; font-size: 0.75rem; }}

        /* Weather card */
        .weather-card {{
            background: {card_bg}; border: 1px solid {border}; border-radius: 16px;
            padding: 20px; margin: 10px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            backdrop-filter: blur(8px);
        }}

        /* Result box */
        .result-box {{
            background: {card_bg}; border: 2px solid {accent}; border-radius: 12px;
            padding: 20px; margin: 15px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            backdrop-filter: blur(8px);
        }}

        /* Footer */
        .pro-footer {{
            color: {text_secondary} !important;
            border-top: 1px solid {border} !important;
            text-align: center !important;
            padding: 18px 0 8px !important;
            margin-top: 28px !important;
            font-size: 0.85rem !important;
            background: transparent !important;
        }}

        /* Sheet link button */
        .sheet-link-btn {{
            display: inline-block !important; padding: 9px 16px !important;
            background: {button_bg} !important; color: {accent} !important;
            border: 1px solid {button_border} !important; border-radius: 8px !important;
            text-decoration: none !important; text-align: center !important; width: 100% !important;
            transition: all 0.15s !important; font-weight: 500 !important; font-size: 0.9rem !important;
            backdrop-filter: blur(4px);
        }}
        .sheet-link-btn:hover {{ background: {accent} !important; color: white !important; border-color: {accent} !important; }}

        /* Print only */
        .print-only {{ display: none; }}
        @media print {{
            .no-print, header, footer, .stSidebar, .stButton, .stExpander, .stTabs,
            .stSelectbox, .stTextInput, .stDateInput, .stNumberInput, .stTextArea, .stRadio,
            .stCheckbox, .stFileUploader, .stCaption, .stImage, .stVideo, .stAudio, .stPlotlyChart,
            .action-box, .pro-footer, .status-pill, .sheet-link-btn, .stChatMessage, .stChatInput,
            .train-count-container, .weather-card, .result-box, .print-area {{ display: none !important; }}
            .print-only {{ display: block !important; }}
            .print-only h2 {{ color: #000 !important; font-size: 18pt !important; margin-top: 0 !important; }}
            .print-only p {{ color: #333 !important; }}
            .print-only table {{
                width: 100% !important; border-collapse: collapse !important; font-size: 8pt !important;
                page-break-inside: auto !important;
            }}
            .print-only tr {{ page-break-inside: avoid !important; }}
            .print-only thead {{ display: table-header-group !important; }}
            .print-only th {{
                background: #333 !important; color: white !important; padding: 5px 6px !important;
                border: 1px solid #333 !important; font-size: 8pt !important; text-align: center !important;
            }}
            .print-only td {{
                border: 1px solid #999 !important; padding: 3px 5px !important;
                font-size: 8pt !important; color: #000 !important; word-wrap: break-word !important;
            }}
            .print-only tr:nth-child(even) {{ background: #f5f5f5 !important; }}
            body {{ background: white !important; }}
        }}

        /* Sidebar toggle button */
        .sidebar-toggle-btn {{
            position: fixed !important;
            top: 12px !important;
            left: 12px !important;
            z-index: 999999 !important;
            width: 42px !important;
            height: 42px !important;
            border-radius: 50% !important;
            background: linear-gradient(135deg, #FF9933, #FF6B35) !important;
            border: none !important;
            color: white !important;
            font-size: 20px !important;
            cursor: pointer !important;
            box-shadow: 0 4px 15px rgba(255, 107, 53, 0.4) !important;
            transition: all 0.3s ease !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }}
        .sidebar-toggle-btn:hover {{
            transform: scale(1.1) rotate(90deg) !important;
            box-shadow: 0 6px 25px rgba(255, 107, 53, 0.6) !important;
        }}
        .sidebar-toggle-btn.collapsed {{
            background: linear-gradient(135deg, #138808, #0d6e05) !important;
        }}

        /* Metric card */
        .metric-card {{
            background: {card_bg}; border: 1px solid {border}; border-radius: 12px; padding: 16px; text-align: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06); transition: transform 0.2s ease; backdrop-filter: blur(8px);
        }}
        .metric-card:hover {{ transform: translateY(-3px); box-shadow: 0 4px 16px rgba(0,0,0,0.1); }}
        .metric-card h3 {{ margin: 0; font-size: 2.2rem; color: {accent}; font-weight: 800; }}
        .metric-card p {{ margin: 4px 0 0 0; color: {text_secondary}; font-size: 0.9rem; font-weight: 500; }}

        /* File card */
        .file-card {{
            background: {card_bg}; border: 1px solid {border}; border-radius: 12px; padding: 14px; margin: 10px 0;
            backdrop-filter: blur(8px);
        }}
        .file-card-title {{ color: {text_color}; font-weight: 600; font-size: 0.95rem; margin-bottom: 2px; }}
        .file-card-meta {{ color: {text_secondary}; font-size: 0.8rem; margin-bottom: 10px; }}

        /* Plotly chart background */
        .js-plotly-plot .plotly text {{ fill: {text_color} !important; }}
        .js-plotly-plot .plotly .gtitle {{ fill: {text_color} !important; }}
        [data-testid="stMain"] .block-container {{ z-index: 50 !important; position: relative !important; }}

        /* Sidebar collapse */
        [data-testid="stSidebar"] {{
            display: flex !important; opacity: 1 !important; transform: none !important;
            min-width: 320px !important; transition: margin-left 0.45s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.4s ease !important;
            margin-left: 0 !important; will-change: margin-left, opacity !important; overflow: hidden !important;
        }}
        body.sidebar-collapsed [data-testid="stSidebar"] {{
            margin-left: -340px !important; opacity: 0 !important; pointer-events: none !important;
        }}
        body.sidebar-collapsed [data-testid="stMain"] {{
            margin-left: 0 !important; max-width: 100% !important;
            transition: margin-left 0.45s cubic-bezier(0.4, 0, 0.2, 1) !important;
        }}
        [data-testid="stSidebarCollapseButton"] {{ display: none !important; }}
        [data-testid="collapsedControl"] {{ display: none !important; }}
        button[kind="header"] {{ display: none !important; }}
        body.sidebar-collapsed [data-testid="stMain"] {{
            margin-left: 0 !important; max-width: 100% !important;
        }}

        /* Marquee */
        .eqms-marquee-box {{
            background: linear-gradient(90deg, #FF9933, #FFFFFF, #138808);
            padding: 10px 0;
            border-radius: 8px;
            margin-bottom: 12px;
            overflow: hidden;
            white-space: nowrap;
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
            backdrop-filter: blur(2px);
        }}
        .eqms-marquee-box .scroll-text {{
            display: inline-block;
            padding-left: 100%;
            animation: marquee-scroll 25s linear infinite;
            color: #000000 !important;
            font-weight: 700;
            letter-spacing: 0.5px;
            font-size: 15px;
            font-family: 'Segoe UI', Arial, sans-serif;
        }}
        @keyframes marquee-scroll {{
            0% {{ transform: translateX(0); }}
            100% {{ transform: translateX(-100%); }}
        }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# =====================================================================
# Generate PDF / Table Image / WhatsApp Message
# =====================================================================
def generate_pdf(df, title, full=True):
    if df.empty:
        pdf = FPDF('L', 'mm', 'A4')
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, f"AI EQMS Hub Pro - {title}", ln=True, align='C')
        pdf.set_font("Arial", '', 12)
        pdf.cell(0, 10, f"Generated: {format_datetime()} IST", ln=True, align='C')
        pdf.cell(0, 10, "No data available for this sheet.", ln=True, align='C')
        output = pdf.output(dest='S')
        if isinstance(output, bytearray): return bytes(output)
        elif isinstance(output, str): return output.encode('latin-1')
        else: return output
    pdf = FPDF('L', 'mm', 'A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, f"AI EQMS Hub Pro - {title}", ln=True, align='C')
    pdf.set_font("Arial", '', 8)
    pdf.cell(0, 6, f"Generated: {format_datetime()} IST | Rows: {len(df)}", ln=True, align='C')
    pdf.ln(3)
    cols = list(df.columns)
    if '_sheet_row' in cols: cols.remove('_sheet_row')
    if len(cols) > 15: cols = cols[:15]
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
    if isinstance(output, bytearray): return bytes(output)
    elif isinstance(output, str): return output.encode('latin-1')
    else: return output

def create_table_image(df, title):
    if df.empty: return None
    cols = list(df.columns)
    if '_sheet_row' in cols: cols.remove('_sheet_row')
    if len(cols) > 10: cols = cols[:10]
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
    lines = []
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📊 *{sheet_name} SHEET REPORT*")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"🕐 Generated: {now_str}")
    lines.append("")
    lines.append("📋 *OVERVIEW:*")
    if selected_count > 0:
        lines.append(f"   • Selected Records: *{selected_count}*")
        lines.append(f"   • Total Records in Sheet: *{total_rows}*")
        if pnrs:
            pnr_list = ", ".join(str(p) for p in pnrs[:8])
            if len(pnrs) > 8: pnr_list += f" (+{len(pnrs)-8} more)"
            lines.append(f"   • Selected PNRs: {pnr_list}")
    else: lines.append(f"   • Total Records: *{total_rows}*")
    lines.append("")
    train_col = None
    for c in df.columns:
        if 'T/N' in c.upper() or 'T_N' in c.upper() or 'TRAIN' in c.upper():
            train_col = c; break
    if train_col and not df.empty:
        train_counts = df[train_col].value_counts().to_dict()
        if train_counts:
            lines.append("🚆 *TRAIN-WISE BREAKDOWN:*")
            sorted_trains = sorted(train_counts.items(), key=lambda x: x[1], reverse=True)
            for i, (train, count) in enumerate(sorted_trains[:15], 1):
                train_mask = df[train_col].astype(str) == str(train)
                train_df = df[train_mask]
                berth_col = next((c for c in df.columns if 'BERTH' in c.upper()), None)
                berth_count = 0
                if berth_col:
                    try: berth_count = int(pd.to_numeric(train_df[berth_col], errors='coerce').sum())
                    except: pass
                berth_str = f" ({berth_count} berths)" if berth_count > 0 else ""
                lines.append(f"   {i}. Train *{train}* → {count} request{berth_str}")
            if len(sorted_trains) > 15: lines.append(f"   ... and {len(sorted_trains)-15} more trains")
            lines.append("")
    class_col = next((c for c in df.columns if 'CLASS' in c.upper()), None)
    if class_col and not df.empty:
        class_counts = df[class_col].value_counts().to_dict()
        if class_counts:
            lines.append("🎫 *CLASS-WISE BREAKDOWN:*")
            sorted_classes = sorted(class_counts.items(), key=lambda x: x[1], reverse=True)
            for cls, count in sorted_classes:
                lines.append(f"   • {cls}: *{count}* request(s)")
            lines.append("")
    vip_col = next((c for c in df.columns if 'VIP' in c.upper() or 'MP/MLA' in c.upper()), None)
    if vip_col and not df.empty:
        vip_counts = df[vip_col].value_counts().to_dict()
        vip_counts = {k: v for k, v in vip_counts.items() if str(k).strip()}
        if vip_counts:
            lines.append("⭐ *VIP / PRIORITY BREAKDOWN:*")
            for status, count in list(vip_counts.items())[:8]:
                lines.append(f"   • {status}: *{count}* request(s)")
            lines.append("")
    doj_col = next((c for c in df.columns if 'DOJ' in c.upper()), None)
    if doj_col and not df.empty:
        try:
            doj_dates = pd.to_datetime(df[doj_col], format='%d-%m-%Y', errors='coerce')
            if doj_dates.isna().all(): doj_dates = pd.to_datetime(df[doj_col], errors='coerce')
            valid_dates = doj_dates.dropna()
            if len(valid_dates) > 0:
                min_doj = valid_dates.min().strftime('%d-%m-%Y')
                max_doj = valid_dates.max().strftime('%d-%m-%Y')
                today_str = now_ist().strftime('%d-%m-%Y')
                lines.append("📅 *DATE INFORMATION:*")
                lines.append(f"   • Date Range: {min_doj} to {max_doj}")
                lines.append(f"   • Today's Date: {today_str}")
                upcoming = sum(1 for d in valid_dates if d >= pd.Timestamp(now_ist().replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)))
                expired = len(valid_dates) - upcoming
                lines.append(f"   • Upcoming Journeys: *{upcoming}*")
                if expired > 0: lines.append(f"   • Past Journeys: {expired}")
                lines.append("")
        except: pass
    from_col = next((c for c in df.columns if c.upper() == 'FROM'), None)
    to_col = next((c for c in df.columns if c.upper() == 'TO'), None)
    if from_col and to_col and not df.empty:
        try:
            route_counts = df.groupby([from_col, to_col]).size().to_dict()
            if route_counts:
                lines.append("🛤️ *TOP ROUTES:*")
                sorted_routes = sorted(route_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                for i, ((frm, to), count) in enumerate(sorted_routes, 1):
                    lines.append(f"   {i}. {frm} → {to}: *{count}* request(s)")
                lines.append("")
        except: pass
    berth_col = next((c for c in df.columns if 'BERTH' in c.upper()), None)
    if berth_col and not df.empty:
        try:
            total_berths = pd.to_numeric(df[berth_col], errors='coerce').sum()
            if total_berths > 0:
                lines.append("🛏️ *BERTH SUMMARY:*")
                lines.append(f"   • Total Berths Required: *{int(total_berths)}*")
                avg_berths = total_berths / len(df) if len(df) > 0 else 0
                lines.append(f"   • Average per Record: {avg_berths:.1f}")
                lines.append("")
        except: pass
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"🔗 *Sheet Link:*")
    lines.append(f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📱 Sent via AI EQMS Hub Pro")
    return "\n".join(lines)

def get_pnr_status_url(pnr):
    if not pnr or len(str(pnr)) != 10: return None
    return f"https://www.confirmtkt.com/pnr-status/{pnr}"

# =====================================================================
# MAIN FUNCTION
# =====================================================================
def main():
    # Splash Screen (shows once per page load)
    components.html("""
    <script>
    (function(){
        var P = window.parent;
        var doc = P.document;
        if (doc.getElementById('eqms-splash')) return;

        var style = doc.createElement('style');
        style.textContent = `
            #eqms-splash {
                position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
                background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%);
                z-index: 99999999; display: flex; flex-direction: column;
                align-items: center; justify-content: center;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            .splash-train {
                font-size: 7rem; filter: drop-shadow(0 0 40px rgba(255,153,51,0.7));
                animation: splash-train-bob 1.5s ease-in-out infinite;
            }
            @keyframes splash-train-bob {
                0%, 100% { transform: translateY(0) scale(1); }
                50% { transform: translateY(-15px) scale(1.1); }
            }
            .splash-title {
                color: #fff; font-size: 2.2rem; font-weight: 800; margin-top: 24px;
                letter-spacing: 3px; text-shadow: 0 4px 20px rgba(0,0,0,0.6);
            }
            .splash-sub {
                color: #94a3b8; font-size: 0.95rem; margin-top: 8px;
                letter-spacing: 5px; text-transform: uppercase;
            }
            .splash-bar-wrap {
                width: 220px; height: 4px; background: #334155;
                border-radius: 2px; margin-top: 32px; overflow: hidden;
            }
            .splash-bar {
                width: 0%; height: 100%;
                background: linear-gradient(90deg, #FF9933, #FFFFFF, #138808);
                animation: splash-load 2s ease-in-out forwards;
            }
            @keyframes splash-load { to { width: 100%; } }
            .splash-fade-out {
                animation: splash-fade 0.6s ease-in-out 2.4s forwards;
            }
            @keyframes splash-fade {
                to { opacity: 0; visibility: hidden; pointer-events: none; }
            }
        `;
        doc.head.appendChild(style);

        var div = doc.createElement('div');
        div.id = 'eqms-splash';
        div.className = 'splash-fade-out';
        div.innerHTML = '<div class="splash-train">🚂</div><div class="splash-title">AI EQMS Hub Pro</div><div class="splash-sub">Indian Railways</div><div class="splash-bar-wrap"><div class="splash-bar"></div></div>';
        doc.body.appendChild(div);

        setTimeout(function(){
            var el = doc.getElementById('eqms-splash');
            if(el) {
                el.style.transition = 'opacity 0.5s ease';
                el.style.opacity = '0';
                setTimeout(function(){ if(el) el.remove(); }, 600);
            }
        }, 2800);
    })();
    </script>
    """, height=0)

    # Solar System Background with Train Engine and Coaches (full screen)
    bg_html = """
    <style>
    .eqms-bg {
        position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
        z-index: -1; pointer-events: none; overflow: hidden;
        background: radial-gradient(ellipse at center, #0a0a1a 0%, #000000 70%);
    }
    .stars {
        position: absolute; top: 0; left: 0; width: 2px; height: 2px;
        background: transparent;
        box-shadow:
            80px 50px #fff, 150px 80px #fff, 220px 30px #fff, 300px 120px #fff,
            400px 60px #fff, 500px 150px #fff, 600px 40px #fff, 700px 100px #fff,
            80px 150px #fff, 180px 200px #fff, 280px 180px #fff, 380px 220px #fff,
            480px 160px #fff, 580px 240px #fff, 680px 190px #fff, 750px 280px #fff,
            50px 280px #fff, 120px 320px #fff, 200px 300px #fff, 320px 350px #fff,
            420px 310px #fff, 520px 360px #fff, 620px 330px #fff, 720px 370px #fff,
            90px 400px #fff, 170px 450px #fff, 250px 420px #fff, 350px 480px #fff,
            450px 440px #fff, 550px 490px #fff, 650px 460px #fff, 730px 500px #fff,
            30px 520px #fff, 110px 560px #fff, 190px 540px #fff, 290px 580px #fff,
            390px 550px #fff, 490px 590px #fff, 590px 570px #fff, 690px 600px #fff,
            70px 650px #fff, 160px 680px #fff, 260px 660px #fff, 360px 700px #fff,
            460px 670px #fff, 560px 710px #fff, 660px 690px #fff, 740px 720px #fff,
            100px 750px #fff, 200px 780px #fff, 300px 760px #fff, 400px 790px #fff,
            500px 770px #fff, 600px 800px #fff, 700px 740px #fff, 770px 790px #fff,
            850px 120px #fff, 920px 200px #fff, 1050px 90px #fff, 1150px 300px #fff,
            1250px 180px #fff, 1350px 400px #fff, 1450px 250px #fff, 1550px 500px #fff,
            80px 850px #fff, 180px 920px #fff, 280px 880px #fff, 380px 950px #fff,
            480px 910px #fff, 580px 970px #fff, 680px 930px #fff, 780px 990px #fff;
        animation: twinkle-stars 3s ease-in-out infinite alternate;
    }
    @keyframes twinkle-stars {
        0% { opacity: 0.3; }
        100% { opacity: 1; }
    }
    .sun-wrap {
        position: absolute; top: 50%; left: 50%;
        transform: translate(-50%, -50%);
        width: 100px; height: 100px;
    }
    .sun-core {
        position: absolute; top: 50%; left: 50%;
        transform: translate(-50%, -50%);
        width: 60px; height: 60px;
        background: radial-gradient(circle, #FFD700 0%, #FF8C00 50%, #FF4500 100%);
        border-radius: 50%;
        box-shadow: 0 0 40px 15px rgba(255,140,0,0.6), 0 0 80px 30px rgba(255,69,0,0.3);
        animation: sun-glow 3s ease-in-out infinite alternate;
    }
    @keyframes sun-glow {
        0% { transform: translate(-50%, -50%) scale(1); }
        100% { transform: translate(-50%, -50%) scale(1.15); }
    }
    .sun-rays {
        position: absolute; top: 50%; left: 50%;
        transform: translate(-50%, -50%);
        width: 100px; height: 100px;
        animation: ray-spin 20s linear infinite;
    }
    .sun-rays::before, .sun-rays::after {
        content: ''; position: absolute; top: 50%; left: 50%;
        width: 50px; height: 2px; background: rgba(255,200,0,0.6);
        transform-origin: 0 50%;
    }
    .sun-rays::before { transform: rotate(0deg); }
    .sun-rays::after { transform: rotate(90deg); }
    @keyframes ray-spin {
        from { transform: translate(-50%, -50%) rotate(0deg); }
        to { transform: translate(-50%, -50%) rotate(360deg); }
    }
    .ring-1 {
        position: absolute; top: 50%; left: 50%;
        transform: translate(-50%, -50%);
        width: 260px; height: 260px;
        border: 1px dashed rgba(255,153,51,0.25);
        border-radius: 50%;
        animation: ring-pulse-1 4s ease-in-out infinite;
    }
    .ring-2 {
        position: absolute; top: 50%; left: 50%;
        transform: translate(-50%, -50%);
        width: 400px; height: 400px;
        border: 1px dashed rgba(19,136,8,0.25);
        border-radius: 50%;
        animation: ring-pulse-2 4s ease-in-out infinite;
        animation-delay: 2s;
    }
    @keyframes ring-pulse-1 {
        0%, 100% { border-color: rgba(255,153,51,0.15); }
        50% { border-color: rgba(255,153,51,0.45); }
    }
    @keyframes ring-pulse-2 {
        0%, 100% { border-color: rgba(19,136,8,0.15); }
        50% { border-color: rgba(19,136,8,0.45); }
    }
    /* Orbit 1: Engine + 3 coaches */
    .orbit-1 {
        position: absolute; top: 50%; left: 50%;
        width: 260px; height: 260px;
        transform: translate(-50%, -50%);
        animation: spin-1 22s linear infinite;
    }
    @keyframes spin-1 {
        from { transform: translate(-50%, -50%) rotate(0deg); }
        to { transform: translate(-50%, -50%) rotate(360deg); }
    }
    .t1 { position: absolute; top: -20px; left: 50%; transform: translateX(-50%); font-size: 28px; filter: drop-shadow(0 0 10px rgba(255,153,51,0.9)); animation: bob-1 0.9s ease-in-out infinite alternate; }
    .t1-b1 { transform: translateX(-50%) translateX(-36px); animation-delay: 0.04s; }
    .t1-b2 { transform: translateX(-50%) translateX(-68px); animation-delay: 0.08s; }
    .t1-b3 { transform: translateX(-50%) translateX(-96px); animation-delay: 0.12s; }
    @keyframes bob-1 {
        from { transform: translateX(-50%) translateY(0) scale(1); }
        to { transform: translateX(-50%) translateY(-5px) scale(1.07); }
    }
    /* Orbit 2: Engine + 5 coaches */
    .orbit-2 {
        position: absolute; top: 50%; left: 50%;
        width: 400px; height: 400px;
        transform: translate(-50%, -50%);
        animation: spin-2 32s linear infinite reverse;
    }
    @keyframes spin-2 {
        from { transform: translate(-50%, -50%) rotate(0deg); }
        to { transform: translate(-50%, -50%) rotate(360deg); }
    }
    .t2 { position: absolute; top: -20px; left: 50%; transform: translateX(-50%); font-size: 28px; filter: drop-shadow(0 0 10px rgba(19,136,8,0.9)); animation: bob-2 1s ease-in-out infinite alternate; }
    .t2-b1 { transform: translateX(-50%) translateX(-34px); animation-delay: 0.04s; }
    .t2-b2 { transform: translateX(-50%) translateX(-64px); animation-delay: 0.08s; }
    .t2-b3 { transform: translateX(-50%) translateX(-90px); animation-delay: 0.12s; }
    .t2-b4 { transform: translateX(-50%) translateX(-116px); animation-delay: 0.16s; }
    .t2-b5 { transform: translateX(-50%) translateX(-142px); animation-delay: 0.20s; }
    @keyframes bob-2 {
        from { transform: translateX(-50%) translateY(0) scale(1); }
        to { transform: translateX(-50%) translateY(-4px) scale(1.05); }
    }
    /* Planets */
    .planet-1 {
        position: absolute; top: 12%; right: 18%;
        width: 16px; height: 16px;
        background: radial-gradient(circle, #ff6b6b, #c92a2a);
        border-radius: 50%;
        box-shadow: 0 0 15px rgba(255,107,107,0.4);
        animation: float-1 7s ease-in-out infinite;
    }
    .planet-2 {
        position: absolute; bottom: 22%; left: 10%;
        width: 12px; height: 12px;
        background: radial-gradient(circle, #4ecdc4, #087f5b);
        border-radius: 50%;
        box-shadow: 0 0 12px rgba(78,205,196,0.4);
        animation: float-2 7s ease-in-out infinite;
        animation-delay: -3s;
    }
    .planet-3 {
        position: absolute; top: 68%; right: 12%;
        width: 20px; height: 20px;
        background: radial-gradient(circle, #ffe66d, #f59f00);
        border-radius: 50%;
        box-shadow: 0 0 20px rgba(255,230,109,0.4);
        animation: float-3 7s ease-in-out infinite;
        animation-delay: -6s;
    }
    @keyframes float-1 { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-12px); } }
    @keyframes float-2 { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-10px); } }
    @keyframes float-3 { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-14px); } }
    .shooting {
        position: absolute; top: 10%; left: 10%;
        width: 100px; height: 2px;
        background: linear-gradient(90deg, rgba(255,255,255,1), transparent);
        transform: rotate(-45deg);
        opacity: 0;
        animation: shoot 5s linear infinite;
    }
    @keyframes shoot {
        0% { transform: translateX(0) translateY(0) rotate(-45deg); opacity: 1; }
        100% { transform: translateX(500px) translateY(500px) rotate(-45deg); opacity: 0; }
    }
    </style>
    <div class="eqms-bg">
        <div class="stars"></div>
        <div class="sun-wrap">
            <div class="sun-rays"></div>
            <div class="sun-core"></div>
        </div>
        <div class="ring-1"></div>
        <div class="ring-2"></div>
        <div class="orbit-1">
            <div class="t1">🚂</div>
            <div class="t1 t1-b1">🚃</div>
            <div class="t1 t1-b2">🚃</div>
            <div class="t1 t1-b3">🚃</div>
        </div>
        <div class="orbit-2">
            <div class="t2">🚂</div>
            <div class="t2 t2-b1">🚃</div>
            <div class="t2 t2-b2">🚃</div>
            <div class="t2 t2-b3">🚃</div>
            <div class="t2 t2-b4">🚃</div>
            <div class="t2 t2-b5">🚃</div>
        </div>
        <div class="planet-1"></div>
        <div class="planet-2"></div>
        <div class="planet-3"></div>
        <div class="shooting"></div>
    </div>
    """
    st.markdown(bg_html, unsafe_allow_html=True)

    # Sidebar Toggle + Back-to-Top Button
    components.html("""
    <script>
    (function() {
        try {
            var P = window.parent;
            var doc = P.document;
            if (!P.__eqmsProInit) {
                P.__eqmsProInit = true;
                // Ensure sidebar starts open
                var body = doc.body;
                body.classList.remove('sidebar-collapsed');

                doc.addEventListener('keydown', function(e) {
                    var t = (e.target.tagName || '').toLowerCase();
                    if (t === 'input' || t === 'textarea' || t === 'select' || e.target.isContentEditable) return;
                    if (e.key === 'd' || e.key === 'D') {
                        var u = new URL(P.location.href);
                        var cur = u.searchParams.get('__theme') || 'Day';
                        u.searchParams.set('__theme', cur === 'Dark' ? 'Day' : 'Dark');
                        P.location.href = u.toString();
                    }
                });

                if (!doc.getElementById('eqms-sidebar-toggle')) {
                    var toggleBtn = doc.createElement('button');
                    toggleBtn.id = 'eqms-sidebar-toggle';
                    toggleBtn.title = 'Toggle Sidebar (Click to Open/Close)';
                    toggleBtn.innerHTML = '☰';
                    toggleBtn.style.cssText = 'position:fixed;top:12px;left:12px;z-index:9999999;width:44px;height:44px;border-radius:50%;border:none;background:linear-gradient(135deg,#FF9933,#FF6B35);color:white;font-size:20px;cursor:pointer;box-shadow:0 4px 15px rgba(255,107,53,0.5);transition:all 0.3s ease;display:flex;align-items:center;justify-content:center;font-weight:bold;';

                    toggleBtn.onmouseenter = function(){ 
                        toggleBtn.style.transform = 'scale(1.15) rotate(90deg)'; 
                        toggleBtn.style.boxShadow = '0 6px 25px rgba(255,107,53,0.7)'; 
                    };
                    toggleBtn.onmouseleave = function(){ 
                        toggleBtn.style.transform = 'scale(1) rotate(0deg)'; 
                        toggleBtn.style.boxShadow = '0 4px 15px rgba(255,107,53,0.5)'; 
                    };

                    toggleBtn.onclick = function() {
                        var body = doc.body;
                        var isCollapsed = body.classList.contains('sidebar-collapsed');
                        if (isCollapsed) {
                            body.classList.remove('sidebar-collapsed');
                            toggleBtn.innerHTML = '✕';
                            toggleBtn.style.background = 'linear-gradient(135deg,#FF9933,#FF6B35)';
                            var sb = doc.querySelector('[data-testid="stSidebar"]');
                            if (sb) { sb.style.marginLeft = '0px'; sb.style.opacity = '1'; sb.style.pointerEvents = 'auto'; }
                            try { localStorage.setItem('eqms_sidebar', 'open'); } catch(e) {}
                        } else {
                            body.classList.add('sidebar-collapsed');
                            toggleBtn.innerHTML = '☰';
                            toggleBtn.style.background = 'linear-gradient(135deg,#138808,#0d6e05)';
                            var sb = doc.querySelector('[data-testid="stSidebar"]');
                            if (sb) { sb.style.marginLeft = '-340px'; sb.style.opacity = '0'; sb.style.pointerEvents = 'none'; }
                            try { localStorage.setItem('eqms_sidebar', 'closed'); } catch(e) {}
                        }
                    };
                    try {
                        var saved = localStorage.getItem('eqms_sidebar');
                        if (saved === 'closed') {
                            doc.body.classList.add('sidebar-collapsed');
                            toggleBtn.innerHTML = '☰';
                            toggleBtn.style.background = 'linear-gradient(135deg,#138808,#0d6e05)';
                        }
                    } catch(e) {}
                    setInterval(function(){
                        var sb = doc.querySelector('[data-testid="stSidebar"]');
                        var isCollapsed = doc.body.classList.contains('sidebar-collapsed');
                        if (sb) {
                            if (isCollapsed) { sb.style.marginLeft = '-340px'; sb.style.opacity = '0'; sb.style.pointerEvents = 'none'; }
                            else { sb.style.marginLeft = '0px'; sb.style.opacity = '1'; sb.style.pointerEvents = 'auto'; }
                        }
                    }, 2000);
                    doc.body.appendChild(toggleBtn);
                }

                if (!doc.getElementById('eqms-top-btn')) {
                    var b = doc.createElement('button');
                    b.id = 'eqms-top-btn';
                    b.title = 'Back to top';
                    b.innerHTML = '⬆';
                    b.style.cssText = 'position:fixed;bottom:26px;right:26px;z-index:999999;width:44px;height:44px;border-radius:50%;border:none;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;font-size:18px;cursor:pointer;opacity:0.85;box-shadow:0 4px 14px rgba(0,0,0,0.25);transition:opacity .2s, transform .2s;';
                    b.onmouseenter = function(){ b.style.opacity = '1'; b.style.transform = 'scale(1.08)'; };
                    b.onmouseleave = function(){ b.style.opacity = '0.85'; b.style.transform = 'scale(1)'; };
                    b.onclick = function(){ window.scrollTo({top:0, behavior:'smooth'}); };
                    doc.body.appendChild(b);
                }
            }
        } catch(e) { console.error('EQMS Toggle Error:', e); }
    })();
    </script>
    """, height=0)

    # Theme setup
    theme_options = ['Day', 'Dark', 'Custom', 'Auto (System)']
    qp_theme = st.query_params.get('__theme')
    if qp_theme in theme_options and st.session_state.theme != qp_theme:
        st.session_state.theme = qp_theme
    qp_bg = st.query_params.get('__bg')
    qp_tx = st.query_params.get('__tx')
    if qp_bg and st.session_state.custom_bg != qp_bg: st.session_state.custom_bg = qp_bg
    if qp_tx and st.session_state.custom_text != qp_tx: st.session_state.custom_text = qp_tx
    view_options = ["📋 Data Table", "📊 Dashboard", "💬 Chat", "🚂 Railway", "🌤️ Weather"]
    qp_view = st.query_params.get('__view')
    if qp_view in view_options and st.session_state.view_mode != qp_view: st.session_state.view_mode = qp_view

    theme_choice = st.sidebar.selectbox("🎨 Theme", theme_options,
        index=theme_options.index(st.session_state.theme) if st.session_state.theme in theme_options else 0,
        key="theme_select")
    if theme_choice != st.session_state.theme:
        st.session_state.theme = theme_choice
        st.query_params['__theme'] = theme_choice
        st.rerun()

    effective_theme = theme_choice
    if theme_choice == 'Auto (System)':
        h = now_ist().hour
        effective_theme = 'Day' if 6 <= h < 19 else 'Dark'

    if effective_theme == 'Custom':
        custom_bg = st.sidebar.color_picker("Background Color", value=st.session_state.custom_bg, key="custom_bg_picker")
        custom_text = st.sidebar.color_picker("Text Color", value=st.session_state.custom_text, key="custom_text_picker")
        if custom_bg != st.session_state.custom_bg or custom_text != st.session_state.custom_text:
            st.session_state.custom_bg = custom_bg
            st.session_state.custom_text = custom_text
            st.query_params['__bg'] = custom_bg
            st.query_params['__tx'] = custom_text
            st.rerun()
    else:
        custom_bg = None
        custom_text = None

    apply_theme(effective_theme, custom_bg, custom_text)

    # =====================================================================
    # SIDEBAR
    # =====================================================================
    with st.sidebar:
        st.markdown("""
        <style>
        @keyframes welcome-glow {
            0%, 100% { box-shadow: 0 4px 20px rgba(255,153,51,0.3); }
            33% { box-shadow: 0 4px 20px rgba(255,255,255,0.3); }
            66% { box-shadow: 0 4px 20px rgba(19,136,8,0.3); }
        }
        .welcome-card, .welcome-card * {
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
            text-shadow: none !important;
            opacity: 1 !important;
        }
        </style>
        <div class="welcome-card" style="background: linear-gradient(135deg, #FF9933 0%, #FF9933 33%, #FFFFFF 33%, #FFFFFF 66%, #138808 66%, #138808 100%); padding: 3px; border-radius: 14px; margin-bottom: 14px; animation: welcome-glow 4s ease-in-out infinite;">
            <div style="background: #ffffff; border-radius: 12px; padding: 14px 16px; text-align: center;">
                <p style="margin: 0 0 10px 0; font-size: 1.35em; font-weight: 800; letter-spacing: 0.5px; line-height: 1.4;">🙏 Namaste</p>
                <div style="display: flex; align-items: center; justify-content: flex-start; gap: 10px; padding: 7px 12px; border-radius: 8px; margin: 5px 0; background: linear-gradient(90deg, rgba(255,153,51,0.18), transparent);">
                    <span style="font-size: 1.3rem; font-weight: 900; color: #FF9933; -webkit-text-fill-color: #FF9933;">●</span>
                    <span style="font-size: 0.95em; font-weight: 600; line-height: 1.4;">Aapka Swagat Hai</span>
                </div>
                <div style="display: flex; align-items: center; justify-content: flex-start; gap: 10px; padding: 7px 12px; border-radius: 8px; margin: 5px 0; background: linear-gradient(90deg, rgba(200,200,200,0.12), transparent);">
                    <span style="font-size: 1.3rem; font-weight: 900; color: #BBBBBB; -webkit-text-fill-color: #BBBBBB;">●</span>
                    <span style="font-size: 0.95em; font-weight: 600; line-height: 1.4;">Ham Bharat ke Log</span>
                </div>
                <div style="display: flex; align-items: center; justify-content: flex-start; gap: 10px; padding: 7px 12px; border-radius: 8px; margin: 5px 0; background: linear-gradient(90deg, rgba(19,136,8,0.18), transparent);">
                    <span style="font-size: 1.3rem; font-weight: 900; color: #138808; -webkit-text-fill-color: #138808;">●</span>
                    <span style="font-size: 0.95em; font-weight: 600; line-height: 1.4;">🇮🇳 Jai Hind</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        now = now_ist()
        st.caption(f"📅 {format_date()}  •  🕐 {format_time()} IST")

        with st.expander("🌤️ Quick Weather", expanded=False):
            city = st.text_input("🏙️ City", value=st.session_state.weather_city, key="sidebar_weather_city")
            if city != st.session_state.weather_city: st.session_state.weather_city = city
            if st.button("🌤️ Get Weather", key="sidebar_weather_btn", use_container_width=True):
                if city:
                    with st.spinner("Fetching..."):
                        data = get_weather(city)
                        if data and 'error' not in data:
                            st.session_state.weather_data = data
                            st.rerun()
                        else: st.error(data.get('error', 'Error'))
            if st.session_state.weather_data and 'error' not in st.session_state.weather_data:
                data = st.session_state.weather_data
                st.markdown(f"""
                <div style="text-align:center; padding: 5px 0;">
                    <div style="font-size:1.5rem; font-weight:700;">{data['temp']}°C</div>
                    <div>{data['weather'].title()}</div>
                    <div style="font-size:0.8rem; color:#64748b;">💧 {data['humidity']}%  🌬️ {data['wind_speed']} m/s</div>
                </div>
                """, unsafe_allow_html=True)

        with st.expander("🔄 Sync & Status", expanded=False):
            if st.button("🔄 Sync Now", use_container_width=True, key="sync_now_btn"):
                st.cache_data.clear()
                st.session_state.last_refresh = time.time()
                log_activity("🔄 Manual sync")
                st.rerun()
            st.caption(f"Last Sync: {format_time(datetime.fromtimestamp(st.session_state.last_refresh, tz=IST))} IST")

        sheet_link = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
        st.markdown(f'<a href="{sheet_link}" target="_blank" class="sheet-link-btn">📊 Open Google Sheet</a>', unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("### 🖨️ Print Options")
        components.html("""
        <div style="width:100%; margin-top:8px;">
            <button onclick="
                (function(){
                    var printArea = window.parent.document.querySelector('.print-only');
                    if (!printArea) { alert('No data to print. Please load a sheet first.'); return; }
                    var content = printArea.innerHTML;
                    if (!content || content.trim() === '' || content.includes('No data available')) {
                        alert('No data to print. Please load data first.');
                        return;
                    }
                    var iframe = window.parent.document.createElement('iframe');
                    iframe.style.position = 'fixed';
                    iframe.style.top = '-9999px';
                    iframe.style.left = '-9999px';
                    iframe.style.width = '0';
                    iframe.style.height = '0';
                    iframe.style.border = 'none';
                    window.parent.document.body.appendChild(iframe);
                    var doc = iframe.contentWindow.document;
                    doc.open();
                    doc.write('<html><head><title>Sheet Print</title>');
                    doc.write('<style>');
                    doc.write('@page { margin: 1cm; size: A4 landscape; }');
                    doc.write('body { font-family: Arial, sans-serif; margin: 0; padding: 10px; background: white; }');
                    doc.write('h2 { text-align: center; font-size: 18pt; margin-bottom: 5px; color: #000; }');
                    doc.write('p.meta { text-align: center; font-size: 10pt; margin-bottom: 15px; color: #333; }');
                    doc.write('table { width: 100%; border-collapse: collapse; font-size: 7.5pt; page-break-inside: auto; }');
                    doc.write('tr { page-break-inside: avoid; }');
                    doc.write('thead { display: table-header-group; }');
                    doc.write('th { background: #333 !important; color: white !important; padding: 4px 5px; border: 1px solid #333; text-align: center; font-weight: bold; }');
                    doc.write('td { border: 1px solid #999; padding: 3px 4px; text-align: center; color: #000; word-wrap: break-word; }');
                    doc.write('tr:nth-child(even) { background: #f5f5f5 !important; }');
                    doc.write('</style></head><body>');
                    doc.write(content);
                    doc.write('</body></html>');
                    doc.close();
                    setTimeout(function(){
                        iframe.contentWindow.focus();
                        iframe.contentWindow.print();
                        setTimeout(function(){ window.parent.document.body.removeChild(iframe); }, 2000);
                    }, 300);
                })();
            " style="display: block; width: 100%; padding: 10px 16px; background: #2563eb; color: white; text-align: center; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 0.95rem; border: none; cursor: pointer; box-sizing: border-box; font-family: inherit;">🖨️ PRINT Sheet</button>
        </div>
        """, height=50)

        with st.expander("📤 Upload & Process", expanded=True):
            st.caption("Image • PDF • Text • Voice")
            mode = st.radio("Type", ["📷 Image / PDF", "📝 Text", "🎤 Voice / Audio"],
                horizontal=True, label_visibility="collapsed", key="upload_mode_radio")
            uploaded = None
            text_data = ""
            audio_data = None
            if mode == "📷 Image / PDF":
                uploaded = st.file_uploader("Image or PDF", type=["png","jpg","jpeg","pdf"],
                    label_visibility="collapsed", key=f"img_pdf_uploader_{st.session_state.img_uploader_key}")
            elif mode == "📝 Text":
                text_data = st.text_area("📝 Paste text", height=150,
                    placeholder="Paste messy text here...",
                    label_visibility="collapsed", key=f"text_input_area_{st.session_state.text_input_key}")
                if text_data: st.caption(f"✓ {len(text_data)} characters ready")
            else:
                st.caption("🎤 Record from microphone")
                audio_data = st.audio_input("Record", label_visibility="collapsed", key=f"audio_recorder_{st.session_state.audio_recorder_key}")
                uploaded = st.file_uploader("Or upload file", type=["mp3","wav","ogg","m4a"],
                    label_visibility="collapsed", key=f"audio_file_uploader_{st.session_state.audio_uploader_key}")
                if audio_data: st.audio(audio_data, format='audio/wav')
                elif uploaded: st.audio(uploaded, format='audio/mp3')

            if st.button("🚀 Process & Save", type="primary", use_container_width=True, key="process_save_btn"):
                if mode == "📝 Text" and not text_data.strip(): st.warning("Please enter text")
                elif mode != "📝 Text" and not uploaded and not audio_data: st.warning("Please choose a file")
                else:
                    prog = st.progress(0)
                    status = st.empty()
                    def upd(v, m): prog.progress(v); status.text(m)
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
                                    st.session_state.text_input_key += 1
                                    st.session_state.img_uploader_key += 1
                                    st.session_state.audio_uploader_key += 1
                                    st.session_state.audio_recorder_key += 1
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

        if st.session_state.upload_success and st.session_state.last_uploaded_file:
            with st.expander("📄 Last Uploaded File", expanded=True):
                st.markdown(f"""
                <div class="file-card">
                    <div class="file-card-title">📄 {st.session_state.last_uploaded_file}</div>
                    <div class="file-card-meta">Uploaded at {st.session_state.get('last_upload_time', '—')} IST</div>
                </div>
                """, unsafe_allow_html=True)
                c1, c2, c3 = st.columns(3)
                with c1:
                    if st.session_state.last_uploaded_view_url:
                        st.link_button("👁️ View", st.session_state.last_uploaded_view_url, use_container_width=True)
                with c2:
                    if st.session_state.last_uploaded_print_url:
                        st.link_button("🖨️ Print File", st.session_state.last_uploaded_print_url, use_container_width=True)
                with c3:
                    if st.session_state.last_uploaded_drive_id:
                        st.link_button("📥 Download", f"https://drive.google.com/uc?export=download&id={st.session_state.last_uploaded_drive_id}", use_container_width=True)
                if st.button("🗑️ Clear History", use_container_width=True, key="clear_history_btn"):
                    st.session_state.last_uploaded_file = None
                    st.session_state.last_uploaded_drive_url = None
                    st.session_state.last_uploaded_view_url = None
                    st.session_state.last_uploaded_print_url = None
                    st.session_state.last_uploaded_drive_id = None
                    st.session_state.upload_success = False
                    st.rerun()

        with st.expander("📋 Activity Log", expanded=False):
            if st.session_state.activity_log:
                for log in reversed(st.session_state.activity_log[-20:]):
                    st.caption(f"{log.get('timestamp', '')} — {log.get('action', '')}")
            else: st.caption("No activity yet")
        st.markdown("---")

        st.markdown("### 📑 Select Sheet")
        sheet_choice = st.selectbox("Select Sheet", list(SHEET_CONFIG.keys()),
            index=list(SHEET_CONFIG.keys()).index(st.session_state.selected_sheet)
            if st.session_state.selected_sheet in SHEET_CONFIG else 0, key="sheet_select")
        if sheet_choice != st.session_state.selected_sheet:
            st.session_state.selected_sheet = sheet_choice
            st.session_state.current_page = 1
            st.cache_data.clear()
            st.rerun()

        if sheet_choice != "NOTE":
            st.markdown("### 🔍 Filters")
            config = SHEET_CONFIG[sheet_choice]
            pnr_col_idx = config.get("pnr_col")
            train_col_idx = config.get("train_col")
            class_col_idx = config.get("class_col")
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

            if class_col_idx is not None:
                class_input = st.text_input("Class (partial)", value=st.session_state.class_val, key="class_filter_input")
                if class_input != st.session_state.class_val:
                    st.session_state.class_val = class_input
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

            if st.button("🧹 Clear All Filters", use_container_width=True, key="clear_filters_btn"):
                st.session_state.pnr_val = ''
                st.session_state.train_val = ''
                st.session_state.class_val = ''
                st.session_state.from_val = None
                st.session_state.to_val = None
                st.session_state.current_page = 1
                st.rerun()

    # Load data for selected sheet
    df_raw = load_sheet_data_cached(sheet_choice, SHEET_ID)
    filtered_df = df_raw.copy() if not df_raw.empty else pd.DataFrame()

    # Apply filters (skip for NOTE sheet)
    if not filtered_df.empty and sheet_choice != "NOTE":
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
        if st.session_state.class_val and class_col_idx is not None and class_col_idx < len(filtered_df.columns):
            col_name = filtered_df.columns[class_col_idx]
            filtered_df = filtered_df[filtered_df[col_name].astype(str).str.contains(st.session_state.class_val, case=False, na=False)]
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

    view = st.session_state.view_mode

    # Top bar with marquee
    st.markdown("""
    <div class="eqms-marquee-box">
        <span class="scroll-text">🚂 Welcome to AI EQMS Hub Pro • Created by Sharique • Indian Railways • Emergency Quota Management System • Real-time Data • PNR Status • Live Train • Weather • Gemini AI • Google Sheets Integration • Drive Auto-Save</span>
    </div>
    """, unsafe_allow_html=True)

    top_c1, top_nav, top_c2 = st.columns([2.4, 2.2, 1.2])
    with top_c1:
        st.markdown(f"<h1 style='font-size:22px; font-weight:700; margin:0;'>🚂 AI EQMS Hub Pro — {sheet_choice}</h1>", unsafe_allow_html=True)
    with top_nav:
        nav_defs = [("📋", "📋 Data Table"), ("📊", "📊 Dashboard"), ("💬", "💬 Chat"), ("🚂", "🚂 Railway"), ("🌤️", "🌤️ Weather")]
        nav_cols = st.columns(5)
        for (icon, name), nc in zip(nav_defs, nav_cols):
            with nc:
                if st.button(icon, key=f"nav_btn_{name}", help=name, use_container_width=True,
                             type="primary" if st.session_state.view_mode == name else "secondary"):
                    st.session_state.view_mode = name
                    st.query_params['__view'] = name
                    st.rerun()
    with top_c2:
        st.markdown(f"<div style='padding-top:6px; text-align:right;'><span class='status-pill status-live'>● Live</span> &nbsp; <span style='font-size:13px;'>Sync {format_time(datetime.fromtimestamp(st.session_state.last_refresh, tz=IST))} IST</span></div>", unsafe_allow_html=True)

    st.caption(f"Enterprise Railway EQ Management  •  {format_date()}  •  {format_time()} IST")
    st.markdown("---")

    # =====================================================================
    # VIEW: 📋 DATA TABLE
    # =====================================================================
    if view == "📋 Data Table":
        st.subheader(f"📋 {sheet_choice}  —  {len(filtered_df)} rows")

        # Global Search
        if not filtered_df.empty and sheet_choice != "NOTE":
            search_col1, search_col2 = st.columns([4, 1])
            with search_col1:
                global_search = st.text_input("🔍 Global Search (searches all columns)",
                    value=st.session_state.global_search,
                    placeholder="Type to search across all columns...",
                    key="global_search_input")
                if global_search != st.session_state.global_search:
                    st.session_state.global_search = global_search
                    st.session_state.current_page = 1
                    st.rerun()
            with search_col2:
                if st.button("🧹 Clear Search", use_container_width=True, key="clear_global_search"):
                    st.session_state.global_search = ''
                    st.session_state.current_page = 1
                    st.rerun()

            if st.session_state.global_search:
                search_term = st.session_state.global_search.lower()
                mask = pd.Series([False] * len(filtered_df))
                for col in filtered_df.columns:
                    if col != '_sheet_row':
                        mask = mask | filtered_df[col].astype(str).str.lower().str.contains(search_term, na=False)
                filtered_df = filtered_df[mask]

        # Advanced Filters
        if not filtered_df.empty and sheet_choice != "NOTE":
            with st.expander("🔍 Advanced Filters & Column Search", expanded=False):
                st.markdown(f"**📊 Monitoring: {sheet_choice} Sheet**")
                af1, af2, af3, af4 = st.columns(4)
                with af1:
                    adv_pnr = st.text_input("🔎 PNR", value=st.session_state.pnr_val, key="adv_pnr")
                with af2:
                    adv_train = st.text_input("🚆 Train", value=st.session_state.train_val, key="adv_train")
                with af3:
                    class_col = next((c for c in filtered_df.columns if 'CLASS' in c.upper()), None)
                    if class_col:
                        unique_classes = ['All'] + sorted(filtered_df[class_col].dropna().astype(str).unique().tolist())
                        adv_class = st.selectbox("🎫 Class", unique_classes, key="adv_class")
                    else:
                        st.selectbox("🎫 Class", ['All'], key="adv_class_dummy")
                with af4:
                    vip_col = next((c for c in filtered_df.columns if 'VIP' in c.upper() or 'MP/MLA' in c.upper()), None)
                    if vip_col:
                        unique_vip = ['All'] + sorted([v for v in filtered_df[vip_col].dropna().astype(str).unique().tolist() if str(v).strip()])
                        st.selectbox("⭐ VIP", unique_vip, key="adv_vip")
                    else:
                        st.selectbox("⭐ VIP", ['All'], key="adv_vip_dummy")

                af5, af6, af7 = st.columns(3)
                with af5:
                    from_col = next((c for c in filtered_df.columns if c.upper() == 'FROM'), None)
                    to_col = next((c for c in filtered_df.columns if c.upper() == 'TO'), None)
                    if from_col and to_col:
                        routes = filtered_df[from_col].astype(str).str.upper() + " → " + filtered_df[to_col].astype(str).str.upper()
                        unique_routes = ['All'] + sorted(routes.dropna().unique().tolist())
                        st.selectbox("🛤️ Route", unique_routes, key="adv_route")
                    else:
                        st.selectbox("🛤️ Route", ['All'], key="adv_route_dummy")
                with af6:
                    st.date_input("📅 From DOJ", value=st.session_state.from_val, key="adv_from_doj", format="DD-MM-YYYY")
                with af7:
                    st.date_input("📅 To DOJ", value=st.session_state.to_val, key="adv_to_doj", format="DD-MM-YYYY")

                if st.button("🚀 Apply Filters", use_container_width=True, key="adv_apply"):
                    st.rerun()

        # Train count summary cards
        train_col_metric = find_column(filtered_df, ['T/N', 'T_N', 'TRAIN', 'TRAIN NO', 'TRAIN NUMBER'])
        doj_col = find_column(filtered_df, ['DOJ', 'DATE OF JOURNEY', 'JOURNEY DATE'])

        if not filtered_df.empty and sheet_choice != "NOTE":
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

        if st.button("🔄 Refresh Data", use_container_width=False, key="refresh_data_btn"):
            st.cache_data.clear()
            st.session_state.last_refresh = time.time()
            log_activity("🔄 Manual refresh from main")
            st.rerun()

        if filtered_df.empty:
            st.info("📭 No data. Clear filters or choose another sheet.")
            has_structure = len(df_raw.columns) > 0
            empty_df = df_raw.drop(columns=['_sheet_row'], errors='ignore') if has_structure else pd.DataFrame()
            if has_structure and len(empty_df.columns) > 0:
                st.markdown("**📋 Column Structure**")
                display_empty = empty_df.head(0).copy()
                display_empty.insert(0, "Select", False)
                st.dataframe(display_empty, use_container_width=True, height=120)
            else:
                st.caption("Sheet has headers but no data rows yet.")
        else:
            # Sorting
            sort_col = st.session_state.sort_column
            sort_asc = st.session_state.sort_ascending
            if sort_col and sort_col in filtered_df.columns:
                try:
                    filtered_df = filtered_df.sort_values(by=sort_col, ascending=sort_asc, key=lambda col: col.astype(str))
                except: pass

            page_size = st.selectbox("Rows per page", [15, 25, 50, 100, 200],
                index=[15, 25, 50, 100, 200].index(st.session_state.rows_per_page) if st.session_state.rows_per_page in [15,25,50,100,200] else 1,
                key="page_size_select")
            if page_size != st.session_state.rows_per_page:
                st.session_state.rows_per_page = page_size
                st.session_state.current_page = 1
                st.rerun()

            total_pages = max(1, math.ceil(len(filtered_df) / page_size))
            if st.session_state.current_page > total_pages: st.session_state.current_page = total_pages
            if st.session_state.current_page < 1: st.session_state.current_page = 1

            nav1, nav2, nav3 = st.columns([1, 2, 1])
            with nav1:
                if st.button("◀ Previous", use_container_width=True, disabled=st.session_state.current_page <= 1, key="prev_page_btn"):
                    st.session_state.current_page -= 1
                    st.rerun()
            with nav2:
                st.markdown(f"<div style='text-align:center; padding-top:6px;'><b>Page {st.session_state.current_page} of {total_pages}</b> &nbsp;|&nbsp; <b>{len(filtered_df)} total rows</b></div>", unsafe_allow_html=True)
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

            # Sorting controls
            if not display_df.empty:
                sort_cols = st.columns(4)
                with sort_cols[0]:
                    sort_options = ['None'] + list(display_df.columns)
                    current_sort = st.session_state.sort_column if st.session_state.sort_column in display_df.columns else 'None'
                    new_sort = st.selectbox("📊 Sort by", sort_options, index=sort_options.index(current_sort) if current_sort in sort_options else 0, key="sort_by_select")
                    if new_sort != current_sort:
                        st.session_state.sort_column = None if new_sort == 'None' else new_sort
                        st.rerun()
                with sort_cols[1]:
                    if st.session_state.sort_column:
                        sort_dir = st.selectbox("Direction", ['Ascending', 'Descending'],
                            index=0 if st.session_state.sort_ascending else 1, key="sort_dir_select")
                        new_asc = sort_dir == 'Ascending'
                        if new_asc != st.session_state.sort_ascending:
                            st.session_state.sort_ascending = new_asc
                            st.rerun()

            # Print-only table
            print_export_df = filtered_df.drop(columns=['_sheet_row'], errors='ignore')
            if not print_export_df.empty:
                print_html_table = print_export_df.to_html(index=False, border=1, classes='print-table', escape=False)
            else:
                print_html_table = "<p>No data available</p>"

            st.markdown(f"""
            <div class="print-only" id="print-content">
                <h2 style="text-align:center; margin-bottom:5px;">{sheet_choice} Sheet Report</h2>
                <p style="text-align:center; font-size:11pt; margin-bottom:15px;">Generated: {format_datetime()} IST | Total Records: {len(filtered_df)}</p>
                {print_html_table}
                <p style="text-align:center; font-size:10pt; margin-top:10px;">— End of Report —</p>
            </div>
            """, unsafe_allow_html=True)

            st.markdown('<div class="print-area">', unsafe_allow_html=True)
            edited_page = st.data_editor(display_df, use_container_width=True, height=500,
                column_config={"Select": st.column_config.CheckboxColumn("Select", width="small")},
                key=f"editor_{sheet_choice}_{st.session_state.current_page}_{page_size}")
            st.markdown('</div>', unsafe_allow_html=True)

            # Select All
            selected_mask = edited_page["Select"] if "Select" in edited_page.columns else pd.Series([False] * len(edited_page))
            if 'select_all_state' not in st.session_state:
                st.session_state.select_all_state = False
            
            select_all = st.checkbox("Select All on Page", value=st.session_state.select_all_state, key="select_all_cb")
            if select_all != st.session_state.select_all_state:
                st.session_state.select_all_state = select_all
                st.rerun()
            
            if st.session_state.select_all_state:
                st.info("✅ All rows on this page are selected")

            selected_indices = edited_page[selected_mask].index.tolist()
            selected_sheet_rows = []
            if selected_indices and sheet_rows:
                for idx in selected_indices:
                    try:
                        pos = list(page_df.index).index(idx)
                        selected_sheet_rows.append(sheet_rows[pos])
                    except (ValueError, IndexError): pass

            pnr_col = next((c for c in edited_page.columns if 'PNR' in str(c).upper()), None)
            selected_pnrs = edited_page.loc[selected_indices, pnr_col].tolist() if pnr_col and selected_indices else []

            # Quick Actions
            st.markdown('<div class="action-box no-print">', unsafe_allow_html=True)
            st.markdown("**⚡ Quick Actions**")
            a1, a2, a3, a4, a5 = st.columns(5)
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
                        else: st.warning("Nothing to save")
                    except Exception as e:
                        if "429" in str(e): st.error("Write quota exceeded. Wait 1 minute.")
                        else: st.error(f"Save error: {e}")
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
                        if len(all_data) >= start_row: blank_row[0] = len(all_data) - start_row + 2
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
            with a5:
                components.html("""
                <div style="width:100%;">
                    <button onclick="
                        (function(){
                            var el = window.parent.document.querySelector('.print-only');
                            if (!el) { alert('No data to print.'); return; }
                            var content = el.innerHTML;
                            if (!content || content.trim() === '' || content.includes('No data available')) {
                                alert('No data to print. Please load data first.');
                                return;
                            }
                            var iframe = window.parent.document.createElement('iframe');
                            iframe.style.position = 'fixed';
                            iframe.style.top = '-9999px';
                            iframe.style.left = '-9999px';
                            iframe.style.width = '0';
                            iframe.style.height = '0';
                            iframe.style.border = 'none';
                            window.parent.document.body.appendChild(iframe);
                            var doc = iframe.contentWindow.document;
                            doc.open();
                            doc.write('<html><head><title>Print</title>');
                            doc.write('<style>@page { margin: 1cm; size: A4 landscape; } body { font-family: Arial; margin: 0; padding: 10px; background: white; } h2 { text-align: center; font-size: 18pt; margin-bottom: 5px; color: #000; } table { width: 100%; border-collapse: collapse; font-size: 7.5pt; page-break-inside: auto; } tr { page-break-inside: avoid; } thead { display: table-header-group; } th { background: #333 !important; color: white !important; padding: 4px 5px; border: 1px solid #333; text-align: center; font-weight: bold; } td { border: 1px solid #999; padding: 3px 4px; text-align: center; color: #000; word-wrap: break-word; } tr:nth-child(even) { background: #f5f5f5 !important; }</style></head><body>');
                            doc.write(content);
                            doc.write('</body></html>');
                            doc.close();
                            setTimeout(function(){ iframe.contentWindow.focus(); iframe.contentWindow.print(); setTimeout(function(){ window.parent.document.body.removeChild(iframe); }, 2000); }, 300);
                        })();
                    " style="display: block; width: 100%; padding: 9px 16px; background: #2563eb; color: white; text-align: center; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 1rem; border: none; cursor: pointer; box-sizing: border-box; font-family: inherit;">🖨️ PRINT</button>
                </div>
                """, height=45)
            st.markdown('</div>', unsafe_allow_html=True)

            # WhatsApp Image Share
            st.markdown('<div class="no-print">', unsafe_allow_html=True)
            st.markdown("**📱 WhatsApp Image Share**")
            wa_col1, wa_col2, wa_col3 = st.columns(3)
            with wa_col1:
                if not filtered_df.empty:
                    img_bytes = create_table_image(filtered_df, f"{sheet_choice} Data")
                    if img_bytes:
                        st.download_button("Download Table Image", data=img_bytes,
                            file_name=f"{sheet_choice}_table.png", mime="image/png",
                            use_container_width=True, key="wa_img_download")
            with wa_col2:
                if selected_indices and not filtered_df.empty:
                    sel_img_bytes = create_table_image(filtered_df.iloc[selected_indices], f"{sheet_choice} Selected")
                    if sel_img_bytes:
                        st.download_button("Download Selected Image", data=sel_img_bytes,
                            file_name=f"{sheet_choice}_selected.png", mime="image/png",
                            use_container_width=True, key="wa_sel_img_download")
                else: st.info("Select rows to generate image")
            with wa_col3:
                if not filtered_df.empty:
                    img_bytes = create_table_image(filtered_df, f"{sheet_choice} Data")
                    if img_bytes:
                        img_b64 = base64.b64encode(img_bytes).decode()
                        copy_js = '<div style="width:100%;"><button onclick="copyImg()" style="background:#25D366;color:white;border:none;border-radius:8px;padding:9px 16px;width:100%;font-weight:600;cursor:pointer;font-size:1rem;">Copy Sheet Image</button><script>function copyImg(){var d="' + img_b64 + '";fetch("data:image/png;base64,"+d).then(r=>r.blob()).then(b=>{navigator.clipboard.write([new ClipboardItem({"image/png":b})]).then(()=>alert("Copied! Paste into WhatsApp.")).catch(()=>alert("Failed. Use download."));});}</script></div>'
                        components.html(copy_js, height=50)
            st.markdown('</div>', unsafe_allow_html=True)

            # Export
            st.markdown('<div class="no-print">', unsafe_allow_html=True)
            st.markdown("**📄 Export**")
            e1, e2, e3, e4 = st.columns(4)
            with e1:
                try:
                    export_df = filtered_df.drop(columns=['_sheet_row'], errors='ignore')
                    pdf_bytes = generate_pdf(export_df, sheet_choice, full=True)
                    st.download_button("PDF (All)", data=pdf_bytes,
                        file_name=f"{sheet_choice}_{now_ist().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf", use_container_width=True, key="pdf_all_download")
                except Exception as e: st.warning(f"PDF error: {e}")
            with e2:
                if selected_indices: export_sel = filtered_df.iloc[selected_indices].drop(columns=['_sheet_row'], errors='ignore')
                else: export_sel = filtered_df.drop(columns=['_sheet_row'], errors='ignore')
                csv_sel = export_sel.to_csv(index=False).encode('utf-8')
                st.download_button("CSV (Selected)" if selected_indices else "CSV (All)", data=csv_sel,
                    file_name=f"{sheet_choice}_{now_ist().strftime('%Y%m%d_%H%M')}_selected.csv",
                    mime="text/csv", use_container_width=True, key="csv_download")
            with e3:
                export_df = filtered_df.drop(columns=['_sheet_row'], errors='ignore')
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                    export_df.to_excel(writer, sheet_name=sheet_choice, index=False)
                excel_data = excel_buffer.getvalue()
                st.download_button("Excel", data=excel_data,
                    file_name=f"{sheet_choice}_{now_ist().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True, key="excel_download")
            with e4:
                csv_full = filtered_df.drop(columns=['_sheet_row'], errors='ignore').to_csv(index=False).encode('utf-8')
                st.download_button("Copy CSV", data=csv_full, file_name="table.csv",
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
                        st.link_button("Check PNR Status", pnr_url, use_container_width=True)
                    st.markdown("**📊 Quick Stats**")
                    if not filtered_df.empty and pnr_col:
                        valid_pnrs = filtered_df[pnr_col].astype(str).str.match(r'\d{10}').sum()
                        st.caption(f"Valid PNRs: {valid_pnrs}")
                    if not filtered_df.empty and doj_col is not None:
                        upcoming = sum(1 for _, r in filtered_df.iterrows() if not is_expired(r.get(doj_col, '')))
                        st.caption(f"Upcoming DOJ: {upcoming}")
                with feat2:
                    st.markdown("**🚆 Train Analysis**")
                    if train_col_metric and not filtered_df.empty:
                        most_common = filtered_df[train_col_metric].mode()
                        if not most_common.empty: st.caption(f"Most common train: {most_common.iloc[0]}")
                        if pnr_col:
                            dupes = filtered_df[pnr_col].value_counts()
                            dupes = dupes[dupes > 1]
                            if not dupes.empty: st.warning(f"⚠️ {len(dupes)} duplicate PNRs found!")
                            else: st.success("✅ No duplicate PNRs")
                    st.markdown("**⌨️ Shortcuts**")
                    st.caption("D: Toggle theme | Refresh button to sync data")
            st.markdown('</div>', unsafe_allow_html=True)

    # =====================================================================
    # VIEW: 📊 DASHBOARD
    # =====================================================================
    elif view == "📊 Dashboard":
        st.markdown("""
        <style>
        @keyframes dash-fade-in { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes dash-scale-in { from { opacity: 0; transform: scale(0.85); } to { opacity: 1; transform: scale(1); } }
        @keyframes dash-pulse-glow { 0%,100% { box-shadow: 0 0 20px rgba(37,99,235,0.15); } 50% { box-shadow: 0 0 40px rgba(37,99,235,0.35); } }
        @keyframes dash-gradient-shift { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
        .dash-anim-1 { animation: dash-fade-in 0.6s ease-out both; }
        .dash-anim-2 { animation: dash-fade-in 0.6s ease-out 0.15s both; }
        .dash-anim-3 { animation: dash-fade-in 0.6s ease-out 0.3s both; }
        .dash-anim-4 { animation: dash-fade-in 0.6s ease-out 0.45s both; }
        .dash-anim-5 { animation: dash-fade-in 0.6s ease-out 0.6s both; }
        .dash-chart-anim { animation: dash-scale-in 0.7s ease-out both; }
        .dash-metric-glow { animation: dash-pulse-glow 3s ease-in-out infinite; }
        .dash-gradient-text { background: linear-gradient(90deg, #FF9933, #FFFFFF, #138808, #FF9933); background-size: 300% 300%; -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; animation: dash-gradient-shift 4s ease infinite; font-weight: 800; }
        </style>
        """, unsafe_allow_html=True)
        st.subheader("📊 Analytics Dashboard")

        dash_sheet_options = ["EQ", "DATA", "FINAL", "DATA2", "EMAIL_DATA"]
        dash_sheet = st.selectbox("📋 Select Sheet for Dashboard", dash_sheet_options,
            index=dash_sheet_options.index(st.session_state.dashboard_sheet) if st.session_state.dashboard_sheet in dash_sheet_options else 0,
            key="dashboard_sheet_select")
        if dash_sheet != st.session_state.dashboard_sheet:
            st.session_state.dashboard_sheet = dash_sheet
            st.rerun()

        dash_df_raw = load_sheet_data_cached(dash_sheet, SHEET_ID)
        dash_df = dash_df_raw.copy() if not dash_df_raw.empty else pd.DataFrame()

        if st.button("🔄 Refresh Dashboard Data", key="refresh_dash_btn"):
            st.cache_data.clear()
            st.session_state.last_refresh = time.time()
            st.rerun()

        # Apply filters
        if not dash_df.empty and dash_sheet != "NOTE":
            config = SHEET_CONFIG[dash_sheet]
            pnr_col_idx = config.get("pnr_col")
            train_col_idx = config.get("train_col")
            doj_col_idx = config.get("doj_col")

            if st.session_state.pnr_val and pnr_col_idx is not None and pnr_col_idx < len(dash_df.columns):
                col_name = dash_df.columns[pnr_col_idx]
                dash_df = dash_df[dash_df[col_name].astype(str).str.contains(st.session_state.pnr_val, case=False, na=False)]
            if st.session_state.train_val and train_col_idx is not None and train_col_idx < len(dash_df.columns):
                col_name = dash_df.columns[train_col_idx]
                dash_df = dash_df[dash_df[col_name].astype(str).str.contains(st.session_state.train_val, case=False, na=False)]
            if (st.session_state.from_val or st.session_state.to_val) and doj_col_idx is not None and doj_col_idx < len(dash_df.columns):
                col_name = dash_df.columns[doj_col_idx]
                try:
                    dash_df['_temp'] = pd.to_datetime(dash_df[col_name], format='%d-%m-%Y', errors='coerce')
                    if dash_df['_temp'].isna().all(): dash_df['_temp'] = pd.to_datetime(dash_df[col_name], errors='coerce')
                except: dash_df['_temp'] = pd.to_datetime(dash_df[col_name], errors='coerce')
                if st.session_state.from_val: dash_df = dash_df[dash_df['_temp'] >= pd.to_datetime(st.session_state.from_val)]
                if st.session_state.to_val: dash_df = dash_df[dash_df['_temp'] <= pd.to_datetime(st.session_state.to_val)]
                dash_df = dash_df.drop('_temp', axis=1, errors='ignore')

        active_filters = []
        if st.session_state.pnr_val: active_filters.append(f"PNR: {st.session_state.pnr_val}")
        if st.session_state.train_val: active_filters.append(f"Train: {st.session_state.train_val}")
        if st.session_state.from_val: active_filters.append(f"From: {st.session_state.from_val.strftime('%d-%m-%Y')}")
        if st.session_state.to_val: active_filters.append(f"To: {st.session_state.to_val.strftime('%d-%m-%Y')}")
        if active_filters: st.caption(f"🔍 Active Filters: {' | '.join(active_filters)}")

        st.markdown("### Key Metrics")
        kcol1, kcol2, kcol3, kcol4, kcol5 = st.columns(5)
        total_records = len(dash_df) if not dash_df.empty else 0
        with kcol1: 
            st.markdown(f'<div class="metric-card"><h3>{total_records}</h3><p>Total Records</p></div>', unsafe_allow_html=True)

        # Use SHEET_CONFIG for reliable column indices per sheet
        dash_cfg = SHEET_CONFIG.get(dash_sheet, {})
        def cfg_col(name):
            idx = dash_cfg.get(name)
            return dash_df.columns[idx] if idx is not None and idx < len(dash_df.columns) else None
        train_col_dash = cfg_col('train_col')
        class_col_dash = cfg_col('class_col')
        from_col_dash = cfg_col('from_col')
        to_col_dash = cfg_col('to_col')
        berth_col_dash = cfg_col('berth_col')
        doj_col_dash = cfg_col('doj_col')
        # VIP column is always the same header across sheets — find by header name
        vip_col_dash = next((c for c in dash_df.columns if 'VIP' in c.upper() or 'MP/MLA' in c.upper() or 'MINISTER' in c.upper()), None)
        if train_col_dash and column_has_data(dash_df, train_col_dash):
            unique_trains = dash_df[train_col_dash].dropna().astype(str).str.strip().ne('').nunique()
            with kcol2: 
                st.markdown(f'<div class="metric-card" style="background:linear-gradient(135deg,#11998e,#38ef7d); color: white;"><h3 style="color: white;">{unique_trains}</h3><p style="color: rgba(255,255,255,0.9);">Unique Trains</p></div>', unsafe_allow_html=True)
        else:
            with kcol2: 
                st.markdown(f'<div class="metric-card"><h3>—</h3><p>Unique Trains</p></div>', unsafe_allow_html=True)

        # vip_col_dash already detected above via find_column()
        if vip_col_dash and column_has_data(dash_df, vip_col_dash):
            vip_count = dash_df[vip_col_dash].astype(str).str.strip().ne('').sum()
            with kcol3: 
                st.markdown(f'<div class="metric-card" style="background:linear-gradient(135deg,#f093fb,#f5576c); color: white;"><h3 style="color: white;">{vip_count}</h3><p style="color: rgba(255,255,255,0.9);">VIP Records</p></div>', unsafe_allow_html=True)
        else:
            with kcol3: 
                st.markdown(f'<div class="metric-card"><h3>—</h3><p>VIP Records</p></div>', unsafe_allow_html=True)

        # class_col_dash already detected above via find_column()
        if class_col_dash and column_has_data(dash_df, class_col_dash):
            class_counts = dash_df[class_col_dash].dropna().astype(str).str.strip()
            class_counts = class_counts[class_counts != ''].value_counts()
            top_class = class_counts.index[0] if len(class_counts) > 0 else "N/A"
            with kcol4: 
                st.markdown(f'<div class="metric-card" style="background:linear-gradient(135deg,#4facfe,#00f2fe); color: white;"><h3 style="color: white;">{top_class}</h3><p style="color: rgba(255,255,255,0.9);">Top Class</p></div>', unsafe_allow_html=True)
        else:
            with kcol4: 
                st.markdown(f'<div class="metric-card"><h3>—</h3><p>Top Class</p></div>', unsafe_allow_html=True)

        # doj_col_dash already detected above via find_column()
        if doj_col_dash and column_has_data(dash_df, doj_col_dash):
            upcoming = sum(1 for _, r in dash_df.iterrows() if not is_expired(r.get(doj_col_dash, '')))
            with kcol5: 
                st.markdown(f'<div class="metric-card" style="background:linear-gradient(135deg,#fa709a,#fee140); color: white;"><h3 style="color: white;">{upcoming}</h3><p style="color: rgba(255,255,255,0.9);">Upcoming</p></div>', unsafe_allow_html=True)
        else:
            with kcol5: 
                st.markdown(f'<div class="metric-card"><h3>—</h3><p>Upcoming</p></div>', unsafe_allow_html=True)

        st.divider()

        if dash_df.empty:
            st.info("No data for charts. Adjust filters or choose another sheet.")
        else:
            # Graph 1: Train-wise Distribution
            st.markdown("### 1️⃣ Train-wise Distribution")
            if train_col_dash and column_has_data(dash_df, train_col_dash):
                tc = dash_df[train_col_dash].dropna().astype(str).str.strip()
                tc = tc[tc != '']
                if len(tc) > 0:
                    train_counts = tc.value_counts().head(15).reset_index()
                    train_counts.columns = ['Train', 'Count']
                    fig1 = px.bar(train_counts, x='Train', y='Count', title="Train-wise Request Count",
                        color='Count', color_continuous_scale='Viridis', text='Count',
                        labels={'Train': 'Train Number', 'Count': 'Total Requests'})
                    fig1.update_traces(textposition='outside', textfont_size=12)
                    fig1.update_layout(height=400, showlegend=False, margin=dict(l=20,r=20,t=50,b=20),
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        font=dict(size=12), title_font_size=16)
                    st.plotly_chart(fig1, use_container_width=True)
                else:
                    st.info("ℹ️ No train data available for chart.")
            else:
                st.info("ℹ️ Train column not found or empty in this sheet.")

            # Graph 2: Class-wise Distribution
            st.markdown("### 2️⃣ Class-wise Distribution")
            if class_col_dash and column_has_data(dash_df, class_col_dash):
                cc = dash_df[class_col_dash].dropna().astype(str).str.strip()
                cc = cc[cc != '']
                if len(cc) > 0:
                    class_counts = cc.value_counts().reset_index()
                    class_counts.columns = ['Class', 'Count']
                    fig2 = px.pie(class_counts, names='Class', values='Count', title="Class-wise Breakdown",
                        hole=0.5, color_discrete_sequence=px.colors.sequential.RdBu)
                    fig2.update_traces(textinfo='label+percent+value', textfont_size=12,
                        pull=[0.05 if i == 0 else 0 for i in range(len(class_counts))])
                    fig2.update_layout(height=400, showlegend=True, margin=dict(l=20,r=20,t=50,b=20),
                        paper_bgcolor='rgba(0,0,0,0)', font=dict(size=12), title_font_size=16)
                    st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.info("ℹ️ No class data available for chart.")
            else:
                st.info("ℹ️ Class column not found or empty in this sheet.")

            # Graph 3: Route-wise Distribution
            st.markdown("### 3️⃣ Route-wise Distribution")
            # from_col_dash & to_col_dash set via cfg_col above
            if from_col_dash and to_col_dash and column_has_data(dash_df, from_col_dash) and column_has_data(dash_df, to_col_dash):
                dash_df['ROUTE'] = dash_df[from_col_dash].astype(str) + " → " + dash_df[to_col_dash].astype(str)
                route_counts = dash_df['ROUTE'].value_counts().head(12).reset_index()
                route_counts.columns = ['Route', 'Count']
                fig3 = px.bar(route_counts, y='Route', x='Count', orientation='h', title="Top Routes",
                    color='Count', color_continuous_scale='Cividis', text='Count',
                    labels={'Route': 'Route (From → To)', 'Count': 'Total Requests'})
                fig3.update_traces(textposition='outside', textfont_size=11)
                fig3.update_layout(height=450, showlegend=False, margin=dict(l=20,r=20,t=50,b=20),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(size=11), title_font_size=16)
                st.plotly_chart(fig3, use_container_width=True)

            # Graph 4: Train × Class Heatmap
            st.markdown("### 4️⃣ Train × Class Heatmap")
            if train_col_dash and class_col_dash and column_has_data(dash_df, train_col_dash) and column_has_data(dash_df, class_col_dash):
                try:
                    pivot_data = pd.crosstab(
                        dash_df[train_col_dash].fillna('Unknown').astype(str),
                        dash_df[class_col_dash].fillna('Unknown').astype(str),
                        margins=False
                    )
                    
                    if not pivot_data.empty:
                        pivot_data = pivot_data.loc[(pivot_data.sum(axis=1) > 0), (pivot_data.sum(axis=0) > 0)]
                        
                        if not pivot_data.empty:
                            if len(pivot_data) > 15:
                                top_trains = pivot_data.sum(axis=1).nlargest(15).index
                                pivot_data = pivot_data.loc[top_trains]
                            
                            fig4 = px.imshow(
                                pivot_data,
                                text_auto=True,
                                aspect="auto",
                                title="Train vs Class Demand Matrix",
                                color_continuous_scale='YlOrRd',
                                labels={'color': 'Requests', 'x': 'Class', 'y': 'Train Number'}
                            )
                            fig4.update_traces(textfont_size=11)
                            fig4.update_layout(
                                height=max(450, 300 + len(pivot_data) * 15),
                                paper_bgcolor='rgba(0,0,0,0)',
                                font=dict(size=11),
                                title_font_size=16
                            )
                            st.plotly_chart(fig4, use_container_width=True)
                        else:
                            st.info("ℹ️ No valid data for heatmap after filtering.")
                    else:
                        st.info("ℹ️ No data available for Train × Class heatmap.")
                except Exception as e:
                    st.warning(f"⚠️ Could not generate heatmap: {str(e)[:100]}")
                    st.info("Try selecting different filters or check if the data has both Train and Class columns.")

            # Graph 5: Train × Route Grouped Bar
            st.markdown("### 5️⃣ Train × Route Analysis")
            if train_col_dash and from_col_dash and to_col_dash and column_has_data(dash_df, train_col_dash):
                try:
                    tr_df = dash_df.groupby([train_col_dash, 'ROUTE']).size().reset_index(name='Count')
                    if not tr_df.empty:
                        top_routes = dash_df['ROUTE'].value_counts().head(6).index.tolist()
                        tr_df_filtered = tr_df[tr_df['ROUTE'].isin(top_routes)]
                        if not tr_df_filtered.empty:
                            fig5 = px.bar(tr_df_filtered, x=train_col_dash, y='Count', color='ROUTE',
                                title="Train vs Top Routes", barmode='group', text='Count',
                                color_discrete_sequence=px.colors.qualitative.Set2)
                            fig5.update_traces(textposition='outside', textfont_size=10)
                            fig5.update_layout(height=450, margin=dict(l=20,r=20,t=50,b=20),
                                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                                font=dict(size=11), title_font_size=16, legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1))
                            st.plotly_chart(fig5, use_container_width=True)
                        else:
                            st.info("ℹ️ No data for Train × Route chart.")
                    else:
                        st.info("ℹ️ No data available for Train × Route analysis.")
                except Exception as e:
                    st.info("ℹ️ Could not generate route analysis chart.")

            # Graph 6: Rush Comparison
            st.markdown("### 6️⃣ Rush Comparison — High Demand vs Low Demand")
            if train_col_dash and column_has_data(dash_df, train_col_dash):
                try:
                    # Use berth/seat count for real demand if available, else fallback to record count
                    if berth_col_dash and column_has_data(dash_df, berth_col_dash):
                        train_demand = dash_df.groupby(train_col_dash)[berth_col_dash].apply(
                            lambda x: pd.to_numeric(x, errors='coerce').fillna(1).sum()
                        ).reset_index()
                        train_demand.columns = ['Train', 'Count']
                    else:
                        train_demand = dash_df[train_col_dash].value_counts().reset_index()
                        train_demand.columns = ['Train', 'Count']
                    if len(train_demand) > 0:
                        median_demand = train_demand['Count'].median()
                        train_demand['Demand'] = train_demand['Count'].apply(lambda x: 'High Demand 🔥' if x >= median_demand else 'Low Demand ❄️')
                        demand_summary = train_demand.groupby('Demand').agg({'Count': 'sum', 'Train': 'count'}).reset_index()
                        demand_summary.columns = ['Demand Category', 'Total Requests', 'Number of Trains']

                        fig6 = make_subplots(rows=1, cols=2, specs=[[{"type": "bar"}, {"type": "pie"}]],
                            subplot_titles=("Total Requests by Demand", "Train Count by Demand"))

                        fig6.add_trace(go.Bar(x=demand_summary['Demand Category'], y=demand_summary['Total Requests'],
                            text=demand_summary['Total Requests'], textposition='outside', marker_color=['#e74c3c', '#3498db'],
                            name='Requests'), row=1, col=1)

                        fig6.add_trace(go.Pie(labels=demand_summary['Demand Category'], values=demand_summary['Number of Trains'],
                            hole=0.4, marker_colors=['#e74c3c', '#3498db'], textinfo='label+percent+value',
                            name='Trains'), row=1, col=2)

                        fig6.update_layout(height=450, showlegend=False, margin=dict(l=20,r=20,t=60,b=20),
                            paper_bgcolor='rgba(0,0,0,0)', font=dict(size=12), title_font_size=16)
                        st.plotly_chart(fig6, use_container_width=True)

                        with st.expander("📋 Detailed Demand Breakdown", expanded=False):
                            high_demand = train_demand[train_demand['Demand'] == 'High Demand 🔥'].sort_values('Count', ascending=False)
                            low_demand = train_demand[train_demand['Demand'] == 'Low Demand ❄️'].sort_values('Count', ascending=True)
                            c1, c2 = st.columns(2)
                            with c1:
                                st.markdown("**🔥 High Demand Trains**")
                                st.dataframe(high_demand[['Train', 'Count']].rename(columns={'Count': 'Requests'}), use_container_width=True, hide_index=True)
                            with c2:
                                st.markdown("**❄️ Low Demand Trains**")
                                st.dataframe(low_demand[['Train', 'Count']].rename(columns={'Count': 'Requests'}), use_container_width=True, hide_index=True)
                    else:
                        st.info("ℹ️ Not enough data for rush comparison.")
                except Exception as e:
                    st.info("ℹ️ Could not generate rush comparison chart.")

            # DOJ Timeline
            st.markdown("### 📅 DOJ Timeline")
            if doj_col_dash and column_has_data(dash_df, doj_col_dash):
                try:
                    dash_df['_date'] = pd.to_datetime(dash_df[doj_col_dash], format='%d-%m-%Y', errors='coerce')
                    if dash_df['_date'].isna().all(): dash_df['_date'] = pd.to_datetime(dash_df[doj_col_dash], errors='coerce')
                    daily = dash_df.groupby('_date').size().reset_index(name='count')
                    if not daily.empty:
                        fig_timeline = px.line(daily, x='_date', y='count', title="Daily Journey Volume",
                            markers=True, labels={'_date': 'Date', 'count': 'Records'})
                        fig_timeline.update_traces(line=dict(width=3), marker=dict(size=8))
                        fig_timeline.update_layout(height=350, margin=dict(l=20,r=20,t=50,b=20),
                            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                            font=dict(size=12), title_font_size=16)
                        st.plotly_chart(fig_timeline, use_container_width=True)
                except Exception as e:
                    pass

    # =====================================================================
    # VIEW: 💬 CHAT
    # =====================================================================
    elif view == "💬 Chat":
        st.markdown("""
        <style>
        @keyframes chat-bounce { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-8px); } }
        @keyframes chat-glow { 0%,100% { box-shadow: 0 0 15px rgba(96,165,250,0.2); } 50% { box-shadow: 0 0 30px rgba(96,165,250,0.5); } }
        @keyframes chat-typing { 0%,100% { opacity: 0.3; } 50% { opacity: 1; } }
        .chat-train-icon { font-size: 3rem; animation: chat-bounce 2s ease-in-out infinite; display: inline-block; filter: drop-shadow(0 0 10px rgba(96,165,250,0.5)); }
        .chat-welcome { animation: chat-glow 3s ease-in-out infinite; border-radius: 16px; padding: 20px; }
        .chat-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #60a5fa; animation: chat-typing 1.4s ease-in-out infinite; }
        .chat-dot:nth-child(2) { animation-delay: 0.2s; }
        .chat-dot:nth-child(3) { animation-delay: 0.4s; }
        </style>
        <div style="text-align: center; padding: 10px 0;">
            <span class="chat-train-icon">🚂</span>
            <div style="font-size: 1.5rem; font-weight: 700; margin-top: 8px;" class="dash-gradient-text">TSKEQ Bot</div>
            <div style="color: #94a3b8; font-size: 0.9rem;">Ask about EQ data, trains, quota, PNR or anything else</div>
        </div>
        """, unsafe_allow_html=True)
        st.subheader("💬 Chat with TSKEQ Bot")
        st.caption("Ask about EQ data, trains, quota, PNR or anything else.")
        if prompt := st.chat_input("Type your question...", key="chat_input"):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    response = chat_with_gemini(prompt, st.session_state.messages)
                    st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
            st.rerun()
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
        st.markdown("**Quick Questions**")
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

    # =====================================================================
    # VIEW: 🚂 RAILWAY
    # =====================================================================
    elif view == "🚂 Railway":
        st.subheader("🚂 Indian Railways - Real-time Info")

        if not NTES_AVAILABLE:
            st.error("❌ 'ntes-client' library not installed. Please run: `pip install ntes-client`")
            st.info("💡 Using alternative web-based PNR and train status services...")
            st.markdown("### 🔍 PNR Status (via ConfirmTkt)")
            pnr_input = st.text_input("Enter 10-digit PNR", max_chars=10, key="rail_pnr_alt")
            if pnr_input and len(pnr_input) == 10 and pnr_input.isdigit():
                pnr_url = f"https://www.confirmtkt.com/pnr-status/{pnr_input}"
                st.link_button("🔍 Check PNR Status", pnr_url, use_container_width=True)
            st.markdown("### 🚂 Live Train Status (via RailYatri)")
            train_no = st.text_input("Enter Train Number (3-5 digits)", key="rail_train_alt")
            if train_no and train_no.isdigit() and (3 <= len(train_no) <= 5):
                train_url = f"https://www.railyatri.in/live-train-status/{train_no}"
                st.link_button("🚂 Check Live Status", train_url, use_container_width=True)
            st.markdown("### 📋 Train Schedule (via RailYatri)")
            train_no_sch = st.text_input("Enter Train Number (3-5 digits)", key="rail_sch_alt")
            if train_no_sch and train_no_sch.isdigit() and (3 <= len(train_no_sch) <= 5):
                sch_url = f"https://www.railyatri.in/train-schedule/{train_no_sch}"
                st.link_button("📋 View Schedule", sch_url, use_container_width=True)
        else:
            tab1, tab2, tab3, tab4 = st.tabs(["🔍 PNR Status", "🚂 Live Train", "📋 Train Schedule", "📸 Passport Photo"])

            with tab1:
                st.markdown("### PNR Status Check")
                pnr_input = st.text_input("Enter 10-digit PNR", max_chars=10, key="rail_pnr")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Check PNR", key="pnr_check", use_container_width=True):
                        if not pnr_input or len(pnr_input) != 10 or not pnr_input.isdigit():
                            st.error("Please enter a valid 10-digit PNR.")
                        else:
                            with st.spinner("Fetching PNR details..."):
                                data = get_pnr_status(pnr_input)
                                if data and isinstance(data, dict) and data.get('error'):
                                    if data['error'] == "FLUSHED_PNR": st.error("❌ FLUSHED PNR / PNR NOT YET GENERATED")
                                    else: st.error(f"❌ {data['error']}")
                                elif data:
                                    st.session_state.pnr_result = data
                                    st.session_state.pnr_last_checked = time.time()
                                    st.rerun()
                                else: st.error("❌ PNR not found or flushed.")
                with c2:
                    if st.button("🔄 Refresh PNR", key="refresh_pnr", use_container_width=True):
                        if pnr_input and len(pnr_input) == 10 and pnr_input.isdigit():
                            with st.spinner("Refreshing PNR..."):
                                data = get_pnr_status(pnr_input)
                                if data and isinstance(data, dict) and data.get('error'): st.error(f"❌ {data['error']}")
                                elif data:
                                    st.session_state.pnr_result = data
                                    st.session_state.pnr_last_checked = time.time()
                                    st.rerun()
                                else: st.error("❌ PNR not found or flushed.")
                        else: st.warning("Please enter a valid PNR first.")

                if st.session_state.pnr_result and st.session_state.pnr_last_checked:
                    elapsed = time.time() - st.session_state.pnr_last_checked
                    if elapsed > 300:
                        with st.spinner("Auto-refreshing PNR..."):
                            current_pnr = st.session_state.pnr_result.get('pnr')
                            if current_pnr:
                                data = get_pnr_status(current_pnr)
                                if data and not isinstance(data, dict) or not data.get('error'):
                                    st.session_state.pnr_result = data
                                    st.session_state.pnr_last_checked = time.time()
                                    st.rerun()

                if st.session_state.pnr_result:
                    with st.container():
                        st.markdown('<div class="result-box">', unsafe_allow_html=True)
                        st.markdown(format_pnr_result(st.session_state.pnr_result))
                        st.markdown('</div>', unsafe_allow_html=True)
                        if st.session_state.pnr_last_checked:
                            last_check = datetime.fromtimestamp(st.session_state.pnr_last_checked).strftime('%H:%M:%S')
                            st.caption(f"⏱️ Last checked: {last_check} IST (auto-refreshes every 5 min)")

            with tab2:
                st.markdown("### Live Train Status")
                train_no = st.text_input("Enter Train Number (3-5 digits)", key="rail_train")
                date_options = [f"{get_date_label(i)} ({get_date_for_offset(i)})" for i in range(5)]
                date_choice = st.selectbox("Select Date", date_options, index=0, key="rail_date")
                offset = 0
                for i in range(5):
                    if get_date_label(i) in date_choice: offset = i; break
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Get Live Status", key="train_live", use_container_width=True):
                        if not train_no or not train_no.isdigit() or not (3 <= len(train_no) <= 5):
                            st.error("Please enter a valid train number (3-5 digits).")
                        else:
                            with st.spinner("Fetching live status..."):
                                date_str = get_date_for_offset(offset)
                                data = get_live_train_status(train_no, date_str)
                                if data and isinstance(data, dict) and data.get('error'):
                                    st.error(f"❌ {data['error']}: {data.get('message', '')}")
                                elif data:
                                    st.session_state.train_result = data
                                    st.rerun()
                                else: st.error("❌ No data available.")
                with c2:
                    if st.button("🔄 Refresh Live Status", key="refresh_live", use_container_width=True):
                        if train_no and train_no.isdigit() and (3 <= len(train_no) <= 5):
                            with st.spinner("Refreshing live status..."):
                                date_str = get_date_for_offset(offset)
                                data = get_live_train_status(train_no, date_str)
                                if data and isinstance(data, dict) and data.get('error'):
                                    st.error(f"❌ {data['error']}: {data.get('message', '')}")
                                elif data:
                                    st.session_state.train_result = data
                                    st.rerun()
                                else: st.error("❌ No data available.")
                        else: st.warning("Please enter a valid train number first.")

                if st.session_state.train_result:
                    with st.container():
                        st.markdown('<div class="result-box">', unsafe_allow_html=True)
                        msg, _ = format_live_train_result(st.session_state.train_result)
                        st.markdown(msg)
                        st.markdown('</div>', unsafe_allow_html=True)

            with tab3:
                st.markdown("### Train Schedule / Route")
                train_no_sch = st.text_input("Enter Train Number (3-5 digits)", key="rail_sch")
                if 'sch_start' not in st.session_state: st.session_state.sch_start = 0
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Get Schedule", key="train_sch", use_container_width=True):
                        if not train_no_sch or not train_no_sch.isdigit() or not (3 <= len(train_no_sch) <= 5):
                            st.error("Please enter a valid train number.")
                        else:
                            with st.spinner("Fetching schedule..."):
                                data = get_train_schedule(train_no_sch)
                                if data and isinstance(data, dict) and data.get('error'): st.error(f"❌ {data['error']}")
                                elif data:
                                    st.session_state.sch_data = data
                                    st.session_state.sch_start = 0
                                    st.rerun()
                                else: st.error("❌ Schedule not found.")
                with c2:
                    if st.button("🔄 Refresh Schedule", key="refresh_sch", use_container_width=True):
                        if train_no_sch and train_no_sch.isdigit() and (3 <= len(train_no_sch) <= 5):
                            with st.spinner("Refreshing schedule..."):
                                data = get_train_schedule(train_no_sch)
                                if data and isinstance(data, dict) and data.get('error'): st.error(f"❌ {data['error']}")
                                elif data:
                                    st.session_state.sch_data = data
                                    st.session_state.sch_start = 0
                                    st.rerun()
                                else: st.error("❌ Schedule not found.")
                        else: st.warning("Please enter a valid train number first.")

                if st.session_state.sch_data:
                    data = st.session_state.sch_data
                    if isinstance(data, dict):
                        msg, pagination = format_schedule_result(data, st.session_state.sch_start)
                        with st.container():
                            st.markdown('<div class="result-box">', unsafe_allow_html=True)
                            st.markdown(msg)
                            st.markdown('</div>', unsafe_allow_html=True)
                        if pagination:
                            start, end, total = pagination
                            chunk = 20
                            if total > 0:
                                col1, col2, col3 = st.columns([1,2,1])
                                with col1:
                                    if start > 0:
                                        if st.button("◀ Previous", key="sch_prev"):
                                            st.session_state.sch_start = max(0, start - chunk)
                                            st.rerun()
                                with col2: st.write(f"Showing {start+1}-{end} of {total}")
                                with col3:
                                    if end < total:
                                        if st.button("Next ▶", key="sch_next"):
                                            st.session_state.sch_start = end
                                            st.rerun()
                    else: st.info("No schedule data available.")

            with tab4:
                st.markdown("### 📸 Passport Photo Maker")
                st.caption("Upload any photo → Auto remove background → Add black border → 35x45mm standard size")
                api_key = str(st.secrets.get("REMOVE_BG_API_KEY", "")).strip()
                if not api_key: api_key = str(os.environ.get("REMOVE_BG_API_KEY", "")).strip()
                if not api_key and "remove_bg_key" in st.session_state: api_key = str(st.session_state.remove_bg_key).strip()
                if not api_key:
                    st.error("❌ REMOVE_BG_API_KEY not found.")
                    st.info("Add to secrets.toml or .env")
                    manual_key = st.text_input("Or paste key here", type="password", key="manual_bg_key_input")
                    if manual_key and manual_key.strip():
                        st.session_state.remove_bg_key = manual_key.strip()
                        st.success("Key saved. Refreshing...")
                        st.rerun()
                    st.stop()
                else: st.success(f"✅ API Key ready: {api_key[:4]}...{api_key[-4:]}")

                photo_file = st.file_uploader("Upload Photo", type=["png", "jpg", "jpeg"], key="passport_photo_uploader")
                if photo_file:
                    st.image(photo_file, caption="Original Photo", width=250)
                    if st.button("✨ Process Passport Photo", type="primary", use_container_width=True, key="process_passport_btn"):
                        with st.spinner("Processing... (10-30 seconds)"):
                            try:
                                image_data = photo_file.read()
                                result = process_passport_image(image_data)
                                if result:
                                    st.success("✅ Passport Photo Ready!")
                                    st.image(result, caption="Background removed | Black border | 35x45mm", width=300)
                                    st.download_button("📥 Download Passport Photo", data=result,
                                        file_name=f"passport_{now_ist().strftime('%Y%m%d_%H%M%S')}.png",
                                        mime="image/png", use_container_width=True)
                                else: st.error("❌ Failed to process photo.")
                            except Exception as e: st.error(f"❌ Error: {str(e)[:200]}")

    # =====================================================================
    # VIEW: 🌤️ WEATHER
    # =====================================================================
    elif view == "🌤️ Weather":
        st.subheader("🌤️ Weather Information")

        qp_lat = st.query_params.get('__lat')
        qp_lon = st.query_params.get('__lon')
        if qp_lat and qp_lon:
            try:
                st.session_state.weather_lat = float(qp_lat)
                st.session_state.weather_lon = float(qp_lon)
            except: pass

        city = st.text_input("🏙️ Enter city name", value=st.session_state.weather_city,
                            placeholder="e.g., Tinsukia, New Delhi, Mumbai", key="weather_city_input")
        if city != st.session_state.weather_city: st.session_state.weather_city = city

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🌤️ Get Weather", key="weather_btn", use_container_width=True):
                if city:
                    with st.spinner(f"Fetching weather for {city}..."):
                        data = get_weather(city)
                        forecast = get_weather_forecast(city)
                        if data and 'error' not in data:
                            st.session_state.weather_data = data
                            if forecast and 'error' not in forecast: st.session_state.weather_forecast = forecast
                            st.rerun()
                        else: st.error(data.get('error', 'Error fetching weather'))
                else: st.warning("Please enter a city name.")
        with col2:
            if st.button("🔄 Refresh", key="refresh_weather", use_container_width=True):
                if city:
                    with st.spinner(f"Refreshing weather for {city}..."):
                        data = get_weather(city)
                        forecast = get_weather_forecast(city)
                        if data and 'error' not in data:
                            st.session_state.weather_data = data
                            if forecast and 'error' not in forecast: st.session_state.weather_forecast = forecast
                            st.rerun()
                        else: st.error(data.get('error', 'Error fetching weather'))
                else: st.warning("Please enter a city name.")
        with col3:
            st.empty()

        if st.session_state.weather_data and 'error' not in st.session_state.weather_data:
            data = st.session_state.weather_data

            # Detect weather condition for background
            weather_condition = str(data.get('weather', '')).lower()
            temp = data.get('temp', 25)
            is_night = False
            try:
                sunrise_ts = data.get('sunrise')
                sunset_ts = data.get('sunset')
                if sunrise_ts and sunset_ts:
                    now_ts = datetime.now().timestamp()
                    is_night = not (sunrise_ts <= now_ts <= sunset_ts)
            except:
                pass

            # Choose sky class
            sky_class = "w-sunny"
            if 'rain' in weather_condition or 'drizz' in weather_condition:
                sky_class = "w-rainy"
            elif 'cloud' in weather_condition:
                sky_class = "w-cloudy"
            elif 'thunder' in weather_condition or 'storm' in weather_condition:
                sky_class = "w-thunder"
            elif 'snow' in weather_condition or 'frost' in weather_condition or 'freez' in weather_condition:
                sky_class = "w-snowy"
            elif 'mist' in weather_condition or 'fog' in weather_condition or 'haz' in weather_condition:
                sky_class = "w-foggy"
            elif is_night:
                sky_class = "w-night"
            elif temp > 30:
                sky_class = "w-hot"

            # Build main weather card with dynamic class
            weather_html = f"""
            <style>
            @keyframes weather-float {{
                0%, 100% {{ transform: translateY(0px); }}
                50% {{ transform: translateY(-8px); }}
            }}
            @keyframes weather-glow {{
                0%, 100% {{ box-shadow: 0 4px 20px rgba(37, 99, 235, 0.15); }}
                50% {{ box-shadow: 0 8px 40px rgba(37, 99, 235, 0.3); }}
            }}
            @keyframes sun-pulse {{
                0%, 100% {{ transform: scale(1); opacity: 0.8; }}
                50% {{ transform: scale(1.15); opacity: 1; }}
            }}
            .weather-main-card {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border-radius: 24px; padding: 30px; color: white;
                box-shadow: 0 10px 40px rgba(102, 126, 234, 0.4);
                animation: weather-float 4s ease-in-out infinite, weather-glow 3s ease-in-out infinite;
                position: relative; overflow: hidden;
            }}
            .weather-main-card::before {{
                content: ''; position: absolute; top: -50%; right: -50%;
                width: 200%; height: 200%;
                background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 60%);
                animation: rotate 20s linear infinite;
            }}
            @keyframes rotate {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}
            .weather-temp-big {{ font-size: 4.5rem; font-weight: 800; line-height: 1; text-shadow: 0 4px 20px rgba(0,0,0,0.3); }}
            .weather-city {{ font-size: 1.8rem; font-weight: 700; margin-bottom: 4px; }}
            .weather-desc {{ font-size: 1.3rem; opacity: 0.95; }}
            .weather-detail-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-top: 20px; }}
            .weather-detail-item {{
                background: rgba(255,255,255,0.15); border-radius: 12px; padding: 12px;
                text-align: center; backdrop-filter: blur(10px);
            }}
            .weather-detail-icon {{ font-size: 1.5rem; margin-bottom: 4px; }}
            .weather-detail-label {{ font-size: 0.8rem; opacity: 0.8; }}
            .weather-detail-value {{ font-size: 1.1rem; font-weight: 700; }}
            .sunrise-sunset {{
                display: flex; justify-content: center; gap: 40px; margin-top: 16px;
                padding-top: 16px; border-top: 1px solid rgba(255,255,255,0.2);
            }}
            .sun-item {{ text-align: center; }}
            .sun-icon {{ font-size: 2rem; animation: sun-pulse 2s ease-in-out infinite; }}
            .sun-time {{ font-size: 1.2rem; font-weight: 700; }}
            .sun-label {{ font-size: 0.85rem; opacity: 0.8; }}
            </style>
            <div class="weather-main-card">
                <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; position: relative; z-index: 1;">
                    <div>
                        <div class="weather-city">{data['city']}, {data['country']}</div>
                        <div class="weather-desc">{data['weather'].title()}</div>
                        <div style="font-size: 0.9rem; opacity: 0.7; margin-top: 6px;">Updated: {format_datetime()}</div>
                    </div>
                    <div style="text-align: center;">
                        <div class="weather-temp-big">{data['temp']}°C</div>
                        <div style="font-size: 1rem; opacity: 0.9;">Feels like {data['feels_like']}°C</div>
                    </div>
                </div>
                <div class="weather-detail-row">
                    <div class="weather-detail-item">
                        <div class="weather-detail-icon">💧</div>
                        <div class="weather-detail-label">Humidity</div>
                        <div class="weather-detail-value">{data['humidity']}%</div>
                    </div>
                    <div class="weather-detail-item">
                        <div class="weather-detail-icon">🌬️</div>
                        <div class="weather-detail-label">Wind</div>
                        <div class="weather-detail-value">{data['wind_speed']} m/s</div>
                    </div>
                    <div class="weather-detail-item">
                        <div class="weather-detail-icon">📊</div>
                        <div class="weather-detail-label">Pressure</div>
                        <div class="weather-detail-value">{data['pressure']} hPa</div>
                    </div>
                    <div class="weather-detail-item">
                        <div class="weather-detail-icon">🌡️</div>
                        <div class="weather-detail-label">Feels Like</div>
                        <div class="weather-detail-value">{data['feels_like']}°C</div>
                    </div>
                </div>
            """

            if data.get('sunrise') and data.get('sunrise') != 'N/A':
                try:
                    from datetime import timezone as tz_utc
                    UTC = tz_utc.utc
                    sunrise_dt = datetime.fromtimestamp(data['sunrise'], tz=UTC).astimezone(IST)
                    sunset_dt = datetime.fromtimestamp(data['sunset'], tz=UTC).astimezone(IST)
                    sunrise = sunrise_dt.strftime('%I:%M %p')
                    sunset = sunset_dt.strftime('%I:%M %p')
                    weather_html += f'<div class="sunrise-sunset"><div class="sun-item"><div class="sun-icon">🌅</div><div class="sun-time">{sunrise}</div><div class="sun-label">Sunrise</div></div><div class="sun-item"><div class="sun-icon">🌇</div><div class="sun-time">{sunset}</div><div class="sun-label">Sunset</div></div></div>'
                except: pass

            weather_html += "</div>"
            st.markdown(weather_html, unsafe_allow_html=True)

            # Detailed Animated Weather Scene (background reflects weather)
            scene_html = f"""
            <style>
            .w-scene-wrap {{
                position: relative; width: 100%; height: 240px; border-radius: 20px; overflow: hidden;
                margin: 15px 0; box-shadow: 0 8px 32px rgba(0,0,0,0.25);
                transition: all 0.5s ease;
            }}
            .w-sky {{
                position: absolute; width: 100%; height: 100%; top: 0; left: 0;
                transition: background 1s ease;
            }}
            .w-sunny {{ background: linear-gradient(180deg, #4facfe 0%, #00f2fe 100%); }}
            .w-rainy {{ background: linear-gradient(180deg, #2c3e50 0%, #4a5568 100%); }}
            .w-cloudy {{ background: linear-gradient(180deg, #7f8c8d 0%, #95a5a6 100%); }}
            .w-thunder {{ background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%); }}
            .w-snowy {{ background: linear-gradient(180deg, #e0e7ff 0%, #c7d2fe 100%); }}
            .w-foggy {{ background: linear-gradient(180deg, #d5d8dc 0%, #aab7b8 100%); }}
            .w-night {{ background: linear-gradient(180deg, #0c1445 0%, #1a1a3a 100%); }}
            .w-hot {{ background: linear-gradient(180deg, #f7971e 0%, #ffd200 100%); }}

            @keyframes w-sun-pulse {{ 0%,100%{{transform:scale(1);opacity:0.9;}} 50%{{transform:scale(1.2);opacity:1;}} }}
            .w-sun {{
                position: absolute; top: 15px; right: 30px; width: 70px; height: 70px;
                background: radial-gradient(circle, #FFD700 0%, #FFA500 60%, transparent 100%);
                border-radius: 50%; animation: w-sun-pulse 3s ease-in-out infinite;
                box-shadow: 0 0 50px 15px rgba(255,215,0,0.4);
            }}
            .w-moon {{
                position: absolute; top: 20px; right: 40px; width: 50px; height: 50px;
                background: radial-gradient(circle, #f0f0f0 0%, #c0c0c0 100%);
                border-radius: 50%; box-shadow: 0 0 40px 10px rgba(200,200,200,0.3);
            }}

            @keyframes w-ray-spin {{ from{{transform:translate(-50%,-50%) rotate(0deg);}} to{{transform:translate(-50%,-50%) rotate(360deg);}} }}
            .w-ray {{ position: absolute; top: 50%; left: 50%; width: 100px; height: 3px; background: linear-gradient(90deg, transparent, #FFD700, transparent); transform-origin: center; animation: w-ray-spin 10s linear infinite; }}

            @keyframes w-cloud-move {{ from{{transform:translateX(-120px);}} to{{transform:translateX(calc(100% + 120px));}} }}
            .w-cloud {{
                position: absolute; background: rgba(255,255,255,0.85); border-radius: 40px;
                animation: w-cloud-move linear infinite;
            }}
            .w-cloud::before {{ content: ''; position: absolute; background: rgba(255,255,255,0.85); border-radius: 50%; }}
            .w-cloud::after {{ content: ''; position: absolute; background: rgba(255,255,255,0.85); border-radius: 50%; }}

            @keyframes w-rain-fall {{ from{{transform:translateY(-20px);opacity:0;}} 10%{{opacity:0.8;}} 90%{{opacity:0.8;}} to{{transform:translateY(260px);opacity:0;}} }}
            .w-rain {{ position: absolute; width: 2px; height: 14px; background: linear-gradient(180deg, transparent, #64b5f6); border-radius: 0 0 2px 2px; animation: w-rain-fall linear infinite; }}

            @keyframes w-lightning {{ 0%,90%,100%{{background:rgba(255,255,255,0);}} 91%{{background:rgba(255,255,255,0.25);}} 92%{{background:rgba(255,255,255,0);}} 93%{{background:rgba(255,255,255,0.4);}} 94%{{background:rgba(255,255,255,0);}} }}
            .w-lightning {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; animation: w-lightning 4s ease-in-out infinite; }}

            @keyframes w-snow-fall {{ from{{transform:translateY(-20px) rotate(0deg);opacity:0;}} 10%{{opacity:1;}} 90%{{opacity:1;}} to{{transform:translateY(260px) rotate(360deg);opacity:0;}} }}
            .w-snow {{ position: absolute; color: white; font-size: 13px; animation: w-snow-fall linear infinite; text-shadow: 0 0 4px rgba(255,255,255,0.8); }}

            @keyframes w-fog-drift {{ from{{transform:translateX(-50%);}} to{{transform:translateX(0%);}} }}
            .w-fog {{ position: absolute; width: 200%; height: 50px; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.5), transparent); animation: w-fog-drift linear infinite; }}

            .w-ground {{
                position: absolute; bottom: 0; left: 0; width: 100%; height: 35px;
                background: linear-gradient(180deg, #2d5016 0%, #1a3009 100%);
                border-radius: 50% 50% 0 0 / 15px 15px 0 0;
            }}
            @keyframes w-tree-sway {{ 0%,100%{{transform:rotate(-4deg);}} 50%{{transform:rotate(4deg);}} }}
            .w-tree {{ position: absolute; bottom: 28px; font-size: 22px; animation: w-tree-sway 3s ease-in-out infinite; }}
            @keyframes w-hot-haze {{ 0%,100%{{opacity:0.6;}} 50%{{opacity:1;}} }}
            .w-haze {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: radial-gradient(ellipse, rgba(255,200,100,0.2), transparent); animation: w-hot-haze 2s ease-in-out infinite; }}
            </style>
            <div class="w-scene-wrap">
                <div class="w-sky {sky_class}">
            """

            if 'rain' in weather_condition or 'drizz' in weather_condition:
                scene_html += '<div class="w-lightning"></div>'
                for i in range(30):
                    scene_html += f'<div class="w-rain" style="left:{(i*3.3)%100}%;animation-duration:{0.4+(i%3)*0.15}s;animation-delay:{(i*0.1)%1.5}s;"></div>'
                scene_html += '<div class="w-cloud" style="top:12px;left:-100px;width:90px;height:32px;animation-duration:22s;"><div style="position:absolute;top:-14px;left:12px;width:32px;height:32px;"></div><div style="position:absolute;top:-10px;left:38px;width:24px;height:24px;"></div></div>'
                scene_html += '<div class="w-cloud" style="top:22px;left:-100px;width:110px;height:38px;animation-duration:28s;animation-delay:6s;"><div style="position:absolute;top:-16px;left:18px;width:38px;height:38px;"></div><div style="position:absolute;top:-12px;left:48px;width:28px;height:28px;"></div></div>'
            elif 'cloud' in weather_condition:
                scene_html += '<div class="w-sun" style="opacity:0.35;"></div>'
                for i in range(5):
                    scene_html += f'<div class="w-cloud" style="top:{12+(i%2)*18}px;left:-100px;width:{70+(i%2)*30}px;height:{28+(i%2)*10}px;animation-duration:{20+i*6}s;animation-delay:{i*4}s;"><div style="position:absolute;top:-{12+(i%2)*6}px;left:{14+(i%2)*6}px;width:{30+(i%2)*12}px;height:{30+(i%2)*12}px;"></div><div style="position:absolute;top:-{8+(i%2)*4}px;left:{36+(i%2)*10}px;width:{22+(i%2)*8}px;height:{22+(i%2)*8}px;"></div></div>'
            elif 'clear' in weather_condition or 'sun' in weather_condition:
                if is_night:
                    scene_html += '<div class="w-moon"></div>'
                    for i in range(20):
                        scene_html += f'<div style="position:absolute;top:{5+(i*4)%70}%;left:{3+(i*7)%90}%;width:3px;height:3px;background:white;border-radius:50%;box-shadow:0 0 6px rgba(255,255,255,0.8);animation:twinkle-stars {2+(i%3)}s ease-in-out infinite alternate;"></div>'
                else:
                    scene_html += '<div class="w-sun">'
                    for angle in range(0, 360, 30):
                        scene_html += f'<div class="w-ray" style="transform:translate(-50%,-50%) rotate({angle}deg);"></div>'
                    scene_html += '</div>'
                    for i in range(3):
                        scene_html += f'<div class="w-cloud" style="top:{18+i*14}px;left:-100px;width:65px;height:24px;animation-duration:{24+i*6}s;animation-delay:{i*5}s;opacity:0.6;"><div style="position:absolute;top:-10px;left:10px;width:26px;height:26px;"></div></div>'
            elif 'thunder' in weather_condition or 'storm' in weather_condition:
                scene_html += '<div class="w-lightning" style="animation-duration:2.5s;"></div>'
                for i in range(25):
                    scene_html += f'<div class="w-rain" style="left:{(i*4)%100}%;animation-duration:{0.3+(i%3)*0.12}s;animation-delay:{(i*0.08)%1.2}s;background:linear-gradient(180deg,transparent,#90caf9);"></div>'
                scene_html += '<div class="w-cloud" style="top:8px;left:-100px;width:100px;height:38px;background:#546e7a;animation-duration:32s;"><div style="position:absolute;top:-16px;left:16px;width:40px;height:40px;background:#546e7a;"></div><div style="position:absolute;top:-12px;left:46px;width:32px;height:32px;background:#546e7a;"></div></div>'
            elif 'snow' in weather_condition or 'frost' in weather_condition or 'freez' in weather_condition:
                snowflakes = ['&#10052;', '&#10053;', '&#10054;', '&#10042;', '&#10043;']
                for i in range(40):
                    scene_html += f'<div class="w-snow" style="left:{(i*2.5)%100}%;font-size:{10+(i%4)*3}px;animation-duration:{2+(i%4)*1.2}s;animation-delay:{(i*0.15)%3}s;">{snowflakes[i%5]}</div>'
                scene_html += '<div class="w-cloud" style="top:8px;left:-100px;width:80px;height:30px;background:rgba(255,255,255,0.8);animation-duration:26s;"><div style="position:absolute;top:-12px;left:12px;width:34px;height:34px;background:rgba(255,255,255,0.8);"></div></div>'
            elif 'mist' in weather_condition or 'fog' in weather_condition or 'haz' in weather_condition:
                for i in range(6):
                    scene_html += f'<div class="w-fog" style="top:{10+i*30}px;animation-duration:{12+i*4}s;animation-delay:{i*2}s;opacity:{0.25+(i%3)*0.15};"></div>'
            elif is_night:
                scene_html += '<div class="w-moon"></div>'
                for i in range(30):
                    scene_html += f'<div style="position:absolute;top:{5+(i*3)%70}%;left:{2+(i*5)%90}%;width:{2+(i%3)}px;height:{2+(i%3)}px;background:white;border-radius:50%;box-shadow:0 0 6px rgba(255,255,255,0.8);animation:twinkle-stars {2+(i%3)}s ease-in-out infinite alternate;"></div>'
            elif temp > 30:
                scene_html += '<div class="w-sun"></div>'
                scene_html += '<div class="w-haze"></div>'
                for i in range(5):
                    scene_html += f'<div style="position:absolute;bottom:{20+i*8}%;left:10%;width:80%;height:4px;background:linear-gradient(90deg,transparent,rgba(255,200,100,0.3),transparent);border-radius:50%;animation:heat-wave {2+i*0.5}s ease-in-out infinite;"></div>'
            else:
                # default sunny
                scene_html += '<div class="w-sun">'
                for angle in range(0, 360, 45):
                    scene_html += f'<div class="w-ray" style="transform:translate(-50%,-50%) rotate({angle}deg);"></div>'
                scene_html += '</div>'
                for i in range(2):
                    scene_html += f'<div class="w-cloud" style="top:{20+i*12}px;left:-100px;width:55px;height:20px;animation-duration:{22+i*5}s;animation-delay:{i*6}s;opacity:0.5;"><div style="position:absolute;top:-8px;left:8px;width:22px;height:22px;"></div></div>'

            # ground and trees
            scene_html += '<div class="w-ground"></div>'
            scene_html += '<div class="w-tree" style="left:5%;">🌲</div>'
            scene_html += '<div class="w-tree" style="left:20%;animation-delay:0.6s;">🌳</div>'
            scene_html += '<div class="w-tree" style="left:65%;animation-delay:1.2s;">🌲</div>'
            scene_html += '<div class="w-tree" style="left:80%;animation-delay:1.8s;">🌳</div>'
            scene_html += '</div></div>'

            st.markdown(scene_html, unsafe_allow_html=True)

            if data.get('icon'):
                icon_url = f"https://openweathermap.org/img/wn/{data['icon']}@4x.png"
                c1, c2, c3 = st.columns([1,1,1])
                with c2:
                    st.image(icon_url, caption=data['weather'].title(), width=120)

            # 5-Day Forecast
            if st.session_state.weather_forecast and 'error' not in st.session_state.weather_forecast:
                forecast = st.session_state.weather_forecast
                st.markdown("---")
                st.subheader(f"📅 5-Day Forecast for {forecast.get('city', city)}")

                forecast_data = forecast.get('forecast', [])
                if forecast_data:
                    cols = st.columns(min(5, len(forecast_data)))
                    for idx, day in enumerate(forecast_data):
                        with cols[idx]:
                            date_obj = datetime.strptime(day['date'], '%Y-%m-%d')
                            day_name = date_obj.strftime('%a, %d %b')
                            icon_url = f"https://openweathermap.org/img/wn/{day['icon']}@2x.png" if day.get('icon') else ""

                            st.markdown(f"""
                            <style>
                            @keyframes forecast-bounce {{
                                0%, 100% {{ transform: translateY(0); }}
                                50% {{ transform: translateY(-5px); }}
                            }}
                            .forecast-card-{idx} {{
                                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                                border-radius: 20px; padding: 18px; text-align: center; color: white;
                                box-shadow: 0 6px 20px rgba(102, 126, 234, 0.3);
                                animation: forecast-bounce 3s ease-in-out infinite;
                                animation-delay: {idx * 0.3}s;
                            }}
                            </style>
                            <div class="forecast-card-{idx}">
                                <div style="font-size: 0.9rem; font-weight: 600; margin-bottom: 8px;">{day_name}</div>
                                <img src="{icon_url}" style="width: 60px; height: 60px; margin: 5px 0;">
                                <div style="font-size: 1.8rem; font-weight: 700;">{day['temp']}°C</div>
                                <div style="font-size: 0.75rem; margin: 4px 0;">{day['description']}</div>
                                <div style="font-size: 0.8rem; margin-top: 8px; opacity: 0.9;">
                                    🔺 {day['max_temp']}° / 🔻 {day['min_temp']}°
                                </div>
                                <div style="font-size: 0.75rem; margin-top: 6px; opacity: 0.85;">
                                    💧 {day['humidity']}% | 🌬️ {day['wind']} m/s
                                </div>
                            </div>
                            """, unsafe_allow_html=True)

                    # Forecast trend chart
                    fig_forecast = go.Figure()
                    dates = [datetime.strptime(d['date'], '%Y-%m-%d').strftime('%d %b') for d in forecast_data]
                    fig_forecast.add_trace(go.Scatter(x=dates, y=[d['max_temp'] for d in forecast_data],
                        mode='lines+markers', name='Max Temp', line=dict(color='#ff6b6b', width=3),
                        marker=dict(size=10)))
                    fig_forecast.add_trace(go.Scatter(x=dates, y=[d['min_temp'] for d in forecast_data],
                        mode='lines+markers', name='Min Temp', line=dict(color='#4ecdc4', width=3),
                        marker=dict(size=10)))
                    fig_forecast.add_trace(go.Scatter(x=dates, y=[d['temp'] for d in forecast_data],
                        mode='lines+markers', name='Avg Temp', line=dict(color='#ffe66d', width=3),
                        marker=dict(size=10)))
                    fig_forecast.update_layout(
                        title="📈 5-Day Temperature Trend", height=400,
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
                        font=dict(size=12), title_font_size=16)
                    st.plotly_chart(fig_forecast, use_container_width=True)

                    with st.expander("📋 Detailed Forecast Data", expanded=False):
                        forecast_df = pd.DataFrame(forecast_data)
                        forecast_df['date'] = pd.to_datetime(forecast_df['date']).dt.strftime('%d-%m-%Y')
                        forecast_df.columns = ['Date', 'Avg Temp (°C)', 'Min (°C)', 'Max (°C)', 'Weather', 'Description', 'Icon', 'Humidity (%)', 'Wind (m/s)', 'Pressure (hPa)']
                        st.dataframe(forecast_df.drop(columns=['Icon']), use_container_width=True)

        elif st.session_state.weather_data and 'error' in st.session_state.weather_data:
            st.error(st.session_state.weather_data['error'])
        else:
            st.info("Enter a city name and click 'Get Weather' to see detailed weather information.")

    # Footer
    st.markdown("""
    <div class='pro-footer no-print'>
        🚂 AI EQMS Hub Pro • Created by Sharique<br>
        © 2026 All Rights Reserved
    </div>
    """, unsafe_allow_html=True)

# =====================================================================
# Run the app
# =====================================================================
if __name__ == "__main__":
    main()
