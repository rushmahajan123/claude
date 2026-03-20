"""
Social media monitoring scheduler — scans Reddit, X, and LinkedIn for founders and
decision-makers expressing Datadog-solvable pain.

Usage:
    python social_scheduler.py                   # Run every 120 minutes (default)
    SOCIAL_SCAN_INTERVAL_MINUTES=60 python social_scheduler.py
    python social_scheduler.py --run-once        # Single run then exit
"""

import sys
import time
import signal
import argparse
from datetime import datetime

import schedule

from social_agent import run_once
from emailer import send_digest

SOCIAL_SCAN_INTERVAL_MINUTES = 60


def _job():
    """Wrapper that catches exceptions so the scheduler keeps running."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] === Starting social media scan ===")
    try:
        new_leads = run_once()
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Scan complete. New signals: {new_leads}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR during scan: {e}")

    try:
        send_digest()
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR sending email: {e}")


def _handle_shutdown(signum, frame):
    print("\nShutting down social media scanner gracefully...")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Social media Datadog signal scanner")
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run a single scan cycle and exit",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=SOCIAL_SCAN_INTERVAL_MINUTES,
        help=f"Scan interval in minutes (default: {SOCIAL_SCAN_INTERVAL_MINUTES})",
    )
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    if args.run_once:
        print("Running single social media scan...")
        _job()
        return

    interval = args.interval
    print(f"Social Media Scanner starting — scanning every {interval} minute(s)")
    print("Platforms: Reddit, X (Twitter), LinkedIn")
    print("Press Ctrl+C to stop\n")

    # Run immediately on start, then on schedule
    _job()

    schedule.every(interval).minutes.do(_job)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
