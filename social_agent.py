"""
Social Media Monitoring Agent — finds startup founders and decision-makers on
Reddit, X (Twitter), and LinkedIn who are complaining about problems Datadog solves
or are actively looking for observability/monitoring solutions.

Uses Claude with built-in web_search and web_fetch tools.
"""

import json
import anthropic
from datetime import datetime

from config import ANTHROPIC_API_KEY, MAX_SEARCHES_PER_RUN
from social_storage import (
    init_social_db, save_social_lead, start_social_run,
    complete_social_run, get_unnotified_social_leads, mark_social_notified,
)


SYSTEM_PROMPT = "You are a sales intelligence agent finding decision-makers on Reddit who are complaining about monitoring, observability, or infrastructure problems."


SEARCH_PROMPT = """Search Reddit for posts from the last 24 hours where people are
complaining about or struggling with monitoring, observability, alerting, on-call,
or infrastructure visibility problems.

The goal: find posts I can reply to with a helpful comment that offers value
and invites them to book a call.

IMPORTANT: Only posts from the last 24 hours. Skip anything older.

Do up to 5 web searches using queries like:
- site:reddit.com/r/devops "monitoring" "painful" OR "nightmare" OR "frustrated"
- site:reddit.com/r/sre "alert fatigue" OR "on-call" "burnout" OR "nightmare"
- site:reddit.com/r/devops "replacing" OR "alternatives to" "datadog" OR "new relic" OR "splunk"
- site:reddit.com/r/kubernetes "monitoring" "prometheus" "too much work" OR "painful"
- site:reddit.com/r/devops "no visibility" OR "flying blind" production

For each result:
1. Check the post date — skip if older than 24 hours
2. Fetch the post URL to read the full content
3. Note the pain being expressed — this is what the reply comment will address

Only include posts where the author appears to be a decision-maker:
founder, co-founder, CTO, VP Engineering, Head of Infrastructure, Engineering Manager,
Principal/Staff Engineer. Skip students, junior devs, or hobbyists.

Aim for 5-10 posts. Stop after 5 searches.

Output a JSON array preceded by the marker LEADS_JSON:
Each lead must follow this exact format:
{
  "platform": "reddit",
  "author": "username",
  "author_title": "inferred role or empty string",
  "company": "company name or empty string",
  "post_url": "https://...",
  "post_snippet": "First 400 chars of the post...",
  "pain_points": ["alert fatigue", "Prometheus maintenance"],
  "pain_score": 3,
  "intent": "venting"
}

Intent values: "actively_seeking", "comparing", "venting", "sharing_pain"

Output ONLY the JSON array after LEADS_JSON:
"""


def run_social_agent() -> tuple[list[dict], int]:
    """
    Run one complete social media scan using Claude with web search tools.
    Returns (leads, searches_performed).
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    messages = [{"role": "user", "content": SEARCH_PROMPT}]

    tools = [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": MAX_SEARCHES_PER_RUN},
        {"type": "web_fetch_20260209", "name": "web_fetch"},
    ]

    searches_performed = 0

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting social media scan...")

    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        tools=tools,
        messages=messages,
        thinking={"type": "adaptive"},
    ) as stream:
        final_message = stream.get_final_message()

    for block in final_message.content:
        if hasattr(block, "type") and block.type == "server_tool_use":
            if hasattr(block, "name") and block.name == "web_search":
                searches_performed += 1

    final_text = ""
    for block in final_message.content:
        if hasattr(block, "type") and block.type == "text":
            final_text += block.text

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scan complete. Searches performed: ~{searches_performed}")

    leads = _parse_leads_from_output(final_text)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Parsed {len(leads)} leads from output")

    return leads, searches_performed


def _parse_leads_from_output(text: str) -> list[dict]:
    """Extract the JSON leads array from agent output."""
    marker = "LEADS_JSON:"
    idx = text.rfind(marker)
    if idx == -1:
        start = text.rfind("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        print("WARNING: Could not find LEADS_JSON marker in agent output")
        print("Agent output tail:", text[-500:])
        return []

    json_str = text[idx + len(marker):].strip()
    try:
        leads = json.loads(json_str)
        if isinstance(leads, list):
            return leads
    except json.JSONDecodeError as e:
        print(f"WARNING: JSON parse error: {e}")
        print("Raw JSON string:", json_str[:500])
    return []


def run_once():
    """Execute one full social scan cycle: search → store → print new leads."""
    init_social_db()
    run_id = start_social_run()

    new_leads_count = 0
    searches_performed = 0

    try:
        leads, searches_performed = run_social_agent()

        for lead in leads:
            if not lead.get("post_url"):
                continue
            is_new = save_social_lead(lead)
            if is_new:
                new_leads_count += 1

        complete_social_run(run_id, new_leads_count, searches_performed)

    except Exception as e:
        print(f"ERROR during social scan: {e}")
        complete_social_run(run_id, new_leads_count, searches_performed, status="error")
        raise

    _print_new_leads()

    return new_leads_count


def _print_new_leads():
    """Print any unnotified social leads and mark them as notified."""
    leads = get_unnotified_social_leads()
    if not leads:
        print("No new social leads this run.")
        return

    print(f"\n{'='*70}")
    print(f"  {len(leads)} NEW SOCIAL MEDIA SIGNALS FOUND")
    print(f"{'='*70}")

    intent_labels = {
        "actively_seeking": "ACTIVELY SEEKING SOLUTION",
        "comparing":        "COMPARING TOOLS",
        "venting":          "VENTING ABOUT PAIN",
        "sharing_pain":     "SHARING PAST PAIN",
    }

    for lead in sorted(leads, key=lambda x: x["pain_score"], reverse=True):
        intent = intent_labels.get(lead.get("intent", ""), lead.get("intent", ""))
        print(f"\n  Platform:   {lead['platform'].upper()}")
        print(f"  Author:     {lead['author']}  [{lead.get('author_title') or 'title unknown'}]")
        if lead.get("company"):
            print(f"  Company:    {lead['company']}")
        print(f"  Intent:     {intent}")
        print(f"  Pain:       {', '.join(lead['pain_points'])} (score: {lead['pain_score']})")
        print(f"  URL:        {lead['post_url']}")
        if lead.get("post_snippet"):
            snippet = lead["post_snippet"][:300].replace("\n", " ")
            print(f"  Snippet:    {snippet}...")
        print(f"  Found:      {lead['discovered_at']}")

    print(f"\n{'='*70}\n")

    mark_social_notified([lead["id"] for lead in leads])
