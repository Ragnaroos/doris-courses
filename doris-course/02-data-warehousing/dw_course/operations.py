"""Find the tagged queries of ordinary users in Doris's audit table."""

from .runtime import identifier
from .streaming import wait_for

AUDIT_QUERY = """SELECT `user`, db, state, error_code, return_rows, query_id, stmt
FROM __internal_schema.audit_log
WHERE `user` IN ({users}) AND stmt LIKE %s
ORDER BY `time`, query_id"""


def audit_records(lab, users, tag, *, expected, timeout=150, title="The users' queries in the audit table"):
    """Wait until the audit table holds `expected` queries of these users that contain `tag`; show and return them.

    Doris's audit plugin writes __internal_schema.audit_log in batches, at least
    once a minute (FE configuration audit_plugin_max_batch_interval_sec = 60), so a
    query appears up to about a minute after it ran. The filter on the users keeps
    root's own queries, and every statement of other accounts, out of the result.
    """
    users = [identifier(user) for user in users]
    statement = AUDIT_QUERY.format(users=", ".join(["%s"] * len(users)))
    params = (*users, f"%{tag}%")
    wait_for(lambda: lab.query(statement, params), lambda rows: len(rows) >= expected,
             description="Wait for the audit plugin to write the queries", timeout=timeout)
    return lab.sql(statement, params, title=title)
