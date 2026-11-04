"""Durable outbox; archive acknowledgement and checkpoint commit are atomic.

This is a single-writer component. The service must hold the process lock while
collecting and delivering. Remote import must enforce Idempotency-Key atomically.
"""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
import uuid
from urllib.parse import urlsplit

from .api import SUCCESS
from .source_health import update


class Journal:
    outbox_order = 'rowid'
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, url TEXT NOT NULL,
                checkpoint TEXT NOT NULL, health TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY, source_id TEXT UNIQUE NOT NULL,
                payload TEXT NOT NULL, failures INTEGER NOT NULL DEFAULT 0,
                retry_at TEXT, last_error TEXT);
            CREATE TABLE IF NOT EXISTS seen (identity TEXT PRIMARY KEY, digest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS metrics (name TEXT PRIMARY KEY, value INTEGER NOT NULL);
        ''')

    def close(self):
        self.db.close()

    def state(self, source):
        row = self.db.execute('SELECT * FROM sources WHERE id=?', (str(source['id']),)).fetchone()
        if not row or row['url'] != source['url']:
            return {}, {}
        return json.loads(row['checkpoint']), json.loads(row['health'])

    def pending(self, source_id=None):
        if source_id is None:
            return self.db.execute('SELECT * FROM outbox ORDER BY '+self.outbox_order).fetchall()
        return self.db.execute('SELECT * FROM outbox WHERE source_id=?', (str(source_id),)).fetchone()

    def host_ready(self, source):
        host=urlsplit(source['url']).hostname.removeprefix('www.')
        for row in self.db.execute('SELECT url,health FROM sources'):
            if urlsplit(row['url']).hostname.removeprefix('www.')!=host:
                continue
            until=json.loads(row['health']).get('host_cooldown_until')
            if until and datetime.fromisoformat(until)>datetime.now(timezone.utc):
                return False
        return True

    def _count(self, key, value):
        self.db.execute('INSERT INTO metrics VALUES (?,?) ON CONFLICT(name) DO UPDATE SET value=metrics.value+excluded.value', (key,value))

    def stage(self, source, result):
        """Persist before sending; keep enrichments even for existing identities."""
        _, health = self.state(source)
        batch_id = str(uuid.uuid4())
        records = list({p['canonical_key']:p for p in result.posts}.values())
        payload = {'schema':'argus-collector-batch-v1', 'batch_id':batch_id,
                   'source':source, 'result':{**asdict(result), 'posts':records}, 'previous_health':health}
        with self.db:
            self.db.execute('INSERT INTO outbox(id,source_id,payload) VALUES (?,?,?)',
                            (batch_id, str(source['id']), json.dumps(payload)))
            self._count('checked_sources', 1)
            self._count('found_posts', len(records))
            self._count('rate_limits', int(result.status in ('http_429','rate_limited')))
            self._count('collection_errors', int(result.status not in SUCCESS))
        return batch_id

    def acknowledge(self, batch_id, receipt):
        row = self.db.execute('SELECT payload FROM outbox WHERE id=?', (batch_id,)).fetchone()
        if row is None:
            return  # Duplicate acknowledgement after a committed transaction.
        payload = json.loads(row['payload'])
        source = payload['source']; result = payload['result']; posts = result['posts']
        expected = {p['canonical_key'] for p in posts}
        accepted = receipt.get('accepted_ids')
        inserted = receipt.get('inserted_ids')
        if (receipt.get('batch_id') != batch_id or not isinstance(accepted,list) or
                not all(isinstance(k,str) for k in accepted) or set(accepted) != expected or
                not isinstance(inserted,list) or not all(isinstance(k,str) for k in inserted) or
                not set(inserted) <= expected or len(inserted) != len(set(inserted))):
            raise ValueError('incomplete_archive_acknowledgement')
        previous_cursor, _ = self.state(source)
        published = [(p['published_at'],p['canonical_key']) for p in posts if p.get('published_at')]
        latest = max(published, default=(None,None))
        lags = [(datetime.fromisoformat(result['checked_at'])-datetime.fromisoformat(stamp)).total_seconds()
                for stamp,_ in published]
        record = {'url':source['url'], 'platform':source['platform'], 'checked_at':result['checked_at'],
                  'status':result['status'], 'new_keys':inserted, 'canonical_keys':sorted(expected),
                  'attempts':result['attempts'], 'seconds':result['seconds'], 'retry_after':result['retry_after'],
                  'latest_published_at':latest[0], 'latest_post_id':latest[1], 'collector_rows':len(posts),
                  'delivery':{'saved_ids':sorted(expected)},
                  'collection_latency':{'max_seconds':max(lags,default=None),'samples':len(lags)}}
        health = update(payload['previous_health'], record)
        cursor = result['checkpoint'] if result['status'] in SUCCESS and result['checkpoint'] is not None else previous_cursor
        with self.db:
            self.db.execute('INSERT INTO sources VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET '
                            'url=excluded.url,checkpoint=excluded.checkpoint,health=excluded.health',
                            (str(source['id']),source['url'],json.dumps(cursor),json.dumps(health)))
            for post in posts:
                digest = hashlib.sha256(json.dumps(post,sort_keys=True).encode()).hexdigest()
                self.db.execute('INSERT INTO seen VALUES (?,?) ON CONFLICT(identity) DO UPDATE SET digest=excluded.digest',
                                (post['canonical_key'], digest))
            self._count('saved_new_posts',len(inserted))
            self._count('already_archived_posts',len(expected)-len(inserted))
            self.db.execute('DELETE FROM outbox WHERE id=?',(batch_id,))

    def defer(self, batch_id, code, retry_after=None):
        row=self.db.execute('SELECT failures FROM outbox WHERE id=?',(batch_id,)).fetchone()
        failures=row['failures']+1
        until=datetime.now(timezone.utc)+timedelta(seconds=min(3600,15*2**min(failures,8)))
        if retry_after:
            until=max(until,retry_after)
        with self.db:
            self.db.execute('UPDATE outbox SET failures=?,retry_at=?,last_error=? WHERE id=?',
                            (failures,until.isoformat(),code,batch_id))

    def metrics(self):
        values={row['name']:row['value'] for row in self.db.execute('SELECT name,value FROM metrics')}
        values['queue_depth']=self.db.execute('SELECT count(*) AS count FROM outbox').fetchone()['count']
        values['unique_archived_identities']=self.db.execute('SELECT count(*) AS count FROM seen').fetchone()['count']
        values['sources']=[{'source_id':r['id'],**json.loads(r['health'])}
                           for r in self.db.execute('SELECT id,health FROM sources')]
        return values
