user_pasted_clipboard_long_content_as_file_#=======================================.txt

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
        # Step 1: Geocode to get lat, lon, name, state, country
        geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city_name}&limit=1&appid={WEATHER_API_KEY}"
        geo_resp = requests.get(geo_url, timeout=10)
        lat, lon, found_name, country, state = None, None, city_name, '', ''
        if geo_resp.status_code == 200:
            geo_data = geo_resp.json()
            if geo_data and len(geo_data) > 0:
                lat = geo_data[0].get('lat')
                lon = geo_data[0].get('lon')
                found_name = geo_data[0].get('name', city_name)
                country = geo_data[0].get('country', '')
                state = geo_data[0].get('state', '')

        # Step 2: Get weather by coordinates (most accurate)
        if lat and lon:
            coord_url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric"
            coord_resp = requests.get(coord_url, timeout=10)
            if coord_resp.status_code == 200:
                data = coord_resp.json()
                return {'city': found_name, 'country': country, 'state': state,
                    'temp': data.get('main', {}).get('temp', 'N/A'), 'feels_like': data.get('main', {}).get('feels_like', 'N/A'),
                    'humidity': data.get('main', {}).get('humidity', 'N/A'), 'pressure': data.get('main', {}).get('pressure', 'N/A'),
                    'weather': data.get('weather', [{}])[0].get('description', 'N/A'),
                    'icon': data.get('weather', [{}])[0].get('icon', ''),
                    'wind_speed': data.get('wind', {}).get('speed', 'N/A'), 'wind_deg': data.get('wind', {}).get('deg', 'N/A'),
                    'sunrise': data.get('sys', {}).get('sunrise', 'N/A'), 'sunset': data.get('sys', {}).get('sunset', 'N/A'),
                    'lat': lat, 'lon': lon}

        # Fallback: direct city name API (no state available)
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={WEATHER_API_KEY}&units=metric"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {'city': data.get('name', city_name), 'country': data.get('sys', {}).get('country', ''), 'state': state,
                'temp': data.get('main', {}).get('temp', 'N/A'), 'feels_like': data.get('main', {}).get('feels_like', 'N/A'),
                'humidity': data.get('main', {}).get('humidity', 'N/A'), 'pressure': data.get('main', {}).get('pressure', 'N/A'),
                'weather': data.get('weather', [{}])[0].get('description', 'N/A'),
                'icon': data.get('weather', [{}])[0].get('icon', ''),
                'wind_speed': data.get('wind', {}).get('speed', 'N/A'), 'wind_deg': data.get('wind', {}).get('deg', 'N/A'),
                'sunrise': data.get('sys', {}).get('sunrise', 'N/A'), 'sunset': data.get('sys', {}).get('sunset', 'N/A'),
                'lat': data.get('coord', {}).get('lat'), 'lon': data.get('coord', {}).get('lon')}

        return {'error': 'City not found. Try a nearby major city.'}
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
        # Fallback: geocoding then forecast by coords
        geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city_name}&limit=1&appid={WEATHER_API_KEY}"
        geo_resp = requests.get(geo_url, timeout=10)
        if geo_resp.status_code == 200:
            geo_data = geo_resp.json()
            if geo_data and len(geo_data) > 0:
                lat = geo_data[0].get('lat')
                lon = geo_data[0].get('lon')
                found_name = geo_data[0].get('name', city_name)
                country = geo_data[0].get('country', '')
                if lat and lon:
                    coord_url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric"
                    coord_resp = requests.get(coord_url, timeout=10)
                    if coord_resp.status_code == 200:
                        data = coord_resp.json()
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
                        return {'forecast': result, 'city': found_name, 'country': country}
        return {'error': 'City not found. Try a nearby major city.'}
    except Exception as e: return {'error': f'Error fetching forecast: {str(e)}'}

def get_weather_by_coords(lat, lon):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {'city': data.get('name', 'Unknown'), 'country': data.get('sys', {}).get('country', ''), 'state': '',
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
    msg += f"**From:** {data.get('source', 'N/A')} → {data.ge
