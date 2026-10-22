# Single-node integrated sandbox

Level 1, Level 2, and the Level 3 query-acceleration module reuse the official
`apache/doris:all-in-one-4.1.3` image, one `doris-rta` Docker network, and the
named volumes `doris-rta-fe-meta` and `doris-rta-be-storage`. The container is
named `doris-rta`; its host ports are listed in the course README.

This is a reusable teaching and integration-test environment containing one FE
and one BE. It is not a production-ready cluster. Stop/start operations retain
the named volumes; module cleanup must not delete them.
