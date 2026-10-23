"""Docker names, host ports, and upstream versions used by the Observability course.

The DOG stack (Doris, OpenTelemetry Collector, Grafana) and the OpenTelemetry
demo come from one pinned commit of the upstream ai-observe-stack repository.
The Compose override files in environments/dog-stack/ give every container,
network, and volume the ``doris-obs`` prefix and publish only the host ports
below, on 127.0.0.1, so this course can run next to the other courses.
Each host port can be changed by setting the environment variable named next
to it before starting Jupyter, for example ``DORIS_OBS_QUERY_PORT=29031``.
The Compose override files read the same variables with the same defaults.
"""

from __future__ import annotations

import os

from doris_labkit.docker import env_port

# Upstream DOG stack and demo. Update the Compose override files together with
# the commit: they name every upstream service.
STACK_REPOSITORY = "https://github.com/ai-observe/ai-observe-stack.git"
STACK_COMMIT = "2c1fbee831701178c7dddba857e88130ef292949"  # main on 2026-09-23
DORIS_IMAGE = "apache/doris:all-in-one-4.1.3"

# DOG core services: Compose project doris-obs (environments/dog-stack/compose.dog.yml).
PROJECT = "doris-obs"
NETWORK = "doris-obs"
DORIS_CONTAINER = "doris-obs"
COLLECTOR_CONTAINER = "doris-obs-otel-collector"
GRAFANA_CONTAINER = "doris-obs-grafana"
# The local mail server that receives Grafana's alert emails in Module 8.
MAILPIT_CONTAINER = "doris-obs-mailpit"
QUERY_PORT = env_port("DORIS_OBS_QUERY_PORT", 29030)  # forwards to FE query port 9030
HTTP_PORT = env_port("DORIS_OBS_HTTP_PORT", 28030)  # forwards to FE HTTP port 8030
BE_HTTP_PORT = env_port("DORIS_OBS_BE_HTTP_PORT", 28040)  # forwards to BE HTTP port 8040
GRAFANA_PORT = env_port("DORIS_OBS_GRAFANA_PORT", 23000)  # forwards to Grafana port 3000
OTLP_GRPC_PORT = env_port("DORIS_OBS_OTLP_GRPC_PORT", 24317)  # forwards to Collector port 4317
OTLP_HTTP_PORT = env_port("DORIS_OBS_OTLP_HTTP_PORT", 24318)  # forwards to Collector port 4318
MAILPIT_PORT = env_port("DORIS_OBS_MAILPIT_PORT", 28025)  # forwards to the Mailpit web inbox port 8025

# The Module 2 collectors, started with docker run on NETWORK. The trace collector
# also publishes its OTLP/HTTP receiver, so Module 2 sends its spans to it.
TRACE_COLLECTOR_CONTAINER = "doris-obs-traces2doris"
MODULE2_COLLECTORS = ("doris-obs-log2doris", "doris-obs-metric2doris", TRACE_COLLECTOR_CONTAINER)
TRACES_OTLP_HTTP_PORT = env_port("DORIS_OBS_TRACES_OTLP_HTTP_PORT", 24328)  # forwards to its port 4318

# The container that Module 8 starts with docker run to keep the CPUs busy for a few minutes.
CPU_LOAD_CONTAINER = "doris-obs-cpu-load"

# OpenTelemetry demo: Compose project doris-obs-demo (environments/dog-stack/compose.demo.yml).
# Its Collector also joins NETWORK and forwards the demo's telemetry to COLLECTOR_CONTAINER.
DEMO_PROJECT = "doris-obs-demo"
DEMO_NETWORK = "doris-obs-demo"
DEMO_PROXY_CONTAINER = "doris-obs-demo-frontend-proxy"
DEMO_PORT = env_port("DORIS_OBS_DEMO_PORT", 28082)  # forwards to the storefront proxy port 8080

# Litefuse for Module 7: Compose project doris-obs-litefuse (environments/litefuse/compose.litefuse.yml).
# It joins NETWORK and keeps its analytics tables in DORIS_CONTAINER, in LITEFUSE_DATABASE.
# The project, keys, and user are created when Litefuse first starts (LITEFUSE_INIT_* in
# the Compose file); Litefuse names the project's tables after LITEFUSE_PROJECT_ID.
LITEFUSE_PROJECT = "doris-obs-litefuse"
LITEFUSE_WEB_CONTAINER = "doris-obs-litefuse-web"
LITEFUSE_PORT = env_port("DORIS_OBS_LITEFUSE_PORT", 23100)  # forwards to the Litefuse web port 3000
LITEFUSE_DATABASE = "litefuse"
LITEFUSE_PROJECT_ID = "llm_app"
LITEFUSE_PUBLIC_KEY = "pk-lf-doris-course"
LITEFUSE_SECRET_KEY = "sk-lf-doris-course"
LITEFUSE_USER_EMAIL = "learner@example.com"
LITEFUSE_USER_PASSWORD = "doris-course-1"
# The address at which the other containers on NETWORK reach the Doris BE's HTTP port.
DORIS_BE_HTTP_ENDPOINT = f"{DORIS_CONTAINER}:8040"

# The local model for Module 7's optional lab: llama.cpp's server with a small open model,
# Compose project doris-obs-llm (environments/llm/compose.llm.yml). The model file is
# downloaded once into the project's volume, from a fixed commit of its Hugging Face
# repository; DORIS_OBS_LLM_MODEL_URL may point to the same file on a mirror.
LOCAL_MODEL_PROJECT = "doris-obs-llm"
LOCAL_MODEL_CONTAINER = "doris-obs-llm"
LOCAL_MODEL_PORT = env_port("DORIS_OBS_LLM_PORT", 28080)  # forwards to the llama.cpp server port 8080
LOCAL_MODEL = "qwen2.5-0.5b-instruct"  # the name under which the server offers the model
LOCAL_MODEL_FILE = "qwen2.5-0.5b-instruct-q4_k_m.gguf"  # Qwen2.5 0.5B Instruct, 4-bit, Apache 2.0
LOCAL_MODEL_SHA256 = "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db"
LOCAL_MODEL_URL = os.environ.get(
    "DORIS_OBS_LLM_MODEL_URL",
    "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/"
    f"9217f5db79a29953eb74d5343926648285ec7e67/{LOCAL_MODEL_FILE}",
)
