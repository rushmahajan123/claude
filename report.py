"""
Quick reporting tool — print all leads from the database.

Usage:
    python report.py              # Show recent 50 leads
    python report.py --all        # Show all leads
    python report.py --top 10     # Top 10 by signal score
    python report.py --csv        # Export as CSV to stdout
"""

import argparse
import csv
import json
import sys
import sqlite3
from config import DB_PATH
from storage import init_db


def get_leads(limit=50, all_leads=False, top=None):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if top:
        c.execute("""
            SELECT * FROM job_leads
            ORDER BY signal_score DESC, discovered_at DESC
            LIMIT ?
        """, (top,))
    elif all_leads:
        c.execute("SELECT * FROM job_leads ORDER BY discovered_at DESC")
    else:
        c.execute("""
            SELECT * FROM job_leads
            ORDER BY discovered_at DESC
            LIMIT ?
        """, (limit,))

    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    for row in rows:
        row["datadog_signals"] = json.loads(row["datadog_signals"] or "[]")
    return rows


def print_leads(leads):
    if not leads:
        print("No leads found. Run `python scheduler.py --run-once` to start searching.")
        return

    print(f"\n{'='*70}")
    print(f"  DATADOG PROSPECTS ({len(leads)} leads)")
    print(f"{'='*70}")

    for lead in leads:
        print(f"\n  Company:    {lead['company_name']}")
        print(f"  Role:       {lead['job_title']}")
        print(f"  Size:       {lead['company_size'] or 'Unknown'}")
        print(f"  Location:   {lead['location'] or 'Unknown'}")
        signals = lead["datadog_signals"]
        print(f"  Signals:    {', '.join(signals)} (score: {lead['signal_score']})")
        print(f"  URL:        {lead['job_url'] or 'N/A'}")
        if lead.get("raw_description"):
            snippet = lead["raw_description"][:200].replace("\n", " ")
            print(f"  Snippet:    {snippet}...")
        print(f"  Found:      {lead['discovered_at']}")

    print(f"\n{'='*70}\n")


def export_csv(leads):
    writer = csv.DictWriter(sys.stdout, fieldnames=[
        "id", "company_name", "job_title", "company_size", "employee_count_estimate",
        "location", "signal_score", "datadog_signals", "job_url", "discovered_at",
    ])
    writer.writeheader()
    for lead in leads:
        row = {k: lead.get(k, "") for k in writer.fieldnames}
        row["datadog_signals"] = ", ".join(lead.get("datadog_signals", []))
        writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description="Report on discovered job leads")
    parser.add_argument("--all", action="store_true", help="Show all leads")
    parser.add_argument("--top", type=int, help="Show top N leads by signal score")
    parser.add_argument("--limit", type=int, default=50, help="Max leads to show (default 50)")
    parser.add_argument("--csv", action="store_true", help="Export as CSV")
    args = parser.parse_args()

    leads = get_leads(limit=args.limit, all_leads=args.all, top=args.top)

    if args.csv:
        export_csv(leads)
    else:
        print_leads(leads)


if __name__ == "__main__":
    main()
