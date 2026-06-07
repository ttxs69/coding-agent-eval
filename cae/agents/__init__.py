"""Agent adapters for cae.

ADAPTERS is the registry used by get_adapter() and list_adapters(). New adapters
import their class and add an entry here.
"""

from cae.agents.aider import AiderAdapter
from cae.agents.base import AgentAdapter
from cae.agents.claude_code import ClaudeCodeAdapter
from cae.agents.codex import CodexAdapter
from cae.agents.mock import MockAdapter

ADAPTERS: dict[str, type[AgentAdapter]] = {
    "mock": MockAdapter,
    "claude-code": ClaudeCodeAdapter,
    "codex": CodexAdapter,
    "aider": AiderAdapter,
}


def get_adapter(name: str, **kwargs: object) -> AgentAdapter:
    """Instantiate the named adapter or raise ValueError."""
    cls = ADAPTERS.get(name)
    if cls is None:
        available = ", ".join(ADAPTERS) or "(none)"
        raise ValueError(f"Unknown agent adapter: {name!r}. Available: {available}")
    return cls(**kwargs)


def list_adapters() -> list[dict[str, str | bool]]:
    """Return a list of {name, available} for every registered adapter.

    `is_available()` should not normally raise, but the bare `except` is a safety
    net so a misbehaving adapter can't break the listing.
    """
    result: list[dict[str, str | bool]] = []
    for name, cls in ADAPTERS.items():
        try:
            adapter = cls()
            available = adapter.is_available()
        except Exception:
            available = False
        result.append({"name": name, "available": available})
    return result


__all__ = ["AgentAdapter", "ADAPTERS", "get_adapter", "list_adapters"]
