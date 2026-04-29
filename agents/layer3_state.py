"""
MEPIA — Layer 3 Graph State
Estado compartido del grafo LangGraph para el loop N11 → N13 → N14.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict


class Layer3State(TypedDict):
    """
    Estado mutable del grafo de Layer 3.

    Campos de trazabilidad (inmutables en la práctica — solo N10 los escribe):
        layer3_run_id    : UUID generado por N10 (str)
        layer2_run_id    : UUID del run de Layer 2 (str)
        sequential_run_id: UUID del run secuencial (str)
        business_id      : UUID del negocio auditado (str)
        date             : Fecha auditada (ISO-8601 string)
        archetype        : Arquetipo CEO del run

    Payload de datos (inmutable — escrito por N10, leído por N11 y N13):
        enriched_payload : EnrichedAuditPayload serializado como dict.
                           N13 lo usa como fuente de verdad para el test matemático.

    Borrador generado por N11 (mutable — N11 lo escribe, N13 lo evalúa):
        draft_report     : DraftReport serializado como dict | None

    Variables de control del loop de calidad (escritas por N13):
        intentos_critico : Contador de intentos del Critic. Inicia en 0.
                           N13 lo incrementa en cada rechazo.
                           Cortafuegos activo cuando intentos_critico >= 2.
        feedback_critico : Último warning del Critic para que N11 corrija.
                           None si no hay rechazo previo.
        historial_feedback: Acumulado de todos los warnings de cada rechazo.
                            N11 puede leer el historial completo para entender
                            el patrón de errores entre reintentos.
        tipos_falla_critico: Lista de tipos de falla detectados en el último veredicto.
                             Puede contener múltiples valores simultáneos.
                             Ej: ["ALUCINACION_MATEMATICA", "DESVIACION_IDENTIDAD"]
        draft_status     : Estado del borrador en el loop de calidad.
                           "pending"               → N11 aún no ha generado borrador
                           "approved"              → N13 aprobó, listo para N14
                           "approved_with_warning" → Cortafuegos activado, pasa a N14
                           "rejected"              → N13 rechazó, vuelve a N11

    Auditoría del nodo (escritas por N13 en cada ejecución):
        audit_results    : Lista acumulada de veredictos serializados de N13.
                           Cada entrada corresponde a una ejecución del nodo.
    """

    # ── Trazabilidad ──────────────────────────────────────────────────────────
    layer3_run_id: str
    layer2_run_id: str
    sequential_run_id: str
    business_id: str
    date: str
    archetype: str

    # ── Payload de datos (fuente de verdad para N13) ──────────────────────────
    enriched_payload: Dict[str, Any]  # EnrichedAuditPayload serializado

    # ── Borrador generado por N11 ─────────────────────────────────────────────
    draft_report: Optional[Dict[str, Any]]  # DraftReport serializado | None

    # ── Control del loop de calidad (escritas por N13) ───────────────────────
    intentos_critico: int                  # default 0
    feedback_critico: Optional[str]        # último warning — default None
    historial_feedback: List[str]          # acumulado de todos los warnings — default []
    tipos_falla_critico: List[str]         # fallas del último veredicto — default []
    draft_status: str                      # "pending" | "approved" | "approved_with_warning" | "rejected"

    # ── Auditoría del nodo ────────────────────────────────────────────────────
    audit_results: List[Dict[str, Any]]    # veredictos serializados de N13 — default []
