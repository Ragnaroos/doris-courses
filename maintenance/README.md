# Notes for maintainers

These notes are for people who change the courses: what each course depends on,
what to recheck after a change, and what to do before a release. Learners do not
need them: each course's README and Labs have everything that a learner needs.
How to set up a clone, run the checks and the tests, and write notebooks and
quizzes is in [CONTRIBUTING.md](../CONTRIBUTING.md).

| Course | Notes |
| --- | --- |
| Real-time Analytics | [01-real-time-analytics/README.md](01-real-time-analytics/README.md) |
| Data Warehousing | [02-data-warehousing/README.md](02-data-warehousing/README.md) |
| Observability | [03-observability/README.md](03-observability/README.md), and [dog-stack.md](03-observability/dog-stack.md) for its environment |
| AI Integrations | [04-ai-integrations/README.md](04-ai-integrations/README.md) |
| All | [images.md](images.md): every image that the courses pull, and the build that was verified |

## Before a release

1. The checks and the offline tests pass (see CONTRIBUTING.md), and so does CI on
   `main`.
2. Every course runs from a clean environment, as a learner would run it: a fresh
   clone, the setup in the course README, no container, volume, or network of the
   course in Docker, and each notebook in a fresh kernel, like Restart & Run All.
   Each output agrees with its Expected result, and the web steps work as written.
   After the README's clean-up, nothing named with the course's prefix is left,
   and `docker volume ls -f dangling=true` lists no new volumes (a filter by name
   does not show anonymous volumes).
3. `python3 tools/check_image_digests.py` reports no image whose build changed or
   that its registry no longer has; [images.md](images.md) says what to do when it
   does.
4. If a change touches ports, container names, or volumes, the courses also run
   together: start the environment of each course without cleaning up the others,
   then clean them up one at a time, and check that each clean-up removes only the
   course's own containers, volumes, and networks.
5. The versions, resource needs, and times in each course README and its
   `course.yaml` match the runs.
6. Every new or changed screenshot has been checked by eye (see CONTRIBUTING.md).

## Changing a version

- Every external dependency names an exact version: the upstream commit of the
  Observability environment, the Python packages in each `requirements.txt`, and
  the image tags. An image tag names one release, such as `haproxy:3.0.30-alpine3.24`,
  never a tag that moves to newer releases, such as `haproxy:3.0-alpine` or `latest`.
  Images are not pinned by digest; [images.md](images.md) records the builds that
  were verified, and a new image or version goes there in the same commit.
- After changing the Doris image, run every Lab of the course, not only its
  environment cells: a statement that works on one version can fail on the next.
  Each course README states the Doris image, its digest, and the version that
  `SHOW FRONTENDS` reports; change them together.
- The notes of each course list what the course relies on in Doris 4.1.3.

## The system proxy on macOS

Python's urllib, requests, botocore, and httpx follow the macOS system proxy. When
the proxy's exceptions name `localhost` but not `127.0.0.1`, a request to a
course's own service at `http://127.0.0.1:<port>` also goes through the proxy. Two
things fail that way:

- boto3 sends an S3 upload with `Expect: 100-continue`. Through such a proxy, the
  body may never arrive, and the object store answers `RequestTimeout`.
- urllib writes the URL into the request line as given, so a URL without a path,
  such as `http://127.0.0.1:28082`, arrives without one, and some servers reject
  it with HTTP 400. Give every URL a path, at least `/`.

Data Warehousing adds `127.0.0.1` and `localhost` to `NO_PROXY` when it is imported,
because its Python code downloads nothing from the internet. Do not do this in the
shared runtime or in a course that downloads files: on macOS, setting any
`*_proxy` variable makes Python ignore the system proxy, and the downloads would no
longer use the learner's proxy. curl does not read the system proxy.
