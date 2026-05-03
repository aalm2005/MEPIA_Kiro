-- =============================================================================
-- MEPIA — Seed de desarrollo: negocio mepia-dev
-- Ejecutar en Supabase SQL Editor UNA SOLA VEZ en el entorno de dev.
-- Después de ejecutar, copiar el UUID generado a .env.local como
-- NEXT_PUBLIC_BUSINESS_ID=<uuid>
-- =============================================================================

INSERT INTO businesses (business_name, industry_sector, currency, opening_date, operating_hours)
VALUES (
    'MEPIA Dev',
    'cafetería',
    'MXN',
    CURRENT_DATE,
    '{"open": "08:00", "close": "22:00"}'
)
RETURNING id, business_name, created_at;
