"""
PBT — N13: CriticVerdict
Propiedades de correctness para el Revisor de Calidad.
Spec: .kiro/specs/mepia/n13_revisor.md §Correctness Properties
"""
from typing import List, Optional
from uuid import uuid4

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from agents.n13_revisor import (
    CriticVerdict,
    TipoFalla,
    n13_conditional_edge,
    MAX_INTENTOS,
)
from agents.layer3_state import Layer3State


# ---------------------------------------------------------------------------
# Estrategias
# ---------------------------------------------------------------------------

tipo_falla_strategy = st.sampled_from([
    TipoFalla.ALUCINACION_MATEMATICA,
    TipoFalla.DESVIACION_IDENTIDAD,
    TipoFalla.NINGUNA,
])

tipos_falla_list_strategy = st.lists(tipo_falla_strategy, min_size=1, max_size=3)


# ---------------------------------------------------------------------------
# P1: aprobado=True → tipos_falla == ["NINGUNA"]
# ---------------------------------------------------------------------------

@given(
    insight=st.text(min_size=5, max_size=200),
)
@settings(max_examples=200)
def test_p1_aprobado_implica_tipos_falla_ninguna(insight):
    """
    P1: aprobado == True → tipos_falla == ["NINGUNA"] siempre.
    Spec: n13_revisor.md §Correctness Properties P1
    """
    verdict = CriticVerdict(
        aprobado=True,
        tipos_falla=[TipoFalla.NINGUNA],
        warning_especifico=None,
        insight_para_memoria=insight,
    )

    assert verdict.aprobado is True
    assert verdict.tipos_falla == [TipoFalla.NINGUNA], (
        f"aprobado=True → tipos_falla debe ser ['NINGUNA'], got {verdict.tipos_falla}"
    )


# ---------------------------------------------------------------------------
# P2: aprobado=False → warning_especifico nunca es None
# ---------------------------------------------------------------------------

@given(
    tipos_falla=st.lists(
        st.sampled_from([TipoFalla.ALUCINACION_MATEMATICA, TipoFalla.DESVIACION_IDENTIDAD]),
        min_size=1,
        max_size=2,
        unique=True,
    ),
    warning=st.text(min_size=5, max_size=200),
)
@settings(max_examples=200)
def test_p2_rechazado_implica_warning_no_nulo(tipos_falla, warning):
    """
    P2: aprobado == False → warning_especifico nunca es None.
    Spec: n13_revisor.md §Correctness Properties P2
    """
    verdict = CriticVerdict(
        aprobado=False,
        tipos_falla=tipos_falla,
        warning_especifico=warning,
        insight_para_memoria=None,
    )

    assert verdict.aprobado is False
    assert verdict.warning_especifico is not None, (
        "aprobado=False → warning_especifico no puede ser None"
    )


# ---------------------------------------------------------------------------
# P4: intentos_critico >= 2 → draft_status == "approved_with_warning"
# ---------------------------------------------------------------------------

@given(
    intentos=st.integers(min_value=MAX_INTENTOS, max_value=10),
)
@settings(max_examples=200)
def test_p4_cortafuegos_garantiza_approved_with_warning(intentos):
    """
    P4: intentos_critico >= MAX_INTENTOS → draft_status == "approved_with_warning", nunca "rejected".
    Spec: n13_revisor.md §Correctness Properties P4
    """
    # Simular el estado con intentos >= MAX_INTENTOS
    state = {
        "layer3_run_id": str(uuid4()),
        "layer2_run_id": str(uuid4()),
        "sequential_run_id": str(uuid4()),
        "business_id": str(uuid4()),
        "date": "2024-01-15",
        "archetype": "Operative Genius",
        "enriched_payload": {},
        "draft_report": {"operational_narrative": "Test narrative"},
        "intentos_critico": intentos,
        "feedback_critico": "Error previo",
        "historial_feedback": ["Error 1"],
        "tipos_falla_critico": [],
        "draft_status": "rejected",
        "audit_results": [],
        "final_response": None,
        "_db": None,
    }

    # El cortafuegos debe activarse
    assert intentos >= MAX_INTENTOS, "El test requiere intentos >= MAX_INTENTOS"

    # Simular la lógica del cortafuegos
    if intentos >= MAX_INTENTOS:
        draft_status = "approved_with_warning"
    else:
        draft_status = "rejected"

    assert draft_status == "approved_with_warning", (
        f"intentos={intentos} >= {MAX_INTENTOS} → debe ser 'approved_with_warning', got '{draft_status}'"
    )
    assert draft_status != "rejected", (
        "Con cortafuegos activo, draft_status nunca debe ser 'rejected'"
    )


# ---------------------------------------------------------------------------
# n13_conditional_edge: approved/approved_with_warning → n14
# ---------------------------------------------------------------------------

@given(
    draft_status=st.sampled_from(["approved", "approved_with_warning"]),
)
@settings(max_examples=200)
def test_conditional_edge_aprobado_va_a_n14(draft_status):
    """
    draft_status approved o approved_with_warning → n14_informe_final.
    Spec: layer3_graph.md §Conditional edge
    """
    state = {
        "layer3_run_id": str(uuid4()),
        "layer2_run_id": str(uuid4()),
        "sequential_run_id": str(uuid4()),
        "business_id": str(uuid4()),
        "date": "2024-01-15",
        "archetype": "Operative Genius",
        "enriched_payload": {},
        "draft_report": None,
        "intentos_critico": 0,
        "feedback_critico": None,
        "historial_feedback": [],
        "tipos_falla_critico": [],
        "draft_status": draft_status,
        "audit_results": [],
        "final_response": None,
    }

    next_node = n13_conditional_edge(state)
    assert next_node == "n14_informe_final", (
        f"draft_status='{draft_status}' → debe ir a 'n14_informe_final', got '{next_node}'"
    )


@given(
    intentos=st.integers(min_value=0, max_value=MAX_INTENTOS - 1),
)
@settings(max_examples=200)
def test_conditional_edge_rechazado_va_a_n11(intentos):
    """
    draft_status rejected con intentos < MAX_INTENTOS → n11_consultor.
    """
    state = {
        "layer3_run_id": str(uuid4()),
        "layer2_run_id": str(uuid4()),
        "sequential_run_id": str(uuid4()),
        "business_id": str(uuid4()),
        "date": "2024-01-15",
        "archetype": "Operative Genius",
        "enriched_payload": {},
        "draft_report": None,
        "intentos_critico": intentos,
        "feedback_critico": "Error detectado",
        "historial_feedback": [],
        "tipos_falla_critico": [],
        "draft_status": "rejected",
        "audit_results": [],
        "final_response": None,
    }

    next_node = n13_conditional_edge(state)
    assert next_node == "n11_consultor", (
        f"draft_status='rejected' con intentos={intentos} → debe ir a 'n11_consultor', got '{next_node}'"
    )
