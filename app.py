import streamlit as st
import pandas as pd
import json
import re
import base64
import io
import time
from datetime import datetime
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

st.set_page_config(page_title="AI EQMS Hub Pro", page_icon="🚂", layout="wide")

# ========== CREDENTIALS ==========
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
GSPREAD_CREDENTIALS = st.secrets.get("GSPREAD_CREDENTIALS")
if not GEMINI_API_KEY or not GSPREAD_CREDENTIALS:
    st.error("❌ Missing credentials!")
    st.stop()

SHEET_ID = "1QcS3ZF3YYxSEykG0KiOUuXbTdBh0DMHdMgoqa9t8yrI"
DRIVE_FOLDER_ID = "1H1gf8WqfoTYFT_pU9WfIDLrHg-NpuUSI"

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
    creds = GDriveCredentials.from_service_account_info(creds_dict, scopes=scopes)
    return build('drive', 'v3', credentials=creds)

# ========== HELPERS ==========
def clean_pnr(pnr):
    if not pnr:
        return ''
    digits = re.sub(r'\D', '', str(pnr))
    return digits if len(digits) == 10 else (digits[-10:] if len(digits) > 10 else '')

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

STATION_MAP = {
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
def get_station(code):
    if not code:
        return ''
    code = code.upper().strip()
    return f"{code} ({STATION_MAP[code]})" if code in STATION_MAP else code

# ========== SHEET LOADER ==========
@st.cache_data(ttl=60)
def load_sheet_data_cached(sheet_name, start_row, sheet_id):
    try:
        gc = init_sheets()
        sheet = gc.open_by_key(sheet_id).worksheet(sheet_name)
        all_data = sheet.get_all_values()
        if len(all_data) < start_row:
            return pd.DataFrame()
        if start_row > 1:
            headers_raw = all_data[start_row-2]
        else:
            headers_raw = all_data[0] if all_data else []
        data_rows = all_data[start_row-1:] if start_row <= len(all_data) else []
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
        return df
    except Exception as e:
        st.error(f"Error loading {sheet_name}: {e}")
        return pd.DataFrame()

# ========== SHEET CONFIG ==========
# Correct column indices (0-based) for each sheet
SHEET_CONFIG = {
    "EQ": {"start_row": 5, "pnr_col": 1, "train_col": 5, "doj_col": 7},
    "DATA": {"start_row": 3, "pnr_col": 1, "train_col": 5, "doj_col": 7},
    "FINAL": {"start_row": 6, "pnr_col": 7, "train_col": 1, "doj_col": 12},
    "DATA2": {"start_row": 4, "pnr_col": 7, "train_col": 1, "doj_col": 12},
    "EMAIL_DATA": {"start_row": 2, "pnr_col": 7, "train_col": 8, "doj_col": 11},
    "NOTE": {"start_row": 2, "pnr_col": None, "train_col": 0, "doj_col": None}
}

# ========== UPLOAD & EXTRACTION ==========
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
            now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            row = [len(all_data)+1, pnr, rec.get('FROM',''), rec.get('TO',''), rec.get('BOARDING',''),
                   rec.get('T_N',''), rec.get('CLASS',''), rec.get('DOJ',''), rec.get('PASS_NAME',''),
                   rec.get('PASS_PH',''), rec.get('T_BERTHS',1), rec.get('PURPOSE',''), rec.get('ADDRESS',''),
                   rec.get('DIARY_NO',''), rec.get('RECOMMENDATION',''), rec.get('DESIGNATION',''),
                   rec.get('PHONE_NUBER',''), rec.get('VIP_STATUS',''), rec.get('WARRANT_NO',''),
                   now, rec.get('APPLICATION_DATE',''), rec.get('RAILWAY_ZONE',''), rec.get('PREFERENCE','General')]
            sheet.append_row(row)
            saved += 1
            time.sleep(0.2)
        return {'saved': saved}
    except Exception as e:
        return {'error': str(e)}

# ========== THEME ==========
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
        .pro-title {{ font-size: 1.8rem; font-weight: 700; color: {text}; }}
        .pro-subtitle {{ color: {text}; opacity: 0.7; }}
        h1, h2, h3, h4, p, label, .stMarkdown {{ color: {text}; }}
        .stButton button {{ border-radius: 8px; font-weight: 500; }}
        .stDataFrame thead th {{ background: #2d7d46 !important; color: white !important; }}
        .pro-footer {{ text-align: center; padding: 20px 0 10px; opacity: 0.5; font-size: 0.8rem; border-top: 1px solid {border}; margin-top: 30px; }}
        .stExpander {{ border: 1px solid {border}; border-radius: 8px; background: {card_bg}; }}
        .stExpander .streamlit-expanderHeader {{ color: {text}; }}
        .stSidebar .sidebar-content {{ background-color: {bg}; }}
        .stSidebar .sidebar-content .stMarkdown {{ color: {text}; }}
        /* Hide row index column */
        .stDataFrame thead tr th:first-child,
        .stDataFrame tbody tr th:first-child,
        .stDataFrame tbody tr td:first-child {{
            display: none !important;
        }}
        .stDataFrame thead tr th:nth-child(2),
        .stDataFrame tbody tr td:nth-child(2) {{
            display: table-cell !important;
        }}
    </style>
    """, unsafe_allow_html=True)

# ========== SHARE FUNCTION ==========
def share_data(df, sheet_name, selected_rows=None):
    if selected_rows is not None and len(selected_rows) > 0:
        data = df.iloc[selected_rows]
        msg = f"📊 {sheet_name} – Selected {len(data)} rows\n"
        pnr_col = next((c for c in data.columns if 'PNR' in c.upper()), None)
        if pnr_col:
            pnrs = data[pnr_col].tolist()
            msg += f"PNRs: {', '.join(str(p) for p in pnrs[:10])}{'...' if len(pnrs)>10 else ''}\n"
    else:
        data = df
        msg = f"📊 {sheet_name} – Total {len(data)} rows\n"
        train_col = next((c for c in data.columns if 'T/N' in c.upper() or 'TRAIN' in c.upper()), None)
        if train_col:
            train_counts = data[train_col].value_counts().head(5)
            msg += "Top trains:\n" + "\n".join([f"{k}: {v}" for k,v in train_counts.items()])

    pdf = FPDF('L', 'mm', 'A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, f"{sheet_name} Report", ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 8)
    cols = data.columns.tolist()
    if 'Select' in cols:
        cols.remove('Select')
    col_width = 260 / len(cols) if len(cols) > 0 else 20
    for col in cols:
        pdf.cell(col_width, 7, str(col)[:12].encode('latin-1', 'ignore').decode('latin-1'), border=1, align='C')
    pdf.ln()
    pdf.set_font("Arial", '', 7)
    for _, row in data.head(100).iterrows():
        for col in cols:
            val = str(row[col])[:15] if pd.notna(row[col]) else ''
            val_safe = val.encode('latin-1', 'ignore').decode('latin-1')
            pdf.cell(col_width, 6, val_safe, border=1, align='L')
        pdf.ln()
    if len(data) > 100:
        pdf.cell(0, 6, f"... and {len(data)-100} more rows", ln=True, align='C')
    pdf_bytes = pdf.output(dest='S').encode('latin-1')
    return msg, pdf_bytes

# ========== DASHBOARD CHARTS ==========
def show_dashboard(df, sheet_name):
    if df.empty:
        st.info("No data to display charts.")
        return
    try:
        total_records = len(df)
        train_col = next((c for c in df.columns if 'T/N' in c.upper() or 'TRAIN' in c.upper()), None)
        unique_trains = df[train_col].nunique() if train_col and train_col in df else 0
        berth_col = next((c for c in df.columns if 'BERTH' in c.upper() or 'T/BERTHS' in c.upper()), None)
        if berth_col and berth_col in df:
            total_berths = pd.to_numeric(df[berth_col], errors='coerce').sum()
        else:
            total_berths = 0

        col1, col2, col3 = st.columns(3)
        col1.metric("📊 Total Records", total_records)
        col2.metric("🚂 Unique Trains", unique_trains)
        col3.metric("💺 Total Berths", int(total_berths) if total_berths else 0)

        if train_col and train_col in df and df[train_col].notna().any():
            fig_pie = px.pie(df, names=train_col, title=f"Train Distribution ({sheet_name})",
                             hole=0.4, color_discrete_sequence=px.colors.qualitative.Set3)
            fig_pie.update_layout(height=350)
            st.plotly_chart(fig_pie, use_container_width=True)

        if berth_col and berth_col in df:
            berth_vals = pd.to_numeric(df[berth_col], errors='coerce').dropna()
            if not berth_vals.empty:
                fig_hist = px.histogram(berth_vals, nbins=10, title="Berths Distribution",
                                        labels={'value': 'Berths', 'count': 'Frequency'},
                                        color_discrete_sequence=['#2d7d46'])
                fig_hist.update_layout(height=350, bargap=0.2)
                st.plotly_chart(fig_hist, use_container_width=True)

        doj_col = next((c for c in df.columns if 'DOJ' in c.upper()), None)
        if doj_col and doj_col in df:
            df_temp = df.copy()
            df_temp['_date'] = pd.to_datetime(df_temp[doj_col], format='%d-%m-%Y', errors='coerce')
            daily_counts = df_temp.groupby('_date').size().reset_index(name='count')
            if not daily_counts.empty:
                fig_line = px.line(daily_counts, x='_date', y='count', title="Daily Records Trend",
                                   labels={'_date': 'Date', 'count': 'Number of Records'},
                                   markers=True, color_discrete_sequence=['#ff6b6b'])
                fig_line.update_layout(height=350)
                st.plotly_chart(fig_line, use_container_width=True)

        if train_col and train_col in df:
            top_trains = df[train_col].value_counts().head(10).reset_index()
            top_trains.columns = ['Train', 'Count']
            if not top_trains.empty:
                fig_bar = px.bar(top_trains, x='Train', y='Count', title="Top 10 Trains",
                                 color='Count', color_continuous_scale='Viridis')
                fig_bar.update_layout(height=350)
                st.plotly_chart(fig_bar, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not render dashboard: {str(e)}")

# ========== MAIN APP ==========
dark_mode = st.sidebar.toggle("🌙 Dark Mode", value=False)
apply_theme(dark_mode)

st.sidebar.title("⚡ AI EQMS Hub Pro")
st.sidebar.write(f"📅 {datetime.now().strftime('%d-%m-%Y')}")

# ---- File Upload (sidebar) ----
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
                try:
                    gc = init_sheets()
                    eq_sheet = gc.open_by_key(SHEET_ID).worksheet("EQ")
                    save_res = save_to_sheet(eq_sheet, result['records'])
                    if 'error' in save_res:
                        st.sidebar.error(f"Save error: {save_res['error']}")
                    else:
                        st.sidebar.success(f"Saved {save_res['saved']} new records!")
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

# ---- Sheet Selector ----
sheet_choice = st.sidebar.selectbox("Select Sheet", list(SHEET_CONFIG.keys()))
config = SHEET_CONFIG[sheet_choice]
start_row = config["start_row"]

# ---- Filters with session state ----
st.sidebar.subheader("🔍 Filters")
if 'pnr_val' not in st.session_state:
    st.session_state.pnr_val = ''
if 'train_val' not in st.session_state:
    st.session_state.train_val = ''
if 'from_val' not in st.session_state:
    st.session_state.from_val = None
if 'to_val' not in st.session_state:
    st.session_state.to_val = None

# Input widgets
pnr_input = st.sidebar.text_input("PNR (partial)", value=st.session_state.pnr_val, key="pnr_input_widget")
train_input = st.sidebar.text_input("Train (partial)", value=st.session_state.train_val, key="train_input_widget")
from_input = st.sidebar.date_input("From DOJ", value=st.session_state.from_val, key="from_input_widget")
to_input = st.sidebar.date_input("To DOJ", value=st.session_state.to_val, key="to_input_widget")

col1, col2 = st.sidebar.columns(2)
with col1:
    if st.button("Apply Filters", use_container_width=True):
        st.session_state.pnr_val = pnr_input
        st.session_state.train_val = train_input
        st.session_state.from_val = from_input
        st.session_state.to_val = to_input
        st.rerun()
with col2:
    if st.button("Clear Filters", use_container_width=True):
        st.session_state.pnr_val = ''
        st.session_state.train_val = ''
        st.session_state.from_val = None
        st.session_state.to_val = None
        st.rerun()

# ---- Load and filter data ----
df_raw = load_sheet_data_cached(sheet_choice, start_row, SHEET_ID)
filtered_df = df_raw.copy() if not df_raw.empty else pd.DataFrame()

if not filtered_df.empty:
    pnr_col_idx = config.get("pnr_col")
    train_col_idx = config.get("train_col")
    doj_col_idx = config.get("doj_col")

    # Apply PNR filter
    if st.session_state.pnr_val and pnr_col_idx is not None and pnr_col_idx < len(filtered_df.columns):
        col_name = filtered_df.columns[pnr_col_idx]
        filtered_df = filtered_df[filtered_df[col_name].astype(str).str.contains(st.session_state.pnr_val, case=False, na=False)]

    # Apply Train filter
    if st.session_state.train_val and train_col_idx is not None and train_col_idx < len(filtered_df.columns):
        col_name = filtered_df.columns[train_col_idx]
        filtered_df = filtered_df[filtered_df[col_name].astype(str).str.contains(st.session_state.train_val, case=False, na=False)]

    # Apply Date filter
    if (st.session_state.from_val or st.session_state.to_val) and doj_col_idx is not None and doj_col_idx < len(filtered_df.columns):
        col_name = filtered_df.columns[doj_col_idx]
        # Convert to datetime with flexible format
        try:
            # Try parsing as DD-MM-YYYY first
            filtered_df['_temp'] = pd.to_datetime(filtered_df[col_name], format='%d-%m-%Y', errors='coerce')
            # If many NaNs, try other formats
            if filtered_df['_temp'].isna().all():
                filtered_df['_temp'] = pd.to_datetime(filtered_df[col_name], errors='coerce')
        except:
            filtered_df['_temp'] = pd.to_datetime(filtered_df[col_name], errors='coerce')
        
        if st.session_state.from_val:
            filtered_df = filtered_df[filtered_df['_temp'] >= pd.to_datetime(st.session_state.from_val)]
        if st.session_state.to_val:
            filtered_df = filtered_df[filtered_df['_temp'] <= pd.to_datetime(st.session_state.to_val)]
        filtered_df = filtered_df.drop('_temp', axis=1)

# ---- Print Button (sidebar) ----
st.sidebar.subheader("🖨️ Print")
if st.sidebar.button("Print Sheet", use_container_width=True):
    print_df = filtered_df.copy()
    if 'Select' in print_df.columns:
        print_df = print_df.drop('Select', axis=1)
    html_table = print_df.to_html(index=False, classes='print-table')
    st.components.v1.html(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; }}
            .print-table {{ width: 100%; border-collapse: collapse; font-size: 10px; }}
            .print-table th {{ background-color: #2d7d46; color: white; font-weight: bold; padding: 6px; border: 1px solid #000; text-align: center; }}
            .print-table td {{ padding: 4px; border: 1px solid #000; text-align: left; }}
            @media print {{
                body * {{ visibility: visible; }}
            }}
        </style>
    </head>
    <body>
        <div id="print-area">
            {html_table}
            <p style="text-align:center; margin-top:20px; font-size:12px;">{sheet_choice} Report • {datetime.now().strftime('%d-%m-%Y %H:%M')}</p>
        </div>
        <script>
            window.onload = function() {{
                window.print();
            }};
        </script>
    </body>
    </html>
    """, height=0, scrolling=False)

st.sidebar.markdown("---")

# ---- Navigation: Data Table or Dashboard ----
view = st.sidebar.radio("View", ["Data Table", "Dashboard"])

st.markdown("<div class='pro-title'>🚂 AI EQMS Hub</div>", unsafe_allow_html=True)
st.markdown("<div class='pro-subtitle'>Enterprise Quality Management – Pro Edition</div>", unsafe_allow_html=True)
st.markdown("---")

# ---- Show Dashboard or Data Table ----
if view == "Dashboard":
    st.subheader("📊 Dashboard")
    show_dashboard(filtered_df, sheet_choice)
else:
    # ---- Data Table ----
    st.subheader(f"📋 {sheet_choice} – {len(filtered_df)} rows")
    if filtered_df.empty:
        st.info("No data to display. Try adjusting filters or clearing them.")
    else:
        # Pagination
        page_size = st.selectbox("Rows per page", [15, 25, 50, 100], index=1, key="page_size")
        total_pages = max(1, (len(filtered_df) + page_size - 1) // page_size)
        page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1, key="page") - 1
        start_idx = page * page_size
        end_idx = min(start_idx + page_size, len(filtered_df))
        page_df = filtered_df.iloc[start_idx:end_idx]

        if page_df.empty:
            st.info("No rows on this page.")
        else:
            page_df.insert(0, "Select", False)
            edited_page = st.data_editor(
                page_df,
                use_container_width=True,
                height=400,
                column_config={"Select": st.column_config.CheckboxColumn("Select", width="small")},
                key="data_editor"
            )
            selected_indices = edited_page[edited_page["Select"]].index.tolist()

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                if st.button("💾 Save Edits", use_container_width=True):
                    try:
                        gc = init_sheets()
                        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                        data_to_update = edited_page.drop("Select", axis=1).values.tolist()
                        if data_to_update:
                            num_cols = len(data_to_update[0])
                            start_row_update = start_row + start_idx
                            end_row_update = start_row_update + len(data_to_update) - 1
                            col_letter = chr(64 + num_cols)
                            range_name = f"A{start_row_update}:{col_letter}{end_row_update}"
                            sheet.update(range_name, data_to_update)
                            st.toast("✅ Changes saved!", icon="💾")
                            st.cache_data.clear()
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.warning("No data to save.")
                    except Exception as e:
                        if "429" in str(e):
                            st.error("❌ Write quota exceeded. Wait a minute and try again.")
                        else:
                            st.error(f"Save error: {e}")
            with col2:
                if st.button("➕ Add Row", use_container_width=True):
                    try:
                        gc = init_sheets()
                        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                        all_data = sheet.get_all_values()
                        num_cols = len(all_data[0]) if all_data else 1
                        blank_row = [''] * num_cols
                        if len(all_data) >= start_row:
                            next_sn = len(all_data) - start_row + 2
                            blank_row[0] = next_sn
                        sheet.append_row(blank_row)
                        st.toast("✅ Blank row added!", icon="➕")
                        st.cache_data.clear()
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e:
                        if "429" in str(e):
                            st.error("❌ Write quota exceeded. Wait a minute and try again.")
                        else:
                            st.error(f"Add row error: {e}")
            with col3:
                if selected_indices:
                    if st.button("🗑️ Delete Selected", use_container_width=True):
                        actual_rows = [start_row + idx for idx in selected_indices]
                        try:
                            gc = init_sheets()
                            sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                            for row_num in sorted(actual_rows, reverse=True):
                                sheet.delete_rows(row_num)
                            st.toast(f"✅ {len(selected_indices)} rows deleted!", icon="🗑️")
                            st.cache_data.clear()
                            time.sleep(0.5)
                            st.rerun()
                        except Exception as e:
                            if "429" in str(e):
                                st.error("❌ Write quota exceeded. Wait a minute and try again.")
                            else:
                                st.error(f"Delete error: {e}")
                else:
                    st.button("🗑️ Delete Selected", disabled=True, use_container_width=True)
            with col4:
                if selected_indices:
                    if st.button("📤 Share Selected", use_container_width=True):
                        msg, pdf_bytes = share_data(edited_page, sheet_choice, selected_indices)
                        st.download_button("📥 Download PDF", data=pdf_bytes, file_name=f"{sheet_choice}_selected.pdf", mime="application/pdf")
                        wa_link = f"https://api.whatsapp.com/send?text={msg.replace(' ', '%20')}"
                        st.markdown(f'<a href="{wa_link}" target="_blank"><button style="padding:10px 20px; background:#25D366; color:white; border:none; border-radius:8px; cursor:pointer;">📱 Share via WhatsApp</button></a>', unsafe_allow_html=True)
                else:
                    st.button("📤 Share Selected", disabled=True, use_container_width=True)

            # Quick Links
            st.subheader("🔗 Quick Links")
            col_indices = {'X': 23, 'Y': 24, 'Z': 25, 'AA': 26}
            for idx, row in filtered_df.iterrows():
                links = []
                for label, col_idx in col_indices.items():
                    if len(filtered_df.columns) > col_idx:
                        col_name = filtered_df.columns[col_idx]
                        val = row[col_name]
                        if isinstance(val, str) and 'HYPERLINK' in val:
                            url_match = re.search(r'HYPERLINK\("([^"]+)"', val)
                            if url_match:
                                url = url_match.group(1)
                                if label == 'X':
                                    links.append(f'<a href="{url}" target="_blank">View</a>')
                                elif label == 'Y':
                                    links.append(f'<a href="{url}&print=true" target="_blank">Print</a>')
                                elif label == 'Z':
                                    links.append('📝 Hover')
                                elif label == 'AA':
                                    links.append(f'<a href="{url}" target="_blank">PNR</a>')
                        elif label == 'Z' and val and not isinstance(val, str):
                            links.append(f'📝 {str(val)[:20]}')
                if links:
                    row_num = idx + 1
                    st.markdown(f"**Row {row_num}:** " + " | ".join(links), unsafe_allow_html=True)

            # Export PDF/CSV
            st.subheader("📄 Export")
            col1, col2 = st.columns(2)
            with col1:
                try:
                    pdf = FPDF('L', 'mm', 'A4')
                    pdf.add_page()
                    pdf.set_font("Arial", 'B', 14)
                    pdf.cell(0, 10, f"{sheet_choice} Report", ln=True, align='C')
                    pdf.ln(5)
                    pdf.set_font("Arial", 'B', 8)
                    cols = filtered_df.columns.tolist()
                    if 'Select' in cols:
                        cols.remove('Select')
                    col_width = 260 / len(cols) if len(cols) > 0 else 20
                    for col in cols:
                        pdf.cell(col_width, 7, str(col)[:12].encode('latin-1', 'ignore').decode('latin-1'), border=1, align='C')
                    pdf.ln()
                    pdf.set_font("Arial", '', 7)
                    for _, row in filtered_df.head(200).iterrows():
                        for col in cols:
                            val = str(row[col])[:15] if pd.notna(row[col]) else ''
                            val_safe = val.encode('latin-1', 'ignore').decode('latin-1')
                            pdf.cell(col_width, 6, val_safe, border=1, align='L')
                        pdf.ln()
                    if len(filtered_df) > 200:
                        pdf.cell(0, 6, f"... and {len(filtered_df)-200} more rows", ln=True, align='C')
                    pdf_bytes = pdf.output(dest='S').encode('latin-1')
                    st.download_button("📥 Download PDF", data=pdf_bytes, file_name=f"{sheet_choice}.pdf", mime="application/pdf", use_container_width=True)
                except Exception as e:
                    st.warning(f"PDF error: {e}")
            with col2:
                csv = filtered_df.drop('Select', axis=1).to_csv(index=False).encode('utf-8') if 'Select' in filtered_df.columns else filtered_df.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download CSV", data=csv, file_name=f"{sheet_choice}.csv", mime="text/csv", use_container_width=True)

# ========== FOOTER ==========
st.markdown("<div class='pro-footer'>© 2026 AI EQMS Hub Pro – All rights reserved.</div>", unsafe_allow_html=True)
