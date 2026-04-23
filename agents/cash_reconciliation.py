from .base_agent import BaseAgent, AgentResult


class CashReconciliationAgent(BaseAgent):
    """Compara tickets POS vs depósitos reportados y detecta discrepancias."""

    module_name = "Conciliación de Caja"
    archetype = "Operative Genius"

    def run(self, input_data: dict) -> AgentResult:
        pos_total: float = input_data.get("pos_total", 0)
        deposit: float = input_data.get("deposit", 0)
        diff = deposit - pos_total

        if diff == 0:
            raw = "Sin discrepancias. POS y depósito coinciden."
            phrase = "Tu caja está cuadrada. Buen control operativo hoy."
        else:
            raw = f"Discrepancia detectada: {diff:+.2f} MXN vs Ticket POS."
            phrase = (
                "Hay una fuga en el flujo de efectivo. "
                "Los tickets marcados no coinciden con el depósito reportado."
            )

        return AgentResult(
            module=self.module_name,
            raw_result=raw,
            copilot_phrase=phrase,
            archetype=self.archetype,
        )
