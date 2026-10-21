"""Host ports of the Data Warehousing course and the variables that change them.

Every port binds to 127.0.0.1. To use another port, set the variable named next
to it before starting Jupyter, for example ``DW_FE_QUERY_PORT=62030``. The
Compose files read the same variables with the same defaults, and the values
are read when a notebook starts or connects to a service, so a running kernel
picks up a changed variable only after a restart.
"""

from doris_labkit.docker import env_port

# The single-node sandbox of every Lab (environments/single-node/compose.yml).
SANDBOX_PORTS = {
    "DW_FE_QUERY_PORT": (52030, "FE MySQL protocol"),
    "DW_FE_HTTP_PORT": (51030, "FE HTTP (Web UI, Profiles)"),
    "DW_BE_HTTP_PORT": (51040, "BE HTTP (Stream Load)"),
}
# The Lab 4 lake environment (environments/lakehouse/compose.yml).
LAKE_PORTS = {
    "DW_LAKE_S3_PORT": (51900, "Lake object storage (Silo)"),
    "DW_LAKE_REST_PORT": (51818, "Iceberg REST Catalog"),
}


def port(variable):
    """Return the host port that ``variable`` sets, or the course default."""
    default, _ = {**SANDBOX_PORTS, **LAKE_PORTS}[variable]
    return env_port(variable, default)


def connection_settings():
    """Return the connection variables of the course sandbox for the configured ports."""
    return {
        "DW_HOST": "127.0.0.1",
        "DW_PORT": str(port("DW_FE_QUERY_PORT")),
        "DW_FE_HTTP_URL": f"http://127.0.0.1:{port('DW_FE_HTTP_PORT')}",
        "DW_BE_HTTP_URL": f"http://127.0.0.1:{port('DW_BE_HTTP_PORT')}",
        "DW_USER": "root",
        "DW_PASSWORD": "",
    }
