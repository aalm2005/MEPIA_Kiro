"""
S3 — Motor de Cálculo
Funciones puras de cálculo financiero. Sin LLM, sin interpretación.
Spec: .kiro/specs/mepia/s3_motor_calculo.md
"""
from __future__ import annotations

import calendar
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# CalcStatus — valores posibles del campo status en CalcResult
# ---------------------------------------------------------------------------

CalcStatus = Literal[
    "ok",
    "warning",
    "critical",
    "incomplete_data",
    "unit_mismatch",
]


# ---------------------------------------------------------------------------
# CalcResult — contrato de salida de TODAS las funciones de S3
# Spec: s3_motor_calculo.md §Formato de respuesta
# ---------------------------------------------------------------------------

class CalcResult(BaseModel):
    """
    Output estándar de cada función del Motor de Cálculo.
    Nunca lanza excepción — errores se expresan como status.
    """
    metric: str                        # nombre de la métrica calculada
    value: Optional[Decimal] = None    # None cuando status es incomplete_data o unit_mismatch
    unit: str                          # unidad del valor (MXN, %, litros, unidades, etc.)
    status: CalcStatus                 # resultado de la evaluación contra umbrales
    context: str                       # descripción legible del resultado para S4


# ---------------------------------------------------------------------------
# Inputs de cada función — tipados para claridad interna
# (las funciones reciben estos valores + el cliente Supabase)
# ---------------------------------------------------------------------------

class ContributionMarginInput(BaseModel):
    """Input para calc_contribution_margin."""
    product_id: str                    # FK a recipes.id


class BreakEvenInput(BaseModel):
    """Input para calc_daily_break_even."""
    business_id: str
    date: str                          # YYYY-MM-DD


class WasteAnalysisInput(BaseModel):
    """Input para calc_waste_analysis."""
    ingredient_id: str                 # FK a recipes.ingredients key
    start_date: str                    # YYYY-MM-DD
    end_date: str                      # YYYY-MM-DD
    business_id: str


class BurnRateInput(BaseModel):
    """Input para calc_burn_rate."""
    business_id: str
    date: str                          # YYYY-MM-DD — determina el mes de cálculo


class PriceInflationInput(BaseModel):
    """Input para check_price_inflation."""
    ingredient_id: str
    business_id: str


class CashReconciliationInput(BaseModel):
    """Input para calc_cash_reconciliation."""
    business_id: str
    date: str                          # YYYY-MM-DD


# ---------------------------------------------------------------------------
# UnitConversion — fila de la tabla unit_conversions en Supabase
# Spec: s3_motor_calculo.md §Normalización de Unidades
# ---------------------------------------------------------------------------

class UnitConversion(BaseModel):
    """Representa una fila de la tabla unit_conversions."""
    from_unit: str                     # unidad origen (ej. "kg", "L")
    to_unit: str                       # unidad base (ej. "g", "ml")
    factor: Decimal                    # multiplicador (ej. 1000)


# ---------------------------------------------------------------------------
# CalcEngineResult — wrapper para ejecutar múltiples métricas en un solo run
# Usado por POST /calc/run en api/main.py
# ---------------------------------------------------------------------------

class CalcRunRequest(BaseModel):
    """Payload de POST /calc/run."""
    business_id: str
    date: str                          # YYYY-MM-DD
    metrics: list[str] = []            # lista de métricas a calcular; vacío = todas las active


class CalcRunResult(BaseModel):
    """Respuesta de POST /calc/run."""
    business_id: str
    date: str
    results: list[CalcResult]
    skipped_metrics: list[str] = []    # métricas dormant/blocked que no se calcularon
    run_id: str                        # UUID del registro en audit_results


# ===========================================================================
# FUNCIONES AUXILIARES PURAS (sin DB)
# ===========================================================================

def normalize_units(
    value: Decimal,
    from_unit: str,
    to_unit: str,
    conversions: list[UnitConversion],
) -> Decimal | None:
    """
    Convierte `value` de `from_unit` a `to_unit` usando la tabla de conversiones.

    Reglas:
    - Si from_unit == to_unit → retorna value sin cambio.
    - Si existe conversión directa → aplica el factor.
    - Si no hay conversión disponible → retorna None (indica unit_mismatch).
    """
    # Misma unidad: no hay nada que convertir
    if from_unit == to_unit:
        return value

    # Buscar conversión directa en la lista cargada desde DB
    for conv in conversions:
        if conv.from_unit == from_unit and conv.to_unit == to_unit:
            return value * conv.factor

    # No se encontró conversión — el caller debe emitir unit_mismatch
    return None


def days_in_month(date_str: str) -> int:
    """
    Retorna el número real de días del mes para la fecha dada (YYYY-MM-DD).

    Usa calendar.monthrange para respetar años bisiestos (febrero 28/29).
    NUNCA retorna 30 fijo.
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    # monthrange retorna (weekday_del_primer_dia, total_dias_del_mes)
    _, total_days = calendar.monthrange(dt.year, dt.month)
    return total_days


# ===========================================================================
# FUNCIONES DE CÁLCULO FINANCIERO
# ===========================================================================

def calc_contribution_margin(product_id: str, db: Any) -> CalcResult:
    """
    Calcula el Margen de Contribución (MC) de un producto.

    Fórmula:
        MC = precio_venta - sum(ingrediente_qty × precio_unitario)

    Fuentes de datos:
        - recipes: sale_price + ingredients (JSONB con qty por ingrediente)
        - transactions: última factura por ingrediente para precio_unitario

    Umbrales:
        - critical : MC_pct < 10%
        - warning  : MC_pct < 20%
        - ok       : MC_pct >= 20%
    """
    try:
        # --- 1. Obtener receta del producto ---
        receta_resp = (
            db.table("recipes")
            .select("sale_price, ingredients")
            .eq("id", product_id)
            .single()
            .execute()
        )
        receta = receta_resp.data
        if not receta:
            return CalcResult(
                metric="margen_contribucion",
                value=None,
                unit="MXN",
                status="incomplete_data",
                context=f"No se encontró receta para product_id={product_id}.",
            )

        precio_venta = Decimal(str(receta["sale_price"]))
        ingredientes: dict = receta.get("ingredients") or {}

        if not ingredientes:
            return CalcResult(
                metric="margen_contribucion",
                value=None,
                unit="MXN",
                status="incomplete_data",
                context=f"La receta de product_id={product_id} no tiene ingredientes.",
            )

        # --- 2. Calcular costo total de ingredientes ---
        costo_total = Decimal("0")
        ingredientes_sin_precio: list[str] = []

        for ing_id, qty_raw in ingredientes.items():
            qty = Decimal(str(qty_raw))

            # Última factura del ingrediente (precio unitario más reciente)
            tx_resp = (
                db.table("transactions")
                .select("unit_price")
                .eq("ingredient_id", ing_id)
                .order("transaction_date", desc=True)
                .limit(1)
                .execute()
            )
            tx_rows = tx_resp.data or []

            if not tx_rows or tx_rows[0].get("unit_price") is None:
                ingredientes_sin_precio.append(ing_id)
                continue

            precio_unitario = Decimal(str(tx_rows[0]["unit_price"]))
            costo_total += qty * precio_unitario

        # Si algún ingrediente no tiene precio, no podemos calcular con certeza
        if ingredientes_sin_precio:
            return CalcResult(
                metric="margen_contribucion",
                value=None,
                unit="MXN",
                status="incomplete_data",
                context=(
                    f"Sin precio para ingrediente(s): {', '.join(ingredientes_sin_precio)}. "
                    "Se requiere al menos una factura por ingrediente."
                ),
            )

        # --- 3. Calcular MC y evaluar umbrales ---
        mc = precio_venta - costo_total

        if precio_venta == Decimal("0"):
            return CalcResult(
                metric="margen_contribucion",
                value=None,
                unit="MXN",
                status="incomplete_data",
                context="El precio de venta del producto es 0.",
            )

        mc_pct = (mc / precio_venta * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        if mc_pct < Decimal("10"):
            status: CalcStatus = "critical"
        elif mc_pct < Decimal("20"):
            status = "warning"
        else:
            status = "ok"

        return CalcResult(
            metric="margen_contribucion",
            value=mc.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            unit="MXN",
            status=status,
            context=(
                f"MC={mc:.2f} MXN ({mc_pct:.1f}% del precio de venta {precio_venta:.2f} MXN). "
                f"Costo de ingredientes: {costo_total:.2f} MXN."
            ),
        )

    except Exception as exc:
        return CalcResult(
            metric="margen_contribucion",
            value=None,
            unit="MXN",
            status="incomplete_data",
            context=f"Error al consultar datos para product_id={product_id}: {exc}",
        )


def calc_daily_break_even(business_id: str, date: str, db: Any) -> CalcResult:
    """
    Calcula el Punto de Equilibrio diario en unidades.

    Fórmula:
        PE_unidades = (sum(FIXED expenses del mes) / days_in_month(date)) / MC_promedio

    Fuentes de datos:
        - transactions: expense_behavior = "FIXED" del mes
        - recipes + transactions: MC promedio de todos los productos con receta

    Notas:
        - Usa days_in_month(date) como divisor, NUNCA 30 fijo.
        - Solo gastos con expense_behavior confirmado explícitamente.
    """
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        # Rango del mes completo
        primer_dia = dt.replace(day=1).strftime("%Y-%m-%d")
        ultimo_dia = dt.replace(
            day=days_in_month(date)
        ).strftime("%Y-%m-%d")

        # --- 1. Gastos FIXED del mes ---
        gastos_resp = (
            db.table("transactions")
            .select("amount")
            .eq("business_id", business_id)
            .eq("expense_behavior", "FIXED")
            .gte("transaction_date", primer_dia)
            .lte("transaction_date", ultimo_dia)
            .execute()
        )
        gastos_rows = gastos_resp.data or []

        if not gastos_rows:
            return CalcResult(
                metric="punto_equilibrio_diario",
                value=None,
                unit="unidades/día",
                status="incomplete_data",
                context=(
                    f"No hay gastos FIXED confirmados para {business_id} "
                    f"en {dt.strftime('%B %Y')}."
                ),
            )

        total_fixed = sum(Decimal(str(r["amount"])) for r in gastos_rows)

        # --- 2. MC promedio de todos los productos con receta ---
        recetas_resp = (
            db.table("recipes")
            .select("id, sale_price, ingredients")
            .eq("business_id", business_id)
            .execute()
        )
        recetas = recetas_resp.data or []

        mc_valores: list[Decimal] = []
        for receta in recetas:
            pid = receta["id"]
            # Reutilizamos calc_contribution_margin para obtener el MC de cada producto
            resultado = calc_contribution_margin(pid, db)
            if resultado.status == "ok" or resultado.status == "warning" or resultado.status == "critical":
                if resultado.value is not None:
                    mc_valores.append(resultado.value)

        if not mc_valores:
            return CalcResult(
                metric="punto_equilibrio_diario",
                value=None,
                unit="unidades/día",
                status="incomplete_data",
                context="No se pudo calcular MC promedio: sin productos con receta y precios completos.",
            )

        mc_promedio = sum(mc_valores) / Decimal(str(len(mc_valores)))

        if mc_promedio == Decimal("0"):
            return CalcResult(
                metric="punto_equilibrio_diario",
                value=None,
                unit="unidades/día",
                status="incomplete_data",
                context="MC promedio es 0 — no es posible calcular el punto de equilibrio.",
            )

        # --- 3. Calcular PE diario ---
        dias = Decimal(str(days_in_month(date)))
        pe_diario = (total_fixed / dias / mc_promedio).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        return CalcResult(
            metric="punto_equilibrio_diario",
            value=pe_diario,
            unit="unidades/día",
            status="ok",
            context=(
                f"Gastos fijos del mes: {total_fixed:.2f} MXN / {int(dias)} días. "
                f"MC promedio: {mc_promedio:.2f} MXN. "
                f"Se necesitan vender {pe_diario:.1f} unidades/día para cubrir costos fijos."
            ),
        )

    except Exception as exc:
        return CalcResult(
            metric="punto_equilibrio_diario",
            value=None,
            unit="unidades/día",
            status="incomplete_data",
            context=f"Error al calcular punto de equilibrio para {business_id}: {exc}",
        )


def calc_waste_analysis(
    ingredient_id: str,
    start_date: str,
    end_date: str,
    business_id: str,
    db: Any,
) -> CalcResult:
    """
    Calcula el porcentaje de merma de un ingrediente en un rango de fechas.

    Fórmula:
        merma_pct = (comprado_base - consumo_teorico_base) / comprado_base × 100

    Donde:
        comprado_base    = sum de qty comprada, normalizada a unidad base
        consumo_teorico  = sum(ventas_producto × qty_ingrediente_en_receta), normalizada

    Umbrales:
        - critical : merma_pct > 15%
        - warning  : merma_pct > 5%
        - ok       : merma_pct <= 5%
    """
    try:
        # --- 1. Cargar conversiones de unidades desde DB ---
        conv_resp = db.table("unit_conversions").select("*").execute()
        conversions = [UnitConversion(**r) for r in (conv_resp.data or [])]

        # --- 2. Cantidad comprada del ingrediente en el rango ---
        compras_resp = (
            db.table("transactions")
            .select("quantity, unit")
            .eq("business_id", business_id)
            .eq("ingredient_id", ingredient_id)
            .gte("transaction_date", start_date)
            .lte("transaction_date", end_date)
            .execute()
        )
        compras = compras_resp.data or []

        if not compras:
            return CalcResult(
                metric="merma",
                value=None,
                unit="%",
                status="incomplete_data",
                context=(
                    f"Sin compras registradas para ingrediente {ingredient_id} "
                    f"entre {start_date} y {end_date}."
                ),
            )

        # Normalizar todas las compras a la unidad base del primer registro
        unidad_base = compras[0]["unit"]
        total_comprado = Decimal("0")

        for compra in compras:
            qty = Decimal(str(compra["quantity"]))
            unidad_origen = compra["unit"]
            qty_normalizada = normalize_units(qty, unidad_origen, unidad_base, conversions)

            if qty_normalizada is None:
                return CalcResult(
                    metric="merma",
                    value=None,
                    unit="%",
                    status="unit_mismatch",
                    context=(
                        f"Unidades incompatibles en compras de {ingredient_id}: "
                        f"'{unidad_origen}' no se puede convertir a '{unidad_base}'."
                    ),
                )
            total_comprado += qty_normalizada

        # --- 3. Consumo teórico: ventas × qty en receta ---
        # Buscar todas las recetas que usan este ingrediente
        recetas_resp = (
            db.table("recipes")
            .select("id, ingredients")
            .eq("business_id", business_id)
            .execute()
        )
        recetas = recetas_resp.data or []

        # Filtrar recetas que contienen el ingrediente
        recetas_con_ing = [
            r for r in recetas
            if ingredient_id in (r.get("ingredients") or {})
        ]

        consumo_teorico = Decimal("0")

        for receta in recetas_con_ing:
            pid = receta["id"]
            ing_info = receta["ingredients"][ingredient_id]

            # ing_info puede ser un número (qty) o un dict {"qty": x, "unit": y}
            if isinstance(ing_info, dict):
                qty_receta = Decimal(str(ing_info.get("qty", 0)))
                unidad_receta = ing_info.get("unit", unidad_base)
            else:
                qty_receta = Decimal(str(ing_info))
                unidad_receta = unidad_base

            # Ventas del producto en el rango desde pos_inputs
            ventas_resp = (
                db.table("pos_inputs")
                .select("quantity")
                .eq("business_id", business_id)
                .eq("product_id", pid)
                .gte("date", start_date)
                .lte("date", end_date)
                .execute()
            )
            ventas_rows = ventas_resp.data or []
            total_ventas = sum(Decimal(str(v["quantity"])) for v in ventas_rows)

            # Normalizar qty de receta a unidad base
            qty_receta_base = normalize_units(qty_receta, unidad_receta, unidad_base, conversions)
            if qty_receta_base is None:
                return CalcResult(
                    metric="merma",
                    value=None,
                    unit="%",
                    status="unit_mismatch",
                    context=(
                        f"Unidades incompatibles en receta de {pid}: "
                        f"'{unidad_receta}' no se puede convertir a '{unidad_base}'."
                    ),
                )

            consumo_teorico += total_ventas * qty_receta_base

        # --- 4. Calcular merma ---
        if total_comprado == Decimal("0"):
            return CalcResult(
                metric="merma",
                value=None,
                unit="%",
                status="incomplete_data",
                context="Total comprado es 0 — no se puede calcular merma.",
            )

        merma_abs = total_comprado - consumo_teorico
        merma_pct = (merma_abs / total_comprado * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        if merma_pct > Decimal("15"):
            status: CalcStatus = "critical"
        elif merma_pct > Decimal("5"):
            status = "warning"
        else:
            status = "ok"

        return CalcResult(
            metric="merma",
            value=merma_pct,
            unit="%",
            status=status,
            context=(
                f"Comprado: {total_comprado:.2f} {unidad_base}. "
                f"Consumo teórico: {consumo_teorico:.2f} {unidad_base}. "
                f"Merma: {merma_abs:.2f} {unidad_base} ({merma_pct:.1f}%)."
            ),
        )

    except Exception as exc:
        return CalcResult(
            metric="merma",
            value=None,
            unit="%",
            status="incomplete_data",
            context=f"Error al calcular merma para {ingredient_id}: {exc}",
        )


def calc_burn_rate(business_id: str, date: str, db: Any) -> CalcResult:
    """
    Calcula el Burn Rate diario del negocio (gasto promedio por día del mes).

    Fórmula:
        BR = sum(FIXED + VARIABLE expenses del mes) / days_in_month(date)

    Notas:
        - Usa days_in_month(date) como divisor, NUNCA 30 fijo.
        - Solo gastos con expense_behavior confirmado (FIXED o VARIABLE).
        - No hay umbrales de warning/critical — siempre "ok" si hay datos.
    """
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        primer_dia = dt.replace(day=1).strftime("%Y-%m-%d")
        ultimo_dia = dt.replace(day=days_in_month(date)).strftime("%Y-%m-%d")

        # --- 1. Gastos FIXED + VARIABLE del mes ---
        gastos_resp = (
            db.table("transactions")
            .select("amount, expense_behavior")
            .eq("business_id", business_id)
            .in_("expense_behavior", ["FIXED", "VARIABLE"])
            .gte("transaction_date", primer_dia)
            .lte("transaction_date", ultimo_dia)
            .execute()
        )
        gastos_rows = gastos_resp.data or []

        if not gastos_rows:
            return CalcResult(
                metric="burn_rate",
                value=None,
                unit="MXN/día",
                status="incomplete_data",
                context=(
                    f"No hay gastos FIXED o VARIABLE confirmados para {business_id} "
                    f"en {dt.strftime('%B %Y')}."
                ),
            )

        # --- 2. Sumar todos los gastos del mes ---
        total_gastos = sum(Decimal(str(r["amount"])) for r in gastos_rows)
        dias = Decimal(str(days_in_month(date)))

        burn_rate = (total_gastos / dias).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        # Desglose por tipo para el contexto
        total_fixed = sum(
            Decimal(str(r["amount"])) for r in gastos_rows if r["expense_behavior"] == "FIXED"
        )
        total_variable = sum(
            Decimal(str(r["amount"])) for r in gastos_rows if r["expense_behavior"] == "VARIABLE"
        )

        return CalcResult(
            metric="burn_rate",
            value=burn_rate,
            unit="MXN/día",
            status="ok",
            context=(
                f"Gastos del mes ({dt.strftime('%B %Y')}): "
                f"Fijos {total_fixed:.2f} MXN + Variables {total_variable:.2f} MXN "
                f"= {total_gastos:.2f} MXN / {int(dias)} días = {burn_rate:.2f} MXN/día."
            ),
        )

    except Exception as exc:
        return CalcResult(
            metric="burn_rate",
            value=None,
            unit="MXN/día",
            status="incomplete_data",
            context=f"Error al calcular burn rate para {business_id}: {exc}",
        )


def check_price_inflation(ingredient_id: str, business_id: str, db: Any) -> CalcResult:
    """
    Detecta inflación de precio en un ingrediente comparando la última factura
    contra el promedio histórico de facturas anteriores.

    Fórmula:
        delta_pct = ((precio_ultima - precio_promedio_anteriores) / precio_promedio_anteriores) × 100

    Umbrales:
        - critical : delta_pct > 15%
        - warning  : delta_pct entre 5% y 15%
        - ok       : delta_pct <= 5%
    """
    try:
        # --- 1. Obtener todas las facturas del ingrediente, más reciente primero ---
        facturas_resp = (
            db.table("transactions")
            .select("unit_price, transaction_date")
            .eq("business_id", business_id)
            .eq("ingredient_id", ingredient_id)
            .order("transaction_date", desc=True)
            .execute()
        )
        facturas = facturas_resp.data or []

        # Se necesitan al menos 2 facturas para comparar
        if len(facturas) < 2:
            return CalcResult(
                metric="inflacion_precio",
                value=None,
                unit="%",
                status="incomplete_data",
                context=(
                    f"Solo {len(facturas)} factura(s) para {ingredient_id}. "
                    "Se necesitan al menos 2 para detectar inflación."
                ),
            )

        # --- 2. Precio de la última factura y promedio de las anteriores ---
        precio_ultima = Decimal(str(facturas[0]["unit_price"]))
        fecha_ultima = facturas[0]["transaction_date"]

        precios_anteriores = [
            Decimal(str(f["unit_price"])) for f in facturas[1:]
            if f.get("unit_price") is not None
        ]

        if not precios_anteriores:
            return CalcResult(
                metric="inflacion_precio",
                value=None,
                unit="%",
                status="incomplete_data",
                context="Las facturas anteriores no tienen precio unitario registrado.",
            )

        precio_promedio = sum(precios_anteriores) / Decimal(str(len(precios_anteriores)))

        if precio_promedio == Decimal("0"):
            return CalcResult(
                metric="inflacion_precio",
                value=None,
                unit="%",
                status="incomplete_data",
                context="El precio promedio histórico es 0 — no se puede calcular delta.",
            )

        # --- 3. Calcular delta y evaluar umbrales ---
        delta_pct = (
            (precio_ultima - precio_promedio) / precio_promedio * Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        delta_abs = abs(delta_pct)

        if delta_abs > Decimal("15"):
            status: CalcStatus = "critical"
        elif delta_abs > Decimal("5"):
            status = "warning"
        else:
            status = "ok"

        return CalcResult(
            metric="inflacion_precio",
            value=delta_pct,
            unit="%",
            status=status,
            context=(
                f"Última factura ({fecha_ultima}): {precio_ultima:.2f} MXN. "
                f"Promedio histórico ({len(precios_anteriores)} facturas): {precio_promedio:.2f} MXN. "
                f"Variación: {delta_pct:+.1f}%."
            ),
        )

    except Exception as exc:
        return CalcResult(
            metric="inflacion_precio",
            value=None,
            unit="%",
            status="incomplete_data",
            context=f"Error al calcular inflación de precio para {ingredient_id}: {exc}",
        )


def calc_cash_reconciliation(business_id: str, date: str, db: Any) -> CalcResult:
    """
    Concilia el efectivo del día comparando lo esperado (POS) vs lo contado físicamente.

    Fórmula:
        expected_cash = initial_float + pos_cash_sales - refunds - cash_payouts
        variance      = actual_cash_counted - expected_cash
        variance_pct  = variance / pos_cash_sales × 100  (si pos_cash_sales > 0)

    Fuentes de datos:
        - pos_inputs  : cash_sales, refunds del día
        - cash_counts : initial_float, actual_counted, cash_payouts del día

    Umbrales:
        - critical : variance < -1% de pos_cash_sales (o variance < 0 si pos_cash_sales = 0)
        - warning  : variance < 0
        - ok       : variance >= 0
    """
    try:
        # --- 1. Datos del POS del día ---
        pos_resp = (
            db.table("pos_inputs")
            .select("cash_sales, refunds")
            .eq("business_id", business_id)
            .eq("date", date)
            .single()
            .execute()
        )
        pos_data = pos_resp.data

        if not pos_data:
            return CalcResult(
                metric="conciliacion_caja",
                value=None,
                unit="MXN",
                status="incomplete_data",
                context=f"Sin datos de POS para {business_id} el {date}.",
            )

        pos_cash_sales = Decimal(str(pos_data.get("cash_sales") or 0))
        refunds = Decimal(str(pos_data.get("refunds") or 0))

        # --- 2. Conteo físico de caja del día ---
        cash_resp = (
            db.table("cash_counts")
            .select("initial_float, actual_counted, cash_payouts")
            .eq("business_id", business_id)
            .eq("date", date)
            .single()
            .execute()
        )
        cash_data = cash_resp.data

        if not cash_data:
            return CalcResult(
                metric="conciliacion_caja",
                value=None,
                unit="MXN",
                status="incomplete_data",
                context=f"Sin conteo de caja registrado para {business_id} el {date}.",
            )

        initial_float = Decimal(str(cash_data.get("initial_float") or 0))
        actual_counted = Decimal(str(cash_data.get("actual_counted") or 0))
        cash_payouts = Decimal(str(cash_data.get("cash_payouts") or 0))

        # --- 3. Calcular varianza ---
        expected_cash = initial_float + pos_cash_sales - refunds - cash_payouts
        variance = actual_counted - expected_cash

        # --- 4. Evaluar umbrales ---
        if pos_cash_sales > Decimal("0"):
            variance_pct = (variance / pos_cash_sales * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            # critical: varianza negativa mayor al 1% de ventas en efectivo
            if variance_pct < Decimal("-1"):
                status: CalcStatus = "critical"
            elif variance < Decimal("0"):
                status = "warning"
            else:
                status = "ok"
            pct_context = f" ({variance_pct:+.2f}% de ventas en efectivo)"
        else:
            # Sin ventas en efectivo: usar varianza absoluta
            variance_pct = Decimal("0")
            if variance < Decimal("0"):
                status = "critical"
            else:
                status = "ok"
            pct_context = " (sin ventas en efectivo registradas)"

        return CalcResult(
            metric="conciliacion_caja",
            value=variance.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            unit="MXN",
            status=status,
            context=(
                f"Efectivo esperado: {expected_cash:.2f} MXN "
                f"(fondo inicial {initial_float:.2f} + ventas {pos_cash_sales:.2f} "
                f"- devoluciones {refunds:.2f} - pagos {cash_payouts:.2f}). "
                f"Contado: {actual_counted:.2f} MXN. "
                f"Varianza: {variance:+.2f} MXN{pct_context}."
            ),
        )

    except Exception as exc:
        return CalcResult(
            metric="conciliacion_caja",
            value=None,
            unit="MXN",
            status="incomplete_data",
            context=f"Error al conciliar caja para {business_id} el {date}: {exc}",
        )


# ===========================================================================
# ORQUESTADOR PRINCIPAL — run_calc_engine()
# Spec: s3_motor_calculo.md §Reglas de Oro
# ===========================================================================

def run_calc_engine(
    gatekeeper_result: Any,
    db: Any,
    date: str,
    business_id: str,
) -> CalcRunResult:
    """
    Orquesta todas las funciones de cálculo financiero para un negocio y fecha.

    Recibe el GatekeeperResult (output de S2) y ejecuta SOLO las métricas
    con status "active". Las métricas dormant/blocked se registran en
    skipped_metrics sin calcular.

    Flujo:
        1. Leer active_metrics del GatekeeperResult
        2. Para cada métrica active → ejecutar la función correspondiente
        3. Métricas dormant/blocked → agregar a skipped_metrics
        4. Persistir resultados en audit_results con node_id="S3"
        5. Retornar CalcRunResult

    Args:
        gatekeeper_result : GatekeeperResult (o dict compatible) de S2
        db                : cliente Supabase (inyección de dependencias)
        date              : YYYY-MM-DD del día a calcular
        business_id       : UUID del negocio

    Returns:
        CalcRunResult con results[], skipped_metrics[] y run_id
    """
    from uuid import uuid4
    from datetime import datetime, timezone

    run_id = str(uuid4())
    results: list[CalcResult] = []
    skipped: list[str] = []

    # Extraer active_metrics — soporta tanto objeto Pydantic como dict
    if isinstance(gatekeeper_result, dict):
        active_metrics: list[str] = gatekeeper_result.get("active_metrics", [])
        dormant_metrics = gatekeeper_result.get("dormant_metrics", [])
        blocked_metrics = gatekeeper_result.get("blocked_metrics", [])
    else:
        active_metrics = getattr(gatekeeper_result, "active_metrics", [])
        dormant_metrics = getattr(gatekeeper_result, "dormant_metrics", [])
        blocked_metrics = getattr(gatekeeper_result, "blocked_metrics", [])

    # Registrar métricas que no se calculan (dormant + blocked)
    for dm in dormant_metrics:
        metric_name = dm["metric"] if isinstance(dm, dict) else dm.metric
        skipped.append(metric_name)

    for bm in blocked_metrics:
        metric_name = bm["metric"] if isinstance(bm, dict) else bm.metric
        skipped.append(metric_name)

    # ---------------------------------------------------------------------------
    # Mapa métrica → función de cálculo
    # Cada función recibe (business_id, date, db) o variantes según el spec.
    # Las métricas que requieren IDs adicionales (product_id, ingredient_id)
    # se resuelven consultando los registros activos del negocio.
    # ---------------------------------------------------------------------------

    for metric in active_metrics:

        # --- cash_reconciliation ---
        if metric == "cash_reconciliation":
            result = calc_cash_reconciliation(business_id, date, db)
            results.append(result)

        # --- daily_break_even ---
        elif metric == "daily_break_even":
            result = calc_daily_break_even(business_id, date, db)
            results.append(result)

        # --- operative_cost_margin (burn_rate como proxy del margen operativo) ---
        elif metric == "operative_cost_margin":
            result = calc_burn_rate(business_id, date, db)
            # Renombrar métrica para alinear con el nombre del Gatekeeper
            results.append(
                CalcResult(
                    metric="operative_cost_margin",
                    value=result.value,
                    unit=result.unit,
                    status=result.status,
                    context=result.context,
                )
            )

        # --- health_score: calcula MC de todos los productos activos ---
        elif metric == "health_score":
            try:
                recetas_resp = (
                    db.table("recipes")
                    .select("id")
                    .eq("business_id", business_id)
                    .execute()
                )
                product_ids = [r["id"] for r in (recetas_resp.data or [])]

                if not product_ids:
                    results.append(
                        CalcResult(
                            metric="health_score",
                            value=None,
                            unit="MXN",
                            status="incomplete_data",
                            context="Sin recetas registradas para calcular health_score.",
                        )
                    )
                else:
                    # Calcular MC de cada producto y promediar
                    mc_results = [calc_contribution_margin(pid, db) for pid in product_ids]
                    mc_validos = [
                        r.value for r in mc_results
                        if r.value is not None and r.status in ("ok", "warning", "critical")
                    ]

                    if not mc_validos:
                        results.append(
                            CalcResult(
                                metric="health_score",
                                value=None,
                                unit="MXN",
                                status="incomplete_data",
                                context="No se pudo calcular MC de ningún producto.",
                            )
                        )
                    else:
                        mc_promedio = sum(mc_validos) / Decimal(str(len(mc_validos)))
                        # Determinar status por el peor resultado individual
                        worst = "ok"
                        for r in mc_results:
                            if r.status == "critical":
                                worst = "critical"
                                break
                            if r.status == "warning":
                                worst = "warning"
                        results.append(
                            CalcResult(
                                metric="health_score",
                                value=mc_promedio.quantize(
                                    Decimal("0.01"), rounding=ROUND_HALF_UP
                                ),
                                unit="MXN",
                                status=worst,
                                context=(
                                    f"MC promedio de {len(mc_validos)} producto(s): "
                                    f"{mc_promedio:.2f} MXN."
                                ),
                            )
                        )
            except Exception as exc:
                results.append(
                    CalcResult(
                        metric="health_score",
                        value=None,
                        unit="MXN",
                        status="incomplete_data",
                        context=f"Error al calcular health_score: {exc}",
                    )
                )

        # --- inventory_variance: merma de todos los ingredientes activos ---
        elif metric == "inventory_variance":
            try:
                # Obtener ingredientes únicos de todas las recetas del negocio
                recetas_resp = (
                    db.table("recipes")
                    .select("ingredients")
                    .eq("business_id", business_id)
                    .execute()
                )
                ingredient_ids: set[str] = set()
                for receta in (recetas_resp.data or []):
                    for ing_id in (receta.get("ingredients") or {}).keys():
                        ingredient_ids.add(ing_id)

                if not ingredient_ids:
                    results.append(
                        CalcResult(
                            metric="inventory_variance",
                            value=None,
                            unit="%",
                            status="incomplete_data",
                            context="Sin ingredientes en recetas para calcular merma.",
                        )
                    )
                else:
                    # Calcular merma del mes (inicio de mes → date)
                    dt = datetime.strptime(date, "%Y-%m-%d")
                    start_date = dt.replace(day=1).strftime("%Y-%m-%d")

                    waste_results = [
                        calc_waste_analysis(ing_id, start_date, date, business_id, db)
                        for ing_id in ingredient_ids
                    ]

                    # Agregar todos los resultados individuales
                    for wr in waste_results:
                        results.append(
                            CalcResult(
                                metric=f"inventory_variance_{wr.metric}",
                                value=wr.value,
                                unit=wr.unit,
                                status=wr.status,
                                context=wr.context,
                            )
                        )
            except Exception as exc:
                results.append(
                    CalcResult(
                        metric="inventory_variance",
                        value=None,
                        unit="%",
                        status="incomplete_data",
                        context=f"Error al calcular inventory_variance: {exc}",
                    )
                )

        else:
            # Métrica activa sin función implementada — registrar como incomplete_data
            results.append(
                CalcResult(
                    metric=metric,
                    value=None,
                    unit="",
                    status="incomplete_data",
                    context=f"Métrica '{metric}' activa pero sin función de cálculo implementada.",
                )
            )

    # ---------------------------------------------------------------------------
    # Persistir resultados en audit_results con node_id="S3"
    # ---------------------------------------------------------------------------
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        db.table("audit_results").insert(
            {
                "id": run_id,
                "business_id": business_id,
                "date": date,
                "pipeline_layer": "sequential",
                "node_id": "S3",
                "node_status": "completed",
                "result_data": {
                    "results": [r.model_dump(mode="json") for r in results],
                    "skipped_metrics": skipped,
                },
                "created_at": now_iso,
            }
        ).execute()
    except Exception:
        # La persistencia no debe bloquear el retorno de resultados
        pass

    return CalcRunResult(
        business_id=business_id,
        date=date,
        results=results,
        skipped_metrics=skipped,
        run_id=run_id,
    )
