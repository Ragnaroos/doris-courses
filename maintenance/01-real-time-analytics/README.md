# Real-time Analytics: notes for maintainers

The course: [doris-course/01-real-time-analytics](../../doris-course/01-real-time-analytics/README.md).

## The data

Many expected results depend on the shape of the course data, which Module 1's
"What the data looks like" and the Dataset section of the course README describe:

- 26 days: 2019-12-01 to 15 and 2020-03-01 to 11.
- Each event type covers its own days. Views: 13 days (2019-12-05 to 11,
  2020-03-03 to 08). Cart additions: 15 days (2019-12-01 to 04, 2019-12-12 to 15,
  2020-03-01 to 03, 2020-03-08 to 11). Purchases: 7 days (2019-12-01 to 04,
  2020-03-01 to 03). Only 2020-03-03 has all three.
- Eight synthetic regions with about 1.27 million events each; 1,580,057 users and
  204,231 products.

These results rely on it: no revenue from March 4 to 8 in Lab 5, section 7; only
cart additions and purchases on 2020-03-01 (75,259 rows) in Lab 4's exercise and in
Labs 8 and 10; the seven days of Lab 1's exercise; and the region bucketing in
Module 4, section 4.7. A daily rate of views to purchases means nothing on this
data, as Module 1 says. A new dataset changes all of them.

## Doris 4.1.3 behavior that the course relies on

Recheck these after changing the Doris version. They were measured on 4.1.3 or read
in its source (commit `7126cf65d96`).

- The S3 table function reads the public bucket with
  `"s3.credentials_provider_type" = "ANONYMOUS"` and two longer timeouts, which a
  slow connection needs. A brace range in an S3 path loses its leading zeros
  (`events-{00000..00039}` finds no file), so the Labs use `*`.
- After a load or a restart, the row counts of `SHOW PARTITIONS` and
  `SHOW TABLETS` stay at -1 or 0 until the BEs report them, about once a minute;
  `lab.wait_for_tablet_rows()` waits for them.
- The dynamic partition scheduler wakes up early when its interval changes. The
  faster path in Lab 10, section 3, relies on it.
- Where RANDOM bucketing applies (Module 4, section 4.7).
- Partial column updates: an `INSERT` with a column list needs
  `enable_unique_key_partial_update = true`, and Stream Load needs
  `partial_columns:true`. New keys follow `partial_update_new_key_behavior = APPEND`
  by default; with `ERROR`, the load fails with E-7003 "Can't append new rows in
  partial update" (Module 7, section 7.3, and Lab 7's exercise).
- `MERGE INTO` works only on a merge-on-write Unique Key table. Other tables fail
  with "merge into command only support MOW unique key olapTable" (Module 7,
  section 7.5).
- Lab 8, section 7: a manual `ANALYZE ... WITH SYNC` collects FULL statistics
  without hot values. `event_type` then has an ndv of 2, and the join is estimated
  at about 37,400 rows against 17,798 actual ones. The automatic ANALYZE in the
  background samples and keeps hot values, and estimates about 17,957, so the
  section runs ANALYZE before EXPLAIN. "planned with unknown column statistics" at
  the end of the plan comes from the hidden delete-sign column of the Unique Key
  table `m08_products`; it does not appear when only `m08_events` is read.
- What the lessons say about LZ4F and ZSTD follows the official Data Compression
  page, and the default, ZSTD, is given without the version that introduced it.
  Check both, and the `partition.retention_count` property of auto range
  partitions, against the documentation of the new version.
- A single-container sandbox can show a Stream Load redirected by the FE only if
  the BE's `webserver_port` equals the host port (18040 on both sides), because the
  FE redirects to the address that the BE registered.

## Exercises

The expected values of each Lab's closing exercise are measured. After changing the
data or the Doris version, run the reference solutions again; Run All runs them. A
reference solution changes only the exercise's own tables and drops them at the
end.

## Quizzes

Each question's `objective` is one of the lesson's learning objectives, word for
word; `tests/test_lessons.py` checks this. When an objective changes, change the
quiz and the objectives that its quiz notebook lists (the `quiz-purpose` cell). A
new question or a new id changes the shuffled order of the options, so run
`tools/check_quiz_balance.py --strict doris-course/01-real-time-analytics`
afterwards.

## Run times

On its first run, Lab 9 reads about 59 MB from S3 for its slice of the data, so its
time depends on the network: about 4 to 5 minutes on a fast connection, and 18
minutes through a slow proxy of about 60 KB/s.
