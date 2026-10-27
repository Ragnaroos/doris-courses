# AI Integrations with Apache Doris (Preview)

Connect AI to Apache Doris in both directions, safely. In the first module you
give an MCP Host, such as Claude Desktop, Cursor, VS Code with GitHub Copilot, or
Codex, read-only access to Doris through the official Apache Doris MCP Server,
and you learn to check what the agent did: which tools it called, what Doris
returned, and whether its answer matches. In the second module Doris calls a
language model from SQL with its AI functions, and you learn to bound, measure,
check, and store what the model answers. Everything runs on your own computer,
against a Doris sandbox and a small open model that the course starts for you.

> **Preview.** The course has two modules so far. They are complete and tested,
> and more modules are planned; see [Roadmap](#roadmap).

## Who this course is for

- Data engineers, analysts, and platform engineers who want an AI agent to
  answer questions from Doris data without an administrator account, or who want
  to label, extract, and summarize text in Doris tables with a language model.
- You should be comfortable with SQL queries that filter, group, join, and sort;
  running commands in a terminal; starting Docker containers; and running a
  Jupyter notebook from a Python virtual environment. In Module 1 you edit one
  JSON or TOML configuration file for your Host.
- No previous experience with MCP or language models is needed. The course
  explains the Doris concepts it uses: the Frontend (FE) and Backend (BE)
  processes, accounts and grants, table statistics, and AI Resources.

## What you will learn

- How the MCP Host, its MCP Client, the Doris MCP Server, and Doris divide the
  work, and what leaves your computer during a conversation.
- How to connect any MCP Host through one protected launcher and a
  least-privilege Doris account, and check an agent's answer against its tool
  calls, the structured results, and the same SQL run directly.
- How an AI function reaches a model from the Doris BE, and how to create and
  test an AI Resource for a local model, and what to protect with a hosted one.
- How to choose an AI function by the shape of its answer, and count and bound
  the requests that a statement makes.
- How to check a model's answers before you use them, store them once, and keep
  model calls out of reports; and how to treat text from tables as untrusted
  input and diagnose failures without widening privileges.

## Course outline

| Level | Module | What you will do | Time | Status |
| --- | --- | --- | --- | --- |
| 1 | [Module 1: Connect AI Agents to Apache Doris with MCP](level1/module01-doris-mcp/course.md) | Start a Doris sandbox, connect one MCP Host through a protected launcher, and check the agent's table context, query results, and memory evidence against Doris | 90 min | Available |
| 1 | [Module 2: Call Language Models from SQL with AI Functions](level1/module02-doris-ai-functions/course.md) | Run a small open model next to the sandbox, label and summarize support tickets from SQL, measure the requests of each statement, check the answers, and store them once | 85 min | Available |

Each module has a lesson (`course.md`), a Lab notebook, and a quiz notebook.
Module 2 does not need Module 1: its Lab starts the sandbox, or reuses it.

## Roadmap

The modules below are planned, in this order. They are not available yet, and
their scope may change once they have been tried on Doris 4.x. Each will state
at its start what it uses from the earlier modules.

| Planned module | What it will cover | Uses from Modules 1 and 2 |
| --- | --- | --- |
| Hybrid Search | Combine Doris's full-text (inverted) index and vector (ANN) index on a table in Doris, and let an agent run the search through the `doris_search` domain. | The read-only account and the evidence checks; the local model server |
| Lakehouse federated retrieval | Query lakehouse tables through Doris catalogs next to tables in Doris, and see where Doris's indexes apply and where they do not. | Discovery of the `doris_lakehouse` domain |

## Environment

- **Supported platforms.** macOS on Apple Silicon, where the course was run end
  to end. Linux on x86-64 uses the same images but was not run end to end. On
  Windows, use WSL 2, because the MCP launcher is a Bash script.
- **Resources.** Module 1: Docker with at least 4 GB of memory for containers;
  the Doris sandbox uses about 3 GB. Module 2: at least 6 GB, because the model
  server needs about 2.3 GB more; the model runs on Docker's CPUs, and no GPU is
  needed. Disk: about 5 GB for Module 1 (the Doris image and the course's virtual
  environment), and about 2.3 GB more for Module 2 (the model server image and
  the model file).
- **Downloads.** The Doris image,
  `apache/doris:all-in-one-4.1.3@sha256:82a5cabc7900ebcd3d080412d636c0cebd6602799fffe2605c652b2ea7d42609`:
  about 1.9 GB to download, 4.5 GB on disk. The Python packages, including
  Jupyter and the Doris MCP Server: about 560 MB installed. `SHOW FRONTENDS`
  reports the version as `doris-4.1.3-rc02-7126cf65d96`; that is how the 4.1.3
  release identifies itself. For Module 2, the model server image
  `ghcr.io/ggml-org/llama.cpp:server-b11429` (about 300 MB to download, 1.2 GB on
  disk) and the model file `qwen2.5-1.5b-instruct-q4_k_m.gguf` (1.1 GB) from
  Hugging Face; the Lab checks the file's SHA-256.
- **Accounts and keys.** Module 1 needs one MCP Host, installed and signed in;
  model use counts against your plan with that vendor. Module 2 needs no account
  and no key: its model runs on your computer. No Doris or cloud credentials are
  needed: the Lab creates the Doris account and generates its password on your
  computer.
- **Ports.** The sandbox and the model server listen only on `127.0.0.1`. Set
  the variables before you start Jupyter to use other ports:

  | Port | Purpose | Variable |
  | --- | --- | --- |
  | 39030 | FE MySQL protocol | `DORIS_AI_QUERY_PORT` |
  | 38030 | FE HTTP | `DORIS_AI_HTTP_PORT` |
  | 38040 | BE HTTP | `DORIS_AI_BE_HTTP_PORT` |
  | 38080 | Module 2's model server | `DORIS_AI_LLM_PORT` |

  The containers are `doris-ai` and, for Module 2, `doris-ai-llm`, with the
  volumes `doris-ai-fe-meta`, `doris-ai-be-storage`, and `doris-ai-llm-models`
  and the network `doris-ai`, so the course runs next to the other courses of
  this repository. To use your own Doris 4.x instead, see section 1.3 of
  Module 1 and section 2.3 of Module 2.

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
   and its Lab, `level1/module01-doris-mcp/lab01_connect_agent_to_doris.ipynb`,
   or go straight to
   [Module 2: Call Language Models from SQL with AI Functions](level1/module02-doris-ai-functions/course.md)
   and its Lab, `level1/module02-doris-ai-functions/lab02_doris_ai_functions.ipynb`.

## Dataset

The Labs use two tables in the database `ai_course`, both written for this
course, so they contain no real people, orders, or products:

- `ai_course.events` (Module 1): 14,307 storefront events from March 2026, in
  which 800 shoppers in four regions view, add to the cart, and buy 200 products.
  `datasets/generate_events.py` wrote `datasets/events.csv` from a fixed seed, and
  `datasets/events.yaml` describes the columns and the numbers that the Lab checks
  after loading.
- `ai_course.support_tickets` (Module 2): 14 short customer support tickets, seven
  in English and seven in Chinese, each with a topic and a sentiment that a person
  chose. `datasets/support_tickets.csv` holds them, and
  `datasets/support_tickets.yaml` describes the columns and the numbers that the
  Lab checks. The names and addresses in them are made up, and `example.com` is a
  domain reserved for examples.

## Clean up

To pause, run the stop cells in the last section of a Lab, or
`docker stop doris-ai-llm doris-ai`. The containers keep their data, and
`lab.start()` (and, for Module 2, `lab.start_model()`) starts them again; while
the sandbox is stopped, a Host that starts the launcher reports the Server as
failed.

To remove everything that the course created:

1. Remove the `doris` entry from each Host you connected. Module 1's Clean up
   section says where each Host keeps it; for Codex, run
   `codex mcp remove doris`.
2. In the last section of either Lab, set `REMOVE_EVERYTHING = True` and run the
   cell. It removes the containers `doris-ai` and `doris-ai-llm`, their volumes
   (including the 1.1 GB model file) and network, the launcher's
   `.env.mcp.local`, and the Server's `logs/`.
3. Optionally, delete `doris-course/04-ai-integrations/.venv`.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| The Lab reports a port `in use` | Another program holds the port. Stop it, or set the `DORIS_AI_*` variable to a free port and restart Jupyter. |
| `pip install` fails, or the Lab cannot import `doris_labkit` | Use Python 3.12 or 3.13, and run the install command in `doris-course/04-ai-integrations`. |
| Doris or the model server stops or restarts while you work | Give Docker at least 4 GB of memory for Module 1 and 6 GB for Module 2, then run `lab.start()` and `lab.start_model()`. |
| The Host shows the `doris` Server as failed | Read `level1/module01-doris-mcp/logs/doris_mcp_server_error.log`, then run `lab.check_launcher()` in the Lab. Module 1, section 1.7, lists the common causes. |
| `Database connectivity test failed` while Doris is running | The password in `.env.mcp.local` does not match the account. Run `lab.check_reader_login()` to confirm, then rerun Lab section 3: it sets the account's password to the one in the file. |
| The model file does not download | When huggingface.co cannot be reached, set `DORIS_AI_LLM_MODEL_URL` to the same file on a mirror before you start Jupyter; the Lab rejects a file whose SHA-256 differs. |
| An AI function fails with `Could not resolve host: doris-ai-llm`, or with a batch result that Doris cannot parse | Start the model server with `lab.start_model()`; for answers that Doris cannot parse, see Module 2, sections 2.6 and 2.8. |
