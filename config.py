"""Configuration for the DevOps job search agent."""

import os
from dotenv import load_dotenv

load_dotenv()

# Anthropic API key
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# How often to run the search (in minutes)
SEARCH_INTERVAL_MINUTES = int(os.getenv("SEARCH_INTERVAL_MINUTES", "60"))

# SQLite database file
DB_PATH = os.getenv("DB_PATH", "jobs.db")

# Max web searches per agent run (controls cost)
MAX_SEARCHES_PER_RUN = int(os.getenv("MAX_SEARCHES_PER_RUN", "5"))

# Job boards and sources to search
JOB_SOURCES = [
    "site:greenhouse.io",
    "site:lever.co",
    "site:jobs.ashbyhq.com",
    "site:boards.greenhouse.io",
    "site:apply.workable.com",
    "site:linkedin.com/jobs",
    "site:indeed.com",
]

# Datadog-signal keywords — job postings mentioning these suggest a good Datadog fit
DATADOG_SIGNAL_KEYWORDS = [
    "monitoring",
    "observability",
    "APM",
    "metrics",
    "tracing",
    "distributed tracing",
    "alerting",
    "dashboards",
    "Prometheus",
    "Grafana",
    "CloudWatch",
    "New Relic",
    "Splunk",
    "ELK stack",
    "OpenTelemetry",
    "log management",
    "infrastructure monitoring",
    "SRE",
    "site reliability",
    "on-call",
    "incident response",
    "Kubernetes",
    "Docker",
    "Terraform",
    "CI/CD",
    "cloud infrastructure",
    "AWS",
    "GCP",
    "Azure",
    "microservices",
    "service mesh",
]

# DevOps job title keywords
DEVOPS_JOB_TITLES = [
    "DevOps",
    "SRE",
    "Site Reliability",
    "Platform Engineer",
    "Infrastructure Engineer",
    "Cloud Engineer",
    "Systems Engineer",
    "DevSecOps",
    "MLOps",
    "DataOps",
    "Release Engineer",
]

# Company size threshold
MAX_COMPANY_EMPLOYEES = 1000
