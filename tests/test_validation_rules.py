"""
Tests for the 10 validation rules in agents/api_ingest.py.
Validates all integrity checks as specified in s1b_ingesta_api.md.
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from agents.api_ingest import (
    APIIngestPayload,
    InventoryUsageEvent,
    PaymentBreakdown,
    ProductLine,
    ShiftAuditEvent,
    ShiftData,
    TicketEvent,
    ValidationResult,
    validate_inventory,
    validate_payload,
    validate_ticket,
)


def _make_item(quantity: int = 1) -> ProductLine:
    return ProductLine(
        item_id="P1",
        product_name="Cafe",
        group="Bebidas",
        unit_price=Decimal("50"),
        quantity=quantity,
    )


def _make_ticket(
    order_id: str = "T-001",
    subtotal: Decimal = Decimal("100"),
    tax: Decimal = Decimal("16"),
    discounts: Decimal = Decimal("0"),
    total_net: Decimal | None = None,
) -> TicketEvent:
    if total_net is None:
        total_net = subtotal + tax - discounts
    return TicketEvent(
        order_id=order_id,
        timestamp=datetime.now(),
        sucursal_id="SUC-01",
        order_type="Comedor",
        subtotal=subtotal,
        tax=tax,
        discounts=discounts,
        total_net=total_net,
        items=[_make_item()],
    )


def _make_payload(**kwargs) -> APIIngestPayload:
    defaults = dict(
        business_id=uuid4(),
        date=date.today(),
        sucursal_id="SUC-01",
        tickets=[],
        payments=[],
        shift_audit=[],
        inventory=[],
    )
    defaults.update(kwargs)
    return APIIngestPayload(**defaults)


# =====================================================================
# Rule 9: date not in the future → reject payload
# =====================================================================

def test_rule9_future_date_rejects():
    payload = _make_payload(date=date.today() + timedelta(days=1))
    result = validate_payload(payload, set(), business_exists=True)
    assert result.is_rejected is True
    assert "422" in result.reject_reason


def test_rule9_today_passes():
    payload = _make_payload(date=date.today())
    result = validate_payload(payload, set(), business_exists=True)
    assert result.is_rejected is False


def test_rule9_past_date_passes():
    payload = _make_payload(date=date.today() - timedelta(days=5))
    result = validate_payload(payload, set(), business_exists=True)
    assert result.is_rejected is False


# =====================================================================
# Rule 10: business_id not in businesses → reject payload
# =====================================================================

def test_rule10_missing_business_rejects():
    payload = _make_payload()
    result = validate_payload(payload, set(), business_exists=False)
    assert result.is_rejected is True
    assert "404" in result.reject_reason


def test_rule10_existing_business_passes():
    payload = _make_payload()
    result = validate_payload(payload, set(), business_exists=True)
    assert result.is_rejected is False


# =====================================================================
# Rule 1: tax ≈ subtotal × 0.16 (±2% tolerance)
# =====================================================================

def test_rule1_tax_mismatch_detected():
    ticket = _make_ticket(subtotal=Decimal("100"), tax=Decimal("20"))
    flags, _ = validate_ticket(ticket, None)
    assert "tax_mismatch" in flags


def test_rule1_exact_tax_passes():
    ticket = _make_ticket(subtotal=Decimal("100"), tax=Decimal("16"))
    flags, _ = validate_ticket(ticket, None)
    assert "tax_mismatch" not in flags


def test_rule1_within_tolerance_passes():
    # 2% of 16 = 0.32, so 16.30 should pass
    ticket = _make_ticket(subtotal=Decimal("100"), tax=Decimal("16.30"))
    flags, _ = validate_ticket(ticket, None)
    assert "tax_mismatch" not in flags


def test_rule1_beyond_tolerance_fails():
    # 2% of 16 = 0.32, so 16.40 should fail (deviation = 0.40/16 = 0.025 > 0.02)
    ticket = _make_ticket(subtotal=Decimal("100"), tax=Decimal("16.40"))
    flags, _ = validate_ticket(ticket, None)
    assert "tax_mismatch" in flags


# =====================================================================
# Rule 2: total_net ≈ subtotal + tax - discounts (±$1 MXN)
# =====================================================================

def test_rule2_inconsistency_detected():
    ticket = _make_ticket(
        subtotal=Decimal("100"),
        tax=Decimal("16"),
        discounts=Decimal("0"),
        total_net=Decimal("120"),  # should be 116
    )
    flags, _ = validate_ticket(ticket, None)
    assert "total_inconsistency" in flags


def test_rule2_within_tolerance_passes():
    # Within $1 tolerance
    ticket = _make_ticket(
        subtotal=Decimal("100"),
        tax=Decimal("16"),
        discounts=Decimal("0"),
        total_net=Decimal("116.90"),  # 0.90 off
    )
    flags, _ = validate_ticket(ticket, None)
    assert "total_inconsistency" not in flags


def test_rule2_exact_passes():
    ticket = _make_ticket(
        subtotal=Decimal("100"),
        tax=Decimal("16"),
        discounts=Decimal("10"),
        total_net=Decimal("106"),
    )
    flags, _ = validate_ticket(ticket, None)
    assert "total_inconsistency" not in flags


# =====================================================================
# Rule 3: Σ PaymentBreakdown == TicketEvent.total_net
# =====================================================================

def test_rule3_payment_mismatch():
    ticket = _make_ticket(total_net=Decimal("116"))
    payment = PaymentBreakdown(order_id="T-001", efectivo=Decimal("100"))
    flags, _ = validate_ticket(ticket, payment)
    assert "payment_mismatch" in flags


def test_rule3_payment_matches():
    ticket = _make_ticket(total_net=Decimal("116"))
    payment = PaymentBreakdown(order_id="T-001", efectivo=Decimal("116"))
    flags, _ = validate_ticket(ticket, payment)
    assert "payment_mismatch" not in flags


def test_rule3_no_payment_no_flag():
    ticket = _make_ticket()
    flags, _ = validate_ticket(ticket, None)
    assert "payment_mismatch" not in flags


# =====================================================================
# Rule 4: quantity >= 1 in each ProductLine → reject item
# =====================================================================

def test_rule4_zero_quantity_rejects_item():
    # NOTE: Pydantic Field(ge=1) normally prevents this, but we test
    # the validation function for programmatically constructed objects.
    ticket = _make_ticket()
    # Manually override quantity to simulate construct() without validation
    ticket.items[0].quantity = 0
    flags, rejected = validate_ticket(ticket, None)
    assert 0 in rejected


# =====================================================================
# Rule 5: order_id unique per (business_id, date) → skip
# =====================================================================

def test_rule5_duplicate_skipped():
    ticket = _make_ticket(order_id="T-DUP")
    payload = _make_payload(tickets=[ticket])
    result = validate_payload(payload, {"T-DUP"}, business_exists=True)
    assert "T-DUP" in result.skipped_order_ids
    assert "T-DUP" not in result.ticket_flags


def test_rule5_new_order_processed():
    ticket = _make_ticket(order_id="T-NEW")
    payload = _make_payload(tickets=[ticket])
    result = validate_payload(payload, {"T-OTHER"}, business_exists=True)
    assert "T-NEW" not in result.skipped_order_ids


# =====================================================================
# Rule 6: shifts not empty in ShiftAuditEvent → reject event
# =====================================================================

def test_rule6_empty_shifts_rejected():
    audit = ShiftAuditEvent(sucursal_id="SUC-01", date=date.today(), shifts=[])
    payload = _make_payload(shift_audit=[audit])
    result = validate_payload(payload, set(), business_exists=True)
    assert 0 in result.rejected_shift_audits


def test_rule6_with_shifts_passes():
    shift = ShiftData(
        turno="matutino",
        apertura=Decimal("1000"),
        cierre_x=Decimal("5000"),
        cierre_z=Decimal("8000"),
        sobrante_faltante=Decimal("50"),
    )
    audit = ShiftAuditEvent(
        sucursal_id="SUC-01", date=date.today(), shifts=[shift]
    )
    payload = _make_payload(shift_audit=[audit])
    result = validate_payload(payload, set(), business_exists=True)
    assert result.rejected_shift_audits == []


# =====================================================================
# Rule 7: current_stock >= 0 → flag negative_stock
# =====================================================================

def test_rule7_negative_stock_flagged():
    inv = InventoryUsageEvent(
        ingredient_id="ING-01",
        ingredient_name="Leche",
        unit="ml",
        consumo_teorico=Decimal("500"),
        current_stock=Decimal("-10"),
        unit_cost=Decimal("5"),
    )
    flags = validate_inventory(inv)
    assert "negative_stock" in flags


def test_rule7_zero_stock_passes():
    inv = InventoryUsageEvent(
        ingredient_id="ING-01",
        ingredient_name="Leche",
        unit="ml",
        consumo_teorico=Decimal("500"),
        current_stock=Decimal("0"),
        unit_cost=Decimal("5"),
    )
    flags = validate_inventory(inv)
    assert "negative_stock" not in flags


# =====================================================================
# Rule 8: unit_cost > 0 → flag zero_cost
# =====================================================================

def test_rule8_zero_cost_flagged():
    inv = InventoryUsageEvent(
        ingredient_id="ING-01",
        ingredient_name="Leche",
        unit="ml",
        consumo_teorico=Decimal("500"),
        current_stock=Decimal("100"),
        unit_cost=Decimal("0"),
    )
    flags = validate_inventory(inv)
    assert "zero_cost" in flags


def test_rule8_negative_cost_flagged():
    inv = InventoryUsageEvent(
        ingredient_id="ING-01",
        ingredient_name="Leche",
        unit="ml",
        consumo_teorico=Decimal("500"),
        current_stock=Decimal("100"),
        unit_cost=Decimal("-1"),
    )
    flags = validate_inventory(inv)
    assert "zero_cost" in flags


def test_rule8_positive_cost_passes():
    inv = InventoryUsageEvent(
        ingredient_id="ING-01",
        ingredient_name="Leche",
        unit="ml",
        consumo_teorico=Decimal("500"),
        current_stock=Decimal("100"),
        unit_cost=Decimal("5.50"),
    )
    flags = validate_inventory(inv)
    assert "zero_cost" not in flags


# =====================================================================
# Warnings generation
# =====================================================================

def test_warnings_tax_mismatch():
    ticket = _make_ticket(subtotal=Decimal("100"), tax=Decimal("20"))
    payload = _make_payload(tickets=[ticket])
    result = validate_payload(payload, set(), business_exists=True)
    assert any("IVA inconsistente" in w for w in result.warnings)


def test_warnings_skipped_tickets():
    ticket = _make_ticket(order_id="T-DUP")
    payload = _make_payload(tickets=[ticket])
    result = validate_payload(payload, {"T-DUP"}, business_exists=True)
    assert any("duplicados ignorados" in w for w in result.warnings)


def test_warnings_shift_rejected():
    audit = ShiftAuditEvent(sucursal_id="SUC-01", date=date.today(), shifts=[])
    payload = _make_payload(shift_audit=[audit])
    result = validate_payload(payload, set(), business_exists=True)
    assert any("turno sin datos" in w for w in result.warnings)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
