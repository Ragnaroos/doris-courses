"""Shared learner-facing support for the Real-time Analytics course."""

__all__ = ["DorisLab"]


def __getattr__(name):
    # Quiz-only imports should not load database client dependencies.
    if name == "DorisLab":
        from .doris_client import DorisLab
        return DorisLab
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
