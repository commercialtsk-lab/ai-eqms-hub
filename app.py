import streamlit as st
import pandas as pd
import json
import re
import base64
import io
from datetime import datetime, timedelta
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.service_account import Credentials as GDriveCredentials
from fpdf import FPDF
import plotly.express as px
import plotly.graph_objects as go
import time

# ==================== PAGE CONFIG ====================
st.set_page_config(
    page_title="AI EQMS Hub – Pro",
    page_icon="🚂",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== CREDENTIALS ====================
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
GSPREAD_CREDENTIALS = st.secrets.get("GSPREAD_CREDENTIALS")
if not GEMINI_API_KEY or not GSPREAD_CREDENTIALS:
    st.error("❌ Missing credentials in secrets!")
    st.stop()

SHEET_ID = "1QcS3ZF3YYxSEykG0KiOUuXbTdBh0DMHdMgoqa9t8yrI"
DRIVE_FOLDER_ID = "1H1gf8WqfoTYFT_pU9WfIDLrHg-NpuUSI"

# ==================== INIT SERVICES ====================
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
    creds = GDriveCredentials.from_service_account_info(creds_dict, scopes=scopes)
    return build('drive', 'v3', credentials=creds)

# ==================== HELPER FUNCTIONS ====================
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
        day = day.zfill(2); month = month.zfill(2)
        if len(year) == 2: year = '20' + year
        if int(month) > 12 and int(day) <= 12: day, month = month, day
        return f"{day}-{month}-{year}"
    return date_str

def get_station(code):
    # shortened map – include full from previous
    station_map = {
        'NTSK': 'New Tinsukia', 'GHY': 'Guwahati', 'NDLS': 'New Delhi',
        'HWH': 'Howrah', 'PNBE': 'Patna', 'BSB': 'Varanasi', 'CNB': 'Kanpur Central',
        'LKO': 'Lucknow', 'DDU': 'Pt. Deen Dayal Upadhyaya', 'GAYA': 'Gaya',
        'MGS': 'Mughalsarai', 'ASN': 'Asansol', 'DHN': 'Dhanbad', 'SC': 'Secunderabad',
        'MAS': 'Chennai Central', 'SBC': 'Bengaluru City', 'CSTM': 'Mumbai CSMT',
        'BCT': 'Mumbai Central', 'PUNE': 'Pune', 'ADI': 'Ahmedabad', 'BRC': 'Vadodara',
        'JP': 'Jaipur', 'AII': 'Ajmer', 'BPL': 'Bhopal', 'INDB': 'Indore',
        'JBP': 'Jabalpur', 'NGP': 'Nagpur', 'HYB': 'Hyderabad', 'BZA': 'Vijayawada',
        'GNT': 'Guntur', 'VSKP': 'Visakhapatnam', 'BBS': 'Bhubaneswar',
        'KGP': 'Kharagpur', 'KOAA': 'Kolkata', 'NJP': 'New Jalpaiguri',
        'NBQ': 'New Bongaigaon', 'KYQ': 'Kamakhya', 'DBRG': 'Dibrugarh',
        'MXN': 'Mariani Junction', 'FKG': 'Furkating', 'JTI': 'Jatinga',
        'MFP': 'Muzaffarpur', 'KIR': 'Katihar Junction', 'DEL': 'Delhi',
        'SDAH': 'Sealdah', 'TBM': 'Tambaram', 'YPR': 'Yesvantpur',
        'SMVB': 'SMVT Bengaluru', 'PRYJ': 'Prayagraj', 'DNR': 'Danapur',
        'RE': 'Rewari', 'AY': 'Ayodhya', 'MLDT': 'Malda Town', 'NNA': 'Naugachia',
        'CLG': 'Kahalgaon', 'ROK': 'Rohtak', 'BGP': 'Bhagalpur', 'JMP': 'Jamalpur',
        'JYG': 'Jaynagar', 'BJU': 'Barauni', 'SPJ': 'Samastipur', 'HJP': 'Hajipur',
        'PPTA': 'Patliputra', 'ARA': 'Ara', 'BXR': 'Buxar', 'TDL': 'Tundla',
        'ALJN': 'Aligarh', 'GZB': 'Ghaziabad', 'BKN': 'Bikaner', 'BME': 'Barmer',
        'JU': 'Jodhpur', 'UDZ': 'Udaipur', 'RTM': 'Ratlam', 'UJN': 'Ujjain',
        'ST': 'Surat', 'BL': 'Valsad', 'PUNE': 'Pune', 'TVC': 'Thiruvananthapuram',
        'ERS': 'Ernakulam', 'MAQ': 'Mangalore', 'MS': 'Chennai Egmore',
        'AF': 'Agra Fort', 'MTJ': 'Mathura', 'GWL': 'Gwalior', 'JHS': 'Jhansi',
        'BHUJ': 'Bhuj', 'GIMB': 'Gandhidham', 'ANND': 'Anand', 'ND': 'Nadiad',
        'BH': 'Bharuch', 'NVS': 'Navsari', 'BSR': 'Vasai Road', 'BVI': 'Borivali',
        'DDR': 'Dadar', 'KYN': 'Kalyan', 'NK': 'Nashik Road', 'MMR': 'Manmad',
        'BSL': 'Bhusaval', 'AK': 'Akola', 'BPQ': 'Balharshah', 'SKZR': 'Sirpur Kagaznagar',
        'MCI': 'Manchiryal', 'KZJ': 'Kazipet', 'KCG': 'Kacheguda', 'MBNR': 'Mahbubnagar',
        'TEL': 'Tenali', 'OGL': 'Ongole', 'NLR': 'Nellore', 'GDR': 'Gudur',
        'CGL': 'Chengalpattu', 'VM': 'Villupuram', 'TJ': 'Thanjavur', 'TPJ': 'Tiruchirappalli',
        'MDU': 'Madurai', 'NCJ': 'Nagercoil', 'QLN': 'Kollam', 'ALLP': 'Alappuzha',
        'TCR': 'Thrissur', 'PGT': 'Palakkad', 'CBE': 'Coimbatore', 'SA': 'Salem',
        'JTJ': 'Jolarpettai', 'KPD': 'Katpadi', 'AJJ': 'Arakkonam', 'PER': 'Perambur',
        'KMU': 'Kumbakonam', 'MV': 'Mayiladuthurai', 'CDM': 'Chidambaram',
        'TDPR': 'Tirupadripulyur', 'CTC': 'Cuttack', 'BHC': 'Bhadrak', 'SRC': 'Santragachi',
        'GMO': 'Gomoh', 'KQR': 'Koderma', 'MGS': 'Mughalsarai', 'BBK': 'Barabanki',
        'GD': 'Gonda', 'BST': 'Basti', 'GKP': 'Gorakhpur', 'DEOS': 'Deoria Sadar',
        'DGR': 'Durgapur', 'BWN': 'Bardhaman', 'VZM': 'Vizianagaram', 'SLO': 'Samalkot',
        'RJY': 'Rajahmundry', 'WADI': 'Wadi', 'YG': 'Yadgir', 'RC': 'Raichur',
        'GTL': 'Guntakal', 'DHNE': 'Dhone', 'KRNT': 'Kurnool City', 'GWD': 'Gadwal',
        'PNU': 'Palanpur', 'ABR': 'Abu Road', 'FA': 'Falna', 'MJ': 'Marwar Junction',
        'AWR': 'Alwar', 'SUR': 'Solapur', 'GR': 'Gulbarga'
    }
    if not code:
        return ''
    code = code.upper().strip()
    return f"{code} ({station_map[code]})" if code in station_map else code

# ==================== LOAD SHEET DATA ====================
def load_sheet_data(sheet_name, start_row):
    """
    Load data from a Google Sheet starting from a given row.
    Returns (headers, data_rows, df) with unique column names.
    """
    try:
        gc = init_sheets()
        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_name)
        all_data = sheet.get_all_values()
        if len(all_data) < start_row:
            return None, None, pd.DataFrame()
        # Headers are at start_row-1 (if start_row>1) else row 0
        if start_row > 1:
            headers_raw = all_data[start_row-2]  # zero-indexed
        else:
            headers_raw = all_data[0] if all_data else []
        # Data rows from start_row-1 to end
        data_rows = all_data[start_row-1:] if start_row <= len(all_data) else []
        # Make headers unique
        seen = {}
        unique_headers = []
        for h in headers_raw:
            h_str = str(h).strip()
            if not h_str:
                h_str = "Unnamed"
            if h_str in seen:
                seen[h_str] += 1
                unique_headers.append(f"{h_str}_{seen[h_str]}")
            else:
                seen[h_str] = 0
                unique_headers.append(h_str)
        df = pd.DataFrame(data_rows, columns=unique_headers[:len(data_rows[0])] if data_rows else [])
        return headers_raw, data_rows, df
    except Exception as e:
        st.error(f"Error loading {sheet_name}: {e}")
        return None, None, pd.DataFrame()

# ==================== SHEET CONFIGURATION ====================
SHEET_CONFIG = {
    "EQ": {
        "start_row": 5,
        "cols": {"pnr": 2, "train": 6, "doj": 8},  # 1-indexed columns
    },
    "DATA": {
        "start_row": 3,
        "cols": {"pnr": 2, "train": 6, "doj": 8},
    },
    "FINAL": {
        "start_row": 4,
        "cols": {"pnr": 8, "train": 2, "doj": 13},
    },
    "DATA2": {
        "start_row": 4,
        "cols": {"pnr": 8, "train": 2, "doj": 13},
    }
}

# ==================== UPLOAD & EXTRACTION (simplified) ====================
def upload_to_drive(file_bytes, filename, mime_type):
    try:
        drive_service = init_drive()
        file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=True)
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id,name,webViewLink,size').execute()
        return {'success': True, 'id': file.get('id'), 'name': file.get('name'), 'url': file.get('webViewLink'), 'size': file.get('size')}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def get_system_prompt():
    return """You are an expert at reading railway EQ forms.
Extract these fields and return ONLY JSON array:
PNR, T_N, CLASS, DOJ (DD-MM-YYYY), FROM, TO, BOARDING, PASS_NAME,
PASS_PH (10 digits), T_BERTHS, PURPOSE, ADDRESS, DIARY_NO,
RECOMMENDATION, DESIGNATION, VIP_STATUS, APPLICATION_DATE,
RAILWAY_ZONE, PREFERENCE, PHONE_NUBER, WARRANT_NO.
Return ONLY JSON array."""

def process_extracted_records(records):
    # simplified version – assume records is list of dicts
    return {'records': records, 'count': len(records)}

def extract_from_file(file_bytes, file_type, caption=None):
    model = init_gemini()
    system_prompt = get_system_prompt()
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
        return {'error': 'Unsupported type'}
    text = response.text
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

def save_to_sheet(sheet, records):
    # simplified – just append rows to sheet
    # For full, we need to get existing PNRs and avoid duplicates
    # We'll implement a basic version
    try:
        all_data = sheet.get_all_values()
        existing_pnrs = []
        for row in all_data[4:]:
            if row and len(row) > 1:
                pnr = clean_pnr(row[1])
                if pnr:
                    existing_pnrs.append(pnr)
        saved = 0
        for rec in records:
            pnr = clean_pnr(rec.get('PNR', ''))
            if not pnr or pnr in existing_pnrs:
                continue
            # prepare row data (just a demo)
            row = [len(all_data)+1, pnr, rec.get('FROM',''), rec.get('TO',''), rec.get('BOARDING',''),
                   rec.get('T_N',''), rec.get('CLASS',''), rec.get('DOJ',''), rec.get('PASS_NAME',''),
                   rec.get('PASS_PH',''), rec.get('T_BERTHS',1), rec.get('PURPOSE',''), rec.get('ADDRESS',''),
                   rec.get('DIARY_NO',''), rec.get('RECOMMENDATION',''), rec.get('DESIGNATION',''),
                   rec.get('PHONE_NUBER',''), rec.get('VIP_STATUS',''), rec.get('WARRANT_NO',''),
                   datetime.now().strftime("%d-%m-%Y %H:%M:%S"), rec.get('APPLICATION_DATE',''),
                   rec.get('RAILWAY_ZONE',''), rec.get('PREFERENCE','General')]
            sheet.append_row(row)
            saved += 1
        return {'saved': saved}
    except Exception as e:
        return {'error': str(e)}

# ==================== THEME & CSS ====================
def load_css(dark_mode):
    bg = "#0e1117" if dark_mode else "#f8f9fa"
    card_bg = "#262730" if dark_mode else "#ffffff"
    text = "#fafafa" if dark_mode else "#1e1e2e"
    border = "#4a4a5a" if dark_mode else "#d1d5db"
    st.markdown(f"""
    <style>
        .stApp {{ background-color: {bg}; }}
        .main .block-container {{ padding-top: 1rem; padding-bottom: 1rem; }}
        .stMetric {{ background-color: {card_bg}; border-radius: 12px; padding: 16px; border: 1px solid {border}; }}
        .pro-card {{ background: {card_bg}; padding: 20px; border-radius: 12px; border: 1px solid {border}; margin-bottom: 16px; }}
        .pro-title {{ font-size: 2rem; font-weight: 700; color: {text}; }}
        .pro-subtitle {{ color: {text}; opacity: 0.7; }}
        h1, h2, h3, h4, p, label, .stMarkdown {{ color: {text}; }}
        .stButton button {{ border-radius: 8px; font-weight: 500; transition: all 0.2s; }}
        .stButton button:hover {{ transform: scale(1.02); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
        .css-1d391kg {{ background-color: {bg}; }}
        .stDataFrame thead th {{ background: #2d7d46 !important; color: white !important; }}
        .pro-footer {{ text-align: center; padding: 20px 0 10px; opacity: 0.5; font-size: 0.8rem; border-top: 1px solid {border}; margin-top: 30px; }}
    </style>
    """, unsafe_allow_html=True)

# ==================== MAIN APP ====================
dark_mode = st.sidebar.toggle("🌙 Dark Mode", value=False)
load_css(dark_mode)

st.sidebar.title("⚡ AI EQMS Hub Pro")
st.sidebar.write(f"📅 {datetime.now().strftime('%d-%m-%Y')}")

# ---- Sidebar: File Upload (Left) ----
st.sidebar.subheader("📤 Upload File")
uploaded_file = st.sidebar.file_uploader("Choose file", type=['png','jpg','jpeg','pdf','mp3','wav','ogg','txt'])
caption = st.sidebar.text_input("Caption (optional)")
if st.sidebar.button("🚀 Process & Save", use_container_width=True):
    if uploaded_file:
        file_bytes = uploaded_file.read()
        file_type = 'pdf' if uploaded_file.type == 'application/pdf' else ('audio' if uploaded_file.type.startswith('audio/') else 'image')
        with st.spinner("Processing..."):
            result = extract_from_file(file_bytes, file_type, caption)
            if 'error' in result:
                st.sidebar.error(f"Error: {result['error']}")
            else:
                st.sidebar.success(f"Extracted {result['count']} records!")
                # Save to EQ sheet
                try:
                    gc = init_sheets()
                    eq_sheet = gc.open_by_key(SHEET_ID).worksheet("EQ")
                    save_res = save_to_sheet(eq_sheet, result['records'])
                    if 'error' in save_res:
                        st.sidebar.error(f"Save error: {save_res['error']}")
                    else:
                        st.sidebar.success(f"Saved {save_res['saved']} new records!")
                        # Upload to Drive
                        drive_res = upload_to_drive(file_bytes, uploaded_file.name, uploaded_file.type)
                        if drive_res['success']:
                            st.sidebar.success(f"File uploaded to Drive: {drive_res['url']}")
                        else:
                            st.sidebar.error(f"Drive upload error: {drive_res['error']}")
                except Exception as e:
                    st.sidebar.error(f"Sheet error: {e}")
    else:
        st.sidebar.warning("Please select a file.")

st.sidebar.markdown("---")

# ---- Main Area ----
st.markdown("<div class='pro-title'>🚂 AI EQMS Hub</div>", unsafe_allow_html=True)
st.markdown("<div class='pro-subtitle'>Enterprise Quality Management – Pro Edition</div>", unsafe_allow_html=True)
st.markdown("---")

# ---- Sheet Selector ----
sheet_choice = st.selectbox("Select Sheet", ["EQ", "DATA", "FINAL", "DATA2"])
config = SHEET_CONFIG[sheet_choice]
start_row = config["start_row"]

# Load data
headers, raw_data, df = load_sheet_data(sheet_choice, start_row)
if df.empty:
    st.warning(f"No data found in {sheet_choice} from row {start_row}.")
    st.stop()

# ---- Train Counts (Top) ----
train_col_idx = config["cols"]["train"] - 1  # zero-index
if train_col_idx < len(df.columns):
    train_col_name = df.columns[train_col_idx]
    train_counts = df[train_col_name].value_counts()
    if not train_counts.empty:
        st.subheader("🚂 Train Counts")
        cols = st.columns(min(len(train_counts), 6))
        for i, (train, count) in enumerate(train_counts.items()):
            with cols[i % 6]:
                st.metric(f"Train {train}", count)

# ---- Filters (Right side) ----
# We'll use a two-column layout: left for table, right for filters
left_col, right_col = st.columns([3, 1])

with right_col:
    st.subheader("🔍 Filters")
    # PNR
    pnr_col_idx = config["cols"]["pnr"] - 1
    if pnr_col_idx < len(df.columns):
        pnr_col_name = df.columns[pnr_col_idx]
        pnr_filter = st.text_input("PNR (partial)", key=f"pnr_{sheet_choice}")
    else:
        pnr_filter = ""
    # Train
    train_col_idx = config["cols"]["train"] - 1
    if train_col_idx < len(df.columns):
        train_col_name = df.columns[train_col_idx]
        train_filter = st.text_input("Train (partial)", key=f"train_{sheet_choice}")
    else:
        train_filter = ""
    # DOJ range
    doj_col_idx = config["cols"]["doj"] - 1
    if doj_col_idx < len(df.columns):
        doj_col_name = df.columns[doj_col_idx]
        from_date = st.date_input("From DOJ", value=None, key=f"from_{sheet_choice}")
        to_date = st.date_input("To DOJ", value=None, key=f"to_{sheet_choice}")
    else:
        from_date = None
        to_date = None
    # Clear filters button
    if st.button("Clear Filters"):
        st.rerun()

# ---- Apply Filters ----
filtered_df = df.copy()
if pnr_filter:
    col_name = df.columns[pnr_col_idx] if pnr_col_idx < len(df.columns) else None
    if col_name:
        filtered_df = filtered_df[filtered_df[col_name].astype(str).str.contains(pnr_filter, case=False, na=False)]
if train_filter:
    col_name = df.columns[train_col_idx] if train_col_idx < len(df.columns) else None
    if col_name:
        filtered_df = filtered_df[filtered_df[col_name].astype(str).str.contains(train_filter, case=False, na=False)]
if from_date or to_date:
    col_name = df.columns[doj_col_idx] if doj_col_idx < len(df.columns) else None
    if col_name:
        try:
            filtered_df['_temp'] = pd.to_datetime(filtered_df[col_name], format='%d-%m-%Y', errors='coerce')
            if from_date:
                filtered_df = filtered_df[filtered_df['_temp'] >= pd.to_datetime(from_date)]
            if to_date:
                filtered_df = filtered_df[filtered_df['_temp'] <= pd.to_datetime(to_date)]
            filtered_df = filtered_df.drop('_temp', axis=1)
        except:
            pass

# ---- Display Data (Left side) ----
with left_col:
    st.subheader(f"📋 {sheet_choice} – {len(filtered_df)} rows")
    # Pagination
    page_size = st.selectbox("Rows per page", [15, 25, 50, 100], index=1, key=f"page_size_{sheet_choice}")
    total_pages = max(1, (len(filtered_df) + page_size - 1) // page_size)
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1, key=f"page_{sheet_choice}") - 1
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(filtered_df))
    page_df = filtered_df.iloc[start_idx:end_idx]

    # Data editor with selection
    if not page_df.empty:
        page_df.insert(0, "Select", False)
        edited_page = st.data_editor(
            page_df,
            use_container_width=True,
            height=400,
            column_config={"Select": st.column_config.CheckboxColumn("Select", width="small")},
            key=f"editor_{sheet_choice}_{page}"
        )
        # Bulk actions
        selected = edited_page[edited_page["Select"]].index.tolist()
        if selected:
            st.warning(f"{len(selected)} rows selected.")
            if st.button("🗑️ Delete Selected", use_container_width=True):
                # Delete from sheet (actual rows = start_row + index)
                actual_rows = [start_row + idx for idx in selected]
                try:
                    gc = init_sheets()
                    sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                    for row_num in sorted(actual_rows, reverse=True):
                        sheet.delete_rows(row_num)
                    st.toast(f"✅ {len(selected)} rows deleted!", icon="🗑️")
                    st.rerun()
                except Exception as e:
                    st.error(f"Delete error: {e}")
        # Save edits button
        if st.button("💾 Save Edits", use_container_width=True):
            try:
                gc = init_sheets()
                sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                for i, (orig_idx, row) in enumerate(edited_page.iterrows()):
                    actual_row = start_row + start_idx + i
                    row_data = row.drop("Select").tolist()
                    for col_idx, val in enumerate(row_data, start=1):
                        sheet.update_cell(actual_row, col_idx, val)
                st.toast("✅ Changes saved!", icon="💾")
            except Exception as e:
                st.error(f"Save error: {e}")

    # ---- Export Options ----
    st.subheader("📄 Export")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("🖨️ Print", use_container_width=True):
            st.markdown('<script>window.print()</script>', unsafe_allow_html=True)
    with col2:
        # Simple PDF (using fpdf)
        try:
            pdf = FPDF('L', 'mm', 'A4')
            pdf.add_page()
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(0, 10, f"{sheet_choice} Report", ln=True, align='C')
            pdf.ln(5)
            pdf.set_font("Arial", 'B', 8)
            # headers
            cols = filtered_df.columns.tolist()
            col_width = 260 / len(cols) if len(cols) > 0 else 20
            for col in cols:
                pdf.cell(col_width, 7, str(col)[:12], border=1, align='C')
            pdf.ln()
            pdf.set_font("Arial", '', 7)
            for _, row in filtered_df.head(50).iterrows():
                for col in cols:
                    val = str(row[col])[:15] if pd.notna(row[col]) else ''
                    pdf.cell(col_width, 6, val, border=1, align='L')
                pdf.ln()
            pdf_bytes = pdf.output(dest='S').encode('latin1')
            st.download_button("📥 PDF", data=pdf_bytes, file_name=f"{sheet_choice}.pdf", mime="application/pdf", use_container_width=True)
        except Exception as e:
            st.warning("PDF generation error")
    with col3:
        csv = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 CSV", data=csv, file_name=f"{sheet_choice}.csv", mime="text/csv", use_container_width=True)
    with col4:
        # Excel
        try:
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                filtered_df.to_excel(writer, sheet_name=sheet_choice, index=False)
            st.download_button("📥 Excel", data=excel_buffer.getvalue(), file_name=f"{sheet_choice}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        except:
            st.warning("Excel requires xlsxwriter")

# ---- Print individual file link (if exists in sheet) ----
# Check if column X (link) exists (usually 24th column)
link_col = None
if len(df.columns) >= 24:
    link_col = df.columns[23]  # zero-index
if link_col and link_col in filtered_df.columns:
    st.subheader("🖨️ Print File from Row")
    for idx, row in filtered_df.iterrows():
        link = row[link_col]
        if isinstance(link, str) and 'HYPERLINK' in link:
            url_match = re.search(r'HYPERLINK\("([^"]+)"', link)
            if url_match:
                file_url = url_match.group(1)
                if st.button(f"🖨️ Print File (Row {idx+1})", key=f"print_{idx}_{sheet_choice}"):
                    st.markdown(f'<script>window.open("{file_url}&print=true", "_blank");</script>', unsafe_allow_html=True)

# ==================== FOOTER ====================
st.markdown("<div class='pro-footer'>© 2026 AI EQMS Hub Pro – All rights reserved.</div>", unsafe_allow_html=True)
