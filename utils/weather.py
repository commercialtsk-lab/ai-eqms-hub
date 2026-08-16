import requests
import streamlit as st
from datetime import datetime

def get_weather(city_name, api_key):
    """Fetch weather data from OpenWeatherMap API"""
    if not api_key:
        return None
    
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={api_key}&units=metric"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {
                'city': data.get('name', city_name),
                'country': data.get('sys', {}).get('country', ''),
                'temp': data.get('main', {}).get('temp', 0),
                'feels_like': data.get('main', {}).get('feels_like', 0),
                'humidity': data.get('main', {}).get('humidity', 0),
                'description': data.get('weather', [{}])[0].get('description', ''),
                'icon': data.get('weather', [{}])[0].get('icon', ''),
                'wind_speed': data.get('wind', {}).get('speed', 0),
                'pressure': data.get('main', {}).get('pressure', 0)
            }
        else:
            return None
    except Exception as e:
        return None

def get_weather_emoji(description):
    """Return emoji for weather condition"""
    desc = description.lower()
    if 'clear' in desc or 'sunny' in desc:
        return '☀️'
    elif 'cloud' in desc:
        return '☁️'
    elif 'rain' in desc or 'drizzle' in desc:
        return '🌧️'
    elif 'thunder' in desc:
        return '⛈️'
    elif 'snow' in desc:
        return '❄️'
    elif 'mist' in desc or 'fog' in desc:
        return '🌫️'
    elif 'haze' in desc:
        return '🌥️'
    else:
        return '🌡️'

def render_weather_widget():
    """Render weather widget in sidebar"""
    WEATHER_API_KEY = st.secrets.get("WEATHER_API_KEY", "")
    
    st.markdown("---")
    st.markdown("### 🌤️ Weather")
    
    # City input with default
    default_city = "Tinsukia"
    if 'weather_city' not in st.session_state:
        st.session_state.weather_city = default_city
    
    # City selection with custom input
    city_options = ["Tinsukia", "Dibrugarh", "Guwahati", "New Delhi", "Mumbai", "Kolkata", "Chennai", "Bangalore", "Custom..."]
    
    selected_option = st.selectbox(
        "Select City",
        city_options,
        index=city_options.index(st.session_state.weather_city) if st.session_state.weather_city in city_options else city_options.index("Custom..."),
        key="weather_city_select",
        help="Select a city or choose 'Custom...' to enter your own"
    )
    
    if selected_option == "Custom...":
        custom_city = st.text_input(
            "Enter City Name",
            value="Tinsukia" if st.session_state.weather_city not in city_options else st.session_state.weather_city,
            key="weather_custom_city",
            help="Enter any city name (e.g., 'London', 'New York')"
        )
        if custom_city:
            st.session_state.weather_city = custom_city
    else:
        st.session_state.weather_city = selected_option
    
    if not WEATHER_API_KEY:
        st.info("🔑 Weather API key not set. Add WEATHER_API_KEY to secrets.toml")
        st.caption("Get free key from: https://openweathermap.org/api")
        return
    
    if st.button("🔄 Refresh Weather", key="weather_refresh", help="Get latest weather data"):
        st.rerun()
    
    # Fetch weather
    with st.spinner("Fetching weather..."):
        weather = get_weather(st.session_state.weather_city, WEATHER_API_KEY)
    
    if weather:
        emoji = get_weather_emoji(weather['description'])
        
        # Display weather with emojis
        st.markdown(f"""
        <div style="background: rgba(255,255,255,0.05); border-radius: 12px; padding: 15px; margin: 5px 0;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 3rem;">{emoji}</span>
                <div>
                    <div style="font-size: 1.8rem; font-weight: 700;">{weather['temp']:.1f}°C</div>
                    <div style="font-size: 0.9rem; opacity: 0.8;">{weather['description'].title()}</div>
                </div>
            </div>
            <div style="font-size: 1.1rem; font-weight: 600; margin-top: 5px;">
                📍 {weather['city']}, {weather['country']}
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 5px; margin-top: 8px; font-size: 0.85rem;">
                <div>🌡️ Feels: {weather['feels_like']:.1f}°C</div>
                <div>💧 Humidity: {weather['humidity']}%</div>
                <div>💨 Wind: {weather['wind_speed']:.1f} m/s</div>
                <div>📊 Pressure: {weather['pressure']} hPa</div>
            </div>
            <div style="font-size: 0.7rem; opacity: 0.6; margin-top: 5px;">
                Last updated: {datetime.now().strftime('%H:%M:%S')}
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.error(f"❌ Could not fetch weather for '{st.session_state.weather_city}'")
        st.caption("Please check city name or try again later.")
