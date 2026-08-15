import streamlit as st
import pandas as pd
import json
import re
import base64
import io
import time
import requests
import urllib.parse
from datetime import datetime
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from fpdf import FPDF
import plotly.express as px
import pytz

# ==================== CONFIG ====================
st.set_page_config(
    page_title="AI EQMS Hub Pro",
    page_icon="🚂",
    layout="wide",
    initial_sidebar_state="expanded"
)

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
GSPREAD_CREDENTIALS = st.secrets.get("GSPREAD_CREDENTIALS")

if not GEMINI_API_KEY or not GSPREAD_CREDENTIALS:
    st.error("❌ Missing credentials in secrets.toml")
    st.stop()

SHEET_ID = "1QcS3ZF3YYxSEykG0KiOUuXbTdBh0DMHdMgoqa9t8yrI"
DRIVE_FOLDER_ID = "1H1gf8WqfoTYFT_pU9WfIDLrHg-NpuUSI"
IST = pytz.timezone("Asia/Kolkata")

def now_ist():
    return datetime.now(IST)

# ==================== SESSION STATE ====================
defaults = {
    "messages": [],
    "last_uploaded_file": None,
    "last_uploaded_view_url": None,
    "last_uploaded_print_url": None,
    "last_refresh": time.time(),
    "dark_mode": True,
    "current_page": 1,
    "pnr_val": "",
    "train_val": "",
    "from_val": None,
    "to_val": None,
    "upload_success": False,
    "last_upload_time": None,
    "pending_suggestion": None,
    "current_view": "💬 Chat",
    "selected_sheet": "EQ",
    "page_size": 25,
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ==================== HELPERS ====================
def clean_pnr(pnr):
    if not pnr: return ""
    digits = re.sub(r"\D", "", str(pnr))
    return digits[-10:] if len(digits) >= 10 else digits

def clean_phone(phone):
    if not phone: return ""
    digits = re.sub(r"\D", "", str(phone))
    return digits[-10:] if len(digits) >= 10 else ""

def parse_date(date_str):
    if not date_str: return ""
    if isinstance(date_str, datetime):
        return date_str.strftime("%d-%m-%Y")
    m = re.search(r"(\d{1,2})[\/\.\-](\d{1,2})[\/\.\-](\d{2,4})", str(date_str))
    if m:
        d, mo, y = m.groups()
        d, mo = d.zfill(2), mo.zfill(2)
        if len(y) == 2: y = "20" + y
        if int(mo) > 12 and int(d) <= 12:
            d, mo = mo, d
        return f"{d}-{mo}-{y}"
    return str(date_str)

def col_index_to_letter(idx):
    res = ""
    while idx > 0:
        idx, r = divmod(idx - 1, 26)
        res = chr(65 + r) + res
    return res

def is_flag_time():
    now = now_ist()
    m = now.month
    if m in [5,6,7]: sh, sm = 18, 45
    elif m in [11,12,1]: sh, sm = 17, 15
    elif m in [2,3,10]: sh, sm = 18, 0
    else: sh, sm = 18, 30
    start = now.replace(hour=6, minute=0, second=0, microsecond=0)
    end = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    return start <= now <= end

# ==================== SERVICES ====================
@st.cache_resource
def init_gemini():
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel("gemini-2.5-flash")

@st.cache_resource
def init_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(GSPREAD_CREDENTIALS, scope)
    return gspread.authorize(creds)

@st.cache_resource
def init_drive():
    creds_dict = dict(GSPREAD_CREDENTIALS)
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://www.googleapis.com/auth/drive.file"])
    return build("drive", "v3", credentials=creds)

SHEET_CONFIG = {
    "EQ": {"start_row": 5, "pnr_col": 1, "train_col": 5, "doj_col": 7},
    "DATA": {"start_row": 3, "pnr_col": 1, "train_col": 5, "doj_col": 7},
    "FINAL": {"start_row": 6, "pnr_col": 7, "train_col": 1, "doj_col": 12},
    "DATA2": {"start_row": 4, "pnr_col": 7, "train_col": 1, "doj_col": 12},
    "EMAIL_DATA": {"start_row": 2, "pnr_col": 7, "train_col": 8, "doj_col": 11},
    "NOTE": {"start_row": 2, "pnr_col": None, "train_col": 0, "doj_col": None},
}

@st.cache_data(ttl=20)
def load_sheet_data(sheet_name):
    try:
        gc = init_sheets()
        ws = gc.open_by_key(SHEET_ID).worksheet(sheet_name)
        data = ws.get_all_values()
        cfg = SHEET_CONFIG.get(sheet_name, {"start_row": 1})
        start = cfg["start_row"]
        if len(data) < start:
            return pd.DataFrame()
        headers = data[start-2] if start > 1 else data[0]
        rows = data[start-1:]
        seen = {}
        unique = []
        for h in headers:
            h = str(h).strip() or "Unnamed"
            if h in seen:
                seen[h] += 1
                unique.append(f"{h}_{seen[h]}")
            else:
                seen[h] = 0
                unique.append(h)
        return pd.DataFrame(rows, columns=unique[:len(rows[0])] if rows else unique)
    except Exception as e:
        st.error(f"Load error: {e}")
        return pd.DataFrame()

# ==================== GEMINI ====================
def gemini_extract(data, dtype, mime=None, progress=None):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = """You are expert railway form extractor. Extract:
PNR, T_N, CLASS, DOJ (DD-MM-YYYY), FROM, TO, BOARDING, PASS_NAME, PASS_PH, T_BERTHS, PURPOSE, ADDRESS, DIARY_NO, RECOMMENDATION, DESIGNATION, VIP_STATUS, APPLICATION_DATE, RAILWAY_ZONE, PREFERENCE, PHONE_NUBER, WARRANT_NO
Return ONLY valid JSON array. No extra text."""
    parts = []
    if dtype in ["image", "pdf", "audio"]:
        parts.append({"inline_data": {"mime_type": mime, "data": data}})
        parts.append({"text": prompt})
    else:
        parts.append({"text": prompt + "\n\n" + str(data)})

    if progress: progress(25, "Sending to Gemini...")
    try:
        res = requests.post(url, json={
            "contents": [{"parts": parts}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192}
        }, timeout=90)
        if res.status_code != 200:
            return {"error": f"API {res.status_code}"}
        text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
        if progress: progress(70, "Parsing...")
        m = re.search(r"\[\s*\{[\s\S]*?\}\s*\]", text)
        if not m:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if m: json_str = m.group(1)
            else: return {"error": "No JSON found"}
        else:
            json_str = m.group(0)
        json_str = re.sub(r",\s*}", "}", json_str)
        json_str = re.sub(r",\s*]", "]", json_str)
        records = json.loads(json_str)
        if isinstance(records, dict): records = [records]
        cleaned, seen = [], set()
        for r in records:
            pnr = clean_pnr(r.get("PNR", ""))
            if not pnr or pnr in seen: continue
            seen.add(pnr)
            r["PNR"] = pnr
            if r.get("PASS_PH"): r["PASS_PH"] = clean_phone(r["PASS_PH"])
            if r.get("DOJ"): r["DOJ"] = parse_date(r["DOJ"])
            r.setdefault("PREFERENCE", "General")
            r.setdefault("T_BERTHS", 1)
            cleaned.append(r)
        if progress: progress(100, "Done")
        return {"records": cleaned, "count": len(cleaned)} if cleaned else {"error": "No valid PNR"}
    except Exception as e:
        return {"error": str(e)}

def upload_drive(file_bytes, name, mime):
    try:
        svc = init_drive()
        meta = {"name": name, "parents": [DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime, resumable=True)
        f = svc.files().create(body=meta, media_body=media, fields="id,name").execute()
        fid = f["id"]
        return {
            "success": True,
            "view_url": f"https://drive.google.com/file/d/{fid}/view",
            "print_url": f"https://drive.google.com/file/d/{fid}/preview",
            "name": f["name"]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def save_records(records):
    try:
        gc = init_sheets()
        ws = gc.open_by_key(SHEET_ID).worksheet("EQ")
        all_data = ws.get_all_values()
        existing = [clean_pnr(r[1]) for r in all_data[4:] if len(r) > 1]
        saved = skipped = 0
        sn = len(all_data) - 3
        for r in records:
            pnr = clean_pnr(r.get("PNR", ""))
            if not pnr or pnr in existing:
                skipped += 1
                continue
            row = [
                sn, pnr, r.get("FROM",""), r.get("TO",""), r.get("BOARDING",""),
                r.get("T_N",""), r.get("CLASS",""), r.get("DOJ",""), r.get("PASS_NAME",""),
                r.get("PASS_PH",""), r.get("T_BERTHS",1), r.get("PURPOSE",""), r.get("ADDRESS",""),
                r.get("DIARY_NO",""), r.get("RECOMMENDATION",""), r.get("DESIGNATION",""),
                r.get("PHONE_NUBER",""), r.get("VIP_STATUS",""), r.get("WARRANT_NO",""),
                now_ist().strftime("%d-%m-%Y %H:%M:%S"), r.get("APPLICATION_DATE",""),
                r.get("RAILWAY_ZONE",""), r.get("PREFERENCE","General")
            ]
            ws.append_row(row)
            existing.append(pnr)
            sn += 1
            saved += 1
            time.sleep(0.1)
        return {"saved": saved, "skipped": skipped}
    except Exception as e:
        return {"error": str(e)}

def chat_gemini(msg, history):
    try:
        model = init_gemini()
        prompt = "You are TSKEQ Bot - smart railway EQ assistant. Be helpful and concise.\n\n"
        for m in history[-6:]:
            prompt += f"{m['role'].title()}: {m['content']}\n"
        prompt += f"User: {msg}\nAssistant:"
        return model.generate_content(prompt).text
    except Exception as e:
        return f"Error: {e}"

# ========== FIXED PDF FUNCTION ==========
def make_pdf(df, title):
    """Generate PDF with proper handling - FIXED bytearray issue"""
    pdf = FPDF(orientation="L", format="A4")
    pdf.add_page()
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, f"AI EQMS Hub Pro - {title}", ln=True, align="C")
    pdf.set_font("Arial", "", 8)
    pdf.cell(0, 6, f"Generated: {now_ist().strftime('%d-%m-%Y %H:%M IST')} | Rows: {len(df)}", ln=True, align="C")
    pdf.ln(3)
    
    # Get all columns
    cols = list(df.columns)
    if len(cols) > 12:
        cols = cols[:12]
    
    # Calculate column width
    col_width = min(25, 277 / max(len(cols), 1))
    
    # Headers
    pdf.set_font("Arial", "B", 7)
    for c in cols:
        safe_c = str(c)[:15].encode('latin-1', 'ignore').decode('latin-1')
        pdf.cell(col_width, 6, safe_c, border=1)
    pdf.ln()
    
    # Data rows
    pdf.set_font("Arial", "", 6)
    for _, row in df.iterrows():
        for c in cols:
            val = str(row.get(c, ""))[:20]
            safe_val = val.encode('latin-1', 'ignore').decode('latin-1')
            pdf.cell(col_width, 5, safe_val, border=1)
        pdf.ln()
        if pdf.get_y() > 185:
            pdf.add_page()
            pdf.set_font("Arial", "B", 7)
            for c in cols:
                safe_c = str(c)[:15].encode('latin-1', 'ignore').decode('latin-1')
                pdf.cell(col_width, 6, safe_c, border=1)
            pdf.ln()
            pdf.set_font("Arial", "", 6)
    
    # FIX: Properly convert output to bytes
    output = pdf.output(dest='S')
    if isinstance(output, bytearray):
        return bytes(output)
    elif isinstance(output, str):
        return output.encode('latin-1')
    else:
        return output

# ========== THEME (Better Contrast) ==========
def apply_theme(dark):
    if dark:
        bg = "#0b0b0f"
        card = "#16161d"
        text = "#f0f0f5"
        secondary = "#b0b0c0"
        border = "#2e2e3a"
        accent = "#a78bfa"
        input_bg = "#1c1c26"
        button_hover = "#8b5cf6"
    else:
        bg = "#f8f9fc"
        card = "#ffffff"
        text = "#1a1a2e"
        secondary = "#4a4a68"
        border = "#e0e0ea"
        accent = "#7c3aed"
        input_bg = "#ffffff"
        button_hover = "#6d28d9"

    st.markdown(f"""
    <style>
        .stApp {{ background-color: {bg} !important; }}
        [data-testid="stSidebar"] {{
            background-color: {card} !important;
            border-right: 1px solid {border} !important;
        }}
        h1, h2, h3, h4, h5, h6, p, div, span, label, .stMarkdown, .stCaption {{
            color: {text} !important;
        }}
        .stTextInput input, .stTextArea textarea, .stSelectbox > div > div, .stDateInput input {{
            background-color: {input_bg} !important;
            color: {text} !important;
            border: 1px solid {border} !important;
            border-radius: 10px !important;
        }}
        .stButton > button {{
            background-color: transparent !important;
            color: {accent} !important;
            border: 1px solid {border} !important;
            border-radius: 10px !important;
            font-weight: 500 !important;
        }}
        .stButton > button:hover {{
            background-color: {button_hover} !important;
            color: white !important;
            border-color: {button_hover} !important;
        }}
        .stChatMessage {{
            background-color: {card} !important;
            border: 1px solid {border} !important;
            border-radius: 12px !important;
        }}
        [data-testid="stDataEditor"], .stDataFrame {{
            background-color: {card} !important;
            border-radius: 10px !important;
        }}
        .block-container {{
            padding-top: 1.1rem !important;
            padding-bottom: 1.5rem !important;
        }}
        .pro-footer {{
            text-align: center;
            color: {secondary} !important;
            font-size: 0.82rem;
            margin-top: 35px;
            padding: 14px 0 6px;
            border-top: 1px solid {border};
        }}
        .stRadio > label, .stCheckbox > label {{
            color: {text} !important;
        }}
        .print-area {{
            background: white !important;
            color: black !important;
        }}
        @media print {{
            .stApp {{ display: none !important; }}
            .print-area {{ display: block !important; }}
        }}
    </style>
    """, unsafe_allow_html=True)

# ==================== MAIN ====================
def main():
    # Theme
    dark = st.sidebar.toggle("🌙 Dark Mode", value=st.session_state.dark_mode)
    if dark != st.session_state.dark_mode:
        st.session_state.dark_mode = dark
        st.rerun()
    apply_theme(dark)

    with st.sidebar:
        now = now_ist()
        if is_flag_time():
            st.markdown("""
            <div style="text-align:center;margin-bottom:12px;">
                <div style="font-size:24px;">🇮🇳</div>
                <div style="color:#FF9933;font-weight:700;">नमस्ते, आपका स्वागत है</div>
                <div style="color:#ffffff;font-weight:600;">हम भारत के लोग</div>
                <div style="color:#138808;font-weight:700;">जय हिंद</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            h = now.hour
            greet = "☀️ Good Morning" if 5<=h<12 else "🌤️ Good Afternoon" if 12<=h<17 else "🌆 Good Evening" if 17<=h<21 else "🌙 Good Night"
            st.markdown(f"**{greet}**")

        st.caption(f"{now.strftime('%d-%m-%Y')}  •  {now.strftime('%H:%M')} IST")

        if st.checkbox("🔄 Auto Sync (20s)", value=True):
            if time.time() - st.session_state.last_refresh > 20:
                st.session_state.last_refresh = time.time()
                st.cache_data.clear()
                st.rerun()

        st.markdown("---")
        st.markdown(f'<a href="https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit" target="_blank" style="display:block;text-align:center;padding:9px;border:1px solid #444;border-radius:10px;text-decoration:none;color:#a78bfa;font-weight:500;">📊 Open Google Sheet</a>', unsafe_allow_html=True)
        st.markdown("---")

        # Upload
        st.subheader("📤 Smart Upload")
        mode = st.radio("Type", ["📷 Image / PDF", "📝 Text", "🎤 Voice / Audio"], horizontal=True, label_visibility="collapsed")

        uploaded = None
        text_data = ""
        audio_data = None

        if mode == "📷 Image / PDF":
            uploaded = st.file_uploader("Image or PDF", type=["png","jpg","jpeg","pdf"], label_visibility="collapsed")
        elif mode == "📝 Text":
            text_data = st.text_area("Paste text", height=120, placeholder="Messy text yahan paste karein...", label_visibility="collapsed")
        else:
            st.caption("Mic se record karein")
            audio_data = st.audio_input("Record", label_visibility="collapsed")
            uploaded = st.file_uploader("Ya file upload", type=["mp3","wav","ogg","m4a"], label_visibility="collapsed")

        if st.button("🚀 Process & Save", type="primary", use_container_width=True):
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
                        res = gemini_extract(text_data, "text", progress=upd)
                        fname = f"text_{now_ist().strftime('%H%M%S')}.txt"
                        fbytes = text_data.encode()
                        mime = "text/plain"
                    elif audio_data:
                        fbytes = audio_data.getvalue()
                        b64 = base64.b64encode(fbytes).decode()
                        res = gemini_extract(b64, "audio", "audio/wav", upd)
                        fname = f"voice_{now_ist().strftime('%H%M%S')}.wav"
                        mime = "audio/wav"
                    else:
                        fbytes = uploaded.read()
                        b64 = base64.b64encode(fbytes).decode()
                        ftype = "pdf" if uploaded.type == "application/pdf" else "audio" if uploaded.type.startswith("audio") else "image"
                        res = gemini_extract(b64, ftype, uploaded.type, upd)
                        fname = uploaded.name
                        mime = uploaded.type

                    if "error" in res:
                        st.error(res["error"])
                    else:
                        st.success(f"✅ {res['count']} records")
                        with st.expander("Preview"):
                            st.dataframe(pd.DataFrame(res["records"]))
                        save_res = save_records(res["records"])
                        if "error" in save_res:
                            st.error(save_res["error"])
                        else:
                            st.success(f"Saved {save_res['saved']} new, {save_res['skipped']} skipped")
                            drive = upload_drive(fbytes, fname, mime)
                            if drive["success"]:
                                st.session_state.last_uploaded_file = fname
                                st.session_state.last_uploaded_view_url = drive["view_url"]
                                st.session_state.last_uploaded_print_url = drive["print_url"]
                                st.session_state.upload_success = True
                                st.session_state.last_upload_time = now_ist().strftime("%H:%M")
                                st.cache_data.clear()
                                st.session_state.last_refresh = time.time()
                                time.sleep(0.5)
                                st.rerun()
                except Exception as e:
                    st.error(str(e))
                finally:
                    prog.empty()
                    status.empty()

        if st.session_state.upload_success and st.session_state.last_uploaded_file:
            st.markdown("---")
            st.markdown(f"**📄 {st.session_state.last_uploaded_file}**")
            c1, c2 = st.columns(2)
            c1.link_button("👁️ View", st.session_state.last_uploaded_view_url, use_container_width=True)
            c2.link_button("🖨️ Print File", st.session_state.last_uploaded_print_url, use_container_width=True)
            if st.button("Clear Upload", use_container_width=True):
                st.session_state.upload_success = False
                st.rerun()

        st.markdown("---")
        st.subheader("🔍 Filters")
        pnr = st.text_input("PNR", value=st.session_state.pnr_val, key="f_pnr")
        train = st.text_input("Train", value=st.session_state.train_val, key="f_train")
        c1, c2 = st.columns(2)
        with c1:
            fr = st.date_input("From", value=st.session_state.from_val, format="DD-MM-YYYY", key="f_from")
        with c2:
            to = st.date_input("To", value=st.session_state.to_val, format="DD-MM-YYYY", key="f_to")

        if (pnr != st.session_state.pnr_val or train != st.session_state.train_val or
            fr != st.session_state.from_val or to != st.session_state.to_val):
            st.session_state.pnr_val = pnr
            st.session_state.train_val = train
            st.session_state.from_val = fr
            st.session_state.to_val = to
            st.session_state.current_page = 1
            st.rerun()

        if st.button("Clear Filters", use_container_width=True):
            st.session_state.pnr_val = ""
            st.session_state.train_val = ""
            st.session_state.from_val = None
            st.session_state.to_val = None
            st.session_state.current_page = 1
            st.rerun()

        sheet = st.selectbox("Sheet", list(SHEET_CONFIG.keys()), index=list(SHEET_CONFIG.keys()).index(st.session_state.selected_sheet))
        st.session_state.selected_sheet = sheet

        # View selector (single click friendly)
        st.markdown("**View**")
        v1, v2, v3 = st.columns(3)
        if v1.button("💬 Chat", use_container_width=True, type="primary" if st.session_state.current_view == "💬 Chat" else "secondary"):
            st.session_state.current_view = "💬 Chat"
            st.rerun()
        if v2.button("📋 Data", use_container_width=True, type="primary" if st.session_state.current_view == "📋 Data Table" else "secondary"):
            st.session_state.current_view = "📋 Data Table"
            st.rerun()
        if v3.button("📊 Dash", use_container_width=True, type="primary" if st.session_state.current_view == "📊 Dashboard" else "secondary"):
            st.session_state.current_view = "📊 Dashboard"
            st.rerun()

    # ---------- MAIN ----------
    st.markdown("<h1 style='font-size:1.5rem;margin-bottom:2px;'>🚂 AI EQMS Hub Pro</h1>", unsafe_allow_html=True)
    st.caption(f"Last sync • {now_ist().strftime('%H:%M:%S')} IST")

    df = load_sheet_data(sheet)
    filtered = df.copy() if not df.empty else pd.DataFrame()
    cfg = SHEET_CONFIG[sheet]

    if not filtered.empty:
        if st.session_state.pnr_val and cfg.get("pnr_col") is not None:
            col = filtered.columns[cfg["pnr_col"]]
            filtered = filtered[filtered[col].astype(str).str.contains(st.session_state.pnr_val, case=False, na=False)]
        if st.session_state.train_val and cfg.get("train_col") is not None:
            col = filtered.columns[cfg["train_col"]]
            filtered = filtered[filtered[col].astype(str).str.contains(st.session_state.train_val, case=False, na=False)]
        if (st.session_state.from_val or st.session_state.to_val) and cfg.get("doj_col") is not None:
            col = filtered.columns[cfg["doj_col"]]
            filtered["_t"] = pd.to_datetime(filtered[col], format="%d-%m-%Y", errors="coerce")
            if st.session_state.from_val:
                filtered = filtered[filtered["_t"] >= pd.to_datetime(st.session_state.from_val)]
            if st.session_state.to_val:
                filtered = filtered[filtered["_t"] <= pd.to_datetime(st.session_state.to_val)]
            filtered = filtered.drop("_t", axis=1)

    view = st.session_state.current_view

    # ========== CHAT ==========
    if view == "💬 Chat":
        st.subheader("💬 Chat with TSKEQ Bot")

        cols = st.columns(3)
        suggestions = ["Show EQ summary", "Records today?", "Train breakup", "Pending EQ", "Quota status", "PNR help"]
        for i, s in enumerate(suggestions):
            if cols[i%3].button(s, key=f"s{i}", use_container_width=True):
                st.session_state.pending_suggestion = s
                st.rerun()

        if st.session_state.pending_suggestion:
            q = st.session_state.pending_suggestion
            st.session_state.pending_suggestion = None
            st.session_state.messages.append({"role":"user","content":q})
            with st.chat_message("user"): st.markdown(q)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    ans = chat_gemini(q, st.session_state.messages)
                    st.markdown(ans)
            st.session_state.messages.append({"role":"assistant","content":ans})
            st.rerun()

        for m in st.session_state.messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

        if prompt := st.chat_input("Sawal likhein..."):
            st.session_state.messages.append({"role":"user","content":prompt})
            with st.chat_message("user"): st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    ans = chat_gemini(prompt, st.session_state.messages)
                    st.markdown(ans)
            st.session_state.messages.append({"role":"assistant","content":ans})
            st.rerun()

        if st.button("🗑️ Clear Chat"):
            st.session_state.messages = []
            st.rerun()

    # ========== DATA TABLE ==========
    elif view == "📋 Data Table":
        st.subheader(f"📋 {sheet} — {len(filtered)} rows")

        if not filtered.empty:
            # ===== PRINT PDF =====
            try:
                pdf_bytes = make_pdf(filtered, sheet)
                # Print button with JavaScript
                st.markdown("""
                    <button onclick="window.print()" style="
                        background: linear-gradient(135deg, #7c3aed, #6d28d9);
                        color: white;
                        border: none;
                        padding: 10px 24px;
                        border-radius: 10px;
                        font-weight: 600;
                        cursor: pointer;
                        margin-right: 10px;
                    ">🖨️ Print Sheet (Ctrl+P)</button>
                """, unsafe_allow_html=True)
                
                # Download PDF
                st.download_button(
                    "📥 Download PDF",
                    data=pdf_bytes,
                    file_name=f"EQMS_{sheet}_{now_ist().strftime('%d%m%Y_%H%M')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
                
                # Share WhatsApp
                msg = f"EQ Sheet: {sheet}\nRows: {len(filtered)}\nTime: {now_ist().strftime('%d-%m-%Y %H:%M')}\n\n"
                wa_url = f"https://api.whatsapp.com/send?text={urllib.parse.quote(msg)}"
                st.link_button("📤 WhatsApp Share", wa_url, use_container_width=True)
                
                st.markdown("---")
            except Exception as e:
                st.warning(f"PDF/Print error: {e}")

        if filtered.empty:
            st.info("No data")
        else:
            page_size = st.selectbox("Rows/page", [15,25,50,100], index=1)
            total_p = max(1, (len(filtered)+page_size-1)//page_size)
            
            col1, col2, col3 = st.columns([1,2,1])
            if col1.button("◀ Prev") and st.session_state.current_page > 1:
                st.session_state.current_page -= 1
                st.rerun()
            col2.write(f"Page {st.session_state.current_page} / {total_p}")
            if col3.button("Next ▶") and st.session_state.current_page < total_p:
                st.session_state.current_page += 1
                st.rerun()

            start = (st.session_state.current_page-1)*page_size
            page_df = filtered.iloc[start:start+page_size].copy()
            
            # Add row numbers
            page_df.insert(0, "#", range(start+1, start+len(page_df)+1))
            page_df.insert(1, "Select", False)
            
            edited = st.data_editor(
                page_df, 
                use_container_width=True, 
                height=400, 
                key="editor",
                column_config={
                    "Select": st.column_config.CheckboxColumn("Select", width="small")
                }
            )
            selected = edited[edited["Select"]].index.tolist()

            st.markdown("#### ⚡ Actions")
            b1, b2, b3, b4, b5 = st.columns(5)
            
            with b1:
                if st.button("💾 Save Edits", use_container_width=True):
                    try:
                        gc = init_sheets()
                        ws = gc.open_by_key(SHEET_ID).worksheet(sheet)
                        # Remove Select column for saving
                        data_to_save = edited.drop(columns=["Select", "#"], errors='ignore').values.tolist()
                        srow = cfg["start_row"] + start
                        erow = srow + len(data_to_save) - 1
                        if data_to_save and len(data_to_save[0]) > 0:
                            letter = col_index_to_letter(len(data_to_save[0]))
                            ws.update(f"A{srow}:{letter}{erow}", data_to_save)
                            st.success("✅ Saved!")
                            st.cache_data.clear()
                            time.sleep(0.4)
                            st.rerun()
                    except Exception as e:
                        st.error(f"Save error: {e}")
                        
            with b2:
                if st.button("➕ Add Row", use_container_width=True):
                    try:
                        gc = init_sheets()
                        ws = gc.open_by_key(SHEET_ID).worksheet(sheet)
                        ws.append_row([""]*22)
                        st.success("✅ Row added")
                        st.cache_data.clear()
                        time.sleep(0.4)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Add error: {e}")
                        
            with b3:
                if selected:
                    if st.button("🗑️ Delete", use_container_width=True):
                        try:
                            gc = init_sheets()
                            ws = gc.open_by_key(SHEET_ID).worksheet(sheet)
                            # Delete from bottom to top
                            for idx in sorted(selected, reverse=True):
                                ws.delete_rows(cfg["start_row"] + start + idx)
                            st.success(f"✅ Deleted {len(selected)} rows")
                            st.cache_data.clear()
                            time.sleep(0.4)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Delete error: {e}")
                else:
                    st.button("🗑️ Delete", disabled=True, use_container_width=True)
                    
            with b4:
                if selected:
                    pnr_col = next((c for c in edited.columns if "PNR" in c.upper()), None)
                    pnrs = edited.loc[selected, pnr_col].tolist() if pnr_col else []
                    msg = f"📊 EQ Data\nSelected: {len(selected)} records\nPNRs: {', '.join(map(str,pnrs[:10]))}\nSheet: {sheet}"
                    wa_url = f"https://api.whatsapp.com/send?text={urllib.parse.quote(msg)}"
                    st.link_button("📤 WA Share", wa_url, use_container_width=True)
                else:
                    st.button("📤 WA Share", disabled=True, use_container_width=True)
                    
            with b5:
                if not filtered.empty:
                    try:
                        pdf_bytes = make_pdf(filtered, sheet)
                        st.download_button(
                            "📥 PDF",
                            data=pdf_bytes,
                            file_name=f"EQMS_{sheet}_{now_ist().strftime('%d%m%Y')}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
                    except:
                        st.button("📥 PDF", disabled=True, use_container_width=True)

    # ========== DASHBOARD ==========
    else:
        st.subheader("📊 Dashboard")
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Total Records", len(filtered))
        
        tcol = next((c for c in filtered.columns if "T/N" in c.upper() or "TRAIN" in c.upper()), None)
        c2.metric("Unique Trains", filtered[tcol].nunique() if tcol else 0)
        
        bcol = next((c for c in filtered.columns if "BERTH" in c.upper() or "T/BERTHS" in c.upper()), None)
        total_b = pd.to_numeric(filtered[bcol], errors="coerce").sum() if bcol else 0
        c3.metric("Total Berths", int(total_b) if total_b else 0)
        
        dcol = next((c for c in filtered.columns if "DOJ" in c.upper()), None)
        expired = 0
        if dcol:
            today = now_ist().replace(tzinfo=None, hour=0, minute=0, second=0)
            for _, r in filtered.iterrows():
                try:
                    if datetime.strptime(parse_date(r.get(dcol,"")), "%d-%m-%Y") < today:
                        expired += 1
                except: pass
        c4.metric("Expired DOJ", expired)

        if not filtered.empty:
            st.markdown("---")
            col1, col2 = st.columns(2)
            
            with col1:
                if tcol:
                    tc = filtered[tcol].value_counts().head(8).reset_index()
                    tc.columns = ["Train", "Count"]
                    fig = px.pie(tc, names="Train", values="Count", hole=0.45, title="Top 8 Trains")
                    fig.update_layout(height=350, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True)
                    
            with col2:
                if bcol:
                    berth_vals = pd.to_numeric(filtered[bcol], errors="coerce").dropna()
                    if not berth_vals.empty:
                        fig = px.histogram(berth_vals, nbins=10, title="Berths Distribution",
                                          labels={'value': 'Berths', 'count': 'Count'})
                        fig.update_layout(height=350, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                        st.plotly_chart(fig, use_container_width=True)
            
            if dcol:
                df_temp = filtered.copy()
                df_temp['_date'] = pd.to_datetime(df_temp[dcol], format="%d-%m-%Y", errors="coerce")
                daily = df_temp.groupby('_date').size().reset_index(name='count')
                if not daily.empty:
                    fig = px.line(daily, x='_date', y='count', title="Daily Trend", markers=True)
                    fig.update_layout(height=300, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="pro-footer">Made with ❤️ by Sharique • AI EQMS Hub Pro</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
