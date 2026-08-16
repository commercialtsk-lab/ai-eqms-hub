import streamlit as st
from utils.ntes_client import (
    NTES_AVAILABLE, get_pnr, get_live_train, get_train_schedule,
    format_pnr, format_live_train, format_train_schedule,
    get_date_label, get_date_for_offset
)

def render_railway():
    st.subheader("🚂 Indian Railways - Real‑time Info")
    if not NTES_AVAILABLE:
        st.error("❌ 'ntes-client' library not installed. Please run: `pip install ntes-client`")
        st.stop()

    tab1, tab2, tab3 = st.tabs(["🔍 PNR Status", "🚂 Live Train", "📋 Train Schedule"])

    with tab1:
        st.markdown("### PNR Status Check")
        pnr_input = st.text_input("Enter 10-digit PNR", max_chars=10, key="rail_pnr")
        if st.button("Check PNR", key="pnr_check", use_container_width=True):
            if not pnr_input or len(pnr_input) != 10 or not pnr_input.isdigit():
                st.error("Please enter a valid 10-digit PNR.")
            else:
                with st.spinner("Fetching PNR details..."):
                    data = get_pnr(pnr_input)
                    if data and isinstance(data, dict) and data.get('error'):
                        st.error(f"❌ {data['error']}")
                    elif data:
                        st.markdown(format_pnr(data))
                    else:
                        st.error("❌ PNR not found or flushed.")

    with tab2:
        st.markdown("### Live Train Status")
        train_no = st.text_input("Enter Train Number (3-5 digits)", key="rail_train")
        date_options = [f"{get_date_label(i)} ({get_date_for_offset(i)})" for i in range(5)]
        date_choice = st.selectbox("Select Date", date_options, index=0, key="rail_date")
        offset = 0
        for i in range(5):
            if get_date_label(i) in date_choice:
                offset = i
                break
        if st.button("Get Live Status", key="train_live", use_container_width=True):
            if not train_no or not train_no.isdigit() or not (3 <= len(train_no) <= 5):
                st.error("Please enter a valid train number (3-5 digits).")
            else:
                with st.spinner("Fetching live status..."):
                    date_str = get_date_for_offset(offset)
                    data = get_live_train(train_no, date_str)
                    if data and isinstance(data, dict) and data.get('error'):
                        st.error(f"❌ {data['error']}")
                    elif data:
                        response, _ = format_live_train(data)
                        st.markdown(response)
                    else:
                        st.error("❌ No data available.")

    with tab3:
        st.markdown("### Train Schedule / Route")
        train_no_sch = st.text_input("Enter Train Number (3-5 digits)", key="rail_sch")
        if 'sch_start' not in st.session_state:
            st.session_state.sch_start = 0
        if st.button("Get Schedule", key="train_sch", use_container_width=True):
            if not train_no_sch or not train_no_sch.isdigit() or not (3 <= len(train_no_sch) <= 5):
                st.error("Please enter a valid train number.")
            else:
                with st.spinner("Fetching schedule..."):
                    data = get_train_schedule(train_no_sch)
                    if data and isinstance(data, dict) and data.get('error'):
                        st.error(f"❌ {data['error']}")
                    elif data:
                        st.session_state.sch_data = data
                        st.session_state.sch_start = 0
                        st.rerun()
                    else:
                        st.error("❌ Schedule not found.")
        if 'sch_data' in st.session_state:
            data = st.session_state.sch_data
            total = len(data.get('stations', []))
            chunk = 20
            start = st.session_state.sch_start
            end = min(start + chunk, total)
            if start >= total:
                start = max(0, total - chunk)
                end = total
                st.session_state.sch_start = start
            msg, _ = format_train_schedule(data, start)
            st.markdown(msg)
            col1, col2, col3 = st.columns([1,2,1])
            with col1:
                if start > 0:
                    if st.button("◀ Previous", key="sch_prev"):
                        st.session_state.sch_start = max(0, start - chunk)
                        st.rerun()
            with col2:
                st.write(f"Showing {start+1}-{end} of {total}")
            with col3:
                if end < total:
                    if st.button("Next ▶", key="sch_next"):
                        st.session_state.sch_start = end
                        st.rerun()
