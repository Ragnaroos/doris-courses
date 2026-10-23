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

## Course manifests

Each course lists its modules in `course.yaml`: the order, titles, times, and the lesson, Lab, quiz and optional parts of each module, for a course catalog to publish. When you add, rename or retime a module, change `course.yaml`, the lesson's heading and "Estimated time" row, the quiz title and the course README's outline together. The structure is described at the top of `tools/check_course_manifests.py`, which checks that they agree and that every Lab, quiz and optional part in the course is listed.

## Checks

Run the repository checks from the repository root. The quiz, manifest and image checks and the tests of the checks need PyYAML: install `tools/requirements.txt`, or run them with a course virtual environment.

```bash
python3 tools/check_links.py doris-course maintenance README.md CONTRIBUTING.md  # relative links and images
python3 tools/check_notebook_outputs.py --strict   # no outputs, errors, local paths or run state in notebooks
python3 tools/check_quiz_balance.py                # quiz structure, and how the answers are spread
python3 tools/check_course_manifests.py            # each course.yaml against the lessons, quizzes and README
python3 tools/check_image_digests.py --offline     # maintenance/images.md lists every image the courses name
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

## Notes for maintainers

What each course depends on, what to recheck after changing its data, its Doris version or an upstream environment, and what to do before a release are in [maintenance/](maintenance/README.md).

## Continuous integration

GitHub Actions runs the checks above and the offline tests of the shared runtime and every course on each pull request and on `main` (`.github/workflows/ci.yml`).

## License

The repository is licensed under the [Apache License 2.0](LICENSE). As section 5 of the license says, a contribution that you submit for inclusion is licensed under the same terms, unless you explicitly state otherwise.
