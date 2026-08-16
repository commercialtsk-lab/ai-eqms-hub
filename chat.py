import streamlit as st
from utils.gemini import chat_with_gemini

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
            if st.button(suggestion, key=f"sugg_{i}", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": suggestion})
                with st.spinner("Thinking..."):
                    response = chat_with_gemini(suggestion, st.session_state.messages)
                    st.session_state.messages.append({"role": "assistant", "content": response})
                st.rerun()
    
    if st.button("🗑️ Clear Chat", use_container_width=True, key="clear_chat_btn"):
        st.session_state.messages = []
        st.rerun()
