# Module 5: Analyzing Data in Apache Doris

| Course information | Value |
| --- | --- |
| Course | Real-time Analytics with Apache Doris — Level 2 |
| Product baseline | Apache Doris 4.x |
| Lab version | Apache Doris 4.1.3 |
| Estimated time | Approximately 70 minutes, including the guided lab |

## Module goal

This module explains how to turn event detail into an analytical answer whose
meaning you can explain. You will choose a reporting grain, define which
events contribute to each measure, and combine SQL functions into stages for
aggregation, comparison, and ranking.

Module 4 created `doris_course.events_modelled` from the persistent `events`
baseline. Its typed columns let you work directly with event times, identifiers,
categories, and revenue. Here, you query that complete event model without
changing its schema or loading another copy of the dataset.

## Learning objectives

After completing this module, you will be able to:

1. Define the population, grain, measures, and ordering of an analytical result,
   and distinguish displaying that result from exporting it.
2. Choose scalar, aggregate, table-valued, and window functions by their role
   in a query.
3. Derive reporting periods and labels with date and string functions, and
   distinguish formatting from grouping and pattern matching.
4. Choose counts, totals, averages, extrema, and statistical aggregates that
   match the business question; use conditional aggregation to keep different
   measures within one result grain.
5. Place row and group filters correctly, and recognize when `ANY_VALUE`
   provides a meaningful representative value.
6. Use a Common Table Expression (CTE) to name an analytical stage and make
   its result grain explicit.
7. Choose window partitions, ordering, and frames for ranking, cumulative
   totals, and comparisons with previous rows.
8. Distinguish built-in functions, array lambda expressions, Alias Functions,
   and externally implemented user-defined functions (UDFs).

## Module structure

| Section | Format | Time | Outcome |
| --- | --- | ---: | --- |
| 5.1 Define the Answer Before Choosing Functions | Requirements walkthrough | 5 min | Connect the result contract to function categories and output choices |
| 5.2 Derive Dimensions That Preserve Meaning | Expression walkthrough | 6 min | Select time grains, labels, and matching rules |
| 5.3 Choose Measures for the Right Population | Metric comparison | 8 min | Explain denominators, conditional measures, and statistical choices |
| 5.4 Filter and Describe Groups Correctly | Grouping walkthrough | 5 min | Separate row filtering, group filtering, and representative values |
| 5.5 Name Each Analytical Stage | CTE walkthrough | 5 min | Expose intermediate grain and distinguish missing dates from zero values |
| 5.6 Compare Rows Without Losing Their Grain | Window walkthrough | 10 min | Choose comparison boundaries, frames, and ranking semantics |
| 5.7 Choose How to Express Reusable Logic | Function comparison | 6 min | Recognize the boundary between expressions and deployed extensions |
| Lab 5 | Hands-on | 25 min | Explore functions and build an analytical query over `events_modelled` |

---

## 5.1 Define the Answer Before Choosing Functions

“Show our best days” leaves several decisions unresolved. Best by revenue,
number of purchases, or number of distinct purchasers? Over which dates?
Should days without purchases appear? Should the output follow calendar order
or start with the largest value?

Turn the question into a **result contract**:

| Decision | Example requirement |
| --- | --- |
| Input population | Purchase events from March 1 inclusive to March 9 exclusive |
| Result grain | One row per date with qualifying events |
| Measure | Sum of purchase revenue |
| Ordering | Revenue descending, then date ascending to resolve equal totals |
| Presentation | A small table in the Notebook |

Changing any of these choices can change the answer. A query can be valid SQL
while answering a different business question.

### Choose functions by the shape of the work

| Category | What it does | Example in this course |
| --- | --- | --- |
| Scalar function | Calculates a value from the arguments for a row | `TO_DATE(event_time)` derives that event's date |
| Aggregate function | Summarizes the rows in a group | `SUM(revenue)` produces one total per group |
| Table-valued function (TVF) | Exposes a relation with rows and columns | The S3 TVF from Module 3 makes file data queryable in `FROM` |
| Window function | Calculates across related result rows while retaining those rows | `ROW_NUMBER() OVER (...)` adds a position to each row |

The surrounding query matters. `SUM(revenue)` with `GROUP BY region` produces
regional totals; adding `OVER (...)` makes an aggregate operate as a window
calculation. Applying a scalar function alone does not collapse events into
groups. A TVF provides input to a query rather than returning a single value
for an event. The [S3 TVF reference](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/s3/)
describes the relation used in Module 3; Lab 5 uses the existing internal table.

### Choose a result surface after defining the calculation

A MySQL-compatible client and a Notebook can display the same query result.
In the MySQL command-line client, `\G` requests vertical display; it is a client
command terminator, not a function to put inside the Notebook's SQL string.
Column aliases make a result readable without changing its grain.

For a downstream file workflow, Doris supports `SELECT INTO OUTFILE` with
formats including CSV, Parquet, and ORC. This executes an export and writes
files to a configured destination; it is a different operation from displaying
rows in a client. Choose CSV for a simple text interchange requirement or a
columnar format when the receiving analytical system expects it. Lab 5 displays
results and does not perform an export. See [SELECT INTO OUTFILE](https://doris.apache.org/docs/4.x/data-operate/export/outfile/).

For internal Doris tables, a query reads a committed snapshot established at
the start of the statement under `READ COMMITTED`. A later query can see newly
committed data. Consequently, two separate dashboard refreshes can differ even
with identical SQL. The course dataset remains stable while you work through
the lab. This builds on Module 3's transaction discussion; see
[Transactions](https://doris.apache.org/docs/4.x/data-operate/transaction/).

## 5.2 Derive Dimensions That Preserve Meaning

A **dimension** is a value used to label, group, or filter observations. The
table stores an event timestamp, but a report may need a day, week, month, or
hour of day. These represent different questions.

For an event at `2020-03-03 12:34:56`, compare these expressions:

| Expression | Result | Appropriate use |
| --- | --- | --- |
| `TO_DATE(event_time)` | `2020-03-03` | Group events by calendar date |
| `DATE_TRUNC(event_time, 'hour')` | `2020-03-03 12:00:00` | Group events into specific hourly periods |
| `DATE_TRUNC(event_time, 'week')` | `2020-03-02 00:00:00` | Group by the week beginning Monday |
| `EXTRACT(HOUR FROM event_time)` | `12` | Compare the same hour of day across dates |
| `DATE_FORMAT(event_time, '%Y-%m')` | Text `2020-03` | Produce a month label for display |

`EXTRACT(HOUR ...)` groups every selected day's noon events together when used
as a grouping expression. It does not identify a particular hour on a
particular date. Similarly, formatting with only `%m` loses the year. Prefer a
typed period boundary for chronological computation and derive a text label
when presenting the result. See [DATE_TRUNC](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/scalar-functions/date-time-functions/date-trunc/)
and [DATE_FORMAT](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/scalar-functions/date-time-functions/date-format/).

Keep the reporting calendar consistent with the source contract. Truncating a
timestamp does not itself convert it into another business time zone.

Lab 5 uses half-open time intervals: the start is included and the next boundary
is excluded. For example, `event_time >= '2020-03-03 00:00:00'` together with
`event_time < '2020-03-04 00:00:00'` selects a full day without guessing the last
representable fraction of a second.

Changing the builder's grain from Day to Week or Month changes grouping, not
the selected interval. Its March 1–8 input can therefore produce totals for
partial weeks or a partial month. A month label does not imply a full month's
coverage.

### Separate normalization, labels, and matching

Use `LOWER` or `UPPER` when case differences should be treated consistently,
`TRIM` to remove surrounding spaces, and `REPLACE` for a specific substring
replacement. For example:

```sql
SELECT LOWER(TRIM(' Purchase ')) AS normalized_event_type;
```

This returns `purchase`. Normalization is appropriate only if those differences
are irrelevant to the field's meaning. A display transformation such as the
lab's `region_01` to `REGION-01` label does not update the stored `region`.

Pattern matching instead decides which rows qualify. In `LIKE`, `%` matches
zero or more characters and `_` matches one character. Thus the lab's
`LIKE 'region_0%'` is broader than a literal `region_0` prefix: the underscore
is a wildcard. It works for the course region categories, but another source
could contain a value such as `regionX01` that also matches.

`REGEXP` expresses a regular expression. In the lab's
`'^(view|purchase)$'`, the parentheses group alternatives and the anchors require
the whole value to match. It selects `view` or `purchase`, rather than any string
containing those words. For a short set of exact categories, `IN ('view',
'purchase')` is also a clear way to express the requirement.

## 5.3 Choose Measures for the Right Population

A **measure** gives a numerical answer about the selected observations. Define
the observations before choosing the aggregate.

| Expression | Meaning within each selected group |
| --- | --- |
| `COUNT(*)` | Number of event rows |
| `COUNT(product_id)` | Number of rows with a non-`NULL` product identifier |
| `COUNT(DISTINCT user_id)` | Number of distinct non-`NULL` users represented |
| `SUM(revenue)` | Total revenue contributed by the selected rows |
| `AVG(revenue)` | Mean of the non-`NULL` revenue values |
| `MIN(revenue)` / `MAX(revenue)` | Lowest / highest non-`NULL` revenue value |

The current `events_modelled` schema requires `product_id`, so its two simple
counts agree. In a different model where product identifiers are optional,
`COUNT(product_id)` would answer a narrower question. See
[COUNT](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/aggregate-functions/count/)
and [AVG](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/aggregate-functions/avg/).

Likewise, the builder's **Active users** metric is `COUNT(DISTINCT user_id)`
after the selected event filter. With **Purchases only**, it counts distinct
purchasers. Its label must be interpreted together with that filter.

Distinct counts are not generally additive across periods. A user active on
Monday and Tuesday contributes to both daily counts but only once to the
week's distinct users. Compute the weekly distinct count from the appropriate
input rather than summing the daily answers.

### Keep the denominator aligned with the question

Consider three illustrative events: one view with zero revenue and two
purchases worth 20 and 40. Across all three events, average revenue is 20.
Across purchases, average purchase-event revenue is 30. Both calculations are
correct, but their denominators differ.

The course contract gives non-purchase events zero revenue. Therefore, including
them leaves a revenue sum unchanged but changes an average. It also changes
what the minimum represents. These meanings follow from the dataset contract,
not from the function name alone.

### Use conditional aggregation when measures need different inputs

Suppose one daily regional row must contain both all-event activity and
purchase revenue. Filtering the entire query to purchases would discard the
other events before `COUNT(*)` could include them. Keep all required events in
the input and place the purchase condition inside the appropriate aggregates.

Lab 5 demonstrates this with `COUNT(*)`, conditional `MIN` and `MAX`, and a
conditional `SUM`. The choice of the nonmatching value is deliberate:

| Desired measure | Treatment of non-purchase events |
| --- | --- |
| Purchase revenue total | Contribute zero to the sum |
| Lowest or highest purchase value | Contribute `NULL`, which the aggregate ignores |
| Average purchase value | Contribute `NULL` so other event types do not enter the denominator |

Using zero in a purchase minimum could introduce a value that no purchase had.
Using zero in a purchase average would change its denominator. If a group has
events but no purchases, a conditional sum with `ELSE 0` can be zero while a
conditional minimum remains `NULL`. This distinguishes no qualifying purchase
value from an actual zero-valued purchase.

### Choose statistical aggregates for a defined observation grain

Totals and averages do not describe every useful relationship. Statistical
aggregates answer additional questions:

| Function | Question it can answer |
| --- | --- |
| `VAR_POP(x)` | How dispersed are the values in the population being described? |
| `VAR_SAMP(x)` | What variance estimate does this sample give for a wider population? |
| `COVAR_POP(x, y)` / `COVAR_SAMP(x, y)` | Do paired values tend to increase or decrease together? |
| `CORR(x, y)` | How strong is their linear association on a normalized scale? |

The population forms divide by the number of valid observations, whereas the
sample forms use one fewer. Variance has squared units; covariance depends on
both input scales. Pearson correlation is unitless, with values near +1 or -1
indicating strong positive or negative linear association when defined. It
does not establish causation. See [VAR_POP](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/aggregate-functions/variance/),
[VAR_SAMP](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/aggregate-functions/var-samp/),
and [CORR](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/aggregate-functions/corr/).

For example, “Do days with more purchasers also have more revenue?” requires
one paired observation per day: that day's purchaser count and revenue. First
produce those daily rows, then aggregate the two measures with `CORR`. Computing
correlation between `user_id` and event revenue would instead treat an
identifier as a numerical measurement and would not answer that question.

This small independent example makes the population/sample distinction visible:

```sql
WITH pairs AS (
    SELECT 1.0 AS x, 2.0 AS y
    UNION ALL SELECT 2.0, 3.0
    UNION ALL SELECT 3.0, 4.0
)
SELECT VAR_POP(x), VAR_SAMP(x),
       COVAR_POP(x, y), COVAR_SAMP(x, y), CORR(x, y)
FROM pairs;
```

The results are approximately `0.6667`, `1`, `0.6667`, `1`, and `1`.
`COVAR_POP` uses population covariance in Doris 4.1.3; the release's
[covariance implementation](https://github.com/apache/doris/blob/4.1.3/be/src/exprs/aggregate/aggregate_function_covar.h)
distinguishes it from `COVAR_SAMP`. For paired aggregates, rows with either input
`NULL` are excluded. Consider the remaining observation count and variability
before interpreting a statistic. The lab's short date range is useful for
learning SQL, not evidence of a stable business relationship.

## 5.4 Filter and Describe Groups Correctly

`WHERE` defines which event rows reach an aggregation. `HAVING` decides which
aggregated groups remain. A requirement can need both:

> Among purchase events on March 3, which products generated at least 120,000
> in revenue?

The date and purchase conditions belong in `WHERE`. Product establishes the
grain in `GROUP BY`. The threshold applies to `SUM(revenue)` in `HAVING`.
Filtering individual events with `revenue >= 120000` would ask for very large
individual purchases, not products whose purchases collectively reach that
total. Lab 5 runs this complete query.

A useful logical reading order is input rows, row filtering, grouping and
aggregation, group filtering, window calculations, then final ordering and
limiting. This explains meaning, not a required physical execution sequence.
The Frontend (FE) creates and optimizes a distributed query plan and assigns
plan fragments; Backend (BE) nodes execute the assigned plan fragments.

### Make every projected value meaningful at the group grain

After grouping by `region`, the result has one row per region. A selected date
must now have a defined meaning for that whole group. An arbitrary detail
column cannot simply accompany the aggregate.

`ANY_VALUE(expression)` returns an arbitrary non-`NULL` value from the group,
or `NULL` when no non-`NULL` value exists. Doris also accepts `ANY` as an alias.
It does not promise the first, latest, most frequent, or repeatably chosen
value. See [ANY_VALUE](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/aggregate-functions/any-value/).

In the lab, the predicate limits input to one calendar day, so every event date
within a region is the same. Any representative date has the required meaning.
If the range expands to several days, the same expression no longer describes
daily regional totals. Choose `(event_date, region)` as the grouping grain for
that requirement, or use `MIN` and `MAX` if you need the earliest and latest
dates covered by a regional total.

Treat `ANY_VALUE` as a semantic choice, not a way to suppress an error before
deciding what a row should represent.

## 5.5 Name Each Analytical Stage

A Common Table Expression gives a query result a name within one statement.
The outer query can use that name in `FROM`. Multiple CTEs can express a sequence
of transformations, with later stages referring to earlier ones. Their names
do not create persistent tables. See [Common Table Expressions](https://doris.apache.org/docs/4.x/query-data/cte/).

Lab 5 names its aggregation `daily`. Read its contract before reading the
outer query:

| Stage | Input grain | Output grain | Purpose |
| --- | --- | --- | --- |
| Filter events | One event | One qualifying event | Select March 1 inclusive through March 9 exclusive |
| `daily` CTE | One qualifying event | One date present in the input | Calculate daily purchase revenue |
| Outer query | One daily result | One daily result | Display or compare the daily measures |

This makes the next calculation easier to express: it operates on daily revenue
rather than repeatedly mixing event expressions and daily measures. The lab
first displays `daily`, then uses the same definition in a separate statement
with windows.

A CTE is a way to express query structure. Its name does not guarantee that
Doris stores the result, scans the input only once, or makes the query faster.
The optimizer determines the execution plan. Use the named stages to clarify
meaning; use an execution plan and runtime evidence for performance claims.

### Distinguish a zero measure from a missing row

The lab's `daily` CTE retains all event types and calculates purchase revenue
conditionally. It returns eight dates. March 4–8 have zero purchase revenue
because those dates have input events but no purchases contributing revenue.

Grouping does not generate a row for a date with no input events. Replacing
the conditional measure with a purchase-only input filter also removes dates
without purchases. Neither a CTE nor a window automatically supplies a complete
calendar. A report that requires every date needs a calendar relation and an
explicit policy for missing values; joining relations is the next module's
subject.

## 5.6 Compare Rows Without Losing Their Grain

After aggregation, the question often changes: “How does each day compare with
the preceding one?” or “What is the cumulative revenue through this date?”
These questions need the daily rows to remain visible. Window functions attach
those comparisons to each row. Lab 5's eight daily rows remain eight after its
window calculations.

Three choices define the context of a window calculation:

| Clause | Decision |
| --- | --- |
| `PARTITION BY` | Which result rows belong to the same independent calculation? |
| Window `ORDER BY` | In what sequence should those rows be compared? |
| Frame, where applicable | Which portion of that sequence contributes to this row's aggregate? |

A window partition is a logical group of query result rows. It is distinct
from the physical table Partitions designed in Module 4. On daily regional
rows, `PARTITION BY region` would restart a cumulative calculation for each
region. Without it, all rows belong to one window partition. See
[Window Functions](https://doris.apache.org/docs/4.x/query-data/window-function/).

### Choose what “previous” means

The lab uses `LAG(daily_revenue, 1, 0) OVER (ORDER BY event_date)`. The offset
of one means the preceding result row in date order; the default zero is used
when that row does not exist. For the first result, zero is an explicit
reporting convention, not an observation of the day before the selected range.

With one row for every date in this lab interval, the preceding row is also the
preceding calendar day. If dates are missing, that equivalence disappears.
For example, a March 5 row immediately following March 3 would compare with
March 3. See [LAG](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/window-functions/lag/).

### State the cumulative frame explicitly

The cumulative expression in the lab is:

```sql
SUM(daily_revenue) OVER (
    ORDER BY event_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

This is an expression to place in a `SELECT` list. For each daily row, it sums
from the first row of the window partition through the current row. “Cumulative”
therefore starts at the first selected date, not at the beginning of the
dataset's history. Filtering out earlier dates also removes their contribution
to this calculation.

`ROWS` defines boundaries by row positions. For comparison,
`ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` would cover at most three result
rows; it represents three calendar days only when the input has exactly one
row per consecutive date. An explicit frame communicates the intended
calculation rather than leaving readers to infer a default.

### Decide how ties should affect ranking

`ROW_NUMBER` assigns distinct sequential positions. To make those positions
stable, supply an ordering that distinguishes the rows. The lab orders by
`daily_revenue DESC, event_date`: revenue determines priority and the unique
daily date resolves ties.

`RANK` instead gives equal ordering values the same rank and leaves gaps after
a tie. Consider these illustrative daily measures:

| Date | Revenue | `ROW_NUMBER` by revenue descending, date | `RANK` by revenue descending |
| --- | ---: | ---: | ---: |
| March 1 | 100 | 1 | 1 |
| March 2 | 100 | 2 | 1 |
| March 3 | 50 | 3 | 3 |

Choose `ROW_NUMBER` for a fixed number of positions with a defined tie-breaker.
Choose `RANK` when equal revenue should share a rank. Adding the distinct date
to `RANK`'s window ordering would break those ties and change the meaning.
The lab executes `ROW_NUMBER`; this comparison explains when you would choose
[RANK](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/window-functions/rank/)
instead.

Finally, window ordering and output ordering have separate jobs. Lab 5 assigns
revenue positions using one order but displays the result using
`ORDER BY event_date`. A chronological report can therefore contain a
revenue-ranking column without displaying the rows in rank order. Always state
the final order needed by the reader.

## 5.7 Choose How to Express Reusable Logic

Start with built-in functions and ordinary SQL expressions. They already
express the date transformations, aggregates, and comparisons in this module.
An unfamiliar requirement does not necessarily need a new function deployed
to the cluster.

| Need | Suitable approach |
| --- | --- |
| A supported transformation or measure | A built-in function, possibly combined with `CASE` |
| Named stages within one query | A CTE |
| A transformation or predicate applied to array elements | A lambda argument to an array higher-order function |
| A reusable name for supported function expressions | An Alias Function |
| Custom logic requiring an external implementation | An appropriate UDF implementation and deployment |

A **higher-order function** accepts a function expression as an argument.
In `ARRAY_MAP(x -> x * 2, [1, 2, 3, 4])`, the lambda names each element `x` and
defines its transformation. `ARRAY_FILTER` instead uses a predicate to decide
which elements to retain. Both return an array value; filtering its elements
does not filter the surrounding table's rows. Lab 5 uses literals so you can
see this without changing `events_modelled`. See [ARRAY_MAP](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/scalar-functions/array-functions/array-map/)
and [ARRAY_FILTER](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/scalar-functions/array-functions/array-filter/).

A lambda argument exists inside that expression. It does not register a
function name for later queries. Doris also provides **Alias Functions**,
registered through `CREATE ALIAS FUNCTION`, to give supported expressions a
reusable signature. For example, an alias can wrap a repeated built-in string
transformation. This is SQL expression reuse and does not require an external
Java implementation. See [Alias Function](https://doris.apache.org/docs/4.x/query-data/udf/alias-function/).

An externally implemented UDF is appropriate when the required behavior extends
beyond those expressions—for example, an organization's custom scoring
algorithm. Lab 5 illustrates the Java path: implement the scalar function's
`evaluate` method, package it in a Java Archive (JAR), make the artifact
available to Doris, and register its signature and implementation class before
calling it from SQL. The registration describes the implementation; it does
not contain the scoring algorithm. See [Java UDFs](https://doris.apache.org/docs/4.x/query-data/udf/java-user-defined-function/)
and [CREATE FUNCTION](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/function/CREATE-FUNCTION/).

The signature, return type, null behavior, and volatility declaration form part
of that function's contract. A declaration of `immutable` is appropriate only
when the same inputs always produce the same output. Logic depending on
changing external state would not meet that promise. The lab's Java registration
block is a non-executing template; you do not build an artifact or deploy a UDF.

---

## Lab 5: Explore Doris Functions and Build Analytical Queries

Open [Lab 5 — Explore Doris Functions and Build Analytical Queries](lab5_analyze_data.ipynb)
after completing Lab 4. The analytical input is the persistent
`doris_course.events_modelled` table with 10,158,080 events. Keep `events` as the
baseline and preserve `events_modelled` for Module 6.

The Notebook provides runnable SQL, function-matching cards, and a guided
query builder. Use the results to connect each stage to its meaning:

| Lab steps | What you do | What the result establishes |
| --- | --- | --- |
| 1–2 | Match function categories and inspect scalar transformations | Functions have different roles; derived values can be compared with their source fields |
| 3–5 | Calculate regional measures, filter product groups, and examine grouped projection | Measure inputs, group thresholds, and representative values follow different rules |
| 6–7 | Display the `daily` CTE and then add windows | Aggregation creates eight daily rows; windows retain those rows and add comparisons |
| 8 | Run array lambdas on literals | Element transformation and filtering return different array results |
| 9 | Select a grain, event filter, and metric | The generated SQL expresses those choices together |
| 10 | Read the Java UDF lifecycle and registration template | Function deployment is a separate activity from using built-in expressions |

For the builder's default **Day / Purchases only / Revenue** choices, describe
the question as “Rank dates with purchases by total purchase revenue during
March 1–8.” The highest result is March 2 with 9,933,097.98. It returns three
purchase dates, whereas the earlier all-event `daily` CTE contains eight dates.
Explain the input-filter difference before comparing their row counts.

When changing the builder, state what one row now represents and which events
contribute to the metric. Its final SQL orders by the metric descending and
then the reporting period, with a limit of ten rows. These are fixed presentation
choices, not additional controls in the builder.

The lab demonstrates SQL results. It does not benchmark alternative query
forms, inspect CTE materialization, export files, or deploy the UDF template.
Statistical aggregates and `RANK` are course extensions beyond its executed
queries. If you already have the optional Level 1 Metabase environment, you
can reuse the final analytical query there.

## Module summary

A useful analytical result connects its population, grain, and measures to a
specific question. Scalar functions derive dimensions; aggregates summarize
observations; CTEs name stages; windows compare the resulting rows while
retaining their grain. Filters, denominators, date coverage, and tie rules
determine what those numbers mean.

In Module 6, you will enrich these events with product attributes. The same
discipline applies: establish the intended grain before interpreting a result,
especially when a join can introduce additional rows.

## Official references

- Query structure: [SELECT](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-query/SELECT/), [CTEs](https://doris.apache.org/docs/4.x/query-data/cte/), and [Window Functions](https://doris.apache.org/docs/4.x/query-data/window-function/).
- Measures and representatives: [COUNT](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/aggregate-functions/count/), [AVG](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/aggregate-functions/avg/), [ANY_VALUE](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/aggregate-functions/any-value/), and [CORR](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/aggregate-functions/corr/).
- Statistical implementation for the lab release: [Apache Doris 4.1.3 covariance source](https://github.com/apache/doris/blob/4.1.3/be/src/exprs/aggregate/aggregate_function_covar.h).
- Function reuse: [Alias Function](https://doris.apache.org/docs/4.x/query-data/udf/alias-function/) and [Java UDFs](https://doris.apache.org/docs/4.x/query-data/udf/java-user-defined-function/).
- Result handling: [SELECT INTO OUTFILE](https://doris.apache.org/docs/4.x/data-operate/export/outfile/) and [Transactions](https://doris.apache.org/docs/4.x/data-operate/transaction/).
