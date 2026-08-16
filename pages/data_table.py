import streamlit as st
import pandas as pd
import math
import time
import urllib.parse
from utils.helpers import now_ist, format_datetime, log_activity, is_expired, col_index_to_letter
from utils.sheets import SHEET_CONFIG, init_sheets, SHEET_ID
from utils.exports import generate_pdf, create_table_image, build_whatsapp_message, get_pnr_status_url

def render_data_table(filtered_df, sheet_choice):
    st.subheader(f"📋 {sheet_choice}  —  {len(filtered_df)} rows")
    
    train_col_metric = None
    doj_col = None
    for c in filtered_df.columns:
        if 'T/N' in c.upper() or 'T_N' in c.upper() or 'TRAIN' in c.upper():
            train_col_metric = c
        if 'DOJ' in c.upper():
            doj_col = c

    if not filtered_df.empty and train_col_metric:
        train_counts_series = filtered_df[train_col_metric].value_counts()
        st.markdown("**🚆 Train-wise Count**")
        cards_html = '<div class="train-count-container">'
        total_eq = len(filtered_df)
        cards_html += f'<div class="train-total-card"><div class="train-total-number">Total EQ: {total_eq}</div></div>'
        for train_num, cnt in train_counts_series.items():
            cards_html += f'<div class="train-count-card"><div class="train-count-number">{train_num}</div><div class="train-count-badge">{cnt}</div></div>'
        cards_html += '</div>'
        st.markdown(cards_html, unsafe_allow_html=True)
        st.markdown("---")

    if filtered_df.empty:
        st.info("No data to show.")
        return

    page_size = st.selectbox("Rows per page", [15, 25, 50, 100], index=1, key="page_size_select")
    total_pages = max(1, math.ceil(len(filtered_df) / page_size))
    if st.session_state.current_page > total_pages:
        st.session_state.current_page = total_pages
    if st.session_state.current_page < 1:
        st.session_state.current_page = 1

    nav1, nav2, nav3 = st.columns([1, 2, 1])
    with nav1:
        if st.button("◀ Previous", use_container_width=True, disabled=st.session_state.current_page <= 1, key="prev_page_btn"):
            st.session_state.current_page -= 1
            st.rerun()
    with nav2:
        st.markdown(f"<div style='text-align:center; padding-top:6px;'><b>Page {st.session_state.current_page} of {total_pages}</b></div>", unsafe_allow_html=True)
    with nav3:
        if st.button("Next ▶", use_container_width=True, disabled=st.session_state.current_page >= total_pages, key="next_page_btn"):
            st.session_state.current_page += 1
            st.rerun()

    page = st.session_state.current_page - 1
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(filtered_df))
    page_df = filtered_df.iloc[start_idx:end_idx].copy()
    sheet_rows = page_df['_sheet_row'].tolist() if '_sheet_row' in page_df.columns else []
    display_df = page_df.drop(columns=['_sheet_row'], errors='ignore')
    display_df.insert(0, "Select", False)

    print_cols = [c for c in display_df.columns if c != 'Select']
    print_df = display_df[print_cols].copy()
    if not print_df.empty:
        html_table = print_df.to_html(index=False, border=1, classes='print-table')
    else:
        html_table = "<p>No data</p>"
    st.markdown(f"""
    <div class="print-only">
        <h3 style="text-align:center;">{sheet_choice} Data</h3>
        {html_table}
        <p style="text-align:center; font-size:10pt;">Generated: {format_datetime()} IST</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="print-area">', unsafe_allow_html=True)
    edited_page = st.data_editor(display_df, use_container_width=True, height=400,
        column_config={"Select": st.column_config.CheckboxColumn("Select", width="small")},
        key=f"editor_{sheet_choice}_{st.session_state.current_page}_{page_size}")
    st.markdown('</div>', unsafe_allow_html=True)

    select_all = st.checkbox("Select All on Page", value=st.session_state.select_all, key="select_all_cb")
    if select_all != st.session_state.select_all:
        st.session_state.select_all = select_all
        st.rerun()

    selected_mask = edited_page["Select"] if "Select" in edited_page.columns else pd.Series([False] * len(edited_page))
    selected_indices = edited_page[selected_mask].index.tolist()
    selected_sheet_rows = []
    if selected_indices and sheet_rows:
        for idx in selected_indices:
            try:
                pos = list(page_df.index).index(idx)
                selected_sheet_rows.append(sheet_rows[pos])
            except (ValueError, IndexError):
                pass

    pnr_col = next((c for c in edited_page.columns if 'PNR' in str(c).upper()), None)
    selected_pnrs = edited_page.loc[selected_indices, pnr_col].tolist() if pnr_col and selected_indices else []

    st.markdown('<div class="action-box no-print">', unsafe_allow_html=True)
    st.markdown("**⚡ Quick Actions**")
    a1, a2, a3, a4, a5 = st.columns(5)
    with a1:
        if st.button("💾 Save Edits", use_container_width=True, key="save_edits_btn"):
            try:
                gc = init_sheets()
                sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                data_to_update = edited_page.drop(columns=["Select"], errors='ignore')
                data_list = data_to_update.values.tolist()
                if data_list and sheet_rows:
                    for i, row_data in enumerate(data_list):
                        sheet_row_num = sheet_rows[i]
                        row_data = [str(x) if pd.notna(x) else '' for x in row_data]
                        num_cols = len(row_data)
                        col_letter = col_index_to_letter(num_cols)
                        range_name = f"A{sheet_row_num}:{col_letter}{sheet_row_num}"
                        sheet.update(range_name, [row_data])
                    st.toast("✅ Saved!", icon="💾")
                    log_activity(f"💾 Saved {len(data_list)} rows in {sheet_choice}")
                    st.cache_data.clear()
                    st.session_state.last_refresh = time.time()
                    time.sleep(0.3)
                    st.rerun()
                else:
                    st.warning("Nothing to save")
            except Exception as e:
                if "429" in str(e):
                    st.error("Write quota exceeded. Wait 1 minute.")
                else:
                    st.error(f"Save error: {e}")
    with a2:
        if st.button("➕ Add Row", use_container_width=True, key="add_row_btn"):
            try:
                gc = init_sheets()
                sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                all_data = sheet.get_all_values()
                num_cols = len(all_data[0]) if all_data else 1
                blank_row = [''] * num_cols
                config = SHEET_CONFIG.get(sheet_choice, {"start_row": 5})
                start_row = config["start_row"]
                if len(all_data) >= start_row:
                    blank_row[0] = len(all_data) - start_row + 2
                sheet.append_row(blank_row)
                st.toast("✅ Row added", icon="➕")
                log_activity(f"➕ Added row in {sheet_choice}")
                st.cache_data.clear()
                st.session_state.last_refresh = time.time()
                time.sleep(0.3)
                st.rerun()
            except Exception as e:
                st.error(f"Add error: {e}")
    with a3:
        if selected_sheet_rows:
            if st.button("🗑️ Delete", use_container_width=True, key="delete_btn"):
                if not st.session_state.delete_confirm:
                    st.session_state.delete_confirm = True
                    st.warning("Confirm delete by clicking again.")
                    st.rerun()
                else:
                    try:
                        gc = init_sheets()
                        sheet = gc.open_by_key(SHEET_ID).worksheet(sheet_choice)
                        for row_num in sorted(selected_sheet_rows, reverse=True):
                            sheet.delete_rows(row_num)
                        st.toast(f"✅ Deleted {len(selected_sheet_rows)}", icon="🗑️")
                        log_activity(f"🗑️ Deleted {len(selected_sheet_rows)} from {sheet_choice}")
                        st.session_state.delete_confirm = False
                        st.cache_data.clear()
                        st.session_state.last_refresh = time.time()
                        time.sleep(0.3)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete error: {e}")
        else:
            st.button("🗑️ Delete", disabled=True, use_container_width=True, key="delete_disabled_btn")
            st.session_state.delete_confirm = False
    with a4:
        msg = build_whatsapp_message(sheet_choice, len(selected_indices), selected_pnrs, len(filtered_df), filtered_df)
        encoded = urllib.parse.quote(msg)
        wa_url = f"https://api.whatsapp.com/send?text={encoded}"
        st.link_button("📤 WhatsApp Text", wa_url, use_container_width=True)
    with a5:
        st.components.v1.html("""
        <div style="width:100%;">
            <button onclick="window.print();" style="
                background: linear-gradient(135deg, #7c3aed, #6d28d9);
                color: white; border: none; border-radius: 8px;
                padding: 9px 16px; width: 100%; font-weight: 600;
                cursor: pointer; font-size: 1rem;
            ">🖨️ PRINT Sheet</button>
        </div>
        """, height=50)
    st.markdown('</div>', unsafe_allow_html=True)
