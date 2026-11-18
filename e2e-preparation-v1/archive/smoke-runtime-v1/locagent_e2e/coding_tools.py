from typing import ClassVar
from threading import Lock
from uuid import uuid4
from pydantic import ConfigDict,Field
from openhands.sdk import Action,Observation,Tool,ToolDefinition,register_tool
from openhands.sdk.tool import ToolExecutor,ToolAnnotations
from .common import encoded,CONFIG
class Command(Action):
 model_config=ConfigDict(extra='forbid',strict=True)
 command:str=Field(min_length=1,max_length=16000)
 timeout_seconds:int=Field(default=120,ge=1,le=120)
class View(Action):
 model_config=ConfigDict(extra='forbid',strict=True)
 path:str=Field(min_length=1,max_length=1000)
class Edit(View):
 operation:str=Field(description='create or replace; replace requires old text matching exactly once')
 content:str|None=None
 old:str|None=None
 new:str|None=None
class Output(Observation):
 @property
 def to_llm_content(self):return self.content
class Session:
 def __init__(self,sandbox):self.sandbox=sandbox;self.used=0;self.calls=0;self.closed=False;self.audit=[];self.lock=Lock()
 def execute(self,name,args):
  with self.lock:
   if self.closed:return Output.from_text('Tool evidence budget exhausted. Call finish.')
   try:
    if name=='terminal':r=self.sandbox.execute(**args)
    elif name=='view_file':r=self.sandbox.file('view',args['path'])
    else:
     if args['operation'] not in ('create','replace'):raise ValueError('invalid_operation')
     if args['operation']=='create' and args['content'] is None:raise ValueError('content_required')
     if args['operation']=='replace' and (args['old'] is None or args['new'] is None):raise ValueError('old_new_required')
     r=self.sandbox.file(**args)
   except Exception as e:r={'tool_error':type(e).__name__,'message':str(e)[:200]}
   raw=encoded(r);cap=min(CONFIG['coding']['tool_output_bytes'],CONFIG['coding']['evidence_bytes']-self.used)
   if len(raw)>cap:
    raw=raw[:max(0,cap-40)].decode('utf-8','ignore').encode()+b'\n[TRUNCATED: tool output byte limit]'
   self.used+=len(raw);self.calls+=1
   if CONFIG['coding']['evidence_bytes']-self.used<128:self.closed=True
   self.audit.append({'tool':name,'arguments':args,'result_bytes':len(raw),'exit_code':r.get('exit_code'),'tool_error':r.get('tool_error')})
   return Output.from_text(raw.decode('utf-8'),is_error=bool(r.get('tool_error')))
class Executor(ToolExecutor):
 def __init__(self,session,name):self.session=session;self.name=name
 def __call__(self,action,conversation=None):return self.session.execute(self.name,action.model_dump(exclude={'kind'}))
class Base(ToolDefinition):
 action_model:ClassVar[type[Action]]=View
 @classmethod
 def create(cls,conv_state=None,*,session):
  return [cls(description={'terminal':'Run a shell command or local tests in isolated /testbed with testbed conda environment. No network.','view_file':'Read a repository UTF-8 text file, with line numbers.','edit_file':'Create a new file or perform one exact text replacement in a repository file.'}[cls.name],action_type=cls.action_model,observation_type=Output,executor=Executor(session,cls.name),annotations=ToolAnnotations(readOnlyHint=cls.name=='view_file',destructiveHint=cls.name!='view_file',idempotentHint=False,openWorldHint=False))]
class Terminal(Base):name='terminal';action_model=Command
class ViewFile(Base):name='view_file'
class EditFile(Base):name='edit_file';action_model=Edit

def register(session):
 tools=[]
 for cls in (Terminal,ViewFile,EditFile):
  key='e2e_'+uuid4().hex;register_tool(key,cls.create(session=session)[0]);tools.append(Tool(name=key))
 return tools
