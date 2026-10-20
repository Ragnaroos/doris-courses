#!/usr/bin/env python3
"""Check quiz YAML structure and answer balance.

Usage (from the repository root, with PyYAML installed; any course virtual
environment has it):
    python3 tools/check_quiz_balance.py [--strict] [PATH ...]

PATH defaults to doris-course/. Every quiz must follow the quiz structure
described in doris-course/common/doris_labkit/quizbank.py, the module the
notebooks load quizzes with; a structure problem always fails the check.

For each course level the script also reports how often the correct option
is the longest option, and how the correct answers are spread over the
positions in which learners see them, after the fixed shuffle. With --strict,
a level where either share is above 40%, or a module quiz that does not have
six questions, fails as well.
"""
import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MAX_LONGEST_SHARE = 0.40
MAX_POSITION_SHARE = 0.40
QUESTIONS_PER_QUIZ = 6

try:
    import yaml
except ImportError:  # pragma: no cover - depends on the local environment
    sys.exit("PyYAML is required: run this script with a course virtual environment, "
             "or `python3 -m pip install -r tools/requirements.txt`.")

sys.path.insert(0, str(REPO / "doris-course/common"))
from doris_labkit.quizbank import display_order, parse_quiz, structure_problems  # noqa: E402


def display(path):
    try:
        return path.relative_to(REPO)
    except ValueError:
        return path


def group_name(path):
    parts = display(path).parts
    course = next((part for part in parts if re.match(r"^0\d-", part)), "?")
    level = next((part for part in parts if part.startswith("level")), "")
    return f"{course} {level}".strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--strict", action="store_true",
                        help="also fail on answer balance and on quizzes without six questions")
    args = parser.parse_args()
    roots = [Path(path).resolve() for path in args.paths] or [REPO / "doris-course"]

    stats = defaultdict(lambda: {"total": 0, "longest": 0, "positions": Counter()})
    problems, short_quizzes = [], []
    for root in roots:
        files = [root] if root.is_file() else sorted(root.rglob("quiz*.yaml"))
        for path in files:
            if any(part in {".venv", ".runtime"} for part in path.parts):
                continue
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            found = structure_problems(document)
            problems += [f"{display(path)} {problem}" for problem in found]
            if found:
                continue
            quiz = display_order(parse_quiz(document))
            if len(quiz.questions) != QUESTIONS_PER_QUIZ:
                short_quizzes.append(f"{display(path)}: {len(quiz.questions)} questions")
            item = stats[group_name(path)]
            for question in quiz.questions:
                texts = [option.text for option in question.options]
                answer = [option.option_id for option in question.options].index(question.answer)
                item["total"] += 1
                item["positions"][answer] += 1
                if len(texts[answer]) == max(len(text) for text in texts):
                    item["longest"] += 1

    unbalanced = False
    print(f"{'group':<36} {'questions':>9} {'longest':>9} {'top position':>13}  answers at positions 1 2 3 4")
    for name in sorted(stats):
        item = stats[name]
        total = item["total"]
        longest = item["longest"] / total
        top = max(item["positions"].values()) / total
        counts = " ".join(str(item["positions"].get(i, 0)) for i in range(4))
        flag = ""
        if longest > MAX_LONGEST_SHARE or top > MAX_POSITION_SHARE:
            flag = "  <-- unbalanced"
            unbalanced = True
        print(f"{name:<36} {total:>9} {longest:>8.0%} {top:>12.0%}   {counts}{flag}")
    if short_quizzes:
        print(f"\n{len(short_quizzes)} quiz(zes) without {QUESTIONS_PER_QUIZ} questions:")
        for line in short_quizzes:
            print(f"  {line}")
    if problems:
        print(f"\n{len(problems)} structure problem(s):")
        for problem in problems:
            print(f"  {problem}")
    print(f"\nThresholds: longest option <= {MAX_LONGEST_SHARE:.0%}, single position <= {MAX_POSITION_SHARE:.0%}, "
          f"{QUESTIONS_PER_QUIZ} questions per quiz. Structure problems always fail; the rest fail with --strict.")
    if problems:
        return 1
    return 1 if (args.strict and (unbalanced or short_quizzes)) else 0


if __name__ == "__main__":
    sys.exit(main())
