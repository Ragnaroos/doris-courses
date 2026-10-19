# First-time setup

Use this page when you are opening the course for the first time or when a Lab says that setup is required.

## What you need

- The complete repository, including the shared course components.
- Python 3.10–3.13 and a virtual environment.
- Docker Desktop on macOS or Windows, or Docker Engine with the Compose plugin on Linux.
- About 4 CPUs, 8 GB of memory, and 20 GB of free disk space for the learning sandbox.

Docker and Jupyter must run on the same machine. The browser may be on another machine, but the Python kernel starts the container and connects to Doris locally.

## Install the Python tools

From this directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Start Jupyter with the course root:

```bash
.venv/bin/jupyter lab level1/module01-introduction/lab01_connect_and_query.ipynb
```

Select the matching `.venv` Python kernel if Jupyter offers more than one kernel.

## Start the database from Lab 1

1. Start Docker Desktop or Docker Engine and wait until `docker info` succeeds.
2. In Lab 1, run **Initialize the Lab Tools**.
3. Read the reset notice, then run **Start and Connect**.
4. Continue only when the result shows `connection_ok = 1`.

The first start downloads `apache/doris:all-in-one-4.1.3` and can take several minutes. The Lab creates the dedicated `dw_course_l1_demo` database and keeps the course container and volumes separate from other Docker projects.

## Follow the data dependencies

The recommended order is Lab 1 to Lab 7. All Labs use the same course database, and each Lab rebuilds only its own tables. The table below shows what each Lab actually needs, so you know what to do when one Lab cannot run yet:

| Lab | Needs before it runs | Leaves for later Labs |
| --- | --- | --- |
| Lab 1 | Docker | The running sandbox and the `dw_course_l1_demo` database |
| Lab 2, Lab 3 | The sandbox from Lab 1 | Only their own practice tables |
| Lab 4 | The sandbox from Lab 1; it starts two lake-table helper containers on demand | Only its own tables |
| Lab 5 | The sandbox from Lab 1 | `orders_imported`, which Levels 2 and 3 read, and the ten `wwi_*` history tables |
| Lab 6 | The sandbox from Lab 1. It reads `wwi_customers` from Lab 5, or loads that table from the bundled history package if it is missing | `orders_clean` and `customers` |
| Lab 7 | `orders_clean` and `customers` from Lab 6. It reads `wwi_products` from Lab 5, or loads that table from the bundled package if it is missing | The current-state and event tables |

If the lake-table environment in Lab 4 cannot start, for example because its images cannot be downloaded, continue with Labs 5–7 and return to Lab 4 later. No other main Lab depends on Lab 4; only the optional Module 4–5 extension Lab uses the same lake-table environment.

After a kernel restart, rerun that Notebook's initialization and connection cells. The connection cell does not start Docker; return to Lab 1 if the sandbox is stopped or has never been created.

## Optional Kafka and Flink labs

The optional Lab 5A Kafka notebook needs Docker-visible capacity of at least 14 GiB RAM and 4 CPUs. The optional Lab 5B Flink CDC notebook needs 18 GiB RAM and 4 CPUs. Set Docker Desktop's **Resources** before running either notebook; the notebook checks capacity before it starts any streaming containers. A 16 GiB Mac can run Lab 5A after allocating about 15 GiB to Docker, but it cannot meet the CDC profile's 18 GiB requirement. These optional labs are independent of the seven main Labs.

## If setup fails

Run these checks from this directory:

```bash
docker info
docker compose version
docker compose --project-name doris-warehousing-course --file environments/single-node/compose.yml ps
```

For `command not found`, install Docker and open a new terminal. For a refused connection, start Lab 1's **Start and Connect** cell and wait for its health check. For missing prerequisite tables, return to the first Lab named in the message and complete it in the same course database.
