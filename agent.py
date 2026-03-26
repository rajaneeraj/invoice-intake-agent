"""
agent.py — Invoice-Intake Agent definition.

Sets up the OpenAI Agent with:
  • A system prompt for single-pass extraction → notification
  • Two bound tools: extract_invoice_data, send_cs_notification
  • Model loaded from .env (defaults to gpt-5-mini)
"""

from __future__ import annotations

import os

from agents import Agent
from dotenv import load_dotenv

from tools import extract_invoice_data, send_cs_notification

load_dotenv()

PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "gpt-5-mini")

# ---------------------------------------------------------------------------
# System prompt — keeps the agent focused and cost-efficient
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are an Invoice-Intake Agent for Accounts Payable automation.

Your job is to process an inbound email with an attached invoice and produce
a structured notification for the Customer Service and Accounts Payable teams.

WORKFLOW (follow these steps exactly, in order):

1. EXTRACT — Call the `extract_invoice_data` tool with the email file path
   provided by the user. This tool will read the email JSON and its attached
   PDF, extract text and images, and return structured invoice data as JSON.

2. NOTIFY — Immediately call the `send_cs_notification` tool, passing the
   complete JSON string returned by the extraction tool. This will generate:
   • A human-readable summary  (output/cs_notification.txt)
   • A structured JSON payload (output/ap_payload.json)

3. CONFIRM — After both tools complete, provide a brief confirmation to the
   user summarising what was extracted (vendor, invoice #, total) and where
   the output files were saved.

RULES:
  • Do NOT retry tools unless they return an explicit error.
  • Do NOT modify or fabricate data — only surface what the tools return.
  • Be concise in your final confirmation.
"""

# ---------------------------------------------------------------------------
# Agent instance
# ---------------------------------------------------------------------------
invoice_agent = Agent(
    name="Invoice-Intake Agent",
    instructions=SYSTEM_PROMPT,
    model=PRIMARY_MODEL,
    tools=[extract_invoice_data, send_cs_notification],
)
