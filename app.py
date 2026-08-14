import streamlit as st
import pandas as pd
import json
import re
import base64
import io
import time
from datetime import datetime, timedelta
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.service_account import Credentials as GDriveCredentials
from fpdf import FPDF

st.set_page_config(page_title="AI EQMS Hub Pro", page_icon="🚂", layout="wide")

# ============================================================
# CONFIG & CREDENTIALS
# ============================================================
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
GSPREAD_CREDENTIALS = st.secrets.get("GSPREAD_CREDENTIALS")
if not GEMINI_API_KEY or not GSPREAD_CREDENTIALS:
    st.error("❌ Missing credentials! Add GEMINI_API_KEY and GSPREAD_CREDENTIALS to secrets.")
    st.stop()

SHEET_ID = "1QcS3ZF3YYxSEykG0KiOUuXbTdBh0DMHdMgoqa9t8yrI"
DRIVE_FOLDER_ID = "1H1gf8WqfoTYFT_pU9WfIDLrHg-NpuUSI"

# ============================================================
# HEADINGS (must match Code 2 exactly — 23 cols A-W, plus X,Y,Z,AA)
# ============================================================
HEADINGS = [
    'S/N', 'PNR', 'FROM', 'TO', 'BOARDING', 'T/N', 'CLASS', 'DOJ',
    'PASS NAME', 'PASS PH', 'T/BERTHS', 'PURPOSE', 'ADDRESS',
    'DIARY NO', 'RECOMMENDATION', 'DESIGNATION', 'PHONE NUBER',
    'MP/MLA/MR/MINISTER/VIP/VVIP', 'WARRANT NUMBER', 'PROCESSING DATE+TIME',
    'APPLICATION DATE', 'RAILWAY/ZONE/DIVISION', 'PREFERENCE',
    'LINK (Click to Open)', 'PRINT (A4 Size)', 'VIEW (Hover Details)', 'PNR STATUS LINK'
]

# 1-based column indices for gspread
COL_X = 24   # View Link (HYPERLINK formula)
COL_Y = 25   # Print Link (HYPERLINK formula)  
COL_Z = 26   # Hover Details (text + note)
COL_AA = 27  # PNR Status Link (HYPERLINK formula)

# ============================================================
# STATION MAP (100+ stations)
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
    'AGC':'Agra Cantt', 'KOJ':'Kokrajhar'
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
        creds_dict["private_key"] = pk.replace("\\n", "
")
    scopes = ['https://www.googleapis.com/auth/drive.file']
    creds = GDriveCredentials.from_service_account_info(creds_dict, scopes=scopes)
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
    """Parse date to DD-MM-YYYY. Handles '24/25.06.26' -> '24-06-2026' (FIRST date)"""
    if not date_str:
        return ''
    if isinstance(date_str, datetime):
        return date_str.strftime("%d-%m-%Y")

    date_str = str(date_str).strip()

    # Handle "24/25.06.26" or "24/25/06/26" — take FIRST date
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
    """Extract URL from =HYPERLINK("url","text") formula or plain URL"""
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
    """Check if DOJ is strictly in the past (before today)"""
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
    """Convert 1-based column index to Excel letter (1=A, 27=AA)"""
    result = ""
    while idx > 0:
        idx, remainder = divmod(idx - 1, 26)
        result = chr(65 + remainder) + result
    return result

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
def load_sheet_data(sheet_name):
    """Load sheet data with proper headers including X,Y,Z,AA"""
    try:
        gc = init_sheets()
        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_name)
        all_data = sheet.get_all_values()
        config = SHEET_CONFIG.get(sheet_name, {"start_row": 1, "header_row": 1})
        start_row = config["start_row"]
        header_row = config.get("header_row", start_row - 1)

        if len(all_data) < header_row:
            return pd.DataFrame()

        headers = all_data[header_row - 1] if header_row > 0 else []
        data_rows = all_data[start_row - 1:] if start_row <= len(all_data) else []

        if not data_rows:
            return pd.DataFrame()

        num_cols = max(len(headers), len(data_rows[0]) if data_rows else 0, len(HEADINGS))

        # For EQ sheet, use predefined HEADINGS
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
        return df
    except Exception as e:
        st.error(f"Error loading {sheet_name}: {e}")
        return pd.DataFrame()

# ============================================================
# NOTE SHEET VALIDATOR
# ============================================================
@st.cache_data(ttl=120)
def get_valid_trains():
    """Get valid trains from NOTE sheet Column A"""
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
# DRIVE UPLOAD (Code 3 integration)
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
# GEMINI EXTRACTION (Code 2 logic adapted for Python)
# ============================================================
def get_gemini_system_prompt():
    return """You are TSKEQ Bot's AI extraction engine. Expert at reading messy, handwritten, torn, rotated, crooked railway EQ forms.

Extract these 21 fields and return ONLY a valid JSON array:
1. PNR - 10 digit number
2. T_N (Train Number) - 3 to 5 digits, remove DN/UP suffix
3. CLASS - SL, 2A, 3A, CC, 1A, 2S, etc.
4. DOJ - Convert to DD-MM-YYYY. "24/25.06.26" → "24-06-2026" (FIRST date only)
5. FROM - Station code (3-5 capital letters)
6. TO - Station code (3-5 capital letters)
7. BOARDING - Station code (optional, blank if not specified)
8. PASS_NAME - Passenger full name
9. PASS_PH - 10 digit phone (take LAST 10 digits if +91 present)
10. T_BERTHS - Number of berths (default 1)
11. PURPOSE - Purpose of travel
12. ADDRESS - Full address
13. DIARY_NO - Diary number (preserve as-is, do NOT overwrite with RAIL BOARD unless explicitly found)
14. RECOMMENDATION - Recommender's name/designation
15. DESIGNATION - Designation of recommender
16. VIP_STATUS - MP, MLA, MR, MINISTER, VIP, VVIP
17. APPLICATION_DATE - Date of application (DD-MM-YYYY)
18. RAILWAY_ZONE - Zone (NFR, NR, ER, etc.)
19. PREFERENCE - General, MP, MLA, MR, Lower Seat, RAIL BOARD
20. PHONE_NUBER - Recommender's phone (LAST 10 digits)
21. WARRANT_NO - Warrant number (IC-240, MP-123, etc.)

=== RAIL BOARD RULE ===
ONLY set DIARY_NO="RAIL BOARD", RAILWAY_ZONE="RAIL BOARD", PREFERENCE="RAIL BOARD", VIP_STATUS="MINISTER" if you see EXPLICIT text like:
- "OFFICE OF THE HON'BLE MINISTER RAILWAYS"
- "MINISTER RAILWAYS"
- "RAIL MANTRI"
- "RAIL BHAWAN"
Otherwise leave these fields empty.

=== OUTPUT ===
Return ONLY a valid JSON array. No extra text."""

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
            response = model.generate_content(system_prompt + "\n\nINPUT DATA:\n" + caption)
        else:
            return {'error': 'Unsupported file type'}

        text = response.text

        # Extract JSON array
        json_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', text)
        if not json_match:
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
            if json_match:
                json_str = json_match.group(1)
            else:
                return {'error': 'No JSON found', 'raw': text[:500]}
        else:
            json_str = json_match.group(0)

        json_str = json_str.replace("'", '"').replace('```json', '').replace('```', '').strip()
        json_str = re.sub(r',\s*\}', '}', json_str)
        json_str = re.sub(r',\s*\]', ']', json_str)

        records = json.loads(json_str)
        if isinstance(records, dict):
            records = [records]

        # Clean and validate
        cleaned = []
        seen_pnrs = set()
        for r in records:
            pnr = clean_pnr(r.get('PNR', ''))
            if not pnr or pnr in seen_pnrs:
                continue
            seen_pnrs.add(pnr)

            doj = parse_date(r.get('DOJ', ''))
            if is_expired(doj):
                continue  # Skip expired DOJ

            train = str(r.get('T_N', '')).strip()
            if train and not is_valid_train(train):
                continue  # Skip trains not in NOTE

            # Extract recommendation/designation properly
            rec = str(r.get('RECOMMENDATION', '')).strip()
            des = str(r.get('DESIGNATION', '')).strip()
            vip = str(r.get('VIP_STATUS', '')).strip().upper()

            # If designation empty but recommendation has title, use it
            if not des and rec:
                title_match = re.search(r'\b(MP|MLA|MINISTER|OSD|PMO|DIR|ADDL|DD|LPA|PS/MOS|ADV)\b', rec, re.I)
                if title_match:
                    des = title_match.group(1).upper()

            # If recommendation is just a title, try to extract name
            if rec.upper() in ['MP', 'MLA', 'MINISTER', 'OSD', 'PMO', 'DIR', 'ADDL', 'DD', 'VIP', 'VVIP', 'MR']:
                rec = des if des else ''

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
                'T_BERTHS': int(r.get('T_BERTHS', 1)) or 1,
                'PURPOSE': str(r.get('PURPOSE', '')).strip(),
                'ADDRESS': str(r.get('ADDRESS', '')).strip(),
                'DIARY_NO': str(r.get('DIARY_NO', '')).strip(),
                'RECOMMENDATION': rec,
                'DESIGNATION': des,
                'VIP_STATUS': vip,
                'APPLICATION_DATE': parse_date(r.get('APPLICATION_DATE', '')),
                'RAILWAY_ZONE': str(r.get('RAILWAY_ZONE', '')).strip(),
                'PREFERENCE': str(r.get('PREFERENCE', 'General')).strip(),
                'PHONE_NUBER': clean_phone(r.get('PHONE_NUBER', '')),
                'WARRANT_NO': str(r.get('WARRANT_NO', '')).strip()
            })

        return {'records': cleaned, 'count': len(cleaned)}
    except Exception as e:
        return {'error': f'Extraction error: {e}'}

# ============================================================
# SAVE TO EQ SHEET (with X/Y/Z/AA + Drive link)
# ============================================================
def save_records_to_sheet(records, uploaded_file_info=None):
    try:
        gc = init_sheets()
        sheet = gc.open_by_key(SHEET_ID).worksheet("EQ")
        all_data = sheet.get_all_values()

        # Existing PNRs from column B
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

            # Build row A-W (23 columns)
            row_data = [
                sno,
                pnr,
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

            # Add X, Y, Z, AA
            if uploaded_file_info and uploaded_file_info.get('success'):
                links = build_drive_links(uploaded_file_info['id'], uploaded_file_info['name'])
                row_data.extend([
                    links['x_formula'],
                    links['y_formula'],
                    links['z_value'],
                    f'=HYPERLINK("https://www.confirmtkt.com/pnr-status/{pnr}","🔍 Check PNR")'
                ])
                # Set note on Z cell after row is created
                try:
                    sheet.update_note(f"Z{next_row}", links['z_note'])
                except:
                    pass
            else:
                row_data.extend([
                    '',
                    '',
                    '',
                    f'=HYPERLINK("https://www.confirmtkt.com/pnr-status/{pnr}","🔍 Check PNR")'
                ])

            sheet.append_row(row_data)
            existing_pnrs.add(pnr)
            saved += 1
            time.sleep(0.3)

        format_eq_sheet(sheet)
        return {'saved': saved}
    except Exception as e:
        return {'error': str(e)}

def format_eq_sheet(sheet):
    try:
        all_data = sheet.get_all_values()
        lr = len(all_data)
        if lr >= 4:
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
# UPDATE / DELETE / ADD ROWS
# ============================================================
def update_sheet_row(sheet_name, actual_row, row_values):
    """Update a specific row in sheet. actual_row is 1-based gspread row number."""
    try:
        gc = init_sheets()
        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_name)
        num_cols = len(row_values)
        end_col = col_index_to_letter(num_cols)
        range_name = f"A{actual_row}:{end_col}{actual_row}"
        sheet.update(range_name, [row_values])
        return True
    except Exception as e:
        st.error(f"Update error: {e}")
        return False

def delete_sheet_rows(sheet_name, actual_rows):
    """Delete rows by their 1-based gspread row numbers."""
    try:
        gc = init_sheets()
        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_name)
        for r in sorted(actual_rows, reverse=True):
            sheet.delete_rows(r)
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
        return True
    except Exception as e:
        st.error(f"Add row error: {e}")
        return False

# ============================================================
# THEME
# ============================================================
def apply_theme(dark_mode):
    bg = "#0e1117" if dark_mode else "#f8f9fa"
    card_bg = "#262730" if dark_mode else "#ffffff"
    text = "#fafafa" if dark_mode else "#1e1e2e"
    border = "#4a4a5a" if dark_mode else "#d1d5db"
    st.markdown(f"""
    <style>
        .stApp {{ background-color: {bg}; }}
        .main .block-container {{ padding-top: 1rem; padding-bottom: 1rem; }}
        .stMetric {{ background-color: {card_bg}; border-radius: 12px; padding: 12px; border: 1px solid {border}; }}
        .pro-title {{ font-size: 2rem; font-weight: 800; color: {text}; text-align: center; }}
        .pro-subtitle {{ color: {text}; opacity: 0.7; text-align: center; font-size: 1.1rem; }}
        h1, h2, h3, h4, p, label, .stMarkdown {{ color: {text}; }}
        .stButton button {{ border-radius: 8px; font-weight: 600; }}
        .stDataFrame thead th {{ background: #2d7d46 !important; color: white !important; font-weight: 600 !important; }}
        .pro-footer {{ text-align: center; padding: 20px 0 10px; opacity: 0.5; font-size: 0.8rem; border-top: 1px solid {border}; margin-top: 30px; }}
        .link-btn {{ display: inline-block; padding: 4px 12px; margin: 2px; border-radius: 6px; text-decoration: none; font-size: 0.8rem; font-weight: 600; }}
        .link-view {{ background: #E3F2FD; color: #1565C0; }}
        .link-print {{ background: #E8F5E9; color: #2E7D32; }}
        .link-pnr {{ background: #FFF3E0; color: #E65100; }}
        .hover-box {{ background: {card_bg}; border: 1px solid {border}; border-radius: 8px; padding: 10px; font-size: 0.85rem; max-width: 300px; }}
        @media print {{
            .stApp {{ background-color: white !important; }}
            .main .block-container {{ max-width: 100% !important; padding: 0 !important; }}
            .stSidebar, .stButton, .stSelectbox, .stTextInput, .stDateInput, .pro-footer {{ display: none !important; }}
            .print-area {{ display: block !important; }}
        }}
    </style>
    """, unsafe_allow_html=True)

# ============================================================
# MAIN APP
# ============================================================
def main():
    dark_mode = st.sidebar.toggle("🌙 Dark Mode", value=False)
    apply_theme(dark_mode)

    st.sidebar.title("⚡ AI EQMS Hub Pro")
    st.sidebar.write(f"📅 {datetime.now().strftime('%d-%m-%Y')}")
    st.sidebar.markdown("---")

    # Session state
    if 'last_refresh' not in st.session_state:
        st.session_state.last_refresh = datetime.now()
    if 'export_data' not in st.session_state:
        st.session_state.export_data = None

    # Auto refresh
    auto_refresh = st.sidebar.checkbox("🔄 Auto Refresh (30s)", value=True)
    if auto_refresh:
        if (datetime.now() - st.session_state.last_refresh).total_seconds() > 30:
            st.session_state.last_refresh = datetime.now()
            st.rerun()

    # ---- FILE UPLOAD ----
    st.sidebar.subheader("📤 Upload Railway Form")
    uploaded_file = st.sidebar.file_uploader(
        "Image / PDF / Audio / Text",
        type=['png','jpg','jpeg','pdf','mp3','wav','ogg','txt']
    )
    caption = st.sidebar.text_input("Caption / Text (optional)")

    if st.sidebar.button("🚀 Process & Save to EQ", use_container_width=True, type="primary"):
        if uploaded_file or caption:
            with st.spinner("🤖 Gemini AI extracting..."):
                drive_result = {'success': False}

                if uploaded_file:
                    file_bytes = uploaded_file.read()
                    mime = uploaded_file.type
                    if mime == 'application/pdf':
                        file_type = 'pdf'
                    elif mime.startswith('audio/'):
                        file_type = 'audio'
                    else:
                        file_type = 'image'

                    # Extract with Gemini
                    result = extract_from_file(file_bytes, file_type, caption)

                    # Upload to Drive
                    drive_result = upload_to_drive(file_bytes, uploaded_file.name, mime)
                    if drive_result['success']:
                        st.sidebar.success(f"📁 Drive: {drive_result['name']}")
                else:
                    result = extract_from_file(None, 'text', caption)

                if 'error' in result:
                    st.sidebar.error(f"❌ Extraction failed: {result['error']}")
                elif result['count'] == 0:
                    st.sidebar.warning("⚠️ No valid records. Possible reasons: expired DOJ, train not in NOTE, or unclear data.")
                else:
                    save_result = save_records_to_sheet(result['records'], drive_result)
                    if 'error' in save_result:
                        st.sidebar.error(f"❌ Save error: {save_result['error']}")
                    else:
                        st.sidebar.success(f"✅ Saved {save_result['saved']} records to EQ!")
                        st.session_state.last_refresh = datetime.now()
                        time.sleep(1)
                        st.rerun()
        else:
            st.sidebar.warning("📎 Upload a file or enter text.")

    st.sidebar.markdown("---")
    sheet_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
    st.sidebar.markdown(f"[🔗 Open Google Sheet]({sheet_url})")

    # ---- HEADER ----
    st.markdown("<div class='pro-title'>🚂 AI EQMS Hub Pro</div>", unsafe_allow_html=True)
    st.markdown("<div class='pro-subtitle'>Enterprise Railway EQ Management System</div>", unsafe_allow_html=True)
    st.markdown("---")

    # ---- SHEET SELECTOR ----
    sheet_choice = st.selectbox("📊 Select Sheet", list(SHEET_CONFIG.keys()), index=0)
    config = SHEET_CONFIG[sheet_choice]
    start_row = config["start_row"]

    # ---- LOAD DATA ----
    df = load_sheet_data(sheet_choice)

    if df.empty:
        st.warning(f"⚠️ No data in **{sheet_choice}** sheet.")
        st.info("💡 Upload a railway form from the sidebar or click '➕ Add Row'.")

    # ---- METRICS ----
    m1, m2, m3 = st.columns(3)
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

    # ---- FILTERS ----
    with st.expander("🔍 Filters & Search", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            pnr_f = st.text_input("🔢 PNR", key=f"pnr_{sheet_choice}")
        with c2:
            train_f = st.text_input("🚂 Train", key=f"train_{sheet_choice}")
        with c3:
            name_f = st.text_input("👤 Name", key=f"name_{sheet_choice}")

        c4, c5, c6 = st.columns(3)
        with c4:
            from_d = st.date_input("From DOJ", value=None, key=f"from_{sheet_choice}")
        with c5:
            to_d = st.date_input("To DOJ", value=None, key=f"to_{sheet_choice}")
        with c6:
            class_f = st.text_input("🎫 Class", key=f"class_{sheet_choice}")

        c7, c8 = st.columns([1,1])
        with c7:
            if st.button("🧹 Clear Filters", use_container_width=True):
                for k in list(st.session_state.keys()):
                    if k.startswith((f"pnr_{sheet_choice}", f"train_{sheet_choice}", f"name_{sheet_choice}",
                                     f"from_{sheet_choice}", f"to_{sheet_choice}", f"class_{sheet_choice}")):
                        del st.session_state[k]
                st.rerun()
        with c8:
            expired_only = st.checkbox("⏰ Expired Only", value=False)

    # ---- APPLY FILTERS ----
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

    # ---- PAGINATION ----
    st.subheader(f"📋 {sheet_choice} — {len(filtered)} records")
    ps = st.selectbox("Rows/page", [10, 25, 50, 100], index=1, key=f"ps_{sheet_choice}")
    total_pages = max(1, (len(filtered) + ps - 1) // ps)
    pg = st.number_input("Page", 1, total_pages, 1, key=f"pg_{sheet_choice}") - 1
    si = pg * ps
    ei = min(si + ps, len(filtered))
    page_df = filtered.iloc[si:ei].copy()

    if not page_df.empty:
        # Add Select column
        page_df.insert(0, "Select", False)

        # Prepare display
        display_df = page_df.copy()
        link_cols = ['LINK (Click to Open)', 'PRINT (A4 Size)', 'PNR STATUS LINK']
        for lc in link_cols:
            if lc in display_df.columns:
                display_df[lc] = display_df[lc].apply(lambda x: extract_hyperlink_url(x) or x)

        edited = st.data_editor(
            display_df,
            use_container_width=True,
            height=450,
            num_rows="dynamic" if sheet_choice == "EQ" else "fixed",
            column_config={
                "Select": st.column_config.CheckboxColumn("✓", width="small"),
                "DOJ": st.column_config.TextColumn("DOJ", help="DD-MM-YYYY"),
                "T/BERTHS": st.column_config.NumberColumn("Berths", min_value=1, max_value=50),
            },
            key=f"ed_{sheet_choice}_{pg}"
        )

        sel_mask = edited["Select"]
        sel_idx = edited[sel_mask].index.tolist()

        # ---- ACTION BUTTONS ----
        b1, b2, b3, b4, b5 = st.columns(5)

        with b1:
            if st.button("💾 Save Edits", use_container_width=True, type="primary"):
                try:
                    edit_data = edited.drop("Select", axis=1)
                    orig_data = page_df.drop("Select", axis=1)
                    changed = False

                    for i, (idx, row) in enumerate(edit_data.iterrows()):
                        orig = orig_data.iloc[i]
                        row_changed = any(str(row[c]) != str(orig.get(c, '')) for c in edit_data.columns)

                        if row_changed:
                            actual_row = start_row + si + i
                            vals = []
                            for c in edit_data.columns:
                                v = row[c]
                                vals.append('' if pd.isna(v) else str(v))

                            if update_sheet_row(sheet_choice, actual_row, vals):
                                changed = True
                            time.sleep(0.2)

                    if changed:
                        st.toast("✅ Saved to Google Sheet!", icon="💾")
                        st.session_state.last_refresh = datetime.now()
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.info("ℹ️ No changes detected.")
                except Exception as e:
                    if "429" in str(e):
                        st.error("❌ Quota exceeded. Wait 1 minute.")
                    else:
                        st.error(f"Save error: {e}")

        with b2:
            if st.button("➕ Add Row", use_container_width=True):
                if add_blank_row(sheet_choice):
                    st.toast("✅ Row added!", icon="➕")
                    st.session_state.last_refresh = datetime.now()
                    time.sleep(1)
                    st.rerun()

        with b3:
            if sel_idx:
                if st.button("🗑️ Delete", use_container_width=True):
                    actual_rows = [start_row + si + (idx - page_df.index[0]) for idx in sel_idx]
                    if delete_sheet_rows(sheet_choice, actual_rows):
                        st.toast(f"🗑️ Deleted {len(sel_idx)} rows!", icon="🗑️")
                        st.session_state.last_refresh = datetime.now()
                        time.sleep(1)
                        st.rerun()
            else:
                st.button("🗑️ Delete", disabled=True, use_container_width=True)

        with b4:
            if st.button("🔄 Refresh", use_container_width=True):
                st.session_state.last_refresh = datetime.now()
                st.rerun()

        with b5:
            if sel_idx:
                if st.button("📤 Export", use_container_width=True):
                    exp = edited[sel_mask].drop("Select", axis=1)
                    st.session_state.export_data = exp
                    st.session_state.export_sheet = sheet_choice
                    st.toast(f"📤 {len(exp)} rows ready!")
            else:
                st.button("📤 Export", disabled=True, use_container_width=True)

        # ---- QUICK LINKS (EQ Sheet Only) ----
        if sheet_choice == "EQ":
            st.markdown("---")
            st.subheader("🔗 File Links & PNR Status")

            for idx, row in page_df.iterrows():
                rnum = idx + 1
                c1, c2, c3, c4, c5 = st.columns([1, 2, 2, 2, 2])

                with c1:
                    st.markdown(f"**Row {rnum}**")

                with c2:
                    x_val = row.get('LINK (Click to Open)', '')
                    x_url = extract_hyperlink_url(x_val)
                    if x_url:
                        st.markdown(f'<a href="{x_url}" target="_blank" class="link-btn link-view">📄 View File</a>', unsafe_allow_html=True)
                    else:
                        st.markdown("<span style='opacity:0.4'>—</span>", unsafe_allow_html=True)

                with c3:
                    y_val = row.get('PRINT (A4 Size)', '')
                    y_url = extract_hyperlink_url(y_val)
                    if y_url:
                        st.markdown(f'<a href="{y_url}" target="_blank" class="link-btn link-print">🖨️ Print File</a>', unsafe_allow_html=True)
                    else:
                        st.markdown("<span style='opacity:0.4'>—</span>", unsafe_allow_html=True)

                with c4:
                    z_val = row.get('VIEW (Hover Details)', '')
                    if z_val and str(z_val).strip():
                        with st.popover(f"👁️ Details"):
                            st.markdown(f"<div class='hover-box'>{z_val}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown("<span style='opacity:0.4'>—</span>", unsafe_allow_html=True)

                with c5:
                    pnr = clean_pnr(row.get('PNR', ''))
                    if pnr:
                        pnr_url = f"https://www.confirmtkt.com/pnr-status/{pnr}"
                        st.markdown(f'<a href="{pnr_url}" target="_blank" class="link-btn link-pnr">🔍 PNR {pnr}</a>', unsafe_allow_html=True)
                    else:
                        st.markdown("<span style='opacity:0.4'>—</span>", unsafe_allow_html=True)

        # ---- EXPORT SECTION ----
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
        st.info("📭 No rows. Adjust filters or add data.")

    # ---- PRINT FULL VIEW ----
    st.markdown("---")
    st.subheader("🖨️ Print / Export Full View")
    p1, p2 = st.columns(2)
    with p1:
        if st.button("🖨️ Print Table", use_container_width=True):
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

    st.markdown("<div class='pro-footer'>© 2026 AI EQMS Hub Pro — Created by Sharique 🚂</div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
