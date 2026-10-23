"""Reusable single-choice quiz UI for course knowledge checks.

The questions come from the module's quiz YAML file; ``doris_labkit.quizbank``
describes its structure and the fixed shuffled order of the options.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

try:
    import ipywidgets as widgets
    from IPython.display import display

    from .quizbank import QuizOption, QuizQuestion, display_order, load_quiz
except ImportError as exc:  # pragma: no cover - learner environment diagnostic
    raise RuntimeError(
        "Quiz dependencies are missing. From the course root, run "
        "`.venv/bin/python -m pip install -r requirements.txt`, restart the "
        "Jupyter kernel, and run the initialization cell again."
    ) from exc

__all__ = ["CourseQuiz", "QuizOption", "QuizQuestion"]


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
  font-size: 14px;
  font-weight: 700;
  letter-spacing: .7px;
  text-transform: uppercase;
  margin-bottom: 8px;
}
.doris-quiz-question {
  color: #000000;
  font-size: 19px;
  line-height: 1.5;
  font-weight: 700;
  margin: 8px 0 14px;
  white-space: pre-wrap;
}
.doris-quiz-objective {
  display: inline-block;
  border-radius: 4px;
  background: #f0fdfa;
  color: #115e59;
  font-size: 14px;
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
  color: #115e59;
  font-size: 16px;
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
  font-size: 16px;
  margin-top: 18px;
  padding-top: 16px;
  line-height: 1.55;
}
.doris-quiz-result-description {
  font-size: 16px;
}
.doris-quiz-review-item {
  border-bottom: 1px solid #e2e8f0;
  margin: 0 0 28px;
  padding-bottom: 24px;
}
.doris-quiz-review-item:last-child {
  border-bottom: 0;
  margin-bottom: 0;
  padding-bottom: 0;
}
.doris-quiz-review-title {
  display: block;
  font-size: 18px;
  margin-bottom: 6px;
}
.doris-quiz-review-answer-label,
.doris-quiz-review-description-label {
  color: #475569;
  font-size: 16px;
  margin-top: 10px;
}
.doris-quiz-review-answer,
.doris-quiz-review-description {
  box-sizing: border-box;
  display: block;
  width: 100%;
  max-width: 100%;
  border: 1px solid #dbe4e8;
  border-radius: 4px;
  background: #f8fafc;
  color: #17212b;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 15px;
  line-height: 1.5;
  margin: 4px 0 10px;
  padding: 10px 12px;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
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
  font-size: 16px;
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
  top: calc(0.725em - 8px);
  font-size: inherit;
  left: 0;
  float: none !important;
  width: 16px;
  height: 16px !important;
  margin: 0 !important;
}
.doris-quiz-root .jupyter-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.doris-quiz-root .jupyter-button i,
.doris-quiz-root .jupyter-button .fa {
  margin: 0;
  line-height: 1;
}
.doris-quiz-controls { gap: 8px; flex-wrap: wrap; }
.doris-quiz-controls .jupyter-button { width: 170px; flex: 0 0 170px; }
</style>
"""


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
        """Load a quiz file and show its options in the quiz's fixed shuffled order.

        Raises ``doris_labkit.quizbank.QuizFormatError`` (a ValueError) listing
        every problem when the file does not follow the quiz structure.
        """
        quiz = display_order(load_quiz(path))
        return cls(
            title=quiz.title,
            description=quiz.description,
            questions=quiz.questions,
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
                f'<div class="doris-quiz-question">{number}. {escape(question.prompt)}</div>'
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
                visibility="hidden" if self._current == 0 else "visible"
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
            layout=widgets.Layout(visibility="hidden"),
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
            submit.disabled = True
            next_button.layout.visibility = "visible"
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
            submit.disabled = True
            next_button.layout.visibility = "visible"
            show_feedback(str(selected))

        def change_selection(change: dict) -> None:
            self._answers.pop(question.question_id, None)
            if change["new"] is not None:
                self._drafts[question.question_id] = str(change["new"])
            submit.disabled = False
            next_button.layout.visibility = "hidden"
            feedback.value = ""

        choices.observe(change_selection, names="value")

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
        for button in (previous_button, submit, next_button):
            button.layout.width = "170px"
            button.layout.flex = "0 0 170px"
        controls = widgets.HBox(
            [previous_button, submit, next_button],
            layout=widgets.Layout(flex_flow="row wrap"),
        )
        controls.add_class("doris-quiz-controls")
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
            (number, question)
            for number, question in enumerate(self.questions, start=1)
            if self._answers.get(question.question_id) != question.answer
        ]
        percent = round(correct_count / total * 100)

        if missed:
            review_items = []
            for number, question in missed:
                selected = self._answers.get(question.question_id)
                review_items.append(
                    '<div class="doris-quiz-review-item">'
                    f"<strong>{number}. {escape(question.prompt)}</strong><br>"
                    '<div class="doris-quiz-review-answer-label">Your answer:</div>'
                    '<div class="doris-quiz-review-answer">'
                    f"{escape(question.option_text(selected))}</div>"
                    '<div class="doris-quiz-review-answer-label">Correct answer:</div>'
                    '<div class="doris-quiz-review-answer">'
                    f"{escape(question.option_text(question.answer))}</div>"
                    '<div class="doris-quiz-review-description-label">Description:</div>'
                    '<div class="doris-quiz-review-description">'
                    f"{escape(question.explanation)}</div></div>"
                )
            review = (
                '<div class="doris-quiz-review">'
                '<strong class="doris-quiz-review-title">Review missed questions</strong>'
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
                '<div class="doris-quiz-result-description">'
                f"{escape(self.description)}</div>{review}</div>"
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
        controls.add_class("doris-quiz-controls")
        content = widgets.VBox([result, controls])
        content.layout = widgets.Layout(max_width="920px")
        self._root.children = (content,)
