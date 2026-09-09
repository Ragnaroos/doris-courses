"""Kafka and Routine Load entry points used by continuous-loading labs."""

from typing import Any


def publish_batches(lab: Any, *args: Any, **kwargs: Any):
    """Publish observable Kafka batches through the shared lab session."""
    return lab.publish_kafka_batches(*args, **kwargs)


def routine_load_status(lab: Any, *args: Any, **kwargs: Any):
    """Read Routine Load state through the shared lab session."""
    return lab.routine_load_status(*args, **kwargs)


__all__ = ["publish_batches", "routine_load_status"]
