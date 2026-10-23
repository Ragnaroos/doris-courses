# Module 11: Interfaces and Boundaries for BI and AI Consumers

| Course information | Value |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 2 |
| Doris | Apache Doris 4.1.3 |
| Environment | The course sandbox from Module 1; `daily_order_metrics_l2` from Lab 10; for the optional dashboard, about 2 GiB more Docker memory and internet access once |
| Estimated time | About 120 minutes: reading 40, Lab 70, quiz 10 |

[Course README](../../README.md) · [Open Lab 11](lab11_bi_and_ai_delivery.ipynb) · [Open Quiz 11](quiz11_bi_and_ai.ipynb)

## Module goal

Publish the daily metrics as an interface whose rows and meaning stay the same for dashboards and models, check it before anyone reads it, and draw the line between what Doris guarantees and what BI and AI tools must check themselves.

## Learning objectives

After completing this module, you will be able to:

1. Design a semantic view with stable names, one declared grain, and measures whose meaning is written down.
2. Tell dimensions, additive measures, and ratios apart in a dashboard.
3. Check an interface's rows, nulls, dates, and totals, and make its contract and freshness checks fail on purpose.
4. Prepare feature inputs over a calendar without claiming anything about a model's accuracy.
5. State what Doris guarantees and what a BI tool or an AI application must check itself.
6. Bound an AI tool's access to Doris with a separate MCP server and a read-only account scoped to published views.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 11.1 A Consumer Contract | 8 min | A semantic view, its grain, and what each column means |
| 11.2 Check the Interface Before Publication | 7 min | Rows, nulls, dates, totals, and two checks that must fail |
| 11.3 What Doris Owns and What a BI Tool Owns | 7 min | Speed, freshness, and accuracy, and who checks each |
| 11.4 Features for AI: Inputs, Not Conclusions | 7 min | A calendar, a day without orders, and what features cannot prove |
| 11.5 Bound What an AI Tool Can Read | 7 min | A separate MCP server and a read-only account |
| 11.6 Optional: A Real Dashboard | 4 min | A local Superset on the payment contract, and how to remove it |
| Lab 11 | 70 min | Publish the semantic view, project features, check and break the contract; optionally build the dashboard |
| Quiz 11 | 10 min | Six questions on these objectives |

## 11.1 A Consumer Contract

A BI team can query a table and still build a wrong dashboard, for example by labeling the pre-tax order amount as money received. Query access is not a data product. A **semantic view** is the interface for consumers: stable names, one declared grain, and measures whose meaning is written down. Lab 11 publishes one over Lab 10's service table:

**SQL reading example: the semantic view of Lab 11. Do not rerun it after the Lab.**

<!-- reading-only-example -->
```sql
CREATE VIEW bi_order_metrics_l2 AS
SELECT order_date,
       SUM(order_count) AS order_count,
       SUM(gross_amount) AS gross_amount,
       CASE WHEN SUM(order_count) = 0 THEN NULL
            ELSE SUM(gross_amount) / SUM(order_count) END AS average_order_amount
FROM daily_order_metrics_l2
GROUP BY order_date;
```

| order_date | order_count | gross_amount | average_order_amount |
| --- | ---: | ---: | ---: |
| 2026-01-01 | 9 | 1200.00 | 133.333333 |
| 2026-01-02 | 1 | 110.00 | 110.000000 |

A dashboard uses three kinds of fields:

| Kind | In this view | What a dashboard may do with it |
| --- | --- | --- |
| Dimension | `order_date` | Group, filter, and sort by it |
| Additive measure | `order_count`, `gross_amount` | Add it up over days |
| Ratio | `average_order_amount` | Show it per row; over several days, add the counts and amounts and divide again, never average it |

The view's contract writes down what consumers rely on:

1. **Names, types, and meanings:** `order_date` is the date of the order's version 1 event; `order_count` counts the orders that are not cancelled; `gross_amount` is their pre-tax order value, not money received; `average_order_amount` is the amount divided by the count.
2. **Grain:** one row per date that has orders. A date without orders has no row; a missing row and a day with zero orders are different things.
3. **Time and coverage:** the time zone, +08:00, the first date, and what happens with late events.
4. **Freshness:** what triggers an update, the delay allowed, and which dates are rebuilt after a late event.
5. **Nulls and zeros:** the ratio is `NULL` without orders, never an invented 0.
6. **Access and owners:** which account may read the view (Module 12), and who approves a change of its definition.

The view's implementation can change, Lab 10's table can gain columns, as long as its columns keep their names and meanings. A new question at a new grain, such as a filter by region, gets a second view, as Lab 11's practice publishes, while the first keeps its consumers.

## 11.2 Check the Interface Before Publication

Before a dashboard or a model reads the view, check what they rely on:

```sql
SELECT COUNT(*) AS serving_days,
       SUM(CASE WHEN order_count IS NULL OR gross_amount IS NULL THEN 1 ELSE 0 END) AS days_with_nulls,
       MIN(order_date) AS first_date,
       MAX(order_date) AS last_date,
       SUM(order_count) AS served_orders,
       SUM(gross_amount) AS served_amount
FROM bi_order_metrics_l2;
```

| Check | Lab 11's result |
| --- | --- |
| Serving days and days with nulls | 2 and 0 |
| First and last date | 2026-01-01 and 2026-01-02 |
| Orders and amount | 10 and 1310.00, the same as the service table |

A query that runs is not a contract test. Lab 11 reads the view's column names through a cursor and compares them with the four that the contract publishes, then creates a broken copy without `average_order_amount`: the same check must reject it. It measures freshness against fixed teaching dates, since the orders are from January 2026: the latest day, January 2, is one day old on January 3, which a one-day rule allows, and seven days old on January 9, which it does not. A real check uses the business's clock and its declared rule. A check that has never failed may check nothing, so make each one fail on purpose once.

## 11.3 What Doris Owns and What a BI Tool Owns

A BI tool such as Apache Superset reads Doris through its SQL interface; the tool owns its charts, its filters, its cache, and its own users and roles. A connection URI has this form:

```text
doris://<username>:<password>@<host>:<port>/internal.<database>
```

> **Do not write a real password into a notebook, a lesson, or a file that you commit.** The optional dashboard of Lab 11 generates the password of its Doris account and passes it to Superset without showing it.

Use the port that the BI tool can reach: inside the course's containers, Doris's MySQL port is 9030; from your computer it is the published port, 52030 or `DW_FE_QUERY_PORT`. Before a dataset is built on the view, check that the account can read only what it should (Module 12), that the catalog and database are right, that the numbers match the reconciliation of Module 10, and that the time zone and freshness are written down.

| Promise | What Doris can show | What another owner checks |
| --- | --- | --- |
| Speed | Query latency, rows scanned, operator time in a Query Profile | The BI tool's queries, concurrency, and cache |
| Freshness | The latest refresh, the latest event time | The scheduler, late data, the BI cache |
| Accuracy | Fixed expectations, reconciliation with the detail, null and count checks | The metric's owner, and the chart's filters |

A 200 ms answer does not say that the data is fresh, and a number on a chart does not say that the definition behind it is right.

## 11.4 Features for AI: Inputs, Not Conclusions

A model that reads daily features needs a row for every day, also for a day without orders: a missing row is no input, a zero is. The semantic view has rows only for the days that had orders, so Lab 11 starts the projection from a calendar of the reporting window and joins the view to it:

```sql
WITH calendar AS (
    SELECT DATE_ADD(DATE '2026-01-01', number) AS feature_date FROM numbers("number"="3")
)
SELECT c.feature_date,
       COALESCE(m.order_count, 0) AS feature_order_count,
       COALESCE(m.gross_amount, 0.00) AS feature_gross_amount,
       m.average_order_amount AS feature_average_amount,
       CASE WHEN COALESCE(m.order_count, 0) = 0 THEN 1 ELSE 0 END AS zero_order_flag
FROM calendar c
LEFT JOIN bi_order_metrics_l2 m ON m.order_date = c.feature_date
ORDER BY c.feature_date;
```

January 3 appears with 0 orders, no average, and `zero_order_flag` 1. The flag cannot say whether the day had no orders or its orders have not arrived yet: the freshness check and the pipeline's records can. A feature projection prepares consistent, checked inputs; it proves nothing about a model's accuracy, does not prevent target leakage, and does not make training and serving data agree by itself: the AI application owns those, with its own evaluation. Doris also offers vector columns and indexes for similarity search; they do not turn a measure into a good feature either.

## 11.5 Bound What an AI Tool Can Read

The [Apache Doris MCP Server](https://doris.apache.org/docs/4.x/key-features/mcp-server/) lets AI tools that speak the Model Context Protocol (MCP) explore schemas and run read queries on Doris. It is a separate service, not a statement of the FE; it connects through the MySQL protocol as a named Doris user:

```text
MCP client (an AI tool) → Doris MCP Server → Doris, as one read-only database user
```

The server's own limits, such as allowed tools, timeouts, result sizes, and its log, add to the Doris account's privileges; they do not replace them. A safe setup gives the server an account that can read only the published views (Module 12), keeps its password out of notebooks and prompts, reviews the SQL that the tool generates, especially for sensitive columns and wide scans, limits rows and time ranges, treats text that comes back from tables as untrusted input, and keeps the audit records (Module 12). Never connect it as root, and never take a model's confidence for a check of a metric.

Lab 11 installs no MCP server. For further reading, [Module 1: Connect AI Agents to Apache Doris with MCP](../../../04-ai-integrations/level1/module01-doris-mcp/course.md) of the course AI Integrations with Apache Doris connects an AI tool to Doris through the MCP server, with a read-only account.

## 11.6 Optional: A Real Dashboard

Lab 11's optional sections 5 and 6 take the payment contract of Module 10, not a relabeled order amount, into a real BI tool: they build and start a local Apache Superset 4.1.2, register Doris's SQLAlchemy driver, and create three charts, paid GMV, paid orders, and the cohort's conversion, whose values the helper reads back through Superset. They run only when you set `BUILD_DASHBOARD = True`.

**Before you switch them on:** the first run downloads Superset and builds the image `doris-course-superset:4.1.2-pydoris1.1.0`, which needs internet access and a few minutes. The service needs about 2 GiB of Docker memory more (its container is capped at 2 GiB and 2 CPUs) and the port 51888 on 127.0.0.1 (`DW_BI_PORT` to use another). It creates the Compose project `doris-warehousing-bi` with a volume for its metadata, the Superset user `course_admin` / `course_local_only`, and the Doris account `course_bi_<suffix>`, which can read only `bi_paid_kpis_l2`; Module 12 moves its grant to a role. These stay after the Lab, so that the dashboard keeps working. Skipping the optional sections changes nothing for Quiz 11 or Level 3.

The Superset user configures dashboards; the Doris account is what the charts read with. A chart that loads and a denied read of `dwd_payments_l2` show the database's boundary for this account; they do not show Superset's own user isolation. The secret key, the plain HTTP, and the public user are for a local course only.

To remove the dashboard, detach the course's Doris container from its network first, then remove the project and the image, from the course directory:

```bash
docker network disconnect doris-warehousing-bi_default doris-warehousing-course-doris-1
docker compose --project-name doris-warehousing-bi --file environments/bi/compose.yml down --volumes
docker image rm doris-course-superset:4.1.2-pydoris1.1.0
```

Then drop the Doris account that Lab 11 showed as `doris_reader`, and the role that Module 12 moved it to: `DROP USER 'course_bi_<suffix>'@'%'` and `DROP ROLE IF EXISTS course_bi_dashboard_l3`.

## Lab 11: Publish a Semantic View and Its Features

Open [Lab 11: Publish a Semantic View and Its Features](lab11_bi_and_ai_delivery.ipynb). You:

1. Publish `bi_order_metrics_l2`: two days, 10 orders, 1310.00.
2. Project features over the reporting window's calendar, with January 3 flagged.
3. Check the interface's days, nulls, dates, and totals against the service table.
4. Make the contract check and the freshness check fail on purpose.
5. Optionally, build a three-chart Superset dashboard on the payment contract.
6. Practice: publish a second view per day and region without changing the first.

You need the course sandbox and Lab 10's `daily_order_metrics_l2`; the optional dashboard also needs Lab 10's `bi_paid_kpis_l2`. Module 12 publishes `bi_order_metrics_l2` to a role.

## Summary

- A semantic view is a contract: stable names, one grain, written meanings, and a time zone, a freshness rule, null rules, and owners; a new grain is a new view.
- In a dashboard, group by dimensions, add up additive measures, and recompute ratios from their sums instead of averaging them.
- Check days, nulls, dates, and totals before publication, and make the contract and freshness checks fail once to prove that they can.
- Project features over a calendar so that a day without orders is a row; features are checked inputs, not evidence of a model's accuracy.
- Doris shows speed, freshness, and accuracy of the SQL interface; a BI tool owns its charts, filters, and cache, and an AI application its model and evaluation.
- Give an AI tool access through a separate MCP server with a read-only account limited to the published views; its own limits add to the privileges, never replace them.

## Quiz 11

Open [Quiz 11: Interfaces and Boundaries for BI and AI Consumers](quiz11_bi_and_ai.ipynb). It has six single-choice questions and needs no running environment.

Next: this is the last module of Level 2. Level 3 starts with [Module 12: Publishing, Permissions, and Audit](../../level3/module12-publishing-permissions-audit/course.md).

## References

- [Apache Doris: CREATE VIEW](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/view/CREATE-VIEW/)
- [Apache Doris: Superset](https://doris.apache.org/docs/4.x/connection-integration/data-integration/superset/)
- [Apache Doris: MCP Server](https://doris.apache.org/docs/4.x/key-features/mcp-server/)
- [Apache Doris: Vector search](https://doris.apache.org/docs/4.x/table-design/index/vector-index/overview/)
