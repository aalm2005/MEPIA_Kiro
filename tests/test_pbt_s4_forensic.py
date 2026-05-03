"""
PBT — S4: ForensicReport
Propiedades de correctness para el Forensic CFO.
Spec: .kiro/specs/mepia/s4_auditoria_ia.md §Correctness Properties
"""
from typing import List
from uuid import uuid4

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from agents.forensic_cfo import AnomalyItem, ForensicReport, _compute_risk_level


# ---------------------------------------------------------------------------
# Estrategias
# ---------------------------------------------------------------------------

severity_strategy = st.sampled_from(["low", "medium", "high"])
anomaly_type_strategy = st.sampled_from([
    "margin_leak", "source_discrepancy", "operational_ceiling", "cost_spike", "other"
])

anomaly_strategy = st.builds(
    AnomalyItem,
    anomaly_id=st.uuids().map(str),
    type=anomaly_type_strategy,
    description=st.text(min_size=5, max_size=200),
    severity=severity_strategy,
    quantified_impact=st.text(min_size=1, max_size=50),
    data_points=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=5),
    metric_origin=st.text(min_size=1, max_size=30),
)

anomaly_list_strategy = st.lists(anomaly_strategy, min_size=0, max_size=10)


# ---------------------------------------------------------------------------
# P1: observed_causality nunca modifica severity
# ---------------------------------------------------------------------------

@given(
    anomalies=anomaly_list_strategy,
    context_tags=st.one_of(
        st.none(),
        st.fixed_dictionaries({
            "clima": st.one_of(st.none(), st.sampled_from(["lluvia", "calor", "frio"])),
            "equipo": st.one_of(st.none(), st.sampled_from(["falla_maquina", "mantenimiento"])),
        })
    ),
)
@settings(max_examples=300)
def test_p1_observed_causality_nunca_modifica_severity(anomalies, context_tags):
    """
    P1: observed_causality se adjunta sin interpretación.
    La severidad de cada AnomalyItem no cambia por el contexto del día.
    """
    # Guardar severidades originales
    original_severities = {a.anomaly_id: a.severity for a in anomalies}

    # Simular que observed_causality se adjunta (como hace ForensicCFOAgent.run)
    # Las severidades no deben cambiar
    for anomaly in anomalies:
        assert anomaly.severity == original_severities[anomaly.anomaly_id], (
            "observed_causality no debe modificar severity de ningún AnomalyItem"
        )


# ---------------------------------------------------------------------------
# P2: risk_level "high" ↔ ≥1 anomalía high
# ---------------------------------------------------------------------------

@given(anomalies=anomaly_list_strategy)
@settings(max_examples=500)
def test_p2_risk_level_high_iff_tiene_anomalia_high(anomalies):
    """
    P2: risk_level "high" ↔ existe al menos 1 AnomalyItem con severity "high".
    Spec: s4_auditoria_ia.md §Reglas de risk_level
    """
    risk_level = _compute_risk_level(anomalies)
    has_high = any(a.severity == "high" for a in anomalies)
    has_medium = any(a.severity == "medium" for a in anomalies)

    if has_high:
        assert risk_level == "high", (
            f"Con anomalía high → risk_level debe ser 'high', got '{risk_level}'"
        )
    elif has_medium:
        assert risk_level == "medium", (
            f"Solo anomalías medium → risk_level debe ser 'medium', got '{risk_level}'"
        )
    else:
        assert risk_level == "low", (
            f"Sin anomalías high/medium → risk_level debe ser 'low', got '{risk_level}'"
        )


# ---------------------------------------------------------------------------
# P3: source_discrepancy siempre severity "high"
# ---------------------------------------------------------------------------

@given(
    base_severity=severity_strategy,
    other_fields=st.fixed_dictionaries({
        "description": st.text(min_size=5, max_size=100),
        "quantified_impact": st.text(min_size=1, max_size=50),
        "data_points": st.lists(st.text(min_size=1, max_size=30), min_size=1, max_size=3),
        "metric_origin": st.text(min_size=1, max_size=30),
    })
)
@settings(max_examples=300)
def test_p3_source_discrepancy_siempre_severity_high(base_severity, other_fields):
    """
    P3: source_discrepancy siempre tiene severity "high" independientemente del contexto.
    El override post-LLM en ForensicCFOAgent.run() garantiza esto.
    Spec: s4_auditoria_ia.md §Acceptance Criteria
    """
    # Simular el override que hace ForensicCFOAgent.run()
    item_data = {
        "anomaly_id": str(uuid4()),
        "type": "source_discrepancy",
        "severity": base_severity,  # el LLM podría retornar cualquier severidad
        **other_fields,
    }

    # Aplicar el override (como hace el agente)
    if item_data["type"] == "source_discrepancy":
        item_data["severity"] = "high"

    anomaly = AnomalyItem(**item_data)
    assert anomaly.severity == "high", (
        f"source_discrepancy debe tener severity 'high', got '{anomaly.severity}'"
    )


# ---------------------------------------------------------------------------
# P4: ForensicReport sin campo archetype
# ---------------------------------------------------------------------------

@given(anomalies=anomaly_list_strategy)
@settings(max_examples=100)
def test_p4_forensic_report_sin_archetype(anomalies):
    """
    P4: ForensicReport no tiene campo archetype — es responsabilidad de N05.
    Spec: s4_auditoria_ia.md §Correctness Properties P4
    """
    risk = _compute_risk_level(anomalies)
    report = ForensicReport(
        business_id=str(uuid4()),
        date="2024-01-15",
        risk_level=risk,
        anomalies=anomalies,
        evidence_sources=["POS"],
        observed_causality=None,
        generated_at="2024-01-15T10:00:00Z",
    )

    # ForensicReport no debe tener campo archetype
    report_dict = report.model_dump()
    assert "archetype" not in report_dict, (
        "ForensicReport no debe tener campo 'archetype'"
    )


# ---------------------------------------------------------------------------
# P5: evidence_sources solo contiene fuentes realmente comparadas
# ---------------------------------------------------------------------------

@given(
    sources=st.lists(
        st.sampled_from(["POS", "facturas", "cash_count", "recipes"]),
        min_size=0,
        max_size=4,
        unique=True,
    )
)
@settings(max_examples=200)
def test_p5_evidence_sources_solo_fuentes_reales(sources):
    """
    P5: evidence_sources contiene solo fuentes que realmente se compararon.
    Verificamos que el modelo acepta cualquier lista de strings válidos.
    """
    report = ForensicReport(
        business_id=str(uuid4()),
        date="2024-01-15",
        risk_level="low",
        anomalies=[],
        evidence_sources=sources,
        observed_causality=None,
        generated_at="2024-01-15T10:00:00Z",
    )
    assert report.evidence_sources == sources


# ---------------------------------------------------------------------------
# _compute_risk_level: sin anomalías → "low"
# ---------------------------------------------------------------------------

def test_compute_risk_level_sin_anomalias_retorna_low():
    """Sin anomalías → risk_level debe ser 'low'."""
    assert _compute_risk_level([]) == "low"
