from dataclasses import replace
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import unittest

from argus_collectors.api import CollectionResult
from argus_collectors.cli import deliver
from argus_collectors.journal import Journal
from argus_collectors.transport import DeliveryError, HttpsSink

SOURCE={'id':'fixture','platform':'rss','url':'https://example.org/feed'}


def result():
    stamp=datetime.now(timezone.utc).isoformat()
    post={'canonical_key':'rss:fixture','external_id':'rss:fixture','source_id':'fixture',
          'platform':'rss','post_url':'https://example.org/news/1','text':'Example',
          'published_at':stamp,'collected_at':stamp,'media':[],'media_urls':[]}
    return CollectionResult([post],'ok',[],{'pending':['https://example.org/page/2']},stamp,0.01)


class DurableImport(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.path=Path(self.directory.name)/'state.sqlite3'
        self.journal=Journal(self.path)

    def tearDown(self):
        self.journal.close()
        self.directory.cleanup()

    def ack(self,batch,inserted=True):
        self.journal.acknowledge(batch,{'batch_id':batch,'accepted_ids':['rss:fixture'],
                                     'inserted_ids':['rss:fixture'] if inserted else []})

    def test_restart_replays_same_batch_before_cursor_commit(self):
        batch=self.journal.stage(SOURCE,result())
        self.assertEqual(self.journal.state(SOURCE),({},{}))
        self.journal.close();self.journal=Journal(self.path)
        self.assertEqual(self.journal.pending()[0]['id'],batch)
        self.ack(batch)
        self.assertEqual(self.journal.state(SOURCE)[0]['pending'],['https://example.org/page/2'])
        self.assertEqual(self.journal.pending(),[])

    def test_partial_ack_cannot_lose_data(self):
        batch=self.journal.stage(SOURCE,result())
        with self.assertRaisesRegex(ValueError,'incomplete_archive_acknowledgement'):
            self.journal.acknowledge(batch,{'batch_id':batch,'accepted_ids':[],'inserted_ids':[]})
        self.assertEqual(self.journal.state(SOURCE),({},{}))
        self.assertEqual(len(self.journal.pending()),1)

    def test_duplicate_ack_and_import_are_idempotent(self):
        batch=self.journal.stage(SOURCE,result());self.ack(batch);self.ack(batch)
        batch=self.journal.stage(SOURCE,result());self.ack(batch,False)
        metrics=self.journal.metrics()
        self.assertEqual(metrics['saved_new_posts'],1)
        self.assertEqual(metrics['unique_archived_identities'],1)
        self.assertEqual(metrics['already_archived_posts'],1)

    def test_partial_collection_keeps_previous_cursor(self):
        batch=self.journal.stage(SOURCE,result());self.ack(batch)
        cursor=self.journal.state(SOURCE)[0]
        batch=self.journal.stage(SOURCE,replace(result(),status='http_429',checkpoint={'pending':[]}))
        self.ack(batch,False)
        self.assertEqual(self.journal.state(SOURCE)[0],cursor)
        self.assertEqual(self.journal.metrics()['rate_limits'],1)

    def test_only_one_pending_batch_per_source(self):
        import sqlite3
        self.journal.stage(SOURCE,result())
        with self.assertRaises(sqlite3.IntegrityError):self.journal.stage(SOURCE,result())
        self.assertEqual(self.journal.metrics()['checked_sources'],1)

    def test_delivery_failure_is_durable_and_backed_off(self):
        class Sink:
            def send(self,payload):raise DeliveryError('import_unavailable')
        batch=self.journal.stage(SOURCE,result());deliver(self.journal,Sink())
        pending=self.journal.pending()[0]
        self.assertEqual(pending['id'],batch)
        self.assertEqual(pending['failures'],1)
        self.assertGreater(datetime.fromisoformat(pending['retry_at']),datetime.now(timezone.utc))
        self.assertEqual(self.journal.state(SOURCE),({},{}))

    def test_source_url_change_resets_state(self):
        batch=self.journal.stage(SOURCE,result());self.ack(batch)
        self.assertEqual(self.journal.state({**SOURCE,'url':'https://example.org/new'}),({},{}))

    def test_rate_limit_cools_down_all_sources_on_host(self):
        batch=self.journal.stage(SOURCE,replace(result(),status='http_429',posts=[],checkpoint=None))
        self.journal.acknowledge(batch,{'batch_id':batch,'accepted_ids':[],'inserted_ids':[]})
        self.assertFalse(self.journal.host_ready({**SOURCE,'url':'https://www.example.org/other'}))
        self.assertTrue(self.journal.host_ready({**SOURCE,'url':'https://unrelated.example/feed'}))

    def test_https_required_and_no_query_credentials(self):
        for url in ('http://example.org/import','https://user:pass@example.org/import',
                    'https://example.org/import?token=abc'):
            with self.assertRaises(ValueError):HttpsSink(url,'test')


if __name__=='__main__':unittest.main()
