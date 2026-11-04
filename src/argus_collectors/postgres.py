"""PostgreSQL outbox for hosts without durable local files.

Requires a direct connection or PgBouncer SESSION pooling, never transaction
pooling. A session advisory lock serializes workers across hosts. Do not reconnect
silently: losing the session must stop the pass before another import is sent.
"""
from contextlib import contextmanager
import hashlib
import re

from .journal import Journal


class PostgresJournal(Journal):
    outbox_order = 'sequence'

    def __init__(self, dsn, *, schema='argus_collectors', verify_tls=True):
        import psycopg
        from psycopg.rows import dict_row
        from psycopg import sql

        if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', schema):
            raise ValueError('invalid_journal_schema')
        if not dsn:
            raise ValueError('database_url_required')
        options = {'sslmode':'verify-full', 'sslrootcert':'system'} if verify_tls else {}
        # verify_tls=False is reserved for a disposable localhost CI service.
        if not verify_tls:
            from psycopg.conninfo import conninfo_to_dict
            if conninfo_to_dict(dsn).get('host') not in ('127.0.0.1', 'localhost', '::1'):
                raise ValueError('unencrypted_database_must_be_localhost')
        connection = psycopg.connect(dsn, autocommit=True, connect_timeout=15,
                                     prepare_threshold=None, row_factory=dict_row, **options)
        try:
            lock_id = int.from_bytes(hashlib.sha256(schema.encode()).digest()[:8], 'big', signed=True)
            locked = connection.execute('SELECT pg_try_advisory_lock(%s) AS locked', (lock_id,)).fetchone()
            if not locked['locked']:
                raise RuntimeError('collector_writer_already_running')
            self.backend_pid = connection.execute('SELECT pg_backend_pid() AS pid').fetchone()['pid']
            with connection.transaction():
                connection.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(schema)))
                connection.execute(sql.SQL('SET search_path TO {}, pg_catalog').format(sql.Identifier(schema)))
                connection.execute('''CREATE TABLE IF NOT EXISTS sources
                    (id TEXT PRIMARY KEY, url TEXT NOT NULL, checkpoint TEXT NOT NULL, health TEXT NOT NULL)''')
                connection.execute('''CREATE TABLE IF NOT EXISTS outbox
                    (id TEXT PRIMARY KEY, source_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL,
                     failures INTEGER NOT NULL DEFAULT 0, retry_at TEXT, last_error TEXT,
                     sequence BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE)''')
                connection.execute('CREATE TABLE IF NOT EXISTS seen (identity TEXT PRIMARY KEY, digest TEXT NOT NULL)')
                connection.execute('CREATE TABLE IF NOT EXISTS metrics (name TEXT PRIMARY KEY, value BIGINT NOT NULL)')
            self.db = _Connection(connection)
        except BaseException:
            connection.close()
            raise

    def check_session(self):
        if self.db.connection.execute('SELECT pg_backend_pid() AS pid').fetchone()['pid'] != self.backend_pid:
            raise RuntimeError('database_session_changed_use_session_pooling')


class _Connection:
    """Adapt only our constant SQLite placeholder syntax and transaction context.

    Values always remain separate bound parameters. Never pass SQL supplied by
    a source, registry or HTTP response through this adapter.
    """
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, parameters=()):
        return self.connection.execute(query.replace('?', '%s'), parameters)

    def __enter__(self):
        self.transaction = self.connection.transaction()
        return self.transaction.__enter__()

    def __exit__(self, *args):
        return self.transaction.__exit__(*args)

    def close(self):
        self.connection.close()


@contextmanager
def open_postgres(dsn):
    """Hide driver diagnostics, which can contain private connection/row data."""
    journal = None
    try:
        journal = PostgresJournal(dsn)
        yield journal
    except Exception:
        raise RuntimeError('postgres_pass_failed_check_private_database_health') from None
    finally:
        if journal is not None:
            journal.close()
