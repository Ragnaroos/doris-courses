# Observability: notes for maintainers

The course: [doris-course/03-observability](../../doris-course/03-observability/README.md).
How the course's override files change the upstream environment, and how to check
them after moving its pinned commit: [dog-stack.md](dog-stack.md).

## The incident that the course follows

- The whole course follows one incident: the demo's feature flag `paymentFailure`
  at `50%`, which the learner sets on the flag page in Lab 1, section 5. The flag
  page writes `doris-opentelemetry-demo/src/flagd/demo.flagd.json` in the upstream
  checkout; `lab.teardown()` restores the file with `git checkout`, and
  `lab.teardown(keep_data=True)` leaves it alone.
- Level 1's expected results rest on the flag: about half of the orders fail, one
  or two failed orders a minute, HTTP 500 in the access log, and the exception
  message on the payment span. A different incident means rewriting Labs 1 to 3 and
  the matching parts of their lessons.
- Level 2 rests on it too. Lab 4's summaries and alerts, and the incident window of
  Labs 5 to 7, which starts at the first failed order, need the flag to have been
  on. Lab 8, section 11, has the learner turn it off, which ends the story. After
  that, Lab 8, section 10, waits in vain for its alert; its waiting cell says that
  the flag must be at 50%. Labs 4 to 7 still work with the failures recorded
  earlier, but the share of failed orders in their window keeps falling.

## Expected results and measured numbers

- Level 2's expected results are written for the least data that a learner can
  have: Lab 1 followed straight away by Labs 2 to 8, so that Lab 4 starts with as
  few as five orders. Quantities are lower bounds, such as "tens of thousands or
  more", and a failure share says that chance can put it far from half. When
  changing the text, compare it with the output of a run from a clean environment.
- The numbers quoted in the lessons (the spans of a failed order, the error spans
  of each service, how busy the host CPU is) were measured on 2026-10-20 with Doris
  4.1.3 and demo 2.0.2. Measure them again after upgrading the demo or the upstream
  DOG stack.
- The bucket skew of Lab 5 (with 10 buckets by `service_name`, the largest tablet
  holds about 38% and one or two are almost empty) depends on the hash values of the
  service names and on the demo's traffic. After a demo upgrade, run the Lab and
  update the numbers in section 5.6 of the lesson. In a RANDOM table, each tablet
  holds 7% to 13% of a small table and closer to 10% of a large one: Doris 4.1.3
  writes each batch of a load to the next tablet in turn (`FIND_TABLET_EVERY_BATCH`
  in `VTabletFinder`), and the FE moves the starting tablet on for each partition
  (`TabletLoadIndexRecorderMgr`).

## Web steps

- The Grafana steps of Lab 3 (sections 2 to 8) and Lab 8 (sections 4 to 6), and the
  flag page in Lab 1, section 5, and Lab 8, section 11, are written for Grafana
  11.4.0 and demo 2.0.2. After changing them, or upgrading Grafana or the demo,
  follow them in a browser exactly as written.
- The Discover and Traces pages of the Doris App 1.0.5 build their time condition
  from the browser's local time, while the tables store UTC. Away from UTC, a
  relative range such as "Last 15 minutes" misses the newest rows, so Lab 3 prints
  an absolute range in UTC for the learner to enter. After upgrading the plugin,
  check whether this still happens before changing the text (section 3.2 of the
  lesson, Lab 3 section 2, and the question `fix_empty_time_range` of Quiz 3).
- Lab 8, section 10, creates the alert rules through Grafana's provisioning API. A
  rule with a fixed uid has to be created first with a POST to
  `/api/v1/provisioning/alert-rules`; a PUT of its group only updates rules whose
  uid exists, and otherwise fails with HTTP 500 "could not find alert rule".
  `lab.provision_alert_rule_group()` does both. The header
  `X-Disable-Provenance: true` keeps the rules editable in the web UI. Check both
  after upgrading Grafana.

## Doris 4.1.3 behavior that the course relies on

Measured on 4.1.3 or read in its source (commit `7126cf65d96`); recheck after
changing the Doris version:

- `UTC_DATE()` is not folded when the query is planned, so a filter on it cannot
  prune partitions (section 5.3).
- With `BUCKETS AUTO`, when the estimate for a new partition is less than half of
  the previous partition's bucket count, the new partition keeps the previous count
  (`DynamicPartitionScheduler.checkAndFixAutoBucketCalcNumIsValid`; section 5.7,
  Lab 5 section 2, and Quiz 5).
- A synchronous materialized view cannot reuse a column name of its base table or
  of another view, and `CREATE MATERIALIZED VIEW IF NOT EXISTS` does not skip a view
  that exists, so Lab 6, section 4, drops the view first.
- Rows that a `MATCH_PHRASE` or `LIKE` filter removes without an index are counted
  in `RowsExprPredFiltered` (`SegmentIterator::_execute_common_expr`,
  `SCAN_FILTER_COUNTERS`).
- `ALTER TABLE ... SET ("compression" = ...)` fails with "Unknown table property".
- The table property `group_commit_mode` exists from 4.1.

## Clean-up

The demo's jaeger, kafka, and prometheus images declare volumes that the demo's
Compose file does not mount (`/tmp`, three for kafka, and `/prometheus`), so Docker
creates anonymous volumes for them. The next start does not reuse them, so
`stop_demo()` and `teardown()` remove the demo with `--volumes`, also with
`keep_data=True`. A filter by name does not find anonymous volumes: compare
`docker volume ls -f dangling=true` before and after, and do it again after
upgrading the demo.

## Linux

The course has run only on Docker Desktop for macOS. What follows was checked on
2026-10-21 by reading the code and by simulating Linux on Docker Desktop:

- The FE's log directory is bind-mounted to `.runtime/doris-logs/fe`. The FE writes
  its logs as root and creates a `profile/` directory. On Docker Engine for Linux,
  those files belong to root on the host too, and the learner cannot delete
  `.runtime/` without sudo; Docker Desktop maps the owner to the current user, so a
  Mac does not show this. Step 6 of `teardown()` therefore runs
  `chown -R --reference=/logs /logs` with the Doris image after removing the DOG
  stack, which hands the files back to the owner of the directory that
  `prepare_environment()` created as the learner. It uses `--reference` rather than
  the learner's uid because, with rootless Docker, the directory appears as root's
  inside the container. This was checked on a named volume, which lives on the ext4
  disk of Docker Desktop's VM and keeps owners as Linux does: before the change, the
  learner could not write to `profile/`; after it, every file belonged to the
  learner.
- Open files: Docker Engine 29 (containerd 2.1.5 and later) sets a container's
  default `ulimit -n` to 1024 on Linux; Docker Desktop sets 1048576. Doris started
  with `--ulimit nofile=1024:524288` had 524288 for both the BE and the FE: the
  embedded JVM raises the soft limit to the hard one, and `start_be.sh` turns off
  `MaxFDLimit` only on macOS. An idle BE has 764 files open.
- `vm.max_map_count`: Doris asks for at least 2000000, and the image sets
  `SKIP_CHECK_ULIMIT=true`, so the start does not check it. Docker Desktop's VM has
  262144. Linux defaults to 65530 (Ubuntu 22.04, Debian 12); Ubuntu 24.04 and
  Fedora 39 and later have 1048576. An idle BE has 3,959 maps; the course's load was
  not measured. When someone runs the course on Linux, look first for mmap failures
  in the BE's log.
- Checked and fine: all 34 images are published for linux/amd64 and linux/arm64
  (`docker buildx imagetools inspect`); Grafana's Doris App has only a frontend, with
  no binary per architecture; flagd-ui runs as root and can write the flag file;
  Module 2's log collector runs with `--user`, as the learner.
- Not considered: rootless Docker and Podman (the demo's Collector mounts
  `/var/run/docker.sock`); SELinux (no bind mount has `:z`); a Linux VM on an Apple
  silicon Mac (`.env.arm64` is added only on macOS).
