"""
Layer 3 — Grafo LangGraph (StateGraph)
Único archivo autorizado para instanciar StateGraph de Layer 3.
Flujo: N10 → N11 → N13 → (conditional) → N14 o N11
Spec: .kiro/specs/mepia/layer3_graph.md
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END

from agents.layer3_state import Layer3State
from agents.context_builder import n10_context_builder_node
from agents.core_auditor import n11_consultor_node
from agents.n13_revisor import make_n13_node, n13_conditional_edge
from agents.n14_informe_final import n14_informe_final_node
from utils.memory_service import MemoryService


def build_layer3_graph(memory_service: MemoryService):
    """
    Construye y compila el grafo LangGraph de Layer 3.

    Args:
        memory_service: Instancia de MemoryService inyectada por el endpoint.
                        N13 la usa para store_memory() al aprobar.

    Returns:
        Grafo compilado listo para .invoke() o .ainvoke().

    Reglas de desacoplamiento (spec layer3_graph.md):
        - Solo este archivo instancia StateGraph(Layer3State)
        - api/main.py solo importa layer3_app y llama .ainvoke()
        - MemoryService se inyecta aquí, no se instancia en los nodos
    """
    graph = StateGraph(Layer3State)

    # ── Registrar nodos ───────────────────────────────────────────────────────
    graph.add_node("n10_context_builder", n10_context_builder_node)
    graph.add_node("n11_consultor", n11_consultor_node)
    graph.add_node("n13_revisor", make_n13_node(memory_service))
    graph.add_node("n14_informe_final", n14_informe_final_node)

    # ── Flujo secuencial ──────────────────────────────────────────────────────
    graph.set_entry_point("n10_context_builder")
    graph.add_edge("n10_context_builder", "n11_consultor")
    graph.add_edge("n11_consultor", "n13_revisor")

    # ── Conditional edge post-N13 (loop o avance) ─────────────────────────────
    # n13_conditional_edge retorna:
    #   "n11_consultor"     → rechazado, reintento (intentos_critico < 2)
    #   "n14_informe_final" → aprobado o cortafuegos (intentos_critico >= 2)
    graph.add_conditional_edges(
        "n13_revisor",
        n13_conditional_edge,
        {
            "n11_consultor": "n11_consultor",
            "n14_informe_final": "n14_informe_final",
        },
    )

    graph.add_edge("n14_informe_final", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Instancia exportada
# Se inicializa en startup de FastAPI con MemoryService real.
# Ver: api/main.py → startup_event → layer3_app = build_layer3_graph(memory_service)
# ---------------------------------------------------------------------------
# layer3_app se asigna en api/main.py durante startup — no aquí,
# porque MemoryService requiere el cliente Supabase que se crea en runtime.
