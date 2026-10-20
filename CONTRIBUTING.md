# Contributing

The courses live in `doris-course/`, one directory per course, each with its own requirements. `doris-course/common/` is the notebook runtime that every course installs, and `tools/` holds the repository checks.

## Notebooks are committed without outputs

Lab and quiz notebooks are committed with no outputs, execution counts or run timestamps. What a learner should see after a step belongs in the Markdown "Expected result" text below the cell, not in a saved output.

A pre-commit hook removes outputs before each commit. Set it up once in your clone:

```bash
python3 -m pip install pre-commit
pre-commit install
```

The hook runs [nbstripout](https://github.com/kynan/nbstripout) on the notebooks you commit. It keeps the cell ids, because the course tests and tools find cells by id. When a commit stops with "files were modified by this hook", the hook has removed the outputs from your copy: add the notebooks again and commit. To clean every notebook at once, run `pre-commit run nbstripout --all-files`.

## Quizzes

Each module's quiz YAML file is the only source of its questions. The structure is described at the top of `doris-course/common/doris_labkit/quizbank.py`. Learners see the options of each question in a fixed shuffled order, so:

- give each option an id that names it, such as `scan_by_date`, not `a` to `d`;
- do not start option text with a letter such as "A. ";
- do not refer to options by letter in explanations; name the option instead.

## Checks

Run the repository checks from the repository root. The quiz check and the tests of the checks need PyYAML: install `tools/requirements.txt`, or run them with a course virtual environment.

```bash
python3 tools/check_links.py                       # relative links and images in Markdown and notebooks
python3 tools/check_notebook_outputs.py --strict   # no outputs, errors, local paths or run state in notebooks
python3 tools/check_quiz_balance.py                # quiz structure, and how the answers are spread
python3 tools/check_sensitive_info.py              # secrets, local paths and personal email addresses
python3 -m unittest discover -s tools/tests        # tests of the checks themselves
```

`check_sensitive_info.py` only knows generic patterns. Screenshots cannot be scanned: before adding one, check it for personal information, account names, unrelated objects from your own environment, and the browser's address bar and profile picture.

## Tests

Each course and the shared runtime have offline tests in their own `tests/` directory. They need no Docker and no running Doris. Create the course's virtual environment with Python 3.10 to 3.13 and install its requirements from the course directory, because the requirements install the shared runtime with the relative path `-e ../common`:

```bash
cd doris-course/02-data-warehousing
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

For the shared runtime, run the same `unittest` command in `doris-course/common` with any course's virtual environment. Changes to `doris-course/common` affect every course, so run the tests of all of them.

The offline tests do not replace running the labs: when you change a lab or its environment, run it from a clean environment as the course README describes.

## Continuous integration

GitHub Actions runs the checks above and the offline tests of the shared runtime and every course on each pull request and on `main` (`.github/workflows/ci.yml`).
