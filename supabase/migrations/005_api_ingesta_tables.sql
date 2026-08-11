-- =============================================================================
-- MEPIA — Migración 005: Tablas de Ingesta API (S1B)
-- =============================================================================
-- Propósito : Crear las tablas shift_audit_events, inventory_daily y
--             delivery_platform_config requeridas por la API de ingesta POS.
-- Depende de: 002_hybrid_schema.sql (tabla businesses debe existir)
-- Spec      : .kiro/specs/mepia/s1b_ingesta_api.md
--             .kiro/specs/mepia/db_schema.md
--
-- Tablas creadas:
--   - shift_audit_events       : Eventos de auditoría operativa por turno
--   - inventory_daily          : Snapshot diario de inventario/costos teóricos
--   - delivery_platform_config : Configuración de comisiones por plataforma delivery
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. shift_audit_events
--    Auditoría operativa por turno: apertura, cierres X/Z, sobrante/faltante,
--    cancellations, reprints, clock_records.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shift_audit_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id uuid NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    sucursal_id text NOT NULL,
    date date NOT NULL,
    turno text NOT NULL,
    apertura numeric(12,2) NOT NULL,
    cierre_x numeric(12,2) NOT NULL,
    cierre_z numeric(12,2) NOT NULL,
    sobrante_faltante numeric(12,2) NOT NULL,
    cancellations jsonb DEFAULT '[]'::jsonb,
    reprints int DEFAULT 0,
    clock_records jsonb DEFAULT '[]'::jsonb,
    created_at timestamptz DEFAULT now()
);

-- UNIQUE constraint para idempotencia en upsert
ALTER TABLE shift_audit_events ADD CONSTRAINT uq_shift_audit_lookup
    UNIQUE (business_id, date, sucursal_id, turno);

-- -----------------------------------------------------------------------------
-- 2. inventory_daily
--    Snapshot diario de consumo teórico, merma, stock actual y costo unitario
--    por ingrediente.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS inventory_daily (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id uuid NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    date date NOT NULL,
    ingredient_id text NOT NULL,
    ingredient_name text NOT NULL,
    unit text NOT NULL,
    consumo_teorico numeric(12,4) NOT NULL,
    waste_recorded numeric(12,4) DEFAULT 0,
    current_stock numeric(12,4) NOT NULL,
    unit_cost numeric(12,4) NOT NULL,
    created_at timestamptz DEFAULT now()
);

-- UNIQUE constraint para idempotencia en upsert
ALTER TABLE inventory_daily ADD CONSTRAINT uq_inventory_daily_lookup
    UNIQUE (business_id, date, ingredient_id);

-- -----------------------------------------------------------------------------
-- 3. delivery_platform_config
--    Configuración de comisiones por plataforma de delivery.
--    Permite historial de tasas por fecha efectiva.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS delivery_platform_config (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id uuid NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    platform text NOT NULL,           -- "UberEats" | "Rappi" | "DiDiFood"
    commission_rate numeric(5,4) NOT NULL,  -- ej. 0.3000 = 30%
    effective_date date NOT NULL,
    created_at timestamptz DEFAULT now()
);

-- UNIQUE constraint: permite historial de tasas por plataforma
ALTER TABLE delivery_platform_config ADD CONSTRAINT uq_delivery_platform_config
    UNIQUE (business_id, platform, effective_date);

-- -----------------------------------------------------------------------------
-- 4. Índices
-- -----------------------------------------------------------------------------
CREATE INDEX idx_shift_audit_lookup ON shift_audit_events (business_id, date, sucursal_id);
CREATE INDEX idx_inventory_daily_lookup ON inventory_daily (business_id, date);
CREATE INDEX idx_inventory_daily_ingredient ON inventory_daily (business_id, ingredient_id, date);
CREATE INDEX idx_delivery_platform_lookup ON delivery_platform_config (business_id, platform, effective_date DESC);
