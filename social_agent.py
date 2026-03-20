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


SYSTEM_PROMPT = """You are a sales intelligence agent for Datadog, a cloud monitoring and
observability platform. Your job is to find startup founders, CTOs, VPs of Engineering,
engineering managers, and senior engineers on Reddit, X (Twitter/X), and LinkedIn who
are expressing pain around problems that Datadog solves.

## Problems Datadog solves (what to look for)

Monitor for posts where people complain about or ask for help with:

### Observability & Monitoring Gaps
- "we have no visibility into production" / "flying blind" / "no idea what's happening in prod"
- Fragmented monitoring tools that don't talk to each other
- Can't correlate logs, metrics, and traces together
- Alert fatigue — too many noisy alerts, pages firing constantly
- Missing alerts — finding out about issues from users, not from monitoring

### Incident Response & MTTR
- Slow time-to-detect or time-to-resolve incidents
- Spending hours debugging production issues
- Can't find root cause quickly
- Poor on-call experience, burnout
- Post-mortems where "we had no data"

### Infrastructure & Kubernetes Pain
- Kubernetes monitoring is a mess / complex to set up
- Prometheus + Grafana too painful to maintain / self-hosted monitoring burden
- AWS CloudWatch is not enough / too expensive / limited
- Container monitoring gaps, no visibility into pods/nodes
- Terraform/infra-as-code with no observability

### Log Management
- Logs too expensive (Splunk, Elastic)
- Drowning in logs, can't search them efficiently
- Logs and metrics siloed from each other
- No centralized log management

### APM & Application Performance
- Can't trace requests across microservices / distributed tracing pain
- Performance regressions that slip through
- No APM in place, debugging by guessing
- "our p99 latency is spiking and we don't know why"

### Cloud Cost & Tool Sprawl
- Too many monitoring tools, paying for 3-4 overlapping things
- New Relic / Splunk too expensive, looking for alternatives
- CloudWatch limits, wanting unified multi-cloud view
- Outgrowing current monitoring as they scale

### Security & Compliance
- No real-time threat detection
- Cloud security posture problems
- Struggling with compliance visibility

## Target personas (who to look for)

Priority signals that the author is a decision-maker or influencer:
- Title/bio mentions: Founder, Co-founder, CTO, VP Engineering, Head of Infrastructure,
  VP of Platform, Principal Engineer, Staff Engineer, Engineering Manager, Director of Engineering
- Company context: startup, scale-up, Series A/B/C, "my company", "we're building", "our stack"
- Active buying signal: "evaluating", "comparing", "what do you use for X", "recommend a tool",
  "looking to replace", "tired of paying for", "we need something better"

## Platforms and subreddits to search

Reddit (high value):
- r/devops, r/sre, r/kubernetes, r/aws, r/googlecloud, r/azure
- r/ExperiencedDevs, r/engineering, r/startups, r/techleader
- r/dataengineering, r/mlops, r/docker

X/Twitter (search for):
- Tweets complaining about monitoring, Datadog alternatives, on-call burnout
- Startup founders tweeting about infrastructure pain
- "#monitoring", "#observability", "#sre", "#devops", "#kubernetes" with pain signals

LinkedIn:
- Posts from founders/CTOs about production incidents, monitoring challenges
- LinkedIn posts about "lessons learned" from outages
- People asking for tool recommendations in infrastructure/observability space

## Output format

After completing your searches, output a JSON array of leads. Each lead must be:
{
  "platform": "reddit",
  "author": "username_or_handle",
  "author_title": "CTO at a Series B startup (from their bio/context)",
  "company": "CompanyName or empty string if not mentioned",
  "post_url": "https://...",
  "post_snippet": "First 400 chars of the post...",
  "pain_points": ["alert fatigue", "Kubernetes monitoring", "Prometheus maintenance burden"],
  "pain_score": 3,
  "intent": "actively_seeking"
}

Intent values:
- "actively_seeking" — explicitly asking for tool recommendations or replacements
- "comparing" — evaluating options, asking "X vs Y"
- "venting" — complaining about pain without explicitly seeking a solution yet
- "sharing_pain" — writing about a past incident or struggle (useful for outreach)

Only include posts where the author appears to be a founder, technical decision-maker,
or senior engineer (not students or junior devs asking basic questions).
Aim for 5-15 high-quality leads per session.

Output ONLY the JSON array at the end, preceded by the marker: LEADS_JSON:
"""


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

Include ANY post with a genuine pain complaint — seniority is less important here,
as a helpful comment can reach the whole thread.

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
