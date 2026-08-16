import io
import base64
import matplotlib.pyplot as plt
from fpdf import FPDF
from utils.helpers import sanitize_latin, format_datetime

def generate_pdf(df, title, full=True):
    if df.empty:
        return None
    pdf = FPDF('L', 'mm', 'A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, f"AI EQMS Hub Pro - {title}", ln=True, align='C')
    pdf.set_font("Arial", '', 8)
    pdf.cell(0, 6, f"Generated: {format_datetime()} IST | Rows: {len(df)}", ln=True, align='C')
    pdf.ln(3)
    cols = list(df.columns)
    if '_sheet_row' in cols:
        cols.remove('_sheet_row')
    if len(cols) > 15:
        cols = cols[:15]
    col_width = min(25, 277 / max(len(cols), 1))
    pdf.set_font("Arial", 'B', 7)
    for c in cols:
        safe_c = sanitize_latin(str(c)[:15])
        pdf.cell(col_width, 6, safe_c, border=1)
    pdf.ln()
    pdf.set_font("Arial", '', 6)
    max_rows = len(df) if full else min(120, len(df))
    for idx, row in df.head(max_rows).iterrows():
        for c in cols:
            val = str(row.get(c, ""))[:20]
            safe_val = sanitize_latin(val)
            pdf.cell(col_width, 5, safe_val, border=1)
        pdf.ln()
        if pdf.get_y() > 185:
            pdf.add_page()
            pdf.set_font("Arial", 'B', 7)
            for c in cols:
                safe_c = sanitize_latin(str(c)[:15])
                pdf.cell(col_width, 6, safe_c, border=1)
            pdf.ln()
            pdf.set_font("Arial", '', 6)
    output = pdf.output(dest='S')
    if isinstance(output, bytearray):
        return bytes(output)
    elif isinstance(output, str):
        return output.encode('latin-1')
    else:
        return output

def create_table_image(df, title):
    if df.empty:
        return None
    cols = list(df.columns)
    if '_sheet_row' in cols:
        cols.remove('_sheet_row')
    if len(cols) > 10:
        cols = cols[:10]
    data = df[cols].head(50).values
    n_rows = min(len(df), 50)
    n_cols = len(cols)
    fig_height = max(3, 0.5 + 0.45 * n_rows)
    fig_width = max(10, 1.5 * n_cols)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    ax.axis('off')
    table = ax.table(cellText=data, colLabels=cols, loc='center', cellLoc='left')
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.6)
    for (i, j), cell in table.get_celld().items():
        if i == 0:
            cell.set_facecolor('#4a90d9')
            cell.set_text_props(color='white', weight='bold', fontsize=10)
        else:
            cell.set_facecolor('#f0f4fa' if i % 2 == 0 else 'white')
            cell.set_text_props(color='#1f2328', fontsize=9)
        cell.set_edgecolor('#cccccc')
        cell.set_height(0.04)
    plt.title(title, fontsize=14, weight='bold', pad=20, color='#1f2328')
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    buf.seek(0)
    plt.close()
    return buf.getvalue()

def build_whatsapp_message(sheet_name, selected_count, pnrs, total_rows, df):
    now_str = format_datetime()
    if not df.empty:
        cols = list(df.columns)
        if '_sheet_row' in cols:
            cols.remove('_sheet_row')
        cols = cols[:5]
        table_lines = []
        header = " | ".join([c[:8] for c in cols])
        table_lines.append(header)
        table_lines.append("-" * (len(header) + 4))
        for _, row in df.head(8).iterrows():
            row_vals = [str(row.get(c, ""))[:10] for c in cols]
            table_lines.append(" | ".join(row_vals))
        if len(df) > 8:
            table_lines.append(f"... and {len(df)-8} more rows")
        table_text = "\n".join(table_lines)
    else:
        table_text = "No data"
    if selected_count > 0 and pnrs:
        pnr_text = ", ".join(str(p) for p in pnrs[:10])
        if len(pnrs) > 10:
            pnr_text += f" (+{len(pnrs)-10} more)"
        msg = f"📊 *{sheet_name}* — {selected_count} rows selected\n🕐 {now_str}\n🎫 PNRs: {pnr_text}\n\n```\n{table_text}\n```"
    else:
        msg = f"📊 *{sheet_name}* — Total {total_rows} rows\n🕐 {now_str}\n\n```\n{table_text}\n```"
    msg += f"\n🔗 Sheet: https://docs.google.com/spreadsheets/d/1QcS3ZF3YYxSEykG0KiOUuXbTdBh0DMHdMgoqa9t8yrI/edit"
    return msg

def get_pnr_status_url(pnr):
    if not pnr or len(str(pnr)) != 10:
        return None
    return f"https://www.confirmtkt.com/pnr-status/{pnr}"
