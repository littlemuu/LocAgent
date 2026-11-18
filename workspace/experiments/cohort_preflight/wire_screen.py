"""Initial wire-size upper screening from frozen successful templates, no requests."""
from copy import deepcopy
from .entry import ROOT,read,save,sha
from readonly_agent.core import encoded
from experiments.eval_preflight.common_contract import raw_payload
OUT=ROOT/'verification/cohort-preflight-v1'
def main():
    cat=read(OUT/'runtime-catalog.json');id='tobymao__sqlglot-3417'
    original=read(next(r['entry'] for r in cat['cases'] if r['id']==id))['issue']
    native_path=OUT/'pilot-v2'/id/'native.json';sdk_path=OUT/'pilot-v2'/id/'sdk/wire-requests.json'
    templates={'native':read(native_path)['requests'][0],'sdk':read(sdk_path)[0]};rows=[]
    for row in cat['cases']:
        value=read(row['entry']);sizes={}
        for system,template in templates.items():
            messages=deepcopy(template['messages']);found=0
            for message in messages:
                content=message.get('content')
                if isinstance(content,str) and original in content:
                    message['content']=content.replace(original,value['issue']);found+=1
            if found!=1:raise ValueError('initial_issue_template_not_unique')
            data=raw_payload(messages,template['tools'],closing=False)
            # Native task-prefix owner names vary. This allowance exceeds the
            # maximum case-ID byte bound in this frozen cohort; no issue is cut.
            upper=len(data)+(512 if system=='native' else 0)
            sizes[system]=upper
        rows.append({'id':row['id'],'issue_utf8_bytes':len(value['issue'].encode()),
            'old_sdk_8192_gate_rejects':len(value['issue'].encode())>8192,
            'initial_wire_upper_bytes':sizes,'initial_wire_fits':max(sizes.values())<=65536})
    save(OUT/'initial-wire-screen.json',{'checked':len(rows),'fit':sum(r['initial_wire_fits'] for r in rows),
        'failed':sum(not r['initial_wire_fits'] for r in rows),'unchecked':0,
        'old_sdk_gate_rejected':sum(r['old_sdk_8192_gate_rejects'] for r in rows),
        'max_issue_bytes':max(r['issue_utf8_bytes'] for r in rows),
        'max_wire_upper_bytes':max(max(r['initial_wire_upper_bytes'].values()) for r in rows),
        'method':'Frozen successful first-request templates; full issue substitution; native prefix 512-byte conservative allowance.',
        'not_full_trajectory_execution':True,'model_requests':0,
        'template_hashes':{'native':sha(native_path),'sdk':sha(sdk_path)},'rows':rows})
    print('Initial request screening complete; full trajectory validation remains 2/130.')
if __name__=='__main__':main()
