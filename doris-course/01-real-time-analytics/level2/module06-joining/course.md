# Module 6: Joining Data in Apache Doris

| Course information | Value |
| --- | --- |
| Course | Real-time Analytics with Apache Doris · Level 2 |
| Doris | Apache Doris 4.1.3 |
| Environment | The course sandbox and `events_modelled` from Lab 4 |
| Estimated time | About 95 minutes: reading 55, Lab 30, quiz 10 |

[Course README](../../README.md) · [Open Lab 6](lab06_join_data.ipynb) · [Open Quiz 6](quiz06_join_semantics_and_execution.ipynb)

## Module goal

Combine related data without losing control of the result's grain: start from
the business relationship and the rows the answer must keep, then see how
Doris implements the Join and moves the data so that matching rows meet.

An operations team wants purchase revenue by product category and region. The
events carry `product_id`, and the product attributes live in a dimension,
`dim_products`, which Lab 6 generates with a Unique Key and one row per
product. It deliberately omits one product to expose an unmatched relationship.
A separate small table, `join_product_cases`, repeats a product key to show
how duplicate matches multiply event rows.

## Learning objectives

After completing this module, you will be able to:

1. Predict a Join's result grain and multiplicity from the grain and key cardinality of both inputs.
2. Choose Inner, Outer, Semi, Anti, Cross, or ASOF Join from the rows that the answer must retain.
3. Decide how `NULL` keys match and whether a right-side condition belongs in `ON` or `WHERE`.
4. Explain when Doris uses a Hash Join or a Nested Loop Join, and what the build and probe sides do.
5. Compare Broadcast, Partition Shuffle, Bucket Shuffle, and Colocate Join by the data each moves and the layout each needs.
6. Read the Join strategy and Runtime Filters in `EXPLAIN` separately from what the Query Profile records.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 6.1 Establish the Relationship Before Adding Attributes | 6 min | Predict one-to-one, one-to-many, or many-to-many results from both grains |
| 6.2 Choose the Logical Join Operator from the Rows the Answer Must Retain | 6 min | Choose Inner, Outer, Semi, Anti, Cross, or ASOF semantics |
| 6.3 Define What Missing Keys and Predicates Mean | 6 min | Choose `=` or `<=>`, and place right-side predicates in `ON` or `WHERE` |
| 6.4 Connect the Join Condition to Its Physical Implementation | 7 min | Tell Hash Join from Nested Loop Join, and the build side from the probe side |
| 6.5 Use Broadcast When the Build Input Is Small Enough to Replicate | 5 min | Copy a small build input to every participant |
| 6.6 Use Partition Shuffle When Both Inputs Need Redistribution | 5 min | Route both inputs by the Join key |
| 6.7 Use Bucket Shuffle When One Existing Layout Can Be Reused | 5 min | Keep one compatible bucketed input in place |
| 6.8 Use Colocate for a Stable, Repeated Join Relationship | 4 min | Store both inputs with matching Buckets in advance |
| 6.9 Reduce Probe Candidates with a Runtime Filter | 6 min | Use the build side's keys to filter the probe-side scan |
| 6.10 Read Plan Evidence Separately from Runtime Effect | 5 min | Read the plan, the Profile, and hints for what each shows |
| Lab 6 | 30 min | Run the Join types on controlled cases, then read plans and a Profile |
| Quiz 6 | 10 min | Six questions on these objectives |

## 6.1 Establish the Relationship Before Adding Attributes

A **fact table** records observations or activity. A **dimension table**
describes business entities used to interpret those facts. In this module:

- one `events_modelled` row represents one original event;
- one valid `dim_products` row represents one product definition.

Both tables contain `product_id`, but a shared column name does not guarantee a
safe relationship. Before writing SQL, ask:

1. What does one row represent on each side?
2. Which columns form the Join condition?
3. How many rows on either side can share that Join Key?
4. Should an input row produce zero, one, or several result rows?
5. Which measures would be repeated if the relationship produces several
   pairs?

### Predict matching multiplicity

For one equality Key, the number of matching pairs is the product of the
matching row counts on both sides:

```text
3 left rows with product_id = 20
×
2 right rows with product_id = 20
=
6 matching result pairs
```

This is valid relational behavior. A Join does not infer that a table called a
dimension should contain one row per Key.

| Relationship | Meaning | Possible result effect |
| --- | --- | --- |
| One-to-one | Each Key occurs at most once on either side | One matching pair per Key |
| Many-to-one | Many events refer to one product row | Each matched event remains one enriched row |
| One-to-many | One event Key matches several dimension or history rows | The event is repeated once for every match |
| Many-to-many | Both sides repeat the Key | Every qualifying left-right combination appears |

The main `dim_products` table uses a Unique Key on `product_id`, supporting the
intended many-events-to-one-product relationship. Lab 6 also creates a small
Duplicate Key fixture with two product-version rows for `product_id = 20`.
The matching event appears twice in the Join result.

### Protect measures as well as row count

Suppose an event has revenue 29.95 and matches two dimension versions. A query
that groups after the Join can sum 59.90 unless it first selects the one version
that belongs to the event.

Do not repair this blindly with `SUM(DISTINCT revenue)`. Two real events can
have the same revenue, so distinct values do not identify distinct events.
Resolve the relationship using its business rule: enforce one current dimension
row, add a version criterion, perform point-in-time matching, or aggregate at a
grain that intentionally contains every match.

### Separate enrichment from existence

If the answer needs category and brand, an ordinary Join can return right-side
columns. If the answer asks only whether a product definition exists, a Semi
Join expresses that requirement without returning dimension columns. It also
does not multiply a left row merely because several right rows satisfy the
existence condition.

Define the needed output before choosing the Join form.

## 6.2 Choose the Logical Join Operator from the Rows the Answer Must Retain

A logical Join operator is primarily a row-retention decision. `INNER`,
`OUTER`, `SEMI`, and `ANTI` describe which matched or unmatched rows belong in
the answer. They do not say where those rows are stored or how Doris will move
them during execution. Start with the required result, not with the shortest
syntax.

### Choose among matched and unmatched rows

| Business requirement | Suitable Join | Result behavior |
| --- | --- | --- |
| Analyze only events with a known product | `INNER JOIN` | Return matching pairs only |
| Keep every event and attach product data when available | `LEFT OUTER JOIN` | Preserve all left rows; unmatched right columns are `NULL` |
| Keep every product and attach event data when available | `RIGHT OUTER JOIN` | Preserve all right rows; unmatched left columns are `NULL` |
| Reconcile both sides and retain both kinds of unmatched row | `FULL OUTER JOIN` | Preserve unmatched rows from both sides |
| Return only events for which a product exists | `LEFT SEMI JOIN` | Return qualifying left rows without right columns |
| Return only events for which no product exists | `LEFT ANTI JOIN` | Return unmatched left rows |
| Generate every combination intentionally | `CROSS JOIN` | Return the Cartesian product |

With 100 left rows and 20 right rows, a Cross Join has 2,000 combinations
before later filtering. Use it only when every combination belongs to the
question, such as constructing a small date-by-region reporting grid. Do not
use it as an accidental substitute for a missing condition.

Right Semi and Right Anti Join reverse which side is returned. The preserved
side should match the subject of the question. “Which events have a product?”
naturally returns event columns through a Left Semi Join when events are on the
left.

### Match historical attributes at the correct time

A current-state dimension answers “what is the product category now?” It may
not answer “which category was in effect when the event occurred?” If product
history contains effective timestamps, exact equality on event and state time
is usually wrong because a state row may begin before many later events.

ASOF Join expresses nearest-neighbor time semantics. For example:

```sql
FROM product_events e
ASOF LEFT JOIN product_history h
MATCH_CONDITION(e.event_time >= h.effective_time)
ON e.product_id = h.product_id
```

Within each equal `product_id`, this direction selects the closest history row
whose effective time is at or before the event time. “Closest” follows the
specified comparison direction; it does not mean the smallest absolute time
difference. ASOF Left Join keeps an event with no qualifying history row and
fills right-side columns with `NULL`; ASOF Inner Join discards it.

Lab 6 uses a current product lookup and does not add a second historical
dimension. See [ASOF Join](https://doris.apache.org/docs/4.x/query-data/asof-join/)
for supported temporal types, comparison directions, and restrictions.

## 6.3 Define What Missing Keys and Predicates Mean

Missing values affect both matching and exclusion. Decide whether `NULL`
means “no comparable Key” or whether two missing values should belong to one
intentional unknown group.

### Choose ordinary or NULL-safe equality

Ordinary SQL equality does not make a matching pair when either operand is
`NULL`:

```text
9 = 9       → TRUE
9 = NULL    → UNKNOWN
NULL = NULL → UNKNOWN
```

Doris also supports NULL-safe equality:

```text
9 <=> 9       → TRUE
9 <=> NULL    → FALSE
NULL <=> NULL → TRUE
```

Use `e.key <=> d.key` only when the relationship explicitly says that a missing
Key on each side represents the same matchable group. If `NULL` means that the
entity is unidentified, matching all missing rows can create a large and false
many-to-many relationship.

The Lab fixture contains four event rows with `product_id` values `10`, `20`,
`30`, and `NULL`; those are four rows, not one composite Key. Its product rows
also include one `NULL`. For the one event whose `product_id` is `NULL`, `=`
produces zero pairs while `<=>` produces one.

### Distinguish Anti Join from `NOT IN` with NULL

A Left Anti Join asks which left rows have no matching right row under its Join
condition. A `NOT IN` subquery carries SQL three-valued logic: if the candidate
set contains `NULL`, ordinary comparisons may become unknown rather than true.

Doris provides `NULL AWARE LEFT ANTI JOIN` for the corresponding NULL-aware
semantics. The official Join contract notes that it handles `NULL` specially
and ignores left rows whose match column is `NULL`. Do not rewrite `NOT IN` as
an ordinary Anti Join until the required NULL behavior has been established.

### Place Outer Join predicates deliberately

Assume the report must keep every event but attach only active product rows.
These two patterns differ:

```sql
-- Preserve every event; only active product rows can match.
LEFT JOIN dim_products d
  ON e.product_id = d.product_id
 AND d.is_active = 1
```

```sql
-- The WHERE predicate removes the NULL-extended unmatched rows.
LEFT JOIN dim_products d
  ON e.product_id = d.product_id
WHERE d.is_active = 1
```

The first retains an event whose product is missing or inactive, with `NULL`
right-side columns. The second filters that result afterward and behaves like
an Inner Join for this predicate. `ON` defines eligible matches; `WHERE`
filters the result rows produced by the Join.

## 6.4 Connect the Join Condition to Its Physical Implementation

Doris supports Hash Join and Nested Loop Join as physical implementations.
The condition determines whether an equality Key can organize candidate
matches.

Sections 6.2 and 6.3 established the logical result: which rows survive, how
`NULL` behaves, and where predicates apply. Physical planning starts here and
answers two separate questions:

1. **How will one Join execution instance find matching candidates?** Hash Join
   uses an equality Key; Nested Loop Join can evaluate relationships without
   one.
2. **How will matching rows reach the same execution instance in a distributed
   cluster?** Broadcast, Partition Shuffle, Bucket Shuffle, and Colocate are
   data-distribution strategies discussed in Sections 6.5–6.8.

Choosing a distribution strategy does not change an Inner Join into an Outer
Join or change the equality condition. It supplies the physical inputs on which
the selected Join implementation operates.

### Build and probe an equi-Join

For an equality condition such as

```sql
e.product_id = d.product_id
```

Doris can build an in-memory hash table from the physical right-side input and
stream physical left-side rows through it:

```text
right-side rows                         left-side rows
dim_products                            events_modelled
      |                                       |
      | build hash table by product_id        | probe by product_id
      v                                       v
{ 10 → row, 20 → row, ... }  <----------  event Key candidates
```

**Build side** and **probe side** are roles inside a Join operator. They are not
permanent properties of a fact or dimension table, and they do not mean one BE
instance is always “the build BE” while another is always “the probe BE.” Each
participating Join execution instance receives the inputs assigned by the
distributed plan and performs its build and probe work.

The optimizer can reorder logical inputs before assigning those physical roles.
Read the plan instead of assuming that SQL text alone fixes them. A filtered
dimension often becomes the build input because its hash table is smaller, but
the decision depends on Join semantics, statistics, filters, and projections.

### Recognize when Nested Loop evaluation is needed

A pure non-equi condition such as

```sql
e.amount > band.minimum_amount
```

provides no equality Key from which to build candidate hash groups. Doris may
use a Nested Loop Join and evaluate the condition across candidate pairs. A
Cartesian product is another Nested Loop scenario.

The presence of `>` does not by itself force Nested Loop Join. This condition
still has an equi-key:

```sql
e.product_id = d.product_id
AND e.event_time > d.effective_time
```

Doris can use `product_id` for Hash Join candidate matching and evaluate the
time condition as an additional predicate. Ask whether any valid equality
condition organizes candidates, rather than scanning the SQL for a range
operator.

Nested Loop Join is more general but may compare far more pairs. Lab 6 keeps
its pure non-equi comparison tiny and uses `EXPLAIN SHAPE PLAN`; it does not run
an unbounded non-equi Join over ten million events. See [Doris Joins](https://doris.apache.org/docs/4.x/query-data/join/).

### Move rows so matching Keys can meet

Data movement becomes a distributed Join concern when participating data and
Join execution are spread across multiple Backend (BE) nodes or execution
instances. A row on one BE cannot be matched by a Hash Join instance that never
receives the corresponding row from the other input.

Suppose three BEs initially hold these unrelated pieces:

```text
BE 1: events product_id {10, 20}       products product_id {30}
BE 2: events product_id {30}           products product_id {10}
BE 3: events product_id {10, 40}       products product_id {20, 40}
```

A local-only Join would miss valid matches: the product row for Key 10 is on
BE 2 while event rows with Key 10 are on BE 1 and BE 3. The distributed plan
must therefore do one of the following:

```text
Broadcast:          copy the complete small build input to every participant
Partition Shuffle: hash both inputs by Join Key and route equal Keys together
Bucket Shuffle:    keep one compatible bucketed input; route only the other
Colocate:          use an existing layout where matching Buckets are together
```

These choices balance network transfer, per-instance memory, skew, and the
ability to reuse an existing layout:

- **Broadcast** avoids moving the large probe input, but every participating
  instance receives and builds a complete copy of the smaller input. It is safe
  only when that post-filter, post-projection build input fits the memory budget
  of every participant. It is not a way to make a large build input fit limited
  memory.
- **Partition Shuffle** is the general large-to-large choice when neither side
  can be replicated. Each instance receives only its Join-Key partition and
  builds or probes that subset, spreading the work and hash state across the
  cluster. Both inputs may cross the network, and a skewed Key can still create
  an oversized partition.
- **Bucket Shuffle** reduces movement by keeping one already compatible input
  in place and moving only the other.
- **Colocate** can avoid Join-time movement when both inputs were deliberately
  stored with compatible Bucket placement for a repeated relationship.

In a single-BE sandbox, an `EXPLAIN` plan can still identify the chosen
distribution strategy and local exchanges may connect execution instances,
but the Lab cannot measure real cross-BE transfer. The reason to learn these
strategies is the multi-BE production case.

## 6.5 Use Broadcast When the Build Input Is Small Enough to Replicate

In a massively parallel processing (MPP) cluster, equal Keys must meet at the
same Join execution location. Broadcast keeps the physical left/probe input in
place and sends the complete physical right/build input to every node
participating in the Join.

```text
small filtered build relation
        rows {10, 20}
          /    |    \
         v     v     v
      Join A Join B Join C
        ^      ^      ^
        |      |      |
local probe partitions remain in place
```

The large fact input is not copied to every BE in this strategy. The replicated
data is the build relation. Every participating instance needs its own complete
build-side set so it can match its local probe rows.

### Compare post-filter inputs

Broadcast suitability depends on data entering the Join, not the original
table label:

- A large dimension can become small after a selective predicate and column
  projection.
- A table called a dimension can still be too large to replicate safely.
- More participating instances increase aggregate network transfer and memory
  for copies of the build data.
- Join type matters; the official Doris contract does not apply Broadcast to
  Right Outer, Right Anti, or Right Semi Hash Joins.

In Lab 6, `dim_products` has 204,231 rows compared with 10,158,080 event rows,
and the query further filters the dimension to one category. The default
Doris 4.1.3 plan reports `hashJoin[INNER_JOIN broadcast]`. In the single-BE
sandbox, this is plan evidence of the chosen strategy. It is not a measurement
of cross-node Broadcast cost.

## 6.6 Use Partition Shuffle When Both Inputs Need Redistribution

Two large inputs may use incompatible storage layouts, and neither may be safe
to replicate. Partition Shuffle computes a Join-Key hash on both inputs and
sends each row to the matching execution partition.

Suppose the target routing rule for illustration is `hash(product_id) mod 3`:

| Input row | Product Key | Target execution partition |
| --- | ---: | --- |
| Event A | 10 | P1 |
| Event B | 20 | P2 |
| Event C | 10 | P1 |
| Product X | 20 | P2 |
| Product Y | 10 | P1 |

The two rows with Key 10 meet in P1, and the rows with Key 20 meet in P2,
regardless of which source BE originally stored them. Each target Join instance
then builds and probes its local partition.

```text
left input ---- hash(join_key) ----\
                                  +--> matching execution partitions
right input --- hash(join_key) ----/
```

These are execution partitions created for data exchange. They are not the
monthly table Partitions introduced in Module 4. A table Partition decides a
stored row's lifecycle and pruning range; Partition Shuffle decides where an
input row travels for this Join execution.

Partition Shuffle is a general large-to-large equi-Join strategy because it can
make matching Keys meet without relying on an existing compatible layout. The
tradeoff is that rows from both inputs may cross Exchange boundaries. Skewed
Join Keys can also concentrate work in one target partition even when the
average input size appears reasonable.

Use table statistics and a Query Profile to assess actual cardinality and skew.
The single-BE lab explains the route and plan structure but does not simulate
cross-node bytes for a real Partition Shuffle.

## 6.7 Use Bucket Shuffle When One Existing Layout Can Be Reused

Bucket Shuffle reduces movement when one physical input is already Hash
bucketed compatibly with the Join condition. That input remains in its existing
Bucket locations; the other input is redistributed by the same Join Key to
those locations.

For a hypothetical event table bucketed by `product_id`:

```text
existing event Bucket 0  <--- dimension rows whose product_id maps to 0
existing event Bucket 1  <--- dimension rows whose product_id maps to 1
existing event Bucket 2  <--- dimension rows whose product_id maps to 2
existing event Bucket 3  <--- dimension rows whose product_id maps to 3
```

Compared with general Partition Shuffle, only one input needs redistribution.
That reduction is available only when the retained side's Bucket column and
the Join Key satisfy the strategy, and when the Join direction, type, Bucket
mapping, and data placement are usable.

“Both tables use Hash distribution somewhere” is insufficient evidence. Check:

- whether the Join equality includes the relevant Bucket column;
- which physical input layout the optimized plan retains;
- the number and mapping of Buckets;
- the Join type and chosen physical orientation;
- the actual `EXPLAIN` distribution label.

In Lab 6, `dim_products` is Hash bucketed by `product_id`. The SQL-text left
table `events_modelled` is bucketed by `user_id`, so the textual order alone
does not prove a reusable layout. The optimizer can choose a physical
orientation. In the tested Doris 4.1.3 plan, the accepted `[shuffle]` comparison
reports `hashJoin[INNER_JOIN shuffleBucket]`, which is the evidence that Bucket
Shuffle was selected for that plan.

Do not generalize this one plan into a permanent rule. Statistics, predicates,
schema layout, and optimizer changes can produce another plan. See
[Adjusting Join Shuffle Mode](https://doris.apache.org/docs/4.x/query-acceleration/tuning/tuning-plan/adjusting-join-shuffle/).

## 6.8 Use Colocate for a Stable, Repeated Join Relationship

Colocate Join addresses a stronger and more durable requirement. Two tables
that repeatedly perform a large-to-large Join on the same stable Key can be
placed in one Colocation Group. Compatible Buckets are stored together so each
local execution location already has the matching rows.

```text
BE 1: orders Bucket 0 + customers Bucket 0  --> local Join
BE 2: orders Bucket 1 + customers Bucket 1  --> local Join
BE 3: orders Bucket 2 + customers Bucket 2  --> local Join
```

The tables must satisfy the current colocation contract, including compatible
distribution columns and types, Bucket count, replica allocation, and group
membership. The group must be stable so matching Bucket replicas are actually
colocated. Rebalancing or an unstable group means you should not assume local
execution merely because the table property exists.

Colocate is a physical data-design commitment for a recurring workload. It is
not a universal hint for one query. The stricter layout can reduce repeated
Join movement, but it also constrains table design and placement operations.

Lab 6 does not create a Colocation Group. A single BE would make every Tablet
local and would not demonstrate the multi-node placement benefit. The course
scenario establishes when to consider Colocate; a production decision requires
the table definitions, group stability, plan, workload frequency, and runtime
evidence.

### Compare the four strategies

| Strategy | Input kept in place | Input moved | Required starting layout |
| --- | --- | --- | --- |
| Broadcast | Probe/physical left input | Complete build/physical right input is copied to participants | Build input small enough to replicate; supported Join type |
| Partition Shuffle | Neither input necessarily | Both inputs repartition by Join Key | Equi-Join Key; no reusable layout required |
| Bucket Shuffle | One compatible bucketed input | The other input routes to retained Buckets | Join condition and one Bucket layout satisfy strategy requirements |
| Colocate | Both compatible inputs | Join data can remain local | Stable shared colocation contract and matching Bucket placement |

These names describe where matching data meets. They do not change the logical
meaning of Inner, Outer, Semi, or Anti Join.

## 6.9 Reduce Probe Candidates with a Runtime Filter

Suppose an analyst needs the number of events for products in `category_1`
during one day. The event input is large, but the category predicate leaves
only a subset of product Keys on the dimension side:

```sql
SELECT COUNT(*)
FROM events_modelled AS e
INNER JOIN dim_products AS d
  ON e.product_id = d.product_id
WHERE d.category = 'category_1'
  AND e.event_time >= '2020-03-01 00:00:00'
  AND e.event_time <  '2020-03-02 00:00:00';
```

The static event Scan does not know which `product_id` values survive the
dimension predicate. Doris learns those values while building the Join. It can
then create a Join Runtime Filter from the surviving build-side Keys and apply
that filter to the probe-side Scan. Event rows whose product Keys cannot match
do not need to continue to the Hash Join.

This pattern is useful when:

- the probe input contains many rows;
- predicates on the build side leave a substantially smaller set of Join Keys;
- the filter becomes ready early enough to reach the probe Scan; and
- reducing candidates saves enough Scan, Exchange, or probe work to repay the
  cost of building, merging, publishing, and applying the filter.

It may help little when the probe input is already small, the build side covers
most probe Keys, or the filter arrives after much of the Scan has progressed.
An approximate Bloom Filter can also allow some nonmatching candidates through.
Doris can prune a Runtime Filter that statistics indicate will not be selective.

A Runtime Filter does not change which rows satisfy the Join. It only rejects
candidates that cannot contribute to the result. It is also separate from Join
distribution: Broadcast, Partition Shuffle, Bucket Shuffle, or Colocate decides
where matching inputs meet, while a Runtime Filter tries to reduce the rows
that reach those later operators. The same plan may therefore contain both a
Broadcast Join and a Runtime Filter.

### Follow the build Keys to the probe Scan

For a Hash Join, Doris can derive a Runtime Filter from build-side Join values
and apply it to the probe-side Scan when Join semantics allow:

```text
filtered product Keys {10, 20}
          |
          | build Join and produce Runtime Filter
          v
event Scan keeps product_id 10 and 20 candidates
and rejects product_id 30, 40, ... candidates
          |
          v
fewer candidate rows reach the Hash Join
```

The plan can show an identifier such as `RF000`, `RF0`, or another generated
label. That label identifies a planned or profiled filter; it is not a table,
Partition, Bucket, or fixed business object. Identifier numbering may change
with the plan.

Runtime Filter type affects interpretation. An exact In Filter can reject Keys
outside its set. A Bloom Filter is approximate: hash collisions can let a
nonmatching candidate pass. Doris can also use a Min-Max Runtime Filter where
its range bound is useful. The final Join condition is still required.

## 6.10 Read Plan Evidence Separately from Runtime Effect

The Frontend (FE) creates and optimizes a distributed query plan and assigns
plan fragments. BE nodes execute the assigned plan fragments. Use the artifact
that answers the question you are asking.

| Question | Evidence |
| --- | --- |
| Which Join type and condition are planned? | `EXPLAIN` or `EXPLAIN SHAPE PLAN` |
| Which distribution and Exchange shape are planned? | `EXPLAIN` plan tree |
| Where is a Runtime Filter produced and consumed? | `build RFs` and `apply RFs` in the plan |
| How many rows reached the executed Join? | Hash Join counters in Query Profile |
| How many rows did a specific Runtime Filter reject? | Matching `RF... InputRows` and `RF... FilterRows` Profile counters |
| How much time and network work occurred? | Relevant operator and Exchange counters in Query Profile |

Seeing `apply RFs` in `EXPLAIN` proves only that the plan arranged a consumer.
It does not prove that the filter arrived early, rejected rows, or avoided
storage reads. Execute the query and inspect its Profile.

### Read the Lab Profile without overstating it

The Lab helper prints a cropped raw MergedProfile excerpt. For each Runtime
Filter on the `events_modelled` Scan:

- `RF... InputRows` counts rows presented to that filter.
- `RF... FilterRows` counts rows that filter rejected.
- `RowsProduced` counts rows the Scan passed onward.
- Hash Join `ProbeRows` counts rows that reached the Join's probe path.
- `ScanRows` counts rows scanned by the Scan operator.

In one tested run, a filter rejected 61,934 of 75,259 input rows, another filter
rejected zero, and both Scan `RowsProduced` and Join `ProbeRows` were 13,325.
This is direct evidence that candidates were removed before the Join operator
in that execution.

It is not evidence that 61,934 rows were never read from storage: `ScanRows`
was still 75,259. Runtime Filter identifiers, arrival timing, execution
instances, and counts can change across runs or environments. Interpret the
Profile currently displayed rather than treating those sample values as a
stable contract. See [Runtime Filter](https://doris.apache.org/docs/4.x/query-acceleration/optimization-technology-principle/runtime-filter/).

### Use hints as controlled comparisons

Doris normally uses statistics, predicates, Join semantics, and layouts to
choose order and distribution. A `[broadcast]` or `[shuffle]` hint asks the
optimizer to consider a specified distribution for a comparison or diagnosed
tuning need. It does not improve a query merely by being explicit.

Use a hint only after you have:

1. inspected the current plan;
2. identified a concrete plan or runtime problem;
3. measured the relevant filtered input sizes and operator behavior;
4. compared the hinted plan under representative data and concurrency;
5. considered how data growth can invalidate the choice.

Lab 6 uses `[shuffle]` to obtain a plan contrast and checks the Hint log. It
does not turn that hint into the recommended production form.

## Lab 6: Joining Data in Apache Doris

Open [Lab 6 — Joining Data in Apache Doris](lab06_join_data.ipynb) after Modules
4 and 5, and plan about 30 minutes. The Notebook reads the persistent
`events_modelled` table and creates three Module 6 tables:

- `dim_products`, a deterministic 204,231-row product dimension generated from
  local product identifiers;
- `join_event_cases`, a four-row event fixture;
- `join_product_cases`, a five-row fixture containing a duplicate Key and a
  `NULL` Key.

It performs no external download and does not read Amazon S3.

| Lab step | What you do | What the result establishes |
| --- | --- | --- |
| 1 | Build the controlled product relationship | One dimension row per product supports event enrichment, while deliberate unmatched Keys make both missing directions visible |
| 2 | Run Inner, Left Outer, Left Semi, and Left Anti Join | Join type follows the rows and columns the answer must retain |
| 3 | Aggregate purchase revenue by category and region | A many-events-to-one-product relationship preserves one matched row per event before aggregation |
| 4 | Join one event to duplicate product-version Keys | A Join emits every matching pair and can repeat a measure |
| 5 | Compare `=` with `<=>` for a `NULL` event Key | Ordinary equality creates no NULL-to-NULL pair; NULL-safe equality creates one under the fixture contract |
| 6 | Compare equi and pure non-equi plans | The equi-condition uses Hash Join and the pure range condition uses Nested Loop Join in the tested plan |
| 7 | Compare distribution plans and inspect a Query Profile | The default plan uses Broadcast, the accepted comparison reports Bucket Shuffle, and Profile counters show actual probe-side filtering |

The Lab executes only bounded logical cases. Right, Full, Cross, NULL-aware
Anti, ASOF, general Partition Shuffle routing, and Colocate are explained in
the course because running each one over the large table would add repetition
without improving the intended evidence.

Read Lab 6 results at three levels:

1. Query result rows establish logical Join semantics.
2. `EXPLAIN SHAPE PLAN` establishes the selected physical plan without
   executing it.
3. Query Profile counters establish what happened in one execution.

Do not use single-BE elapsed time to rank multi-node distribution strategies.
Preserve `events_modelled` for the analytical flow; Module 6 owns and may
rebuild only its dimension and controlled Join tables.

The Lab ends with a practice: predict the rows of an Outer Join when a condition
moves from `ON` to `WHERE`. Predict the result first, then write the code in the
empty cell; the collapsed reference solution after it also runs with Run All and
leaves the Lab's tables as they were.

## Summary

- A Join returns one row for every matching pair: a key that repeats on both
  sides multiplies rows and their measures, so state both grains and the key's
  cardinality before you trust a total.
- The Join type follows the rows the answer must keep: matched pairs (Inner),
  every row of one side (Outer), rows that have or lack a match (Semi, Anti),
  every combination (Cross), or the closest earlier state (ASOF).
- `=` never matches `NULL` keys and `<=>` matches them as one group; a
  right-side condition in `ON` limits which rows match, while the same
  condition in `WHERE` removes the unmatched rows that the Outer Join kept.
- An equality key lets Doris build a hash table from one input and probe it
  with the other; a pure non-equi condition needs a Nested Loop Join; the
  optimizer, not the SQL text, assigns the build and probe sides.
- Broadcast copies a small build input to every participant, Partition
  Shuffle routes both inputs by the Join key, Bucket Shuffle keeps one
  compatible bucketed input in place and routes the other, and Colocate stores
  both inputs with matching Buckets in advance.
- `EXPLAIN` shows the planned Join, its distribution, and the Runtime Filters
  it builds and applies; only the Query Profile shows how many rows a filter
  removed in one execution, and a hint is a tool for a controlled comparison.

## Quiz 6: Joining Data in Apache Doris

Open [Quiz 6: Joining Data in Apache Doris](quiz06_join_semantics_and_execution.ipynb).
It has six single-choice questions and needs no running environment.

Next module: [Module 7: Updating and Deleting Data in Apache Doris](../module07-updating-deleting/course.md).

## References

- Logical and physical Join behavior: [Doris Joins](https://doris.apache.org/docs/4.x/query-data/join/) and [SELECT Join syntax](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-query/SELECT/).
- Point-in-time matching: [ASOF Join](https://doris.apache.org/docs/4.x/query-data/asof-join/).
- Plan and distribution control: [EXPLAIN](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-query/EXPLAIN/) and [Adjusting Join Shuffle Mode](https://doris.apache.org/docs/4.x/query-acceleration/tuning/tuning-plan/adjusting-join-shuffle/).
- Runtime evidence: [Runtime Filter](https://doris.apache.org/docs/4.x/query-acceleration/optimization-technology-principle/runtime-filter/).
- Doris 4.1.3 implementation terminology: [`HashJoinNode.java`](https://github.com/apache/doris/blob/4.1.3/fe/fe-core/src/main/java/org/apache/doris/planner/HashJoinNode.java) defines `BROADCAST`, `PARTITIONED`, and `BUCKET_SHUFFLE` distribution modes and the Colocate plan label; [`RuntimeFilter.java`](https://github.com/apache/doris/blob/4.1.3/fe/fe-core/src/main/java/org/apache/doris/planner/RuntimeFilter.java) contains the Runtime Filter type and plan metadata used by the FE planner.
