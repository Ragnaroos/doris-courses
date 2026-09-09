"""Reusable single-choice quiz UI for course knowledge checks."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

try:
    import ipywidgets as widgets
    import yaml
    from IPython.display import display
except ImportError as exc:  # pragma: no cover - learner environment diagnostic
    raise RuntimeError(
        "Quiz dependencies are missing. From the course root, run "
        "`.venv/bin/python -m pip install -r requirements.txt`, restart the "
        "Jupyter kernel, and run the initialization cell again."
    ) from exc


_QUIZ_STYLES = """
<style>
.doris-quiz-shell {
  border: 1px solid #dbe4e8;
  border-top: 4px solid #0f766e;
  border-radius: 6px;
  background: #ffffff;
  padding: 22px 24px;
  color: #17212b;
  max-width: 920px;
  box-sizing: border-box;
}
.doris-quiz-kicker {
  color: #0f766e;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .7px;
  text-transform: uppercase;
  margin-bottom: 8px;
}
.doris-quiz-question {
  font-size: 19px;
  line-height: 1.5;
  font-weight: 700;
  margin: 8px 0 14px;
}
.doris-quiz-objective {
  display: inline-block;
  border-radius: 4px;
  background: #f0fdfa;
  color: #115e59;
  font-size: 12px;
  padding: 4px 8px;
}
.doris-quiz-progress-track {
  height: 6px;
  background: #e2e8f0;
  border-radius: 999px;
  overflow: hidden;
  margin: 12px 0 18px;
}
.doris-quiz-progress-value {
  height: 100%;
  background: #0f766e;
}
.doris-quiz-feedback {
  border-left: 4px solid #0f766e;
  border-radius: 4px;
  background: #f0fdfa;
  padding: 12px 14px;
  margin: 14px 0 4px;
  line-height: 1.55;
}
.doris-quiz-feedback.incorrect {
  border-left-color: #d97706;
  background: #fffbeb;
}
.doris-quiz-feedback.warning {
  border-left-color: #b45309;
  background: #fff7ed;
}
.doris-quiz-result {
  font-size: 24px;
  font-weight: 750;
  margin: 4px 0 8px;
}
.doris-quiz-review {
  border-top: 1px solid #dbe4e8;
  margin-top: 18px;
  padding-top: 16px;
  line-height: 1.55;
}
.doris-quiz-review-item {
  margin: 0 0 18px;
}
.doris-quiz-shell .widget-radio-box,
.doris-quiz-shell .jupyter-widget-radio-box {
  overflow: visible;
}
.doris-quiz-shell .widget-radio-box label,
.doris-quiz-shell .jupyter-widget-radio-box label {
  display: block !important;
  position: relative;
  box-sizing: border-box;
  width: 100%;
  height: auto !important;
  min-height: 0 !important;
  padding: 0 0 0 30px;
  white-space: normal !important;
  line-height: 1.45;
  margin: 0 0 12px !important;
}
.doris-quiz-shell .widget-radio-box label:last-child,
.doris-quiz-shell .jupyter-widget-radio-box label:last-child {
  margin-bottom: 2px !important;
}
.doris-quiz-shell .widget-radio-box label input[type="radio"],
.doris-quiz-shell .jupyter-widget-radio-box label input[type="radio"] {
  position: absolute;
  top: 1px;
  left: 0;
  float: none !important;
  width: 16px;
  height: 16px !important;
  margin: 0 !important;
}
.doris-quiz-shell .jupyter-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.doris-quiz-shell .jupyter-button i,
.doris-quiz-shell .jupyter-button .fa {
  margin: 0;
  line-height: 1;
}
</style>
"""


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


class CourseQuiz:
    """Render a one-question-at-a-time, self-assessed course quiz."""

    def __init__(
        self,
        *,
        title: str,
        description: str,
        questions: tuple[QuizQuestion, ...],
    ) -> None:
        if not questions:
            raise ValueError("A quiz must contain at least one question.")
        self.title = title
        self.description = description
        self.questions = questions
        self._current = 0
        self._answers: dict[str, str] = {}
        self._drafts: dict[str, str] = {}
        self._root = widgets.VBox()
        self._root.add_class("doris-quiz-root")

    @classmethod
    def from_yaml(cls, path: str | Path) -> "CourseQuiz":
        quiz_path = Path(path).expanduser().resolve()
        with quiz_path.open("r", encoding="utf-8") as stream:
            document = yaml.safe_load(stream)
        if not isinstance(document, dict):
            raise ValueError(f"Quiz file must contain a mapping: {quiz_path}")

        raw_questions = document.get("questions")
        if not isinstance(raw_questions, list):
            raise ValueError(f"Quiz file has no questions list: {quiz_path}")

        questions = tuple(
            cls._parse_question(raw_question, index, quiz_path)
            for index, raw_question in enumerate(raw_questions, start=1)
        )
        return cls(
            title=str(document.get("title", "Course knowledge check")),
            description=str(document.get("description", "")),
            questions=questions,
        )

    @staticmethod
    def _parse_question(
        raw: Any,
        index: int,
        quiz_path: Path,
    ) -> QuizQuestion:
        if not isinstance(raw, dict):
            raise ValueError(f"Question {index} must be a mapping: {quiz_path}")
        raw_options = raw.get("options")
        if not isinstance(raw_options, list) or len(raw_options) < 2:
            raise ValueError(
                f"Question {index} must contain at least two options: {quiz_path}"
            )
        options = tuple(
            QuizOption(option_id=str(option["id"]), text=str(option["text"]))
            for option in raw_options
        )
        option_ids = {option.option_id for option in options}
        answer = str(raw.get("answer", ""))
        if answer not in option_ids:
            raise ValueError(
                f"Question {index} answer does not match an option: {quiz_path}"
            )
        return QuizQuestion(
            question_id=str(raw.get("id", f"question_{index}")),
            objective=str(raw.get("objective", "Module knowledge")),
            prompt=str(raw.get("prompt", "")),
            options=options,
            answer=answer,
            explanation=str(raw.get("explanation", "")),
        )

    def show(self) -> widgets.VBox:
        """Display the quiz and reset any answers from an earlier attempt."""
        self._current = 0
        self._answers = {}
        self._drafts = {}
        display(widgets.HTML(_QUIZ_STYLES))
        display(self._root)
        self._render_question()
        return self._root

    def _render_question(self) -> None:
        question = self.questions[self._current]
        number = self._current + 1
        total = len(self.questions)
        progress = number / total * 100

        header = widgets.HTML(
            value=(
                f'<div class="doris-quiz-kicker">Question {number} of {total}</div>'
                f'<span class="doris-quiz-objective">{escape(question.objective)}</span>'
                f'<div class="doris-quiz-question">{escape(question.prompt)}</div>'
                '<div class="doris-quiz-progress-track">'
                f'<div class="doris-quiz-progress-value" style="width:{progress:.0f}%"></div>'
                "</div>"
            )
        )
        saved_answer = self._answers.get(question.question_id)
        saved_selection = saved_answer or self._drafts.get(question.question_id)
        choices = widgets.RadioButtons(
            options=[(option.text, option.option_id) for option in question.options],
            value=saved_selection,
            description="",
            layout=widgets.Layout(width="100%"),
        )
        feedback = widgets.HTML()
        previous_button = widgets.Button(
            description="Previous question",
            icon="arrow-left",
            layout=widgets.Layout(
                display="none" if self._current == 0 else "inline-flex"
            ),
        )
        submit = widgets.Button(
            description="Submit answer",
            button_style="success",
            icon="check",
        )
        next_label = (
            "View results" if number == total else "Next question"
        )
        next_button = widgets.Button(
            description=next_label,
            icon="arrow-right",
            layout=widgets.Layout(display="none"),
        )

        def show_feedback(selected: str) -> None:
            correct = selected == question.answer
            if correct:
                feedback.value = (
                    '<div class="doris-quiz-feedback"><strong>Correct.</strong> '
                    f"{escape(question.explanation)}</div>"
                )
            else:
                correct_text = question.option_text(question.answer)
                feedback.value = (
                    '<div class="doris-quiz-feedback incorrect">'
                    "<strong>Not quite.</strong> The correct answer is "
                    f"<strong>{escape(correct_text)}</strong>. "
                    f"{escape(question.explanation)}</div>"
                )

        if saved_answer is not None:
            choices.disabled = True
            submit.disabled = True
            next_button.layout.display = "inline-flex"
            show_feedback(saved_answer)

        def submit_answer(_: widgets.Button) -> None:
            selected = choices.value
            if selected is None:
                feedback.value = (
                    '<div class="doris-quiz-feedback warning">'
                    "Select one answer before submitting.</div>"
                )
                return

            self._answers[question.question_id] = str(selected)
            self._drafts.pop(question.question_id, None)
            choices.disabled = True
            submit.disabled = True
            next_button.layout.display = "inline-flex"
            show_feedback(str(selected))

        def go_back(_: widgets.Button) -> None:
            if question.question_id not in self._answers and choices.value is not None:
                self._drafts[question.question_id] = str(choices.value)
            self._current -= 1
            self._render_question()

        def advance(_: widgets.Button) -> None:
            if self._current + 1 == len(self.questions):
                self._render_results()
            else:
                self._current += 1
                self._render_question()

        submit.on_click(submit_answer)
        next_button.on_click(advance)
        previous_button.on_click(go_back)
        controls = widgets.HBox([previous_button, submit, next_button])
        content = widgets.VBox([header, choices, feedback, controls])
        content.add_class("doris-quiz-shell")
        content.layout = widgets.Layout(max_width="920px")
        self._root.children = (content,)

    def _render_results(self) -> None:
        total = len(self.questions)
        correct_count = sum(
            self._answers.get(question.question_id) == question.answer
            for question in self.questions
        )
        missed = [
            question
            for question in self.questions
            if self._answers.get(question.question_id) != question.answer
        ]
        percent = round(correct_count / total * 100)

        if missed:
            review_items = []
            for question in missed:
                selected = self._answers.get(question.question_id)
                review_items.append(
                    '<div class="doris-quiz-review-item">'
                    f"<strong>{escape(question.prompt)}</strong><br>"
                    f"Your answer: {escape(question.option_text(selected))}<br>"
                    f"Correct answer: {escape(question.option_text(question.answer))}<br>"
                    f"{escape(question.explanation)}</div>"
                )
            review = (
                '<div class="doris-quiz-review"><strong>Review missed questions</strong>'
                + "".join(review_items)
                + "</div>"
            )
        else:
            review = (
                '<div class="doris-quiz-review">All learning objectives in this '
                "knowledge check were answered correctly.</div>"
            )

        result = widgets.HTML(
            value=(
                '<div class="doris-quiz-shell">'
                '<div class="doris-quiz-kicker">Quiz complete</div>'
                f'<div class="doris-quiz-result">{correct_count} of {total} correct ({percent}%)</div>'
                f"<div>{escape(self.description)}</div>{review}</div>"
            )
        )
        retry = widgets.Button(description="Try again", icon="refresh")
        previous_button = widgets.Button(
            description="Previous question",
            icon="arrow-left",
        )

        def restart(_: widgets.Button) -> None:
            self._current = 0
            self._answers = {}
            self._drafts = {}
            self._render_question()

        def review_last_question(_: widgets.Button) -> None:
            self._current = len(self.questions) - 1
            self._render_question()

        retry.on_click(restart)
        previous_button.on_click(review_last_question)
        controls = widgets.HBox([previous_button, retry])
        content = widgets.VBox([result, controls])
        content.layout = widgets.Layout(max_width="920px")
        self._root.children = (content,)
