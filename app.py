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
    "activity_log": [],
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
    "NOTE": {"start_row": 2, "pnr_col": None, "train_col": 0, "doj_col": None}
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

# ==================== GEMINI PARSER ====================
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
        cleaned = []
        seen = set()
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

def make_pdf(df, title):
    pdf = FPDF(orientation="L", format="A4")
    pdf.add_page()
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, f"AI EQMS Hub Pro - {title}", ln=True, align="C")
    pdf.set_font("Arial", "", 8)
    pdf.cell(0, 6, f"Generated: {now_ist().strftime('%d-%m-%Y %H:%M IST')} | Rows: {len(df)}", ln=True, align="C")
    pdf.ln(3)
    cols = list(df.columns)[:11]
    w = 277 / max(len(cols), 1)
    pdf.set_font("Arial", "B", 7)
    for c in cols:
        pdf.cell(w, 6, str(c)[:16], border=1)
    pdf.ln()
    pdf.set_font("Arial", "", 6)
    for _, row in df.iterrows():
        for c in cols:
            pdf.cell(w, 5, str(row.get(c, ""))[:18], border=1)
        pdf.ln()
        if pdf.get_y() > 185:
            pdf.add_page()
    return pdf.output(dest="S").encode("latin-1")

# ==================== THEME ====================
def apply_theme(dark):
    if dark:
        bg, card, text, sec, border, accent, inp = "#0a0a0a", "#141414", "#e8e8e8", "#a0a0a0", "#2a2a2a", "#a855f7", "#1a1a1a"
    else:
        bg, card, text, sec, border, accent, inp = "#f7f7f8", "#ffffff", "#1a1a1a", "#5f6368", "#e5e5e5", "#7c3aed", "#ffffff"

    st.markdown(f"""
    <style>
        .stApp {{ background: {bg} !important; }}
        [data-testid="stSidebar"] {{ background: {card} !important; border-right: 1px solid {border}; }}
        h1,h2,h3,h4,p,div,span,label, .stMarkdown {{ color: {text} !important; }}
        .stTextInput input, .stTextArea textarea, .stSelectbox>div>div {{
            background: {inp} !important; color: {text} !important; border: 1px solid {border} !important; border-radius: 10px !important;
        }}
        .stButton>button {{
            background: transparent !important; color: {accent} !important; border: 1px solid {border} !important;
            border-radius: 10px !important; font-weight: 500 !important;
        }}
        .stButton>button:hover {{ background: {accent} !important; color: white !important; }}
        .stChatMessage {{ background: {card} !important; border: 1px solid {border} !important; border-radius: 12px !important; }}
        .block-container {{ padding-top: 1.2rem !important; padding-bottom: 2rem !important; }}
        .pro-footer {{
            text-align: center; color: {sec}; font-size: 0.82rem; margin-top: 40px;
            padding: 16px 0 8px; border-top: 1px solid {border};
        }}
        [data-testid="stDataEditor"] {{ border-radius: 10px !important; }}
    </style>
    """, unsafe_allow_html=True)

# ==================== MAIN ====================
def main():
    # Theme toggle
    dark = st.sidebar.toggle("🌙 Dark Mode", value=st.session_state.dark_mode)
    if dark != st.session_state.dark_mode:
        st.session_state.dark_mode = dark
        st.rerun()
    apply_theme(dark)

    # ---------- SIDEBAR ----------
    with st.sidebar:
        now = now_ist()
        if is_flag_time():
            st.markdown("""
            <div style="text-align:center;margin-bottom:14px;">
                <div style="font-size:26px;">🇮🇳</div>
                <div style="color:#FF9933;font-weight:700;font-size:1.05rem;">नमस्ते, आपका स्वागत है</div>
                <div style="color:#fff;font-weight:600;">हम भारत के लोग</div>
                <div style="color:#138808;font-weight:700;">जय हिंद</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            h = now.hour
            greeting = "☀️ Good Morning" if 5<=h<12 else "🌤️ Good Afternoon" if 12<=h<17 else "🌆 Good Evening" if 17<=h<21 else "🌙 Good Night"
            st.markdown(f"**{greeting}**")

        st.caption(f"{now.strftime('%d-%m-%Y')}  •  {now.strftime('%H:%M')} IST")

        if st.checkbox("🔄 Auto Sync (20s)", value=True):
            if time.time() - st.session_state.last_refresh > 20:
                st.session_state.last_refresh = time.time()
                st.cache_data.clear()
                st.rerun()

        st.markdown("---")
        st.markdown(f'<a href="https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit" target="_blank" style="display:block;text-align:center;padding:9px;border:1px solid #444;border-radius:10px;text-decoration:none;color:#a855f7;font-weight:500;">📊 Open Google Sheet</a>', unsafe_allow_html=True)
        st.markdown("---")

        # ===== SMART UPLOAD =====
        st.subheader("📤 Smart Upload")
        mode = st.radio("Type", ["📷 Image / PDF", "📝 Text", "🎤 Voice / Audio"], horizontal=True, label_visibility="collapsed")

        uploaded = None
        text_data = ""
        audio_data = None

        if mode == "📷 Image / PDF":
            uploaded = st.file_uploader("Image or PDF (1-2 pages)", type=["png","jpg","jpeg","pdf"], label_visibility="collapsed")
        elif mode == "📝 Text":
            text_data = st.text_area("Paste messy text", height=130, placeholder="Yahan text paste / type karein...", label_visibility="collapsed")
        else:
            st.caption("Mobile jaisa mic se record karein ↓")
            audio_data = st.audio_input("Record Audio", label_visibility="collapsed")
            uploaded = st.file_uploader("Ya audio file upload karein", type=["mp3","wav","ogg","m4a"], label_visibility="collapsed")

        if st.button("🚀 Process & Save", type="primary", use_container_width=True):
            if mode == "📝 Text" and not text_data.strip():
                st.warning("Text daalein")
            elif mode != "📝 Text" and not uploaded and not audio_data:
                st.warning("File / Audio select karein")
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
                        st.success(f"✅ {res['count']} records extracted")
                        with st.expander("Preview Extracted"):
                            st.dataframe(pd.DataFrame(res["records"]), use_container_width=True)

                        save_res = save_records(res["records"])
                        if "error" in save_res:
                            st.error(save_res["error"])
                        else:
                            st.success(f"Saved {save_res['saved']} • Skipped {save_res['skipped']}")
                            drive = upload_drive(fbytes, fname, mime)
                            if drive["success"]:
                                st.session_state.last_uploaded_file = fname
                                st.session_state.last_uploaded_view_url = drive["view_url"]
                                st.session_state.last_uploaded_print_url = drive["print_url"]
                                st.session_state.upload_success = True
                                st.session_state.last_upload_time = now_ist().strftime("%H:%M")
                                st.success("📁 Drive me save ho gaya")
                                st.cache_data.clear()
                                st.session_state.last_refresh = time.time()
                                time.sleep(0.6)
                                st.rerun()
                except Exception as e:
                    st.error(str(e))
                finally:
                    prog.empty()
                    status.empty()

        if st.session_state.upload_success and st.session_state.last_uploaded_file:
            st.markdown("---")
            st.markdown(f"**📄 {st.session_state.last_uploaded_file}**")
            st.caption(f"Uploaded {st.session_state.last_upload_time}")
            c1, c2 = st.columns(2)
            c1.link_button("👁️ View", st.session_state.last_uploaded_view_url, use_container_width=True)
            c2.link_button("🖨️ Print Original", st.session_state.last_uploaded_print_url, use_container_width=True)
            if st.button("Clear", use_container_width=True):
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
            st.session_state.pnr_val = st.session_state.train_val = ""
            st.session_state.from_val = st.session_state.to_val = None
            st.session_state.current_page = 1
            st.rerun()

        sheet = st.selectbox("Sheet", list(SHEET_CONFIG.keys()))
        view = st.radio("View", ["💬 Chat", "📋 Data Table", "📊 Dashboard"], index=0)

    # ---------- MAIN AREA ----------
    st.markdown("<h1 style='font-size:1.55rem;margin-bottom:2px;'>🚂 AI EQMS Hub Pro</h1>", unsafe_allow_html=True)
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

    # ==================== CHAT (TOP PRIORITY) ====================
    if view == "💬 Chat":
        st.subheader("💬 Chat with TSKEQ Bot")

        # Suggestions
        cols = st.columns(3)
        suggestions = ["Show EQ summary", "How many records today?", "Train wise breakup", "Pending requests", "Quota status", "PNR help"]
        for i, s in enumerate(suggestions):
            if cols[i % 3].button(s, key=f"sug_{i}", use_container_width=True):
                st.session_state.pending_suggestion = s
                st.rerun()

        if st.session_state.pending_suggestion:
            q = st.session_state.pending_suggestion
            st.session_state.pending_suggestion = None
            st.session_state.messages.append({"role": "user", "content": q})
            with st.chat_message("user"):
                st.markdown(q)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    ans = chat_gemini(q, st.session_state.messages)
                    st.markdown(ans)
            st.session_state.messages.append({"role": "assistant", "content": ans})
            st.rerun()

        for m in st.session_state.messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

        if prompt := st.chat_input("Apna sawal likhein..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    ans = chat_gemini(prompt, st.session_state.messages)
                    st.markdown(ans)
            st.session_state.messages.append({"role": "assistant", "content": ans})
            st.rerun()

        if st.button("🗑️ Clear Chat"):
            st.session_state.messages = []
            st.rerun()

    # ==================== DATA TABLE ====================
    elif view == "📋 Data Table":
        st.subheader(f"📋 {sheet} — {len(filtered)} rows")

        # PRINT BUTTON
        if not filtered.empty:
            pdf_bytes = make_pdf(filtered, sheet)
            st.download_button(
                "🖨️ Print / Download Filtered (A4 PDF)",
                data=pdf_bytes,
                file_name=f"EQMS_{sheet}_{now_ist().strftime('%d%m%Y_%H%M')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

        if filtered.empty:
            st.info("No data")
        else:
            page_size = st.selectbox("Rows/page", [15, 25, 50], index=1)
            total_p = max(1, (len(filtered) + page_size - 1) // page_size)
            c1, c2, c3 = st.columns([1, 2, 1])
            if c1.button("◀ Prev") and st.session_state.current_page > 1:
                st.session_state.current_page -= 1
                st.rerun()
            c2.write(f"Page {st.session_state.current_page} / {total_p}")
            if c3.button("Next ▶") and st.session_state.current_page < total_p:
                st.session_state.current_page += 1
                st.rerun()

            start = (st.session_state.current_page - 1) * page_size
            page_df = filtered.iloc[start:start+page_size].copy()
            page_df.insert(0, "Select", False)
            edited = st.data_editor(page_df, use_container_width=True, height=380, key="editor")
            selected = edited[edited["Select"]].index.tolist()

            st.markdown("#### Actions")
            b1, b2, b3, b4 = st.columns(4)
            with b1:
                if st.button("💾 Save Edits", use_container_width=True):
                    try:
                        gc = init_sheets()
                        ws = gc.open_by_key(SHEET_ID).worksheet(sheet)
                        data = edited.drop("Select", axis=1).values.tolist()
                        srow = cfg["start_row"] + start
                        erow = srow + len(data) - 1
                        letter = col_index_to_letter(len(data[0]))
                        ws.update(f"A{srow}:{letter}{erow}", data)
                        st.success("Saved")
                        st.cache_data.clear()
                        time.sleep(0.4)
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            with b2:
                if st.button("➕ Add Row", use_container_width=True):
                    try:
                        gc = init_sheets()
                        ws = gc.open_by_key(SHEET_ID).worksheet(sheet)
                        ws.append_row([""] * 22)
                        st.success("Added")
                        st.cache_data.clear()
                        time.sleep(0.4)
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            with b3:
                if selected and st.button("🗑️ Delete", use_container_width=True):
                    try:
                        gc = init_sheets()
                        ws = gc.open_by_key(SHEET_ID).worksheet(sheet)
                        for idx in sorted(selected, reverse=True):
                            ws.delete_rows(cfg["start_row"] + idx)
                        st.success(f"Deleted {len(selected)}")
                        st.cache_data.clear()
                        time.sleep(0.4)
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
                else:
                    st.button("🗑️ Delete", disabled=True, use_container_width=True)
            with b4:
                if selected:
                    pnr_col = next((c for c in edited.columns if "PNR" in c.upper()), None)
                    pnrs = edited.loc[selected, pnr_col].tolist() if pnr_col else []
                    msg = f"EQ • {len(selected)} records\nPNRs: {', '.join(map(str, pnrs[:8]))}"
                    st.link_button("📤 WhatsApp", f"https://api.whatsapp.com/send?text={urllib.parse.quote(msg)}", use_container_width=True)
                else:
                    st.button("📤 WhatsApp", disabled=True, use_container_width=True)

    # ==================== DASHBOARD ====================
    else:
        st.subheader("📊 Dashboard")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", len(filtered))
        tcol = next((c for c in filtered.columns if "T/N" in c.upper() or "TRAIN" in c.upper()), None)
        c2.metric("Trains", filtered[tcol].nunique() if tcol else 0)
        bcol = next((c for c in filtered.columns if "BERTH" in c.upper()), None)
        total_b = pd.to_numeric(filtered[bcol], errors="coerce").sum() if bcol else 0
        c3.metric("Berths", int(total_b) if total_b else 0)
        dcol = next((c for c in filtered.columns if "DOJ" in c.upper()), None)
        expired = 0
        if dcol:
            for _, r in filtered.iterrows():
                try:
                    if datetime.strptime(parse_date(r.get(dcol,"")), "%d-%m-%Y") < now_ist().replace(tzinfo=None).replace(hour=0,minute=0,second=0):
                        expired += 1
                except: pass
        c4.metric("Expired", expired)

        if not filtered.empty and tcol:
            tc = filtered[tcol].value_counts().head(8).reset_index()
            tc.columns = ["Train", "Count"]
            fig = px.pie(tc, names="Train", values="Count", hole=0.45, title="Train Distribution")
            st.plotly_chart(fig, use_container_width=True)

    # ===== FOOTER (ALWAYS LAST) =====
    st.markdown('<div class="pro-footer">Made with ❤️ by Sharique • AI EQMS Hub Pro</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
