# Data Warehousing: notes for maintainers

The course: [doris-course/02-data-warehousing](../../doris-course/02-data-warehousing/README.md).

## Lessons and quizzes

- The 14 lessons follow one structure: the course information table, Module goal,
  Learning objectives, Module structure, sections numbered N.M, Lab, Summary, Quiz,
  and References. Sections are organized as business question, concept, example,
  and what the result means. A section title names the feature plainly (for
  example, "Streaming Jobs and CDC_STREAM"); the scenario and the meaning of the
  terms belong in the text.
- Each lesson has six learning objectives, one for each of its six quiz questions,
  and its Summary returns to the same objectives. Each question's `objective` is the
  objective's text, word for word; `tests/test_lessons.py` checks this. The
  optional reading of Module 5, `optional05_continuous_ingestion.md`, has six
  questions of its own.
- The lesson's links point to the quiz notebook; the YAML file is only the source
  of its questions.
- The learner's material states each Lab's prerequisites, its risks, and how
  mature a feature is. It does not record how the course was made or tested.
- The times are estimates for the lesson, the Lab, and the quiz together, without
  the setup. Calibrate them when the course is taught.

## What the Labs do not run

The continuous ingestion reading of Module 5 describes four paths, and only two have
a Lab, both optional: Kafka with Routine Load (Lab 5A) and MySQL with Flink CDC and
the Doris connector (Lab 5B). Streaming Jobs with CDC_STREAM, and the loading of new
files from object storage, are described but not run. Before a Lab or a lesson claims
more about them, run them on the target Doris version: their mode, source
requirements, progress, and recovery. A batch Broker Load does not show how a
continuous job behaves, and passing Labs 5A and 5B does not show that recovery from
a failed source or production concurrency works.

## Running the Labs from the command line

`scripts/run_labs.py` runs the code cells of the Level 1 Labs in order, the
collapsed reference solutions too, as Run All does, without writing outputs into
the notebooks. Run it from the course directory, against the course sandbox, with a
database of its own:

```bash
export DW_DATABASE=dw_course_l1_validation
export DW_ALLOW_WRITES=yes          # the Labs rebuild their own tables in DW_DATABASE
.venv/bin/python scripts/run_labs.py
.venv/bin/python scripts/run_labs.py --iceberg      # also the lake environment and Lab 4
# the three extensions need PyArrow: pip install -e '.[extensions]'
DW_DATABASE=dw_course_l1_extensions_check .venv/bin/python scripts/run_labs.py --iceberg --extensions
```

With the main Labs' results already in the database, `--extensions-only` runs just
the extensions. `scripts/run_streaming_labs.py kafka`, `cdc`, or `all` runs the
optional Labs 5A and 5B. Read their first cells for the memory that they need. They
use fixed services and the database `dw_course_l1_streaming`, so only one run of
them at a time can use a sandbox.

Several people can share one sandbox for the main Labs, each with their own
`DW_DATABASE`, set before Jupyter starts.

## The Wide World Importers data

`datasets/wwi/` holds a small part of Microsoft's Wide World Importers sample
database (v1.0, MIT license, `LICENSE.txt`): ten orders (OrderID 1 to 5 and 80 to
84), the dimensions that they reference, and the IDs 1 to 11 that the course's
simulated orders use. Labs 1 to 4 read the ten orders from `sample.json`; Lab 5
unpacks the Parquet files of `wwi-core.tar.gz` and checks each one against
`manifest.json`, which records the selection, the one derived column
(`order_amount` is the sum of quantity times unit price, without tax), the SHA-256
of the source backup, and each file's hash and row count. `DW_WWI_DATA_DIR` points
Lab 5 to a directory that holds the same files instead. The files were exported
from a SQL Server restore of that backup. To change them, export new files from the
same backup, write a new manifest, and run the whole course again: most Labs check
numbers that come from this data.
