"""Notebook display for the order-domain course, built on the shared doris_labkit components."""

import html
import json

import pandas as pd
from IPython import get_ipython
from IPython.display import HTML, display

from doris_labkit.db import report_sql_error
from doris_labkit.results import result_frame, show_frame
from doris_labkit.ui import card, install_styles, show_log, show_sql, workflow_html


def in_notebook():
    return get_ipython() is not None


class WorkflowProgress:
    """Update one shared workflow panel; keep complete logs below the panel."""

    def __init__(self, title, steps):
        self.title = title
        self.steps = steps
        self.current = 1
        self.logs = []
        self.handle = None
        self.notebook = in_notebook()

    def _render(self, state, detail=""):
        panel = workflow_html(self.title, self.steps, self.current, state, detail)
        if self.handle is None:
            self.handle = display(panel, display_id=True)
        else:
            self.handle.update(panel)

    def advance(self, number):
        self.current = number
        self.log(f"[{number}/{len(self.steps)}] {self.steps[number]}")
        if self.notebook:
            self._render("running")
        else:
            print(self.logs[-1], flush=True)

    def log(self, text):
        self.logs.append(text)

    def update(self, detail):
        """Show the latest observation while an asynchronous step is running."""
        self.log(detail)
        if self.notebook:
            self._render("running", detail)
        else:
            print(detail, flush=True)

    def finish(self):
        if self.notebook:
            self._render("success")
            show_log("View complete startup logs", "\n".join(self.logs))
        else:
            print(f"Completed: {self.title}", flush=True)

    def fail(self, detail, *, opened=True):
        self.log(detail)
        if self.notebook:
            self._render("failure", detail)
            show_log("View the failure reason and complete logs", "\n".join(self.logs), opened=opened)
        else:
            print("\n".join(self.logs), flush=True)


def show_records(title, rows, *, columns=None, collapsed=False):
    """Display structured observations without changing their values or returning duplicate output."""
    frame = pd.DataFrame(rows, columns=columns)
    if in_notebook():
        if collapsed:
            table = frame.to_html(index=False, classes="doris-table", border=0, escape=True)
            display(HTML('<details class="doris-log"><summary>' + html.escape(title) +
                         '</summary><div class="doris-result-table-wrap">' + table + '</div></details>'))
        else:
            show_frame(title, frame)
        if {"query_id", "profile_url"}.issubset(frame.columns):
            links = [f'<a href="{html.escape(str(row.profile_url))}" target="_blank" rel="noopener">'
                     f'{html.escape(str(row.query_id))}</a>'
                     for row in frame.itertuples() if str(row.profile_url).startswith(("http://", "https://"))]
            display(HTML('<p>Open the corresponding FE Profile: ' + ' · '.join(links) + '</p>'))
    else:
        print(title)
        print(frame.to_string(index=False))


def show_response(response, title="Stream Load response"):
    content = json.dumps(response, ensure_ascii=False, indent=2)
    if in_notebook():
        rows = [
            (key, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value)
            for key, value in response.items()
        ]
        show_records(title, rows, columns=["Field", "Value"])
        show_log("Complete JSON: " + title, content)
    else:
        print(content)


__all__ = [
    "WorkflowProgress",
    "card",
    "in_notebook",
    "install_styles",
    "report_sql_error",
    "result_frame",
    "show_frame",
    "show_log",
    "show_records",
    "show_response",
    "show_sql",
    "workflow_html",
]
