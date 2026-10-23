"""Explicit opt-in lifecycle for course 02's own single-node Compose project."""

import json
import os
import shlex
import subprocess

import pymysql

from doris_labkit.docker import port_in_use

from .environment import SANDBOX_PORTS, connection_settings, port
from .runtime import COURSE_ROOT, WarehouseLab
from .ui import WorkflowProgress
from .onboarding import SetupRequired

COMPOSE_FILE = COURSE_ROOT / "environments/single-node/compose.yml"
PROJECT = "doris-warehousing-course"
STARTUP_STEPS = {
    1: "Check Docker and Compose",
    2: "Validate the course configuration and its host ports",
    3: "Prepare the Doris image",
    4: "Start or reuse the container and volumes, then wait for health",
    5: "Verify the FE connection and BE execution",
    6: "Inspect the running course container",
}


def compose_command(*arguments, streaming=False):
    override = (["--file", str(COURSE_ROOT / "environments/streaming/doris-resources.yml")]
                if streaming else [])
    return [
        "docker", "compose", "--project-name", PROJECT,
        "--file", str(COMPOSE_FILE), *override, *arguments,
    ]


def _run(command, progress, *, timeout=30):
    progress.log("$ " + shlex.join(command))
    try:
        result = subprocess.run(
            command, check=True, timeout=timeout, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
    except (OSError, subprocess.SubprocessError) as error:
        if command[:2] == ["docker", "info"]:
            message = (
                "Docker was not found. Install Docker Desktop (macOS/Windows) or Docker Engine "
                "with Compose (Linux) on the machine running Jupyter. Open a new terminal, "
                "check `docker info`, then restart Jupyter and rerun this cell."
                if isinstance(error, FileNotFoundError) else
                "Docker is not ready. Start Docker Desktop or Docker Engine on the machine "
                "running Jupyter, finish first-time setup, and wait for `docker info` to succeed. "
                "Then rerun this cell."
            )
        elif command == ["docker", "compose", "version"]:
            message = "Docker Compose is unavailable. Install the Compose plugin or repair Docker Desktop, then check `docker compose version` and rerun this cell."
        else:
            raise
        raise SetupRequired(message, detail=str(error) + "\n" + str(getattr(error, "output", "") or "")) from None
    progress.log(result.stdout)


def published_ports(project):
    """Return the host ports that the running containers of a Compose project publish."""
    containers = subprocess.run(
        ["docker", "ps", "--quiet", "--filter", f"label=com.docker.compose.project={project}"],
        check=True, timeout=30, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    ).stdout.split()
    ports = set()
    for container in containers:
        # .HostConfig.PortBindings lists what the container asked for, even while it restarts.
        bindings = subprocess.run(
            ["docker", "inspect", "--format", "{{json .HostConfig.PortBindings}}", container],
            check=True, timeout=30, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        ).stdout
        for entries in (json.loads(bindings or "null") or {}).values():
            ports.update(int(entry["HostPort"]) for entry in entries or [] if entry.get("HostPort"))
    return ports


def check_host_ports(ports, project, progress):
    """Stop before starting containers when another program holds one of the course's host ports."""
    ours = published_ports(project)
    blocked = []
    for variable, (default, purpose) in ports.items():
        number = port(variable)
        if number in ours:
            status = "used by this course"
        elif port_in_use(number):
            status = "in use"
            blocked.append((number, variable, purpose, default))
        else:
            status = "available"
        progress.log(f"127.0.0.1:{number} {purpose} ({variable}): {status}")
    if blocked:
        listed = "; ".join(f"{number} ({variable}, {purpose})" for number, variable, purpose, _ in blocked)
        first, variable, _, default = blocked[0]
        raise SetupRequired(
            f"Another program is using {listed}. Nothing was started. Find it with "
            f"`lsof -nP -iTCP:{first} -sTCP:LISTEN` (macOS and Linux); when that shows Docker itself, "
            f"`docker ps --filter publish={first}` names the container. Stop it if it is yours. Otherwise "
            f"start Jupyter again with a free port in the variable, for example "
            f"`{variable}={default + 10000} .venv/bin/jupyter lab`, and rerun this Lab from the top.",
            detail="\n".join(progress.logs),
        )


def _verify_sql(settings):
    connection = pymysql.connect(
        host=settings["DW_HOST"], port=int(settings["DW_PORT"]),
        user=settings["DW_USER"], password=settings["DW_PASSWORD"],
        connect_timeout=5, read_timeout=10, autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone() != (1,):
                raise RuntimeError("Sandbox SQL readiness check failed")
            cursor.execute('SELECT SUM(number) FROM numbers("number"="10")')
            if cursor.fetchone() != (45,):
                raise RuntimeError("Sandbox BE execution check failed")
    finally:
        connection.close()


def prepare_environment(*, start=False, streaming=False, streaming_profile=None):
    """Start on explicit opt-in and report each completed or failed step."""
    if not start and os.environ.get("DW_START_SANDBOX") != "yes":
        raise RuntimeError("Set DW_START_SANDBOX=yes only to start course 02's Docker sandbox")
    if streaming:
        from .streaming import check_resources
        check_resources(streaming_profile or "cdc")

    def command(*arguments):
        return compose_command(*arguments, streaming=True) if streaming else compose_command(*arguments)

    settings = connection_settings()
    progress = WorkflowProgress("Prepare the Doris lab environment", STARTUP_STEPS)
    try:
        progress.advance(1)
        _run(["docker", "info", "--format", "{{.ServerVersion}}"], progress)
        _run(["docker", "compose", "version"], progress)
        progress.advance(2)
        _run(command("config", "--quiet"), progress)
        check_host_ports(SANDBOX_PORTS, PROJECT, progress)
        progress.advance(3)
        _run(command("pull", "--policy", "missing"), progress, timeout=1800)
        progress.advance(4)
        # The pinned image supplies the container healthcheck.
        _run(command("up", "-d", "--wait", "--wait-timeout", "300"),
             progress, timeout=1800)
        progress.advance(5)
        _verify_sql(settings)
        progress.log("SELECT 1 = 1; BE SUM(number) = 45")
        progress.advance(6)
        _run(command("ps"), progress)
    except Exception as error:
        detail = str(error)
        if isinstance(error, (subprocess.CalledProcessError, subprocess.TimeoutExpired)):
            output = error.output
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            if output:
                detail += "\n" + output
        progress.fail(detail, opened=not isinstance(error, SetupRequired))
        raise
    os.environ.update(settings)
    progress.finish()
    return settings


def connect_sandbox(*, module=None):
    """Connect this notebook to the course container without starting Docker.

    The connection variables always point at the course sandbox on the ports
    that DW_FE_QUERY_PORT, DW_FE_HTTP_PORT, and DW_BE_HTTP_PORT set, so a value
    left over from another server cannot redirect the Labs.
    """
    settings = connection_settings()
    os.environ.update(settings)
    try:
        lab = WarehouseLab(allow_writes=True)
    except pymysql.err.OperationalError as error:
        if error.args[0] not in (2002, 2003):
            raise
        # Diagnose only on connection failure; a healthy sandbox needs no Docker CLI call.
        try:
            _run(["docker", "info", "--format", "{{.ServerVersion}}"],
                 WorkflowProgress("Check Docker", {1: "Check Docker"}), timeout=10)
        except SetupRequired:
            raise
        raise SetupRequired(
            f"Doris is not reachable at 127.0.0.1:{settings['DW_PORT']} (DW_FE_QUERY_PORT). Open Lab 1, "
            "run Initialize the Lab Tools, then Start and Connect. Wait for connection_ok = 1, return here, "
            "and rerun this cell. Opening Jupyter alone does not start the database. If you changed the "
            "port variables, start Jupyter with the same values for every notebook.",
            labs=(1,), detail=str(error),
        ) from None
    try:
        _check_prerequisites(lab, module)
    except Exception:
        lab.close()
        raise
    return lab


# Labs 6 and 7 load these WWI tables from the bundled Parquet package when
# they are absent, so only an existing but incomplete copy blocks the lab.
RELOADABLE_TABLES = {"wwi_customers", "wwi_products"}


# The tables each Lab reads from earlier Labs: (rows when complete, the Lab that writes them).
PREREQUISITES = {
    6: {"wwi_customers": (663, 5)},
    7: {"wwi_products": (227, 5), "customers": (663, 6), "orders_clean": (10, 6)},
    8: {"orders_current": (11, 7), "order_events": (18, 7)},
    9: {"customers": (663, 6), "orders_current": (11, 7), "order_events": (18, 7)},
    10: {"orders_fact_l2": (11, 9), "dwd_orders_l2": (8, 9), "dwd_payments_l2": (6, 9), "customers_case_dim_l2": (5, 9)},
    11: {"daily_order_metrics_l2": (3, 10)},
    12: {"orders_fact_l2": (11, 9), "bi_order_metrics_l2": (2, 11)},
}
LAB_STEPS = {5: "Lab 5 (historical import)", 6: "Lab 6 (quality checks)", 7: "Lab 7 (current state and replay)",
             9: "Lab 9 (modeling and joins)", 10: "Lab 10 (metric processing)", 11: "Lab 11 (BI and AI consumers)"}


def _check_prerequisites(lab, module):
    requirements = PREREQUISITES.get(module, {})
    if not requirements:
        return
    existing = {row[0] for row in lab.query("SHOW TABLES")}
    missing = []
    upstream = set()
    for table, (count, source) in requirements.items():
        if table not in existing and table in RELOADABLE_TABLES:
            continue
        if table not in existing or lab.query(f"SELECT COUNT(*) FROM {table}")[0][0] != count:
            missing.append(table)
            upstream.add(source)
    if missing:
        verb = "is" if len(missing) == 1 else "are"
        raise SetupRequired(
            f"Lab {module} needs data in {lab.database}: {', '.join(missing)} {verb} missing or incomplete. "
            f"Complete {', then '.join(LAB_STEPS[number] for number in sorted(upstream))} "
            "in this same database. Return here and rerun this cell. No lab tables have been reset.",
            labs=tuple(sorted(upstream)),
        )
