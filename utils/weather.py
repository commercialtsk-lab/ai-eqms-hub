import requests
import streamlit as st
from datetime import datetime

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
    # ✅ FIX: Directly read from st.secrets
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
        st.info("🔑 Weather API key not set. Add WEATHER_API_KEY to secrets.toml")
        st.caption("Get free key from: https://openweathermap.org/api")
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
        st.caption("Please check city name or try again later.")
