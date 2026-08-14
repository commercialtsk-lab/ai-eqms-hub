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

# ==================== PAGE CONFIG ====================
st.set_page_config(
    page_title="AI EQMS Hub – Bot + Drive Linker",
    page_icon="🚂",
    layout="wide"
)

# ==================== CREDENTIALS (from secrets) ====================
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
GSPREAD_CREDENTIALS = st.secrets.get("GSPREAD_CREDENTIALS")

if not GEMINI_API_KEY:
    st.error("❌ GEMINI_API_KEY not found in secrets!")
    st.stop()
if not GSPREAD_CREDENTIALS:
    st.error("❌ GSPREAD_CREDENTIALS not found in secrets!")
    st.stop()

SHEET_ID = "1QcS3ZF3YYxSEykG0KiOUuXbTdBh0DMHdMgoqa9t8yrI"
DRIVE_FOLDER_ID = "1H1gf8WqfoTYFT_pU9WfIDLrHg-NpuUSI"

# ==================== INITIALIZE SERVICES ====================
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
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    scopes = ['https://www.googleapis.com/auth/drive.file']
    creds = GDriveCredentials.from_service_account_info(creds_dict, scopes=scopes)
    return build('drive', 'v3', credentials=creds)

# ==================== CONSTANTS (exact as bot) ====================
HEADINGS = [
    'S/N', 'PNR', 'FROM', 'TO', 'BOARDING', 'T/N', 'CLASS', 'DOJ',
    'PASS NAME', 'PASS PH', 'T/BERTHS', 'PURPOSE', 'ADDRESS',
    'DIARY NO', 'RECOMMENDATION', 'DESIGNATION', 'PHONE NUBER',
    'MP/MLA/MR/MINISTER/VIP/VVIP', 'WARRANT NUMBER', 'PROCEESING DATE+TIME',
    'APPLICATION DATE', 'RAILWAY/ZONE/DIVISION', 'PREFERENCE'
]

PRIORITY_ORDER = {
    'MR': 5, 'MINISTER': 5, 'OSD': 5, 'PMO': 5, 'RAIL BOARD': 5,
    'MP': 4, 'MLA': 3, 'VIP': 2, 'VVIP': 2, 'GENERAL': 1, '': 1, 'N/A': 1
}

# Full STATION_MAP (same as bot)
STATION_MAP = {
    'MXN': 'Mariani Junction', 'KOJ': 'Kokrajhar', 'DBRG': 'Dibrugarh',
    'NTSK': 'New Tinsukia', 'MFP': 'Muzaffarpur', 'KIR': 'Katihar Junction',
    'DEL': 'Delhi', 'NDLS': 'New Delhi', 'HWH': 'Howrah', 'SDAH': 'Sealdah',
    'GHY': 'Guwahati', 'NJP': 'New Jalpaiguri', 'NBQ': 'New Bongaigaon',
    'TBM': 'Tambaram', 'YPR': 'Yesvantpur', 'SMVB': 'SMVT Bengaluru',
    'LKO': 'Lucknow', 'PRYJ': 'Prayagraj', 'DNR': 'Danapur',
    'RE': 'Rewari', 'AY': 'Ayodhya', 'FKG': 'Furkating',
    'KYQ': 'Kamakhya', 'MLDT': 'Malda Town', 'NNA': 'Naugachia',
    'JTI': 'Jatinga', 'CLG': 'Kahalgaon', 'ROK': 'Rohtak',
    'BGP': 'Bhagalpur', 'JMP': 'Jamalpur', 'JYG': 'Jaynagar',
    'BJU': 'Barauni', 'SPJ': 'Samastipur', 'HJP': 'Hajipur',
    'PPTA': 'Patliputra', 'PNBE': 'Patna', 'ARA': 'Ara',
    'BXR': 'Buxar', 'DDU': 'Pt. Deen Dayal Upadhyaya',
    'BSB': 'Varanasi', 'CNB': 'Kanpur Central', 'TDL': 'Tundla',
    'ALJN': 'Aligarh', 'GZB': 'Ghaziabad', 'BKN': 'Bikaner',
    'BME': 'Barmer', 'JU': 'Jodhpur', 'AII': 'Ajmer',
    'JP': 'Jaipur', 'UDZ': 'Udaipur', 'BPL': 'Bhopal',
    'INDB': 'Indore', 'JBP': 'Jabalpur', 'RTM': 'Ratlam',
    'UJN': 'Ujjain', 'BRC': 'Vadodara', 'ADI': 'Ahmedabad',
    'ST': 'Surat', 'BL': 'Valsad', 'PUNE': 'Pune',
    'BCT': 'Mumbai Central', 'CSTM': 'Mumbai CSMT', 'TVC': 'Thiruvananthapuram',
    'ERS': 'Ernakulam', 'MAQ': 'Mangalore', 'SBC': 'Bengaluru City',
    'MAS': 'Chennai Central', 'MS': 'Chennai Egmore', 'BBS': 'Bhubaneswar',
    'VSKP': 'Visakhapatnam', 'HYB': 'Hyderabad', 'SC': 'Secunderabad',
    'BZA': 'Vijayawada', 'GNT': 'Guntur', 'AGC': 'Agra Cantt',
    'AF': 'Agra Fort', 'MTJ': 'Mathura', 'GWL': 'Gwalior',
    'JHS': 'Jhansi', 'BHUJ': 'Bhuj', 'GIMB': 'Gandhidham',
    'ANND': 'Anand', 'ND': 'Nadiad', 'BH': 'Bharuch',
    'NVS': 'Navsari', 'BSR': 'Vasai Road', 'BVI': 'Borivali',
    'DDR': 'Dadar', 'KYN': 'Kalyan', 'NK': 'Nashik Road',
    'MMR': 'Manmad', 'BSL': 'Bhusaval', 'AK': 'Akola',
    'NGP': 'Nagpur', 'BPQ': 'Balharshah', 'SKZR': 'Sirpur Kagaznagar',
    'MCI': 'Manchiryal', 'KZJ': 'Kazipet', 'KCG': 'Kacheguda',
    'MBNR': 'Mahbubnagar', 'TEL': 'Tenali', 'OGL': 'Ongole',
    'NLR': 'Nellore', 'GDR': 'Gudur', 'CGL': 'Chengalpattu',
    'VM': 'Villupuram', 'TJ': 'Thanjavur', 'TPJ': 'Tiruchirappalli',
    'MDU': 'Madurai', 'NCJ': 'Nagercoil', 'QLN': 'Kollam',
    'ALLP': 'Alappuzha', 'TCR': 'Thrissur', 'PGT': 'Palakkad',
    'CBE': 'Coimbatore', 'SA': 'Salem', 'JTJ': 'Jolarpettai',
    'KPD': 'Katpadi', 'AJJ': 'Arakkonam', 'PER': 'Perambur',
    'KMU': 'Kumbakonam', 'MV': 'Mayiladuthurai', 'CDM': 'Chidambaram',
    'TDPR': 'Tirupadripulyur', 'CTC': 'Cuttack', 'BHC': 'Bhadrak',
    'KGP': 'Kharagpur', 'SRC': 'Santragachi', 'KOAA': 'Kolkata',
    'ASN': 'Asansol', 'DHN': 'Dhanbad', 'GMO': 'Gomoh',
    'KQR': 'Koderma', 'GAYA': 'Gaya', 'MGS': 'Mughalsarai',
    'BBK': 'Barabanki', 'GD': 'Gonda', 'BST': 'Basti',
    'GKP': 'Gorakhpur', 'DEOS': 'Deoria Sadar', 'DGR': 'Durgapur',
    'BWN': 'Bardhaman', 'VZM': 'Vizianagaram', 'SLO': 'Samalkot',
    'RJY': 'Rajahmundry', 'WADI': 'Wadi', 'YG': 'Yadgir',
    'RC': 'Raichur', 'GTL': 'Guntakal', 'DHNE': 'Dhone',
    'KRNT': 'Kurnool City', 'GWD': 'Gadwal', 'PNU': 'Palanpur',
    'ABR': 'Abu Road', 'FA': 'Falna', 'MJ': 'Marwar Junction',
    'AWR': 'Alwar', 'SUR': 'Solapur', 'GR': 'Gulbarga'
}

# ==================== HELPER FUNCTIONS (exact as bot) ====================
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
    date_str = str(date_str).strip()
    if isinstance(date_str, datetime):
        return date_str.strftime("%d-%m-%Y")
    match = re.search(r'(\d{1,2})[\/.\-](\d{1,2})[\/.\-](\d{2,4})', date_str)
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

def get_priority(vip_status):
    if not vip_status:
        return 1
    v = str(vip_status).upper().strip()
    if v in PRIORITY_ORDER:
        return PRIORITY_ORDER[v]
    if 'MR' in v or 'MINISTER' in v or 'RAIL BOARD' in v:
        return 5
    if 'MP' in v and 'PMO' not in v:
        return 4
    if 'MLA' in v:
        return 3
    if 'VVIP' in v:
        return 2
    if 'VIP' in v:
        return 1
    return 1

def extract_berth(name_field):
    if not name_field:
        return {'name': '', 'berths': 1}
    name = str(name_field).strip()
    match = re.search(r'^(.+?)(?:\s*\+\s*(\d+))?\s*$', name)
    if match:
        extra = int(match[2]) if match[2] else 0
        return {'name': match[1].strip(), 'berths': 1 + extra}
    return {'name': name, 'berths': 1}

def smart_detect_warrant(text):
    if not text:
        return {'warrant': '', 'found': False}
    text = str(text).upper()
    patterns = [
        r'IC[-_\s]*(\d{2,4})',
        r'WARRANT\s*NO\.?\s*[:#]?\s*([A-Z0-9\-]+)',
        r'WARRANT\s*NUMBER\s*[:#]?\s*([A-Z0-9\-]+)',
        r'W[\/\-]?NO\.?\s*[:#]?\s*([A-Z0-9\-]+)',
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
    text = str(text).upper().replace('\\s+', ' ')
    patterns = [
        r'RAIL\s*BOARD',
        r'OFFICE\s*OF\s*(?:THE\s*)?HON\'?BLE\s*MINISTER\s*RAILWAYS',
        r'OFFICE\s*OF\s*(?:THE\s*)?HONOURABLE\s*MINISTER\s*RAILWAYS',
        r'MINISTER\s*RAILWAYS',
        r'MINISTRY\s*OF\s*RAILWAYS',
        r'RAIL\s*MANTRI',
        r'RAIL\s*BHAWAN'
    ]
    for pattern in patterns:
        if re.search(pattern, text):
            return {'isRailBoard': True}
    keywords = ['MINISTER', 'RAILWAYS', 'RAILWAY', 'HONBLE', "HON'BLE", 'RAIL MANTRI', 'OFFICE', 'RAIL', 'BOARD']
    score = sum(1 for kw in keywords if kw in text)
    if score >= 4:
        return {'isRailBoard': True}
    if 'OFFICE' in text and 'MINISTER' in text and ('RAILWAYS' in text or 'RAILWAY' in text):
        if text.find('OFFICE') < 50:
            return {'isRailBoard': True}
    return {'isRailBoard': False}

def smart_detect_diary(text):
    if not text:
        return {'diary': '', 'found': False}
    text = str(text).upper()
    patterns = [
        r'DIARY\s*NO\.?\s*[:#]?\s*([A-Z0-9\/\-]+)',
        r'DIARY\s*NUMBER\s*[:#]?\s*([A-Z0-9\/\-]+)',
        r'D\/?NO\.?\s*[:#]?\s*([A-Z0-9\/\-]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return {'diary': match.group(1).strip(), 'found': True}
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
    if re.search(r'\bOSD\b', text):
        return 'OSD'
    if re.search(r'\bPMO\b', text):
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

def match_train_number(input_train, note_train):
    if not input_train or not note_train:
        return False
    input_t = str(input_train).strip().upper()
    note_t = str(note_train).strip().upper()
    if input_t == note_t:
        return True
    input_clean = re.sub(r'\s*(DN|UP)$', '', input_t).strip()
    note_clean = re.sub(r'\s*(DN|UP)$', '', note_t).strip()
    return input_clean == note_clean or input_clean == note_t or input_t == note_clean

# ==================== GEMINI PROMPT (exact as bot) ====================
def get_system_prompt():
    return """You are TSKEQ Bot's AI extraction engine. You are an EXPERT at reading messy, handwritten, torn, or low-quality railway forms.

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
3. DOJ: Convert to DD-MM-YYYY. "24/25.06.26" → "24-06-2026"
4. Phone: Remove all non‑digits, then take the LAST 10 digits. Example: "+919138328565" → "9138328565"
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

# ==================== PROCESS EXTRACTED RECORDS (exact as bot) ====================
def process_extracted_records(records):
    if not records:
        return {'records': [], 'count': 0}
    if not isinstance(records, list):
        records = [records]

    processed = []
    seen_pnrs = set()

    for rec in records:
        pnr = clean_pnr(rec.get('PNR', ''))
        if not pnr or pnr in seen_pnrs:
            continue
        seen_pnrs.add(pnr)

        full_text = ' '.join([
            str(rec.get('PURPOSE', '')),
            str(rec.get('ADDRESS', '')),
            str(rec.get('RECOMMENDATION', '')),
            str(rec.get('DESIGNATION', '')),
            str(rec.get('DIARY_NO', '')),
            str(rec.get('PASS_NAME', '')),
            str(rec.get('PASS_PH', '')),
            str(rec.get('PHONE_NUBER', '')),
            str(rec.get('WARRANT_NO', '')),
            str(rec.get('VIP_STATUS', ''))
        ])

        # Smart detection
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

        if not rec.get('DIARY_NO') or rec.get('DIARY_NO') == '-':
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

        # Clean data
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

        processed.append(rec)

    return {'records': processed, 'count': len(processed)}

# ==================== DRIVE UPLOAD ====================
def upload_to_drive(file_bytes, filename, mime_type):
    try:
        drive_service = init_drive()
        file_metadata = {
            'name': filename,
            'parents': [DRIVE_FOLDER_ID]
        }
        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=True)
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink, size'
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

# ==================== SHEET LINK FUNCTIONS (Drive Linker) ====================
def is_row_linked(sheet, row_num):
    try:
        for col in [24, 25, 26]:
            val = sheet.get_range(row_num, col).get_value()
            if val and 'HYPERLINK' in str(val):
                return True
        return False
    except:
        return True

def clear_row_links(sheet, row_num):
    try:
        for col in [24, 25, 26]:
            sheet.get_range(row_num, col).clear_content()
            sheet.get_range(row_num, col).clear_note()
        sheet.get_range(row_num, 24, 1, 3).set_background(None).set_font_color(None)
    except:
        pass

def update_row_with_file(sheet, row_num, drive_file):
    try:
        file_id = drive_file['id']
        view_url = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
        print_url = f"https://drive.google.com/file/d/{file_id}/preview?usp=sharing"
        details = f"📄 EQ File Details:\n"
        details += f"━━━━━━━━━━━━━━━━━\n"
        details += f"📎 Name: {drive_file['name']}\n"
        details += f"📂 Type: {drive_file['name'].split('.')[-1].upper()}\n"
        details += f"📊 Size: {round(int(drive_file['size'])/1024)} KB\n"
        details += f"🕐 Saved: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n"
        details += f"🔑 Drive ID: {file_id}\n"
        details += f"━━━━━━━━━━━━━━━━━\n📁 Drive: EQ"

        sheet.get_range(row_num, 24).clear_note()
        sheet.get_range(row_num, 25).clear_note()
        sheet.get_range(row_num, 26).clear_note()

        sheet.get_range(row_num, 24).set_formula(f'=HYPERLINK("{view_url}","Click to Open")')
        sheet.get_range(row_num, 24).set_background('#E3F2FD').set_font_color('#1565C0')

        sheet.get_range(row_num, 25).set_formula(f'=HYPERLINK("{print_url}","🖨️ Print")')
        sheet.get_range(row_num, 25).set_background('#E8F5E9').set_font_color('#2E7D32')

        sheet.get_range(row_num, 26).set_value('👁️ View')
        sheet.get_range(row_num, 26).set_note(details)
        sheet.get_range(row_num, 26).set_background('#FFF3E0').set_font_color('#E65100')

        sheet.get_range(row_num, 24, 1, 3).set_horizontal_alignment('center') \
            .set_vertical_alignment('middle') \
            .set_font_weight('bold') \
            .set_font_size(10) \
            .set_border(True, True, True, True, True, True)
        return True
    except Exception as e:
        st.error(f"Update link error: {e}")
        return False

# ==================== SAVE TO SHEET (with X/Y/Z) ====================
def save_to_sheet(sheet, records):
    existing = []
    try:
        all_values = sheet.get_all_values()
        for row in all_values[4:]:
            if row and len(row) > 1:
                pnr = clean_pnr(row[1])
                if pnr:
                    existing.append(pnr)
    except:
        pass

    saved = 0
    skipped = 0
    skip_reasons = []
    current_count = len(sheet.get_all_values()) - 4

    for rec in records:
        pnr = clean_pnr(rec.get('PNR', ''))
        if not pnr:
            skipped += 1
            skip_reasons.append("No PNR found")
            continue
        if pnr in existing:
            skipped += 1
            skip_reasons.append(f"PNR {pnr} already exists")
            continue

        current_count += 1
        now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        berth_info = extract_berth(rec.get('PASS_NAME', ''))
        pass_name = re.sub(r'\s*\+\s*\d+\s*$', '', str(rec.get('PASS_NAME', '')).strip()) or berth_info['name']

        row_data = [
            current_count,
            pnr,
            get_station(rec.get('FROM', '')),
            get_station(rec.get('TO', '')),
            get_station(rec.get('BOARDING', '')),
            rec.get('T_N', '').strip(),
            rec.get('CLASS', '').upper(),
            rec.get('DOJ', ''),
            pass_name,
            rec.get('PASS_PH', ''),
            int(rec.get('T_BERTHS', 1)),
            rec.get('PURPOSE', '').strip(),
            rec.get('ADDRESS', '').strip(),
            rec.get('DIARY_NO', '').strip(),
            rec.get('RECOMMENDATION', '').strip(),
            rec.get('DESIGNATION', '').strip(),
            rec.get('PHONE_NUBER', ''),
            rec.get('VIP_STATUS', '').upper(),
            rec.get('WARRANT_NO', '').strip(),
            now,
            rec.get('APPLICATION_DATE', ''),
            rec.get('RAILWAY_ZONE', '').upper(),
            rec.get('PREFERENCE', 'General')
        ]
        sheet.append_row(row_data)
        existing.append(pnr)
        saved += 1

    return {'saved': saved, 'skipped': skipped, 'skip_reasons': skip_reasons}

# ==================== GET PNR FROM ROW ====================
def get_pnr_from_row(sheet, row_num):
    try:
        pnr = sheet.get_range(row_num, 2).get_value()
        return str(pnr).strip() if pnr else 'N/A'
    except:
        return 'N/A'

# ==================== FIND ROW BY TIMESTAMP (recent first) ====================
def parse_column_t_date(val):
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.strptime(str(val), "%d-%m-%Y %H:%M:%S")
    except:
        try:
            return datetime.strptime(str(val), "%d-%m-%Y %H:%M")
        except:
            return None

def find_row_by_timestamp(sheet, file_time):
    try:
        lr = sheet.get_last_row()
        if lr < 5:
            return -1
        ts_data = sheet.get_range(5, 20, lr-4, 1).get_values()
        file_ms = file_time.timestamp() * 1000
        for i in range(len(ts_data)-1, -1, -1):
            val = ts_data[i][0]
            if val:
                sheet_time = parse_column_t_date(val)
                if sheet_time:
                    diff = abs(sheet_time.timestamp() * 1000 - file_ms)
                    if diff <= 60000:
                        return i + 5
        return -1
    except:
        return -1

# ==================== GEMINI EXTRACTION ====================
def extract_from_file(file_bytes, file_type, caption=None):
    model = init_gemini()
    system_prompt = get_system_prompt()
    if file_type in ['image', 'pdf']:
        mime = 'image/jpeg' if file_type == 'image' else 'application/pdf'
        b64 = base64.b64encode(file_bytes).decode('utf-8')
        response = model.generate_content([
            system_prompt,
            {"mime_type": mime, "data": b64}
        ])
    elif file_type == 'audio':
        # Audio extraction – same as bot, we treat as audio/mpeg
        b64 = base64.b64encode(file_bytes).decode('utf-8')
        response = model.generate_content([
            system_prompt,
            {"mime_type": "audio/mpeg", "data": b64}
        ])
    elif file_type == 'text':
        if caption is None:
            caption = ''
        response = model.generate_content(system_prompt + "\n\nINPUT DATA:\n" + caption)
    else:
        return {'error': 'Unsupported file type'}

    text = response.text
    # Try to find JSON array
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
    try:
        records = json.loads(json_str)
        if isinstance(records, dict):
            records = [records]
        processed = process_extracted_records(records)
        return processed
    except Exception as e:
        return {'error': f'JSON parse error: {e}', 'raw': json_str[:500]}

# ==================== MAIN UI ====================
st.title("🚂 AI EQMS Hub – Bot + Drive Linker")
st.markdown("Upload railway forms (image, PDF, text, audio) – Gemini extracts data, saves to sheet, uploads to Drive, and links the row.")

# Sidebar
with st.sidebar:
    st.header("📤 Upload")
    upload_type = st.radio("Select upload type:", ["📷 Image", "📄 PDF", "📝 Text", "🎵 Audio"])
    uploaded_file = None
    text_input = None
    if upload_type in ["📷 Image", "📄 PDF", "🎵 Audio"]:
        types = {
            "📷 Image": ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'],
            "📄 PDF": ['pdf'],
            "🎵 Audio": ['mp3', 'wav', 'ogg', 'm4a']
        }
        uploaded_file = st.file_uploader(f"Upload {upload_type}", type=types.get(upload_type, []))
    else:
        text_input = st.text_area("Enter text data:", height=150, placeholder="Paste railway form text...")
    caption = st.text_input("Caption (optional – include PNR to help match row)", placeholder="e.g., PNR 1234567890")
    process_btn = st.button("🚀 Process & Save", use_container_width=True, type="primary")

# Main area
if process_btn:
    if uploaded_file:
        file_bytes = uploaded_file.read()
        file_type = 'pdf' if uploaded_file.type == 'application/pdf' else (
            'audio' if uploaded_file.type.startswith('audio/') else 'image'
        )
        file_name = uploaded_file.name
    elif text_input:
        file_bytes = text_input.encode('utf-8')
        file_type = 'text'
        file_name = 'text_input.txt'
        caption = text_input
    else:
        st.warning("Please upload a file or enter text.")
        st.stop()

    with st.spinner("🔄 Processing with Gemini..."):
        # Step 1: Extract data
        extract_result = extract_from_file(file_bytes, file_type, caption)
        if 'error' in extract_result:
            st.error(f"❌ Extraction error: {extract_result['error']}")
            if 'raw' in extract_result:
                with st.expander("Raw Gemini response"):
                    st.text(extract_result['raw'])
            st.stop()

        records = extract_result.get('records', [])
        if not records:
            st.warning("No records extracted.")
            st.stop()

        st.success(f"✅ Extracted {len(records)} records!")
        df = pd.DataFrame(records)
        st.dataframe(df, use_container_width=True)

        # Step 2: Connect to sheets
        try:
            gc = init_sheets()
            sheet = gc.open_by_key(SHEET_ID).worksheet("EQ")
        except Exception as e:
            st.error(f"❌ Sheets connection error: {e}")
            st.stop()

        # Step 3: Save to sheet
        save_result = save_to_sheet(sheet, records)
        if save_result['saved'] > 0:
            st.success(f"✅ Saved {save_result['saved']} new records to Google Sheets!")
        else:
            st.warning("No new records saved (duplicates or errors).")
            if save_result['skipped'] > 0:
                with st.expander(f"⚠️ Skipped {save_result['skipped']}"):
                    for r in save_result['skip_reasons']:
                        st.text(f"  - {r}")

        # Step 4: Upload file to Drive
        drive_result = upload_to_drive(file_bytes, file_name, uploaded_file.type if uploaded_file else 'text/plain')
        if not drive_result['success']:
            st.error(f"❌ Drive upload error: {drive_result['error']}")
            st.stop()

        st.success(f"✅ File uploaded to Drive: {drive_result['name']}")

        # Step 5: Find the row to link
        # Try by PNR from caption or first record
        pnr_from_caption = clean_pnr(caption) if caption else ''
        target_row = -1
        if pnr_from_caption:
            all_data = sheet.get_all_values()
            for i, row in enumerate(all_data[4:], start=5):
                if len(row) > 1 and clean_pnr(row[1]) == pnr_from_caption:
                    target_row = i
                    break
        if target_row == -1:
            # If records have PNR, try to find the latest saved row matching any PNR
            for rec in records:
                pnr = clean_pnr(rec.get('PNR', ''))
                if pnr:
                    all_data = sheet.get_all_values()
                    for i, row in enumerate(all_data[4:], start=5):
                        if len(row) > 1 and clean_pnr(row[1]) == pnr:
                            target_row = i
                            break
                    if target_row != -1:
                        break
        if target_row == -1:
            # Fallback: find by timestamp (use current time)
            target_row = find_row_by_timestamp(sheet, datetime.now())
        if target_row == -1:
            # Last resort: most recent row with data
            lr = sheet.get_last_row()
            if lr >= 5:
                for r in range(lr, 4, -1):
                    ts = sheet.get_range(r, 20).get_value()
                    if ts and str(ts).strip():
                        target_row = r
                        break
        if target_row == -1:
            st.warning("Could not find a matching row to link the file.")
            st.info("💡 Please ensure the sheet has a record with matching PNR or timestamp.")
            st.stop()

        # Step 6: Check if row already linked
        if is_row_linked(sheet, target_row):
            st.warning(f"⚠️ Row {target_row} already has a link. Skipping link update.")
        else:
            clear_row_links(sheet, target_row)
            if update_row_with_file(sheet, target_row, drive_result):
                st.success(f"✅ Row {target_row} updated with Drive links!")
                pnr = get_pnr_from_row(sheet, target_row)
                st.info(f"PNR: {pnr} | File: {drive_result['name']}")
            else:
                st.error("Failed to update sheet with links.")

        # Show final status
        st.markdown("---")
        st.subheader("📋 Final Status")
        st.write(f"**Sheet ID:** {SHEET_ID}")
        st.write(f"**Drive File ID:** {drive_result['id']}")
        st.write(f"**Row Number:** {target_row}")
        st.write(f"**View Link:** [Open in Drive]({drive_result['url']})")

# ==================== NAVIGATION (Sheets View, EQ Report, Quota Status) ====================
st.sidebar.markdown("---")
st.sidebar.title("⚡ Other Views")
view = st.sidebar.radio("Select View", ["📊 Sheets View", "📋 EQ Report", "📊 Quota Status"])

try:
    gc = init_sheets()
    eq_sheet = gc.open_by_key(SHEET_ID).worksheet("EQ")
    note_sheet = gc.open_by_key(SHEET_ID).worksheet("NOTE")
except:
    st.sidebar.error("Sheets not available")

if view == "📊 Sheets View":
    st.title("📊 Google Sheets Data")
    sheet_names = ["EQ", "NOTE", "DATA", "FINAL", "DATA2", "EMAIL_DATA"]
    tabs = st.tabs(sheet_names)
    for i, tab in enumerate(tabs):
        with tab:
            try:
                ws = gc.open_by_key(SHEET_ID).worksheet(sheet_names[i])
                data = ws.get_all_values()
                if data and len(data) > 1:
                    seen = {}
                    headers = []
                    for h in data[0]:
                        h_str = str(h).strip()
                        if h_str in seen:
                            seen[h_str] += 1
                            headers.append(f"{h_str}_{seen[h_str]}")
                        else:
                            seen[h_str] = 0
                            headers.append(h_str if h_str else "Unnamed")
                    df = pd.DataFrame(data[1:], columns=headers)
                    st.dataframe(df, use_container_width=True, height=400)
                    st.caption(f"📊 {len(df)} rows • Updated: {datetime.now().strftime('%H:%M:%S')}")
                else:
                    st.warning(f"Sheet '{sheet_names[i]}' is empty")
            except Exception as e:
                st.error(f"Error: {str(e)}")

elif view == "📋 EQ Report":
    st.title("📋 EQ Report")
    try:
        all_data = eq_sheet.get_all_values()
        if len(all_data) > 4:
            records = []
            for row in all_data[4:]:
                if len(row) > 1:
                    records.append({
                        'S/N': row[0] if len(row)>0 else '',
                        'PNR': row[1] if len(row)>1 else '',
                        'FROM': row[2] if len(row)>2 else '',
                        'TO': row[3] if len(row)>3 else '',
                        'T/N': row[5] if len(row)>5 else '',
                        'CLASS': row[6] if len(row)>6 else '',
                        'DOJ': row[7] if len(row)>7 else '',
                        'PASS_NAME': row[8] if len(row)>8 else '',
                        'PASS_PH': row[9] if len(row)>9 else '',
                        'T_BERTHS': row[10] if len(row)>10 else '',
                        'PREFERENCE': row[22] if len(row)>22 else ''
                    })
            df = pd.DataFrame(records)
            st.dataframe(df, use_container_width=True)
            st.caption(f"📊 Total EQ records: {len(records)}")
        else:
            st.info("No records found.")
    except Exception as e:
        st.error(f"Error: {e}")

elif view == "📊 Quota Status":
    st.title("📊 Quota Status")
    try:
        note_data = note_sheet.get_all_values()
        if len(note_data) > 1:
            df = pd.DataFrame(note_data[1:], columns=note_data[0] if note_data else [])
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No quota data found.")
    except Exception as e:
        st.error(f"Error: {e}")

# ==================== FOOTER ====================
st.sidebar.markdown("---")
st.sidebar.caption("🚂 AI EQMS Hub – Bot + Drive Linker | Powered by Gemini 2.5 Flash")
