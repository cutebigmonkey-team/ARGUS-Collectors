"""One bounded collection pass; production scheduling belongs to the cloud host."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from .api import collect, SUPPORTED
from .journal import Journal
from .transport import HttpsSink, DeliveryError


@contextmanager
def single_writer(path):
    # This entry point targets Linux cloud VMs. No listening ports are needed.
    import fcntl
    with open(str(path)+'.lock','a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(handle,fcntl.LOCK_UN)


def deliver(journal,sink):
    for row in journal.pending():
        if row['retry_at'] and datetime.fromisoformat(row['retry_at'])>datetime.now(timezone.utc):
            continue
        payload=json.loads(row['payload'])
        try:
            receipt=sink.send(payload) if payload['result']['posts'] else {
                'batch_id':row['id'],'accepted_ids':[],'inserted_ids':[]}
            journal.acknowledge(row['id'],receipt)
        except DeliveryError as error:
            journal.defer(row['id'],error.code,error.retry_after)
        except (ValueError,TypeError,KeyError,AttributeError):
            journal.defer(row['id'],'invalid_archive_acknowledgement')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--metrics',type=Path,required=True)
    parser.add_argument('--max-sources',type=int,default=20)
    args=parser.parse_args()
    if not 1<=args.max_sources<=1000:parser.error('invalid source budget')
    sources=json.loads(args.sources.read_text(encoding='utf-8'))
    if isinstance(sources,dict):sources=sources['sources']
    if not isinstance(sources,list) or len({str(s['id']) for s in sources})!=len(sources):
        parser.error('source IDs must be unique')
    if any(s.get('platform') not in SUPPORTED for s in sources):
        parser.error('unsupported platform; retain its existing production collector')
    sink=HttpsSink(os.environ.get('ARGUS_IMPORT_URL',''),os.environ.get('ARGUS_IMPORT_TOKEN',''))
    args.state.parent.mkdir(parents=True,exist_ok=True)
    with single_writer(args.state):
        journal=Journal(args.state)
        try:
            deliver(journal,sink)
            due=[]
            for source in sources:
                cursor,health=journal.state(source)
                when=health.get('next_check_at')
                if not journal.pending(source['id']) and (not when or datetime.fromisoformat(when)<=datetime.now(timezone.utc)):
                    due.append((when or '',str(source['id']),source,cursor))
            for _,_,source,cursor in sorted(due)[:args.max_sources]:
                if not journal.host_ready(source):
                    continue
                journal.stage(source,collect(source,cursor))
                deliver(journal,sink)
            deliver(journal,sink)
            metrics=journal.metrics()
            metrics['runtime_last_tick_at']=datetime.now(timezone.utc).isoformat()
            args.metrics.parent.mkdir(parents=True,exist_ok=True)
            temporary=args.metrics.with_suffix('.tmp')
            temporary.write_text(json.dumps(metrics),encoding='utf-8')
            temporary.replace(args.metrics)
            # Keep source URLs, content and credentials out of service logs.
            print(json.dumps({k:v for k,v in metrics.items() if k!='sources'}))
        finally:
            journal.close()
