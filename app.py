import streamlit as st
import pandas as pd
import json
import re
import base64
import io
import time
import requests
import urllib.parse
from datetime import datetime
from collections import Counter
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from fpdf import FPDF
import plotly.express as px
import pytz

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

# ========== TIMEZONE ==========
IST = pytz.timezone("Asia/Kolkata")

def now_ist():
    return datetime.now(IST)

# ========== SESSION STATE ==========
defaults = {
    'messages': [],
    'activity_log': [],
    'last_uploaded_file': None,
    'last_uploaded_drive_url': None,
    'last_uploaded_view_url': None,
    'last_refresh': time.time(),
    'chat_suggestions': [
        "Show me EQ summary",
        "How many records today?",
        "Train wise breakup",
        "Pending EQ requests",
        "Quota status",
        "PNR status"
    ],
    'dark_mode': True,          # Default dark (Grok style)
    'current_page': 1,
    'pnr_val': '',
    'train_val': '',
    'from_val': None,
    'to_val': None,
    'upload_success': False,
    'last_upload_time': None,
    'pending_suggestion': None,
    'text_input_data': "",
}

for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ========== STATION MAP (same as before) ==========
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
    if not pnr: return ''
    digits = re.sub(r'\D', '', str(pnr))
    return digits if len(digits) == 10 else (digits[-10:] if len(digits) > 10 else '')

def clean_phone(phone):
    if not phone: return ''
    digits = re.sub(r'\D', '', str(phone))
    return digits[-10:] if len(digits) >= 10 else ''

def parse_date(date_str):
    if not date_str: return ''
    if isinstance(date_str, datetime):
        return date_str.strftime("%d-%m-%Y")
    date_str = str(date_str).strip()
    multi_match = re.search(r'(\d{1,2})[\/\.\-](\d{1,2})[\/\.\-](\d{2,4})', date_str)
    if multi_match:
        day, month, year = multi_match.groups()
        day = day.zfill(2)
        month = month.zfill(2)
        if len(year) == 2: year = '20' + year
        if int(month) > 12 and int(day) <= 12:
            day, month = month, day
        return f"{day}-{month}-{year}"
    return date_str

def is_expired(doj_str):
    if not doj_str: return False
    parsed = parse_date(doj_str)
    if not parsed: return False
    try:
        doj_dt = datetime.strptime(parsed, "%d-%m-%Y")
        today = now_ist().replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
        return doj_dt < today
    except:
        return False

def col_index_to_letter(idx):
    result = ""
    while idx > 0:
        idx, remainder = divmod(idx - 1, 26)
        result = chr(65 + remainder) + result
    return result

def is_flag_time():
    now = now_ist()
    month = now.month
    if month in [5, 6, 7]: sunset_h, sunset_m = 18, 45
    elif month in [11, 12, 1]: sunset_h, sunset_m = 17, 15
    elif month in [2, 3, 10]: sunset_h, sunset_m = 18, 0
    else: sunset_h, sunset_m = 18, 30
    start = now.replace(hour=6, minute=0, second=0, microsecond=0)
    end = now.replace(hour=sunset_h, minute=sunset_m, second=0, microsecond=0)
    return start <= now <= end

# ========== SHEET CONFIG ==========
SHEET_CONFIG = {
    "EQ": {"start_row": 5, "pnr_col": 1, "train_col": 5, "doj_col": 7},
    "DATA": {"start_row": 3, "pnr_col": 1, "train_col": 5, "doj_col": 7},
    "FINAL": {"start_row": 6, "pnr_col": 7, "train_col": 1, "doj_col": 12},
    "DATA2": {"start_row": 4, "pnr_col": 7, "train_col": 1, "doj_col": 12},
    "EMAIL_DATA": {"start_row": 2, "pnr_col": 7, "train_col": 8, "doj_col": 11},
    "NOTE": {"start_row": 2, "pnr_col": None, "train_col": 0, "doj_col": None}
}

@st.cache_data(ttl=25)
def load_sheet_data_cached(sheet_name, sheet_id):
    try:
        gc = init_sheets()
        sheet = gc.open_by_key(sheet_id).worksheet(sheet_name)
        all_data = sheet.get_all_values()
        config = SHEET_CONFIG.get(sheet_name, {"start_row": 1})
        start_row = config["start_row"]
        if len(all_data) < start_row:
            return pd.DataFrame()
        headers_raw = all_data[start_row - 2] if start_row > 1 else all_data[0] if all_data else []
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
        return pd.DataFrame(data_rows, columns=unique_headers[:len(data_rows[0])])
    except Exception as e:
        st.error(f"Error loading {sheet_name}: {e}")
        return pd.DataFrame()

# ========== GEMINI PARSER (same strong logic) ==========
def gemini_universal_parser(input_data, input_type, mime_type=None, progress_callback=None):
    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}'

    system_prompt = """
You are TSKEQ Bot's AI extraction engine. Expert at messy, handwritten, torn railway forms.

Extract these fields:
PNR, T_N, CLASS, DOJ (DD-MM-YYYY), FROM, TO, BOARDING, PASS_NAME, PASS_PH, T_BERTHS, PURPOSE, ADDRESS, DIARY_NO, RECOMMENDATION, DESIGNATION, VIP_STATUS, APPLICATION_DATE, RAILWAY_ZONE, PREFERENCE, PHONE_NUBER, WARRANT_NO

Rules:
- DOJ: take first date if range given
- PREFERENCE = "Lower Seat" if Lower Berth / Coupe mentioned
- RAIL BOARD detection important
- Return ONLY valid JSON array
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
        parts.append({"text": system_prompt + "\n\nINPUT:\n" + str(input_data)})
    else:
        return {'error': 'Unsupported type'}

    if progress_callback:
        progress_callback(30, "Gemini processing...")

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.25, "maxOutputTokens": 16384}
    }

    try:
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=120)
        if response.status_code != 200:
            return {'error': f'Gemini API Error: {response.status_code}'}
        data = response.json()
        if not data.get('candidates'):
            return {'error': 'Empty response from Gemini'}
        response_text = data['candidates'][0]['content']['parts'][0]['text']

        if progress_callback:
            progress_callback(70, "Parsing response...")

        json_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', response_text)
        if not json_match:
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
            if json_match:
                json_str = json_match.group(1)
            else:
                return {'error': 'Could not extract JSON'}
        else:
            json_str = json_match.group(0)

        json_str = json_str.replace('```json', '').replace('```', '').strip()
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        records = json.loads(json_str)
        if isinstance(records, dict):
            records = [records]

        # Clean records
        cleaned = []
        seen = set()
        for rec in records:
            pnr = clean_pnr(rec.get('PNR', ''))
            if not pnr or pnr in seen: continue
            seen.add(pnr)
            if rec.get('PASS_PH'): rec['PASS_PH'] = clean_phone(rec['PASS_PH'])
            if rec.get('PHONE_NUBER'): rec['PHONE_NUBER'] = clean_phone(rec['PHONE_NUBER'])
            if rec.get('DOJ'): rec['DOJ'] = parse_date(rec['DOJ'])
            if rec.get('APPLICATION_DATE'): rec['APPLICATION_DATE'] = parse_date(rec['APPLICATION_DATE'])
            rec.setdefault('PREFERENCE', 'General')
            rec.setdefault('T_BERTHS', 1)
            cleaned.append(rec)

        if not cleaned:
            return {'error': 'No valid records found'}
        if progress_callback:
            progress_callback(100, "Done!")
        return {'records': cleaned, 'count': len(cleaned)}
    except Exception as e:
        return {'error': f'Parser Error: {str(e)}'}

# ========== DRIVE & SHEET ==========
def upload_to_drive(file_bytes, filename, mime_type):
    try:
        drive_service = init_drive()
        file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=True)
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id,name,webViewLink').execute()
        file_id = file.get('id')
        return {
            'success': True,
            'id': file_id,
            'name': file.get('name'),
            'view_url': f"https://drive.google.com/file/d/{file_id}/view",
            'print_url': f"https://drive.google.com/file/d/{file_id}/preview"
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

def save_to_sheet(sheet, records):
    try:
        all_data = sheet.get_all_values()
        existing_pnrs = [clean_pnr(row[1]) for row in all_data[4:] if row and len(row) > 1]
        saved = 0
        skipped = 0
        next_sn = len(all_data) - 3
        for rec in records:
            pnr = clean_pnr(rec.get('PNR', ''))
            if not pnr or pnr in existing_pnrs:
                skipped += 1
                continue
            now = now_ist().strftime("%d-%m-%Y %H:%M:%S")
            row = [
                next_sn, pnr, rec.get('FROM',''), rec.get('TO',''), rec.get('BOARDING',''),
                rec.get('T_N',''), rec.get('CLASS',''), rec.get('DOJ',''), rec.get('PASS_NAME',''),
                rec.get('PASS_PH',''), rec.get('T_BERTHS',1), rec.get('PURPOSE',''), rec.get('ADDRESS',''),
                rec.get('DIARY_NO',''), rec.get('RECOMMENDATION',''), rec.get('DESIGNATION',''),
                rec.get('PHONE_NUBER',''), rec.get('VIP_STATUS',''), rec.get('WARRANT_NO',''),
                now, rec.get('APPLICATION_DATE',''), rec.get('RAILWAY_ZONE',''), rec.get('PREFERENCE','General')
            ]
            sheet.append_row(row)
            existing_pnrs.append(pnr)
            next_sn += 1
            saved += 1
            time.sleep(0.12)
        return {'saved': saved, 'skipped': skipped}
    except Exception as e:
        return {'error': str(e)}

def chat_with_gemini(user_message, chat_history):
    try:
        model = init_gemini()
        context = "You are TSKEQ Bot - helpful railway EQ assistant."
        system_prompt = f"{context}\n\nConversation:\n"
        for msg in chat_history[-8:]:
            role = "User" if msg['role'] == 'user' else "Assistant"
            system_prompt += f"{role}: {msg['content']}\n"
        system_prompt += f"User: {user_message}\nAssistant:"
        response = model.generate_content(system_prompt)
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"

# ========== THEME (Grok style) ==========
def apply_theme(dark_mode):
    if dark_mode:
        bg = "#0a0a0a"
        card = "#141414"
        text = "#e8e8e8"
        secondary = "#a0a0a0"
        border = "#2a2a2a"
        accent = "#a855f7"          # Grok purple
        input_bg = "#1a1a1a"
    else:
        bg = "#f8f9fa"
        card = "#ffffff"
        text = "#1a1a1a"
        secondary = "#5f6368"
        border = "#e0e0e0"
        accent = "#7c3aed"
        input_bg = "#ffffff"

    st.markdown(f"""
    <style>
        .stApp {{ background-color: {bg} !important; }}
        [data-testid="stSidebar"] {{
            background-color: {card} !important;
            border-right: 1px solid {border} !important;
        }}
        h1, h2, h3, h4, p, div, span, label {{ color: {text} !important; }}
        .stTextInput input, .stTextArea textarea, .stSelectbox > div > div {{
            background-color: {input_bg} !important;
            color: {text} !important;
            border: 1px solid {border} !important;
            border-radius: 10px !important;
        }}
        .stButton > button {{
            background: transparent !important;
            color: {accent} !important;
            border: 1px solid {border} !important;
            border-radius: 10px !important;
            font-weight: 500 !important;
        }}
        .stButton > button:hover {{
            background: {accent} !important;
            color: white !important;
            border-color: {accent} !important;
        }}
        .stDataFrame, [data-testid="stDataEditor"] {{
            background-color: {card} !important;
            border-radius: 10px !important;
        }}
        .block-container {{ padding-top: 1.5rem !important; }}
        .pro-footer {{
            text-align: center;
            color: {secondary};
            font-size: 0.85rem;
            margin-top: 30px;
            padding-top: 15px;
            border-top: 1px solid {border};
        }}
    </style>
    """, unsafe_allow_html=True)

# ========== MAIN ==========
def main():
    # Theme
    dark_mode = st.sidebar.toggle("🌙 Dark Mode", value=st.session_state.dark_mode)
    if dark_mode != st.session_state.dark_mode:
        st.session_state.dark_mode = dark_mode
        st.rerun()
    apply_theme(dark_mode)

    with st.sidebar:
        # Greeting
        now = now_ist()
        if is_flag_time():
            st.markdown("""
            <div style="text-align:center; margin-bottom:15px;">
                <div style="font-size:28px;">🇮🇳</div>
                <div style="color:#FF9933; font-weight:700; font-size:1.1rem;">नमस्ते, आपका स्वागत है</div>
                <div style="color:#ffffff; font-weight:600;">हम भारत के लोग</div>
                <div style="color:#138808; font-weight:700;">जय हिंद</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            hour = now.hour
            if 5 <= hour < 12: st.markdown("☀️ **Good Morning**")
            elif 12 <= hour < 17: st.markdown("🌤️ **Good Afternoon**")
            elif 17 <= hour < 21: st.markdown("🌆 **Good Evening**")
            else: st.markdown("🌙 **Good Night**")

        st.caption(f"📅 {now.strftime('%d-%m-%Y')}  |  🕐 {now.strftime('%H:%M')} IST")

        auto_refresh = st.checkbox("🔄 Auto Sync (25s)", value=True)
        if auto_refresh and time.time() - st.session_state.last_refresh > 25:
            st.session_state.last_refresh = time.time()
            st.cache_data.clear()
            st.rerun()

        st.markdown("---")
        st.markdown(f'<a href="https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit" target="_blank" style="display:block;text-align:center;padding:10px;border:1px solid #444;border-radius:10px;text-decoration:none;color:#a855f7;">📊 Open Google Sheet</a>', unsafe_allow_html=True)
        st.markdown("---")

        # ========== SMART UPLOAD SECTION ==========
        st.subheader("📤 Smart Upload")
        upload_mode = st.radio(
            "Select Type",
            ["📷 Image / PDF", "📝 Text", "🎤 Audio"],
            horizontal=True,
            label_visibility="collapsed"
        )

        uploaded_file = None
        text_content = ""

        if upload_mode == "📷 Image / PDF":
            uploaded_file = st.file_uploader(
                "Upload Image or PDF (1-2 pages recommended)",
                type=['png', 'jpg', 'jpeg', 'pdf'],
                key="img_pdf_uploader"
            )
        elif upload_mode == "📝 Text":
            text_content = st.text_area(
                "Paste or type messy text here",
                height=150,
                placeholder="Yahan messy text paste karein ya type karein...",
                key="text_area_input"
            )
        else:  # Audio
            uploaded_file = st.file_uploader(
                "Upload Audio (mp3 / wav / ogg / m4a)",
                type=['mp3', 'wav', 'ogg', 'm4a'],
                key="audio_uploader"
            )
            st.caption("Mobile se record karke upload kar sakte ho")

        process_clicked = st.button("🚀 Process & Save", type="primary", use_container_width=True)

        if process_clicked:
            if upload_mode == "📝 Text" and not text_content.strip():
                st.warning("Please enter some text")
            elif upload_mode != "📝 Text" and uploaded_file is None:
                st.warning("Please select a file")
            else:
                progress = st.progress(0)
                status = st.empty()

                def update_p(val, msg):
                    progress.progress(val)
                    status.text(msg)

                try:
                    if upload_mode == "📝 Text":
                        result = gemini_universal_parser(text_content, "text", progress_callback=update_p)
                        filename = f"text_upload_{now_ist().strftime('%H%M%S')}.txt"
                        file_bytes = text_content.encode('utf-8')
                        mime = "text/plain"
                    else:
                        file_bytes = uploaded_file.read()
                        b64 = base64.b64encode(file_bytes).decode()
                        if uploaded_file.type == "application/pdf":
                            ftype = "pdf"
                        elif uploaded_file.type.startswith("audio"):
                            ftype = "audio"
                        else:
                            ftype = "image"
                        result = gemini_universal_parser(b64, ftype, uploaded_file.type, update_p)
                        filename = uploaded_file.name
                        mime = uploaded_file.type

                    if 'error' in result:
                        st.error(result['error'])
                    else:
                        st.success(f"✅ {result['count']} records extracted")
                        with st.expander("Preview"):
                            st.dataframe(pd.DataFrame(result['records']))

                        gc = init_sheets()
                        eq_sheet = gc.open_by_key(SHEET_ID).worksheet("EQ")
                        save_res = save_to_sheet(eq_sheet, result['records'])

                        if 'error' in save_res:
                            st.error(save_res['error'])
                        else:
                            st.success(f"Saved {save_res['saved']} new records")

                            drive_res = upload_to_drive(file_bytes, filename, mime)
                            if drive_res['success']:
                                st.session_state.last_uploaded_file = filename
                                st.session_state.last_uploaded_view_url = drive_res['view_url']
                                st.session_state.last_uploaded_drive_url = drive_res['print_url']
                                st.session_state.upload_success = True
                                st.session_state.last_upload_time = now_ist().strftime("%H:%M")
                                st.success("📁 File saved to Drive")
                                st.cache_data.clear()
                                st.session_state.last_refresh = time.time()
                                time.sleep(0.5)
                                st.rerun()
                except Exception as e:
                    st.error(str(e))
                finally:
                    progress.empty()
                    status.empty()

        # Show last uploaded file actions
        if st.session_state.upload_success and st.session_state.last_uploaded_file:
            st.markdown("---")
            st.markdown(f"**📄 {st.session_state.last_uploaded_file}**")
            st.caption(f"Uploaded at {st.session_state.last_upload_time}")
            c1, c2 = st.columns(2)
            with c1:
                st.link_button("👁️ View", st.session_state.last_uploaded_view_url, use_container_width=True)
            with c2:
                st.link_button("🖨️ Print Original", st.session_state.last_uploaded_drive_url, use_container_width=True)

            if st.button("Clear History", use_container_width=True):
                st.session_state.upload_success = False
                st.session_state.last_uploaded_file = None
                st.rerun()

        st.markdown("---")

        # Filters
        st.subheader("🔍 Filters")
        pnr_input = st.text_input("PNR", value=st.session_state.pnr_val, key="pnr_f")
        train_input = st.text_input("Train", value=st.session_state.train_val, key="train_f")

        c1, c2 = st.columns(2)
        with c1:
            from_input = st.date_input("From DOJ", value=st.session_state.from_val, format="DD-MM-YYYY", key="from_f")
        with c2:
            to_input = st.date_input("To DOJ", value=st.session_state.to_val, format="DD-MM-YYYY", key="to_f")

        # Apply filters immediately
        if (pnr_input != st.session_state.pnr_val or train_input != st.session_state.train_val or
            from_input != st.session_state.from_val or to_input != st.session_state.to_val):
            st.session_state.pnr_val = pnr_input
            st.session_state.train_val = train_input
            st.session_state.from_val = from_input
            st.session_state.to_val = to_input
            st.session_state.current_page = 1
            st.rerun()

        if st.button("Clear Filters", use_container_width=True):
            st.session_state.pnr_val = ""
            st.session_state.train_val = ""
            st.session_state.from_val = None
            st.session_state.to_val = None
            st.session_state.current_page = 1
            st.rerun()

        sheet_choice = st.selectbox("Sheet", list(SHEET_CONFIG.keys()))
        view = st.radio("View", ["📋 Data Table", "📊 Dashboard", "💬 Chat"], index=0)

    # ========== MAIN CONTENT ==========
    st.markdown(f"<h1 style='font-size:1.6rem; margin-bottom:4px;'>🚂 AI EQMS Hub Pro</h1>", unsafe_allow_html=True)
    st.caption(f"Last sync: {now_ist().strftime('%H:%M:%S')} IST")

    # Load data
    df_raw = load_sheet_data_cached(sheet_choice, SHEET_ID)
    filtered_df = df_raw.copy() if not df_raw.empty else pd.DataFrame()
    config = SHEET_CONFIG[sheet_choice]

    if not filtered_df.empty:
        if st.session_state.pnr_val and config.get("pnr_col") is not None:
            col = filtered_df.columns[config["pnr_col"]]
            filtered_df = filtered_df[filtered_df[col].astype(str).str.contains(st.session_state.pnr_val, case=False, na=False)]
        if st.session_state.train_val and config.get("train_col") is not None:
            col = filtered_df.columns[config["train_col"]]
            filtered_df = filtered_df[filtered_df[col].astype(str).str.contains(st.session_state.train_val, case=False, na=False)]
        if (st.session_state.from_val or st.session_state.to_val) and config.get("doj_col") is not None:
            col = filtered_df.columns[config["doj_col"]]
            filtered_df['_tmp'] = pd.to_datetime(filtered_df[col], format='%d-%m-%Y', errors='coerce')
            if st.session_state.from_val:
                filtered_df = filtered_df[filtered_df['_tmp'] >= pd.to_datetime(st.session_state.from_val)]
            if st.session_state.to_val:
                filtered_df = filtered_df[filtered_df['_tmp'] <= pd.to_datetime(st.session_state.to_val)]
            filtered_df = filtered_df.drop('_tmp', axis=1)

    if view == "💬 Chat":
        st.subheader("💬 Chat with TSKEQ Bot")
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if prompt := st.chat_input("Type your question..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    reply = chat_with_gemini(prompt, st.session_state.messages)
                    st.markdown(reply)
            st.session_state.messages.append({"role": "assistant", "content": reply})
            st.rerun()

        if st.button("Clear Chat"):
            st.session_state.messages = []
            st.rerun()

    elif view == "📊 Dashboard":
        st.subheader("📊 Dashboard")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Records", len(filtered_df))
        train_col = next((c for c in filtered_df.columns if 'T/N' in c.upper() or 'TRAIN' in c.upper()), None)
        c2.metric("Unique Trains", filtered_df[train_col].nunique() if train_col else 0)
        berth_col = next((c for c in filtered_df.columns if 'BERTH' in c.upper()), None)
        total_b = pd.to_numeric(filtered_df[berth_col], errors='coerce').sum() if berth_col else 0
        c3.metric("Total Berths", int(total_b) if total_b else 0)
        doj_col = next((c for c in filtered_df.columns if 'DOJ' in c.upper()), None)
        expired = sum(1 for _, r in filtered_df.iterrows() if is_expired(r.get(doj_col, ''))) if doj_col else 0
        c4.metric("Expired", expired)

        if not filtered_df.empty and train_col:
            train_counts = filtered_df[train_col].value_counts().head(8).reset_index()
            train_counts.columns = ['Train', 'Count']
            fig = px.pie(train_counts, names='Train', values='Count', hole=0.4, title="Train Distribution")
            st.plotly_chart(fig, use_container_width=True)

    else:  # Data Table
        st.subheader(f"📋 {sheet_choice} — {len(filtered_df)} rows")

        if filtered_df.empty:
            st.info("No data found")
        else:
            # Pagination
            page_size = st.selectbox("Rows per page", [15, 25, 50], index=1)
            total_pages = max(1, (len(filtered_df) + page_size - 1) // page_size)
            col1, col2, col3 = st.columns([1, 2, 1])
            with col1:
                if st.button("◀ Prev") and st.session_state.current_page > 1:
                    st.session_state.current_page -= 1
                    st.rerun()
            with col2:
                st.write(f"Page {st.session_state.current_page} of {total_pages}")
            with col3:
                if st.button("Next ▶") and st.session_state.current_page < total_pages:
                    st.session_state.current_page += 1
                    st.rerun()

            start = (st.session_state.current_page - 1) * page_size
            page_df = filtered_df.iloc[start:start + page_size].copy()
            page_df.insert(0, "Select", False)

            edited = st.data_editor(page_df, use_container_width=True, height=400, key="editor")
            selected = edited[edited["Select"]].index.tolist()

            st.markdown("### Actions")
            b1, b2, b3, b4 = st.columns(4)

            with b1:
                if st.button("💾 Save Edits", use_container_width=True):
                    try:
                        gc = init_sheets()
                        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                        data = edited.drop("Select", axis=1).values.tolist()
                        start_row = config["start_row"] + start
                        end_row = start_row + len(data) - 1
                        col_letter = col_index_to_letter(len(data[0]))
                        sheet.update(f"A{start_row}:{col_letter}{end_row}", data)
                        st.success("Saved!")
                        st.cache_data.clear()
                        time.sleep(0.4)
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

            with b2:
                if st.button("➕ Add Row", use_container_width=True):
                    try:
                        gc = init_sheets()
                        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                        sheet.append_row([''] * 20)
                        st.success("Row added")
                        st.cache_data.clear()
                        time.sleep(0.4)
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

            with b3:
                if selected and st.button("🗑️ Delete", use_container_width=True):
                    try:
                        gc = init_sheets()
                        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                        for idx in sorted(selected, reverse=True):
                            sheet.delete_rows(config["start_row"] + idx)
                        st.success(f"Deleted {len(selected)}")
                        st.cache_data.clear()
                        time.sleep(0.4)
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
                else:
                    st.button("🗑️ Delete", disabled=True, use_container_width=True)

            with b4:
                if selected:
                    pnrs = []
                    pnr_col = next((c for c in edited.columns if 'PNR' in c.upper()), None)
                    if pnr_col:
                        pnrs = edited.loc[selected, pnr_col].tolist()
                    msg = f"EQ Data - {len(selected)} records\nPNRs: {', '.join(map(str, pnrs[:10]))}"
                    wa = f"https://api.whatsapp.com/send?text={urllib.parse.quote(msg)}"
                    st.link_button("📤 WhatsApp", wa, use_container_width=True)
                else:
                    st.button("📤 WhatsApp", disabled=True, use_container_width=True)

    st.markdown('<div class="pro-footer">Made with ❤️ by Sharique • AI EQMS Hub Pro</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
