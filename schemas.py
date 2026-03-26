"""
schemas.py — Pydantic models for structured invoice extraction.

These models enforce a strict schema on the LLM output, reducing
hallucination and guaranteeing all required fields are present.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    """A single line item from the invoice."""

    sku: str = Field(default="", description="Product SKU or item code")
    description: str = Field(default="", description="Item description")
    quantity: float = Field(default=0, description="Quantity ordered")
    unit_price: float = Field(default=0.0, description="Price per unit")
    line_total: float = Field(default=0.0, description="Total for this line (qty × unit price)")


class TaxBreakdown(BaseModel):
    """A single tax entry (e.g., HST-ON, GST, QST)."""

    tax_type: str = Field(default="", description="Tax type, e.g. HST, GST, QST, PST")
    jurisdiction: str = Field(default="", description="Jurisdiction the tax applies to, e.g. ON, QC")
    rate: str = Field(default="", description="Tax rate as a string, e.g. '13%'")
    amount: float = Field(default=0.0, description="Tax amount in the invoice currency")


class ShipToLocation(BaseModel):
    """A ship-to / delivery destination."""

    site_name: str = Field(default="", description="Destination site name")
    address: str = Field(default="", description="Street address")
    city: str = Field(default="", description="City")
    province_or_state: str = Field(default="", description="Province or state")
    postal_code: str = Field(default="", description="Postal / ZIP code")
    allocated_items: list[str] = Field(
        default_factory=list,
        description="List of items or line-item references allocated to this site",
    )


class InvoiceSchema(BaseModel):
    """
    Complete structured representation of an extracted invoice.

    Every field uses a sensible default so the LLM can omit fields
    that genuinely don't appear in the source document.
    """

    vendor_name: str = Field(default="", description="Name of the vendor / supplier")
    invoice_number: str = Field(default="", description="Invoice number (may appear only in an image)")
    invoice_date: str = Field(default="", description="Invoice issue date")
    due_date: str = Field(default="", description="Payment due date")
    payment_terms: str = Field(default="", description="Payment terms, e.g. Net 30")
    currency: str = Field(default="", description="Currency code, e.g. CAD, USD")
    customer_po_number: str = Field(default="", description="Customer purchase order number")

    subtotal: float = Field(default=0.0, description="Subtotal before taxes")
    taxes: list[TaxBreakdown] = Field(default_factory=list, description="Tax breakdown")
    total_due: float = Field(default=0.0, description="Grand total amount due")

    line_items: list[LineItem] = Field(default_factory=list, description="Table of line items")
    ship_to_locations: list[ShipToLocation] = Field(
        default_factory=list,
        description="Ship-to / delivery locations with site allocations",
    )

    notes: list[str] = Field(
        default_factory=list,
        description="Contextual notes: delivery windows, receiving requirements, duplicate warnings, etc.",
    )
