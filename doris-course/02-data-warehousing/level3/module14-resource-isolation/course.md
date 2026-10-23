# Module 14: Resource Isolation and Query Protection

| Course information | Value |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 3 |
| Doris | Apache Doris 4.1.3 |
| Environment | The course sandbox from Module 1 |
| Estimated time | About 100 minutes: reading 45, Lab 45, quiz 10 |

[Course README](../../README.md) · [Open Lab 14](lab14_resource_isolation.ipynb) · [Open Quiz 14](quiz14_resource_isolation.ipynb)

## Module goal

Keep ad hoc analysis from slowing down the dashboard: give each workload a Workload Group, route each account to its group, stop excessive queries before or while they run, and remove it all again in an order that its dependencies allow.

## Learning objectives

After completing this module, you will be able to:

1. Explain the order in which Doris selects a query's Workload Group.
2. Predict from max_concurrency, max_queue_size, and queue_timeout whether a query runs, waits, or is rejected.
3. Explain where memory and CPU limits apply and what CPU enforcement requires.
4. Route an account to a group with USAGE_PRIV and default_workload_group, and explain why bypass_workload_group is not an isolation boundary.
5. Tell query_timeout, Workload Policy, and SQL Block Rule apart by when and where they act.
6. Write a resource runbook with groups, routing, protection, observations, and a rollback in dependency order.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 14.1 Who Competes with the Dashboard | 6 min | Two workloads, one group, and the order of routing |
| 14.2 Run, Wait, or Be Rejected | 9 min | Concurrency, queue, and wait, and what bypasses them |
| 14.3 Memory and CPU on Each BE | 6 min | Per-BE limits, and the cgroup that CPU limits need |
| 14.4 Route an Account to Its Group | 8 min | Usage privileges and the account's default, as an ordinary user sees them |
| 14.5 Stop an Excessive Query | 10 min | Timeouts, Workload Policies, and SQL Block Rules |
| 14.6 A Resource Runbook and Its Rollback | 6 min | Configuration, observations, and the order of removal |
| Lab 14 | 45 min | Create two groups, queue and reject queries, route an ordinary user, block a full scan, and check a plan |
| Quiz 14 | 10 min | Six questions on these objectives |

## 14.1 Who Competes with the Dashboard

The dashboard that Module 11 published refreshes in under a second. On Monday's monthly review, analysts send detail queries without date filters and a few large aggregations, the refresh takes 20 seconds, and some dashboard queries time out. Both workloads run in the default group `normal`, which by default has no practical limit on concurrency and no queue, and nothing stops a scan of every partition.

| | Dashboard queries | Ad hoc analysis |
| --- | --- | --- |
| Frequency | High: each refresh sends several | Lower, but one query can run long |
| Scan | Small: the latest days | Unpredictable: a date filter is easily forgotten |
| Latency target | About a second | Tens of seconds may be fine |

A **Workload Group** applies limits to the queries that run in it, on two levels:

| Where | Controls | Properties |
| --- | --- | --- |
| Each FE | How many queries run, how many wait, and how long | `max_concurrency`, `max_queue_size`, `queue_timeout` |
| Each BE | The group's memory, CPU, and scan resources | `max_memory_percent`, `max_cpu_percent`, `scan_thread_num`, `read_bytes_per_second` |

Separate groups keep ad hoc queries out of the dashboard's slots and bound what each group uses on a BE. They share one BE process, with its caches and threads, so they reduce interference rather than isolate completely; workloads that must not affect each other at all need separate nodes.

Doris selects a query's group in this order:

1. A hint in the query: `SET_VAR(workload_group = ...)`.
2. The session's `workload_group`, when it is not empty.
3. The account's property `default_workload_group`.
4. `normal`, which every account may use and which cannot be dropped.

## 14.2 Run, Wait, or Be Rejected

For a query in a group, its FE decides:

1. Fewer queries run than `max_concurrency`: the query starts.
2. The slots are full and fewer than `max_queue_size` wait: it waits.
3. The queue is full too: it is rejected with `query waiting queue is full`.
4. It waits longer than its time allows: it fails with `query queue timeout`.

Lab 14's ad hoc group has one slot and one place in the queue. Of three slow queries, the first runs, the second waits, and the third is rejected at once: `query waiting queue is full, queue capacity=1, waiting num=1`. The defaults matter:

| Property | Default | Meaning |
| --- | --- | --- |
| `max_concurrency` | 2147483647 | No practical limit |
| `max_queue_size` | 0 | No queue: a query beyond the slots is rejected |
| `queue_timeout` | 0 | In milliseconds; 0 sets no wait of its own, so the query's own timeout bounds the wait |

Setting only `max_concurrency` creates no queue: set `max_queue_size` too if extra queries should wait. A positive `queue_timeout`, in milliseconds, bounds the wait together with `query_timeout`, in seconds: whichever ends first wins.

Some queries never queue. The FE queues queries that scan data; `SELECT 1` and queries of `information_schema` alone do not. A query answered from the SQL cache returns at once without queueing: with the cache on, as in the sandbox, a repeated query can be cached after its tables have not changed for about 30 seconds, so Lab 14's sessions turn the cache off. Each FE has its own slots and queue: three FEs with 8 slots each have 24, if the connections are spread over them. `SHOW WORKLOAD GROUPS` shows each group's `running_query_num` and `waiting_query_num`; in `information_schema.active_queries`, a waiting query is `WAIT_IN_QUEUE` and a running one `RUNNING`.

## 14.3 Memory and CPU on Each BE

A group's memory and CPU properties apply on each BE, not to the cluster as a whole:

| Property | Meaning | Default |
| --- | --- | --- |
| `max_memory_percent` | The most memory the group may use on a BE, as a share of the BE process's `mem_limit` | 100% |
| `min_memory_percent` | The share kept for the group when memory is short | 0% |
| `memory_high_watermark` | The share of its maximum at which new memory requests of the group start to fail | 85% |
| `memory_low_watermark` | The share below which its paused queries normally resume | 75% |
| `max_cpu_percent` | A hard limit on CPU, also when the CPU is otherwise idle | 100% |
| `min_cpu_percent` | The share kept for the group when the CPU is busy | 0% |

The minimum shares of all groups must add up to at most 100%; the maximums can add up to more. When a group nears its memory limit, its requests can fail and its queries pause; Doris may spill intermediate data to disk, or resume a query when memory is freed, and otherwise cancels it with `memory limit is exceeded while handling workload group memory pressure`. Which of these happens depends on the BE's load at the moment, so Lab 14 sets a memory limit without claiming to reproduce an overload.

Memory limits use Doris's own accounting. CPU limits need Linux CPU cgroups: if the BE's `doris_cgroup_cpu_path` is empty, Doris creates no cgroup for the groups, and `max_cpu_percent` is a setting that nothing enforces. The course's sandbox has no such path.

## 14.4 Route an Account to Its Group

Two things route an account's queries to a group, and either alone is not enough.

**SQL reading example: Lab 14 runs these for a temporary user. Do not run them outside the Lab.**

<!-- reading-only-example -->
```sql
GRANT USAGE_PRIV ON WORKLOAD GROUP 'course_dashboard_l3' TO ROLE 'course_dashboard_reader_l3';
SET PROPERTY FOR 'bi_dashboard_user' 'default_workload_group' = 'course_dashboard_l3';
```

| Configuration | Result |
| --- | --- |
| `USAGE_PRIV` without a default or another setting | The queries still run in `normal` |
| A default without `USAGE_PRIV` | Every query fails: `Access denied; you need (at least one of) the USAGE/ADMIN privilege(s) to use workload group '...'` |
| Both | The queries run in the group |

Lab 14 tests this as a temporary ordinary user with the role and the default. Its slow query runs in `course_dashboard_l3`, as `information_schema.active_queries` shows, although the user named no group. Then the user sets its session to `course_adhoc_l3`, which its role may not use: the `SET` succeeds, and the next query is refused, because Doris checks the privilege when a query runs. A user may change its own `default_workload_group`, but its queries run only in groups that it may use; the other account properties, such as `query_timeout` and `sql_block_rules`, only an administrator can set, with `SET PROPERTY FOR`. A group that is some account's default cannot be dropped until the default changes.

Any user can set `bypass_workload_group = true` for its session. That skips the FE's queue, `max_concurrency`, `max_queue_size`, and `queue_timeout`; it does not change the group, skip the usage check, or lift the BE's memory limits. In Lab 14, a query with it set runs while the ad hoc group's slot and queue are full. So the queue is not a boundary that an ordinary user cannot cross; the BE's limits, an administrator's timeout, and SQL Block Rules are.

## 14.5 Stop an Excessive Query

A group bounds what all of its queries use together; one query also needs bounds of its own. Doris has three, which act at different times:

| Mechanism | When it acts | On which queries | What happens |
| --- | --- | --- | --- |
| `query_timeout` | During execution, when the time is up | Each query | Cancelled: `query timeout` |
| Workload Policy | During execution, when a condition matches | The queries of a group, or all of them | An action, such as `cancel_query` |
| SQL Block Rule | Before execution | Every account for a global rule, the associated accounts otherwise | Rejected before it scans |

**Execution timeout.** `query_timeout`, in seconds, defaults to 900. A user can raise it for its session; an administrator's account property of the same name takes precedence and cannot be changed by the user.

**SQL reading example: not executed in the Lab.**

<!-- reading-only-example -->
```sql
SET PROPERTY FOR 'adhoc_analyst' 'query_timeout' = '600';
```

Lab 14 sets two seconds in a session to see the error. A timeout stops the cost, but the query used resources until then; a queue timeout, in contrast, means that the query never ran.

**Workload Policy.** A policy checks the running queries and acts when its condition matches; this one cancels the ad hoc queries that run longer than a minute.

**SQL reading example: not executed in the Lab.**

<!-- reading-only-example -->
```sql
CREATE WORKLOAD POLICY course_adhoc_guard_l3
CONDITIONS (query_time > 60000)
ACTIONS (cancel_query)
PROPERTIES ("workload_group" = "course_adhoc_l3");
```

`query_time` is in milliseconds; other conditions are `be_scan_rows`, `be_scan_bytes`, and `query_be_memory_bytes`. The FE sends policies to the BEs periodically and the BEs check about every half second, so a cancellation comes with a delay; its message contains `cancelled by workload policy` and the policy's name. A policy without a group applies to every query, which makes a wrong condition costly. A group that a policy references cannot be dropped first; `information_schema.workload_policy` lists the policies. Lab 14 does not run one: its timing would not make a reliable check.

**SQL Block Rule.** A rule rejects a matching query before it runs, by its text or by what its plan would scan:

| Kind | Properties | What it reads |
| --- | --- | --- |
| Text | `sql`, a regular expression, or `sqlHash` | The query's text |
| Scan | `partition_num`, `tablet_num`, `cardinality` | The partitions, tablets, or estimated rows of the plan's scans |

**SQL reading example: the rule of Lab 14, which drops it at the end. Do not run it outside the Lab: the rule is global.**
It allows a scan of at most two partitions:

<!-- reading-only-example -->
```sql
CREATE SQL_BLOCK_RULE course_scan_guard_l3
PROPERTIES ("partition_num" = "2", "global" = "true", "enable" = "true");
```

`orders_monthly_l3` has three monthly partitions. An unfiltered `SUM(amount)` would scan all three, and Doris rejects it: `sql hits sql block rule: course_scan_guard_l3, reach partition_num : 2`, where 2 is the rule's limit, not the scan's count. A query of March alone prunes to one partition and runs. Four details matter:

- `global` defaults to false: an administrator associates the rule with accounts through the account property `sql_block_rules`, which the account cannot remove. A global rule applies to every account, root and the dashboards included.
- A text rule matches the original text, case-sensitively by default: a rule for `select * from orders_monthly_l3` misses `SELECT * FROM db.orders_monthly_l3`. When the requirement is about scan scope, use a scan rule.
- A scan rule needs a plan that scans. An unfiltered `COUNT(*)` of a Duplicate Key table may be answered from the FE's statistics without a scan, so Lab 14 uses `SUM(amount)`.
- A query that is already in the SQL cache can keep returning its cached answer under a new rule: test with the cache off.

The mechanisms combine: a scan rule rejects unbounded scans at the door, a policy cancels long ad hoc queries, and an administrator's timeout bounds every query.

## 14.6 A Resource Runbook and Its Rollback

A resource change needs an owner, observations, and a way back:

| Part | Lab 14's example |
| --- | --- |
| Groups | Dashboard: 8 slots, 20 places in the queue, a wait of 10 s, 50% memory. Ad hoc: 1, 1, 30 s, 30% memory, and a CPU limit of 30% that the sandbox does not enforce |
| Routing | `course_dashboard_reader_l3` holds `USAGE_PRIV` on the dashboard group; its accounts get the group as their default |
| Protection | `course_scan_guard_l3` limits scans to two partitions; an administrator sets the accounts' timeouts |
| Observations | The groups' running and waiting counts, `WAIT_IN_QUEUE`, the exact errors |
| Rollback | Remove the policies that reference the groups, set the accounts' defaults to another group, revoke the usage privileges, drop the unused roles and the groups, drop the rules, and check each with its `SHOW` statement |

The order follows the dependencies: Doris refuses to drop a group that a policy references or that is an account's default. And dropping a group does not drop the grants of its usage: a group created later with the same name would show the old `USAGE_PRIV` again in `SHOW ROLES`. Revoke the grants, or drop a role that has no purpose left, before you drop the group. Lab 14's practice checks a plan before it is applied: on three FEs, 8 slots each hold a peak of 20 dashboard queries only if the connections are spread over the FEs.

## Lab 14: Separate Dashboard and Ad Hoc Resources

Open [Lab 14: Separate Dashboard and Ad Hoc Resources](lab14_resource_isolation.ipynb). You:

1. See which group root's queries use.
2. Prepare the table, and remove what an earlier run left.
3. Create the dashboard and ad hoc groups, and grant the dashboard group to a role.
4. Send five queries and see them run, wait, be rejected, and bypass the queue.
5. Tell a queue timeout from an execution timeout.
6. Route a temporary ordinary user with its account's default, and see it refused the ad hoc group.
7. Reject a full scan with a SQL Block Rule.
8. Check that no policy or account default holds the groups, then revoke the grant and drop the role and the groups.
9. Practice: check a resource plan, then apply it under trial names.

You need only the course sandbox. Workload Groups, roles, users, and rules belong to the whole cluster; the Lab removes all of its own and leaves `normal` and root's account unchanged.

## Summary

- Doris takes a query's group from a hint, then the session, then the account's default, then `normal`.
- A query runs when a slot is free, waits while the queue has room, and is rejected otherwise; a positive `queue_timeout` ends the wait, and each FE has its own slots and queue.
- Memory and CPU limits apply on each BE; CPU limits need a CPU cgroup, which the sandbox does not have.
- An account reaches a group with both `USAGE_PRIV` and `default_workload_group`; the privilege is checked when a query runs, and `bypass_workload_group` skips only the FE's queue.
- `query_timeout` cancels a running query, a Workload Policy acts on running queries that match, and a SQL Block Rule rejects a query before it runs.
- A runbook names the groups, routing, protection, and observations, and removes policies, defaults, grants, roles, groups, and rules in the order of their dependencies.

## Quiz 14

Open [Quiz 14: Resource Isolation and Query Protection](quiz14_resource_isolation.ipynb). It has six single-choice questions and needs no running environment.

Next: this is the last module of the course. Over fourteen modules you loaded orders and their history into Doris, kept only the inputs that passed their checks, followed the orders' changes, modeled them as facts and dimensions, turned them into metrics with written contracts, published those metrics to dashboards and models, granted that access through roles and audited it, kept the data's lifecycle in partitions with a tested way back, and gave each workload its own resources. The [course README](../../README.md) says how to remove what the Labs created; the other courses of this series, such as [Real-time Analytics with Apache Doris](../../../01-real-time-analytics/README.md), are further reading.

## References

- [Apache Doris: Workload Group](https://doris.apache.org/docs/4.x/admin-manual/workload-management/workload-group/)
- [Apache Doris: Concurrency control and queuing](https://doris.apache.org/docs/4.x/admin-manual/workload-management/concurrency-control-and-queuing/)
- [Apache Doris: SQL blocking and Workload Policy](https://doris.apache.org/docs/4.x/admin-manual/workload-management/sql-blocking/)
- [Apache Doris: CREATE SQL_BLOCK_RULE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-governance/CREATE-SQL_BLOCK_RULE/)
- [Apache Doris: CREATE WORKLOAD POLICY](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/cluster-management/compute-management/CREATE-WORKLOAD-POLICY/)
- [Apache Doris: SET PROPERTY](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/SET-PROPERTY/)
- [Apache Doris: active_queries](https://doris.apache.org/docs/4.x/admin-manual/system-tables/information_schema/active_queries/)
- [Apache Doris: SQL Cache](https://doris.apache.org/docs/4.x/query-acceleration/sql-cache-manual/)
