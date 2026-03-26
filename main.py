"""
main.py — CLI entrypoint for the Invoice-Intake Agent.

Usage:
    uv run python main.py --email ./data/Email.json

This script:
  1. Validates that the email JSON and its referenced attachment exist.
  2. Runs the Invoice-Intake Agent which extracts data and generates
     notification files in the output/ directory.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys
import time

from dotenv import load_dotenv

# Ensure UTF-8 output on Windows consoles (avoids cp1252 encoding errors)
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

load_dotenv()


def _validate_inputs(email_path: pathlib.Path) -> dict:
    """
    Validate the email JSON file and its referenced attachment.

    Returns the parsed email data dict on success, exits on failure.
    """
    # Check email file exists
    if not email_path.exists():
        print(f"❌ Email file not found: {email_path}")
        sys.exit(1)

    # Parse JSON
    try:
        with open(email_path, encoding="utf-8") as f:
            email_data = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"❌ Invalid JSON in email file: {exc}")
        sys.exit(1)

    # Check for attachments
    attachments = email_data.get("Message", {}).get("Attachments", [])
    if not attachments:
        print("⚠️  No attachments found in email JSON. The agent will proceed but extraction may be limited.")
        return email_data

    # Check each referenced attachment exists on disk
    email_dir = email_path.parent
    for att in attachments:
        att_name = att.get("Name", "")
        att_path = email_dir / att_name
        if not att_path.exists():
            print(f"❌ Referenced attachment not found: {att_path}")
            print(f"   Make sure '{att_name}' is in the same directory as the email JSON.")
            sys.exit(1)

    print(f"✅ Email file validated: {email_path}")
    print(f"✅ Attachment(s) found: {', '.join(a.get('Name', '') for a in attachments)}")
    return email_data


async def _run_agent(email_path: str) -> None:
    """Execute the Invoice-Intake Agent."""
    # Import here to avoid circular import and allow validation to run first
    from agents import Runner

    from agent import invoice_agent

    print("\n🤖 Starting Invoice-Intake Agent...")
    print(f"   Model: {invoice_agent.model}")
    print(f"   Tools: {[t.name for t in invoice_agent.tools]}")
    print("-" * 50)

    start = time.time()

    result = await Runner.run(
        invoice_agent,
        input=f"Process the invoice email at: {email_path}",
    )

    elapsed = time.time() - start

    print("\n" + "=" * 50)
    print("AGENT RESPONSE")
    print("=" * 50)
    print(result.final_output)
    print(f"\n⏱  Completed in {elapsed:.1f}s")


def main() -> None:
    """Parse CLI arguments and run the agent."""
    parser = argparse.ArgumentParser(
        prog="invoice-agent",
        description="Invoice-Intake Agent — extract and notify from email + PDF",
    )
    parser.add_argument(
        "--email",
        required=True,
        type=pathlib.Path,
        help="Path to the input email JSON file (e.g., ./data/Email.json)",
    )
    args = parser.parse_args()

    # Validate inputs
    _validate_inputs(args.email)

    # Run the agent
    asyncio.run(_run_agent(str(args.email)))


if __name__ == "__main__":
    main()
