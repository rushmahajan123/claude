"""
DevOps Job Search Agent — finds small companies (<1000 employees) with
job postings that signal Datadog would be a good fit.

Uses Claude with built-in web_search and web_fetch tools.
"""

import json
import anthropic
from datetime import datetime

from config import (
    ANTHROPIC_API_KEY,
    MAX_SEARCHES_PER_RUN,
    DATADOG_SIGNAL_KEYWORDS,
    DEVOPS_JOB_TITLES,
    MAX_COMPANY_EMPLOYEES,
)
from storage import init_db, save_lead, start_run, complete_run, get_unnotified_leads, mark_notified


SYSTEM_PROMPT = f"""You are a sales intelligence agent for Datadog, a cloud monitoring and observability platform.

Your job is to find small companies (fewer than {MAX_COMPANY_EMPLOYEES} employees) that have active
DevOps, SRE, infrastructure, or platform engineering job postings. These companies are
strong sales prospects for Datadog because they are building or scaling infrastructure.

## What makes a strong Datadog prospect?

A job posting signals Datadog fit when it mentions:
- Monitoring, observability, APM, metrics, tracing, alerting, dashboards
- Tools like Prometheus, Grafana, CloudWatch, New Relic, Splunk, ELK, OpenTelemetry
- Infrastructure: Kubernetes, Docker, Terraform, CI/CD pipelines
- Cloud platforms: AWS, GCP, Azure
- SRE practices: on-call rotations, incident response, SLOs/SLAs
- Microservices, service mesh, distributed systems

## Your search strategy

1. Search job boards (LinkedIn, Greenhouse, Lever, Indeed, Workable, Ashby) for DevOps/SRE/
   infrastructure/platform engineer roles
2. For each job posting found, assess:
   - Is this a small company? (< {MAX_COMPANY_EMPLOYEES} employees — check LinkedIn, Crunchbase,
     company website, or estimate from context)
   - Does the job description mention Datadog signals?
3. For promising leads, fetch the full job description to extract details
4. Return structured data for each qualifying lead

## Output format

After completing your searches, output a JSON array of leads. Each lead must be a JSON object with:
{{
  "company_name": "Acme Corp",
  "job_title": "Senior DevOps Engineer",
  "job_url": "https://...",
  "company_size": "50-200 employees",
  "employee_count_estimate": 100,
  "location": "San Francisco, CA / Remote",
  "datadog_signals": ["Prometheus", "Kubernetes", "AWS", "monitoring"],
  "signal_score": 4,
  "raw_description": "First 500 chars of job description..."
}}

Only include companies you are reasonably confident have fewer than {MAX_COMPANY_EMPLOYEES} employees.
If you cannot verify company size, include your best estimate and note it in company_size.
Aim to find at least 5-10 qualifying leads per search session.

Output ONLY the JSON array at the end (no other text after it), preceded by the marker: LEADS_JSON:
"""


SEARCH_PROMPT = """Search for DevOps, SRE, platform engineering, and infrastructure job postings
at small companies. Focus on companies that are building cloud infrastructure and would benefit
from monitoring and observability tools.

Use a variety of search queries across different job boards. For each promising result:
1. Check if the company is small (< 1000 employees)
2. Look for Datadog-signal keywords in the job description
3. Fetch the full job description when the snippet isn't detailed enough

Search queries to try (mix and match, don't repeat the same exact query):
- "devops engineer" site:greenhouse.io "series a" OR "series b" OR "startup"
- "site reliability engineer" site:lever.co monitoring observability
- "infrastructure engineer" site:jobs.ashbyhq.com kubernetes prometheus
- "platform engineer" site:boards.greenhouse.io "small team" OR "fast-growing"
- "devops" "observability" "monitoring" job posting small company -enterprise
- "SRE" "prometheus" "grafana" hiring startup 2024 2025
- "cloud infrastructure" "terraform" "kubernetes" engineer job "50 employees" OR "100 employees" OR "200 employees"
- site:linkedin.com/jobs "devops engineer" "series b" observability metrics
- "infrastructure engineer" "datadog" OR "new relic" OR "prometheus" startup hiring

Be thorough — search multiple job boards and use varied query combinations.
"""


def run_search_agent() -> list[dict]:
    """
    Run one complete search session using Claude with web search tools.
    Returns a list of job lead dicts.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    messages = [{"role": "user", "content": SEARCH_PROMPT}]

    tools = [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": MAX_SEARCHES_PER_RUN},
        {"type": "web_fetch_20260209", "name": "web_fetch"},
    ]

    leads = []
    searches_performed = 0

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting search agent run...")

    # Use streaming to handle long agent runs without timeout
    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        tools=tools,
        messages=messages,
        thinking={"type": "adaptive"},
    ) as stream:
        final_message = stream.get_final_message()

    # Count web_search tool uses from the response
    for block in final_message.content:
        if hasattr(block, "type") and block.type == "server_tool_use":
            if hasattr(block, "name") and block.name == "web_search":
                searches_performed += 1

    # Extract the LEADS_JSON output from the final text block
    final_text = ""
    for block in final_message.content:
        if hasattr(block, "type") and block.type == "text":
            final_text += block.text

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Agent completed. Searches performed: ~{searches_performed}")

    leads = _parse_leads_from_output(final_text)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Parsed {len(leads)} leads from agent output")

    return leads, searches_performed


def _parse_leads_from_output(text: str) -> list[dict]:
    """Extract the JSON leads array from agent output."""
    marker = "LEADS_JSON:"
    idx = text.rfind(marker)
    if idx == -1:
        # Try to find a JSON array anywhere in the output
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


def _score_lead(lead: dict) -> dict:
    """Ensure signal_score is computed from datadog_signals list."""
    signals = lead.get("datadog_signals", [])
    if isinstance(signals, list):
        lead["signal_score"] = len(signals)
    return lead


def run_once():
    """Execute one full search cycle: search → store → print new leads."""
    init_db()
    run_id = start_run()

    new_leads_count = 0
    searches_performed = 0

    try:
        leads, searches_performed = run_search_agent()

        for lead in leads:
            lead = _score_lead(lead)
            # Only store leads under the employee threshold
            emp = lead.get("employee_count_estimate")
            if emp is not None and emp > MAX_COMPANY_EMPLOYEES:
                continue
            is_new = save_lead(lead)
            if is_new:
                new_leads_count += 1

        complete_run(run_id, new_leads_count, searches_performed)

    except Exception as e:
        print(f"ERROR during search run: {e}")
        complete_run(run_id, new_leads_count, searches_performed, status="error")
        raise

    # Print new leads to stdout
    _print_new_leads()

    return new_leads_count


def _print_new_leads():
    """Print any unnotified leads and mark them as notified."""
    leads = get_unnotified_leads()
    if not leads:
        print("No new leads this run.")
        return

    print(f"\n{'='*70}")
    print(f"  {len(leads)} NEW DATADOG PROSPECTS FOUND")
    print(f"{'='*70}")

    for lead in sorted(leads, key=lambda x: x["signal_score"], reverse=True):
        print(f"\n  Company:    {lead['company_name']}")
        print(f"  Role:       {lead['job_title']}")
        print(f"  Size:       {lead['company_size']}")
        print(f"  Location:   {lead['location']}")
        print(f"  Signals:    {', '.join(lead['datadog_signals'])} (score: {lead['signal_score']})")
        print(f"  URL:        {lead['job_url']}")
        if lead.get("raw_description"):
            snippet = lead["raw_description"][:200].replace("\n", " ")
            print(f"  Snippet:    {snippet}...")
        print(f"  Found:      {lead['discovered_at']}")

    print(f"\n{'='*70}\n")

    mark_notified([lead["id"] for lead in leads])
