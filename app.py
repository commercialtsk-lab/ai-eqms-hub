import google.generativeai as genai
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
import streamlit as st

# 1. Page Configuration
st.set_page_config(
    page_title="Pro Intelligence Hub", page_icon="⚡", layout="wide"
)

# 2. Custom CSS for Pro UI
st.markdown(
    """
    <style>
    .stApp { background: #090d16; color: #e2e8f0; font-family: 'Inter', sans-serif; }
    .main-title { font-size: 2.8rem; font-weight: 800; background: linear-gradient(90deg, #6366f1, #a855f7, #ec4899); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 0px; }
    .sub-title { color: #94a3b8; font-size: 1.1rem; margin-bottom: 30px; }
    .pro-card { background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); padding: 24px; border-radius: 16px; backdrop-filter: blur(8px); }
    .stButton>button { width: 100%; background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%); color: white; font-weight: 600; border: none; padding: 0.6rem 1rem; border-radius: 10px; }
    </style>
""",
    unsafe_allow_html=True,
)

# 3. Sidebar Navigation
with st.sidebar:
  st.markdown("### ⚡ Navigation Hub")
  selected_tab = st.radio(
      "Go to",
      [
          "🏠 Dashboard",
          "📤 Upload & Process",
          "📊 Live Google Sheets",
          "⚙️ System Settings",
      ],
  )
  st.markdown("---")
  st.info("System Status: *Online & Secured* 🟢")

# 4. Main Content Area
if selected_tab == "🏠 Dashboard":
  st.markdown(
      '<p class="main-title">Command Center</p>', unsafe_allow_html=True
  )
  st.markdown(
      '<p class="sub-title">Welcome! Real-time automation dashboard is'
      " active.</p>",
      unsafe_allow_html=True,
  )

  col1, col2, col3, col4 = st.columns(4)
  with col1:
    st.metric(label="Total Processed", value="0", delta="Ready")
  with col2:
    st.metric(label="AI Brain", value="Gemini Flash", delta="Active")
  with col3:
    st.metric(label="Modules", value="10/10", delta="Healthy")
  with col4:
    st.metric(label="Cloud Sync", value="Ready", delta="Waiting Setup")

elif selected_tab == "📤 Upload & Process":
  st.markdown('<p class="main-title">Multi-Media Ingestion</p>', unsafe_allow_html=True)
  st.markdown(
      '<p class="sub-title">Upload files or text for Gemini AI processing.</p>',
      unsafe_allow_html=True,
  )

  user_input = st.text_area("Messy text ya details yahan paste karein:")
  api_key = st.text_input("Gemini API Key", type="password")

  if st.button("⚡ Process with Gemini Flash"):
    if not api_key:
      st.error("Kripya apni Gemini API Key daalein.")
    elif not user_input:
      st.error("Kripya kuch text enter karein.")
    else:
      with st.spinner("Gemini data process kar raha hai..."):
        try:
          genai.configure(api_key=api_key)
          model = genai.GenerativeModel("gemini-2.5-flash")
          response = model.generate_content(
              "Is messy data ko clean karke structured format mein do:"
              f" {user_input}"
          )
          st.success("Processing Complete! ✨")
          st.markdown(
              f'<div class="pro-card"><h4>Output:</h4><p>{response.text}</p></div>',
              unsafe_allow_html=True,
          )
        except Exception as e:
          st.error(f"Error: {e}")

elif selected_tab == "📊 Live Google Sheets":
  st.markdown(
      '<p class="main-title">Live Database Viewer</p>', unsafe_allow_html=True
  )
  st.markdown(
      '<p class="sub-title">Real-time data from Google Sheets.</p>',
      unsafe_allow_html=True,
  )
  st.info(
      "Google Sheet connect karne ke liye 'credentials.json' file repository"
      " mein upload karein."
  )

elif selected_tab == "⚙️ System Settings":
  st.markdown('<p class="main-title">System Configurations</p>', unsafe_allow_html=True)
  st.markdown(
      '<p class="sub-title">Manage system settings and API integrations.</p>',
      unsafe_allow_html=True,
  )
  st.text_input("Google Sheets Name", value="Railway_Emergency_Data")
