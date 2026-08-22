import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime, timedelta
import requests
import json
import os
import random

st.set_page_config(
    page_title='AI-EQMS Hub',
    page_icon='🚂',
    layout='wide',
    initial_sidebar_state='expanded'
)

def init_session():
    defaults = {
        'weather_data': None,
        'last_weather_update': None,
        'selected_sheet': 'EMAIL_DATA',
        'df_data': None,
        'bg_weather': 'clear-day',
        'city': 'New Delhi',
        'animation_key': 0
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()

@st.cache_resource(show_spinner=False)
def get_gsheet_client():
    try:
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/spreadsheets'
        ]
        creds = None
        if os.path.exists('credentials.json'):
            creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
        elif os.path.exists('service_account.json'):
            creds = Credentials.from_service_account_file('service_account.json', scopes=scope)
        else:
            try:
                creds_dict = st.secrets['gcp_service_account']
                creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            except:
                pass
        if creds:
            return gspread.authorize(creds)
        return None
    except Exception as e:
        st.error(f'Google Sheets auth error: {e}')
        return None

@st.cache_data(ttl=300, show_spinner=False)
def get_sheet_data(sheet_name, spreadsheet_id=None):
    try:
        client = get_gsheet_client()
        if not client:
            return None, 'Google Sheets client not initialized. Please check credentials.'
        
        if spreadsheet_id:
            spreadsheet = client.open_by_key(spreadsheet_id)
        else:
            try:
                spreadsheet = client.open_by_key(st.secrets['spreadsheet_id'])
            except:
                spreadsheets = client.list_spreadsheet_files()
                if spreadsheets:
                    spreadsheet = client.open_by_key(spreadsheets[0]['id'])
                else:
                    return None, 'No spreadsheets found in account.'
        
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            return None, f"Sheet '{sheet_name}' not found in spreadsheet."
        
        all_values = worksheet.get_all_values()
        if len(all_values) < 2:
            return None, 'Sheet is empty or has no data rows.'
        
        if sheet_name.upper() == 'EMAIL_DATA':
            data_rows = all_values[1:] if len(all_values) > 1 else []
            mapped_data = []
            for row in data_rows:
                if len(row) > 15 and str(row[8]).strip() != '':
                    mapped_row = {
                        'S/N': len(mapped_data) + 1,
                        'Train Number': str(row[8]).strip(),
                        'From Station': str(row[9]).strip() if len(row) > 9 else '',
                        'To Station': str(row[10]).strip() if len(row) > 10 else '',
                        'Date of Journey': str(row[11]).strip() if len(row) > 11 else '',
                        'Class': str(row[12]).strip() if len(row) > 12 else '',
                        'Total Seats': str(row[15]).strip() if len(row) > 15 else ''
                    }
                    mapped_data.append(mapped_row)
            df = pd.DataFrame(mapped_data)
            return df, None
        else:
            headers = all_values[0] if all_values else [f'Col_{i}' for i in range(len(all_values[1]) if len(all_values) > 1 else 0)]
            data_rows = all_values[1:] if len(all_values) > 1 else []
            if data_rows:
                max_cols = max(len(row) for row in data_rows)
                headers = headers + [f'Col_{i}' for i in range(len(headers), max_cols)]
                for row in data_rows:
                    while len(row) < max_cols:
                        row.append('')
                df = pd.DataFrame(data_rows, columns=headers[:max_cols])
            else:
                df = pd.DataFrame(columns=headers)
            return df, None
    except Exception as e:
        return None, str(e)

@st.cache_data(ttl=600, show_spinner=False)
def fetch_weather(city):
    try:
        api_key = None
        try:
            api_key = st.secrets['openweather_api_key']
        except:
            api_key = 'demo'
        
        if not api_key or api_key == 'demo':
            return {
                'main': {'temp': 32, 'feels_like': 35, 'humidity': 65},
                'weather': [{'main': 'Clear', 'description': 'clear sky', 'icon': '01d'}],
                'wind': {'speed': 3.5},
                'name': city,
                'sys': {'sunrise': int(datetime.now().timestamp()), 'sunset': int((datetime.now() + timedelta(hours=12)).timestamp())},
                'dt': int(datetime.now().timestamp()),
                'clouds': {'all': 10}
            }
        
        url = f'https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric'
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return None
    except:
        return None

def get_weather_type(weather_data):
    if not weather_data:
        return 'clear-day'
    w = weather_data.get('weather', [{}])[0].get('main', 'Clear').lower()
    desc = weather_data.get('weather', [{}])[0].get('description', '').lower()
    icon = weather_data.get('weather', [{}])[0].get('icon', '01d')
    is_night = icon.endswith('n')
    
    if 'thunder' in w or 'thunder' in desc:
        return 'thunderstorm'
    elif 'rain' in w or 'drizzle' in w or 'rain' in desc:
        return 'rain-night' if is_night else 'rain'
    elif 'snow' in w:
        return 'snow'
    elif 'cloud' in w or weather_data.get('clouds', {}).get('all', 0) > 50:
        return 'cloudy-night' if is_night else 'cloudy'
    elif 'mist' in w or 'fog' in w or 'haze' in w:
        return 'fog'
    elif is_night:
        return 'clear-night'
    else:
        temp = weather_data.get('main', {}).get('temp', 25)
        if temp > 35:
            return 'heat'
        return 'clear-day'

def inject_weather_css(weather_type):
    css = '''
    <style>
    .stApp { background: transparent !important; }
    .weather-bg {
        position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
        z-index: -1; overflow: hidden; pointer-events: none;
    }
    .bg-clear-day {
        background: linear-gradient(135deg, #4facfe 0%, #00f2fe 50%, #43e97b 100%);
    }
    .bg-clear-day .sun {
        position: absolute; top: 5%; right: 10%;
        width: 120px; height: 120px;
        background: radial-gradient(circle, #ffd700 30%, #ff8c00 70%, transparent 100%);
        border-radius: 50%;
        box-shadow: 0 0 60px #ffd700, 0 0 100px #ff8c00;
        animation: sunPulse 4s ease-in-out infinite;
    }
    @keyframes sunPulse {
        0%, 100% { transform: scale(1); opacity: 0.9; }
        50% { transform: scale(1.1); opacity: 1; }
    }
    .bg-clear-day .cloud {
        position: absolute; background: rgba(255,255,255,0.8);
        border-radius: 100px; animation: floatCloud 20s linear infinite;
    }
    @keyframes floatCloud {
        0% { transform: translateX(-200px); }
        100% { transform: translateX(calc(100vw + 200px)); }
    }
    .bg-clear-night {
        background: linear-gradient(135deg, #0c0c2e 0%, #1a1a3e 50%, #16213e 100%);
    }
    .bg-clear-night .star {
        position: absolute; width: 2px; height: 2px;
        background: white; border-radius: 50%;
        animation: twinkle 3s ease-in-out infinite;
    }
    @keyframes twinkle {
        0%, 100% { opacity: 0.3; } 50% { opacity: 1; }
    }
    .bg-clear-night .moon {
        position: absolute; top: 8%; right: 12%;
        width: 80px; height: 80px;
        background: radial-gradient(circle at 30% 30%, #fff9e6, #e6e6e6);
        border-radius: 50%;
        box-shadow: 0 0 40px rgba(255,255,255,0.3), 0 0 80px rgba(255,255,255,0.1);
    }
    .bg-rain {
        background: linear-gradient(135deg, #203a43 0%, #2c5364 100%);
    }
    .bg-rain .raindrop {
        position: absolute; width: 2px;
        background: linear-gradient(to bottom, transparent, rgba(174,194,224,0.8));
        animation: fall linear infinite; border-radius: 2px;
    }
    @keyframes fall {
        0% { transform: translateY(-100px); opacity: 1; }
        100% { transform: translateY(100vh); opacity: 0.3; }
    }
    .bg-rain .cloud-dark {
        position: absolute; background: rgba(80,90,110,0.9);
        border-radius: 100px; animation: driftCloud 25s linear infinite;
    }
    @keyframes driftCloud {
        0% { transform: translateX(-300px); }
        100% { transform: translateX(calc(100vw + 300px)); }
    }
    .bg-rain-night {
        background: linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%);
    }
    .bg-rain-night .raindrop {
        position: absolute; width: 2px;
        background: linear-gradient(to bottom, transparent, rgba(150,170,200,0.6));
        animation: fall linear infinite;
    }
    .bg-rain-night .lightning {
        position: absolute; top: 0; left: 0; width: 100%; height: 100%;
        background: rgba(255,255,255,0);
        animation: lightning 8s infinite; pointer-events: none;
    }
    @keyframes lightning {
        0%, 90%, 100% { background: rgba(255,255,255,0); }
        91% { background: rgba(255,255,255,0.3); }
        92% { background: rgba(255,255,255,0); }
        93% { background: rgba(255,255,255,0.2); }
        94% { background: rgba(255,255,255,0); }
    }
    .bg-thunderstorm {
        background: linear-gradient(135deg, #141e30 0%, #243b55 100%);
    }
    .bg-thunderstorm .raindrop-heavy {
        position: absolute; width: 3px;
        background: linear-gradient(to bottom, transparent, rgba(180,190,210,0.9));
        animation: fallHeavy 0.8s linear infinite;
    }
    @keyframes fallHeavy {
        0% { transform: translateY(-100px) translateX(0); opacity: 1; }
        100% { transform: translateY(100vh) translateX(-20px); opacity: 0.3; }
    }
    .bg-thunderstorm .flash {
        position: absolute; top: 0; left: 0; width: 100%; height: 100%;
        background: rgba(255,255,255,0);
        animation: thunderFlash 5s infinite;
    }
    @keyframes thunderFlash {
        0%, 85%, 100% { background: rgba(255,255,255,0); }
        86% { background: rgba(255,255,255,0.6); }
        87% { background: rgba(255,255,255,0); }
        88% { background: rgba(255,255,255,0.4); }
        89% { background: rgba(255,255,255,0); }
    }
    .bg-cloudy {
        background: linear-gradient(135deg, #757f9a 0%, #d7dde8 100%);
    }
    .bg-cloudy .cloud-big {
        position: absolute; background: rgba(255,255,255,0.7);
        border-radius: 100px; animation: floatSlow 30s linear infinite;
    }
    @keyframes floatSlow {
        0% { transform: translateX(-400px); }
        100% { transform: translateX(calc(100vw + 400px)); }
    }
    .bg-cloudy-night {
        background: linear-gradient(135deg, #1e1e2f 0%, #2d2d44 100%);
    }
    .bg-cloudy-night .cloud-dim {
        position: absolute; background: rgba(100,100,120,0.5);
        border-radius: 100px; animation: floatSlow 35s linear infinite;
    }
    .bg-heat {
        background: linear-gradient(135deg, #ff512f 0%, #dd2476 50%, #ff9966 100%);
    }
    .bg-heat .heat-wave {
        position: absolute; bottom: 0; left: 0; width: 100%; height: 30%;
        background: linear-gradient(to top, rgba(255,100,0,0.3), transparent);
        animation: heatRise 3s ease-in-out infinite;
    }
    @keyframes heatRise {
        0%, 100% { transform: translateY(0) scaleY(1); opacity: 0.5; }
        50% { transform: translateY(-20px) scaleY(1.2); opacity: 0.8; }
    }
    .bg-heat .sun-hot {
        position: absolute; top: 5%; right: 10%;
        width: 140px; height: 140px;
        background: radial-gradient(circle, #ff4500 20%, #ff8c00 50%, #ffd700 80%, transparent 100%);
        border-radius: 50%;
        box-shadow: 0 0 80px #ff4500, 0 0 150px #ff8c00;
        animation: sunBurn 3s ease-in-out infinite;
    }
    @keyframes sunBurn {
        0%, 100% { transform: scale(1); filter: brightness(1); }
        50% { transform: scale(1.15); filter: brightness(1.3); }
    }
    .bg-snow {
        background: linear-gradient(135deg, #83a4d4 0%, #b6fbff 100%);
    }
    .bg-snow .snowflake {
        position: absolute; color: white; font-size: 1em;
        animation: snowfall linear infinite;
        text-shadow: 0 0 5px rgba(255,255,255,0.8);
    }
    @keyframes snowfall {
        0% { transform: translateY(-100px) rotate(0deg); opacity: 1; }
        100% { transform: translateY(100vh) rotate(360deg); opacity: 0.3; }
    }
    .bg-fog {
        background: linear-gradient(135deg, #3e5151 0%, #decba4 100%);
    }
    .bg-fog .fog-layer {
        position: absolute; width: 200%; height: 100%;
        background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.3) 25%, rgba(255,255,255,0.5) 50%, rgba(255,255,255,0.3) 75%, transparent 100%);
        animation: fogMove 15s ease-in-out infinite;
    }
    @keyframes fogMove {
        0%, 100% { transform: translateX(-50%); }
        50% { transform: translateX(0%); }
    }
    .stDataFrame, .stTable, [data-testid='stDataFrameResizable'] {
        background: rgba(255, 255, 255, 0.12) !important;
        backdrop-filter: blur(12px) !important;
        -webkit-backdrop-filter: blur(12px) !important;
        border-radius: 12px !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
    }
    .stDataFrame th, .stTable th {
        background: rgba(0, 0, 0, 0.3) !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        text-align: center !important;
        border-bottom: 2px solid rgba(255,255,255,0.3) !important;
    }
    .stDataFrame td, .stTable td {
        background: rgba(255, 255, 255, 0.05) !important;
        color: #ffffff !important;
        border-bottom: 1px solid rgba(255,255,255,0.1) !important;
    }
    .stDataFrame tr:hover td {
        background: rgba(255, 255, 255, 0.15) !important;
    }
    [data-testid='stSidebar'] {
        background: rgba(0, 0, 0, 0.25) !important;
        backdrop-filter: blur(15px) !important;
        -webkit-backdrop-filter: blur(15px) !important;
        border-right: 1px solid rgba(255,255,255,0.15) !important;
    }
    [data-testid='stSidebar'] .stMarkdown, [data-testid='stSidebar'] label,
    [data-testid='stSidebar'] .stSelectbox label {
        color: #ffffff !important;
    }
    .glass-card {
        background: rgba(255, 255, 255, 0.1) !important;
        backdrop-filter: blur(15px) !important;
        -webkit-backdrop-filter: blur(15px) !important;
        border-radius: 16px !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        padding: 20px !important;
        margin: 10px 0 !important;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2) !important;
    }
    .glass-card h1, .glass-card h2, .glass-card h3,
    .glass-card p, .glass-card span, .glass-card div {
        color: #ffffff !important;
    }
    .stButton > button {
        background: rgba(255, 255, 255, 0.15) !important;
        backdrop-filter: blur(10px) !important;
        border: 1px solid rgba(255, 255, 255, 0.3) !important;
        color: #ffffff !important;
        border-radius: 10px !important;
        font-weight: 500 !important;
        transition: all 0.3s ease !important;
    }
    .stButton > button:hover {
        background: rgba(255, 255, 255, 0.3) !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 5px 20px rgba(0,0,0,0.3) !important;
    }
    .stTextInput > div > div > input,
    .stSelectbox > div > div > div {
        background: rgba(255, 255, 255, 0.1) !important;
        backdrop-filter: blur(10px) !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        color: #ffffff !important;
        border-radius: 10px !important;
    }
    .stTextInput > div > div > input::placeholder {
        color: rgba(255,255,255,0.5) !important;
    }
    .streamlit-expanderHeader {
        background: rgba(255, 255, 255, 0.1) !important;
        backdrop-filter: blur(10px) !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        border-radius: 10px !important;
        color: #ffffff !important;
    }
    .streamlit-expanderContent {
        background: rgba(0, 0, 0, 0.2) !important;
        backdrop-filter: blur(10px) !important;
        border-radius: 0 0 10px 10px !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-top: none !important;
    }
    .stTabs [data-baseweb='tab-list'] {
        background: rgba(255, 255, 255, 0.1) !important;
        backdrop-filter: blur(10px) !important;
        border-radius: 10px 10px 0 0 !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        border-bottom: none !important;
    }
    .stTabs [data-baseweb='tab'] { color: rgba(255,255,255,0.7) !important; }
    .stTabs [data-baseweb='tab-highlight'] { background: rgba(255,255,255,0.5) !important; }
    .stTabs [aria-selected='true'] { color: #ffffff !important; }
    [data-testid='stMetricValue'] {
        color: #ffffff !important; font-weight: 700 !important;
    }
    [data-testid='stMetricLabel'] { color: rgba(255,255,255,0.8) !important; }
    [data-testid='stMetricDelta'] { color: #90EE90 !important; }
    .stAlert {
        background: rgba(255, 255, 255, 0.1) !important;
        backdrop-filter: blur(10px) !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        border-radius: 12px !important;
    }
    @media print {
        .weather-bg, .weather-bg * { display: none !important; }
        .stApp { background: white !important; }
        .glass-card, .stDataFrame, .stTable, [data-testid='stDataFrameResizable'],
        [data-testid='stSidebar'], .streamlit-expanderHeader, .streamlit-expanderContent {
            background: white !important; color: black !important;
            border: 1px solid #ccc !important; backdrop-filter: none !important;
        }
        .glass-card h1, .glass-card h2, .glass-card h3,
        .glass-card p, .glass-card span, .glass-card div,
        .stDataFrame th, .stDataFrame td, .stTable th, .stTable td {
            color: black !important;
        }
        .stButton > button { display: none !important; }
    }
    ::-webkit-scrollbar { width: 8px; }
    ::-webkit-scrollbar-track { background: rgba(0,0,0,0.1); }
    ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.3); border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.5); }
    </style>
    '''
    elements = generate_weather_elements(weather_type)
    full_html = css + f'<div class="weather-bg bg-{weather_type}">{elements}</div>'
    st.markdown(full_html, unsafe_allow_html=True)

def generate_weather_elements(weather_type):
    elements = []
    random.seed(42)

    if weather_type == 'clear-day':
        elements.append('<div class="sun"></div>')
        for i in range(3):
            top = 10 + i * 15
            delay = i * 7
            duration = 20 + i * 5
            width = 100 + i * 40
            elements.append(f'<div class="cloud" style="top:{top}%;width:{width}px;height:40px;animation-duration:{duration}s;animation-delay:-{delay}s;"></div>')

    elif weather_type == 'clear-night':
        elements.append('<div class="moon"></div>')
        for i in range(50):
            top = random.randint(0, 60)
            left = random.randint(0, 100)
            delay = random.uniform(0, 3)
            elements.append(f'<div class="star" style="top:{top}%;left:{left}%;animation-delay:-{delay:.1f}s;"></div>')

    elif weather_type == 'rain':
        elements.append('<div class="cloud-dark" style="top:5%;width:300px;height:80px;animation-duration:25s;"></div>')
        elements.append('<div class="cloud-dark" style="top:10%;width:250px;height:60px;animation-duration:30s;animation-delay:-10s;"></div>')
        for i in range(60):
            left = (i * 1.7) % 100
            delay = (i * 0.3) % 2
            duration = 0.8 + (i % 3) * 0.2
            height = 80 + (i % 5) * 20
            elements.append(f'<div class="raindrop" style="left:{left}%;height:{height}px;animation-duration:{duration}s;animation-delay:-{delay:.1f}s;"></div>')

    elif weather_type == 'rain-night':
        elements.append('<div class="lightning"></div>')
        elements.append('<div class="cloud-dark" style="top:5%;width:350px;height:90px;animation-duration:28s;"></div>')
        for i in range(50):
            left = (i * 2) % 100
            delay = (i * 0.4) % 3
            duration = 1 + (i % 4) * 0.2
            height = 60 + (i % 5) * 15
            elements.append(f'<div class="raindrop" style="left:{left}%;height:{height}px;animation-duration:{duration}s;animation-delay:-{delay:.1f}s;"></div>')

    elif weather_type == 'thunderstorm':
        elements.append('<div class="flash"></div>')
        elements.append('<div class="cloud-dark" style="top:3%;width:400px;height:100px;animation-duration:20s;"></div>')
        elements.append('<div class="cloud-dark" style="top:8%;width:300px;height:70px;animation-duration:25s;animation-delay:-8s;"></div>')
        for i in range(80):
            left = (i * 1.3) % 100
            delay = (i * 0.2) % 1.5
            duration = 0.6 + (i % 3) * 0.15
            height = 100 + (i % 6) * 25
            elements.append(f'<div class="raindrop-heavy" style="left:{left}%;height:{height}px;animation-duration:{duration}s;animation-delay:-{delay:.1f}s;"></div>')

    elif weather_type == 'cloudy':
        for i in range(5):
            top = 5 + i * 12
            delay = i * 6
            duration = 25 + i * 8
            width = 200 + i * 60
            elements.append(f'<div class="cloud-big" style="top:{top}%;width:{width}px;height:60px;animation-duration:{duration}s;animation-delay:-{delay}s;"></div>')

    elif weather_type == 'cloudy-night':
        elements.append('<div class="moon" style="opacity:0.6;"></div>')
        for i in range(4):
            top = 5 + i * 15
            delay = i * 8
            duration = 30 + i * 10
            width = 250 + i * 50
            elements.append(f'<div class="cloud-dim" style="top:{top}%;width:{width}px;height:70px;animation-duration:{duration}s;animation-delay:-{delay}s;"></div>')

    elif weather_type == 'heat':
        elements.append('<div class="sun-hot"></div>')
        elements.append('<div class="heat-wave" style="left:0%;"></div>')
        elements.append('<div class="heat-wave" style="left:33%;animation-delay:-1s;"></div>')
        elements.append('<div class="heat-wave" style="left:66%;animation-delay:-2s;"></div>')

    elif weather_type == 'snow':
        snow_chars = ['❄', '❅', '❆', '•']
        for i in range(40):
            left = (i * 2.5) % 100
            delay = (i * 0.5) % 5
            duration = 3 + (i % 4) * 1.5
            size = 0.8 + (i % 4) * 0.4
            char = snow_chars[i % 4]
            elements.append(f'<div class="snowflake" style="left:{left}%;font-size:{size}em;animation-duration:{duration}s;animation-delay:-{delay:.1f}s;">{char}</div>')

    elif weather_type == 'fog':
        for i in range(3):
            delay = i * 5
            elements.append(f'<div class="fog-layer" style="top:{20 + i * 25}%;animation-delay:-{delay}s;"></div>')

    return ''.join(elements)

def display_weather_card(weather_data, city):
    if not weather_data:
        st.markdown('''
        <div class='glass-card' style='text-align:center;'>
            <h3>🌡️ Weather Unavailable</h3>
            <p>Unable to fetch weather data. Please check your API key.</p>
        </div>
        ''', unsafe_allow_html=True)
        return
    
    main = weather_data.get('main', {})
    w = weather_data.get('weather', [{}])[0]
    wind = weather_data.get('wind', {})
    
    temp = main.get('temp', '--')
    feels = main.get('feels_like', '--')
    humidity = main.get('humidity', '--')
    desc = w.get('description', 'N/A').title()
    icon = w.get('icon', '01d')
    wind_speed = wind.get('speed', '--')
    icon_url = f'https://openweathermap.org/img/wn/{icon}@2x.png'
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(f'''
        <div class='glass-card' style='text-align:center;'>
            <h2>🌍 {city}</h2>
            <img src='{icon_url}' style='width:80px;height:80px;filter:drop-shadow(0 0 10px rgba(255,255,255,0.5));'>
            <h1 style='font-size:3em;margin:0;'>{temp}°C</h1>
            <p style='font-size:1.2em;text-transform:capitalize;'>{desc}</p>
            <div style='display:flex;justify-content:space-around;margin-top:15px;'>
                <div><p style='margin:0;font-size:0.9em;opacity:0.8;'>Feels Like</p>
                <p style='margin:0;font-size:1.3em;font-weight:600;'>{feels}°C</p></div>
                <div><p style='margin:0;font-size:0.9em;opacity:0.8;'>Humidity</p>
                <p style='margin:0;font-size:1.3em;font-weight:600;'>{humidity}%</p></div>
                <div><p style='margin:0;font-size:0.9em;opacity:0.8;'>Wind</p>
                <p style='margin:0;font-size:1.3em;font-weight:600;'>{wind_speed} m/s</p></div>
            </div>
        </div>
        ''', unsafe_allow_html=True)

def display_data_table(df, sheet_name):
    if df is None or df.empty:
        st.markdown('''
        <div class='glass-card' style='text-align:center;padding:40px;'>
            <h3>📭 No Data Available</h3>
            <p>The selected sheet is empty or data could not be loaded.</p>
        </div>
        ''', unsafe_allow_html=True)
        return
    
    st.markdown(f'''
    <div class='glass-card'>
        <h3>📊 {sheet_name} — Data Overview</h3>
        <p style='opacity:0.8;'>Total Records: <strong>{len(df)}</strong> | Columns: <strong>{len(df.columns)}</strong></p>
    </div>
    ''', unsafe_allow_html=True)
    
    column_config = {}
    for col in df.columns:
        if 'seat' in col.lower() or 'total' in col.lower():
            column_config[col] = st.column_config.NumberColumn(col)
        elif 'date' in col.lower() or 'doj' in col.lower():
            column_config[col] = st.column_config.TextColumn(col)
        elif 'train' in col.lower():
            column_config[col] = st.column_config.TextColumn(col)
        else:
            column_config[col] = st.column_config.TextColumn(col)
    
    st.dataframe(
        df,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=min(500, 50 + len(df) * 35)
    )
    
    csv = df.to_csv(index=False).encode('utf-8')
    col1, col2, col3 = st.columns([2, 1, 2])
    with col2:
        st.download_button(
            label='📥 Download CSV',
            data=csv,
            file_name=f'{sheet_name}_data.csv',
            mime='text/csv',
            use_container_width=True
        )

def display_analytics(df, sheet_name):
    if df is None or df.empty:
        return
    
    st.markdown('''
    <div class='glass-card'>
        <h3>📈 Analytics Dashboard</h3>
    </div>
    ''', unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        unique_trains = df['Train Number'].nunique() if 'Train Number' in df.columns else 0
        st.metric('Total Trains', unique_trains)
    with col2:
        total_seats = 0
        if 'Total Seats' in df.columns:
            try:
                total_seats = pd.to_numeric(df['Total Seats'], errors='coerce').sum()
            except:
                pass
        st.metric('Total Seats', int(total_seats) if not pd.isna(total_seats) else 0)
    with col3:
        unique_routes = 0
        if 'From Station' in df.columns and 'To Station' in df.columns:
            routes = df['From Station'].astype(str) + ' → ' + df['To Station'].astype(str)
            unique_routes = routes.nunique()
        st.metric('Unique Routes', unique_routes)
    with col4:
        unique_classes = df['Class'].nunique() if 'Class' in df.columns else 0
        st.metric('Classes', unique_classes)
    
    if 'Class' in df.columns and not df['Class'].empty:
        st.markdown("<div class='glass-card'><h4>Class-wise Distribution</h4></div>", unsafe_allow_html=True)
        class_counts = df['Class'].value_counts().reset_index()
        class_counts.columns = ['Class', 'Count']
        st.bar_chart(class_counts.set_index('Class'), use_container_width=True, color=['#4facfe'])
    
    if 'Train Number' in df.columns and not df['Train Number'].empty:
        st.markdown("<div class='glass-card'><h4>Train-wise Demand</h4></div>", unsafe_allow_html=True)
        train_counts = df['Train Number'].value_counts().head(10).reset_index()
        train_counts.columns = ['Train Number', 'Requests']
        st.bar_chart(train_counts.set_index('Train Number'), use_container_width=True, color=['#43e97b'])

def main():
    city = st.session_state.get('city', 'New Delhi')
    weather_data = fetch_weather(city)
    weather_type = get_weather_type(weather_data)
    inject_weather_css(weather_type)
    
    with st.sidebar:
        st.markdown('''
        <div style='text-align:center;margin-bottom:20px;'>
            <h1 style='font-size:2em;'>🚂 AI-EQMS</h1>
            <p style='opacity:0.7;'>Smart Railway Management</p>
        </div>
        ''', unsafe_allow_html=True)
        
        st.markdown("<hr style='border-color:rgba(255,255,255,0.2);'>", unsafe_allow_html=True)
        
        city_input = st.text_input('🌍 City for Weather', value=city, key='city_input')
        if city_input != city:
            st.session_state.city = city_input
            st.rerun()
        
        st.markdown("<hr style='border-color:rgba(255,255,255,0.2);'>", unsafe_allow_html=True)
        
        sheet_options = ['EMAIL_DATA', 'EQ', 'DATA', 'NOTE']
        selected = st.selectbox('📑 Select Sheet', sheet_options, index=0)
        
        st.markdown("<hr style='border-color:rgba(255,255,255,0.2);'>", unsafe_allow_html=True)
        
        st.markdown("<h4 style='color:white;'>Navigation</h4>", unsafe_allow_html=True)
        nav = st.radio('', ['Data Table', 'Analytics', 'Weather Info', 'About'], label_visibility='collapsed')
        
        st.markdown("<hr style='border-color:rgba(255,255,255,0.2);'>", unsafe_allow_html=True)
        
        if st.button('🔄 Refresh Data', use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        
        st.markdown('''
        <button onclick="window.print()" style="
            width:100%;padding:10px;border-radius:10px;
            background:rgba(255,255,255,0.15);border:1px solid rgba(255,255,255,0.3);
            color:white;cursor:pointer;font-size:1em;margin-top:10px;
        ">🖨️ Print Page</button>
        ''', unsafe_allow_html=True)
    
    st.markdown('''
    <div style='text-align:center;margin-bottom:30px;'>
        <h1 style='font-size:2.5em;text-shadow:0 0 20px rgba(0,0,0,0.5);'>🚆 AI-EQMS Hub</h1>
        <p style='font-size:1.1em;opacity:0.8;'>Intelligent Extra Quota Management System</p>
    </div>
    ''', unsafe_allow_html=True)
    
    if nav == 'Data Table':
        with st.spinner('Loading sheet data...'):
            df, error = get_sheet_data(selected)
        
        if error:
            st.error(f'Error loading data: {error}')
            st.info('Please ensure your Google Sheets credentials are configured correctly.')
        else:
            display_data_table(df, selected)
    
    elif nav == 'Analytics':
        with st.spinner('Loading analytics...'):
            df, error = get_sheet_data(selected)
        
        if error:
            st.error(f'Error: {error}')
        else:
            display_analytics(df, selected)
    
    elif nav == 'Weather Info':
        display_weather_card(weather_data, city)
        
        st.markdown('''
        <div class='glass-card' style='margin-top:20px;'>
            <h4>🌤️ Weather Effects</h4>
            <p>The background automatically adapts to current weather conditions:</p>
            <ul>
                <li><strong>Clear Day:</strong> Bright blue sky with animated sun and floating clouds</li>
                <li><strong>Clear Night:</strong> Dark sky with twinkling stars and moon</li>
                <li><strong>Rain:</strong> Dark clouds with animated rainfall</li>
                <li><strong>Thunderstorm:</strong> Heavy rain with lightning flashes</li>
                <li><strong>Cloudy:</strong> Overcast sky with drifting clouds</li>
                <li><strong>Heat:</strong> Hot orange tones with pulsing sun and heat waves</li>
                <li><strong>Snow:</strong> Cool blue tones with falling snowflakes</li>
                <li><strong>Fog:</strong> Misty atmosphere with drifting fog layers</li>
            </ul>
            <p style='opacity:0.8;margin-top:10px;'>💡 <em>Background is hidden when printing for clean output.</em></p>
        </div>
        ''', unsafe_allow_html=True)
    
    elif nav == 'About':
        st.markdown('''
        <div class='glass-card'>
            <h3>🚂 About AI-EQMS Hub</h3>
            <p>AI-powered Extra Quota Management System for Indian Railways.</p>
            
            <h4>Features:</h4>
            <ul>
                <li>📊 Real-time Google Sheets integration</li>
                <li>🌤️ Dynamic weather-responsive backgrounds</li>
                <li>📈 Interactive analytics and visualizations</li>
                <li>🖨️ Print-friendly output (no backgrounds)</li>
                <li>📱 Fully responsive glass-morphism design</li>
                <li>🔍 Smart data filtering and search</li>
            </ul>
            
            <h4>EMAIL_DATA Column Mapping:</h4>
            <table style='width:100%;border-collapse:collapse;margin-top:10px;'>
                <tr style='background:rgba(0,0,0,0.3);'>
                    <th style='padding:8px;border:1px solid rgba(255,255,255,0.2);'>Field</th>
                    <th style='padding:8px;border:1px solid rgba(255,255,255,0.2);'>Column</th>
                </tr>
                <tr><td style='padding:8px;border:1px solid rgba(255,255,255,0.1);'>Train Number</td>
                    <td style='padding:8px;border:1px solid rgba(255,255,255,0.1);'>I (Row 2+)</td></tr>
                <tr style='background:rgba(0,0,0,0.1);'><td style='padding:8px;border:1px solid rgba(255,255,255,0.1);'>From Station</td>
                    <td style='padding:8px;border:1px solid rgba(255,255,255,0.1);'>J (Row 2+)</td></tr>
                <tr><td style='padding:8px;border:1px solid rgba(255,255,255,0.1);'>To Station</td>
                    <td style='padding:8px;border:1px solid rgba(255,255,255,0.1);'>K (Row 2+)</td></tr>
                <tr style='background:rgba(0,0,0,0.1);'><td style='padding:8px;border:1px solid rgba(255,255,255,0.1);'>Date of Journey</td>
                    <td style='padding:8px;border:1px solid rgba(255,255,255,0.1);'>L (Row 2+)</td></tr>
                <tr><td style='padding:8px;border:1px solid rgba(255,255,255,0.1);'>Class</td>
                    <td style='padding:8px;border:1px solid rgba(255,255,255,0.1);'>M (Row 2+)</td></tr>
                <tr style='background:rgba(0,0,0,0.1);'><td style='padding:8px;border:1px solid rgba(255,255,255,0.1);'>Total Seats</td>
                    <td style='padding:8px;border:1px solid rgba(255,255,255,0.1);'>P (Row 2+)</td></tr>
            </table>
        </div>
        ''', unsafe_allow_html=True)

if __name__ == '__main__':
    main()
