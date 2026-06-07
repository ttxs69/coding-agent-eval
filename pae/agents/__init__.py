"""Agent adapters for pae.

ADAPTERS is the registry used by get_adapter() and list_adapters(). New adapters
import their class and add an entry here.
"""

from pae.agents.base import AgentAdapter, AgentResult, UsageInfo
from pae.agents.mock import MockAdapter

ADAPTERS: dict[str, type[AgentAdapter]] = {
    "mock": MockAdapter,
}


def get_adapter(name: str, **kwargs: object) -> AgentAdapter:
    """Instantiate the named adapter or raise ValueError."""
    cls = ADAPTERS.get(name)
    if cls is None:
        available = ", ".join(ADAPTERS) or "(none)"
        raise ValueError(f"Unknown agent adapter: {name!r}. Available: {available}")
    return cls(**kwargs)


def list_adapters() -> list[dict[str, str | bool]]:
    """Return a list of {name, available} for every registered adapter."""
    result: list[dict[str, str | bool]] = []
    for name, cls in ADAPTERS.items():
        try:
            adapter = cls()
            available = adapter.is_available()
        except Exception:
            available = False
        result.append({"name": name, "available": available})
    return result


__all__ = ["AgentAdapter", "AgentResult", "UsageInfo", "ADAPTERS", "get_adapter", "list_adapters"]
