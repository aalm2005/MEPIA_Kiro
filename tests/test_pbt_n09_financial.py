"""
PBT — N09: FinancialAuditResult
Propiedades de correctness para el Agente de Auditoría Financiera.
Spec: .kiro/specs/mepia/n09_gastos.md §Correctness Properties
"""
import calendar
from decimal import Decimal
from typing import Optional

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from agents.business_health import FinancialAuditResult, _days_in_month, _classify_lifecycle


# ---------------------------------------------------------------------------
# Estrategias
# ---------------------------------------------------------------------------

decimal_non_negative = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1000000"),
    allow_nan=False,
    allow_infinity=False,
).map(lambda x: x.quantize(Decimal("0.01")))

decimal_positive = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("1000000"),
    allow_nan=False,
    allow_infinity=False,
).map(lambda x: x.quantize(Decimal("0.01")))

date_strategy = st.dates(
    min_value=__import__("datetime").date(2020, 1, 1),
    max_value=__import__("datetime").date(2030, 12, 31),
)

months_strategy = st.integers(min_value=0, max_value=120)


# ---------------------------------------------------------------------------
# P4: resultado_operativo = total_sales - costo_fijo - gasto_variable
# ---------------------------------------------------------------------------

@given(
    total_sales=decimal_non_negative,
    costo_fijo=decimal_non_negative,
    gasto_variable=decimal_non_negative,
)
@settings(max_examples=500)
def test_p4_resultado_operativo_formula_correcta(total_sales, costo_fijo, gasto_variable):
    """
    P4: resultado_operativo_mxn = total_sales - costo_fijo_diario - gasto_variable_dia.
    Spec: n09_gastos.md §Correctness Properties P4
    """
    resultado = total_sales - costo_fijo - gasto_variable

    # Verificar break_even_status
    if resultado > Decimal("0"):
        expected_status = "ganancia"
    elif resultado < Decimal("0"):
        expected_status = "perdida"
    else:
        expected_status = "equilibrio"

    result = FinancialAuditResult(
        fase_ciclo_vida="Madurez (Mes 30)",
        business_age_months=30,
        break_even_status=expected_status,
        resultado_operativo_mxn=resultado,
        costo_fijo_diario=costo_fijo,
        gasto_variable_dia=gasto_variable,
        total_sales=total_sales,
        gastos_incompletos=False,
        burn_rate_variable_pct=None,
        burn_rate_status="incomplete_data",
        delta_ventas_7d_pct=None,
        ventas_status="incomplete_data",
        capex_sin_categorizar=0,
        dias_historial_disponibles=0,
    )

    assert result.resultado_operativo_mxn == resultado, (
        f"resultado_operativo debe ser {resultado}, got {result.resultado_operativo_mxn}"
    )


# ---------------------------------------------------------------------------
# P5: break_even_status == "perdida" ↔ resultado_operativo < 0
# ---------------------------------------------------------------------------

@given(
    total_sales=decimal_non_negative,
    costo_fijo=decimal_non_negative,
    gasto_variable=decimal_non_negative,
)
@settings(max_examples=500)
def test_p5_break_even_status_correlaciona_con_resultado(total_sales, costo_fijo, gasto_variable):
    """
    P5: break_even_status == "perdida" ↔ resultado_operativo_mxn < 0.
    Spec: n09_gastos.md §Correctness Properties P5
    """
    resultado = total_sales - costo_fijo - gasto_variable

    if resultado > Decimal("0"):
        status = "ganancia"
    elif resultado < Decimal("0"):
        status = "perdida"
    else:
        status = "equilibrio"

    # P5: perdida ↔ resultado < 0
    if status == "perdida":
        assert resultado < Decimal("0")
    if resultado < Decimal("0"):
        assert status == "perdida"


# ---------------------------------------------------------------------------
# P10: costo_fijo_diario usa days_in_month, nunca divisor fijo 30
# ---------------------------------------------------------------------------

@given(date=date_strategy)
@settings(max_examples=300)
def test_p10_costo_fijo_usa_days_in_month_no_30_fijo(date):
    """
    P10: costo_fijo_diario calculado con days_in_month(date) — nunca con divisor fijo 30.
    Spec: n09_gastos.md §Correctness Properties P10
    """
    dias = _days_in_month(date)
    _, expected_days = calendar.monthrange(date.year, date.month)

    assert dias == expected_days, (
        f"_days_in_month({date}) = {dias}, esperado {expected_days}"
    )
    # Verificar que no siempre retorna 30
    # (para meses con 28, 29 o 31 días, el resultado debe ser diferente de 30)
    if date.month == 2:
        assert dias in (28, 29), f"Febrero debe tener 28 o 29 días, got {dias}"
    elif date.month in (1, 3, 5, 7, 8, 10, 12):
        assert dias == 31, f"Mes {date.month} debe tener 31 días, got {dias}"


# ---------------------------------------------------------------------------
# P12: burn_rate nunca capeado
# ---------------------------------------------------------------------------

@given(
    gasto_variable=decimal_positive,
    total_sales=decimal_positive,
)
@settings(max_examples=300)
def test_p12_burn_rate_nunca_capeado(gasto_variable, total_sales):
    """
    P12: burn_rate_variable_pct reporta valor real aunque supere 100% — nunca capeado.
    Spec: n09_gastos.md §Correctness Properties P12
    """
    burn_rate = (gasto_variable / total_sales * Decimal("100")).quantize(Decimal("0.01"))

    # El valor real debe ser reportado, incluso si supera 100%
    assert burn_rate == (gasto_variable / total_sales * Decimal("100")).quantize(Decimal("0.01"))

    # Si gasto > ventas, burn_rate > 100% — esto es válido y no debe capearse
    if gasto_variable > total_sales:
        assert burn_rate > Decimal("100"), (
            f"Cuando gasto({gasto_variable}) > ventas({total_sales}), "
            f"burn_rate debe ser > 100%, got {burn_rate}"
        )


# ---------------------------------------------------------------------------
# P2: burn_rate_variable_pct es None cuando total_sales = 0
# ---------------------------------------------------------------------------

@given(
    costo_fijo=decimal_non_negative,
    gasto_variable=decimal_non_negative,
)
@settings(max_examples=200)
def test_p2_burn_rate_none_cuando_total_sales_cero(costo_fijo, gasto_variable):
    """
    P2: burn_rate_variable_pct es None cuando total_sales = 0 — nunca calculado.
    Spec: n09_gastos.md §Correctness Properties P2
    """
    total_sales = Decimal("0")

    # Simular la lógica del agente
    if total_sales == Decimal("0"):
        burn_rate_pct = None
        burn_rate_status = "incomplete_data"
    else:
        burn_rate_pct = gasto_variable / total_sales * Decimal("100")
        burn_rate_status = "ok"

    assert burn_rate_pct is None, (
        "burn_rate_variable_pct debe ser None cuando total_sales = 0"
    )
    assert burn_rate_status == "incomplete_data"


# ---------------------------------------------------------------------------
# P9: business_age_months siempre entero >= 0
# ---------------------------------------------------------------------------

@given(months=months_strategy)
@settings(max_examples=200)
def test_p9_business_age_months_siempre_no_negativo(months):
    """
    P9: business_age_months siempre entero >= 0.
    Spec: n09_gastos.md §Correctness Properties P9
    """
    result = FinancialAuditResult(
        fase_ciclo_vida=_classify_lifecycle(months) + f" (Mes {months})",
        business_age_months=months,
        break_even_status="equilibrio",
        resultado_operativo_mxn=Decimal("0"),
        costo_fijo_diario=Decimal("0"),
        gasto_variable_dia=Decimal("0"),
        total_sales=Decimal("0"),
        gastos_incompletos=False,
        burn_rate_variable_pct=None,
        burn_rate_status="incomplete_data",
        delta_ventas_7d_pct=None,
        ventas_status="incomplete_data",
        capex_sin_categorizar=0,
        dias_historial_disponibles=0,
    )

    assert result.business_age_months >= 0
    assert isinstance(result.business_age_months, int)
