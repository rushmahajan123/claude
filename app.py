"""
Local web app for Datadog lead finder.

Usage:
    python app.py
    Then open http://localhost:5000
"""

import json
import sqlite3
import threading
from flask import Flask, render_template, jsonify

from social_storage import init_social_db, SOCIAL_DB_PATH
from social_agent import run_once

app = Flask(__name__)

_scan_running = False


def _get_all_leads():
    init_social_db()
    conn = sqlite3.connect(SOCIAL_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM social_leads ORDER BY pain_score DESC, discovered_at DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    for row in rows:
        row["pain_points"] = json.loads(row["pain_points"] or "[]")
    return rows


@app.route("/")
def index():
    leads = _get_all_leads()
    return render_template("index.html", leads=leads)


@app.route("/scan", methods=["POST"])
def scan():
    global _scan_running
    if _scan_running:
        return jsonify({"status": "already_running"})

    def _run():
        global _scan_running
        _scan_running = True
        try:
            run_once()
        except Exception as e:
            print(f"Scan error: {e}")
        finally:
            _scan_running = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/scan/status")
def scan_status():
    return jsonify({"running": _scan_running})


if __name__ == "__main__":
    init_social_db()
    print("Starting Datadog Lead Finder → http://localhost:5000")
    app.run(debug=False, port=5000)
