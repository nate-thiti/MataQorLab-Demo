import io
import pandas as pd
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Font, Border, Side, Alignment, PatternFill
from openpyxl.chart import BarChart, Reference
from typing import Dict, Any, List, Optional

def generate_excel_report(
    df: pd.DataFrame,
    analytics_results: Dict[str, Any],
    insight: str,
    filename: str,
    locale: str = "th"
) -> io.BytesIO:
    """
    Layer 11: Report Generation - สร้างไฟล์ Excel พร้อมกราฟฝังตัว
    """
    buffer = io.BytesIO()
    wb = Workbook()

    # --- Sheet 1: Summary and Charts ---
    ws_summary = wb.active
    ws_summary.title = "Summary & Charts"

    # Title
    ws_summary['A1'] = "MataQorLab AI Analysis Report" if locale == "en" else "รายงานวิเคราะห์ข้อมูลโดย MataQorLab AI"
    ws_summary['A1'].font = Font(size=18, bold=True)
    ws_summary['A2'] = f"File: {filename}"
    ws_summary['A2'].font = Font(size=12)
    ws_summary['A3'] = f"Generated On: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}"
    ws_summary['A3'].font = Font(size=10, italic=True)

    # AI Insight
    ws_summary['A5'] = "AI Executive Summary:" if locale == "en" else "สรุปผลโดย AI:"
    ws_summary['A5'].font = Font(size=14, bold=True)
    ws_summary['A6'] = insight
    ws_summary['A6'].alignment = Alignment(wrapText=True)
    ws_summary.row_dimensions[6].height = 100 # Adjust height for summary

    # Calculated Metrics
    ws_summary['A8'] = "Calculated Metrics:" if locale == "en" else "ตัวชี้วัดที่คำนวณได้:"
    ws_summary['A8'].font = Font(size=14, bold=True)
    
    # Write formatted notes from analytics_results
    notes_start_row = 9
    if 'formatted_notes' in analytics_results:
        for i, line in enumerate(analytics_results['formatted_notes'].split('\n')):
            ws_summary[f'A{notes_start_row + i}'] = line.strip()
            ws_summary[f'A{notes_start_row + i}'].font = Font(size=10)

    # --- Embed Chart (Example: Monthly Sales Bar Chart) ---
    chart_start_row = notes_start_row + len(analytics_results.get('formatted_notes', '').split('\n')) + 2
    monthly_data = analytics_results.get('monthly_sales_for_chart')
    if monthly_data:
        chart_data_df = pd.DataFrame(monthly_data)
        
        # Write chart data to a temporary area on the summary sheet
        chart_data_start_row = chart_start_row + 10 # Place data below summary
        for r_idx, r in enumerate(dataframe_to_rows(chart_data_df, index=False, header=True)):
            for c_idx, val in enumerate(r):
                ws_summary.cell(row=chart_data_start_row + r_idx, column=c_idx + 1, value=val)

        # Create Bar Chart
        chart = BarChart()
        chart.type = "col"
        chart.style = 10
        chart.title = "Monthly Sales Trend" if locale == "en" else "แนวโน้มยอดขายรายเดือน"
        chart.y_axis.title = "Sales" if locale == "en" else "ยอดขาย"
        chart.x_axis.title = "Month" if locale == "en" else "เดือน"

        # Data for the chart
        data_ref = Reference(ws_summary, min_col=2, min_row=chart_data_start_row + 1, max_row=chart_data_start_row + len(chart_data_df), max_col=2)
        categories_ref = Reference(ws_summary, min_col=1, min_row=chart_data_start_row + 1, max_row=chart_data_start_row + len(chart_data_df), max_col=1)
        
        chart.add_data(data_ref, titles_from_data=True)
        chart.set_categories(categories_ref)

        # Customize chart appearance
        chart.shape = 4 # Rounded corners
        chart.width = 15 # inches
        chart.height = 8 # inches
        
        # Add chart to summary sheet
        ws_summary.add_chart(chart, f"A{chart_start_row}")

    # Adjust column widths for summary sheet
    ws_summary.column_dimensions['A'].width = 80

    # --- Sheet 2: Raw Data ---
    ws_data = wb.create_sheet("Raw Data" if locale == "en" else "ข้อมูลดิบ")
    
    # Write DataFrame to sheet
    for r_idx, r in enumerate(dataframe_to_rows(df, index=False, header=True)):
        ws_data.append(r)

    # Apply styling to header
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="D97706", end_color="D97706", fill_type="solid")
    thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))

    for cell in ws_data[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border
        cell.alignment = Alignment(horizontal='center', vertical='center')

    # Auto-fit column widths
    for column in ws_data.columns:
        max_length = 0
        column = [cell for cell in column]
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = (max_length + 2)
        ws_data.column_dimensions[column[0].column_letter].width = adjusted_width

    wb.save(buffer)
    buffer.seek(0)
    return buffer