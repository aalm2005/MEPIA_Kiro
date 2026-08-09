# MEPIA v4 — Documento Maestro de Diseño
*Documento vivo. Consolida todas las decisiones tomadas hasta ahora. Se actualiza cada vez que se cierra una discusión de diseño.*

**Documentos relacionados** (este archivo es el punto de entrada, no repite su contenido completo):
- `mepia_ground_truth_8_escenarios.md` — los 8 casos de ground truth formulados en detalle
- `kiro_prompt_ingesta_api_metricas.md` — prompt listo para pegar en Kiro (25 funciones nuevas de S3)

---

## 0. Registro de decisiones (changelog)

| # | Decisión | Estado |
|---|---|---|
| 1 | `Contexto del día` sale del diseño, sin reemplazo | ✅ Cerrado |
| 2 | Fuente de datos primaria = API JSON a nivel línea (5 capas). PDF/OCR queda documentado como fallback, sin más inversión de tiempo | ✅ Cerrado |
| 3 | Catálogo de 31 métricas candidatas, clasificadas por tipo y aporte al LLM | ✅ Cerrado |
| 4 | Config de negocio: dos tipos — Tipo A (dato de catálogo, sin default posible) y Tipo B (umbral de materialidad, con default de arranque) | ✅ Cerrado |
| 5 | Prompt de Kiro corregido: de 16 a 25 funciones nuevas de S3 (se habían quedado 9 fuera sin razón declarada, incluyendo cancelaciones/reimpresiones por responsable, que resultó ser un requisito real, no opcional) | ✅ Cerrado |
| 6 | Ground truth: unidad = **día completo**, método = mayoría sintético dirigido + un caso de revisión ciega. A futuro, el diario real de producción (`mepia_memory`/`audit_runs`) alimenta casos reales sin rediseño adicional | ✅ Cerrado |
| 7 | 8 escenarios de ground truth formulados **y con JSON real construido** (`tests/eval_set/caso_01...08`) | ✅ Cerrado (ver archivos aparte) |
| 8 | Paradigma de interfaz de salida: **híbrido** — pestañas tipo dashboard (Configuración, Métricas, Gráficas, otras) + pestaña "Chat IA" con semáforo + narrativa libre | ✅ Cerrado |
| 9 | Confirmado: 3 niveles de verdad para el ground truth, ninguno requiere rediseño adicional dado lo ya construido | ✅ Cerrado |
| 10 | Umbrales nuevos confirmados esta sesión: comisión delivery (8%), merma (5%/10%, con benchmark de industria) | ✅ Cerrado |
| 11 | "Por responsable" generalizado como dimensión estándar para cancelación, reimpresión, descuento y cortesía — no una excepción por función | ✅ Cerrado |
| — | Prioridad de hallazgos actualizada (ya no incluye "deducibilidad", heredado del diseño PLD anterior) — propuesta en `caso_08`: fraude > conciliación > zona gris > estadística | ✅ Cerrado — fraude va primero por severidad aunque sea de baja frecuencia, no por frecuencia |
| — | Revisión ciega del Caso 8 (segunda persona o segunda IA, sin ver `anomalias_inyectadas`) | ⏳ Pendiente — prompt listo en `caso_08_prompt_revision_ciega.md` |
| — | Campos exactos de Umbrales/Costos en la pantalla de Configuración | ⏳ Pendiente |
| — | Ejecutar el prompt de Kiro (Tareas 1–5) | ⏳ Pendiente |

---

## 1. Cambios confirmados en la fuente de datos

- **`contexto del día` eliminado.** Generaba ruido, sin valor claro para el diseño final. No se reemplaza.
- **Nueva fuente**: API con JSON a nivel línea, 5 capas — Transacción/Ticket, Detalle de Producto, Formas de Pago, Operación/Caja/Auditoría, Inventarios/Costos Teóricos. Ver el detalle exacto de campos en `kiro_prompt_ingesta_api_metricas.md`, Tarea 2.
- Esto resuelve el problema de fondo señalado en el análisis original: *"el techo real es la confiabilidad del parseo"* — con datos de API estructurados, ese techo prácticamente desaparece.

---

## 2. Catálogo de métricas — resumen

31 métricas candidatas identificadas, distribuidas en 5 niveles de datos. Clasificación:

- **Passthrough** (sin cálculo): solo metadata de identidad (negocio, sucursal, periodo) y registros puntuales de excepción ya detectados por una regla determinista. Casi nada más debe llegar crudo al LLM — es la misma razón por la que el motor de Anthropic pasó de 21% a 95%: el ruido no es "mucha información", es información sin agregar.
- **Control** (validación de integridad, no insight de negocio): validación de IVA, cumplimiento de Cierre X/Z. Viven en `S2 Gatekeeper`, no en S3, y solo se exponen si fallan.
- **Calculado** (función determinista en S3): el resto — 25 funciones nuevas más las 3 que ya existían en el repo (`calc_contribution_margin`, `calc_waste_analysis`, `check_price_inflation`).

El listado completo, función por función, está en `kiro_prompt_ingesta_api_metricas.md`, Tarea 3 (ya corregido).

**Shortlist de mayor valor / menor ruido**: ticket promedio y volumen por turno, costo de comisión por canal delivery (el insight nuevo de mayor valor de todo el catálogo), tasa de descuento efectiva, top/bottom sellers + concentración Pareto, varianza de caja por turno, cancelación post-comanda, tasa de reimpresión, costo de merma en pesos, % de nómina sobre ventas, inflación de insumo clave.

---

## 3. Configuración de usuario — qué debe definir el negocio

### Tipo A — Dato de catálogo, sin el cual la métrica NO se calcula (sin default honesto posible)

| Métrica | Qué debe capturar el negocio |
|---|---|
| Consistencia de precio | Catálogo de precios esperados por producto |
| Costo de comisión por canal delivery | % de comisión por plataforma (UberEats/Rappi/DiDi) — varía por contrato, un default equivocado produce un margen *falso* |
| Costo de redención de lealtad | Valor/costo real del programa de lealtad |
| % de nómina sobre ventas | Costo por hora/salario del personal |

**Regla de diseño**: si el dato de config no está capturado, la métrica se queda `incomplete_data`/`dormant` — mismo patrón que ya usa `S2 Gatekeeper` para completitud de datos del día, extendido a completitud de config de negocio. Nunca inventar un default aquí.

### Tipo B — Umbral de materialidad (la métrica se calcula sola; el negocio solo ajusta la sensibilidad)

| Métrica | Default sugerido |
|---|---|
| Tasa de descuento | >10% del subtotal en un turno |
| Cancelaciones | >5% general; post-comanda: cualquier caso ya es flag |
| Reimpresión | >3% |
| Varianza de caja por turno | >1% o $100 MXN (flag), >3% o $500 MXN (crítico) |
| Merma vs. consumo teórico | >5% (warning), >10% (crítico) — alineado con benchmark de industria (4-10% promedio en restaurantes; 3.11% en servicio completo per estudio Univ. Arizona) |
| Días de inventario restante | <7 días (warning), <3 días (crítico) — ajustar por tipo de insumo |
| Inflación de insumo | >5% en 30 días |
| Costo de comisión delivery (erosión de margen) | >8% de las ventas del día (base subtotal) |
| Top/bottom sellers a mostrar | Top 10 |
| Validación de IVA | 16% (8% si aplica zona fronteriza — confirmar con contador) |

**⚠️ Base de cálculo estandarizada — encontrado en revisión ciega del Caso 8**: todo ratio "% de
ventas" (`discount_rate`, `staff_courtesy_ratio`, y cualquiera que se agregue después) usa
`subtotal` (antes de IVA, antes de cualquier descuento o cortesía de OTRAS órdenes) como
denominador. Nunca `total_net`. Razón: dos revisiones independientes del mismo día calcularon
`staff_courtesy_ratio` distinto (12.4% vs 9.63%) porque una usó `total_net` como base — que ya
trae restado el descuento de otras órdenes del mismo responsable, inflando artificialmente el
ratio de la segunda métrica cuando dos anomalías coinciden en la misma persona/periodo. Con
`subtotal` fijo como base, esa distorsión desaparece.

Esta tabla mapea directo a las pestañas **"2. UMBRALES"** y **"3. COSTOS"** del prototipo de Figma — Umbrales = Tipo B, Costos = Tipo A. Coincidencia útil: el diseño de datos y el de UI ya están alineados sin haberlo planeado explícitamente.

---

## 4. Parseo OCR/PDF — veredicto

**No como ruta primaria. Sí como plan B, sin más inversión.**

`N01 POS PDF Input` ya está `✅ done` en el repo — no se pierde nada dejándolo así. La API elimina el techo de confiabilidad que tenía el PDF (ambigüedad de layout/OCR). Toda la inversión nueva de ingesta va al nodo de API. Documentar el PDF como *"ruta de respaldo si la integración API no está disponible."*

---

## 5. Ground truth — diseño acordado

### 5.1 Granularidad y método

| Opción evaluada | Ventaja principal | Desventaja principal |
|---|---|---|
| A — Un turno | Grano operativo natural, rápido | No sirve para métricas con baseline histórico |
| **B — Un día completo** ✅ elegida | Cubre casi todo nivel 1–4, coincide con el diseño original ("daily = unidad atómica") | Pierde algo de precisión turno-por-turno si hay varios turnos |
| C — Ventana de N días | Única forma de probar métricas con historial (inflación, Pareto estable) | Cara y lenta — se pospone, no bloquea el primer número de accuracy |
| **D — Sintético focalizado** ✅ método principal | Barato, preciso, controlas la respuesta correcta | No prueba el sistema completo por sí solo |
| **E — End-to-end real** ✅ método secundario, "un poco" | Única medida fiel del pipeline completo | Caro — se usa con revisión ciega en vez de con datos reales (que aún no existen) |

**Decisión**: unidad = día completo (B). Construcción = mayoría tipo D (anomalía inyectada y conocida de antemano), con el Escenario 8 usando revisión ciega (una persona construye, otra revisa sin ver la respuesta) como aproximación a E sin necesitar datos reales todavía. Cuando exista negocio piloto real, "el diario" de producción (`mepia_memory`/`audit_runs`, ya diseñado) se vuelve fuente natural de casos E reales — no requiere rediseño, el mecanismo ya existe.

### 5.2 Plantilla de caso

```
caso:
  id
  tipo: "dia_completo_sintetico"
  escenario_narrativo: "una o dos frases: qué pasa este día y por qué importa"
  anomalias_inyectadas:
    - donde, que, metrica_que_deberia_dispararse
  input: { ...json de 5 niveles }
  config_negocio: { comisiones, tarifas, umbrales usados }
  esperado_S3: [ {metric, value, status}, ... ]
  esperado_hallazgos: [ {flag, severidad, justificacion_corta}, ... ]
  esperado_narrativa: null   # pendiente — depende de la interfaz final, ver sección 6
  revisado_por: null
```

### 5.3 Los 8 escenarios

Formulados en detalle en `mepia_ground_truth_8_escenarios.md`: día limpio, faltante de caja, patrón de fraude operativo, erosión de margen por delivery, merma/inventario en riesgo, descuentos fuera de rango, ruidoso pero normal (frontera del umbral), multi-hallazgo (revisión ciega).

### 5.4 Hallazgo de diseño ya aplicado

`calc_cancellation_rate` y `calc_reprint_rate` deben calcularse **desagregadas por responsable** (cajero/mesero), no solo a nivel turno/día — si no, un patrón concentrado en una sola persona se diluye entre el resto del personal normal (surgió al construir el Escenario 3). Ya corregido en `kiro_prompt_ingesta_api_metricas.md`.

---

## 6. Paradigma de interfaz / salida

### 6.1 Opciones evaluadas

| Opción | A favor | En contra |
|---|---|---|
| 1 — Dashboard pasivo (recuadros por pestaña) | Rápido de escanear, ground truth barato | Desperdicia la síntesis multi-señal que ya construyeron (N05/N11/N13); rígido; no escala bien a 31 métricas |
| 2 — Chat con menú de botones | La síntesis multi-señal brilla; los 8 escenarios encajan sin cambios | Más fricción; texto largo = más riesgo de alucinación; ground truth de narrativa es caro |
| **3 — Híbrido** ✅ elegida | Lo mejor de ambos: semáforo casi gratis + narrativa solo cuando vale la pena | Requiere decidir bien la jerarquía de pantallas (ver 6.4) |

### 6.2 Decisión

Híbrido, confirmado. Interfaz imaginada: menú lateral (fijo o desplegable) con pestañas — Configuración, Métricas, Gráficas, otras por definir — más una pestaña **"Chat IA"** que contiene el semáforo, el área de prompt, y el área donde el LLM se explaya sobre lo que está pasando en el negocio.

### 6.3 Mapeo pestañas → tipo de ground truth

| Pestaña | Qué muestra | Ground truth necesario | ¿Requiere diseño nuevo? |
|---|---|---|---|
| Métricas / Gráficas | `CalcResult` de S3 tal cual | Número y `status` correctos | No — ya cubierto por PBT existentes |
| Chat IA — semáforo | Resumen visual de 3–5 `status` | Mismo `status` de arriba | No — mismo dato, sin trabajo extra |
| Chat IA — narrativa | Texto largo, síntesis multi-señal | Los 8 escenarios | No — tal como están |

### 6.4 Punto abierto — no bloquea nada, pero no olvidar

Si el semáforo vive *dentro* de la pestaña "Chat IA", el dueño tiene que entrar a esa pestaña para su primer vistazo del día — se pierde parcialmente la ventaja de "verlo en 2 segundos sin tocar nada". Puede estar bien si "Chat IA" termina siendo la pantalla de inicio de la app. Es una decisión de jerarquía de pantallas a resolver cuando diseñen las pantallas — no bloquea el trabajo de datos/ground truth de hoy.

---

## 7. Brecha actualizada hacia 90–95% accuracy

| # | Qué falta | Estado |
|---|---|---|
| 1 | Nodo de ingesta API | Diseño listo (Tarea 2 del prompt Kiro), falta ejecutar |
| 2 | Extender S3 con las 25 funciones nuevas | Diseño listo (Tarea 3, corregida), falta ejecutar |
| 3 | Retirar `contexto del día` | Diseño listo (Tarea 1), falta ejecutar |
| 4 | Set de evaluación offline | Diseño de los 8 escenarios listo, falta construir el JSON real de cada uno |
| 5 | Capa de skills | Sigue sin diseñar — próximo tema pendiente después del eval set |
| 6 | Footer de procedencia/linaje en N14 | Sigue sin diseñar |
| 7 | Tabla de configuración Tipo A (comisiones, salarios, catálogo de precios) | Diseño listo (sección 3 de este documento + Tarea 4 del prompt Kiro) |

---

## 8. Próximos pasos pendientes

1. Construir el JSON real del Escenario 2 (faltante de caja) — sirve de plantilla técnica para los otros 7.
2. Definir los campos exactos de las pestañas Umbrales/Costos en la pantalla de Configuración (ya tienen la lista de qué debe capturarse en la sección 3, falta el detalle de UI).
3. Ejecutar el prompt de Kiro (Tareas 1–5) para generar/actualizar los specs en `.kiro/specs/mepia/`.
4. Después del eval set: diseñar la capa de skills y el footer de procedencia — quedaron marcados como pendientes en la sección 7 y no se ha vuelto a ellos.
