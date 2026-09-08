"""Docker lifecycle primitives shared by course environments."""

from .doris_client import (
    container_inspect,
    docker_exists,
    docker_preflight,
    ensure_network,
    ensure_volume,
    run,
    wait_for_health,
    wait_for_port,
)

__all__ = [
    "container_inspect",
    "docker_exists",
    "docker_preflight",
    "ensure_network",
    "ensure_volume",
    "run",
    "wait_for_health",
    "wait_for_port",
]
