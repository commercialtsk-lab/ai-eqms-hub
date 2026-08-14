import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import streamlit as st

st.set_page_config(page_title="EQ Master Bot Hub", layout="wide")

# --- Google Sheets Setup ---
def get_sheets_client():
    creds_dict = dict(st.secrets["GSPREAD_CREDENTIALS"])
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

client = get_sheets_client()
sheet_names = ["EQ", "EMAIL_DATA", "NOTE", "DATA", "FINAL", "DATA2"]

# Duplicate columns ko unique banane ka function
def make_headers_unique(headers):
    seen = {}
    unique_headers = []
    for h in headers:
        h_str = str(h).strip()
        if h_str in seen:
            seen[h_str] += 1
            unique_headers.append(f"{h_str}_{seen[h_str]}")
        else:
            seen[h_str] = 0
            unique_headers.append(h_str if h_str else "Unnamed")
    return unique_headers

# --- Logic Definitions ---
def run_logic(logic_id):
    st.write(f"Executing Logic {logic_id}...")

# --- UI ---
st.sidebar.title("⚡ Navigation Hub")
menu = st.sidebar.radio("Select View", ["Sheets View", "Bot Logic Control"])

if menu == "Sheets View":
    st.title("📊 Google Sheets Data")
    tabs = st.tabs(sheet_names)
    
    for i, tab in enumerate(tabs):
        with tab:
            try:
                sh = client.open("EQ Master Bot")
                worksheet = sh.worksheet(sheet_names[i])
                data = worksheet.get_all_values()
                if data and len(data) > 1:
                    unique_headers = make_headers_unique(data[0])
                    df = pd.DataFrame(data[1:], columns=unique_headers)
                    st.dataframe(df, use_container_width=True)
                elif data:
                    df = pd.DataFrame(data)
                    st.dataframe(df, use_container_width=True)
                else:
                    st.warning("Sheet is empty.")
            except Exception as e:
                st.error(f"Error loading {sheet_names[i]}: {e}")

elif menu == "Bot Logic Control":
    st.title("🤖 Bot Logic Control Center")
    col1, col2 = st.columns(2)
    for i in range(1, 9):
        if i % 2 != 0:
            with col1:
                if st.button(f"Run Logic {i}"): run_logic(i)
        else:
            with col2:
                if st.button(f"Run Logic {i}"): run_logic(i)
