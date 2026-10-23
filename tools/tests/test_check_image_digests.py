"""Check tools/check_image_digests.py: the image list, the offline checks, and the registry protocol."""

import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from email.message import Message
from pathlib import Path
from unittest.mock import patch

TOOL = Path(__file__).resolve().parents[1] / "check_image_digests.py"
spec = importlib.util.spec_from_file_location("check_image_digests", TOOL)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

OLD = "sha256:" + "1" * 64
NEW = "sha256:" + "2" * 64
RECORD = f"""# Images

| Image | Used by | Digest |
| --- | --- | --- |
| `apache/doris:all-in-one-4.1.3` | Every Lab | `{OLD}` |
| `haproxy:3.0.30-alpine3.24` | Lab 9 | `{OLD}` |
| `ghcr.io/open-telemetry/demo:2.0.2-cart` | The demo | `{OLD}` |
| `redis:7.4.11` | Lab 7 | new |
"""


def make_repository(directory, files):
    root = Path(directory)
    for name, text in {"maintenance/images.md": RECORD, **files}.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    return root


def offline(files):
    with tempfile.TemporaryDirectory() as directory:
        root = make_repository(directory, files)
        return subprocess.run([sys.executable, str(TOOL), "--offline", "--root", str(root)],
                              capture_output=True, text=True)


def online(fetch, *arguments, files=None):
    with tempfile.TemporaryDirectory() as directory:
        root = make_repository(directory, files or {})
        output = io.StringIO()
        with redirect_stdout(output):
            status = tool.main(["--root", str(root), *arguments], fetch=fetch)
        return status, output.getvalue(), (root / "maintenance/images.md").read_text()


class ReferenceTests(unittest.TestCase):
    def test_references_name_their_registry(self):
        cases = {
            "haproxy:3.0.30-alpine3.24": ("registry-1.docker.io", "library/haproxy", "3.0.30-alpine3.24"),
            "valkey/valkey:8.1.10-alpine3.24": ("registry-1.docker.io", "valkey/valkey", "8.1.10-alpine3.24"),
            "ghcr.io/open-telemetry/demo:2.0.2-cart": ("ghcr.io", "open-telemetry/demo", "2.0.2-cart"),
            "quay.io/prometheus/prometheus:v3.2.0": ("quay.io", "prometheus/prometheus", "v3.2.0"),
            "localhost:5000/course/image:1.0.0": ("localhost:5000", "course/image", "1.0.0"),
        }
        for image, expected in cases.items():
            with self.subTest(image=image):
                self.assertEqual(tool.split_reference(image), expected)


class RegistryTests(unittest.TestCase):
    @staticmethod
    def response(headers=None, body=b""):
        message = Message()
        for key, value in (headers or {}).items():
            message[key] = value
        response = io.BytesIO(body)
        response.headers = message
        return response

    def test_an_anonymous_token_answers_the_registry_challenge(self):
        challenge = Message()
        challenge["WWW-Authenticate"] = ('Bearer realm="https://auth.example.test/token",'
                                         'service="registry.example.test",scope="repository:library/haproxy:pull"')
        requests = []

        def urlopen(request, timeout):
            requests.append(request)
            if isinstance(request, str):
                self.assertEqual(request, "https://auth.example.test/token?service=registry.example.test"
                                          "&scope=repository%3Alibrary%2Fhaproxy%3Apull")
                return self.response(body=b'{"token": "anonymous"}')
            if request.get_header("Authorization") is None:
                raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", challenge, None)
            self.assertEqual(request.get_method(), "HEAD")
            self.assertEqual(request.get_header("Authorization"), "Bearer anonymous")
            self.assertIn("application/vnd.oci.image.index.v1+json", request.get_header("Accept"))
            return self.response({"Docker-Content-Digest": NEW})

        with patch.object(tool.urllib.request, "urlopen", urlopen):
            self.assertEqual(tool.registry_digest("haproxy:3.0.30-alpine3.24"), NEW)
        self.assertEqual(requests[0].full_url,
                         "https://registry-1.docker.io/v2/library/haproxy/manifests/3.0.30-alpine3.24")
        self.assertEqual(len(requests), 3)

    def test_a_missing_tag_is_reported_as_none(self):
        def urlopen(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", Message(), None)

        with patch.object(tool.urllib.request, "urlopen", urlopen):
            self.assertIsNone(tool.registry_digest("minio/minio:RELEASE.2025-01-01T00-00-00Z"))

    def test_without_the_digest_header_the_manifest_is_hashed(self):
        def urlopen(request, timeout):
            return self.response(body=b"{}")

        with patch.object(tool.urllib.request, "urlopen", urlopen):
            self.assertEqual(tool.registry_digest("busybox:1.37.0"),
                             "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a")


class CompareTests(unittest.TestCase):
    def test_unchanged_images_pass(self):
        status, output, _ = online(lambda image: OLD,
                                   files={"maintenance/images.md": RECORD.replace("| new |", f"| `{OLD}` |")})
        self.assertEqual(status, 0, output)
        self.assertIn("4 image(s): 4 same, 0 changed, 0 new, 0 missing, 0 error", output)

    def test_changed_missing_new_and_failed_images_are_reported(self):
        answers = {"apache/doris:all-in-one-4.1.3": OLD, "haproxy:3.0.30-alpine3.24": NEW,
                   "ghcr.io/open-telemetry/demo:2.0.2-cart": None, "redis:7.4.11": RuntimeError("timed out")}

        def fetch(image):
            if isinstance(answers[image], Exception):
                raise answers[image]
            return answers[image]

        status, output, record = online(fetch)
        self.assertEqual(status, 1)
        self.assertIn(f"CHANGED  haproxy:3.0.30-alpine3.24: verified {OLD}, the registry now has {NEW} (used by Lab 9)",
                      output)
        self.assertIn("MISSING  ghcr.io/open-telemetry/demo:2.0.2-cart", output)
        self.assertIn("ERROR    redis:7.4.11: RuntimeError: timed out", output)
        self.assertEqual(record, RECORD)

    def test_update_writes_the_changed_and_new_digests_only(self):
        answers = {"apache/doris:all-in-one-4.1.3": OLD, "haproxy:3.0.30-alpine3.24": NEW,
                   "ghcr.io/open-telemetry/demo:2.0.2-cart": OLD, "redis:7.4.11": NEW}
        status, output, record = online(answers.get, "--update")
        self.assertEqual(status, 0, output)
        self.assertIn("Wrote 2 digest(s)", output)
        expected = (RECORD.replace(f"| `haproxy:3.0.30-alpine3.24` | Lab 9 | `{OLD}` |",
                                   f"| `haproxy:3.0.30-alpine3.24` | Lab 9 | `{NEW}` |")
                    .replace("| `redis:7.4.11` | Lab 7 | new |", f"| `redis:7.4.11` | Lab 7 | `{NEW}` |"))
        self.assertEqual(record, expected)

    def test_a_malformed_list_stops_before_asking_the_registries(self):
        def fetch(image):
            raise AssertionError("the registries must not be asked")

        status, output, _ = online(fetch, files={"maintenance/images.md": RECORD + "| `busybox` | Lab 8 | new |\n"
                                                 + f"| `redis:7.4.11` | Lab 7 | `{OLD}` |\n"})
        self.assertEqual(status, 1)
        self.assertIn("busybox is not an image name with a tag", output)
        self.assertIn("redis:7.4.11 is listed more than once", output)


class OfflineTests(unittest.TestCase):
    def test_listed_images_and_other_mentions_pass(self):
        result = offline({
            "doris-course/01/compose.yml": "services:\n  doris:\n    image: ${DORIS_IMAGE:-apache/doris:all-in-one-4.1.3}\n"
                                           "  proxy:\n    image: haproxy:3.0.30-alpine3.24\n    ports: !reset []\n"
                                           "  built:\n    build: .\n    image: doris-course-built:1.0.0\n",
            "doris-course/01/README.md": "Pull `haproxy:3.0.30-alpine3.24`. Then pull redis:7.4.11.\n"
                                         "The demo uses `ghcr.io/open-telemetry/demo:2.0.2-*` images.\n"
                                         "Redis listens on redis:6379, as user redis:redis.\n"
                                         "Another image whose name ends the same way: `example/haproxy:2.9.1`.\n",
            "doris-course/02/Dockerfile": "FROM redis:7.4.11\nRUN chown redis:redis /data\n",
        })
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("4 image(s) listed, 0 problem(s)", result.stdout)

    def test_unlisted_images_and_tags_fail(self):
        result = offline({
            "doris-course/01/compose.kafka.yml": "services:\n  kafka:\n    image: apache/kafka:3.9.1\n",
            "doris-course/02/Dockerfile": "FROM --platform=linux/amd64 flink:1.20.1-scala_2.12-java11 AS base\n",
            "doris-course/01/lab.ipynb": '{"cells": [{"source": ["docker pull haproxy:3.0-alpine\\n"]}]}\n',
        })
        self.assertEqual(result.returncode, 1)
        self.assertIn("doris-course/01/compose.kafka.yml pulls apache/kafka:3.9.1, which maintenance/images.md "
                      "does not list", result.stdout)
        self.assertIn("doris-course/02/Dockerfile pulls flink:1.20.1-scala_2.12-java11", result.stdout)
        self.assertIn("doris-course/01/lab.ipynb:1 names haproxy:3.0-alpine", result.stdout)

    def test_update_needs_the_registries(self):
        result = subprocess.run([sys.executable, str(TOOL), "--offline", "--update"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--update needs the registries", result.stderr)


if __name__ == "__main__":
    unittest.main()
