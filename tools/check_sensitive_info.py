#!/usr/bin/env python3
"""Scan the tracked files for secrets, local paths and personal email addresses.

Usage (from the repository root):
    python3 tools/check_sensitive_info.py [ROOT]

ROOT defaults to this repository; it must be a Git work tree, and only the
files Git tracks are read. The patterns are generic: private keys, cloud and
API tokens, paths inside a user's home or temporary directory, and email
addresses outside the reserved example domains (example.com, .test, ...).
Images and other binary files cannot be scanned; review them by eye.

Not scanned: maintenance/, the development area, which is removed before the
repository is published, and tools/, whose checks contain the patterns they
look for. Exits with status 1 when a pattern matches.
"""
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKIP_PREFIXES = ("maintenance/", "tools/")
RULES = {
    "private key": re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})"),
    "API key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}"),
    "local path": re.compile(
        r"(?:/Users|/home)/[A-Za-z0-9._-]+/|[A-Za-z]:\\{1,2}Users\\{1,2}"
        r"|/(?:private/)?var/folders/|~/(?:Desktop|Documents|Downloads)/"
    ),
}
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})")
EXAMPLE_DOMAIN = re.compile(
    r"(?:^|\.)(?:example\.(?:com|org|net)|example|invalid|test|localhost|users\.noreply\.github\.com)$", re.I
)


def tracked_files(root):
    listing = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True)
    for name in listing.stdout.decode("utf-8").split("\0"):
        if name and not name.startswith(SKIP_PREFIXES):
            yield name


def findings(text):
    for number, line in enumerate(text.splitlines(), start=1):
        for rule, pattern in RULES.items():
            for match in pattern.finditer(line):
                yield number, rule, match.group(0)
        for match in EMAIL.finditer(line):
            if not EXAMPLE_DOMAIN.search(match.group(1)):
                yield number, "email address", match.group(0)


def main(argv):
    root = Path(argv[0]).resolve() if argv else REPO
    problems = 0
    for name in tracked_files(root):
        path = root / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data[:8192]:
            continue  # binary
        for number, rule, value in findings(data.decode("utf-8", errors="replace")):
            problems += 1
            print(f"{name}:{number}: {rule}: {value}")
    print(f"{problems} finding(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
