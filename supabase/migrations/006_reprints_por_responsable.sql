-- Migration 006: Cambiar reprints de int a jsonb (lista de registros con responsable)
-- No hay datos de producción reales todavía (piloto) — resetear a [] es seguro.

ALTER TABLE shift_audit_events ALTER COLUMN reprints DROP DEFAULT;
ALTER TABLE shift_audit_events ALTER COLUMN reprints TYPE jsonb USING '[]'::jsonb;
ALTER TABLE shift_audit_events ALTER COLUMN reprints SET DEFAULT '[]'::jsonb;
