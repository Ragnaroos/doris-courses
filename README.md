# Apache Doris Courses

Hands-on courses on Apache Doris 4.1.3. Each course runs on your own computer:
its Jupyter notebooks start Doris in Docker, bring in the course's data, and
check the results as you go. Each module has a lesson to read, a Lab to run,
and a quiz.

The four courses are independent of each other. Start with the one that fits
your work; each course teaches the Doris basics that it uses.

## Courses

### [Real-time Analytics with Apache Doris](doris-course/01-real-time-analytics/README.md)

Build a real-time analytics system on ten million ecommerce events: load them
from files, S3, and Kafka, model and analyze them, make queries faster without
changing their answers, and run a cluster of three FEs and three BEs through
failures.

- **For:** data engineers, analytics engineers, and backend developers who
  build real-time dashboards or analytical services.
- **Time:** about 16 hours, in 10 modules.
- **Needs:** Docker with 4 CPUs, 8 GB of memory, and 20 GiB of free disk. The
  data, 72 MiB, comes from a public S3 bucket and needs no account.

### [Data Warehousing with Apache Doris](doris-course/02-data-warehousing/README.md)

Build an order warehouse that the business can trust: load orders and their
history in batches, keep only the inputs that pass their checks, follow every
change of an order, model facts and dimensions, publish metrics to dashboards
and models, and operate the warehouse with roles, a data lifecycle, and
Workload Groups.

- **For:** data engineers and analytics engineers who build a data warehouse
  on Doris.
- **Time:** about 22 hours, in 14 modules.
- **Needs:** Docker with 4 CPUs, 8 GB of memory, and about 20 GB of free disk;
  the optional streaming Labs need 8 to 10 GiB of memory. The data is in the
  repository.

### [Observability with Apache Doris](doris-course/03-observability/README.md)

Run an online store on your computer, let it fail, and investigate the
failure with the DOG stack, Doris with the OpenTelemetry Collector and
Grafana: collect logs, metrics, and traces, search and chart them, design
tables for telemetry, and alert on it.

- **For:** engineers who operate services, developers who want to know what
  their services record, and data engineers who want to use Doris for logs,
  metrics, and traces.
- **Time:** about 11 hours, in 8 modules.
- **Needs:** Docker with at least 10 GB of memory, Docker Compose 2.24.4 or
  later, about 21 GB of disk for the images, and Git. The telemetry comes from
  the systems that the course runs.

### [AI Integrations with Apache Doris](doris-course/04-ai-integrations/README.md) (Preview)

Give an AI agent read-only access to Doris through the Apache Doris MCP
Server, and check what it did: which tools it called, what Doris returned,
and whether its answer matches.

- **For:** data engineers, analysts, and platform engineers who want an AI
  agent to answer questions from Doris data without an administrator account.
- **Time:** about 90 minutes, in the one module available so far. More
  modules are planned; the course README lists them.
- **Needs:** Docker with 4 GB of memory and about 5 GB of disk, Python 3.12 or
  3.13, and one MCP Host, such as Claude Desktop, Cursor, VS Code with GitHub
  Copilot, or Codex, installed and signed in; its model use counts against
  your plan with that vendor.

## Before you start

- **A copy of the whole repository.** Clone it with Git. Each course installs
  `doris_labkit`, the notebook runtime that the courses share, from
  `doris-course/common/` through its `requirements.txt`, so the course
  directories need the rest of the repository; you do not install the runtime
  yourself.
- **Docker.** Every course was run from start to finish on macOS with Apple
  silicon and Docker Desktop. Linux on x86-64 with Docker Engine uses the same
  images but has not been run from start to finish, and neither has Windows
  with WSL 2. Each course's README says which platforms it supports and what
  differs on them.
- **Python 3.10 to 3.13** for the course's virtual environment, which also
  installs JupyterLab. Real-time Analytics also runs on 3.9; AI Integrations
  needs 3.12 or 3.13. If `python3 --version` reports 3.14, create the
  environment with an older version, such as `python3.12`.
- **Internet access** for the first downloads, which each course's README
  lists: Docker images, Python packages, and for some courses data or code. No
  course needs a cloud account or a paid key, apart from the MCP Host of AI
  Integrations.

Then open the README of a course and follow its **Get started** section.

## Running more than one course

Each course gives its Docker containers, networks, and volumes its own prefix
and uses its own host ports, all bound to 127.0.0.1, so the courses do not
collide with each other or with your own containers. You can change every port
with an environment variable; each course's README lists them.

| Course | Docker prefix | Doris query port |
| --- | --- | --- |
| Real-time Analytics | `doris-rta` | 19030 |
| Data Warehousing | `doris-warehousing` | 52030 |
| Observability | `doris-obs` | 29030 |
| AI Integrations | `doris-ai` | 39030 |

Each course's environment needs the memory that its README gives, so running
two at the same time needs the memory of both. The **Clean up** section of each
course's README shows how to stop the course's containers and keep its data,
and how to remove only that course's containers, volumes, and networks.

## Repository layout

- `doris-course/<course>/`: one directory per course, with its README, its
  modules in `level*/module*/`, the code that starts its environment, its
  tests, and `course.yaml`, which lists the modules in order.
- `doris-course/common/`: `doris_labkit`, the notebook runtime that every
  course installs.
- `tools/`: the repository checks, which CI runs on every pull request.
- `maintenance/`: notes for maintainers: what each course depends on, what to
  recheck after a change, and what to do before a release.

To change a course, see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

This repository, with its lessons, notebooks, quizzes, and code, is licensed
under the [Apache License 2.0](LICENSE). [NOTICE](NOTICE) names the copyright
holders and the third-party material in the repository, which keeps its own
license, such as the part of Microsoft's Wide World Importers sample in Data
Warehousing (MIT). What the courses download when they run keeps its own terms
too: the software and container images, and the REES46 eCommerce data of
Real-time Analytics, whose source its README credits.

Apache, Apache Doris, and Doris are trademarks of The Apache Software
Foundation. These courses are not a project of The Apache Software Foundation.
