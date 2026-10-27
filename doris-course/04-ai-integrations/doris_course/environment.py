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

Module 2 adds a local model server, ``doris-ai-llm``, on the sandbox's network.
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

# Module 2's local model: the server of llama.cpp (MIT), which answers OpenAI's
# chat completions API, with Qwen2.5 1.5B Instruct (Apache 2.0), quantized to 4
# bits. The model file is downloaded once into LLM_VOLUME, from a fixed commit of
# its Hugging Face repository, and checked against its SHA-256;
# DORIS_AI_LLM_MODEL_URL may point to the same file on a mirror.
LLM_IMAGE = "ghcr.io/ggml-org/llama.cpp:server-b11429"
LLM_CONTAINER = "doris-ai-llm"
LLM_VOLUME = "doris-ai-llm-models"
LLM_PORT = env_port("DORIS_AI_LLM_PORT", 38080)  # forwards to the llama.cpp server port 8080
LLM_MODEL = "qwen2.5-1.5b-instruct"  # the name under which the server offers the model
LLM_MODEL_FILE = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
LLM_MODEL_BYTES = 1_117_320_736
LLM_MODEL_SHA256 = "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"
LLM_MODEL_URL = os.environ.get("DORIS_AI_LLM_MODEL_URL", "").strip() or (
    "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/"
    f"91cad51170dc346986eccefdc2dd33a9da36ead9/{LLM_MODEL_FILE}"
)
# The address that the Doris BE uses: the container's name on DORIS_NETWORK. A
# Doris that is not the sandbox needs an address that its own BE can reach.
LLM_ENDPOINT = os.environ.get("DORIS_AI_LLM_ENDPOINT", "").strip() or (
    f"http://{LLM_CONTAINER}:8080/v1/chat/completions"
)

# Module 2's tables and the AI Resource that its functions use.
TICKETS_TABLE = "support_tickets"
ENRICHMENT_TABLE = "ticket_enrichment"
AI_RESOURCE = "ai_course_llm"
