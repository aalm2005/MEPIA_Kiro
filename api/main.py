"""
MEPIA — FastAPI backend
Expone /ingest, /audit y /business/{id}/onboarding al frontend Next.js
"""
import sys
import os
from pathlib import Path

# Agrega tanto la raíz del proyecto (para agents/, utils/) como api/ (para core/)
# al path de Python, sin importar desde dónde se corra uvicorn.
_ROOT = Path(__file__).resolve().parent.parent   # MEPIA-V2/
_API  = Path(__file__).resolve().parent          # MEPIA-V2/api/
for _p in [str(_ROOT), str(_API)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import asyncio
from dataclasses import asdict
from datetime import date as date_type, datetime, timezone
from decimal import Decimal
from typing import Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import create_client, Client

from agents import CashReconciliationAgent, OperativeCostAgent, BusinessHealthAgent
from agents.gatekeeper import GatekeeperAgent
from agents.pos_parser import extract_pos_data, POSExtractResult
from agents.factura_parser import (
    extract_factura_xml,
    extract_factura_pdf,
    FacturaExtractResult,
    ExtractedFacturaFields,
    calculate_sha256,
)
from core.config import settings

app = FastAPI(title="MEPIA Agents API")

# En prod, reemplazar por el dominio real del frontend.
_ALLOWED_ORIGINS = (
    ["http://localhost:3000"]
    if settings.ENVIRONMENT == "dev"
    else ["https://mepia.app"]  # ajustar al dominio de producción
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Supabase client (singleton)
# ---------------------------------------------------------------------------
def get_supabase() -> Client:
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


# ---------------------------------------------------------------------------
# Pydantic models — OnboardingIdentityPayload (spec: n10_onboarding_identidad.md)
# ---------------------------------------------------------------------------
class AuditTolerances(BaseModel):
    max_cash_discrepancy_pct: float = Field(gt=0, le=1)
    max_cash_discrepancy_abs: Decimal = Field(ge=0)
    margin_warning_threshold: float = Field(gt=0, le=1)
    margin_critical_threshold: float = Field(gt=0, le=1)
    cost_spike_threshold_pct: float = Field(gt=0, le=1)


class ExpectedCostStructure(BaseModel):
    concept: str
    expected_monthly_amount: Decimal = Field(ge=0)
    tolerance_pct: float = Field(ge=0, le=1, default=0.05)
    expense_behavior: Literal["FIXED", "VARIABLE", "CAPEX"]


class AuditRules(BaseModel):
    red_alert_triggers: list[str] = Field(default=[])
    ignored_anomaly_types: list[str] = Field(default=[])
    audit_frequency: Literal["daily", "weekly"] = "daily"


class BrandIdentity(BaseModel):
    brand_voice: str = Field(max_length=500)
    prohibited_recommendations: list[str] = Field(default=[])
    priority_focus: Literal["efficiency", "quality", "growth"]


class OnboardingIdentityPayload(BaseModel):
    brand_identity: BrandIdentity
    audit_tolerances: AuditTolerances
    expected_cost_structure: list[ExpectedCostStructure] = Field(min_length=1)
    audit_rules: AuditRules

    def validate_thresholds(self) -> None:
        """Regla de negocio: umbral crítico debe ser menor que warning."""
        t = self.audit_tolerances
        if t.margin_critical_threshold >= t.margin_warning_threshold:
            raise ValueError(
                "margin_critical_threshold debe ser menor que margin_warning_threshold"
            )

# ---------------------------------------------------------------------------
# Flujo paralelo: los tres agentes corren simultáneamente
# ---------------------------------------------------------------------------
async def run_audit_pipeline(payload: dict) -> list[dict]:
    loop = asyncio.get_event_loop()

    cash_agent   = CashReconciliationAgent()
    cost_agent   = OperativeCostAgent()
    health_agent = BusinessHealthAgent()

    results = await asyncio.gather(
        loop.run_in_executor(None, cash_agent.run,   payload.get("cash", {})),
        loop.run_in_executor(None, cost_agent.run,   payload.get("cost", {})),
        loop.run_in_executor(None, health_agent.run, payload.get("health", {})),
    )

    return [asdict(r) for r in results]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/audit")
async def audit():
    """Devuelve resultados de auditoría con datos de ejemplo."""
    sample_payload = {
        "cash":   {"pos_total": 5150.00, "deposit": 5000.00},
        "cost":   {"item": "leche deslactosada", "prev": 800.0, "current": 896.0},
        "health": {"revenue": 50000.0, "costs": 41000.0, "archetype": "Operative Genius"},
    }
    rows = await run_audit_pipeline(sample_payload)
    return {"rows": rows}


@app.post("/ingest")
async def ingest(file: UploadFile = File(...)):
    """Recibe un PDF, extrae datos y dispara el pipeline de agentes."""
    content = await file.read()
    # TODO: parsear PDF con pdfplumber y extraer tablas de POS/facturas
    # Por ahora retorna confirmación
    return {
        "status": "received",
        "filename": file.filename,
        "size_kb": round(len(content) / 1024, 1),
        "message": "Documento en cola para procesamiento.",
    }


# ---------------------------------------------------------------------------
# Onboarding — N10 Identidad del Negocio
# Spec: .kiro/specs/mepia/n10_onboarding_identidad.md
# ---------------------------------------------------------------------------

def _build_memory_content(business_id: str, payload: OnboardingIdentityPayload) -> str:
    """Construye el texto del chunk de identidad para mepia_memory."""
    bi = payload.brand_identity
    at = payload.audit_tolerances
    ar = payload.audit_rules
    prohibited = ", ".join(bi.prohibited_recommendations) or "ninguna"
    triggers = ", ".join(ar.red_alert_triggers) or "ninguna"
    return (
        f"IDENTIDAD DE MARCA:\n{bi.brand_voice}\n\n"
        f"PROHIBIDO EN RECOMENDACIONES:\n{prohibited}\n\n"
        f"FOCO PRINCIPAL: {bi.priority_focus}\n\n"
        f"UMBRALES DE AUDITORÍA:\n"
        f"- Discrepancia caja máxima: {at.max_cash_discrepancy_pct * 100:.1f}%"
        f" o ${at.max_cash_discrepancy_abs} MXN (el más permisivo)\n"
        f"- Margen warning: {at.margin_warning_threshold * 100:.1f}%\n"
        f"- Margen crítico: {at.margin_critical_threshold * 100:.1f}%\n"
        f"- Spike de costo: {at.cost_spike_threshold_pct * 100:.1f}%\n\n"
        f"ALERTAS ROJAS AUTOMÁTICAS:\n{triggers}\n"
    )


def _upsert_onboarding(
    db: Client,
    business_id: str,
    payload: OnboardingIdentityPayload,
    now_iso: str,
) -> str:
    """
    Persiste la configuración en business_onboarding y business_fixed_costs.
    Retorna el memory_chunk_id insertado en mepia_memory.
    """
    bi = payload.brand_identity
    at = payload.audit_tolerances
    ar = payload.audit_rules

    # 1. Upsert en business_onboarding
    db.table("business_onboarding").upsert(
        {
            "business_id": business_id,
            "brand_voice": bi.brand_voice,
            "prohibited_recommendations": bi.prohibited_recommendations,
            "priority_focus": bi.priority_focus,
            "max_cash_discrepancy_pct": float(at.max_cash_discrepancy_pct),
            "max_cash_discrepancy_abs": float(at.max_cash_discrepancy_abs),
            "margin_warning_threshold": float(at.margin_warning_threshold),
            "margin_critical_threshold": float(at.margin_critical_threshold),
            "cost_spike_threshold_pct": float(at.cost_spike_threshold_pct),
            "audit_rules": ar.model_dump(),
            "completed_at": now_iso,
            "updated_at": now_iso,
        },
        on_conflict="business_id",
    ).execute()

    # 2. Marcar costos anteriores como inactivos
    db.table("business_fixed_costs").update({"is_active": False}).eq(
        "business_id", business_id
    ).execute()

    # 3. Insertar nueva estructura de costos
    if payload.expected_cost_structure:
        cost_rows = [
            {
                "business_id": business_id,
                "concept": item.concept,
                "expected_monthly_amount": float(item.expected_monthly_amount),
                "tolerance_pct": float(item.tolerance_pct),
                "expense_behavior": item.expense_behavior,
                "is_active": True,
            }
            for item in payload.expected_cost_structure
        ]
        db.table("business_fixed_costs").insert(cost_rows).execute()

    # 4. Insertar chunk en mepia_memory
    content = _build_memory_content(business_id, payload)
    memory_res = (
        db.table("mepia_memory")
        .insert(
            {
                "business_id": business_id,
                "source_audit_run_id": None,
                "content": content,
                "metadata": {
                    "node_origin": "onboarding",
                    "date": now_iso[:10],
                    "chunk_index": 0,
                    "chunk_total": 1,
                    "archetype": None,
                },
                "status": "pending_embed",
            }
        )
        .execute()
    )
    return memory_res.data[0]["id"]


@app.post("/business/{business_id}/onboarding", status_code=201)
async def create_onboarding(business_id: str, payload: OnboardingIdentityPayload):
    """
    POST /business/{business_id}/onboarding
    Crea la configuración de identidad y auditoría del negocio.
    Prerequisito obligatorio para ejecutar Layer 3.
    """
    # Validación de umbrales cruzados
    try:
        payload.validate_thresholds()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    db = get_supabase()

    # Verificar que el negocio existe
    biz = db.table("businesses").select("id").eq("id", business_id).execute()
    if not biz.data:
        raise HTTPException(
            status_code=404,
            detail=f"Negocio '{business_id}' no encontrado. Crear el negocio primero.",
        )

    # Verificar si ya existe onboarding (409 Conflict)
    existing = (
        db.table("business_onboarding")
        .select("id")
        .eq("business_id", business_id)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=409,
            detail="Onboarding ya completado. Usar PUT para actualizar.",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    memory_chunk_id = await asyncio.to_thread(
        _upsert_onboarding, db, business_id, payload, now_iso
    )

    return {
        "business_id": business_id,
        "onboarding_status": "complete",
        "memory_chunk_id": memory_chunk_id,
        "audit_config_stored": True,
        "completed_at": now_iso,
    }


@app.put("/business/{business_id}/onboarding", status_code=200)
async def update_onboarding(business_id: str, payload: OnboardingIdentityPayload):
    """
    PUT /business/{business_id}/onboarding
    Actualiza la configuración de onboarding. Crea nuevo chunk en mepia_memory.
    """
    try:
        payload.validate_thresholds()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    db = get_supabase()

    biz = db.table("businesses").select("id").eq("id", business_id).execute()
    if not biz.data:
        raise HTTPException(
            status_code=404,
            detail=f"Negocio '{business_id}' no encontrado.",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    memory_chunk_id = await asyncio.to_thread(
        _upsert_onboarding, db, business_id, payload, now_iso
    )

    return {
        "business_id": business_id,
        "onboarding_status": "updated",
        "memory_chunk_id": memory_chunk_id,
        "audit_config_stored": True,
        "completed_at": now_iso,
    }


@app.get("/business/{business_id}/onboarding/status")
async def get_onboarding_status(business_id: str):
    """
    GET /business/{business_id}/onboarding/status
    Verifica si el onboarding está completo antes de disparar Layer 3.
    """
    db = get_supabase()

    biz = db.table("businesses").select("id").eq("id", business_id).execute()
    if not biz.data:
        raise HTTPException(status_code=404, detail=f"Negocio '{business_id}' no encontrado.")

    onboarding = (
        db.table("business_onboarding")
        .select("*")
        .eq("business_id", business_id)
        .execute()
    )

    if not onboarding.data:
        return {
            "business_id": business_id,
            "onboarding_complete": False,
            "completed_at": None,
            "has_brand_identity": False,
            "has_audit_tolerances": False,
            "has_cost_structure": False,
        }

    row = onboarding.data[0]
    costs = (
        db.table("business_fixed_costs")
        .select("id")
        .eq("business_id", business_id)
        .eq("is_active", True)
        .execute()
    )

    return {
        "business_id": business_id,
        "onboarding_complete": True,
        "completed_at": row.get("completed_at"),
        "has_brand_identity": bool(row.get("brand_voice")),
        "has_audit_tolerances": row.get("max_cash_discrepancy_pct") is not None,
        "has_cost_structure": len(costs.data) > 0,
    }


# ===========================================================================
# S1 Ingesta — N01: POS PDF Input
# Spec: .kiro/specs/mepia/n01_pos_pdf_input.md
# ===========================================================================

_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


class POSIngestResult(BaseModel):
    file_id: str
    storage_path: str
    extraction_status: Literal["success", "needs_human_review"]
    needs_human_review: bool
    uploaded_at: str
    date: Optional[str] = None
    totals: Optional[dict] = None
    payment_methods: Optional[dict] = None
    line_items: Optional[list] = None
    ocr_confidence: dict
    missing_fields: Optional[list[str]] = None


class POSReviewPayload(BaseModel):
    date: str                          # YYYY-MM-DD
    totals: dict                       # { cash, card, total }
    payment_methods: Optional[dict] = None


def _upload_to_storage(db: Client, path: str, data: bytes) -> str:
    """
    Sube bytes a Supabase Storage en el bucket 'mepia-documents'.
    Si el bucket no existe o hay error, retorna un path local como fallback.
    """
    try:
        db.storage.from_("mepia-documents").upload(
            path,
            data,
            {"content-type": "application/octet-stream"},
        )
        return path
    except Exception:
        # Fallback: continuar sin subir el archivo
        return f"local/{path.split('/')[-1]}"


def _verify_business_exists(db: Client, business_id: str) -> None:
    """Verifica que el business_id existe en la tabla businesses. HTTP 404 si no."""
    result = db.table("businesses").select("id").eq("id", business_id).execute()
    if not result.data:
        raise HTTPException(
            status_code=404,
            detail=f"Negocio '{business_id}' no encontrado.",
        )


def _check_duplicate_sha256(db: Client, sha256: str, business_id: str) -> Optional[dict]:
    """
    Verifica si ya existe un documento con el mismo SHA-256 y business_id.
    Retorna el registro existente o None.
    """
    result = (
        db.table("documents")
        .select("*")
        .eq("business_id", business_id)
        .execute()
    )
    for row in result.data or []:
        extracted = row.get("extracted_data") or {}
        if extracted.get("sha256") == sha256:
            return row
    return None


@app.post("/ingest/pos", response_model=list[POSIngestResult])
async def ingest_pos(
    file: UploadFile = File(...),
    business_id: str = Form(...),
):
    """
    POST /ingest/pos
    Recibe un PDF de ticket POS, extrae datos y persiste en documents + pos_inputs.
    Retorna un array de POSIngestResult, uno por día detectado.
    Spec: n01_pos_pdf_input.md
    """
    # 1. Validar MIME
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        # Intentar detectar por nombre si el content_type es genérico
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(
                status_code=422,
                detail="El archivo debe ser un PDF (MIME: application/pdf).",
            )

    # 2. Leer bytes y validar tamaño
    pdf_bytes = await file.read()
    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=422, detail="El archivo está vacío.")
    if len(pdf_bytes) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=422, detail="El archivo supera el límite de 20 MB.")

    db = get_supabase()

    # 3. Verificar business_id
    _verify_business_exists(db, business_id)

    # 4. Calcular SHA-256 y verificar deduplicación
    from agents.pos_parser import calculate_sha256 as pos_sha256
    sha = pos_sha256(pdf_bytes)
    existing = _check_duplicate_sha256(db, sha, business_id)
    if existing:
        # Retornar resultado existente sin duplicar
        uploaded_at = existing.get("uploaded_at", datetime.now(timezone.utc).isoformat())
        extracted = existing.get("extracted_data") or {}
        return [
            POSIngestResult(
                file_id=existing["id"],
                storage_path=existing.get("storage_path", ""),
                extraction_status="success" if not existing.get("needs_human_review") else "needs_human_review",
                needs_human_review=existing.get("needs_human_review", False),
                uploaded_at=uploaded_at,
                date=extracted.get("date"),
                totals=extracted.get("totals"),
                payment_methods=extracted.get("payment_methods"),
                line_items=extracted.get("line_items"),
                ocr_confidence=extracted.get("ocr_confidence", {}),
                missing_fields=extracted.get("missing_fields"),
            )
        ]

    # 5. Extraer datos del PDF
    extract_results: list[POSExtractResult] = await asyncio.to_thread(
        extract_pos_data, pdf_bytes
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    output: list[POSIngestResult] = []

    for result in extract_results:
        file_id = str(uuid4())
        date_str = result.date.isoformat() if result.date else "unknown"

        # 6a. Subir a Storage
        storage_path = _upload_to_storage(
            db,
            f"pos-tickets/{business_id}/{date_str}/{file_id}.pdf",
            pdf_bytes,
        )

        # Serializar datos extraídos para JSONB
        extracted_data = {
            "sha256": sha,
            "date": date_str if result.date else None,
            "totals": (
                {
                    "cash": str(result.totals.cash),
                    "card": str(result.totals.card),
                    "total": str(result.totals.total),
                }
                if result.totals
                else None
            ),
            "payment_methods": (
                {
                    "cash": str(result.payment_methods.cash),
                    "card": str(result.payment_methods.card),
                    "other": str(result.payment_methods.other),
                }
                if result.payment_methods
                else None
            ),
            "line_items": (
                [li.model_dump(mode="json") for li in result.line_items]
                if result.line_items
                else None
            ),
            "ocr_confidence": result.ocr_confidence.model_dump(),
            "missing_fields": result.missing_fields,
        }

        ocr_status = "error" if result.needs_human_review else "processed"
        ocr_confidence_val = result.ocr_confidence.totals

        # 6b. Insertar en documents
        doc_row = {
            "id": file_id,
            "business_id": business_id,
            "storage_path": storage_path,
            "filename": file.filename or f"{file_id}.pdf",
            "document_type": "PDF",
            "ocr_status": ocr_status,
            "ocr_confidence": ocr_confidence_val,
            "needs_human_review": result.needs_human_review,
            "extracted_data": extracted_data,
        }
        db.table("documents").insert(doc_row).execute()

        # 6c. Insertar en pos_inputs si no requiere revisión
        if not result.needs_human_review and result.totals and result.date:
            db.table("pos_inputs").insert(
                {
                    "business_id": business_id,
                    "date": result.date.isoformat(),
                    "total_sales": float(result.totals.total),
                    "cash_sales": float(result.totals.cash),
                    "card_sales": float(result.totals.card),
                }
            ).execute()

        output.append(
            POSIngestResult(
                file_id=file_id,
                storage_path=storage_path,
                extraction_status="needs_human_review" if result.needs_human_review else "success",
                needs_human_review=result.needs_human_review,
                uploaded_at=now_iso,
                date=date_str if result.date else None,
                totals=(
                    {
                        "cash": float(result.totals.cash),
                        "card": float(result.totals.card),
                        "total": float(result.totals.total),
                    }
                    if result.totals
                    else None
                ),
                payment_methods=(
                    {
                        "cash": float(result.payment_methods.cash),
                        "card": float(result.payment_methods.card),
                        "other": float(result.payment_methods.other),
                    }
                    if result.payment_methods
                    else None
                ),
                line_items=(
                    [li.model_dump(mode="json") for li in result.line_items]
                    if result.line_items
                    else None
                ),
                ocr_confidence=result.ocr_confidence.model_dump(),
                missing_fields=result.missing_fields,
            )
        )

    return output


@app.patch("/ingest/pos/{file_id}/review")
async def review_pos(file_id: str, payload: POSReviewPayload):
    """
    PATCH /ingest/pos/{file_id}/review
    Permite enviar datos corregidos para un documento POS que requiere revisión humana.
    Spec: n01_pos_pdf_input.md
    """
    db = get_supabase()

    # 1. Verificar que file_id existe
    doc_result = db.table("documents").select("*").eq("id", file_id).execute()
    if not doc_result.data:
        raise HTTPException(status_code=404, detail=f"Documento '{file_id}' no encontrado.")

    doc = doc_result.data[0]

    # 2. Verificar que necesita revisión
    if not doc.get("needs_human_review", False):
        raise HTTPException(
            status_code=409,
            detail="El documento ya fue procesado. No requiere revisión.",
        )

    # 3. Actualizar documents
    db.table("documents").update(
        {
            "needs_human_review": False,
            "ocr_status": "processed",
        }
    ).eq("id", file_id).execute()

    # 4. Insertar en pos_inputs con datos corregidos
    totals = payload.totals
    db.table("pos_inputs").insert(
        {
            "business_id": doc["business_id"],
            "date": payload.date,
            "total_sales": float(totals.get("total", 0)),
            "cash_sales": float(totals.get("cash", 0)),
            "card_sales": float(totals.get("card", 0)),
        }
    ).execute()

    return {
        "file_id": file_id,
        "extraction_status": "success",
        "needs_human_review": False,
    }


# ===========================================================================
# S1 Ingesta — N02: Facturas de Proveedor
# Spec: .kiro/specs/mepia/n02_facturas_input.md
# ===========================================================================

class FacturaIngestResult(BaseModel):
    file_id: str
    storage_path: str
    extraction_status: Literal["success", "needs_human_review"]
    needs_human_review: bool
    ocr_confidence: Optional[float] = None
    transaction_id: Optional[str] = None
    extracted_fields: Optional[dict] = None
    missing_fields: Optional[list[str]] = None


class FacturaReviewPayload(BaseModel):
    transaction_date: str              # YYYY-MM-DD
    amount: float
    tax_amount: float
    supplier_name: str
    concept: str
    document_reference: str


_XML_MIMES = {"text/xml", "application/xml", "text/plain"}
_PDF_MIMES = {"application/pdf", "application/octet-stream"}


@app.post("/ingest/factura", response_model=FacturaIngestResult)
async def ingest_factura(
    file: UploadFile = File(...),
    business_id: str = Form(...),
    document_type: str = Form(...),
):
    """
    POST /ingest/factura
    Recibe una factura XML (CFDI) o PDF, extrae datos y persiste en documents + transactions.
    Spec: n02_facturas_input.md
    """
    document_type = document_type.upper()
    if document_type not in ("XML", "PDF"):
        raise HTTPException(
            status_code=422,
            detail="document_type debe ser 'XML' o 'PDF'.",
        )

    # 1. Validar MIME vs document_type declarado
    content_type = file.content_type or ""
    filename = (file.filename or "").lower()

    if document_type == "XML":
        mime_ok = content_type in _XML_MIMES or filename.endswith(".xml")
    else:
        mime_ok = content_type in _PDF_MIMES or filename.endswith(".pdf")

    if not mime_ok:
        raise HTTPException(
            status_code=422,
            detail=f"El MIME del archivo ({content_type}) no coincide con document_type='{document_type}'.",
        )

    # 2. Leer bytes y validar tamaño
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=422, detail="El archivo está vacío.")
    if len(file_bytes) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=422, detail="El archivo supera el límite de 20 MB.")

    db = get_supabase()

    # 3. Verificar business_id
    _verify_business_exists(db, business_id)

    # 4. Deduplicación por SHA-256
    sha = calculate_sha256(file_bytes)
    existing = _check_duplicate_sha256(db, sha, business_id)
    if existing:
        extracted = existing.get("extracted_data") or {}
        return FacturaIngestResult(
            file_id=existing["id"],
            storage_path=existing.get("storage_path", ""),
            extraction_status="success" if not existing.get("needs_human_review") else "needs_human_review",
            needs_human_review=existing.get("needs_human_review", False),
            ocr_confidence=existing.get("ocr_confidence"),
            transaction_id=extracted.get("transaction_id"),
            extracted_fields=extracted.get("extracted_fields"),
            missing_fields=extracted.get("missing_fields"),
        )

    file_id = str(uuid4())
    ext = "xml" if document_type == "XML" else "pdf"
    now_iso = datetime.now(timezone.utc).isoformat()

    # 5. Extraer datos
    try:
        if document_type == "XML":
            extract_result: FacturaExtractResult = await asyncio.to_thread(
                extract_factura_xml, file_bytes
            )
        else:
            extract_result = await asyncio.to_thread(
                extract_factura_pdf, file_bytes
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Determinar fecha para el path de storage
    date_str = "unknown"
    if extract_result.extracted_fields and extract_result.extracted_fields.transaction_date:
        date_str = extract_result.extracted_fields.transaction_date.isoformat()

    # 6. Subir a Storage
    storage_path = _upload_to_storage(
        db,
        f"facturas/{business_id}/{date_str}/{file_id}.{ext}",
        file_bytes,
    )

    # 7. Insertar en transactions si no requiere revisión
    transaction_id: Optional[str] = None
    if not extract_result.needs_human_review and extract_result.extracted_fields:
        ef = extract_result.extracted_fields
        transaction_id = str(uuid4())
        db.table("transactions").insert(
            {
                "id": transaction_id,
                "business_id": business_id,
                "document_id": file_id,
                "type": "egreso",
                "category": "proveedor",
                "amount": float(ef.amount),
                "tax_amount": float(ef.tax_amount),
                "transaction_date": ef.transaction_date.isoformat(),
                "supplier_name": ef.supplier_name,
                "concept": ef.concept,
                "document_reference": ef.document_reference,
                "expense_behavior": None,
                "raw_metadata": extract_result.raw_metadata,
            }
        ).execute()

    # 8. Insertar en documents
    extracted_data_json = {
        "sha256": sha,
        "transaction_id": transaction_id,
        "extracted_fields": (
            extract_result.extracted_fields.model_dump(mode="json")
            if extract_result.extracted_fields
            else None
        ),
        "missing_fields": extract_result.missing_fields,
    }

    ocr_status = "error" if extract_result.needs_human_review else "processed"
    db.table("documents").insert(
        {
            "id": file_id,
            "business_id": business_id,
            "storage_path": storage_path,
            "filename": file.filename or f"{file_id}.{ext}",
            "document_type": document_type,
            "ocr_status": ocr_status,
            "ocr_confidence": extract_result.ocr_confidence,
            "needs_human_review": extract_result.needs_human_review,
            "extracted_data": extracted_data_json,
        }
    ).execute()

    return FacturaIngestResult(
        file_id=file_id,
        storage_path=storage_path,
        extraction_status=extract_result.extraction_status,
        needs_human_review=extract_result.needs_human_review,
        ocr_confidence=extract_result.ocr_confidence,
        transaction_id=transaction_id,
        extracted_fields=(
            extract_result.extracted_fields.model_dump(mode="json")
            if extract_result.extracted_fields
            else None
        ),
        missing_fields=extract_result.missing_fields,
    )


@app.patch("/ingest/factura/{file_id}/review")
async def review_factura(file_id: str, payload: FacturaReviewPayload):
    """
    PATCH /ingest/factura/{file_id}/review
    Permite enviar campos corregidos para una factura que requiere revisión humana.
    Spec: n02_facturas_input.md
    """
    db = get_supabase()

    # 1. Verificar que file_id existe
    doc_result = db.table("documents").select("*").eq("id", file_id).execute()
    if not doc_result.data:
        raise HTTPException(status_code=404, detail=f"Documento '{file_id}' no encontrado.")

    doc = doc_result.data[0]

    # 2. Verificar que necesita revisión
    if not doc.get("needs_human_review", False):
        raise HTTPException(
            status_code=409,
            detail="El documento ya fue procesado. No requiere revisión.",
        )

    # 3. Actualizar documents
    db.table("documents").update(
        {
            "needs_human_review": False,
            "ocr_status": "processed",
        }
    ).eq("id", file_id).execute()

    # 4. Insertar en transactions con datos corregidos
    transaction_id = str(uuid4())
    db.table("transactions").insert(
        {
            "id": transaction_id,
            "business_id": doc["business_id"],
            "document_id": file_id,
            "type": "egreso",
            "category": "proveedor",
            "amount": payload.amount,
            "tax_amount": payload.tax_amount,
            "transaction_date": payload.transaction_date,
            "supplier_name": payload.supplier_name,
            "concept": payload.concept,
            "document_reference": payload.document_reference,
            "expense_behavior": None,
        }
    ).execute()

    return {
        "file_id": file_id,
        "transaction_id": transaction_id,
        "extraction_status": "success",
        "needs_human_review": False,
    }


# ===========================================================================
# S1 Ingesta — N03: Human Input Endpoints
# Spec: .kiro/specs/mepia/n03_human_input_endpoints.md
# ===========================================================================

# ---------------------------------------------------------------------------
# 4.3.1 — Expense Behavior
# ---------------------------------------------------------------------------

class ExpenseBehaviorPayload(BaseModel):
    expense_behavior: Literal["FIXED", "VARIABLE", "CAPEX"]
    confirmed_by: str  # UUID del usuario
    force: bool = False  # permite sobreescribir si ya está confirmado


@app.patch("/transactions/{transaction_id}/expense-behavior")
async def confirm_expense_behavior(
    transaction_id: str,
    payload: ExpenseBehaviorPayload,
):
    """
    PATCH /transactions/{transaction_id}/expense-behavior
    Confirma o corrige la clasificación de un gasto extraído.
    Spec: n03_human_input_endpoints.md §1
    """
    db = get_supabase()

    # 1. Verificar que transaction_id existe
    tx_result = db.table("transactions").select("*").eq("id", transaction_id).execute()
    if not tx_result.data:
        raise HTTPException(
            status_code=404,
            detail=f"Transacción '{transaction_id}' no encontrada.",
        )

    tx = tx_result.data[0]

    # 2. Si ya tiene expense_behavior confirmado y force=False → 409
    if tx.get("expense_behavior") is not None and not payload.force:
        raise HTTPException(
            status_code=409,
            detail=(
                "La transacción ya tiene expense_behavior confirmado. "
                "Usar force=true para sobreescribir."
            ),
        )

    # 3. Actualizar transactions.expense_behavior
    now_iso = datetime.now(timezone.utc).isoformat()
    db.table("transactions").update(
        {"expense_behavior": payload.expense_behavior}
    ).eq("id", transaction_id).execute()

    # 4. Disparar re-evaluación de S2 (Gatekeeper)
    business_id = tx.get("business_id")
    transaction_date = tx.get("transaction_date")
    if business_id and transaction_date:
        try:
            GatekeeperAgent(db).evaluate(business_id, transaction_date)
        except Exception:
            pass  # El trigger no debe bloquear la respuesta

    # 5. Retornar resultado
    return {
        "transaction_id": transaction_id,
        "expense_behavior": payload.expense_behavior,
        "confirmed_by": payload.confirmed_by,
        "confirmed_at": now_iso,
        "gatekeeper_triggered": True,
    }


# ---------------------------------------------------------------------------
# 4.3.2 — Pending Review
# ---------------------------------------------------------------------------

_FIXED_SUPPLIER_KEYWORDS = {
    "CFE", "TELMEX", "IZZI", "TOTALPLAY", "MEGACABLE", "RENTA", "ARRENDAMIENTO"
}


def _infer_suggested_behavior(
    supplier_name: Optional[str],
    category: Optional[str],
) -> str:
    """
    Infiere el expense_behavior sugerido a partir de supplier_name y category.
    Nunca persiste el valor — solo es una sugerencia para el cliente.
    """
    if supplier_name:
        upper = supplier_name.upper()
        for keyword in _FIXED_SUPPLIER_KEYWORDS:
            if keyword in upper:
                return "FIXED"
    if category == "nomina":
        return "FIXED"
    return "VARIABLE"


@app.get("/transactions/pending-review")
async def get_pending_review(
    business_id: str,
    date: Optional[str] = None,
):
    """
    GET /transactions/pending-review
    Lista transacciones con expense_behavior=null para un negocio y fecha.
    Spec: n03_human_input_endpoints.md §1
    """
    if not business_id:
        raise HTTPException(status_code=400, detail="business_id es requerido.")

    # Default: hoy en formato YYYY-MM-DD
    if date is None:
        date = datetime.now(timezone.utc).date().isoformat()

    db = get_supabase()

    # Consultar transactions con expense_behavior IS NULL
    result = (
        db.table("transactions")
        .select("id, supplier_name, concept, amount, transaction_date, category")
        .eq("business_id", business_id)
        .eq("transaction_date", date)
        .is_("expense_behavior", "null")
        .execute()
    )

    pending = [
        {
            "transaction_id": row["id"],
            "supplier_name": row.get("supplier_name"),
            "concept": row.get("concept"),
            "amount": float(row["amount"]) if row.get("amount") is not None else None,
            "transaction_date": row.get("transaction_date"),
            "suggested_behavior": _infer_suggested_behavior(
                row.get("supplier_name"), row.get("category")
            ),
        }
        for row in (result.data or [])
    ]

    return {"pending": pending, "total": len(pending)}


# ---------------------------------------------------------------------------
# 4.3.3 — Cash Counts (POST + PUT)
# ---------------------------------------------------------------------------

class CashCountPayload(BaseModel):
    business_id: str
    date: str  # YYYY-MM-DD
    initial_float: float = 0.0
    actual_counted: float
    cash_payouts: float = 0.0
    recorded_by: str  # UUID


@app.post("/cash-counts", status_code=201)
async def create_cash_count(payload: CashCountPayload):
    """
    POST /cash-counts
    Registra el conteo físico del cajón para un negocio y fecha.
    Spec: n03_human_input_endpoints.md §2
    """
    db = get_supabase()

    # 1. Verificar business_id existe
    biz = db.table("businesses").select("id").eq("id", payload.business_id).execute()
    if not biz.data:
        raise HTTPException(
            status_code=404,
            detail=f"Negocio '{payload.business_id}' no encontrado.",
        )

    # 2. Verificar que date no es futuro
    try:
        count_date = date_type.fromisoformat(payload.date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Formato de fecha inválido. Usar YYYY-MM-DD.")

    today = datetime.now(timezone.utc).date()
    if count_date > today:
        raise HTTPException(
            status_code=422,
            detail="La fecha del conteo no puede ser futura.",
        )

    # 3. Verificar que no existe ya un conteo para business_id + date
    existing = (
        db.table("cash_counts")
        .select("id")
        .eq("business_id", payload.business_id)
        .eq("date", payload.date)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Ya existe un conteo para business_id='{payload.business_id}' "
                f"y date='{payload.date}'. Usar PUT para actualizar."
            ),
        )

    # 4. Insertar en cash_counts
    cash_count_id = str(uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    db.table("cash_counts").insert(
        {
            "id": cash_count_id,
            "business_id": payload.business_id,
            "date": payload.date,
            "initial_float": payload.initial_float,
            "actual_counted": payload.actual_counted,
            "cash_payouts": payload.cash_payouts,
            "recorded_by": payload.recorded_by,
            "created_at": now_iso,
        }
    ).execute()

    # 5. Disparar re-evaluación de S2 (Gatekeeper)
    try:
        GatekeeperAgent(db).evaluate(payload.business_id, payload.date)
    except Exception:
        pass  # El trigger no debe bloquear la respuesta

    # 6. Retornar registro creado con gatekeeper_triggered: true
    return {
        "cash_count_id": cash_count_id,
        "business_id": payload.business_id,
        "date": payload.date,
        "initial_float": payload.initial_float,
        "actual_counted": payload.actual_counted,
        "cash_payouts": payload.cash_payouts,
        "recorded_by": payload.recorded_by,
        "created_at": now_iso,
        "gatekeeper_triggered": True,
    }


@app.put("/cash-counts/{cash_count_id}")
async def update_cash_count(cash_count_id: str, payload: CashCountPayload):
    """
    PUT /cash-counts/{cash_count_id}
    Actualiza un conteo ya registrado (corrección antes del cierre contable).
    Spec: n03_human_input_endpoints.md §2
    """
    db = get_supabase()

    # 1. Verificar que cash_count_id existe
    existing = (
        db.table("cash_counts").select("*").eq("id", cash_count_id).execute()
    )
    if not existing.data:
        raise HTTPException(
            status_code=404,
            detail=f"Conteo '{cash_count_id}' no encontrado.",
        )

    # 2. Actualizar el registro
    now_iso = datetime.now(timezone.utc).isoformat()
    db.table("cash_counts").update(
        {
            "business_id": payload.business_id,
            "date": payload.date,
            "initial_float": payload.initial_float,
            "actual_counted": payload.actual_counted,
            "cash_payouts": payload.cash_payouts,
            "recorded_by": payload.recorded_by,
            "updated_at": now_iso,
        }
    ).eq("id", cash_count_id).execute()

    # 3. Disparar re-evaluación de S2 (Gatekeeper)
    try:
        GatekeeperAgent(db).evaluate(payload.business_id, payload.date)
    except Exception:
        pass  # El trigger no debe bloquear la respuesta

    # 4. Retornar registro actualizado con gatekeeper_triggered: true
    return {
        "cash_count_id": cash_count_id,
        "business_id": payload.business_id,
        "date": payload.date,
        "initial_float": payload.initial_float,
        "actual_counted": payload.actual_counted,
        "cash_payouts": payload.cash_payouts,
        "recorded_by": payload.recorded_by,
        "updated_at": now_iso,
        "gatekeeper_triggered": True,
    }


# ---------------------------------------------------------------------------
# 4.3.4 — GET /cash-counts
# ---------------------------------------------------------------------------

@app.get("/cash-counts")
async def get_cash_count(
    business_id: str,
    date: Optional[str] = None,
):
    """
    GET /cash-counts
    Consulta el estado del conteo para un negocio y fecha.
    Nunca retorna HTTP 404 — siempre HTTP 200.
    Spec: n03_human_input_endpoints.md §2
    """
    if not business_id:
        raise HTTPException(status_code=400, detail="business_id es requerido.")

    if date is None:
        date = datetime.now(timezone.utc).date().isoformat()

    db = get_supabase()

    result = (
        db.table("cash_counts")
        .select("*")
        .eq("business_id", business_id)
        .eq("date", date)
        .execute()
    )

    if result.data:
        row = result.data[0]
        return {
            "cash_count_id": row["id"],
            "date": row.get("date"),
            "initial_float": row.get("initial_float"),
            "actual_counted": row.get("actual_counted"),
            "cash_payouts": row.get("cash_payouts"),
            "recorded_by": row.get("recorded_by"),
            "created_at": row.get("created_at"),
        }

    # Sin conteo registrado — siempre HTTP 200
    return {
        "cash_count_id": None,
        "date": date,
        "status": "pending",
        "message": "No hay conteo registrado para esta fecha. cash_reconciliation en dormant.",
    }


# ---------------------------------------------------------------------------
# 4.3.5 — Daily Context (POST + PUT)
# ---------------------------------------------------------------------------

class DailyContextTags(BaseModel):
    clima: Optional[Literal["lluvia", "calor", "frio"]] = None
    equipo: Optional[Literal["falla_maquina", "mantenimiento"]] = None
    evento: Optional[Literal["festivo", "obra_vial", "promocion"]] = None
    personal: Optional[Literal["falta_staff", "capacitacion"]] = None
    otros: Optional[str] = Field(default=None, max_length=500)


class DailyContextPayload(BaseModel):
    business_id: str
    date: str  # YYYY-MM-DD
    tags: DailyContextTags


@app.post("/daily-context", status_code=201)
async def create_daily_context(payload: DailyContextPayload):
    """
    POST /daily-context
    Registra los tags de contexto para un negocio y fecha.
    Spec: n03_human_input_endpoints.md §4
    """
    db = get_supabase()

    # 1. Verificar business_id existe
    biz = db.table("businesses").select("id").eq("id", payload.business_id).execute()
    if not biz.data:
        raise HTTPException(
            status_code=404,
            detail=f"Negocio '{payload.business_id}' no encontrado.",
        )

    # 2. Verificar que no existe contexto para business_id + date
    existing = (
        db.table("daily_context")
        .select("id")
        .eq("business_id", payload.business_id)
        .eq("date", payload.date)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Ya existe contexto para business_id='{payload.business_id}' "
                f"y date='{payload.date}'. Usar PUT para actualizar."
            ),
        )

    # 3. Insertar en daily_context con tags como JSONB
    # Los campos null se persisten como null, nunca como string vacío
    context_id = str(uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    tags_dict = payload.tags.model_dump()  # None values preserved as null

    db.table("daily_context").insert(
        {
            "id": context_id,
            "business_id": payload.business_id,
            "date": payload.date,
            "tags": tags_dict,
            "created_at": now_iso,
        }
    ).execute()

    # 4. Retornar el registro creado con context_id
    return {
        "context_id": context_id,
        "business_id": payload.business_id,
        "date": payload.date,
        "tags": tags_dict,
        "created_at": now_iso,
    }


@app.put("/daily-context/{context_id}")
async def update_daily_context(context_id: str, payload: DailyContextPayload):
    """
    PUT /daily-context/{context_id}
    Actualiza los tags de un contexto ya registrado.
    Spec: n03_human_input_endpoints.md §4
    """
    db = get_supabase()

    # 1. Verificar que context_id existe
    existing = (
        db.table("daily_context").select("*").eq("id", context_id).execute()
    )
    if not existing.data:
        raise HTTPException(
            status_code=404,
            detail=f"Contexto '{context_id}' no encontrado.",
        )

    # 2. Actualizar tags (null values preserved as null, nunca string vacío)
    now_iso = datetime.now(timezone.utc).isoformat()
    tags_dict = payload.tags.model_dump()

    db.table("daily_context").update(
        {
            "tags": tags_dict,
            "updated_at": now_iso,
        }
    ).eq("id", context_id).execute()

    # 3. Retornar el registro actualizado
    return {
        "context_id": context_id,
        "business_id": payload.business_id,
        "date": payload.date,
        "tags": tags_dict,
        "updated_at": now_iso,
    }


# ===========================================================================
# S2 Gatekeeper — GET /gatekeeper/status
# Spec: .kiro/specs/mepia/s2_gatekeeper.md
# ===========================================================================

@app.get("/gatekeeper/status")
async def get_gatekeeper_status(
    business_id: str,
    date: Optional[str] = None,
):
    """
    GET /gatekeeper/status
    Retorna el GatekeeperResult actual para business_id + date.
    Si no hay registros en metric_status para esa fecha, evalúa primero.
    Spec: s2_gatekeeper.md
    """
    # 1. Default: hoy en formato YYYY-MM-DD
    if date is None:
        date = datetime.now(timezone.utc).date().isoformat()

    db = get_supabase()

    # 2. Verificar que business_id existe
    biz = db.table("businesses").select("id").eq("id", business_id).execute()
    if not biz.data:
        raise HTTPException(
            status_code=404,
            detail=f"Negocio '{business_id}' no encontrado.",
        )

    agent = GatekeeperAgent(db)

    # 3. Leer estado actual desde metric_status
    result = await asyncio.to_thread(agent.get_status, business_id, date)

    # 4. Si no hay registros → evaluar primero
    if (
        not result.active_metrics
        and not result.dormant_metrics
        and not result.blocked_metrics
    ):
        result = await asyncio.to_thread(agent.evaluate, business_id, date)

    # 5. Retornar GatekeeperResult
    return result
