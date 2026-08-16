import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils.helpers import is_expired

def render_dashboard(filtered_df):
    st.subheader("📊 Analytics Dashboard")
    
    train_col = None
    doj_col = None
    for c in filtered_df.columns:
        if 'T/N' in c.upper() or 'T_N' in c.upper() or 'TRAIN' in c.upper():
            train_col = c
        if 'DOJ' in c.upper():
            doj_col = c
    
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
        if doj_col and doj_col in filtered_df:
            expired = sum(1 for _, r in filtered_df.iterrows() if is_expired(r.get(doj_col, '')))
        st.metric("Expired DOJ", expired)
    
    st.markdown("---")
    
    if not filtered_df.empty:
        # ============================================
        # 1. 🌟 TREEMAP - Best for train distribution
        # ============================================
        if train_col:
            train_counts = filtered_df[train_col].value_counts().reset_index()
            train_counts.columns = ['Train', 'Count']
            
            fig_treemap = px.treemap(
                train_counts.head(30),
                path=['Train'],
                values='Count',
                title="🌳 Train-wise EQ Distribution (Treemap)",
                color='Count',
                color_continuous_scale='Viridis',
                hover_data={'Train': True, 'Count': True}
            )
            fig_treemap.update_layout(
                height=500,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            fig_treemap.update_traces(
                textinfo='label+value',
                textfont_size=12
            )
            st.plotly_chart(fig_treemap, use_container_width=True)
        
        # ============================================
        # 2. 🎯 SUNBURST CHART - Beautiful alternative
        # ============================================
        if train_col:
            train_counts = filtered_df[train_col].value_counts().reset_index()
            train_counts.columns = ['Train', 'Count']
            train_counts['Category'] = 'Trains'
            
            fig_sunburst = px.sunburst(
                train_counts.head(20),
                path=['Category', 'Train'],
                values='Count',
                title="☀️ Train Distribution (Sunburst)",
                color='Count',
                color_continuous_scale='Rainbow'
            )
            fig_sunburst.update_layout(
                height=450,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_sunburst, use_container_width=True)
        
        # ============================================
        # 3. 🥧 PIE CHART - Class Distribution
        # ============================================
        class_col = next((c for c in filtered_df.columns if 'CLASS' in str(c).upper()), None)
        if class_col:
            class_counts = filtered_df[class_col].value_counts().reset_index()
            class_counts.columns = ['Class', 'Count']
            
            fig_pie = px.pie(
                class_counts, 
                names='Class', 
                values='Count', 
                title="🎫 Class Distribution",
                hole=0.35,
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            fig_pie.update_traces(
                textposition='inside', 
                textinfo='percent+label',
                pull=[0.05 if i == 0 else 0 for i in range(len(class_counts))]
            )
            fig_pie.update_layout(
                height=400,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        
        # ============================================
        # 4. 📈 FREQUENCY POLYGON - Daily Trend
        # ============================================
        if doj_col:
            df_temp = filtered_df.copy()
            df_temp['_date'] = pd.to_datetime(df_temp[doj_col], format='%d-%m-%Y', errors='coerce')
            if df_temp['_date'].isna().all():
                df_temp['_date'] = pd.to_datetime(df_temp[doj_col], errors='coerce')
            
            daily = df_temp.groupby('_date').size().reset_index(name='count')
            
            if not daily.empty:
                fig_poly = go.Figure()
                fig_poly.add_trace(go.Scatter(
                    x=daily['_date'],
                    y=daily['count'],
                    mode='lines+markers',
                    name='EQ Records',
                    line=dict(color='#ff6b6b', width=3),
                    marker=dict(size=12, color='#ff6b6b', symbol='diamond'),
                    fill='tozeroy',
                    fillcolor='rgba(255, 107, 107, 0.25)'
                ))
                fig_poly.update_layout(
                    title="📈 Daily EQ Frequency Polygon",
                    xaxis_title="Date",
                    yaxis_title="Number of Records",
                    height=350,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    hovermode='x unified'
                )
                st.plotly_chart(fig_poly, use_container_width=True)
        
        # ============================================
        # 5. 📊 WATERFALL CHART - Cumulative train count
        # ============================================
        if train_col:
            train_counts = filtered_df[train_col].value_counts().reset_index()
            train_counts.columns = ['Train', 'Count']
            top_trains = train_counts.head(10)
            
            # Prepare data for waterfall
            waterfall_data = []
            total = 0
            for i, row in top_trains.iterrows():
                total += row['Count']
                waterfall_data.append({
                    'Train': row['Train'],
                    'Count': row['Count'],
                    'Cumulative': total
                })
            
            fig_waterfall = go.Figure(go.Waterfall(
                name="Cumulative EQ Count",
                orientation="v",
                measure=["relative"] * len(waterfall_data) + ["total"],
                x=[d['Train'] for d in waterfall_data] + ["Total"],
                y=[d['Count'] for d in waterfall_data] + [total],
                text=[str(d['Count']) for d in waterfall_data] + [str(total)],
                textposition="outside",
                connector={"line": {"color": "#888"}},
                increasing={"marker": {"color": "#2ecc71"}},
                decreasing={"marker": {"color": "#e74c3c"}},
                totals={"marker": {"color": "#3498db"}}
            ))
            fig_waterfall.update_layout(
                title="📊 Cumulative EQ Count (Top 10 Trains)",
                xaxis_title="Train Number",
                yaxis_title="Cumulative Count",
                height=400,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_waterfall, use_container_width=True)
        
        # ============================================
        # 6. 📋 Full List
        # ============================================
        with st.expander("📊 Train-wise EQ Count (Full List)", expanded=False):
            if train_col:
                train_counts_full = filtered_df[train_col].value_counts().reset_index()
                train_counts_full.columns = ['Train Number', 'EQ Count']
                st.dataframe(train_counts_full, use_container_width=True, height=400)
    
    else:
        st.info("No data for charts. Adjust filters or choose another sheet.")
