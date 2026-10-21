# Module 7: Trace Analysis and Litefuse

| Course information | Value |
| --- | --- |
| Course | Observability with Apache Doris · Level 2 |
| Doris | Apache Doris 4.1.3 |
| Environment | The DOG stack and the OpenTelemetry demo of Module 1, with the payment failure turned on; Litefuse 26.3.0, which the Lab starts |
| Estimated time | About 90 minutes: reading 30, Lab 50 (plus the first download of about 1.2 GB of images), quiz 10 |

[Course README](../../README.md) · [Open Lab 7](lab07_data_analysis_litefuse.ipynb) · [Open Quiz 7](quiz07_analysis_and_litefuse.ipynb)

## Module goal

Measure the payment incident across all of its traces with SQL, and trace an application built on a large language model (LLM) with Litefuse, which keeps its traces in Doris.

## Learning objectives

After completing this module, you will be able to:

1. Compute the failure rate and the latency of each operation from server spans.
2. Interpret latency percentiles without claiming more than they show.
3. Find with SQL the service in which each failure of many traces starts.
4. Use a window function to compute a value for each row from the rows related to it.
5. Explain what the trace of an LLM application records that service spans do not.
6. Find an LLM application's traces in Doris, and query them with SQL.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 7.1 From one trace to all of them | 4 min | Rate, errors, and duration per operation |
| 7.2 Percentiles | 4 min | What P50 and P99 say, and what they hide |
| 7.3 Where failures start | 6 min | The service that failed on its own, for every failed order |
| 7.4 Window functions | 5 min | Values over related rows, without grouping |
| 7.5 Traces of an LLM application | 5 min | Prompts, models, tokens, costs, and steps |
| 7.6 Litefuse on Doris | 6 min | How Litefuse stores and serves its traces |
| Lab 7 | 50 min | The incident measured with SQL, and an LLM application traced with Litefuse |
| Quiz 7 | 10 min | Six questions on these objectives |

## 7.1 From one trace to all of them

In Module 3 you followed one failed order through its trace. A trace shows how one request went; the questions of an incident are about all requests: how many failed, in which operations, how slow they were, and whether the failures all start in the same place. SQL on `otel_traces` answers them for every span at once.

The usual summary of a service is three numbers per operation, sometimes called RED: the **rate** of requests, the **errors** among them, and their **duration**. A request that a service handles is a server span (`span_kind = 'SPAN_KIND_SERVER'`), so one `GROUP BY service_name, span_name` over the server spans of the incident window gives all three:

| Service and operation | Requests | Failed | Failed % |
| --- | ---: | ---: | ---: |
| `checkout` `oteldemo.CheckoutService/PlaceOrder` | 57 | 31 | 54.4 |
| `payment` `grpc.oteldemo.PaymentService/Charge` | 57 | 31 | 54.4 |
| `frontend` `POST` | 207 | 30 | 14.5 |
| `frontend-proxy` `ingress` | 75,022 | 30 | 0.0 |

The same failures show in four places with very different rates. Every order makes one charge, and a failed charge fails its order, so `PlaceOrder` and `Charge` fail equally. The frontend's `POST` also covers the storefront's other POST requests, and the proxy's `ingress` covers every request of the store: the failure of one operation disappears in the rate of a gateway. Break rates down by operation before you judge them.

Durations need care with their unit and with their meaning. The Doris exporter stores `duration` in microseconds, so Lab 7 divides by 1,000 for milliseconds. And faster is not always healthier: in one run of Lab 7, the failed orders took a median of about 6 ms, the successful ones about 11 ms, because a failed order stops at the charge, while a successful one goes on to ship the order, empty the cart, send the confirmation email, and publish the order to Kafka. An alert on latency alone would not see this incident.

## 7.2 Percentiles

An average hides the slow requests among the fast ones. A **percentile** says how long the requests took up to a given share: half of them took at most the median, P50; 99% took at most P99. P99 shows the slow tail that users notice, without assuming that every request is slow. `PERCENTILE_APPROX(duration, 0.99)` computes it from a compact summary of the values instead of sorting them all, which is accurate enough for latency and much cheaper on millions of spans.

Read percentiles with the number of requests behind them. With 57 orders, P99 is set by the slowest order or two; with 75,000 requests, it is a stable measure. A P99 of 2 seconds with a P50 of 90 ms says that about 1% of requests took 2 seconds or more, not that every request did, and not how many users were affected. Some spans are not requests at all: `flagd`'s flag streams stay open for up to 10 minutes, so their durations measure how long a stream was open, and they belong in a separate row, not in a service's latency.

## 7.3 Where failures start

When payment fails, every span on the path back to the user records an error: checkout's call to payment, checkout's `PlaceOrder`, the frontend's call to checkout and its own spans, the proxy, and the load generator. The trace view of Module 3 lets you find the deepest error by eye. For hundreds of failed orders, SQL needs a rule, and the obvious rules break on real traces:

- **The error span whose children have no error.** In the frontend, the span `POST /api/checkout` sits between two error spans but records no error itself. A rule that looks only at a span's direct children stops at the frontend's `POST` as well as at payment's `Charge`.
- **The error span that ended first.** The spans of a trace come from different services, whose clocks and SDKs can disagree by a fraction of a millisecond. In one measured trace, the frontend's call to checkout ended 0.7 ms before checkout's span that it waited for.

A rule that compares services is robust to both: a service's server span failed, and none of the calls that the same service made in that trace failed. Such a service did not fail because of another one. In SQL, `NOT EXISTS` keeps a row only when its subquery finds nothing:

```sql
SELECT s.service_name, s.span_name, COUNT(DISTINCT s.trace_id) AS failed_orders
FROM otel_traces AS s
WHERE s.span_kind = 'SPAN_KIND_SERVER'
  AND s.status_code = 'STATUS_CODE_ERROR'
  AND s.trace_id IN (... the traces of the failed orders ...)
  AND NOT EXISTS (
      SELECT 1 FROM otel_traces AS c
      WHERE c.trace_id = s.trace_id
        AND c.service_name = s.service_name
        AND c.span_kind = 'SPAN_KIND_CLIENT'
        AND c.status_code = 'STATUS_CODE_ERROR')
GROUP BY s.service_name, s.span_name
```

In Lab 7 the result is one row: `payment`'s `Charge`, for every failed order. The checkout service, the frontend, and the proxy each have a failed call of their own in each trace, so `NOT EXISTS` leaves them out. The query leaves out the orders of the last minute, whose spans may not all have reached Doris yet: a trace whose payment span is still on its way would have no starting service at all.

## 7.4 Window functions

A `GROUP BY` collapses rows into one per group. A **window function** computes a value for each row from a set of rows related to it, the window, and keeps every row. Its `OVER` clause says which rows:

- `ORDER BY` puts the rows of the window in order. `ROW_NUMBER() OVER (ORDER BY timestamp)` numbers the orders in time order.
- A frame limits the window to rows around the current one. `AVG(x) OVER (ORDER BY timestamp ROWS BETWEEN 9 PRECEDING AND CURRENT ROW)` averages the current order and the nine before it.
- `PARTITION BY` starts the window again for each group. `ROW_NUMBER() OVER (PARTITION BY service_name ORDER BY duration DESC)` numbers each service's spans from the slowest, and a filter `<= 3` on that number keeps the three slowest of each service, with their trace IDs. A global `ORDER BY ... LIMIT 3` would keep the three slowest of all services together.

With one to four orders a minute, a single minute's share of failed orders jumps between 0 and 100%. Lab 7 computes the share among the last ten orders for every order instead: it stays around 0.5 while the payment failure lasts. Module 8 alerts on such a share.

## 7.5 Traces of an LLM application

The spans in `otel_traces` describe requests between services. An application built on an LLM needs more about each request: the prompt that it sent to the model, the model's answer, the model and its parameters, the tokens that the model counted and what they cost, and the steps around the model call, such as the search for documents to put into the prompt. LLM observability platforms record a trace for each request, with an **observation** for each step: a span for the request, a retriever for the document search, a generation for the model call.

**Langfuse** is such a platform, with SDKs that send the observations as OpenTelemetry spans. **Litefuse** is an open-source fork of Langfuse that keeps its traces in Apache Doris instead of ClickHouse, with the same API, so applications send to it with Langfuse's SDKs, pointed at Litefuse's address. Litefuse does not collect logs, host metrics, or service spans: it adds to the DOG stack for LLM applications, it does not replace it.

Lab 7's application is a small assistant that answers questions about this course. Its model is simulated in the notebook, so the Lab needs no API key: the simulated model returns a prepared answer, and the code reports the prompt, the model name, the token counts, and an example cost itself. With a real model, Langfuse's integrations record them; the optional Lab 7A runs a small open model on your computer.

## 7.6 Litefuse on Doris

Litefuse runs as five containers: the web UI and API, a worker that loads the traces into Doris, PostgreSQL for users, projects, and API keys, Redis for the queues between them, and Silo, an S3-compatible object storage server, for the batches that the API receives. The API stores each batch and queues it; the worker loads it into Doris with Stream Load; the UI and the API read the traces back with SQL. In this course, Litefuse uses the DOG stack's Doris, in the database `litefuse`.

Two details of this setup:

- The worker loads through the FE, which redirects each Stream Load to the address at which the BE registered. The all-in-one Doris registered its BE as `127.0.0.1`, which, from another container, is that container itself. Giving the BE a private endpoint, `ALTER SYSTEM MODIFY BACKEND ... SET ("tag.location" = "default", "tag.private_endpoint" = "doris-obs:8040")`, makes the FE redirect to the host name that the client used, with the endpoint's port.
- When the first trace of a project arrives, Litefuse creates the project's tables, named after its ID: `spans_llm_app`, one row per observation, and `traces_scalar_llm_app`, one row per trace.

Their design uses Modules 4 to 6. `spans_llm_app` is a DUPLICATE table keyed on `trace_id`, `start_time`, and `span_id`, so that the observations of a trace are stored together. `traces_scalar_llm_app` is a UNIQUE table, because Litefuse writes a trace's row again as its observations arrive. Both are partitioned by day with AUTO PARTITION and bucketed by the trace ID with `BUCKETS AUTO`: a lookup of one trace reads one tablet of each partition that it scans. `spans_llm_app` has a synchronous materialized view of the tokens and costs of each trace by day, and inverted indexes on 14 columns, including `input` and `output` with the `unicode` parser, so that `input MATCH_ANY 'litefuse'` finds the prompts that mention Litefuse. A query on these tables, such as the tokens and the cost by user, uses the same SQL as any other table in Doris.

## Lab 7: Analyze Traces with SQL and Litefuse

Open [Lab 7: Analyze Traces with SQL and Litefuse](lab07_data_analysis_litefuse.ipynb). You:

1. Check the server spans in Doris.
2. Measure the incident: the failure rate and the latency of each operation, the failed against the successful orders, where each failure starts, and the share of failed orders over time.
3. Start Litefuse, and trace a small LLM application with the Langfuse SDK.
4. Find its traces in Doris, and look at the same traces in Litefuse's web UI.
5. Look at how Litefuse's tables use Doris, and search the prompts.
6. Practice: add up the traces, tokens, and cost of each user.

The [optional Lab 7A](optional07_trace_a_real_model.ipynb) gives the same application a real model: a small open model that runs on your computer, or OpenAI's API with your own key. You need the DOG stack and the demo from Module 1, with the payment failure turned on, and about 1 GB more of memory for Litefuse.

## Summary

- Rate, errors, and duration per operation, from the server spans, measure an incident across all requests. A gateway's rate hides the failure of one operation; failures can make requests faster.
- A percentile says how long a share of the requests took at most: P99 shows the slow tail, P50 the typical request. Read it with the number of requests, and keep long-lived streams apart.
- The service where a failure starts is the one whose server span failed while none of its own calls in that trace failed; `NOT EXISTS` finds it for every trace. Rules based on direct children or on end times break on real traces.
- A window function computes a value per row over related rows: `ORDER BY` orders them, a frame limits them, and `PARTITION BY` starts again per group.
- An LLM trace records prompts, answers, models, tokens, costs, and the steps of a request; Litefuse, a fork of Langfuse, keeps them in Doris and adds to the DOG stack.
- Litefuse's tables in the database `litefuse` hold the observations and the traces of each project, in DUPLICATE and UNIQUE tables partitioned by day and bucketed by trace ID, which any SQL client can query.

## Quiz 7

Open [Quiz 7: Trace Analysis and Litefuse](quiz07_analysis_and_litefuse.ipynb). It has six single-choice questions and needs no running environment.

Next module: [Module 8: Alerting with Grafana](../module08-alerting/course.md).

## References

- [OpenTelemetry: Traces](https://opentelemetry.io/docs/concepts/signals/traces/)
- [Apache Doris: Trace analysis](https://doris.apache.org/docs/4.x/observability/trace/)
- [Apache Doris: Window functions](https://doris.apache.org/docs/4.x/query-data/window-function/) and [PERCENTILE_APPROX](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/aggregate-functions/percentile-approx/)
- [Apache Doris: Stream Load practices in complex network environments](https://doris.apache.org/docs/4.x/data-operate/import/load-best-practices/stream-load-in-complex-network/)
- [Litefuse](https://github.com/litefuse/litefuse) and [Langfuse: Observability overview](https://langfuse.com/docs/observability/overview)
