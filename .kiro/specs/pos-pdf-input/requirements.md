# POS PDF Input — Requirements

## Overview

Nodo de ingesta de archivos PDF provenientes de sistemas POS (Point of Sale). Extrae transacciones estructuradas mediante OCR y las persiste en Supabase para su uso en el pipeline de auditoría MEPIA.

## Requirements

### 1. Carga de archivos
- El sistema debe aceptar archivos PDF subidos desde el frontend Next.js
- Los archivos deben almacenarse en Supabase Storage antes de procesarse

### 2. Extracción OCR
- El sistema debe extraer tablas de transacciones, totales y fechas del PDF
- El resultado debe incluir un campo `ocr_confidence` para validación posterior

### 3. Persistencia
- Las transacciones extraídas deben persistirse en la tabla `transactions` de Supabase
- El documento original debe registrarse en la tabla `documents`

### 4. Output
- El nodo debe retornar un `POSIngestResult` con los campos: `document_id`, `transactions[]`, `ocr_confidence`, `raw_metadata`

## Archivos de spec relacionados

- `.kiro/specs/mepia/n01_pos_pdf_input.md` — spec detallado del nodo
- `.kiro/specs/mepia/s1_ingesta.md` — contexto de la capa de ingesta completa
- `.kiro/specs/mepia/_glossary.md` — contrato POSIngestResult
