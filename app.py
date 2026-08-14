import streamlit as st
import pandas as pd
import json
import re
import base64
import io
import time
import math
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

st.set_page_config(page_title="AI EQMS Hub Pro", page_icon="🚂", layout="wide", initial_sidebar_state="expanded")

# ============================================================
# CONFIG & CREDENTIALS
# ============================================================
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
GSPREAD_CREDENTIALS = st.secrets.get("GSPREAD_CREDENTIALS", None)

SHEET_ID = "1QcS3ZF3YYxSEykG0KiOUuXbTdBh0DMHdMgoqa9t8yrI"
DRIVE_FOLDER_ID = "1H1gf8WqfoTYFT_pU9WfIDLrHg-NpuUSI"

if not GEMINI_API_KEY or not GSPREAD_CREDENTIALS:
    st.error("""
    ❌ Missing credentials!

    Please add these to your `.streamlit/secrets.toml`:
    ```toml
    GEMINI_API_KEY = "your_gemini_api_key"
    GSPREAD_CREDENTIALS = { type = "service_account", project_id = "...", private_key = "...", client_email = "..." }
    ```
    """)
    st.stop()

# ============================================================
# HEADINGS (27 columns A-AA)
# ============================================================
HEADINGS = [
    'S/N', 'PNR', 'FROM', 'TO', 'BOARDING', 'T/N', 'CLASS', 'DOJ',
    'PASS NAME', 'PASS PH', 'T/BERTHS', 'PURPOSE', 'ADDRESS',
    'DIARY NO', 'RECOMMENDATION', 'DESIGNATION', 'PHONE NUBER',
    'MP/MLA/MR/MINISTER/VIP/VVIP', 'WARRANT NUMBER', 'PROCESSING DATE+TIME',
    'APPLICATION DATE', 'RAILWAY/ZONE/DIVISION', 'PREFERENCE',
    'LINK (Click to Open)', 'PRINT (A4 Size)', 'VIEW (Hover Details)', 'PNR STATUS LINK'
]

# ============================================================
# STATION MAP
# ============================================================
STATION_MAP = {
    'NTSK':'New Tinsukia', 'GHY':'Guwahati', 'NDLS':'New Delhi', 'HWH':'Howrah',
    'PNBE':'Patna', 'BSB':'Varanasi', 'CNB':'Kanpur Central', 'LKO':'Lucknow',
    'DDU':'Pt. Deen Dayal Upadhyaya', 'GAYA':'Gaya', 'MGS':'Mughalsarai',
    'ASN':'Asansol', 'DHN':'Dhanbad', 'SC':'Secunderabad', 'MAS':'Chennai Central',
    'SBC':'Bengaluru City', 'CSTM':'Mumbai CSMT', 'BCT':'Mumbai Central',
    'PUNE':'Pune', 'ADI':'Ahmedabad', 'BRC':'Vadodara', 'JP':'Jaipur',
    'AII':'Ajmer', 'BPL':'Bhopal', 'INDB':'Indore', 'JBP':'Jabalpur',
    'NGP':'Nagpur', 'HYB':'Hyderabad', 'BZA':'Vijayawada', 'GNT':'Guntur',
    'VSKP':'Visakhapatnam', 'BBS':'Bhubaneswar', 'KGP':'Kharagpur',
    'KOAA':'Kolkata', 'NJP':'New Jalpaiguri', 'NBQ':'New Bongaigaon',
    'KYQ':'Kamakhya', 'DBRG':'Dibrugarh', 'MXN':'Mariani Junction',
    'FKG':'Furkating', 'JTI':'Jatinga', 'MFP':'Muzaffarpur',
    'KIR':'Katihar Junction', 'DEL':'Delhi', 'SDAH':'Sealdah',
    'TBM':'Tambaram', 'YPR':'Yesvantpur', 'SMVB':'SMVT Bengaluru',
    'PRYJ':'Prayagraj', 'DNR':'Danapur', 'RE':'Rewari', 'AY':'Ayodhya',
    'MLDT':'Malda Town', 'NNA':'Naugachia', 'CLG':'Kahalgaon', 'ROK':'Rohtak',
    'BGP':'Bhagalpur', 'JMP':'Jamalpur', 'JYG':'Jaynagar', 'BJU':'Barauni',
    'SPJ':'Samastipur', 'HJP':'Hajipur', 'PPTA':'Patliputra', 'ARA':'Ara',
    'BXR':'Buxar', 'TDL':'Tundla', 'ALJN':'Aligarh', 'GZB':'Ghaziabad',
    'BKN':'Bikaner', 'BME':'Barmer', 'JU':'Jodhpur', 'UDZ':'Udaipur',
    'RTM':'Ratlam', 'UJN':'Ujjain', 'ST':'Surat', 'BL':'Valsad',
    'TVC':'Thiruvananthapuram', 'ERS':'Ernakulam', 'MAQ':'Mangalore',
    'MS':'Chennai Egmore', 'AF':'Agra Fort', 'MTJ':'Mathura', 'GWL':'Gwalior',
    'JHS':'Jhansi', 'BHUJ':'Bhuj', 'GIMB':'Gandhidham', 'ANND':'Anand',
    'ND':'Nadiad', 'BH':'Bharuch', 'NVS':'Navsari', 'BSR':'Vasai Road',
    'BVI':'Borivali', 'DDR':'Dadar', 'KYN':'Kalyan', 'NK':'Nashik Road',
    'MMR':'Manmad', 'BSL':'Bhusaval', 'AK':'Akola', 'BPQ':'Balharshah',
    'SKZR':'Sirpur Kagaznagar', 'MCI':'Manchiryal', 'KZJ':'Kazipet',
    'KCG':'Kacheguda', 'MBNR':'Mahbubnagar', 'TEL':'Tenali', 'OGL':'Ongole',
    'NLR':'Nellore', 'GDR':'Gudur', 'CGL':'Chengalpattu', 'VM':'Villupuram',
    'TJ':'Thanjavur', 'TPJ':'Tiruchirappalli', 'MDU':'Madurai',
    'NCJ':'Nagercoil', 'QLN':'Kollam', 'ALLP':'Alappuzha', 'TCR':'Thrissur',
    'PGT':'Palakkad', 'CBE':'Coimbatore', 'SA':'Salem', 'JTJ':'Jolarpettai',
    'KPD':'Katpadi', 'AJJ':'Arakkonam', 'PER':'Perambur', 'KMU':'Kumbakonam',
    'MV':'Mayiladuthurai', 'CDM':'Chidambaram', 'TDPR':'Tirupadripulyur',
    'CTC':'Cuttack', 'BHC':'Bhadrak', 'SRC':'Santragachi', 'GMO':'Gomoh',
    'KQR':'Koderma', 'BBK':'Barabanki', 'GD':'Gonda', 'BST':'Basti',
    'GKP':'Gorakhpur', 'DEOS':'Deoria Sadar', 'DGR':'Durgapur',
    'BWN':'Bardhaman', 'VZM':'Vizianagaram', 'SLO':'Samalkot',
    'RJY':'Rajahmundry', 'WADI':'Wadi', 'YG':'Yadgir', 'RC':'Raichur',
    'GTL':'Guntakal', 'DHNE':'Dhone', 'KRNT':'Kurnool City', 'GWD':'Gadwal',
    'PNU':'Palanpur', 'ABR':'Abu Road', 'FA':'Falna', 'MJ':'Marwar Junction',
    'AWR':'Alwar', 'SUR':'Solapur', 'GR':'Gulbarga', 'CSMT':'Mumbai CSMT',
    'AGC':'Agra Cantt', 'KOJ':'Kokrajhar', 'RNC':'Ranchi', 'TATA':'Tatanagar',
    'CKP':'Chakradharpur', 'ROU':'Rourkela', 'SBP':'Sambalpur',
    'BAM':'Brahmapur', 'KUR':'Khurda Road', 'PURI':'Puri', 'SMI':'Sitamarhi',
    'RXL':'Raxaul', 'SGL':'Sagauli', 'CPR':'Chhapra', 'SV':'Siwan',
    'BUG':'Bagaha', 'NKE':'Narkatiaganj', 'BMKI':'Bapudham Motihari',
    'DBG':'Darbhanga', 'LSI':'Laheria Sarai', 'HYT':'Haiaghat',
    'SEE':'Sonpur', 'GCT':'Ghazipur City', 'BUI':'Ballia', 'RSR':'Rasra',
    'MAU':'Mau', 'BLTR':'Belthara Road', 'LRD':'Lar Road', 'SRU':'Salempur',
    'BTT':'Bhatni', 'BE':'Bareilly', 'RMU':'Rampur', 'MB':'Moradabad',
    'SRE':'Saharanpur', 'UMB':'Ambala Cantt', 'LDH':'Ludhiana',
    'JUC':'Jalandhar City', 'ASR':'Amritsar', 'PTA':'Patiala',
    'BTI':'Bathinda', 'SGNR':'Shri Ganganagar', 'AII':'Ajmer',
    'DLI':'Old Delhi', 'NZM':'Hazrat Nizamuddin', 'ETW':'Etawah',
    'FTP':'Fatehpur', 'NHLG':'New Haflong', 'LMG':'Lumding',
    'RNY':'Rangiya', 'BPRD':'Barpeta Road', 'FKM':'Fakiragram',
    'NOQ':'New Alipurduar', 'HSA':'Hasimara', 'JPG':'Jalpaiguri',
    'KNE':'Kishanganj', 'BOE':'Barsoi', 'BGS':'Begusarai',
    'BJP':'Bijapur', 'BGK':'Bagalkot', 'UBL':'Hubballi', 'DWR':'Dharwad',
    'LD':'Londa', 'QLM':'Kulem', 'MAO':'Madgaon', 'KRMI':'Karmali',
    'THVM':'Thivim', 'PERN':'Pernem', 'STR':'Satara', 'KRD':'Karad',
    'SLI':'Sangli', 'MRJ':'Miraj', 'BGM':'Belagavi', 'GPB':'Ghatprabha',
    'HPT':'Hospet', 'BAY':'Ballari', 'ATP':'Anantapur', 'DMM':'Dharmavaram',
    'SSPN':'Sri Sathya Sai Prasanthi Nilayam', 'HUP':'Hindupur',
    'YNK':'Yelahanka', 'BNC':'Bengaluru Cantt', 'KJM':'Krishnarajapuram',
    'WFD':'Whitefield', 'KPN':'Kuppam', 'KON':'Kodaikanal Road',
    'VPT':'Virudhunagar', 'SRT':'Sattur', 'CVP':'Kovilpatti',
    'TEN':'Tirunelveli', 'CAPE':'Kanyakumari', 'KYJ':'Kayamkulam',
    'AWY':'Aluva', 'ERN':'Ernakulam Town', 'KTYM':'Kottayam',
    'CGY':'Changanassery', 'TRVL':'Tiruvalla', 'CNGR':'Chengannur',
    'MVLK':'Mavelikara', 'VAK':'Varkala', 'TVP':'Thiruvananthapuram Pettah'
}

# ============================================================
# SERVICES INIT
# ============================================================
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

@st.cache_resource
def init_drive():
    creds_dict = dict(GSPREAD_CREDENTIALS)
    pk = creds_dict.get("private_key", "")
    if "\\n" in pk:
        creds_dict["private_key"] = pk.replace("\\n", "\n")
    scope = ['https://www.googleapis.com/auth/drive.file']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return build('drive', 'v3', credentials=creds)

# ============================================================
# HELPERS
# ============================================================
def clean_pnr(pnr):
    if not pnr:
        return ''
    digits = re.sub(r'\D', '', str(pnr))
    return digits if len(digits) == 10 else (digits[-10:] if len(digits) > 10 else '')

def clean_phone(phone):
    if not phone:
        return ''
    digits = re.sub(r'\D', '', str(phone))
    if len(digits) == 10:
        return digits
    if len(digits) > 10:
        return digits[-10:]
    return ''

def parse_date(date_str):
    if not date_str:
        return ''
    if isinstance(date_str, datetime):
        return date_str.strftime("%d-%m-%Y")
    date_str = str(date_str).strip()
    # Handle "24/25.06.26"
    slash_split = date_str.split('/')
    if len(slash_split) == 2 and '.' in slash_split[1]:
        first_day = slash_split[0]
        rest = slash_split[1]
        dot_parts = rest.split('.')
        if len(dot_parts) == 3:
            day = first_day.zfill(2)
            month = dot_parts[1].zfill(2)
            year = dot_parts[2]
            if len(year) == 2:
                year = '20' + year
            return f"{day}-{month}-{year}"
    # Handle "24/25-06-2026"
    if '/' in date_str and '-' in date_str:
        parts = date_str.split('/')
        if len(parts) >= 2:
            first_date = parts[0]
            rest = '-'.join(parts[1:]) if len(parts) == 2 else parts[1]
            match = re.search(r'(\d{1,2})-(\d{1,2})-(\d{2,4})', rest)
            if match:
                day, month, year = match.groups()
                day = first_date.zfill(2)
                month = month.zfill(2)
                if len(year) == 2:
                    year = '20' + year
                return f"{day}-{month}-{year}"
    # Standard regex
    match = re.search(r'(\d{1,2})[\/\.\-](\d{1,2})[\/\.\-](\d{2,4})', date_str)
    if match:
        day, month, year = match.groups()
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
    except:
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

def get_flag_colors():
    if is_flag_time():
        return {
            'saffron': {'red': 1.0, 'green': 0.6, 'blue': 0.0},
            'white': {'red': 1.0, 'green': 1.0, 'blue': 1.0},
            'green': {'red': 0.0, 'green': 0.6, 'blue': 0.2}
        }
    return None

# ============================================================
# SHEET CONFIG
# ============================================================
SHEET_CONFIG = {
    "EQ":      {"start_row": 5, "header_row": 4, "pnr_col": 2, "train_col": 6, "doj_col": 8},
    "DATA":    {"start_row": 3, "header_row": 2, "pnr_col": 2, "train_col": 6, "doj_col": 8},
    "FINAL":   {"start_row": 6, "header_row": 5, "pnr_col": 8, "train_col": 2, "doj_col": 13},
    "DATA2":   {"start_row": 4, "header_row": 3, "pnr_col": 8, "train_col": 2, "doj_col": 13},
    "EMAIL_DATA":{"start_row": 2, "header_row": 1, "pnr_col": 8, "train_col": 9, "doj_col": 12},
    "NOTE":    {"start_row": 2, "header_row": 1, "pnr_col": None, "train_col": 1, "doj_col": None}
}

# ============================================================
# LOAD SHEET DATA
# ============================================================
def load_sheet_data(sheet_name, force_refresh=False):
    cache_key = f"df_{sheet_name}"
    if not force_refresh and cache_key in st.session_state and st.session_state[cache_key] is not None:
        return st.session_state[cache_key]
    try:
        gc = init_sheets()
        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_name)
        all_data = sheet.get_all_values()
        config = SHEET_CONFIG.get(sheet_name, {"start_row": 1, "header_row": 1})
        start_row = config["start_row"]
        header_row = config.get("header_row", start_row - 1)
        if len(all_data) < header_row:
            st.session_state[cache_key] = pd.DataFrame()
            return pd.DataFrame()
        headers = all_data[header_row - 1] if header_row > 0 else []
        data_rows = all_data[start_row - 1:] if start_row <= len(all_data) else []
        if not data_rows:
            st.session_state[cache_key] = pd.DataFrame()
            return pd.DataFrame()
        num_cols = max(len(headers), len(data_rows[0]) if data_rows else 0, len(HEADINGS))
        if sheet_name == "EQ":
            headers = HEADINGS[:num_cols]
        else:
            seen = {}
            unique_headers = []
            for h in headers:
                h_str = str(h).strip() if h else ""
                if not h_str:
                    h_str = f"Col_{len(unique_headers)+1}"
                if h_str in seen:
                    seen[h_str] += 1
                    unique_headers.append(f"{h_str}_{seen[h_str]}")
                else:
                    seen[h_str] = 0
                    unique_headers.append(h_str)
            headers = unique_headers
        while len(headers) < num_cols:
            headers.append(f"Col_{len(headers)+1}")
        df = pd.DataFrame(data_rows, columns=headers[:num_cols])
        st.session_state[cache_key] = df
        return df
    except Exception as e:
        st.error(f"Error loading {sheet_name}: {e}")
        return pd.DataFrame()

def refresh_sheet_data(sheet_name):
    cache_key = f"df_{sheet_name}"
    st.session_state[cache_key] = None
    return load_sheet_data(sheet_name, force_refresh=True)

# ============================================================
# NOTE SHEET VALIDATOR
# ============================================================
def get_valid_trains():
    try:
        df = load_sheet_data("NOTE")
        if df.empty:
            return set()
        trains = set()
        for val in df.iloc[:, 0].dropna():
            v = str(val).strip()
            if v:
                trains.add(v.upper())
                trains.add(re.sub(r'\s*(DN|UP)$', '', v, flags=re.IGNORECASE).strip().upper())
        return trains
    except:
        return set()

def is_valid_train(train_num):
    valid = get_valid_trains()
    if not valid:
        return True
    t = str(train_num).strip().upper()
    if t in valid:
        return True
    t_clean = re.sub(r'\s*(DN|UP)$', '', t, flags=re.IGNORECASE).strip()
    return t_clean in valid

# ============================================================
# DRIVE UPLOAD
# ============================================================
def upload_to_drive(file_bytes, filename, mime_type):
    try:
        drive_service = init_drive()
        file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=True)
        file = drive_service.files().create(
            body=file_metadata, media_body=media,
            fields='id,name,webViewLink,size'
        ).execute()
        return {
            'success': True,
            'id': file.get('id'),
            'name': file.get('name'),
            'url': file.get('webViewLink'),
            'size': file.get('size')
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

def build_drive_links(file_id, file_name):
    view_url = f'https://drive.google.com/file/d/{file_id}/view?usp=sharing'
    print_url = f'https://drive.google.com/file/d/{file_id}/preview?usp=sharing'
    details = f"📄 EQ File Details:\n"
    details += f"━━━━━━━━━━━━━━━━━\n"
    details += f"📎 Name: {file_name}\n"
    details += f"🕐 Saved: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n"
    details += f"🔑 Drive ID: {file_id}\n"
    details += f"━━━━━━━━━━━━━━━━━"
    return {
        'x_formula': f'=HYPERLINK("{view_url}","📄 Click to Open")',
        'y_formula': f'=HYPERLINK("{print_url}","🖨️ Print")',
        'z_value': '👁️ View',
        'z_note': details
    }

# ============================================================
# GEMINI EXTRACTION ENGINE
# ============================================================
def get_gemini_system_prompt():
    return """You are TSKEQ Bot's AI extraction engine. Expert at reading messy, handwritten, torn, rotated, crooked, blurred, low-quality railway EQ forms, PDFs, images, and audio.

Extract these fields and return ONLY a valid JSON array. Each object = one passenger/entry.

REQUIRED FIELDS (return empty string "" if not found):
1. PNR - 10 digit number only
2. T_N - Train Number, 3 to 5 digits. Remove DN/UP suffixes.
3. CLASS - SL, 2A, 3A, CC, 1A, 2S, 3E, FC, etc.
4. DOJ - Date of Journey. Convert to DD-MM-YYYY. 
   CRITICAL: "24/25.06.26" or "24/25-06-2026" → use FIRST date only: "24-06-2026"
5. FROM - Station code (3-5 capital letters)
6. TO - Station code (3-5 capital letters)
7. BOARDING - Boarding station code (blank if not specified)
8. PASS_NAME - Full passenger name
9. PASS_PH - 10 digit phone. If +91 present, take LAST 10 digits.
10. T_BERTHS - Number of berths/seats demanded (default 1)
11. PURPOSE - Purpose of travel
12. ADDRESS - Full address
13. DIARY_NO - Diary number. PRESERVE AS-IS. Do NOT guess "RAIL BOARD".
14. RECOMMENDATION - Name of recommender or reference person
15. DESIGNATION - Designation of recommender (MP, MLA, OSD, DIR, ADDL, DD, etc.)
16. VIP_STATUS - One of: MP, MLA, MR, MINISTER, VIP, VVIP, or blank
17. APPLICATION_DATE - Date of application (DD-MM-YYYY)
18. RAILWAY_ZONE - Railway zone (NFR, NR, ER, WR, SR, SCR, SWR, CR, etc.)
19. PREFERENCE - General, MP, MLA, MR, Lower Seat, RAIL BOARD, etc.
20. PHONE_NUBER - Recommender's phone (LAST 10 digits)
21. WARRANT_NO - Warrant number (IC-240, MP-123, etc.)

=== RAIL BOARD RULE (STRICT) ===
ONLY set these if you EXPLICITLY see text like:
- "OFFICE OF THE HON'BLE MINISTER OF RAILWAYS"
- "MINISTER OF RAILWAYS" / "RAIL MANTRI" / "RAIL BHAWAN"
- "RAILWAY BOARD" / "RAIL BOARD"
If NOT explicitly seen, leave DIARY_NO, RAILWAY_ZONE, PREFERENCE empty strings.

=== MR vs MP/MLA RULE ===
- "MR" or "Member of Railway" → VIP_STATUS = "MR"
- "MP" or "Member of Parliament" → VIP_STATUS = "MP"
- "MLA" or "Member of Legislative Assembly" → VIP_STATUS = "MLA"
- "MINISTER" → VIP_STATUS = "MINISTER"
- "OSD", "PMO", "DIR", "ADDL", "DD", "LPA", "PS/MOS" → put in DESIGNATION

=== RECOMMENDATION & DESIGNATION LOGIC ===
- "Recommended by Shri Ram Prasad, MP" → RECOMMENDATION="Shri Ram Prasad", DESIGNATION="MP"
- "OSD to Minister" → RECOMMENDATION="OSD to Minister", DESIGNATION="OSD"
- If only a title given (just "MP" or "MLA"), put in DESIGNATION, leave RECOMMENDATION blank.
- Extract FULL name when available, not just initials.

=== OUTPUT FORMAT ===
Return ONLY a valid JSON array. NO extra text."""

def extract_from_file(file_bytes, file_type, caption=None):
    model = init_gemini()
    system_prompt = get_gemini_system_prompt()
    try:
        if file_type in ['image', 'pdf']:
            mime = 'image/jpeg' if file_type == 'image' else 'application/pdf'
            b64 = base64.b64encode(file_bytes).decode('utf-8')
            response = model.generate_content([system_prompt, {"mime_type": mime, "data": b64}])
        elif file_type == 'audio':
            b64 = base64.b64encode(file_bytes).decode('utf-8')
            response = model.generate_content([system_prompt, {"mime_type": "audio/mpeg", "data": b64}])
        elif file_type == 'text':
            response = model.generate_content(system_prompt + "\n\nINPUT DATA:\n" + str(caption))
        else:
            return {'error': 'Unsupported file type'}
        text = response.text
        json_str = None
        arr_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', text)
        if arr_match:
            json_str = arr_match.group(0)
        else:
            block_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
            if block_match:
                json_str = block_match.group(1)
            else:
                obj_match = re.search(r'\{\s*"[\s\S]*\}\s*', text)
                if obj_match:
                    json_str = "[" + obj_match.group(0) + "]"
        if not json_str:
            return {'error': 'No JSON found in response', 'raw': text[:800]}
        json_str = json_str.replace("'", '"')
        json_str = json_str.replace('```json', '').replace('```', '').strip()
        json_str = re.sub(r',\s*\}', '}', json_str)
        json_str = re.sub(r',\s*\]', ']', json_str)
        json_str = re.sub(r'\n\s*\n', '\n', json_str)
        records = json.loads(json_str)
        if isinstance(records, dict):
            records = [records]
        cleaned = []
        seen_pnrs = set()
        for r in records:
            pnr = clean_pnr(r.get('PNR', ''))
            if not pnr or pnr in seen_pnrs:
                continue
            seen_pnrs.add(pnr)
            doj = parse_date(r.get('DOJ', ''))
            if is_expired(doj):
                continue
            train = str(r.get('T_N', '')).strip()
            if train and not is_valid_train(train):
                continue
            rec = str(r.get('RECOMMENDATION', '')).strip()
            des = str(r.get('DESIGNATION', '')).strip()
            vip = str(r.get('VIP_STATUS', '')).strip().upper()
            if not des and rec:
                title_match = re.search(r'\b(MP|MLA|MINISTER|OSD|PMO|DIR|ADDL|DD|LPA|PS/MOS|ADV|MR|VIP|VVIP)\b', rec, re.I)
                if title_match:
                    des = title_match.group(1).upper()
            if rec.upper() in ['MP', 'MLA', 'MINISTER', 'OSD', 'PMO', 'DIR', 'ADDL', 'DD', 'VIP', 'VVIP', 'MR', '']:
                rec = ''
            diary_no = str(r.get('DIARY_NO', '')).strip()
            railway_zone = str(r.get('RAILWAY_ZONE', '')).strip()
            preference = str(r.get('PREFERENCE', '')).strip()
            raw_text = str(r)
            rail_board_keywords = ['MINISTER OF RAILWAYS', 'RAIL MANTRI', 'RAIL BHAWAN', 'RAILWAY BOARD', 'RAIL BOARD', "HON'BLE MINISTER"]
            is_rail_board = any(kw.upper() in raw_text.upper() for kw in rail_board_keywords)
            if not is_rail_board:
                if diary_no.upper() == 'RAIL BOARD':
                    diary_no = ''
                if railway_zone.upper() == 'RAIL BOARD':
                    railway_zone = ''
                if preference.upper() == 'RAIL BOARD':
                    preference = 'General'
            else:
                if not diary_no:
                    diary_no = 'RAIL BOARD'
                if not railway_zone:
                    railway_zone = 'RAIL BOARD'
                if not preference:
                    preference = 'RAIL BOARD'
                if not vip:
                    vip = 'MINISTER'
            cleaned.append({
                'PNR': pnr,
                'T_N': re.sub(r'\s*(DN|UP)$', '', train, flags=re.IGNORECASE).strip(),
                'CLASS': str(r.get('CLASS', '')).strip().upper(),
                'DOJ': doj,
                'FROM': str(r.get('FROM', '')).strip().upper(),
                'TO': str(r.get('TO', '')).strip().upper(),
                'BOARDING': str(r.get('BOARDING', '')).strip().upper(),
                'PASS_NAME': str(r.get('PASS_NAME', '')).strip(),
                'PASS_PH': clean_phone(r.get('PASS_PH', '')),
                'T_BERTHS': max(1, int(r.get('T_BERTHS', 1)) or 1),
                'PURPOSE': str(r.get('PURPOSE', '')).strip(),
                'ADDRESS': str(r.get('ADDRESS', '')).strip(),
                'DIARY_NO': diary_no,
                'RECOMMENDATION': rec,
                'DESIGNATION': des,
                'VIP_STATUS': vip,
                'APPLICATION_DATE': parse_date(r.get('APPLICATION_DATE', '')),
                'RAILWAY_ZONE': railway_zone,
                'PREFERENCE': preference if preference else 'General',
                'PHONE_NUBER': clean_phone(r.get('PHONE_NUBER', '')),
                'WARRANT_NO': str(r.get('WARRANT_NO', '')).strip()
            })
        return {'records': cleaned, 'count': len(cleaned)}
    except Exception as e:
        return {'error': f'Extraction error: {e}'}

# ============================================================
# GEMINI CHAT
# ============================================================
def gemini_chat(user_message, chat_history=None):
    model = init_gemini()
    system_msg = """You are TSKEQ Bot, a helpful AI assistant for railway EQ management. You can:
- Answer questions about railway quotas, PNR status, train schedules
- Help extract data from messy text
- Explain EQ sheet columns and processes
- Provide general railway information
- Chat naturally in Hindi or English

Be concise, helpful, and accurate."""
    try:
        if chat_history:
            convo = model.start_chat(history=chat_history)
            response = convo.send_message(user_message)
        else:
            response = model.generate_content(system_msg + "\n\nUser: " + user_message)
        return response.text
    except Exception as e:
        return f"❌ Error: {e}"

def get_suggested_questions():
    return [
        "🚂 How do I extract data from a messy railway form?",
        "📋 What do EQ sheet columns mean?",
        "🔍 How to check PNR status?",
        "🎫 What is the difference between 2A and 3A class?",
        "📅 How to format DOJ as DD-MM-YYYY?",
        "⭐ What is VIP quota in railways?",
        "📤 How to upload files to Google Drive?",
        "🔄 How does real-time sync work?",
    ]

# ============================================================
# SAVE TO EQ SHEET
# ============================================================
def save_records_to_sheet(records, uploaded_file_info=None):
    try:
        gc = init_sheets()
        sheet = gc.open_by_key(SHEET_ID).worksheet("EQ")
        all_data = sheet.get_all_values()
        existing_pnrs = set()
        for row in all_data[4:]:
            if row and len(row) > 1:
                p = clean_pnr(row[1])
                if p:
                    existing_pnrs.add(p)
        saved = 0
        now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        for rec in records:
            pnr = rec.get('PNR', '')
            if not pnr or pnr in existing_pnrs:
                continue
            next_row = len(all_data) + 1
            sno = next_row - 4
            row_data = [
                sno, pnr,
                get_station(rec.get('FROM', '')),
                get_station(rec.get('TO', '')),
                get_station(rec.get('BOARDING', '')),
                rec.get('T_N', ''),
                rec.get('CLASS', ''),
                rec.get('DOJ', ''),
                rec.get('PASS_NAME', ''),
                rec.get('PASS_PH', ''),
                rec.get('T_BERTHS', 1),
                rec.get('PURPOSE', ''),
                rec.get('ADDRESS', ''),
                rec.get('DIARY_NO', ''),
                rec.get('RECOMMENDATION', ''),
                rec.get('DESIGNATION', ''),
                rec.get('PHONE_NUBER', ''),
                rec.get('VIP_STATUS', ''),
                rec.get('WARRANT_NO', ''),
                now,
                rec.get('APPLICATION_DATE', ''),
                rec.get('RAILWAY_ZONE', ''),
                rec.get('PREFERENCE', 'General')
            ]
            if uploaded_file_info and uploaded_file_info.get('success'):
                links = build_drive_links(uploaded_file_info['id'], uploaded_file_info['name'])
                row_data.extend([
                    links['x_formula'],
                    links['y_formula'],
                    links['z_value'],
                    f'=HYPERLINK("https://www.confirmtkt.com/pnr-status/{pnr}","🔍 Check PNR")'
                ])
                sheet.append_row(row_data)
                try:
                    sheet.update_note(f"Z{next_row}", links['z_note'])
                except:
                    pass
            else:
                row_data.extend([
                    '', '', '',
                    f'=HYPERLINK("https://www.confirmtkt.com/pnr-status/{pnr}","🔍 Check PNR")'
                ])
                sheet.append_row(row_data)
            existing_pnrs.add(pnr)
            saved += 1
            time.sleep(0.3)
        format_eq_sheet(sheet)
        st.session_state['df_EQ'] = None
        return {'saved': saved}
    except Exception as e:
        return {'error': str(e)}

def format_eq_sheet(sheet):
    try:
        all_data = sheet.get_all_values()
        lr = len(all_data)
        colors = get_flag_colors()
        if colors and lr >= 5:
            sheet.format('A4:I4', {
                'backgroundColor': colors['saffron'],
                'textFormat': {'bold': True, 'foregroundColor': {'red':1,'green':1,'blue':1}},
                'horizontalAlignment': 'CENTER'
            })
            sheet.format('J4:Q4', {
                'backgroundColor': colors['white'],
                'textFormat': {'bold': True},
                'horizontalAlignment': 'CENTER'
            })
            sheet.format('R4:AA4', {
                'backgroundColor': colors['green'],
                'textFormat': {'bold': True, 'foregroundColor': {'red':1,'green':1,'blue':1}},
                'horizontalAlignment': 'CENTER'
            })
        elif lr >= 4:
            sheet.format('A4:AA4', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.88, 'green': 0.88, 'blue': 0.88},
                'horizontalAlignment': 'CENTER',
                'verticalAlignment': 'MIDDLE'
            })
        if lr >= 5:
            sheet.format(f'A5:AA{lr}', {
                'horizontalAlignment': 'CENTER',
                'verticalAlignment': 'MIDDLE',
                'wrapStrategy': 'WRAP'
            })
    except:
        pass

# ============================================================
# CRUD OPERATIONS
# ============================================================
def update_sheet_row(sheet_name, actual_row, row_values):
    try:
        gc = init_sheets()
        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_name)
        num_cols = len(row_values)
        end_col = col_index_to_letter(num_cols)
        range_name = f"A{actual_row}:{end_col}{actual_row}"
        sheet.update(range_name, [row_values])
        st.session_state[f'df_{sheet_name}'] = None
        return True
    except Exception as e:
        st.error(f"Update error: {e}")
        return False

def delete_sheet_rows(sheet_name, actual_rows):
    try:
        gc = init_sheets()
        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_name)
        for r in sorted(actual_rows, reverse=True):
            sheet.delete_rows(r)
        st.session_state[f'df_{sheet_name}'] = None
        return True
    except Exception as e:
        st.error(f"Delete error: {e}")
        return False

def add_blank_row(sheet_name):
    try:
        gc = init_sheets()
        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_name)
        all_data = sheet.get_all_values()
        num_cols = max(len(all_data[0]) if all_data else 0, 27)
        blank = [''] * num_cols
        config = SHEET_CONFIG.get(sheet_name, {"start_row": 1})
        start_row = config["start_row"]
        next_sn = len(all_data) - start_row + 2 if len(all_data) >= start_row else 1
        blank[0] = next_sn
        sheet.append_row(blank)
        st.session_state[f'df_{sheet_name}'] = None
        return True
    except Exception as e:
        st.error(f"Add row error: {e}")
        return False

# ============================================================
# THEME & STYLING
# ============================================================
def apply_theme(dark_mode):
    if dark_mode:
        bg = "#0e1117"
        card_bg = "#1e1e2e"
        text = "#e0e0e0"
        border = "#3a3a4a"
        input_bg = "#262730"
        header_bg = "#1a1a2e"
    else:
        bg = "#f5f7fa"
        card_bg = "#ffffff"
        text = "#1e1e2e"
        border = "#d1d5db"
        input_bg = "#ffffff"
        header_bg = "#ffffff"

    st.markdown(f"""
    <style>
        .stApp {{ background-color: {bg} !important; }}
        .main .block-container {{ padding-top: 1rem; padding-bottom: 1rem; }}
        .stMetric {{ background-color: {card_bg}; border-radius: 12px; padding: 12px; border: 1px solid {border}; }}
        .stMetric label {{ color: {text} !important; }}
        .stMetric div {{ color: {text} !important; }}
        .pro-title {{ font-size: 2.2rem; font-weight: 800; color: {text}; text-align: center; margin-bottom: 0.2rem; }}
        .pro-subtitle {{ color: {text}; opacity: 0.7; text-align: center; font-size: 1.1rem; margin-bottom: 1rem; }}
        h1, h2, h3, h4, p, label, .stMarkdown {{ color: {text} !important; }}
        .stButton button {{ border-radius: 8px; font-weight: 600; }}
        .stDataFrame thead th {{ background: #2d7d46 !important; color: white !important; font-weight: 600 !important; }}
        .stDataFrame tbody td {{ color: {text} !important; }}
        .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {{ 
            background-color: {input_bg} !important; 
            color: {text} !important;
            border-color: {border} !important;
        }}
        .pro-footer {{ text-align: center; padding: 20px 0 10px; opacity: 0.5; font-size: 0.8rem; border-top: 1px solid {border}; margin-top: 30px; color: {text}; }}
        .link-btn {{ display: inline-block; padding: 4px 12px; margin: 2px; border-radius: 6px; text-decoration: none; font-size: 0.8rem; font-weight: 600; }}
        .link-view {{ background: #E3F2FD; color: #1565C0; }}
        .link-print {{ background: #E8F5E9; color: #2E7D32; }}
        .link-pnr {{ background: #FFF3E0; color: #E65100; }}
        .hover-box {{ background: {card_bg}; border: 1px solid {border}; border-radius: 8px; padding: 10px; font-size: 0.85rem; max-width: 300px; color: {text}; }}
        .chat-user {{ background: {card_bg}; border: 1px solid {border}; border-radius: 12px; padding: 10px 14px; margin: 6px 0; margin-left: 40px; }}
        .chat-bot {{ background: #e3f2fd; border: 1px solid #bbdefb; border-radius: 12px; padding: 10px 14px; margin: 6px 0; margin-right: 40px; }}
        .suggested-q {{ background: {card_bg}; border: 1px solid {border}; border-radius: 20px; padding: 6px 14px; margin: 3px; cursor: pointer; font-size: 0.85rem; display: inline-block; color: {text}; }}
        .suggested-q:hover {{ background: #2d7d46; color: white; border-color: #2d7d46; }}
        @media print {{
            .stApp {{ background-color: white !important; }}
            .main .block-container {{ max-width: 100% !important; padding: 0 !important; }}
            .stSidebar, .stButton, .stSelectbox, .stTextInput, .stDateInput, .pro-footer {{ display: none !important; }}
        }}
    </style>
    """, unsafe_allow_html=True)

# ============================================================
# MAIN APP
# ============================================================
def main():
    # Session state init
    if 'last_refresh' not in st.session_state:
        st.session_state.last_refresh = time.time()
    if 'export_data' not in st.session_state:
        st.session_state.export_data = None
    if 'export_sheet' not in st.session_state:
        st.session_state.export_sheet = None
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    if 'chat_input_key' not in st.session_state:
        st.session_state.chat_input_key = 0

    # Theme
    dark_mode = st.sidebar.toggle("🌙 Dark Mode", value=False, key="dark_mode_toggle")
    apply_theme(dark_mode)

    # Sidebar Header
    st.sidebar.title("⚡ AI EQMS Hub Pro")
    now = datetime.now()
    st.sidebar.write(f"📅 {now.strftime('%d-%m-%Y')}")
    st.sidebar.write(f"🕐 {now.strftime('%H:%M:%S')}")

    # Greeting
    hour = now.hour
    if 5 <= hour < 12:
        if is_flag_time():
            st.sidebar.markdown("""
            🇮🇳 **Good Morning!**
            <div style="color:#FF9933">🟠 Saffron</div>
            <div style="color:#000000">⚪ White</div>
            <div style="color:#138808">🟢 Green</div>
            """, unsafe_allow_html=True)
        else:
            st.sidebar.markdown("☀️ **Good Morning!**")
    elif 12 <= hour < 17:
        st.sidebar.markdown("🌤️ **Good Afternoon!**")
    elif 17 <= hour < 21:
        st.sidebar.markdown("🌆 **Good Evening!**")
    else:
        st.sidebar.markdown("🌙 **Good Night!**")

    st.sidebar.markdown("---")

    # Auto Refresh
    auto_refresh = st.sidebar.checkbox("🔄 Auto Sync (30s)", value=True, key="auto_sync")
    if auto_refresh:
        if time.time() - st.session_state.last_refresh > 30:
            st.session_state.last_refresh = time.time()
            for key in list(st.session_state.keys()):
                if key.startswith('df_'):
                    st.session_state[key] = None
            st.rerun()

    # File Upload
    st.sidebar.subheader("📤 Upload Railway Form")
    uploaded_file = st.sidebar.file_uploader(
        "Image / PDF / Audio / Text",
        type=['png','jpg','jpeg','pdf','mp3','wav','ogg','txt'],
        key="file_uploader"
    )
    caption = st.sidebar.text_area("Caption / Text (optional)", height=80, key="caption")

    if st.sidebar.button("🚀 Process & Save to EQ", use_container_width=True, type="primary", key="process_btn"):
        if uploaded_file or caption:
            with st.spinner("🤖 Gemini AI extracting..."):
                drive_result = {'success': False}
                start_time = time.time()
                if uploaded_file:
                    file_bytes = uploaded_file.read()
                    mime = uploaded_file.type
                    if mime == 'application/pdf':
                        file_type = 'pdf'
                    elif mime.startswith('audio/'):
                        file_type = 'audio'
                    else:
                        file_type = 'image'
                    result = extract_from_file(file_bytes, file_type, caption)
                    drive_result = upload_to_drive(file_bytes, uploaded_file.name, mime)
                    if drive_result['success']:
                        st.sidebar.success(f"📁 Drive: {drive_result['name']}")
                else:
                    result = extract_from_file(None, 'text', caption)
                elapsed = round(time.time() - start_time, 2)
                if 'error' in result:
                    st.sidebar.error(f"❌ Extraction failed: {result['error']}")
                    if 'raw' in result:
                        with st.sidebar.expander("Raw Response"):
                            st.code(result['raw'])
                elif result['count'] == 0:
                    st.sidebar.warning("⚠️ No valid records. Reasons: expired DOJ, train not in NOTE, or unclear data.")
                else:
                    save_result = save_records_to_sheet(result['records'], drive_result)
                    if 'error' in save_result:
                        st.sidebar.error(f"❌ Save error: {save_result['error']}")
                    else:
                        st.sidebar.success(f"✅ Saved {save_result['saved']} records in {elapsed}s!")
                        st.session_state.last_refresh = time.time()
                        time.sleep(0.5)
                        st.rerun()
        else:
            st.sidebar.warning("📎 Upload a file or enter text.")

    st.sidebar.markdown("---")
    sheet_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
    st.sidebar.markdown(f"[🔗 Open Google Sheet]({sheet_url})")

    # Main Header
    st.markdown("<div class='pro-title'>🚂 AI EQMS Hub Pro</div>", unsafe_allow_html=True)
    st.markdown("<div class='pro-subtitle'>Enterprise Railway EQ Management System with Real-Time Sync</div>", unsafe_allow_html=True)
    st.markdown("---")

    # Tabs
    tab_main, tab_eqlist, tab_report, tab_chat = st.tabs([
        "📊 Sheet Manager", "🚂 EQ List by Train", "📈 Final Report", "💬 Gemini Chat"
    ])

    # ============================================================
    # TAB 1: SHEET MANAGER
    # ============================================================
    with tab_main:
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            sheet_choice = st.selectbox("📊 Select Sheet", list(SHEET_CONFIG.keys()), index=0, key="sheet_select")
        with c2:
            st.write("")
            st.write("")
            if st.button("🔄 Sync Now", use_container_width=True, key="sync_now"):
                st.session_state.last_refresh = time.time()
                for key in list(st.session_state.keys()):
                    if key.startswith('df_'):
                        st.session_state[key] = None
                st.toast("🔄 Synced with Google Sheets!", icon="🔄")
                st.rerun()
        with c3:
            st.write("")
            st.write("")
            live_badge = "🟢 Live" if auto_refresh else "⚪ Manual"
            st.markdown(f"<div style='text-align:right;font-weight:600;'>{live_badge}</div>", unsafe_allow_html=True)

        config = SHEET_CONFIG[sheet_choice]
        start_row = config["start_row"]

        # Load data
        df = load_sheet_data(sheet_choice)

        if df.empty:
            st.warning(f"⚠️ No data in **{sheet_choice}** sheet.")
            st.info("💡 Upload a railway form from the sidebar or click '➕ Add Row'.")

        # Metrics
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("📋 Total Records", len(df))
        with m2:
            if sheet_choice == "EQ" and not df.empty and 'DOJ' in df.columns:
                expired = sum(1 for _, r in df.iterrows() if is_expired(r.get('DOJ', '')))
                st.metric("⏰ Expired DOJ", expired)
            else:
                st.metric("📁 Sheets", len(SHEET_CONFIG))
        with m3:
            if sheet_choice == "EQ":
                st.metric("🚂 NOTE Trains", len(get_valid_trains()))
            else:
                st.metric("📅 Today", datetime.now().strftime("%d-%m-%Y"))
        with m4:
            st.metric("⏱️ Last Sync", f"{int(time.time() - st.session_state.last_refresh)}s ago")

        # Filters
        with st.expander("🔍 Filters & Search", expanded=False):
            fc1, fc2, fc3 = st.columns(3)
            with fc1:
                pnr_f = st.text_input("🔢 PNR", key=f"pnr_{sheet_choice}")
            with fc2:
                train_f = st.text_input("🚂 Train", key=f"train_{sheet_choice}")
            with fc3:
                name_f = st.text_input("👤 Name", key=f"name_{sheet_choice}")

            fc4, fc5, fc6 = st.columns(3)
            with fc4:
                from_d = st.date_input("From DOJ", value=None, key=f"from_{sheet_choice}")
            with fc5:
                to_d = st.date_input("To DOJ", value=None, key=f"to_{sheet_choice}")
            with fc6:
                class_f = st.text_input("🎫 Class", key=f"class_{sheet_choice}")

            fc7, fc8 = st.columns([1, 1])
            with fc7:
                if st.button("🧹 Clear Filters", use_container_width=True, key="clear_filters"):
                    for k in list(st.session_state.keys()):
                        if k.startswith((f"pnr_{sheet_choice}", f"train_{sheet_choice}", f"name_{sheet_choice}",
                                         f"from_{sheet_choice}", f"to_{sheet_choice}", f"class_{sheet_choice}")):
                            del st.session_state[k]
                    st.rerun()
            with fc8:
                expired_only = st.checkbox("⏰ Expired Only", value=False, key="expired_only")

        # Apply filters
        filtered = df.copy()
        if pnr_f and 'PNR' in filtered.columns:
            filtered = filtered[filtered['PNR'].astype(str).str.contains(pnr_f, case=False, na=False)]
        if train_f and 'T/N' in filtered.columns:
            filtered = filtered[filtered['T/N'].astype(str).str.contains(train_f, case=False, na=False)]
        if name_f and 'PASS NAME' in filtered.columns:
            filtered = filtered[filtered['PASS NAME'].astype(str).str.contains(name_f, case=False, na=False)]
        if class_f and 'CLASS' in filtered.columns:
            filtered = filtered[filtered['CLASS'].astype(str).str.contains(class_f, case=False, na=False)]
        if from_d or to_d:
            if 'DOJ' in filtered.columns:
                try:
                    filtered['_td'] = pd.to_datetime(filtered['DOJ'], format='%d-%m-%Y', errors='coerce')
                    if from_d:
                        filtered = filtered[filtered['_td'] >= pd.Timestamp(from_d)]
                    if to_d:
                        filtered = filtered[filtered['_td'] <= pd.Timestamp(to_d)]
                    filtered = filtered.drop('_td', axis=1)
                except:
                    pass
        if expired_only and 'DOJ' in filtered.columns:
            filtered = filtered[filtered['DOJ'].apply(is_expired)]

        # Pagination
        st.subheader(f"📋 {sheet_choice} — {len(filtered)} records")
        ps = st.selectbox("Rows/page", [10, 25, 50, 100, 200], index=1, key=f"ps_{sheet_choice}")
        total_pages = max(1, (len(filtered) + ps - 1) // ps)
        pg = st.number_input("Page", 1, total_pages, 1, key=f"pg_{sheet_choice}") - 1
        si = pg * ps
        ei = min(si + ps, len(filtered))
        page_df = filtered.iloc[si:ei].copy()

        if not page_df.empty:
            # Use session state for selection to avoid data_editor boolean mask issues
            select_key = f"select_rows_{sheet_choice}_{pg}"
            if select_key not in st.session_state:
                st.session_state[select_key] = [False] * len(page_df)

            # Create display dataframe WITHOUT Select column in data_editor
            display_df = page_df.copy()
            link_cols = ['LINK (Click to Open)', 'PRINT (A4 Size)', 'PNR STATUS LINK']
            for lc in link_cols:
                if lc in display_df.columns:
                    display_df[lc] = display_df[lc].apply(lambda x: extract_hyperlink_url(x) or x)

            edited = st.data_editor(
                display_df,
                use_container_width=True,
                height=500,
                num_rows="dynamic" if sheet_choice == "EQ" else "fixed",
                column_config={
                    "DOJ": st.column_config.TextColumn("DOJ", help="DD-MM-YYYY"),
                    "T/BERTHS": st.column_config.NumberColumn("Berths", min_value=1, max_value=50),
                    "CLASS": st.column_config.TextColumn("Class"),
                    "PNR": st.column_config.TextColumn("PNR"),
                },
                key=f"ed_{sheet_choice}_{pg}"
            )

            # Selection via multiselect (safer than boolean mask)
            st.markdown("---")
            st.write("**📝 Select rows for Delete / Export:**")
            row_options = []
            for i, (idx, row) in enumerate(page_df.iterrows()):
                label = f"Row {idx+1}"
                if 'PNR' in row and row['PNR']:
                    label += f" | PNR: {row['PNR']}"
                if 'PASS NAME' in row and row['PASS NAME']:
                    label += f" | {row['PASS NAME']}"
                row_options.append((idx, label))

            selected_labels = st.multiselect(
                "Select rows:",
                options=[label for _, label in row_options],
                key=f"ms_{sheet_choice}_{pg}"
            )
            sel_idx = [idx for idx, label in row_options if label in selected_labels]

            # Action Buttons
            b1, b2, b3, b4, b5 = st.columns(5)

            with b1:
                if st.button("💾 Save Edits", use_container_width=True, type="primary", key="save_edits"):
                    try:
                        edit_data = edited
                        orig_data = page_df
                        changed_count = 0
                        for i, (idx, row) in enumerate(edit_data.iterrows()):
                            orig = orig_data.iloc[i]
                            vals = []
                            row_changed = False
                            for c in edit_data.columns:
                                v = row[c]
                                v_str = '' if pd.isna(v) else str(v)
                                orig_str = str(orig.get(c, ''))
                                if v_str != orig_str:
                                    row_changed = True
                                vals.append(v_str)
                            if row_changed:
                                actual_row = start_row + si + i
                                if update_sheet_row(sheet_choice, actual_row, vals):
                                    changed_count += 1
                                time.sleep(0.2)
                        if changed_count > 0:
                            st.toast(f"✅ Saved {changed_count} rows to Google Sheet!", icon="💾")
                            st.session_state.last_refresh = time.time()
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.info("ℹ️ No changes detected.")
                    except Exception as e:
                        if "429" in str(e):
                            st.error("❌ Quota exceeded. Wait 1 minute.")
                        else:
                            st.error(f"Save error: {e}")

            with b2:
                if st.button("➕ Add Row", use_container_width=True, key="add_row"):
                    if add_blank_row(sheet_choice):
                        st.toast("✅ Row added!", icon="➕")
                        st.session_state.last_refresh = time.time()
                        time.sleep(0.5)
                        st.rerun()

            with b3:
                if sel_idx:
                    if st.button("🗑️ Delete", use_container_width=True, key="delete_rows"):
                        actual_rows = [start_row + si + (idx - page_df.index[0]) for idx in sel_idx]
                        if delete_sheet_rows(sheet_choice, actual_rows):
                            st.toast(f"🗑️ Deleted {len(sel_idx)} rows!", icon="🗑️")
                            st.session_state.last_refresh = time.time()
                            time.sleep(0.5)
                            st.rerun()
                else:
                    st.button("🗑️ Delete", disabled=True, use_container_width=True, key="delete_rows_d")

            with b4:
                if st.button("🔄 Refresh", use_container_width=True, key="refresh_btn"):
                    st.session_state.last_refresh = time.time()
                    for key in list(st.session_state.keys()):
                        if key.startswith('df_'):
                            st.session_state[key] = None
                    st.rerun()

            with b5:
                if sel_idx:
                    if st.button("📤 Export", use_container_width=True, key="export_btn"):
                        exp = page_df.loc[sel_idx]
                        st.session_state.export_data = exp
                        st.session_state.export_sheet = sheet_choice
                        st.toast(f"📤 {len(exp)} rows ready for export!")
                else:
                    st.button("📤 Export", disabled=True, use_container_width=True, key="export_btn_d")

            # Quick Links (EQ only)
            if sheet_choice == "EQ":
                st.markdown("---")
                st.subheader("🔗 File Links & PNR Status")
                for idx, row in page_df.iterrows():
                    rnum = idx + 1
                    cc1, cc2, cc3, cc4, cc5 = st.columns([1, 2, 2, 2, 2])
                    with cc1:
                        st.markdown(f"**Row {rnum}**")
                    with cc2:
                        x_url = extract_hyperlink_url(row.get('LINK (Click to Open)', ''))
                        if x_url:
                            st.markdown(f'<a href="{x_url}" target="_blank" class="link-btn link-view">📄 View File</a>', unsafe_allow_html=True)
                        else:
                            st.markdown("<span style='opacity:0.4'>—</span>", unsafe_allow_html=True)
                    with cc3:
                        y_url = extract_hyperlink_url(row.get('PRINT (A4 Size)', ''))
                        if y_url:
                            st.markdown(f'<a href="{y_url}" target="_blank" class="link-btn link-print">🖨️ Print File</a>', unsafe_allow_html=True)
                        else:
                            st.markdown("<span style='opacity:0.4'>—</span>", unsafe_allow_html=True)
                    with cc4:
                        z_val = row.get('VIEW (Hover Details)', '')
                        if z_val and str(z_val).strip():
                            with st.popover(f"👁️ Details"):
                                st.markdown(f"<div class='hover-box'>{z_val}</div>", unsafe_allow_html=True)
                        else:
                            st.markdown("<span style='opacity:0.4'>—</span>", unsafe_allow_html=True)
                    with cc5:
                        pnr = clean_pnr(row.get('PNR', ''))
                        if pnr:
                            pnr_url = f"https://www.confirmtkt.com/pnr-status/{pnr}"
                            st.markdown(f'<a href="{pnr_url}" target="_blank" class="link-btn link-pnr">🔍 PNR {pnr}</a>', unsafe_allow_html=True)
                        else:
                            st.markdown("<span style='opacity:0.4'>—</span>", unsafe_allow_html=True)

            # Export Section
            if st.session_state.get('export_data') is not None:
                st.markdown("---")
                st.subheader("📄 Export Selected")
                exp_df = st.session_state.export_data
                e1, e2, e3 = st.columns(3)
                with e1:
                    csv = exp_df.to_csv(index=False).encode('utf-8')
                    st.download_button("📥 CSV", csv, f"{sheet_choice}_export.csv", "text/csv", use_container_width=True)
                with e2:
                    try:
                        pdf = FPDF('L', 'mm', 'A4')
                        pdf.add_page()
                        pdf.set_font("Arial", 'B', 14)
                        pdf.cell(0, 10, f"{sheet_choice} Export", ln=True, align='C')
                        pdf.ln(5)
                        pdf.set_font("Arial", 'B', 8)
                        cols = exp_df.columns.tolist()
                        cw = 260 / len(cols) if cols else 20
                        for c in cols:
                            pdf.cell(cw, 7, str(c)[:12].encode('latin-1','ignore').decode('latin-1'), border=1, align='C')
                        pdf.ln()
                        pdf.set_font("Arial", '', 7)
                        for _, r in exp_df.iterrows():
                            for c in cols:
                                v = str(r[c])[:15] if pd.notna(r[c]) else ''
                                pdf.cell(cw, 6, v.encode('latin-1','ignore').decode('latin-1'), border=1, align='L')
                            pdf.ln()
                        pdf_bytes = pdf.output(dest='S').encode('latin-1')
                        st.download_button("📥 PDF", pdf_bytes, f"{sheet_choice}_export.pdf", "application/pdf", use_container_width=True)
                    except Exception as e:
                        st.warning(f"PDF error: {e}")
                with e3:
                    msg = f"📊 {sheet_choice} Export\nTotal: {len(exp_df)} rows"
                    if 'PNR' in exp_df.columns:
                        pnrs = exp_df['PNR'].dropna().astype(str).tolist()[:10]
                        msg += f"\nPNRs: {', '.join(pnrs)}"
                    wa = f"https://api.whatsapp.com/send?text={msg.replace(' ', '%20').replace(chr(10), '%0A')}"
                    st.markdown(f'<a href="{wa}" target="_blank"><button style="width:100%;padding:8px;background:#25D366;color:white;border:none;border-radius:8px;font-weight:600;">📱 WhatsApp</button></a>', unsafe_allow_html=True)
        else:
            st.info("📭 No rows match your filters. Adjust filters or add data.")

        # Print Full View
        st.markdown("---")
        st.subheader("🖨️ Print / Export Full View")
        p1, p2 = st.columns(2)
        with p1:
            if st.button("🖨️ Print Table", use_container_width=True, key="print_table"):
                p_df = filtered.copy()
                html = p_df.to_html(index=False, classes='print-table', border=1)
                st.components.v1.html(f"""
                <html><head><style>
                body {{font-family:Arial;padding:20px;}}
                table {{width:100%;border-collapse:collapse;font-size:9px;}}
                th {{background:#2d7d46;color:white;padding:5px;border:1px solid #000;}}
                td {{padding:4px;border:1px solid #000;}}
                </style></head><body>
                <h3>{sheet_choice} — {datetime.now().strftime('%d-%m-%Y %H:%M')}</h3>
                {html}
                <script>window.onload=function(){{window.print();}}</script>
                </body></html>
                """, height=600, scrolling=True)
        with p2:
            try:
                csv_full = filtered.to_csv(index=False).encode('utf-8')
                st.download_button("📥 CSV Full", csv_full, f"{sheet_choice}_full.csv", "text/csv", use_container_width=True)
            except:
                pass

    # ============================================================
    # TAB 2: EQ LIST BY TRAIN
    # ============================================================
    with tab_eqlist:
        st.subheader("🚂 EQ List by Train Number")
        train_input = st.text_input("Enter Train Number (e.g., 15909)", key="eq_train_input")
        if train_input:
            eq_df = load_sheet_data("EQ")
            if not eq_df.empty and 'T/N' in eq_df.columns:
                train_df = eq_df[eq_df['T/N'].astype(str).str.contains(train_input, case=False, na=False)]
                if not train_df.empty:
                    st.success(f"✅ Found {len(train_df)} entries for Train {train_input}")
                    show_cols = ['S/N', 'PNR', 'FROM', 'TO', 'DOJ', 'CLASS', 'T/BERTHS', 'PASS NAME', 'PASS PH', 'PREFERENCE']
                    avail_cols = [c for c in show_cols if c in train_df.columns]
                    st.dataframe(train_df[avail_cols], use_container_width=True, hide_index=True)
                    st.markdown("---")
                    st.subheader("🪑 Seat Assignment")
                    for idx, row in train_df.iterrows():
                        c1, c2, c3 = st.columns([2, 1, 1])
                        with c1:
                            st.write(f"**{row.get('PASS NAME', 'N/A')}** | PNR: {row.get('PNR', 'N/A')} | {row.get('CLASS', '')}")
                        with c2:
                            current_berths = row.get('T/BERTHS', 1)
                            new_berths = st.number_input(
                                f"Seats for {row.get('PNR', idx)}",
                                min_value=1, max_value=50,
                                value=int(current_berths) if str(current_berths).isdigit() else 1,
                                key=f"seat_{idx}"
                            )
                        with c3:
                            if st.button("💾 Update", key=f"update_seat_{idx}"):
                                actual_row = SHEET_CONFIG["EQ"]["start_row"] + idx
                                try:
                                    gc = init_sheets()
                                    sheet = gc.open_by_key(SHEET_ID).worksheet("EQ")
                                    sheet.update_cell(actual_row, 11, new_berths)
                                    st.toast(f"✅ Updated berths to {new_berths}!", icon="🪑")
                                    st.session_state['df_EQ'] = None
                                    time.sleep(0.5)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Update failed: {e}")
                else:
                    st.warning(f"⚠️ No EQ entries found for Train {train_input}")
            else:
                st.info("📭 EQ sheet is empty.")

    # ============================================================
    # TAB 3: FINAL REPORT
    # ============================================================
    with tab_report:
        st.subheader("📈 Final Report & Quota Summary")
        eq_df = load_sheet_data("EQ")
        if not eq_df.empty:
            if 'CLASS' in eq_df.columns and 'T/BERTHS' in eq_df.columns:
                st.markdown("#### 📊 Class-wise Demand")
                eq_df['T_BERTHS_NUM'] = pd.to_numeric(eq_df['T/BERTHS'], errors='coerce').fillna(0)
                class_summary = eq_df.groupby('CLASS')['T_BERTHS_NUM'].agg(['sum', 'count']).reset_index()
                class_summary.columns = ['Class', 'Total Berths', 'Entries']
                st.dataframe(class_summary, use_container_width=True, hide_index=True)
                try:
                    fig = px.bar(class_summary, x='Class', y='Total Berths', color='Class',
                                 title='Berth Demand by Class', text='Total Berths')
                    st.plotly_chart(fig, use_container_width=True)
                except:
                    pass
            if 'T/N' in eq_df.columns:
                st.markdown("#### 🚂 Train-wise Summary")
                train_summary = eq_df.groupby('T/N').size().reset_index(name='Count')
                st.dataframe(train_summary, use_container_width=True, hide_index=True)
            vip_col = 'MP/MLA/MR/MINISTER/VIP/VVIP'
            if vip_col in eq_df.columns:
                st.markdown("#### ⭐ VIP Status Summary")
                vip_summary = eq_df[eq_df[vip_col].astype(str).str.strip() != ''].groupby(vip_col).size().reset_index(name='Count')
                if not vip_summary.empty:
                    st.dataframe(vip_summary, use_container_width=True, hide_index=True)
                else:
                    st.info("No VIP entries found.")
            if 'DOJ' in eq_df.columns:
                st.markdown("#### 📅 Upcoming Journeys (Next 7 Days)")
                try:
                    eq_df['_doj_dt'] = pd.to_datetime(eq_df['DOJ'], format='%d-%m-%Y', errors='coerce')
                    today = pd.Timestamp.now().normalize()
                    upcoming = eq_df[(eq_df['_doj_dt'] >= today) & (eq_df['_doj_dt'] <= today + pd.Timedelta(days=7))]
                    if not upcoming.empty:
                        show_cols = ['PNR', 'T/N', 'DOJ', 'CLASS', 'PASS NAME', 'FROM', 'TO']
                        avail = [c for c in show_cols if c in upcoming.columns]
                        st.dataframe(upcoming[avail], use_container_width=True, hide_index=True)
                    else:
                        st.info("No upcoming journeys in next 7 days.")
                    eq_df = eq_df.drop('_doj_dt', axis=1, errors='ignore')
                except:
                    pass
        else:
            st.info("📭 No data in EQ sheet for report generation.")

    # ============================================================
    # TAB 4: GEMINI CHAT
    # ============================================================
    with tab_chat:
        st.subheader("💬 Gemini AI Chat Assistant")
        st.markdown("Ask anything about railway EQ management, PNR status, quotas, or get help with data extraction.")

        # Suggested Questions
        st.markdown("#### 💡 Suggested Questions")
        suggestions = get_suggested_questions()
        sugg_cols = st.columns(4)
        for i, sq in enumerate(suggestions):
            with sugg_cols[i % 4]:
                if st.button(sq, key=f"sugg_{i}", use_container_width=True):
                    st.session_state.chat_input_value = sq
                    st.rerun()

        # Chat Input
        chat_input = st.text_input(
            "Your message:",
            value=st.session_state.get('chat_input_value', ''),
            key=f"chat_input_{st.session_state.chat_input_key}"
        )

        if st.button("📤 Send", type="primary", key="chat_send") and chat_input.strip():
            with st.spinner("🤖 Gemini thinking..."):
                # Build chat history for context
                hist = []
                for msg in st.session_state.chat_history[-10:]:
                    role = "user" if msg['role'] == 'user' else "model"
                    hist.append({"role": role, "parts": [msg['content']]})

                response = gemini_chat(chat_input, hist if hist else None)

                st.session_state.chat_history.append({"role": "user", "content": chat_input})
                st.session_state.chat_history.append({"role": "bot", "content": response})
                st.session_state.chat_input_key += 1
                st.session_state.chat_input_value = ""
                st.rerun()

        # Display Chat History
        st.markdown("---")
        st.markdown("#### 🗨️ Conversation")
        for msg in st.session_state.chat_history:
            if msg['role'] == 'user':
                st.markdown(f'<div class="chat-user"><b>👤 You:</b><br>{msg["content"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="chat-bot"><b>🤖 Gemini:</b><br>{msg["content"]}</div>', unsafe_allow_html=True)

        if st.session_state.chat_history:
            if st.button("🗑️ Clear Chat", key="clear_chat"):
                st.session_state.chat_history = []
                st.rerun()

    # ---- FOOTER ----
    st.markdown("<div class='pro-footer'>© 2026 AI EQMS Hub Pro — Created by Sharique 🚂</div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
