import google.generativeai as genai
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import streamlit as st

st.set_page_config(
    page_title="EQ Master Bot Hub", page_icon="⚡", layout="wide"
)

# Secrets Setup
try:
  creds_dict = dict(st.secrets["GSPREAD_CREDENTIALS"])

  if "private_key" in creds_dict:
    creds_dict["private_key"] = creds_dict["private_key"].replace(
        "\\n", "\n"
    )

  scopes = [
      "https://www.googleapis.com/auth/spreadsheets",
      "https://www.googleapis.com/auth/drive",
  ]
  creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
  client = gspread.authorize(creds)
except Exception as e:
  st.error(f"Google Sheets Connection Error: {e}")

try:
  genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception as e:
  st.warning("Gemini API Key missing.")

# UI Navigation Hub
st.sidebar.markdown(
    "<h2 style='color: #ff9933;'>⚡ Navigation Hub</h2>", unsafe_allow_html=True
)
selected_tab = st.sidebar.radio(
    "",
    ["Dashboard", "Upload & Process", "Live Google Sheets", "System Settings"],
    label_visibility="collapsed",
)

if selected_tab == "Dashboard":
  st.markdown(
      "<p style='font-size: 2.8rem; font-weight: 800; color: #ffffff;'>Command"
      " Center</p>",
      unsafe_allow_html=True,
  )
  st.write("Welcome! Real-time EQ Master Bot dashboard is active.")

elif selected_tab == "Upload & Process":
  st.markdown(
      "<p style='font-size: 2.8rem; font-weight: 800; color: #ffffff;'>Upload"
      " & Process</p>",
      unsafe_allow_html=True,
  )
  st.write("Upload section is ready.")

elif selected_tab == "Live Google Sheets":
  st.markdown(
      "<p style='font-size: 2.8rem; font-weight: 800; color: #ffffff;'>Live"
      " Google Sheets</p>",
      unsafe_allow_html=True,
  )
  try:
    spreadsheet_id = client.open("EQ Master Bot").id
    sheet = client.open_by_key(spreadsheet_id).get_worksheet(0)
    data = sheet.get_all_values()

    if data and len(data) > 1:
      # Duplicate column names fix karne ke liye unique headers bana rahe hain
      headers = data[0]
      seen = {}
      unique_headers = []
      for h in headers:
        h_str = str(h).strip()
        if h_str in seen:
          seen[h_str] += 1
          unique_headers.append(f"{h_str}_{seen[h_str]}")
        else:
          seen[h_str] = 0
          unique_headers.append(h_str)

      df = pd.DataFrame(data[1:], columns=unique_headers)
      st.dataframe(df, use_container_width=True)
    elif data:
      df = pd.DataFrame(data)
      st.dataframe(df, use_container_width=True)
    else:
      st.warning("Google Sheet is empty.")
  except Exception as e:
    st.error(f"Google Sheet load error: {e}")

elif selected_tab == "System Settings":
  st.markdown(
      "<p style='font-size: 2.8rem; font-weight: 800; color: #ffffff;'>System"
      " Configurations</p>",
      unsafe_allow_html=True,
  )
  st.success("Secrets and Google Sheet successfully linked!")
