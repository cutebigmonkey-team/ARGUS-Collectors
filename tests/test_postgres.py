"""Run the same durable-import contract against real PostgreSQL, not mocks.

ARGUS_TEST_DATABASE_URL must point to a dedicated test database: this suite
creates and removes only randomly named test schemas. Never use an archive DB.
"""
import os
import unittest
import uuid

import test_journal
from test_journal import SOURCE, result
from argus_collectors.postgres import PostgresJournal


@unittest.skipUnless(os.environ.get('ARGUS_TEST_DATABASE_URL'), 'PostgreSQL integration service not configured')
class PostgresImport(test_journal.DurableImport):
    def setUp(self):
        import psycopg
        self.integrity_error=psycopg.IntegrityError
        self.dsn=os.environ['ARGUS_TEST_DATABASE_URL']
        self.schema='argus_test_'+uuid.uuid4().hex
        self.journal=self.open_journal()

    def open_journal(self):
        return PostgresJournal(self.dsn,schema=self.schema,
                               verify_tls=os.environ.get('ARGUS_TEST_LOCAL_POSTGRES')!='1')

    def tearDown(self):
        from psycopg import sql
        # The exact generated schema belongs exclusively to this test.
        self.journal.db.connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.journal.close()

    def test_only_one_database_writer_across_processes(self):
        with self.assertRaisesRegex(RuntimeError,'collector_writer_already_running'):
            self.open_journal()
        self.journal.check_session()

    def test_failed_ack_transaction_rolls_back_all_changes(self):
        batch=self.journal.stage(SOURCE,result())
        original=self.journal._count
        def fail(name,value):
            if name=='saved_new_posts':raise RuntimeError('injected_commit_failure')
            original(name,value)
        self.journal._count=fail
        with self.assertRaisesRegex(RuntimeError,'injected_commit_failure'):
            self.ack(batch)
        self.assertEqual(self.journal.state(SOURCE),({},{}))
        self.assertEqual(self.journal.metrics()['unique_archived_identities'],0)
        self.assertEqual(len(self.journal.pending()),1)
        self.journal._count=original
        self.ack(batch)
        self.assertEqual(self.journal.metrics()['saved_new_posts'],1)

    def test_process_loss_releases_lock_and_preserves_outbox(self):
        import subprocess
        import sys
        connection=self.journal.db.connection
        connection.execute('DELETE FROM outbox')
        self.journal.close()
        program='''
import os
from argus_collectors.postgres import PostgresJournal
from test_journal import SOURCE, result
j=PostgresJournal(os.environ['ARGUS_TEST_DATABASE_URL'],schema=os.environ['ARGUS_TEST_SCHEMA'],verify_tls=os.environ.get('ARGUS_TEST_LOCAL_POSTGRES')!='1')
j.stage(SOURCE,result())
os._exit(0)
'''
        env={**os.environ,'ARGUS_TEST_SCHEMA':self.schema}
        from pathlib import Path
        env['PYTHONPATH']=os.pathsep.join([str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'src')])
        subprocess.run([sys.executable,'-c',program],env=env,check=True,capture_output=True,timeout=45)
        self.journal=self.open_journal()
        self.assertEqual(len(self.journal.pending()),1)
        self.assertEqual(self.journal.state(SOURCE),({},{}))


if __name__=='__main__':unittest.main()
