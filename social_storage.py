"""SQLite storage for social media leads."""

import sqlite3
import json
from datetime import datetime
from config import DB_PATH

SOCIAL_DB_PATH = DB_PATH.replace("jobs.db", "social_leads.db") if "jobs.db" in DB_PATH else "social_leads.db"


def init_social_db():
    """Initialize the social leads database schema."""
    conn = sqlite3.connect(SOCIAL_DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS social_leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,          -- reddit / twitter / linkedin
            author TEXT,                     -- username or handle
            author_title TEXT,               -- CTO, Founder, VP Eng, etc (if known)
            company TEXT,                    -- company name if mentioned/known
            post_url TEXT UNIQUE,            -- link to the post
            post_snippet TEXT,               -- first 500 chars of post
            pain_points TEXT,                -- JSON list of detected pain points
            pain_score INTEGER DEFAULT 0,    -- how many pain points matched
            intent TEXT,                     -- 'venting' / 'actively_seeking' / 'comparing'
            discovered_at TEXT NOT NULL,
            notified INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS social_scan_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            leads_found INTEGER DEFAULT 0,
            searches_performed INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running'
        )
    """)
    conn.commit()
    conn.close()


def save_social_lead(lead: dict) -> bool:
    """Save a social lead. Returns True if new, False if duplicate."""
    conn = sqlite3.connect(SOCIAL_DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO social_leads
                (platform, author, author_title, company, post_url,
                 post_snippet, pain_points, pain_score, intent, discovered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            lead.get("platform", ""),
            lead.get("author", ""),
            lead.get("author_title", ""),
            lead.get("company", ""),
            lead.get("post_url", ""),
            lead.get("post_snippet", ""),
            json.dumps(lead.get("pain_points", [])),
            lead.get("pain_score", 0),
            lead.get("intent", ""),
            datetime.utcnow().isoformat(),
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def start_social_run() -> int:
    """Record a new scan run and return its ID."""
    conn = sqlite3.connect(SOCIAL_DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO social_scan_runs (started_at) VALUES (?)",
        (datetime.utcnow().isoformat(),)
    )
    run_id = c.lastrowid
    conn.commit()
    conn.close()
    return run_id


def complete_social_run(run_id: int, leads_found: int, searches_performed: int, status: str = "completed"):
    """Mark a scan run as complete."""
    conn = sqlite3.connect(SOCIAL_DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE social_scan_runs
        SET completed_at=?, leads_found=?, searches_performed=?, status=?
        WHERE id=?
    """, (datetime.utcnow().isoformat(), leads_found, searches_performed, status, run_id))
    conn.commit()
    conn.close()


def get_unnotified_social_leads() -> list[dict]:
    """Return social leads that haven't been printed yet."""
    conn = sqlite3.connect(SOCIAL_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT * FROM social_leads
        WHERE notified=0
        ORDER BY pain_score DESC, discovered_at DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    for row in rows:
        row["pain_points"] = json.loads(row["pain_points"] or "[]")
    return rows


def mark_social_notified(lead_ids: list[int]):
    """Mark social leads as notified."""
    if not lead_ids:
        return
    conn = sqlite3.connect(SOCIAL_DB_PATH)
    c = conn.cursor()
    c.executemany(
        "UPDATE social_leads SET notified=1 WHERE id=?",
        [(lid,) for lid in lead_ids]
    )
    conn.commit()
    conn.close()
