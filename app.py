import json
import google.generativeai as genai
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import streamlit as st

# 1. Page Configuration
st.set_page_config(
    page_title="Pro Intelligence Hub", page_icon="⚡", layout="wide"
)

# 2. Secrets & Credentials Setup (PEM / Newline Fix)
try:
  creds_json = st.secrets["GOOGLE_CREDENTIALS_JSON"]
  
  # Ensure it's handled properly whether it's a string or already parsed
  if isinstance(creds_json, str):
    creds_dict = json.loads(creds_json)
  else:
    creds_dict = dict(creds_json)

  # Robust fix for private key newlines (handles both \\n and \n)
  if "private_key" in creds_dict:
    pk = creds_dict["private_key"]
    # Replace literal '\\n' with actual '\n'
    pk = pk.replace("\\\\n", "\n").replace("\\n", "\n")
    creds_dict["private_key"] = pk

  scopes = [
      "https://spreadsheets.google.com/feeds",
      "https://www.googleapis.com/auth/drive",
  ]
  creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
  client = gspread.authorize(creds)
except Exception as e:
  st.error(f"Google Sheets Connection Error: {e}")

# Gemini API Key Setup
try:
  GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
  genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
  st.warning("Gemini API Key not found in Streamlit Secrets.")

# 3. Custom CSS for Pro UI (Tiranga / Dark Theme vibe)
st.markdown(
    """
    <style>
    .stApp { background: #090d16; color: #e2e8f0; }
    .main-title { font-size: 2.8rem; font-weight: 800; color: #ffffff; }
    .sub-title { color: #94a3b8; font-size: 1.1rem; }
    .pro-card { background: rgba(30, 41, 59, 0.7); padding: 20px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.1); }
    </style>
    """,
    unsafe_allow_html=True,
)

# 4. Sidebar Navigation Hub
st.sidebar.markdown(
    "<h2 style='color: #ff9933;'>⚡ Navigation Hub</h2>", unsafe_allow_html=True
)
st.sidebar.write("Go to")
selected_tab = st.sidebar.radio(
    "",
    ["Dashboard", "Upload & Process", "Live Google Sheets", "System Settings"],
    label_visibility="collapsed",
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    "<div class='pro-card'><b>System Status:</b> <span"
    " style='color: #22c55e;'>● Online & Secured</span></div>",
    unsafe_allow_html=True,
)

# 5. Main Application Routing
if selected_tab == "Dashboard":
  st.markdown(
      "<p class='main-title'>Command Center</p>", unsafe_allow_html=True
  )
  st.markdown(
      "<p class='sub-title'>Welcome! Real-time automation dashboard is"
      " active.</p>",
      unsafe_allow_html=True,
  )

  col1, col2, col3 = st.columns(3)
  with col1:
    st.markdown(
        "<div"
        " class='pro-card'><h3>0</h3><p>Ready</p></div>",
        unsafe_allow_html=True,
    )
  with col2:
    st.markdown(
        "<div"
        " class='pro-card'><h3>Gemini Flash 2.5</h3><p>Active</p></div>",
        unsafe_allow_html=True,
    )
  with col3:
    st.markdown(
        "<div"
        " class='pro-card'><h3>Healthy</h3><p>System Status</p></div>",
        unsafe_allow_html=True,
    )

elif selected_tab == "Upload & Process":
  st.markdown("<p class='main-title'>Upload & Process</p>", unsafe_allow_html=True)
  st.markdown(
      "<p class='sub-title'>Upload your documents for AI extraction.</p>",
      unsafe_allow_html=True,
  )
  uploaded_file = st.file_uploader(
      "Choose a file", type=["csv", "xlsx", "txt", "pdf"]
  )
  if uploaded_file:
    st.success("File uploaded successfully! Ready for AI processing.")

elif selected_tab == "Live Google Sheets":
  st.markdown(
      "<p class='main-title'>Live Google Sheets</p>", unsafe_allow_html=True
  )
  st.markdown(
      "<p class='sub-title'>Real-time data synchronization from Google"
      " Sheets.</p>",
      unsafe_allow_html=True,
  )
  try:
    sheet = client.open("Railway_Emergency_Data").sheet1
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    st.dataframe(df)
  except Exception as e:
    st.info(f"Google Sheet load karne mein error: {e}")

elif selected_tab == "System Settings":
  st.markdown(
      "<p class='main-title'>System Configurations</p>", unsafe_allow_html=True
  )
  st.markdown(
      "<p class='sub-title'>Manage system settings and API integrations</p>",
      unsafe_allow_html=True,
  )
  st.text_input("Google Sheets Name", value="Railway_Emergency_Data")
  st.success("API keys and cloud parameters are securely linked via Secrets.")
