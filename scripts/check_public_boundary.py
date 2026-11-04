"""Fail closed on private data/configuration or credential literals in tracked files."""
from pathlib import Path
import re
import subprocess

root=Path(__file__).resolve().parents[1]
tracked=subprocess.run(['git','ls-files','-z'],cwd=root,capture_output=True,check=True).stdout.decode().split('\0')
forbidden_names={'sources.json','dsns-official-sources.json','registry.json','monitor.json',
                 'report.json','credentials.json','token.json','collection-state.json'}
patterns=[r'gh[pousr]_[A-Za-z0-9]{30,}',r'github_pat_[A-Za-z0-9_]{50,}',
          r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
          r'\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}',
          r'https://[^\s/]+\.internal(?:/|\b)',r'https://docs\.google\.com/spreadsheets/d/[A-Za-z0-9_-]{20,}',
          r'(?i)(?:client_secret|refresh_token|private_key)\s*["\']?\s*[:=]\s*["\'][^"\']{16,}']
errors=[]
for name in filter(None,tracked):
    path=Path(name)
    if (path.name in forbidden_names or path.suffix in {'.sqlite3','.db','.log','.pem','.key'} or
            path.name.startswith('.env') or any(part in {'backend','private','state','node_modules','.venv'} for part in path.parts)):
        errors.append((name,'private_file_type'))
    content=(root/path).read_bytes().decode('utf-8',errors='replace')
    for index,pattern in enumerate(patterns):
        if re.search(pattern,content):errors.append((name,'credential_or_private_endpoint_rule_'+str(index)))
if errors:
    for name,rule in errors:print(name+': '+rule)  # Never print matched values.
    raise SystemExit(1)
print('Public boundary checks passed for '+str(len(list(filter(None,tracked))))+' tracked files')
