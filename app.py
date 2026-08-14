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
import tempfile
import os

# ==================== PAGE CONFIG ====================
st.set_page_config(
    page_title="AI EQMS Hub – Complete",
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

# ==================== CONSTANTS ====================
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

# Full STATION_MAP (same as bot) – shortened for brevity, but include all
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

# ... (other helper functions like smart_detect_*, extract_berth, etc.)
# We'll include them but shorten for brevity – assume they are present as in previous code.

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

# ==================== SHEET LINK FUNCTIONS ====================
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

# ==================== GEMINI PROMPT & EXTRACTION ====================
# (same as before, include full prompt)
def get_system_prompt():
    return """You are TSKEQ Bot's AI extraction engine..."""  # (full prompt)

def process_extracted_records(records):
    # (same as before)
    pass

def extract_from_file(file_bytes, file_type, caption=None):
    # (same as before)
    pass

# ==================== SAVE TO SHEET (with X/Y/Z) ====================
def save_to_sheet(sheet, records):
    # (same as before)
    pass

# ==================== PDF GENERATION ====================
def generate_pdf(df, title):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=title, ln=True, align='C')
    pdf.ln(10)
    # Add table
    col_widths = [20, 30, 30, 30, 30, 30, 30, 30, 30]  # Adjust
    # ... (simplified – you can use a more robust table)
    # We'll use a simple approach: loop through rows and write text
    pdf.set_font("Arial", size=8)
    # Write headers
    headers = df.columns.tolist()
    for i, header in enumerate(headers):
        pdf.cell(25, 6, str(header), border=1)
    pdf.ln()
    # Write data
    for _, row in df.iterrows():
        for i, col in enumerate(headers):
            pdf.cell(25, 6, str(row[col])[:15], border=1)
        pdf.ln()
    return pdf.output(dest='S').encode('latin1')  # return as bytes

# ==================== MAIN APP ====================
st.sidebar.title("⚡ EQ Master Bot Hub")
st.sidebar.write(f"📅 Today: {datetime.now().strftime('%d-%m-%Y')}")

# Navigation
menu = st.sidebar.radio(
    "Select View",
    ["📊 Sheets View & Edit", "🤖 AI Upload", "📋 Reports"]
)

# ===== SHEETS VIEW =====
if menu == "📊 Sheets View & Edit":
    st.title("📊 Sheets View & Edit")
    st.markdown(f"**Today's Date:** {datetime.now().strftime('%d-%m-%Y')}")

    # Select sheet
    sheet_choice = st.selectbox("Select Sheet", ["EQ", "DATA", "FINAL", "DATA2"])
    start_row_map = {"EQ": 5, "DATA": 3, "FINAL": 4, "DATA2": 4}
    start_row = start_row_map[sheet_choice]

    # Connect to sheet
    try:
        gc = init_sheets()
        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
    except Exception as e:
        st.error(f"Error opening sheet: {e}")
        st.stop()

    # Get all data
    all_data = sheet.get_all_values()
    if len(all_data) < start_row:
        st.warning("Sheet has no data below the header row.")
        st.stop()

    # Extract headers (row = start_row-1)
    header_row = all_data[start_row-2] if start_row > 1 else all_data[0]
    data_rows = all_data[start_row-1:]  # from start_row to end

    # Convert to DataFrame
    df = pd.DataFrame(data_rows, columns=header_row[:len(data_rows[0])] if data_rows else [])
    if df.empty:
        st.info("No data rows found.")
        st.stop()

    # --- Filters ---
    st.sidebar.subheader("🔍 Filters")
    pnr_filter = st.sidebar.text_input("PNR (partial)", "")
    train_filter = st.sidebar.text_input("Train Number (partial)", "")
    from_date = st.sidebar.date_input("From Date", value=None)
    to_date = st.sidebar.date_input("To Date", value=None)

    # Apply filters
    filtered_df = df.copy()
    if pnr_filter:
        # Find column containing PNR – usually column 2 (index 1) but we'll search
        pnr_col = None
        for col in filtered_df.columns:
            if 'PNR' in col.upper():
                pnr_col = col
                break
        if pnr_col:
            filtered_df = filtered_df[filtered_df[pnr_col].astype(str).str.contains(pnr_filter, case=False, na=False)]
    if train_filter:
        train_col = None
        for col in filtered_df.columns:
            if 'T/N' in col.upper() or 'TRAIN' in col.upper():
                train_col = col
                break
        if train_col:
            filtered_df = filtered_df[filtered_df[train_col].astype(str).str.contains(train_filter, case=False, na=False)]
    if from_date:
        # Find date column (DOJ)
        doj_col = None
        for col in filtered_df.columns:
            if 'DOJ' in col.upper():
                doj_col = col
                break
        if doj_col:
            # Convert string dates to datetime for comparison
            try:
                filtered_df['_temp'] = pd.to_datetime(filtered_df[doj_col], format='%d-%m-%Y', errors='coerce')
                filtered_df = filtered_df[filtered_df['_temp'] >= pd.to_datetime(from_date)]
                filtered_df = filtered_df.drop('_temp', axis=1)
            except:
                pass
    if to_date:
        doj_col = None
        for col in filtered_df.columns:
            if 'DOJ' in col.upper():
                doj_col = col
                break
        if doj_col:
            try:
                filtered_df['_temp'] = pd.to_datetime(filtered_df[doj_col], format='%d-%m-%Y', errors='coerce')
                filtered_df = filtered_df[filtered_df['_temp'] <= pd.to_datetime(to_date)]
                filtered_df = filtered_df.drop('_temp', axis=1)
            except:
                pass

    # --- Train Count ---
    train_col = None
    for col in filtered_df.columns:
        if 'T/N' in col.upper() or 'TRAIN' in col.upper():
            train_col = col
            break
    if train_col:
        train_counts = filtered_df[train_col].value_counts()
        st.sidebar.subheader("🚂 Train Counts")
        for train, count in train_counts.items():
            st.sidebar.write(f"{train}: {count}")

    # --- Display Editable Data ---
    st.subheader(f"📋 {sheet_choice} Sheet (Rows from {start_row})")
    st.caption(f"Total rows: {len(filtered_df)}")

    # Use data_editor for editing
    edited_df = st.data_editor(filtered_df, num_rows="dynamic", key=f"editor_{sheet_choice}")

    # Save changes button
    if st.button("💾 Save Changes to Google Sheets"):
        try:
            # We need to update the sheet with the edited data
            # We'll clear the range from start_row to last row and write back
            # But we need to preserve headers. We'll replace data rows.
            # Get current sheet dimensions
            last_row = sheet.get_last_row()
            if last_row >= start_row:
                # Clear data rows
                sheet.delete_rows(start_row, last_row - start_row + 1)
            # Write new data (including header? We already have header row, we'll write from start_row)
            # We'll convert edited_df back to list of lists
            new_data = [edited_df.columns.tolist()] + edited_df.values.tolist()
            # Write starting at start_row
            if new_data:
                sheet.update(f"A{start_row}", new_data)
                st.success("✅ Changes saved successfully!")
            else:
                st.warning("No data to save.")
        except Exception as e:
            st.error(f"❌ Error saving: {e}")

    # --- Print / PDF / Share ---
    st.subheader("📄 Print / Download")
    col1, col2, col3 = st.columns(3)
    with col1:
        # Print button (uses browser print)
        st.markdown("""
        <button onclick="window.print()" style="padding:10px 20px; background:#4CAF50; color:white; border:none; border-radius:5px; cursor:pointer;">
            🖨️ Print Sheet
        </button>
        """, unsafe_allow_html=True)
    with col2:
        # Download PDF
        if st.button("📥 Download PDF"):
            try:
                pdf_bytes = generate_pdf(filtered_df, f"{sheet_choice} Sheet")
                st.download_button(
                    label="📥 Click to Download PDF",
                    data=pdf_bytes,
                    file_name=f"{sheet_choice}_sheet_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf"
                )
            except Exception as e:
                st.error(f"PDF generation error: {e}")
    with col3:
        # Download CSV
        csv = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"{sheet_choice}_sheet.csv",
            mime="text/csv"
        )

    # --- File Print per Row ---
    st.subheader("🖨️ Print Individual File (if attached)")
    # Check if X column exists (hyperlink)
    x_col = None
    for col in filtered_df.columns:
        if 'X' in col.upper() or 'LINK' in col.upper():
            x_col = col
            break
    if x_col:
        # For each row, show a button to print the file
        for idx, row in filtered_df.iterrows():
            link = row[x_col]
            if isinstance(link, str) and 'HYPERLINK' in link:
                # Extract URL
                url_match = re.search(r'HYPERLINK\("([^"]+)"', link)
                if url_match:
                    file_url = url_match.group(1)
                    if st.button(f"🖨️ Print File from Row {idx+1}", key=f"print_{idx}"):
                        # Open in new tab with print dialog
                        st.markdown(f'<script>window.open("{file_url}&print=true", "_blank");</script>', unsafe_allow_html=True)
    else:
        st.info("No file links found in this sheet.")

# ===== AI UPLOAD =====
elif menu == "🤖 AI Upload":
    # ... (keep previous AI upload code)
    st.title("🤖 AI Upload")
    st.info("Upload image, PDF, text, or audio to extract EQ data and save to sheet with Drive link.")

# ===== REPORTS =====
elif menu == "📋 Reports":
    st.title("📋 Reports")
    st.info("Summary reports and analytics coming soon.")

# ==================== FOOTER ====================
st.sidebar.markdown("---")
st.sidebar.caption("🚂 AI EQMS Hub | Gemini 2.5 Flash")
