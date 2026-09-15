# Module 5: Analyzing Data in Apache Doris

| Course information | Value |
| --- | --- |
| Course | Real-time Analytics with Apache Doris — Level 2 |
| Product baseline | Apache Doris 4.x |
| Lab version | Apache Doris 4.1.3 |
| Estimated time | Approximately 80 minutes, including the guided lab |

## Module goal

This module explains how to turn event detail into an analytical result whose
meaning you can defend. You will begin with a business question, define the
result grain and metric populations, and then choose functions by the shape of
work they perform. You will also divide a complex analysis into stages so that
filtering, aggregation, comparison, and presentation remain distinguishable.

Module 4 created `doris_course.events_modelled` from the persistent `events`
baseline. Each row in that table represents an event. Its typed time,
identifier, category, and revenue columns support the operational scenario in
this module: compare daily activity and purchasing behavior across regions,
then add trends and rankings without losing the daily-region grain.

## Learning objectives

After completing this module, you will be able to:

1. Define the population, grain, measures, and ordering of an analytical
   result, and distinguish result calculation from display or export.
2. Choose Scalar, Aggregate, Combinator, Analytic (Window), Table, Table-Valued,
   or Artificial Intelligence (AI) Functions from their inputs, outputs, row-count
   behavior, and dependencies.
3. Derive reporting periods and labels with date and string functions while
   preserving event-detail rows.
4. Choose counts, totals, averages, extrema, and statistical aggregates that
   answer a stated business question.
5. Use conditional expressions inside aggregates so that several measures at
   one result grain can read different event populations.
6. Distinguish `WHERE` filtering of input rows from `HAVING` filtering of
   aggregated groups.
7. Use `ANY_VALUE` only when any representative value satisfies the business
   meaning of the group.
8. Distinguish a Table Function that expands each input row from a Table-Valued
   Function (TVF) that supplies a relation to `FROM`.
9. Use a Common Table Expression (CTE) to name an analytical stage and make its
   grain explicit.
10. Distinguish aggregation, which can collapse rows, from window calculation,
    which retains its input result rows.
11. Choose window partitions, ordering, frames, and ranking semantics for
    previous-value, cumulative, and ranking questions.
12. Distinguish built-in functions, array Lambda expressions, Alias Functions,
    and the User-Defined Function (UDF) family.

## Scenario-led content outline

An operations team wants a report with one row per date and region. Each row
must show event volume, active users, purchasing users, purchase revenue, the
previous observed day's revenue for that region, cumulative regional revenue,
and the region's revenue rank for that date. The same event data may later need
tag expansion, generated rows, or company-specific reusable logic.

Each section turns one part of that requirement into an analytical decision:

| Section | Requirement scenario | Decision developed in this module | Lab 5 evidence |
| --- | --- | --- | --- |
| **5.1 Define the analytical answer** | A request for a regional performance report leaves its population, grain, measures, date coverage, and ordering unstated. | Write a result contract before choosing functions; keep computation separate from display and export. | Inspect how every executed query states a time range, grouping grain, measures, and final ordering. |
| **5.2 Choose a function category** | One event dataset must support row transformations, grouped metrics, trends, expansion, generated relations, and model calls. | Classify functions by input, output, row-count behavior, and external dependency; recognize categories that overlap. | Match seven function categories interactively. |
| **5.3 Derive dimensions** | Event timestamps and codes must become reporting dates, hours, patterns, and labels without discarding the original values. | Use Scalar Functions for per-row derivation; distinguish grouping values, presentation labels, and predicates. | Compare source and derived values in eight event rows. |
| **5.4 Define grouped measures** | Stakeholders need event counts, user counts, revenue, thresholds, and representative attributes at a declared grain. | Define each metric population, use conditional aggregation, place `WHERE` and `HAVING` correctly, and constrain `ANY_VALUE`. | Produce daily-region metrics, filter product groups, and compare rejected and valid grouped projections. |
| **5.5 Obtain new rows** | Tags inside a row must be expanded, while a different task needs a generated or external relation. | Choose a Table Function for row-dependent expansion and a TVF for a relation source; reassess grain after expansion. | Run `EXPLODE` with `LATERAL VIEW` and query the `NUMBERS` TVF without external storage. |
| **5.6 Name analytical stages** | A daily-region report combines input filtering, derived dates, grouped metrics, windows, and final presentation. | Give each stage one responsibility with a CTE; do not assume that a CTE is automatically materialized or faster. | Build a three-stage query that returns 24 daily-region rows. |
| **5.7 Compare retained rows** | Each daily-region row needs its previous value, cumulative value, and rank among regions on that date. | Choose window `PARTITION BY`, `ORDER BY`, frame, and tie behavior from the question. | Use `LAG`, cumulative `SUM`, `ROW_NUMBER`, and `RANK` while retaining the aggregated rows. |
| **5.8 Extend missing reusable behavior** | Built-in SQL cannot express a proprietary row calculation, aggregate state, window state, or parser. | Choose UDF, User-Defined Aggregate Function (UDAF), User-Defined Window Function (UDWF), or User-Defined Table Function (UDTF) only when its row behavior and deployment cost fit the requirement. | Compare the four extension families and inspect a non-executing Java UDF registration template. |

The explanations in this module focus on choosing the correct operation and on
interpreting its result. Lab 5 supplies the concrete Doris 4.1.3 behavior. It
does not contact an external AI provider, read Amazon
S3 again, deploy user code, or use elapsed time to compare query forms.

---

## 5.1 Define the Analytical Answer Before Choosing Functions

“Show regional performance” is not yet a query contract. It leaves several
questions unresolved:

- Which events belong to the report?
- What does one output row represent?
- Which events contribute to each metric?
- Should dates or regions with no qualifying events appear?
- What sequence defines “previous,” “cumulative,” and “rank”?
- Is the result for interactive inspection or for a downstream file workflow?

Resolve these choices before selecting function names. For the scenario in
this module, one possible contract is:

| Decision | Requirement |
| --- | --- |
| Input population | Events from March 1 inclusive to March 4 exclusive |
| Result grain | One row per `event_date` and `region` |
| Activity measures | All events and distinct users in each daily-region group |
| Purchase measures | Distinct purchasing users and purchase revenue in the same group |
| Time comparison | Previous observed daily revenue and cumulative revenue within each region |
| Cross-region comparison | Revenue rank among regions on the same date |
| Final ordering | Date, rank, then region for a stable display |

This contract prevents superficially plausible mistakes. Grouping only by date
would remove the region grain. Filtering to purchases before calculating
`event_count` would turn that column into a purchase-event count. Ranking all
24 rows together would answer a different question from ranking eight regions
independently on each date.

### Trace the report grain through the query

The query can be understood as a sequence of row shapes:

```text
event-detail rows
        |
        | filter dates and derive event_date
        v
selected event-detail rows
        |
        | group by event_date and region
        v
daily-region rows
        |
        | add previous, cumulative, and rank values
        v
the same daily-region rows with more columns
```

Filtering can remove rows. Grouping usually reduces many detail rows to fewer
grouped rows. Window calculation retains the rows it receives and adds a value
to each one. Final ordering changes their presentation sequence, not their
grain.

### Separate result meaning from result delivery

A MySQL-compatible client and a Jupyter Notebook can display the same SQL
result in different forms. In the MySQL command-line client, `\G` requests a
vertical display; it is a client command terminator, not part of a query sent
through the Notebook helper. Column aliases can improve readability, but they
do not change which rows or values the query computes.

When another system needs files, Doris supports `SELECT INTO OUTFILE` with
formats such as comma-separated values (CSV), Parquet, and Optimized Row
Columnar (ORC). Export destination, format, permissions,
and credentials form a delivery contract. They do not repair an incorrectly
defined metric or grain. Lab 5 displays results and performs no export. See
[SELECT INTO OUTFILE](https://doris.apache.org/docs/4.x/data-operate/export/outfile/).

## 5.2 Choose a Function Category from the Required Work

The Doris SQL function catalog is easier to navigate when you first ask what
the operation consumes, what it returns, and what happens to the number of
rows. The categories are not merely lists of names.

| Function category | Main input and output relationship | Suitable scenario | Representative form |
| --- | --- | --- | --- |
| Scalar Function | Arguments for one input row produce one value | Derive a date or normalize a label | `TO_DATE(event_time)` |
| Aggregate Function | Values from multiple rows produce one value for a group | Calculate regional revenue | `SUM(revenue)` |
| Combinator | An aggregate is adapted with state, merge, or array-position behavior | Merge aggregate states or aggregate corresponding array elements | `SUM_FOREACH(metric_array)` |
| Analytic (Window) Function | Related result rows contribute to one value for every retained row | Compare a daily row with its predecessor | `LAG(revenue) OVER (...)` |
| Table Function | A value in each current input row produces zero to many rows | Expand the tags attached to an event | `EXPLODE(tags)` with `LATERAL VIEW` |
| Table-Valued Function (TVF) | The function itself provides a relation to `FROM` | Generate numbers or query files as rows and columns | `NUMBERS(...)` or `S3(...)` |
| AI Function | Doris invokes a model through an AI Resource | Classify, extract, translate, summarize, or analyze text | `AI_SENTIMENT(resource, text)` |

### Follow the row shape through the analysis

A useful first approximation connects the three core function shapes:

```text
one input row  -- Scalar Function --> one derived value for that row
many rows      -- Aggregate Function --> one value for each group
one input row  -- Table Function --> zero to many expanded rows
```

In shorthand, these are **one-to-one**, **many-to-one**, and **one-to-many**.
They describe what the function contributes to the query, not a guarantee that
the complete SQL statement preserves that exact row count. A `WHERE` clause can
remove rows, a Join can multiply them, and `GROUP BY` defines how many aggregate
groups remain.

The later sections follow that row-shape progression. Section 5.3 derives
values while retaining event rows. Section 5.4 deliberately collapses many
events into each daily-region row. Section 5.5 expands one row into several
element rows. Section 5.6 then gives those transformations explicit stages,
and Section 5.7 uses a window of related rows to calculate one value for every
retained result row:

```text
event rows
   |  Scalar: derive event_date
   v
enriched event rows
   |  Aggregate: group by event_date, region
   v
daily-region rows
   |  Window: compare related daily-region rows
   v
the same daily-region rows, now with previous values, totals, or ranks
```

### Some categories describe different dimensions

Row shape and capability source can overlap. `AI_SENTIMENT` behaves like a
per-row scalar calculation, but “AI Function” also tells you that it requires
a configured AI Resource and an external model call. `AI_AGG` instead operates
across grouped text. Seeing an `AI_*` name is therefore not enough to infer its
row-count behavior.

Likewise, `SUM(revenue)` is an Aggregate Function when it summarizes a group.
When an aggregate is written with `OVER`, it follows window semantics and
produces a value for every retained input result row. SQL context determines
how the operation participates in the result.

Table Functions and TVFs both produce rows, but their starting points differ.
A Table Function expands something in a current row; a TVF acts as a table
source. Section 5.5 develops that distinction with concrete row shapes.

### Treat AI calls as an external dependency

An AI Function is appropriate only after the application has defined the model
provider, AI Resource, credentials, network access, latency expectations,
failure policy, data-governance rules, and acceptable cost. A sentiment label
returned by an external model is not equivalent to a deterministic local
string transformation.

The lab classifies `AI_SENTIMENT` but does not execute it. This keeps the lab
self-contained and avoids sending course data to an external provider. Consult
the [AI Functions overview](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/ai-functions/overview/)
and the chosen function's current contract before adopting it.

## 5.3 Use Scalar Functions to Derive Explainable Dimensions

The event table already stores `event_time`, `region`, and `event_type` in
typed columns. A report may still need an event date, hour boundary, hour
number, or display label. Scalar Functions derive those values independently
for each selected input row.

### Distinguish time meaning from time presentation

Different time expressions answer different questions:

| Need | Expression role | Example |
| --- | --- | --- |
| Calendar date for grouping | Convert the timestamp to a `DATE` value | `TO_DATE(event_time)` |
| Start of the event's hour | Normalize to an hourly temporal boundary | `DATE_TRUNC(event_time, 'hour')` |
| Hour component for a distribution | Extract one component | `EXTRACT(HOUR FROM event_time)` |
| Human-readable label | Format for presentation | `DATE_FORMAT(event_time, ...)` |

A formatted string may look like a date, but its contract is still a string.
Prefer a temporal value when later operations must compare dates, calculate
intervals, or preserve calendar semantics. Format the value when the consumer
actually needs a label.

The query's time zone and boundary convention are part of the metric contract.
“Daily” is ambiguous if the source timestamp and the business reporting zone
differ. A function cannot resolve that business decision by itself.

### Separate normalization, labeling, and matching

String operations also serve distinct purposes:

- `LOWER`, `UPPER`, and `TRIM` can normalize values for a stated comparison or
  presentation rule.
- `REPLACE` can construct a display label when the transformation is truly
  mechanical.
- `LIKE` and `REGEXP` are predicates that decide which rows qualify; they do
  not standardize the stored value.

Do not casually normalize an identifier that is case-sensitive by contract.
If several spellings represent the same category, decide whether ingestion
should establish one canonical value. Repeating cleanup logic across every
analytical query can signal that the data boundary is too permissive.

Scalar expressions do not group rows by themselves. If eight event rows enter
a projection containing `TO_DATE(event_time)` and `UPPER(region)`, eight rows
can still leave that projection. A later `GROUP BY` changes the grain.

## 5.4 Use Aggregate Functions to Answer Defined Metric Questions

An Aggregate Function combines observations. The correct function depends on
both the mathematical operation and the population being observed.

### Define the population for every measure

Consider four measures in one daily-region row:

| Measure | Contributing population | Suitable expression pattern |
| --- | --- | --- |
| Event count | All selected events in the group | `COUNT(*)` |
| Active users | Distinct non-`NULL` users among all selected events | `COUNT(DISTINCT user_id)` |
| Purchasing users | Distinct users among purchase events only | `COUNT(DISTINCT CASE WHEN event_type = 'purchase' THEN user_id END)` |
| Purchase revenue | Revenue from purchase events only | `SUM(CASE WHEN event_type = 'purchase' THEN revenue ELSE 0 END)` |

The conditional expressions allow measures with different contributing
populations to share the same daily-region result grain. Filtering the entire
query to purchases would also remove non-purchase events from `event_count` and
`active_users`, changing their meaning.

Distinct counts are not generally additive. A user active in two regions or
on two dates contributes to each relevant group but should appear once in a
global distinct-user count. Summing daily-region distinct counts does not
produce a globally distinct population.

### Choose the statistic that matches the question

`COUNT`, `SUM`, `AVG`, `MIN`, and `MAX` answer different questions. An average
needs a defined observation and denominator. “Average revenue” might mean
average per purchase event, per purchasing user, or per day; these values are
not interchangeable.

Variance describes spread in one numeric measure. Covariance describes how
two measures vary together in their units. Correlation normalizes that
relationship to a dimensionless scale. None establishes causation. Before
using a statistical aggregate, define the observation grain, sample or
population interpretation, missing-value policy, and whether extreme values
should remain in scope.

### Put filters at the stage they are meant to affect

`WHERE` and `HAVING` operate at different row shapes:

```text
FROM events_modelled
        |
        | WHERE: remove input event rows
        v
GROUP BY product_id
        |
        | calculate one row per product
        v
HAVING: remove product groups by their aggregate values
```

To find products whose purchase revenue reaches a threshold on one day,
`WHERE` should choose that day's purchase events, while `HAVING SUM(revenue)`
should choose qualifying product groups. A predicate such as
`WHERE revenue >= 120000` asks whether each individual event reaches the
threshold. It does not test the product total.

### Use `ANY_VALUE` only under a real constraint

A grouped query cannot project an ordinary column whose value varies within
the group unless that column also defines the group. Doris rejects an ambiguous
projection such as choosing `event_time` while grouping only by `region`.

`ANY_VALUE(expression)` explicitly requests any non-`NULL` representative value
when one exists; it returns `NULL` when all candidates are `NULL`. This is
meaningful when the exact selected value cannot change the business meaning.
For example, after a predicate restricts every input row to one calendar date,
any event date within each region is that same date. It is not meaningful when
the group spans several dates and the result is supposed to identify one of
them. In that case, add the date to the grain or state a rule such as `MIN` or
`MAX` that has an interpretable meaning.

Never depend on which eligible row `ANY_VALUE` happens to select. Its purpose
is to express indifference, not to provide a shortcut to a predictable first
or latest value. See [ANY_VALUE](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/aggregate-functions/any-value/).

### Introduce a Combinator only for its specialized behavior

A Combinator modifies how an Aggregate Function is represented or applied.
State and merge forms support workflows that store or combine intermediate
aggregate states. A `FOREACH` form applies an aggregate independently to
corresponding positions of array values across rows.

These are useful when the data product genuinely contains mergeable aggregate
states or positionally meaningful arrays. They are unnecessary for an ordinary
revenue total. Prefer the direct and readable `SUM(revenue)` until the
specialized requirement exists. See the current [Combinators catalog](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/combinators/)
for supported combinations and type constraints.

## 5.5 Use a Table Function to Expand Values into Rows

An event may store several tags, map entries, or delimited values in one row.
When the analysis needs one of those elements per result row, use a Table
Function to expand the value while retaining its relationship to the source
row.

### Expand a value belonging to each input row

Suppose an event has an array of tags:

| `event_id` | `tags` |
| ---: | --- |
| 41 | `['mobile', 'promotion']` |
| 42 | `['desktop']` |

Using `EXPLODE(tags)` with `LATERAL VIEW` associates every generated tag with
its source event:

| `event_id` | `tag` |
| ---: | --- |
| 41 | `mobile` |
| 41 | `promotion` |
| 42 | `desktop` |

The result grain is now one row per event-tag occurrence, not one row per
event. Summing event revenue after this expansion would count event 41 twice
unless the metric intentionally measures tag attribution or the query first
returns to an appropriate grain. Empty and `NULL` collections also require an
explicit retention decision; consult the chosen Table Function's contract.

Table Functions suit row-dependent parsing or expansion. Examples include
array expansion and splitting a delimited value. Doris commonly uses them with
`LATERAL VIEW`. See [Table Functions](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-functions/).

> **Table Function and TVF are different categories.** A Table Function such
> as `EXPLODE(tags)` runs against each current input row and produces zero to
> many rows associated with that row. A Table-Valued Function (TVF) such as
> `NUMBERS(...)` or `S3(...)` is itself a relation source in `FROM`; it does
> not need a row from `events_modelled` to generate its relation. Module 3
> already used the S3 TVF to expose external files as a temporary relation.
> Lab 5 uses `NUMBERS("number" = "4")` only as a small, self-contained contrast
> and does not revisit S3 access or persistence. See
> [Table-Valued Functions](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/)
> and [NUMBERS](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/numbers/).

## 5.6 Use CTEs to Express the Stages of a Complex Analysis

A Common Table Expression gives a temporary result set a name within one SQL
statement. It can make the grain and responsibility of each stage visible.
It does not create a permanent table.

For the daily-region scenario, divide the work as follows:

| Stage | Responsibility | Result grain |
| --- | --- | --- |
| `filtered` | Choose the three-day input population and derive `event_date` | One row per selected event |
| `daily_region` | Group by date and region; calculate activity and purchase measures | One row per date and region |
| `scored` | Add previous revenue, cumulative revenue, and daily rank | One row per date and region |
| Final `SELECT` | Choose visible columns and presentation order | One row per date and region |

The structural outline is easier to review than one query layer that attempts
every operation at once:

```sql
WITH filtered AS (
    -- select the input population and derive event_date
),
daily_region AS (
    -- establish the daily-region grain and calculate measures
),
scored AS (
    -- retain those rows and add window calculations
)
SELECT ...
FROM scored
ORDER BY ...;
```

This organization makes errors easier to locate. If purchase revenue is wrong,
inspect the input predicate and conditional aggregate. If the row count is not
three dates multiplied by eight regions, inspect the `daily_region` grouping.
If “previous” crosses from one region to another, inspect the window partition.

A CTE is a semantic and readability boundary. Its presence does not guarantee
that Doris materializes the result, executes each named block separately, or
makes the query faster. Use `EXPLAIN` and a Query Profile when physical
execution matters; do not infer a performance property from the syntax alone.
See [Common Table Expressions](https://doris.apache.org/docs/4.x/query-data/cte/).

### Preserve missing-period meaning

Grouping event detail produces rows only for groups represented by qualifying
input. If a region has no selected event on a date, an event-only aggregation
does not automatically invent a zero-valued row for that combination.

This matters to later windows. `LAG` reads the previous result row in its
ordered window, which may not be the previous calendar day. A report that must
show every calendar date needs a calendar relation and an outer Join or another
explicit gap-filling design. Zero activity and an absent result row are
different states.

## 5.7 Use Window Functions to Compare Rows Without Losing Their Grain

After aggregation, each row already represents a date and region. Window
functions compare those rows while preserving them. Three clauses establish
the comparison contract:

| Window component | Question it answers |
| --- | --- |
| `PARTITION BY` | Which rows form an independent comparison population? |
| Window `ORDER BY` | In what sequence are previous, next, and cumulative positions defined? |
| Window frame | Which positions around the current row contribute to a frame-sensitive calculation? |

### Compare each region with its previous observed row

For regional revenue trends, the independent sequence is each region:

```sql
LAG(purchase_revenue, 1, 0) OVER (
    PARTITION BY region
    ORDER BY event_date
)
```

The offset `1` means one preceding result row, and `0` is the default when no
such row exists. The first displayed date therefore receives zero in the lab.
That value does not claim that revenue before the selected range was zero. It
only makes the boundary behavior explicit.

If dates are missing, `LAG` still reads the preceding row. Describe it as
“previous observed date” unless the query has guaranteed a consecutive
calendar relation.

### State the cumulative frame

A running total for each region can use:

```sql
SUM(purchase_revenue) OVER (
    PARTITION BY region
    ORDER BY event_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

The `ROWS` frame starts with the first selected row in that region and ends at
the current row. Filtering earlier dates out of the input also removes them
from the cumulative total. “Cumulative” must always name its starting scope.

A frame such as `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` contains at most
three row positions. It represents three calendar days only when the input has
one row for each consecutive date.

### Choose the intended tie behavior

`ROW_NUMBER` assigns distinct sequential positions. Provide a tie-breaker when
the position must be deterministic. `RANK` gives equal ordering values the
same rank and leaves a gap after a tie:

| Region | Revenue | `ROW_NUMBER` with region as tie-breaker | `RANK` by revenue only |
| --- | ---: | ---: | ---: |
| East | 100 | 1 | 1 |
| West | 100 | 2 | 1 |
| North | 80 | 3 | 3 |

Choose `ROW_NUMBER` when the output needs one deterministic position for each
row. Choose `RANK` when equal metric values should share a business rank. For
the module scenario, `PARTITION BY event_date` restarts the competition each
day, while `ORDER BY purchase_revenue DESC` gives the largest value rank 1.

Window ordering and final result ordering serve different purposes. A window
may define a revenue rank while the final `ORDER BY` displays date, rank, and
region. The display order does not recalculate the window values. See
[Analytic (Window) Functions](https://doris.apache.org/docs/4.x/query-data/window-function/).

## 5.8 Choose the Right Extension for Missing Reusable Logic

Start with Doris built-in functions and clear SQL expressions. They already
cover the date transformations, grouping, conditional metrics, expansion, and
windows used in this module. Repeated expression syntax alone does not justify
deploying user code.

### Compare reuse and extension choices

| Requirement | Suitable starting point |
| --- | --- |
| Doris already provides the operation | Built-in function |
| One query needs a readable combination of existing expressions | Ordinary SQL expression or CTE |
| A higher-order array operation needs a short element expression | Lambda expression passed to a built-in function |
| Supported expressions need a reusable SQL signature | Alias Function |
| Required reusable behavior cannot be expressed with supported SQL | An appropriate user-defined function family |

In `ARRAY_MAP(x -> x * 2, [1, 2, 3, 4])`, the Lambda expression defines what
happens to each array element. `ARRAY_FILTER` uses a Lambda predicate to decide
which elements remain in the returned array. Neither expression registers a
new function for other queries, and filtering array elements does not filter
the surrounding table rows.

An Alias Function gives a reusable name to an expression composed from
supported functions. It remains expression reuse. It does not provide a place
to hide an external proprietary algorithm. See [Alias Function](https://doris.apache.org/docs/4.x/query-data/udf/alias-function/).

### Match the user-defined family to its row behavior

When the missing logic requires an implementation artifact, choose the family
that matches its input and output contract:

| Extension | Input and output behavior | Suitable example |
| --- | --- | --- |
| User-Defined Function (UDF) | One input row produces one value | Apply a proprietary customer-risk score |
| User-Defined Aggregate Function (UDAF) | Rows in a group maintain and merge state to produce one result | Calculate a company-specific grouped index |
| User-Defined Window Function (UDWF) | Window state produces a value for each retained row | Apply a specialized rolling state and reset rule |
| User-Defined Table Function (UDTF) | One input row produces zero to many rows | Parse and expand a proprietary encoded payload |

A Java scalar UDF illustrates the deployment boundary:

```text
implement the Java method and its type contract
        |
        v
package the implementation in a Java Archive (JAR)
        |
        v
make the artifact available to the required Doris nodes
        |
        v
register the SQL signature and implementation with CREATE FUNCTION
        |
        v
invoke the registered function in a query
```

`CREATE FUNCTION` registers metadata that points to the implementation; the
statement does not contain the algorithm. The contract includes argument and
return types, null behavior, implementation location, privileges, and function
properties. A function declared `immutable` must return the same result for the
same inputs. Logic that reads changing external state does not satisfy that
promise.

The Backend (BE) executes the registered implementation as part of query
execution. Deployment therefore introduces artifact availability, security,
resource use, failure handling, compatibility, and upgrade responsibilities.
Choose an extension because the behavior is both missing and reusable, not
because the built-in catalog is unfamiliar.

Doris 4.1.3 documentation marks Python UDF, UDAF, and UDTF support as
experimental. The lab uses the documented Java lifecycle as a non-executing
template and does not build a JAR or register a function. Consult
[Java UDF, UDAF, UDWF, and UDTF](https://doris.apache.org/docs/4.x/query-data/udf/java-user-defined-function/),
[Python UDF family](https://doris.apache.org/docs/4.x/query-data/udf/python-user-defined-function/),
and [CREATE FUNCTION](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/function/CREATE-FUNCTION/)
for the current implementation contracts.

---

## Lab 5: Explore Doris Functions and Build Analytical Queries

Open [Lab 5 — Explore Doris Functions and Build Analytical Queries](lab5_analyze_data.ipynb)
after completing Lab 4. It uses the persistent
`doris_course.events_modelled` table containing 10,158,080 event rows. It reads
that model without replacing it so Module 6 can enrich the same events.

The lab turns the choices in this module into observable results:

| Lab step | What you do | What the result establishes |
| --- | --- | --- |
| 1 | Match seven function categories | Input, output, row behavior, and dependencies distinguish the categories |
| 2 | Run `EXPLODE` and `NUMBERS` | A Table Function expands a current row; a TVF supplies a relation |
| 3 | Derive dates, hours, and labels | Scalar Functions add values while retaining the event-detail rows |
| 4 | Calculate daily-region measures | Aggregation changes the grain from events to groups |
| 5 | Apply `WHERE` and `HAVING` | Input-row and group filters answer different questions |
| 6 | Compare an invalid projection with `ANY_VALUE` | A representative value is valid only under a supporting business constraint |
| 7 | Display a named daily CTE | A CTE exposes an intermediate result and its grain |
| 8 | Add `LAG`, cumulative `SUM`, and `ROW_NUMBER` | Window calculations retain the eight daily rows |
| 9 | Run the complete daily-region analysis | Three dates and eight regions produce 24 rows with activity, trend, and rank measures |
| 10 | Apply array Lambda expressions | Element transformation and filtering return new array values |
| 11 | Assemble a query from bounded choices | Grain, input filter, and metric selections map to visible SQL |
| 12 | Compare UDF, UDAF, UDWF, and UDTF | Extension type follows the missing reusable logic and its row behavior |

In Step 9, follow `region_02` across the three dates. Its March 2 row reads the
March 1 revenue through `LAG`, adds March 2 revenue to its regional cumulative
total, and receives rank 1 within the March 2 partition. These values are
direct query results. The lab does not claim that its CTEs were materialized or
that one query form is faster.

When you change the guided builder, state two things before reading its values:
what one row represents and which events contribute to the chosen metric. A
different date grain, event filter, or measure produces a different business
answer even when every query runs successfully.

## Module summary

An analytical result begins with a population, grain, measures, comparison
rules, and output requirement. Scalar Functions derive values for rows;
Aggregate Functions summarize groups; Combinators adapt specialized aggregate
behavior; Table Functions expand current rows; TVFs supply relations; and
Analytic Functions compare retained result rows. AI Functions also introduce
an external model dependency that must be part of the design.

CTEs make analytical stages and their grains visible. Window partitions,
ordering, frames, and tie rules determine what previous, cumulative, and rank
values mean. Built-in functions should remain the first choice; UDF, UDAF,
UDWF, and UDTF add deployment cost and fit different row behaviors.

In Module 6, you will enrich the event rows with product attributes. Continue
to state the result grain before interpreting a metric, because duplicate or
unmatched Join keys can change which rows reach the next analytical stage.

## Official references

- Function categories: [SQL Functions](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/), [Scalar Functions](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/scalar-functions/), [Aggregate Functions](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/aggregate-functions/), [Combinators](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/combinators/), and [AI Functions](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/ai-functions/overview/).
- Row-producing functions: [Table Functions](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-functions/), [Table-Valued Functions](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/), and [NUMBERS](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/numbers/).
- Analytical query structure: [SELECT](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-query/SELECT/), [Common Table Expressions](https://doris.apache.org/docs/4.x/query-data/cte/), and [Analytic (Window) Functions](https://doris.apache.org/docs/4.x/query-data/window-function/).
- Grouping and higher-order behavior: [ANY_VALUE](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/aggregate-functions/any-value/), [ARRAY_MAP](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/scalar-functions/array-functions/array-map/), and [ARRAY_FILTER](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/scalar-functions/array-functions/array-filter/).
- Reusable extensions: [Alias Function](https://doris.apache.org/docs/4.x/query-data/udf/alias-function/), [Java UDF, UDAF, UDWF, and UDTF](https://doris.apache.org/docs/4.x/query-data/udf/java-user-defined-function/), [Python UDF family](https://doris.apache.org/docs/4.x/query-data/udf/python-user-defined-function/), and [CREATE FUNCTION](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/function/CREATE-FUNCTION/).
- Result delivery: [SELECT INTO OUTFILE](https://doris.apache.org/docs/4.x/data-operate/export/outfile/).
