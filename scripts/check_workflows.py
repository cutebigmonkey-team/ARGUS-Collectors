from pathlib import Path
import re
import yaml

root=Path(__file__).resolve().parents[1]
for path in (root/'.github/workflows').glob('*.yml'):
    text=path.read_text()
    data=yaml.load(text,Loader=yaml.BaseLoader)
    assert data['permissions']=={'contents':'read'},path
    assert data['concurrency']['group'],path
    assert 'pull_request_target' not in data['on'],path
    assert 'secrets.' not in text,path
    for name,job in data['jobs'].items():
        assert job['runs-on']=='ubuntu-latest',(path,name)
        assert 1<=int(job['timeout-minutes'])<=15,(path,name)
        for step in job['steps']:
            if 'uses' in step:
                assert re.fullmatch(r'actions/[a-z-]+@[0-9a-f]{40}',step['uses']),step
    if 'schedule' in data['on']:
        assert path.name=='collector-smoke-tests.yml',path
print('Workflow security and runner checks passed')
