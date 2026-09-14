# Module 4: Modeling Data in Apache Doris

| Course information | Value |
| --- | --- |
| Course | Real-time Analytics with Apache Doris — Level 2 |
| Product baseline | Apache Doris 4.x |
| Lab version | Apache Doris 4.1.3 |
| Estimated time | Approximately 65 minutes, including the guided lab |

## Module goal

This module explains how to turn source data and analytical requirements into
a Doris table schema. You will decide what one row represents, what repeated
keys mean, which values a column can hold, and how to organize the resulting
data for its workload.

Level 1 established the persistent `doris_course` Database and its `events`
baseline. Module 2 explained how Doris stores and processes that data;
Module 3 explained how data reaches an internal table. This module applies
those foundations to two different needs: retaining individual events for
flexible analysis and keeping daily measures for a defined reporting grain.

## Learning objectives

After completing this module, you will be able to:

1. Define a table's grain from the source contract and the questions it must
   answer.
2. Select Duplicate Key, Unique Key, or Aggregate Key from the required
   repeated-key behavior, and explain the role of Key columns in each model.
3. Choose types for identifiers, time, money, and categories using their
   meaning, required operations, range, and precision.
4. Distinguish `NULL`, `NOT NULL`, and `DEFAULT`, and place conversion and
   invalid-value handling at the ingestion boundary.
5. Recognize when typed columns, `ARRAY`, `MAP`, `STRUCT`, `JSON`, or `VARIANT`
   fit the source structure.
6. Justify Partition, Bucket, and sort-key choices from lifecycle, filtering,
   distribution, and data volume.
7. Derive a summary grain with additive measures and identify the questions
   that summary can no longer answer.
8. Reconcile detail and summary models using grain-appropriate counts and
   totals, while distinguishing query results from storage or performance
   evidence.

## Module structure

| Section | Format | Time | Outcome |
| --- | --- | ---: | --- |
| 4.1 Define What One Row Represents | Requirements walkthrough | 5 min | Separate source meaning, grain, and analytical requirements |
| 4.2 Choose What Repeated Keys Mean | Model comparison | 6 min | Select a Table Model before choosing its Key columns |
| 4.3 Give Each Field the Right Representation | Type-selection walkthrough | 9 min | Match scalar and complex types to the source contract |
| 4.4 Resolve Missing and Invalid Values at Ingestion | Small-example walkthrough | 7 min | Explain typed validation, defaults, and meaningful nullability |
| 4.5 Organize Data for Its Workload | Physical-design walkthrough | 7 min | Justify the layout of `events_modelled` |
| 4.6 Build a Summary That Preserves the Required Measures | Grain comparison | 6 min | Derive and reconcile `daily_event_metrics` |
| Lab 4 | Hands-on | 25 min | Build the typed sample, complete event model, and daily summary |

---

## 4.1 Define What One Row Represents

A **source contract** describes the meaning and permitted representation of
incoming fields. A **grain** states what one row represents. Both come before
the table definition.

For the course `events` dataset, one row represents one original ecommerce
event. A user can generate many events, and a product can appear in many
users' events. Neither `user_id` nor `product_id` alone identifies an event.

The fields describe that event:

| Field | Meaning in the course contract | Analytical use |
| --- | --- | --- |
| `event_time` | Time of the event | Select a time interval and derive reporting periods |
| `event_id` | Identifier of the original event | Retrieve or inspect individual events |
| `user_id` | Identifier of the user associated with the event | Analyze activity across a user's events |
| `event_type` | Event category, such as `view`, `cart`, or `purchase` | Separate activity types and purchase measures |
| `region` | Course region category | Compare activity across regions |
| `product_id` | Identifier of the associated product | Analyze products and later join product attributes |
| `revenue` | Event revenue; non-purchase events contribute zero in this dataset | Calculate exact monetary totals |

Now consider three requirements:

| Required answer | Appropriate row grain |
| --- | --- |
| Inspect a user's individual events during a time interval | One original event |
| Report daily event count and revenue by region and event type | One `(event_date, region, event_type)` combination |
| Show the current state of an order | One order's current state |

These are different data products. A daily total cannot reveal which user
generated an event. A current order row cannot reconstruct every earlier
state unless that history is retained elsewhere.

Keep event detail and daily totals in separate tables. Placing a summary row
beside the events it summarizes would make an unqualified revenue sum count
the same business activity twice.

### Use observations to check a contract

Lab 4 first checks that `events` contains the expected 10,158,080 rows and
uses `SHOW FULL COLUMNS` to inspect its schema. The count establishes source
availability; the metadata reveals types, nullability, and defaults. Neither
establishes the business meaning of a row by itself.

Similarly, a sample's largest identifier is evidence about today's data, not
a guarantee about tomorrow's range. Choose a durable contract from the source
definition and expected growth, then use data checks to detect violations.

---

## 4.2 Choose What Repeated Keys Mean

A **Table Model** defines the result when new rows have the same Key values
as existing rows. Module 2 introduced the three models; here the choice follows
the required row meaning.

| Requirement | Table Model | Role of Key columns in the course definitions |
| --- | --- | --- |
| Preserve every accepted event row | Duplicate Key | Define the sort key; repeated Key values do not remove rows |
| Expose one current row per business key | Unique Key | Define logical uniqueness for upsert and, by default, sorting |
| Combine measures for the same reporting dimensions | Aggregate Key | Define aggregation groups and sorting; Value columns declare how to merge |

**Key columns** appear in the model's `KEY(...)` clause. **Value columns** are
the remaining columns. In these definitions, Key columns precede Value
columns. Grain is the business decision; the Key definition implements the
chosen model's behavior. See the [Table Model overview](https://doris.apache.org/docs/4.x/table-design/data-model/intro/)
and [model best practices](https://doris.apache.org/docs/4.x/table-design/data-model/tips/).

### Preserve event history with Duplicate Key

`events_modelled` uses `DUPLICATE KEY(event_time, event_id, user_id)`. This
orders event data beginning with time while retaining every accepted row.
It does not enforce uniqueness of `event_id`, or of the complete Key tuple.

If a successful event batch is submitted again as a new write, Duplicate Key
can retain both copies. Preserving history and preventing accidental replay
are separate requirements. Module 3's batch identity and retry rules still
apply; adding an identifier to the sort key does not make a load idempotent.

### Represent current state with Unique Key

An **upsert** updates an existing logical row when its Key is present and
inserts a row when that Key is absent. This fits Module 7's `order_state`,
where the business needs one current state per `order_id`.

New Unique Key tables use **Merge-on-Write (MoW)** by default in Doris 4.x.
Doris resolves repeated keys during writing and uses a delete bitmap to hide
superseded row versions from queries. Background Compaction later reclaims
obsolete stored data. This is the documented mechanism, not an observation
made by Lab 4. See [Unique Key](https://doris.apache.org/docs/4.x/table-design/data-model/unique/)
and [Merge-on-Write](https://doris.apache.org/docs/4.x/table-design/data-model/merge-on-write/).

“Current” also needs an ordering rule when changes arrive out of order.
Module 7 uses a Sequence column to express that rule. A timestamp column
alone does not automatically become a Sequence column.

### Combine reporting measures with Aggregate Key

`daily_event_metrics` groups by date, region, and event type. Its Value columns
use `SUM` because another batch for the same combination should contribute
additional events and revenue. Section 4.6 derives this design from the
reporting requirement.

Choose the Table Model before loading production data: an existing model
cannot be directly converted into another model through schema change.
A different repeated-key contract calls for a newly designed table and a
controlled migration.

---

## 4.3 Give Each Field the Right Representation

A type defines which values and operations a column can represent. Start
with meaning, then consider range, precision, and storage. Use a sufficiently
small type that covers the complete contract, including expected growth.

### Keep identifiers consistent across tables

The baseline uses `BIGINT` for `event_id`, `user_id`, and `product_id`. These
are numeric identifiers under the upstream contract. Keeping their types
consistent avoids repeated conversions and prepares `product_id` for the
fact-dimension join in Module 6.

Do not convert an identifier to a number simply because today's values contain
digits. If leading zeros distinguish `00123` from `123`, or future values can
contain letters, a string contract may be necessary. For numeric measures
with a genuinely bounded range, a smaller integer type may be sufficient.
The [Doris type overview](https://doris.apache.org/docs/4.x/table-design/data-type/)
lists supported integer ranges.

### Preserve the time precision that the source provides

`event_time` uses `DATETIME`, which has second precision when no fractional
precision is specified. `DATETIME(3)` can represent milliseconds and
`DATETIME(6)` microseconds. `DATE` is appropriate for the derived
`event_date` in a daily summary, where the time of day is intentionally lost.

Agree on the source time-zone convention before ingestion. A `DATETIME`
value does not carry its own time-zone identifier, so choosing that type does
not resolve inconsistent source time zones. The course keeps the baseline
timestamps unchanged. See [DATETIME](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/date-time/DATETIME/).

### Use exact decimals for monetary amounts

`DECIMAL(p, s)` specifies **precision** `p`, the total number of decimal
digits, and **scale** `s`, the digits after the decimal point.
`DECIMAL(12,2)` leaves ten digits before the decimal point and two after it;
its largest positive value is `9,999,999,999.99`.

This fits the event-revenue contract. The daily summary uses
`DECIMAL(18,2)` for greater total-value headroom while retaining cents.
Decimal arithmetic is exact within the selected precision and scale, but
range overflow and conversion to a smaller scale still require a policy.
It does not provide unlimited precision. See [DECIMAL](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/numeric/DECIMAL/).

`FLOAT` and `DOUBLE` use approximate binary floating-point representations.
They fit measurements where approximation is acceptable. Lab 4 uses a
deliberately large amount to make their limitation visible: adding one cent
to a `DOUBLE` does not produce the same monetary result as adding it to a
`DECIMAL(18,2)`. This demonstrates numeric representation, not query speed.

Text is a third, different representation. A `VARCHAR` revenue column can
accept `not-a-number`; a query must convert it before calculating revenue.
That moves validation into each analytical query unless ingestion establishes
a typed boundary.

### Bound categories without confusing length and cardinality

`event_type VARCHAR(32)` and `region VARCHAR(16)` accommodate short category
labels and controlled growth. In Doris, the length of `VARCHAR(n)` is a
maximum in **bytes**, not a count of characters; non-ASCII characters may
occupy several bytes. It is variable-length storage, so a larger declared
maximum does not reserve that many bytes for every value. See
[VARCHAR](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/string-type/VARCHAR/).

An unnecessarily large bound weakens the contract by accepting oversized
values that the field should not contain. Narrowing a declaration alone is
not evidence of a measured speedup or proportional storage reduction.

**Cardinality** means the number of distinct values. It is independent of
string length: a short code can have many distinct values. A `VARCHAR(32)`
also does not restrict `event_type` to `view`, `cart`, and `purchase`.
Validate the allowed vocabulary in the ingestion contract when that matters.

### Use complex types for structure that belongs inside a row

The seven stable event fields remain ordinary typed columns. If a source also
contains nested attributes, select a representation based on their shape:

| Source shape | Candidate Doris type | Example purpose |
| --- | --- | --- |
| A sequence of elements with a common type | `ARRAY<T>` | Tags attached to one event |
| Key-value attributes with declared key and value types | `MAP<K,V>` | String-valued event properties |
| A record with named fields and declared types | `STRUCT<...>` | A device record with a known field layout |
| A document accessed with JSON functions | `JSON` | Validated JavaScript Object Notation (JSON) stored in binary form |
| A document whose paths and value types evolve | `VARIANT` | Semi-structured attributes stored using inferred subcolumns |

Consider a possible extension to the event source. This illustrative payload
is not part of the Lab 4 dataset:

```json
{
  "event_id": 90001,
  "tags": ["mobile", "promotion"],
  "device": {"os": "Android", "screen_width": 1080},
  "campaign_labels": {"channel": "email", "campaign": "autumn"},
  "extra": {"experiment": {"group": "B"}, "delivery_minutes": 12}
}
```

`tags` fits an `ARRAY` of strings: each event can have a different number of
tags, but every element has the same declared type. Keeping the collection
inside the row preserves event grain; expanding it into one row per tag would
change the result grain.

If the device contract fixes `os` as text and `screen_width` as an integer,
`STRUCT` expresses those named fields and their different types. For
`campaign_labels`, the set of label names may vary while both names and
values remain strings, which fits `MAP`. The distinction is whether field
names belong to a fixed schema or are themselves data. See
[ARRAY](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/ARRAY/),
[MAP](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/MAP/),
and [STRUCT](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/STRUCT/).

For `extra`, suppose producers can add nested objects, numbers, or strings
without agreeing on a fixed field layout. `JSON` fits a document accessed
through JSON functions; `VARIANT` is a candidate when analysis needs to read
evolving document paths through Doris's subcolumn representation. Receiving
a JSON payload does not require putting the entire event into one JSON or
VARIANT column: `event_id` can still be extracted into its existing `BIGINT`
column, and stable reporting fields can remain explicit typed columns.

Doris `JSON` and `VARIANT` have different storage representations. `JSON`
uses a binary document representation; `VARIANT` can extract paths into
subcolumns. Do not infer identical layout or performance from their ability
to ingest JSON-shaped data. See [JSON](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/JSON/)
and [VARIANT](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/VARIANT/).

Keep frequently filtered, joined, and aggregated fields with stable contracts
as explicit typed columns. Complex types have model and Key restrictions;
the [type reference](https://doris.apache.org/docs/4.x/table-design/data-type/)
describes those constraints. The table above is a choice guide, not a proposal
to change `events_modelled`. Module 5 introduces ARRAY operations using a
small literal without altering this schema.

---

## 4.4 Resolve Missing and Invalid Values at Ingestion

Missing, zero, empty, and invalid are different states. Decide which ones
belong in the analytical model before choosing nullability and defaults.

### Choose a missing-value rule from business meaning

`NULL` represents a missing or unknown value. `NOT NULL` requires a stored
value. `DEFAULT` supplies a value when an insert omits the column, or requests
its default; it does not replace every explicitly supplied `NULL`.

Use the business meaning of absence to choose the rule:

| Business requirement | Column contract | Reason |
| --- | --- | --- |
| The actual value is required for a valid event | `NOT NULL`, with no invented fallback | Ingestion must obtain a valid value or handle the incomplete record |
| Absence is a valid and meaningful state | Allow `NULL` | Preserve that distinction for later analysis |
| An omitted value has an agreed business interpretation | Declare that `DEFAULT` | Give every writer the same fallback rule |

Whether a violating row causes a whole load to fail depends on the load path
and its quality settings. The schema defines which stored values are valid;
the ingestion policy defines how to handle invalid input. Module 3 covered
that distinction for Stream Load. The [CREATE TABLE reference](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/table/CREATE-TABLE/)
defines column defaults and nullability.

In the controlled sample, a missing region is assigned the explicit reporting
category `'unknown'`, while a missing `product_id` remains valid as `NULL`.
Replacing the missing product with zero would invent an identifier unless
the business contract explicitly reserved zero for that purpose.

Lab 4 Section 3 makes these choices observable: one insert supplies region,
another omits it to use the default, and the optional product remains `NULL`.
Explicitly supplying `NULL` would not request the region default. An empty
string is also a supplied value; `NOT NULL` alone does not validate whether a
category is meaningful.

These sample rules differ from the complete baseline. `events_modelled`
keeps both `region` and `product_id` as `NOT NULL`, matching `events`;
it does not introduce the sample's region default or optional product.
Nullability follows each source contract, not a rule that all tables must
allow or forbid missing values.

### Count invalid conversions before they disappear from a total

Lab 4 Section 2 shows that `TRY_CAST` turns malformed revenue into `NULL`,
which `SUM` ignores. Its separate invalid-row count explains why a plausible
total is insufficient. This also reveals an important modeling distinction:
a failed conversion and a legitimately missing product can both appear as
SQL `NULL`, but require different ingestion decisions. Record the cause of
invalid data before it becomes indistinguishable from permitted absence.

`CAST` and `TRY_CAST` are not interchangeable failure policies. Doris 4.x
supports strict conversion through `enable_strict_cast`; invalid `CAST`
behavior depends on that setting and the conversion involved. The 4.1.3
source initializes the setting to `false`, so do not assume strict conversion
merely from the release number. `TRY_CAST` explicitly provides the
NULL-on-failure behavior used here. See [CAST and TRY_CAST](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/conversion/cast-expr/)
and the [4.1.3 session-variable definition](https://github.com/apache/doris/blob/4.1.3/fe/fe-core/src/main/java/org/apache/doris/qe/SessionVariable.java#L2641).

### Establish one boundary for downstream queries

Establish the typed contract before data reaches shared analytical tables,
so downstream queries can use `SUM(revenue)` without rebuilding the same
conversion and missing-value rules. Lab 4 implements this boundary with an
explicit revenue-validation predicate before insertion. It demonstrates
selection of valid rows, rather than rejection of a transaction containing
malformed revenue, and does not measure the time saved by removing casts.

A production pipeline should account for excluded records and retain them
for diagnosis or correction. The sample isolates one invalid field; a broader
source contract also needs validation for identifiers, timestamps, categories,
range, and decimal scale. `TRY_CAST` alone cannot establish every business rule.

Finally, use a zero revenue default only when absence is defined to contribute
zero. A purchase whose amount is unknown should not silently become a
zero-value purchase. The complete-model insert explicitly copies `revenue`
from `events`, so it does not rely on the default to fill existing amounts.

---

## 4.5 Organize Data for Its Workload

Grain, Table Model, and types establish meaning. Partitioning, bucketing, and
sorting organize that data without changing its event-detail grain.

The following is the layout excerpt from the Lab 4 table definition, not a
standalone statement:

```sql
DUPLICATE KEY(event_time, event_id, user_id)
AUTO PARTITION BY RANGE (date_trunc(event_time, 'month'))
()
DISTRIBUTED BY HASH(user_id) BUCKETS 10
PROPERTIES ("replication_num" = "1")
```

### Choose Partitions from time ranges and lifecycle boundaries

Monthly Auto Range Partitioning creates the required calendar-month
Partitions as values arrive during ingestion. The empty `()` declares no
initial Partitions. It fits this historical baseline because the source
dates, rather than today's system date, determine which Partitions are needed.

For example, March 2020 belongs to the interval from
`2020-03-01 00:00:00` inclusive to `2020-04-01 00:00:00` exclusive.
The partition expression assigns rows to that interval; it does not replace
each stored `event_time` with the start of the month.

Time Partitions provide a lifecycle boundary and allow partition pruning
when predicates exclude whole ranges. Auto Partitioning creates missing
Partitions; this definition does not configure automatic retention or delete
old events. See [Auto Partitioning](https://doris.apache.org/docs/4.x/table-design/data-partitioning/auto-partitioning/).

Choose daily rather than monthly boundaries when the retention or replacement
unit requires days and the data volume supports that layout. Avoid a Partition
per event or user: high-cardinality partitioning can create excessive metadata
and small Tablets. A small table with no independent lifecycle requirement
may need no explicit Partition clause at all.

### Choose Buckets from distribution and useful parallelism

Within each Partition, `HASH(user_id)` routes equal user identifiers to the
same Bucket under that Partition's layout. Ten Buckets means ten physical
shards, called **Tablets**, per Partition. It does not mean ten Backend (BE)
nodes; the course runs those shards in a single-BE sandbox.

High cardinality helps distribute values, but frequent activity from a few
users can still create skew. Evaluate value frequencies and data size, not
only distinct counts. Bucket count should reflect per-Partition volume and
available resources: too few can limit parallel work; too many create small
Tablets and management overhead. Ten is the lab configuration, not a universal
production recommendation.

Doris also supports Random bucketing for Duplicate Key tables, as used by the
tiny raw and typed samples. It needs no bucket key, but cannot use equality
on a hash key for tablet pruning. See [Data Bucketing](https://doris.apache.org/docs/4.x/table-design/data-partitioning/data-bucketing/).

### Put useful filters at the beginning of the sort key

The Duplicate Key definition starts with `event_time` because the event
workload frequently selects time ranges. Module 2 explained how ordered
storage and the Prefix Index can narrow scan ranges. The later Key columns
order rows within equal earlier values; including `user_id` last does not
make this equivalent to a sort key beginning with `user_id`.

Sorting does not guarantee the order of a query result. Use a query-level
`ORDER BY` when presentation order matters.

In the Lab 4 definitions, the model's Key columns are also the sort key.
Doris 4.1 additionally supports a separate table-level `ORDER BY` for Unique
Key tables, allowing sorting to differ from the uniqueness key. That feature
does not change the meaning of `UNIQUE KEY` and is not used by these labs.
See the [CREATE TABLE sorting parameters](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/table/CREATE-TABLE/).

The layout choices work together: time determines eligible Partitions,
Hash distribution determines Tablets within them, and the sort key helps
organize scans inside stored data. In query execution, the **Frontend (FE)**
creates and optimizes a distributed query plan and assigns plan fragments;
BE nodes execute the assigned plan fragments. Lab 4 reconciles the resulting
data. It does not run an `EXPLAIN` comparison or a scan-performance benchmark.

---

## 4.6 Build a Summary That Preserves the Required Measures

The reporting requirement is daily event count and revenue by region and
event type. That gives `daily_event_metrics` the grain
`(event_date, region, event_type)`.

`event_id`, `user_id`, and `product_id` do not belong in this summary grain.
Adding `user_id` to the Key would create a different, more detailed grouping.
The full `events_modelled` table remains available for those questions.

### Store measures that can be combined correctly

An **additive measure** can be summed across disjoint sets of events to
produce the combined measure. The summary stores:

| Column | Declaration in the lab | Meaning |
| --- | --- | --- |
| `event_count` | `BIGINT SUM NOT NULL DEFAULT "0"` | Number of represented original events |
| `total_revenue` | `DECIMAL(18,2) SUM NOT NULL DEFAULT "0.00"` | Revenue of those events |

Its `AGGREGATE KEY(event_date, region, event_type)` defines which incoming
rows combine. Lab 4 first uses `GROUP BY` to produce one row per combination
from `events_modelled`. The table's declared `SUM` behavior also allows
contributions from later batches with the same Key to combine.

That later-batch behavior follows the [Aggregate Key model documentation](https://doris.apache.org/docs/4.x/table-design/data-model/aggregate/).
Lab 4 performs one pre-grouped load; it does not independently demonstrate
repeated-key merging across several batches or inspect Compaction. Doris
applies aggregation during ingestion, Compaction, and querying as needed to
return the logical aggregate result.

Replaying a batch is still consequential: a second contribution to a `SUM`
measure can double it. The summary is a separately populated table, not an
automatically refreshed view of `events_modelled`.

### Recognize measures that are not additive

Daily distinct-user counts cannot simply be summed into a monthly distinct
count: a user active on two days would be counted twice. Retain user-level
detail or design a mergeable distinct-count state, such as an appropriate
Bitmap state or **HyperLogLog (HLL)** state. HLL is approximate; exactness for
a Bitmap design depends on the identifier representation used. Neither state
is created in Lab 4.

An average has a similar limitation. To combine event averages across unequal
groups, retain the total and the relevant count, then divide the combined
total by the combined count. An unweighted average of group averages changes
the answer.

### Reconcile the summary at its own grain

The notebook's expected reconciliation is:

| Table | Rows returned by `COUNT(*)` | Represented events | Represented revenue |
| --- | ---: | ---: | ---: |
| `events_modelled` | 10,158,080 | 10,158,080 | 39,984,455.64 |
| `daily_event_metrics` | 280 | 10,158,080 | 39,984,455.64 |

For event detail, `COUNT(*)` counts event rows. For the summary, it counts
date-region-type combinations; `SUM(event_count)` counts represented events.
The notebook labels the first count `stored_rows`, but this is a SQL-visible
logical count, not an inspection of physical rows in Rowsets or Segments.

Matching event and revenue totals are useful reconciliation checks, although
they cannot prove every field was mapped correctly. The smaller summary count
demonstrates a different grain, not a measured query-speed improvement.

The summary has no explicit Partition clause and uses `HASH(region)` with
one Bucket. Its expected 280 groups are small and have no separate
Partition-level lifecycle requirement in this lab. Both the detail and
summary tables use one replica because the sandbox has one BE; that replica
choice does not provide production redundancy.

---

## Lab 4: Model Data for Analytical Workloads

Use the existing `doris_course` Database and complete `events` baseline. The
lab reads that baseline and creates four Module 4 tables:
`modeling_raw_events`, `modeling_typed_events`, `events_modelled`, and
`daily_event_metrics`.

You will:

1. Confirm source availability and inspect the baseline column contract.
2. Load a controlled five-row text sample, count invalid revenue conversions,
   and compare approximate and exact amount arithmetic.
3. Load four valid typed rows, observe an omitted region receive its default,
   and preserve an optional product as `NULL`.
4. Build the complete `events_modelled` table with explicit time Partitions,
   Hash Buckets, and a time-leading sort key; reconcile its count and revenue
   with `events`.
5. Derive `daily_event_metrics` from the reporting grain and reconcile its
   represented events and revenue with event detail.

Open the notebook:

[Lab 4 — Model Data for Analytical Workloads](lab4_model_data.ipynb)

The lab truncates its own targets before rebuilding them so rerunning the
load cells does not append another complete copy. This is a repeatable lab
reset, not an atomic production refresh strategy. It does not reset `events`
or tables owned by other modules.

Keep `events_modelled` for Module 5's analytical queries and Module 6's product
joins. Module 7 maintains independent order-state tables. Optional sandbox
stop and restart cells preserve the course data in Docker named volumes.

## Module summary

- Define grain from the source and reporting requirements before writing a
  table definition.
- Choose the Table Model from repeated-key semantics: preserve event detail,
  replace current state, or combine declared measures.
- Give stable fields explicit types. Select identifier ranges, time precision,
  decimal scale, and string bounds from the full contract.
- Preserve meaningful missing values. Defaults handle omitted values;
  conversion and quality rules handle invalid input.
- Use Partition, Bucket, and sort-key choices to serve a workload without
  changing the meaning of a row.
- Keep detail and summary grains separate, and reconcile them through the
  measures the summary actually retains.

## Official references

- [Table Model Overview](https://doris.apache.org/docs/4.x/table-design/data-model/intro/)
- [Table Model Best Practices](https://doris.apache.org/docs/4.x/table-design/data-model/tips/)
- [Unique Key Model](https://doris.apache.org/docs/4.x/table-design/data-model/unique/)
- [Merge-on-Write](https://doris.apache.org/docs/4.x/table-design/data-model/merge-on-write/)
- [Aggregate Key Model](https://doris.apache.org/docs/4.x/table-design/data-model/aggregate/)
- [Data Types](https://doris.apache.org/docs/4.x/table-design/data-type/)
- [DECIMAL](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/numeric/DECIMAL/)
- [DATETIME](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/date-time/DATETIME/)
- [VARCHAR](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/string-type/VARCHAR/)
- [ARRAY](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/ARRAY/)
- [MAP](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/MAP/)
- [STRUCT](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/STRUCT/)
- [JSON](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/JSON/)
- [VARIANT](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/VARIANT/)
- [CAST and TRY_CAST](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/conversion/cast-expr/)
- [CREATE TABLE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/table/CREATE-TABLE/)
- [Auto Partitioning](https://doris.apache.org/docs/4.x/table-design/data-partitioning/auto-partitioning/)
- [Data Bucketing](https://doris.apache.org/docs/4.x/table-design/data-partitioning/data-bucketing/)
- [Apache Doris 4.1.3 source: session variables and strict CAST default](https://github.com/apache/doris/blob/4.1.3/fe/fe-core/src/main/java/org/apache/doris/qe/SessionVariable.java#L2641)
