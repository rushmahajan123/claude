"""SQLite storage for job leads."""

import sqlite3
import json
from datetime import datetime
from config import DB_PATH


def init_db():
    """Initialize the database schema."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS job_leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            job_title TEXT NOT NULL,
            job_url TEXT UNIQUE,
            company_size TEXT,
            employee_count_estimate INTEGER,
            location TEXT,
            datadog_signals TEXT,  -- JSON list of matched keywords
            signal_score INTEGER,  -- how many Datadog signals matched
            raw_description TEXT,
            discovered_at TEXT NOT NULL,
            notified INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS search_runs (
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


def save_lead(lead: dict) -> bool:
    """
    Save a job lead. Returns True if it's a new lead, False if duplicate.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO job_leads
                (company_name, job_title, job_url, company_size,
                 employee_count_estimate, location, datadog_signals,
                 signal_score, raw_description, discovered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            lead.get("company_name", "Unknown"),
            lead.get("job_title", "Unknown"),
            lead.get("job_url", ""),
            lead.get("company_size", ""),
            lead.get("employee_count_estimate"),
            lead.get("location", ""),
            json.dumps(lead.get("datadog_signals", [])),
            lead.get("signal_score", 0),
            lead.get("raw_description", ""),
            datetime.utcnow().isoformat(),
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Duplicate URL
        return False
    finally:
        conn.close()


def start_run() -> int:
    """Record a new search run and return its ID."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO search_runs (started_at) VALUES (?)",
        (datetime.utcnow().isoformat(),)
    )
    run_id = c.lastrowid
    conn.commit()
    conn.close()
    return run_id


def complete_run(run_id: int, leads_found: int, searches_performed: int, status: str = "completed"):
    """Mark a search run as complete."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE search_runs
        SET completed_at=?, leads_found=?, searches_performed=?, status=?
        WHERE id=?
    """, (datetime.utcnow().isoformat(), leads_found, searches_performed, status, run_id))
    conn.commit()
    conn.close()


def get_recent_leads(limit: int = 20) -> list[dict]:
    """Return the most recently discovered leads."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
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


def get_unnotified_leads() -> list[dict]:
    """Return leads that haven't been printed/notified yet."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT * FROM job_leads
        WHERE notified=0
        ORDER BY signal_score DESC, discovered_at DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    for row in rows:
        row["datadog_signals"] = json.loads(row["datadog_signals"] or "[]")
    return rows


def mark_notified(lead_ids: list[int]):
    """Mark leads as notified."""
    if not lead_ids:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executemany(
        "UPDATE job_leads SET notified=1 WHERE id=?",
        [(lid,) for lid in lead_ids]
    )
    conn.commit()
    conn.close()


def already_seen_url(url: str) -> bool:
    """Check if we've already stored a job by its URL."""
    if not url:
        return False
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM job_leads WHERE job_url=?", (url,))
    result = c.fetchone() is not None
    conn.close()
    return result
