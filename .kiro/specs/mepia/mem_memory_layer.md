# MEM — Capa de Memoria (Transversal)

**Capa:** Transversal | **Anterior:** todos los nodos | **Siguiente:** todos los nodos
**Archivos relacionados:** `db_schema.md`, `_glossary.md`, `_index.md`

## Responsabilidad

Persistencia de contexto y recuperación semántica (RAG) para todos los agentes de MEPIA.
Dos sistemas de memoria coexisten con propósitos estrictamente distintos:

| Sistema             | Tecnología              | Rol                  | Alias    |
|---------------------|-------------------------|----------------------|----------|
| `mepia_vector_store`| Supabase + pgvector     | Datos duros pasados  | "Ledger" → NO. Ver nota abajo |
| Engram              | Binario Go (local)      | Patrones abstractos  | "Brain"  |

> Nota: `audit_results` es el Ledger (fuente de verdad estructurada para dashboard/frontend).
> `mepia_vector_store` es el Brain semántico — solo para LangChain RAG, no para el frontend.

---

## Input / Output

- **Input (read):** `query: str`, `business_id: UUID`, `limit: int = 5`
- **Output:** `context: str` — string consolidado listo para inyectar en system prompt
- **Input (write):** `MemoryChunk` — solo desde N12 o N13 al final de Layer 3

---

## User Stories

- Como agente, quiero recuperar auditorías pasadas del mismo negocio para contextualizar alertas.
- Como agente, quiero recuperar patrones abstractos (preferencias, reglas no escritas) desde Engram.
- Como N12/N13, quiero persistir el reporte final consolidado como memoria de largo plazo.
- Como infraestructura, quiero saber exactamente qué binario compilar y cómo configurar el MCP.

---

## Acceptance Criteria

- WHEN `get_context(query, business_id)` es llamado THEN retorna string con contexto de pgvector + Engram
- WHEN un nodo de Layer 1 o Layer 2 llama a memoria THEN solo puede leer, nunca escribir
- WHEN N12 o N13 consolida el reporte final THEN escribe un `MemoryChunk` en pgvector y en Engram
- WHEN Engram no está disponible THEN `get_context` retorna solo el resultado de pgvector (graceful degradation)
- WHEN se escribe en `mepia_vector_store` THEN el embedding usa `text-embedding-3-small` (1536 dims)

---

## Infraestructura — Engram (MCP Bridge)

Engram es un repositorio local desarrollado en **Go (Golang)**. No es un paquete Python.

### Requisito de compilación
El binario `engram` debe estar compilado y disponible en el PATH del servidor antes de iniciar MEPIA.
```bash
# En el repo de Engram:
go build -o engram .
# Mover al PATH o referenciar ruta absoluta en mcp.json
```

### Configuración MCP (`.kiro/settings/mcp.json`)
```json
{
  "mcpServers": {
    "engram": {
      "command": "engram",
      "args": ["mcp"],
      "disabled": false,
      "autoApprove": ["search", "store"]
    }
  }
}
```

### Herramientas MCP expuestas por Engram
| Herramienta | Permiso en MEPIA         | Quién la usa        |
|-------------|--------------------------|---------------------|
| `search`    | read — todos los agentes | `MemoryService`     |
| `store`     | write — solo N12 / N13   | `MemoryService`     |

---

## Implementación — `utils/memory_service.py`

Wrapper Python que abstrae ambos sistemas de memoria.

```python
class MemoryService:
    async def get_context(self, query: str, business_id: UUID, limit: int = 5) -> str:
        # 1. Busca en Supabase pgvector (datos duros pasados del mismo business_id)
        # 2. Busca en Engram via MCP tool "search" (patrones abstractos)
        # 3. Retorna string consolidado para el prompt

    async def store_memory(self, chunk: MemoryChunk) -> None:
        # Solo llamado por N12 o N13
        # 1. Genera embedding con text-embedding-3-small
        # 2. Inserta en mepia_vector_store
        # 3. Llama MCP tool "store" de Engram
```

### Modificación en `BaseAgent`
```python
class BaseAgent:
    def __init__(self, memory: MemoryService):
        self.memory = memory  # inyectado — read-only para Layer 1 y 2

    async def get_context(self, query: str, limit: int = 5) -> str:
        return await self.memory.get_context(query, self.business_id, limit)
```

---

## Regla de permisos de escritura

| Nodo / Capa          | `mepia_vector_store` | Engram (`store`) |
|----------------------|----------------------|------------------|
| S1, S2, S3, S4       | ❌ read-only          | ❌ read-only      |
| N07, N08, N09, N10   | ❌ read-only          | ❌ read-only      |
| N11 (Consultor)      | ❌ read-only          | ❌ read-only      |
| N12 (Phrase Expander)| ✅ write              | ✅ write          |
| N13 (Quality Reviewer)| ✅ write (si consolida) | ✅ write       |

Rationale: evitar saturar la memoria con alertas crudas. Solo el reporte final validado se persiste.

---

## Edge Cases

- Engram binario no encontrado → log warning, continuar solo con pgvector
- Embedding API de OpenAI falla → reintentar 1 vez, luego marcar chunk como `pending_embed`
- `business_id` sin historial en pgvector → retornar string vacío, no error
- N12 y N13 ambos intentan escribir → N13 tiene prioridad si `quality_approved: true`

---

## Archivos relacionados de este nodo
- `db_schema.md` — tabla `mepia_vector_store` + índice ivfflat
- `_glossary.md` — contratos `MemoryChunk`, componentes `Engram` y `MemoryService`
