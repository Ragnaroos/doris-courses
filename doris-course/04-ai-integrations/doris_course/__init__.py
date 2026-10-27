"""Learner-facing support for the Apache Doris AI Integrations course."""

from .ai_functions import AiFunctionsLab

__all__ = ["AiFunctionsLab", "AiIntegrationsLab", "DorisLab"]


def __getattr__(name: str):
    """Load the MCP runtime only when a Module 01 notebook asks for it."""
    if name in {"AiIntegrationsLab", "DorisLab"}:
        from .lab import AiIntegrationsLab, DorisLab

        return {"AiIntegrationsLab": AiIntegrationsLab, "DorisLab": DorisLab}[name]
    raise AttributeError(name)
