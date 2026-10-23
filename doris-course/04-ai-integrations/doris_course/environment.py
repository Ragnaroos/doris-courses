"""Docker names, host ports, and Doris objects used by the AI Integrations course.

The course runs its own single-container Doris sandbox. Its container,
network, and volumes start with ``doris-ai`` and its host ports are in the
3xxxx range, so this course can run next to the other courses. Each host port
can be changed by setting the environment variable named next to it before
starting Jupyter, for example ``DORIS_AI_QUERY_PORT=39031``.

A learner who already runs Doris 4.x can point the labs at it instead of the
sandbox: set ``DORIS_AI_HOST``, the three ports, and the administrator account
below, and skip the sandbox step. The labs then create the course database and
the read-only MCP account in that Doris.
"""

from __future__ import annotations

import os

from doris_labkit.docker import env_port

DORIS_IMAGE = "apache/doris:all-in-one-4.1.3"

# The single-node sandbox.
DORIS_CONTAINER = "doris-ai"
DORIS_NETWORK = "doris-ai"
FE_VOLUME = "doris-ai-fe-meta"
BE_VOLUME = "doris-ai-be-storage"
QUERY_PORT = env_port("DORIS_AI_QUERY_PORT", 39030)  # forwards to FE query port 9030
HTTP_PORT = env_port("DORIS_AI_HTTP_PORT", 38030)  # forwards to FE HTTP port 8030
# The BE web server listens on this port inside the container too, so the
# address the BE registers with the FE also works from this computer.
BE_HTTP_PORT = env_port("DORIS_AI_BE_HTTP_PORT", 38040)

# The Doris that the labs and the MCP Server connect to: the sandbox by default.
HOST = os.environ.get("DORIS_AI_HOST", "").strip() or "127.0.0.1"
ADMIN_USER = os.environ.get("DORIS_AI_ADMIN_USER", "").strip() or "root"
ADMIN_PASSWORD = os.environ.get("DORIS_AI_ADMIN_PASSWORD", "")

# The course data and the account that the MCP Server uses.
DATABASE = "ai_course"
TABLE = "events"
MCP_USER = "mcp_reader"
