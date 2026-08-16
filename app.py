import streamlit as st
import pandas as pd
import time
import base64
import io
import requests
import json
import re
import math
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
import matplotlib.pyplot as plt

# ============================================
# CONFIG
# ============================================
from utils.config import GEMINI_API_KEY, GSPREAD_CREDENTIALS, SHEET_ID, DRIVE_FOLDER_ID
from utils.helpers import now_ist, format_time, format_date, format_datetime, log_activity, clean_pnr, parse_date, is_expired, col_index_to_letter, sanitize_latin
from utils.theme import apply_theme
from utils.sheets import SHEET_CONFIG, init_sheets, load_sheet_data_cached, save_to_sheet
from utils.ntes_client import NTES_AVAILABLE, get_pnr_status, get_live_train_status, get_train_schedule, format_pnr_result, format_live_train_result, format_schedule_result

st.set_page_config(page_title="AI EQMS Hub Pro", page_icon="🚂", layout="wide", initial_sidebar_state="expanded")

if not GEMINI_API_KEY or not GSPREAD_CREDENTIALS:
    st.error("❌ Missing credentials! Please check secrets.toml")
    st.stop()

# ============================================
# SESSION STATE
# ============================================
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
    'auto_theme_detected': False, 'sidebar_collapsed': False,
    'quick_filter_train': '', 'show_keyboard_help': False, 'print_trigger': False,
}

for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ============================================
# GEMINI PARSER
# ============================================
@st.cache_resource
def init_gemini():
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel('gemini-2.5-flash')

@st.cache_resource
def init_drive():
    creds_dict = dict(GSPREAD_CREDENTIALS)
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    scopes = ['https://www.googleapis.com/auth/drive.file']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes)
    return build('drive', 'v3', credentials=creds)

def upload_to_drive(file_bytes, filename, mime_type):
    try:
        drive_service = init_drive()
        file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=True)
        file = drive_service.files().create(
            body=file_metadata, media_body=media,
            fields='id,name,webViewLink,size'
        ).execute()
        file_id = file.get('id')
        return {
            'success': True, 'id': file_id, 'name': file.get('name'),
            'url': file.get('webViewLink'), 'size': file.get('size'),
            'view_url': f"https://drive.google.com/file/d/{file_id}/view",
            'print_url': f"https://drive.google.com/file/d/{file_id}/preview",
            'download_url': f"https://drive.google.com/uc?export=download&id={file_id}"
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

def gemini_universal_parser(input_data, input_type, mime_type, progress_callback=None):
    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}'
    system_prompt = """You are TSKEQ Bot's AI extraction engine. Extract PNR, T_N, CLASS, DOJ, FROM, TO, BOARDING, PASS_NAME, PASS_PH, T_BERTHS, PURPOSE, ADDRESS, DIARY_NO, RECOMMENDATION, DESIGNATION, VIP_STATUS, APPLICATION_DATE, RAILWAY_ZONE, PREFERENCE, PHONE_NUBER, WARRANT_NO. Return ONLY JSON array."""
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
            return {'error': 'No JSON found in response'}
        json_str = json_match.group(0)
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        records = json.loads(json_str)
        if isinstance(records, dict):
            records = [records]
        if progress_callback:
            progress_callback(90, "Processing records...")
        for rec in records:
            rec['PNR'] = clean_pnr(rec.get('PNR', ''))
            if rec.get('DOJ'):
                rec['DOJ'] = parse_date(rec['DOJ'])
        if progress_callback:
            progress_callback(100, "Complete!")
        return {'records': records, 'count': len(records)}
    except Exception as e:
        return {'error': f'Parser Error: {e}'}

def chat_with_gemini(user_message, chat_history):
    try:
        model = init_gemini()
        context = "EQ Sheet data available."
        system_prompt = f"""You are TSKEQ Bot - a professional railway EQ assistant.
Sheet Context: {context}
Previous conversation: """
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
    return "EQ Sheet available."

# ============================================
# EXPORT FUNCTIONS (INLINE)
# ============================================
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

# ============================================
# RENDER FUNCTIONS
# ============================================
def render_chat():
    st.subheader("💬 Chat with TSKEQ Bot")
    st.caption("Ask about EQ data, trains, quota, PNR or anything else.")
    
    if prompt := st.chat_input("Type your question...", key="chat_input"):
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
    
    st.markdown("**Quick questions**")
    sugg_cols = st.columns(3)
    for i, suggestion in enumerate(st.session_state.chat_suggestions):
        with sugg_cols[i % 3]:
            if st.button(suggestion, key=f"sugg_{i}", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": suggestion})
                with st.spinner("Thinking..."):
                    response = chat_with_gemini(suggestion, st.session_state.messages)
                    st.session_state.messages.append({"role": "assistant", "content": response})
                st.rerun()
    
    if st.button("🗑️ Clear Chat", use_container_width=True, key="clear_chat_btn"):
        st.session_state.messages = []
        st.rerun()

def render_dashboard(filtered_df):
    st.subheader("📊 Analytics Dashboard")
    
    train_col = None
    for c in filtered_df.columns:
        if 'T/N' in c.upper() or 'T_N' in c.upper() or 'TRAIN' in c.upper():
            train_col = c
            break
    
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        total_records = len(filtered_df) if not filtered_df.empty else 0
        st.metric("Total Records", total_records)
    with m2:
        unique_trains = filtered_df[train_col].nunique() if train_col else 0
        st.metric("Unique Trains", unique_trains)
    with m3:
        berth_col = next((c for c in filtered_df.columns if 'BERTH' in str(c).upper() or 'T/BERTHS' in str(c).upper()), None)
        total_berths = 0
        if berth_col and berth_col in filtered_df:
            total_berths = pd.to_numeric(filtered_df[berth_col], errors='coerce').sum()
        st.metric("Total Berths", int(total_berths) if total_berths else 0)
    with m4:
        expired = 0
        doj_col = next((c for c in filtered_df.columns if 'DOJ' in str(c).upper()), None)
        if doj_col and doj_col in filtered_df:
            expired = sum(1 for _, r in filtered_df.iterrows() if is_expired(r.get(doj_col, '')))
        st.metric("Expired DOJ", expired)
    
    st.markdown("---")
    if not filtered_df.empty and train_col:
        train_counts = filtered_df[train_col].value_counts().reset_index()
        train_counts.columns = ['Train', 'Count']
        fig_bar = px.bar(train_counts.head(15), x='Train', y='Count', title="Top 15 Trains by EQ Count", color='Count', color_continuous_scale='Blues')
        fig_bar.update_layout(height=400, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("No data for charts.")

def render_railway():
    st.subheader("🚂 Indian Railways - Real‑time Info")
    if not NTES_AVAILABLE:
        st.error("❌ 'ntes-client' library not installed. Please run: `pip install ntes-client`")
        return

    tab1, tab2, tab3 = st.tabs(["🔍 PNR Status", "🚂 Live Train", "📋 Train Schedule"])

    with tab1:
        st.markdown("### PNR Status Check")
        pnr_input = st.text_input("Enter 10-digit PNR", max_chars=10, key="rail_pnr")
        if st.button("Check PNR", key="pnr_check", use_container_width=True):
            if not pnr_input or len(pnr_input) != 10 or not pnr_input.isdigit():
                st.error("Please enter a valid 10-digit PNR.")
            else:
                with st.spinner("Fetching PNR details..."):
                    data = get_pnr_status(pnr_input)
                    if data and isinstance(data, dict) and data.get('error'):
                        st.error(f"❌ {data['error']}")
                    elif data:
                        st.markdown(format_pnr_result(data))
                    else:
                        st.error("❌ PNR not found or flushed.")

    with tab2:
        st.markdown("### Live Train Status")
        train_no = st.text_input("Enter Train Number (3-5 digits)", key="rail_train")
        from utils.helpers import get_date_label, get_date_for_offset
        date_options = [f"{get_date_label(i)} ({get_date_for_offset(i)})" for i in range(5)]
        date_choice = st.selectbox("Select Date", date_options, index=0, key="rail_date")
        offset = 0
        for i in range(5):
            if get_date_label(i) in date_choice:
                offset = i
                break
        if st.button("Get Live Status", key="train_live", use_container_width=True):
            if not train_no or not train_no.isdigit() or not (3 <= len(train_no) <= 5):
                st.error("Please enter a valid train number (3-5 digits).")
            else:
                with st.spinner("Fetching live status..."):
                    date_str = get_date_for_offset(offset)
                    data = get_live_train_status(train_no, date_str)
                    if data and isinstance(data, dict) and data.get('error'):
                        st.error(f"❌ {data['error']}")
                    elif data:
                        st.markdown(format_live_train_result(data))
                    else:
                        st.error("❌ No data available.")

    with tab3:
        st.markdown("### Train Schedule / Route")
        train_no_sch = st.text_input("Enter Train Number (3-5 digits)", key="rail_sch")
        if 'sch_start' not in st.session_state:
            st.session_state.sch_start = 0
        if st.button("Get Schedule", key="train_sch", use_container_width=True):
            if not train_no_sch or not train_no_sch.isdigit() or not (3 <= len(train_no_sch) <= 5):
                st.error("Please enter a valid train number.")
            else:
                with st.spinner("Fetching schedule..."):
                    data = get_train_schedule(train_no_sch)
                    if data and isinstance(data, dict) and data.get('error'):
                        st.error(f"❌ {data['error']}")
                    elif data:
                        st.session_state.sch_data = data
                        st.session_state.sch_start = 0
                        st.rerun()
                    else:
                        st.error("❌ Schedule not found.")
        if 'sch_data' in st.session_state:
            data = st.session_state.sch_data
            total = len(data.get('stations', []))
            chunk = 20
            start = st.session_state.sch_start
            end = min(start + chunk, total)
            if start >= total:
                start = max(0, total - chunk)
                end = total
                st.session_state.sch_start = start
            msg, _ = format_schedule_result(data, start, chunk)
            st.markdown(msg)
            col1, col2, col3 = st.columns([1,2,1])
            with col1:
                if start > 0:
                    if st.button("◀ Previous", key="sch_prev"):
                        st.session_state.sch_start = max(0, start - chunk)
                        st.rerun()
            with col2:
                st.write(f"Showing {start+1}-{end} of {total}")
            with col3:
                if end < total:
                    if st.button("Next ▶", key="sch_next"):
                        st.session_state.sch_start = end
                        st.rerun()

def render_data_table(filtered_df, sheet_choice):
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
        cards_html += f'<div class="train-total-card"><div class="train-total-number">Total EQ: {total_eq}</div></div>'
        for train_num, cnt in train_counts_series.items():
            cards_html += f'<div class="train-count-card"><div class="train-count-number">{train_num}</div><div class="train-count-badge">{cnt}</div></div>'
        cards_html += '</div>'
        st.markdown(cards_html, unsafe_allow_html=True)
        st.markdown("---")

    if filtered_df.empty:
        st.info("No data to show.")
        return

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

    # Print table
    print_cols = [c for c in display_df.columns if c != 'Select']
    print_df = display_df[print_cols].copy()
    if not print_df.empty:
        html_table = print_df.to_html(index=False, border=1, classes='print-table')
    else:
        html_table = "<p>No data</p>"
    st.markdown(f"""
    <div class="print-only">
        <h3 style="text-align:center;">{sheet_choice} Data</h3>
        {html_table}
        <p style="text-align:center; font-size:10pt;">Generated: {format_datetime()} IST</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="print-area">', unsafe_allow_html=True)
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
        st.components.v1.html("""
        <div style="width:100%;">
            <button onclick="window.print();" style="
                background: linear-gradient(135deg, #7c3aed, #6d28d9);
                color: white; border: none; border-radius: 8px;
                padding: 9px 16px; width: 100%; font-weight: 600;
                cursor: pointer; font-size: 1rem;
            ">🖨️ PRINT Sheet</button>
        </div>
        """, height=50)
    st.markdown('</div>', unsafe_allow_html=True)

    # WhatsApp Image Share
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
                copy_js = f"""
                <div style="width:100%;">
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
                </div>
                """
                st.components.v1.html(copy_js, height=50)
    st.markdown('</div>', unsafe_allow_html=True)

    # Export
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

# ============================================
# MAIN FUNCTION
# ============================================
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

    # Sidebar
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center; margin-bottom:10px; font-size:1.3rem; line-height:1.8;">
            <span style="color:#FF9933;">🟠 नमस्ते आपका स्वागत है</span><br>
            <span style="color:#FFFFFF;">⚪ हम भारत के लोग</span><br>
            <span style="color:#138808; font-weight:bold;">🟢 जय हिंद</span>
        </div>
        """, unsafe_allow_html=True)
        st.caption(f"📅 {format_date()}  •  🕐 {format_time()} IST")

        # Sync & Status
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
        st.markdown(f'<a href="{sheet_link}" target="_blank" class="sheet-link-btn">📊 Open Google Sheet</a>', unsafe_allow_html=True)

        # ============================================
        # UPLOAD & PROCESS SECTION
        # ============================================
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
                            ftype = "pdf" if uploaded.type == "application/pdf" else "audio" if uploaded.type.startswith("audio") else "image"
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
                                save_res = save_to_sheet(eq_sheet, res['records'])
                                if "error" in save_res:
                                    st.error(f"❌ Save error: {save_res['error']}")
                                else:
                                    st.success(f"✅ Saved {save_res['saved']} new • {save_res['skipped']} skipped")
                                    if uploaded or audio_data:
                                        drive_res = upload_to_drive(fbytes, fname, mime)
                                        if drive_res['success']:
                                            st.success(f"📁 Drive: {drive_res['name']}")
                                            st.session_state.last_uploaded_file = fname
                                            st.session_state.last_uploaded_drive_url = drive_res.get('url')
                                            st.session_state.last_uploaded_view_url = drive_res.get('view_url')
                                            st.session_state.last_uploaded_print_url = drive_res.get('print_url')
                                            st.session_state.upload_success = True
                                            st.session_state.last_upload_time = format_time()
                                            log_activity(f"✅ {fname} → {save_res['saved']} records")
                                        else:
                                            st.error(f"❌ Drive: {drive_res['error']}")
                                    else:
                                        st.session_state.upload_success = True
                                        st.session_state.last_upload_time = format_time()
                                        log_activity(f"✅ Text input → {save_res['saved']} records")
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

        # Last Uploaded File
        if st.session_state.upload_success and st.session_state.last_uploaded_file:
            with st.expander("📄 Last Uploaded File", expanded=True):
                st.markdown(f"""
                <div class="file-card">
                    <div class="file-card-title">📄 {st.session_state.last_uploaded_file}</div>
                    <div class="file-card-meta">Uploaded at {st.session_state.get('last_upload_time', '—')} IST</div>
                </div>
                """, unsafe_allow_html=True)
                c1, c2 = st.columns(2)
                with c1:
                    if st.session_state.last_uploaded_view_url:
                        st.link_button("👁️ View", st.session_state.last_uploaded_view_url, use_container_width=True)
                with c2:
                    if st.session_state.last_uploaded_print_url:
                        st.link_button("🖨️ Print File (Drive)", st.session_state.last_uploaded_print_url, use_container_width=True)
                if st.button("🗑️ Clear History", use_container_width=True, key="clear_history_btn"):
                    st.session_state.last_uploaded_file = None
                    st.session_state.last_uploaded_drive_url = None
                    st.session_state.last_uploaded_view_url = None
                    st.session_state.last_uploaded_print_url = None
                    st.session_state.upload_success = False
                    st.rerun()

        # Activity Log
        with st.expander("📋 Activity Log", expanded=True):
            if st.session_state.activity_log:
                for log in reversed(st.session_state.activity_log[-20:]):
                    st.caption(f"{log.get('timestamp', '')} — {log.get('action', '')}")
            else:
                st.caption("No activity yet")
        st.markdown("---")

        # Sheet & Filters
        with st.expander("📑 Sheet & Filters", expanded=True):
            sheet_choice = st.selectbox("Select Sheet", list(SHEET_CONFIG.keys()),
                index=list(SHEET_CONFIG.keys()).index(st.session_state.selected_sheet)
                if st.session_state.selected_sheet in SHEET_CONFIG else 0,
                key="sheet_select")
            st.session_state.selected_sheet = sheet_choice
            config = SHEET_CONFIG[sheet_choice]

            pnr_input = st.text_input("PNR (partial)", value=st.session_state.pnr_val, key="pnr_filter_input")
            if pnr_input != st.session_state.pnr_val:
                st.session_state.pnr_val = pnr_input
                st.session_state.current_page = 1
                st.rerun()

            train_input = st.text_input("Train (partial)", value=st.session_state.train_val, key="train_filter_input")
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

        view = st.radio("View Mode", ["📋 Data Table", "📊 Dashboard", "💬 Chat", "🚂 Railway"],
            index=["📋 Data Table", "📊 Dashboard", "💬 Chat", "🚂 Railway"].index(st.session_state.view_mode)
            if st.session_state.view_mode in ["📋 Data Table", "📊 Dashboard", "💬 Chat", "🚂 Railway"] else 0,
            key="view_mode_radio")
        if view != st.session_state.view_mode:
            st.session_state.view_mode = view
            st.rerun()

    # Top bar
    top_c1, top_c2 = st.columns([4, 1])
    with top_c1:
        st.markdown("<h1 style='font-size:22px; font-weight:700; margin:0;'>🚂 AI EQMS Hub Pro</h1>", unsafe_allow_html=True)
    with top_c2:
        st.markdown(f"<div style='padding-top:6px; text-align:right;'><span class='status-pill status-live'>● Live</span> &nbsp; <span style='font-size:13px;'>Sync {format_time(datetime.fromtimestamp(st.session_state.last_refresh, tz=IST))} IST</span></div>", unsafe_allow_html=True)

    st.caption(f"Enterprise Railway EQ Management  •  {format_date()}  •  {format_time()} IST")
    st.markdown("---")

    # View routing
    if view == "💬 Chat":
        render_chat()
    elif view == "📊 Dashboard":
        render_dashboard(filtered_df)
    elif view == "🚂 Railway":
        render_railway()
    else:
        render_data_table(filtered_df, sheet_choice)

    # Footer
    st.markdown("""
    <div class='pro-footer no-print'>
        🚂 AI EQMS Hub Pro • Created by Sharique<br>
        © 2026 All Rights Reserved
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
