"""
Sends an hourly email digest of new social media leads.

Requires env vars:
    ALERT_EMAIL      — where to send the digest (your email)
    SMTP_FROM        — Gmail address used to send
    SMTP_PASSWORD    — Gmail App Password (not your login password)
                       Create one at: https://myaccount.google.com/apppasswords
"""

import os
import smtplib
import sqlite3
import json
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv
from social_storage import init_social_db, SOCIAL_DB_PATH

load_dotenv()

ALERT_EMAIL   = os.getenv("ALERT_EMAIL")
SMTP_FROM     = os.getenv("SMTP_FROM")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))


def _get_recent_social_leads(since: datetime):
    init_social_db()
    conn = sqlite3.connect(SOCIAL_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT * FROM social_leads
        WHERE discovered_at >= ?
        ORDER BY pain_score DESC
    """, (since.isoformat(),))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    for row in rows:
        row["pain_points"] = json.loads(row["pain_points"] or "[]")
    return rows


def _build_html(leads, since: datetime):
    now_str   = datetime.now().strftime("%b %d, %Y %I:%M %p")
    since_str = since.strftime("%I:%M %p")

    intent_labels = {
        "actively_seeking": "Actively Seeking",
        "comparing":        "Comparing Tools",
        "venting":          "Venting",
        "sharing_pain":     "Sharing Pain",
    }

    rows = ""
    for l in leads:
        pain    = ", ".join(l["pain_points"])
        url     = l.get("post_url") or "#"
        intent  = intent_labels.get(l.get("intent", ""), l.get("intent", ""))
        snippet = (l.get("post_snippet") or "")[:250]
        rows += f"""
        <tr>
          <td>{l['platform'].upper()}</td>
          <td><a href="{url}">{l['author']}</a><br><small style="color:#888">{l.get('author_title') or ''}</small></td>
          <td>{l.get('company') or '—'}</td>
          <td>{intent}</td>
          <td>{pain}</td>
          <td style="font-size:12px;color:#555">{snippet}…</td>
          <td style="text-align:center"><strong>{l['pain_score']}</strong></td>
        </tr>"""

    empty = "<tr><td colspan='7' style='color:#888;padding:12px'>No new social leads this hour.</td></tr>"

    return f"""
    <html><body style="font-family:Arial,sans-serif;font-size:14px;color:#222;max-width:960px;margin:auto">
      <h2 style="color:#632CA6">Datadog Social Leads — {now_str}</h2>
      <p style="color:#666">Leads found since {since_str}</p>

      <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%">
        <thead style="background:#f0eafa">
          <tr>
            <th>Platform</th><th>Author</th><th>Company</th><th>Intent</th>
            <th>Pain Points</th><th>Snippet</th><th>Score</th>
          </tr>
        </thead>
        <tbody>{rows or empty}</tbody>
      </table>

      <p style="color:#aaa;font-size:12px;margin-top:24px">Sent automatically every hour</p>
    </body></html>
    """


def send_digest():
    """Fetch social leads from the last hour and email them."""
    if not all([ALERT_EMAIL, SMTP_FROM, SMTP_PASSWORD]):
        print("[emailer] Skipping — ALERT_EMAIL, SMTP_FROM, or SMTP_PASSWORD not set.")
        return

    since  = datetime.now() - timedelta(hours=1)
    leads  = _get_recent_social_leads(since)
    total  = len(leads)

    print(f"[emailer] Sending digest: {total} social lead(s)")

    subject = (
        f"[Datadog] {total} social lead{'s' if total != 1 else ''} — "
        + datetime.now().strftime("%b %d %I:%M %p")
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_FROM
    msg["To"]      = ALERT_EMAIL
    msg.attach(MIMEText(_build_html(leads, since), "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_FROM, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM, ALERT_EMAIL, msg.as_string())

    print(f"[emailer] Digest sent to {ALERT_EMAIL}")


if __name__ == "__main__":
    send_digest()
