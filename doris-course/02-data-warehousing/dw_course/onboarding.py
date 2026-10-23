"""Actionable setup failures without replacing IPython's global error handler."""

import html
import os
from pathlib import Path
from urllib.parse import quote

from IPython.display import HTML, display

COURSE_ROOT = Path(__file__).resolve().parents[1]
LABS = {
    1: "level1/module01-introduction/lab01_connect_and_query.ipynb",
    5: "level1/module05-ingestion/lab05_stream_load.ipynb",
    6: "level1/module06-data-quality/lab06_validate_orders.ipynb",
    7: "level1/module07-state-changes/lab07_current_state_and_replay.ipynb",
    9: "level2/module09-modeling-and-joins/lab09_modeling_and_joins.ipynb",
    10: "level2/module10-metric-processing/lab10_metric_processing.ipynb",
    11: "level2/module11-bi-and-ai/lab11_bi_and_ai_delivery.ipynb",
}


class SetupRequired(RuntimeError):
    """Still stop execution, but show recovery links and folded details in IPython."""

    def __init__(self, message, *, labs=(), detail=""):
        super().__init__(message)
        self.links = [("Get started (course README)", "README.md")]
        self.links.extend((f"Open Lab {number}", LABS[number]) for number in labs)
        self.detail = detail

    def _render_traceback_(self):
        from .ui import install_styles

        install_styles()
        links = " · ".join(
            f'<a href="{html.escape(quote(os.path.relpath(COURSE_ROOT / path, Path.cwd()), safe="/"))}">{html.escape(label)}</a>'
            for label, path in self.links
        )
        details = (
            '<details class="doris-log"><summary>Technical details</summary>'
            f'<pre>{html.escape(self.detail)}</pre></details>' if self.detail else ""
        )
        display(HTML(
            '<div class="doris-status failure"><div class="doris-status-title">'
            'One more setup step is needed</div>'
            f'<p>{html.escape(str(self))}</p><p>{links}</p></div>{details}'
        ))
        return [f"SetupRequired: {self}"]
