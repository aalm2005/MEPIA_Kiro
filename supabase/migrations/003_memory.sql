-- =============================================================================
-- MEPIA — Migración 003: Capa de Memoria Semántica (mepia_memory)
-- =============================================================================
-- Propósito : Crear la tabla mepia_memory para RAG + persistencia de contexto.
-- Depende de: 002_hybrid_schema.sql (tablas businesses y audit_results deben existir)
-- Spec      : .kiro/specs/mepia/mem_memory_layer.md
--             .kiro/specs/mepia/db_schema.md
--
-- Decisiones fijas (V1):
--   - Motor de embeddings : text-embedding-3-small (OpenAI)
--   - Dimensiones         : 1536 (fijo — cambiar requiere recrear tabla + regenerar vectores)
--   - Métrica de similitud: coseno (estándar para embeddings de OpenAI)
--   - Índice              : HNSW (mejor que ivfflat para volúmenes pequeños/medianos de V1)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Habilitar la extensión pgvector
--    Supabase la incluye por defecto; este comando es idempotente.
-- -----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;

-- -----------------------------------------------------------------------------
-- 2. Tabla mepia_memory
--    "Brain" semántico del sistema. Single Source of Truth para RAG.
--    Escritura: solo N12 / N13 / proceso de onboarding vía MemoryService.
--    Lectura  : todos los agentes vía MemoryService.get_context().
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mepia_memory (

    -- Identidad
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Negocio propietario del chunk.
    -- ON DELETE CASCADE: si se elimina el negocio, se eliminan todos sus chunks.
    business_id UUID NOT NULL
        REFERENCES businesses(id) ON DELETE CASCADE,

    -- Run de auditoría que originó este chunk.
    -- NULLABLE: los chunks de onboarding no tienen auditoría previa asociada.
    -- Sin FK formal: audit_results.run_id no es PK (puede haber N filas por run).
    -- La trazabilidad se mantiene como dato en metadata.
    source_audit_run_id UUID,

    -- Contenido del chunk (≤ 500 tokens según pipeline de chunking).
    -- Prohibido guardar reportes completos en un solo registro.
    content TEXT NOT NULL,

    -- Metadatos del chunk para filtrado y trazabilidad.
    -- Estructura esperada:
    --   {
    --     "node_origin"  : "N12" | "N13" | "onboarding",
    --     "date"         : "YYYY-MM-DD",
    --     "chunk_index"  : 0,
    --     "chunk_total"  : 4,
    --     "archetype"    : "Operative Genius" | null
    --   }
    metadata JSONB NOT NULL DEFAULT '{}',

    -- Vector de embedding generado con text-embedding-3-small (OpenAI).
    -- Dimensión fija: 1536. Cambiar el modelo requiere recrear esta columna
    -- y regenerar todos los embeddings existentes.
    -- NULL hasta que el worker asíncrono procese el chunk (status = 'pending_embed').
    embedding VECTOR(1536),

    -- Estado del ciclo de vida del embedding.
    --   pending_embed : chunk insertado, embedding aún no generado
    --   embedded      : embedding generado y almacenado correctamente
    --   failed        : falló la generación tras 3 intentos (reconciliación pendiente)
    status TEXT NOT NULL DEFAULT 'pending_embed'
        CHECK (status IN ('pending_embed', 'embedded', 'failed')),

    -- Timestamp de creación — usado para Time-Weighted Retrieval.
    -- score_final = similarity_cosine * (1 / (1 + 0.01 * days_elapsed))
    -- Chunks más recientes tienen mayor peso en la búsqueda semántica.
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()

);

-- -----------------------------------------------------------------------------
-- 3. Índice HNSW para búsqueda de similitud coseno
--    HNSW (Hierarchical Navigable Small World) elegido sobre ivfflat porque:
--      - No requiere entrenamiento previo (ivfflat necesita datos para crear centroides)
--      - Funciona bien desde el primer registro (V1 friendly)
--      - Mayor precisión (recall) a costa de más RAM — aceptable para V1
--    vector_cosine_ops: métrica coseno, estándar para embeddings de OpenAI.
--    Solo indexa filas con embedding NOT NULL (status = 'embedded').
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_memory_embedding
    ON mepia_memory
    USING hnsw (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL;

-- -----------------------------------------------------------------------------
-- 4. Índices de soporte para filtrado y operaciones frecuentes
-- -----------------------------------------------------------------------------

-- Filtrado por negocio (todas las queries incluyen business_id)
CREATE INDEX IF NOT EXISTS idx_memory_business
    ON mepia_memory (business_id);

-- Filtrado por negocio + fecha de creación (Time-Weighted Retrieval)
CREATE INDEX IF NOT EXISTS idx_memory_business_created
    ON mepia_memory (business_id, created_at DESC);

-- Búsqueda de chunks pendientes de embedding (worker de reconciliación)
CREATE INDEX IF NOT EXISTS idx_memory_pending
    ON mepia_memory (status)
    WHERE status IN ('pending_embed', 'failed');

-- Búsqueda por metadata (node_origin, date, archetype)
CREATE INDEX IF NOT EXISTS idx_memory_metadata
    ON mepia_memory
    USING GIN (metadata);

-- -----------------------------------------------------------------------------
-- 5. Comentarios de tabla y columnas (documentación en DB)
-- -----------------------------------------------------------------------------
COMMENT ON TABLE mepia_memory IS
    'Memoria semántica de MEPIA. Single Source of Truth para RAG. '
    'Embeddings generados con text-embedding-3-small (OpenAI, 1536 dims). '
    'Escritura exclusiva vía MemoryService.store_memory() desde N12, N13 u onboarding.';

COMMENT ON COLUMN mepia_memory.embedding IS
    'Vector de 1536 dimensiones generado con text-embedding-3-small (OpenAI). '
    'DECISIÓN FIJA V1: cambiar el modelo requiere recrear esta columna y regenerar todos los vectores.';

COMMENT ON COLUMN mepia_memory.source_audit_run_id IS
    'Nullable: NULL para chunks de onboarding sin auditoría previa asociada.';

COMMENT ON COLUMN mepia_memory.status IS
    'pending_embed: esperando worker. embedded: listo para RAG. failed: error tras 3 intentos.';

COMMENT ON COLUMN mepia_memory.created_at IS
    'Usado para Time-Weighted Retrieval: score = similarity * (1 / (1 + 0.01 * days_elapsed)).';
