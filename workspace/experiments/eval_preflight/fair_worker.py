"""Isolated local source/index and native-system worker. Mock transport only."""
import contextlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from experiments.eval_preflight.frozen import load,sha,ENGINE
from readonly_agent.core import encoded


def main():
    req=json.load(sys.stdin)
    sys.path.insert(0,str(ENGINE))
    from locagent_service.offline import offline_engine
    with contextlib.redirect_stdout(sys.stderr),offline_engine():
        snapshot,graph,retriever,persisted,plan=load(req)
        if req['mode']=='query':
            result={'text':retriever.retrieve(req['query']),'snapshot':snapshot.identity}
        else:
            from experiments.eval_preflight import body_index
            directory=Path(req['body_root'])/req['case']
            if req['mode']=='build_body':
                result=body_index.build(snapshot,directory)
            else:
                body,att=body_index.load(snapshot,directory,req['body_attestation_hash'])
                from experiments.eval_preflight.common_contract import SharedWire,CONTRACT
                from experiments.eval_preflight.native_adapter import adapted_protocol
                from readonly_agent.journal import Ledger
                from util.localizer import GraphLocalizer
                from util.localization_contract import LocalizationRequest,LocalizationOptions
                from plugins.location_tools.repo_ops import repo_ops as ops
                from unittest.mock import patch
                import httpx
                from litellm import ModelResponse
                wire=SharedWire(Ledger(req['ledger'],req['plan_hash']),'baseline',snapshot)
                calls=[]; body_audit=[]
                def provider(**kw):
                    turn=len(calls)+1
                    messages=kw['messages'];args=None
                    if turn==1:
                        name='search_code_snippets';args={'search_terms':['SET TAG']}
                    elif turn==2:
                        previous=next(m for m in reversed(messages) if m['role']=='tool')
                        page=json.loads(previous['content'])
                        if page['next_offset'] is not None:
                            name='read_tool_output';args={'output_id':page['output_id'],'offset':page['next_offset']}
                        else:
                            name='get_entity_contents';args={'entity_names':[sorted(snapshot.files)[0]]}
                    elif turn==3:
                        name='get_entity_contents';args={'entity_names':[sorted(snapshot.files)[0]]}
                    else:
                        name='finish';args={'message':{'files':[],'entities':[],'answer':'Scripted connectivity only; no quality claim.'}}
                    def respond(request):
                        sent=json.loads(request.content);calls.append(sent)
                        assert wire.ledger.summary()['calls'][-1]['status']=='reserved'
                        return httpx.Response(200,json={'id':'mock-native-'+str(turn),'model':'deepseek-flash',
                            'choices':[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
                            'tool_calls':[{'id':'native-'+str(turn),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}}],
                            'usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}})
                    raw,_,_=wire.exchange(messages,kw['tools'],kw.get('tool_choice') is not None,httpx.MockTransport(respond))
                    return ModelResponse(**raw)
                engine=GraphLocalizer.from_graph(graph,provider=provider,model_name='deepseek-flash',
                    options=LocalizationOptions(max_iterations=4,search_protocol='bounded-v1'),
                    module_retriever=persisted,bm25_index_dir=req['body_root'])
                try:
                    with patch.object(ops,'bm25_content_retrieve',body_index.backend(body,body_audit)),adapted_protocol(snapshot):
                        output=engine.localize(LocalizationRequest(req['case'],'tobymao/sqlglot',plan['commit'],req['issue']))
                    if output.diagnostics['termination_reason']!='finished':
                        wire.fail(output.diagnostics['termination_reason'])
                        raise RuntimeError('native_not_finished')
                    wire.finish()
                except BaseException:
                    wire.fail('native_run_failed');raise
                assert body_audit,'body_backend_not_exercised'
                result={'native_result':output.to_dict(),'requests':calls,'body_queries':body_audit,
                        'body_attestation':att,'contract':CONTRACT,'tool_calls':wire.calls,
                        'simulation':True,'real_model_requests':0,'quality':None}
    sys.stdout.buffer.write(encoded(result))

if __name__=='__main__':main()
