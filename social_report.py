"""
Reporting tool for social media leads.

Usage:
    python social_report.py              # Recent 50 leads
    python social_report.py --all        # All leads
    python social_report.py --top 10     # Top 10 by pain score
    python social_report.py --platform reddit   # Filter by platform
    python social_report.py --intent actively_seeking
    python social_report.py --csv        # Export as CSV
"""

import argparse
import csv
import json
import sys
import sqlite3

from social_storage import SOCIAL_DB_PATH, init_social_db


def get_leads(limit=50, all_leads=False, top=None, platform=None, intent=None):
    init_social_db()
    conn = sqlite3.connect(SOCIAL_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    filters = []
    params = []
    if platform:
        filters.append("platform = ?")
        params.append(platform.lower())
    if intent:
        filters.append("intent = ?")
        params.append(intent.lower())

    where = f"WHERE {' AND '.join(filters)}" if filters else ""

    if top:
        c.execute(f"""
            SELECT * FROM social_leads {where}
            ORDER BY pain_score DESC, discovered_at DESC
            LIMIT ?
        """, params + [top])
    elif all_leads:
        c.execute(f"SELECT * FROM social_leads {where} ORDER BY discovered_at DESC", params)
    else:
        c.execute(f"""
            SELECT * FROM social_leads {where}
            ORDER BY discovered_at DESC
            LIMIT ?
        """, params + [limit])

    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    for row in rows:
        row["pain_points"] = json.loads(row["pain_points"] or "[]")
    return rows


def print_leads(leads):
    if not leads:
        print("No social leads found. Run `python social_scheduler.py --run-once` to start scanning.")
        return

    intent_labels = {
        "actively_seeking": "ACTIVELY SEEKING",
        "comparing":        "COMPARING TOOLS",
        "venting":          "VENTING",
        "sharing_pain":     "SHARING PAIN",
    }

    print(f"\n{'='*70}")
    print(f"  SOCIAL MEDIA DATADOG SIGNALS ({len(leads)} leads)")
    print(f"{'='*70}")

    for lead in leads:
        intent = intent_labels.get(lead.get("intent", ""), lead.get("intent", ""))
        print(f"\n  Platform:   {lead['platform'].upper()}")
        print(f"  Author:     {lead['author']}  [{lead.get('author_title') or 'unknown'}]")
        if lead.get("company"):
            print(f"  Company:    {lead['company']}")
        print(f"  Intent:     {intent}")
        pain = lead.get("pain_points", [])
        print(f"  Pain:       {', '.join(pain)} (score: {lead['pain_score']})")
        print(f"  URL:        {lead['post_url'] or 'N/A'}")
        if lead.get("post_snippet"):
            snippet = lead["post_snippet"][:300].replace("\n", " ")
            print(f"  Snippet:    {snippet}...")
        print(f"  Found:      {lead['discovered_at']}")

    print(f"\n{'='*70}\n")


def export_csv(leads):
    writer = csv.DictWriter(sys.stdout, fieldnames=[
        "id", "platform", "author", "author_title", "company",
        "intent", "pain_score", "pain_points", "post_url", "discovered_at",
    ])
    writer.writeheader()
    for lead in leads:
        row = {k: lead.get(k, "") for k in writer.fieldnames}
        row["pain_points"] = ", ".join(lead.get("pain_points", []))
        writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description="Report on social media Datadog signals")
    parser.add_argument("--all", action="store_true", help="Show all leads")
    parser.add_argument("--top", type=int, help="Show top N leads by pain score")
    parser.add_argument("--limit", type=int, default=50, help="Max leads (default 50)")
    parser.add_argument("--platform", help="Filter by platform: reddit, twitter, linkedin")
    parser.add_argument("--intent", help="Filter by intent: actively_seeking, comparing, venting, sharing_pain")
    parser.add_argument("--csv", action="store_true", help="Export as CSV")
    args = parser.parse_args()

    leads = get_leads(
        limit=args.limit,
        all_leads=args.all,
        top=args.top,
        platform=args.platform,
        intent=args.intent,
    )

    if args.csv:
        export_csv(leads)
    else:
        print_leads(leads)


if __name__ == "__main__":
    main()
