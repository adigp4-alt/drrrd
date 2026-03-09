"""Report and export routes."""

from flask import Blueprint, jsonify, render_template, send_file

from app.data_fetcher import CACHE
from app.models import query_db
from app.reports import generate_excel_report, generate_performance_summary

bp = Blueprint("export", __name__)


@bp.route("/reports")
def reports_page():
    return render_template("reports.html")


@bp.route("/api/reports/excel")
def download_excel():
    holdings = query_db("SELECT * FROM holdings")
    current_prices = CACHE.get("data", {})
    output = generate_excel_report(holdings, current_prices)
    return send_file(
        output,
        as_attachment=True,
        download_name="investment_report.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@bp.route("/api/export/ai-signals")
def export_ai_signals():
    """Export the proprietary AI signals log as a sellable CSV dataset."""
    import csv
    import io
    from flask import Response
    
    # Query all historical AI signals
    logs = query_db("SELECT * FROM ai_signal_logs ORDER BY date DESC, ticker ASC")
    
    if not logs:
        return "No AI signals have been collected yet. Please wait for the daily scheduled job or restart the server.", 404
        
    si = io.StringIO()
    # Get headers from the first row's keys
    keys = list(logs[0].keys())
    writer = csv.DictWriter(si, fieldnames=keys)
    writer.writeheader()
    writer.writerows(logs)
    
    output = si.getvalue()
    si.close()
    
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=premium_ai_signals.csv"}
    )
    

@bp.route("/api/reports/summary")
def api_summary():
    current_prices = CACHE.get("data", {})
    history = CACHE.get("history", {})
    summary = generate_performance_summary(current_prices, history)
    return jsonify(summary)
