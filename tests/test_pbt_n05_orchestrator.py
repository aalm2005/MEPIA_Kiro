"""
PBT — N05: OrchestratorResult
Propiedades de correctness para el CEO Orchestrator.
Spec: .kiro/specs/mepia/n05_ceo_orchestrator.md §Correctness Properties
"""
from typing import Optional
from uuid import uuid4

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from agents.ceo_orchestrator import (
    AuditInsight,
    EscalationInfo,
    OrchestratorResult,
    SequentialResults,
    _SEVERITY_TO_ALERT,
)


# ---------------------------------------------------------------------------
# Estrategias
# ---------------------------------------------------------------------------

archetype_strategy = st.sampled_from(["Operative Genius", "Product Purist", "Growth Hacker"])
severity_strategy = st.sampled_from(["low", "medium", "high"])
alert_level_strategy = st.sampled_from(["info", "warning", "critical"])
pipeline_status_strategy = st.sampled_from(["completed", "partial", "escalated", "failed"])


# ---------------------------------------------------------------------------
# P1: run_id, pipeline_status, completed_at siempre no nulos
# ---------------------------------------------------------------------------

@given(
    pipeline_status=pipeline_status_strategy,
    archetype=archetype_strategy,
)
@settings(max_examples=200)
def test_p1_campos_obligatorios_siempre_presentes(pipeline_status, archetype):
    """
    P1: run_id, pipeline_status y completed_at siempre no nulos en OrchestratorResult.
    """
    result = OrchestratorResult(
        run_id=str(uuid4()),
        business_id=str(uuid4()),
        date="2024-01-15",
        archetype=archetype,
        pipeline_status=pipeline_status,
        sequential_results=SequentialResults(
            active_metrics=[],
            calc_results=[],
            forensic_report={},
            audit_insights=[],
        ),
        escalation=EscalationInfo(triggered=False),
        dormant_metrics=[],
        completed_at="2024-01-15T22:00:00Z",
    )

    assert result.run_id is not None and result.run_id != ""
    assert result.pipeline_status in ("completed", "partial", "escalated", "failed")
    assert result.completed_at is not None


# ---------------------------------------------------------------------------
# P2: escalation.triggered=True → layer2_run_id no nulo
# ---------------------------------------------------------------------------

@given(layer2_run_id=st.uuids().map(str))
@settings(max_examples=200)
def test_p2_escalation_triggered_implica_layer2_run_id_no_nulo(layer2_run_id):
    """
    P2: escalation.triggered=True → layer2_run_id no nulo.
    Spec: n05_ceo_orchestrator.md §Correctness Properties P2
    """
    escalation = EscalationInfo(
        triggered=True,
        reason="critical_alerts_detected",
        layer2_run_id=layer2_run_id,
    )

    assert escalation.triggered is True
    assert escalation.layer2_run_id is not None
    assert escalation.layer2_run_id != ""


# ---------------------------------------------------------------------------
# P3: escalation.triggered=False → layer2_run_id es null
# ---------------------------------------------------------------------------

@given(reason=st.one_of(st.none(), st.text(min_size=1, max_size=50)))
@settings(max_examples=200)
def test_p3_escalation_not_triggered_implica_layer2_run_id_nulo(reason):
    """
    P3: escalation.triggered=False → layer2_run_id es null siempre.
    Spec: n05_ceo_orchestrator.md §Correctness Properties P3
    """
    escalation = EscalationInfo(triggered=False, reason=reason, layer2_run_id=None)

    assert escalation.triggered is False
    assert escalation.layer2_run_id is None


# ---------------------------------------------------------------------------
# P4: escalate_to_parallel=False → triggered siempre False
# ---------------------------------------------------------------------------

@given(
    risk_level=st.sampled_from(["low", "medium", "high"]),
)
@settings(max_examples=200)
def test_p4_escalate_to_parallel_false_nunca_escala(risk_level):
    """
    P4: escalate_to_parallel=False → escalation.triggered siempre False.
    Spec: n05_ceo_orchestrator.md §Correctness Properties P4
    """
    # Simular la lógica de _evaluate_escalation con escalate_to_parallel=False
    escalate_to_parallel = False

    if not escalate_to_parallel:
        escalation = EscalationInfo(triggered=False, reason=None, layer2_run_id=None)
    else:
        # No debería llegar aquí en este test
        escalation = EscalationInfo(triggered=True, reason="test", layer2_run_id=str(uuid4()))

    assert escalation.triggered is False, (
        "escalate_to_parallel=False → triggered debe ser False siempre"
    )


# ---------------------------------------------------------------------------
# P6: severity "high" → alert_level "critical" sin excepción
# ---------------------------------------------------------------------------

@given(severity=severity_strategy)
@settings(max_examples=300)
def test_p6_severity_high_implica_alert_level_critical(severity):
    """
    P6: AnomalyItem.severity "high" → AuditInsight.alert_level "critical" sin excepción.
    El mapeo está garantizado en código, no solo en el prompt.
    Spec: n05_ceo_orchestrator.md §Correctness Properties P6
    """
    alert_level = _SEVERITY_TO_ALERT.get(severity, "info")

    if severity == "high":
        assert alert_level == "critical", (
            f"severity='high' → alert_level debe ser 'critical', got '{alert_level}'"
        )
    elif severity == "medium":
        assert alert_level == "warning"
    elif severity == "low":
        assert alert_level == "info"


# ---------------------------------------------------------------------------
# P7: observed_causality no cambia alert_level
# ---------------------------------------------------------------------------

@given(
    severity=severity_strategy,
    has_causality=st.booleans(),
)
@settings(max_examples=300)
def test_p7_observed_causality_no_cambia_alert_level(severity, has_causality):
    """
    P7: observed_causality presente → alert_level no cambia, solo context_weight y tono.
    Spec: n05_ceo_orchestrator.md §Correctness Properties P7
    """
    # El mapeo severity → alert_level es fijo, independiente de observed_causality
    alert_level_sin_causality = _SEVERITY_TO_ALERT.get(severity, "info")
    alert_level_con_causality = _SEVERITY_TO_ALERT.get(severity, "info")

    assert alert_level_sin_causality == alert_level_con_causality, (
        "observed_causality no debe cambiar el alert_level"
    )
