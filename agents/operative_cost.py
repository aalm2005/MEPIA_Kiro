from .base_agent import BaseAgent, AgentResult


class OperativeCostAgent(BaseAgent):
    """Detecta incrementos anómalos en insumos comparando períodos."""

    module_name = "Gasto Operativo"
    archetype = "Product Purist"

    THRESHOLD = 0.08  # 8% de incremento dispara alerta

    def run(self, input_data: dict) -> AgentResult:
        # input_data: {"item": str, "prev": float, "current": float}
        item: str = input_data.get("item", "insumo")
        prev: float = input_data.get("prev", 1)
        current: float = input_data.get("current", 1)

        pct = (current - prev) / prev if prev else 0

        if pct > self.THRESHOLD:
            raw = f"Incremento del {pct:.0%} en compra de {item}."
            phrase = (
                f"Tu costo de {item} está subiendo más rápido que tus ventas. "
                "Revisa el desperdicio en barra."
            )
        else:
            raw = f"Gasto en {item} estable ({pct:+.1%} vs período anterior)."
            phrase = f"El costo de {item} está bajo control. Sigue monitoreando."

        return AgentResult(
            module=self.module_name,
            raw_result=raw,
            copilot_phrase=phrase,
            archetype=self.archetype,
        )
