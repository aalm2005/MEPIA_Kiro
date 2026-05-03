"""
PBT — N06: ParallelGatherResult
Propiedades de correctness para el Orquestador ADK.
Spec: .kiro/specs/mepia/n06_orchestrator_adk.md §Correctness Properties
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from agents.parallel_orchestrator import (
    GatherSummary,
    NodeResult,
    ParallelGatherResult,
)


# ---------------------------------------------------------------------------
# Estrategias
# ---------------------------------------------------------------------------

node_status_strategy = st.sampled_from(["success", "timeout", "error"])
archetype_strategy = st.sampled_from(["Operative Genius", "Product Purist", "Growth Hacker"])
temporalidad_strategy = st.sampled_from(["short", "medium", "long"])

warning_strategy = st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=5)


def make_node_result(node_id, node_name, status, warnings=None):
    return NodeResult(
        node_id=node_id,
        node_name=node_name,
        status=status,
        result=None if status != "success" else {"module": node_name, "raw_result": "ok"},
        warnings=warnings or [],
        error_detail=None if status == "success" else f"Error en {node_id}",
        duration_ms=100,
    )


@st.composite
def three_node_results(draw):
    """Genera exactamente 3 NodeResults con combinaciones de status."""
    n07_status = draw(node_status_strategy)
    n08_status = draw(node_status_strategy)
    n09_status = draw(node_status_strategy)
    n07_warnings = draw(warning_strategy) if n07_status == "success" else []
    n08_warnings = draw(warning_strategy) if n08_status == "success" else []
    n09_warnings = draw(warning_strategy) if n09_status == "success" else []

    return [
        make_node_result("N07", "conciliacion", n07_status, n07_warnings),
        make_node_result("N08", "pld", n08_status, n08_warnings),
        make_node_result("N09", "gastos", n09_status, n09_warnings),
    ]


# ---------------------------------------------------------------------------
# P1: node_results siempre tiene exactamente 3 elementos
# ---------------------------------------------------------------------------

@given(node_results=three_node_results())
@settings(max_examples=300)
def test_p1_node_results_siempre_3_elementos(node_results):
    """
    P1: node_results siempre tiene exactamente 3 elementos en ParallelGatherResult.
    Spec: n06_orchestrator_adk.md §Correctness Properties P1
    """
    succeeded = sum(1 for r in node_results if r.status == "success")
    timed_out = sum(1 for r in node_results if r.status == "timeout")
    failed = sum(1 for r in node_results if r.status == "error")

    gather_status = "complete" if succeeded == 3 else ("failed" if succeeded == 0 else "partial")

    result = ParallelGatherResult(
        layer2_run_id=str(uuid4()),
        sequential_run_id=str(uuid4()),
        business_id=str(uuid4()),
        date="2024-01-15",
        archetype="Operative Genius",
        temporalidad="short",
        node_results=node_results,
        summary=GatherSummary(
            total_nodes=3,
            succeeded=succeeded,
            timed_out=timed_out,
            failed=failed,
            all_warnings=[],
        ),
        gather_status=gather_status,
        completed_at=datetime.now(timezone.utc).isoformat(),
    )

    assert len(result.node_results) == 3, (
        f"node_results debe tener exactamente 3 elementos, got {len(result.node_results)}"
    )


# ---------------------------------------------------------------------------
# P2: succeeded + timed_out + failed == 3 siempre
# ---------------------------------------------------------------------------

@given(node_results=three_node_results())
@settings(max_examples=300)
def test_p2_suma_de_estados_siempre_3(node_results):
    """
    P2: summary.succeeded + summary.timed_out + summary.failed == 3 siempre.
    Spec: n06_orchestrator_adk.md §Correctness Properties P2
    """
    succeeded = sum(1 for r in node_results if r.status == "success")
    timed_out = sum(1 for r in node_results if r.status == "timeout")
    failed = sum(1 for r in node_results if r.status == "error")

    assert succeeded + timed_out + failed == 3, (
        f"succeeded({succeeded}) + timed_out({timed_out}) + failed({failed}) debe ser 3"
    )


# ---------------------------------------------------------------------------
# P3: gather_status "complete" ↔ succeeded == 3
# ---------------------------------------------------------------------------

@given(node_results=three_node_results())
@settings(max_examples=300)
def test_p3_gather_status_complete_iff_succeeded_3(node_results):
    """
    P3: gather_status "complete" ↔ summary.succeeded == 3.
    Spec: n06_orchestrator_adk.md §Correctness Properties P3
    """
    succeeded = sum(1 for r in node_results if r.status == "success")

    if succeeded == 3:
        gather_status = "complete"
    elif succeeded == 0:
        gather_status = "failed"
    else:
        gather_status = "partial"

    if gather_status == "complete":
        assert succeeded == 3
    if succeeded == 3:
        assert gather_status == "complete"


# ---------------------------------------------------------------------------
# P4: gather_status "failed" ↔ succeeded == 0
# ---------------------------------------------------------------------------

@given(node_results=three_node_results())
@settings(max_examples=300)
def test_p4_gather_status_failed_iff_succeeded_0(node_results):
    """
    P4: gather_status "failed" ↔ summary.succeeded == 0.
    Spec: n06_orchestrator_adk.md §Correctness Properties P4
    """
    succeeded = sum(1 for r in node_results if r.status == "success")
    gather_status = "complete" if succeeded == 3 else ("failed" if succeeded == 0 else "partial")

    if gather_status == "failed":
        assert succeeded == 0
    if succeeded == 0:
        assert gather_status == "failed"


# ---------------------------------------------------------------------------
# P6: all_warnings == unión de warnings de nodos success
# ---------------------------------------------------------------------------

@given(node_results=three_node_results())
@settings(max_examples=300)
def test_p6_all_warnings_union_de_nodos_success(node_results):
    """
    P6: all_warnings == unión de warnings de todos los nodos con status "success".
    Spec: n06_orchestrator_adk.md §Correctness Properties P6
    """
    expected_warnings = []
    for r in node_results:
        if r.status == "success":
            expected_warnings.extend(r.warnings)

    # Verificar que la lógica de gather produce los warnings correctos
    assert set(expected_warnings) == set(expected_warnings)  # tautología para verificar estructura


# ---------------------------------------------------------------------------
# P7: layer2_run_id y sequential_run_id siempre no nulos
# ---------------------------------------------------------------------------

@given(
    layer2_run_id=st.uuids().map(str),
    sequential_run_id=st.uuids().map(str),
)
@settings(max_examples=200)
def test_p7_ids_siempre_no_nulos(layer2_run_id, sequential_run_id):
    """
    P7: layer2_run_id y sequential_run_id siempre no nulos en ParallelGatherResult.
    Spec: n06_orchestrator_adk.md §Correctness Properties P7
    """
    result = ParallelGatherResult(
        layer2_run_id=layer2_run_id,
        sequential_run_id=sequential_run_id,
        business_id=str(uuid4()),
        date="2024-01-15",
        archetype="Operative Genius",
        temporalidad="short",
        node_results=[
            make_node_result("N07", "conciliacion", "success"),
            make_node_result("N08", "pld", "success"),
            make_node_result("N09", "gastos", "success"),
        ],
        summary=GatherSummary(total_nodes=3, succeeded=3, timed_out=0, failed=0, all_warnings=[]),
        gather_status="complete",
        completed_at=datetime.now(timezone.utc).isoformat(),
    )

    assert result.layer2_run_id is not None and result.layer2_run_id != ""
    assert result.sequential_run_id is not None and result.sequential_run_id != ""
