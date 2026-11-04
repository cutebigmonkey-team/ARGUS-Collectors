# Hostless staged database verification

This directory runs synthetic PostgreSQL recovery tests. It does **not** collect
production sources or send publications to an archive. No private catalog or
connection string belongs in this repository.

Use PostgreSQL 17 in a dedicated collector-state database. Hostless PostgreSQL
uses PgBouncer: enable **session pooling** in database Settings first. The
PostgresJournal holds a session advisory lock for the complete collection pass;
transaction pooling is unsupported. No automatic reconnection is allowed.
The public endpoint must have a trusted TLS certificate; the driver requires
`sslmode=verify-full` and system trust roots.

Create a standalone **cron job** from the reviewed commit with Dockerfile
`deploy/hostless/Dockerfile`, working directory `/`. Choose one replica, at most
0.25 vCPU and 512 MB RAM, no volume, and a paused schedule. Set `DATABASE_URL`
as a private environment variable from the database's connection settings. Do
not share it with review deployments. Check the combined account cost before
creating the job: the database also consumes CPU and memory.

Manually run the job once. Its command `python /app/check_database.py` exercises
the same outbox contract against PostgreSQL as SQLite: persistence after process
loss, writer exclusion, duplicate and partial acknowledgement, transaction
rollback, rate limiting and cursor commit ordering. Tests create uniquely named
`argus_test_*` schemas and remove only those schemas. A failed setup may leave a
test schema for diagnosis; inspect ownership before removing it. Test failures
are logged by test name and counts, without driver exceptions or credentials.

The successful result is a completed run with exit code 0, `failures: 0` and
`errors: 0`. Do not interpret a successful image build or a running database as
proof of collector integration. Leave the cron schedule paused afterward.

For a later approved production process, install the `postgres` extra (or the
two requirements lockfiles) and run `argus-collectors --postgres --sources
/path/to/private/sources.json --metrics /tmp/metrics.json --max-sources 20`.
`DATABASE_URL` configures durable state; `ARGUS_IMPORT_URL` and
`ARGUS_IMPORT_TOKEN` still require a separately validated private import sink.
The metrics file is temporary; export it to a private monitor. SQLite remains
available with `--state`. This release does not automatically migrate existing
SQLite/Drive checkpoints or provide an archive endpoint.
