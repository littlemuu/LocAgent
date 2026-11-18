"""Real SDK dispatch with scripted LLM only. No live transport argument or fallback."""
import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from readonly_agent.core import Limits,Trace,encoded,digest
from readonly_agent.offline import no_network
from readonly_agent.control import budget_notice
from experiments.sdk_finish_selfcheck_v7.sdk_adapter import SDK_SYSTEM
from experiments.sdk_finish_selfcheck_v7.finish_policy import SELF_CHECK_INSTRUCTION,validate_finish,audit_predictions
from .bridge import ProcessRetriever


def run_offline(*,snapshot,issue,script,output_dir,retriever,limits=Limits(max_requests=4)):
    if type(retriever) is not ProcessRetriever or retriever.snapshot_id!=snapshot.identity:raise ValueError('v8_bound_retriever_required')
    if not isinstance(issue,str) or not issue.strip() or len(issue.encode())>65536:raise ValueError('invalid_issue')
    if not isinstance(script,list):raise ValueError('explicit_script_required')
    output=Path(output_dir).resolve();output.mkdir(parents=True,exist_ok=False)
    trace=Trace(output/'trace.jsonl');responses=iter(deepcopy(script));count=0;finished=None;failure=None
    contract={'version':'sdk-hybrid-v8-offline-1','mode':'offline_scripted','quality_measured':False,'snapshot':snapshot.identity,'source_hashes':dict(snapshot.hashes),'issue_hash':digest(issue),'script_hash':digest(script),'config':retriever.config.to_dict(),'algorithm':retriever.config.algorithm,'config_hash':retriever.config.identity,'corpus_hash':retriever.corpus_id,'cache_hash':retriever.cache_hash,'limits':limits.__dict__,'embedding_kind':'synthetic-fixture' if retriever.cache else 'none','real_llm_requests':0,'real_embedding_requests':0}
    (output/'contract.json').write_bytes(encoded(contract))
    with TemporaryDirectory(prefix='sdk-hybrid-v8-') as td:
        root=Path(td)
        with no_network(root/'profiles') as attempts:
            from litellm import ModelResponse
            from pydantic import SecretStr
            from openhands.sdk import Agent,LocalConversation,LLM
            from openhands.sdk.llm import Message,TextContent
            from openhands.sdk.llm.message import MessageToolCall
            from openhands.sdk.llm.llm_response import LLMResponse
            from openhands.sdk.llm.utils.metrics import MetricsSnapshot
            from readonly_agent.openhands_tools import ToolSession,register_readonly_tools
            session=ToolSession(snapshot,retriever=retriever,limits=limits)
            def generate(llm,messages,tools=None,**kwargs):
                nonlocal count,finished,failure
                if retriever.failure:failure='retrieval_failed';raise RuntimeError(failure)
                if count>=limits.max_requests:failure='request_budget_exhausted';raise RuntimeError(failure)
                count+=1;closing=session.closed or count==limits.max_requests
                if closing:session.close_investigation()
                active=[t for t in tools if t.name=='finish'] if closing else list(tools)
                notice=budget_notice(turn=count,maximum=limits.max_requests,tool_calls_left=max(0,limits.max_tool_calls-session.calls),source_bytes_left=max(0,limits.source_bytes-session.used),closing=closing,reason='request_limit' if count==limits.max_requests else 'investigation_budget' if closing else None)
                visible=list(messages)+[Message(role='user',content=[TextContent(text=notice)])]
                request={'messages':[m.model_dump(mode='json') for m in visible],'tools':[t.to_openai_tool() for t in active],'closing':closing,'max_output_tokens':limits.max_output_tokens}
                size=len(encoded(request));trace.emit('request',number=count,serialized_bytes=size,request=request)
                if size>limits.request_bytes:failure='request_budget_exhausted';raise RuntimeError(failure)
                try:response=next(responses)
                except StopIteration:failure='script_exhausted';raise RuntimeError(failure) from None
                trace.emit('scripted_response',response=response)
                if len(encoded(response))>limits.response_bytes:failure='response_budget_exhausted';raise RuntimeError(failure)
                if response.get('stop_reason')!='tool_use':failure='missing_finish';raise RuntimeError(failure)
                calls=[b for b in response.get('content',[]) if b.get('type')=='tool_use']
                if not calls or len(calls)>16 or len({c.get('id') for c in calls})!=len(calls):failure='protocol_error';raise RuntimeError(failure)
                if any(c['name']=='finish' for c in calls) and len(calls)!=1:failure='mixed_finish';raise RuntimeError(failure)
                native=[]
                for call in calls:
                    if call['name'] not in {t.name for t in active}:failure='unavailable_tool';raise RuntimeError(failure)
                    args=call['input']
                    if call['name']=='finish':
                        finished=validate_finish(args,snapshot);args={'message':encoded(finished).decode()}
                    native.append(MessageToolCall(id=call['id'],name=call['name'],arguments=encoded(args).decode(),origin='completion'))
                return LLMResponse(message=Message(role='assistant',content=[],tool_calls=native),metrics=MetricsSnapshot(model_name='offline-scripted'),raw_response=ModelResponse(id=f'fixture-{count}',choices=[]))
            llm=LLM(model='openai/gpt-4.1-mini',api_key=SecretStr('offline-not-a-key'),base_url='http://127.0.0.1:9',usage_id='offline',num_retries=0,max_output_tokens=limits.max_output_tokens)
            agent=Agent(llm=llm,tools=register_readonly_tools(session),include_default_tools=['FinishTool'],condenser=None,agent_context=None,system_prompt=SDK_SYSTEM+'\n'+SELF_CHECK_INSTRUCTION)
            def on_event(event):trace.emit('sdk_event',data=event.model_dump(mode='json'))
            with patch.object(LLM,'generate',generate),patch.object(LLM,'resolve_runtime_metadata',return_value=None):
                (root/'workspace').mkdir()
                conversation=LocalConversation(agent=agent,workspace=root/'workspace',persistence_dir=output/'sdk-events',profile_store_dir=root/'profiles',callbacks=[on_event],visualizer=None,max_iteration_per_run=limits.max_requests,stuck_detection=False,delete_on_close=False)
                try:
                    conversation.send_message(issue);conversation.run();status=conversation.state.execution_status.value
                except Exception as exc:status='error';failure=failure or type(exc).__name__
                finally:conversation.close()
            if retriever.failure:failure='retrieval_failed'
            result={'status':'completed' if status=='finished' and finished is not None and failure is None else 'failed','failure':failure,'sdk_status':status,'answer':finished,'requests':count,'tool_calls':session.calls,'source_bytes':session.used,'network_attempts':len(attempts),'real_llm_requests':0,'real_embedding_requests':0,'cost':0,'quality_measured':False,'embedding_kind':contract['embedding_kind'],'worker_calls':retriever.worker_calls,'retrieval_failure':retriever.failure,'retrieval_audit':retriever.audits,'tools':list(agent.tools_map)}
            if finished is not None:result['prediction_audit']=audit_predictions(finished,snapshot)
            trace.emit('tool_audit',audit=session.audit);trace.emit('terminal',result=result)
            (output/'result.json').write_bytes(encoded(result))
    trace.close();return result
