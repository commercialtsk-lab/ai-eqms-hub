import streamlit as st
import pandas as pd
import json
import re
import base64
from datetime import datetime
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image
import io
import time

st.set_page_config(page_title="AI EQMS Hub", page_icon="🚂", layout="wide")

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
GSPREAD_CREDENTIALS = st.secrets.get("GSPREAD_CREDENTIALS")

if not GEMINI_API_KEY:
    st.error("❌ GEMINI_API_KEY not found!")
    st.stop()

if not GSPREAD_CREDENTIALS:
    st.error("❌ GSPREAD_CREDENTIALS not found!")
    st.stop()

SHEET_ID = "1QcS3ZF3YYxSEykG0KiOUuXbTdBh0DMHdMgoqa9t8yrI"

@st.cache_resource
def init_gemini():
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel('gemini-2.5-flash')

@st.cache_resource
def init_sheets():
    time.sleep(1)  # Rate limit avoid karne ke liye
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(GSPREAD_CREDENTIALS, scope)
    return gspread.authorize(creds)

HEADINGS = [
    'S/N', 'PNR', 'FROM', 'TO', 'BOARDING', 'T/N', 'CLASS', 'DOJ',
    'PASS NAME', 'PASS PH', 'T/BERTHS', 'PURPOSE', 'ADDRESS',
    'DIARY NO', 'RECOMMENDATION', 'DESIGNATION', 'PHONE NUBER',
    'MP/MLA/MR/MINISTER/VIP/VVIP', 'WARRANT NUMBER', 'PROCEESING DATE+TIME',
    'APPLICATION DATE', 'RAILWAY/ZONE/DIVISION', 'PREFERENCE'
]

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

def get_system_prompt():
    return """You are an expert at reading railway EQ forms.
Extract these fields and return ONLY JSON array:
PNR, T_N, CLASS, DOJ (DD-MM-YYYY), FROM, TO, BOARDING, PASS_NAME,
PASS_PH (10 digits), T_BERTHS, PURPOSE, ADDRESS, DIARY_NO,
RECOMMENDATION, DESIGNATION, VIP_STATUS, APPLICATION_DATE,
RAILWAY_ZONE, PREFERENCE, PHONE_NUBER, WARRANT_NO

Example: [{"PNR":"9085176759","T_N":"15909","CLASS":"SL","DOJ":"28-06-2026","FROM":"NTSK","TO":"DLI","BOARDING":"","PASS_NAME":"SHARIQUE","PASS_PH":"9876543210","T_BERTHS":1,"PURPOSE":"","ADDRESS":"","DIARY_NO":"","RECOMMENDATION":"","DESIGNATION":"","VIP_STATUS":"","APPLICATION_DATE":"","RAILWAY_ZONE":"","PREFERENCE":"General","PHONE_NUBER":"","WARRANT_NO":""}]
Return ONLY JSON."""

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
        processed.append(rec)
    return {'records': processed, 'count': len(processed)}

@st.cache_data(ttl=60)
def get_sheet_data(sheet_name):
    """Cache sheet data to reduce API calls"""
    try:
        gc = init_sheets()
        ws = gc.open_by_key(SHEET_ID).worksheet(sheet_name)
        return ws.get_all_values()
    except Exception as e:
        return []

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
        row_data = [
            current_count, pnr, rec.get('FROM', '').upper(),
            rec.get('TO', '').upper(), rec.get('BOARDING', '').upper(),
            rec.get('T_N', '').strip(), rec.get('CLASS', '').upper(),
            rec.get('DOJ', ''), rec.get('PASS_NAME', '').strip(),
            rec.get('PASS_PH', ''), int(rec.get('T_BERTHS', 1)),
            rec.get('PURPOSE', '').strip(), rec.get('ADDRESS', '').strip(),
            rec.get('DIARY_NO', '').strip(), rec.get('RECOMMENDATION', '').strip(),
            rec.get('DESIGNATION', '').strip(), rec.get('PHONE_NUBER', ''),
            rec.get('VIP_STATUS', '').upper(), rec.get('WARRANT_NO', '').strip(),
            now, rec.get('APPLICATION_DATE', ''),
            rec.get('RAILWAY_ZONE', '').upper(), rec.get('PREFERENCE', 'General')
        ]
        sheet.append_row(row_data)
        existing.append(pnr)
        saved += 1
        time.sleep(0.5)  # Rate limit avoid
    return {'saved': saved, 'skipped': skipped, 'skip_reasons': skip_reasons}

st.sidebar.title("⚡ EQ Master Bot")
menu = st.sidebar.radio("Select View", ["📊 Sheets View", "🤖 AI Upload"])

try:
    gc = init_sheets()
    sheet = gc.open_by_key(SHEET_ID).worksheet("EQ")
except Exception as e:
    st.error(f"❌ Sheets error: {str(e)}")
    st.info("💡 Please wait 1-2 minutes and refresh the page")
    st.stop()

if menu == "📊 Sheets View":
    st.title("📊 Google Sheets Data")
    sheet_names = ["EQ", "EMAIL_DATA", "NOTE", "DATA", "FINAL", "DATA2"]
    tabs = st.tabs(sheet_names)
    for i, tab in enumerate(tabs):
        with tab:
            try:
                data = get_sheet_data(sheet_names[i])
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

elif menu == "🤖 AI Upload":
    st.title("🤖 AI Upload")
    upload_type = st.radio("Type:", ["📷 Image", "📄 PDF", "📝 Text", "🎵 Audio"], horizontal=True)
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
        text_input = st.text_area("Enter text:", height=150)
    if st.button("🚀 Process", use_container_width=True, type="primary"):
        with st.spinner("Processing..."):
            try:
                model = init_gemini()
                if uploaded_file:
                    file_bytes = uploaded_file.read()
                    file_base64 = base64.b64encode(file_bytes).decode('utf-8')
                    mime = "image/jpeg" if upload_type == "📷 Image" else ("application/pdf" if upload_type == "📄 PDF" else "audio/mpeg")
                    response = model.generate_content([get_system_prompt(), {"mime_type": mime, "data": file_base64}])
                    if upload_type == "📷 Image":
                        st.image(uploaded_file, width=300)
                elif text_input:
                    response = model.generate_content(get_system_prompt() + f"\n\nDATA:\n{text_input}")
                else:
                    st.warning("Please upload or enter data")
                    st.stop()
                match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', response.text)
                if match:
                    json_str = match.group().replace("'", '"')
                    records = json.loads(json_str)
                    if isinstance(records, dict):
                        records = [records]
                    result = process_extracted_records(records)
                    if result['count'] > 0:
                        st.success(f"✅ Extracted {result['count']} records!")
                        st.dataframe(pd.DataFrame(result['records']), use_container_width=True)
                        save_result = save_to_sheet(sheet, result['records'])
                        if save_result['saved'] > 0:
                            st.success(f"✅ Saved {save_result['saved']} new records!")
                        else:
                            st.warning("No new records (duplicates)")
                        if save_result['skipped'] > 0:
                            with st.expander(f"⚠️ Skipped {save_result['skipped']}"):
                                for r in save_result['skip_reasons']:
                                    st.text(f"  - {r}")
                    else:
                        st.warning("No valid records")
                else:
                    st.error("Could not parse JSON")
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")

st.markdown("---")
st.caption("🚂 EQ Master Bot Hub | Gemini 2.5 Flash")
