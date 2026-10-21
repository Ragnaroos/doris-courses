"""Explicitly prepare only the course's local Iceberg fixtures."""

import json
import subprocess
import time

import boto3
import pymysql
import requests

from .docker_runtime import check_host_ports, compose_command, _run
from .environment import LAKE_PORTS, port
from .runtime import COURSE_ROOT, expect, identifier
from .ui import WorkflowProgress, in_notebook, show_sql
from .wwi import HISTORY_COLUMNS, history_rows

PROJECT = "doris-warehousing-lake"
NETWORK = PROJECT + "_default"
COMPOSE = COURSE_ROOT / "environments/lakehouse/compose.yml"
ACCESS_KEY = "course_lake"
SECRET_KEY = "course_lake_local_only"


def _wait_http(url, timeout=90):
    deadline = time.monotonic() + timeout
    last_error = "service not ready"
    while time.monotonic() < deadline:
        try:
            response = requests.get(url, timeout=3)
            response.raise_for_status()
            return
        except requests.RequestException as error:
            last_error = str(error)
        time.sleep(1)
    raise TimeoutError(url + ": " + last_error)


def _execute_when_reachable(lab, statement, progress, *, timeout=60):
    """Run a statement that reaches the lake services, retrying while Doris still uses their old address.

    When Compose recreates the lake containers they get new addresses, and Doris
    keeps connecting to the old ones for up to about 30 seconds.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            return lab.execute(statement)
        except pymysql.MySQLError as error:
            if "Connection refused" not in str(error) or time.monotonic() >= deadline:
                raise
            progress.log(f"Doris cannot reach the lake services yet, retrying in 3 s: {error}")
            time.sleep(3)


def prepare_lakehouse(lab, *, start=False):
    """Start with explicit consent; create a per-lab namespace and reuse matching data.

    Returns the lake table's full name. When it finishes, it shows the SQL that
    it ran in Doris: the Catalog, the lake database and table, and the INSERT
    of the ten orders on the first run.
    """
    if not start:
        raise ValueError("Read the Lab 4 environment guide, then set start=True to start the course lakehouse services")
    namespace = identifier(lab.database)
    catalog = identifier(lab.database + "_lake")
    table = catalog + "." + namespace + ".orders"
    progress = WorkflowProgress("Prepare the lakehouse lab", {
        1: "Start the course object storage and Iceberg services",
        2: "Wait for services to become ready",
        3: "Connect Doris to the lakehouse network",
        4: "Prepare storage for the sample",
        5: "Create the catalog and lake tables",
        6: "Verify the ten orders in the lake",
    })
    s3_endpoint = f"http://127.0.0.1:{port('DW_LAKE_S3_PORT')}"
    try:
        progress.advance(1)
        check_host_ports(LAKE_PORTS, PROJECT, progress)
        _run(["docker", "compose", "--project-name", PROJECT, "--file", str(COMPOSE),
              "up", "-d", "--pull", "missing"], progress, timeout=1800)
        progress.advance(2)
        _wait_http(s3_endpoint + "/minio/health/live")
        _wait_http(f"http://127.0.0.1:{port('DW_LAKE_REST_PORT')}/v1/config")
        progress.advance(3)
        container = subprocess.check_output(compose_command("ps", "-q", "doris"), text=True).strip()
        if not container or "\n" in container:
            raise RuntimeError("Run Lab 1 first to start the single-container Doris sandbox")
        networks = json.loads(subprocess.check_output(
            ["docker", "inspect", "--format", "{{json .NetworkSettings.Networks}}", container], text=True))
        if NETWORK not in networks:
            _run(["docker", "network", "connect", NETWORK, container], progress)
            # Attaching a network can invalidate an established host-port TCP connection.
            lab.restore_session()
        progress.advance(4)
        client = boto3.client("s3", endpoint_url=s3_endpoint,
                              aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY,
                              region_name="us-east-1")
        buckets = {entry["Name"] for entry in client.list_buckets()["Buckets"]}
        if "course-warehouse" not in buckets:
            client.create_bucket(Bucket="course-warehouse")
        progress.advance(5)
        statements = [f'''CREATE CATALOG IF NOT EXISTS {catalog} PROPERTIES (
    "type"="iceberg", "iceberg.catalog.type"="rest",
    "iceberg.rest.uri"="http://course-lake-rest:8181",
    "warehouse"="s3://course-warehouse/",
    "s3.endpoint"="http://course-lake-silo:9000", "s3.region"="us-east-1",
    "s3.access_key"="{ACCESS_KEY}", "s3.secret_key"="{SECRET_KEY}",
    "use_path_style"="true", "iceberg.rest.view-enabled"="false"
)''']
        lab.execute(statements[-1])
        properties = dict(lab.query(f"SHOW CATALOG {catalog}"))
        expected_properties = {
            "type": "iceberg", "iceberg.catalog.type": "rest",
            "iceberg.rest.uri": "http://course-lake-rest:8181",
            "s3.endpoint": "http://course-lake-silo:9000",
            "warehouse": "s3://course-warehouse/",
        }
        if any(properties.get(key) != value for key, value in expected_properties.items()):
            raise ValueError("The existing catalog with this name points to another environment. Keep its configuration and use a new course lab database")
        statements.append(f"CREATE DATABASE IF NOT EXISTS {catalog}.{namespace}")
        _execute_when_reachable(lab, statements[-1], progress)
        statements.append(f'''CREATE TABLE IF NOT EXISTS {table} (
    order_id BIGINT, customer_id BIGINT, order_date DATE,
    order_amount DECIMAL(18,2), line_count INT, data_source STRING
)''')
        lab.execute(statements[-1])
        count = lab.query(f"SELECT COUNT(*) FROM {table}")[0][0]
        if count == 0:
            # Identifiers are fixed and validated above; values remain parameterized.
            placeholders = ",".join(["(%s,%s,%s,%s,%s,%s)"] * len(history_rows()))
            values = tuple(value for row in history_rows() for value in row)
            insert = f"INSERT INTO {table} ({','.join(HISTORY_COLUMNS)}) VALUES {placeholders}"
            with lab.connection.cursor() as cursor:
                statements.append(cursor.mogrify(insert, values).replace("),(", "),\n("))
            lab.execute(insert, values)
        else:
            statements.append(f"-- {table} already holds {count} rows: nothing inserted")
        progress.advance(6)
        expect(lab.query(f"SELECT order_id,customer_id,CAST(order_date AS STRING),order_amount,line_count,data_source FROM {table} ORDER BY order_id"), history_rows())
        progress.finish()
        if in_notebook():
            show_sql("The SQL that the preparation ran in Doris", ";\n\n".join(statements) + ";")
        return table
    except Exception as error:
        progress.fail(str(error))
        raise
