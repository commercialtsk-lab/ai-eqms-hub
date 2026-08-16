import streamlit as st
import pandas as pd
import plotly.express as px
from utils.helpers import is_expired

def render_dashboard(filtered_df):
    st.subheader("📊 Analytics Dashboard")
    
    train_col = None
    for c in filtered_df.columns:
        if 'T/N' in c.upper() or 'T_N' in c.upper() or 'TRAIN' in c.upper():
            train_col = c
            break
    
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        total_records = len(filtered_df) if not filtered_df.empty else 0
        st.metric("Total Records", total_records)
    with m2:
        unique_trains = filtered_df[train_col].nunique() if train_col else 0
        st.metric("Unique Trains", unique_trains)
    with m3:
        berth_col = next((c for c in filtered_df.columns if 'BERTH' in str(c).upper() or 'T/BERTHS' in str(c).upper()), None)
        total_berths = 0
        if berth_col and berth_col in filtered_df:
            total_berths = pd.to_numeric(filtered_df[berth_col], errors='coerce').sum()
        st.metric("Total Berths", int(total_berths) if total_berths else 0)
    with m4:
        expired = 0
        doj_col = next((c for c in filtered_df.columns if 'DOJ' in str(c).upper()), None)
        if doj_col and doj_col in filtered_df:
            expired = sum(1 for _, r in filtered_df.iterrows() if is_expired(r.get(doj_col, '')))
        st.metric("Expired DOJ", expired)
    
    st.markdown("---")
    if not filtered_df.empty and train_col:
        train_counts = filtered_df[train_col].value_counts().reset_index()
        train_counts.columns = ['Train', 'Count']
        fig_bar = px.bar(train_counts.head(15), x='Train', y='Count', title="Top 15 Trains by EQ Count", color='Count', color_continuous_scale='Blues')
        fig_bar.update_layout(height=400, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_bar, use_container_width=True)
        
        class_col = next((c for c in filtered_df.columns if 'CLASS' in c.upper()), None)
        if class_col:
            class_counts = filtered_df[class_col].value_counts().reset_index()
            class_counts.columns = ['Class', 'Count']
            fig_pie = px.pie(class_counts, names='Class', values='Count', title="Class Distribution", hole=0.4)
            fig_pie.update_layout(height=350, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("No data for charts.")
