# AI Integrations: notes for maintainers

The course: [doris-course/04-ai-integrations](../../doris-course/04-ai-integrations/README.md).

## The environment and the data

- The course brings its own sandbox: the container `doris-ai`, ports 39030, 38030,
  and 38040, which the `DORIS_AI_*` variables change.
- `datasets/events.csv` is written by `datasets/generate_events.py` from a fixed
  seed. After changing the generator or the data, update `datasets/events.yaml` and
  the numbers in the lesson; the tests compare them.

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

## New modules

The course is published as a preview, and its README's Roadmap lists the modules to
come, in order: Hybrid Search, AI Functions, and Lakehouse federated retrieval.
Before a new module is published, it meets these requirements:

1. Its lesson says at the start what it uses from Module 1 (the read-only account,
   the launcher, the evidence checks, a `doris_*` domain), and has a "Before you
   begin" section: platform, Docker resources, Python version, the Host or external
   services that it needs, and the accounts and costs.
2. It uses this course's `doris-ai` sandbox, with the same container, ports, and
   `DORIS_AI_*` variables. An extra container or service has the `doris-ai-` prefix
   and a port in the course's range that an environment variable can change. A
   module that needs a model or an embedding service, such as AI Functions, uses a
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
