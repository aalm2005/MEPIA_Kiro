#!/usr/bin/env python3
"""
tests/generate_test_dataset.py — Generador de dataset de prueba para MEPIA

Genera:
  - 15 JSON de facturas de proveedor (contratos N02)
  - 15 JSON de reportes POS (contratos N01)
  - 5 PDFs de facturas para probar factura_parser.py (requiere fpdf2)

Incluye anomalías financieras definidas en s4_auditoria_ia.md:
  - Facturas duplicadas (mismo SHA-256 + business_id)
  - Discrepancias de caja (source_discrepancy)
  - Picos de costo (cost_spike)
  - Fugas de margen (margin_leak)
  - Techos operacionales (operational_ceiling)

Lógica NIIF para desglose de impuestos:
  - IVA 16% sobre subtotal
  - Retención ISR 10% (servicios profesionales)
  - Retención IVA 10.6667% del IVA (servicios profesionales)

Uso:
    python tests/generate_test_dataset.py [--output-dir tests/fixtures]
"""
import argparse
import json
import os
import random
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
DEFAULT_OUTPUT_DIR = "tests/fixtures"
BUSINESS_ID = str(uuid.uuid4())
SEED = 42

# IVA México (NIIF / CFDI)
IVA_RATE = Decimal("0.16")
# Retenciones para servicios profesionales
ISR_RETENTION_RATE = Decimal("0.10")
IVA_RETENTION_RATE = Decimal("0.106667")

random.seed(SEED)


# ---------------------------------------------------------------------------
# Catálogos de datos realistas para restaurante
# ---------------------------------------------------------------------------
SUPPLIERS = [
    {"name": "Distribuidora La Paloma SA de CV", "rfc": "DLP200101AAA"},
    {"name": "Lácteos del Valle SA", "rfc": "LVA190515BBB"},
    {"name": "Café Orgánico Chiapas SPR", "rfc": "COC180301CCC"},
    {"name": "Carnes Selectas del Norte SA", "rfc": "CSN170820DDD"},
    {"name": "Frutas y Verduras El Huerto SC", "rfc": "FVH160610EEE"},
    {"name": "Panadería Industrial Moderna SA", "rfc": "PIM210405FFF"},
    {"name": "Bebidas y Refrescos del Centro SA", "rfc": "BRC200901GGG"},
    {"name": "Aceites y Grasas Premium SA", "rfc": "AGP190101HHH"},
    {"name": "Servicios de Limpieza ProClean SC", "rfc": "SLP220101III"},
    {"name": "Mantenimiento Integral Gastro SA", "rfc": "MIG210601JJJ"},
]

CONCEPTS_INSUMOS = [
    ("Leche entera 24 piezas", "proveedor", Decimal("280.00")),
    ("Café grano arábica 5kg", "proveedor", Decimal("1250.00")),
    ("Azúcar refinada 10kg", "proveedor", Decimal("185.00")),
    ("Harina de trigo 25kg", "proveedor", Decimal("320.00")),
    ("Aceite vegetal 20L", "proveedor", Decimal("480.00")),
    ("Pollo entero 10kg", "proveedor", Decimal("890.00")),
    ("Queso manchego 5kg", "proveedor", Decimal("650.00")),
    ("Jitomate bola 10kg", "proveedor", Decimal("175.00")),
    ("Cebolla blanca 10kg", "proveedor", Decimal("95.00")),
    ("Servilletas 1000 pzas", "proveedor", Decimal("120.00")),
]

CONCEPTS_SERVICIOS = [
    ("Servicio de fumigación mensual", "proveedor", Decimal("2500.00")),
    ("Mantenimiento máquina espresso", "proveedor", Decimal("3800.00")),
    ("Servicio de limpieza profunda", "proveedor", Decimal("1800.00")),
]

POS_MENU_ITEMS = [
    {"description": "Café Americano", "unit_price": Decimal("45.00")},
    {"description": "Café Latte", "unit_price": Decimal("65.00")},
    {"description": "Cappuccino", "unit_price": Decimal("60.00")},
    {"description": "Espresso Doble", "unit_price": Decimal("50.00")},
    {"description": "Té Chai Latte", "unit_price": Decimal("55.00")},
    {"description": "Croissant", "unit_price": Decimal("40.00")},
    {"description": "Sandwich Club", "unit_price": Decimal("95.00")},
    {"description": "Ensalada César", "unit_price": Decimal("85.00")},
    {"description": "Jugo Natural", "unit_price": Decimal("50.00")},
    {"description": "Agua Mineral", "unit_price": Decimal("25.00")},
    {"description": "Pastel del Día", "unit_price": Decimal("75.00")},
    {"description": "Molletes", "unit_price": Decimal("70.00")},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _dec(val: Decimal | float | int, places: int = 2) -> float:
    """Redondea Decimal a float con N decimales para JSON."""
    d = Decimal(str(val)).quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)
    return float(d)


def _uuid() -> str:
    return str(uuid.uuid4())


def _random_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def _niif_tax_breakdown(subtotal: Decimal, is_service: bool = False) -> dict:
    """
    Calcula desglose de impuestos según NIIF / CFDI México.

    Para bienes (insumos):
      - IVA trasladado: 16% del subtotal
      - Total = subtotal + IVA

    Para servicios profesionales:
      - IVA trasladado: 16% del subtotal
      - Retención ISR: 10% del subtotal
      - Retención IVA: 10.6667% del IVA trasladado
      - Total = subtotal + IVA - retención ISR - retención IVA
    """
    iva_trasladado = (subtotal * IVA_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if is_service:
        retencion_isr = (subtotal * ISR_RETENTION_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        retencion_iva = (iva_trasladado * IVA_RETENTION_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total = subtotal + iva_trasladado - retencion_isr - retencion_iva
        return {
            "subtotal": _dec(subtotal),
            "iva_trasladado": _dec(iva_trasladado),
            "retencion_isr": _dec(retencion_isr),
            "retencion_iva": _dec(retencion_iva),
            "total": _dec(total),
            "tasa_iva": 0.16,
            "tasa_retencion_isr": 0.10,
            "tasa_retencion_iva": 0.106667,
        }
    else:
        total = subtotal + iva_trasladado
        return {
            "subtotal": _dec(subtotal),
            "iva_trasladado": _dec(iva_trasladado),
            "retencion_isr": 0.0,
            "retencion_iva": 0.0,
            "total": _dec(total),
            "tasa_iva": 0.16,
        }


# ---------------------------------------------------------------------------
# Generadores de facturas (N02)
# ---------------------------------------------------------------------------

def _generate_factura_normal(idx: int, tx_date: date) -> dict:
    """Genera una factura normal de proveedor (insumo) con desglose NIIF."""
    supplier = random.choice(SUPPLIERS[:8])  # primeros 8 son insumos
    concept_name, category, base_amount = random.choice(CONCEPTS_INSUMOS)
    # Variación de precio ±15%
    variation = Decimal(str(random.uniform(0.85, 1.15)))
    subtotal = (base_amount * variation).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    taxes = _niif_tax_breakdown(subtotal, is_service=False)
    folio = f"FAC-{tx_date.year}-{idx:05d}"

    return {
        "file_id": _uuid(),
        "storage_path": f"facturas/{BUSINESS_ID}/{tx_date.isoformat()}/{_uuid()}.xml",
        "extraction_status": "success",
        "needs_human_review": False,
        "ocr_confidence": None,
        "transaction_id": _uuid(),
        "extracted_fields": {
            "transaction_date": tx_date.isoformat(),
            "amount": taxes["total"],
            "tax_amount": taxes["iva_trasladado"],
            "supplier_name": supplier["name"],
            "concept": concept_name,
            "document_reference": folio,
        },
        "missing_fields": None,
        "niif_tax_breakdown": taxes,
        "raw_metadata": {
            "rfc_emisor": supplier["rfc"],
            "category": category,
            "document_type": "XML",
            "cfdi_version": "4.0",
        },
        "_anomaly": None,
    }


def _generate_factura_servicio(idx: int, tx_date: date) -> dict:
    """Genera una factura de servicio profesional con retenciones NIIF."""
    supplier = random.choice(SUPPLIERS[8:])  # últimos 2 son servicios
    concept_name, category, base_amount = random.choice(CONCEPTS_SERVICIOS)
    subtotal = base_amount
    taxes = _niif_tax_breakdown(subtotal, is_service=True)
    folio = f"SRV-{tx_date.year}-{idx:05d}"

    return {
        "file_id": _uuid(),
        "storage_path": f"facturas/{BUSINESS_ID}/{tx_date.isoformat()}/{_uuid()}.xml",
        "extraction_status": "success",
        "needs_human_review": False,
        "ocr_confidence": None,
        "transaction_id": _uuid(),
        "extracted_fields": {
            "transaction_date": tx_date.isoformat(),
            "amount": taxes["total"],
            "tax_amount": taxes["iva_trasladado"],
            "supplier_name": supplier["name"],
            "concept": concept_name,
            "document_reference": folio,
        },
        "missing_fields": None,
        "niif_tax_breakdown": taxes,
        "raw_metadata": {
            "rfc_emisor": supplier["rfc"],
            "category": category,
            "document_type": "XML",
            "cfdi_version": "4.0",
            "has_retentions": True,
        },
        "_anomaly": None,
    }


def _generate_factura_duplicada(original: dict) -> dict:
    """
    Genera una factura duplicada (mismo SHA-256 + business_id).
    Anomalía S4: source_discrepancy — severity: high.
    """
    dup = json.loads(json.dumps(original))
    dup["file_id"] = original["file_id"]  # mismo file_id = duplicado
    dup["_anomaly"] = {
        "type": "source_discrepancy",
        "description": "Factura duplicada detectada — mismo SHA-256 y business_id",
        "severity": "high",
    }
    return dup


def _generate_factura_cost_spike(idx: int, tx_date: date) -> dict:
    """
    Genera una factura con pico de costo anómalo (>15% sobre promedio).
    Anomalía S4: cost_spike — severity: high.
    """
    supplier = SUPPLIERS[0]  # Distribuidora La Paloma — proveedor recurrente
    concept_name = "Leche entera 24 piezas"
    # Precio normal ~280, spike a 420 (+50%)
    subtotal = Decimal("420.00")
    taxes = _niif_tax_breakdown(subtotal, is_service=False)
    folio = f"FAC-{tx_date.year}-{idx:05d}"

    return {
        "file_id": _uuid(),
        "storage_path": f"facturas/{BUSINESS_ID}/{tx_date.isoformat()}/{_uuid()}.xml",
        "extraction_status": "success",
        "needs_human_review": False,
        "ocr_confidence": None,
        "transaction_id": _uuid(),
        "extracted_fields": {
            "transaction_date": tx_date.isoformat(),
            "amount": taxes["total"],
            "tax_amount": taxes["iva_trasladado"],
            "supplier_name": supplier["name"],
            "concept": concept_name,
            "document_reference": folio,
        },
        "missing_fields": None,
        "niif_tax_breakdown": taxes,
        "raw_metadata": {
            "rfc_emisor": supplier["rfc"],
            "category": "proveedor",
            "document_type": "XML",
            "cfdi_version": "4.0",
            "price_vs_average": "+50%",
        },
        "_anomaly": {
            "type": "cost_spike",
            "description": "Precio de leche 50% sobre promedio histórico",
            "severity": "high",
            "quantified_impact": "+$140.00 MXN sobre precio promedio",
        },
    }


def _generate_factura_needs_review(idx: int, tx_date: date) -> dict:
    """Genera una factura PDF con confianza baja que requiere revisión humana."""
    supplier = random.choice(SUPPLIERS[:5])
    folio = f"PDF-{tx_date.year}-{idx:05d}"

    return {
        "file_id": _uuid(),
        "storage_path": f"facturas/{BUSINESS_ID}/{tx_date.isoformat()}/{_uuid()}.pdf",
        "extraction_status": "needs_human_review",
        "needs_human_review": True,
        "ocr_confidence": round(random.uniform(0.55, 0.84), 2),
        "transaction_id": None,
        "extracted_fields": None,
        "missing_fields": random.sample(
            ["supplier_name", "document_reference", "amount", "transaction_date"],
            k=random.randint(1, 3),
        ),
        "niif_tax_breakdown": None,
        "raw_metadata": {
            "document_type": "PDF",
            "raw_text_length": random.randint(200, 800),
        },
        "_anomaly": None,
    }


def generate_facturas(n: int = 15) -> list[dict]:
    """
    Genera N facturas con distribución de anomalías:
      - 8 normales (insumos)
      - 2 servicios profesionales (con retenciones)
      - 1 duplicada
      - 2 con pico de costo
      - 2 que requieren revisión humana
    """
    start = date(2024, 1, 1)
    end = date(2024, 3, 31)
    facturas: list[dict] = []

    # 8 facturas normales de insumos
    for i in range(8):
        tx_date = _random_date(start, end)
        facturas.append(_generate_factura_normal(i + 1, tx_date))

    # 2 facturas de servicios profesionales
    for i in range(2):
        tx_date = _random_date(start, end)
        facturas.append(_generate_factura_servicio(i + 100, tx_date))

    # 1 factura duplicada (copia de la primera)
    facturas.append(_generate_factura_duplicada(facturas[0]))

    # 2 facturas con pico de costo
    for i in range(2):
        tx_date = _random_date(start, end)
        facturas.append(_generate_factura_cost_spike(i + 200, tx_date))

    # 2 facturas que requieren revisión humana
    for i in range(2):
        tx_date = _random_date(start, end)
        facturas.append(_generate_factura_needs_review(i + 300, tx_date))

    return facturas[:n]


# ---------------------------------------------------------------------------
# Generadores de reportes POS (N01)
# ---------------------------------------------------------------------------

def _generate_pos_normal(idx: int, pos_date: date) -> dict:
    """Genera un reporte POS normal de un día."""
    # Generar line items aleatorios
    num_items = random.randint(5, 10)
    selected_items = random.sample(POS_MENU_ITEMS, min(num_items, len(POS_MENU_ITEMS)))
    line_items = []
    total_from_items = Decimal("0.00")

    for item in selected_items:
        qty = random.randint(5, 60)
        line_items.append({
            "description": item["description"],
            "quantity": qty,
            "unit_price": _dec(item["unit_price"]),
        })
        total_from_items += item["unit_price"] * qty

    # Distribución efectivo/tarjeta
    cash_pct = Decimal(str(random.uniform(0.40, 0.70)))
    cash_sales = (total_from_items * cash_pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    card_sales = total_from_items - cash_sales

    return {
        "file_id": _uuid(),
        "storage_path": f"pos-tickets/{BUSINESS_ID}/{pos_date.isoformat()}/{_uuid()}.pdf",
        "extraction_status": "success",
        "needs_human_review": False,
        "uploaded_at": datetime(pos_date.year, pos_date.month, pos_date.day, 22, 0, 0).isoformat() + "Z",
        "date": pos_date.isoformat(),
        "totals": {
            "cash": _dec(cash_sales),
            "card": _dec(card_sales),
            "total": _dec(total_from_items),
        },
        "payment_methods": {
            "cash": _dec(cash_sales),
            "card": _dec(card_sales),
            "other": 0.0,
        },
        "line_items": line_items,
        "ocr_confidence": {
            "totals": round(random.uniform(0.93, 0.99), 2),
            "payment_methods": round(random.uniform(0.92, 0.98), 2),
            "line_items": round(random.uniform(0.83, 0.95), 2),
        },
        "missing_fields": None,
        "_anomaly": None,
    }


def _generate_pos_cash_discrepancy(idx: int, pos_date: date) -> dict:
    """
    Genera un reporte POS con discrepancia de caja.
    Anomalía S4: source_discrepancy — severity: high.
    El total de line_items no coincide con totals.total.
    """
    pos = _generate_pos_normal(idx, pos_date)

    # Inflar el total reportado vs lo que suman los items
    real_total = sum(
        Decimal(str(item["unit_price"])) * item["quantity"]
        for item in pos["line_items"]
    )
    inflated_total = real_total + Decimal(str(random.randint(200, 500)))
    cash_portion = (inflated_total * Decimal("0.55")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    card_portion = inflated_total - cash_portion

    pos["totals"] = {
        "cash": _dec(cash_portion),
        "card": _dec(card_portion),
        "total": _dec(inflated_total),
    }
    pos["payment_methods"] = {
        "cash": _dec(cash_portion),
        "card": _dec(card_portion),
        "other": 0.0,
    }
    pos["_anomaly"] = {
        "type": "source_discrepancy",
        "description": f"Total reportado ({_dec(inflated_total)}) no coincide con suma de line_items ({_dec(real_total)})",
        "severity": "high",
        "quantified_impact": f"-{_dec(inflated_total - real_total)} MXN",
        "line_items_sum": _dec(real_total),
        "reported_total": _dec(inflated_total),
    }
    return pos


def _generate_pos_margin_leak(idx: int, pos_date: date) -> dict:
    """
    Genera un reporte POS con ventas muy bajas (fuga de margen).
    Anomalía S4: margin_leak — severity: high.
    """
    # Solo 2-3 items vendidos, cantidades mínimas
    selected = random.sample(POS_MENU_ITEMS, 3)
    line_items = []
    total = Decimal("0.00")
    for item in selected:
        qty = random.randint(1, 3)
        line_items.append({
            "description": item["description"],
            "quantity": qty,
            "unit_price": _dec(item["unit_price"]),
        })
        total += item["unit_price"] * qty

    cash = (total * Decimal("0.60")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    card = total - cash

    return {
        "file_id": _uuid(),
        "storage_path": f"pos-tickets/{BUSINESS_ID}/{pos_date.isoformat()}/{_uuid()}.pdf",
        "extraction_status": "success",
        "needs_human_review": False,
        "uploaded_at": datetime(pos_date.year, pos_date.month, pos_date.day, 22, 0, 0).isoformat() + "Z",
        "date": pos_date.isoformat(),
        "totals": {
            "cash": _dec(cash),
            "card": _dec(card),
            "total": _dec(total),
        },
        "payment_methods": {
            "cash": _dec(cash),
            "card": _dec(card),
            "other": 0.0,
        },
        "line_items": line_items,
        "ocr_confidence": {
            "totals": 0.95,
            "payment_methods": 0.94,
            "line_items": 0.88,
        },
        "missing_fields": None,
        "_anomaly": {
            "type": "margin_leak",
            "description": f"Ventas del día extremadamente bajas: {_dec(total)} MXN",
            "severity": "high",
            "quantified_impact": f"Venta total {_dec(total)} MXN — posible fuga de margen",
        },
    }


def _generate_pos_operational_ceiling(idx: int, pos_date: date) -> dict:
    """
    Genera un reporte POS que evidencia techo operacional.
    Anomalía S4: operational_ceiling — severity: medium.
    Muchos items pero cantidades saturadas (mismo volumen todos los días).
    """
    pos = _generate_pos_normal(idx, pos_date)
    # Forzar cantidades idénticas (techo operacional)
    ceiling_qty = 42
    for item in pos["line_items"]:
        item["quantity"] = ceiling_qty

    # Recalcular totales
    total = sum(
        Decimal(str(item["unit_price"])) * item["quantity"]
        for item in pos["line_items"]
    )
    cash = (total * Decimal("0.50")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    card = total - cash
    pos["totals"] = {"cash": _dec(cash), "card": _dec(card), "total": _dec(total)}
    pos["payment_methods"] = {"cash": _dec(cash), "card": _dec(card), "other": 0.0}
    pos["_anomaly"] = {
        "type": "operational_ceiling",
        "description": f"Todas las líneas con qty={ceiling_qty} — posible techo de producción",
        "severity": "medium",
        "quantified_impact": f"techo: {ceiling_qty} unidades/producto/día",
    }
    return pos


def _generate_pos_needs_review(idx: int, pos_date: date) -> dict:
    """Genera un reporte POS con confianza baja que requiere revisión humana."""
    return {
        "file_id": _uuid(),
        "storage_path": f"pos-tickets/{BUSINESS_ID}/{pos_date.isoformat()}/{_uuid()}.pdf",
        "extraction_status": "needs_human_review",
        "needs_human_review": True,
        "uploaded_at": datetime(pos_date.year, pos_date.month, pos_date.day, 22, 0, 0).isoformat() + "Z",
        "date": None,
        "totals": None,
        "payment_methods": None,
        "line_items": None,
        "ocr_confidence": {
            "totals": round(random.uniform(0.60, 0.89), 2),
            "payment_methods": round(random.uniform(0.55, 0.85), 2),
            "line_items": None,
        },
        "missing_fields": ["totals", "payment_methods"],
        "_anomaly": None,
    }


def generate_pos_reports(n: int = 15) -> list[dict]:
    """
    Genera N reportes POS con distribución de anomalías:
      - 8 normales
      - 2 con discrepancia de caja
      - 1 con fuga de margen
      - 2 con techo operacional
      - 2 que requieren revisión humana
    """
    start = date(2024, 1, 1)
    end = date(2024, 3, 31)
    reports: list[dict] = []

    # 8 reportes normales
    for i in range(8):
        pos_date = _random_date(start, end)
        reports.append(_generate_pos_normal(i + 1, pos_date))

    # 2 con discrepancia de caja
    for i in range(2):
        pos_date = _random_date(start, end)
        reports.append(_generate_pos_cash_discrepancy(i + 50, pos_date))

    # 1 con fuga de margen
    reports.append(_generate_pos_margin_leak(60, _random_date(start, end)))

    # 2 con techo operacional
    for i in range(2):
        pos_date = _random_date(start, end)
        reports.append(_generate_pos_operational_ceiling(i + 70, pos_date))

    # 2 que requieren revisión humana
    for i in range(2):
        pos_date = _random_date(start, end)
        reports.append(_generate_pos_needs_review(i + 80, pos_date))

    return reports[:n]


# ---------------------------------------------------------------------------
# Generador de cash_counts complementarios (para conciliación S3)
# ---------------------------------------------------------------------------

def generate_cash_counts(pos_reports: list[dict]) -> list[dict]:
    """
    Genera registros de cash_counts que complementan los POS reports
    para probar calc_cash_reconciliation de S3.
    Incluye discrepancias intencionales en algunos registros.
    """
    counts: list[dict] = []
    for pos in pos_reports:
        if pos["date"] is None or pos["totals"] is None:
            continue

        cash_sales = Decimal(str(pos["totals"]["cash"]))
        initial_float = Decimal("1500.00")
        cash_payouts = Decimal(str(random.randint(0, 300)))

        expected_cash = initial_float + cash_sales - cash_payouts

        # Introducir varianza en algunos registros
        if pos.get("_anomaly") and pos["_anomaly"]["type"] == "source_discrepancy":
            # Discrepancia intencional: faltante de caja
            variance = Decimal(str(random.randint(-500, -200)))
            actual_counted = expected_cash + variance
        else:
            # Varianza normal ±50 MXN
            variance = Decimal(str(random.uniform(-50, 50))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            actual_counted = expected_cash + variance

        counts.append({
            "id": _uuid(),
            "business_id": BUSINESS_ID,
            "date": pos["date"],
            "initial_float": _dec(initial_float),
            "actual_counted": _dec(actual_counted),
            "cash_payouts": _dec(cash_payouts),
            "recorded_by": _uuid(),
            "expected_cash": _dec(expected_cash),
            "variance": _dec(variance),
        })

    return counts


# ---------------------------------------------------------------------------
# Generador de daily_context (para observed_causality de S4)
# ---------------------------------------------------------------------------

def generate_daily_contexts(pos_reports: list[dict]) -> list[dict]:
    """Genera contextos diarios para los días con anomalías."""
    contexts: list[dict] = []
    clima_opts = ["lluvia", "calor", "frio", None]
    equipo_opts = ["falla_maquina", "mantenimiento", None]
    evento_opts = ["festivo", "obra_vial", "promocion", None]
    personal_opts = ["falta_staff", "capacitacion", None]

    for pos in pos_reports:
        if pos["date"] is None:
            continue
        if pos.get("_anomaly") is not None:
            # Días con anomalía siempre tienen contexto
            contexts.append({
                "id": _uuid(),
                "business_id": BUSINESS_ID,
                "date": pos["date"],
                "tags": {
                    "clima": random.choice(clima_opts),
                    "equipo": random.choice(equipo_opts[:2]),  # más probable falla
                    "evento": random.choice(evento_opts),
                    "personal": random.choice(personal_opts),
                    "otros": "Día con anomalía detectada en dataset de prueba",
                },
            })
        elif random.random() < 0.3:
            # 30% de días normales también tienen contexto
            contexts.append({
                "id": _uuid(),
                "business_id": BUSINESS_ID,
                "date": pos["date"],
                "tags": {
                    "clima": random.choice(clima_opts),
                    "equipo": None,
                    "evento": random.choice(evento_opts),
                    "personal": None,
                    "otros": None,
                },
            })

    return contexts


# ---------------------------------------------------------------------------
# Generador de PDFs con fpdf2 (opcional)
# ---------------------------------------------------------------------------

def generate_factura_pdfs(facturas: list[dict], output_dir: str, count: int = 5) -> list[str]:
    """
    Genera PDFs de facturas para probar factura_parser.py.
    Requiere fpdf2 (pip install fpdf2).

    Retorna lista de paths generados.
    """
    try:
        from fpdf import FPDF
        from fpdf.enums import XPos, YPos
    except ImportError:
        print("⚠️  fpdf2 no instalado. Saltando generación de PDFs.")
        print("   Instalar con: pip install fpdf2")
        return []

    pdf_dir = os.path.join(output_dir, "pdfs")
    os.makedirs(pdf_dir, exist_ok=True)
    generated: list[str] = []

    def _cell(p: "FPDF", w: int, h: int, txt: str, **kw) -> None:
        """Wrapper que usa la API moderna de fpdf2 y sanitiza caracteres."""
        txt = txt.replace("\u2014", "-").replace("\u2013", "-")
        p.cell(w, h, txt, new_x=XPos.LMARGIN, new_y=YPos.NEXT, **kw)

    # Tomar las primeras N facturas con extraction_status=success
    valid_facturas = [f for f in facturas if f["extraction_status"] == "success"][:count]

    for i, factura in enumerate(valid_facturas):
        fields = factura["extracted_fields"]
        taxes = factura.get("niif_tax_breakdown", {})
        meta = factura.get("raw_metadata", {})

        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Header
        pdf.set_font("Helvetica", "B", 16)
        _cell(pdf, 0, 10, "FACTURA", align="C")
        pdf.ln(5)

        # Datos del emisor
        pdf.set_font("Helvetica", "B", 11)
        _cell(pdf, 0, 7, "Emisor / Proveedor:")
        pdf.set_font("Helvetica", "", 10)
        _cell(pdf, 0, 6, f"  Razon Social: {fields['supplier_name']}")
        if meta.get("rfc_emisor"):
            _cell(pdf, 0, 6, f"  RFC: {meta['rfc_emisor']}")
        pdf.ln(3)

        # Datos de la factura
        pdf.set_font("Helvetica", "B", 11)
        _cell(pdf, 0, 7, "Datos de la Factura:")
        pdf.set_font("Helvetica", "", 10)
        _cell(pdf, 0, 6, f"  Folio: {fields['document_reference']}")
        _cell(pdf, 0, 6, f"  Fecha: {fields['transaction_date']}")
        pdf.ln(3)

        # Concepto
        pdf.set_font("Helvetica", "B", 11)
        _cell(pdf, 0, 7, "Concepto:")
        pdf.set_font("Helvetica", "", 10)
        _cell(pdf, 0, 6, f"  Descripcion: {fields['concept']}")
        pdf.ln(3)

        # Desglose de importes
        pdf.set_font("Helvetica", "B", 11)
        _cell(pdf, 0, 7, "Desglose de Importes (NIIF):")
        pdf.set_font("Helvetica", "", 10)
        if taxes:
            _cell(pdf, 0, 6, f"  Subtotal:          ${taxes.get('subtotal', 0):>12,.2f} MXN")
            _cell(pdf, 0, 6, f"  IVA (16%):         ${taxes.get('iva_trasladado', 0):>12,.2f} MXN")
            if taxes.get("retencion_isr", 0) > 0:
                _cell(pdf, 0, 6, f"  Ret. ISR (10%):   -${taxes['retencion_isr']:>12,.2f} MXN")
                _cell(pdf, 0, 6, f"  Ret. IVA (10.67%): -${taxes['retencion_iva']:>12,.2f} MXN")
            _cell(pdf, 0, 6, f"  Importe Total:     ${taxes.get('total', 0):>12,.2f} MXN")
        else:
            _cell(pdf, 0, 6, f"  Importe Total: ${fields['amount']:>12,.2f} MXN")
        pdf.ln(5)

        # Anomalia (si existe) - metadata para debugging
        anomaly = factura.get("_anomaly")
        if anomaly:
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(180, 0, 0)
            _cell(pdf, 0, 6, f"[ANOMALIA TEST: {anomaly['type']} - {anomaly['description']}]")
            pdf.set_text_color(0, 0, 0)

        # Footer
        pdf.ln(10)
        pdf.set_font("Helvetica", "I", 8)
        _cell(pdf, 0, 5, "Documento generado para pruebas MEPIA - No tiene validez fiscal", align="C")

        filename = f"factura_{i+1:02d}_{fields['document_reference'].replace('-', '_')}.pdf"
        filepath = os.path.join(pdf_dir, filename)
        pdf.output(filepath)
        generated.append(filepath)
        print(f"  ✅ PDF generado: {filepath}")

    return generated


# ---------------------------------------------------------------------------
# Generador de XMLs CFDI (para probar factura_parser.py con XML)
# ---------------------------------------------------------------------------

def generate_factura_xmls(facturas: list[dict], output_dir: str, count: int = 5) -> list[str]:
    """
    Genera XMLs CFDI 4.0 simulados para probar extract_factura_xml().
    """
    xml_dir = os.path.join(output_dir, "xmls")
    os.makedirs(xml_dir, exist_ok=True)
    generated: list[str] = []

    valid = [f for f in facturas if f["extraction_status"] == "success"][:count]

    for i, factura in enumerate(valid):
        fields = factura["extracted_fields"]
        taxes = factura.get("niif_tax_breakdown", {})
        meta = factura.get("raw_metadata", {})

        subtotal = taxes.get("subtotal", fields["amount"])
        iva = taxes.get("iva_trasladado", fields["tax_amount"])
        total = taxes.get("total", fields["amount"])

        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante
    xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
    Version="4.0"
    Fecha="{fields['transaction_date']}T12:00:00"
    Folio="{fields['document_reference']}"
    SubTotal="{subtotal}"
    Total="{total}"
    Moneda="MXN"
    TipoDeComprobante="I">
  <cfdi:Emisor
      Nombre="{fields['supplier_name']}"
      Rfc="{meta.get('rfc_emisor', 'XAXX010101000')}"
      RegimenFiscal="601"/>
  <cfdi:Receptor
      Nombre="MEPIA Test Business"
      Rfc="XEXX010101000"
      UsoCFDI="G03"/>
  <cfdi:Conceptos>
    <cfdi:Concepto
        Descripcion="{fields['concept']}"
        Cantidad="1"
        ValorUnitario="{subtotal}"
        Importe="{subtotal}"/>
  </cfdi:Conceptos>
  <cfdi:Impuestos TotalImpuestosTrasladados="{iva}">
    <cfdi:Traslados>
      <cfdi:Traslado
          Impuesto="002"
          TipoFactor="Tasa"
          TasaOCuota="0.160000"
          Importe="{iva}"/>
    </cfdi:Traslados>
  </cfdi:Impuestos>
</cfdi:Comprobante>"""

        filename = f"cfdi_{i+1:02d}_{fields['document_reference'].replace('-', '_')}.xml"
        filepath = os.path.join(xml_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(xml_content)
        generated.append(filepath)
        print(f"  ✅ XML generado: {filepath}")

    return generated


# ---------------------------------------------------------------------------
# Resumen del dataset
# ---------------------------------------------------------------------------

def print_summary(facturas: list[dict], pos_reports: list[dict],
                  cash_counts: list[dict], contexts: list[dict]) -> None:
    """Imprime resumen del dataset generado."""
    print("\n" + "=" * 60)
    print("📊 RESUMEN DEL DATASET DE PRUEBA MEPIA")
    print("=" * 60)
    print(f"  Business ID: {BUSINESS_ID}")
    print(f"  Período: 2024-01-01 a 2024-03-31")
    print()

    # Facturas
    anomaly_types_f = [f["_anomaly"]["type"] for f in facturas if f.get("_anomaly")]
    review_f = sum(1 for f in facturas if f["needs_human_review"])
    print(f"  📄 Facturas de proveedor: {len(facturas)}")
    print(f"     - Exitosas: {len(facturas) - review_f}")
    print(f"     - Requieren revisión: {review_f}")
    print(f"     - Anomalías: {dict((t, anomaly_types_f.count(t)) for t in set(anomaly_types_f))}")

    # POS
    anomaly_types_p = [p["_anomaly"]["type"] for p in pos_reports if p.get("_anomaly")]
    review_p = sum(1 for p in pos_reports if p["needs_human_review"])
    print(f"\n  🧾 Reportes POS: {len(pos_reports)}")
    print(f"     - Exitosos: {len(pos_reports) - review_p}")
    print(f"     - Requieren revisión: {review_p}")
    print(f"     - Anomalías: {dict((t, anomaly_types_p.count(t)) for t in set(anomaly_types_p))}")

    # Complementarios
    print(f"\n  💰 Cash counts: {len(cash_counts)}")
    discrepancies = sum(1 for c in cash_counts if abs(c["variance"]) > 100)
    print(f"     - Con discrepancia > $100: {discrepancies}")

    print(f"\n  📅 Contextos diarios: {len(contexts)}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Genera dataset de prueba para MEPIA")
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directorio de salida (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="Omitir generación de PDFs (no requiere fpdf2)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=SEED,
        help=f"Semilla para reproducibilidad (default: {SEED})",
    )
    args = parser.parse_args()

    random.seed(args.seed)
    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    print("🚀 Generando dataset de prueba MEPIA...")
    print(f"   Directorio: {output_dir}")
    print()

    # 1. Generar facturas
    print("📄 Generando 15 facturas de proveedor...")
    facturas = generate_facturas(15)
    facturas_path = os.path.join(output_dir, "facturas.json")
    with open(facturas_path, "w", encoding="utf-8") as f:
        json.dump(facturas, f, indent=2, ensure_ascii=False, default=str)
    print(f"   ✅ {facturas_path}")

    # 2. Generar reportes POS
    print("\n🧾 Generando 15 reportes POS...")
    pos_reports = generate_pos_reports(15)
    pos_path = os.path.join(output_dir, "pos_reports.json")
    with open(pos_path, "w", encoding="utf-8") as f:
        json.dump(pos_reports, f, indent=2, ensure_ascii=False, default=str)
    print(f"   ✅ {pos_path}")

    # 3. Generar cash counts complementarios
    print("\n💰 Generando cash counts...")
    cash_counts = generate_cash_counts(pos_reports)
    cash_path = os.path.join(output_dir, "cash_counts.json")
    with open(cash_path, "w", encoding="utf-8") as f:
        json.dump(cash_counts, f, indent=2, ensure_ascii=False, default=str)
    print(f"   ✅ {cash_path}")

    # 4. Generar contextos diarios
    print("\n📅 Generando contextos diarios...")
    contexts = generate_daily_contexts(pos_reports)
    ctx_path = os.path.join(output_dir, "daily_contexts.json")
    with open(ctx_path, "w", encoding="utf-8") as f:
        json.dump(contexts, f, indent=2, ensure_ascii=False, default=str)
    print(f"   ✅ {ctx_path}")

    # 5. Generar XMLs CFDI
    print("\n📝 Generando XMLs CFDI para factura_parser.py...")
    xml_paths = generate_factura_xmls(facturas, output_dir, count=5)

    # 6. Generar PDFs (opcional)
    if not args.no_pdf:
        print("\n📑 Generando PDFs de facturas para factura_parser.py...")
        pdf_paths = generate_factura_pdfs(facturas, output_dir, count=5)
    else:
        pdf_paths = []
        print("\n⏭️  Generación de PDFs omitida (--no-pdf)")

    # 7. Generar índice del dataset
    index = {
        "business_id": BUSINESS_ID,
        "seed": args.seed,
        "generated_at": datetime.now().isoformat(),
        "period": {"start": "2024-01-01", "end": "2024-03-31"},
        "files": {
            "facturas": "facturas.json",
            "pos_reports": "pos_reports.json",
            "cash_counts": "cash_counts.json",
            "daily_contexts": "daily_contexts.json",
            "xmls": [os.path.basename(p) for p in xml_paths],
            "pdfs": [os.path.basename(p) for p in pdf_paths],
        },
        "anomaly_summary": {
            "facturas": {
                "source_discrepancy": sum(1 for f in facturas if f.get("_anomaly") and f["_anomaly"]["type"] == "source_discrepancy"),
                "cost_spike": sum(1 for f in facturas if f.get("_anomaly") and f["_anomaly"]["type"] == "cost_spike"),
            },
            "pos": {
                "source_discrepancy": sum(1 for p in pos_reports if p.get("_anomaly") and p["_anomaly"]["type"] == "source_discrepancy"),
                "margin_leak": sum(1 for p in pos_reports if p.get("_anomaly") and p["_anomaly"]["type"] == "margin_leak"),
                "operational_ceiling": sum(1 for p in pos_reports if p.get("_anomaly") and p["_anomaly"]["type"] == "operational_ceiling"),
            },
        },
    }
    index_path = os.path.join(output_dir, "dataset_index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False, default=str)

    # Resumen
    print_summary(facturas, pos_reports, cash_counts, contexts)


if __name__ == "__main__":
    main()
