"""Real OpenHands conversation and tool dispatch; explicit no-retry wire only."""
import json,time,os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from .common import CONFIG,ROOT,encoded,write_json,digest
os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True',DO_NOT_TRACK='1',OTEL_SDK_DISABLED='true',OPENHANDS_SUPPRESS_BANNER='1',HF_HUB_OFFLINE='1')
from readonly_agent.offline import no_network
# Imports are offline; only explicit transport can call the provider later.
with TemporaryDirectory() as _td, no_network(Path(_td)):
 from openhands.sdk import Agent,LLM,LocalConversation
 from openhands.sdk.llm import Message,TextContent
 from openhands.sdk.llm.llm_response import LLMResponse
 from openhands.sdk.llm.utils.metrics import MetricsSnapshot
 from litellm import ModelResponse
 from pydantic import SecretStr
from .coding_tools import Session,register

def run(*,issue,output,transport,sandbox=None,packet=None,locator=None,scripted=False):
 output=Path(output);output.mkdir(parents=True,exist_ok=False);start=time.monotonic();count=0;failure=None;finished=None;events=[]
 is_locator=locator is not None;budget=CONFIG['locator' if is_locator else 'coding']
 if is_locator:
  from readonly_agent.core import Limits
  from readonly_agent.openhands_tools import ToolSession,register_readonly_tools
  from readonly_agent.control import budget_notice
  from readonly_agent.deepseek_wire import payload as locator_payload,normalize
  from .locator_policy import SDK_SYSTEM
  from experiments.sdk_finish_selfcheck_v7.finish_policy import SELF_CHECK_INSTRUCTION,validate_finish
  session=ToolSession(locator.snapshot,retriever=locator,limits=Limits(max_requests=4));tools=register_readonly_tools(session);prompt=SDK_SYSTEM+'\n'+SELF_CHECK_INSTRUCTION
 else:session=Session(sandbox);tools=register(session);prompt=(ROOT/'config/coding-system.txt').read_text()
 record_start=len(transport.records)
 def generate(llm,messages,tools=None,**kwargs):
  nonlocal count,failure,finished
  used=transport.records[record_start:];pt=sum(r['usage'].get('prompt_tokens',0) for r in used);ct=sum(r['usage'].get('completion_tokens',0) for r in used)
  if count>=budget['max_requests'] or time.monotonic()-start>=budget['timeout_seconds']:raise RuntimeError('agent_request_or_time_budget')
  count+=1;closing=session.closed or count==budget['max_requests'];active=[t for t in tools if t.name=='finish'] if closing else list(tools)
  if is_locator:
   if closing:session.close_investigation()
   notice=budget_notice(turn=count,maximum=budget['max_requests'],tool_calls_left=max(0,16-session.calls),source_bytes_left=max(0,14336-session.used),closing=closing,reason='request_limit' if closing else None)
   visible=list(messages)+[Message(role='user',content=[TextContent(text=notice)])]
   body=json.loads(locator_payload(visible,active,closing=closing))
  else:
   visible=list(messages)+[Message(role='user',content=[TextContent(text=f'Controller: request {count}/{budget["max_requests"]}; remaining tool evidence {budget["evidence_bytes"]-session.used} bytes.'+(' Call finish now; tools are closed.' if closing else ''))])]
   wire=[m.to_chat_dict(cache_enabled=False,vision_enabled=False,function_calling_enabled=True,force_string_serializer=True,send_reasoning_content=False) for m in visible]
   body={'model':CONFIG['model'],'messages':wire,'tools':[t.to_openai_tool() for t in active],'temperature':CONFIG['temperature'],'thinking':CONFIG['thinking'],'stream':False,'max_tokens':budget['max_output_tokens'],'tool_choice':{'type':'function','function':{'name':'finish'}} if closing else 'auto'}
  input_bound=len(encoded(body))+4096
  if pt+input_bound>budget['input_tokens'] or ct+body['max_tokens']>budget['output_tokens']:raise RuntimeError('agent_token_budget')
  raw=transport.exchange(body)
  choices=raw.get('choices',[])
  if len(choices)!=1 or choices[0].get('finish_reason')!='tool_calls':raise RuntimeError('missing_tool_or_truncated_response')
  calls=choices[0]['message'].get('tool_calls',[]);names={t.name for t in active}
  if not calls or any(c['function']['name'] not in names for c in calls):raise RuntimeError('unavailable_tool')
  if any(c['function']['name']=='finish' for c in calls) and len(calls)!=1:raise RuntimeError('mixed_finish')
  if is_locator:
   response=normalize(raw,names,closing=closing)
   for call in response.message.tool_calls or []:
    if call.name=='finish':finished=validate_finish(json.loads(json.loads(call.arguments)['message']),locator.snapshot)
  else:
   native=ModelResponse(**raw);response=LLMResponse(message=Message.from_llm_chat_message(native.choices[0].message),raw_response=native,metrics=MetricsSnapshot(model_name=raw.get('model','unknown')))
   if calls[0]['function']['name']=='finish':finished=json.loads(calls[0]['function']['arguments']).get('message')
  return response
 llm=LLM(model='openai/deepseek-flash',api_key=SecretStr('transport-supplies-credential'),base_url='http://127.0.0.1:9',num_retries=0,max_output_tokens=budget['max_output_tokens'])
 agent=Agent(llm=llm,tools=tools,include_default_tools=['FinishTool'],condenser=None,agent_context=None,system_prompt=prompt)
 with TemporaryDirectory(prefix='e2e-sdk-') as td,patch.object(LLM,'generate',generate),patch.object(LLM,'resolve_runtime_metadata',return_value=None):
  workspace=Path(td)/'empty-sdk-workspace';workspace.mkdir()
  conversation=LocalConversation(agent=agent,workspace=workspace,persistence_dir=output/'events',profile_store_dir=Path(td)/'profiles',visualizer=None,max_iteration_per_run=budget['max_requests'],stuck_detection=False,delete_on_close=False)
  try:
   text=issue if is_locator else encoded({'issue':issue,'localization_packet':packet}).decode()
   conversation.send_message(text);conversation.run();status=conversation.state.execution_status.value
  except Exception as e:status='error';failure=type(e).__name__+': '+str(e)[:250]
  finally:conversation.close()
 records=transport.records[record_start:]
 result={'status':('completed' if status=='finished' and finished is not None and not failure else 'budget_exhausted' if not is_locator and failure and ('agent_request_or_time_budget' in failure or 'agent_token_budget' in failure) else 'failed'),'technical_failure':failure,'requests':count,'prompt_tokens':sum(r['usage'].get('prompt_tokens',0) for r in records),'completion_tokens':sum(r['usage'].get('completion_tokens',0) for r in records),'cost_upper_cny':sum(r.get('charged_upper_microcny',0) for r in records)/1e6,'actual_model_ids':sorted({r['actual_model'] for r in records}),'elapsed_seconds':time.monotonic()-start,'finished':finished,'source_bytes':session.used,'tool_calls':session.calls,'tool_audit':session.audit,'scripted':scripted,'system_prompt_sha256':digest(prompt),'tool_schema_sha256':digest([t.to_openai_tool() for t in agent.tools_map.values()]),'budget':budget}
 write_json(output/'result.json',result);return result
