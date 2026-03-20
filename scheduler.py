"""
Continuous scheduler — runs the DevOps job search agent on a repeating interval.

Usage:
    python scheduler.py                  # Run every 60 minutes (default)
    SEARCH_INTERVAL_MINUTES=30 python scheduler.py  # Run every 30 minutes
    python scheduler.py --run-once       # Single run then exit
"""

import sys
import time
import signal
import argparse
from datetime import datetime

import schedule

from config import SEARCH_INTERVAL_MINUTES
from agent import run_once


def _job():
    """Wrapper that catches exceptions so the scheduler keeps running."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] === Starting scheduled search run ===")
    try:
        new_leads = run_once()
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Run complete. New leads: {new_leads}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: {e}")


def _handle_shutdown(signum, frame):
    print("\nShutting down scheduler gracefully...")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="DevOps job search agent scheduler")
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run a single search cycle and exit",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=SEARCH_INTERVAL_MINUTES,
        help=f"Search interval in minutes (default: {SEARCH_INTERVAL_MINUTES})",
    )
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    if args.run_once:
        print("Running single search cycle...")
        _job()
        return

    interval = args.interval
    print(f"DevOps Job Search Agent starting — searching every {interval} minute(s)")
    print("Press Ctrl+C to stop\n")

    # Run immediately on start, then on schedule
    _job()

    schedule.every(interval).minutes.do(_job)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
