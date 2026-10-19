"""Notebook runtime shared by the Apache Doris courses.

Each course installs this package from ``doris-course/common`` through its
requirements.txt and builds its own lab helpers on top of it:

- ``ui``: output styles, status cards, SQL blocks, logs, and step progress;
- ``results``: result DataFrames that keep NULL and integers, and their tables;
- ``db``: connecting to Doris and running SQL with readable error cards;
- ``docker``: Docker and process helpers;
- ``shell``: learner-visible Bash with live progress;
- ``profiles``: values read from Query Profile text;
- ``quiz``: the single-choice knowledge-check widget.
"""
