from .base_agent import BaseAgent, AgentResult


class BusinessHealthAgent(BaseAgent):
    """Calcula margen neto y genera insight según arquetipo del CEO."""

    module_name = "Salud del Negocio"
    archetype = "Operative Genius"

    def run(self, input_data: dict) -> AgentResult:
        revenue: float = input_data.get("revenue", 1)
        costs: float = input_data.get("costs", 0)
        archetype: str = input_data.get("archetype", "Operative Genius")

        margin = (revenue - costs) / revenue if revenue else 0
        raw = f"Margen de utilidad neta: {margin:.0%}."

        phrases = {
            "Operative Genius": (
                "Eres eficiente, pero la inconsistencia en extracciones de espresso "
                "está afectando tu recompra."
            ),
            "Product Purist": (
                "Tu margen refleja calidad, pero hay oportunidad de reducir merma "
                "sin sacrificar la experiencia del cliente."
            ),
            "Growth Hacker": (
                "Con este margen puedes escalar. Considera abrir un segundo turno "
                "antes de invertir en otro local."
            ),
        }

        phrase = phrases.get(archetype, phrases["Operative Genius"])

        return AgentResult(
            module=self.module_name,
            raw_result=raw,
            copilot_phrase=phrase,
            archetype=archetype,  # type: ignore[arg-type]
        )
