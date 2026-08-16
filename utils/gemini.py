import streamlit as st
import requests
import json
import re
import base64
from utils.config import GEMINI_API_KEY
from utils.sheets import SHEET_ID, init_sheets

def gemini_universal_parser(input_data, input_type, mime_type, progress_callback=None):
    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}'
    system_prompt = """You are TSKEQ Bot's AI extraction engine. You are an EXPERT at reading messy, handwritten, torn, or low-quality railway forms.

=== FIELDS TO EXTRACT (21 fields) ===
PNR, T_N (Train Number), CLASS, DOJ (DD-MM-YYYY), FROM, TO, BOARDING, PASS_NAME, PASS_PH (10 digits), T_BERTHS, PURPOSE, ADDRESS, DIARY_NO, RECOMMENDATION, DESIGNATION, VIP_STATUS, APPLICATION_DATE, RAILWAY_ZONE, PREFERENCE, PHONE_NUBER, WARRANT_NO

=== SPECIAL RULES ===
1. DIARY_NO: Look for "No." or "Diary No." pattern. Preserve as-is.
2. PREFERENCE: If you see "Lower Berth", "Lower Seat", "Coupe", set PREFERENCE = "Lower Seat".
3. RAIL BOARD: If you see "Office of the Hon'ble Minister Railways", set DIARY_NO="RAIL BOARD", RAILWAY_ZONE="RAIL BOARD".
4. DOJ: If you see "24/25.06.26", return the FIRST date: "24-06-2026".

=== OUTPUT FORMAT ===
Return ONLY a valid JSON array. No explanations.
[
  {
    "PNR": "6307598699",
    "T_N": "20503",
    "CLASS": "1A",
    "DOJ": "12-08-2026",
    "FROM": "HJP",
    "TO": "LKO",
    "BOARDING": "",
    "PASS_NAME": "INDU DUBEY",
    "PASS_PH": "9771425900",
    "T_BERTHS": 1,
    "PURPOSE": "",
    "ADDRESS": "",
    "DIARY_NO": "ECR/CRM/PCCM Cell/EQ/01/2026",
    "RECOMMENDATION": "MRITYUNJAY KUMAR",
    "DESIGNATION": "Secy to PCCM",
    "VIP_STATUS": "",
    "APPLICATION_DATE": "10-08-2026",
    "RAILWAY_ZONE": "ECR",
    "PREFERENCE": "Lower Seat",
    "PHONE_NUBER": "9771425962",
    "WARRANT_NO": ""
  }
]
CRITICAL: Return ONLY the JSON array.
"""
    parts = []
    if input_type in ['image', 'pdf']:
        mime = mime_type or ("image/jpeg" if input_type == 'image' else "application/pdf")
        parts.append({"inline_data": {"mime_type": mime, "data": input_data}})
        parts.append({"text": system_prompt})
    elif input_type == 'audio':
        parts.append({"inline_data": {"mime_type": mime_type or "audio/ogg", "data": input_data}})
        parts.append({"text": system_prompt})
    elif input_type == 'text':
        parts.append({"text": system_prompt + "\n\nINPUT DATA:\n" + input_data})
    else:
        return {'error': 'Unsupported type'}
    
    if progress_callback:
        progress_callback(30, "Sending to Gemini...")
    
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 16384}
    }
    
    try:
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, timeout=120)
        if response.status_code != 200:
            return {'error': f'Gemini API Error: {response.status_code}'}
        data = response.json()
        if not data.get('candidates') or not data['candidates'][0].get('content', {}).get('parts'):
            return {'error': 'Empty response from Gemini'}
        response_text = data['candidates'][0]['content']['parts'][0]['text']
        if progress_callback:
            progress_callback(60, "Parsing Gemini response...")
        json_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', response_text)
        if not json_match:
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
            if json_match:
                json_str = json_match.group(1)
            else:
                if progress_callback:
                    progress_callback(80, "Using fallback extraction...")
                return {'error': 'No JSON found in response'}
        else:
            json_str = json_match.group(0)
        json_str = json_str.replace('```json', '').replace('```', '').strip()
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        json_str = re.sub(r'([a-zA-Z0-9_]+)\s*:', r'"\1":', json_str)
        json_str = json_str.replace("'", '"')
        records = json.loads(json_str)
        if isinstance(records, dict):
            records = [records]
        if progress_callback:
            progress_callback(100, "Complete!")
        return {'records': records, 'count': len(records)}
    except Exception as e:
        return {'error': f'Parser Error: {e}'}

def chat_with_gemini(user_message, chat_history):
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')
        context = get_sheet_context()
        system_prompt = f"""You are TSKEQ Bot - a professional railway EQ assistant. You have access to the EQ sheet data.

Sheet Context:
{context}

Instructions:
1. Answer questions based on the sheet data if relevant.
2. For general railway questions, use your knowledge.
3. Be helpful, concise, and professional yet friendly.

Previous conversation:
"""
        for msg in chat_history[-10:]:
            if msg['role'] == 'user':
                system_prompt += f"User: {msg['content']}\n"
            else:
                system_prompt += f"Assistant: {msg['content']}\n"
        system_prompt += f"\nUser: {user_message}\nAssistant:"
        response = model.generate_content(system_prompt)
        return response.text
    except Exception as e:
        return f"⚠️ Error: Could not process your request. ({str(e)})"

def get_sheet_context():
    try:
        gc = init_sheets()
        eq_sheet = gc.open_by_key(SHEET_ID).worksheet("EQ")
        all_data = eq_sheet.get_all_values()
        total = max(0, len(all_data) - 4)
        summary = f"EQ Sheet has {total} records.\n"
        if total > 0:
            sample = all_data[-5:] if len(all_data) > 5 else all_data[4:]
            summary += "Recent records:\n"
            for row in sample:
                if len(row) > 7:
                    summary += f"PNR: {row[1] if len(row)>1 else ''}, Train: {row[5] if len(row)>5 else ''}, DOJ: {row[7] if len(row)>7 else ''}\n"
        return summary
    except Exception:
        return "Sheet data temporarily unavailable."
