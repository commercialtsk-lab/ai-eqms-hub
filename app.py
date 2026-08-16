import streamlit as st
import time
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

from utils.config import GEMINI_API_KEY, GSPREAD_CREDENTIALS, SHEET_ID
from utils.helpers import now_ist, format_time, format_date, log_activity
from utils.theme import apply_theme
from utils.sheets import SHEET_CONFIG, load_sheet_data_cached
from utils.ntes_client import NTES_AVAILABLE
from utils.weather import render_weather_widget

st.set_page_config(page_title="AI EQMS Hub Pro", page_icon="🚂", layout="wide", initial_sidebar_state="expanded")

if not GEMINI_API_KEY or not GSPREAD_CREDENTIALS:
    st.error("❌ Missing credentials! Please check secrets.toml")
    st.stop()

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

def main():
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
        <div style="text-align:center; margin-bottom:10px; font-size:1.3rem; line-height:1.8;">
            <span style="color:#FF9933;">🟠 नमस्ते आपका स्वागत है</span><br>
            <span style="color:#FFFFFF;">⚪ हम भारत के लोग</span><br>
            <span style="color:#138808; font-weight:bold;">🟢 जय हिंद</span>
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
        st.markdown(f'<a href="{sheet_link}" target="_blank" class="sheet-link-btn">📊 Open Google Sheet</a>', unsafe_allow_html=True)

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

        render_weather_widget()

    top_c1, top_c2 = st.columns([4, 1])
    with top_c1:
        st.markdown("<h1 style='font-size:22px; font-weight:700; margin:0;'>🚂 AI EQMS Hub Pro</h1>", unsafe_allow_html=True)
    with top_c2:
        st.markdown(f"<div style='padding-top:6px; text-align:right;'><span class='status-pill status-live'>● Live</span> &nbsp; <span style='font-size:13px;'>Sync {format_time(datetime.fromtimestamp(st.session_state.last_refresh, tz=IST))} IST</span></div>", unsafe_allow_html=True)

    st.caption(f"Enterprise Railway EQ Management  •  {format_date()}  •  {format_time()} IST")
    st.markdown("---")

    if view == "💬 Chat":
        from pages.chat import render_chat
        render_chat()
    elif view == "📊 Dashboard":
        from pages.dashboard import render_dashboard
        render_dashboard(filtered_df)
    elif view == "🚂 Railway":
        from pages.railway import render_railway
        render_railway()
    else:
        from pages.data_table import render_data_table
        render_data_table(filtered_df, sheet_choice)

    st.markdown("""
    <div class='pro-footer no-print'>
        🚂 AI EQMS Hub Pro • Created by Sharique<br>
        © 2026 All Rights Reserved
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
