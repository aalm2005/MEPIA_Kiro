"""
N09 — Agente de Auditoría Operativa y Financiera (Layer 2)
Evalúa rentabilidad, burn rate y ciclo de vida del negocio.
LLM: gpt-4o-mini, temperatura 0.2 (solo para copilot_phrase — fallback: null).
Spec: .kiro/specs/mepia/n09_gastos.md
"""
from __future__ import annotations

import calendar
import os
from datetime import datetime, date as date_type, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Modelos de output
# ---------------------------------------------------------------------------

class FinancialAuditResult(BaseModel):
    """
    Resultado de las 3 heurísticas de N09 (Python puro, sin LLM).
    Spec: n09_gastos.md §FinancialAuditResult
    """
    fase_ciclo_vida: str
    business_age_months: int = Field(ge=0)
    break_even_status: Literal["ganancia", "perdida", "equilibrio"]
    resultado_operativo_mxn: Decimal
    costo_fijo_diario: Decimal = Field(ge=0)
    gasto_variable_dia: Decimal = Field(ge=0)
    total_sales: Decimal = Field(ge=0)
    gastos_incompletos: bool
    burn_rate_variable_pct: Optional[Decimal]   # None si total_sales = 0
    burn_rate_status: Literal["ok", "warning", "critical", "incomplete_data"]
    delta_ventas_7d_pct: Optional[Decimal]      # None si historial < 3 días
    ventas_status: Literal["ok", "warning", "critical", "incomplete_data"]
    capex_sin_categorizar: int = Field(ge=0)
    dias_historial_disponibles: int = Field(ge=0)


class AgentResult(BaseModel):
    """Output estándar de nodo paralelo. Spec: _glossary.md §AgentResult"""
    module: str
    raw_result: FinancialAuditResult
    copilot_phrase: Optional[str] = None
    archetype: str


class NodeResult(BaseModel):
    """Contrato de retorno de N09 hacia N06. Spec: n06_orchestrator_adk.md §NodeResult"""
    node_id: Literal["N09"]
    node_name: Literal["auditoria_financiera"]
    status: Literal["success", "timeout", "error"]
    result: Optional[AgentResult] = None
    warnings: list[str] = Field(default_factory=list)
    error_detail: Optional[str] = None
    duration_ms: int


# ---------------------------------------------------------------------------
# Helpers puros
# ---------------------------------------------------------------------------

def _days_in_month(d: date_type) -> int:
    """Días reales del mes — nunca 30 fijo. Respeta años bisiestos."""
    _, total = calendar.monthrange(d.year, d.month)
    return total


def _months_between(start: date_type, end: date_type) -> int:
    """Meses completos entre dos fechas. Retorna 0 si start >= end."""
    if start >= end:
        return 0
    return (end.year - start.year) * 12 + (end.month - start.month)


def _classify_lifecycle(months: int) -> str:
    """Clasifica la fase del ciclo de vida según meses de operación."""
    if months <= 2:
        return "Luna de miel"
    if months <= 6:
        return "Valle crítico"
    if months <= 17:
        return "Construcción lenta"
    if months <= 24:
        return "Break-even zone"
    return "Madurez"


# ---------------------------------------------------------------------------
# N09FinancialAuditAgent
# ---------------------------------------------------------------------------

class N09FinancialAuditAgent:
    """
    N09 — Agente de Auditoría Operativa y Financiera.
    Corre las 3 heurísticas en Python puro y genera copilot_phrase con gpt-4o-mini.
    Spec: n09_gastos.md
    """

    def __init__(self, supabase_client: Any) -> None:
        self._db = supabase_client

    def run(
        self,
        business_id: str,
        date_str: str,
        archetype: str,
        context_tags: Optional[dict] = None,
    ) -> NodeResult:
        """
        Ejecuta las 3 heurísticas y genera el NodeResult.
        Nunca lanza excepción — errores se capturan y retornan como status="error".
        """
        import time
        t0 = time.monotonic()

        try:
            audit_date = date_type.fromisoformat(date_str)
            result, warnings = self._run_heuristics(business_id, audit_date)

            # Generar copilot_phrase con gpt-4o-mini (fallback: None)
            copilot_phrase = self._generate_copilot_phrase(result, archetype, context_tags)

            duration_ms = int((time.monotonic() - t0) * 1000)
            return NodeResult(
                node_id="N09",
                node_name="auditoria_financiera",
                status="success",
                result=AgentResult(
                    module="auditoria_operativa",
                    raw_result=result,
                    copilot_phrase=copilot_phrase,
                    archetype=archetype,
                ),
                warnings=warnings,
                duration_ms=duration_ms,
            )

        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            return NodeResult(
                node_id="N09",
                node_name="auditoria_financiera",
                status="error",
                error_detail=str(exc),
                duration_ms=duration_ms,
            )

    # ------------------------------------------------------------------
    # Heurísticas (Python puro — sin LLM)
    # ------------------------------------------------------------------

    def _run_heuristics(
        self,
        business_id: str,
        audit_date: date_type,
    ) -> tuple[FinancialAuditResult, list[str]]:
        """Ejecuta las 3 heurísticas y retorna (FinancialAuditResult, warnings)."""
        warnings: list[str] = []
        date_str = audit_date.isoformat()

        # --- Datos base del negocio ---
        biz_resp = (
            self._db.table("businesses")
            .select("opening_date")
            .eq("id", business_id)
            .single()
            .execute()
        )
        if not biz_resp.data or not biz_resp.data.get("opening_date"):
            raise ValueError("missing opening_date")

        opening_date = date_type.fromisoformat(biz_resp.data["opening_date"])
        business_age_months = _months_between(opening_date, audit_date)
        fase = _classify_lifecycle(business_age_months)

        # --- Ventas del día ---
        pos_resp = (
            self._db.table("pos_inputs")
            .select("total_sales")
            .eq("business_id", business_id)
            .eq("date", date_str)
            .single()
            .execute()
        )
        total_sales = Decimal(str(pos_resp.data["total_sales"])) if pos_resp.data else Decimal("0")

        # --- Heurística A: Break-Even + Ciclo de Vida ---
        dias_mes = _days_in_month(audit_date)

        # Costos fijos desde business_fixed_costs
        fixed_resp = (
            self._db.table("business_fixed_costs")
            .select("expected_monthly_amount, expense_behavior")
            .eq("business_id", business_id)
            .eq("is_active", True)
            .execute()
        )
        fixed_rows = fixed_resp.data or []

        if not fixed_rows:
            warnings.append("Sin gastos fijos registrados — break-even no confiable")

        costo_fijo_mensual = sum(
            Decimal(str(r["expected_monthly_amount"])) for r in fixed_rows
        )
        costo_fijo_diario = (costo_fijo_mensual / Decimal(str(dias_mes))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        # Gastos variables del día (confirmados, sin needs_human_review)
        var_resp = (
            self._db.table("transactions")
            .select("amount")
            .eq("business_id", business_id)
            .eq("transaction_date", date_str)
            .eq("expense_behavior", "VARIABLE")
            .eq("needs_human_review", False)
            .execute()
        )
        gasto_variable_dia = sum(
            Decimal(str(r["amount"])) for r in (var_resp.data or [])
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Detectar gastos incompletos (facturas pendientes de revisión)
        pending_resp = (
            self._db.table("documents")
            .select("id")
            .eq("business_id", business_id)
            .eq("needs_human_review", True)
            .execute()
        )
        gastos_incompletos = bool(pending_resp.data)
        if gastos_incompletos:
            warnings.append("Gastos del día incompletos — hay facturas pendientes de revisión")

        resultado_operativo = (total_sales - costo_fijo_diario - gasto_variable_dia).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        if resultado_operativo > Decimal("0"):
            break_even_status: Literal["ganancia", "perdida", "equilibrio"] = "ganancia"
        elif resultado_operativo < Decimal("0"):
            break_even_status = "perdida"
            # Pérdida en madurez → critical warning
            if fase == "Madurez":
                warnings.append("Pérdida operativa en negocio maduro")
        else:
            break_even_status = "equilibrio"

        # --- Heurística B: Burn Rate Variable ---
        if total_sales == Decimal("0"):
            burn_rate_pct = None
            burn_rate_status: Literal["ok", "warning", "critical", "incomplete_data"] = "incomplete_data"
            warnings.append("Sin datos de ventas — burn rate no calculable")
        else:
            burn_rate_pct = (gasto_variable_dia / total_sales * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if burn_rate_pct > Decimal("100"):
                warnings.append("Burn rate variable supera el 100% — gastos mayores que ventas")
                burn_rate_status = "critical"
            elif burn_rate_pct > Decimal("50"):
                burn_rate_status = "critical"
            elif burn_rate_pct > Decimal("35"):
                burn_rate_status = "warning"
                warnings.append("Burn rate variable superior al 35% ideal")
            else:
                burn_rate_status = "ok"

        # --- Heurística C: Detección de Anomalías ---
        # C1: Caída de ventas vs promedio móvil 7 días anteriores
        from datetime import timedelta
        dias_anteriores_ventas: list[Decimal] = []
        for i in range(1, 8):
            prev_date = (audit_date - timedelta(days=i)).isoformat()
            prev_resp = (
                self._db.table("pos_inputs")
                .select("total_sales")
                .eq("business_id", business_id)
                .eq("date", prev_date)
                .execute()
            )
            for row in (prev_resp.data or []):
                v = Decimal(str(row["total_sales"]))
                if v > Decimal("0"):
                    dias_anteriores_ventas.append(v)

        dias_historial = len(dias_anteriores_ventas)

        if dias_historial < 3:
            delta_ventas_pct = None
            ventas_status: Literal["ok", "warning", "critical", "incomplete_data"] = "incomplete_data"
        else:
            promedio_7d = sum(dias_anteriores_ventas) / Decimal(str(dias_historial))
            if promedio_7d == Decimal("0"):
                delta_ventas_pct = None
                ventas_status = "incomplete_data"
            else:
                delta_ventas_pct = (
                    (total_sales - promedio_7d) / promedio_7d * Decimal("100")
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                if delta_ventas_pct < Decimal("-35"):
                    ventas_status = "critical"
                    warnings.append("Caída atípica de ventas vs promedio 7 días")
                elif delta_ventas_pct < Decimal("-20"):
                    ventas_status = "warning"
                    warnings.append("Caída atípica de ventas vs promedio 7 días")
                else:
                    ventas_status = "ok"

        # C2: CAPEX sin categorizar
        capex_resp = (
            self._db.table("transactions")
            .select("id")
            .eq("business_id", business_id)
            .eq("transaction_date", date_str)
            .eq("expense_behavior", "CAPEX")
            .is_("category", "null")
            .execute()
        )
        capex_sin_cat = len(capex_resp.data or [])
        if capex_sin_cat >= 1:
            warnings.append("CAPEX sin categorizar detectado")

        result = FinancialAuditResult(
            fase_ciclo_vida=f"{fase} (Mes {business_age_months})",
            business_age_months=business_age_months,
            break_even_status=break_even_status,
            resultado_operativo_mxn=resultado_operativo,
            costo_fijo_diario=costo_fijo_diario,
            gasto_variable_dia=gasto_variable_dia,
            total_sales=total_sales,
            gastos_incompletos=gastos_incompletos,
            burn_rate_variable_pct=burn_rate_pct,
            burn_rate_status=burn_rate_status,
            delta_ventas_7d_pct=delta_ventas_pct,
            ventas_status=ventas_status,
            capex_sin_categorizar=capex_sin_cat,
            dias_historial_disponibles=dias_historial,
        )
        return result, warnings

    # ------------------------------------------------------------------
    # Generación de copilot_phrase con gpt-4o-mini
    # ------------------------------------------------------------------

    def _generate_copilot_phrase(
        self,
        result: FinancialAuditResult,
        archetype: str,
        context_tags: Optional[dict],
    ) -> Optional[str]:
        """
        Genera copilot_phrase con gpt-4o-mini.
        Si el LLM falla → retorna None. El nodo sigue siendo "success" (P7).
        """
        try:
            from openai import OpenAI
            import json

            client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
            context_str = json.dumps(context_tags, ensure_ascii=False) if context_tags else "ninguno"

            prompt = f"""Eres el copiloto financiero de un restaurante con perfil CEO: {archetype}.
Genera UNA frase directa al dueño basada en estos datos financieros del día.

Datos:
- Fase del negocio: {result.fase_ciclo_vida}
- Resultado operativo: {result.resultado_operativo_mxn:.2f} MXN ({result.break_even_status})
- Costo fijo diario: {result.costo_fijo_diario:.2f} MXN
- Gasto variable: {result.gasto_variable_dia:.2f} MXN
- Ventas totales: {result.total_sales:.2f} MXN
- Burn rate variable: {result.burn_rate_variable_pct if result.burn_rate_variable_pct is not None else 'N/A'}% ({result.burn_rate_status})
- Variación ventas 7d: {result.delta_ventas_7d_pct if result.delta_ventas_7d_pct is not None else 'N/A'}% ({result.ventas_status})
- Gastos incompletos: {result.gastos_incompletos}
- Contexto del día: {context_str}

Reglas:
- Máximo 2 oraciones.
- Menciona el número exacto más relevante.
- Si hay pérdida, cuantifica en MXN.
- Si burn_rate es critical, incluye acción con plazo.
- Si gastos_incompletos=true, menciona que el análisis es parcial.
- PROHIBIDO frases genéricas como "debes mejorar" o "considera revisar"."""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.2,
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content.strip()

        except Exception:
            # P7: LLM falla → copilot_phrase: null, status sigue "success"
            return None


# ---------------------------------------------------------------------------
# Compatibilidad con código legacy (agents/__init__.py importa BusinessHealthAgent)
# ---------------------------------------------------------------------------

class BusinessHealthAgent:
    """
    Wrapper de compatibilidad para el código legacy que importa BusinessHealthAgent.
    Delega a N09FinancialAuditAgent cuando hay cliente Supabase disponible.
    """
    def run(self, payload: dict) -> Any:
        from dataclasses import dataclass

        @dataclass
        class LegacyResult:
            module: str
            raw_result: str
            copilot_phrase: str
            archetype: str

        revenue = payload.get("revenue", 0)
        costs = payload.get("costs", 0)
        archetype = payload.get("archetype", "Operative Genius")
        margin = ((revenue - costs) / revenue * 100) if revenue > 0 else 0

        return LegacyResult(
            module="Salud del Negocio",
            raw_result=f"Margen de utilidad neta: {margin:.1f}%",
            copilot_phrase=(
                f"Tu margen neto es {margin:.1f}%. "
                "Revisa los costos variables para optimizar la rentabilidad."
            ),
            archetype=archetype,
        )
