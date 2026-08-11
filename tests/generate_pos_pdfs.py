#!/usr/bin/env python3
"""
tests/generate_pos_pdfs.py — Genera PDFs de tickets POS para probar MEPIA

Genera 5 PDFs que simulan reportes diarios de punto de venta.
Los PDFs usan las etiquetas exactas que pos_parser.py busca con regex:
  - "Total" / "Venta Total"
  - "Efectivo" / "Cash"
  - "Tarjeta" / "Card"
  - Fechas en formato DD/MM/YYYY o YYYY-MM-DD

Incluye:
  - 3 tickets normales (parser extrae todo correctamente)
  - 1 ticket con discrepancia de caja (total != sum de items)
  - 1 ticket con datos parciales (needs_human_review)

Uso:
    python tests/generate_pos_pdfs.py
"""
import os
import random
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

random.seed(42)

OUTPUT_DIR = "tests/fixtures/pos_pdfs"

# Menu items del restaurante
MENU = [
    ("Cafe Americano", Decimal("45.00")),
    ("Cafe Latte", Decimal("65.00")),
    ("Cappuccino", Decimal("60.00")),
    ("Espresso Doble", Decimal("50.00")),
    ("Te Chai Latte", Decimal("55.00")),
    ("Croissant", Decimal("40.00")),
    ("Sandwich Club", Decimal("95.00")),
    ("Ensalada Cesar", Decimal("85.00")),
    ("Jugo Natural", Decimal("50.00")),
    ("Agua Mineral", Decimal("25.00")),
    ("Pastel del Dia", Decimal("75.00")),
    ("Molletes", Decimal("70.00")),
]


def _dec(val) -> str:
    return str(Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def generate_normal_ticket(ticket_date: date, ticket_num: int) -> dict:
    """Genera datos de un ticket POS normal."""
    num_items = random.randint(6, 10)
    selected = random.sample(MENU, num_items)
    items = []
    total = Decimal("0.00")
    for name, price in selected:
        qty = random.randint(8, 55)
        items.append((name, qty, price))
        total += price * qty

    cash_pct = Decimal(str(random.uniform(0.40, 0.65)))
    cash = (total * cash_pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    card = total - cash

    return {
        "date": ticket_date,
        "num": ticket_num,
        "items": items,
        "total": total,
        "cash": cash,
        "card": card,
        "anomaly": None,
    }


def generate_discrepancy_ticket(ticket_date: date, ticket_num: int) -> dict:
    """Ticket donde el total no coincide con la suma de items."""
    data = generate_normal_ticket(ticket_date, ticket_num)
    real_total = data["total"]
    # Inflar el total reportado
    inflated = real_total + Decimal(str(random.randint(250, 450)))
    cash_portion = (inflated * Decimal("0.55")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    card_portion = inflated - cash_portion
    data["total"] = inflated
    data["cash"] = cash_portion
    data["card"] = card_portion
    data["anomaly"] = f"Discrepancia: total reportado {_dec(inflated)} vs suma items {_dec(real_total)}"
    return data


def generate_partial_ticket(ticket_date: date, ticket_num: int) -> dict:
    """Ticket con datos parciales — sin desglose de metodos de pago."""
    data = generate_normal_ticket(ticket_date, ticket_num)
    # No incluir desglose de efectivo/tarjeta → parser no encuentra → needs_human_review
    data["cash"] = None
    data["card"] = None
    data["anomaly"] = "Sin desglose de metodos de pago"
    return data


def render_ticket_pdf(data: dict, filepath: str) -> None:
    """Renderiza un ticket POS como PDF usando fpdf2."""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    def cell(w, h, txt, **kw):
        txt = txt.replace("\u2014", "-").replace("\u2013", "-")
        pdf.cell(w, h, txt, new_x=XPos.LMARGIN, new_y=YPos.NEXT, **kw)

    ticket_date = data["date"]
    items = data["items"]
    total = data["total"]
    cash = data["cash"]
    card = data["card"]

    # === Header ===
    pdf.set_font("Courier", "B", 14)
    cell(0, 8, "REPORTE DIARIO DE VENTAS POS", align="C")
    pdf.set_font("Courier", "", 10)
    cell(0, 6, "Cafeteria MEPIA Test", align="C")
    cell(0, 6, f"Fecha: {ticket_date.strftime('%d/%m/%Y')}", align="C")
    cell(0, 6, f"Ticket #{data['num']:04d}", align="C")
    pdf.ln(3)

    # === Separador ===
    pdf.set_font("Courier", "", 8)
    cell(0, 4, "-" * 60)

    # === Tabla de items ===
    pdf.set_font("Courier", "B", 9)
    # Header de tabla
    pdf.cell(80, 6, "Producto", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(25, 6, "Cant", new_x=XPos.RIGHT, new_y=YPos.TOP, align="R")
    pdf.cell(30, 6, "P.Unit", new_x=XPos.RIGHT, new_y=YPos.TOP, align="R")
    pdf.cell(35, 6, "Importe", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")

    pdf.set_font("Courier", "", 8)
    cell(0, 3, "-" * 60)

    pdf.set_font("Courier", "", 9)
    for name, qty, price in items:
        subtotal = price * qty
        pdf.cell(80, 5, name[:25], new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(25, 5, str(qty), new_x=XPos.RIGHT, new_y=YPos.TOP, align="R")
        pdf.cell(30, 5, f"${_dec(price)}", new_x=XPos.RIGHT, new_y=YPos.TOP, align="R")
        pdf.cell(35, 5, f"${_dec(subtotal)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")

    # === Separador ===
    pdf.set_font("Courier", "", 8)
    cell(0, 3, "=" * 60)
    pdf.ln(2)

    # === Totales (etiquetas que pos_parser.py busca) ===
    pdf.set_font("Courier", "B", 11)
    cell(0, 7, f"Venta Total:    ${_dec(total)} MXN")

    pdf.ln(2)
    pdf.set_font("Courier", "B", 10)
    cell(0, 6, "DESGLOSE POR METODO DE PAGO:")
    pdf.set_font("Courier", "", 10)

    if cash is not None:
        cell(0, 6, f"  Efectivo:     ${_dec(cash)} MXN")
    if card is not None:
        cell(0, 6, f"  Tarjeta:      ${_dec(card)} MXN")

    if cash is None and card is None:
        cell(0, 6, "  (Desglose no disponible)")

    # === Transacciones ===
    pdf.ln(3)
    pdf.set_font("Courier", "", 9)
    num_tx = sum(qty for _, qty, _ in items)
    cell(0, 5, f"Total transacciones: {num_tx}")

    # === Anomalia (si existe) ===
    if data.get("anomaly"):
        pdf.ln(3)
        pdf.set_font("Courier", "I", 8)
        pdf.set_text_color(180, 0, 0)
        cell(0, 5, f"[TEST: {data['anomaly']}]")
        pdf.set_text_color(0, 0, 0)

    # === Footer ===
    pdf.ln(5)
    pdf.set_font("Courier", "", 8)
    cell(0, 4, "-" * 60)
    cell(0, 4, "Documento generado para pruebas MEPIA", align="C")
    cell(0, 4, f"Fecha impresion: {ticket_date.isoformat()}", align="C")

    pdf.output(filepath)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Generando PDFs de tickets POS para MEPIA...")
    print(f"Directorio: {OUTPUT_DIR}\n")

    tickets = []

    # 3 tickets normales
    for i in range(3):
        d = date(2024, 1, 15) + timedelta(days=i)
        tickets.append(generate_normal_ticket(d, i + 1))

    # 1 con discrepancia
    tickets.append(generate_discrepancy_ticket(date(2024, 1, 20), 4))

    # 1 parcial (needs_human_review)
    tickets.append(generate_partial_ticket(date(2024, 1, 22), 5))

    for i, ticket in enumerate(tickets):
        date_str = ticket["date"].strftime("%Y%m%d")
        anomaly_tag = ""
        if ticket.get("anomaly"):
            if "Discrepancia" in ticket["anomaly"]:
                anomaly_tag = "_discrepancia"
            else:
                anomaly_tag = "_parcial"

        filename = f"pos_ticket_{i+1:02d}_{date_str}{anomaly_tag}.pdf"
        filepath = os.path.join(OUTPUT_DIR, filename)

        render_ticket_pdf(ticket, filepath)
        status = "NORMAL" if not ticket.get("anomaly") else ticket["anomaly"][:50]
        print(f"  PDF: {filename}")
        print(f"       Fecha: {ticket['date']}  |  Total: ${_dec(ticket['total'])}")
        print(f"       Status: {status}")
        print()

    # Verificar que pos_parser puede leerlos
    print("Verificando con pos_parser.py...")
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from agents.pos_parser import extract_pos_data

    for i, ticket in enumerate(tickets):
        date_str = ticket["date"].strftime("%Y%m%d")
        anomaly_tag = ""
        if ticket.get("anomaly"):
            if "Discrepancia" in ticket["anomaly"]:
                anomaly_tag = "_discrepancia"
            else:
                anomaly_tag = "_parcial"
        filename = f"pos_ticket_{i+1:02d}_{date_str}{anomaly_tag}.pdf"
        filepath = os.path.join(OUTPUT_DIR, filename)

        with open(filepath, "rb") as f:
            results = extract_pos_data(f.read())

        r = results[0]
        review = "REVIEW" if r.needs_human_review else "OK"
        extracted_date = r.date.isoformat() if r.date else "null"
        extracted_total = str(r.totals.total) if r.totals else "null"
        extracted_cash = str(r.totals.cash) if r.totals else "null"
        extracted_card = str(r.totals.card) if r.totals else "null"
        print(f"  {filename}: [{review}]")
        print(f"    date={extracted_date}  total={extracted_total}  cash={extracted_cash}  card={extracted_card}")

    print(f"\nListo. {len(tickets)} PDFs en {OUTPUT_DIR}/")
    print("Sube los archivos al dropzone 'Ticket POS' en la UI de MEPIA.")


if __name__ == "__main__":
    main()
