# Images

Every image that the courses pull, by the exact tag that the courses name, with
the digest of the build that the last full run of the courses used (2026-10-23).

The courses pull images by tag, not by digest, so a learner gets the build that a
tag points to on the day they pull it. A tag names one version, such as
`haproxy:3.0.30-alpine3.24`, never a tag that moves to newer versions, such as
`haproxy:3.0-alpine` or `latest`. Its publisher can still push a new build of the
same version under the same tag, usually with operating-system patches, and an old
tag can disappear from its registry. Docker's local cache hides both: a computer
that already has an image keeps running its old build.

Before a release, ask the registries what each tag points to now:

```bash
python3 tools/check_image_digests.py
```

It lists each image whose build changed and each image that its registry no longer
has. For a changed image, pull the new build, run the Labs in the "Used by" column
again from a clean environment, and then record the new digests with
`python3 tools/check_image_digests.py --update`. A missing image has to be replaced:
Data Warehousing and Observability use Silo because MinIO no longer publishes its
images.

When a course starts to use another image, or another version of one, change this
table in the same commit, with `new` in place of the digest until `--update` fills it
in. `python3 tools/check_image_digests.py --offline`, which CI runs, checks that the
table has every image that the courses' Compose files and Dockerfiles pull, and that
the courses name no other tag of a listed image. The images marked "named upstream"
come from the OpenTelemetry demo's own files, at the commit that Observability pins:
check them by hand when that commit moves.

| Image | Used by | Digest |
| --- | --- | --- |
| `apache/doris:all-in-one-4.1.3` | Every course: every Lab | `sha256:82a5cabc7900ebcd3d080412d636c0cebd6602799fffe2605c652b2ea7d42609` |
| `apache/kafka:3.9.1` | Real-time Analytics: Lab 3 | `sha256:4ceccc577f03f51f6af8dbfda55194d0d892f4fa7913ffbded567ce3895622ed` |
| `haproxy:3.0.30-alpine3.24` | Real-time Analytics: Lab 9 | `sha256:cf3af0facf7eb22b9fee463daf0fbc07ead740b8150696dce724264faf7b4318` |
| `metabase/metabase:v0.59.6.3` | Real-time Analytics: the optional Metabase lab of Module 1 | `sha256:73e6cf0db674281c68b2105c921820e5be7d6a4c8c94fe4f2f76edee92c161f6` |
| `pgsty/silo:RELEASE.2026-10-18T00-00-00Z` | Data Warehousing: Lab 4's lake, the Module 4–5 extension, and Lab 13's backup; Observability: Lab 7 (Litefuse) | `sha256:2636fc4155d9a7e41ff58cdb65ddd13ba9304e67184e13c25bc5cb34016269d7` |
| `apache/iceberg-rest-fixture:1.10.0` | Data Warehousing: Lab 4's lake | `sha256:df2e9dd421928b7aab01557678ce8e2bb73064d0e253baebd72adad3439ffc2e` |
| `apache/kafka:3.9.0` | Data Warehousing: Lab 5A | `sha256:fbc7d7c428e3755cf36518d4976596002477e4c052d1f80b5b9eafd06d0fff2f` |
| `mysql:8.0.33` | Data Warehousing: Lab 5B | `sha256:ea68e51ffe9b96fef6076f1218af11301aeaf13c6201e0ec9aaef5791d5ddc5d` |
| `flink:1.20.1-scala_2.12-java11` | Data Warehousing: Lab 5B, as the base of `doris-course-flink` | `sha256:b9d7f306720ef6e8ba1b4cc0b3474197ba9fe3169e18ef4089f59930fcb12f26` |
| `apache/superset:4.1.2` | Data Warehousing: Lab 11's dashboard, as the base of `doris-course-superset` | `sha256:15e110b8533d3cb6a0d529512ea71252b0ac62e3f72b1f7a5000f1361822ac26` |
| `otel/opentelemetry-collector-contrib:0.144.0` | Observability: the DOG stack's Collector and Module 2's collectors, every Lab | `sha256:213886eb6407af91b87fa47551c3632be1a6419ff3a5114ef1e6fc364628496f` |
| `grafana/grafana:11.4.0` | Observability: the DOG stack, every Lab | `sha256:d8ea37798ccc41061a62ab080f2676dda6bf7815558499f901bdb0f533a456fb` |
| `axllent/mailpit:v1.31.3` | Observability: the DOG stack, every Lab | `sha256:ed9b00c609e77e99c79b93f1178255ebc271868920f2c69a8d166bd5634ed10d` |
| `ghcr.io/open-telemetry/demo:2.0.2-accounting` | Observability: the demo, every Lab (named upstream) | `sha256:5dd4d4655a1c2bb8868e691c8c37dbedc0ffd7461c36a99417dd89b4b7a2d140` |
| `ghcr.io/open-telemetry/demo:2.0.2-ad` | Observability: the demo, every Lab (named upstream) | `sha256:7f6c3fda7fed57ea4dbca92d801d8a3c01909a848b33170f16494da89e90343c` |
| `ghcr.io/open-telemetry/demo:2.0.2-cart` | Observability: the demo, every Lab (named upstream) | `sha256:2ec7601655cbe5d295d0e5bd85f5b8acaf3b0f2651f8ea33ba1150edbf6000bf` |
| `ghcr.io/open-telemetry/demo:2.0.2-checkout` | Observability: the demo, every Lab (named upstream) | `sha256:5ab0d7b9003206a32c72ef48b42a535c3f70565251d7d832f86fe9f249f16635` |
| `ghcr.io/open-telemetry/demo:2.0.2-currency` | Observability: the demo, every Lab (named upstream) | `sha256:03fb9bf6d8072cacabdf018396f6d48082ad5f824443965573a064c7faecd944` |
| `ghcr.io/open-telemetry/demo:2.0.2-email` | Observability: the demo, every Lab (named upstream) | `sha256:270c487983d8aaf111df31eb1075ddc366d9eafec1e4c937899d05be9a6dd4b3` |
| `ghcr.io/open-telemetry/demo:2.0.2-flagd-ui` | Observability: the demo, every Lab (named upstream) | `sha256:655da6a8735b7bb7da2c36c8992387d03ae06420f2a06fbc499f2591889c1d03` |
| `ghcr.io/open-telemetry/demo:2.0.2-fraud-detection` | Observability: the demo, every Lab (named upstream) | `sha256:8b0a841c19f583a83b150bbd0609d85b3f09d19a75888d716bb234098f3385b4` |
| `ghcr.io/open-telemetry/demo:2.0.2-frontend` | Observability: the demo, every Lab (named upstream) | `sha256:3a0c7649f63d59656f6ba76fcd7ec79c1974cc3db0ae624efdf38fbdc8a14d4c` |
| `ghcr.io/open-telemetry/demo:2.0.2-frontend-proxy` | Observability: the demo, every Lab (named upstream) | `sha256:9cc478aa226b33cd80af46971683bfa963283a4309adf36d39706a406641ac7e` |
| `ghcr.io/open-telemetry/demo:2.0.2-image-provider` | Observability: the demo, every Lab (named upstream) | `sha256:bfa0b940f79df27c564778bc70eaf506c7234fcef328d8139e30d0f592e8fbfc` |
| `ghcr.io/open-telemetry/demo:2.0.2-kafka` | Observability: the demo, every Lab (named upstream) | `sha256:0f1270d986ffd18ce73ca56e6c9b94077929fb31ae2be101036663213da0a4a1` |
| `ghcr.io/open-telemetry/demo:2.0.2-load-generator` | Observability: the demo, every Lab (named upstream) | `sha256:d257288d374e1f6ebceb9997049fd4a31437037e85fc6dccaedd0c4810e1ca11` |
| `ghcr.io/open-telemetry/demo:2.0.2-payment` | Observability: the demo, every Lab (named upstream) | `sha256:33f327b357617379bfa3b292f430d1f06e66e2872494125a40bae14d8fe57d87` |
| `ghcr.io/open-telemetry/demo:2.0.2-product-catalog` | Observability: the demo, every Lab (named upstream) | `sha256:050a0fc2026b75cc8716cbd5daf9c9e5fd552808a59928a6bfca18bfb8edd2d5` |
| `ghcr.io/open-telemetry/demo:2.0.2-quote` | Observability: the demo, every Lab (named upstream) | `sha256:38f9d9abe0808c154011f3286754c848977bb9816923bdddd6dd39043c1e2139` |
| `ghcr.io/open-telemetry/demo:2.0.2-recommendation` | Observability: the demo, every Lab (named upstream) | `sha256:2ca9d61f520e94c7d28fd77d9715483513773a248bf10e8612885868b2c147e5` |
| `ghcr.io/open-telemetry/demo:2.0.2-shipping` | Observability: the demo, every Lab (named upstream) | `sha256:e29cb4277ebd2f0532eb43ae704038cbc47f220205fdb389ac8292a6356d1a0a` |
| `ghcr.io/open-feature/flagd:v0.12.1` | Observability: the demo, every Lab (named upstream) | `sha256:9595dffe7a9e33d15f6200e1b1ec88b6f98dc697c9f64564a2a5e35ab5ec7943` |
| `valkey/valkey:8.1.10-alpine3.24` | Observability: the demo, every Lab | `sha256:081c2f5cb575efc901aa80ff9cdbd1ec6a301682fd35e1ebb4b0990a4a4a8507` |
| `jaegertracing/all-in-one:1.66.0` | Observability: the demo, every Lab (named upstream) | `sha256:9864182b4e01350fcc64631bdba5f4085f87daae9d477a04c25d9cb362e787a9` |
| `ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-contrib:0.120.0` | Observability: the demo's Collector, every Lab (named upstream) | `sha256:85ac41c2db88d0df9bd6145e608a3cb023f5d8443868adbfbbf66efb51087917` |
| `quay.io/prometheus/prometheus:v3.2.0` | Observability: the demo, every Lab (named upstream) | `sha256:5888c188cf09e3f7eebc97369c3b2ce713e844cdbd88ccf36f5047c958aea120` |
| `litefuse/litefuse-web:26.3.0` | Observability: Lab 7 | `sha256:7bf5f5384e9f4c9a7081e35ac08378c564605d7bea9675da2c748d5f018f79b5` |
| `litefuse/litefuse-worker:26.3.0` | Observability: Lab 7 | `sha256:334c72e3312186b7653c5a79cb81f2b3fb4dbc0159ecf3e89ba372ba7880a739` |
| `postgres:17.11` | Observability: Lab 7 (Litefuse) | `sha256:b8faeff7712663c2773a190181e1246e37e364b887611c04658c28b44e2408fe` |
| `redis:7.4.11` | Observability: Lab 7 (Litefuse) | `sha256:44960b3100c48159a66d28c18b0588c193492e25f7551d60e51dd464fc3eca5b` |
| `ghcr.io/ggml-org/llama.cpp:server-b11429` | Observability: the optional Lab 7A | `sha256:2f8ebc2dde83c4bd7e5c6d61efa57965e0d5a79d29802c246c4593740d9c04c1` |
| `busybox:1.37.0` | Observability: Lab 8 | `sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e` |
