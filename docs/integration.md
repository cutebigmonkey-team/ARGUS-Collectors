# Private integration contract

The existing deployment's approved archive writer remains authoritative. This
library does not contain that writer, its credentials, source catalog or URLs.

For an HTTPS adapter, the request is `POST` to an operator-configured endpoint:

```json
{"schema":"argus-collector-batch-v1","batch_id":"opaque-uuid","posts":[]}
```

Authenticate with `Authorization: Bearer ...`; set `Idempotency-Key` to the batch
ID. The receiver must validate the schema and source authorization, atomically
upsert all records by `canonical_key`, and store a receipt with the same batch
ID. Only after durable persistence/readback should it return:

```json
{"batch_id":"opaque-uuid","accepted_ids":[],"inserted_ids":[]}
```

`accepted_ids` must exactly match all submitted canonical keys. `inserted_ids`
is the subset newly inserted on the first processing of that batch. Replays
return that original receipt, including the original inserted IDs. Enrichment
of an already archived identity must not create a second publication.

The client refuses redirects so authentication cannot be forwarded to another
origin. Non-2xx responses, invalid JSON and partial acknowledgements retain the
outbox and previous cursor. Retry-After on 429/503 is honored alongside bounded
exponential backoff. Failed or partial collection never advances its cursor.

Private metrics distinguish discovered, acknowledged and newly inserted records,
queue depth, deduplicated identities, error/rate-limit counts, last success per
source and detection lag. The host must export a heartbeat from `metrics.json`
to an approved private monitor; alert when the heartbeat is stale, queue age
increases, disk is near capacity or a source exceeds its latency target. An
external observer is needed to detect a stopped VM; a local file alone cannot.

The single-writer lock is mandatory. Do not run independent writers against
different SQLite disks for the same source. Back up the SQLite database using
SQLite's backup API, not a live copy of only its main file while WAL is active.
Protect the metrics, configuration, database and backups as private data.

JSONBin remains a configuration source. Do not upload publication archives or
per-source checkpoints there without evaluating its request and record-size
quotas. Keep its key in the private runtime's secret store. Never pass it to
public CI, pull requests, logs, release assets or build arguments.
