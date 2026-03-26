# Invoice-Intake Agent

An automated Python agent built with the **OpenAI Agents SDK** that processes inbound emails with attached PDF invoices. It extracts structured billing and logistical data — including fields embedded in images — and generates notification payloads for Customer Service and Accounts Payable teams.

## Architecture

```
Email JSON ──→ ┌──────────────────────────┐
               │   Invoice-Intake Agent   │
               │    (configurable model)   │
               │                          │
Invoice PDF ──→│  Tool 1: Extract Data    │──→ Structured Invoice JSON
               │   • PyMuPDF text parse   │
               │   • Vision (page images) │
               │   • Pydantic validation  │
               │                          │
               │  Tool 2: Send Notify     │──→ cs_notification.txt
               │   • Bulleted summary     │──→ ap_payload.json
               └──────────────────────────┘
```

## Quick Start

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- An OpenAI API key with access to `gpt-5-mini` (default model; `gpt-5-nano` optional)

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/rajaneeraj/invoice-intake-agent.git
cd invoice-intake-agent

# 2. Install dependencies
uv sync

# 3. Configure your API key
#    Create a .env file in the project root:
echo "OPENAI_API_KEY=sk-your-key-here" > .env
```

### Run

```bash
uv run python main.py --email ./data/Email.json
```

### Configure Models

Edit `.env` to swap models without changing code:

```env
OPENAI_API_KEY=sk-your-key-here
PRIMARY_MODEL=gpt-5-mini       # Used for extraction (supports vision)
LIGHTWEIGHT_MODEL=gpt-5-nano   # Available for lightweight tasks
```

## Output Files

After a successful run, two files are generated in `output/`:

| File | Purpose |
|------|---------|
| `cs_notification.txt` | Human-readable bulleted summary for Customer Service |
| `ap_payload.json` | Structured JSON payload for downstream ERP / Accounting systems |

## Project Structure

```
Invoice-IntakeAgent/
├── main.py          # CLI entrypoint (argparse)
├── agent.py         # Agent definition + system prompt
├── tools.py         # Two agent tools (extractor + notifier)
├── schemas.py       # Pydantic models for extraction schema
├── .env             # API key + model config (gitignored)
├── .gitignore
├── pyproject.toml
├── README.md
├── data/
│   ├── Email.json   # Sample input email
│   └── Invoice.pdf  # Sample attached invoice
└── output/          # Generated at runtime
    ├── cs_notification.txt
    └── ap_payload.json
```

## Extracted Fields

The agent extracts the following fields from the email + PDF:

- **Vendor**: name
- **Invoice**: number, date, due date, payment terms, currency
- **Financials**: subtotal, taxes (with breakdown), total due
- **Customer PO**: purchase order number
- **Line Items**: SKU, description, quantity, unit price, line total
- **Ship-To Locations**: site name, address, allocated items
- **Notes**: delivery windows, receiving requirements, duplicate warnings

## Error Handling

- Missing email JSON → clear error message with expected path
- Missing PDF attachment → checks that referenced file exists before running
- Unreadable PDF → graceful fallback with error reporting
- Invalid LLM output → validation error with raw output for debugging

## License

MIT
