# MEPIA — Requirements

> Este archivo es el punto de entrada del spec para el panel de Kiro.
> La documentación detallada de requerimientos está distribuida en los archivos de nodo.
> Ver `_index.md` para el mapa completo del pipeline.

## Overview

MEPIA (Mise En Place Artificial Intelligence) es un copiloto financiero para dueños de restaurantes que automatiza la auditoría operativa y financiera mediante agentes de IA multi-capa.

## Requirements

### 1. Ingesta de documentos (S1)
- El sistema debe aceptar PDFs de POS, facturas de proveedores, recetas (BOM), conteos de caja y contexto del día
- Cada documento debe ser procesado por OCR y persistido en Supabase Storage y SQL
- Ver spec detallado: `s1_ingesta.md`, `n01_pos_pdf_input.md`, `n02_facturas_input.md`, `n03_human_input_endpoints.md`

### 2. Validación de integridad (S2)
- El sistema debe validar que el set de datos por métrica esté completo antes de calcular
- Cada métrica tiene estado `dormant` (faltan datos) o `active` (set completo)
- Ver spec detallado: `s2_gatekeeper.md`

### 3. Motor de cálculo (S3)
- El sistema debe ejecutar cálculos financieros en Python puro sobre métricas `active`
- El output son números crudos sin interpretación (CalcResult[])
- Ver spec detallado: `s3_motor_calculo.md`

### 4. Auditoría forense IA (S4)
- El sistema debe generar un diagnóstico forense (fugas, discrepancias, techos) usando LLM
- El output es un ForensicReport sin recomendaciones directas
- Ver spec detallado: `s4_auditoria_ia.md`

### 5. CEO Orchestrator (N05)
- El sistema debe sintetizar el ForensicReport con memoria RAG y arquetipo CEO
- El output son AuditInsight[] con copilot_phrase personalizada por arquetipo
- Ver spec detallado: `n05_ceo_orchestrator.md`

### 6. Capa paralela y loop (N06–N14)
- El sistema debe ejecutar auditoría de gastos en paralelo (N09)
- El sistema debe construir contexto enriquecido, generar reporte y revisar calidad en loop
- Ver specs: `n06_orchestrator_adk.md`, `n09_gastos.md`, `n10_context_builder.md`, `n11_consultor.md`

### 7. Memoria transversal
- El sistema debe mantener memoria RAG persistente entre sesiones de auditoría
- Ver spec detallado: `mem_memory_layer.md`

## Archivos de spec relacionados

- `_index.md` — mapa completo del pipeline y estado de cada nodo
- `_glossary.md` — contratos de datos y términos de dominio
- `db_schema.md` — schema de base de datos híbrido
