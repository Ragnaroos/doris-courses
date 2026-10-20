# AI Integrations with Apache Doris (Preview)

Connect AI agents to Apache Doris safely. In this course you give an MCP Host,
such as Claude Desktop, Cursor, VS Code with GitHub Copilot, or Codex, read-only
access to Doris through the official Apache Doris MCP Server, and you learn to
check what the agent did: which tools it called, what Doris returned, and
whether its answer matches. Everything runs on your own computer, against a
Doris sandbox that the course starts for you.

> **Preview.** The course has one module so far. It is complete and tested, and
> more modules are planned; see [Roadmap](#roadmap).

## Who this course is for

- Data engineers, analysts, and platform engineers who want an AI agent to
  answer questions from Doris data without an administrator account.
- You should be comfortable with SQL queries that filter, group, and sort;
  running commands in a terminal; starting Docker containers; and running a
  Jupyter notebook from a Python virtual environment. You will edit one JSON or
  TOML configuration file for your Host.
- No previous experience with MCP is needed. The course explains the Doris
  concepts it uses: the Frontend (FE) and Backend (BE) processes, accounts and
  grants, and table statistics.

## What you will learn

- How the MCP Host, its MCP Client, the Doris MCP Server, and Doris divide the
  work, and what leaves your computer during a conversation.
- How hierarchical discovery exposes the Server's eight tool domains, and why a
  tool can be unavailable.
- How to connect any MCP Host through one protected launcher and a
  least-privilege Doris account.
- How to check an agent's answer against its tool calls, the structured results
  with their warnings, and the same SQL run directly.
- How to treat table text as untrusted input, read the audit trail, and diagnose
  a failing connection without widening privileges.

## Course outline

| Level | Module | What you will do | Time | Status |
| --- | --- | --- | --- | --- |
| 1 | [Module 1: Connect AI Agents to Apache Doris with MCP](level1/module01-doris-mcp/course.md) | Start a Doris sandbox, connect one MCP Host through a protected launcher, and check the agent's table context, query results, and memory evidence against Doris | 90 min | Available |

Each module has a lesson (`course.md`), a Lab notebook, and a quiz notebook.

## Roadmap

The modules below are planned, in this order. They are not available yet, and
their scope may change once they have been tried on Doris 4.x. Each will state
at its start what it uses from Module 1.

| Planned module | What it will cover | Uses from Module 1 |
| --- | --- | --- |
| Hybrid Search | Combine Doris's full-text (inverted) index and vector (ANN) index on a table in Doris, and let an agent run the search through the `doris_search` domain. | The read-only account and the evidence checks |
| AI Functions | Call language models from SQL with Doris's AI functions, available since Doris 4.0, and handle their cost, rate limits, failures, and non-deterministic results. | What leaves your computer, and text that cannot be trusted |
| Lakehouse federated retrieval | Query lakehouse tables through Doris catalogs next to tables in Doris, and see where Doris's indexes apply and where they do not. | Discovery of the `doris_lakehouse` domain |

## Environment

- **Supported platforms.** macOS on Apple Silicon, where the course was run end
  to end. Linux on x86-64 uses the same Doris image but was not run end to end.
  On Windows, use WSL 2, because the MCP launcher is a Bash script.
- **Resources.** Docker with at least 4 GB of memory for containers; the Doris
  sandbox uses about 3 GB. About 5 GB of disk for the Doris image and the
  course's virtual environment.
- **Downloads.** The Doris image,
  `apache/doris:all-in-one-4.1.3@sha256:82a5cabc7900ebcd3d080412d636c0cebd6602799fffe2605c652b2ea7d42609`:
  about 1.9 GB to download, 4.5 GB on disk. The Python packages, including
  Jupyter and the Doris MCP Server: about 560 MB installed. `SHOW FRONTENDS`
  reports the version as `doris-4.1.3-rc02-7126cf65d96`; that is how the 4.1.3
  release identifies itself.
- **Accounts and keys.** One MCP Host, installed and signed in; model use
  counts against your plan with that vendor. No Doris or cloud credentials are
  needed: the Lab creates the Doris account and generates its password on your
  computer.
- **Ports.** The sandbox listens only on `127.0.0.1`. Set the variables before
  you start Jupyter to use other ports:

  | Port | Purpose | Variable |
  | --- | --- | --- |
  | 39030 | FE MySQL protocol | `DORIS_AI_QUERY_PORT` |
  | 38030 | FE HTTP | `DORIS_AI_HTTP_PORT` |
  | 38040 | BE HTTP | `DORIS_AI_BE_HTTP_PORT` |

  The container is `doris-ai`, with the volumes `doris-ai-fe-meta` and
  `doris-ai-be-storage` and the network `doris-ai`, so the course runs next to
  the other courses of this repository. To use your own Doris 4.x instead, see
  section 1.3 of Module 1.

## Get started

1. Create the course's virtual environment with Python 3.12 or 3.13 and install
   the requirements. Run the commands in the course directory: the
   requirements install the shared notebook runtime from `../common`.

   ```bash
   cd doris-course/04-ai-integrations
   python3.12 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

2. Start Docker, then start Jupyter from the same environment:

   ```bash
   .venv/bin/jupyter lab
   ```

3. Open the lesson
   [Module 1: Connect AI Agents to Apache Doris with MCP](level1/module01-doris-mcp/course.md)
   and its Lab, `level1/module01-doris-mcp/lab01_connect_agent_to_doris.ipynb`.

## Dataset

The Labs use one table, `ai_course.events`: 14,307 storefront events from March
2026, in which 800 shoppers in four regions view, add to the cart, and buy 200
products. The data is synthetic: `datasets/generate_events.py` wrote
`datasets/events.csv` from a fixed seed, so it contains no real people, orders,
or products. `datasets/events.yaml` describes the columns and the numbers that
the Lab checks after loading.

## Clean up

1. Remove the `doris` entry from each Host you connected. Module 1's Clean up
   section says where each Host keeps it; for Codex, run
   `codex mcp remove doris`.
2. In the last section of the Lab, set `REMOVE_EVERYTHING = True` and run the
   cell. It removes the `doris-ai` container, its volumes and network, the
   launcher's `.env.mcp.local`, and the Server's `logs/`.
3. Optionally, delete `doris-course/04-ai-integrations/.venv`.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| The Lab reports a port `in use` | Another program holds the port. Stop it, or set the `DORIS_AI_*` variable to a free port and restart Jupyter. |
| `pip install` fails, or the Lab cannot import `doris_labkit` | Use Python 3.12 or 3.13, and run the install command in `doris-course/04-ai-integrations`. |
| Doris stops or restarts while you work | Give Docker at least 4 GB of memory, then run `lab.start()`. |
| The Host shows the `doris` Server as failed | Read `level1/module01-doris-mcp/logs/doris_mcp_server_error.log`, then run `lab.check_launcher()` in the Lab. Module 1, section 1.7, lists the common causes. |
| `Database connectivity test failed` while Doris is running | The password in `.env.mcp.local` does not match the account. Run `lab.check_reader_login()` to confirm, then rerun Lab section 3: it sets the account's password to the one in the file. |
