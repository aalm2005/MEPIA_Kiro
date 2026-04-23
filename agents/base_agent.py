from dataclasses import dataclass
from typing import Literal

Archetype = Literal["Operative Genius", "Product Purist", "Growth Hacker"]


@dataclass
class AgentResult:
    module: str
    raw_result: str
    copilot_phrase: str
    archetype: Archetype


class BaseAgent:
    """Clase base para todos los agentes de auditoría MEPIA."""

    module_name: str = "Base"
    archetype: Archetype = "Operative Genius"

    def run(self, input_data: dict) -> AgentResult:
        raise NotImplementedError
