# Module 7: Updating and Deleting Data in Apache Doris

| Course information | Value |
| --- | --- |
| Course | Real-time Analytics with Apache Doris — Level 2 |
| Product baseline | Apache Doris 4.x |
| Lab version | Apache Doris 4.1.3 |
| Estimated time | Approximately 65 minutes, including the guided lab |

## Module goal

This module explains how to maintain current state and remove data with an
operation that matches the change. You will distinguish complete replacement
rows from partial changes, order incoming states, and choose between deleting
selected rows and replacing an entire reporting scope.

Earlier modules preserved and analyzed event history. This module uses separate
tables in the `doris_course` Database: `order_state`, `order_deletions`, and
`order_lifecycle`. The persistent `events` baseline, `events_modelled`, and
`dim_products` remain available for analytical work.

## Learning objectives

After completing this module, you will be able to:

1. Define a current-state grain and choose a Unique Key table for incoming
   states identified by a business key.
2. Use a Sequence column to distinguish source ordering from arrival order.
3. Explain how full-row upserts and partial column updates treat omitted
   columns, and distinguish omission from an explicit value.
4. Choose SQL `UPDATE` for a predicate-based correction and recognize its
   model and Key-column restrictions.
5. Select predicate `DELETE` or load-based Delete Sign from how deleted rows
   are identified.
6. Choose `TRUNCATE` or atomic overwrite for whole-table or whole-Partition
   maintenance, with an explicit replacement scope.
7. Distinguish visible rows, hidden delete markers, Tablet metadata, and
   documented Merge-on-Write storage behavior.

## Module structure

| Section | Format | Time | Outcome |
| --- | --- | ---: | --- |
| 7.1 Define the State You Want to Keep | Contract walkthrough | 4 min | Separate current state from event history |
| 7.2 Let Source Order Decide Which State Wins | Timeline walkthrough | 6 min | Interpret upsert and Sequence behavior |
| 7.3 Decide What an Omitted Column Means | Write comparison | 7 min | Choose full-row or partial column semantics |
| 7.4 Correct Selected Rows with SQL UPDATE | Operation walkthrough | 4 min | Apply predicate corrections within their boundaries |
| 7.5 Choose How to Identify Deleted Rows | Delete comparison | 6 min | Distinguish predicates and incoming delete keys |
| 7.6 Match Replacement Scope to Data Lifecycle | Partition walkthrough | 7 min | Separate clearing, patching, and atomic replacement |
| 7.7 Explain Visibility Without Assuming Physical Cleanup | Evidence walkthrough | 6 min | Interpret query and storage observations accurately |
| Lab 7 | Hands-on | 25 min | Maintain controlled order states and compare deletion paths |

---

## 7.1 Define the State You Want to Keep

An event-history table answers “What happened?” A current-state table answers
“What is true for this entity now?” An order that progresses from `created` to
`paid` to `shipped` can therefore contribute three history records but only one
current row.

In `order_state`, `order_id` identifies the business entity. The other columns
describe its current customer, status, amount, shipping region, and update time.
A Unique Key model keeps one visible state per key; Merge-on-Write (MoW) is
the default implementation in Doris 4.x. See [Unique Key Model](https://doris.apache.org/docs/4.x/table-design/data-model/unique/).

This choice does not create an audit log. A query over the current table cannot
reconstruct every earlier order status merely because Doris may still retain
some older storage versions. Keep history separately when the business needs
transitions, historical attributes, or replay.

Before choosing a command, describe the incoming change:

| Question | Why it matters |
| --- | --- |
| Which business key identifies the entity? | Determines which state can be replaced |
| Does the producer send a complete row or selected columns? | Determines what omitted fields mean |
| Which source value orders changes? | Prevents an older state from winning through late arrival |
| Are rows selected by an incoming key or a SQL predicate? | Distinguishes load-based changes from conditional corrections |
| Does the operation affect some rows or a complete Partition? | Determines whether row maintenance or scope replacement fits |

The lab uses small tables to make each answer visible. The same decisions
apply when a production pipeline batches many changes.

## 7.2 Let Source Order Decide Which State Wins

An **upsert** combines insert and update semantics. A new key creates a logical
row; a write for an existing key can replace that row's state. `INSERT INTO`
and ingestion methods such as Stream Load can supply those states to a Unique
Key table. The producer does not need a separate lookup followed by an
application-side decision to insert or update. See [Load-Based Updates](https://doris.apache.org/docs/4.x/data-operate/update/update-of-unique-model/).

Uniqueness alone does not define business recency. Network delays and parallel
loaders can make an older change arrive after a newer one. The lab maps the
Sequence column to `updated_at` through
`"function_column.sequence_col" = "updated_at"`.

For writes sharing the same Key, a larger Sequence value wins over a smaller
one. The lab's order `1001` illustrates why arrival and source order differ:

| Arrival | Incoming status | Source `updated_at` | Visible status afterward |
| --- | --- | --- | --- |
| Initial row | `created` | 09:00 | `created` |
| Newer state | `shipped` | 10:10 | `shipped` |
| Delayed older state | `paid` | 10:05 | `shipped` |

The delayed row can be accepted by the loading operation without becoming the
visible winner. A successful write response alone therefore does not prove
that a particular incoming value is now current. Query the selected key when
verifying the state transition.

### Choose a source ordering contract

Use a source revision or update time that orders changes for the same entity.
Do not replace it with the loader's receipt time: that would make a delayed
old event appear new. A timestamp also needs sufficient precision and
consistent source clocks. Equal timestamps do not express which of two
conflicting business states is newer; resolve that ambiguity in the source
contract rather than assuming it is covered by the lab's larger-value example.

A Sequence column is separate from a load Label. Module 3 used Labels for
transaction identity and retry handling. Sequence values choose among states
for one key across writes. Neither mechanism replaces the other. See
[Sequence Column and Update Ordering](https://doris.apache.org/docs/4.x/data-operate/update/unique-update-concurrent-control/).

The lab demonstrates a delayed lower Sequence value, not arbitrary concurrent
producers or conflicting equal values. Its separate `order_deletions` table
has an `updated_at` field but does not configure it as a Sequence column. A
column's name alone does not enable ordering.

## 7.3 Decide What an Omitted Column Means

A column list tells Doris which values the statement supplies. It does not,
by itself, request partial-update semantics.

Under the default full-row upsert behavior, unspecified value columns are
filled according to the schema, rather than copied from the old row. Under
partial column update, omitted values are retained from an existing matching
row. Lab 7 contrasts these meanings using two orders:

| Write | Supplied changes | Effect on omitted values |
| --- | --- | --- |
| Full-row upsert for `1002` | Customer, status, and update time | Amount becomes its default `0.00`; region becomes `UNASSIGNED` |
| Partial column update for `1003` | Status and update time | Amount remains `88.00`; region remains `CN-WEST` |

These are different operations even though both change a status to `shipped`.
Select full-row upsert when the producer owns the complete state. Select
partial column update when it owns only selected fields and intends to preserve
the rest.

For the lab's `INSERT INTO` statements, the switch is the session variable
`enable_unique_key_partial_update`. The Notebook enables it for the partial
write and restores `false` afterward. Load paths such as Stream Load use their
corresponding partial-column settings. All Key columns must be supplied.
See [Column Update](https://doris.apache.org/docs/4.x/data-operate/update/partial-column-update/).

### Separate omission, NULL, and a default

For a nullable value column in another current-state model, these instructions
would have different meanings:

| Producer intent | Required representation |
| --- | --- |
| Leave the value unchanged | Omit it from an enabled partial column update |
| Clear it to unknown | Supply an explicit `NULL`, if the schema allows it |
| Replace it with a known value | Supply that value |

An explicit `NULL` is not an instruction to retain an existing value. Nor does
declaring a default mean that every explicit `NULL` is replaced with that
default. The schema's nullability and the chosen ingestion behavior still apply.
The lab's order columns are non-nullable, so it demonstrates omission rather
than clearing a nullable field.

### Handle new keys separately from existing keys

For a new key there is no previous row from which to preserve omitted values.
Doris 4.1.3 exposes `partial_update_new_key_behavior`: `ERROR` requires existing
keys, while `APPEND` permits new ones. In the latter case, omitted fields need
defaults or permitted `NULL` values; a required field without either cannot be
recovered from a nonexistent row.

For example, `order_state.customer_id` is required and has no default. The lab
can omit it when partially updating existing order `1003`, because the old row
supplies it. That does not establish a valid way to create a brand-new order
using only an ID and status.

The lab uses a fixed set of updated columns per statement. Doris also has a
flexible column-update mode for supported load paths, but that is a separate
configuration and is not enabled here. Do not infer that the session switch
used in this lab enables every form of partial ingestion.

Partial updates reduce what the producer must send. In MoW, Doris still needs
to fill missing values from existing data when constructing the replacement
row. They are not a promise of zero reads or an in-place edit to a Segment.

## 7.4 Correct Selected Rows with SQL UPDATE

Use SQL `UPDATE` when a condition describes a correction: for example, change
the shipping region of a selected order while retaining its other values.
`WHERE` selects the rows and `SET` names the changed columns.

The lab corrects `order_state` for `order_id = 1001`, changing `CN-EAST` to
`CN-NORTH`. Its status, amount, and `updated_at` remain unchanged. This last
detail matters: Doris does not automatically turn a timestamp named
`updated_at` into the time of every SQL correction.

If the same table also receives a Change Data Capture (CDC) stream, decide how
manual corrections relate to the authoritative source. A later qualifying
full state from that source can overwrite a correction. Updating a local
field is not a policy for reconciling two writers.

SQL `UPDATE` supports Unique Key target tables and changes value columns, not
Key columns. Changing `order_id` changes the entity's identity and requires a
workflow that removes the old key and writes the new one. Those two actions
need an explicit consistency plan; they are not an ordinary single-column
update. See [UPDATE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-modification/DML/UPDATE/).

### Match the selection method to the workload

| Incoming requirement | Suitable starting point |
| --- | --- |
| Many complete states already identified by key | Batched load-based full-row upserts |
| Many key-based changes to selected fields | Partial column updates |
| An occasional correction selected through SQL | `UPDATE` |

Doris must identify the rows for a predicate correction and write replacement
versions. A tight loop of individual `UPDATE` statements repeats that work
and transaction overhead. Grouping source changes into appropriate batches
also reduces the number of tiny writes the storage system must maintain.

Batching is a throughput and freshness tradeoff: larger batches amortize work
but delay when an individual source change becomes visible. Choose it from
the latency requirement and observed workload rather than a universal batch
size. The lab does not measure that tradeoff.

## 7.5 Choose How to Identify Deleted Rows

Two requirements can remove the same logical row while starting from different
information. A SQL predicate says which currently stored rows should disappear.
A CDC record or deletion file already supplies the keys that were deleted at
the source.

### Use a predicate when the condition defines the target

Predicate `DELETE` is available for Duplicate Key, Unique Key, and Aggregate
Key tables, with model-specific restrictions. Aggregate Key tables restrict
delete conditions to Key columns; do not assume that a predicate on an
aggregated measure is supported. Non-Unique tables also have a more restricted
predicate syntax than general analytical `SELECT`. See [Delete Operation](https://doris.apache.org/docs/4.x/data-operate/delete/delete-manual/).

Lab 7 removes test order `2003` from the Unique Key table `order_deletions`
using a key predicate. A predicate can also express a business condition, but
its selection must match the intended meaning. For example, deleting a
cancelled order removes it from a current-state report; retaining it with
status `cancelled` keeps cancellation part of the report. Decide whether the
entity should be absent before choosing deletion.

### Use Delete Sign when deleted keys arrive as data

Unique Key tables have the hidden column `__DORIS_DELETE_SIGN__`. A value of
`1` represents a delete marker for the key. Lab 7 supplies that marker for
order `2002` through a small `INSERT INTO` example. In a pipeline, the load
method or connector carries the corresponding deletion information in batches.
See [Load-Based Batch Delete](https://doris.apache.org/docs/4.x/data-operate/delete/batch-delete-manual/).

The ordinary query then excludes the deleted key. You do not need to turn a
large incoming list of deleted IDs into thousands of separate SQL statements.
The marker shares the ingestion workflow with other key-based changes.

Deletion is also an ordered change in a CDC system. When the target uses a
Sequence column, deletes and live states need a consistent source-ordering
contract. The lab's non-sequenced deletion table does not test late updates
against a newer delete, and a delete marker is not an indefinite ban on
reinserting a key. Design replay and source retention accordingly.

### Do not confuse the marker with the delete bitmap

Delete Sign is a row-level hidden column supplied or generated through a write
path. The internal **delete bitmap** identifies superseded physical row
versions for MoW reads. They serve related but different purposes: one
represents a deleted state for a key; the other helps exclude obsolete row
versions. Displaying Delete Sign does not display the bitmap.

The lab temporarily enables `show_hidden_columns` for inspection and restores
it afterward. Deleted records may contain default values rather than their
previous business attributes. Hidden rows are not a recovery interface or a
historical record of the original state, and markers may disappear after
background cleanup.

## 7.6 Match Replacement Scope to Data Lifecycle

Row-level predicates are useful when only some rows should change. A complete
Partition has a different contract: remove all of its contents, or replace
those contents with a corrected dataset.

| Requirement | Operation | Intended contents afterward |
| --- | --- | --- |
| Remove selected rows | Predicate `DELETE` | Rows outside the predicate remain |
| Empty a table or named Partitions | `TRUNCATE TABLE` with the appropriate scope | The selected scope is empty; its definition remains |
| Rebuild a table or named Partitions | `INSERT OVERWRITE` | The selected scope contains the replacement dataset |
| Prepare and inspect a replacement before a separate swap | Temporary Partition workflow | Validated staged data replaces the selected formal scope |

### Clear a complete scope with TRUNCATE

The lab's command `TRUNCATE TABLE order_lifecycle PARTITION(p20260910)` clears
one named Partition. Omitting the Partition clause would instead select the
whole table. `TRUNCATE` has no row-level `WHERE` condition.

The operation retains the table and Partition definition while replacing its
data-bearing storage structures. It avoids representing the cleanup as an
individual logical deletion for every old row. This behavior is documented in
[Truncate Operation](https://doris.apache.org/docs/4.x/data-operate/delete/truncate-manual/)
and implemented by Partition replacement in the release's
[InternalCatalog](https://github.com/apache/doris/blob/4.1.3/fe/fe-core/src/main/java/org/apache/doris/datasource/InternalCatalog.java).

Use the actual Partition range to identify the scope. In the lab,
`p20260910 VALUES LESS THAN ('2026-09-11')` is the first Range Partition, so
it also permits earlier dates. Its name does not impose a lower bound. The
controlled data happens to contain only September 10 rows there.

### Replace complete contents with INSERT OVERWRITE

`INSERT OVERWRITE` is replacement of the selected scope, not a patch for the
keys that happen to appear in the input. The lab replaces `p20260911` with
orders `3003` and `3005`. Old order `3004` disappears because it is absent from
the replacement, even though no delete predicate names it.

For a Partition overwrite, Doris prepares replacement data and atomically
replaces the target Partition. Readers need not pass through an intentionally
empty state between separate clearing and loading commands. This is the
documented behavior; the lab shows the before/after contents rather than
running a concurrent reader to observe the switch. See [INSERT OVERWRITE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-modification/DML/INSERT-OVERWRITE/).

Atomic replacement does not establish that the replacement is complete or
correct. An accidentally narrow source filter can successfully replace a
Partition with an incomplete result. Verify the target range, source coverage,
grain, and required totals before using the replacement as the published
dataset. Coordinate overlapping source writes so the replacement includes the
intended cutoff of changes.

A [Temporary Partition](https://doris.apache.org/docs/4.x/data-operate/delete/table-temp-partition/)
provides a separate staging scope when loading, checking, and publishing must
be distinct steps. It is an extension beyond the lab's single overwrite
statement. Recovery also needs an explicit source or retention plan: clearing
data, replacing a scope, and retaining a backup are different operations. The
lab does not perform recovery or establish a general undo guarantee.

## 7.7 Explain Visibility Without Assuming Physical Cleanup

Module 2 introduced immutable Segments and Rowsets within Tablets. An update
does not require rewriting a value inside an existing Segment file. In MoW,
Doris writes new versions and tracks which older versions should no longer
participate in a current read. Affected Tablets maintain their own Rowsets;
one transaction does not create a single global Rowset for the table.

Once the write is successfully published and visible, a subsequent ordinary
query sees the winning live state or the absence of a deleted key. It does not
need to wait for Compaction to establish that logical result. Compaction later
consolidates storage and can remove obsolete versions and delete records.
See [Merge-on-Write](https://doris.apache.org/docs/4.x/table-design/data-model/merge-on-write/).

Visibility is relative to the query snapshot. A query already running can
continue using its earlier snapshot; a later statement can see newly published
changes. This follows the statement-level visibility discussed in Module 5,
not a requirement to restart the client or manually merge data. See
[Transactions](https://doris.apache.org/docs/4.x/data-operate/transaction/).

### Read each observation at the level it measures

| Observation in Lab 7 | What it establishes | What it does not establish |
| --- | --- | --- |
| Ordinary rows before and after deletion | Which order keys and values the query can see | Which old Segment bytes remain |
| `COUNT(*) OVER()` in the result | Number of visible rows in that result | Number of physical row versions |
| A later Tablet `Version` | A later storage version has been published | How many rows were deleted or how much disk was reclaimed |
| Tablet `VersionCount` | Reported retained version count at inspection time | A fixed count of business updates |
| Tablet `RowCount` | Reported storage metadata | An exact substitute for ordinary `COUNT(*)` |
| Hidden `__DORIS_DELETE_SIGN__` | A retained record's delete marker | The delete bitmap or the original deleted business row |

Background Compaction can change retained-version counts between inspections.
Do not infer a Compaction duration or bytes reclaimed from the lab's two
Tablet snapshots. A delete marker visible immediately after the exercise may
no longer be available in a later inspection; that does not make the earlier
logical deletion unsuccessful.

This distinction also explains the workload guidance. Many tiny transactions
can increase version and Rowset maintenance work. Batching changes and choosing
whole-scope operations for lifecycle tasks address different sources of work.
Their performance effects require measurements; the lab demonstrates behavior,
not comparative throughput or physical cleanup timing.

---

## Lab 7: Maintain Current State and Remove Data Safely

Open [Lab 7 — Maintain Current State and Remove Data Safely](lab7_update_delete_data.ipynb).
Its five main sections use controlled starting states:

| Lab section | Table | Result to explain |
| --- | --- | --- |
| 1. Current state and upserts | `order_state` | A newer state wins; a delayed older state does not replace it; a new key is inserted |
| 2. Omitted columns | `order_state` | Full-row defaults differ from partial-update preservation |
| 3. SQL correction | `order_state` | Only the selected order's shipping region changes |
| 4. Deletion and inspection | `order_deletions` | Predicate deletion and an incoming Delete Sign leave only order `2001` visible |
| 5. Partition lifecycle | `order_lifecycle` | The expired scope is cleared; the active scope is replaced with `3003` and `3005` |

Sections 2 and 3 reset `order_state` before their own comparisons. Consequently,
the four logical orders after Section 1 are not the table's final lab count.
The two orders restored in Section 3 remain for the optional restart check.
Run the setup before dependent sections and read each result against that
section's starting state.

The lab provides executable SQL. Use this course to explain why each command
fits its change contract, rather than treating every example as an interchangeable
way to modify a row. New-key partial-update policies, nullable-field clearing,
equal-Sequence conflicts, concurrent reader behavior, temporary Partition
replacement, and recovery are not executed cases in the Notebook.

## Module summary

Current-state maintenance starts with a key, a source-ordering rule, and a
definition of omitted values. Complete states fit full-row upsert; selected
fields fit partial column update; occasional SQL corrections fit `UPDATE`.
Choose predicates or Delete Sign from how deleted rows are identified, and
use scope-level clearing or replacement when the whole Partition is the unit
of change.

Across Level 2, the same principle connects modeling, analysis, joining, and
maintenance: define what a row represents and what the operation must preserve.
Logical results tell you whether that contract holds; storage and runtime
evidence answer separate questions about how Doris carries it out.

## Official references

- Model and storage: [Unique Key Model](https://doris.apache.org/docs/4.x/table-design/data-model/unique/) and [Merge-on-Write](https://doris.apache.org/docs/4.x/table-design/data-model/merge-on-write/).
- Update paths: [Load-Based Updates](https://doris.apache.org/docs/4.x/data-operate/update/update-of-unique-model/), [Column Update](https://doris.apache.org/docs/4.x/data-operate/update/partial-column-update/), [Sequence Column](https://doris.apache.org/docs/4.x/data-operate/update/unique-update-concurrent-control/), and [UPDATE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-modification/DML/UPDATE/).
- Deletion: [Delete Operation](https://doris.apache.org/docs/4.x/data-operate/delete/delete-manual/) and [Load-Based Batch Delete](https://doris.apache.org/docs/4.x/data-operate/delete/batch-delete-manual/).
- Lifecycle: [Truncate Operation](https://doris.apache.org/docs/4.x/data-operate/delete/truncate-manual/), [INSERT OVERWRITE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-modification/DML/INSERT-OVERWRITE/), and [Temporary Partition](https://doris.apache.org/docs/4.x/data-operate/delete/table-temp-partition/).
- Release implementation: [Apache Doris 4.1.3 InternalCatalog.java](https://github.com/apache/doris/blob/4.1.3/fe/fe-core/src/main/java/org/apache/doris/datasource/InternalCatalog.java), including `truncateTable` and `truncateTableInternal`.
