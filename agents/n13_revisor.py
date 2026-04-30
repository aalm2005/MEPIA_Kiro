"""
MEPIA — N13 Revisor de Calidad (Critic & Enforcer)
Capa: Layer 3 — Nodo 3 | Anterior: N11 Consultor | Siguiente: N14 Informe Final

Patrón: Actor-Critic — evalúa el DraftReport de N11 contra los datos crudos
del EnrichedAuditPayload. Actúa como "unit test cognitivo" del pipeline.

Dos validaciones estrictas:
  1. Test Matemático   → detecta alucinaciones numéricas en la narrativa
  2. Test de Identidad → detecta lenguaje corporativo / pérdida del tono de piso

Archivo de implementación: agents/n13_revisor.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from agents.layer3_state import Layer3State

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

MAX_INTENTOS = 2  # Cortafuegos: si intentos_critico >= MAX_INTENTOS → approved_with_warning
MAX_PERIODOS = 7  # Límite de registros de time_series.periodos para el contexto del LLM


# ---------------------------------------------------------------------------
# Esquemas Pydantic — Salida Estructurada del LLM (N13)
# ---------------------------------------------------------------------------


class TipoFalla(str, Enum):
    """Categorías de falla que puede detectar el Critic."""

    ALUCINACION_MATEMATICA = "ALUCINACION_MATEMATICA"
    DESVIACION_IDENTIDAD = "DESVIACION_IDENTIDAD"
    NINGUNA = "NINGUNA"


class CriticVerdict(BaseModel):
    """
    Salida estructurada obligatoria del LLM de N13.

    El LLM DEBE retornar exactamente este esquema — sin texto adicional.
    tipos_falla es una lista para capturar múltiples fallas simultáneas
    (ej. alucinación matemática + desviación de identidad en el mismo borrador).
    """

    aprobado: bool = Field(
        description="True si el DraftReport pasa ambos tests. False si falla alguno."
    )
    tipos_falla: List[TipoFalla] = Field(
        description=(
            "Lista de fallas detectadas. Puede contener múltiples valores simultáneos. "
            "Valores posibles: ALUCINACION_MATEMATICA, DESVIACION_IDENTIDAD, NINGUNA. "
            "Si aprueba: ['NINGUNA']. Si falla: lista con todas las fallas encontradas."
        )
    )
    warning_especifico: Optional[str] = Field(
        default=None,
        description=(
            "Feedback exacto y accionable para que N11 corrija el borrador. "
            "Describe TODAS las fallas encontradas. "
            "Obligatorio cuando aprobado=False. Null cuando aprobado=True."
        ),
    )
    insight_para_memoria: Optional[str] = Field(
        default=None,
        description=(
            "Resumen de exactamente 2 líneas de la conclusión principal del reporte. "
            "Obligatorio cuando aprobado=True. Null cuando aprobado=False. "
            "Será guardado en mepia_memory como MemoryChunk."
        ),
    )


# ---------------------------------------------------------------------------
# System Prompt del Critic
# ---------------------------------------------------------------------------

CRITIC_SYSTEM_PROMPT = """Eres el Revisor de Calidad (N13) del sistema MEPIA.
Tu único trabajo es evaluar si el borrador de auditoría generado por el Consultor (N11)
es matemáticamente correcto y mantiene el tono adecuado para el dueño del negocio.

Recibirás dos bloques de información:
  1. DATOS_CRUDOS: El EnrichedAuditPayload con los números reales del negocio.
  2. BORRADOR: El DraftReport generado por N11 para evaluar.

═══════════════════════════════════════════════════════
TEST 1 — VERIFICACIÓN MATEMÁTICA (Anti-Alucinación)
═══════════════════════════════════════════════════════
Extrae CADA cifra, porcentaje, monto en MXN o cantidad mencionada en:
  - BORRADOR.executive_summary
  - BORRADOR.operational_narrative
  - BORRADOR.pragmatic_actions[*].action

Para cada cifra extraída, búscala en DATOS_CRUDOS. Fuentes válidas:
  - forensic_report.anomalies[*].quantified_impact
  - forensic_report.anomalies[*].data_points
  - audit_insights[*].raw_result
  - time_series.periodos[*] (ingresos, gastos_variable, gastos_fijos, etc.)

REGLA: Si una cifra aparece en el borrador pero NO existe en ninguna fuente de DATOS_CRUDOS,
o si el valor difiere en más de un 5% del valor real, incluye ALUCINACION_MATEMATICA en tipos_falla.

En warning_especifico describe: qué cifra está mal, qué dice el borrador, qué dicen los datos.
Ejemplo: "MATEMÁTICA: El borrador menciona '-$1,500 MXN' pero forensic_report dice '-320 MXN'."

EXCEPCIÓN: Las equivalencias físicas (ej. "3 kilos de café") son estimaciones aceptables
si están basadas en datos reales del borrador. No las penalices si son razonables.

═══════════════════════════════════════════════════════
TEST 2 — VERIFICACIÓN DE IDENTIDAD (Anti-Robot)
═══════════════════════════════════════════════════════
El borrador DEBE sonar como un operador de piso con 15 años de experiencia en cafeterías,
hablando directamente al dueño. NO como un consultor corporativo.

Incluye DESVIACION_IDENTIDAD en tipos_falla si detectas:
  - Palabras prohibidas: "optimizar", "sinergia", "KPIs", "roadmap", "stakeholders",
    "apalancar", "deep dive", "best practices", "implementar estrategias", "maximizar"
  - Tono distante, frío o genérico que no menciona realidades físicas del negocio
  - Recomendaciones que contradicen la brand_identity del negocio (si está disponible)
  - Frases que suenan a plantilla corporativa sin contexto específico del negocio

En warning_especifico indica: qué frase o sección falla y cómo debería reescribirse.
Ejemplo: "IDENTIDAD: La frase 'optimizar el flujo de caja' debe reescribirse como
'cuadrar la caja antes de cerrar el turno de la tarde'."

IMPORTANTE: Si detectas AMBAS fallas, incluye ambas en tipos_falla y describe
ambos problemas en warning_especifico, separados claramente.

═══════════════════════════════════════════════════════
APROBACIÓN
═══════════════════════════════════════════════════════
Si el borrador pasa AMBOS tests:
  - aprobado: true
  - tipos_falla: ["NINGUNA"]
  - warning_especifico: null
  - insight_para_memoria: Redacta un resumen de EXACTAMENTE 2 líneas que capture
    la conclusión principal del reporte. Será guardado como memoria del negocio.
    Ejemplo: "Semana del 15 ene: margen cayó 10% por falla de máquina de espresso.
    Acción tomada: mantenimiento preventivo programado para el 20 ene."

═══════════════════════════════════════════════════════
FORMATO DE SALIDA OBLIGATORIO
═══════════════════════════════════════════════════════
Responde ÚNICAMENTE con un JSON válido con esta estructura exacta:
{
  "aprobado": true | false,
  "tipos_falla": ["ALUCINACION_MATEMATICA"] | ["DESVIACION_IDENTIDAD"] | ["ALUCINACION_MATEMATICA", "DESVIACION_IDENTIDAD"] | ["NINGUNA"],
  "warning_especifico": "string describiendo TODAS las fallas, o null",
  "insight_para_memoria": "string de 2 líneas o null"
}
No incluyas texto fuera del JSON. No uses markdown dentro del JSON.
"""


# ---------------------------------------------------------------------------
# Factory — única fuente de verdad del nodo N13
# ---------------------------------------------------------------------------


def make_n13_node(memory_service=None):
    """
    Factory que retorna el nodo N13 con el MemoryService inyectado.

    El LLM se instancia aquí, fuera de la función interna, para que se
    reutilice en los reintentos del loop sin crear nuevas conexiones HTTP.

    Uso en el grafo:
        graph.add_node("n13_revisor", make_n13_node(memory_service))

    Args:
        memory_service: Instancia de MemoryService inyectada por el orquestador.
                        Puede ser None en tests unitarios.

    Returns:
        Función async compatible con LangGraph.
    """
    # ── LLM instanciado una sola vez — reutilizado en todos los reintentos ────
    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0,        # Determinismo máximo para el Critic
        request_timeout=30,   # Evita bloqueos indefinidos por lentitud de API
    )
    structured_llm = llm.with_structured_output(CriticVerdict)

    async def _node(state: Layer3State) -> Dict[str, Any]:
        """
        Lógica principal del nodo N13.

        Lee el DraftReport del estado, lo evalúa contra el EnrichedAuditPayload
        y retorna las actualizaciones de estado para el grafo.

        Returns:
            dict con las claves del estado que deben actualizarse.
        """
        draft_report: Dict[str, Any] = state.get("draft_report") or {}
        enriched_payload: Dict[str, Any] = state.get("enriched_payload") or {}
        intentos_actuales: int = state.get("intentos_critico", 0)
        historial_actual: List[str] = list(state.get("historial_feedback") or [])
        audit_results_actual: List[Dict[str, Any]] = list(state.get("audit_results") or [])

        # ── Construir el mensaje humano con truncamiento de periodos ──────────
        human_content = _build_human_message(
            draft_report=draft_report,
            enriched_payload=enriched_payload,
        )

        messages = [
            SystemMessage(content=CRITIC_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ]

        # ── Llamar al LLM con manejo de errores ───────────────────────────────
        try:
            verdict: CriticVerdict = await structured_llm.ainvoke(messages)
        except Exception as exc:
            # Fallback: el Critic falló — aprobar con advertencia para no bloquear el pipeline
            error_msg = f"N13 Critic falló por error de LLM: {type(exc).__name__}: {exc}"
            draft_report_con_error = _append_warning_text(
                draft_report=draft_report,
                warning_text=(
                    f"\n\n---\n"
                    f"⚠️ AVISO DEL SISTEMA: La revisión automática de calidad no pudo completarse "
                    f"({type(exc).__name__}). Se recomienda revisión manual de este reporte."
                ),
            )
            audit_entry = _build_audit_entry(
                intento=intentos_actuales,
                aprobado=False,
                tipos_falla=["CRITIC_ERROR"],
                warning=error_msg,
                insight=None,
            )
            return {
                "draft_report": draft_report_con_error,
                "draft_status": "approved_with_warning",
                "feedback_critico": error_msg,
                "historial_feedback": historial_actual + [error_msg],
                "tipos_falla_critico": ["CRITIC_ERROR"],
                "audit_results": audit_results_actual + [audit_entry],
            }

        # ── Construir entrada de auditoría para este veredicto ────────────────
        tipos_falla_str = [f.value for f in verdict.tipos_falla]
        audit_entry = _build_audit_entry(
            intento=intentos_actuales,
            aprobado=verdict.aprobado,
            tipos_falla=tipos_falla_str,
            warning=verdict.warning_especifico,
            insight=verdict.insight_para_memoria,
        )

        # ── Ruta A: Aprobado ──────────────────────────────────────────────────
        if verdict.aprobado:
            # Guardar insight en memoria — await directo, parte del contrato del nodo
            if memory_service is not None:
                await _store_insight_in_memory(verdict, state, memory_service)

            return {
                "draft_status": "approved",
                "feedback_critico": None,
                "tipos_falla_critico": tipos_falla_str,
                "audit_results": audit_results_actual + [audit_entry],
            }

        # ── Rechazado — determinar ruta B o C ─────────────────────────────────
        nuevo_intento = intentos_actuales + 1
        nuevo_historial = historial_actual + [verdict.warning_especifico or ""]

        if intentos_actuales < MAX_INTENTOS:
            # ── Ruta B: Reintento — vuelve a N11 con feedback ─────────────────
            return {
                "intentos_critico": nuevo_intento,
                "feedback_critico": verdict.warning_especifico,
                "historial_feedback": nuevo_historial,
                "tipos_falla_critico": tipos_falla_str,
                "draft_status": "rejected",
                "audit_results": audit_results_actual + [audit_entry],
            }
        else:
            # ── Ruta C: Cortafuegos — aprueba con advertencia explícita ───────
            # El texto de advertencia incluye el warning_especifico del último rechazo
            # para que el dueño sepa exactamente qué revisar manualmente.
            warning_text = (
                f"\n\n---\n"
                f"⚠️ AVISO DEL SISTEMA: Este reporte fue generado con advertencias de calidad "
                f"no resueltas tras {nuevo_intento} intentos de corrección automática. "
                f"Problema detectado: {verdict.warning_especifico or 'No especificado'}. "
                f"Se recomienda revisión manual antes de tomar decisiones basadas en este análisis."
            )
            draft_report_modificado = _append_warning_text(draft_report, warning_text)

            return {
                "draft_report": draft_report_modificado,
                "draft_status": "approved_with_warning",
                "feedback_critico": verdict.warning_especifico,
                "historial_feedback": nuevo_historial,
                "tipos_falla_critico": tipos_falla_str,
                "audit_results": audit_results_actual + [audit_entry],
            }

    return _node


# ---------------------------------------------------------------------------
# Conditional Edge — Función de ruteo post-N13
# ---------------------------------------------------------------------------


def n13_conditional_edge(state: Layer3State) -> str:
    """
    Función de ruteo del grafo LangGraph después de N13.

    Retorna el nombre del siguiente nodo según el draft_status:
      - "approved"              → "n14_informe_final"
      - "approved_with_warning" → "n14_informe_final"
      - "rejected"              → "n11_consultor"  (loop de reintento)

    Registro en el grafo:
        graph.add_conditional_edges("n13_revisor", n13_conditional_edge)
    """
    draft_status = state.get("draft_status", "pending")

    if draft_status in ("approved", "approved_with_warning"):
        return "n14_informe_final"

    if draft_status == "rejected":
        return "n11_consultor"

    # Fallback defensivo — estado inesperado, no bloquear el pipeline
    return "n14_informe_final"


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------


async def _store_insight_in_memory(
    verdict: CriticVerdict,
    state: Layer3State,
    memory_service: Any,
) -> None:
    """
    Guarda el insight_para_memoria en mepia_memory vía MemoryService.
    Solo se llama cuando aprobado == True y memory_service no es None.

    El MemoryChunk usa node_origin="N13" según el contrato de MemoryChunk
    definido en _glossary.md y mem_memory_layer.md.
    """
    if not verdict.insight_para_memoria:
        return

    # MemoryChunk se importa desde utils — el módulo debe existir antes de producción
    from utils.memory_service import MemoryChunk  # type: ignore[import]

    chunk = MemoryChunk(
        business_id=state["business_id"],
        source_audit_run_id=state["layer3_run_id"],
        node_origin="N13",
        date=state["date"],
        content=verdict.insight_para_memoria,
        archetype=state.get("archetype"),
        quality_approved=True,
    )

    await memory_service.store_memory(chunk)


def _build_human_message(
    draft_report: Dict[str, Any],
    enriched_payload: Dict[str, Any],
) -> str:
    """
    Construye el mensaje humano para el LLM del Critic.

    Incluye solo los campos relevantes del EnrichedAuditPayload.
    Trunca time_series.periodos a los últimos MAX_PERIODOS registros
    para evitar desbordar el contexto del LLM con series temporales largas
    (modo 'long' puede tener hasta 365 registros diarios).
    """
    time_series_raw: Dict[str, Any] = dict(enriched_payload.get("time_series") or {})
    periodos = time_series_raw.get("periodos") or []

    if len(periodos) > MAX_PERIODOS:
        time_series_raw["periodos"] = periodos[-MAX_PERIODOS:]
        time_series_raw["_periodos_truncados"] = (
            f"Mostrando últimos {MAX_PERIODOS} de {len(periodos)} registros"
        )

    datos_crudos = {
        "forensic_report": enriched_payload.get("forensic_report", {}),
        "audit_insights": enriched_payload.get("audit_insights", []),
        "time_series": time_series_raw,
        "brand_identity": enriched_payload.get("brand_identity", {}),
    }

    return (
        "DATOS_CRUDOS (fuente de verdad — inmutable):\n"
        f"{json.dumps(datos_crudos, ensure_ascii=False, indent=2)}\n\n"
        "BORRADOR (a evaluar):\n"
        f"{json.dumps(draft_report, ensure_ascii=False, indent=2)}"
    )


def _append_warning_text(draft_report: Dict[str, Any], warning_text: str) -> Dict[str, Any]:
    """
    Agrega un texto de advertencia al final de operational_narrative.

    Retorna una copia modificada del draft_report — no muta el original.
    Usado tanto en el cortafuegos (Ruta C) como en el fallback de error del LLM.
    """
    modified = dict(draft_report)
    narrative = modified.get("operational_narrative", "")
    modified["operational_narrative"] = narrative + warning_text
    return modified


def _build_audit_entry(
    intento: int,
    aprobado: bool,
    tipos_falla: List[str],
    warning: Optional[str],
    insight: Optional[str],
) -> Dict[str, Any]:
    """
    Construye la entrada de auditoría para audit_results.

    Cada ejecución de N13 genera una entrada que se acumula en el estado,
    permitiendo trazabilidad completa del loop de calidad.
    """
    return {
        "node_id": "N13",
        "intento": intento,
        "aprobado": aprobado,
        "tipos_falla": tipos_falla,
        "warning_especifico": warning,
        "insight_para_memoria": insight,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
