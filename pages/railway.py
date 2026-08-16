# ============================================
# WEATHER FEATURE (New)
# ============================================
import requests
from utils.config import WEATHER_API_KEY, WEATHER_BASE_URL

def get_weather(city_name):
    """Get current weather for a city using OpenWeatherMap API"""
    if not WEATHER_API_KEY:
        return {"error": "Weather API key not configured"}
    
    try:
        url = f"{WEATHER_BASE_URL}?q={city_name}&appid={WEATHER_API_KEY}&units=metric"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "city": data.get("name", "N/A"),
                "country": data.get("sys", {}).get("country", "N/A"),
                "temperature": data.get("main", {}).get("temp", "N/A"),
                "feels_like": data.get("main", {}).get("feels_like", "N/A"),
                "humidity": data.get("main", {}).get("humidity", "N/A"),
                "description": data.get("weather", [{}])[0].get("description", "N/A"),
                "icon": data.get("weather", [{}])[0].get("icon", "01d"),
                "wind_speed": data.get("wind", {}).get("speed", "N/A"),
                "pressure": data.get("main", {}).get("pressure", "N/A")
            }
        else:
            return {"error": f"API Error: {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def format_weather_result(data):
    """Format weather data for display"""
    if data.get("error"):
        return f"❌ {data['error']}"
    
    icon_url = f"https://openweathermap.org/img/wn/{data['icon']}@2x.png"
    
    msg = f"""
## 🌤️ Weather: {data['city']}, {data['country']}

**Temperature:** {data['temperature']}°C (feels like {data['feels_like']}°C)
**Humidity:** {data['humidity']}%
**Pressure:** {data['pressure']} hPa
**Wind Speed:** {data['wind_speed']} m/s
**Description:** {data['description'].capitalize()}

![Weather Icon]({icon_url})
"""
    return msg
