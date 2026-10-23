# Module 12: Publishing, Permissions, and Audit

| Course information | Value |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 3 |
| Doris | Apache Doris 4.1.3 |
| Environment | The course sandbox from Module 1; `orders_fact_l2` from Lab 9 and `bi_order_metrics_l2` from Lab 11 |
| Estimated time | About 123 minutes: reading 38, Lab 75, quiz 10 |

[Course README](../../README.md) · [Open Lab 12](lab12_publishing_permissions_audit.ipynb) · [Open Quiz 12](quiz12_publishing_permissions_audit.ipynb)

## Module goal

Give a consumer exactly the access its contract needs, through a role, prove it as the consumer, keep records that another person can check, and take the access away again without breaking anyone else.

## Learning objectives

After completing this module, you will be able to:

1. Write a consumer contract and choose the object to publish before granting any privilege.
2. Grant only the needed object privilege through a role, and tell read privileges from administrative ones.
3. Tell what SHOW GRANTS, SHOW ROLES, a consumer's queries, a change record, and the audit table each prove.
4. Retire access by revoking a membership or a role's privilege, and verify the effect as the consumer.
5. Release a table with a validated cutover, and say when its rollback stops being safe.
6. Choose between table privileges, column privileges, a Row Policy, and masking for a restriction.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 12.1 A Contract Before a Grant | 6 min | What the BI team needs, and which object to publish |
| 12.2 Privileges, Roles, and Scope | 8 min | Read privileges against administrative ones, and grants through roles |
| 12.3 Evidence | 7 min | Configuration, the consumer's own queries, records, and the audit table |
| 12.4 Retire Access | 5 min | A membership or a privilege, and in which order |
| 12.5 Release a Table and Roll It Back | 5 min | A swap of names, a validated cutover, and the end of a safe rollback |
| 12.6 Rows and Columns | 7 min | Row Policies, column privileges, and masking |
| Lab 12 | 75 min | Publish the view to a role, test it as a consumer, retire it, move a direct grant, release a table, and restrict rows and columns |
| Quiz 12 | 10 min | Six questions on these objectives |

## 12.1 A Contract Before a Grant

Module 11 published `bi_order_metrics_l2`, and the BI team asks for an account before the dashboard goes live. Two quick answers cause trouble later. Sharing root lets the dashboard's users drop tables and grant privileges, and the audit records show root for all of them. An account with `SELECT_PRIV ON *.*.*` can read every table, the detail and tables created later. And when the dashboard is retired, nobody remembers what was granted.

First decide what the consumer reads:

| Candidate | One row is | What a dashboard on it must do |
| --- | --- | --- |
| `orders_fact_l2` | One order with its customer, status, payments, and region | Repeat the contract's filter and aggregation in every chart |
| `bi_order_metrics_l2` | One day: orders, amount, and average order amount | Read the published measures |

The semantic view is the object to deliver: its contract (Module 11) says what each column means, and its implementation can change without the dashboard. Write down, before the grant: the object; its grain; what its fields mean, such as `gross_amount` being order value, not money received; its freshness; the consumer and the scope of its access, read this view only; the owners of the data, the dashboard, and the approval; and how the release will be checked. The grant then follows from the object and the scope.

## 12.2 Privileges, Roles, and Scope

Doris grants **privileges** on objects to **roles**, and roles to **users**. Five people of the BI team then share one role; when one leaves, only a membership changes, and a review reads one role instead of five users.

| Privilege | Allows | Does the dashboard need it? |
| --- | --- | --- |
| `SELECT_PRIV` | Reading the objects in its scope | Yes |
| `LOAD_PRIV`, `ALTER_PRIV`, `DROP_PRIV` | Loading, changing, dropping | No |
| `GRANT_PRIV` | Granting privileges, managing users and roles | No |
| `ADMIN_PRIV` | Administration, reading and granting included, not node management | No |
| `NODE_PRIV` | Adding and removing FE and BE nodes | No |

These are separate: `GRANT_PRIV` does not read, and `SELECT_PRIV` does not grant. Granting `ADMIN_PRIV` to read one view gives a consumer far more than it needs. The scope after `ON` decides what `SELECT_PRIV` covers:

| Scope | Covers | Objects created later |
| --- | --- | --- |
| `*.*.*` | Every table of every catalog | Readable too |
| `internal.<db>.*` | Every table and view of one database | Readable too |
| `internal.<db>.<table>` | One table or view | Not affected |
| `SELECT_PRIV(col1, col2) ON internal.<db>.<table>` | Named columns of one table | New columns are not covered |

**SQL reading example: the grant of Lab 12. Do not rerun it after the Lab.**
It grants the narrowest scope that the contract allows:

<!-- reading-only-example -->
```sql
CREATE ROLE course_bi_reader_l3;
GRANT SELECT_PRIV ON internal.dw_course_l1_demo.bi_order_metrics_l2 TO ROLE 'course_bi_reader_l3';
```

The Lab writes your own database's name. A member of the role can read the view without any privilege on its sources, `daily_order_metrics_l2` and `orders_fact_l2`: Doris checks the privilege on the object that the query names. The course runs the change as root, the sandbox's administrator; in production an approved administrator does, and consumers get accounts of their own with a host scope and managed credentials.

A privilege granted to a user directly, as Module 11's optional dashboard did, works too, but no review of the roles finds it, and the next account for the same purpose needs the grant again. Doris keeps a user's own privileges in a hidden role of the user, `default_role_rbac_<user>@<host>`. Lab 12 moves the dashboard's direct grant to a role in an order that never cuts it off: grant the role the privilege, grant the user the role, then revoke the user's own privilege.

## 12.3 Evidence

Three months after the release, a reviewer asks who changed what, why, and with what effect. "The SQL succeeded" answers none of it. Each kind of evidence answers part:

| Evidence | What it shows | What it does not show |
| --- | --- | --- |
| `SHOW ROLES` | Each role's privileges by scope, and its members | What a member can actually do with them |
| `SHOW GRANTS` / `SHOW ALL GRANTS` | An account's privileges, its own and its roles' merged into one list | Which of them are its own and which come from a role |
| Queries as the consumer | What that identity can and cannot read | Other identities, other hosts |
| A change record | The change's ID, role, object, privilege, reason, and approval | That the change ran, or what it did |
| The audit table, `__internal_schema.audit_log` | Who ran which statement, in which database, with which outcome | That the privileges are right, or who the person behind an account was |

Lab 12's checks combine them. `SHOW ROLES` shows `course_bi_reader_l3` with `internal.<db>.bi_order_metrics_l2: Select_priv` in `TablePrivs` and nothing in `GlobalPrivs` or `DatabasePrivs`, where a grant would cover more. Then a temporary ordinary user, created with the role and dropped at the end, reads the view's two days and is refused both sources: `Access denied; you need (at least one of) the (Admin_priv,Select_priv) privilege(s) on table orders_fact_l2 for this operation`. Root's own queries prove nothing about a consumer: root may read everything.

Doris's audit plugin writes every statement, with the user, the database, its state, and its error code, to the table `__internal_schema.audit_log`, and to the FE's log file `fe.audit.log`. SQL can read the table up to about a minute after the statement, because the plugin writes in batches:

```sql
SELECT `user`, db, state, error_code, return_rows, stmt
FROM __internal_schema.audit_log
WHERE `user` = 'course_orders_l3_<random>'
ORDER BY `time`;
```

A query that returned its rows has the state `EOF` and error code 0; a refused one `ERR` and, in Lab 12, 1105. The record is execution evidence, not a review of the privileges: on a cluster every FE writes its own records, and keeping them, protecting them, and alerting on them is the job of an audit platform.

## 12.4 Retire Access

When a dashboard is retired, its account may still read through the role. Look at the role's `Users` first, then decide what to revoke:

| Situation | Revoke | Affects |
| --- | --- | --- |
| Dashboard A is retired, B shares the role | A's membership: `REVOKE 'course_bi_reader_l3' FROM 'dashboard_a'@'%'` | A only |
| The role has no purpose left | Its privilege, then the role: `REVOKE SELECT_PRIV ON ... FROM ROLE ...`, `DROP ROLE ...` | Every member |

Revoking the role's privilege while B still uses it cuts B off too. Check other paths before you call A retired: a direct grant or another role could still let it read. Then verify as the consumer: after Lab 12 revokes the role from its user, Doris refuses even the connection to the lab database, `Access denied for user '...' to database '...'`, because the user has no privilege left in it.

Some objects outlive what they belong to. Dropping a role leaves its Row Policies, and dropping a Workload Group leaves the grants of its usage (Module 14): a role or group created later with the same name gets them back. Remove the policies and grants first, then the role or group, and check `SHOW ROW POLICY` and `SHOW ROLES` afterward. `DROP ROLE` removes an object; keep the approval and the record of why.

## 12.5 Release a Table and Roll It Back

A new version of a table can be built beside the published one and released by name.

**SQL reading example: the release of Lab 12. Do not rerun it after the Lab.**

<!-- reading-only-example -->
```sql
ALTER TABLE published_orders_l3 REPLACE WITH TABLE candidate_orders_l3 PROPERTIES ("swap" = "true");
```

The swap is atomic: queries see either the old table or the new one, never half of each. `swap = true` keeps the old version under the candidate's name, ready for a rollback. Doris does not backfill, reconcile, or catch up the writes for you: that is the procedure around the swap. Lab 12 pauses its simulated writer, applies the final delta to both tables, compares every row, swaps, rehearses the rollback while the writer is still paused, swaps again, and resumes writing. After one more write, the retained old version lacks it: 3 orders and 205.00 against the published 4 and 230.00. A rollback is safe only until the published table receives its first write; afterward, the old version must catch up before it can come back.

## 12.6 Rows and Columns

Two new requirements arrive: the EAST team may read only EAST orders, and only Finance may see what was paid and refunded. Table privileges cover every row and column, so neither fits:

| Requirement | Mechanism | Check |
| --- | --- | --- |
| Some columns for some roles | Column privileges: `SELECT_PRIV(order_id, order_date, status, order_amount, region)` | A query of another column is refused; a column added later is not covered |
| Some rows for some roles | A Row Policy on the table, for a role | The consumer sees only its rows, even when it asks for others |
| A part of a value hidden, such as a card number | Masking, through Apache Ranger | Not in this course: Lab 12 installs no Ranger |

A **Row Policy** adds a condition that Doris applies to every query of the table by the roles or users that it names; a `RESTRICTIVE` policy keeps only the matching rows.

**SQL reading example: the EAST policy of Lab 12. Do not rerun it after the Lab.**

<!-- reading-only-example -->
```sql
CREATE ROW POLICY region_east_l3 ON dw_course_l1_demo.orders_fact_l2
AS RESTRICTIVE TO ROLE course_region_east_l3 USING (region = 'EAST');
```

The policy follows the role's members, as the role's privilege does. In Lab 12 the EAST user sees 6 orders and 830.00, and its `WHERE region = 'WEST'` returns nothing: unlike a dashboard filter, no query can widen it. Policies do not apply to root, so test them as the consumer.

With column privileges, a role that has five columns of `orders_fact_l2` reads them, and Doris refuses `SUM(paid_amount)`, `SELECT *`, which it refuses for the first column that the role lacks, and `COUNT(*)`: a count of rows needs the privilege on the whole table, so count a granted column instead, `COUNT(order_id)`. Decide the restriction, the objects it covers, and how you will test it before you choose the mechanism.

## Lab 12: Publish a View to a Role, and Audit Who Read What

Open [Lab 12: Publish a View to a Role, and Audit Who Read What](lab12_publishing_permissions_audit.ipynb). You:

1. Record the identity, the object, and the role baseline.
2. Grant a role `SELECT_PRIV` on `bi_order_metrics_l2` alone, and check it in `SHOW ROLES`.
3. As a temporary ordinary user, read the view, be refused its sources, and be refused the view after the `REVOKE`.
4. Retire the role.
5. Move Module 11's direct grant, if you built the dashboard, to a role.
6. Release a table with a validated cutover, and see when its rollback stops being safe.
7. Restrict two regional roles with Row Policies, and a third role to five columns.
8. Find the users' queries, and a refusal, in the audit table.
9. Practice: retire one of two dashboards that share a role.

You need the course sandbox, Lab 9's `orders_fact_l2`, and Lab 11's `bi_order_metrics_l2`. Roles, users, and policies belong to the whole Doris cluster; the Lab removes the ones it does not keep.

## Summary

- Write the consumer's contract first, and publish the semantic view rather than its detail: the grant's object and scope follow from it.
- Grant `SELECT_PRIV` on the one object through a role; administrative and granting privileges are separate, and a direct grant moves to a role without cutting the account off.
- `SHOW ROLES` shows configuration, `SHOW GRANTS` merges an account's own and its roles' privileges, queries as the consumer show what it can do, a change record documents, and `__internal_schema.audit_log` records what ran.
- Revoke one membership to retire one consumer and a role's privilege to retire everyone; check other paths, verify as the consumer, and remove policies and grants before the role or group.
- A swap of table names is atomic, the cutover around it is your procedure, and its rollback is safe only until the next write.
- Column privileges limit columns, a Row Policy limits rows for its roles, masking hides parts of values; `COUNT(*)` needs the table's privilege.

## Quiz 12

Open [Quiz 12: Publishing, Permissions, and Audit](quiz12_publishing_permissions_audit.ipynb). It has six single-choice questions and needs no running environment.

Next module: [Module 13: Storage and Lifecycle Management](../module13-storage-lifecycle/course.md).

## References

- [Apache Doris: Built-in authorization](https://doris.apache.org/docs/4.x/admin-manual/auth/authorization/internal/)
- [Apache Doris: Data access control](https://doris.apache.org/docs/4.x/admin-manual/auth/authorization/data/)
- [Apache Doris: GRANT TO](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/GRANT-TO)
- [Apache Doris: REVOKE FROM](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/REVOKE-FROM)
- [Apache Doris: SHOW GRANTS](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/SHOW-GRANTS/)
- [Apache Doris: CREATE ROW POLICY](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-governance/CREATE-ROW-POLICY/)
- [Apache Doris: ALTER TABLE REPLACE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/table/ALTER-TABLE-REPLACE/)
- [Apache Doris: Audit log](https://doris.apache.org/docs/4.x/admin-manual/audit-plugin/)
