"""Quiz files: load, check and order the questions of a module quiz.

A quiz YAML file is the only source of a module's questions::

    title: "Module N Quiz: <module name>"
    description: <one sentence>
    questions:
      - id: <question_slug>
        objective: <the lesson's learning objective>
        prompt: <question text>
        options:
          - id: <option_slug>
            text: <option text, without a letter prefix such as "A. ">
        answer: <option_slug>
        explanation: <why the answer is correct>

Learners see each question's options in a shuffled order. The order is fixed
for a quiz, so every learner and every run sees the same one, and the correct
options are spread evenly over the positions. Because a letter would not
point to the same option after shuffling, option ids name the option, and
explanations do not refer to options by letter.

This module needs only PyYAML, so the repository checks can use it without
the notebook widget dependencies of ``doris_labkit.quiz``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

QUIZ_KEYS = ("title", "description", "questions")
QUESTION_KEYS = ("id", "objective", "prompt", "options", "answer", "explanation")
OPTION_KEYS = ("id", "text")
SLUG = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
TITLE = re.compile(r"^Module \d+ Quiz: \S")
LETTER_PREFIX = re.compile(r"^[A-Da-d][.)]\s")
LETTER_REFERENCE = re.compile(
    r"(?:^|[\s'\"(])[A-D]:\s|\b(?:[Oo]ptions?|[Cc]hoices?|[Aa]nswers?) [A-D]\b"
)


class QuizFormatError(ValueError):
    """A quiz file does not follow the quiz structure."""


@dataclass(frozen=True)
class QuizOption:
    option_id: str
    text: str


@dataclass(frozen=True)
class QuizQuestion:
    question_id: str
    objective: str
    prompt: str
    options: tuple[QuizOption, ...]
    answer: str
    explanation: str

    def option_text(self, option_id: str | None) -> str:
        for option in self.options:
            if option.option_id == option_id:
                return option.text
        return "No answer"


@dataclass(frozen=True)
class Quiz:
    title: str
    description: str
    questions: tuple[QuizQuestion, ...]


def _text(value: Any) -> str | None:
    """Return a YAML scalar as text, or None when it is empty or not a scalar."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    text = str(value).strip()
    return text or None


def _keys(mapping: dict, expected: tuple[str, ...], where: str) -> list[str]:
    problems = [f"{where}missing '{key}'" for key in expected if key not in mapping]
    problems += [f"{where}unknown key '{key}'" for key in mapping if key not in expected]
    return problems


def _id_problems(value: Any, where: str, kind: str) -> list[str]:
    if not isinstance(value, str):
        return [f"{where}{kind} id must be text; quote values such as yes, no or numbers"]
    if not SLUG.match(value):
        return [f"{where}{kind} id '{value}' is not a slug (lowercase letters, digits and underscores)"]
    return []


def structure_problems(document: Any) -> list[str]:
    """List every way a loaded quiz document breaks the quiz structure."""
    if not isinstance(document, dict):
        return ["the file must contain a mapping with title, description and questions"]
    problems = _keys(document, QUIZ_KEYS, "")
    for key in ("title", "description"):
        if key in document and _text(document[key]) is None:
            problems.append(f"'{key}' must be non-empty text")
    title = _text(document.get("title"))
    if title is not None and not TITLE.match(title):
        problems.append("the title must start with 'Module N Quiz: ' followed by the module name")
    questions = document.get("questions")
    if "questions" in document and (not isinstance(questions, list) or not questions):
        problems.append("'questions' must be a non-empty list")
        return problems
    seen_questions: dict[str, int] = {}
    for number, question in enumerate(questions or [], start=1):
        where = f"Q{number}: "
        if not isinstance(question, dict):
            problems.append(f"{where}each question must be a mapping")
            continue
        problems += _keys(question, QUESTION_KEYS, where)
        if "id" in question:
            id_problems = _id_problems(question["id"], where, "question")
            problems += id_problems
            if not id_problems:
                if question["id"] in seen_questions:
                    problems.append(f"{where}question id '{question['id']}' is also used by Q{seen_questions[question['id']]}")
                seen_questions.setdefault(question["id"], number)
        for key in ("objective", "prompt", "explanation"):
            if key in question and _text(question[key]) is None:
                problems.append(f"{where}'{key}' must be non-empty text")
        explanation = _text(question.get("explanation")) or ""
        reference = LETTER_REFERENCE.search(explanation)
        if reference:
            problems.append(
                f"{where}the explanation refers to an option by letter ('{reference.group(0).strip()}'); "
                "name the option instead, because options are shown in a shuffled order"
            )
        options = question.get("options")
        if "options" in question and (not isinstance(options, list) or len(options) < 2):
            problems.append(f"{where}'options' must be a list of at least two options")
            continue
        option_ids: list[str] = []
        texts: dict[str, int] = {}
        for index, option in enumerate(options or [], start=1):
            at = f"{where}option {index}: "
            if not isinstance(option, dict):
                problems.append(f"{at}each option must be a mapping with id and text")
                continue
            problems += _keys(option, OPTION_KEYS, at)
            option_id = option.get("id")
            if "id" in option:
                id_problems = _id_problems(option_id, at, "option")
                if not id_problems and len(option_id) == 1:
                    id_problems = [
                        f"{at}option id '{option_id}' is a single letter; name the option, "
                        "because options are shown in a shuffled order"
                    ]
                problems += id_problems
                if not id_problems:
                    if option_id in option_ids:
                        problems.append(f"{at}option id '{option_id}' is used twice")
                    option_ids.append(option_id)
            if "text" in option:
                text = _text(option["text"])
                if text is None:
                    problems.append(f"{at}'text' must be non-empty text")
                    continue
                if LETTER_PREFIX.match(text):
                    problems.append(f"{at}the text starts with a letter prefix ('{text[:3]}'); remove it")
                if text in texts:
                    problems.append(f"{at}the text repeats option {texts[text]}")
                texts.setdefault(text, index)
        answer = question.get("answer")
        if "answer" in question and option_ids and answer not in option_ids:
            problems.append(f"{where}answer '{answer}' is not one of the option ids")
    return problems


def parse_quiz(document: Any, source: str = "quiz") -> Quiz:
    """Build a quiz from a loaded YAML document, or raise QuizFormatError."""
    problems = structure_problems(document)
    if problems:
        raise QuizFormatError(
            f"{source} does not follow the quiz structure:\n"
            + "\n".join(f"- {problem}" for problem in problems)
        )
    questions = tuple(
        QuizQuestion(
            question_id=question["id"],
            objective=_text(question["objective"]),
            prompt=_text(question["prompt"]),
            options=tuple(
                QuizOption(option_id=option["id"], text=_text(option["text"]))
                for option in question["options"]
            ),
            answer=question["answer"],
            explanation=_text(question["explanation"]),
        )
        for question in document["questions"]
    )
    return Quiz(
        title=_text(document["title"]),
        description=_text(document["description"]),
        questions=questions,
    )


def load_quiz(path: str | Path) -> Quiz:
    """Read a quiz YAML file; options keep the order of the file."""
    quiz_path = Path(path).expanduser().resolve()
    with quiz_path.open("r", encoding="utf-8") as stream:
        document = yaml.safe_load(stream)
    return parse_quiz(document, source=str(quiz_path))


def _rank(*parts: str) -> int:
    # sha256 instead of the random module: random's shuffle may change across
    # Python versions, and the order must be the same everywhere.
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def display_order(quiz: Quiz) -> Quiz:
    """Return the quiz with each question's options in the order learners see.

    The order is derived from the quiz title and the question and option ids,
    so it changes only when they change. Within a quiz, each position holds
    the correct option of at most one question more than any other position.
    """
    seed = quiz.title
    usage: dict[int, int] = {}
    positions: dict[str, int] = {}
    # Visit the questions in a seeded order, so that the first questions of
    # the file do not always take different positions.
    for question in sorted(quiz.questions, key=lambda q: _rank(seed, q.question_id)):
        position = min(
            range(len(question.options)),
            key=lambda slot: (usage.get(slot, 0), _rank(seed, question.question_id, str(slot))),
        )
        usage[position] = usage.get(position, 0) + 1
        positions[question.question_id] = position
    questions = []
    for question in quiz.questions:
        answer = next(option for option in question.options if option.option_id == question.answer)
        options = sorted(
            (option for option in question.options if option is not answer),
            key=lambda option: _rank(seed, question.question_id, option.option_id),
        )
        options.insert(positions[question.question_id], answer)
        questions.append(replace(question, options=tuple(options)))
    return replace(quiz, questions=tuple(questions))
