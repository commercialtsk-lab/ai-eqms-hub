import re
from datetime import datetime, timedelta

# ============================================
# NTES Client Initialization
# ============================================
try:
    from ntes import NTESClient
    ntes_client = NTESClient()
    NTES_AVAILABLE = True
except ImportError:
    NTES_AVAILABLE = False

# ============================================
# Helper Functions
# ============================================
def safe_list(data, key):
    val = data.get(key) if data else None
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]

def safe_str(val, default='N/A'):
    return str(val) if val is not None else default

def get_date_label(offset):
    target = datetime.now() - timedelta(days=offset)
    day = target.day
    suffix = {1:'st', 2:'nd', 3:'rd'}.get(day%10 if day not in [11,12,13] else 0, 'th')
    return f"{day}{suffix} {target.strftime('%b')}"

def get_date_for_offset(offset):
    return (datetime.now() - timedelta(days=offset)).strftime("%d-%b-%Y")

def format_station_time(time_str):
    if not time_str or time_str in ['N/A', 'Source', 'Dest']:
        return time_str
    time_parts = time_str.split()
    if len(time_parts) >= 2 and any(m in time_parts[1] for m in ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']):
        return time_parts[0]
    return time_str

def get_stn_field(station, possible_keys, default=''):
    if not station or not isinstance(station, dict):
        return default
    for key in possible_keys:
        if key in station:
            return station[key]
    lower_map = {k.lower(): v for k, v in station.items()}
    for key in possible_keys:
        if key.lower() in lower_map:
            return lower_map[key.lower()]
    return default

def normalize_station(s):
    if not s or not isinstance(s, dict):
        return {'SC':'N/A','SN':'N/A','STA':'N/A','STD':'N/A','ETA':'','ETD':'','DAY':''}
    sta = s.get('STA','')
    std = s.get('STD','')
    eta = s.get('ETA','')
    etd = s.get('ETD','')
    day = s.get('Day', s.get('day', ''))
    return {
        'SC': get_stn_field(s, ['SC','StationCode','StnCode','Code','stationCode','stnCode','StnCd'], 'N/A'),
        'SN': get_stn_field(s, ['SN','StationName','StnName','Name','stationName','stnName'], 'N/A'),
        'STA': sta if sta else (eta if eta else 'N/A'),
        'STD': std if std else (etd if etd else 'N/A'),
        'ETA': eta,
        'ETD': etd,
        'DAY': safe_str(day, '')
    }

# ============================================
# Main NTES Functions
# ============================================
def get_pnr(pnr):
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

def get_live_train(train_number, date_str=None):
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
        dest_code = safe_str(response.get('DST'), '')
        journey_date = safe_str(response.get('STD'), date_str)
        current_pos = safe_str(response.get('CPOS'), 'N/A')
        delay = safe_str(response.get('LDEL'), '0')
        excpt = safe_str(response.get('EXCP'), '')
        pos_str = str(current_pos)
        pos_lower = pos_str.lower()
        is_completed = any(k in pos_lower for k in ["reached destination", "journey completed", "terminated", "destination reached", "arrived at destination", "train completed", "train reached", "journey ended", "train terminated", "has terminated", "run terminated"])
        is_not_started = any(k in pos_lower for k in ["not started", "yet to start", "scheduled", "at source", "will start", "starts from", "origin", "before departure"])
        if not is_completed and destination != 'N/A':
            dest_upper = destination.upper()
            if any(w in pos_lower for w in ['arrived', 'reached', 'terminated', 'completed', 'ended']):
                dest_words = [w for w in dest_upper.split() if len(w) >= 3]
                for word in dest_words:
                    if word in pos_str.upper():
                        is_completed = True
                        break
        current_code = None
        current_name = None
        m = re.search(r'\(([A-Z]{2,5})\)', pos_str)
        if m:
            current_code = m.group(1).upper()
        if not current_code:
            for pattern in [r'from\s+([A-Z]{2,5})\b', r'at\s+([A-Z]{2,5})\b', r'(?:departed|arrived|left|reached)\s+(?:from\s+|at\s+)?([A-Z]{2,5})\b']:
                m = re.search(pattern, pos_str, re.IGNORECASE)
                if m:
                    current_code = m.group(1).upper()
                    break
        if not current_name:
            for pattern in [r'(?:from|at|departed|arrived|left|reached)\s+([A-Z][A-Z\s]+?)(?:\s*\(|$)', r'(?:has|is)\s+([A-Z][A-Z\s]+?)\s+(?:station|junction|jn)']:
                m = re.search(pattern, pos_str, re.IGNORECASE)
                if m:
                    current_name = re.sub(r'\s+(JUNCTION|JN|ROAD|RD|CITY|CANTT|NAGAR|NG)$', '', m.group(1).strip().upper())
                    break
        live_stations_map = {}
        stations_raw = safe_list(response, 'STNSD')
        if not stations_raw:
            stations_raw = safe_list(response, 'STNS')
        all_live = []
        for s in stations_raw:
            ns = normalize_station(s)
            if ns['SC'] != 'N/A':
                live_stations_map[ns['SC'].upper()] = ns
                all_live.append(ns)
        return {
            "train_number": train_number,
            "train_name": train_name,
            "current_station": current_pos,
            "source": source,
            "destination": destination,
            "journey_date": journey_date,
            "delay": delay,
            "state": "running",
            "stations": [],
            "last_updated": datetime.now().strftime('%d %b %H:%M:%S')
        }
    except Exception as e:
        return {"error": "API_ERROR", "message": str(e)}

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

# ============================================
# Formatting Functions
# ============================================
def format_pnr(data):
    if data and data.get('error') == "FLUSHED_PNR":
        return "❌ FLUSHED PNR / PNR NOT YET GENERATED\n\nPlease check the PNR number and try again."
    if not data:
        return "❌ PNR not found."
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
    msg += f"\n_Last updated: {datetime.now().strftime('%d %b %H:%M:%S')}_"
    return msg

def format_live_train(data):
    if not data:
        return "❌ Train not found.", None
    if isinstance(data, dict) and data.get('error'):
        return f"❌ {data['error']}", None
    train_no = data.get('train_number', 'N/A')
    train_name = data.get('train_name', 'N/A')
    msg = f"## 🚂 {train_no}\n"
    msg += f"**{train_name}**\n\n"
    msg += f"**From:** {data.get('source', 'N/A')} → {data.get('destination', 'N/A')}\n"
    msg += f"**Date:** {data.get('journey_date', 'N/A')}\n"
    delay = data.get('delay', '0')
    msg += f"**Delay:** {'✅ On Time' if str(delay) == '0' else f'⏰ {delay} mins late'}\n"
    msg += f"**Current Status:** {data.get('current_station', 'N/A')}\n"
    msg += f"\n_Last updated: {data.get('last_updated', datetime.now().strftime('%d %b %H:%M:%S'))}_"
    return msg, None

def format_train_schedule(data, chunk_start=0):
    if not data:
        return "❌ Schedule not found.", None
    if isinstance(data, dict) and data.get('error'):
        return f"❌ {data['error']}", None
    stations = data.get('stations', [])
    total = len(stations)
    CHUNK_SIZE = 20
    start = chunk_start
    end = min(start + CHUNK_SIZE, total)
    msg = f"**Train:** {data.get('train_number', 'N/A')} - {data.get('train_name', 'N/A')}\n"
    msg += f"**From:** {data.get('source', 'N/A')} → {data.get('destination', 'N/A')}\n"
    msg += f"**Showing {start+1} to {end} of {total}**\n\n"
    for i in range(start, end):
        s = stations[i]
        msg += f"{i+1}. **{s.get('code', 'N/A')}** - {s.get('name', 'N/A')}\n"
        msg += f"   Arr: {s.get('arrival', 'N/A')}  Dep: {s.get('departure', 'N/A')}"
        if s.get('day') and s.get('day') != 'N/A':
            msg += f"  Day: {s.get('day')}"
        msg += "\n\n"
    msg += f"_Last updated: {data.get('last_updated', datetime.now().strftime('%d %b %H:%M:%S'))}_"
    return msg, (start, end, total)
