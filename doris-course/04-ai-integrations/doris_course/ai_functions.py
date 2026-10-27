"""Lab helpers for Module 2 of the AI Integrations course: Doris AI Functions.

``AiFunctionsLab`` uses the same Doris sandbox as Module 1 and adds what Module 2
needs: the local model server ``doris-ai-llm`` on the sandbox's network, the
support tickets, the AI Resource, and a measurement of the model work that each
statement causes, read from the model server's log and metrics.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd
import pymysql
import yaml
from pymysql.converters import escape_string

from doris_labkit import docker as labkit_docker
from doris_labkit.docker import container_inspect, ensure_network, ensure_volume, port_in_use, run
from doris_labkit.results import result_frame, show_frame
from doris_labkit.ui import card, progress_step, show_log, show_sql

from . import environment as env
from .lab import COURSE_DIR, AiIntegrationsLab, EnvironmentNotReady

TICKETS_SPEC = COURSE_DIR / "datasets/support_tickets.yaml"
# Doris needs about 3 GiB and the model server about 2.3 GiB; below this, Docker may stop one of them.
MIN_DOCKER_MEMORY = 6 * 2**30
LLM_CONTEXT_TOKENS = 8192
# The settings that the Lab's AI Resource gives every request.
RESOURCE_SETTINGS = (
    ("ai.temperature", "0"),
    ("ai.max_token", "256"),
    ("ai.max_retries", "1"),
    ("ai.retry_delay_second", "1"),
)
# One line of the model server's log for each request that it finished.
FINISHED_REQUEST = re.compile(r"\btotal time =")
METRIC = re.compile(r"^llamacpp:(\w+) ([0-9.eE+-]+)$", re.M)

# Download the model file into the volume of the model server, once, and check it.
# It runs in the server's image, which has curl and sha256sum; $0 is the URL.
DOWNLOAD_MODEL = r"""
set -e
model=/models/$MODEL_FILE
if [ -f "$model" ]; then
  echo "Already downloaded: $model"
else
  curl -fsSL -o "$model.part" "$0" &
  download=$!
  while kill -0 "$download" 2>/dev/null; do
    sleep 5
    echo "Downloaded $(( $(stat -c %s "$model.part" 2>/dev/null || echo 0) / 1000000 )) MB of $MODEL_MB MB"
  done
  if ! wait "$download"; then
    rm -f "$model.part"
    echo "The download failed. If $0 cannot be reached, set DORIS_AI_LLM_MODEL_URL to the same file on a mirror before starting Jupyter."
    exit 1
  fi
  mv "$model.part" "$model"
fi
echo "Checking the SHA-256 of $model"
if ! echo "$MODEL_SHA256  $model" | sha256sum -c -; then
  rm -f "$model"
  echo "The file is not the course's model file, so it was deleted. Rerun the cell to download it again."
  exit 1
fi
"""

# Doris's messages when a model's answer or the route to the model fails, and what they mean.
MODEL_ANSWER_ERRORS = re.compile(r"batch result|Invalid batch result format|AI returned empty result")
FAILURE_HINTS = (
    (MODEL_ANSWER_ERRORS,
     "The model's answer did not have the shape that Doris parses: one JSON array with one string for each "
     "row that Doris sent. Doris failed the whole statement, so no row got a value. Rerun the statement, or "
     "send fewer rows per request (section 4)."),
    (re.compile(r"Could not resolve host"),
     "The BE could not find the model server by its name. Start it with lab.start_model(), and check the "
     "endpoint of the Resource."),
    (re.compile(r"Couldn't connect|Connection refused|Failed to connect"),
     "Nothing answered at the Resource's endpoint, as seen from the BE. Inside the Doris container, "
     "127.0.0.1 is the container itself, not this computer."),
    (re.compile(r"timeout|timed out", re.I),
     "The request ran out of time. Doris gives an AI request only what is left of query_timeout."),
    (re.compile(r"AI resource .* does not exist|Please specify the AI Resource"),
     "The statement names no Resource that exists. Run lab.create_resource(), then rerun this cell."),
)


class AiFunctionsLab(AiIntegrationsLab):
    """Learner-facing helpers for Module 2: AI functions on support tickets with a local model."""

    def __init__(self, lab_dir: Path | None = None) -> None:
        self.tickets = yaml.safe_load(TICKETS_SPEC.read_text(encoding="utf-8"))
        self.session_variables: dict[str, Any] = {}
        super().__init__(lab_dir)

    def _show_ready(self) -> None:
        target = "the course sandbox" if self.uses_sandbox else "your own Doris"
        card(
            f"Doris: {env.HOST}:{env.QUERY_PORT} ({target}). Model server: {self.model_url} on this computer, "
            f"{env.LLM_ENDPOINT} for the Doris BE. AI Resource: {env.AI_RESOURCE}",
            "ok",
            "AI Functions lab tools are ready",
        )

    # ------------------------------------------------------------------ helpers

    @property
    def model_url(self) -> str:
        """The model server as this computer reaches it."""
        return f"http://127.0.0.1:{env.LLM_PORT}"

    @property
    def model_name(self) -> str:
        return env.LLM_MODEL

    @property
    def model_sha256(self) -> str:
        return env.LLM_MODEL_SHA256

    @staticmethod
    def _open_local(url: str, timeout: int = 10) -> str:
        """Read a URL of the model server on this computer, without a proxy in between."""
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=timeout) as response:
            return response.read().decode("utf-8")

    def _admin(self):
        fresh = self.connection is None
        connection = super()._admin()
        if fresh and self.session_variables:
            # A new connection starts with the defaults; set again what the Lab set before.
            with connection.cursor() as cursor:
                for name, value in self.session_variables.items():
                    cursor.execute(f"SET {name} = {value}")
            print("Set again on the new connection: " + ", ".join(
                f"{name} = {value}" for name, value in self.session_variables.items()), flush=True)
        return connection

    def set_session(self, **variables: Any) -> None:
        """Set session variables on the Lab's connection, and keep them for a new connection."""
        for name, value in variables.items():
            if not re.fullmatch(r"[a-z_]+", name):
                raise ValueError(f"{name!r} is not a session variable name.")
            literal = str(value) if isinstance(value, int) else "'" + str(value).replace("'", "''") + "'"
            self.sql(f"SET {name} = {literal}", title=f"Set {name} for this session")
            self.session_variables[name] = literal

    # ------------------------------------------------------------- model server

    def _check_model_port(self) -> None:
        state = container_inspect(env.LLM_CONTAINER)
        published = set()
        if state and state.get("State", {}).get("Running"):
            for bindings in (state.get("HostConfig", {}).get("PortBindings") or {}).values():
                published.update(int(item["HostPort"]) for item in bindings or [] if item.get("HostPort"))
        if env.LLM_PORT in published:
            status = "used by this course"
        elif port_in_use(env.LLM_PORT):
            status = "in use"
        else:
            status = "available"
        show_frame("Host port check", pd.DataFrame([{
            "host_port": env.LLM_PORT, "purpose": "Model server (llama.cpp)",
            "variable": "DORIS_AI_LLM_PORT", "status": status,
        }]))
        if status == "in use":
            self._failure(
                "Required port is unavailable",
                f"Another program is using {env.LLM_PORT} (DORIS_AI_LLM_PORT). Stop it, or set the variable to a "
                "free port before starting Jupyter, then rerun this cell.",
            )
            raise EnvironmentNotReady("the model server's host port is in use.")

    def _model_container_matches(self, state: Mapping[str, Any]) -> bool:
        bindings = (state.get("HostConfig", {}).get("PortBindings") or {}).get("8080/tcp") or [{}]
        mounts = {mount["Destination"]: mount.get("Name") for mount in state.get("Mounts", [])}
        return (
            state.get("Config", {}).get("Image") == env.LLM_IMAGE
            and (bindings[0].get("HostIp"), bindings[0].get("HostPort")) == ("127.0.0.1", str(env.LLM_PORT))
            and mounts.get("/models") == env.LLM_VOLUME
            and env.DORIS_NETWORK in state.get("NetworkSettings", {}).get("Networks", {})
        )

    def _check_docker_memory_for_model(self) -> None:
        info = run(["docker", "info", "--format", "{{.MemTotal}}"], check=False)
        try:
            memory = int(info.stdout.strip())
        except ValueError:
            return
        if memory < MIN_DOCKER_MEMORY:
            card(f"Docker can use {memory / 2**30:.1f} GiB of memory. Doris and the model server together need "
                 "about 5.5 GiB; give Docker at least 6 GiB if a container stops unexpectedly.", "info",
                 "Docker resources")
        else:
            card(f"Docker can use {memory / 2**30:.1f} GiB of memory; Doris and the model server need about "
                 "5.5 GiB together.", "ok", "Docker resources")

    def start_model(self, *, timeout_seconds: int = 180) -> None:
        """Download the course's model file once, check it, and serve it with llama.cpp's server.

        Returns once the server answers and lists the model. The model file is
        checked against its SHA-256 at every start.
        """
        steps = 4
        progress_step(1, steps, "Check Docker, its memory, and the host port")
        labkit_docker.ensure_docker_ready()
        self._check_docker_memory_for_model()
        self._check_model_port()
        existing = container_inspect(env.LLM_CONTAINER)
        if existing is not None and not self._model_container_matches(existing):
            self._failure(
                "Existing container conflict",
                f"A container named {env.LLM_CONTAINER} exists but does not use this course's image, port, volume, "
                f"or network, for example because it was created with another DORIS_AI_LLM_PORT. It was left "
                f"unchanged. Set the variable back, or remove it with `docker rm -f {env.LLM_CONTAINER}` (the "
                f"volume {env.LLM_VOLUME} keeps the model file) and rerun this cell.",
            )
            raise EnvironmentNotReady(f"a different container named {env.LLM_CONTAINER} exists.")

        progress_step(2, steps, "Create or reuse the Docker network and the volume for the model file")
        ensure_network(env.DORIS_NETWORK)
        ensure_volume(env.LLM_VOLUME)

        megabytes = round(env.LLM_MODEL_BYTES / 1_000_000)
        progress_step(3, steps, "Download the model file once and check its SHA-256",
                      f"{env.LLM_MODEL_FILE}, {megabytes:,} MB")
        if not labkit_docker.docker_exists("image", env.LLM_IMAGE):
            pull = run(["docker", "pull", env.LLM_IMAGE], check=False, stream=True, timeout=3600)
            if pull.returncode != 0:
                self._failure("Model server image pull failed",
                              "Check network or proxy access to ghcr.io, then rerun this cell.", pull.stdout)
                raise EnvironmentNotReady("the model server image could not be pulled.")
        show_sql("Where the model file comes from", f"{env.LLM_MODEL_URL}\nSHA-256 {env.LLM_MODEL_SHA256}")
        show_log("The download script, which runs in the model server's image", DOWNLOAD_MODEL.strip())
        command = [
            "docker", "run", "--rm", "--entrypoint", "sh", "-v", f"{env.LLM_VOLUME}:/models",
            "-e", f"MODEL_FILE={env.LLM_MODEL_FILE}", "-e", f"MODEL_SHA256={env.LLM_MODEL_SHA256}",
            "-e", f"MODEL_MB={megabytes}", env.LLM_IMAGE, "-c", DOWNLOAD_MODEL, env.LLM_MODEL_URL,
        ]
        shown = " ".join(command[:-3]) + f" -c '<the download script>' {env.LLM_MODEL_URL}"
        if self._stream(command, shown) != 0:
            self._failure("The model file is not ready",
                          "Read the output above. A failed download leaves nothing behind; rerun this cell to "
                          "try again.")
            raise EnvironmentNotReady("the model file could not be downloaded or checked.")

        progress_step(4, steps, "Start the model server", env.LLM_IMAGE)
        if existing is None:
            command = [
                "docker", "run", "-d", "--name", env.LLM_CONTAINER, "--network", env.DORIS_NETWORK,
                "-p", f"127.0.0.1:{env.LLM_PORT}:8080", "-v", f"{env.LLM_VOLUME}:/models", env.LLM_IMAGE,
                "--model", f"/models/{env.LLM_MODEL_FILE}", "--alias", env.LLM_MODEL,
                "--ctx-size", str(LLM_CONTEXT_TOKENS), "--parallel", "1", "--metrics",
            ]
            started = run(command, check=False, stream=True)
            if started.returncode != 0:
                self._failure("The model server did not start",
                              "Read the Docker output, correct the conflict, and rerun this cell.", started.stdout)
                raise EnvironmentNotReady("the model server did not start.")
        elif not existing.get("State", {}).get("Running"):
            run(["docker", "start", env.LLM_CONTAINER], show=True)
        else:
            card(f"Reusing the running container {env.LLM_CONTAINER}", "ok")
        self._wait_for_model_server(timeout_seconds)
        models = json.loads(self._open_local(f"{self.model_url}/v1/models")).get("data") or []
        show_frame("Models that the server offers (GET /v1/models)",
                   pd.DataFrame([{"model": item.get("id"), "owned_by": item.get("owned_by")} for item in models]))
        card(f"{env.LLM_MODEL} answers OpenAI's chat completions API at {self.model_url}/v1 on this computer. It "
             "runs on Docker's CPUs and needs no account or key.", "ok", "The local model is running")

    @staticmethod
    def _stream(command: Sequence[str], shown: str) -> int:
        """Run a command and print its output as it arrives, after ``shown`` in place of the command."""
        print("$ " + shown, flush=True)
        process = subprocess.Popen(list(command), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   bufsize=1)
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
        return process.wait()

    def _wait_for_model_server(self, timeout_seconds: int) -> None:
        """Wait until the model server answers GET /health; stop with its log when it exits or takes too long."""
        show_sql(f"Wait until the model server answers (every second, for up to {timeout_seconds} seconds)",
                 f'curl -s "{self.model_url}/health"')
        started = time.monotonic()
        while True:
            state = (container_inspect(env.LLM_CONTAINER) or {}).get("State", {})
            try:
                if json.loads(self._open_local(f"{self.model_url}/health", timeout=5)).get("status") == "ok":
                    break
            except (OSError, ValueError):
                pass
            if state.get("Status") in {"exited", "dead"} or time.monotonic() - started >= timeout_seconds:
                logs = run(["docker", "logs", "--tail", "60", env.LLM_CONTAINER], check=False)
                self._failure("The model server does not answer",
                              f"{self.model_url}/health did not answer within {timeout_seconds} seconds, or the "
                              f"container stopped. Read its log below or with docker logs {env.LLM_CONTAINER}; a "
                              "server that stops at once often lacks memory (see Docker resources above). Then "
                              "rerun this cell.", logs.stdout + logs.stderr)
                raise EnvironmentNotReady("the model server did not answer.")
            time.sleep(1)
        print(f"The model server answered after {time.monotonic() - started:.0f} seconds.", flush=True)

    def stop_model(self) -> None:
        """Stop the model server; the container and the downloaded model file stay for lab.start_model()."""
        if container_inspect(env.LLM_CONTAINER) is None:
            card(f"There is no {env.LLM_CONTAINER} container.", "skip", "Nothing to stop")
            return
        run(["docker", "stop", env.LLM_CONTAINER], show=True)
        card(f"{env.LLM_CONTAINER} is stopped; the volume {env.LLM_VOLUME} keeps the model file. Run "
             "lab.start_model() to continue. AI functions fail until it runs again.", "ok", "Model server stopped")

    def check_model_routes(self) -> None:
        """Ask the model server for its models from this computer and from inside the Doris container."""
        rows = []
        try:
            served = json.loads(self._open_local(f"{self.model_url}/v1/models")).get("data") or []
            answer = "answers: " + ", ".join(str(item.get("id")) for item in served)
        except (OSError, ValueError) as error:
            answer = f"no answer: {error}"
        rows.append({"from": "this computer (the notebook)", "address": f"{self.model_url}/v1/models",
                     "result": answer})
        if not self.uses_sandbox or container_inspect(env.DORIS_CONTAINER) is None:
            show_frame("The model server, asked from this computer", pd.DataFrame(rows))
            card(f"With your own Doris, its BE must reach {env.LLM_ENDPOINT}. The first AI function in section 3 "
                 "tests that route.", "info", "Route from the BE not checked")
            return
        endpoint_models = env.LLM_ENDPOINT.replace("/chat/completions", "/models")
        be_results = {}
        for address in (endpoint_models, f"http://127.0.0.1:{env.LLM_PORT}/v1/models",
                        "http://127.0.0.1:8080/v1/models"):
            probe = run(["docker", "exec", env.DORIS_CONTAINER, "curl", "-s", "-m", "5", "-o", "/dev/null",
                         "-w", "%{http_code}", address], check=False)
            code = probe.stdout.strip()
            be_results[address] = (f"HTTP {code}" if probe.returncode == 0 and code != "000"
                                   else f"no answer (curl exit code {probe.returncode})")
            rows.append({"from": f"the Doris BE ({env.DORIS_CONTAINER} container)", "address": address,
                         "result": be_results[address]})
        show_frame("The same model server, asked from two places", pd.DataFrame(rows))
        if be_results[endpoint_models] == "HTTP 200":
            card(f"The BE reaches the model server at {env.LLM_ENDPOINT}: its name on the {env.DORIS_NETWORK} "
                 "network. The Resource must use that address, not the one this computer uses.", "ok",
                 "Use the address that the BE can reach")
        else:
            self._failure("The BE cannot reach the model server",
                          f"Start both with lab.prepare_environment() and lab.start_model(); they must share the "
                          f"{env.DORIS_NETWORK} network.")
            raise EnvironmentNotReady("the Doris container cannot reach the model server.")

    # ------------------------------------------------------- model work done

    def _measurable(self) -> bool:
        """True when the Resource's endpoint is this course's model server, whose work the Lab can read."""
        endpoint = env.LLM_ENDPOINT
        return env.LLM_CONTAINER in endpoint or f":{env.LLM_PORT}/" in endpoint

    def _model_counters(self) -> dict[str, float | None] | None:
        """The model server's totals so far: finished requests, and the tokens it read and wrote."""
        if not self._measurable():
            return None
        logs = run(["docker", "logs", env.LLM_CONTAINER], check=False)
        if logs.returncode != 0:
            return None
        try:
            metrics = {name: float(value) for name, value in METRIC.findall(self._open_local(
                f"{self.model_url}/metrics", timeout=5))}
        except (OSError, ValueError):
            metrics = {}
        counters: dict[str, float | None] = {"requests": len(FINISHED_REQUEST.findall(logs.stdout + logs.stderr))}
        if "prompt_tokens_total" in metrics:
            # The server reuses the start of a prompt that it has seen; the prompt is both parts.
            counters["prompt_tokens"] = metrics["prompt_tokens_total"] + metrics.get("prompt_tokens_cached_total", 0)
            counters["generated_tokens"] = metrics.get("tokens_predicted_total", 0)
        else:
            counters["prompt_tokens"] = counters["generated_tokens"] = None
        return counters

    @staticmethod
    def model_work(before: Mapping[str, float | None] | None, after: Mapping[str, float | None] | None,
                   seconds: float) -> dict[str, Any]:
        """The difference between two readings of the model server's totals, for one table row."""
        def change(name: str) -> int | str:
            if before is None or after is None or before.get(name) is None or after.get(name) is None:
                return "not measured"
            return int(after[name] - before[name])
        return {"model requests": change("requests"), "prompt tokens": change("prompt_tokens"),
                "generated tokens": change("generated_tokens"), "seconds": f"{seconds:.1f}"}

    def _explain_failure(self, message: str) -> tuple[str, bool]:
        """Return what a failure means, and whether it is in the model's answer rather than the route to it."""
        for pattern, hint in FAILURE_HINTS:
            if pattern.search(message):
                return hint, pattern is MODEL_ANSWER_ERRORS
        return "Read Doris's message, correct the statement or the environment, and rerun this cell.", False

    def _execute(self, statement: str) -> tuple[pd.DataFrame | int | None, str | None]:
        clean = statement.strip().rstrip(";").rstrip()
        try:
            with self._admin().cursor() as cursor:
                cursor.execute(clean)
                if cursor.description:
                    names = [column[0] for column in cursor.description]
                    return result_frame(cursor.fetchall(), names), None
                return cursor.rowcount, None
        except pymysql.MySQLError as error:
            message = str(error.args[1]) if len(error.args) > 1 else str(error)
            return None, message.split("detailMessage =", 1)[-1].strip()

    def ai_sql(self, statement: str, *, title: str, each: Iterable[Any] | None = None, **fields: Any):
        """Run a statement that calls AI functions; show its result and the model work it caused.

        With ``each``, ``statement`` is a template with ``{ticket_id}``: it runs once
        for each value, so that an answer that Doris cannot parse fails only its own
        ticket. ``fields`` fill the template's other names. When Doris cannot use the
        model's answer, a card shows Doris's message and the cell goes on: a model's
        answer is not guaranteed to have the shape that Doris expects. A failure on
        the way to the model stops the cell.

        Returns the rows of a query, or the number of rows that a statement wrote;
        None when a single statement failed because of the model's answer.
        """
        is_query = statement.lstrip().upper().startswith(("SELECT", "WITH"))
        values = list(each) if each is not None else [None]
        templated = each is not None or bool(fields)
        if each is not None and not values:
            show_sql(title, statement.format(ticket_id="<ticket_id>", **fields).strip())
            card("No ticket is waiting, so the statement did not run and the model did no work.", "skip",
                 "Nothing to do")
            return pd.DataFrame() if is_query else 0
        shown = statement.format(ticket_id=values[0], **fields) if templated else statement
        if each is not None:
            title_shown = f"{title} (shown for ticket {values[0]}; it runs once for each of {len(values)} tickets)"
        else:
            title_shown = title
        show_sql(title_shown, shown.strip())
        before, started = self._model_counters(), time.perf_counter()
        frames, written, outcomes = [], 0, []
        for value in values:
            result, error = self._execute(statement.format(ticket_id=value, **fields) if templated else statement)
            if error is not None:
                hint, in_answer = self._explain_failure(error)
                if not in_answer:
                    self._show_work(before, started)
                    self._failure(f"{title}: the statement failed", hint, error)
                    raise EnvironmentNotReady("an AI function could not reach its model.")
                outcomes.append({"ticket_id": value, "outcome": "failed", "Doris's message": error})
                continue
            if isinstance(result, pd.DataFrame):
                frames.append(result)
                outcomes.append({"ticket_id": value, "outcome": f"{len(result)} row(s)", "Doris's message": ""})
            else:
                written += int(result or 0)
                outcomes.append({"ticket_id": value, "outcome": f"wrote {int(result or 0)} row(s)",
                                 "Doris's message": ""})
        failed = [row for row in outcomes if row["outcome"] == "failed"]
        if each is not None:
            show_frame("Outcome for each ticket", pd.DataFrame(outcomes))
            if failed:
                card(f"Doris could not use the model's answer for {len(failed)} of {len(values)} tickets; the other "
                     "tickets are unaffected. Rerun the cell to try those again.", "info", "Some answers failed")
        elif failed:
            card(self._explain_failure(failed[0]["Doris's message"])[0], "info",
                 "Doris could not use the model's answer")
            show_log("Doris's message", failed[0]["Doris's message"], opened=True)
        frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if frames:
            show_frame(title, frame, final=True)
        self._show_work(before, started)
        if each is None and failed:
            return None
        return frame if is_query else written

    def try_functions(self, statements: Mapping[str, str]) -> pd.DataFrame:
        """Run one statement per AI function and show each answer, or Doris's message, in one table."""
        show_sql("The statements", ";\n".join(statement.strip() for statement in statements.values()) + ";")
        before, started = self._model_counters(), time.perf_counter()
        rows = []
        for function, statement in statements.items():
            result, error = self._execute(statement)
            if error is not None:
                hint, in_answer = self._explain_failure(error)
                if not in_answer:
                    self._show_work(before, started)
                    self._failure(f"{function}: the statement failed", hint, error)
                    raise EnvironmentNotReady("an AI function could not reach its model.")
                rows.append({"function": function, "answer": "", "Doris's message": error})
            else:
                rows.append({"function": function, "answer": str(result.iloc[0, 0]), "Doris's message": ""})
        frame = pd.DataFrame(rows)
        show_frame("The other AI functions, one ticket each", frame, final=True)
        self._show_work(before, started)
        return frame

    def _show_work(self, before: Mapping[str, float | None] | None, started: float) -> None:
        work = self.model_work(before, self._model_counters(), time.perf_counter() - started)
        show_frame("Model work for this cell, read from the model server", pd.DataFrame([work]))

    # ------------------------------------------------------------------ data

    def _tickets_ddl(self) -> str:
        columns = ",\n".join(
            f'    {column["name"]} {column["type"]} NOT NULL COMMENT "{column["comment"]}"'
            for column in self.tickets["columns"]
        )
        return (
            f"CREATE TABLE IF NOT EXISTS {env.DATABASE}.{env.TICKETS_TABLE} (\n{columns}\n)\n"
            "DUPLICATE KEY(ticket_id)\n"
            f'COMMENT "{self.tickets["comment"]}"\n'
            "DISTRIBUTED BY HASH(ticket_id) BUCKETS 1\n"
            'PROPERTIES ("replication_num" = "1")'
        )

    def _ticket_rows(self) -> list[dict[str, str]]:
        path = TICKETS_SPEC.with_name(self.tickets["file"])
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            expected = [column["name"] for column in self.tickets["columns"]]
            if reader.fieldnames != expected:
                raise ValueError(f"{path.name} has columns {reader.fieldnames}; expected {expected}.")
            return list(reader)

    def _insert_tickets_sql(self, rows: Sequence[Mapping[str, str]]) -> str:
        names = [column["name"] for column in self.tickets["columns"]]
        values = ",\n".join(
            "(" + ", ".join(str(int(row[name])) if name == "ticket_id" else "'" + escape_string(row[name]) + "'"
                            for name in names) + ")"
            for row in rows
        )
        return f"INSERT INTO {env.DATABASE}.{env.TICKETS_TABLE} ({', '.join(names)}) VALUES\n{values}"

    def load_tickets(self) -> None:
        """Create the tickets table, load datasets/support_tickets.csv once, and check the result."""
        self.sql(f"CREATE DATABASE IF NOT EXISTS {env.DATABASE}", title="Create the course database")
        self.sql(self._tickets_ddl(), title="Create the tickets table")
        rows = self._ticket_rows()
        names = [column["name"] for column in self.tickets["columns"]]
        loaded = self.query(f"SELECT {', '.join(names)} FROM {env.DATABASE}.{env.TICKETS_TABLE} ORDER BY ticket_id")
        current = [{name: str(record[name]) for name in names} for record in loaded.to_dict("records")]
        if current == rows:
            card(f"{env.DATABASE}.{env.TICKETS_TABLE} already holds the {len(rows)} course tickets; nothing to load.",
                 "ok", "Reusing the loaded tickets")
        else:
            self.sql(f"TRUNCATE TABLE {env.DATABASE}.{env.TICKETS_TABLE}", title="Empty the table before loading")
            statement = self._insert_tickets_sql(rows)
            preview = statement.split("\n")
            show_sql(f"Insert the {len(rows)} tickets from datasets/{self.tickets['file']}",
                     "\n".join(preview[:4]) + "\n...")
            with self._admin().cursor() as cursor:
                cursor.execute(statement)
            card(f"Inserted {len(rows)} tickets.", "ok", "Loaded the support tickets")
        summary = self.query(f"""
SELECT COUNT(*) AS tickets,
       MIN(ticket_id) AS first_ticket,
       MAX(ticket_id) AS last_ticket,
       SUM(CASE WHEN language = 'en' THEN 1 ELSE 0 END) AS english,
       SUM(CASE WHEN language = 'zh' THEN 1 ELSE 0 END) AS chinese,
       COUNT(DISTINCT expected_topic) AS topics,
       COUNT(DISTINCT expected_sentiment) AS sentiments
FROM {env.DATABASE}.{env.TICKETS_TABLE}""").iloc[0]
        spec = self.tickets
        checks = [
            ("tickets", spec["row_count"], summary["tickets"]),
            ("first ticket", spec["first_ticket"], summary["first_ticket"]),
            ("last ticket", spec["last_ticket"], summary["last_ticket"]),
            ("English tickets", spec["languages"]["en"], summary["english"]),
            ("Chinese tickets", spec["languages"]["zh"], summary["chinese"]),
            ("topics a person chose", len(spec["topics"]), summary["topics"]),
            ("sentiments a person chose", len(spec["sentiments"]), summary["sentiments"]),
        ]
        rows_checked = [(name, str(expected), str(actual)) for name, expected, actual in checks]
        show_frame("The loaded table compared with datasets/support_tickets.yaml",
                   pd.DataFrame(rows_checked, columns=["check", "expected", "in Doris"]))
        if any(expected != actual for _, expected, actual in rows_checked):
            self._failure("The loaded tickets do not match the course dataset",
                          "Rerun this cell. If the numbers still differ, the CSV file was changed.")
            raise EnvironmentNotReady("the loaded tickets do not match datasets/support_tickets.yaml.")

    # -------------------------------------------------------------- resource

    def resource_sql(self) -> str:
        """The CREATE RESOURCE statement for the course's local model."""
        settings = "".join(f',\n    "{name}" = "{value}"' for name, value in RESOURCE_SETTINGS)
        return (
            f'CREATE RESOURCE "{env.AI_RESOURCE}"\n'
            "PROPERTIES (\n"
            '    "type" = "ai",\n'
            '    "ai.provider_type" = "local",\n'
            f'    "ai.endpoint" = "{env.LLM_ENDPOINT}",\n'
            f'    "ai.model_name" = "{env.LLM_MODEL}"'
            f"{settings}\n)"
        )

    def resource_properties(self) -> dict[str, str]:
        frame = self.query(f'SHOW RESOURCES WHERE NAME = "{env.AI_RESOURCE}"')
        return {str(row["Item"]): str(row["Value"]) for row in frame.to_dict("records")}

    def create_resource(self) -> None:
        """Create the AI Resource for the local model, replacing one that an earlier run created."""
        if not self.uses_sandbox and env.LLM_CONTAINER in env.LLM_ENDPOINT:
            self._failure(
                "Your Doris needs another address for the model",
                f"The BE of your own Doris is not on the sandbox's network, so it cannot reach {env.LLM_ENDPOINT}. "
                f"Set DORIS_AI_LLM_ENDPOINT to an address that your BE can reach, such as "
                f"http://host.docker.internal:{env.LLM_PORT}/v1/chat/completions when your Doris runs in Docker "
                "Desktop on this computer, then restart Jupyter.",
            )
            raise EnvironmentNotReady("DORIS_AI_LLM_ENDPOINT is needed with your own Doris.")
        existing = self.resource_properties()
        if existing and (existing.get("type") != "ai" or existing.get("ai.provider_type") != "LOCAL"):
            self._failure(
                "A different Resource has this name",
                f"{env.AI_RESOURCE} exists with type {existing.get('type')} and provider "
                f"{existing.get('ai.provider_type')}, so the Lab did not create it. It was left unchanged.",
            )
            raise EnvironmentNotReady(f"a different resource named {env.AI_RESOURCE} exists.")
        if existing:
            self.sql(f'DROP RESOURCE IF EXISTS "{env.AI_RESOURCE}"', title="Remove the Resource of an earlier run")
        self.sql(self.resource_sql(), title="Create the AI Resource")
        properties = self.resource_properties()
        shown = ("type", "ai.provider_type", "ai.endpoint", "ai.model_name") + tuple(
            name for name, _ in RESOURCE_SETTINGS)
        show_frame(f'SHOW RESOURCES WHERE NAME = "{env.AI_RESOURCE}" (the properties that the Lab set)',
                   pd.DataFrame([{"Item": name, "Value": properties.get(name)} for name in shown]))
        card(f"Doris stored the Resource; it did not contact {env.LLM_ENDPOINT}. Only the first AI function call "
             "shows whether the BE can reach the model.", "ok", "The AI Resource exists")

    def drop_resource(self) -> None:
        """Remove the AI Resource; AI functions that name it fail afterwards."""
        self.sql(f'DROP RESOURCE IF EXISTS "{env.AI_RESOURCE}"', title="Remove the AI Resource")
