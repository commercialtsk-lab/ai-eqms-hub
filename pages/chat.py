import streamlit as st
import google.generativeai as genai
from utils.config import GEMINI_API_KEY
from utils.sheets import SHEET_ID, init_sheets

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

def chat_with_gemini(user_message, chat_history):
    try:
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

def render_chat():
    st.subheader("💬 Chat with TSKEQ Bot")
    st.caption("Ask about EQ data, trains, quota, PNR or anything else.")
    
    if prompt := st.chat_input("Type your question...", key="chat_input"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response = chat_with_gemini(prompt, st.session_state.messages)
                st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})
        st.rerun()
    
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    
    st.markdown("**Quick questions**")
    sugg_cols = st.columns(3)
    for i, suggestion in enumerate(st.session_state.chat_suggestions):
        with sugg_cols[i % 3]:
            if st.button(suggestion, key=f"sugg_{i}", use_container_width=True, help=f"Ask: {suggestion}"):
                st.session_state.messages.append({"role": "user", "content": suggestion})
                with st.spinner("Thinking..."):
                    response = chat_with_gemini(suggestion, st.session_state.messages)
                    st.session_state.messages.append({"role": "assistant", "content": response})
                st.rerun()
    
    if st.button("🗑️ Clear Chat", use_container_width=True, key="clear_chat_btn", help="Clear all chat history"):
        st.session_state.messages = []
        st.rerun()
