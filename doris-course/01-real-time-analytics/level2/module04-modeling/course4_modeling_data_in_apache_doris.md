# Module 4: Modeling Data in Apache Doris

| Course information | Value |
| --- | --- |
| Course | Real-time Analytics with Apache Doris — Level 2 |
| Product baseline | Apache Doris 4.x |
| Lab version | Apache Doris 4.1.3 |
| Estimated time | Approximately 75 minutes, including the guided lab |

## Module goal

This module explains how to translate source data and analytical requirements
into an Apache Doris table schema. You will begin with what one row means and
what should happen when the same Key appears again. You will then choose column
contracts, missing-value rules, Partitions, Buckets, and a sort key from the
workload they must serve.

Level 1 established the persistent `doris_course` Database and its `events`
baseline. Module 2 explained the storage hierarchy and distributed execution;
Module 3 explained how data crosses an ingestion boundary. Module 4 uses those
foundations to build two data products: `events_modelled`, which preserves event
detail, and `daily_event_metrics`, which represents a defined daily summary.

## Learning objectives

After completing this module, you will be able to:

1. Define a table's grain from its source contract and the questions it must
   answer.
2. Select Duplicate Key, Unique Key, or Aggregate Key from the required
   repeated-key behavior, and explain the role of Key columns in each model.
3. Choose types for identifiers, time, money, categories, and semi-structured
   values from their meaning and required operations.
4. Explain why analytical money normally uses `DECIMAL` instead of an
   approximate floating-point or text representation.
5. Distinguish `NULL`, `NOT NULL`, and `DEFAULT`, including omitted values,
   explicit `NULL`, and failed conversion.
6. Recognize repeated runtime casts, unstable identifier types, oversized
   strings, unnecessary nullability, and mixed grain as modeling problems.
7. Design Partition, Bucket, and sort-key choices from time filtering,
   lifecycle boundaries, data distribution, and expected volume.
8. Recognize when `ARRAY`, `MAP`, `STRUCT`, `JSON`, or `VARIANT` fits an
   application structure and when ordinary typed columns remain preferable.
9. Derive a summary grain and additive measures from a reporting requirement.
10. Reconcile detail and summary models with grain-appropriate counts and
    totals while keeping logical query evidence separate from physical-storage
    or performance claims.

## Scenario-led content outline

Imagine an ecommerce analytics platform with three simultaneous needs. It must
retain every browsing, cart, and purchase event; expose the current state of
changing entities such as orders; and serve a recurring dashboard at daily,
regional, and event-type grain. New months arrive continuously, most analysis
starts with a time range, and different fields have different missing-value
rules.

Course and Lab use several tables because each table represents a different
stage or data product. Learn their contracts here; Lab 4 supplies the DDL and
observable results.

| Table | Grain and role | Why the course needs it |
| --- | --- | --- |
| `events` | One source event; persistent Level 1 baseline | Supplies the complete source contract and the detail population to reconcile |
| `modeling_raw_events` | One received sample record with permissive text fields | Isolates the landing-stage need to preserve malformed and missing input before a validation policy accepts it |
| `modeling_typed_events` | One accepted sample event with typed columns | Shows what changes when conversion, nullability, and defaults become an analytical contract |
| `events_modelled` | One accepted event from the complete baseline | Provides query-ready event detail for this module and for Modules 5–6 |
| `daily_event_metrics` | One `(event_date, region, event_type)` summary group | Provides a separate reporting product with additive event-count and revenue measures |

`modeling_raw_events` and `modeling_typed_events` are small teaching boundary
tables. They are not additional production copies that every Doris design must
create. `events_modelled` and `daily_event_metrics` coexist because they answer
questions at different grains, not because one table replaces the other.

Each section turns one requirement into a modeling decision:

| Section | Requirement scenario | Decision developed in this module | Lab 4 evidence |
| --- | --- | --- | --- |
| **4.1 Define one row** | Analysts need event history, current entity state, and daily totals. | Give each data product one explicit grain; do not mix detail and summary rows. | Confirm the `events` source contract and later reconcile detail with summary. |
| **4.2 Choose repeated-key meaning** | Repeated log keys must remain, repeated order keys must replace current state, and repeated metric keys must combine measures. | Choose Duplicate Key, Unique Key, or Aggregate Key from repeated-key semantics. | Build Duplicate Key `events_modelled` and Aggregate Key `daily_event_metrics`; defer Unique Key updates to Module 7. |
| **4.3 Build a valid summary** | A dashboard repeatedly needs daily event counts and revenue by region and event type. | Define the summary grain, store additive measures, identify lost detail, and reconcile represented totals. | Build 280 logical summary rows that represent 10,158,080 events and the same revenue. |
| **4.4 Choose column types** | Reports join identifiers, filter by time, total money exactly, and group bounded categories; a landing amount may still be text. | Select integer or string identifiers, temporal types, `DECIMAL`, and bounded `VARCHAR` from meaning and operations. | Compare permissive text with typed values and observe `DOUBLE` versus `DECIMAL` arithmetic. |
| **4.5 Resolve missing and invalid values** | A missing product is permitted, an omitted region maps to `unknown`, and malformed revenue is invalid. | Use nullable columns, `NOT NULL`, `DEFAULT`, and conversion checks for distinct business states. | Preserve one `NULL` product, apply one region default, and count one invalid amount before typed ingestion. |
| **4.6 Partition by lifecycle range** | Queries and retention use calendar periods while new time ranges arrive continuously. | Choose time Range Partitions and decide whether Auto Partitioning or explicit Partition management fits the lifecycle. | Create and inspect monthly Auto Range Partitions for the source months that actually occur. |
| **4.7 Distribute each Partition into Buckets** | Each monthly range must be divided into physical shards without concentrating a skewed three-value region. | Hash on a sufficiently distributed field and choose Bucket count from volume, cluster resources, and parallelism needs. | Observe `HASH(user_id)`, 10 Buckets per Partition, and 20 Tablets across two Partitions. |
| **4.8 Align the sort key** | Most event queries begin with a time range and then identify event detail. | Place commonly useful filtering columns early while respecting the Table Model's Key semantics. | Inspect `DUPLICATE KEY(event_time, event_id, user_id)` without making a timing claim. |
| **4.9 Represent nested attributes** | An event may carry tags, fixed device fields, dynamic campaign properties, or an evolving payload. | Map application shape to `ARRAY`, `STRUCT`, `MAP`, `JSON`, or `VARIANT`; promote stable analytical fields to typed columns. | Use the decision framework and current official references; Lab 4 creates no complex-type table. |

The requirement comes first in every section. A `CREATE TABLE` statement is the
implementation of those decisions, not the source of them. Lab 4 makes selected
Doris 4.1.3 behavior observable. It does not benchmark schema alternatives,
inspect Rowsets or Segments, demonstrate a delete bitmap, or infer a production
Bucket count from the single-Backend sandbox.

---

## 4.1 Define What One Row Represents

Before naming columns, finish this sentence:

> One row in this table represents ...

That statement defines the table's **grain**. Grain comes from a business and
source contract. It is not discovered by choosing whichever column happens to
be unique in today's sample.

### Separate three common data products

The ecommerce platform needs three different row meanings:

| Data product | One row represents | Example question |
| --- | --- | --- |
| Event history | One accepted user or system event | Which purchases occurred between 09:00 and 10:00? |
| Current state | The currently visible state of one business entity | What is order 7842's current status and shipping address? |
| Summary metrics | One declared combination of reporting dimensions | How many purchase events occurred per date, region, and event type? |

These products may originate from the same activity, but they are not
interchangeable. Event history preserves the sequence and attributes of
individual observations. Current state intentionally hides superseded values
from an ordinary query. A summary intentionally removes dimensions and detail
that its reports do not need.

### Do not mix detail and summary grain

Suppose two purchase events have revenue 12.00 and 18.00. A daily summary for
those events contains revenue 30.00:

```text
event detail                         daily summary

event 101   purchase   12.00         2026-09-15   purchase   30.00
event 102   purchase   18.00
```

If all three rows are placed in one table and a query simply calculates
`SUM(revenue)`, the result is 60.00. The same activity has been represented once
as event detail and again as a summary. A row-type flag could let every query
filter one representation, but the table would still contain mixed grain and
make accidental double counting easy.

Keep the two grains in separate tables. Query event detail when the answer
needs users, products, timestamps, or individual events. Query the summary when
its declared dimensions and stored measures are sufficient.

### Use observations to verify a declared contract

A row count can confirm that the expected source is available. Distinct counts,
minimum and maximum values, and duplicate checks can reveal violations. They do
not replace the declared meaning of a row.

For example, a duplicated `event_id` may indicate bad source data, an event
identifier scoped to another field, or a legitimate repeated delivery. Only
the source contract says which interpretation is correct. Lab 4 therefore uses
`COUNT(*)` to confirm the baseline and schema metadata to inspect its columns;
it does not claim that a full-table `COUNT(DISTINCT ...)` defines the grain.

## 4.2 Choose a Table Model from Repeated-Key Semantics

After defining the grain, ask what an accepted row should do when its Key values
match values already present. Apache Doris provides three main Table Models for
three different answers.

| Repeated-Key requirement | Table Model | Visible logical result |
| --- | --- | --- |
| Preserve every accepted row | Duplicate Key | Matching-Key rows remain available |
| Expose one current row per business Key | Unique Key | A new row upserts the current Key state |
| Combine measure contributions per reporting Key | Aggregate Key | Value columns merge with declared aggregate functions |

The model expresses row meaning and change semantics. Choose it before chasing
a perceived performance advantage. Doris does not directly convert an existing
table from one Table Model to another; a changed contract normally requires a
new table and a controlled data transition. See the [Table Model overview](https://doris.apache.org/docs/4.x/table-design/data-model/intro/)
and [Table Model best practices](https://doris.apache.org/docs/4.x/table-design/data-model/tips/).

### Preserve an append-style history with Duplicate Key

An event log or audit trail usually requires every accepted observation. A
user can create many events, and two events may even share all declared Key
values if the source contract permits it. A Duplicate Key table retains those
rows rather than using the Key as a uniqueness constraint.

In this model, Key columns primarily establish the sort key. The declaration

```sql
DUPLICATE KEY(event_time, event_id, user_id)
```

does not mean “one row per `(event_time, event_id, user_id)`.” The grain of
`events_modelled` remains one accepted source event. Repeated Key values are
not automatically replaced or aggregated. See the [Duplicate Key model](https://doris.apache.org/docs/4.x/table-design/data-model/duplicate/).

### Expose current state with Unique Key

An order-state table has a different contract:

| `order_id` | `status` | Meaning |
| ---: | --- | --- |
| 7842 | `paid` | Earlier accepted state |
| 7842 | `shipped` | New current state for the same order |

If ordinary queries should expose one current logical row for `order_id = 7842`,
`order_id` belongs in a Unique Key. New records for that Key perform an upsert.
Doris 4.x uses the Merge-on-Write implementation by default for Unique Key
tables, so the write path establishes current logical visibility for later
queries.

Arrival order is not always business order. Change Data Capture (CDC) events
can arrive late or be retried. A Sequence column can make a source version or
event time decide which state wins. Module 7 demonstrates full-row upsert,
partial column update, Sequence-column behavior, and deletion. Module 4 only
establishes why a current-state requirement selects Unique Key. See the
[Unique Key model](https://doris.apache.org/docs/4.x/table-design/data-model/unique/)
and [Merge-on-Write](https://doris.apache.org/docs/4.x/table-design/data-model/merge-on-write/).

### Combine measure contributions with Aggregate Key

A reporting pipeline may receive several contributions for the same
`(event_date, region, event_type)` combination. If `event_count` and
`total_revenue` should be added, an Aggregate Key table declares those
dimensions as Key columns and the measures as Value columns with `SUM`:

```text
(2026-09-15, east, purchase, event_count=4, total_revenue=90.00)
(2026-09-15, east, purchase, event_count=3, total_revenue=65.00)
                                      |
                                      v
one logical group representing event_count=7 and total_revenue=155.00
```

Aggregate Key columns define both the aggregation group and the sort key.
Value columns define how contributions merge. Different Value columns can use
different supported aggregate methods when their contracts require it.

This model is not a general replacement for event detail. Once individual
event identifiers and timestamps are absent, the table cannot reconstruct
them. It is also not a retry-deduplication mechanism: inserting the same metric
contribution twice can add it twice. Load identity and retry safety still need
the contracts introduced in Module 3. See the [Aggregate Key model](https://doris.apache.org/docs/4.x/table-design/data-model/aggregate/).

## 4.3 Derive a Summary Model from the Reporting Requirement

The dashboard repeatedly needs daily event count and total revenue by region
and event type. Begin with that output, then derive the table contract.

### Define dimensions and measures separately

One summary row represents one:

```text
(event_date, region, event_type)
```

Those three dimensions become the Aggregate Key. The table stores two Value
columns:

- `event_count BIGINT SUM` represents the number of events contributing to the
  group.
- `total_revenue DECIMAL(18,2) SUM` represents their additive revenue.

`DECIMAL(18,2)` gives the accumulated summary more integral range than the
per-event `DECIMAL(12,2)` source. The required precision should follow expected
group size and revenue range rather than copying the detail type automatically.

The summary does not carry `event_id`, `user_id`, or `product_id`, because they
would change its grain. It therefore cannot answer which user purchased,
recover an individual event, or group accurately by product.

### Store only measures that combine correctly

Counts and revenue totals are additive across disjoint event contributions.
Several common metrics are not safely additive:

- A distinct-user count can count the same user in several batches or groups.
  An ordinary `SUM` of those counts overstates the union. A mergeable Bitmap or
  HyperLogLog (HLL) state may fit an approximate or exact distinct-count design,
  depending on the requirement.
- An average should not normally be added. Store a compatible numerator and
  denominator, then calculate the weighted result.
- Ratios and percentages generally need their underlying additive components.
- Minimum and maximum can merge with their matching aggregate semantics, but
  they do not behave like a sum.

The reporting question must identify how later batches and rollups combine.
Declaring `SUM` is a semantic promise, not just column syntax.

### Reconcile at the summary grain

`COUNT(*)` means different things in the two models:

| Table | `COUNT(*)` counts | Event population represented by one row |
| --- | --- | --- |
| `events_modelled` | Event-detail rows | One event |
| `daily_event_metrics` | Date-region-event type groups | `event_count` events |

Lab 4 observes 10,158,080 visible detail rows and 280 visible summary rows. The
280 is the number of SQL-visible summary groups. It is not a physical count of
Rows in Segments or Rowsets.

Reconcile the models using measures that both can represent:

```text
COUNT(*) from events_modelled
        = SUM(event_count) from daily_event_metrics
        = 10,158,080 represented events

SUM(revenue) from events_modelled
        = SUM(total_revenue) from daily_event_metrics
        = 39,984,455.64 represented revenue
```

Matching totals verifies the declared additive measures for this load. It does
not prove that the summary can answer every detail question, that Aggregate Key
merged several separate batches, or that the summary has a particular
performance advantage. The lab truncates the target and performs one
pre-grouped insert, so repeated-Key merging across batches is an official
mechanism explanation rather than an observed lab result.

## 4.4 Choose Data Types from Business Meaning

A data type should represent the valid domain of a field and support the
operations that matter. Choosing from the values visible in one file can
underestimate future range, precision, or structural needs.

Start with the required operations and correctness, then consider storage and
calculation cost:

| Business value and required behavior | Suitable starting type | Main tradeoff to evaluate |
| --- | --- | --- |
| Whole counts, quantities, or identifiers defined as numeric | The smallest integer type with safe future range | A narrower type uses less space, but an underestimated range can overflow |
| Money, account balances, tax rates, or another base-10 quantity requiring declared scale | `DECIMAL(p, s)` | Exact decimal behavior requires choosing sufficient precision and may use wider arithmetic as precision increases |
| Sensor measurements, scientific observations, coordinates, or model scores where approximation is acceptable | `FLOAT` or `DOUBLE` | Wide range and conventional floating-point computation come with representation error, non-associative aggregation, and unsuitable exact-equality semantics |
| Opaque identifiers or categorical labels | Bounded `VARCHAR` | Preserves formatting and nonnumeric identity but should not be used as a substitute for a number that every query must parse |
| Calendar date or event timestamp | `DATE` or `DATETIME(p)` | Precision and time-zone meaning must match the source and reporting boundaries |

Fixed-width and lower-precision numeric operations can be cheaper than wider
high-precision arithmetic, so `DOUBLE` may outperform a sufficiently wide
`DECIMAL` for some calculations. That is a workload-dependent performance
question, not a data-correctness rule. Do not store money as `DOUBLE` merely on
the assumption that it is faster. First decide whether approximation is valid;
then benchmark representative expressions and data volumes if the performance
difference matters.

### Keep identifiers consistent

An identifier may contain digits without being a quantity. Choose its type from
the source contract:

- Use an integer type when the identifier is defined as numeric, fits the
  selected range, and does not require formatting such as leading zeroes.
- Use a string type when letters, leading zeroes, composite formatting, or an
  external opaque convention belongs to the identity.

The same business Key should use compatible types in fact, dimension, and
state tables. Storing `product_id` as `BIGINT` in one table and as loosely
formatted text in another introduces repeated casts and can complicate Join
conditions. A cast in an occasional migration is normal; the same cast in
every production query signals an unresolved schema boundary.

### Represent time at the required precision

Use `DATE` when the value is a calendar date without time-of-day meaning. Use
`DATETIME` when the source and analysis require date and time. Doris supports
fractional-second precision in `DATETIME(p)`; choose `p` from the actual source
contract rather than inventing precision the source does not provide.

A temporal type does not define the business time zone. Document whether the
value represents Coordinated Universal Time (UTC), a local business zone, or
another convention. Daily boundaries are ambiguous until that convention is
known. See [DATETIME](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/date-time/DATETIME/).

### Use exact fixed-point values for money and deliberate approximation for measurements

`DECIMAL(p, s)` gives an exact fixed-point contract:

- `p`, the precision, is the total number of significant decimal digits.
- `s`, the scale, is the number of digits after the decimal point.

For `DECIMAL(12,2)`, two digits belong to cents and the remaining capacity
supports the integral range. Choose enough precision for valid future values,
intermediate arithmetic, and required totals.

`FLOAT` and `DOUBLE` are approximate IEEE 754 binary floating-point types.
Choose them for values such as temperature, signal strength, coordinates, or a
statistical score only when small representation differences are acceptable.
`DOUBLE` provides more precision and range than `FLOAT`, but it still does not
represent every decimal fraction exactly. Floating-point addition is not
strictly associative, so distributed aggregation order can also expose small
differences. Avoid floating-point columns as exact Join Keys or equality-based
business identifiers.

For money, sufficiently large floating-point values can no longer represent
every cent. Text preserves characters but does not guarantee a valid amount and
forces conversion before numeric operations. Lab 4 makes both problems
observable: one text value fails conversion, and adding one cent to a large
`DOUBLE` does not produce the exact decimal result. See [DECIMAL](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/numeric/DECIMAL/)
and [Floating-Point Types](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/numeric/FLOATING-POINT/).

### Bound category strings without confusing two concepts

`event_type` and `region` are short categories, so bounded `VARCHAR` types
express their expected maximum length. String length and cardinality are
different:

- **Length** is the maximum number of characters or bytes required by one
  value's type contract.
- **Cardinality** is the number of distinct values appearing in the data.

A region can have low cardinality while each label still needs several
characters. An oversized `VARCHAR` does not create more category values, but it
weakens the contract and can increase unnecessary storage or processing costs.
Leave sensible headroom for controlled future values rather than using the
largest possible declaration by habit. See [VARCHAR](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/string-type/VARCHAR/).

## 4.5 Give Missing, Omitted, and Invalid Values Different Rules

The following source conditions are not equivalent:

1. A product does not apply to an event.
2. A region was omitted and the business has agreed to classify it as
   `unknown`.
3. Revenue contains `not-a-number` and cannot satisfy the monetary contract.

One universal `NULL` or default rule would hide these differences.

### Choose nullability from allowed business states

Use a nullable column when absence is a valid state such as unknown, not yet
provided, or not applicable. Queries must then define how that state behaves in
filters, groups, counts, and Joins. For example, `COUNT(product_id)` ignores
`NULL`, while `COUNT(*)` still counts the event row.

Use `NOT NULL` when every accepted row must contain a valid value. This makes a
minimum data-quality requirement part of the table contract. Avoid declaring
every field nullable merely because a source parser can produce missing values.
That transfers unresolved decisions into every downstream query.

### Use `DEFAULT` only for an agreed omission rule

A default supplies a value when the target column is omitted from an insert.
For example:

```sql
region VARCHAR(16) NOT NULL DEFAULT "unknown"
```

supports a contract in which an omitted region belongs to the `unknown`
reporting category. It does not mean that an explicitly supplied `NULL` should
be silently converted, and it does not repair a malformed region value.

The distinction matters operationally:

| Input condition | Appropriate result for the lab contract |
| --- | --- |
| `product_id` is absent and absence is allowed | Store `NULL` in a nullable column |
| `region` is omitted and `unknown` is agreed | Omit the target column so its default applies |
| `region` is explicitly `NULL` in a `NOT NULL` column | Reject or transform before the insert according to the ingestion policy |
| Revenue text cannot become `DECIMAL(12,2)` | Count and route or reject the invalid row; do not treat it as valid missing revenue |

### Establish a typed ingestion boundary

`TRY_CAST` is useful when a landing table must preserve permissive source text.
It returns `NULL` when the conversion cannot be performed. That lets an
ingestion query count invalid rows before selecting valid typed values.

Do not calculate only
`SUM(TRY_CAST(revenue_text AS DECIMAL(12,2)))` and declare success. Aggregate
functions such as `SUM` ignore `NULL`, so malformed values could disappear from
the total. Pair the calculation with an invalid-row count and an explicit
policy. Once valid rows enter a typed analytical table, downstream queries can
use `SUM(revenue)` without repeating parsing logic. See [CAST and TRY_CAST](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/conversion/cast-expr/).

## 4.6 Choose Time Partitions from Query and Lifecycle Boundaries

Most event queries read recent time ranges, while retention, replacement, and
backfill operate on complete calendar periods. A Range Partition maps each row
to a declared value interval and gives Doris a data-management boundary inside
the table.

### Treat Partition as a value range that contains Tablets

A Partition is often called a logical range because a rule such as
`[2020-03-01, 2020-04-01)` decides membership. That does not mean the Partition
has no physical consequence. Each Partition contains Buckets represented by
Tablets. The two levels answer different questions:

```text
events_modelled
    |
    +-- December 2019 Partition: which time range?
    |       +-- Tablet 1: which hash bucket?
    |       +-- ...
    |       +-- Tablet 10
    |
    +-- March 2020 Partition: which time range?
            +-- Tablet 1: which hash bucket?
            +-- ...
            +-- Tablet 10
```

Partitioning supports metadata-based range exclusion when a query predicate
matches the Partition key, and it provides a unit for lifecycle operations such
as dropping or replacing a period. Lab 4 inspects the generated ranges; it does
not run a pruning benchmark because Module 2 already demonstrates pruning.

### Choose a useful time grain

Partition granularity follows the workload:

- Daily Partitions can give fine lifecycle control but create more metadata and
  smaller physical units.
- Monthly Partitions reduce the number of Partition objects but make a whole
  month the natural lifecycle boundary.
- A very coarse Partition can contain too much data for precise retention or
  replacement work.

There is no universal day-or-month answer. Consider the amount of data per
period, common filter ranges, retention policy, backfill size, and expected
number of Partition objects.

### Use Auto Range Partitioning for rule-driven arrival

If new time values arrive continuously and their boundaries follow a stable
rule, Auto Range Partitioning can create the required Partition when data needs
it. The lab declaration uses:

```sql
AUTO PARTITION BY RANGE (date_trunc(event_time, 'month'))
```

The current source has events in December 2019 and March 2020. Doris therefore
creates those two monthly ranges. It does not create empty January and February
Partitions merely to fill the gap. This observed result follows the loaded
values and monthly expression; another dataset can produce different ranges.

Choose explicit Partition management when boundaries require advance approval,
special names, or a tightly controlled lifecycle process. Auto Partitioning
automates range creation. It does not choose the Table Model, validate grain,
select the Bucket key, or define the sort key. See [Auto Partitioning](https://doris.apache.org/docs/4.x/table-design/data-partitioning/auto-partitioning/).

## 4.7 Use Buckets to Distribute Data Within Every Partition

One monthly Partition can still contain millions of rows. Doris divides each
Partition into Buckets, each represented by a Tablet. Tablets are the physical
data shards distributed and processed by Backend (BE) nodes.

### Choose a Hash key that can spread the workload

With Hash distribution, Doris hashes the selected distribution columns to
choose a Bucket inside the row's Partition. The key should have enough distinct
and sufficiently distributed values for the workload.

The module scenario offers two candidates:

| Candidate | Data shape | Likely distribution consequence |
| --- | --- | --- |
| `region` | Only a few values with heavy skew | Many rows can concentrate in the Buckets reached by dominant values |
| `user_id` | Numerous values distributed across the event population | Hash values can use the available Buckets more evenly |

This is why `events_modelled` uses `HASH(user_id)`. It does not promise exactly
the same number of rows in every Tablet. Hash distribution controls the mapping
rule; the source frequency distribution still affects the outcome.

Random distribution can spread rows without preserving a key-based placement
relationship. In the current Doris 4.x contract, Random distribution applies
to Duplicate Key tables, while Unique Key and Aggregate Key use Hash
distribution. Hash distribution is useful when stable placement by selected
columns benefits filtering or Join layouts. Module 6 explains how compatible
distribution may affect Join strategies; do not select a Hash key solely from
one future Join without considering overall skew and workload.

### Choose Bucket count as a capacity decision

Bucket count affects Tablet size, scheduling, and available parallel work:

- Too few Buckets can create very large Tablets and limit parallelism.
- Too many Buckets can create small Tablets and unnecessary metadata and
  scheduling overhead.

Consider rows and bytes per Partition, cluster size, expected growth,
concurrency, compaction pressure, and the useful degree of parallelism. The ten
Buckets in Lab 4 make the two-level layout visible and fit the course data; they
are not a production recommendation.

For the observed table:

```text
2 generated Partitions × 10 Buckets per Partition = 20 Tablets
20 Tablets × 1 replica in the sandbox = 20 Tablet replicas
```

A production cluster would place replicas across eligible BE nodes according
to its allocation policy. The single-BE lab can verify Tablet count and row
distribution metadata, but it cannot demonstrate multi-node placement or
parallel speed. See [Data Bucketing](https://doris.apache.org/docs/4.x/table-design/data-partitioning/data-bucketing/).

## 4.8 Align the Sort Key with the Main Access Path

Doris stores table data in the order defined by its Key columns. This ordering
supports prefix-based data access and compression behavior. The Table Model
determines what else those Key columns mean:

| Table Model | Additional Key responsibility |
| --- | --- |
| Duplicate Key | Sort rows; matching Keys do not imply uniqueness |
| Unique Key | Sort rows and identify the logical upsert Key |
| Aggregate Key | Sort rows and identify the aggregation group |

### Begin the event sort key with the common range filter

Most queries over `events_modelled` first restrict `event_time`. The sort key

```sql
DUPLICATE KEY(event_time, event_id, user_id)
```

therefore begins with time, followed by stable detail identifiers. This is
compatible with the event-history contract because Duplicate Key does not use
those columns to remove matching rows.

Ordering should follow real access patterns, not an attempt to include every
possible filter column. A leading low-selectivity field can weaken the usefulness
of later fields for common predicates. Conversely, a field used only in rare
queries may not justify an early position.

### Keep the three layout questions separate

| Design layer | Question answered for an event row |
| --- | --- |
| Partition | Which time range contains the row? |
| Bucket / Tablet | Which shard inside that Partition receives the row? |
| Sort key | In what column order is data organized within the table's storage? |

Putting `event_time` in the sort key does not create monthly ranges. Partitioning
by time does not order every row or decide its Hash Bucket. Hashing `user_id`
does not make it a uniqueness constraint. The three choices cooperate, but
each implements a different part of the workload contract.

Lab 4 inspects the declaration and generated layout. It does not compare query
times between alternative sort keys. A performance conclusion would require
equivalent data, controlled queries, and Query Profile evidence.

## 4.9 Map Complex Types from the Application Structure

Some attributes naturally belong inside one event row. Choose a complex type
from that structure and its analytical operations, not because the source is
nested or because one type appears more flexible.

| Application shape | Candidate Doris type | Example |
| --- | --- | --- |
| Ordered values of one element type | `ARRAY` | Tags or experiment identifiers attached to one event |
| Fixed named fields with known types | `STRUCT` | Device operating system, version, and form factor |
| Dynamic key-value attributes | `MAP` | Campaign properties whose names vary by event |
| JSON document retained and queried as JSON | `JSON` | A payload whose document structure must remain available |
| Evolving semi-structured document requiring flexible subfields | `VARIANT` | Partner events whose attributes change across producers |

An `ARRAY` preserves an ordered collection in one row; it does not represent
several independent event rows. A `STRUCT` fits a stable set of named child
fields. A `MAP` fits keys that vary while its key and value type contracts
remain meaningful. `JSON` and `VARIANT` support document-oriented and evolving
data, but flexibility does not remove the need for governance.

### Promote stable analytical fields

Fields used frequently for filtering, Partitioning, Bucketing, sorting, Joins,
grouping, or measures usually deserve ordinary typed columns. Keeping
`event_time`, `user_id`, `region`, and `revenue` buried inside a flexible payload
would force every query to recover the same contract.

Complex values work well for secondary attributes whose nested shape belongs
to a single row. Before production use, check the current Doris version for:

- supported nesting and element types;
- available access, transformation, and expansion functions;
- nullability and conversion behavior;
- restrictions on Key, Partition, distribution, index, and Join use;
- ingestion format and schema-evolution behavior.

These capabilities evolve. Use the application shape to select candidates,
then confirm syntax and restrictions in the current [ARRAY](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/ARRAY/),
[MAP](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/MAP/),
[STRUCT](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/STRUCT/),
[JSON](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/JSON/),
and [VARIANT](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/VARIANT/)
documentation. Lab 4 does not create complex-type columns; Lab 5 uses a small
array literal to demonstrate row and element operations without changing the
event schema.
---

## Lab 4: Model Data for Analytical Workloads

Open [Lab 4 — Model Data for Analytical Workloads](lab4_model_data.ipynb) after
the Level 1 `events` baseline is available. The Notebook uses four Module 4
target tables and does not replace or delete the baseline:

- `modeling_raw_events` contains a five-row permissive landing sample.
- `modeling_typed_events` contains the four valid typed sample rows.
- `events_modelled` contains the complete event-detail model for Modules 5 and
  6.
- `daily_event_metrics` contains the daily reporting summary.

The five numbered lab steps provide these observations:

| Lab step | What you do | What the result establishes |
| --- | --- | --- |
| 1 | Confirm 10,158,080 baseline rows and inspect column metadata | The source is available and its stored types, nullability, and defaults can be checked; grain still comes from the source contract |
| 2 | Query text revenue with `TRY_CAST` and compare `DOUBLE` with `DECIMAL` | A permissive string accepts an invalid amount; failed conversion needs a separate count; approximate arithmetic can lose cent-level precision |
| 3 | Insert valid values through a typed boundary | Four rows remain, one omitted region receives `unknown`, one valid product remains `NULL`, and revenue totals 39.94 |
| 4 | Build and inspect `events_modelled` | Duplicate Key preserves 10,158,080 events; two monthly Partitions each contain 10 Hash Buckets, producing 20 Tablets in this sandbox |
| 5 | Build and reconcile `daily_event_metrics` | 280 visible groups represent all 10,158,080 events and the same 39,984,455.64 revenue |

In Step 4, the two generated Partitions reflect only source months that occur:
December 2019 and March 2020. The metadata does not show empty January and
February ranges because Auto Partitioning did not need to create them. The
Tablet summary is direct metadata evidence of the current layout. It does not
show multi-node placement performance, Partition pruning, Rowsets, Segments, or
Compaction.

In Step 5, distinguish three quantities:

- `stored_rows` from `COUNT(*)` is the number of SQL-visible logical rows in
  each table.
- `represented_event_rows` is one per detail row but comes from
  `SUM(event_count)` for the summary.
- `represented_revenue` comes from the compatible revenue measure in each
  grain.

Run the optional stop and restart cells only when you want to release and then
restore sandbox resources. Docker named volumes preserve the baseline and Lab
4 tables. `events_modelled` must remain available for Modules 5 and 6.

## Module summary

A Doris schema begins with row meaning and repeated-Key meaning. Duplicate Key
retains accepted history, Unique Key exposes current state, and Aggregate Key
combines declared measures at a reporting grain. Identifiers, time, money,
categories, missing values, and nested structures each need a contract based on
valid values and required operations.

Partition, Bucket, and sort key make three separate layout decisions. A
Partition maps a row to a value and lifecycle range; a Hash Bucket maps it to a
Tablet inside that Partition; the sort key defines stored column order and also
serves the Table Model's Key semantics. Auto Partitioning creates required
ranges from incoming values but does not make the remaining choices.

A summary is useful only for questions its grain and measures preserve. Reconcile
detail and summary with represented counts and compatible totals, not by
assuming that their `COUNT(*)` values should match. Module 5 now uses the
complete `events_modelled` table to build analytical results whose grain remains
explicit at every stage.

## Official references

- Table design workflow: [Table Design Guide](https://doris.apache.org/docs/4.x/table-design/overview/) and [Table Model Best Practices](https://doris.apache.org/docs/4.x/table-design/data-model/tips/).
- Repeated-Key semantics: [Table Model Overview](https://doris.apache.org/docs/4.x/table-design/data-model/intro/), [Duplicate Key](https://doris.apache.org/docs/4.x/table-design/data-model/duplicate/), [Unique Key](https://doris.apache.org/docs/4.x/table-design/data-model/unique/), [Merge-on-Write](https://doris.apache.org/docs/4.x/table-design/data-model/merge-on-write/), and [Aggregate Key](https://doris.apache.org/docs/4.x/table-design/data-model/aggregate/).
- Doris 4.1.3 implementation terminology: [`KeysType.java`](https://github.com/apache/doris/blob/4.1.3/fe/fe-core/src/main/java/org/apache/doris/catalog/KeysType.java) maps the model types to `DUPLICATE KEY`, `UNIQUE KEY`, and `AGGREGATE KEY`; [`AggregateType.java`](https://github.com/apache/doris/blob/4.1.3/fe/fe-core/src/main/java/org/apache/doris/catalog/AggregateType.java) defines supported stored aggregation types such as `SUM`, `MIN`, `MAX`, `BITMAP_UNION`, and `HLL_UNION`.
- Column contracts: [Data Types](https://doris.apache.org/docs/4.x/table-design/data-type/), [DECIMAL](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/numeric/DECIMAL/), [DATETIME](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/date-time/DATETIME/), [VARCHAR](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/string-type/VARCHAR/), and [CAST and TRY_CAST](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/conversion/cast-expr/).
- Physical design: [CREATE TABLE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/table/CREATE-TABLE/), [Auto Partitioning](https://doris.apache.org/docs/4.x/table-design/data-partitioning/auto-partitioning/), and [Data Bucketing](https://doris.apache.org/docs/4.x/table-design/data-partitioning/data-bucketing/).
- Complex types: [ARRAY](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/ARRAY/), [MAP](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/MAP/), [STRUCT](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/STRUCT/), [JSON](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/JSON/), and [VARIANT](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/VARIANT/).
