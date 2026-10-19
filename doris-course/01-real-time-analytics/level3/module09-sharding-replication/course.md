# Module 9: Sharding, Replication, and Distributed Execution in Apache Doris

| Course information | Value |
| --- | --- |
| Course | Real-time Analytics with Apache Doris — Level 3 |
| Product baseline | Apache Doris 4.x |
| Lab version | Apache Doris 4.1.3 |
| Estimated time | Approximately 100 minutes, including the guided lab |

## Module goal

An ecommerce event service has outgrown the single-FE, single-BE teaching
topology used earlier in the course. New client sessions must be able to avoid
one failed FE, operators need to add BE capacity without changing the table's
logical shards, writes must continue through a supported replica failure, and
a recurring event–user report should avoid unnecessary network movement.

This module follows that service as its topology and workload change. You will
separate three different problems:

- giving clients a healthy FE query entry point;
- placing and recovering Tablet replicas across BEs; and
- moving intermediate rows only where a distributed query requires it.

The module begins with FE election and client reconnection, expands a two-BE
replica layout onto a third BE, follows one query from logical Tablets to actual
BE scan tasks, and observes replica versions during a controlled BE outage. It
then compares Bucket Shuffle and Colocate for the same event–user Join.

Module 8 reduced work inside a query by selecting a materialized result or a
secondary index. Module 9 asks where the selected data lives, which copy Doris
reads, where each plan fragment runs, and which rows must move between nodes.

## Learning objectives

After completing this module, you will be able to:

1. Distinguish FE metadata availability, client-side query-entry availability,
   BE data availability, and distributed query execution.
2. Explain the relationship among a Partition, Bucket, logical Tablet, physical
   replica, and BE placement.
3. Predict when every BE must contain every Tablet and when different BEs can
   hold different Tablet subsets.
4. Explain why adding a BE can rebalance existing replicas without changing
   the table's Partition or Bucket count.
5. Trace a query from Partition pruning through Tablet-replica selection,
   Fragment Instances, PipelineTasks, Exchanges, and the final result.
6. Distinguish stored replica placement from the replicas actually selected for
   one query execution.
7. Apply the default majority-write rule and interpret relative replica
   versions during outage and recovery.
8. Explain how Bucket Shuffle routes one input to an existing `user_id` Bucket
   layout and how a stable Colocation Group can avoid that Join input movement.
9. Bound conclusions from a multi-container lab that still shares one physical
   Docker host.

## Follow One Growing Distributed Service

The team does not add every distributed feature at once. Each operational
change exposes the next decision:

```text
identify the client, FE, BE, and proxy responsibilities
    -> lose the directly connected FE and establish a new healthy session
    -> add a third BE and observe existing replica placement rebalance
    -> trace one SQL statement to the BE replicas that actually scan
    -> keep writing during one supported BE outage and wait for version recovery
    -> compare Bucket Shuffle and Colocate on the restored stable layout
    -> state what the shared-host experiment does and does not establish
    -> separate online replica health from long-term data lifecycle
```

The same event service connects these stages. FE election protects metadata
service, a proxy or driver gives new client sessions a healthy FE target,
Tablet replicas protect online data, and Fragments and Exchanges distribute
query work. These mechanisms cooperate, but none substitutes for the others.

| Section | Requirement scenario | Decision developed | Lab 9 evidence |
| --- | --- | --- | --- |
| **9.1 Identify each distributed role** | A single-node sandbox cannot expose election, replica placement, or cross-BE work. | Separate client, FE, BE, and proxy responsibilities. | Start three FEs with exactly two live BEs in an isolated cluster. |
| **9.2 Separate FE election from client routing** | A connected FE stops while other FEs remain healthy. | Use FE quorum for metadata availability and a client/proxy mechanism for new connections. | The direct session fails; HAProxy establishes replacement sessions only to healthy FEs. |
| **9.3 Expand replica placement** | Two BEs need capacity from a third BE. | Add a placement target and observe automatic replica balancing without changing logical shards. | Existing event replicas move onto the new BE while logical rows and total replica count remain constant. |
| **9.4 Trace distributed scan work** | Several BEs store eligible replicas, but the team needs to know which ones execute a query. | Follow Tablet selection, Fragment Instances, and PipelineTasks through plan and Profile evidence. | A regional aggregation displays planned Tablet scope and actual BE scan tasks. |
| **9.5 Recover a lagging replica** | One BE is unavailable while a write arrives. | Use a replica count that can form a majority, then distinguish heartbeat recovery from version recovery. | Two replicas commit a business event; the returning replica catches up to the current version. |
| **9.6 Compare Join data movement** | The same event–user relationship is joined repeatedly after the layout is stable. | First preserve the event layout with Bucket Shuffle; then pre-position both inputs with Colocate. | The same answer reports `BUCKET_SHUFFLE` with one Join-input Exchange and `COLOCATE` without it. |
| **9.7 Bound the evidence** | Container failure, replica recovery, and local Join plans succeeded, but production needs a defensible conclusion. | Separate storage placement, query execution, service availability, and shared-host limitations. | Metadata, `EXPLAIN`, and Profile each support a different conclusion; no single-host timing claim is added. |
| **9.8 Continue into lifecycle policy** | All online replicas are healthy, but incorrect or obsolete data can still exist on every copy. | Separate replication from retention, recycle-bin recovery, and independent backup. | Replica health closes the availability scenario and exposes the lifecycle questions addressed in Module 10. |

Lab 9 provides bounded Doris 4.1.3 evidence from an isolated multi-container
cluster. All FEs, BEs, HAProxy, and Docker storage still share one physical
host. Fixed service names, IP addresses, Tablet IDs, replica versions, and scan
row counts belong to the Lab. The course develops mechanisms and decisions that
remain valid when those values change.

---

## 9.1 Identify the Roles in a Distributed Doris Request

The event service is moving beyond one FE and one BE. Before changing the
topology, the team must identify which component accepts the client session,
which component plans the query, and which components store and scan data. A
client submitting SQL does not connect directly to every BE. It opens a MySQL
protocol session to an FE query port, or to a proxy that selects an FE for that
session.

```text
application or SQL client
           |
           v
client-side multi-address logic or TCP proxy
           |
           v
connected FE: parse, analyze, optimize, coordinate
           |
           v
selected BEs: scan local Tablet replicas and execute fragments
```

### Frontend responsibilities

An FE maintains and uses cluster metadata, parses SQL, creates a distributed
query plan, selects execution locations, dispatches plan fragments, and
coordinates the result. In a high-availability FE deployment:

- Follower FEs participate in metadata replication and election;
- one Follower is the current Master;
- other healthy Follower FEs remain part of the voting group; and
- an Observer can replicate metadata for read scaling but does not participate
  in election.

The Master role can move after failure. The hostname that an application used
does not move with it.

### Backend responsibilities

A BE stores Tablet replicas and executes assigned operators. A scan Fragment
Instance on a BE reads selected local Tablet replicas, and later operators can
aggregate, join, sort, or exchange intermediate data.

Adding more BEs can provide:

- more storage locations for Tablet replicas;
- more possible scan and execution locations; and
- more aggregate CPU, memory, and I/O capacity in a real multi-host cluster.

It does not automatically add Buckets to an existing table, and it does not
guarantee that every query uses every BE.

### Proxy and client responsibilities

A TCP proxy or multi-address driver chooses an FE for a new session. It does
not create Doris plans, store Doris metadata, or execute BE operators. An
application still owns retry policy for a connection or request that fails.

Keep these health questions separate:

| Observation | What it establishes |
| --- | --- |
| Container process is running | The process exists at the Docker level |
| `SHOW FRONTENDS` reports `Alive=true` | The Doris FE membership view sees that FE as alive |
| `SHOW BACKENDS` reports `Alive=true` | The Doris FE membership view sees that BE as alive |
| Proxy target is `UP` | The configured proxy health check currently succeeds |
| SQL query succeeds | This new or retained client path completed that query |
| Replica is current | A particular Tablet copy has the complete current version |

No single row in one of these views answers all five questions.

The responsibilities are now separate, but the application is still directly
connected to one FE. Stopping that FE tests the first unresolved boundary:
whether Doris metadata election also preserves the client's existing network
session.

## 9.2 Separate FE Election from Client Load Balancing

Suppose three Follower FEs form the voting group and the client directly
connects to the current Master. If that FE stops, the remaining majority can
elect another Master and preserve FE metadata service availability.

The existing MySQL TCP session still terminates:

```text
client ===== TCP session ===== failed FE
                                   X

new Master elected elsewhere does not move that TCP session
```

The application must establish a new session through another address or a
stable entry point.

### Choose an entry mechanism

| Mechanism | Where target selection happens | Main operating consideration |
| --- | --- | --- |
| JDBC load-balance URL | In each Java client | Every application and connection pool must use the correct driver configuration |
| Nginx TCP proxy | In a general-purpose proxy | Fits existing Nginx operations; requires stream/TCP health and forwarding configuration |
| HAProxy | In a dedicated TCP load balancer | Provides rich health checks and connection statistics |
| ProxySQL | In a MySQL-aware proxy | Adds protocol-aware connection and routing features with more operating surface |

Lab 9 uses HAProxy because the Notebook client is Python rather than JDBC and
the experiment needs visible TCP health and connection counters. This is an
environment choice, not a Doris requirement or a universal recommendation.

### Understand what HAProxy counts

A proxied MySQL session has two TCP legs:

```text
Python client ---> HAProxy listening port ---> selected FE query port
```

The Lab's statistics use these fields:

| Field | Meaning | Do not interpret it as |
| --- | --- | --- |
| `active connections` | Sessions currently forwarded from HAProxy to that FE | Number of running SQL queries |
| `total connections` | Sessions assigned to that FE since this HAProxy process started | Lifetime Doris query count |
| `L4OK` | The TCP health check connected successfully to the FE port | Successful authentication, SQL execution, or Master identity |

Round-robin distributes newly created sessions, not individual statements
inside one persistent session. A connection pool can therefore make statement
counts look uneven even when new sessions were distributed as configured.

### Use distinct evidence for distinct behavior

A controlled FE failure should establish four facts separately:

1. The directly connected FE was identified before it was stopped.
2. The old connection failed rather than migrating invisibly.
3. The surviving FEs retained a voting majority and one became Master.
4. A newly created proxy session avoided the failed target and completed a
   business query.

This supports “new connections can be re-established around one failed FE.” It
does not support “in-flight queries migrate” or “the system has zero
interruption.” One HAProxy container is also a single proxy failure point.

See [FE Load Balancing](https://doris.apache.org/docs/4.x/admin-manual/cluster-management/load-balancing/).

After the failed FE returns, the service again has a complete FE voting group
and a stable client entry. The next constraint is storage and execution
capacity. The data layer begins with two BEs and two replicas, then adds a third
BE without redefining the event table's Partition or Bucket layout.

## 9.3 Relate Partitions, Buckets, Tablets, and Replicas

Module 4 introduced Partition and Bucket design. A multi-BE cluster makes the
physical consequences visible.

For the base index of a table with a fixed Bucket count per Partition:

```text
logical Tablets = Partitions x Buckets per Partition
physical replica records = logical Tablets x replication count
```

For example, a two-Partition table with six Buckets per Partition has twelve
logical Tablets in its base index. With two replicas, Doris maintains two
physical copies of each logical Tablet.

```text
Partition A                       Partition B
  Bucket 0 -> Tablet A0             Bucket 0 -> Tablet B0
  Bucket 1 -> Tablet A1             Bucket 1 -> Tablet B1
  ...                               ...

Tablet A0 replicas: copy on one BE + copy on another BE
```

SQL reads the logical rows represented by Tablet A0 once. Replication does not
double the business answer.

### When every BE stores every Tablet

If the number of available placement targets equals the replication count,
every logical Tablet needs one replica on every BE. With two BEs and two
replicas, both BEs cover the complete set of logical Tablets.

This does not mean Doris stores one indivisible copy of the table on each BE.
The storage unit is still a Tablet replica, and each Tablet has its own ID,
version, size, and health state.

### When BEs store different Tablet subsets

After adding a third BE while keeping two replicas per Tablet, Doris has more
placement targets than copies. The Tablet scheduler can move some existing
replicas to the new BE while keeping the configured replica count:

```text
before expansion
    Tablet T1 -> BE A, BE B
    Tablet T2 -> BE A, BE B

after balancing
    Tablet T1 -> BE A, BE C
    Tablet T2 -> BE A, BE B
```

The exact balanced distribution depends on scheduler state, disk usage,
placement constraints, and cluster load. A new BE reporting `Alive=true` means
that it joined the available topology. It does not prove that existing replicas
have already moved.

### Expansion does not reshard the table

Adding a BE can change replica placement. It does not automatically change:

- Partition boundaries;
- the table's distribution column;
- the number of Buckets in an existing Partition;
- logical Tablet IDs; or
- SQL-visible rows.

More placement targets and more logical shards are different changes. A table
with too few Buckets can still limit scan parallelism after adding BEs.

### Read placement metadata with the correct scope

| Evidence | Appropriate use |
| --- | --- |
| `SHOW BACKENDS` | Node membership, heartbeat state, capacity fields, version |
| `SHOW REPLICA DISTRIBUTION` | Summary of where table replicas are placed |
| `SHOW TABLETS` | Tablet-level replica IDs, BE IDs, versions, and health metadata |
| `SELECT COUNT(*)` | Logical row count visible through SQL |

Do not add the capacity value reported by every BE container in a shared Docker
filesystem as if each value represented an independent disk. Likewise, Tablet
metadata `RowCount` is not a substitute for an exact SQL count.

Use a bounded wait when observing balancing. A fixed sleep can finish before
the scheduler acts or waste time after balancing is complete. If a small table
does not visibly move within the observation window, report that limit instead
of forcing a manual move and calling it automatic balancing.

See [Elastic Expansion](https://doris.apache.org/docs/4.x/admin-manual/cluster-management/elastic-expansion/)
and [Data Replica Management](https://doris.apache.org/docs/4.x/admin-manual/maint-monitor/tablet-repair-and-balance/).

Expansion changes where replicas can live, but placement metadata still does
not reveal which copy serves a particular query. With the third BE available,
the team can now follow one regional aggregation from the FE plan to the actual
BE scan tasks.

## 9.4 Follow a Query from SQL to BE Scan Tasks

Replica placement shows where Doris could read a Tablet. It does not show which
copy one query actually used.

Consider a regional aggregation over an event table:

```sql
SELECT region,
       COUNT(*) AS event_count,
       SUM(revenue) AS total_revenue
FROM event_detail
GROUP BY region
ORDER BY region;
```

The simplified distributed path is:

```text
1. connected FE parses and optimizes the SQL
2. predicates prune Partitions and determine required Tablets
3. FE selects one healthy replica for each required Tablet
4. physical plan is split into Plan Fragments at Exchange boundaries
5. Fragment Instances are assigned to selected BEs
6. each BE builds PipelineTasks and scans its local selected Tablets
7. local partial results travel through Exchanges
8. an upper/root Fragment merges results and returns them to the client
```

### Distinguish the execution units

| Term | Meaning |
| --- | --- |
| Plan Fragment | A reusable portion of the distributed physical plan separated by data-exchange boundaries |
| Fragment Instance | One scheduled execution of that Fragment on one BE |
| Pipeline | A connected operator path within an Instance that can execute as a pipeline |
| PipelineTask | A schedulable parallel task for a Pipeline |
| Tablet replica | The physical local storage selected for a logical Tablet scan |

One BE can run several PipelineTasks. Counting PipelineTask blocks does not tell
you how many replicas exist or how many BEs participated. Local pipeline
parallelism is different from distributed node parallelism.

### Read the plan from the scan upward

A cropped plan can contain a structure such as:

```text
PLAN FRAGMENT: scan and partial aggregation
  TABLE: event_detail(base index)
  partitions = selected/total
  tablets = selected/total
  numNodes = planned node count

EXCHANGE

PLAN FRAGMENT: merge or final aggregation
```

This establishes the planned Tablet scope, Fragment boundaries, and data
distribution. It does not establish the actual host or actual scan count for
one execution.

### Read the DetailProfile as runtime evidence

The Profile can then show:

```text
Fragment
  Pipeline(host=<BE address>)
    PipelineTask
      OLAP_SCAN_OPERATOR
        TabletIds: [...]
        ScanRows: ...
```

For each BE host, read the Tablet IDs and `ScanRows` inside the matching scan
operator. If a BE stores an eligible replica but does not appear in this scan
scope, it did not perform this table scan in that execution.

The FE normally selects one replica per required logical Tablet. It does not
scan every replica and then deduplicate the business rows. Replica selection
can vary between executions as node health, scheduling, and placement change.

Do not hard-code:

- container IP addresses;
- Tablet IDs;
- exact per-BE scan rows; or
- that every available BE must participate.

Several BE hosts in the scan Profile establish distributed work. A single
Docker host still cannot provide a meaningful production network or scaling
benchmark.

For the plan hierarchy, see [Product Concepts](https://doris.apache.org/docs/4.x/features-architecture/product-concepts/)
and [`EXPLAIN`](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-query/EXPLAIN/).

The regional aggregation shows how healthy replicas support distributed reads.
The next operational question is whether the service can also publish a new
event while one BE is unavailable, and how the returning copy becomes current
after the write.

## 9.5 Commit Through a Majority and Recover the Lagging Replica

Replication affects read availability, write commit rules, storage cost, and
failure tolerance. Those properties depend on the configured replica count.

By default, Doris considers a load successful when more than half of the
replicas are written successfully:

| Replica count | Default successful replicas required | One unavailable replica |
| ---: | ---: | --- |
| 1 | 1 | No remaining copy can accept the write |
| 2 | 2 | The default majority cannot be formed |
| 3 | 2 | The two surviving replicas can form a majority |

This is why Lab 9 does not use its two-replica analytics table to promise a
successful write during one BE outage. It creates an isolated three-replica
event table after all three BEs are healthy.

The `min_load_replica_num` feature can change the required number according to
the documented table and global configuration precedence. Lowering the
threshold trades some immediate replica coverage for load availability. Do not
assume the default majority rule when an environment overrides it.

### Follow the commit and recovery states

Before failure:

```text
BE A replica: version V, current
BE B replica: version V, current
BE C replica: version V, current
```

After BE B stops and a new write commits through A and C:

```text
BE A replica: version V+1, current
BE B replica: version V,   not current, BE unavailable
BE C replica: version V+1, current
```

After BE B returns and catches up:

```text
BE A replica: version V+1, current
BE B replica: version V+1, current
BE C replica: version V+1, current
```

The exact numbers do not matter. Compare versions relative to each other.
During the outage, FE metadata can retain the stopped replica's last known
version. That does not mean the Notebook read files from a stopped process.

### Heartbeat recovery is not data recovery

Two milestones must be checked separately:

1. `SHOW BACKENDS` reports the returning BE as alive.
2. Every target Tablet replica reports a complete current version.

The second can happen so quickly that an immediate sample already shows equal
versions. If so, report that the transition was not captured; do not invent an
older value. A bounded replica-health wait should finish only when the intended
replicas are healthy and current.

Use `stop/start` or another process-level interruption that preserves the BE's
data when teaching version catch-up. Removing the container and storage would
be a different replacement-replica experiment.

Replica convergence is not backup. A logically wrong write can be replicated
successfully to every BE. Module 10 separates online copies from recycle-bin
recovery and independent backup.

See [Load High Availability](https://doris.apache.org/docs/4.x/data-operate/import/load-best-practices/load-high-availability/)
and [Data Replica Management](https://doris.apache.org/docs/4.x/admin-manual/maint-monitor/tablet-repair-and-balance/).

Once all three replicas are current again, temporary recovery state no longer
confounds the next plan comparison. The team can use the stable layout to ask
how much event–user Join input must move for a recurring report.

## 9.6 Compare Bucket Shuffle and Colocate Join Data Movement

The restored cluster repeatedly joins event measures to user segments on
`user_id`. The logical Inner Join and its business answer stay fixed. The
decision is how much Join input should move across the distributed execution.

### Reuse the Event-Side Layout with Bucket Shuffle

Module 6 separated logical Join semantics, physical Hash Join, and Join data
distribution. Here the business query is fixed so the distribution path is the
only intended change.

The report asks for event count and revenue by user segment:

1. select one event time Partition;
2. aggregate event rows to one intermediate row per `user_id`;
3. join each user to a `new`, `returning`, or `loyal` segment; and
4. aggregate the joined measures by `user_segment`.

The event-side intermediate relation has this shape:

```text
(user_id, event_count, total_revenue)
```

Because the event table is Hash distributed by `user_id`, the per-user
aggregation can preserve an existing `user_id` Bucket layout. The first user
dimension deliberately uses RANDOM distribution:

```text
event-side state for user 1001 -> event Bucket selected by hash(user_id)
user row for 1001             -> arbitrary RANDOM user Tablet
```

The matching rows may not initially be at the same Join execution location.

#### Route only the user side

Bucket Shuffle keeps the compatible event-side layout. The Join-side Exchange
routes each user row according to the event Bucket mapping:

```text
RANDOM user row
    (1001, returning)
           |
           | hash and route with retained event Bucket mapping
           v
Fragment Instance responsible for that event Bucket
    event state (1001, count, revenue)
    user row    (1001, returning)
           |
           v
        local Hash Join
```

The user side moves; the retained event-side intermediate rows do not need a
general repartition. A Bucket number is a logical position in the retained
layout, not a permanent BE address. The FE still selects actual Tablet replicas
and execution hosts for this query.

The Lab filters one physical event Partition because the documented direct
physical-table Bucket Shuffle conditions require a usable single-Partition
left-side layout. The broader Doris definition also allows an intermediate
operator result to be the retained bucketed relation when its distribution
property is preserved.

#### Read the plan evidence locally around the Join

The expected evidence has this shape:

```text
VHASH JOIN
  join op: INNER JOIN(BUCKET_SHUFFLE)
  equal join conjunct: user_id = user_id
  input VEXCHANGE for the moved side

event scan: one selected time Partition
user scan: RANDOM-distributed table
```

An Exchange above the Join may still be required to merge final
`GROUP BY user_segment` results or order the output. “Bucket Shuffle moves one
Join input” does not mean “the entire query has no Exchange.” Read the Exchange
in relation to the Hash Join and its two input branches.

The `[shuffle]` hint in the Lab prevents the small user dimension from taking a
reasonable Broadcast path, making the Shuffle comparison observable. The hint
does not prove Bucket Shuffle. The actual `INNER JOIN(BUCKET_SHUFFLE)` plan
label is the evidence.

See [Doris Joins](https://doris.apache.org/docs/4.x/query-data/join/) and
[Join Optimization](https://doris.apache.org/docs/4.x/query-acceleration/join-optimization-intro/).

### Pre-position Both Inputs for Colocate Join

Bucket Shuffle reuses one layout for one query. If two large tables repeatedly
join on a stable Key, the table design can make the relationship durable.

A Colocation Group gives participating tables a compatible Bucket sequence and
replica placement. For the event–user relationship:

```text
BE A: event Bucket 0 replicas + user Bucket 0 replicas
BE B: event Bucket 1 replicas + user Bucket 1 replicas
BE C: event Bucket 2 replicas + user Bucket 2 replicas
```

Rows with the same `user_id` map to corresponding Buckets, and the replicas of
those Buckets are placed on compatible BEs. The Hash Join can run locally at
those locations.

#### Matching DDL is necessary but insufficient

For physical tables in the same Colocation Group, confirm:

- the tables belong to the same group;
- distribution columns have compatible types and counts;
- Bucket counts match;
- replica counts are compatible;
- the Join equality includes the Bucket Key; and
- group status reports `IsStable=true`.

Two tables that both say `DISTRIBUTED BY HASH(user_id)` are not necessarily
colocated. Without a shared stable placement contract, corresponding Buckets
can reside on different BEs.

#### Compare the same business answer

The Bucket Shuffle and Colocate queries must keep the same:

- time range and selected event Partition;
- event-side per-user aggregation;
- Join Key and logical Join type;
- user-segment data;
- output grouping and measures; and
- complete expected result.

Only the durable user-table layout and group membership should change. The
Colocate plan should report:

```text
INNER JOIN(COLOCATE)
```

There should be no `VEXCHANGE` between that Hash Join and either input scan.
An Exchange above the Join can still serve final aggregation or result merge.

Colocate is not automatically faster for every workload. A small Bucket count
can limit parallelism, a Colocation Group constrains placement and balancing,
and maintaining the relationship has an operating cost. Use it when repeated
Join movement is a demonstrated bottleneck and the participating table designs
can remain compatible.

See [Colocation Join](https://doris.apache.org/docs/4.x/query-acceleration/colocation-join/).

The two plans answer the same business question but use different placement
contracts. Their Join-local `VEXCHANGE` evidence explains which input moves; a
single shared host still cannot establish a production network or latency
advantage. The team must now state precisely what every topology, plan, and
runtime observation supports.

## 9.7 State the Availability and Performance Boundary

Module 9 combines several successful observations, but each supports a limited
conclusion.

| Evidence | Supported conclusion | Unsupported conclusion |
| --- | --- | --- |
| FE election after one FE stops | A surviving voting majority selected a Master | The failed client session migrated or every request was uninterrupted |
| HAProxy sends new sessions only to `UP` targets | New connections can avoid the failed FE under this health check | The proxy is itself redundant or every SQL statement is evenly distributed |
| Replicas appear on a newly added BE | Existing physical copies were rebalanced onto another placement target | Existing Buckets were split or logical rows changed |
| Several BE hosts appear in a scan Profile | Those BEs executed that scan in this run | Every replica or every available BE participated |
| Majority write succeeds with one BE stopped | The tested transaction became visible through surviving replicas | Every table with any replica count can accept the same outage |
| Returning replica versions converge | The tested Tablet copies became current again | An incorrect business write was undone or a backup exists |
| Colocate plan removes Join input Exchange | The selected Join can use local compatible placement | Production latency improvement has been measured |

### Shared-host limitations

All Module 9 containers share:

- one Docker Engine;
- one physical host and memory pool;
- one physical failure domain;
- host networking and storage infrastructure; and
- one HAProxy container.

Stopping one process is useful for observing Doris state transitions. It does
not test a host outage, rack or availability-zone isolation, production network
throughput, independent disks, or proxy high availability.

Do not compare single-host elapsed times to rank distributed strategies. Use
the Lab to identify selected plans, data movement, execution locations, and
replica states. Measure production performance only with representative data,
concurrency, hosts, and failure domains.

### Preserve the intended failure experiment

Container commands also define the evidence boundary:

- `stop/start` preserves a container and its writable data for a return-and-
  catch-up experiment;
- removing a container or its storage creates a replacement-data experiment;
  and
- `docker compose down` can delete the isolated environment when data is not
  mounted externally.

The Lab therefore uses `stop/start` and never treats a destructive teardown as
a temporary node failure.

## 9.8 Move from Replica Health to Data Lifecycle

The event service now has a healthy FE voting group, a reusable client entry,
healthy online replicas placed across the available BEs, and understood Join
distribution choices. Those properties keep current data available and place
current query work. They do not decide how long historical events should
remain online or how to undo a valid but incorrect operation that has reached
every replica.

Keep the next set of responsibilities separate:

| Current Module 9 mechanism | What it protects | What it does not provide |
| --- | --- | --- |
| FE metadata replication and election | Metadata service after a supported FE failure | Migration of an existing client TCP session |
| Tablet replicas | Online copies for supported BE failures | Historical versions or an independent backup |
| Replica balancing and version repair | Healthy placement and convergence of current data | Reversal of an incorrect committed write |
| Bucket Shuffle or Colocate | A distributed Join data-movement choice | A retention, archival, or recovery policy |

Module 10 therefore starts with a different business question: as the event
history keeps growing, how should the team control storage cost, remove whole
time ranges from the online table, handle late data, and recover from an
eligible mistaken deletion?

---

## Lab 9: Observe Sharding, Replication, and Distributed Execution

Open [Lab 9 — Observe Sharding, Replication, and Distributed Execution](lab09_observe_sharding_and_replication.ipynb)
after completing Lab 8. It uses an isolated Module 9 Compose project rather
than the single-node `doris-rta` container from Modules 1–8.

Check the environment before you start:

- The Lab runs three FEs, three BEs, and an HAProxy container on one Docker
  host. Docker needs at least 4 CPUs, 8 GB of memory, and 20 GiB of free disk
  space. The first Lab cell checks these values before it starts any Module 9
  container and stops with an explanation if one is too low. The running
  cluster uses about 1 GiB of memory per FE and 1.2 GiB per BE.
- Stop the single-node sandbox first with `docker stop doris-rta`. The Lab checks
  for it and stops instead of stopping it for you.
- With the Doris image already downloaded, the first start takes about one
  minute, including the HAProxy image download. On a new machine, downloading
  the Doris image takes longer.

The first complete run imports a read-only, bounded seven-hour course sample
when no reusable local baseline exists. Later runs can preserve only the 12,062
committed logical event rows as a temporary local source, then rebuild the
controlled physical event table. Other Module 9 business objects are rebuilt
by the sections that own them. This avoids repeated S3 reads while ensuring the
two-BE placement experiment starts from the intended DDL.

| Lab section | What you do | What the result establishes |
| --- | --- | --- |
| **1.1 Establish two live BEs** | Start three voting FEs, restart two BEs, stop the third BE and HAProxy, and connect directly to the identified FE entry. | FE quorum exists while the initial data layer has exactly two live placement targets and no proxy path. |
| **1.2 Rebuild and expand** | Rebuild a two-Partition, six-Bucket, two-replica event table on two BEs, then start the third BE and wait for replicas to move. | Twelve logical Tablets remain twelve, 24 physical replicas remain 24, and the new BE receives existing replicas automatically. |
| **1.3 Break the direct FE connection** | Stop the directly connected Master only after verifying three live FEs, then start HAProxy without restoring it. | The old TCP session fails; new proxy sessions use only surviving healthy FEs and still query 12,062 events. |
| **1.4 Restore the FE** | Restart the stopped FE and wait for Doris membership and proxy health. | Three FEs return, one is Master, and `L4OK` reports TCP reachability rather than SQL success. |
| **2.1 Inspect physical layout** | Show Partition, Bucket, Tablet, replica, and row-range metadata. | Storage placement and logical row count are distinct quantities. |
| **2.2 Trace a distributed scan** | Run the regional aggregation and compare cropped `EXPLAIN` with host-scoped DetailProfile scan tasks. | The plan covers the required Tablets; the Profile identifies the BEs and replicas actually scanned. |
| **2.3 Commit during one BE outage** | Create a three-replica event table, stop `be-2`, and insert one known purchase. | Two surviving replicas form the default majority and publish the event while the stopped replica remains on an older version. |
| **2.4 Recover the replica** | Restart `be-2`, sample immediately, then wait for all three replicas to become current. | `Alive=true` and current replica version are separate recovery milestones. |
| **3.1 Use Bucket Shuffle** | Build 6,706 RANDOM-distributed user rows and join them to the `user_id`-distributed event intermediate result. | The fixed business answer uses `INNER JOIN(BUCKET_SHUFFLE)` and moves the user input through an Exchange. |
| **3.2 Use Colocate** | Rebuild the same users with compatible `HASH(user_id)` Buckets, replicas, and group membership. | The same answer uses `INNER JOIN(COLOCATE)` after the group becomes stable, with no Join-input Exchange. |

Read Lab 9 evidence in four layers:

1. SQL answers establish the visible business data.
2. FE and BE metadata establish membership, placement, and replica versions.
3. `EXPLAIN` establishes planned Fragments, scans, Join strategy, and Exchanges.
4. DetailProfile establishes the BE hosts, Tablet IDs, and scan rows for one
   execution.

The Stop and Restart controls preserve the isolated containers and verify the
persisted event baseline, user dimension, and outage purchase. They are not a
backup test. Do not run `down` while you still need the cluster.

If the Module 9 cluster reaches a state that the Lab cannot recover from, for
example after a container was deleted or the FEs lost their majority, reset
it. From the course directory, run:

```bash
docker compose --file level3/module09-sharding-replication/compose.multinode.yml down
```

Then rerun the Lab from Section 1.1. The command deletes only the Module 9
containers, the data stored in them, and their network; the single-node
`doris-rta` container is not affected. The next run imports the seven-hour sample
again. Use the same command to remove the cluster when you finish the course.

## Module summary

FE availability, client routing, and BE data availability are separate layers.
A surviving FE majority can elect a Master, but an application must open a new
session through another address or proxy after its connected FE fails. HAProxy
health and connection counters describe TCP session routing, not Doris query
execution.

A Bucket creates a logical Tablet within each Partition; replication creates
physical copies of that Tablet. Adding a BE expands the set of placement
targets and can rebalance replicas without adding Buckets or changing logical
rows. A query selects one healthy replica per needed Tablet, dispatches Fragment
Instances to BEs, and uses PipelineTasks and Exchanges to complete distributed
work. The Profile, not replica placement alone, identifies actual scan hosts.

Default writes require a majority of replicas. A returning BE can become alive
before its replicas reach the current version. Replica convergence protects
online data availability; it does not undo replicated mistakes or replace a
backup.

Bucket Shuffle preserves one compatible Bucket layout and routes the other
Join input to it. Colocate makes both physical layouts compatible and stable in
advance. These strategies change where rows meet, not which rows belong in the
logical answer. Module 10 next defines how long those rows remain online and
what recovery boundary exists after data is deliberately removed.

## Quiz 9: Sharding, Replication, and Distributed Execution in Apache Doris

Complete the interactive knowledge check after finishing the module and
Lab 9. It runs without a Doris sandbox.

[Open Quiz 9 — Sharding, Replication, and Distributed Execution in Apache Doris](quiz09_distribution_and_availability.ipynb)

Next module: [Module 10: Controlling Storage Cost and Data Lifecycle in Apache Doris](../module10-managing-data/course.md).

## Official references

- Architecture and execution: [Product Concepts](https://doris.apache.org/docs/4.x/features-architecture/product-concepts/) and [`EXPLAIN`](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-query/EXPLAIN/)
- FE entry points: [FE Load Balancing](https://doris.apache.org/docs/4.x/admin-manual/cluster-management/load-balancing/)
- BE expansion and replicas: [Elastic Expansion](https://doris.apache.org/docs/4.x/admin-manual/cluster-management/elastic-expansion/) and [Data Replica Management](https://doris.apache.org/docs/4.x/admin-manual/maint-monitor/tablet-repair-and-balance/)
- Write availability: [Load High Availability](https://doris.apache.org/docs/4.x/data-operate/import/load-best-practices/load-high-availability/)
- Join movement: [Doris Joins](https://doris.apache.org/docs/4.x/query-data/join/), [Join Optimization](https://doris.apache.org/docs/4.x/query-acceleration/join-optimization-intro/), and [Colocation Join](https://doris.apache.org/docs/4.x/query-acceleration/colocation-join/)
- Lab environment: [All-in-One Image](https://doris.apache.org/community/developer-guide/all-in-one-image)
