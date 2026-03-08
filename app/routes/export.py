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


@bp.route("/api/reports/summary")
def api_summary():
    current_prices = CACHE.get("data", {})
    history = CACHE.get("history", {})
    summary = generate_performance_summary(current_prices, history)
    return jsonify(summary)
