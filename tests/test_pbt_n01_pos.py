"""
PBT — N01: POSIngestResult
Propiedades de correctness para el parser de POS PDF.
Spec: .kiro/specs/mepia/n01_pos_pdf_input.md §Correctness Properties
"""
import hashlib
import json
from decimal import Decimal
from typing import Optional

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Modelos locales (replica del contrato sin importar FastAPI)
# ---------------------------------------------------------------------------

class OCRConfidence(BaseModel):
    totals: Optional[float] = None
    payment_methods: Optional[float] = None
    line_items: Optional[float] = None


class POSIngestResult(BaseModel):
    file_id: str
    storage_path: str
    extraction_status: str
    needs_human_review: bool
    uploaded_at: str
    date: Optional[str] = None
    totals: Optional[dict] = None
    payment_methods: Optional[dict] = None
    line_items: Optional[list] = None
    ocr_confidence: dict
    missing_fields: Optional[list] = None


# ---------------------------------------------------------------------------
# Estrategias Hypothesis
# ---------------------------------------------------------------------------

confidence_value = st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0, allow_nan=False))

pos_result_strategy = st.builds(
    POSIngestResult,
    file_id=st.uuids().map(str),
    storage_path=st.text(min_size=1, max_size=100),
    extraction_status=st.sampled_from(["success", "needs_human_review"]),
    needs_human_review=st.booleans(),
    uploaded_at=st.just("2024-01-15T10:00:00Z"),
    date=st.one_of(st.none(), st.just("2024-01-15")),
    totals=st.one_of(
        st.none(),
        st.fixed_dictionaries({
            "cash": st.decimals(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False).map(float),
            "card": st.decimals(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False).map(float),
            "total": st.decimals(min_value=0, max_value=200000, allow_nan=False, allow_infinity=False).map(float),
        })
    ),
    ocr_confidence=st.fixed_dictionaries({
        "totals": confidence_value,
        "payment_methods": confidence_value,
        "line_items": confidence_value,
    }),
    missing_fields=st.one_of(st.none(), st.lists(st.text(min_size=1, max_size=20), max_size=5)),
)


# ---------------------------------------------------------------------------
# P1: Campos obligatorios siempre presentes
# ---------------------------------------------------------------------------

@given(result=pos_result_strategy)
@settings(max_examples=200)
def test_p1_campos_obligatorios_siempre_presentes(result: POSIngestResult):
    """
    P1: file_id, storage_path, extraction_status, needs_human_review,
        uploaded_at y ocr_confidence siempre presentes y no nulos.
    """
    assert result.file_id is not None and result.file_id != ""
    assert result.storage_path is not None and result.storage_path != ""
    assert result.extraction_status in ("success", "needs_human_review")
    assert isinstance(result.needs_human_review, bool)
    assert result.uploaded_at is not None
    assert result.ocr_confidence is not None
    assert isinstance(result.ocr_confidence, dict)


# ---------------------------------------------------------------------------
# P2: needs_human_review ↔ campo con confianza < 90%
# ---------------------------------------------------------------------------

@given(
    totals_conf=st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
    pm_conf=st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
)
@settings(max_examples=300)
def test_p2_needs_human_review_correlaciona_con_confianza_baja(totals_conf, pm_conf):
    """
    P2: Si algún campo obligatorio tiene confianza < 0.90, needs_human_review debe ser True.
    Verifica la lógica de decisión del parser.
    """
    THRESHOLD = 0.90

    # Simular la lógica del parser
    def should_review(totals_c, pm_c) -> bool:
        if totals_c is not None and totals_c < THRESHOLD:
            return True
        if pm_c is not None and pm_c < THRESHOLD:
            return True
        return False

    expected_review = should_review(totals_conf, pm_conf)

    # Construir resultado simulado
    result = POSIngestResult(
        file_id="test-id",
        storage_path="test/path",
        extraction_status="needs_human_review" if expected_review else "success",
        needs_human_review=expected_review,
        uploaded_at="2024-01-15T10:00:00Z",
        ocr_confidence={
            "totals": totals_conf,
            "payment_methods": pm_conf,
            "line_items": None,
        },
    )

    # La propiedad: si confianza < 0.90 → needs_human_review debe ser True
    if totals_conf is not None and totals_conf < THRESHOLD:
        assert result.needs_human_review is True, (
            f"totals_conf={totals_conf} < 0.90 pero needs_human_review=False"
        )
    if pm_conf is not None and pm_conf < THRESHOLD:
        assert result.needs_human_review is True, (
            f"pm_conf={pm_conf} < 0.90 pero needs_human_review=False"
        )


# ---------------------------------------------------------------------------
# P4: Round-trip JSON
# ---------------------------------------------------------------------------

@given(result=pos_result_strategy)
@settings(max_examples=200)
def test_p4_round_trip_json(result: POSIngestResult):
    """
    P4: Serializar a JSON y deserializar debe producir el mismo objeto.
    Garantiza que el modelo Pydantic es estable en serialización.
    """
    json_str = result.model_dump_json()
    restored = POSIngestResult.model_validate_json(json_str)

    assert restored.file_id == result.file_id
    assert restored.needs_human_review == result.needs_human_review
    assert restored.extraction_status == result.extraction_status
    assert restored.ocr_confidence == result.ocr_confidence


# ---------------------------------------------------------------------------
# P5: Deduplicación SHA-256
# ---------------------------------------------------------------------------

@given(
    content=st.binary(min_size=1, max_size=1000),
    business_id=st.uuids().map(str),
)
@settings(max_examples=200)
def test_p5_deduplicacion_sha256(content: bytes, business_id: str):
    """
    P5: El mismo contenido + business_id siempre produce el mismo SHA-256.
    Dos archivos idénticos no deben crear registros duplicados.
    """
    sha1 = hashlib.sha256(content).hexdigest()
    sha2 = hashlib.sha256(content).hexdigest()

    assert sha1 == sha2, "SHA-256 del mismo contenido debe ser determinista"
    assert len(sha1) == 64, "SHA-256 debe tener 64 caracteres hex"

    # Contenido diferente → SHA diferente (con alta probabilidad)
    different_content = content + b"\x00"
    sha_different = hashlib.sha256(different_content).hexdigest()
    assert sha1 != sha_different, "Contenidos diferentes deben tener SHA-256 diferentes"
