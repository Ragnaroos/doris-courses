"""Offline checks that every place naming a Docker resource or host port agrees."""

import json
import os
import re
import unittest
from pathlib import Path

import yaml

from doris_course import environment
from doris_course.doris_client import (
    CORE_PORTS,
    DEMO_PORTS,
    LITEFUSE_COMPOSE_FILE,
    LITEFUSE_PORTS,
    LOCAL_MODEL_COMPOSE_FILE,
    LOCAL_MODEL_PORTS,
    TRACE_COLLECTOR_PORTS,
)

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT_DIR = ROOT / "environments/dog-stack"
LITEFUSE_COMPOSE = ROOT / LITEFUSE_COMPOSE_FILE
LOCAL_MODEL_COMPOSE = ROOT / LOCAL_MODEL_COMPOSE_FILE
MODULE2_LAB = ROOT / "level1/module02-data-ingest/lab02_ingest_observability_data.ipynb"
DEFAULTS = dict(re.findall(r'env_port\("(DORIS_OBS_\w+)", (\d+)\)', (ROOT / "doris_course/environment.py").read_text()))
SHELL_DEFAULT = re.compile(r"\$\{(DORIS_OBS_\w+):-(\d+)\}")
UPSTREAM = ROOT / ".runtime/ai-observe-stack"
# Services that compose.dog.yml adds to the upstream DOG stack.
COURSE_SERVICES = {"mailpit"}
HOST_METRICS_CONFIG = "/etc/otelcol/collector-host-metrics.yaml"


class ComposeLoader(yaml.SafeLoader):
    """Reads Compose files and keeps the !reset and !override merge tags."""


def _tagged(loader, suffix, node):
    if isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    elif isinstance(node, yaml.MappingNode):
        value = loader.construct_mapping(node, deep=True)
    else:
        value = loader.construct_scalar(node)
    return {"tag": "!" + suffix, "value": value}


ComposeLoader.add_multi_constructor("!", _tagged)


def load_compose(path):
    return yaml.load(path.read_text(), Loader=ComposeLoader)


def notebook_sources():
    for path in sorted(ROOT.glob("level*/module*/*.ipynb")):
        for cell in json.loads(path.read_text())["cells"]:
            yield path, "".join(cell["source"])


class EnvironmentTests(unittest.TestCase):
    def test_compose_files_and_notebooks_use_the_python_defaults(self):
        places = [(path, path.read_text()) for path in sorted(ROOT.glob("environments/*/compose*.yml"))]
        places += list(notebook_sources())
        seen = set()
        for path, text in places:
            for name, default in SHELL_DEFAULT.findall(text):
                with self.subTest(file=path.name, variable=name):
                    self.assertIn(name, DEFAULTS)
                    self.assertEqual(default, DEFAULTS[name])
                    seen.add(name)
        # Every host port is published by a Compose file or a notebook cell.
        self.assertEqual(seen, set(DEFAULTS))

    def test_names_use_the_course_prefix(self):
        names = [environment.PROJECT, environment.NETWORK, environment.DORIS_CONTAINER,
                 environment.COLLECTOR_CONTAINER, environment.GRAFANA_CONTAINER, environment.MAILPIT_CONTAINER,
                 environment.DEMO_PROJECT, environment.DEMO_NETWORK, environment.DEMO_PROXY_CONTAINER,
                 *environment.MODULE2_COLLECTORS, environment.CPU_LOAD_CONTAINER,
                 environment.LITEFUSE_PROJECT, environment.LITEFUSE_WEB_CONTAINER,
                 environment.LOCAL_MODEL_PROJECT, environment.LOCAL_MODEL_CONTAINER]
        for name in names:
            self.assertTrue(name.startswith("doris-obs"), name)

    def test_default_host_ports_stay_in_the_course_range(self):
        ports = [int(value) for value in DEFAULTS.values()]
        self.assertEqual(len(ports), len(set(ports)))
        for port in ports:
            self.assertTrue(20000 <= port < 30000, port)

    def test_port_checks_cover_every_host_port(self):
        checked = {variable: port for port, variable, _purpose
                   in CORE_PORTS + DEMO_PORTS + TRACE_COLLECTOR_PORTS + LITEFUSE_PORTS + LOCAL_MODEL_PORTS}
        self.assertEqual(checked, {name: int(value) for name, value in DEFAULTS.items()})

    def test_dog_override_uses_the_python_names(self):
        compose = load_compose(ENVIRONMENT_DIR / "compose.dog.yml")
        services = compose["services"]
        self.assertEqual(services["doris"]["image"], environment.DORIS_IMAGE)
        self.assertEqual(services["doris"]["container_name"], environment.DORIS_CONTAINER)
        self.assertEqual(services["otel-collector"]["container_name"], environment.COLLECTOR_CONTAINER)
        self.assertEqual(services["grafana"]["container_name"], environment.GRAFANA_CONTAINER)
        self.assertEqual(services["mailpit"]["container_name"], environment.MAILPIT_CONTAINER)
        self.assertEqual(compose["networks"]["aiobs-net"]["name"], environment.NETWORK)
        for name, service in services.items():
            with self.subTest(service=name):
                if name in COURSE_SERVICES:
                    bindings = service["ports"]
                else:
                    # !override replaces the upstream list, which binds every interface.
                    self.assertEqual(service["ports"]["tag"], "!override")
                    bindings = service["ports"]["value"]
                for binding in bindings:
                    self.assertTrue(binding.startswith("127.0.0.1:"), binding)

    def test_grafana_sends_its_email_to_mailpit(self):
        services = load_compose(ENVIRONMENT_DIR / "compose.dog.yml")["services"]
        settings = dict(item.split("=", 1) for item in services["grafana"]["environment"])
        self.assertEqual(settings["GF_SMTP_ENABLED"], "true")
        # Mailpit listens for SMTP on port 1025 of the course network.
        self.assertEqual(settings["GF_SMTP_HOST"], f"{environment.MAILPIT_CONTAINER}:1025")
        mailpit = services["mailpit"]
        self.assertRegex(mailpit["image"], r"^axllent/mailpit:v\d+\.\d+\.\d+$")
        self.assertEqual(mailpit["networks"], ["aiobs-net"])

    def test_dog_collector_labels_its_host_metrics_with_the_host_name(self):
        collector = load_compose(ENVIRONMENT_DIR / "compose.dog.yml")["services"]["otel-collector"]
        # In the Docker host's UTS namespace, the system detector reads the host's name.
        # Upstream sets a fixed hostname, which Docker does not allow together with it.
        self.assertEqual(collector["uts"], "host")
        self.assertEqual(collector["hostname"]["tag"], "!reset")
        self.assertEqual(collector["command"]["tag"], "!override")
        self.assertEqual(collector["command"]["value"][-1], f"--config={HOST_METRICS_CONFIG}")
        self.assertIn("${DORIS_OBS_COURSE_ROOT:?set DORIS_OBS_COURSE_ROOT}/environments/dog-stack/"
                      f"collector-host-metrics.yml:{HOST_METRICS_CONFIG}:ro", collector["volumes"])
        config = yaml.safe_load((ENVIRONMENT_DIR / "collector-host-metrics.yml").read_text())
        self.assertEqual(config["processors"]["resourcedetection/host"]["detectors"], ["system"])
        pipelines = config["service"]["pipelines"]
        self.assertEqual(pipelines["metrics/host"]["receivers"], ["hostmetrics"])
        self.assertIn("resourcedetection/host", pipelines["metrics/host"]["processors"])
        self.assertEqual(pipelines["metrics/host"]["exporters"], ["doris"])
        # The demo's telemetry stays in the shared pipeline, without the Collector's host name.
        self.assertNotIn("hostmetrics", pipelines["metrics"]["receivers"])

    def test_demo_override_renames_every_container_and_publishes_only_the_storefront(self):
        compose = load_compose(ENVIRONMENT_DIR / "compose.demo.yml")
        services = compose["services"]
        names = [service["container_name"] for service in services.values()]
        self.assertEqual(len(names), len(set(names)))
        for name in names:
            self.assertTrue(name.startswith(environment.DEMO_PROJECT + "-"), name)
        proxy = services["frontend-proxy"]
        self.assertEqual(proxy["container_name"], environment.DEMO_PROXY_CONTAINER)
        self.assertEqual(proxy["ports"], {"tag": "!override", "value": ["127.0.0.1:${DORIS_OBS_DEMO_PORT:-28082}:8080"]})
        for name, service in services.items():
            if name != "frontend-proxy" and "ports" in service:
                self.assertEqual(service["ports"], {"tag": "!reset", "value": []}, name)
        self.assertEqual(compose["networks"]["default"]["name"], environment.DEMO_NETWORK)
        self.assertEqual(compose["networks"]["dog"], {"name": environment.NETWORK, "external": True})
        self.assertEqual(services["otel-collector"]["networks"], ["default", "dog"])

    def test_demo_collector_forwards_to_the_dog_collector(self):
        config = yaml.safe_load((ENVIRONMENT_DIR / "demo-collector-extras.yml").read_text())
        self.assertEqual(config["exporters"]["otlp/gateway"]["endpoint"], f"{environment.COLLECTOR_CONTAINER}:4317")

    def test_litefuse_uses_the_course_names_and_publishes_only_its_web_ui(self):
        compose = load_compose(LITEFUSE_COMPOSE)
        services = compose["services"]
        self.assertEqual(compose["networks"], {"doris-obs": {"name": environment.NETWORK, "external": True}})
        names = {name: service["container_name"] for name, service in services.items()}
        self.assertEqual(names["litefuse-web"], environment.LITEFUSE_WEB_CONTAINER)
        for name, service in services.items():
            with self.subTest(service=name):
                self.assertEqual(service["container_name"], f"{environment.LITEFUSE_PROJECT}-{name.split('-')[-1]}")
                self.assertEqual(service["networks"], ["doris-obs"])
                # Every image is pinned to a version: a tag other than latest, or a digest.
                self.assertRegex(service["image"], r"(:(?!latest$)[\w.-]+|@sha256:[0-9a-f]{64})$")
                if name != "litefuse-web":
                    self.assertNotIn("ports", service)
        self.assertEqual(services["litefuse-web"]["ports"], ["127.0.0.1:${DORIS_OBS_LITEFUSE_PORT:-23100}:3000"])

    def test_litefuse_settings_match_the_python_names(self):
        services = load_compose(LITEFUSE_COMPOSE)["services"]
        settings = services["litefuse-web"]["environment"]
        self.assertEqual(services["litefuse-worker"]["environment"], settings)
        container = {name: service["container_name"] for name, service in services.items()}
        # Litefuse keeps its tables in the DOG stack's Doris, reached by container name.
        self.assertEqual(settings["DORIS_FE_HTTP_URL"], f"http://{environment.DORIS_CONTAINER}:8030")
        self.assertEqual(settings["DORIS_DB"], environment.LITEFUSE_DATABASE)
        self.assertEqual(settings["DORIS_REPLICATION_NUM"], "1")
        self.assertEqual(settings["NEXTAUTH_URL"], "http://127.0.0.1:${DORIS_OBS_LITEFUSE_PORT:-23100}")
        self.assertIn(f"@{container['postgres']}:5432/", settings["DATABASE_URL"])
        self.assertEqual(settings["REDIS_HOST"], container["redis"])
        for kind in ("EVENT", "MEDIA"):
            self.assertEqual(settings[f"LITEFUSE_S3_{kind}_UPLOAD_ENDPOINT"], f"http://{container['silo']}:9000")
        self.assertEqual(settings["REDIS_AUTH"], services["redis"]["command"][1])
        self.assertEqual(settings["LITEFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID"],
                         services["silo"]["environment"]["MINIO_ROOT_USER"])
        self.assertEqual(settings["LITEFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY"],
                         services["silo"]["environment"]["MINIO_ROOT_PASSWORD"])
        # The project, keys, and user that the runtime and Lab 7 use.
        self.assertEqual(settings["LITEFUSE_INIT_PROJECT_ID"], environment.LITEFUSE_PROJECT_ID)
        # Litefuse names the project's tables after its ID and accepts only these characters.
        self.assertRegex(environment.LITEFUSE_PROJECT_ID, r"^[A-Za-z0-9_]+$")
        self.assertEqual(settings["LITEFUSE_INIT_PROJECT_PUBLIC_KEY"], environment.LITEFUSE_PUBLIC_KEY)
        self.assertEqual(settings["LITEFUSE_INIT_PROJECT_SECRET_KEY"], environment.LITEFUSE_SECRET_KEY)
        self.assertEqual(settings["LITEFUSE_INIT_USER_EMAIL"], environment.LITEFUSE_USER_EMAIL)
        self.assertEqual(settings["LITEFUSE_INIT_USER_PASSWORD"], environment.LITEFUSE_USER_PASSWORD)
        # Litefuse's sign-up rules: at least 8 characters with a letter, a digit, and another character.
        self.assertRegex(environment.LITEFUSE_USER_PASSWORD, r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z\d]).{8,}$")
        self.assertEqual(environment.DORIS_BE_HTTP_ENDPOINT, f"{environment.DORIS_CONTAINER}:8040")

    def test_the_llm_sdks_are_pinned(self):
        requirements = (ROOT / "requirements.txt").read_text().splitlines()
        for package in ("langfuse", "openai"):
            with self.subTest(package=package):
                pinned = [line for line in requirements if line.startswith(package)]
                self.assertEqual(len(pinned), 1)
                self.assertRegex(pinned[0], rf"^{package}==\d+\.\d+\.\d+$")
                self.assertIn(f'"{pinned[0]}"', (ROOT / "pyproject.toml").read_text())

    def test_local_model_server_is_pinned_and_serves_the_python_model(self):
        compose = load_compose(LOCAL_MODEL_COMPOSE)
        server = compose["services"]["llm"]
        self.assertEqual(list(compose["services"]), ["llm"])
        self.assertEqual(server["container_name"], environment.LOCAL_MODEL_CONTAINER)
        self.assertRegex(server["image"], r"^ghcr\.io/ggml-org/llama\.cpp:server-b\d+$")
        self.assertEqual(server["ports"], ["127.0.0.1:${DORIS_OBS_LLM_PORT:-28080}:8080"])
        self.assertEqual(server["volumes"], ["models:/models"])
        command = server["command"]
        # The server loads the file that start_local_model() downloads, under the name that requests use.
        self.assertEqual(command[command.index("--model") + 1], f"/models/{environment.LOCAL_MODEL_FILE}")
        self.assertEqual(command[command.index("--alias") + 1], environment.LOCAL_MODEL)
        self.assertRegex(environment.LOCAL_MODEL_SHA256, r"^[0-9a-f]{64}$")
        if "DORIS_OBS_LLM_MODEL_URL" not in os.environ:
            # The file comes from a fixed commit of its repository, not from a branch that can move.
            self.assertRegex(environment.LOCAL_MODEL_URL,
                             rf"^https://huggingface\.co/[\w.-]+/[\w.-]+/resolve/[0-9a-f]{{40}}/"
                             rf"{re.escape(environment.LOCAL_MODEL_FILE)}$")

    def test_module2_collectors_use_the_course_network_and_names(self):
        text = "\n".join(source for path, source in notebook_sources() if path == MODULE2_LAB)
        for name in environment.MODULE2_COLLECTORS:
            self.assertIn(f"--name {name} ", text)
        self.assertEqual(text.count(f"--network {environment.NETWORK} "), len(environment.MODULE2_COLLECTORS))
        for path in sorted(MODULE2_LAB.parent.glob("otel_for_*.yaml")):
            config = yaml.safe_load(path.read_text())
            exporter = config["exporters"]["doris"]
            with self.subTest(config=path.name):
                self.assertEqual(exporter["endpoint"], f"http://{environment.DORIS_CONTAINER}:8040")
                # The DOG Collector writes UTC into the same tables, which partition by UTC days.
                self.assertEqual(exporter["timezone"], "UTC")
                # The DOG Collector created the tables in Module 1. Settings that the exporter uses only
                # to create tables would have no effect, and creating the trace tables again would
                # reset the exporter's otel_traces_graph job.
                self.assertIs(exporter["create_schema"], False)
                for setting in ("mysql_endpoint", "history_days", "create_history_days", "replication_num"):
                    self.assertNotIn(setting, exporter)

    def test_module2_log_collector_reads_the_directory_and_keeps_its_read_position(self):
        config = yaml.safe_load((MODULE2_LAB.parent / "otel_for_logs.yaml").read_text())
        state = config["extensions"]["file_storage"]["directory"]
        self.assertEqual(config["service"]["extensions"], ["file_storage"])
        receiver = config["receivers"]["filelog"]
        self.assertEqual(receiver["storage"], "file_storage")
        # The FE rotates fe.log by renaming it; a mounted directory shows the new file, a mounted file does not.
        self.assertEqual(receiver["include"], ["/var/log/doris-fe/fe.log"])
        cell = next(source for path, source in notebook_sources()
                    if path == MODULE2_LAB and "--name doris-obs-log2doris " in source)
        self.assertIn('-v "$DORIS_FE_LOG_DIR:/var/log/doris-fe:ro"', cell)
        self.assertIn('STATE_DIR="$PWD/.runtime/collector-state/log2doris"', cell)
        self.assertIn(f'-v "$STATE_DIR:{state}"', cell)
        # The collector writes its read position to a directory of the learner's.
        self.assertIn('--user "$(id -u):$(id -g)"', cell)
        # A running collector saves its position only when it stops gracefully.
        self.assertLess(cell.index("docker stop doris-obs-log2doris"), cell.index("docker run"))
        self.assertNotIn("docker rm -f", cell)

    def test_module2_collectors_have_only_the_receivers_that_receive_data(self):
        metrics = yaml.safe_load((MODULE2_LAB.parent / "otel_for_metrics.yaml").read_text())
        # Nothing can reach an OTLP receiver whose port is not published.
        self.assertEqual(list(metrics["receivers"]), ["prometheus"])
        self.assertEqual(metrics["service"]["pipelines"]["metrics"]["receivers"], ["prometheus"])
        # Doris publishes no units; the course does not invent them.
        self.assertNotIn("transform", metrics.get("processors", {}))
        # With max_filter_ratio 1, a load that rejects every row still counts as a success.
        self.assertNotIn("max_filter_ratio", metrics["exporters"]["doris"].get("headers", {}))
        traces = yaml.safe_load((MODULE2_LAB.parent / "otel_for_traces.yaml").read_text())
        # Only OTLP/HTTP is published on the host (DORIS_OBS_TRACES_OTLP_HTTP_PORT).
        self.assertEqual(list(traces["receivers"]["otlp"]["protocols"]), ["http"])

    def test_doris_mounts_only_the_fe_log_directory(self):
        doris = load_compose(ENVIRONMENT_DIR / "compose.dog.yml")["services"]["doris"]
        logs = [volume for volume in doris["volumes"]["value"] if "/log" in volume]
        # Module 2 reads the FE log; nothing reads the BE log on the host.
        self.assertEqual(logs, ["${DORIS_OBS_COURSE_ROOT:?set DORIS_OBS_COURSE_ROOT}/.runtime/doris-logs/fe:"
                                "/opt/apache-doris/fe/log"])

    def test_module2_spans_go_to_the_trace_collector(self):
        """Lab 2 sends its span to doris-obs-traces2doris, not to the DOG Collector."""
        cells = [source for path, source in notebook_sources() if path == MODULE2_LAB]
        start = next(cell for cell in cells if f"--name {environment.TRACE_COLLECTOR_CONTAINER} " in cell)
        self.assertIn('-p "127.0.0.1:${DORIS_OBS_TRACES_OTLP_HTTP_PORT:-24328}:4318"', start)
        self.assertLess(start.index("lab.check_trace_collector_port()"), start.index("docker run"))
        send = next(cell for cell in cells if "OTLPSpanExporter(" in cell)
        self.assertIn('endpoint=f"{lab.trace_collector_url}/v1/traces"', send)
        self.assertIn("provider.force_flush()", send)
        text = "\n".join(cells)
        self.assertNotIn("lab.otlp_http_url", text)
        self.assertNotIn("%pip", text)
        # The check in Doris reads the attribute that only the trace collector adds.
        config = yaml.safe_load((MODULE2_LAB.parent / "otel_for_traces.yaml").read_text())
        self.assertIn("resource", config["service"]["pipelines"]["traces"]["processors"])
        added = [item["key"] for item in config["processors"]["resource"]["attributes"]]
        self.assertEqual(added, ["deployment.environment.name"])
        self.assertIn(f"resource_attributes['{added[0]}']", text)

    def test_notebooks_no_longer_name_the_old_resources(self):
        old = re.compile(r"docker_aiobs-net|--name (log2doris|metric2doris|traces2doris)\b|DORIS_CONTAINER:-doris\}"
                         r"|localhost:(3000|4318|8082)\b|127\.0\.0\.1:(8030|9030)\b")
        for path, text in notebook_sources():
            with self.subTest(notebook=path.name):
                self.assertIsNone(old.search(text))

    def test_overrides_cover_every_upstream_service(self):
        """Run after prepare_environment(); it catches upstream changes when the pinned commit moves."""
        head = UPSTREAM / ".git/HEAD"
        if not head.is_file() or head.read_text().strip() != environment.STACK_COMMIT:
            self.skipTest("the pinned DOG stack is not checked out in .runtime/")
        pairs = (("docker/docker-compose.yaml", "compose.dog.yml", COURSE_SERVICES),
                 ("doris-opentelemetry-demo/docker-compose.yml", "compose.demo.yml", set()))
        for upstream_file, override_file, added in pairs:
            upstream = load_compose(UPSTREAM / upstream_file)["services"]
            override = load_compose(ENVIRONMENT_DIR / override_file)["services"]
            with self.subTest(override=override_file):
                self.assertEqual(set(override), set(upstream) | added)
                for name, service in upstream.items():
                    if service.get("ports"):
                        self.assertIn("ports", override[name], name)
        # collector-host-metrics.yml restates the upstream metrics pipeline without hostmetrics.
        upstream = yaml.safe_load((UPSTREAM / "docker/otel-collector-config/otel-collector-config.yaml").read_text())
        course = yaml.safe_load((ENVIRONMENT_DIR / "collector-host-metrics.yml").read_text())["service"]["pipelines"]
        receivers = upstream["service"]["pipelines"]["metrics"]["receivers"]
        self.assertEqual(sorted(receivers), sorted(course["metrics"]["receivers"] + course["metrics/host"]["receivers"]))
        for processor in course["metrics/host"]["processors"]:
            if processor != "resourcedetection/host":
                self.assertIn(processor, upstream["processors"])
        self.assertIn("doris", upstream["exporters"])


if __name__ == "__main__":
    unittest.main()
