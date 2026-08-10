# Tasks — Sesión de Codificación (Specs → Código Real)

## Metadata
- spec_id: mepia-codificacion-session
- created: 2025-01-01

## Tasks

- [x] 1. Implementar nodo S1B — Ingesta API
  - [x] 1.1 Crear modelos Pydantic para los 5 niveles de ingesta API (TicketEvent, ProductLine, PaymentBreakdown, ShiftAuditEvent, InventoryUsageEvent) y el output APIIngestResult en agents/api_ingest.py
  - [x] 1.2 Implementar las 10 reglas de validación de integridad (tax ≈ 16% × subtotal como control silencioso, total_net consistency, payment sum check, quantity >= 1, order_id dedup, shifts no vacío, stock >= 0, unit_cost > 0, date no futura, business_id existe)
  - [x] 1.3 Implementar el mapeo a tablas de db_schema.md (pos_inputs, transactions, cash_counts, shift_audit_events, inventory_daily) con upsert/idempotencia
  - [x] 1.4 Implementar endpoint POST /ingest/api-event en api/main.py que orquesta validación + persistencia + retorna APIIngestResult
  - [x] 1.5 Crear migración SQL 005_api_ingesta_tables.sql para shift_audit_events, inventory_daily, delivery_platform_config con índices
- [x] 2. Implementar las 24 funciones nuevas de S3
  - [x] 2.1 Implementar funciones de nivel transacción: calc_avg_ticket, calc_ticket_volume, calc_channel_mix, calc_discount_rate, calc_hourly_sales_pattern, calc_sales_by_staff, calc_sales_by_branch (7 funciones)
  - [x] 2.2 Implementar funciones de nivel producto: calc_top_bottom_sellers, calc_revenue_concentration, check_price_consistency, calc_category_mix, calc_modifier_attach_rate, calc_item_discount_split (6 funciones)
  - [x] 2.3 Implementar funciones de nivel forma de pago: calc_payment_mix, calc_delivery_commission_cost, calc_staff_courtesy_ratio, calc_loyalty_redemption_cost (4 funciones)
  - [x] 2.4 Implementar funciones de nivel operación/caja: calc_cancellation_rate, calc_reprint_rate, calc_shift_cash_variance, calc_labor_cost_ratio, calc_sales_per_labor_hour (5 funciones)
  - [x] 2.5 Implementar funciones de nivel inventario: calc_waste_cost, calc_stock_days_remaining (2 funciones)
- [x] 3. Migración y conexión de delivery_platform_config
  - [x] 3.1 Crear/verificar migración real para delivery_platform_config con UNIQUE constraint e índice (en 005_api_ingesta_tables.sql de tarea 1.5)
  - [x] 3.2 Conectar calc_delivery_commission_cost para leer tasas desde delivery_platform_config — nunca tasa fija hardcodeada
- [x] 4. Retiro real de daily_context del código activo
  - [x] 4.1 Eliminar lectura/escritura de daily_context en api/main.py (endpoints POST/PUT /daily-context → HTTP 410 Gone)
  - [x] 4.2 Eliminar lectura de daily_context en agents/forensic_cfo.py y agents/ceo_orchestrator.py — observed_causality = null fijo
  - [x] 4.3 Simplificar ForensicReport.observed_causality a null literal en el código
- [x] 5. Arnés de evaluación (tests/eval_test/)
  - [x] 5.1 Construir runner Nivel 1 — Determinista (S3 solo, sin LLM): leer los 8 JSON de ground truth, invocar funciones S3, comparar contra esperado_S3 con tolerancia documentada
  - [x] 5.2 Construir runner Nivel 2 — Pipeline completo (con LLM, flag --full-pipeline): ejecutar pipeline real y producir reporte estructurado de hallazgos esperados/encontrados/faltantes/extra
  - [x] 5.3 Implementar salida del harness: reporte por caso + resumen agregado (consola + archivo tests/eval_test/results/run_<timestamp>.json)
  - [x] 5.4 Actualizar eval_offline.md con la ruta real (tests/eval_test/) y documentar los dos niveles de verificación
