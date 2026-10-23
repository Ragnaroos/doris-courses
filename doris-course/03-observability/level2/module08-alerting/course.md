# Module 8: Alerting with Grafana

| Course information | Value |
| --- | --- |
| Course | Observability with Apache Doris · Level 2 |
| Doris | Apache Doris 4.1.3 |
| Grafana | Grafana 11.4.0, with Mailpit as the local mail server |
| Environment | The DOG stack and the OpenTelemetry demo of Module 1, with the payment failure turned on |
| Estimated time | About 95 minutes: reading 30, Lab 55 (three waits of 3 to 6 minutes), quiz 10 |

[Course README](../../README.md) · [Open Lab 8](lab08_alerting.ipynb) · [Open Quiz 8](quiz08_alerting_rules.ipynb)

## Module goal

Alert on the host's CPU and on the payment incident with Grafana rules that query Doris, route the alerts to an inbox, keep a rule as code, and end the incident by watching its alert resolve.

## Learning objectives

After completing this module, you will be able to:

1. Write an alert query that measures what the alert is about.
2. Predict how an alert instance moves between Normal, Pending, and Alerting, and back.
3. Separate what a contact point, a notification policy, and an alert rule each decide.
4. Keep the labels that an alert needs to be acted on.
5. Decide how a rule treats missing data, and detect a source that stops reporting.
6. Keep alert rules as code, and send them to Grafana.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 8.1 From a dashboard to an alert | 3 min | What alerting adds |
| 8.2 The alert query | 5 min | A query that measures the right thing, per instance |
| 8.3 Rules, evaluation, and states | 6 min | When an alert fires and resolves |
| 8.4 Contact points and notification policies | 5 min | Who is told, how, and how often |
| 8.5 When data stops | 4 min | No data, and silent sources |
| 8.6 Rules as code | 4 min | Export, provisioning files, and the HTTP API |
| 8.7 Alerting on what users see | 3 min | The failed orders, and the end of the incident |
| Lab 8 | 55 min | Two rules that fire and resolve, and the end of the incident |
| Quiz 8 | 10 min | Six questions on these objectives |

## 8.1 From a dashboard to an alert

The dashboard of Module 3 shows the incident to whoever looks at it. Nobody looks at dashboards all night, so a system that must stay healthy needs **alerts**: queries that run on a schedule and notify someone when their result crosses a line. In the DOG stack, Grafana's alerting runs them against Doris, through the same data source as the panels. Grafana's alerting has three parts, and Lab 8 sets up each:

| Part | Decides |
| --- | --- |
| **Alert rule** | What to evaluate, how often, and when the result counts as firing |
| **Notification policy** | Which alerts go to which contact point, grouped and timed how |
| **Contact point** | How to notify: email to an address, a chat message, a webhook |

## 8.2 The alert query

A rule's query must measure what the alert is about, and return one value for each thing that can be in trouble.

**Measure the right thing.** The first rule of Lab 8 alerts when the host's CPU stays busy. Module 3 showed how the DOG Collector stores host CPU: `system.cpu.utilization` in `otel_metrics_gauge`, one row per core and state, each the share of time that the core spent in that state. A rule that compares every row with 90% fires on idle cores, whose `idle` rows are close to 1, and the quieter the host, the more rows pass. The query must compute the busy share: 1 minus the average `idle` share of the host's cores in the last minute, from one source per host, the DOG Collector's host metrics receiver with its `host.name`:

```sql
SELECT CAST(resource_attributes['host.name'] AS STRING) AS host,
       ROUND((1 - AVG(value)) * 100, 1) AS cpu_busy_percent
FROM otel_metrics_gauge
WHERE metric_name = 'system.cpu.utilization'
  AND attributes['state'] = 'idle'
  AND scope_name LIKE '%hostmetricsreceiver%'
  AND resource_attributes['host.name'] IS NOT NULL
  AND timestamp >= UTC_TIMESTAMP() - INTERVAL 1 MINUTE
GROUP BY host
```

**One row per instance.** Grafana makes an **alert instance** of each row of a query in Table format, and labels it with the row's text columns. `GROUP BY host` gives each host its own instance, labeled `host=...`: a notification can then say which host is busy, a policy can group by host, and two hosts can fire and resolve independently. A query that averaged all hosts into one value would fire without saying where.

**A window that ends now.** The query reads the last minute before `UTC_TIMESTAMP()`, not the minute before the newest row, as the analysis queries of earlier modules did. When a host stops reporting, its rows leave the window and the query returns nothing for it, instead of comparing its last samples with the threshold again and again. Section 8.5 shows what Grafana does then. The tables store UTC, so the window starts from `UTC_TIMESTAMP()`.

## 8.3 Rules, evaluation, and states

A rule belongs to an **evaluation group** in a folder, and Grafana evaluates every rule of the group at the group's interval, 30 seconds in Lab 8. Each evaluation runs the query (A), then the expressions: here a **Threshold** expression (C), `A IS ABOVE 90`, which is the rule's condition. A query in Table format already returns one number per instance, so the Reduce expression that Grafana proposes is not needed.

An instance moves between states:

- **Normal**: the condition is false.
- **Pending**: the condition is true, but has not been true for the whole **pending period** yet. One evaluation with the condition false returns the instance to Normal, and the period starts again.
- **Alerting** (firing): the condition has been true at every evaluation for the pending period. Grafana sends a notification.
- Back to **Normal** when the condition is false again; there is no pending period on the way back, and Grafana sends a resolved notification.

The pending period trades speed for quiet. Lab 8 uses 1 minute so that you can watch the rule fire; production rules often wait longer, such as 10 minutes, so that a short peak does not wake anyone. A sustained condition is broken by any evaluation below the threshold, so three high samples in ten minutes are not ten minutes above it.

A value that hovers around the threshold makes an instance **flap**: firing, resolved, firing again. A **recovery threshold** on the Threshold expression helps: for example, fire above 90, but resolve only below 80.

## 8.4 Contact points and notification policies

A **contact point** says how to send: Lab 8's `doris-course-email` sends email to `oncall@example.com` through Mailpit, a local mail server that the DOG stack starts, so no email leaves your computer. Grafana needs SMTP settings to send email at all; the DOG stack sets them with `GF_SMTP_*` environment variables. The contact point's **Test** sends a test notification: it proves that Grafana can deliver to that address, once. It does not prove that a rule fires when it should, that its alerts take this route, or that a resolved notification follows; Lab 8 checks each of those separately.

A **notification policy** decides, by the labels of an alert, which contact point it goes to, and how notifications are grouped and timed. Alerts that match no other policy follow the default policy. Lab 8 adds a child policy that matches `team = doris-course`, and every rule of the course carries that label:

| Policy setting | Lab 8 | Meaning |
| --- | --- | --- |
| Group by | `grafana_folder`, `alertname`, `host` | Each host's alerts of a rule form a group, with one notification |
| Group wait | 10s | Wait for other alerts of a new group before the first notification |
| Group interval | 1m | Wait before notifying about changes in a group, such as a resolved alert |
| Repeat interval | 4h | Repeat the notification of a group that keeps firing |

The rule decides what fires, the policy where and when it goes, and the contact point how. The labels connect them: keep the labels that a responder needs, such as `host` and `severity`, and route on them.

Two more tools keep notifications in check. A **silence** suppresses the notifications of alerts that match its labels for a time, for example while someone works on the problem; the email of every alert has a link to create one. A **mute timing** suppresses notifications of a policy during recurring times, such as a weekly maintenance window. Both stop notifications only: Grafana keeps evaluating the rules, and the instances keep their states.

## 8.5 When data stops

The CPU query returns nothing when the host stops reporting. Without rows, there is no value to compare with 90, and the rule's setting **Alert state if no data or all values are null** decides what happens. With the default, **No Data**, the rule reports no data, and Grafana raises a separate alert, `DatasourceNoData`, labeled with the data source and the query instead of a host, through the same policy. Lab 8 stops the DOG Collector to watch it. **Alert state if execution error or timeout**, `Error` by default, does the same when the query itself fails.

No Data applies only when the query returns nothing at all. If one of several hosts stopped reporting, the query would still return the others: the silent host's instance would disappear after two evaluations without a notification. Missing telemetry is not a low value, and it is not proof of health; watch it with a query of its own, such as the seconds since each host's newest sample, as the exercise of Lab 8 does. Choose the no data state by what a missing value means: for the CPU of a host, a problem; for the share of failed orders when no order arrived, nothing failed, so that rule uses `OK`.

## 8.6 Rules as code

A rule that exists only in a web page is hard to review, copy, or rebuild. Grafana can **export** a rule in the format of its provisioning files, YAML that names the group, the folder, the interval, and every setting of the form. Grafana loads such files from its `provisioning/alerting` directory when it starts, and shows the rules as provisioned: the file stays their one source, and the web page does not let you edit them.

The **provisioning HTTP API** takes the same content as JSON:

| Request | Does |
| --- | --- |
| `POST /api/v1/provisioning/alert-rules` | Creates a rule, with the `uid` that you choose |
| `PUT /api/v1/provisioning/folder/{folder uid}/rule-groups/{group}` | Sets a group's interval and rules: afterwards, the group holds exactly the rules that you sent |
| `GET /api/v1/provisioning/alert-rules/{uid}/export` | Exports a rule in the file format |

A group's `PUT` updates only rules whose `uid` exists, so a new rule with a fixed uid is created with `POST` first. Writing needs a user with the right permissions, such as the admin. Rules created through the API are provisioned too; the header `X-Disable-Provenance: true` keeps them editable in the web page. Lab 8 writes its second rule as JSON in the notebook and sends it with `lab.provision_alert_rule_group(...)`, which shows each request. A team keeps such files in version control, reviews changes to them like code, and applies them to every Grafana it runs.

## 8.7 Alerting on what users see

The CPU rule watches a possible cause of trouble. The second rule of Lab 8 watches the trouble itself: the share of the orders that ended in the last 5 minutes that failed, above 10%. Five minutes hold about ten orders, so the share does not jump between 0 and 100 with every order, and a pending period of 1 minute filters single unlucky minutes. A rule on a symptom that users feel, failed orders, catches failures whatever their cause, including this one, where the host was idle, the services sent no error logs, and the store showed nothing to its customers.

The rule fires within about two minutes, because the incident has been running since Module 1. Then the incident ends where it started: you set `paymentFailure` back to `off` in the flag page, and every new order succeeds. The rule's window still holds the failed orders of the last 5 minutes, so the alert resolves only when enough of them have left it, within about 5 minutes, followed by the resolved email. That delay is the price of a window long enough to be stable.

## Lab 8: Configure Grafana Alerting

Open [Lab 8: Configure Grafana Alerting](lab08_alerting.ipynb). You:

1. Check the host metrics, see why a row is not a measure of a busy host, and run the alert query.
2. Create a contact point and test it, and route the course's alerts with a notification policy.
3. Create the rule `Host CPU busy`, make the CPU busy, and watch it fire and resolve, with emails.
4. Stop the host metrics and watch the rule report no data.
5. Export the rule as code, then write the rule `Failed orders` as code, send it to Grafana, and watch it fire.
6. Turn the payment failure off and watch the alert resolve.
7. Practice: find a host that stopped reporting.

Sections 4 to 6 and 11 of the Lab take place in web pages. You need the DOG stack and the demo from Module 1, with the payment failure turned on.

## Summary

- An alert query must measure the thing it is about, such as 1 minus the average idle share of a host's cores, and return one row per instance, labeled with what a responder needs, such as the host.
- Grafana evaluates a group's rules at its interval; an instance becomes Pending when its condition is true and Alerting after the whole pending period, and returns to Normal at the first evaluation without the condition. A recovery threshold reduces flapping.
- The rule decides what fires, the notification policy routes alerts by their labels and times their notifications, and the contact point delivers. A test notification proves only delivery.
- With no data, a rule raises a separate alert by default, but only when its query returns nothing at all; a host that goes silent among others needs a check of its own.
- Rules can be exported, provisioned from files, and created through the HTTP API; a team keeps them as code.
- A rule on what users see, the share of failed orders, caught the incident whatever its cause, and resolved once the cause was gone.

## Quiz 8

Open [Quiz 8: Alerting with Grafana](quiz08_alerting_rules.ipynb). It has six single-choice questions and needs no running environment.

Next: this is the last module of the course. Over eight modules you started an incident, collected its evidence into Doris, investigated it in Grafana, kept its numbers in tables designed for its questions, measured it with SQL, and alerted on it. The [course README](../../README.md) explains how to stop and remove the environment.

## References

- [Grafana: Alerting overview](https://grafana.com/docs/grafana/v11.4/alerting/) and [queries and conditions, with recovery thresholds](https://grafana.com/docs/grafana/v11.4/alerting/fundamentals/alert-rules/queries-conditions/)
- [Grafana: State and health of alerts](https://grafana.com/docs/grafana/v11.4/alerting/fundamentals/alert-rule-evaluation/state-and-health/)
- [Grafana: Notification policies](https://grafana.com/docs/grafana/v11.4/alerting/fundamentals/notifications/notification-policies/), [silences](https://grafana.com/docs/grafana/v11.4/alerting/configure-notifications/create-silence/), and [mute timings](https://grafana.com/docs/grafana/v11.4/alerting/configure-notifications/mute-timings/)
- [Grafana: Use the HTTP API to manage alerting resources](https://grafana.com/docs/grafana/v11.4/alerting/set-up/provision-alerting-resources/http-api-provisioning/) and [file provisioning](https://grafana.com/docs/grafana/v11.4/alerting/set-up/provision-alerting-resources/file-provisioning/)
- [Grafana: Configure email (SMTP)](https://grafana.com/docs/grafana/v11.4/setup-grafana/configure-grafana/#smtp)
- [Mailpit](https://mailpit.axllent.org/)
