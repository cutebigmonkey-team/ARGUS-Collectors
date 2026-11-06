# ARGUS-Collectors
  
Independent Python collection modules extracted from ARGUS. The application,
source catalogs, credentials, storage writers and operational reports remain private.

Version 0.1.0 is a staged library release, **not a completed production migration**.
It includes RSS/Atom, public article metadata and sitemaps, Telegram public HTML
history, YouTube native Atom, identity normalization and polling health logic.
Other platform collectors remain in the private deployment until their dependencies
and output parity are verified. No empty platform modules are provided.

## Install and test

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps .
python -m unittest discover -s tests -v
```

Python 3.12 and 3.13 are tested in CI. These workflows use synthetic offline
fixtures; they do not run production collection or require any private secrets.
No Playwright installation is needed for this release.

## Public API

```python
from argus_collectors import collect

source = {"id": "example", "platform": "rss", "url": "https://example.org/feed"}
result = collect(source, previous={}, max_pages=3, max_posts=1000, seconds=45)
# Deliver result.posts using the private deployment's approved writer.
# Commit result.checkpoint only AFTER durable archive acknowledgement.
```

Records retain `canonical_key`, `source_id`, `platform`, `post_url`, `text`,
`published_at`, `observed_at`, `collected_at`, `media` and `media_urls`.
`external_id` is an additive alias of `canonical_key`. Unknown publication dates
remain unknown. Media files are not downloaded. Source ownership checks, robots
rules, login/challenge stops and bounded continuation are retained.

Telegram uses the existing HTML fallback by default. Pass `telegram_parser` to
retain a deployment's enhanced parser chain; equivalence to that full chain is
not claimed. YouTube resolves ownership from the supplied public source instead
of using any private channel-pin file. Optional article enrichment is used only
if its libraries are already installed; those optional paths are not covered by
the minimal dependency lock or the initial compatibility claim.

## Delivery and recovery

`Journal` persists a pending batch before upload, then commits its cursor only
after acknowledgement of every canonical identity. A restart retries the same
batch ID. The receiver must atomically enforce `Idempotency-Key`, upsert canonical
identities, and return the same stored receipt for a repeated batch. The durable
outbox is not a replacement for server-side idempotency.

The optional `HttpsSink` implements the contract in [integration.md](docs/integration.md).
It is **not an existing ARGUS endpoint**. Keep using the approved private storage
writer until that endpoint or an equivalent adapter has been implemented and
verified. JSONBin is suitable for a private configuration registry, not for
executing collectors. No JSONBin, Drive or import credential belongs in this repo.

## Cloud deployment

The `deploy/` systemd units and Dockerfile are deployment templates. They are not
enabled automatically. The CLI targets a Linux VM with a persistent volume,
holds a single-writer process lock, polls due sources and keeps private metrics
on disk. It exposes no inbound HTTP port.

Before enabling the timer, provision the runtime, install a pinned release,
configure supported sources and an authenticated approved import endpoint, then
complete [the cutover gates](docs/migration.md). Keep the private jobs active
until equivalence and recovery are proven. There is no home-PC dependency in
the target deployment.

## Releases and licensing

Tags `v*` run tests and create a GitHub Release with wheel, source distribution
and SHA-256 checksums. Consumers should pin the version and verify the checksum;
never install a moving branch in production.

No third-party collector source trees or private Git history are included.
`PROVENANCE.json` records hashes for the explicitly selected original modules.
No open-source license grant has been inferred for the original application
code; repository visibility alone is not a software license. The owner must
choose a license before advertising unrestricted reuse. Dependency license
metadata is documented in [THIRD_PARTY.md](THIRD_PARTY.md).
