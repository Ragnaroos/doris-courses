"""Explicit lifecycle for the optional local services, attached only to course Doris.

Lab 11 starts ``bi`` (Superset) and Lab 13 starts ``backup`` (Silo). Each one is a
Compose project of its own; its host port is a variable (dw_course/environment.py).
"""

import json
import subprocess

from .docker_runtime import _run, check_host_ports, compose_command
from .environment import SERVICE_PORTS
from .onboarding import SetupRequired
from .runtime import COURSE_ROOT
from .ui import WorkflowProgress

SERVICES = {
    "bi": "the Superset dashboard service of Lab 11",
    "backup": "the backup object storage of Lab 13",
}
# Lines in Compose's output that mean the image could not be downloaded or built.
NETWORK_ERRORS = ("failed to solve", "failed to resolve", "failed to fetch", "could not resolve",
                  "temporary failure in name resolution", "tls handshake", "i/o timeout",
                  "connection refused", "pull access denied", "error pulling", "unable to fetch")


def service_command(service, *arguments):
    return ['docker', 'compose', '--project-name', 'doris-warehousing-' + service,
            '--file', str(COURSE_ROOT / 'environments' / service / 'compose.yml'), *arguments]


def _start_failure(service, output):
    """Explain why `up --wait` failed: the download or build, memory, or the health check."""
    command = f"docker compose --project-name doris-warehousing-{service} --file environments/{service}/compose.yml"
    lowered = (output or "").lower()
    if any(marker in lowered for marker in NETWORK_ERRORS):
        source = ("apache/superset:4.1.2 from Docker Hub and packages from deb.debian.org and PyPI"
                  if service == "bi" else "pgsty/silo from Docker Hub")
        return (f"The image could not be downloaded or built. The first start downloads {source}, so the "
                "machine running Docker needs internet access (and the proxy settings of Docker Desktop, if "
                "you use one). Check the connection and rerun this cell. The output above shows the failing "
                f"step; `{command} build` from the course directory shows the whole build.")
    container = subprocess.run(service_command(service, "ps", "--all", "--quiet"), text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30).stdout.strip()
    if container:
        state = json.loads(subprocess.run(["docker", "inspect", "--format", "{{json .State}}", container],
                                          text=True, stdout=subprocess.PIPE, timeout=30).stdout or "{}")
        if state.get("OOMKilled"):
            return ("Docker stopped the container because it ran out of memory. The service needs about "
                    f"{'2 GiB' if service == 'bi' else '512 MiB'} in addition to the course sandbox: give Docker "
                    "more memory (Docker Desktop: Settings > Resources), or stop other containers, then rerun "
                    "this cell.")
    return (f"The service did not become healthy within 5 minutes. Its log is in the details below; "
            f"`{command} logs --tail 80` from the course directory shows more. If Docker is short of memory, "
            "give it more or stop other containers, then rerun this cell.")


def start_service(lab, service, *, start=False):
    """Require explicit opt-in; check the host port, start, and attach only our Doris container.

    Returns the service's network. Its data stays in the project's volume.
    """
    if not start:
        raise RuntimeError('Pass start=True to start the local ' + service + ' teaching service')
    progress = WorkflowProgress("Start " + SERVICES[service], {
        1: "Check the service's host port",
        2: "Download or build the image, then start the service and wait for health",
        3: "Connect the course Doris container to the service's network",
    })
    try:
        progress.advance(1)
        check_host_ports(SERVICE_PORTS[service], 'doris-warehousing-' + service, progress)
        progress.advance(2)
        try:
            _run(service_command(service, 'up', '-d', '--wait', '--wait-timeout', '300'), progress, timeout=1800)
        except subprocess.CalledProcessError as error:
            raise SetupRequired(_start_failure(service, error.output),
                                detail="\n".join(progress.logs + [str(error.output or "")])) from None
        progress.advance(3)
        container = subprocess.check_output(compose_command('ps', '-q', 'doris'), text=True).strip()
        if not container:
            raise SetupRequired("The course Doris container is not running, so it cannot join the service's "
                                "network. Open Lab 1, run Start and Connect, then rerun this cell.", labs=(1,))
        sidecar = subprocess.check_output(service_command(service, 'ps', '-q'), text=True).strip()
        networks = json.loads(subprocess.check_output(
            ['docker', 'inspect', '--format', '{{json .NetworkSettings.Networks}}', sidecar], text=True))
        network = next(name for name in networks if name.endswith('_default'))
        attached = json.loads(subprocess.check_output(
            ['docker', 'inspect', '--format', '{{json .NetworkSettings.Networks}}', container], text=True))
        if network not in attached:
            try:
                _run(['docker', 'network', 'connect', '--alias', 'course-doris', network, container], progress)
            except subprocess.CalledProcessError as error:
                raise SetupRequired(
                    f"Docker could not connect the course Doris container to {network}: {error.output}. "
                    f"`docker network inspect {network}` shows what is attached. If Doris is restarting, wait "
                    "until Lab 1's connection cell reports it healthy, then rerun this cell.",
                    detail="\n".join(progress.logs)) from None
            # Adding a container interface can invalidate an existing TCP connection.
            lab.restore_session()
    except Exception as error:
        progress.fail(str(error), opened=not isinstance(error, SetupRequired))
        raise
    progress.finish()
    return network
