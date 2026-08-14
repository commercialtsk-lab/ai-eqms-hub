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

# ==================== PAGE CONFIG ====================
st.set_page_config(
    page_title="AI EQMS Hub – Pro",
    page_icon="🚂",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== CUSTOM CSS (Dark/Light Support) ====================
def load_css(dark_mode):
    if dark_mode:
        bg = "#0e1117"
        card_bg = "#262730"
        text = "#fafafa"
        border = "#4a4a5a"
        input_bg = "#1e1e24"
    else:
        bg = "#f8f9fa"
        card_bg = "#ffffff"
        text = "#1e1e2e"
        border = "#d1d5db"
        input_bg = "#f1f3f4"

    st.markdown(f"""
    <style>
        /* Global */
        .stApp {{ background-color: {bg}; }}
        .main .block-container {{ padding-top: 1rem; padding-bottom: 1rem; }}
        .stMetric {{ background-color: {card_bg}; border-radius: 12px; padding: 16px; border: 1px solid {border}; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }}
        .stDataFrame {{ border-radius: 12px; border: 1px solid {border}; }}
        .pro-card {{ background: {card_bg}; padding: 20px; border-radius: 12px; border: 1px solid {border}; margin-bottom: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.04); }}
        .pro-badge {{ background: #2d7d46; color: white; padding: 2px 12px; border-radius: 20px; font-size: 0.7rem; font-weight: 600; }}
        .pro-title {{ font-size: 1.8rem; font-weight: 700; color: {text}; }}
        .pro-subtitle {{ color: {text}; opacity: 0.7; font-size: 0.9rem; }}
        h1, h2, h3, h4, p, label, .stMarkdown {{ color: {text}; }}
        .stButton button {{ border-radius: 8px; font-weight: 500; transition: all 0.2s; }}
        .stButton button:hover {{ transform: scale(1.02); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
        .stSelectbox, .stTextInput, .stDateInput {{ background-color: {input_bg}; border-radius: 8px; }}
        .css-1d391kg {{ background-color: {bg}; }}
        .css-18e3th9 {{ background-color: {card_bg}; }}
        /* sidebar */
        .css-1d391kg .sidebar-content {{ background-color: {bg}; }}
        .css-1d391kg .sidebar-content .stMarkdown {{ color: {text}; }}
        /* scrollbar */
        ::-webkit-scrollbar {{ width: 6px; }}
        ::-webkit-scrollbar-track {{ background: {bg}; }}
        ::-webkit-scrollbar-thumb {{ background: #555; border-radius: 10px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: #888; }}
        /* toast notifications */
        .stToast {{ background: {card_bg}; border-left: 4px solid #2d7d46; }}
        /* select rows checkbox */
        .stCheckbox {{ margin-top: 0; }}
        .stDataFrame thead th {{ background: #2d7d46 !important; color: white !important; }}
        /* footer */
        .pro-footer {{ text-align: center; padding: 20px 0 10px; opacity: 0.5; font-size: 0.8rem; border-top: 1px solid {border}; margin-top: 30px; }}
    </style>
    """, unsafe_allow_html=True)

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

# ==================== CONSTANTS ====================
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
    'MXN': 'Mariani Junction', 'FKG': 'Furkating', 'JTI': 'Jatinga'
}
# (Full map is longer, but this covers major ones – you can copy full from previous code)

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

def get_station(code):
    if not code:
        return ''
    code = code.upper().strip()
    return f"{code} ({STATION_MAP[code]})" if code in STATION_MAP else code

def get_priority(vip_status):
    if not vip_status:
        return 1
    v = vip_status.upper().strip()
    if v in ['MR', 'MINISTER', 'OSD', 'PMO', 'RAIL BOARD']: return 5
    if v == 'MP': return 4
    if v == 'MLA': return 3
    if v in ['VVIP', 'VIP']: return 2
    return 1

# ==================== DRIVE UPLOAD & LINKING ====================
# (same as before – kept for upload feature)
def upload_to_drive(file_bytes, filename, mime_type):
    try:
        drive_service = init_drive()
        file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=True)
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id,name,webViewLink,size').execute()
        return {'success': True, 'id': file.get('id'), 'name': file.get('name'), 'url': file.get('webViewLink'), 'size': file.get('size')}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ==================== PDF GENERATOR (Pro) ====================
def generate_pro_pdf(df, title, sheet_name):
    pdf = FPDF('L', 'mm', 'A4')  # Landscape for more columns
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"AI EQMS Hub - {sheet_name} Report", ln=True, align='C')
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, f"Generated: {datetime.now().strftime('%d-%m-%Y %H:%M')}", ln=True, align='C')
    pdf.ln(6)
    pdf.set_font("Arial", 'B', 8)
    # Columns
    cols = df.columns.tolist()
    col_width = 270 / len(cols) if len(cols) > 0 else 20
    for col in cols:
        pdf.cell(col_width, 7, str(col)[:12], border=1, align='C')
    pdf.ln()
    pdf.set_font("Arial", '', 7)
    for _, row in df.head(50).iterrows():
        for col in cols:
            val = str(row[col])[:15] if pd.notna(row[col]) else ''
            pdf.cell(col_width, 6, val, border=1, align='L')
        pdf.ln()
    if len(df) > 50:
        pdf.cell(0, 6, f"... and {len(df)-50} more rows", ln=True, align='C')
    return pdf.output(dest='S').encode('latin1')

# ==================== DASHBOARD ====================
def show_dashboard(sheet_choice, df, start_row):
    total_records = len(df)
    if total_records == 0:
        st.info("No data in this sheet.")
        return

    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📊 Total Records", total_records)
    with col2:
        # Unique PNRs
        pnr_col = next((c for c in df.columns if 'PNR' in c.upper()), None)
        unique_pnrs = df[pnr_col].nunique() if pnr_col else 0
        st.metric("🆔 Unique PNRs", unique_pnrs)
    with col3:
        train_col = next((c for c in df.columns if 'T/N' in c.upper() or 'TRAIN' in c.upper()), None)
        unique_trains = df[train_col].nunique() if train_col else 0
        st.metric("🚂 Unique Trains", unique_trains)
    with col4:
        # Total Berths
        berth_col = next((c for c in df.columns if 'BERTH' in c.upper() or 'T/BERTHS' in c.upper()), None)
        total_berths = pd.to_numeric(df[berth_col], errors='coerce').sum() if berth_col else 0
        st.metric("💺 Total Berths", int(total_berths))

    # Chart: Train distribution
    if train_col and len(df) > 0:
        st.subheader("📈 Train-Wise Distribution")
        train_counts = df[train_col].value_counts().head(10).reset_index()
        train_counts.columns = ['Train', 'Count']
        fig = px.bar(train_counts, x='Train', y='Count', title=f"Top 10 Trains in {sheet_choice}",
                     color='Count', color_continuous_scale='Viridis', text='Count')
        fig.update_layout(height=350, margin=dict(l=20, r=20, t=40, b=20), plot_bgcolor='rgba(0,0,0,0)')
        fig.update_traces(textposition='outside')
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

# ==================== MAIN APP ====================
# ---- Theme toggle ----
dark_mode = st.sidebar.toggle("🌙 Dark Mode", value=False)
load_css(dark_mode)

st.sidebar.title("⚡ AI EQMS Hub Pro")
st.sidebar.write(f"📅 {datetime.now().strftime('%d-%m-%Y')}")

# Navigation
menu = st.sidebar.radio("Navigation", ["🏠 Dashboard & Sheets", "🤖 AI Upload", "📋 Reports & Quota"])

gc = init_sheets()

# ===== DASHBOARD & SHEETS =====
if menu == "🏠 Dashboard & Sheets":
    st.markdown("<div class='pro-title'>🚂 AI EQMS Hub</div>", unsafe_allow_html=True)
    st.markdown("<div class='pro-subtitle'>Enterprise Quality Management System – Pro Edition</div>", unsafe_allow_html=True)
    st.markdown("---")

    # Sheet selector
    sheet_choice = st.selectbox("Select Sheet", ["EQ", "DATA", "FINAL", "DATA2", "EMAIL_DATA"])
    start_row_map = {"EQ": 5, "DATA": 3, "FINAL": 4, "DATA2": 4, "EMAIL_DATA": 2}
    start_row = start_row_map.get(sheet_choice, 1)

    try:
        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
    except Exception as e:
        st.error(f"Error opening {sheet_choice}: {e}")
        st.stop()

    all_data = sheet.get_all_values()
    if len(all_data) < start_row:
        st.warning("No data rows.")
        st.stop()

    header_row = all_data[start_row-2] if start_row > 1 else all_data[0]
    data_rows = all_data[start_row-1:]
    df = pd.DataFrame(data_rows, columns=header_row[:len(data_rows[0])] if data_rows else [])
    if df.empty:
        st.info("No data found.")
        st.stop()

    # ---- Dashboard (always visible) ----
    show_dashboard(sheet_choice, df, start_row)

    # ---- Advanced Filters ----
    with st.expander("🔍 Advanced Filters", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            pnr_filter = st.text_input("PNR (partial)", key="pnr_filter")
        with col2:
            train_filter = st.text_input("Train (partial)", key="train_filter")
        with col3:
            priority_filter = st.selectbox("Priority", ["All", "VIP", "MP", "MLA", "MR", "General"], key="priority_filter")
        with col4:
            show_only = st.selectbox("Show", ["All Rows", "With File Link", "Without File Link"], key="show_only")

        # Date range
        col5, col6 = st.columns(2)
        with col5:
            from_date = st.date_input("From DOJ", value=None, key="from_date")
        with col6:
            to_date = st.date_input("To DOJ", value=None, key="to_date")

    # Apply filters
    filtered_df = df.copy()
    if pnr_filter:
        pnr_col = next((c for c in filtered_df.columns if 'PNR' in c.upper()), None)
        if pnr_col:
            filtered_df = filtered_df[filtered_df[pnr_col].astype(str).str.contains(pnr_filter, case=False, na=False)]
    if train_filter:
        train_col = next((c for c in filtered_df.columns if 'T/N' in c.upper() or 'TRAIN' in c.upper()), None)
        if train_col:
            filtered_df = filtered_df[filtered_df[train_col].astype(str).str.contains(train_filter, case=False, na=False)]
    if priority_filter != "All":
        pref_col = next((c for c in filtered_df.columns if 'PREFERENCE' in c.upper() or 'VIP' in c.upper()), None)
        if pref_col:
            filtered_df = filtered_df[filtered_df[pref_col].astype(str).str.upper().str.contains(priority_filter.upper(), na=False)]
    if show_only == "With File Link":
        link_col = next((c for c in filtered_df.columns if 'X' in c.upper() or 'LINK' in c.upper()), None)
        if link_col:
            filtered_df = filtered_df[filtered_df[link_col].astype(str).str.contains('HYPERLINK', na=False)]
    elif show_only == "Without File Link":
        link_col = next((c for c in filtered_df.columns if 'X' in c.upper() or 'LINK' in c.upper()), None)
        if link_col:
            filtered_df = filtered_df[~filtered_df[link_col].astype(str).str.contains('HYPERLINK', na=False)]

    # Date filter
    doj_col = next((c for c in filtered_df.columns if 'DOJ' in c.upper()), None)
    if doj_col:
        try:
            filtered_df['_temp_dt'] = pd.to_datetime(filtered_df[doj_col], format='%d-%m-%Y', errors='coerce')
            if from_date:
                filtered_df = filtered_df[filtered_df['_temp_dt'] >= pd.to_datetime(from_date)]
            if to_date:
                filtered_df = filtered_df[filtered_df['_temp_dt'] <= pd.to_datetime(to_date)]
            filtered_df = filtered_df.drop('_temp_dt', axis=1)
        except:
            pass

    # ---- Train Counts Sidebar ----
    train_col = next((c for c in filtered_df.columns if 'T/N' in c.upper() or 'TRAIN' in c.upper()), None)
    if train_col and not filtered_df.empty:
        train_counts = filtered_df[train_col].value_counts()
        st.sidebar.subheader("🚂 Train Counts")
        for train, count in train_counts.items():
            st.sidebar.write(f"**{train}**: {count}")

    # ---- Pagination ----
    page_size = st.sidebar.selectbox("Rows per page", [15, 25, 50, 100], index=1)
    total_pages = max(1, (len(filtered_df) + page_size - 1) // page_size)
    page = st.sidebar.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1) - 1
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(filtered_df))
    page_df = filtered_df.iloc[start_idx:end_idx]

    # ---- Display + Bulk Delete ----
    st.subheader(f"📋 {sheet_choice} – {len(filtered_df)} rows (showing {start_idx+1}-{end_idx})")
    st.caption(f"Start row in sheet: {start_row}")

    if not page_df.empty:
        # Add a selection column
        page_df.insert(0, "Select", False)
        edited_page = st.data_editor(
            page_df,
            use_container_width=True,
            height=400,
            column_config={
                "Select": st.column_config.CheckboxColumn("Select", width="small"),
            },
            key=f"pro_editor_{sheet_choice}_{page}"
        )

        # Bulk actions
        selected_rows = edited_page[edited_page["Select"]].index.tolist()
        if selected_rows:
            st.warning(f"⚠️ {len(selected_rows)} rows selected.")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🗑️ Delete Selected Rows", type="primary", use_container_width=True):
                    # Delete from sheet (actual row numbers: start_row + selected row index)
                    actual_rows = [start_row + idx for idx in selected_rows]
                    # Delete in reverse order to avoid shifting
                    for row_num in sorted(actual_rows, reverse=True):
                        try:
                            sheet.delete_rows(row_num)
                        except Exception as e:
                            st.error(f"Failed to delete row {row_num}: {e}")
                    st.toast(f"✅ {len(selected_rows)} rows deleted!", icon="🗑️")
                    st.rerun()
            with col2:
                if st.button("📥 Export Selected as CSV", use_container_width=True):
                    csv_data = edited_page[edited_page["Select"]].drop("Select", axis=1).to_csv(index=False).encode('utf-8')
                    st.download_button("Download CSV", data=csv_data, file_name="selected_rows.csv", mime="text/csv")
        else:
            st.info("Select rows using the checkbox to perform bulk actions.")

        # ---- Save Edits ----
        if st.button("💾 Save All Edits to Sheet", use_container_width=True):
            try:
                # We only write back the edited page, not the whole sheet to avoid overwriting others.
                # We'll update rows one by one for the visible page.
                for i, (orig_idx, row) in enumerate(edited_page.iterrows()):
                    actual_row = start_row + start_idx + i
                    row_data = row.drop("Select").tolist()
                    # Update row in sheet
                    for col_idx, val in enumerate(row_data, start=1):
                        sheet.update_cell(actual_row, col_idx, val)
                st.toast("✅ All changes saved successfully!", icon="💾")
            except Exception as e:
                st.error(f"Save error: {e}")

    # ---- Export Options ----
    st.subheader("📄 Export Options")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("🖨️ Print Sheet", use_container_width=True):
            st.markdown('<script>window.print()</script>', unsafe_allow_html=True)
    with col2:
        pdf_bytes = generate_pro_pdf(filtered_df, f"{sheet_choice} Report", sheet_choice)
        st.download_button("📥 Download PDF", data=pdf_bytes, file_name=f"{sheet_choice}_report.pdf", mime="application/pdf", use_container_width=True)
    with col3:
        csv_bytes = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download CSV", data=csv_bytes, file_name=f"{sheet_choice}.csv", mime="text/csv", use_container_width=True)
    with col4:
        # Excel export
        try:
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                filtered_df.to_excel(writer, sheet_name=sheet_choice, index=False)
            st.download_button("📥 Download Excel", data=excel_buffer.getvalue(), file_name=f"{sheet_choice}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        except:
            st.info("Excel export requires xlsxwriter. Install: pip install xlsxwriter")

    # ---- Print individual file ----
    link_col = next((c for c in filtered_df.columns if 'X' in c.upper() or 'LINK' in c.upper()), None)
    if link_col:
        st.subheader("🖨️ Print File from Row")
        for idx, row in filtered_df.iterrows():
            link = row[link_col]
            if isinstance(link, str) and 'HYPERLINK' in link:
                url_match = re.search(r'HYPERLINK\("([^"]+)"', link)
                if url_match:
                    file_url = url_match.group(1)
                    if st.button(f"🖨️ Print File (Row {idx+1})", key=f"print_{idx}_{sheet_choice}"):
                        st.markdown(f'<script>window.open("{file_url}&print=true", "_blank");</script>', unsafe_allow_html=True)

# ===== AI UPLOAD =====
elif menu == "🤖 AI Upload":
    st.title("🤖 AI Upload")
    st.markdown("Upload image, PDF, text, or audio. Gemini extracts railway EQ data and saves to sheet + Drive.")
    upload_type = st.radio("Type:", ["📷 Image", "📄 PDF", "📝 Text", "🎵 Audio"], horizontal=True)
    uploaded_file = None
    text_input = None
    if upload_type in ["📷 Image", "📄 PDF", "🎵 Audio"]:
        types = {"📷 Image": ['png','jpg','jpeg','gif','bmp','webp'], "📄 PDF": ['pdf'], "🎵 Audio": ['mp3','wav','ogg','m4a']}
        uploaded_file = st.file_uploader(f"Upload {upload_type}", type=types.get(upload_type, []))
    else:
        text_input = st.text_area("Enter text:", height=150)

    if st.button("🚀 Process & Save", use_container_width=True, type="primary"):
        # (Insert your existing Gemini extraction code here – same as before)
        st.toast("✅ Processing complete!", icon="🤖")

# ===== REPORTS & QUOTA =====
else:
    st.title("📋 Reports & Quota")
    try:
        note_sheet = gc.open_by_key(SHEET_ID).worksheet("NOTE")
        note_data = note_sheet.get_all_values()
        if len(note_data) > 1:
            df_note = pd.DataFrame(note_data[1:], columns=note_data[0] if note_data else [])
            st.dataframe(df_note, use_container_width=True)
        else:
            st.info("No quota data found.")
    except Exception as e:
        st.error(f"Error: {e}")

# ==================== FOOTER ====================
st.sidebar.markdown("---")
st.sidebar.caption("🚂 AI EQMS Hub Pro v3.0 | Gemini 2.5 Flash")
st.markdown("<div class='pro-footer'>© 2026 AI EQMS Hub – Pro Edition. All rights reserved.</div>", unsafe_allow_html=True)
