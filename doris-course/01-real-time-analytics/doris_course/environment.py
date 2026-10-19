"""Docker names and host ports used by the Real-time Analytics course.

Every container, network, and volume starts with ``doris-rta`` and every host
port is in the 1xxxx range, so this course can run next to the other courses.
Each host port can be changed by setting the environment variable named next
to it before starting Jupyter, for example ``DORIS_RTA_QUERY_PORT=29030``.
Shell cells and Compose files read the same variables with the same defaults.
"""

from __future__ import annotations

from doris_labkit.docker import env_port

DORIS_IMAGE = "apache/doris:all-in-one-4.1.3"

# The single-node sandbox used by Modules 1-8 and 10.
DORIS_CONTAINER = "doris-rta"
DORIS_NETWORK = "doris-rta"
FE_VOLUME = "doris-rta-fe-meta"
BE_VOLUME = "doris-rta-be-storage"
QUERY_PORT = env_port("DORIS_RTA_QUERY_PORT", 19030)  # forwards to FE query port 9030
HTTP_PORT = env_port("DORIS_RTA_HTTP_PORT", 18030)  # forwards to FE HTTP port 8030
# The BE web server listens on this port inside the container too, so the
# address FE puts in a Stream Load redirect also works from the host.
BE_HTTP_PORT = env_port("DORIS_RTA_BE_HTTP_PORT", 18040)

# The Module 3 Kafka broker. Doris reaches it as kafka:29092 on DORIS_NETWORK.
KAFKA_CONTAINER = "doris-rta-kafka"
KAFKA_PORT = env_port("DORIS_RTA_KAFKA_PORT", 19092)

# The optional Metabase dashboard in Module 1.
METABASE_CONTAINER = "doris-rta-metabase"
METABASE_VOLUME = "doris-rta-metabase-data"
METABASE_PORT = env_port("DORIS_RTA_METABASE_PORT", 13000)

# The Module 9 multi-node cluster, Compose project doris-rta-m09.
M09_PROJECT = "doris-rta-m09"
M09_FE_QUERY_PORTS = {
    "fe-1": env_port("DORIS_RTA_M09_FE1_QUERY_PORT", 19130),
    "fe-2": env_port("DORIS_RTA_M09_FE2_QUERY_PORT", 19131),
    "fe-3": env_port("DORIS_RTA_M09_FE3_QUERY_PORT", 19132),
}
M09_FE_HTTP_PORTS = {
    "fe-1": env_port("DORIS_RTA_M09_FE1_HTTP_PORT", 18130),
    "fe-2": env_port("DORIS_RTA_M09_FE2_HTTP_PORT", 18131),
    "fe-3": env_port("DORIS_RTA_M09_FE3_HTTP_PORT", 18132),
}
M09_BE_HTTP_PORT = env_port("DORIS_RTA_M09_BE_HTTP_PORT", 18140)
M09_PROXY_PORT = env_port("DORIS_RTA_M09_PROXY_PORT", 19230)
M09_PROXY_STATS_PORT = env_port("DORIS_RTA_M09_PROXY_STATS_PORT", 18230)


def m09_container(service: str) -> str:
    """Return the container name Compose gives a Module 9 service, e.g. fe-1."""
    return f"{M09_PROJECT}-{service}-1"
