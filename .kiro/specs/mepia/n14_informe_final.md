# N14 — Informe Final

**Capa:** Layer 3 — Nodo 4 (terminal) | **Anterior:** N13 Revisor | **Siguiente:** —
**Archivo de implementación:** `agents/n14_informe_final.py`
**Tipo:** Determinista — sin llamadas a LLM. Empaquetador puro.
**Archivos relacionados:** `n13_revisor.md`, `agents/layer3_state.py`, `_glossary.md`

---

## Input / Output

**Input:** `Layer3State` con `draft_report`, `draft_status`, `audit_results`
**Output:** Actualización de estado: `final_response` (dict) + entrada en `audit_results`

---

## Responsabilidad

Nodo terminal del grafo Layer 3. No llama a ningún LLM. Extrae del estado los
artefactos validados por N13 y los empaqueta en `final_response`, el contrato
que consume el frontend/cliente.

---

## Contrato de Salida — `FinalResponse`

```python
{
  "report_markdown": str,          # contenido de draft_report
  "status": str,                   # contenido de draft_status
  "has_warnings": bool,            # True si draft_status == "approved_with_warning"
  "metadata": {
    "generated_at": str,           # timestamp UTC en formato ISO-8601
    "audit_trail": List[Dict]      # historial completo de audit_results
  }
}
```

---

## Actualización de `Layer3State`

```python
{
  "final_response": FinalResponse,
  "audit_results": audit_results + [entrada_n14]  # append del paso N14
}
```

La entrada de N14 en `audit_results` sigue el mismo patrón que N13:
```python
{
  "node": "N14",
  "status": "completed",
  "timestamp": "<ISO UTC>",
  "final_status": draft_status
}
```

---

## Lógica de `has_warnings`

```python
has_warnings = (draft_status == "approved_with_warning")
```

Valor `True` solo cuando el cortafuegos de N13 se activó (`intentos_critico >= 2`).
El frontend usa este flag para mostrar un banner de advertencia al dueño.

---

## Ensamblaje del Grafo (StateGraph)

```python
from langgraph.graph import StateGraph, END

graph = StateGraph(Layer3State)

graph.add_node("n11_consultor",    n11_node)
graph.add_node("n13_revisor",      n13_node)
graph.add_node("n14_informe_final", n14_node)

graph.set_entry_point("n11_consultor")

graph.add_edge("n11_consultor", "n13_revisor")

graph.add_conditional_edges(
    "n13_revisor",
    route_n13,          # función de enrutamiento — lee draft_status del estado
    {
        "approved":              "n14_informe_final",   # Ruta A
        "rejected":              "n11_consultor",       # Ruta B — reintento
        "approved_with_warning": "n14_informe_final",   # Ruta C — cortafuegos
    }
)

graph.add_edge("n14_informe_final", END)

compiled_graph = graph.compile()
```

---

## Acceptance Criteria

- WHEN N14 ejecuta → `final_response["report_markdown"]` == `draft_report` exacto
- WHEN `draft_status == "approved_with_warning"` → `has_warnings == True`
- WHEN `draft_status == "approved"` → `has_warnings == False`
- WHEN N14 ejecuta → `final_response["metadata"]["generated_at"]` es timestamp UTC válido
- WHEN N14 ejecuta → `final_response["metadata"]["audit_trail"]` contiene todos los `audit_results` previos + entrada de N14
- WHEN N14 ejecuta → exactamente 1 entrada nueva en `audit_results` con `node == "N14"`
- WHEN N14 ejecuta → ninguna llamada a LLM ni operación de red

## Correctness Properties (PBT)

| ID | Propiedad |
|----|-----------|
| P1 | `final_response["report_markdown"]` == `state["draft_report"]` siempre |
| P2 | `has_warnings == True` ↔ `draft_status == "approved_with_warning"` |
| P3 | `audit_trail` contiene exactamente `len(audit_results_previos) + 1` entradas |
| P4 | `generated_at` es ISO-8601 UTC válido y posterior a `draft_report.generated_at` |
| P5 | N14 nunca modifica `draft_report`, `draft_status` ni ningún campo de control del loop |

---

## Archivos relacionados de este nodo
- `agents/n14_informe_final.py` — implementación completa
- `agents/layer3_state.py` — definición del `Layer3State` (agregar `final_response`)
- `n13_revisor.md` — origen de `draft_status` y lógica de enrutamiento
- `_glossary.md` — contratos `DraftReport`, `FinalResponse`, `Layer3State`
