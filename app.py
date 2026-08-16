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
from zoneinfo import ZoneInfo
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from fpdf import FPDF
import plotly.express as px
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import numpy as np

st.set_page_config(page_title="AI EQMS Hub Pro", page_icon="🚂", layout="wide", initial_sidebar_state="expanded")

IST = ZoneInfo("Asia/Kolkata")

def now_ist():
    return datetime.now(IST)

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

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
GSPREAD_CREDENTIALS = st.secrets.get("GSPREAD_CREDENTIALS")
WEATHER_API_KEY = st.secrets.get("WEATHER_API_KEY", "")

if not GEMINI_API_KEY or not GSPREAD_CREDENTIALS:
    st.error("❌ Missing credentials! Please check secrets.toml")
    st.stop()

SHEET_ID = "1QcS3ZF3YYxSEykG0KiOUuXbTdBh0DMHdMgoqa9t8yrI"
DRIVE_FOLDER_ID = "1H1gf8WqfoTYFT_pU9WfIDLrHg-NpuUSI"

defaults = {
    'messages': [], 'activity_log': [], 'last_uploaded_file': None,
    'last_uploaded_drive_url': None, 'last_uploaded_view_url': None,
    'last_uploaded_print_url': None, 'last_refresh': time.time(),
    'chat_suggestions': [
        "Show me EQ summary", "How many records today?", "Train wise breakup",
        "Pending EQ requests", "Quota status", "PNR status"
    ],
    'theme': 'Day', 'custom_bg': '#ffffff', 'custom_text': '#000000',
    'current_page': 1, 'pnr_val': '', 'train_val': '', 'from_val': None,
    'to_val': None, 'upload_success': False, 'last_upload_time': None,
    'selected_sheet': "EQ", 'view_mode': "📋 Data Table",
    'select_all': False, 'delete_confirm': False,
    'auto_theme_detected': False,
}

for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

STATION_MAP = {
    'NTSK': 'New Tinsukia', 'GHY': 'Guwahati', 'NDLS': 'New Delhi', 'HWH': 'Howrah',
    'PNBE': 'Patna', 'BSB': 'Varanasi', 'CNB': 'Kanpur Central', 'LKO': 'Lucknow',
}

# ============================================================
# GOOGLE SHEETS
# ============================================================
@st.cache_resource
def init_sheets():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(GSPREAD_CREDENTIALS, scope)
    return gspread.authorize(creds)

SHEET_CONFIG = {
    "EQ": {"start_row": 5, "pnr_col": 1, "train_col": 5, "doj_col": 7},
    "DATA": {"start_row": 3, "pnr_col": 1, "train_col": 5, "doj_col": 7},
    "FINAL": {"start_row": 6, "pnr_col": 7, "train_col": 1, "doj_col": 12},
    "DATA2": {"start_row": 4, "pnr_col": 7, "train_col": 1, "doj_col": 12},
}

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

# ============================================================
# HELPERS
# ============================================================
def clean_pnr(pnr):
    if not pnr:
        return ''
    digits = re.sub(r'\D', '', str(pnr))
    return digits if len(digits) == 10 else (digits[-10:] if len(digits) > 10 else '')

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
        today = now_ist().replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
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
    st.session_state.activity_log.append({'timestamp': format_time(), 'action': action})
    if len(st.session_state.activity_log) > 50:
        st.session_state.activity_log = st.session_state.activity_log[-50:]

def sanitize_latin(text):
    if not text:
        return ''
    replacements = {'•': '-', '·': '-', '‘': "'", '’': "'", '“': '"', '”': '"', '–': '-', '—': '-'}
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode('latin-1', 'ignore').decode('latin-1')

# ============================================================
# GEMINI PARSER
# ============================================================
def gemini_universal_parser(input_data, input_type, mime_type, progress_callback=None):
    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}'
    system_prompt = """You are TSKEQ Bot's AI extraction engine. You are an EXPERT at reading messy, handwritten, torn, or low-quality railway forms.

=== FIELDS TO EXTRACT (21 fields) ===
PNR, T_N (Train Number), CLASS, DOJ (DD-MM-YYYY), FROM, TO, BOARDING, PASS_NAME, PASS_PH (10 digits), T_BERTHS, PURPOSE, ADDRESS, DIARY_NO, RECOMMENDATION, DESIGNATION, VIP_STATUS, APPLICATION_DATE, RAILWAY_ZONE, PREFERENCE, PHONE_NUBER, WARRANT_NO

=== SPECIAL RULES ===
1. DIARY_NO: Look for "No." or "Diary No." pattern.
2. PREFERENCE: If you see "Lower Berth", "Lower Seat", "Coupe", set PREFERENCE = "Lower Seat".
3. RAIL BOARD: If you see "Office of the Hon'ble Minister Railways", set DIARY_NO="RAIL BOARD".

=== OUTPUT FORMAT ===
Return ONLY a valid JSON array. No explanations.
[
  {
    "PNR": "6307598699",
    "T_N": "20503",
    "CLASS": "1A",
    "DOJ": "12-08-2026",
    "FROM": "HJP",
    "TO": "LKO",
    "BOARDING": "",
    "PASS_NAME": "INDU DUBEY",
    "PASS_PH": "9771425900",
    "T_BERTHS": 1,
    "PURPOSE": "",
    "ADDRESS": "",
    "DIARY_NO": "ECR/CRM/PCCM Cell/EQ/01/2026",
    "RECOMMENDATION": "MRITYUNJAY KUMAR",
    "DESIGNATION": "Secy to PCCM",
    "VIP_STATUS": "",
    "APPLICATION_DATE": "10-08-2026",
    "RAILWAY_ZONE": "ECR",
    "PREFERENCE": "Lower Seat",
    "PHONE_NUBER": "9771425962",
    "WARRANT_NO": ""
  }
]
CRITICAL: Return ONLY the JSON array.
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
        parts.append({"text": system_prompt + "\n\nINPUT DATA:\n" + input_data})
    else:
        return {'error': 'Unsupported type'}
    
    if progress_callback:
        progress_callback(30, "Sending to Gemini...")
    
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
        if not data.get('candidates') or not data['candidates'][0].get('content', {}).get('parts'):
            return {'error': 'Empty response from Gemini'}
        response_text = data['candidates'][0]['content']['parts'][0]['text']
        if progress_callback:
            progress_callback(60, "Parsing Gemini response...")
        json_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', response_text)
        if not json_match:
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
            if json_match:
                json_str = json_match.group(1)
            else:
                if progress_callback:
                    progress_callback(80, "Using fallback extraction...")
                return {'error': 'No JSON found in response'}
        else:
            json_str = json_match.group(0)
        json_str = json_str.replace('```json', '').replace('```', '').strip()
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        json_str = re.sub(r'([a-zA-Z0-9_]+)\s*:', r'"\1":', json_str)
        json_str = json_str.replace("'", '"')
        records = json.loads(json_str)
        if isinstance(records, dict):
            records = [records]
        if progress_callback:
            progress_callback(100, "Complete!")
        return {'records': records, 'count': len(records)}
    except Exception as e:
        return {'error': f'Parser Error: {e}'}

# ============================================================
# EXPORTS
# ============================================================
def generate_pdf(df, title, full=True):
    pdf = FPDF('L', 'mm', 'A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, f"AI EQMS Hub Pro - {title}", ln=True, align='C')
    pdf.set_font("Arial", '', 8)
    pdf.cell(0, 6, f"Generated: {format_datetime()} IST | Rows: {len(df)}", ln=True, align='C')
    pdf.ln(3)
    cols = list(df.columns)
    if '_sheet_row' in cols:
        cols.remove('_sheet_row')
    if len(cols) > 15:
        cols = cols[:15]
    col_width = min(25, 277 / max(len(cols), 1))
    pdf.set_font("Arial", 'B', 7)
    for c in cols:
        safe_c = sanitize_latin(str(c)[:15])
        pdf.cell(col_width, 6, safe_c, border=1)
    pdf.ln()
    pdf.set_font("Arial", '', 6)
    max_rows = len(df) if full else min(120, len(df))
    for idx, row in df.head(max_rows).iterrows():
        for c in cols:
            val = str(row.get(c, ""))[:20]
            safe_val = sanitize_latin(val)
            pdf.cell(col_width, 5, safe_val, border=1)
        pdf.ln()
        if pdf.get_y() > 185:
            pdf.add_page()
            pdf.set_font("Arial", 'B', 7)
            for c in cols:
                safe_c = sanitize_latin(str(c)[:15])
                pdf.cell(col_width, 6, safe_c, border=1)
            pdf.ln()
            pdf.set_font("Arial", '', 6)
    output = pdf.output(dest='S')
    if isinstance(output, bytearray):
        return bytes(output)
    elif isinstance(output, str):
        return output.encode('latin-1')
    else:
        return output

def create_table_image(df, title):
    if df.empty:
        return None
    cols = list(df.columns)
    if '_sheet_row' in cols:
        cols.remove('_sheet_row')
    if len(cols) > 10:
        cols = cols[:10]
    data = df[cols].head(50).values
    n_rows = min(len(df), 50)
    n_cols = len(cols)
    fig_height = max(3, 0.5 + 0.45 * n_rows)
    fig_width = max(10, 1.5 * n_cols)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    ax.axis('off')
    table = ax.table(cellText=data, colLabels=cols, loc='center', cellLoc='left')
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.6)
    for (i, j), cell in table.get_celld().items():
        if i == 0:
            cell.set_facecolor('#4a90d9')
            cell.set_text_props(color='white', weight='bold', fontsize=10)
        else:
            cell.set_facecolor('#f0f4fa' if i % 2 == 0 else 'white')
            cell.set_text_props(color='#1f2328', fontsize=9)
        cell.set_edgecolor('#cccccc')
        cell.set_height(0.04)
    plt.title(title, fontsize=14, weight='bold', pad=20, color='#1f2328')
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    buf.seek(0)
    plt.close()
    return buf.getvalue()

def build_whatsapp_message(sheet_name, selected_count, pnrs, total_rows, df):
    now_str = format_datetime()
    if not df.empty:
        cols = list(df.columns)
        if '_sheet_row' in cols:
            cols.remove('_sheet_row')
        cols = cols[:5]
        table_lines = []
        header = " | ".join([c[:8] for c in cols])
        table_lines.append(header)
        table_lines.append("-" * (len(header) + 4))
        for _, row in df.head(8).iterrows():
            row_vals = [str(row.get(c, ""))[:10] for c in cols]
            table_lines.append(" | ".join(row_vals))
        if len(df) > 8:
            table_lines.append(f"... and {len(df)-8} more rows")
        table_text = "\n".join(table_lines)
    else:
        table_text = "No data"
    if selected_count > 0 and pnrs:
        pnr_text = ", ".join(str(p) for p in pnrs[:10])
        if len(pnrs) > 10:
            pnr_text += f" (+{len(pnrs)-10} more)"
        msg = f"📊 *{sheet_name}* — {selected_count} rows selected\n🕐 {now_str}\n🎫 PNRs: {pnr_text}\n\n```\n{table_text}\n```"
    else:
        msg = f"📊 *{sheet_name}* — Total {total_rows} rows\n🕐 {now_str}\n\n```\n{table_text}\n```"
    msg += f"\n🔗 Sheet: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
    return msg

def get_pnr_status_url(pnr):
    if not pnr or len(str(pnr)) != 10:
        return None
    return f"https://www.confirmtkt.com/pnr-status/{pnr}"

# ============================================================
# WEATHER
# ============================================================
def get_weather(city_name, api_key):
    if not api_key:
        return None
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={api_key}&units=metric"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            d = r.json()
            return {
                'city': d.get('name', city_name),
                'country': d.get('sys', {}).get('country', ''),
                'temp': d.get('main', {}).get('temp', 0),
                'feels_like': d.get('main', {}).get('feels_like', 0),
                'humidity': d.get('main', {}).get('humidity', 0),
                'description': d.get('weather', [{}])[0].get('description', ''),
                'wind_speed': d.get('wind', {}).get('speed', 0),
                'pressure': d.get('main', {}).get('pressure', 0)
            }
    except:
        return None
    return None

def get_weather_emoji(desc):
    desc = desc.lower()
    if 'clear' in desc or 'sunny' in desc: return '☀️'
    if 'cloud' in desc: return '☁️'
    if 'rain' in desc: return '🌧️'
    if 'thunder' in desc: return '⛈️'
    if 'snow' in desc: return '❄️'
    if 'mist' in desc or 'fog' in desc: return '🌫️'
    return '🌡️'

def render_weather_widget():
    try:
        WEATHER_API_KEY = st.secrets["WEATHER_API_KEY"]
    except:
        WEATHER_API_KEY = ""
    
    st.markdown("---")
    st.markdown("### 🌤️ Weather")
    
    if 'weather_city' not in st.session_state:
        st.session_state.weather_city = "Tinsukia"
    
    city = st.selectbox("Select City", ["Tinsukia", "Dibrugarh", "Guwahati", "Delhi", "Mumbai", "Custom..."], index=0, key="weather_city_select")
    
    if city == "Custom...":
        city = st.text_input("Enter City", value=st.session_state.weather_city, key="weather_custom")
        if city:
            st.session_state.weather_city = city
    else:
        st.session_state.weather_city = city
    
    if not WEATHER_API_KEY:
        st.info("🔑 Weather API key not set.")
        return
    
    if st.button("🔄 Refresh", key="weather_refresh"):
        st.rerun()
    
    with st.spinner("Fetching weather..."):
        w = get_weather(st.session_state.weather_city, WEATHER_API_KEY)
    
    if w:
        emoji = get_weather_emoji(w['description'])
        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.05);border-radius:12px;padding:15px;margin:5px 0;">
            <div style="display:flex;align-items:center;gap:10px;">
                <span style="font-size:3rem;">{emoji}</span>
                <div>
                    <div style="font-size:1.8rem;font-weight:700;">{w['temp']:.1f}°C</div>
                    <div style="opacity:0.8;">{w['description'].title()}</div>
                </div>
            </div>
            <div style="font-weight:600;margin-top:5px;">📍 {w['city']}, {w['country']}</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-top:8px;font-size:0.85rem;">
                <div>🌡️ Feels: {w['feels_like']:.1f}°C</div>
                <div>💧 Humidity: {w['humidity']}%</div>
                <div>💨 Wind: {w['wind_speed']:.1f} m/s</div>
                <div>📊 Pressure: {w['pressure']} hPa</div>
            </div>
            <div style="font-size:0.7rem;opacity:0.6;margin-top:5px;">Updated: {datetime.now().strftime('%H:%M:%S')}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.error(f"❌ Could not fetch weather for '{st.session_state.weather_city}'")

# ============================================================
# THEME
# ============================================================
def apply_theme(theme, custom_bg=None, custom_text=None):
    if theme == 'Day':
        bg = "#f6f8fa"; card_bg = "#ffffff"; text_color = "#1f2328"
        border = "#d0d7de"; accent = "#0969da"; success = "#1a7f37"
        button_bg = "#f6f8fa"; button_text = "#1f2328"
    elif theme == 'Dark':
        bg = "#0d1117"; card_bg = "#161b22"; text_color = "#e6edf3"
        border = "#30363d"; accent = "#58a6ff"; success = "#3fb950"
        button_bg = "#21262d"; button_text = "#e6edf3"
    else:
        bg = custom_bg if custom_bg else "#ffffff"
        card_bg = bg; text_color = custom_text if custom_text else "#000000"
        border = "#d0d7de"; accent = "#0969da"; success = "#1a7f37"
        button_bg = bg; button_text = text_color

    css = f"""
    <style>
        .stApp {{ background-color: {bg} !important; }}
        [data-testid="stSidebar"] {{ background-color: {card_bg} !important; border-right: 1px solid {border} !important; }}
        h1, h2, h3, h4, h5, h6, .stMarkdown p, .stMarkdown div, .stMarkdown span {{
            color: {text_color} !important;
        }}
        .stButton > button {{
            background-color: {accent} !important;
            color: white !important;
            border-radius: 8px !important;
            font-weight: 500 !important;
            border: none !important;
        }}
        .stButton > button:hover {{
            background-color: {accent} !important;
            opacity: 0.8 !important;
        }}
        .stTextInput input, .stNumberInput input, .stDateInput input, .stTextArea textarea {{
            background-color: {card_bg} !important;
            color: {text_color} !important;
            border: 1px solid {border} !important;
            border-radius: 8px !important;
        }}
        .stDataFrame, .stDataEditor {{
            background-color: {card_bg} !important;
            color: {text_color} !important;
        }}
        .train-count-card {{
            border: 1px solid {border} !important;
            border-radius: 4px;
            padding: 1px 6px !important;
            min-width: auto !important;
            display: inline-block;
            margin: 1px !important;
            background: transparent !important;
        }}
        .train-count-number {{ 
            color: {accent} !important;
            font-weight: 600;
            font-size: 0.85rem !important;
            line-height: 1.2;
        }}
        .train-count-badge {{ 
            display: inline-block;
            background: {accent} !important;
            color: white;
            font-size: 0.55rem !important;
            font-weight: 600;
            padding: 0px 4px !important;
            border-radius: 8px;
        }}
        .train-total-card {{ 
            background: transparent !important;
            border: 1.5px solid {success} !important;
            border-radius: 4px;
            padding: 1px 10px !important;
            min-width: auto !important;
            display: inline-block;
            margin: 1px !important;
        }}
        .train-total-number {{ 
            color: {success} !important;
            font-weight: 600;
            font-size: 0.85rem !important;
        }}
        .train-count-container {{ 
            display: flex; 
            flex-wrap: wrap; 
            gap: 3px !important; 
            justify-content: flex-start; 
            margin: 4px 0; 
            align-items: center; 
        }}
        .print-table {{ display: none; }}
        @media print {{
            .print-table {{ display: block !important; }}
            .print-table table {{ width: 100% !important; border-collapse: collapse !important; }}
            .print-table th, .print-table td {{ border: 1px solid #333 !important; padding: 4px !important; font-size: 10pt !important; }}
            .print-table th {{ background: #eee !important; }}
            .no-print {{ display: none !important; }}
            .stDataFrame {{ display: none !important; }}
        }}
        .status-pill {{ display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 500; }}
        .status-live {{ background: rgba(63, 185, 80, 0.15); color: {success} !important; border: 1px solid {success} !important; }}
        .sheet-link-btn {{
            display: inline-block !important; padding: 8px 16px !important;
            background: {button_bg} !important; color: {accent} !important;
            border: 1px solid {border} !important; border-radius: 8px !important;
            text-decoration: none !important; text-align: center !important; width: 100% !important;
            font-weight: 500 !important; font-size: 0.9rem !important;
        }}
        .sheet-link-btn:hover {{ background: {accent} !important; color: white !important; border-color: {accent} !important; }}
        .pro-footer {{ color: {text_color} !important; opacity: 0.6; border-top: 1px solid {border} !important; text-align: center !important; padding: 18px 0 8px !important; margin-top: 28px !important; font-size: 0.8rem !important; }}
        .action-box {{ background: {card_bg} !important; border: 1px solid {border} !important; border-radius: 12px; padding: 15px; margin-bottom: 16px; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# ============================================================
# MAIN APP
# ============================================================
def main():
    # Theme
    theme_options = ['Day', 'Dark', 'Custom', 'Auto (System)']
    if not st.session_state.auto_theme_detected:
        st.session_state.auto_theme_detected = True
        if st.session_state.theme == 'Day':
            st.session_state.theme = 'Auto (System)'

    theme_choice = st.sidebar.selectbox("🎨 Theme", theme_options,
        index=theme_options.index(st.session_state.theme) if st.session_state.theme in theme_options else 0,
        key="theme_select")
    if theme_choice != st.session_state.theme:
        st.session_state.theme = theme_choice
        st.rerun()

    effective_theme = theme_choice
    if theme_choice == 'Auto (System)':
        effective_theme = 'Day'
        if st.query_params.get('__dark_mode') == '1':
            effective_theme = 'Dark'

    if effective_theme == 'Custom':
        custom_bg = st.sidebar.color_picker("Background Color", value=st.session_state.custom_bg, key="custom_bg_picker")
        custom_text = st.sidebar.color_picker("Text Color", value=st.session_state.custom_text, key="custom_text_picker")
        if custom_bg != st.session_state.custom_bg or custom_text != st.session_state.custom_text:
            st.session_state.custom_bg = custom_bg
            st.session_state.custom_text = custom_text
            st.rerun()
    else:
        custom_bg = None
        custom_text = None

    apply_theme(effective_theme, custom_bg, custom_text)

    with st.sidebar:
        st.markdown("""
        <div style="text-align:center; margin-bottom:10px; font-size:1.2rem; line-height:1.8;">
            <span style="color:#FF9933;">🟠 नमस्ते</span><br>
            <span style="color:#FFFFFF;">⚪ जय हिंद</span><br>
            <span style="color:#138808; font-weight:bold;">🟢 भारत</span>
        </div>
        """, unsafe_allow_html=True)
        st.caption(f"📅 {format_date()}  •  🕐 {format_time()} IST")

        with st.expander("🔄 Sync & Status", expanded=True):
            auto_refresh = st.checkbox("Auto Sync (every 10s)", value=True, key="auto_sync_cb")
            if auto_refresh:
                elapsed = time.time() - st.session_state.last_refresh
                if elapsed > 10:
                    st.session_state.last_refresh = time.time()
                    st.cache_data.clear()
                    st.rerun()
                else:
                    remaining = 10 - int(elapsed)
                    st.caption(f"⏳ Next sync in {remaining}s")
            if st.button("🔄 Sync Now", use_container_width=True, key="sync_now_btn"):
                st.cache_data.clear()
                st.session_state.last_refresh = time.time()
                log_activity("🔄 Manual sync")
                st.rerun()
            st.caption(f"Last sync: {format_time(datetime.fromtimestamp(st.session_state.last_refresh, tz=IST))} IST")

        sheet_link = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
        st.markdown(f'<a href="{sheet_link}" target="_blank" class="sheet-link-btn">📊 Open Sheet</a>', unsafe_allow_html=True)

        # ============================================================
        # 📤 UPLOAD SECTION
        # ============================================================
        with st.expander("📤 Upload & Process", expanded=True):
            st.caption("📷 Image • 📄 PDF • 📝 Text • 🎤 Audio")
            mode = st.radio("Type", ["📷 Image / PDF", "📝 Text", "🎤 Voice / Audio"],
                horizontal=True, label_visibility="collapsed", key="upload_mode_radio")
            uploaded = None
            text_data = ""
            audio_data = None
            if mode == "📷 Image / PDF":
                uploaded = st.file_uploader("Image or PDF", type=["png","jpg","jpeg","pdf"],
                    label_visibility="collapsed", key="img_pdf_uploader")
            elif mode == "📝 Text":
                text_data = st.text_area("📝 Paste text", height=150,
                    placeholder="Messy text yahan paste karein...",
                    label_visibility="collapsed", key="text_input_area")
                if text_data:
                    st.caption(f"✓ {len(text_data)} characters ready")
            else:
                st.caption("🎤 Mic se record karein")
                audio_data = st.audio_input("Record", label_visibility="collapsed", key="audio_recorder")
                uploaded = st.file_uploader("Ya file upload", type=["mp3","wav","ogg","m4a"],
                    label_visibility="collapsed", key="audio_file_uploader")
                if audio_data:
                    st.audio(audio_data, format='audio/wav')
                elif uploaded:
                    st.audio(uploaded, format='audio/mp3')

            if st.button("🚀 Process & Save", type="primary", use_container_width=True, key="process_save_btn"):
                if mode == "📝 Text" and not text_data.strip():
                    st.warning("Text daalein")
                elif mode != "📝 Text" and not uploaded and not audio_data:
                    st.warning("File select karein")
                else:
                    prog = st.progress(0)
                    status = st.empty()
                    def upd(v, m):
                        prog.progress(v)
                        status.text(m)
                    try:
                        if mode == "📝 Text":
                            fbytes = text_data.encode()
                            b64 = base64.b64encode(fbytes).decode()
                            res = gemini_universal_parser(b64, "text", None, upd)
                            fname = f"text_{now_ist().strftime('%H%M%S')}.txt"
                            mime = "text/plain"
                        elif audio_data:
                            fbytes = audio_data.getvalue()
                            b64 = base64.b64encode(fbytes).decode()
                            res = gemini_universal_parser(b64, "audio", "audio/wav", upd)
                            fname = f"voice_{now_ist().strftime('%H%M%S')}.wav"
                            mime = "audio/wav"
                        else:
                            fbytes = uploaded.read()
                            b64 = base64.b64encode(fbytes).decode()
                            ftype = "pdf" if uploaded.type == "application/pdf" else "image"
                            res = gemini_universal_parser(b64, ftype, uploaded.type, upd)
                            fname = uploaded.name
                            mime = uploaded.type

                        if "error" in res:
                            st.error(res["error"])
                            log_activity(f"❌ Parse failed: {res['error'][:50]}")
                        else:
                            st.success(f"✅ Extracted {res['count']} record(s)")
                            if res.get('records'):
                                with st.expander("🔍 Preview extracted data"):
                                    st.dataframe(pd.DataFrame(res['records']), use_container_width=True)
                            try:
                                gc = init_sheets()
                                eq_sheet = gc.open_by_key(SHEET_ID).worksheet("EQ")
                                # Save to sheet - simplified
                                saved = 0
                                for rec in res['records']:
                                    pnr = clean_pnr(rec.get('PNR', ''))
                                    if pnr:
                                        now = format_datetime()
                                        row = [
                                            len(eq_sheet.get_all_values()) - 4 + 1,
                                            pnr,
                                            rec.get('FROM', ''), rec.get('TO', ''), rec.get('BOARDING', ''),
                                            rec.get('T_N', ''), rec.get('CLASS', ''), rec.get('DOJ', ''),
                                            rec.get('PASS_NAME', ''), rec.get('PASS_PH', ''),
                                            rec.get('T_BERTHS', 1), rec.get('PURPOSE', ''), rec.get('ADDRESS', ''),
                                            rec.get('DIARY_NO', ''), rec.get('RECOMMENDATION', ''),
                                            rec.get('DESIGNATION', ''), rec.get('PHONE_NUBER', ''),
                                            rec.get('VIP_STATUS', ''), rec.get('WARRANT_NO', ''),
                                            now, rec.get('APPLICATION_DATE', ''), rec.get('RAILWAY_ZONE', ''),
                                            rec.get('PREFERENCE', 'General')
                                        ]
                                        eq_sheet.append_row(row)
                                        saved += 1
                                        time.sleep(0.12)
                                st.success(f"✅ Saved {saved} records")
                                st.cache_data.clear()
                                st.session_state.last_refresh = time.time()
                                time.sleep(0.3)
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Sheet error: {e}")
                    except Exception as e:
                        st.error(f"❌ Processing error: {e}")
                    finally:
                        prog.empty()
                        status.empty()

        with st.expander("📑 Sheet & Filters", expanded=True):
            sheet_choice = st.selectbox("Select Sheet", list(SHEET_CONFIG.keys()),
                index=list(SHEET_CONFIG.keys()).index(st.session_state.selected_sheet)
                if st.session_state.selected_sheet in SHEET_CONFIG else 0,
                key="sheet_select")
            st.session_state.selected_sheet = sheet_choice
            config = SHEET_CONFIG[sheet_choice]

            pnr_input = st.text_input("PNR", value=st.session_state.pnr_val, key="pnr_filter_input")
            if pnr_input != st.session_state.pnr_val:
                st.session_state.pnr_val = pnr_input
                st.session_state.current_page = 1
                st.rerun()

            train_input = st.text_input("Train", value=st.session_state.train_val, key="train_filter_input")
            if train_input != st.session_state.train_val:
                st.session_state.train_val = train_input
                st.session_state.current_page = 1
                st.rerun()

            c1, c2 = st.columns(2)
            with c1:
                from_input = st.date_input("From DOJ", value=st.session_state.from_val,
                    key="from_date_input", format="DD-MM-YYYY")
            with c2:
                to_input = st.date_input("To DOJ", value=st.session_state.to_val,
                    key="to_date_input", format="DD-MM-YYYY")
            if from_input != st.session_state.from_val:
                st.session_state.from_val = from_input
                st.session_state.current_page = 1
                st.rerun()
            if to_input != st.session_state.to_val:
                st.session_state.to_val = to_input
                st.session_state.current_page = 1
                st.rerun()

        df_raw = load_sheet_data_cached(sheet_choice, SHEET_ID)
        filtered_df = df_raw.copy() if not df_raw.empty else pd.DataFrame()

        if not filtered_df.empty:
            pnr_col_idx = config.get("pnr_col")
            train_col_idx = config.get("train_col")
            doj_col_idx = config.get("doj_col")
            if st.session_state.pnr_val and pnr_col_idx is not None and pnr_col_idx < len(filtered_df.columns):
                col_name = filtered_df.columns[pnr_col_idx]
                filtered_df = filtered_df[filtered_df[col_name].astype(str).str.contains(st.session_state.pnr_val, case=False, na=False)]
            if st.session_state.train_val and train_col_idx is not None and train_col_idx < len(filtered_df.columns):
                col_name = filtered_df.columns[train_col_idx]
                filtered_df = filtered_df[filtered_df[col_name].astype(str).str.contains(st.session_state.train_val, case=False, na=False)]
            if (st.session_state.from_val or st.session_state.to_val) and doj_col_idx is not None and doj_col_idx < len(filtered_df.columns):
                col_name = filtered_df.columns[doj_col_idx]
                try:
                    filtered_df['_temp'] = pd.to_datetime(filtered_df[col_name], format='%d-%m-%Y', errors='coerce')
                    if filtered_df['_temp'].isna().all():
                        filtered_df['_temp'] = pd.to_datetime(filtered_df[col_name], errors='coerce')
                except Exception:
                    filtered_df['_temp'] = pd.to_datetime(filtered_df[col_name], errors='coerce')
                if st.session_state.from_val:
                    filtered_df = filtered_df[filtered_df['_temp'] >= pd.to_datetime(st.session_state.from_val)]
                if st.session_state.to_val:
                    filtered_df = filtered_df[filtered_df['_temp'] <= pd.to_datetime(st.session_state.to_val)]
                filtered_df = filtered_df.drop('_temp', axis=1, errors='ignore')

        view = st.radio("View Mode", ["📋 Data Table", "📊 Dashboard", "💬 Chat"],
            index=["📋 Data Table", "📊 Dashboard", "💬 Chat"].index(st.session_state.view_mode)
            if st.session_state.view_mode in ["📋 Data Table", "📊 Dashboard", "💬 Chat"] else 0,
            key="view_mode_radio")
        if view != st.session_state.view_mode:
            st.session_state.view_mode = view
            st.rerun()

        render_weather_widget()

    top_c1, top_c2 = st.columns([4, 1])
    with top_c1:
        st.markdown("<h1 style='font-size:20px; font-weight:700; margin:0;'>🚂 AI EQMS Hub Pro</h1>", unsafe_allow_html=True)
    with top_c2:
        st.markdown(f"<div style='padding-top:6px; text-align:right;'><span class='status-pill status-live'>● Live</span> <span style='font-size:12px;'>Sync {format_time(datetime.fromtimestamp(st.session_state.last_refresh, tz=IST))}</span></div>", unsafe_allow_html=True)

    st.caption(f"Enterprise Railway EQ Management • {format_date()} • {format_time()} IST")
    st.markdown("---")

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
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    elif view == "📊 Dashboard":
        st.subheader("📊 Analytics Dashboard")
        train_col = None
        for c in filtered_df.columns:
            if 'T/N' in c.upper() or 'T_N' in c.upper() or 'TRAIN' in c.upper():
                train_col = c
                break
        
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Total Records", len(filtered_df) if not filtered_df.empty else 0)
        with m2:
            st.metric("Unique Trains", filtered_df[train_col].nunique() if train_col else 0)
        with m3:
            berth_col = next((c for c in filtered_df.columns if 'BERTH' in str(c).upper() or 'T/BERTHS' in str(c).upper()), None)
            total_berths = 0
            if berth_col and berth_col in filtered_df:
                total_berths = pd.to_numeric(filtered_df[berth_col], errors='coerce').sum()
            st.metric("Total Berths", int(total_berths) if total_berths else 0)
        with m4:
            doj_col = next((c for c in filtered_df.columns if 'DOJ' in str(c).upper()), None)
            expired = 0
            if doj_col and doj_col in filtered_df:
                expired = sum(1 for _, r in filtered_df.iterrows() if is_expired(r.get(doj_col, '')))
            st.metric("Expired DOJ", expired)
        
        st.markdown("---")
        if not filtered_df.empty and train_col:
            train_counts = filtered_df[train_col].value_counts().reset_index()
            train_counts.columns = ['Train', 'Count']
            fig_bar = px.bar(train_counts.head(15), x='Train', y='Count', title="Top 15 Trains", color='Count', color_continuous_scale='Blues')
            fig_bar.update_layout(height=400, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_bar, use_container_width=True)
            
            class_col = next((c for c in filtered_df.columns if 'CLASS' in str(c).upper()), None)
            if class_col:
                class_counts = filtered_df[class_col].value_counts().reset_index()
                class_counts.columns = ['Class', 'Count']
                fig_pie = px.pie(class_counts, names='Class', values='Count', title="Class Distribution", hole=0.4)
                fig_pie.update_layout(height=350, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_pie, use_container_width=True)

    else:  # Data Table
        st.subheader(f"📋 {sheet_choice}  —  {len(filtered_df)} rows")
        
        train_col_metric = None
        doj_col = None
        for c in filtered_df.columns:
            if 'T/N' in c.upper() or 'T_N' in c.upper() or 'TRAIN' in c.upper():
                train_col_metric = c
            if 'DOJ' in c.upper():
                doj_col = c

        if not filtered_df.empty and train_col_metric:
            train_counts_series = filtered_df[train_col_metric].value_counts()
            st.markdown("**🚆 Train-wise Count**")
            cards_html = '<div class="train-count-container">'
            total_eq = len(filtered_df)
            cards_html += f'<span class="train-total-card"><span class="train-total-number">Total EQ: {total_eq}</span></span>'
            for train_num, cnt in train_counts_series.items():
                cards_html += f'<span class="train-count-card"><span class="train-count-number">{train_num}</span> <span class="train-count-badge">{cnt}</span></span>'
            cards_html += '</div>'
            st.markdown(cards_html, unsafe_allow_html=True)
            st.markdown("---")

        if filtered_df.empty:
            st.info("No data to show.")
        else:
            page_size = st.selectbox("Rows per page", [15, 25, 50, 100], index=1, key="page_size_select")
            total_pages = max(1, math.ceil(len(filtered_df) / page_size))
            if st.session_state.current_page > total_pages:
                st.session_state.current_page = total_pages
            if st.session_state.current_page < 1:
                st.session_state.current_page = 1

            nav1, nav2, nav3 = st.columns([1, 2, 1])
            with nav1:
                if st.button("◀ Previous", use_container_width=True, disabled=st.session_state.current_page <= 1, key="prev_page_btn"):
                    st.session_state.current_page -= 1
                    st.rerun()
            with nav2:
                st.markdown(f"<div style='text-align:center; padding-top:6px;'><b>Page {st.session_state.current_page} of {total_pages}</b></div>", unsafe_allow_html=True)
            with nav3:
                if st.button("Next ▶", use_container_width=True, disabled=st.session_state.current_page >= total_pages, key="next_page_btn"):
                    st.session_state.current_page += 1
                    st.rerun()

            page = st.session_state.current_page - 1
            start_idx = page * page_size
            end_idx = min(start_idx + page_size, len(filtered_df))
            page_df = filtered_df.iloc[start_idx:end_idx].copy()
            sheet_rows = page_df['_sheet_row'].tolist() if '_sheet_row' in page_df.columns else []
            display_df = page_df.drop(columns=['_sheet_row'], errors='ignore')
            display_df.insert(0, "Select", False)

            print_cols = [c for c in display_df.columns if c != 'Select']
            print_df = display_df[print_cols].copy()
            if not print_df.empty:
                st.markdown(f"""
                <div class="print-table">
                    <h3 style="text-align:center;">{sheet_choice} Data</h3>
                    {print_df.to_html(index=False, border=1)}
                    <p style="text-align:center; font-size:9pt;">Generated: {format_datetime()} IST</p>
                </div>
                """, unsafe_allow_html=True)

            st.markdown('<div class="print-area no-print">', unsafe_allow_html=True)
            edited_page = st.data_editor(display_df, use_container_width=True, height=400,
                column_config={"Select": st.column_config.CheckboxColumn("Select", width="small")},
                key=f"editor_{sheet_choice}_{st.session_state.current_page}_{page_size}")
            st.markdown('</div>', unsafe_allow_html=True)

            select_all = st.checkbox("Select All on Page", value=st.session_state.select_all, key="select_all_cb")
            if select_all != st.session_state.select_all:
                st.session_state.select_all = select_all
                st.rerun()

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

            pnr_col = next((c for c in edited_page.columns if 'PNR' in str(c).upper()), None)
            selected_pnrs = edited_page.loc[selected_indices, pnr_col].tolist() if pnr_col and selected_indices else []

            st.markdown('<div class="action-box no-print">', unsafe_allow_html=True)
            st.markdown("**⚡ Quick Actions**")
            a1, a2, a3, a4, a5 = st.columns(5)
            with a1:
                if st.button("💾 Save Edits", use_container_width=True, key="save_edits_btn"):
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
                                range_name = f"A{sheet_row_num}:{col_letter}{sheet_row_num}"
                                sheet.update(range_name, [row_data])
                            st.toast("✅ Saved!", icon="💾")
                            log_activity(f"💾 Saved {len(data_list)} rows in {sheet_choice}")
                            st.cache_data.clear()
                            st.session_state.last_refresh = time.time()
                            time.sleep(0.3)
                            st.rerun()
                        else:
                            st.warning("Nothing to save")
                    except Exception as e:
                        if "429" in str(e):
                            st.error("Write quota exceeded. Wait 1 minute.")
                        else:
                            st.error(f"Save error: {e}")
            with a2:
                if st.button("➕ Add Row", use_container_width=True, key="add_row_btn"):
                    try:
                        gc = init_sheets()
                        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                        all_data = sheet.get_all_values()
                        num_cols = len(all_data[0]) if all_data else 1
                        blank_row = [''] * num_cols
                        config = SHEET_CONFIG.get(sheet_choice, {"start_row": 5})
                        start_row = config["start_row"]
                        if len(all_data) >= start_row:
                            blank_row[0] = len(all_data) - start_row + 2
                        sheet.append_row(blank_row)
                        st.toast("✅ Row added", icon="➕")
                        log_activity(f"➕ Added row in {sheet_choice}")
                        st.cache_data.clear()
                        st.session_state.last_refresh = time.time()
                        time.sleep(0.3)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Add error: {e}")
            with a3:
                if selected_sheet_rows:
                    if st.button("🗑️ Delete", use_container_width=True, key="delete_btn"):
                        if not st.session_state.delete_confirm:
                            st.session_state.delete_confirm = True
                            st.warning("Confirm delete by clicking again.")
                            st.rerun()
                        else:
                            try:
                                gc = init_sheets()
                                sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                                for row_num in sorted(selected_sheet_rows, reverse=True):
                                    sheet.delete_rows(row_num)
                                st.toast(f"✅ Deleted {len(selected_sheet_rows)}", icon="🗑️")
                                log_activity(f"🗑️ Deleted {len(selected_sheet_rows)} from {sheet_choice}")
                                st.session_state.delete_confirm = False
                                st.cache_data.clear()
                                st.session_state.last_refresh = time.time()
                                time.sleep(0.3)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Delete error: {e}")
                else:
                    st.button("🗑️ Delete", disabled=True, use_container_width=True, key="delete_disabled_btn")
                    st.session_state.delete_confirm = False
            with a4:
                msg = build_whatsapp_message(sheet_choice, len(selected_indices), selected_pnrs, len(filtered_df), filtered_df)
                encoded = urllib.parse.quote(msg)
                wa_url = f"https://api.whatsapp.com/send?text={encoded}"
                st.link_button("📤 WhatsApp Text", wa_url, use_container_width=True)
            with a5:
                st.button("🖨️ PRINT SHEET", use_container_width=True, key="print_btn")
                st.components.v1.html("""
                <script>
                    document.addEventListener('DOMContentLoaded', function() {
                        const btn = document.querySelector('button[data-testid="baseButton-secondary"][kind="secondary"]');
                        if (btn && btn.innerText.includes('PRINT SHEET')) {
                            btn.onclick = function() { window.print(); };
                        }
                    });
                </script>
                """, height=0)
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="no-print">', unsafe_allow_html=True)
            st.markdown("**📱 WhatsApp Image Share**")
            wa_col1, wa_col2, wa_col3 = st.columns(3)
            with wa_col1:
                if not filtered_df.empty:
                    img_bytes = create_table_image(filtered_df, f"{sheet_choice} Data")
                    if img_bytes:
                        st.download_button("🖼️ Download Table Image", data=img_bytes,
                            file_name=f"{sheet_choice}_table.png", mime="image/png",
                            use_container_width=True, key="wa_img_download")
            with wa_col2:
                if selected_indices and not filtered_df.empty:
                    sel_img_bytes = create_table_image(filtered_df.iloc[selected_indices], f"{sheet_choice} Selected")
                    if sel_img_bytes:
                        st.download_button("🖼️ Download Selected Image", data=sel_img_bytes,
                            file_name=f"{sheet_choice}_selected.png", mime="image/png",
                            use_container_width=True, key="wa_sel_img_download")
                    else:
                        st.info("Select rows to generate image")
            with wa_col3:
                if not filtered_df.empty:
                    img_bytes = create_table_image(filtered_df, f"{sheet_choice} Data")
                    if img_bytes:
                        img_b64 = base64.b64encode(img_bytes).decode()
                        st.markdown(f"""
                        <button onclick="copyImageToClipboard()" style="
                            background: #25D366; color: white; border: none; border-radius: 8px;
                            padding: 9px 16px; width: 100%; font-weight: 600;
                            cursor: pointer; font-size: 1rem;
                        ">📋 Copy Sheet Image</button>
                        <script>
                        function copyImageToClipboard() {{
                            var imgData = "{img_b64}";
                            fetch('data:image/png;base64,' + imgData)
                                .then(res => res.blob())
                                .then(blob => {{
                                    navigator.clipboard.write([
                                        new ClipboardItem({{ 'image/png': blob }})
                                    ]).then(() => {{
                                        alert('Image copied to clipboard! Paste it into WhatsApp.');
                                    }}).catch(() => {{
                                        alert('Failed to copy. Please use download instead.');
                                    }});
                                }});
                        }}
                        </script>
                        """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="no-print">', unsafe_allow_html=True)
            st.markdown("**📄 Export**")
            e1, e2, e3, e4 = st.columns(4)
            with e1:
                try:
                    export_df = filtered_df.drop(columns=['_sheet_row'], errors='ignore')
                    pdf_bytes = generate_pdf(export_df, sheet_choice, full=True)
                    st.download_button("📥 PDF (All)", data=pdf_bytes,
                        file_name=f"{sheet_choice}_{now_ist().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf", use_container_width=True, key="pdf_all_download")
                except Exception as e:
                    st.warning(f"PDF error: {e}")
            with e2:
                if selected_indices:
                    export_sel = filtered_df.iloc[selected_indices].drop(columns=['_sheet_row'], errors='ignore')
                else:
                    export_sel = filtered_df.drop(columns=['_sheet_row'], errors='ignore')
                csv_sel = export_sel.to_csv(index=False).encode('utf-8')
                st.download_button("📥 CSV (Selected)" if selected_indices else "📥 CSV (All)", data=csv_sel,
                    file_name=f"{sheet_choice}_{now_ist().strftime('%Y%m%d_%H%M')}_selected.csv",
                    mime="text/csv", use_container_width=True, key="csv_download")
            with e3:
                export_df = filtered_df.drop(columns=['_sheet_row'], errors='ignore')
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                    export_df.to_excel(writer, sheet_name=sheet_choice, index=False)
                excel_data = excel_buffer.getvalue()
                st.download_button("📥 Excel", data=excel_data,
                    file_name=f"{sheet_choice}_{now_ist().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True, key="excel_download")
            with e4:
                csv_full = filtered_df.drop(columns=['_sheet_row'], errors='ignore').to_csv(index=False).encode('utf-8')
                st.download_button("📋 Copy CSV", data=csv_full, file_name="table.csv",
                    mime="text/csv", use_container_width=True, key="copy_csv_download")
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="no-print">', unsafe_allow_html=True)
            with st.expander("🔧 Extra Features", expanded=False):
                feat1, feat2 = st.columns(2)
                with feat1:
                    st.markdown("**🎫 PNR Status Check**")
                    pnr_check = st.text_input("Enter PNR", max_chars=10, key="pnr_status_input")
                    if pnr_check and len(pnr_check) == 10:
                        pnr_url = get_pnr_status_url(pnr_check)
                        st.link_button("🔍 Check PNR Status", pnr_url, use_container_width=True)
                    st.markdown("**📊 Quick Stats**")
                    if not filtered_df.empty and pnr_col:
                        valid_pnrs = filtered_df[pnr_col].astype(str).str.match(r'\d{10}').sum()
                        st.caption(f"✅ Valid PNRs: {valid_pnrs}")
                    if not filtered_df.empty and doj_col is not None:
                        upcoming = sum(1 for _, r in filtered_df.iterrows() if not is_expired(r.get(doj_col, '')))
                        st.caption(f"📅 Upcoming DOJ: {upcoming}")
                with feat2:
                    st.markdown("**🚆 Train Analysis**")
                    if train_col_metric and not filtered_df.empty:
                        most_common = filtered_df[train_col_metric].mode()
                        if not most_common.empty:
                            st.caption(f"🔥 Most frequent train: {most_common.iloc[0]}")
                        if pnr_col:
                            dupes = filtered_df[pnr_col].value_counts()
                            dupes = dupes[dupes > 1]
                            if not dupes.empty:
                                st.warning(f"⚠️ {len(dupes)} duplicate PNR(s) found!")
                            else:
                                st.success("✅ No duplicate PNRs")
                    st.markdown("**⌨️ Shortcuts**")
                    st.caption("Ctrl+R: Refresh | Ctrl+P: Print | Auto-sync: ON")
            st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("""
    <div class='pro-footer no-print'>
        🚂 AI EQMS Hub Pro • Created by Sharique<br>
        © 2026 All Rights Reserved
    </div>
    """, unsafe_allow_html=True)

def chat_with_gemini(user_message, chat_history):
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')
        context = get_sheet_context()
        system_prompt = f"""You are TSKEQ Bot - a professional railway EQ assistant.
Sheet Context: {context}
Instructions: Answer questions based on sheet data. Be helpful, concise, professional."""
        for msg in chat_history[-10:]:
            if msg['role'] == 'user':
                system_prompt += f"User: {msg['content']}\n"
            else:
                system_prompt += f"Assistant: {msg['content']}\n"
        system_prompt += f"\nUser: {user_message}\nAssistant:"
        response = model.generate_content(system_prompt)
        return response.text
    except Exception as e:
        return f"⚠️ Error: {str(e)}"

def get_sheet_context():
    try:
        gc = init_sheets()
        eq_sheet = gc.open_by_key(SHEET_ID).worksheet("EQ")
        all_data = eq_sheet.get_all_values()
        total = max(0, len(all_data) - 4)
        summary = f"EQ Sheet has {total} records.\n"
        if total > 0:
            sample = all_data[-5:] if len(all_data) > 5 else all_data[4:]
            for row in sample:
                if len(row) > 7:
                    summary += f"PNR: {row[1] if len(row)>1 else ''}, Train: {row[5] if len(row)>5 else ''}, DOJ: {row[7] if len(row)>7 else ''}\n"
        return summary
    except:
        return "Sheet data temporarily unavailable."

if __name__ == "__main__":
    main()
