"""Generic pilot worker; only two already exposed development cases may replay."""
import contextlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'engine_adaptation/v4/engine')]
from experiments.cohort_preflight.entry import load_entry,load_graph,read,checked_file,sha
from experiments.cohort_preflight import body
from readonly_agent.core import encoded
from locagent_service.offline import offline_engine

def main():
    req=json.load(sys.stdin)
    catalog=read(checked_file(req['catalog'],req['catalog_sha256']))
    row=next(r for r in catalog['cases'] if r['id']==req['case_id'])
    if row['id'] not in catalog['pilot_allowlist']:raise PermissionError('development_pilot_only')
    with contextlib.redirect_stdout(sys.stderr),offline_engine():
        value,snapshot=load_entry(row['entry'],row['entry_sha256'])
        graph,retriever,module=load_graph(value,snapshot)
        if req['mode']=='query':
            result={'text':retriever.retrieve(req['query']),'snapshot':snapshot.identity}
        else:
            if req['mode']!='native':raise ValueError('unknown_mode')
            status=read(checked_file(req['body_status'],req['body_status_sha256']))
            if status['id']!=row['id'] or status['snapshot']!=snapshot.identity:raise ValueError('cross_case_body')
            br,_=body.load(snapshot,status['body_directory'],status['body_attestation_sha256'])
            from readonly_agent.journal import Ledger
            from experiments.eval_preflight.common_contract import SharedWire
            from experiments.eval_preflight.native_adapter import adapted_protocol
            from util.localizer import GraphLocalizer
            from util.localization_contract import LocalizationRequest,LocalizationOptions
            from plugins.location_tools.repo_ops import repo_ops as ops
            from unittest.mock import patch
            from litellm import ModelResponse
            import httpx
            ledger=Ledger(req['ledger'],req['plan_hash'])
            with ledger.transaction() as db:
                plan=ledger.validate(db)[0]
                if (plan['snapshot']!=snapshot.identity or plan['issue']!=value['issue']
                        or plan['cohort_entry']!={'case_id':row['id'],'entry_sha256':row['entry_sha256']}):
                    raise ValueError('cross_case_ledger')
            wire=SharedWire(ledger,'baseline',snapshot);queries=[]
            issue_query='SET TAG' if row['id'].startswith('tobymao') else 'RecursionError'
            if issue_query not in value['issue']:raise ValueError('query_not_in_issue')
            def provider(**kw):
                turn=len(wire.requests)+1
                if turn==1:name,args='search_code_snippets',{'search_terms':[issue_query]}
                elif turn==2:
                    message=next(m for m in reversed(kw['messages']) if m['role']=='tool');page=json.loads(message['content'])
                    if page['next_offset'] is not None:name,args='read_tool_output',{'output_id':page['output_id'],'offset':page['next_offset']}
                    else:name,args='get_entity_contents',{'entity_names':[sorted(snapshot.files)[0]]}
                elif turn==3:name,args='get_entity_contents',{'entity_names':[sorted(snapshot.files)[0]]}
                else:name,args='finish',{'message':{'files':[],'entities':[],'answer':'Offline fixture; no localization score.'}}
                def respond(request):
                    return httpx.Response(200,json={'id':f'fixture-{turn}','model':'deepseek-flash',
                        'choices':[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
                        'tool_calls':[{'id':f'native-{turn}','type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}}],
                        'usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}})
                raw,_,_=wire.exchange(kw['messages'],kw['tools'],kw.get('tool_choice') is not None,httpx.MockTransport(respond))
                return ModelResponse(**raw)
            engine=GraphLocalizer.from_graph(graph,provider=provider,model_name='deepseek-flash',
                module_retriever=module,bm25_index_dir=str(Path(status['body_directory']).parent),
                options=LocalizationOptions(max_iterations=4,search_protocol='bounded-v1'))
            try:
                with patch.object(ops,'bm25_content_retrieve',body.backend(br,queries)),adapted_protocol(snapshot):
                    answer=engine.localize(LocalizationRequest(row['id'],value['repo'],value['base_commit'],value['issue']))
                if answer.diagnostics['termination_reason']!='finished':raise RuntimeError('native_not_finished')
                wire.finish()
            except BaseException:
                wire.fail('native_failed');raise
            result={'simulation':True,'quality_scored':False,'case_id':row['id'],'snapshot':snapshot.identity,
                    'result':answer.to_dict(),'requests':wire.requests,'body_queries':queries,'tool_calls':wire.calls}
    sys.stdout.buffer.write(encoded(result))
if __name__=='__main__':main()
