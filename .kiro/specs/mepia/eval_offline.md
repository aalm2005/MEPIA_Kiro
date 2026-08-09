# EVAL — Set de Evaluación Offline

**Capa:** Transversal (Calidad) | **Relación:** Valida S3, S4, N05, N11
**Archivos relacionados:** `s3_motor_calculo.md`, `s4_auditoria_ia.md`, `n05_ceo_orchestrator.md`, `n11_consultor.md`

## Decisión de LLM

No aplica — evaluación offline sin LLM en el propio set. Los nodos evaluados sí usan LLM.

## Responsabilidad

Definir un set de casos de evaluación con ground truth conocido para validar que:
1. S3 produce cálculos correctos ante inputs controlados.
2. S4 detecta las anomalías esperadas.
3. N05 genera insights alineados al arquetipo.
4. N11 produce reportes que cumplen las directivas y restricciones de marca.

---

## Decisiones Resueltas

### Ubicación de los casos

Los casos viven en `tests/eval_set/caso_NN_nombre.json`, un archivo por caso,
siguiendo el mismo patrón que `tests/test_pbt_*.py`.

**Nunca en mepia.db.** Los casos son fixtures de prueba sintéticos y deben quedarse
fijos para que el número de accuracy sea comparable entre corridas. Meterlos a la base
de producción contaminaría `mepia_memory` con historial falso.

### Formato del caso

Ya existe un ejemplo real en `tests/eval_set/caso_02_faltante_caja.json` — se usa como
plantilla de estructura. Los campos obligatorios de cada caso:

```json
{
  "id": "caso_02_faltante_caja",
  "tipo": "anomalia_caja",
  "escenario_narrativo": "Descripción humana del escenario de prueba",
  "anomalias_inyectadas": [
    { "tipo": "faltante_caja", "magnitud": "-$350 MXN", "turno": "vespertino" }
  ],
  "input": {
    "tickets": [ /* TicketEvent[] */ ],
    "payments": [ /* PaymentBreakdown[] */ ],
    "shift_audit": [ /* ShiftAuditEvent[] */ ],
    "inventory": [ /* InventoryUsageEvent[] */ ],
    "config_negocio": {
      "business_id": "uuid",
      "opening_date": "2023-01-15",
      "archetype": "Operative Genius",
      "multi_sucursal": false,
      "delivery_platform_config": [ /* tasas de comisión */ ]
    }
  },
  "esperado_S3": {
    "calc_shift_cash_variance": { "value": -350, "status": "critical" },
    "calc_cancellation_rate": { "value": 0, "status": "ok" }
  },
  "esperado_hallazgos": [
    { "tipo_anomalia": "source_discrepancy", "severity": "high", "metric_origin": "calc_shift_cash_variance" }
  ],
  "esperado_narrativa": {
    "debe_mencionar": ["faltante", "turno vespertino", "$350"],
    "no_debe_mencionar": ["cancelación", "merma"]
  },
  "revisado_por": "aalm2",
  "notas_construccion": "string libre — observaciones del etiquetador"
}
```

---

## Pendiente de diseño

Los siguientes elementos se diseñan a detalle en la siguiente sesión:

### Harness de ejecución

- Cómo se construye el runner que lee los JSON de `tests/eval_set/` y corre el pipeline
  completo contra cada uno (pytest plugin, script standalone, o integration test en CI).
- Si el harness mockea la DB o usa una instancia de test con seeds reales.
- Cómo se manejan los nodos con LLM (S4, N05, N11) — ¿se usa un modelo determinístico
  con seed fija? ¿Se evalúa solo estructura y no contenido narrativo exacto?

### Método de etiquetado y umbral de aprobación

- Quién etiqueta los ground truths (experto de dominio, generados programáticamente, híbrido).
- Cuántos casos mínimo para una evaluación confiable (target por nodo).
- Qué % de casos pasados constituye un "pass" del set completo (ej. 95% para S3, 80% para N11).
- Cómo se versionan los casos — actualmente en git (`tests/eval_set/`), confirmar que es suficiente.

### Ambigüedad de regla de materialidad Tipo B

Resolver: ¿el umbral efectivo para generar un hallazgo es "cualquiera de las dos condiciones
dispara" (umbral absoluto O umbral porcentual) o "el mayor de las dos"?

> Referencia: ver `notas_construccion` en `caso_02_faltante_caja.json`.
> Ejemplo: faltante de $350 en un día de $50,000 ventas = 0.7% (bajo en %) pero $350 en absoluto.
> ¿Es critical, warning, o ok? Depende de cuál regla domina.

Esta ambigüedad afecta directamente la etiqueta de `esperado_S3.status` en los casos
del eval set — debe resolverse antes de escalar a >5 casos.

---

## Heurísticas (Python/SQL — sin LLM)

Pendiente — se definirá el runner de evaluación (pytest + fixtures vs script standalone).

## Output — EvalResult (placeholder)

```python
class EvalCaseResult(BaseModel):
    case_id: str
    node_under_test: str            # "S3" | "S4" | "N05" | "N11"
    passed: bool
    expected: dict                  # ground truth
    actual: dict                    # output del nodo
    delta: dict | None              # diferencia si numérico
    notes: str | None
```

---

## Reglas de generación de warnings

Pendiente — se definirán alertas de regresión cuando un caso previamente pasado falla.

## Acceptance Criteria

- WHEN un caso definido se ejecuta → produce `EvalCaseResult` con `passed: bool`
- WHEN `passed: false` → `delta` documenta la diferencia exacta
- WHEN se agrega nueva función a S3 → debe existir al menos 1 caso de eval para ella
- WHEN se modifica umbral de status → los casos de eval reflejan el nuevo umbral
- WHEN el eval set corre en CI → los casos JSON de `tests/eval_set/` nunca tocan mepia.db

## Edge Cases

Pendiente.

## Correctness Properties (PBT)

Pendiente — las propiedades del set de evaluación se derivarán de las propiedades
ya definidas en cada nodo (S3.P1–P12, S4.P1–Pn, etc.).
