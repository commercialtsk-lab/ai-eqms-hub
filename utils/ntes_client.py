import re
from datetime import datetime

try:
    from ntes import NTESClient
    ntes_client = NTESClient()
    NTES_AVAILABLE = True
except ImportError:
    NTES_AVAILABLE = False

def safe_list(data, key):
    val = data.get(key) if data else None
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]

def safe_str(val, default='N/A'):
    return str(val) if val is not None else default

def get_pnr_status(pnr):
    if not NTES_AVAILABLE:
        return {"error": "NTES library not installed"}
    try:
        response = ntes_client.pnr_status(pnr)
        if not response:
            return None
        err_msg = response.get('errorMessage', '')
        if err_msg and 'FLUSHED' in str(err_msg).upper():
            return {"error": "FLUSHED_PNR"}
        if not response.get('pnrNumber'):
            return None
        passengers = []
        for p in safe_list(response, 'passengerList'):
            passengers.append({
                'booking_status': safe_str(p.get('bookingStatusDetails'), 'N/A'),
                'current_status': safe_str(p.get('currentStatusDetails'), 'N/A')
            })
        return {
            "pnr": safe_str(response.get('pnrNumber')),
            "train_number": safe_str(response.get('trainNumber')),
            "train_name": safe_str(response.get('trainName')),
            "journey_date": safe_str(response.get('dateOfJourney')),
            "class": safe_str(response.get('journeyClass')),
            "quota": safe_str(response.get('quota')),
            "chart_status": safe_str(response.get('chartStatus'), 'Not Prepared'),
            "boarding_point": safe_str(response.get('boardingPoint')),
            "destination": safe_str(response.get('destinationStation')),
            "passengers": passengers
        }
    except Exception as e:
        return {"error": str(e)}

def get_live_train_status(train_number, date_str=None):
    if not NTES_AVAILABLE:
        return {"error": "NTES library not installed"}
    try:
        if date_str is None:
            date_str = datetime.now().strftime("%d-%b-%Y")
        date_formats = [date_str, date_str.replace('-', ' '), date_str.replace('-', '/')]
        response = None
        for fmt in date_formats:
            try:
                response = ntes_client.live_status(train_number, fmt)
                if response and response.get('CPOS'):
                    break
            except:
                continue
        if not response or not response.get('CPOS'):
            return {"error": "NO_DATA"}
        train_name = safe_str(response.get('TNM'), 'N/A')
        source = safe_str(response.get('SRCN', response.get('DFROM')), 'N/A')
        destination = safe_str(response.get('DSTNN', response.get('DTO')), 'N/A')
        current_pos = safe_str(response.get('CPOS'), 'N/A')
        delay = safe_str(response.get('LDEL'), '0')
        journey_date = safe_str(response.get('STD'), date_str)
        pos_lower = str(current_pos).lower()
        is_completed = any(k in pos_lower for k in ["reached destination", "journey completed", "terminated"])
        is_not_started = any(k in pos_lower for k in ["not started", "yet to start", "at source"])
        state = "completed" if is_completed else ("not_started" if is_not_started else "running")
        stations_raw = safe_list(response, 'STNSD')
        if not stations_raw:
            stations_raw = safe_list(response, 'STNS')
        upcoming = []
        current_code = None
        m = re.search(r'\(([A-Z]{2,5})\)', current_pos)
        if m:
            current_code = m.group(1).upper()
        if current_code:
            for i, s in enumerate(stations_raw):
                sc = s.get('SC', '').upper()
                if sc == current_code:
                    upcoming = stations_raw[i+1:i+9]
                    break
        if not upcoming:
            if is_not_started:
                upcoming = stations_raw[:8]
            else:
                upcoming = stations_raw[:8]
        formatted_stations = []
        for s in upcoming:
            formatted_stations.append({
                'code': safe_str(s.get('SC', 'N/A')),
                'name': safe_str(s.get('SN', 'N/A')),
                'arrival': safe_str(s.get('STA', 'N/A')),
                'departure': safe_str(s.get('STD', 'N/A')),
                'day': safe_str(s.get('Day', ''))
            })
        return {
            "train_number": train_number,
            "train_name": train_name,
            "current_station": current_pos,
            "source": source,
            "destination": destination,
            "journey_date": journey_date,
            "delay": delay,
            "state": state,
            "stations": formatted_stations,
            "last_updated": datetime.now().strftime('%d %b %H:%M:%S')
        }
    except Exception as e:
        return {"error": str(e)}

def get_train_schedule(train_number):
    if not NTES_AVAILABLE:
        return {"error": "NTES library not installed"}
    try:
        response = ntes_client.schedule(train_number)
        if not response:
            return None
        stations = []
        for s in safe_list(response, 'stations'):
            sta = s.get('STA', '')
            std = s.get('STD', '')
            if (sta and sta != 'N/A') or (std and std != 'N/A') or sta == 'Source' or std == 'Dest':
                stations.append({
                    'code': safe_str(s.get('StationCode')),
                    'name': safe_str(s.get('StationName')),
                    'arrival': sta if sta else 'Source',
                    'departure': std if std else 'Dest',
                    'day': safe_str(s.get('Day'))
                })
        return {
            "train_number": train_number,
            "train_name": safe_str(response.get('TrainName')),
            "source": safe_str(response.get('Source')),
            "destination": safe_str(response.get('Destination')),
            "stations": stations,
            "last_updated": datetime.now().strftime('%d %b %H:%M:%S')
        }
    except Exception as e:
        return {"error": str(e)}

def format_pnr_result(data):
    if not data:
        return "❌ PNR not found."
    if isinstance(data, dict) and data.get('error'):
        if data['error'] == "FLUSHED_PNR":
            return "❌ FLUSHED PNR / PNR NOT YET GENERATED\n\nPlease check the PNR number and try again."
        return f"❌ Error: {data['error']}"
    pnr = data.get('pnr', 'N/A')
    train_no = data.get('train_number', 'N/A')
    train_name = data.get('train_name', 'N/A')
    journey_date = data.get('journey_date', 'N/A')
    class_code = data.get('class', 'N/A')
    quota = data.get('quota', 'N/A')
    chart_status = data.get('chart_status', 'N/A')
    boarding = data.get('boarding_point', 'N/A')
    destination = data.get('destination', 'N/A')
    passengers = data.get('passengers', [])
    msg = f"**PNR:** {pnr}\n"
    msg += f"**Train:** {train_no} - {train_name}\n"
    msg += f"**From:** {boarding} → {destination}\n"
    msg += f"**Date:** {journey_date}  **Class:** {class_code} ({quota})\n"
    msg += f"**Chart:** {chart_status}\n\n"
    if passengers:
        msg += "**Passengers:**\n"
        for i, p in enumerate(passengers, 1):
            msg += f"{i}. Booking: {p['booking_status']}  Current: {p['current_status']}\n"
    msg += f"\n_Last updated: {data.get('last_updated', datetime.now().strftime('%d %b %H:%M:%S'))}_"
    return msg

def format_live_train_result(data):
    if not data:
        return "❌ Train not found."
    if isinstance(data, dict) and data.get('error'):
        return f"❌ {data['error']}"
    train_no = data.get('train_number', 'N/A')
    train_name = data.get('train_name', 'N/A')
    state = data.get('state', 'running')
    msg = f"## 🚂 {train_no}\n"
    msg += f"**{train_name}**\n\n"
    msg += f"**From:** {data.get('source', 'N/A')} → {data.get('destination', 'N/A')}\n"
    msg += f"**Date:** {data.get('journey_date', 'N/A')}\n"
    delay = data.get('delay', '0')
    msg += f"**Delay:** {'✅ On Time' if delay == '0' else f'⏰ {delay} mins late'}\n"
    msg += f"**Current Status:** {data.get('current_station', 'N/A')}\n"
    if state == "completed":
        msg += "\n🏁 **JOURNEY COMPLETED**\n"
    elif state == "not_started":
        msg += "\n⏳ **JOURNEY NOT STARTED**\n"
    else:
        msg += "\n**Upcoming Stations:**\n"
        for s in data.get('stations', []):
            msg += f"- {s['code']} - {s['name']}  Arr: {s['arrival']}  Dep: {s['departure']}\n"
    msg += f"\n_Last updated: {data.get('last_updated', datetime.now().strftime('%d %b %H:%M:%S'))}_"
    return msg

def format_schedule_result(data, start=0, chunk=20):
    if not data:
        return "❌ Schedule not found.", None
    if isinstance(data, dict) and data.get('error'):
        return f"❌ {data['error']}", None
    stations = data.get('stations', [])
    total = len(stations)
    end = min(start + chunk, total)
    if start >= total:
        start = max(0, total - chunk)
        end = total
    msg = f"**Train:** {data.get('train_number', 'N/A')} - {data.get('train_name', 'N/A')}\n"
    msg += f"**From:** {data.get('source', 'N/A')} → {data.get('destination', 'N/A')}\n"
    msg += f"**Showing {start+1} to {end} of {total}**\n\n"
    for i in range(start, end):
        s = stations[i]
        msg += f"{i+1}. **{s['code']}** - {s['name']}\n"
        msg += f"   Arr: {s['arrival']}  Dep: {s['departure']}  Day: {s['day']}\n\n"
    msg += f"_Last updated: {data.get('last_updated', datetime.now().strftime('%d %b %H:%M:%S'))}_"
    return msg, (start, end, total)
