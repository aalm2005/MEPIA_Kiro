-- =============================================================================
-- MEPIA — Migración 004: RPC de búsqueda vectorial + RLS básico
-- =============================================================================
-- Depende de: 003_memory.sql (mepia_memory con pgvector debe existir)
-- Spec: .kiro/specs/mepia/mem_memory_layer.md
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Función RPC: match_mepia_memory
--    Usada por MemoryService._search_pgvector() para búsqueda semántica.
--    Retorna los chunks más similares al query_embedding, filtrados por negocio.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION match_mepia_memory(
    query_embedding   VECTOR(1536),
    business_id_filter UUID,
    match_count       INT DEFAULT 5
)
RETURNS TABLE (
    id                  UUID,
    content             TEXT,
    metadata            JSONB,
    similarity          FLOAT,
    created_at          TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        m.id,
        m.content,
        m.metadata,
        1 - (m.embedding <=> query_embedding) AS similarity,
        m.created_at
    FROM mepia_memory m
    WHERE
        m.business_id = business_id_filter
        AND m.status = 'embedded'
        AND m.embedding IS NOT NULL
    ORDER BY m.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- -----------------------------------------------------------------------------
-- 2. Habilitar RLS en todas las tablas de negocio
--    Por ahora: política permisiva para service_role (backend Python).
--    En producción: agregar políticas por usuario autenticado.
-- -----------------------------------------------------------------------------

ALTER TABLE businesses              ENABLE ROW LEVEL SECURITY;
ALTER TABLE business_onboarding     ENABLE ROW LEVEL SECURITY;
ALTER TABLE business_fixed_costs    ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents               ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions            ENABLE ROW LEVEL SECURITY;
ALTER TABLE pos_inputs              ENABLE ROW LEVEL SECURITY;
ALTER TABLE cash_counts             ENABLE ROW LEVEL SECURITY;
ALTER TABLE recipes                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_context           ENABLE ROW LEVEL SECURITY;
ALTER TABLE metric_status           ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_results           ENABLE ROW LEVEL SECURITY;
ALTER TABLE circuit_breaker_state   ENABLE ROW LEVEL SECURITY;
ALTER TABLE mepia_memory            ENABLE ROW LEVEL SECURITY;

-- Política: service_role tiene acceso total (backend Python usa service_role key)
CREATE POLICY "service_role_all" ON businesses
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "service_role_all" ON business_onboarding
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "service_role_all" ON business_fixed_costs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "service_role_all" ON documents
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "service_role_all" ON transactions
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "service_role_all" ON pos_inputs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "service_role_all" ON cash_counts
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "service_role_all" ON recipes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "service_role_all" ON daily_context
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "service_role_all" ON metric_status
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "service_role_all" ON audit_results
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "service_role_all" ON circuit_breaker_state
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "service_role_all" ON mepia_memory
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Política: anon key puede leer audit_results y businesses (para el frontend)
CREATE POLICY "anon_read_businesses" ON businesses
    FOR SELECT TO anon USING (true);

CREATE POLICY "anon_read_audit_results" ON audit_results
    FOR SELECT TO anon USING (true);
