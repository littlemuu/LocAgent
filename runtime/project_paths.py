"""All application paths resolve from the one versioned project configuration."""
import json,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CONFIG=json.loads((ROOT/'project_config.json').read_text())

def path(name):
    candidate=Path(CONFIG['paths'][name])
    if candidate.is_absolute():raise ValueError('runtime_path_must_be_project_relative')
    resolved=(ROOT/candidate).resolve()
    if resolved!=ROOT and ROOT not in resolved.parents:raise ValueError('project_path_escape')
    return resolved

def deny_historical_io():
    roots=tuple(CONFIG['historical_readonly_aliases'].values())
    attempts=[]
    def audit(event,args):
        if event in ('open','os.listdir','os.scandir') and args and isinstance(args[0],(str,bytes,os.PathLike)):
            p=os.fsdecode(args[0]);p=os.path.abspath(p)
            if any(p==r or p.startswith(r+'/') for r in roots):
                attempts.append({'event':event,'path':p})
                raise PermissionError('historical_workspace_access_forbidden')
    sys.addaudithook(audit)
    return attempts
