# Module 6: Joining Data in Apache Doris

| Course information | Value |
| --- | --- |
| Course | Real-time Analytics with Apache Doris — Level 2 |
| Product baseline | Apache Doris 4.x |
| Lab version | Apache Doris 4.1.3 |
| Estimated time | Approximately 70 minutes, including the guided lab |

## Module goal

This module explains how to enrich event data through relationships with other
tables while preserving the meaning of an analytical result. You will choose
which rows a Join should retain, predict how many matches each event can
produce, and connect these logical choices to Doris execution plans.

Module 5 analyzed `doris_course.events_modelled`. Module 6 adds product category
and brand through `dim_products`, a dimension generated locally in the lab.
The persistent `events` baseline and `events_modelled` remain unchanged.

## Learning objectives

After completing this module, you will be able to:

1. Describe the grain and cardinality of a relationship, and identify when a
   Join can multiply events and their measures.
2. Choose Inner, Outer, Semi, Anti, or Cross Join from the required matches and
   unmatched rows, and place outer-join predicates deliberately.
3. Distinguish ordinary equality, NULL-safe equality, and the NULL-aware
   behavior required by `NOT IN`.
4. Recognize when historical enrichment requires an ASOF Join rather than a
   current product lookup.
5. Explain Hash Join build and probe roles and when a Nested Loop Join may be
   needed.
6. Compare Broadcast, Partition Shuffle, Bucket Shuffle, and Colocate Join
   using data movement, memory, and layout requirements.
7. Read Join and Runtime Filter evidence in `EXPLAIN`, distinguish it from
   runtime measurements, and explain why a hint needs evidence.

## Module structure

| Section | Format | Time | Outcome |
| --- | --- | ---: | --- |
| 6.1 Establish the Relationship Before Adding Attributes | Grain walkthrough | 5 min | Predict matching multiplicity and protect measures |
| 6.2 Choose Which Rows the Answer Must Retain | Join comparison | 7 min | Select retention rules and place outer-join filters |
| 6.3 Define What Missing Keys Mean | Small-case walkthrough | 5 min | Separate equality, existence, and NULL-aware exclusion |
| 6.4 Match Attributes to the Required Time | Temporal example | 5 min | Recognize current-state and ASOF requirements |
| 6.5 Connect Matching Rules to Physical Execution | Execution walkthrough | 6 min | Identify build, probe, and non-equi comparisons |
| 6.6 Choose Where Matching Rows Meet | Distribution comparison | 8 min | Explain four strategies and their tradeoffs |
| 6.7 Read the Plan Without Overstating the Evidence | Plan walkthrough | 9 min | Interpret distribution, Runtime Filters, and hints |
| Lab 6 | Hands-on | 25 min | Enrich events and inspect controlled Join results and plans |

---

## 6.1 Establish the Relationship Before Adding Attributes

A **fact table** records observations or business activity. A **dimension
table** provides descriptive attributes used to interpret that activity. Here,
one `events_modelled` row represents an original event, while one `dim_products`
row represents a product and its teaching category and brand.

Both tables contain `product_id`. Matching that identifier lets a query attach
product attributes to an event without copying them into the event table.
Start by asking how many dimension rows can match each event.

| Relationship on the Join key | Consequence for matching rows |
| --- | --- |
| One-to-one | Each row can have at most one match on the other side |
| Many events to one product | Many events reuse one product description; each event has at most one product match |
| One event to several product versions | The event produces a pair with every qualifying version |
| Many rows on both sides for the same key | Every qualifying left–right pair can appear |

For an equality Join, a non-`NULL` key appearing three times on the left and
twice on the right produces six matching pairs when there are no additional
conditions. The Join key need not be unique merely because it appears in `ON`.

Lab 6 uses a Unique Key table for `dim_products`, with `product_id` as its key.
Its one-row-per-product contract limits each event to at most one product
match. The separate Duplicate Key table `join_product_cases` deliberately
retains two versions of product `20` to demonstrate the other case. This
applies the Table Model distinctions from Module 4.

### Protect the measure as well as the row count

Suppose an event has revenue 40 and matches two product versions. The matching
result contains its revenue twice. A subsequent `SUM` can return 80 even though
the source event contributed only 40. Grouping after the Join does not repair
the relationship.

Choose the relationship required by the question before aggregating. For
current attributes, provide one current product row. For historical attributes,
select the version valid at the event time. For existence alone, a Semi Join
avoids returning every matching right-side row.

`DISTINCT` is not a general repair: version attributes may differ, and removing
identical projected rows can also collapse legitimate events. Likewise,
`SUM(DISTINCT revenue)` would discard equal monetary values from different
events. Neither operation expresses which product version belongs to an event.

## 6.2 Choose Which Rows the Answer Must Retain

The lab deliberately omits product `1005115` from `dim_products` and adds
dimension-only product `999999999`. Product `1004767` appears on both sides.
These cases make missing relationships visible without changing event data.

| Required answer | Join choice with events on the left |
| --- | --- |
| Events enriched only where a product definition exists | `INNER JOIN` |
| All events, with attributes where available | `LEFT OUTER JOIN` |
| All products, including those without events | `RIGHT OUTER JOIN` |
| Matches plus unmatched rows from both inputs | `FULL OUTER JOIN` |
| Events that have at least one product match, returning event columns | `LEFT SEMI JOIN` |
| Events that have no product match, returning event columns | `LEFT ANTI JOIN` |
| Every possible event–product combination | `CROSS JOIN` |

Outer Joins fill the absent side's columns with `NULL`. Right Semi and Right
Anti Joins apply the corresponding existence rules to the right input.
See the [Doris Join reference](https://doris.apache.org/docs/4.x/query-data/join/)
for the supported types.

An Inner Join is appropriate for a report explicitly limited to recognized
products. A Left Outer Join is appropriate when unrecognized products must
remain part of the event population. Neither choice is universally correct:
it depends on whether missing enrichment should exclude business activity.

In the lab's category-and-region report, the Inner Join intentionally excludes
the omitted product. Its revenue total therefore need not equal the total of
all selected purchases before enrichment. Moreover, `LIMIT 12` displays only
the leading groups. Those displayed rows are not the complete matched total.

A Semi Join retains each qualifying left input row once even when several
right rows match. It does not deduplicate separate left input rows. An Anti
Join identifies unmatched events; add a separate grouping or distinct
projection only if the requested answer is a list of orphan product IDs.

A Cross Join between four rows and five rows returns twenty pairs. It can be
useful for a deliberately small grid, such as dates crossed with regions, but
it would be an inappropriate starting point for enriching ten million events
with a large product dimension.

### Keep outer-join matching separate from result filtering

Consider “Keep every event, and attach a product description only when its
category is `category_1`.” The category condition belongs in the match:

```sql
SELECT e.event_id, d.category
FROM doris_course.events_modelled e
LEFT OUTER JOIN doris_course.dim_products d
  ON e.product_id = d.product_id
 AND d.category = 'category_1'
WHERE e.event_id IN (1, 2, 3);
```

The final predicate limits this illustrative query to three event identifiers.
Within that selection, events without a qualifying category match still
appear, with `NULL` for `d.category`.

Moving `d.category = 'category_1'` into `WHERE` would discard those rows:
equality against the resulting `NULL` is not true. That would answer “Keep only
events with a matching product in this category.” Predicate placement is part
of the result contract, not just a formatting preference.

After an outer join, also choose counts deliberately. `COUNT(*)` counts result
rows, including unmatched rows. `COUNT(d.product_id)` counts matched product
values here because the dimension's identifier is non-nullable. A nullable
attribute such as an optional brand would not be a reliable match indicator.

## 6.3 Define What Missing Keys Mean

SQL conditions distinguish true, false, and unknown. Ordinary equality involving
`NULL` is unknown, so two missing keys do not form a match under `=`. The lab's
event `4` and its `NULL` product-case row therefore remain unmatched.

Doris provides NULL-safe equality, `<=>`, which considers two `NULL` values
equal. The same controlled event then has one match. This is useful only when
the business contract treats two missing values as the same category. Missing
product IDs do not automatically refer to the same unknown product.

If several rows on each side have `NULL` keys, using `<=>` can multiply their
matches just as repeated non-`NULL` keys do. Changing the equality operator
changes the relationship; it does not restore uniqueness.

### Distinguish “no matching row” from `NOT IN`

With ordinary equality, a Left Anti Join asks whether any right row forms a
true match. In the lab's small cases, it retains event `3` with product `30`
and event `4` with a `NULL` key: neither finds an equal product.

Now consider this separate query over those same cases:

```sql
SELECT e.event_id
FROM doris_course.join_event_cases e
WHERE e.product_id NOT IN (
    SELECT product_id FROM doris_course.join_product_cases
)
ORDER BY e.event_id;
```

It returns no rows. Product `30` is unequal to the known right-side identifiers,
but the right-side `NULL` makes its membership exclusion unknown. A missing
left key also does not make the predicate true for this nonempty input.

A NULL-aware Anti Join is an execution form Doris can use to preserve these
`NOT IN` semantics. It is not equivalent to an ordinary Anti Join or to replacing
`=` with `<=>`. Choose `NOT EXISTS` or an explicit Anti Join when the business
question is absence of a matching row; choose `NOT IN` only with a deliberate
understanding of the input's nullability. See [Subqueries](https://doris.apache.org/docs/4.x/query-data/subquery/)
and the release's [Join type definitions](https://github.com/apache/doris/blob/4.1.3/fe/fe-core/src/main/java/org/apache/doris/nereids/trees/plans/JoinType.java).

## 6.4 Match Attributes to the Required Time

A current product dimension answers “What attributes does this product have
now?” If a product changes category, joining an old event to its current row
can classify historical revenue under the new category. That may be correct
for a current catalog report, but it does not reconstruct the past.

For “Which category applied when the event occurred?”, retain product-state
history and match on both identity and time. Imagine a product state at 10:00,
another at 10:20, and an event at 10:15. A backward-looking match selects the
10:00 state. Equality of timestamps would miss it, while a regular Join to
every earlier state could return several rows.

Doris ASOF Join chooses the nearest qualifying right-side time within an
equality-key group. `MATCH_CONDITION(e.event_time >= d.valid_from)` means the
latest state at or before the event; `<=` looks forward instead. Strict `>`
and `<` exclude equal timestamps. `ASOF LEFT JOIN` preserves an unmatched
event, while `ASOF INNER JOIN` discards it.

This independent example uses only Common Table Expressions (CTEs) and literals:

```sql
WITH event_sample AS (
    SELECT 10 AS product_id,
           CAST('2020-03-03 10:15:00' AS DATETIME) AS event_time
), product_states AS (
    SELECT 10 AS product_id,
           CAST('2020-03-03 10:00:00' AS DATETIME) AS valid_from,
           'earlier' AS category
    UNION ALL
    SELECT 10, CAST('2020-03-03 10:20:00' AS DATETIME), 'later'
)
SELECT e.event_time, d.valid_from, d.category
FROM event_sample e
ASOF LEFT JOIN product_states d
    MATCH_CONDITION(e.event_time >= d.valid_from)
    ON e.product_id = d.product_id;
```

The result selects `earlier`, with `valid_from = 2020-03-03 10:00:00`.
Ensure a single authoritative state per product and effective timestamp;
tied right-side timestamps do not provide a deterministic business choice.
A nearest earlier state also needs to be valid until superseded for this
model to express historical validity. See [ASOF Join](https://doris.apache.org/docs/4.x/query-data/asof-join/).

Lab 6's generated category and brand are fixed teaching attributes. It does
not create a history table or execute ASOF; this example extends the choice
of relationship beyond its current product dimension.

## 6.5 Connect Matching Rules to Physical Execution

The logical Join defines the answer. A physical implementation describes how
Doris finds the matches. Data distribution describes where its inputs meet.
Keep these separate: an Inner Join can use a Hash Join with Broadcast or with
Shuffle without changing the intended matching rows.

The Frontend (FE) creates and optimizes a distributed query plan, then assigns
plan fragments. Backend (BE) nodes execute the assigned plan fragments.
Join order, estimated input sizes, conditions, and available data distribution
inform the optimizer's choices.

### Use equality to organize candidate matches

In a Hash Join, the **build side** supplies rows organized in a hash table by
the equality keys. The **probe side** supplies rows whose keys locate candidate
matches. Doris uses the physical right child as build and the physical left
child as probe. Inspect the actual plan: the optimizer can reorder inputs, so
SQL text order alone does not establish those roles.

The hash table does not make duplicate keys disappear. It must support the
matches required by the logical Join. It also consumes memory for keys and
the required build-side data, which is one reason a smaller build input can
be attractive.

An equality condition can coexist with other predicates. A Join on product ID
plus a time-range condition can use the equality key to locate candidates and
then test the remaining condition. The presence of any inequality does not
automatically require Nested Loop Join.

### Recognize when there is no equality key

A pure condition such as `e.product_id > d.product_id` supplies no equality
key for a hash lookup. A Nested Loop Join can compare candidate row pairs and
evaluate that condition. Its potential work grows with both inputs, so keep
unbounded pairwise comparisons away from large event tables.

Lab 6 inspects an equality and a pure inequality query on four event rows and
five product rows. Their plans show Hash Join and Nested Loop Join respectively.
These are implementation examples, not a timing contest. A physical strategy
cannot make an unintended many-to-many relationship correct.

## 6.6 Choose Where Matching Rows Meet

In a distributed cluster, rows with the same product ID may initially reside
on different BE nodes. Doris must make the required candidates available to
the Join instances. Four important strategies address that need:

| Strategy | How the Join inputs meet | Main consideration |
| --- | --- | --- |
| Broadcast | Replicate a build input to participating Join workers | Repeated transfer and a build copy at each destination |
| Partition Shuffle | Hash-redistribute both inputs on the Join keys | Transfer both sides while spreading matching work |
| Bucket Shuffle | Reuse one compatible hash layout and redistribute the other input | Layout compatibility and the retained side's parallelism |
| Colocate | Use compatible inputs already placed together | A maintained colocation contract for stored tables |

“Partition” in Partition Shuffle refers to dividing query rows among execution
destinations. It does not mean creating or changing the monthly table
Partitions from Module 4.

### Compare the inputs after filtering and projection

Broadcast is often useful when a filtered dimension is small enough to replicate
and build comfortably at the destinations. The relevant size includes selected
columns and surviving rows, not merely the total row count of the stored table.
The lab's `d.category = 'category_1'` predicate reduces the dimension input.

For two large inputs, replicating one side can be expensive. Partition Shuffle
distributes both by the equality keys so matching keys arrive together. It can
spread work across workers, but a highly frequent key can still create a
hotspot: hashing does not divide one key's matches evenly among destinations.

There is no universal row-count threshold or fastest strategy. Row width,
filter selectivity, key skew, worker count, memory, and Join type all matter.
Optimizer estimates depend on statistics; inspect them when a plan makes an
unexpected choice. See [Statistics](https://doris.apache.org/docs/4.x/query-acceleration/optimization-technology-principle/statistics/).

### Reuse layout only when it fits the Join

`events_modelled` is bucketed by `user_id`, whereas this relationship joins on
`product_id`. Its existing layout therefore does not by itself colocate product
matches. `dim_products` is hash bucketed by `product_id`, with four Buckets.
The lab's hinted plan can reuse that compatible layout and reports Bucket
Shuffle. Reuse is determined by the plan's distribution properties, not by
whether the table is called a fact or a dimension.

Colocate Join requires more than writing the same `HASH(product_id)` expression
on two stored tables. Tables in a Colocation Group share compatible distribution
column types, Bucket counts, replica counts, and corresponding replica placement.
The Join must use compatible keys, and the group must be stable. The lab's
tables do not establish that contract. See [Colocation Join](https://doris.apache.org/docs/4.x/query-acceleration/colocation-join/).

Avoiding Join shuffle does not eliminate every transfer in a query. A later
aggregation or result gather can still move data. Nor does less transfer
guarantee lower elapsed time: a layout with too few Buckets may limit useful
parallelism. Choose layout from the wider workload rather than redesigning
every table around one Join.

## 6.7 Read the Plan Without Overstating the Evidence

`EXPLAIN` describes the planned execution. Lab 6 uses `EXPLAIN SHAPE PLAN` to
make operator relationships visible without executing the analytical query.
Its helper displays a comparison summary for the tiny cases and retains their
complete plans; the final distribution examples display the raw plan trees.

Read the Join operator and then trace its children to their Scans:

| Evidence in the tested lab plan | What it tells you |
| --- | --- |
| `hashJoin[INNER_JOIN broadcast]` | The logical type, physical implementation, and chosen distribution |
| `hashCondition=((e.product_id = d.product_id))` | The equality used for matching |
| `build RFs:RF... product_id->[product_id]` | A planned Runtime Filter producer and its key relationship |
| `PhysicalOlapScan[events_modelled] apply RFs: RF...` | The event Scan is a planned filter consumer |
| `hashJoin[INNER_JOIN shuffleBucket]` | The alternative plan uses Bucket Shuffle |
| `[shuffle]` in the hint log's `Used` entry | The planner accepted the comparison hint |

Node identifiers and Runtime Filter numbers may change. Use the table names,
conditions, and parent–child relationships to interpret the tree. A
`PhysicalDistribute[DistributionSpecGather]` above the aggregation gathers
results; its presence alone does not identify the Join's distribution. The
full `EXPLAIN` can expose fragment and Exchange details beyond the compact
shape. See [EXPLAIN](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-query/EXPLAIN/).

### Understand what a Runtime Filter can remove

For the lab's Inner Hash Join, the filtered product input supplies qualifying
product IDs. During execution, Doris can construct a Join Runtime Filter from
those values and send it toward the event Scan. An event whose product cannot
match can then be rejected before reaching the Join.

This optimization preserves the answer; it does not replace the Join or return
category attributes. Some filter forms, such as Bloom Filters, can allow
nonmatching candidates through, so final matching still matters. The same
rejection is not generally valid on a Left Outer Join's preserved event side,
where unmatched events must remain. Filter placement must respect Join semantics.
See [Runtime Filter](https://doris.apache.org/docs/4.x/query-acceleration/optimization-technology-principle/runtime-filter/).

A planned producer and consumer do not reveal how many rows were actually
rejected, whether the filter arrived early enough to help, or how much input/output
(I/O) it saved. Those questions require execution and a Runtime Profile. The
lab collects plan evidence, not those runtime measurements.

### Treat the hint as a comparison, not a default recipe

Lab 6 places `[shuffle]` immediately before the right relation to request an
alternative distribution. The accepted request produces Bucket Shuffle in
the tested 4.1.3 environment; it does not necessarily mean both stored tables
are fully redistributed. Read the resulting plan to determine how Doris
satisfies the request. See [Join distribution hints](https://doris.apache.org/docs/4.x/query-acceleration/tuning/tuning-plan/adjusting-join-shuffle/).

In application queries, begin with the optimizer's choice. If runtime evidence
shows a problem, examine filtered input sizes, statistics, skew, and memory
before testing a hint. A changed distribution label is not evidence of an
improvement. The single-BE sandbox cannot demonstrate cross-BE network savings
or establish which strategy would win on a distributed workload.

---

## Lab 6: Enrich Event Data and Observe Join Execution

Open [Lab 6 — Enrich Event Data and Observe Join Execution](lab6_join_data.ipynb)
after completing the earlier modules. It uses the persistent
`doris_course.events_modelled` input and creates only its own `dim_products`,
`join_event_cases`, and `join_product_cases` tables.

The dimension contains 204,231 product rows. Category and brand are generated
deterministically from identifiers; they are teaching attributes, not a real
product catalog. No additional external dataset is required.

| Lab section | What you observe | Connection to the course |
| --- | --- | --- |
| 1 | A product dimension with deliberate matched and unmatched identifiers | Establish the relationship contract |
| 2 | Inner, Left Outer, Left Semi, and Left Anti results | Choose row retention before enrichment |
| 3 | Twelve leading category-and-region purchase groups | Connect matching population to analytical grain |
| 4 | Four event-case rows produce five Left Outer Join rows | Predict duplicate-key multiplication |
| 5 | A missing key has zero matches under `=` and one under `<=>` | Make missing-key semantics explicit |
| 6 | Hash and Nested Loop operators for different conditions | Separate logical Join from physical implementation |
| 7 | Broadcast and Bucket Shuffle plans, with Runtime Filter annotations | Explain planned distribution and its evidence limits |

For the selected baseline products, `1004767` retains 105,046 events with a
dimension match. The 89,522 events for omitted product `1005115` survive the
Left Outer and Left Anti queries but not the Inner or Left Semi queries.
These counts demonstrate retention over the selected identifiers; they do not
represent the entire baseline.

Right/Full Outer Join, Cross Join, NULL-aware exclusion, ASOF, and Colocate are
conceptual extensions beyond the lab's executed cases. Its distribution
comparison uses plans and does not benchmark Join strategies. Preserve the
baseline and modeled events when completing or rerunning the lab.

## Module summary

A Join combines a relationship contract with a retention rule. Check how many
matches a row can produce, how missing keys behave, and whether attributes
describe the required point in time before interpreting counts or revenue.
Then read the physical plan to understand how Doris finds and distributes
those matches. Runtime evidence is needed to evaluate performance.

Module 7 moves from querying relationships to maintaining current state with
updates and deletes. It uses separate tables so the event history remains
available for analytical work.

## Official references

- Semantics: [Joins](https://doris.apache.org/docs/4.x/query-data/join/), [Subqueries](https://doris.apache.org/docs/4.x/query-data/subquery/), and [ASOF Join](https://doris.apache.org/docs/4.x/query-data/asof-join/).
- Distribution: [Colocation Join](https://doris.apache.org/docs/4.x/query-acceleration/colocation-join/) and [Join distribution hints](https://doris.apache.org/docs/4.x/query-acceleration/tuning/tuning-plan/adjusting-join-shuffle/).
- Evidence: [EXPLAIN](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-query/EXPLAIN/) and [Runtime Filter](https://doris.apache.org/docs/4.x/query-acceleration/optimization-technology-principle/runtime-filter/).
- Release source: [Apache Doris 4.1.3 JoinType.java](https://github.com/apache/doris/blob/4.1.3/fe/fe-core/src/main/java/org/apache/doris/nereids/trees/plans/JoinType.java), including logical Join types and left/right transformations.
