-- =============================================================================
-- MEPIA — Migración 002: Schema híbrido completo
-- =============================================================================
-- Depende de: 001_init.sql
-- Spec: .kiro/specs/mepia/db_schema.md
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. businesses — entidad raíz
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS businesses (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_name    TEXT NOT NULL,
    industry_sector  TEXT,
    currency         TEXT NOT NULL DEFAULT 'MXN',
    opening_date     DATE,
    operating_hours  JSONB DEFAULT '{"open": "08:00", "close": "22:00"}',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- 2. business_onboarding — configuración de auditoría e identidad de marca
--    Separada de businesses para no mezclar datos operativos con configuración.
--    Una fila por negocio (upsert en PUT). Historial en mepia_memory.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS business_onboarding (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id             UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    brand_voice             TEXT,
    prohibited_recommendations JSONB DEFAULT '[]',
    priority_focus          TEXT CHECK (priority_focus IN ('efficiency', 'quality', 'growth')),
    max_cash_discrepancy_pct    NUMERIC(5,4),
    max_cash_discrepancy_abs    NUMERIC(12,2),
    margin_warning_threshold    NUMERIC(5,4),
    margin_critical_threshold   NUMERIC(5,4),
    cost_spike_threshold_pct    NUMERIC(5,4),
    audit_rules             JSONB DEFAULT '{}',
    completed_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (business_id)
);

-- -----------------------------------------------------------------------------
-- 3. business_fixed_costs — estructura de costos esperada del onboarding
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS business_fixed_costs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id      UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    concept          TEXT NOT NULL,
    amount           NUMERIC(12,2),
    expected_monthly_amount NUMERIC(12,2),
    tolerance_pct    NUMERIC(5,4) DEFAULT 0.05,
    recurrence       TEXT DEFAULT 'monthly',
    expense_behavior TEXT CHECK (expense_behavior IN ('FIXED', 'VARIABLE', 'CAPEX')),
    is_active        BOOLEAN NOT NULL DEFAULT true,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- 4. documents
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id         UUID NOT NULL REFERENCES businesses(id),
    storage_path        TEXT,
    filename            TEXT,
    document_type       TEXT CHECK (document_type IN ('PDF', 'XML', 'JPG')),
    ocr_status          TEXT DEFAULT 'pending' CHECK (ocr_status IN ('pending', 'processed', 'error')),
    ocr_confidence      NUMERIC(5,2),
    needs_human_review  BOOLEAN NOT NULL DEFAULT false,
    uploaded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    extracted_data      JSONB
);

-- -----------------------------------------------------------------------------
-- 5. transactions
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transactions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id         UUID NOT NULL REFERENCES businesses(id),
    document_id         UUID REFERENCES documents(id),
    type                TEXT CHECK (type IN ('ingreso', 'egreso')),
    category            TEXT CHECK (category IN ('venta', 'nomina', 'proveedor', 'impuesto')),
    amount              NUMERIC(12,2),
    tax_amount          NUMERIC(12,2),
    transaction_date    DATE,
    supplier_name       TEXT,
    concept             TEXT,
    document_reference  TEXT,
    expense_behavior    TEXT CHECK (expense_behavior IN ('FIXED', 'VARIABLE', 'CAPEX')),
    metadata            JSONB,
    raw_metadata        JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- 6. pos_inputs
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pos_inputs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id      UUID NOT NULL REFERENCES businesses(id),
    date             DATE NOT NULL,
    total_sales      NUMERIC(12,2),
    cash_sales       NUMERIC(12,2),
    card_sales       NUMERIC(12,2),
    refunds          NUMERIC(12,2) DEFAULT 0,
    num_transactions INT
);

-- -----------------------------------------------------------------------------
-- 7. cash_counts
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cash_counts (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id      UUID NOT NULL REFERENCES businesses(id),
    date             DATE NOT NULL,
    initial_float    NUMERIC(12,2),
    actual_counted   NUMERIC(12,2),
    cash_payouts     NUMERIC(12,2) DEFAULT 0,
    recorded_by      TEXT
);

-- -----------------------------------------------------------------------------
-- 8. recipes
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recipes (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id      UUID NOT NULL REFERENCES businesses(id),
    product_name     TEXT NOT NULL,
    sale_price       NUMERIC(12,2),
    ingredients      JSONB,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- 9. daily_context
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_context (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id      UUID NOT NULL REFERENCES businesses(id),
    date             DATE NOT NULL,
    tags             JSONB DEFAULT '{}',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- 10. metric_status
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metric_status (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id      UUID NOT NULL REFERENCES businesses(id),
    date             DATE NOT NULL,
    metric_name      TEXT NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('dormant', 'active', 'blocked')),
    missing_fields   JSONB DEFAULT '[]',
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- 11. audit_results (reemplaza la de 001_init.sql)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_results (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id           UUID,
    business_id      UUID REFERENCES businesses(id),
    date             DATE,
    pipeline_layer   TEXT CHECK (pipeline_layer IN ('sequential', 'parallel', 'loop')),
    node_id          TEXT,
    module           TEXT,
    archetype        TEXT,
    raw_result       JSONB,
    copilot_phrase   TEXT,
    node_status      TEXT CHECK (node_status IN ('success', 'partial', 'failed', 'timeout', 'error')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- 12. circuit_breaker_state
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS circuit_breaker_state (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id          UUID NOT NULL REFERENCES businesses(id),
    date                 DATE NOT NULL,
    node_id              TEXT NOT NULL CHECK (node_id IN ('N07', 'N08', 'N09')),
    consecutive_failures INT NOT NULL DEFAULT 0,
    circuit_status       TEXT NOT NULL DEFAULT 'closed' CHECK (circuit_status IN ('closed', 'open')),
    opened_at            TIMESTAMPTZ,
    reset_by             UUID,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- 13. unit_conversions
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS unit_conversions (
    id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_unit TEXT NOT NULL,
    to_unit   TEXT NOT NULL,
    factor    NUMERIC NOT NULL
);

INSERT INTO unit_conversions (from_unit, to_unit, factor) VALUES
    ('kg',     'g',      1000),
    ('L',      'ml',     1000),
    ('unidad', 'unidad', 1)
ON CONFLICT DO NOTHING;

-- -----------------------------------------------------------------------------
-- 14. Índices
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_transactions_metadata          ON transactions USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_transactions_raw_metadata      ON transactions USING GIN (raw_metadata);
CREATE INDEX IF NOT EXISTS idx_documents_extracted            ON documents    USING GIN (extracted_data);
CREATE INDEX IF NOT EXISTS idx_transactions_business_date     ON transactions (business_id, transaction_date);
CREATE INDEX IF NOT EXISTS idx_transactions_expense_behavior  ON transactions (business_id, expense_behavior);
CREATE INDEX IF NOT EXISTS idx_documents_review               ON documents    (needs_human_review) WHERE needs_human_review = true;
CREATE INDEX IF NOT EXISTS idx_daily_context_lookup           ON daily_context (business_id, date);
CREATE INDEX IF NOT EXISTS idx_metric_status_lookup           ON metric_status (business_id, date, status);
CREATE INDEX IF NOT EXISTS idx_recipes_business               ON recipes (business_id);
CREATE INDEX IF NOT EXISTS idx_audit_results_run              ON audit_results (run_id);
CREATE INDEX IF NOT EXISTS idx_audit_results_lookup           ON audit_results (business_id, date, pipeline_layer, node_id);
CREATE INDEX IF NOT EXISTS idx_circuit_breaker_lookup         ON circuit_breaker_state (business_id, date, node_id);
CREATE INDEX IF NOT EXISTS idx_circuit_breaker_open           ON circuit_breaker_state (node_id, circuit_status) WHERE circuit_status = 'open';
CREATE INDEX IF NOT EXISTS idx_onboarding_business            ON business_onboarding (business_id);
CREATE INDEX IF NOT EXISTS idx_fixed_costs_business_active    ON business_fixed_costs (business_id, is_active);
