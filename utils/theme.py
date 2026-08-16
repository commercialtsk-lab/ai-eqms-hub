import streamlit as st

def apply_theme(theme, custom_bg=None, custom_text=None):
    if theme == 'Day':
        bg = "#f6f8fa"
        card_bg = "#ffffff"
        text_color = "#1f2328"
        text_secondary = "#656d76"
        border = "#d0d7de"
        input_bg = "#ffffff"
        accent = "#0969da"
        accent_hover = "#0550ae"
        success = "#1a7f37"
        danger = "#cf222e"
        button_bg = "#f6f8fa"
        button_text = "#1f2328"
        button_border = "#d0d7de"
        button_hover_bg = accent
        button_hover_text = "white"
        button_hover_border = accent
    elif theme == 'Dark':
        bg = "#0d1117"
        card_bg = "#161b22"
        text_color = "#e6edf3"
        text_secondary = "#8b949e"
        border = "#30363d"
        input_bg = "#0d1117"
        accent = "#58a6ff"
        accent_hover = "#79c0ff"
        success = "#3fb950"
        danger = "#f85149"
        button_bg = "#21262d"
        button_text = "#e6edf3"
        button_border = "#30363d"
        button_hover_bg = accent
        button_hover_text = "white"
        button_hover_border = accent
    else:
        bg = custom_bg if custom_bg else "#ffffff"
        card_bg = bg
        text_color = custom_text if custom_text else "#000000"
        text_secondary = text_color
        border = "#d0d7de"
        input_bg = bg
        accent = "#0969da"
        accent_hover = "#0550ae"
        success = "#1a7f37"
        danger = "#cf222e"
        button_bg = bg
        button_text = text_color
        button_border = border
        button_hover_bg = accent
        button_hover_text = "white"
        button_hover_border = accent

    css = f"""
    <style>
        .block-container {{ padding-top: 0.5rem !important; padding-bottom: 1rem !important; }}
        .stApp {{ background-color: {bg} !important; }}
        [data-testid="stSidebar"] {{ background-color: {card_bg} !important; border-right: 1px solid {border} !important; }}
        [data-testid="stSidebar"] .stMarkdown p, [data-testid="stSidebar"] .stMarkdown div,
        [data-testid="stSidebar"] label, [data-testid="stSidebar"] .stTextInput label,
        [data-testid="stSidebar"] .stSelectbox label, [data-testid="stSidebar"] .stDateInput label,
        [data-testid="stSidebar"] .stNumberInput label, [data-testid="stSidebar"] .stTextArea label,
        [data-testid="stSidebar"] .stRadio label, [data-testid="stSidebar"] .stCheckbox label {{
            color: {text_color} !important;
        }}
        header[data-testid="stHeader"] {{ background-color: {card_bg} !important; border-bottom: 1px solid {border} !important; }}
        h1, h2, h3, h4, h5, h6, .stMarkdown p, .stMarkdown div, .stMarkdown span,
        .stMarkdown h1, .stMarkdown h2, .stMarkdown h3,
        [data-testid="stMetricLabel"], [data-testid="stMetricValue"], .stCaption {{
            color: {text_color} !important;
        }}
        .stTextInput input, .stNumberInput input, .stDateInput input, .stTextArea textarea,
        .stSelectbox > div > div > div {{
            background-color: {input_bg} !important;
            color: {text_color} !important;
            border: 1px solid {border} !important;
            border-radius: 8px !important;
        }}
        .stButton > button {{
            background-color: {button_bg} !important;
            color: {button_text} !important;
            border: 1px solid {button_border} !important;
            border-radius: 8px !important;
            font-weight: 500 !important;
            transition: all 0.15s ease !important;
        }}
        .stButton > button:hover {{
            background-color: {button_hover_bg} !important;
            color: {button_hover_text} !important;
            border-color: {button_hover_border} !important;
        }}
        .stFileUploader {{
            background-color: {input_bg} !important;
            border: 2px dashed {border} !important;
            border-radius: 12px !important; padding: 16px !important;
        }}
        .train-count-card {{
            border: 1px solid {border} !important;
            border-radius: 10px;
            padding: 8px 16px;
            min-width: 80px;
            text-align: center;
            background: transparent !important;
        }}
        .train-count-number {{ 
            color: {accent} !important;
            font-weight: 800;
            font-size: 1.8rem;
            line-height: 1.2;
        }}
        .train-count-badge {{ 
            display: inline-block;
            background: {accent} !important;
            color: white;
            font-size: 0.9rem;
            font-weight: 700;
            padding: 2px 10px;
            border-radius: 20px;
        }}
        .train-total-card {{ 
            background: {success}15 !important;
            border: 2px solid {success} !important;
            border-radius: 12px;
            padding: 8px 20px;
            min-width: 120px;
            text-align: center;
        }}
        .train-total-number {{ 
            color: {success} !important;
            font-weight: 800;
            font-size: 1.5rem;
        }}
        .print-only {{ display: none; }}
        @media print {{
            @page {{ margin: 1cm; size: A4 landscape; }}
            .no-print, header, footer, .stSidebar, .stButton, .stExpander,
            .action-box, .pro-footer, .train-count-container {{ display: none !important; }}
            .print-area, .print-area * {{ visibility: visible !important; color: black !important; background: white !important; }}
            .print-only {{ display: block !important; }}
            .print-only table {{ width: 100% !important; border-collapse: collapse !important; }}
            .print-only th, .print-only td {{ border: 1px solid #333 !important; padding: 4px !important; font-size: 10pt !important; }}
            .print-only th {{ background: #eee !important; }}
        }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
