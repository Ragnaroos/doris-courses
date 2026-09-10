"""Profile-related entry points used by architecture and tuning labs."""

from typing import Any


def compare_profiles(lab: Any, *args: Any, **kwargs: Any):
    """Delegate a runtime-profile comparison to the shared lab session."""
    return lab.compare_profiles(*args, **kwargs)


__all__ = ["compare_profiles"]
