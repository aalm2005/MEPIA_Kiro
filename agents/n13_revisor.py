"""
N13 — Revisor de Calidad (Critic & Enforcer)
LLM: gpt-4o, temperatura 0, structured output.
Patrón Actor-Critic con cortafuegos en intentos >= 2.
Spec: .kiro/specs/mepia/n13_revisor.md
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, List, Optional
from uuid import uuid4

from pydantic import BaseModel

from agents.layer3_state import Layer3State

# Cortafuegos: máximo de intentos antes de forzar approved_with_warning
MAX_INTENTOS = 2

_SYSTEM_WARNING_TEXT = (
    "\n\n> ⚠️ ADVERTENCIA DE CALIDAD: Este reporte fue aprobado con observaciones "
    "no resueltas tras múltiples revisiones. Revisar manualmente antes de tomar decisiones."
)

# Palabras prohibidas para test de identidad
_PALABRAS_PROHIBIDAS = [
    "optimizar recursos", "sinergia", "kpis", "roadmap", "stakeholders",
    "apalancar", "deep dive", "best practices", "optimización", "sinergias",
]


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------

class TipoFalla(str, Enum):
    ALUCINACION_MATEMATICA = "ALUCINACION_MATEMATICA"
    DESVIACION_IDENTIDAD = "DESVIACION_IDENTIDAD"
    NINGUNA = "NINGUNA"


class CriticVerdict(BaseModel):
    aprobado: bool
    tipos_falla: List[TipoFalla]
    warning_especifico: Optional[str] = None
    insight_para_memoria: Optional[str] = None


# ---------------------------------------------------------------------------
# Schema para structured output del LLM
# ---------------------------------------------------------------------------

_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "aprobado": {"type": "boolean"},
        "tipos_falla": {
            "type": "array",
            "items": {"type": "string", "enum": ["ALUCINACION_MATEMATICA", "DESVIACION_IDENTIDAD", "NINGUNA"]},
        },
        "warning_especifico": {"type": ["string", "null"]},
        "insight_para_memoria": {"type": ["string", "null"]},
    },
    "required": ["aprobado", "tipos_falla", "warning_especifico", "insight_para_memoria"],
    "additionalProperties": False,
}

_SYSTEM_PROMPT_N13 = """Eres el Revisor de Calidad (N13) del sistema MEPIA.
Tu trabajo es evaluar el borrador de auditoría generado por N11 en dos dimensiones:

1. TEST MATEMÁTICO (ALUCINACION_MATEMATICA):
   - Extrae TODAS las cifras numéricas del operational_narrative y executive_summary.
   - Verifica que cada cifra exista en forensic_report, audit_insights o time_series.
   - Si encuentras UNA cifra que no existe en los datos → ALUCINACION_MATEMATICA.

2. TEST DE IDENTIDAD (DESVIACION_IDENTIDAD):
   - Verifica que el texto NO use lenguaje corporativo prohibido.
   - Palabras prohibidas: "optimizar recursos", "sinergia", "KPIs", "roadmap",
     "stakeholders", "apalancar", "deep dive", "best practices".
   - Si encuentras UNA palabra prohibida → DESVIACION_IDENTIDAD.

REGLAS:
- Si apruebas: tipos_falla = ["NINGUNA"], warning_especifico = null,
  insight_para_memoria = resumen de 2 líneas del reporte para memoria histórica.
- Si rechazas: tipos_falla = lista de fallas encontradas, warning_especifico = descripción
  detallada de TODAS las fallas para que N11 las corrija, insight_para_memoria = null.
- Puedes detectar múltiples fallas simultáneas.
- Responde ÚNICAMENTE con el JSON estructurado."""


# ---------------------------------------------------------------------------
# Factory de nodo (recibe MemoryService inyectado)
# ---------------------------------------------------------------------------

def make_n13_node(memory_service: Any) -> Callable:
    """
    Crea el nodo N13 con MemoryService inyectado.
    Spec: layer3_graph.md §build_layer3_graph
    """
    def n13_revisor_node(state: Layer3State) -> dict:
        return _run_n13(state, memory_service)
    return n13_revisor_node


def _run_n13(state: Layer3State, memory_service: Any) -> dict:
    """
    Ejecuta la revisión del DraftReport.
    Actualiza draft_status, feedback_critico, intentos_critico en el estado.
    """
    db = state.get("_db")
    layer3_run_id = state["layer3_run_id"]
    draft_report = state.get("draft_report") or {}
    enriched_payload = state.get("enriched_payload") or {}
    intentos = state.get("intentos_critico", 0)
    historial = list(state.get("historial_feedback") or [])

    # --- Cortafuegos (P4): si ya llegamos al límite → approved_with_warning ---
    if intentos >= MAX_INTENTOS:
        narrative = draft_report.get("operational_narrative", "")
        draft_report_updated = {
            **draft_report,
            "operational_narrative": narrative + _SYSTEM_WARNING_TEXT,
        }
        verdict_entry = {
            "intento": intentos,
            "resultado": "approved_with_warning_cortafuegos",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _persist_n13(db, layer3_run_id, state["business_id"], state["date"], verdict_entry)
        return {
            "draft_report": draft_report_updated,
            "draft_status": "approved_with_warning",
            "audit_results": list(state.get("audit_results") or []) + [verdict_entry],
        }

    # --- Llamar al LLM para evaluar ---
    verdict = _evaluate_with_llm(draft_report, enriched_payload)

    # Entrada de auditoría (P7: siempre 1 entrada por ejecución)
    verdict_entry = {
        "intento": intentos,
        "resultado": "approved" if verdict.aprobado else "rejected",
        "tipos_falla": [f.value for f in verdict.tipos_falla],
        "warning": verdict.warning_especifico,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _persist_n13(db, layer3_run_id, state["business_id"], state["date"], verdict_entry)

    new_audit_results = list(state.get("audit_results") or []) + [verdict_entry]

    if verdict.aprobado:
        # P1: aprobado → tipos_falla == ["NINGUNA"]
        # P3: insight_para_memoria nunca null cuando aprobado
        # Guardar en memoria (await directo — parte del contrato)
        if verdict.insight_para_memoria and memory_service:
            _store_memory_sync(memory_service, state, verdict.insight_para_memoria, layer3_run_id)

        return {
            "draft_status": "approved",
            "feedback_critico": None,
            "tipos_falla_critico": ["NINGUNA"],
            "audit_results": new_audit_results,
        }
    else:
        # Rechazado: incrementar contador y guardar feedback
        new_intentos = intentos + 1
        new_historial = historial + [verdict.warning_especifico or ""]

        # Si con este rechazo llegamos al límite → approved_with_warning
        if new_intentos >= MAX_INTENTOS:
            narrative = draft_report.get("operational_narrative", "")
            draft_report_updated = {
                **draft_report,
                "operational_narrative": narrative + _SYSTEM_WARNING_TEXT,
            }
            return {
                "draft_report": draft_report_updated,
                "draft_status": "approved_with_warning",
                "intentos_critico": new_intentos,
                "feedback_critico": verdict.warning_especifico,
                "historial_feedback": new_historial,
                "tipos_falla_critico": [f.value for f in verdict.tipos_falla],
                "audit_results": new_audit_results,
            }

        return {
            "draft_status": "rejected",
            "intentos_critico": new_intentos,
            "feedback_critico": verdict.warning_especifico,
            "historial_feedback": new_historial,
            "tipos_falla_critico": [f.value for f in verdict.tipos_falla],
            "audit_results": new_audit_results,
        }


def _evaluate_with_llm(draft_report: dict, enriched_payload: dict) -> CriticVerdict:
    """Llama a gpt-4o con structured output para evaluar el DraftReport."""
    try:
        from openai import OpenAI

        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

        # Truncar time_series a 7 periodos para no saturar el contexto (P10)
        ts = (enriched_payload.get("time_series") or {})
        periodos = (ts.get("periodos") or [])[:7]
        ts_truncated = {**ts, "periodos": periodos}

        user_content = json.dumps({
            "draft_report": draft_report,
            "datos_referencia": {
                "forensic_report": enriched_payload.get("forensic_report"),
                "audit_insights": enriched_payload.get("audit_insights"),
                "time_series": ts_truncated,
            },
        }, ensure_ascii=False, default=str)

        response = client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "critic_verdict",
                    "strict": True,
                    "schema": _VERDICT_SCHEMA,
                },
            },
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT_N13},
                {"role": "user", "content": user_content},
            ],
        )

        raw = json.loads(response.choices[0].message.content)
        tipos = [TipoFalla(t) for t in raw.get("tipos_falla", ["NINGUNA"])]

        return CriticVerdict(
            aprobado=raw["aprobado"],
            tipos_falla=tipos,
            warning_especifico=raw.get("warning_especifico"),
            insight_para_memoria=raw.get("insight_para_memoria"),
        )

    except Exception as exc:
        # P9: LLM error → approved_with_warning, pipeline no se bloquea
        return CriticVerdict(
            aprobado=True,
            tipos_falla=[TipoFalla.NINGUNA],
            warning_especifico=None,
            insight_para_memoria=f"Revisión automática — LLM no disponible: {exc}",
        )


def _store_memory_sync(
    memory_service: Any,
    state: Layer3State,
    insight: str,
    layer3_run_id: str,
) -> None:
    """Guarda insight en mepia_memory de forma síncrona (P6)."""
    try:
        import asyncio
        from utils.memory_service import MemoryChunk

        chunk = MemoryChunk(
            business_id=state["business_id"],
            source_audit_run_id=layer3_run_id,
            node_origin="N13",
            date=state["date"],
            content=insight,
            archetype=state.get("archetype"),
            quality_approved=True,
        )
        asyncio.get_event_loop().run_until_complete(memory_service.store_memory(chunk))
    except Exception:
        pass  # Si falla → approved_with_warning (ver spec)


def _persist_n13(
    db: Any,
    layer3_run_id: str,
    business_id: str,
    date: str,
    verdict_entry: dict,
) -> None:
    """Persiste entrada de auditoría de N13 en audit_results."""
    if db is None:
        return
    try:
        db.table("audit_results").insert(
            {
                "id": str(uuid4()),
                "business_id": business_id,
                "date": date,
                "pipeline_layer": "loop",
                "node_id": "N13",
                "node_status": verdict_entry.get("resultado", "unknown"),
                "result_data": verdict_entry,
                "created_at": verdict_entry.get("timestamp"),
            }
        ).execute()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Conditional edge para el grafo LangGraph
# ---------------------------------------------------------------------------

def n13_conditional_edge(state: Layer3State) -> str:
    """
    Determina el siguiente nodo tras N13.
    Retorna "n11_consultor" o "n14_informe_final".
    Spec: layer3_graph.md §Conditional edge
    """
    draft_status = state.get("draft_status", "pending")

    if draft_status in ("approved", "approved_with_warning"):
        return "n14_informe_final"

    # rejected → volver a N11
    return "n11_consultor"
