# MEM — Capa de Memoria (Transversal)

**Capa:** Transversal | **Anterior:** todos los nodos | **Siguiente:** todos los nodos
**Archivos relacionados:** `db_schema.md`, `_glossary.md`, `_index.md`

## Responsabilidad

Persistencia de contexto y recuperación semántica (RAG) para todos los agentes de MEPIA.
Dos sistemas de memoria coexisten con propósitos estrictamente distintos:

| Sistema        | Tecnología          | Rol                                        |
|----------------|---------------------|--------------------------------------------|
| `mepia_memory` | Supabase + pgvector | Fuente de Verdad — datos duros + semántica |
| Engram         | Binario Go (local)  | Patrones abstractos de largo plazo         |

> `audit_results` = Ledger estructurado para dashboard/frontend.
> `mepia_memory` = Brain semántico para LangChain RAG. Postgres es la Single Source of Truth.
> Engram es secundario: si falla, reconstruye su estado leyendo `mepia_memory` al reiniciar.

## Decisión de Motor de Embeddings (V1 — Fijo)

| Campo | Valor |
|-------|-------|
| **Modelo** | `text-embedding-3-small` |
| **Proveedor** | OpenAI |
| **Dimensiones** | **1536** (fijo — no modificable sin migración completa de la tabla) |
| **Justificación** | Balance óptimo entre calidad semántica y costo. Dimensión estándar compatible con pgvector HNSW. Menor latencia que `text-embedding-3-large` (3072 dims) sin sacrificar precisión para el dominio de auditoría financiera. |
| **Variable de entorno requerida** | `OPENAI_API_KEY` |
| **Impacto en schema** | La columna `mepia_memory.embedding` es `vector(1536)`. Cambiar de modelo requiere recrear la tabla y regenerar todos los embeddings existentes. |

---

## Input / Output

- **Input (read):** `query: str`, `business_id: UUID`, `limit: int = 5`
- **Output:** `context: str` — string consolidado listo para inyectar en system prompt
- **Input (write):** `MemoryChunk` — solo desde N12 o N13 al final de Layer 3, o desde el proceso de onboarding (`node_origin: "onboarding"`)

---

## User Stories

- Como agente de Layer 1/2, quiero recuperar contexto semántico de auditorías pasadas (read-only).
- Como agente de Layer 3 (N12/N13), quiero persistir el reporte final consolidado como memoria.
- Como infraestructura, quiero que ningún chunk se pierda silenciosamente si la API de embeddings falla.
- Como sistema, quiero que recuerdos recientes tengan más peso en RAG sin borrar los históricos.

---

## Acceptance Criteria

- WHEN `get_context(query, business_id)` es llamado THEN retorna string con contexto de pgvector + Engram
- WHEN un nodo de Layer 1 o Layer 2 llama a memoria THEN solo tiene acceso a `search_memory` tool
- WHEN N12 o N13 consolida el reporte THEN tiene acceso a `search_memory` + `store_memory` tools
- WHEN la API de embeddings falla THEN el chunk queda en `status: "pending_embed"` — nunca se pierde
- WHEN Engram no está disponible THEN `get_context` retorna solo resultado de pgvector (graceful degradation)
- WHEN Engram reinicia THEN reconstruye su estado leyendo registros `status: "embedded"` de `mepia_memory`
- WHEN se guarda un chunk THEN se divide en fragmentos de ≤500 tokens con 50 tokens de solapamiento

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
      "autoApprove": []
    }
  }
}
```

> `autoApprove` vacío — ningún agente tiene acceso directo al MCP de Engram.
> Todo acceso pasa exclusivamente por `MemoryService` (Application Guard).

---

## Seguridad — Application Guard (MemoryService como proxy)

Los agentes **nunca** tienen acceso directo al cliente MCP ni a Supabase.
El enforcement de permisos ocurre en la capa de aplicación Python:

| Tool inyectada     | Layer 1 / 2 | Layer 3 (N12, N13) |
|--------------------|-------------|---------------------|
| `search_memory`    | ✅           | ✅                   |
| `store_memory`     | ❌           | ✅                   |

El orquestador inyecta solo las tools correspondientes al instanciar cada agente.
`MemoryService` actúa como proxy estricto — rechaza llamadas a `store_memory` si el agente no es Layer 3.

---

## Implementación — `utils/memory_service.py`

```python
class MemoryService:
    async def get_context(self, query: str, business_id: UUID, limit: int = 5) -> str:
        # 1. Busca en mepia_memory con Time-Weighted Retrieval
        # 2. Busca en Engram via MCP tool "search" (patrones abstractos)
        # 3. Retorna string consolidado para el prompt

    async def store_memory(self, chunk: MemoryChunk) -> None:
        # Llamado por N12, N13 (enforced por el orquestador) o proceso de onboarding
        # node_origin acepta: "N12" | "N13" | "onboarding"
        # source_audit_run_id es nullable — null para chunks de onboarding
        # 1. Divide content en chunks de 500 tokens / 50 solapamiento
        # 2. Inserta cada chunk en mepia_memory con status="pending_embed"
        # 3. FastAPI BackgroundTask genera embedding y actualiza status="embedded"
        # 4. BackgroundTask llama MCP tool "store" de Engram (best-effort)
```

### Modificación en `BaseAgent`
```python
class BaseAgent:
    def __init__(self, memory: MemoryService, tools: list[str]):
        self.memory = memory
        self._allowed_tools = tools  # ["search_memory"] o ["search_memory", "store_memory"]
```

---

## Pipeline de Chunking

Obligatorio antes de cualquier escritura en `mepia_memory`:

```
content (texto largo)
    → tokenizar (tiktoken, cl100k_base)
    → dividir en ventanas de 500 tokens con 50 de solapamiento
    → por cada chunk:
        metadata["chunk_index"] = i
        metadata["chunk_total"] = N
        INSERT INTO mepia_memory (business_id, content, metadata, status="pending_embed")
```

Prohibido guardar un reporte completo en un solo vector.

---

## Time-Weighted Retrieval

Sin TTL — el historial financiero nunca se borra. Los recuerdos recientes tienen más peso:

```
score_final = similarity_cosine * (1 / (1 + decay_factor * days_elapsed))
```

- `decay_factor` recomendado: `0.01` (recuerdo de 100 días = ~37% del peso original)
- `days_elapsed` = `now() - mepia_memory.created_at` en días
- Consulta explícita por fecha ignora el decay (acceso directo al historial)

---

## Worker Asíncrono de Embeddings (FastAPI BackgroundTask)

```
POST /memory/store  →  responde 202 inmediatamente
                    →  BackgroundTask: genera embedding → UPDATE status="embedded"
                    →  BackgroundTask: store en Engram (best-effort, no bloquea)
```

### Reconciliación al arranque
Endpoint admin o script de startup que procesa chunks huérfanos:
```
GET /admin/memory/reconcile
→ SELECT * FROM mepia_memory WHERE status IN ('pending_embed', 'failed')
→ Reintenta embedding para cada registro
→ Actualiza status="embedded" o status="failed" (tras 3 intentos)
```

Ejecutar en startup del servidor o como cron ligero (ej. cada 15 min).

---

## Sincronización Engram ↔ Postgres

Postgres (`mepia_memory`) es la **Single Source of Truth**.

- Engram es secundario y eventual.
- Si Engram falla o reinicia → lee todos los registros `status="embedded"` de `mepia_memory` y reconstruye.
- No hay transacciones distribuidas. El orden de operaciones es:
  1. INSERT en `mepia_memory` (obligatorio, bloquea si falla)
  2. UPDATE embedding en `mepia_memory` (BackgroundTask)
  3. store en Engram (BackgroundTask, best-effort — fallo no revierte paso 1 ni 2)

---

## Edge Cases

- Engram binario no encontrado → log warning, continuar solo con pgvector
- Embedding API falla → chunk queda `pending_embed`, reconciliación lo reintenta
- `business_id` sin historial → retornar string vacío, no error
- N12 y N13 ambos intentan escribir → N13 tiene prioridad si `quality_approved: true`
- Engram reinicia → reconstruye desde `mepia_memory WHERE status = 'embedded'`

---

## Archivos relacionados de este nodo
- `db_schema.md` — tabla `mepia_memory` + índice hnsw + columnas FK
- `_glossary.md` — contratos `MemoryChunk`, componentes `Engram` y `MemoryService`
