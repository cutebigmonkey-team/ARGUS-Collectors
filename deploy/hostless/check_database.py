"""One-shot cloud verification, synthetic records only, sanitized output."""
import io
import json
import os
from pathlib import Path
import sys
import unittest

dsn=os.environ.get('DATABASE_URL')
if not dsn:
    print(json.dumps({'level':'error','check':'postgres','reason':'database_url_missing'}),flush=True)
    sys.exit(1)
os.environ['ARGUS_TEST_DATABASE_URL']=dsn
os.environ.pop('ARGUS_TEST_LOCAL_POSTGRES',None)  # Cloud ALWAYS verifies TLS.
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'tests'))
try:
    from test_postgres import PostgresImport
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(PostgresImport)
    # Tracebacks may contain private URI/row details; keep them out of cloud logs.
    result=unittest.TextTestRunner(stream=io.StringIO(),failfast=True).run(suite)
    print(json.dumps({'level':'info' if result.wasSuccessful() else 'error',
                      'check':'postgres_recovery','tests':result.testsRun,
                      'failures':len(result.failures),'errors':len(result.errors),
                      'failed_tests':[test.id().split('.')[-1] for test,_ in result.failures+result.errors],
                      'tls_verification':'required','production_collection':False}),flush=True)
    sys.exit(0 if result.wasSuccessful() else 1)
except Exception as error:
    print(json.dumps({'level':'error','check':'postgres_recovery','error_type':type(error).__name__}),flush=True)
    sys.exit(1)
