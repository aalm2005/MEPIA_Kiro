"""
agents/factura_parser.py — N02 Factura de Proveedor Parser
Extrae datos de facturas XML (CFDI) y PDF.
Spec: .kiro/specs/mepia/n02_facturas_input.md
"""
import hashlib
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal, Optional

import pdfplumber
from lxml import etree
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Modelos Pydantic
# ---------------------------------------------------------------------------

class ExtractedFacturaFields(BaseModel):
    transaction_date: date
    amount: Decimal
    tax_amount: Decimal
    supplier_name: str
    concept: str
    document_reference: str


class FacturaExtractResult(BaseModel):
    extraction_status: Literal["success", "needs_human_review"]
    needs_human_review: bool
    ocr_confidence: Optional[float] = None   # None para XML (parseo determinístico)
    extracted_fields: Optional[ExtractedFacturaFields] = None
    missing_fields: Optional[list[str]] = None
    raw_metadata: dict = {}
    sha256: str


# ---------------------------------------------------------------------------
# Namespaces CFDI
# ---------------------------------------------------------------------------
_NS_CFDI4 = "http://www.sat.gob.mx/cfd/4"
_NS_CFDI3 = "http://www.sat.gob.mx/cfd/3"
_NAMESPACES = {
    "cfdi": _NS_CFDI4,
    "cfdi3": _NS_CFDI3,
}

# Umbral de confianza para PDF
_CONFIDENCE_ALL_FIELDS = 0.88
_CONFIDENCE_PARTIAL = 0.70
_THRESHOLD_PDF = 0.85


# ---------------------------------------------------------------------------
# Función auxiliar
# ---------------------------------------------------------------------------

def calculate_sha256(data: bytes) -> str:
    """Calcula el hash SHA-256 de los bytes dados."""
    return hashlib.sha256(data).hexdigest()


def _parse_decimal(raw: Optional[str]) -> Optional[Decimal]:
    """Convierte string de monto a Decimal."""
    if not raw:
        return None
    try:
        return Decimal(raw.strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _parse_date(raw: Optional[str]) -> Optional[date]:
    """Parsea fecha desde string ISO-8601 o formatos comunes."""
    if not raw:
        return None
    raw = raw.strip()
    # CFDI usa formato YYYY-MM-DDTHH:MM:SS o YYYY-MM-DD
    try:
        if "T" in raw:
            return date.fromisoformat(raw.split("T")[0])
        return date.fromisoformat(raw[:10])
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Extracción XML (CFDI)
# ---------------------------------------------------------------------------

def extract_factura_xml(xml_bytes: bytes) -> FacturaExtractResult:
    """
    Parsea un XML CFDI (3.3 o 4.0) y extrae los campos obligatorios.

    Args:
        xml_bytes: Contenido del XML en bytes.

    Returns:
        FacturaExtractResult con extraction_status="success" si todos los campos
        obligatorios están presentes.

    Raises:
        ValueError: Si el XML es inválido o no es un CFDI válido.
    """
    sha = calculate_sha256(xml_bytes)

    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"XML no es CFDI válido: {exc}") from exc

    # Detectar namespace activo (CFDI 4.0 o 3.3)
    tag = root.tag
    if _NS_CFDI4 in tag:
        ns = _NS_CFDI4
        ns_prefix = "cfdi"
    elif _NS_CFDI3 in tag:
        ns = _NS_CFDI3
        ns_prefix = "cfdi3"
    else:
        raise ValueError("XML no es CFDI válido: namespace no reconocido")

    ns_map = {ns_prefix: ns}

    # Extraer atributos del Comprobante (raíz)
    attribs = dict(root.attrib)

    # Fecha
    fecha_raw = attribs.get("Fecha")
    transaction_date = _parse_date(fecha_raw)

    # Total
    total_raw = attribs.get("Total")
    amount = _parse_decimal(total_raw)

    # Folio / referencia
    document_reference = (
        attribs.get("Folio")
        or attribs.get("NoCertificado")
        or ""
    )

    # IVA desde Impuestos
    tax_amount = Decimal("0.00")
    impuestos = root.find(f"{{{ns}}}Impuestos")
    if impuestos is not None:
        iva_raw = impuestos.attrib.get("TotalImpuestosTrasladados")
        parsed_iva = _parse_decimal(iva_raw)
        if parsed_iva is not None:
            tax_amount = parsed_iva

    # Emisor → supplier_name
    emisor = root.find(f"{{{ns}}}Emisor")
    supplier_name = ""
    if emisor is not None:
        supplier_name = emisor.attrib.get("Nombre", "")

    # Primer Concepto → concept
    conceptos = root.find(f"{{{ns}}}Conceptos")
    concept = ""
    all_concepts: list[str] = []
    if conceptos is not None:
        for concepto_el in conceptos.findall(f"{{{ns}}}Concepto"):
            desc = concepto_el.attrib.get("Descripcion", "")
            if desc:
                all_concepts.append(desc)
        concept = all_concepts[0] if all_concepts else ""

    # raw_metadata: todos los atributos del Comprobante + conceptos completos
    raw_metadata: dict = {k: v for k, v in attribs.items()}
    if len(all_concepts) > 1:
        raw_metadata["all_concepts"] = all_concepts

    # Validar campos obligatorios
    missing: list[str] = []
    if transaction_date is None:
        missing.append("transaction_date")
    if amount is None:
        missing.append("amount")
    if not supplier_name:
        missing.append("supplier_name")
    if not concept:
        missing.append("concept")
    if not document_reference:
        missing.append("document_reference")

    if missing:
        return FacturaExtractResult(
            extraction_status="needs_human_review",
            needs_human_review=True,
            ocr_confidence=None,
            extracted_fields=None,
            missing_fields=missing,
            raw_metadata=raw_metadata,
            sha256=sha,
        )

    return FacturaExtractResult(
        extraction_status="success",
        needs_human_review=False,
        ocr_confidence=None,  # XML determinístico — sin OCR
        extracted_fields=ExtractedFacturaFields(
            transaction_date=transaction_date,
            amount=amount,
            tax_amount=tax_amount,
            supplier_name=supplier_name,
            concept=concept,
            document_reference=document_reference,
        ),
        missing_fields=None,
        raw_metadata=raw_metadata,
        sha256=sha,
    )


# ---------------------------------------------------------------------------
# Extracción PDF (OCR con pdfplumber)
# ---------------------------------------------------------------------------

# Patrones regex para facturas PDF
_PDF_DATE_PATTERNS = [
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
    re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b"),
    re.compile(r"\b(\d{2})-(\d{2})-(\d{4})\b"),
]
_PDF_TOTAL_PATTERN = re.compile(
    r"(?:total|importe\s*total|monto\s*total)[^\d]*\$?\s*(\d[\d,]*\.?\d*)",
    re.IGNORECASE,
)
_PDF_SUPPLIER_PATTERN = re.compile(
    r"(?:proveedor|emisor|raz[oó]n\s*social|empresa)[:\s]+([A-ZÁÉÍÓÚÑ][^\n]{3,80})",
    re.IGNORECASE,
)
_PDF_CONCEPT_PATTERN = re.compile(
    r"(?:concepto|descripci[oó]n|servicio|producto)[:\s]+([^\n]{3,200})",
    re.IGNORECASE,
)
_PDF_FOLIO_PATTERN = re.compile(
    r"(?:folio|factura|no\.?\s*factura|n[uú]mero)[:\s#]*([A-Z0-9\-]{3,50})",
    re.IGNORECASE,
)


def _extract_date_from_pdf_text(text: str) -> Optional[date]:
    """Extrae la primera fecha válida del texto del PDF."""
    for pattern in _PDF_DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            groups = match.groups()
            try:
                if len(groups[0]) == 4:
                    return date(int(groups[0]), int(groups[1]), int(groups[2]))
                else:
                    return date(int(groups[2]), int(groups[1]), int(groups[0]))
            except ValueError:
                continue
    return None


def extract_factura_pdf(pdf_bytes: bytes) -> FacturaExtractResult:
    """
    Extrae datos de una factura en formato PDF usando pdfplumber.

    Args:
        pdf_bytes: Contenido del PDF en bytes.

    Returns:
        FacturaExtractResult con confidence simulada.
        Si confidence < 0.85 → needs_human_review=True.
    """
    sha = calculate_sha256(pdf_bytes)

    try:
        full_text = ""
        with pdfplumber.open(__import__("io").BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                full_text += page_text + "\n"
    except Exception:
        return FacturaExtractResult(
            extraction_status="needs_human_review",
            needs_human_review=True,
            ocr_confidence=_CONFIDENCE_PARTIAL,
            extracted_fields=None,
            missing_fields=["transaction_date", "amount", "supplier_name", "concept", "document_reference"],
            raw_metadata={},
            sha256=sha,
        )

    # Extraer campos con regex
    transaction_date = _extract_date_from_pdf_text(full_text)

    total_match = _PDF_TOTAL_PATTERN.search(full_text)
    amount = _parse_decimal(total_match.group(1)) if total_match else None

    supplier_match = _PDF_SUPPLIER_PATTERN.search(full_text)
    supplier_name = supplier_match.group(1).strip() if supplier_match else None

    concept_match = _PDF_CONCEPT_PATTERN.search(full_text)
    concept = concept_match.group(1).strip() if concept_match else None

    folio_match = _PDF_FOLIO_PATTERN.search(full_text)
    document_reference = folio_match.group(1).strip() if folio_match else None

    # Determinar campos faltantes
    missing: list[str] = []
    if transaction_date is None:
        missing.append("transaction_date")
    if amount is None:
        missing.append("amount")
    if not supplier_name:
        missing.append("supplier_name")
    if not concept:
        missing.append("concept")
    if not document_reference:
        missing.append("document_reference")

    # Calcular confianza simulada
    confidence = _CONFIDENCE_ALL_FIELDS if not missing else _CONFIDENCE_PARTIAL
    needs_review = confidence < _THRESHOLD_PDF or bool(missing)

    if needs_review:
        return FacturaExtractResult(
            extraction_status="needs_human_review",
            needs_human_review=True,
            ocr_confidence=confidence,
            extracted_fields=None,
            missing_fields=missing if missing else None,
            raw_metadata={"raw_text_length": len(full_text)},
            sha256=sha,
        )

    return FacturaExtractResult(
        extraction_status="success",
        needs_human_review=False,
        ocr_confidence=confidence,
        extracted_fields=ExtractedFacturaFields(
            transaction_date=transaction_date,
            amount=amount,
            tax_amount=Decimal("0.00"),  # PDF no siempre tiene IVA desglosado
            supplier_name=supplier_name,
            concept=concept,
            document_reference=document_reference,
        ),
        missing_fields=None,
        raw_metadata={"raw_text_length": len(full_text)},
        sha256=sha,
    )
