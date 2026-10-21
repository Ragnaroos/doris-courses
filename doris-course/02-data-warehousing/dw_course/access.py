"""Temporary ordinary users for the access drills of Labs 12 and 14.

A drill proves what a consumer can read only when it runs as the consumer, not as
root. temporary_user() creates a user with a random name and password, grants it
roles, and drops it again, also when the cell fails. The password stays in
memory and is never shown; the SQL that the helper runs is shown with it masked.
"""

import os
import secrets
from contextlib import contextmanager

import pymysql

from .runtime import identifier
from .ui import in_notebook, show_sql

# The errors with which Doris refuses a statement for lack of a privilege.
DENIED = ("Access denied", "Permission denied")


class Reader:
    """An ordinary user of the course sandbox, with its own connections."""

    def __init__(self, lab, name, password):
        self.lab = lab
        self.name = name
        self.identity = f"'{name}'@'%'"
        self._password = password

    def connect(self, **session):
        """Open a connection as this user to the lab database, with these session variables."""
        connection = pymysql.connect(
            host=os.environ["DW_HOST"], port=int(os.environ["DW_PORT"]), user=self.name,
            password=self._password, database=self.lab.database, charset="utf8mb4",
            autocommit=True, connect_timeout=5, read_timeout=120,
        )
        try:
            with connection.cursor() as cursor:
                for name, value in session.items():
                    cursor.execute(f"SET {identifier(name)} = %s", (value,))
        except BaseException:
            connection.close()
            raise
        return connection

    def query(self, statement, params=None):
        """Run one statement as this user and return its rows."""
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(statement, params)
                return list(cursor.fetchall())
        finally:
            connection.close()

    def denied(self, statement, params=None):
        """Return Doris's message when it refuses the statement for a missing privilege, None when it runs.

        Any other error is raised: a typo is not a working restriction.
        """
        try:
            self.query(statement, params)
        except pymysql.err.OperationalError as error:
            message = str(error.args[-1])
            if any(text in message for text in DENIED):
                return message.split("detailMessage = ", 1)[-1].strip()
            raise
        return None


@contextmanager
def temporary_user(lab, *roles, prefix="course_reader_l3"):
    """Create an ordinary user with these roles, yield it as a Reader, and drop it at the end."""
    name = identifier(f"{prefix}_{secrets.token_hex(4)}")
    identity = f"'{name}'@'%'"
    password = secrets.token_urlsafe(18)
    statements = [f"CREATE USER {identity} IDENTIFIED BY '<a generated password, not shown>'"]
    statements += [f"GRANT '{role}' TO {identity}" for role in roles]
    if in_notebook():
        show_sql(f"A temporary user, {name}", ";\n".join(statements) + ";")
    created = False
    try:
        # %% escapes the host wildcard while PyMySQL fills in the password.
        lab.execute(f"CREATE USER '{name}'@'%%' IDENTIFIED BY %s", (password,))
        created = True
        for role in roles:
            lab.execute(f"GRANT '{identifier(role)}' TO {identity}")
        yield Reader(lab, name, password)
    finally:
        password = None
        if created:
            lab.execute(f"DROP USER IF EXISTS {identity}")
