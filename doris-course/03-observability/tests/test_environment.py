"""Offline checks that every place naming a Docker resource or host port agrees."""

import json
import re
import unittest
from pathlib import Path

import yaml

from doris_course import environment
from doris_course.doris_client import CORE_PORTS, DEMO_PORTS, TRACE_COLLECTOR_PORTS

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT_DIR = ROOT / "environments/dog-stack"
MODULE2_LAB = ROOT / "level1/module02-data-ingest/lab02_ingest_observability_data.ipynb"
DEFAULTS = dict(re.findall(r'env_port\("(DORIS_OBS_\w+)", (\d+)\)', (ROOT / "doris_course/environment.py").read_text()))
SHELL_DEFAULT = re.compile(r"\$\{(DORIS_OBS_\w+):-(\d+)\}")
UPSTREAM = ROOT / ".runtime/ai-observe-stack"


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
        places = [(path, path.read_text()) for path in sorted(ENVIRONMENT_DIR.glob("compose*.yml"))]
        places += list(notebook_sources())
        seen = set()
        for path, text in places:
            for name, default in SHELL_DEFAULT.findall(text):
                with self.subTest(file=path.name, variable=name):
                    self.assertIn(name, DEFAULTS)
                    self.assertEqual(default, DEFAULTS[name])
                    seen.add(name)
        # Every host port is published by a Compose override file or a notebook cell.
        self.assertEqual(seen, set(DEFAULTS))

    def test_names_use_the_course_prefix(self):
        names = [environment.PROJECT, environment.NETWORK, environment.DORIS_CONTAINER,
                 environment.COLLECTOR_CONTAINER, environment.GRAFANA_CONTAINER,
                 environment.DEMO_PROJECT, environment.DEMO_NETWORK, environment.DEMO_PROXY_CONTAINER,
                 *environment.MODULE2_COLLECTORS]
        for name in names:
            self.assertTrue(name.startswith("doris-obs"), name)

    def test_default_host_ports_stay_in_the_course_range(self):
        ports = [int(value) for value in DEFAULTS.values()]
        self.assertEqual(len(ports), len(set(ports)))
        for port in ports:
            self.assertTrue(20000 <= port < 30000, port)

    def test_port_checks_cover_every_host_port(self):
        checked = {variable: port for port, variable, _purpose in CORE_PORTS + DEMO_PORTS + TRACE_COLLECTOR_PORTS}
        self.assertEqual(checked, {name: int(value) for name, value in DEFAULTS.items()})

    def test_dog_override_uses_the_python_names(self):
        compose = load_compose(ENVIRONMENT_DIR / "compose.dog.yml")
        services = compose["services"]
        self.assertEqual(services["doris"]["image"], environment.DORIS_IMAGE)
        self.assertEqual(services["doris"]["container_name"], environment.DORIS_CONTAINER)
        self.assertEqual(services["otel-collector"]["container_name"], environment.COLLECTOR_CONTAINER)
        self.assertEqual(services["grafana"]["container_name"], environment.GRAFANA_CONTAINER)
        self.assertEqual(compose["networks"]["aiobs-net"]["name"], environment.NETWORK)
        for name, service in services.items():
            with self.subTest(service=name):
                # !override replaces the upstream list, which binds every interface.
                self.assertEqual(service["ports"]["tag"], "!override")
                for binding in service["ports"]["value"]:
                    self.assertTrue(binding.startswith("127.0.0.1:"), binding)

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
                self.assertEqual(exporter["mysql_endpoint"], f"{environment.DORIS_CONTAINER}:9030")
                # The DOG Collector writes UTC into the same tables, which partition by UTC days.
                self.assertEqual(exporter["timezone"], "UTC")

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
        pairs = (("docker/docker-compose.yaml", "compose.dog.yml"),
                 ("doris-opentelemetry-demo/docker-compose.yml", "compose.demo.yml"))
        for upstream_file, override_file in pairs:
            upstream = load_compose(UPSTREAM / upstream_file)["services"]
            override = load_compose(ENVIRONMENT_DIR / override_file)["services"]
            with self.subTest(override=override_file):
                self.assertEqual(set(upstream), set(override))
                for name, service in upstream.items():
                    if service.get("ports"):
                        self.assertIn("ports", override[name], name)


if __name__ == "__main__":
    unittest.main()
