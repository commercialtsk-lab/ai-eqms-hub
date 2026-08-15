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
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
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

# ========== TIMEZONE (IST) ==========
def now_ist():
    return datetime.now()

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
    'view_mode': "📋 Data Table",
    'select_all': False,
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
        '•': '-', '·': '-', '‘': "'", '’': "'",
        '“': '"', '”': '"', '–': '-', '—': '-',
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

# ========== GEMINI EXTRACTION (Simplified) ==========
def gemini_universal_parser(input_data, input_type, mime_type, progress_callback=None):
    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}'

    system_prompt = """
You are TSKEQ Bot's AI extraction engine. Extract the following fields from the input:
PNR, T_N, CLASS, DOJ (DD-MM-YYYY), FROM, TO, BOARDING, PASS_NAME, PASS_PH, T_BERTHS, PURPOSE, ADDRESS, DIARY_NO, RECOMMENDATION, DESIGNATION, VIP_STATUS, APPLICATION_DATE, RAILWAY_ZONE, PREFERENCE, PHONE_NUBER, WARRANT_NO

Return ONLY a valid JSON array. No explanations.
"""
    parts = []
    if input_type in ['image', 'pdf']:
        mime = mime_type or ("image/jpeg" if input_type == 'image' else "application/pdf")
        parts.append({"inline_data": {"mime_type": mime, "data": input_data}})
        parts.append({"text": system_prompt})
    elif input_type == 'audio':
        mime = mime_type or "audio/ogg"
        parts.append({"inline_data": {"mime_type": mime, "data": input_data}})
        parts.append({"text": system_prompt})
    elif input_type == 'text':
        parts.append({"text": system_prompt + "\n\nINPUT DATA:\n" + input_data})
    else:
        return {'error': 'Unsupported type'}

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
        if not data.get('candidates'):
            return {'error': 'Empty response from Gemini'}
        response_text = data['candidates'][0]['content']['parts'][0]['text']
        
        # Extract JSON
        json_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', response_text)
        if not json_match:
            return {'error': 'No JSON found in response'}
        
        json_str = json_match.group(0)
        records = json.loads(json_str)
        if isinstance(records, dict):
            records = [records]
        
        # Process records
        cleaned = []
        for rec in records:
            pnr = clean_pnr(rec.get('PNR', ''))
            if pnr:
                rec['PNR'] = pnr
                if rec.get('PASS_PH'):
                    rec['PASS_PH'] = clean_phone(rec['PASS_PH'])
                if rec.get('DOJ'):
                    rec['DOJ'] = parse_date(rec['DOJ'])
                cleaned.append(rec)
        
        return {'records': cleaned, 'count': len(cleaned)}
    except Exception as e:
        return {'error': f'Parser Error: {e}'}

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
            'view_url': f"https://drive.google.com/file/d/{file_id}/view",
            'print_url': f"https://drive.google.com/file/d/{file_id}/preview",
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ========== SAVE TO SHEET ==========
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
        next_sn = len(all_data) - 3
        for rec in records:
            pnr = clean_pnr(rec.get('PNR', ''))
            if not pnr or pnr in existing_pnrs:
                skipped += 1
                continue
            row = [
                next_sn, pnr, rec.get('FROM', ''), rec.get('TO', ''), rec.get('BOARDING', ''),
                rec.get('T_N', ''), rec.get('CLASS', ''), rec.get('DOJ', ''), rec.get('PASS_NAME', ''),
                rec.get('PASS_PH', ''), rec.get('T_BERTHS', 1), rec.get('PURPOSE', ''), rec.get('ADDRESS', ''),
                rec.get('DIARY_NO', ''), rec.get('RECOMMENDATION', ''), rec.get('DESIGNATION', ''),
                rec.get('PHONE_NUBER', ''), rec.get('VIP_STATUS', ''), rec.get('WARRANT_NO', ''),
                format_datetime(), rec.get('APPLICATION_DATE', ''), rec.get('RAILWAY_ZONE', ''), rec.get('PREFERENCE', 'General')
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
        return f"EQ Sheet has {total} records."
    except Exception:
        return "Sheet data temporarily unavailable."

def chat_with_gemini(user_message, chat_history):
    try:
        model = init_gemini()
        context = get_sheet_context()
        system_prompt = f"""You are TSKEQ Bot - a railway EQ assistant. 
Sheet Context: {context}
Previous conversation: {chat_history[-10:]}
User: {user_message}
Assistant:"""
        response = model.generate_content(system_prompt)
        return response.text
    except Exception as e:
        return f"⚠️ Error: {str(e)}"

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
        success = "#3fb950"
        button_bg = "#21262d"
        button_text = "#e6edf3"
        button_border = "#30363d"
    else:
        bg = "#f6f8fa"
        card_bg = "#ffffff"
        text_color = "#1f2328"
        text_secondary = "#656d76"
        border = "#d0d7de"
        input_bg = "#ffffff"
        accent = "#0969da"
        success = "#1a7f37"
        button_bg = "#f6f8fa"
        button_text = "#1f2328"
        button_border = "#d0d7de"

    css = f"""
    <style>
        .stApp {{ background-color: {bg} !important; }}
        [data-testid="stSidebar"] {{
            background-color: {card_bg} !important;
            border-right: 1px solid {border} !important;
        }}
        [data-testid="stSidebar"] .stMarkdown p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] .stTextInput label,
        [data-testid="stSidebar"] .stSelectbox label,
        [data-testid="stSidebar"] .stDateInput label,
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
        }}
        .stTextInput input, .stNumberInput input,
        .stDateInput input, .stTextArea textarea,
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
        .stDataFrame, [data-testid="stDataFrame"],
        .stDataFrame table, [data-testid="stDataFrame"] table,
        .stDataFrame thead, [data-testid="stDataFrame"] thead,
        .stDataFrame tbody, [data-testid="stDataFrame"] tbody,
        .stDataFrame th, [data-testid="stDataFrame"] th,
        .stDataFrame td, [data-testid="stDataFrame"] td {{
            background-color: {card_bg} !important;
            color: {text_color} !important;
            border-color: {border} !important;
        }}
        .stDataFrame th, [data-testid="stDataFrame"] th {{
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
        @media print {{
            body * {{ visibility: hidden; }}
            .print-area, .print-area * {{ visibility: visible; }}
            .print-area {{ position: absolute; left: 0; top: 0; width: 100%; }}
            .stApp, header, footer, .stSidebar, .stButton, .stExpander, .stMarkdown, .stCaption {{
                display: none !important;
            }}
        }}
        * {{
            transition: background-color 0.2s ease, color 0.2s ease, border-color 0.2s ease;
        }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# ========== WHATSAPP SHARE ==========
def build_whatsapp_message(sheet_name, selected_count, pnrs):
    now_str = format_datetime()
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
    apply_theme(st.session_state.dark_mode)

    # ---- SIDEBAR ----
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center; margin-bottom:10px; font-size:1.3rem; line-height:1.8;">
            <span style="color:#FF9933;">🟠 नमस्ते आपका स्वागत है</span><br>
            <span style="color:#FFFFFF;">⚪ हम भारत के लोग</span><br>
            <span style="color:#138808; font-weight:bold;">🟢 जय हिंद</span>
        </div>
        """, unsafe_allow_html=True)

        now = datetime.now()
        st.caption(f"📅 {format_date()}  •  🕐 {format_time()} IST")

        dark_mode = st.toggle("🌙 Dark Mode", value=st.session_state.dark_mode, key="sidebar_theme")
        if dark_mode != st.session_state.dark_mode:
            st.session_state.dark_mode = dark_mode
            st.rerun()

        with st.expander("🔄 Sync & Status", expanded=True):
            if st.button("🔄 Sync Now", use_container_width=True):
                st.cache_data.clear()
                st.session_state.last_refresh = time.time()
                log_activity("🔄 Manual sync")
                st.rerun()
            st.caption(f"Last sync: {format_time()} IST")

        sheet_link = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
        st.markdown(f'<a href="{sheet_link}" target="_blank" class="sheet-link-btn">📊 Open Google Sheet</a>', unsafe_allow_html=True)

        with st.expander("📤 Upload & Process", expanded=True):
            st.caption("Image • PDF • Text • Audio")
            file_type_choice = st.selectbox("File type", ["Image", "PDF", "Text", "Audio"], index=0)
            
            # ===== TEXT INPUT BOX =====
            if file_type_choice == "Text":
                text_input = st.text_area("📝 Paste or type your text here", height=200, 
                                         placeholder="Paste text from documents, emails, or handwritten notes...")
                uploaded_file = None
                if text_input:
                    st.success(f"✓ {len(text_input)} characters ready for processing")
            else:
                uploaded_file = st.file_uploader(
                    "Choose a file",
                    type=['png', 'jpg', 'jpeg', 'pdf', 'mp3', 'wav', 'ogg', 'm4a'],
                    label_visibility="collapsed"
                )
                # ===== AUDIO PLAYER =====
                if uploaded_file and file_type_choice == "Audio":
                    st.audio(uploaded_file, format='audio/mp3')
                text_input = ""

            if st.button("🚀 Process & Save", use_container_width=True, type="primary"):
                if file_type_choice == "Text":
                    if text_input.strip():
                        input_data = text_input
                        input_type = 'text'
                        mime = 'text/plain'
                    else:
                        st.warning("⚠️ Please enter some text.")
                        st.stop()
                else:
                    if not uploaded_file:
                        st.warning("⚠️ Please select a file.")
                        st.stop()
                    file_bytes = uploaded_file.read()
                    input_data = base64.b64encode(file_bytes).decode('utf-8')
                    if file_type_choice == "Image":
                        input_type = 'image'
                        mime = uploaded_file.type or 'image/jpeg'
                    elif file_type_choice == "PDF":
                        input_type = 'pdf'
                        mime = 'application/pdf'
                    else:
                        input_type = 'audio'
                        mime = uploaded_file.type or 'audio/ogg'

                try:
                    with st.spinner("AI is reading the file..."):
                        parse_result = gemini_universal_parser(input_data, input_type, mime)

                        if 'error' in parse_result:
                            st.error(f"❌ {parse_result['error']}")
                        else:
                            st.success(f"✅ Extracted {parse_result['count']} record(s)")
                            if parse_result.get('records'):
                                with st.expander("Preview extracted data"):
                                    st.dataframe(pd.DataFrame(parse_result['records']), use_container_width=True)

                            gc = init_sheets()
                            eq_sheet = gc.open_by_key(SHEET_ID).worksheet("EQ")
                            save_res = save_to_sheet(eq_sheet, parse_result['records'])

                            if 'error' in save_res:
                                st.error(f"❌ Save error: {save_res['error']}")
                            else:
                                st.success(f"✅ Saved {save_res['saved']} new • {save_res['skipped']} skipped")

                                if uploaded_file:
                                    drive_res = upload_to_drive(file_bytes, uploaded_file.name, mime)
                                    if drive_res['success']:
                                        st.success(f"📁 Drive: {drive_res['name']}")
                                        st.session_state.last_uploaded_file = uploaded_file.name
                                        st.session_state.last_uploaded_view_url = drive_res.get('view_url')
                                        st.session_state.last_uploaded_print_url = drive_res.get('print_url')
                                        st.session_state.upload_success = True
                                        st.session_state.last_upload_time = format_time()
                                        log_activity(f"✅ {uploaded_file.name} → {save_res['saved']} records")

                                st.cache_data.clear()
                                time.sleep(0.5)
                                st.rerun()
                except Exception as e:
                    st.error(f"❌ Processing error: {e}")
                    log_activity(f"❌ Process: {str(e)[:40]}")

        if st.session_state.upload_success and st.session_state.last_uploaded_file:
            with st.expander("📄 Last Uploaded File", expanded=True):
                st.markdown(f"""
                <div class="file-card">
                    <div class="file-card-title">📄 {st.session_state.last_uploaded_file}</div>
                    <div class="file-card-meta">Uploaded at {st.session_state.get('last_upload_time', '—')} IST</div>
                </div>
                """, unsafe_allow_html=True)
                if st.session_state.last_uploaded_view_url:
                    st.link_button("👁️ View", st.session_state.last_uploaded_view_url, use_container_width=True)
                if st.session_state.last_uploaded_print_url:
                    st.link_button("🖨️ Print", st.session_state.last_uploaded_print_url, use_container_width=True)
                if st.button("🗑️ Clear History", use_container_width=True):
                    st.session_state.last_uploaded_file = None
                    st.session_state.last_uploaded_view_url = None
                    st.session_state.last_uploaded_print_url = None
                    st.session_state.upload_success = False
                    st.rerun()

        with st.expander("📋 Activity Log", expanded=False):
            if st.session_state.activity_log:
                for log in reversed(st.session_state.activity_log[-15:]):
                    st.caption(f"{log.get('timestamp', '')} — {log.get('action', '')}")
            else:
                st.caption("No activity yet")

        st.markdown("---")

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

            def update_pnr():
                st.session_state.pnr_val = st.session_state._pnr_input
                st.session_state.current_page = 1
            def update_train():
                st.session_state.train_val = st.session_state._train_input
                st.session_state.current_page = 1

            pnr_input = st.text_input(
                "PNR (partial)",
                value=st.session_state.pnr_val,
                key="_pnr_input",
                on_change=update_pnr
            )
            train_input = st.text_input(
                "Train (partial)",
                value=st.session_state.train_val,
                key="_train_input",
                on_change=update_train
            )

        df_raw = load_sheet_data_cached(sheet_choice, SHEET_ID)
        filtered_df = df_raw.copy() if not df_raw.empty else pd.DataFrame()

        if not filtered_df.empty:
            pnr_col_idx = config.get("pnr_col")
            train_col_idx = config.get("train_col")

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

        def set_view_mode():
            st.session_state.view_mode = st.session_state._view_radio
        
        view = st.radio(
            "View Mode",
            ["📋 Data Table", "📊 Dashboard", "💬 Chat"],
            index=["📋 Data Table", "📊 Dashboard", "💬 Chat"].index(st.session_state.view_mode)
            if st.session_state.view_mode in ["📋 Data Table", "📊 Dashboard", "💬 Chat"] else 0,
            key="_view_radio",
            on_change=set_view_mode
        )

    # ========== MAIN AREA ==========
    top_c1, top_c2, top_c3 = st.columns([3, 2, 2])
    with top_c1:
        st.markdown("<h1 style='font-size:22px; font-weight:700; margin:0;'>🚂 AI EQMS Hub Pro</h1>", unsafe_allow_html=True)
    with top_c2:
        st.markdown(f"<div style='padding-top:6px;'><span class='status-pill status-live'>● Live</span> &nbsp; <span style='font-size:13px;'>Sync {format_time()} IST</span></div>", unsafe_allow_html=True)
    with top_c3:
        main_theme = st.toggle("🌙 Dark", value=st.session_state.dark_mode, key="main_theme")
        if main_theme != st.session_state.dark_mode:
            st.session_state.dark_mode = main_theme
            st.rerun()

    st.caption(f"Enterprise Railway EQ Management  •  {format_date()}  •  {format_time()} IST")
    st.markdown("---")

    # ========== CHAT ==========
    if view == "💬 Chat":
        st.subheader("💬 Chat with TSKEQ Bot")
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

        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    # ========== DASHBOARD ==========
    elif view == "📊 Dashboard":
        st.subheader("📊 Analytics Dashboard")
        
        if not filtered_df.empty:
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric("Total Records", len(filtered_df))
            with m2:
                train_col = next((c for c in filtered_df.columns if 'T/N' in str(c).upper()), None)
                unique_trains = filtered_df[train_col].nunique() if train_col else 0
                st.metric("Unique Trains", unique_trains)
            with m3:
                expired = sum(1 for _, r in filtered_df.iterrows() if is_expired(r.get('DOJ', '')))
                st.metric("Expired DOJ", expired)
            with m4:
                berth_col = next((c for c in filtered_df.columns if 'BERTH' in str(c).upper()), None)
                total_berths = 0
                if berth_col:
                    total_berths = pd.to_numeric(filtered_df[berth_col], errors='coerce').sum()
                st.metric("Total Berths", int(total_berths) if total_berths else 0)
            
            st.markdown("---")
            
            # Pie chart and histogram
            col1, col2 = st.columns(2)
            with col1:
                train_col = next((c for c in filtered_df.columns if 'T/N' in str(c).upper()), None)
                if train_col and filtered_df[train_col].notna().any():
                    train_counts = filtered_df[train_col].value_counts().head(10).reset_index()
                    train_counts.columns = ['Train', 'Count']
                    fig = px.pie(train_counts, names='Train', values='Count', title="Top 10 Trains", hole=0.4)
                    fig.update_layout(height=350, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True)
            with col2:
                berth_col = next((c for c in filtered_df.columns if 'BERTH' in str(c).upper()), None)
                if berth_col:
                    berth_vals = pd.to_numeric(filtered_df[berth_col], errors='coerce').dropna()
                    if not berth_vals.empty:
                        fig = px.histogram(berth_vals, nbins=10, title="Berths Distribution",
                                           labels={'value': 'Berths', 'count': 'Count'})
                        fig.update_layout(height=350, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                        st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data for charts. Adjust filters or select another sheet.")

    # ========== DATA TABLE ==========
    else:
        st.subheader(f"📋 {sheet_choice}  —  {len(filtered_df)} rows")

        if st.button("🔄 Refresh Data", use_container_width=False):
            st.cache_data.clear()
            st.session_state.last_refresh = time.time()
            log_activity("🔄 Manual refresh from main")
            st.rerun()

        if filtered_df.empty:
            st.info("No data to show. Clear filters or select another sheet.")
        else:
            page_size = st.selectbox("Rows per page", [15, 25, 50, 100], index=1, key="page_size")
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

            edited_page = st.data_editor(
                display_df,
                use_container_width=True,
                height=400,
                column_config={"Select": st.column_config.CheckboxColumn("Select", width="small")},
                key=f"editor_{sheet_choice}_{st.session_state.current_page}"
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
            st.markdown("**⚡ Quick Actions**")

            a1, a2, a3, a4, a5 = st.columns(5)

            with a1:
                if st.button("💾 Save Edits", use_container_width=True):
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
                                sheet.update(f"A{sheet_row_num}:{col_letter}{sheet_row_num}", [row_data])
                            st.toast("✅ Saved!", icon="💾")
                            log_activity(f"💾 Saved {len(data_list)} rows")
                            st.cache_data.clear()
                            time.sleep(0.3)
                            st.rerun()
                    except Exception as e:
                        st.error(f"Save error: {e}")

            with a2:
                if st.button("➕ Add Row", use_container_width=True):
                    try:
                        gc = init_sheets()
                        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                        all_data = sheet.get_all_values()
                        num_cols = len(all_data[0]) if all_data else 1
                        blank_row = [''] * num_cols
                        blank_row[0] = len(all_data) - start_row + 2
                        sheet.append_row(blank_row)
                        st.toast("✅ Row added", icon="➕")
                        st.cache_data.clear()
                        time.sleep(0.3)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Add error: {e}")

            with a3:
                if selected_sheet_rows:
                    if st.button("🗑️ Delete", use_container_width=True):
                        try:
                            gc = init_sheets()
                            sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                            for row_num in sorted(selected_sheet_rows, reverse=True):
                                sheet.delete_rows(row_num)
                            st.toast(f"✅ Deleted {len(selected_sheet_rows)}", icon="🗑️")
                            st.cache_data.clear()
                            time.sleep(0.3)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Delete error: {e}")
                else:
                    st.button("🗑️ Delete", disabled=True, use_container_width=True)

            with a4:
                share_option = st.selectbox("Share via", ["WhatsApp", "Email", "SMS"], key="share_opt")
                if selected_indices:
                    pnr_col = next((c for c in edited_page.columns if 'PNR' in str(c).upper()), None)
                    pnrs = edited_page.loc[selected_indices, pnr_col].tolist() if pnr_col else []
                    msg = build_whatsapp_message(sheet_choice, len(selected_indices), pnrs)
                    encoded = urllib.parse.quote(msg)
                    if share_option == "WhatsApp":
                        url = f"https://api.whatsapp.com/send?text={encoded}"
                    elif share_option == "Email":
                        url = f"mailto:?subject=EQ Data&body={encoded}"
                    else:
                        url = f"sms:?body={encoded}"
                    st.link_button("📤 Share", url, use_container_width=True)
                else:
                    st.button("📤 Share", disabled=True, use_container_width=True)

            with a5:
                # ===== PRINT BUTTON =====
                st.markdown("""
                <div style="width:100%;">
                    <button onclick="window.print()" style="
                        background-color: #f0f0f0;
                        border: 1px solid #d0d7de;
                        border-radius: 8px;
                        padding: 9px 16px;
                        width: 100%;
                        font-weight: 500;
                        cursor: pointer;
                        transition: 0.15s;
                        color: #1f2328;
                        font-size: 1rem;
                    ">🖨️ Print Sheet</button>
                </div>
                """, unsafe_allow_html=True)

            st.markdown('</div>', unsafe_allow_html=True)

            # ===== EXPORT =====
            st.markdown("**📄 Export**")
            e1, e2, e3 = st.columns(3)
            
            with e1:
                try:
                    export_df = filtered_df.drop(columns=['_sheet_row'], errors='ignore')
                    pdf = FPDF('L', 'mm', 'A4')
                    pdf.add_page()
                    pdf.set_font("Arial", 'B', 12)
                    title = sanitize_latin(f"{sheet_choice} Report - {format_datetime()}")
                    pdf.cell(0, 8, title, ln=True, align='C')
                    pdf.ln(3)
                    pdf.set_font("Arial", 'B', 6)
                    cols = export_df.columns.tolist()
                    if cols:
                        col_width = min(22, 270 / max(len(cols), 1))
                        for col in cols:
                            safe_col = sanitize_latin(str(col)[:12])
                            pdf.cell(col_width, 5, safe_col, border=1, align='C')
                        pdf.ln()
                        pdf.set_font("Arial", '', 5)
                        for _, row in export_df.head(120).iterrows():
                            for col in cols:
                                val = str(row[col])[:14] if pd.notna(row[col]) else ''
                                safe_val = sanitize_latin(val)
                                pdf.cell(col_width, 4, safe_val, border=1, align='L')
                            pdf.ln()
                        pdf_bytes = pdf.output(dest='S')
                        st.download_button(
                            "📥 PDF",
                            data=pdf_bytes,
                            file_name=f"{sheet_choice}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
                except Exception as e:
                    st.warning(f"PDF: {e}")

            with e2:
                export_df = filtered_df.drop(columns=['_sheet_row'], errors='ignore')
                csv = export_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 CSV",
                    data=csv,
                    file_name=f"{sheet_choice}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

            with e3:
                export_df = filtered_df.drop(columns=['_sheet_row'], errors='ignore')
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                    export_df.to_excel(writer, sheet_name=sheet_choice, index=False)
                st.download_button(
                    "📥 Excel",
                    data=excel_buffer.getvalue(),
                    file_name=f"{sheet_choice}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

    st.markdown("""
    <div class='pro-footer'>
        🚂 AI EQMS Hub Pro • Created by Sharique<br>
        © 2026 All Rights Reserved
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
