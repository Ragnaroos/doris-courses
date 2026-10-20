#!/usr/bin/env python3
"""Report committed notebook outputs, error outputs, and local paths.

Usage (from the repository root):
    python3 tools/check_notebook_outputs.py [--strict] [PATH ...]

PATH defaults to doris-course/. Error outputs and local paths always fail
the check. Notebooks are committed without outputs; with --strict, any
remaining output also fails, and so does the other state a run leaves
behind: execution counts, run timestamps in cell metadata, and saved widget
state. The pre-commit hook (see CONTRIBUTING.md) removes all of these.
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOCAL_PATH = re.compile(
    r"(/Users/[^/\s\"']+|/home/[^/\s\"']+|/mnt/[^/\s\"']+|/private/var/folders/|/var/folders/"
    r"|[A-Za-z]:\\\\Users|~/[^/\s\"'\\]+)"
)
RUN_METADATA = ("ExecuteTime", "execution")


def display(path):
    try:
        return path.relative_to(REPO)
    except ValueError:
        return path


def iter_notebooks(root):
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*.ipynb")):
        if ".ipynb_checkpoints" not in path.parts and ".venv" not in path.parts:
            yield path


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--strict", action="store_true", help="fail when any output or run state remains")
    args = parser.parse_args()
    roots = [Path(path).resolve() for path in args.paths] or [REPO / "doris-course"]

    failures = 0
    for root in roots:
        for path in iter_notebooks(root):
            notebook = json.loads(path.read_text(encoding="utf-8"))
            outputs = counts = stamps = 0
            for index, cell in enumerate(notebook.get("cells", [])):
                for output in cell.get("outputs", []) or []:
                    outputs += 1
                    if output.get("output_type") == "error":
                        failures += 1
                        print(f"ERROR   {display(path)} cell {index}: {output.get('ename')}")
                    for local in sorted(set(LOCAL_PATH.findall(json.dumps(output, ensure_ascii=False)))):
                        failures += 1
                        print(f"PATH    {display(path)} cell {index}: {local}")
                if cell.get("execution_count") is not None:
                    counts += 1
                if any(key in cell.get("metadata", {}) for key in RUN_METADATA):
                    stamps += 1
            leftovers = [
                f"{number} {label}"
                for number, label in ((outputs, "output(s)"), (counts, "execution count(s)"),
                                      (stamps, "run timestamp(s)"))
                if number
            ]
            if notebook.get("metadata", {}).get("widgets"):
                leftovers.append("saved widget state")
            if leftovers:
                if args.strict:
                    failures += 1
                print(f"OUTPUT  {display(path)}: {', '.join(leftovers)}")
    print(f"{failures} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
