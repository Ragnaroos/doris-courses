#!/usr/bin/env python3
"""Check relative links and images in Markdown files and notebook Markdown cells.

Usage (from the repository root):
    python3 tools/check_links.py [PATH ...]

PATH defaults to doris-course/. Markdown links and images are checked, and so
are HTML <img src="..."> tags, which the notebooks use for screenshots.
External links (http:, mailto:, ...) and in-page anchors are skipped. Exits
with status 1 when a link is broken.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LINK = re.compile(r'!?\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
HTML_IMAGE = re.compile(r'<img\b[^>]*?\bsrc\s*=\s*["\']([^"\']+)["\']', re.I)
FENCED_CODE = re.compile(r"^(```|~~~).*?^\1", re.M | re.S)
INLINE_CODE = re.compile(r"`[^`\n]*`")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
SKIP_DIRS = {".git", ".venv", ".runtime", ".ipynb_checkpoints", "node_modules", "__pycache__"}


def iter_files(root):
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and path.suffix in (".md", ".ipynb"):
            yield path


def markdown_sources(path):
    if path.suffix == ".md":
        yield "", path.read_text(encoding="utf-8", errors="replace")
        return
    notebook = json.loads(path.read_text(encoding="utf-8"))
    for index, cell in enumerate(notebook.get("cells", [])):
        if cell.get("cell_type") == "markdown":
            yield f" cell {index}", "".join(cell.get("source", []))


def display(path):
    try:
        return path.relative_to(REPO)
    except ValueError:
        return path


def main(argv):
    roots = [Path(arg).resolve() for arg in argv] or [REPO / "doris-course"]
    broken = 0
    for root in roots:
        for path in iter_files(root):
            for where, text in markdown_sources(path):
                text = INLINE_CODE.sub("", FENCED_CODE.sub("", text))
                for match in (*LINK.finditer(text), *HTML_IMAGE.finditer(text)):
                    target = match.group(1)
                    if SCHEME.match(target) or target.startswith("#"):
                        continue
                    file_part = target.split("#", 1)[0]
                    if file_part and not (path.parent / file_part).exists():
                        broken += 1
                        print(f"BROKEN {display(path)}{where}: {target}")
    print(f"{broken} broken link(s)")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
