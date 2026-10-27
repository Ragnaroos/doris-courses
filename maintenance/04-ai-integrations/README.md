# AI Integrations: notes for maintainers

The course: [doris-course/04-ai-integrations](../../doris-course/04-ai-integrations/README.md).

## The environment and the data

- The course brings its own sandbox: the container `doris-ai`, ports 39030, 38030,
  and 38040, which the `DORIS_AI_*` variables change. Module 2 adds the model
  server `doris-ai-llm` on the same network, with the volume `doris-ai-llm-models`
  and the host port 38080 (`DORIS_AI_LLM_PORT`). `lab.teardown()` in either Lab
  removes both containers, all three volumes, and the network.
- `datasets/events.csv` is written by `datasets/generate_events.py` from a fixed
  seed. After changing the generator or the data, update `datasets/events.yaml` and
  the numbers in the lesson; the tests compare them.
- `datasets/support_tickets.csv` (Module 2) was written by hand. After changing a
  ticket, update `datasets/support_tickets.yaml`; the tests compare them. The
  lesson and the Lab name tickets 1002 and 1009 to 1013 for what they show, so
  read those passages again too.

## The reference traces

- The reference trace at the end of each step in section 1.6 of the lesson is a
  real result of calling the MCP Server through the launcher, and the raw results
  are kept for the tests in `tests/fixtures/reference_results.json`.
- After upgrading `doris-mcp-server` or Doris, get the results again with section 6
  of the Lab or with `doris_course.mcp_client.run_host_session`, then update the
  lesson, the fixture, and the lesson's "Tested with" table.
- A known problem of `doris-mcp-server` 1.0.0: `execute_query` with `max_rows` above
  about 2000 returns `CHILD_RESULT_INVALID` for `SELECT *` on `ai_course.events`
  (the check of its output schema fails, and the log hides why); 1000 rows work. The
  lesson only mentions the default limit of 100 rows.

## Module 2: the model and the AI functions

- The model server is `ghcr.io/ggml-org/llama.cpp:server-b11429`, and the model
  is `qwen2.5-1.5b-instruct-q4_k_m.gguf` from the Hugging Face repository
  `Qwen/Qwen2.5-1.5B-Instruct-GGUF` at commit
  `91cad51170dc346986eccefdc2dd33a9da36ead9`. Its URL, size, and SHA-256 are in
  `doris_course/environment.py`, and the lesson's "Tested with" table repeats
  them. To change the model or the server, change them there, run the Lab twice in
  a fresh kernel, update the observed numbers in the lesson (section 2.6) and in
  the Lab's Expected results, and update [images.md](../images.md).
- The Lab measures the model's work from the server: one `total time =` line of
  its log per finished request, and the token counters of its `/metrics`
  endpoint (`--metrics`). The prompt tokens are `prompt_tokens_total` plus
  `prompt_tokens_cached_total`, because the server reuses the start of a prompt
  that it has seen. Another server needs another way to count.
- Model answers are not repeatable, even at `ai.temperature` 0, so the Lab's
  Expected results describe what to look for and give the observed numbers as
  examples. The tests check only what does not depend on the model.
- What the module relies on in Doris 4.1.3 (source tag `4.1.3`, the AI functions
  under `be/src/exprs/function/ai/` and the Resource under
  `fe/fe-core/src/main/java/org/apache/doris/catalog/AIResource.java`), each
  checked in the sandbox:
  - The `local` provider sends the OpenAI request format unless the endpoint ends
    with `chat` or `generate` (Ollama's own format, in which `ai.max_token` is sent
    under a name that Ollama ignores).
  - Scalar functions batch rows up to `ai_context_window_size` bytes (default
    131072) and fail the whole statement unless the answer is a JSON array of as
    many strings. With the course's model every batch of more than one row failed,
    so the Lab sets the variable to 1. `AI_AGG` ignores the variable and packs up
    to 128 KiB per request.
  - `AI_FILTER` and `AI_SIMILARITY` fail with the course's model, which answers
    `[0]` or a bare score; the parser requires strings.
  - `CREATE RESOURCE` contacts no endpoint, for any provider. `SHOW RESOURCES`
    masks `ai.api_key`, but `__internal_schema.audit_log` and `fe.audit.log` keep
    the statement with the key in clear (`ai.api_key` is not in
    `PrintableMap.SENSITIVE_KEY`; 4.1.4 is the same). Calling a Resource checks
    no privilege; `USAGE_PRIV` only filters `SHOW RESOURCES`.
- Where the Doris 4.x documentation differs from 4.1.3: the page "LLM SQL
  Functions" says that `CREATE RESOURCE` probes a hosted endpoint and that
  `AI_SIMILARITY` returns `DOUBLE`; in 4.1.3 there is no probe, and the function
  returns `FLOAT`. The lesson describes 4.1.3. After a Doris upgrade, check these
  points again.

## New modules

The course is published as a preview, and its README's Roadmap lists the modules to
come, in order: Hybrid Search and Lakehouse federated retrieval. Module 2 (AI
functions) meets the requirements below, and is an example for the next ones.
Before a new module is published, it meets these requirements:

1. Its lesson says at the start what it uses from Module 1 (the read-only account,
   the launcher, the evidence checks, a `doris_*` domain), and has a "Before you
   begin" section: platform, Docker resources, Python version, the Host or external
   services that it needs, and the accounts and costs.
2. It uses this course's `doris-ai` sandbox, with the same container, ports, and
   `DORIS_AI_*` variables. An extra container or service has the `doris-ai-` prefix
   and a port in the course's range that an environment variable can change. A
   module that needs a model or an embedding service, such as Module 2, uses a
   local open model by default; a paid service is only an option, and its key comes
   only from an environment variable.
3. The Doris image, `doris-mcp-server`, and the other Python packages have exact
   versions, and the lesson ends with a "Tested with" table: what was verified, on
   which versions, and when.
4. It has a quiz that can be scored: `quizNN_<slug>.yaml` and its notebook, six
   single-choice questions, one for each learning objective of the lesson, in the
   structure of `doris_labkit.quizbank`, passing
   `tools/check_quiz_balance.py --strict` in CI.
5. Its Lab starts with the cell that initializes it, has an Expected result after
   each step, ends with an empty exercise cell followed by a collapsed reference
   solution that runs, and has a clean-up cell. Its offline tests are in the
   course's `tests/`, which CI runs.
6. The results of tool calls that the lesson shows come from real runs, as Module
   1's reference traces do, and the tests check the parts of them that do not
   change.
