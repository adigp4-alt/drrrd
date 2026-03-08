"""Report generation for Excel export and performance summaries."""

import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.chart import BarChart, Reference

from app.config import TIERS


def generate_excel_report(holdings, current_prices):
    """Generate an Excel report with portfolio data and charts."""
    wb = Workbook()

    # --- Portfolio Holdings Sheet ---
    ws = wb.active
    ws.title = "Portfolio"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2E86C1", end_color="2E86C1", fill_type="solid")
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )

    headers = ["Ticker", "Name", "Tier", "Shares", "Buy Price", "Current Price",
               "Cost Basis", "Market Value", "P&L ($)", "P&L (%)", "Allocation %"]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border
        cell.alignment = Alignment(horizontal="center")

    total_value = 0
    rows_data = []
    for h in holdings:
        ticker = h["ticker"]
        price_data = current_prices.get(ticker, {})
        current = price_data.get("price", h["buy_price"])
        cost_basis = h["shares"] * h["buy_price"]
        market_value = h["shares"] * current
        pnl = market_value - cost_basis
        pnl_pct = (pnl / cost_basis * 100) if cost_basis else 0
        total_value += market_value
        rows_data.append({
            "ticker": ticker,
            "name": price_data.get("name", ticker),
            "tier": price_data.get("tier", ""),
            "shares": h["shares"],
            "buy_price": h["buy_price"],
            "current": current,
            "cost_basis": cost_basis,
            "market_value": market_value,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
        })

    for i, rd in enumerate(rows_data):
        row = i + 2
        alloc = (rd["market_value"] / total_value * 100) if total_value else 0
        values = [rd["ticker"], rd["name"], rd["tier"], rd["shares"],
                  rd["buy_price"], rd["current"], rd["cost_basis"],
                  rd["market_value"], rd["pnl"], rd["pnl_pct"], alloc]
        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=round(val, 2) if isinstance(val, float) else val)
            cell.border = thin_border
            if col in (5, 6, 7, 8, 9):
                cell.number_format = '$#,##0.00'
            elif col in (10, 11):
                cell.number_format = '0.00"%"'

    # P&L chart
    if rows_data:
        chart = BarChart()
        chart.title = "P&L by Position"
        chart.y_axis.title = "P&L ($)"
        data = Reference(ws, min_col=9, min_row=1, max_row=len(rows_data) + 1)
        cats = Reference(ws, min_col=1, min_row=2, max_row=len(rows_data) + 1)
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        chart.width = 20
        ws.add_chart(chart, "A" + str(len(rows_data) + 4))

    # --- Market Overview Sheet ---
    ws2 = wb.create_sheet("Market Overview")
    headers2 = ["Ticker", "Name", "Tier", "Price", "Change %", "Volume"]
    for col, header in enumerate(headers2, 1):
        cell = ws2.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border

    row = 2
    for ticker, data in current_prices.items():
        values = [ticker, data.get("name", ""), data.get("tier", ""),
                  data.get("price", 0), data.get("change_pct", 0), data.get("volume", 0)]
        for col, val in enumerate(values, 1):
            cell = ws2.cell(row=row, column=col, value=val)
            cell.border = thin_border
        row += 1

    # Auto-size columns
    for ws_sheet in [ws, ws2]:
        for col in ws_sheet.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            ws_sheet.column_dimensions[col[0].column_letter].width = min(max_len + 2, 25)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def generate_performance_summary(current_prices, history_data):
    """Generate a performance summary dict."""
    if not current_prices:
        return {"error": "No data available"}

    tickers = list(current_prices.keys())
    sorted_by_change = sorted(tickers, key=lambda t: current_prices[t].get("change_pct", 0))

    top_gainers = []
    for t in reversed(sorted_by_change[-5:]):
        d = current_prices[t]
        top_gainers.append({"ticker": t, "change_pct": d["change_pct"], "price": d["price"]})

    top_losers = []
    for t in sorted_by_change[:5]:
        d = current_prices[t]
        top_losers.append({"ticker": t, "change_pct": d["change_pct"], "price": d["price"]})

    # Tier performance
    tier_perf = {}
    for tid, tdata in TIERS.items():
        changes = []
        for sym in tdata["tickers"]:
            if sym in current_prices:
                changes.append(current_prices[sym].get("change_pct", 0))
        if changes:
            tier_perf[tid] = {
                "name": tdata["name"],
                "avg_change": round(sum(changes) / len(changes), 2),
                "best": max(changes),
                "worst": min(changes),
            }

    return {
        "total_tickers": len(current_prices),
        "top_gainers": top_gainers,
        "top_losers": top_losers,
        "tier_performance": tier_perf,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
