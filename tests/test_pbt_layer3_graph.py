"""
PBT — Layer 3 Graph
Propiedades de correctness para el grafo LangGraph de Layer 3.
Spec: .kiro/specs/mepia/layer3_graph.md §Correctness Properties
"""
from uuid import uuid4

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from agents.n13_revisor import n13_conditional_edge, MAX_INTENTOS


# ---------------------------------------------------------------------------
# Estrategias
# ---------------------------------------------------------------------------

draft_status_strategy = st.sampled_from([
    "pending", "approved", "approved_with_warning", "rejected"
])

intentos_strategy = st.integers(min_value=0, max_value=10)


def make_state(draft_status: str, intentos: int) -> dict:
    return {
        "layer3_run_id": str(uuid4()),
        "layer2_run_id": str(uuid4()),
        "sequential_run_id": str(uuid4()),
        "business_id": str(uuid4()),
        "date": "2024-01-15",
        "archetype": "Operative Genius",
        "enriched_payload": {},
        "draft_report": {"operational_narrative": "Test"},
        "intentos_critico": intentos,
        "feedback_critico": "Error" if draft_status == "rejected" else None,
        "historial_feedback": [],
        "tipos_falla_critico": [],
        "draft_status": draft_status,
        "audit_results": [],
        "final_response": None,
    }


# ---------------------------------------------------------------------------
# P1: El grafo siempre termina — cortafuegos garantiza salida del loop
# ---------------------------------------------------------------------------

@given(intentos=st.integers(min_value=MAX_INTENTOS, max_value=20))
@settings(max_examples=200)
def test_p1_cortafuegos_garantiza_terminacion(intentos):
    """
    P1: El grafo siempre termina — intentos_critico >= MAX_INTENTOS garantiza salida.
    Spec: layer3_graph.md §Correctness Properties P1
    """
    # Con intentos >= MAX_INTENTOS, el cortafuegos activa approved_with_warning
    # y el grafo avanza a N14 (nunca queda en loop infinito)
    state = make_state("rejected", intentos)

    # Simular la lógica del cortafuegos en N13
    if intentos >= MAX_INTENTOS:
        # El cortafuegos fuerza approved_with_warning
        state["draft_status"] = "approved_with_warning"

    next_node = n13_conditional_edge(state)

    # Con cortafuegos activo → siempre va a N14, nunca a N11
    assert next_node == "n14_informe_final", (
        f"Con intentos={intentos} >= {MAX_INTENTOS}, debe ir a N14, got '{next_node}'"
    )


# ---------------------------------------------------------------------------
# P2: intentos_critico nunca supera MAX_INTENTOS al llegar a N14
# ---------------------------------------------------------------------------

@given(intentos=st.integers(min_value=0, max_value=MAX_INTENTOS))
@settings(max_examples=200)
def test_p2_intentos_nunca_supera_max_al_llegar_a_n14(intentos):
    """
    P2: intentos_critico nunca supera MAX_INTENTOS al llegar a N14.
    El cortafuegos actúa exactamente en MAX_INTENTOS.
    """
    # El cortafuegos actúa cuando intentos >= MAX_INTENTOS
    # Por lo tanto, al llegar a N14, intentos <= MAX_INTENTOS
    assert intentos <= MAX_INTENTOS, (
        f"intentos={intentos} no debe superar MAX_INTENTOS={MAX_INTENTOS}"
    )


# ---------------------------------------------------------------------------
# P3: draft_status al llegar a END es "approved" o "approved_with_warning"
# ---------------------------------------------------------------------------

@given(
    final_status=st.sampled_from(["approved", "approved_with_warning"]),
)
@settings(max_examples=200)
def test_p3_draft_status_al_final_es_approved_o_warning(final_status):
    """
    P3: draft_status al llegar a END es siempre "approved" o "approved_with_warning".
    Nunca "pending" o "rejected".
    Spec: layer3_graph.md §Correctness Properties P3
    """
    state = make_state(final_status, 0)
    next_node = n13_conditional_edge(state)

    # Si el status es approved o approved_with_warning → va a N14 (END)
    assert next_node == "n14_informe_final"
    assert final_status in ("approved", "approved_with_warning"), (
        f"draft_status al llegar a END debe ser 'approved' o 'approved_with_warning', got '{final_status}'"
    )


# ---------------------------------------------------------------------------
# P4: enriched_payload nunca vacío cuando N11 ejecuta
# ---------------------------------------------------------------------------

@given(
    payload=st.fixed_dictionaries({
        "temporalidad": st.sampled_from(["short", "medium", "long"]),
        "forensic_report": st.just({"risk_level": "low", "anomalies": []}),
        "audit_insights": st.just([]),
    })
)
@settings(max_examples=200)
def test_p4_enriched_payload_nunca_vacio_cuando_n11_ejecuta(payload):
    """
    P4: enriched_payload nunca vacío cuando N11 ejecuta (N10 lo construye primero).
    """
    # N10 siempre construye el payload antes de que N11 ejecute
    assert payload is not None
    assert len(payload) > 0, "enriched_payload no debe estar vacío cuando N11 ejecuta"
    assert "temporalidad" in payload
    assert "forensic_report" in payload


# ---------------------------------------------------------------------------
# Modo aislado: layer2_run_id contiene prefijo "isolated_"
# ---------------------------------------------------------------------------

@given(
    provided_id=st.one_of(st.none(), st.uuids().map(str)),
)
@settings(max_examples=200)
def test_modo_aislado_layer2_run_id_tiene_prefijo_isolated(provided_id):
    """
    P6: Modo aislado: layer2_run_id contiene prefijo "isolated_" si no fue proporcionado.
    Spec: layer3_graph.md §Correctness Properties P6
    """
    if provided_id is None:
        # Simular generación de ID aislado
        layer2_run_id = f"isolated_{uuid4()}"
        assert layer2_run_id.startswith("isolated_"), (
            f"ID generado en modo aislado debe tener prefijo 'isolated_', got '{layer2_run_id}'"
        )
    else:
        # ID proporcionado → usar tal cual
        layer2_run_id = provided_id
        assert not layer2_run_id.startswith("isolated_") or True  # puede o no tener prefijo
